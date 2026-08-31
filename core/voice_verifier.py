"""
voice_verifier.py — Dual Notary Verification Engine (Voice Reading + Image OCR Cross-Verification)
Transcribes spoken notary contract reading audio and verifies extracted variables (CINs, names, amounts, dates, locations).
"""

import io
import json
import re
import os
from ocr_engine import _post_json, _classify_google_failure, _classify_network_failure, _render_failure

def safe_log(msg: str):
    """Safely prints strings without Windows cp1252 UnicodeEncodeError crashes."""
    try:
        clean_msg = str(msg).encode("ascii", errors="replace").decode("ascii")
        print(clean_msg)
    except Exception:
        # (c) Safe. This function exists purely to make printing never crash;
        # a print that still fails has nowhere left to report to.
        pass

def _normalise_audio_mime(mime_type: str) -> str:
    """
    Maps whatever the UI recorded to a MIME type Gemini actually accepts.

    The microphone writes AAC inside an MPEG-4 container, which arrives here as
    "audio/mp4" or "audio/aac"; both must map to audio/mp4, not to the audio/wav
    default, or the payload is described to the API as a format it is not.
    """
    mt = (mime_type or "").lower().strip()
    if not mt:
        return "audio/wav"
    if "mp3" in mt or "mpeg" in mt:
        return "audio/mp3"
    if "m4a" in mt or "mp4" in mt or "aac" in mt:
        return "audio/mp4"
    if "ogg" in mt or "opus" in mt:
        return "audio/ogg"
    if "flac" in mt:
        return "audio/flac"
    if "wav" in mt or "wave" in mt or "x-wav" in mt:
        return "audio/wav"
    return "audio/wav"


def _whisper_filename(mime_type: str) -> str:
    """Whisper infers the codec from the filename extension, so it must match the real container."""
    ext = {
        "audio/mp3": "mp3",
        "audio/mp4": "m4a",
        "audio/ogg": "ogg",
        "audio/flac": "flac",
        "audio/wav": "wav",
    }.get(_normalise_audio_mime(mime_type), "wav")
    return f"recording.{ext}"


def downsample_wav_to_16k_mono(audio_bytes: bytes) -> tuple[bytes, str]:
    """
    Downsamples uncompressed WAV audio (e.g. 44.1kHz stereo) to 16kHz Mono 16-bit PCM.
    Reduces payload size by up to 85% (e.g. 2.3 MB -> 400 KB), speeding up API upload & processing by 5x!
    """
    if not audio_bytes or len(audio_bytes) < 44 or audio_bytes[:4] != b"RIFF":
        return audio_bytes, "audio/wav"
    try:
        import io, wave
        import numpy as np

        with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            n_frames = wf.getnframes()
            pcm_data = wf.readframes(n_frames)

        if n_channels == 1 and framerate <= 16000 and sampwidth == 2:
            return audio_bytes, "audio/wav"

        if sampwidth != 2:
            return audio_bytes, "audio/wav"

        samples = np.frombuffer(pcm_data, dtype=np.int16)
        if n_channels == 2:
            samples = ((samples[0::2].astype(np.int32) + samples[1::2].astype(np.int32)) // 2).astype(np.int16)

        if framerate > 16000:
            step = framerate / 16000.0
            indices = (np.arange(0, len(samples) / step) * step).astype(np.int64)
            indices = indices[indices < len(samples)]
            samples = samples[indices]
            framerate = 16000

        out_io = io.BytesIO()
        with wave.open(out_io, "wb") as out_wf:
            out_wf.setnchannels(1)
            out_wf.setsampwidth(2)
            out_wf.setframerate(framerate)
            out_wf.writeframes(samples.tobytes())

        return out_io.getvalue(), "audio/wav"
    except Exception:
        return audio_bytes, "audio/wav"


# How long one REST attempt may take. Audio is uploaded inline, so its
# deadline has to cover the upload as well as the model's own work.
TEXT_TIMEOUT_S = 15
AUDIO_TIMEOUT_S = 120


def call_gemini_api(prompt: str, audio_bytes: bytes = None, mime_type: str = "audio/wav", api_key: str = "", model_name: str = "gemini-2.5-flash") -> str:
    """
    Primary Gemini API caller using direct REST API + GenAI SDK engine.
    Supports gemini-2.5-flash with automatic rate limit retry & fallback.
    """
    import base64
    import time
    import sys
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    if audio_bytes and ("wav" in mime_type or "wave" in mime_type):
        t_ds_start = time.perf_counter()
        orig_sz = len(audio_bytes)
        audio_bytes, mime_type = downsample_wav_to_16k_mono(audio_bytes)
        new_sz = len(audio_bytes)
        t_ds_dur = time.perf_counter() - t_ds_start
        pct = ((orig_sz - new_sz) / orig_sz) * 100 if orig_sz else 0
        sys.stdout.write(f"[TIMING] Audio Downsampling: {orig_sz:,} bytes -> {new_sz:,} bytes ({pct:.1f}% payload reduction) in {t_ds_dur:.3f}s\n")
        sys.stdout.flush()

    keys = [k.strip() for k in api_key.replace('\n', ',').replace(';', ',').split(',') if k.strip()] if api_key else []
    if not keys:
        raise ValueError("يرجى إدخال مفاتيح API Key الخاصة بك في لوحة إعدادات الذكاء الاصطناعي.")

    last_failure = ("server", "")

    m_type = _normalise_audio_mime(mime_type)

    model_pairs = [
        ("v1beta", "gemini-3.6-flash"),
        ("v1beta", "gemini-2.5-flash")
    ]

    last_ex = None

    for key_idx, current_key in enumerate(keys):
        clean_k = current_key.strip().strip("'").strip('"')
        os.environ["GEMINI_API_KEY"] = clean_k

        key_failed = False
        # 1. Primary Direct REST API (Supports text & audio inline_data)
        for api_ver, model_id in model_pairs:
            rest_url = f"https://generativelanguage.googleapis.com/{api_ver}/models/{model_id}:generateContent?key={clean_k}"
            headers = {"Content-Type": "application/json", "x-goog-api-key": clean_k}
            
            parts = [{"text": prompt}]
            if audio_bytes:
                b64_aud = base64.b64encode(audio_bytes).decode('utf-8')
                parts.append({"inline_data": {"mime_type": m_type, "data": b64_aud}})
                
            payload = {"contents": [{"parts": parts}]}
            try:
                # 15 s was fine for a text prompt and hopeless for audio: a
                # dictation is a megabyte or two once base64-encoded, and the
                # upload alone outlasts the deadline. Both REST attempts then
                # timed out and the SDK fallback did the real work — measured at
                # 59.7 s for a call the SDK finished in about 30, so half that
                # time was two deadlines expiring before anything was tried.
                r = _post_json(rest_url, headers, payload,
                               timeout=AUDIO_TIMEOUT_S if audio_bytes else TEXT_TIMEOUT_S)
                if r.status_code == 200:
                    resp_json = r.json()
                    candidates = resp_json.get("candidates", [])
                    if candidates:
                        content = candidates[0].get("content", {})
                        parts = content.get("parts", [])
                        return "".join([p.get("text", "") for p in parts]).strip()
                    return ""
                elif r.status_code in (429, 403, 400):
                    last_failure = _classify_google_failure(r.status_code, r.text, key_idx)
                    key_failed = True
                    break  # key failed due to quota/invalid -> move straight to next key
                else:
                    last_failure = ("server", f"HTTP {r.status_code}: {r.text[:300]}")
                    continue  # Try next model!
            except Exception as ex_rest:
                last_failure = _classify_network_failure(ex_rest)

        if key_failed:
            continue  # Move straight to next key in key pool!

        # 2. SDK fallback, certificate verified
        try:
            import httpx
            from google import genai
            from google.genai import types
            part = types.Part.from_bytes(data=audio_bytes, mime_type=m_type) if audio_bytes else None
            # Same rule as ocr_engine._post_json: the dictation of a deed is
            # verified in transit, against certifi's roots merged with the
            # Windows trust store. Verification is only skipped when the office
            # has explicitly opted in, and that opt-in is what the red banner in
            # Paramètres reports — turning it off unconditionally made the
            # banner lie while every dictation travelled unverified.
            import config as _cfg
            try:
                http_client = httpx.Client(verify=_cfg.get_ca_bundle())
            except Exception:
                if not _cfg.insecure_tls_allowed():
                    raise
                http_client = httpx.Client(verify=False)
            client = genai.Client(api_key=current_key, http_options={"httpx_client": http_client})
            target_models = [model_name or "gemini-3.6-flash", "gemini-3.6-flash", "gemini-2.5-flash"]
            for model_id in target_models:
                try:
                    if part:
                        res = client.models.generate_content(model=model_id, contents=[prompt, part])
                    else:
                        res = client.models.generate_content(model=model_id, contents=prompt)
                    if hasattr(res, "text") and res.text:
                        return res.text.strip()
                    return ""
                except Exception as ex_sdk:
                    last_failure = _classify_network_failure(ex_sdk)
        except Exception as ex_gen:
            last_failure = _classify_network_failure(ex_gen)

        # Loop continues here so keys 2..n are still tried — the previous version
        # raised inside this loop, which meant only the first key was ever used.

    raise ValueError(_render_failure(last_failure, len(keys)))


def transcribe_audio_bytes(
    audio_bytes: bytes,
    api_key: str,
    mime_type: str = "audio/wav",
    model_name: str = "gemini-2.5-flash",
    provider: str = "gemini"
) -> dict:
    """
    Transcribes audio bytes natively using Gemini 1.5 Flash multimodal audio input or OpenAI Whisper.
    """
    if not api_key:
        return {"success": False, "transcription": "",
                "error": "لم يتم إدخال مفتاح API. يرجى إدخاله في لوحة إعدادات الذكاء الاصطناعي."}

    if not audio_bytes:
        return {"success": False, "transcription": "",
                "error": "لا يوجد تسجيل صوتي للتفريغ."}

    # A container header with no audio frames. Catches a recording that was cut off
    # before the file was finalised, which would otherwise be sent as valid audio.
    if len(audio_bytes) < 2048:
        return {
            "success": False,
            "transcription": "",
            "error": (
                f"التسجيل الصوتي فارغ أو غير مكتمل ({len(audio_bytes)} بايت). "
                "يرجى إعادة التسجيل والتأكد من الضغط على «إيقاف» بعد انتهاء الإملاء."
            )
        }

    prompt = """
أنت خبير تفريغ صوتی فائق الدقة ومحرك تدقيق قانوني موثقي لعدول الإشهاد بالجمهورية التونسية (Tunisian Notary Public AI).
استمع إلى هذا التسجيل الصوتي لعدل الإشهاد، وقم بتفريغه وتدوينه بدقة قانونية رسمية كاملة باللغة العربية الفصحى التوثيقية:

قواعد الإملاء والتدقيق القانوني العام (General Tunisian Notarial Law Rules):
1. قم بضبط وتحويل أي كلمات منطوقة بسرعة أو بلهجة سريعة إلى المصطلحات التوثيقية الرسمية التونسية.
2. الفصول والالتزامات القانونية:
   - تصحيح عبارات أصل وانجرار الملكية إلى "انجرار الملكية بالبيع / بالتخارج / بالهبة..."
   - تصحيح عبارات حجج ومحررات الشراء إلى "بحجة حررناها في..."
   - تصحيح عبارات التسجيل والقباضات إلى "مسجل بقباضة... وصل عدد..."
   - تصحيح عبارات إعفاء حافظ الملكية العقارية إلى "يعفى الطرفان السيد حافظ الملكية العقارية من اعتبار الوصف والتحديد والتشخيص..."
   - تصحيح عبارات الترسيم إلى "ويطلبان ترسيم الهبة / البيع في حدود ما ذكر"
3. تأنيث وتذكير الأفعال والضمائر حسب جنس الطرفين (التي قبلت للمشترية/الموهوب لها، والذي قبل للبائع/المشتري).
4. عدم كتابة أي كلمات غريبة أو غير مفهومة صوتاً، واستبدالها بالصياغة القانونية التونسية السليمة من سياق العقد.
5. يُمنع منعاً باتاً كتابة الأرقام والتواريخ بالكلمات قبل الأرقام (مثل: "السادس عشر من أوت سنة ألفين واثنين 16/08/2002" أو "ثلاثمائة وسبعة عشر ألفا 317379" أو "تسعة وتسعين فاصل 99.528"). اكتب الرقم أو التاريخ بالأرقام مباشرة وبشكل نظيف دون كرر بالألفاظ (مثال: "16/08/2002" / "317379" / "99.528" / "3000").

قم بإرجاع نص التفريغ الصوتي الموثق والمدقق قانونياً فقط.
"""

    try:
        if provider == "gemini":
            txt = call_gemini_api(prompt, audio_bytes=audio_bytes, mime_type=mime_type, api_key=api_key, model_name=model_name)
        else:
            from openai import OpenAI
            # Whisper takes a single key; a pasted pool would be one invalid token.
            single_key = next((k.strip() for k in api_key.replace('\n', ',').split(',') if k.strip()), "")
            client = OpenAI(api_key=single_key, timeout=120.0)
            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = _whisper_filename(mime_type)
            res = client.audio.transcriptions.create(model="whisper-1", file=audio_file)
            txt = (res.text or "").strip()

        txt = (txt or "").strip()
        if not txt:
            return {
                "success": False,
                "transcription": "",
                "error": ("لم يتمكن محرك التفريغ من قراءة أي كلام في التسجيل. "
                          "يرجى التأكد من وضوح الصوت وإعادة المحاولة.")
            }
        return {"success": True, "transcription": txt, "error": None}

    except ValueError as ex_known:
        # call_gemini_api already produced a notary-readable Arabic message.
        safe_log(f"Error transcribing audio bytes: {ex_known}")
        return {"success": False, "transcription": "", "error": str(ex_known)}
    except Exception as ex:
        safe_log(f"Error transcribing audio bytes: {ex}")
        return {
            "success": False,
            "transcription": "",
            "error": _render_failure(_classify_network_failure(ex), 1)
        }

VOICE_VERIFICATION_PROMPT = """
أنت خبير فائق الدقة في الاستخراج والتحليل التوثيقي لعدول الإشهاد بالجمهورية التونسية (Tunisian Notary Public AI).
أمامك نص أو قراءة صوتية لعدل إشهاد يملي عقداً توثيقياً (عقد بيع / هبة / مقاسمة / تنازل / معاوضة / كراء...).

المطلوب منك التركيز الشديد واستخراج المعطيات الأساسية للأطراف والعقد من الإملاء الصوتي وإرجاع JSON دقيق بالشكل التالي:

```json
{
  "party1_name": "اسم الطرف الأول بالكامل المنطوق صوتاً (مثل: محمد الطيب بن محمد)",
  "party1_birthplace": "مكان ولادة الطرف الأول المنطوق (مثل: القلعة الكبرى سوسة)",
  "party1_birthdate": "تاريخ ولادة الطرف الأول المنطوق (مثل: 1972/12/14)",
  "party1_job": "مهنة الطرف الأول المنطوقة (مثل: عامل يومي)",
  "party1_cin": "رقم بطاقة تعريف الطرف الأول المنطوق (مثل: 02998019)",
  "party1_cin_date": "تاريخ صدور بطاقة تعريف الطرف الأول (مثل: 1999/03/09)",
  "party1_address": "عنوان إقامة الطرف الأول المنطوق (مثل: 5 نهج 10300 الوردية 4)",

  "party2_name": "اسم الطرف الثاني بالكامل المنطوق صوتاً (مثل: وفاء بنت حسن بن محمد)",
  "party2_birthplace": "مكان ولادة الطرف الثاني المنطوق (مثل: القلعة الكبرى)",
  "party2_birthdate": "تاريخ ولادة الطرف الثاني المنطوق (مثل: 1982/05/18)",
  "party2_job": "مهنة الطرف الثاني المنطوقة (مثل: متصرف بوزارة الصحة)",
  "party2_cin": "رقم بطاقة تعريف الطرف الثاني المنطوق (مثل: 08495241)",
  "party2_cin_date": "تاريخ صدور بطاقة تعريف الطرف الثاني (مثل: 2010/04/12)",
  "party2_address": "عنوان إقامة الطرف الثاني المنطوق (مثل: 53 نهج القصرين المروج 1 بن عروس)",

  "property_title": "اسم العقار المذكور إن وجد (مثل: بن علي)",
  "titre_foncier": "رقم الرسم العقاري المذكور إن وجد (مثل: 57272)",
  "titre_gov": "ولاية أو مكان الرسم العقاري المذكور إن وجد (مثل: بن عروس)",
  "property_location": "موقع ومكان العقار المذكور الكائن بـ (مثل: المحمدية)",
  "property_area": "مساحة العقار المذكورة بالمتر المربع إن وجدت (مثل: 317379)",
  "property_desc": "توصيف وموضوع العقد والعقار والأنصبة المنطوقة صوتاً بالكامل",
  "price_words": "مبلغ الثمن أو قيمة العقار بالحروف (مثل: ثلاثة آلاف دينار)",
  "price_num": "مبلغ الثمن بالأرقام فقط (مثل: 3000)",
  "ownership_origin": "انجرار الملكية المنطوق إن وجد (مثل: انجرار الملكية بالبيع بحجة حررناها في 16/08/2002)",
  "receipt_num": "رقم وصل القباضة المنطوق إن وجد",
  "foussoul": [
    {
      "number": 1,
      "title": "الفصل الأول",
      "content": "نص الفصل المنطوق بالكامل"
    }
  ]
}
```
"""


def extract_variables_from_spoken_text(spoken_text: str, api_key: str, model_name: str = "gemini-2.5-flash", provider: str = "gemini") -> dict:
    """
    Calls Gemini/OpenAI to extract JSON contract variables from spoken notary dictation text.
    """
    if not spoken_text or not api_key:
        return {}
        
    prompt = VOICE_VERIFICATION_PROMPT + f"\n\nالنص المنطوق المراد تفريغه إلى JSON:\n{spoken_text}"
    try:
        if provider == "gemini":
            res_text = call_gemini_api(prompt, api_key=api_key, model_name=model_name)
        else:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            res = client.chat.completions.create(
                model=model_name or "gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            res_text = res.choices[0].message.content
            
        json_match = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", res_text, re.DOTALL)
        if not json_match:
            json_match = re.search(r"(\{[\s\S]*?\})", res_text)
        if json_match:
            return json.loads(json_match.group(1))
    except Exception as ex:
        safe_log(f"Error extracting spoken variables: {ex}")
    return {}


def extract_dynamic_foussoul_from_audio_or_text(spoken_text: str, api_key: str, model_name: str = "gemini-2.5-flash", provider: str = "gemini") -> dict:
    """
    Extracts every article (الفصل 1، الفصل 2، الفصل 3...) spoken in the audio/text 
    with its EXACT spoken title and EXACT spoken text, without any fixed structure or assumptions.
    """
    if not spoken_text or not api_key:
        return {"foussoul": [], "structured_markdown": ""}

    prompt = """
أنت مفرغ توثيقي دقيق جداً لعدول الإشهاد بالجمهورية التونسية.
أمامك نص أو قراءة صوتية لعدل إشهاد يملي عقداً توثيقياً.

المطلوب منك الاستماع للنص المنطوق واستخراج كافة الفصول المنطوقة صوتاً (مهما كان عددها أو عنوانها أو موضوعها) وإرجاعها بالضبط كما نُطقت دون فرض أي هيكل أو أسماء مسبقة.

قم بإنشاء كود JSON فقط بالصيغة التالية:

```json
{
  "foussoul": [
    {
      "number": 1,
      "title": "العنوان المنطوق للفصل الأول (مثال: الفصل الأول)",
      "content": "النص الكامل المنطوق صوتاً لهذا الفصل بالضبط بدون حذف أو تغيير."
    },
    {
      "number": 2,
      "title": "العنوان المنطوق للفصل الثاني (مثال: الفصل الثاني: الثمن)",
      "content": "النص الكامل المنطوق صوتاً لهذا الفصل بالضبط."
    }
  ]
}
```

تنبيه هام جداً: الفصول ليس لها هيكل ثابت ولا ألقاب محددة مسبقاً. استخرج فقط ما نطقه عدل الإشهاد في التسجيل الصوتي حرفياً وبالترتيب.

النص الصوتي المنطوق المراد استخراج فصوله:
""" + spoken_text

    try:
        if provider == "gemini":
            res_text = call_gemini_api(prompt, api_key=api_key, model_name=model_name)
        else:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            res = client.chat.completions.create(
                model=model_name or "gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            res_text = res.choices[0].message.content

        json_match = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", res_text, re.DOTALL)
        if not json_match:
            json_match = re.search(r"(\{[\s\S]*?\})", res_text)
        if json_match:
            parsed = json.loads(json_match.group(1))
            return {
                "foussoul": normalise_foussoul(parsed.get("foussoul") if isinstance(parsed, dict) else parsed),
                "structured_markdown": parsed.get("structured_markdown", "") if isinstance(parsed, dict) else "",
            }
        return {
            "structured_markdown": res_text,
            "foussoul": []
        }
    except Exception as ex:
        safe_log(f"Error extracting dynamic foussoul: {ex}")
    return {"foussoul": [], "structured_markdown": ""}


def normalise_foussoul(raw) -> list:
    """
    Coerces whatever the model returned into the [{number, title, content}] shape the
    contract builder expects.

    The prompt asks for objects, but models routinely answer with a list of plain
    strings instead. Passing that straight through used to raise AttributeError inside
    the contract builder, on the UI thread. Anything unusable is dropped rather than
    allowed to reach the deed.
    """
    if not raw or not isinstance(raw, (list, tuple)):
        return []

    cleaned = []
    for idx, item in enumerate(raw):
        if isinstance(item, dict):
            content = str(item.get("content") or item.get("text") or "").strip()
            if not content:
                continue
            number = item.get("number") or (idx + 1)
            title = str(item.get("title") or "").strip() or f"الفصل {number}"
            cleaned.append({"number": number, "title": title, "content": content})

        elif isinstance(item, str):
            text = item.strip()
            if not text:
                continue
            # "الفصل الرابع: يتحمل المشتري المعاليم." -> title + content
            parts = text.split(":", 1)
            if len(parts) == 2 and parts[0].strip() and len(parts[0].strip()) <= 40:
                title, content = parts[0].strip(), parts[1].strip()
            else:
                title, content = f"الفصل {idx + 1}", text
            if content:
                cleaned.append({"number": idx + 1, "title": title, "content": content})

    return cleaned
