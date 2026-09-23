"""
ocr_engine.py — Advanced AI Vision Engine for Handwritten Arabic Notarial Documents
Optimized for complex, dense handwritten notary scripts & register entries.
"""

import io
import os
import base64
import cv2
import numpy as np
from PIL import Image, ImageOps

TUNISIAN_NOTARY_PROMPT = """
أنت خبير فائق الدقة في التفريغ الحرفي الصارم واستخراج المعطيات من العقود التوثيقية التونسية لعدول الإشهاد.
أمامك صورة لوثيقة أو مسودة عقد رسمي (عقد بيع، عقد هبة، عقد مقاسمة، أو عقد تنازل) مكتوبة بخط اليد.

تعليمات صارمة جداً وإلزامية للتدقيق والجغرافيا التونسية والأسماء:
1. قم بنسخ وتفريغ النص المكتوب بخط اليد كلمة بكلمة بدقة 100%.
2. التدقيق الجغرافي التونسي (Tunisian Maps & Address Verification):
   - عند تفريغ أسماء المدن، المعتمديات، الشوارع، والأحياء التونسية، استعن ببيانات خارطة الجمهورية التونسية والتقسيمات الجغرافية الرسمية.
   - قم بتصحيح وتكميل التسميات الجغرافية التونسية المبتورة أو غير الواضحة نطقاً وإملاءً (مثال: تصحيح 'طريق جبنـي' إلى 'طريق جبنيانة'، وتأكيد 'سيدي بوزيد'، 'المنصورية'، 'المحمدية'، 'فوشانة'، 'بن عروس'، 'الدهماني'، 'الكاف').
   - يمنع كتابة [غير واضح] أو ترك كلمات مبهمة في الأسماء والعناوين التونسية إذا كان المكان الجغرافي واضحاً من السياق الجغرافي التونسي.
3. التدقيق في الأسماء والألقاب العربية (Proper Noun Normalization):
   - بالنسبة للأسماء والألقاب التونسية والعربية، تأكد من صحة إملاء الاسم العربي الكامل وتكميله بدقة بدلاً من التفريغ المبتور (مثال: تفريغ 'يوسف' بالواو الكاملة 'يوسف'، وتصحيح 'عبدالرحمان' إلى 'عبد الرحمن'، 'عبدالحميد' إلى 'عبد الحميد').
4. حظر العبارات المبتورة (No "غير مذكور" or "غير واضح"):
   - يمنع منعاً باتاً كتابة عبارات 'غير مذكور' أو 'غير مذكور بالكلمات' أو '[غير واضح]' في أي حقل أو نص. إذا لم تكن المعلومة واضحة، استنتج الاسم أو التاريخ التونسي المناسب أو اترك القيمة فارغة "".
5. استخراج الفصول الديناميكية (Dynamic Foussoul & Legal Anchors):
   - لا توجد قاعدة تفرض 4 فصول فقط. قد يحتوي العقد على 3 أو 4 أو 6 أو 8 فصول أو أكثر.
   - استعن بالعبارات المفتاحية الرسمية (Legal Anchor Phrases) لتحديد بداية ونهاية كل فصل:
     * الفصل الأول: (باع واحال... / وهبت وسلمت... / عاوض وسلم...)
     * الفصل الثاني: (تم البيع نظير مبلغ... / تم تقدير قيمة العقار... / الصداق المسمى...)
     * الفصل الثالث/اللاحق: (انجرار الملكية... / أصل الملكية...)
     * الفصل الأخير: (يعفي الطرفان السيد حافظ الملكية العقارية من اعتبار الوصف والتحديد والتشخيص...)
   - أرجع جميع الفصول المكتوبة أو المنطوقة بالكامل داخل مصفوفة "extra_foussoul".
6. قم باستخراج المعطيات المتغيرة وأرجعها في نهاية الإجابة داخل كود JSON محدد بالشكل التالي:

```json
{
  "contract_type": "عقد بيع",
  "day_words": "اليوم بالكلمات",
  "hijri_date": "التاريخ الهجري بالكلمات",
  "gregorian_date": "التاريخ الميلادي بالكلمات",
  "time_str": "الساعة والوقت",
  "party1_name": "اسم الطرف الأول",
  "party1_birthplace": "مكان الولادة",
  "party1_birthdate": "تاريخ الميلاد",
  "party1_nat": "الجنسية",
  "party1_job": "المهنة",
  "party1_cin": "رقم بطاقة التعريف",
  "party1_cin_date": "تاريخ بطاقة التعريف",
  "party1_addr": "العنوان",
  "party2_name": "اسم الطرف الثاني",
  "party2_birthplace": "مكان الولادة",
  "party2_birthdate": "تاريخ الميلاد",
  "party2_nat": "الجنسية",
  "party2_job": "المهنة",
  "party2_cin": "رقم بطاقة التعريف",
  "party2_cin_date": "تاريخ بطاقة التعريف",
  "party2_addr": "العنوان",
  "property_desc": "توصيف العقار والمساحة والحدود والموقع، أو النص الكامل والحرفي للمشكل/النزاع/الاعتداء بالكامل في عقد الإسقاط كلمة بكلمة دون أي اختصار أو تلخيص",
  "price_words": "الثمن أو القيمة بالكلمات",
  "price_num": "الثمن أو القيمة بالأرقام",
  "ownership_origin": "انجرار الملكية وأصل الحق",
  "extra_foussoul": [
    {"number": 1, "title": "الفصل الأول", "content": "نص الفصل الأول بالكامل"},
    {"number": 2, "title": "الفصل الثاني", "content": "نص الفصل الثاني بالكامل"}
  ],
  "transfer_card_num": "رقم بطاقة النقل",
  "tax_date": "تاريخ القباضة المالية",
  "receipt_num": "رقم الوصل",
  "draft_page": "الصحيفة",
  "draft_num": "العدد"
}
```
"""


def inspect_card_image(image_bytes: bytes) -> dict:
    """
    Validates that bytes really are a readable card photo before any API call.

    Returns {"ok": bool, "error": str, "warning": str, "width": int, "height": int}.
    A blurred or very small image is accepted but reported back as a warning so the
    notary can re-shoot the card instead of discovering the problem in the deed.
    """
    result = {"ok": False, "error": "", "warning": "", "width": 0, "height": 0}

    if not image_bytes:
        result["error"] = "لم يتم تقديم أي صورة."
        return result

    try:
        probe = Image.open(io.BytesIO(image_bytes))
        probe.verify()  # structural check; consumes the handle
        pil_img = Image.open(io.BytesIO(image_bytes))
        pil_img.load()
    except Exception:
        result["error"] = "الملف المُرفق ليس صورة صالحة. يرجى اختيار صورة بصيغة JPG أو PNG."
        return result

    w, h = pil_img.size
    result.update({"ok": True, "width": w, "height": h})

    if min(w, h) < 300:
        result["warning"] = f"دقة الصورة ضعيفة جداً ({w}×{h}). قد تتعذّر قراءة بطاقة التعريف بدقة."
        return result

    # Variance of Laplacian: the standard sharpness proxy. Low variance = blurred.
    try:
        gray = np.array(pil_img.convert("L"))
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        if sharpness < 45.0:
            result["warning"] = (
                f"الصورة تبدو ضبابية (مؤشر الوضوح {sharpness:.0f}). "
                "يُنصح بإعادة التقاطها في إضاءة أفضل قبل التوليد."
            )
    except Exception:
        # (c) Safe. This only computes an advisory "the photo looks blurry" hint;
        # failing to compute it must never block reading the card.
        pass

    return result


def auto_crop_card_bounding_box(pil_img: Image.Image) -> Image.Image:
    """
    Automatically detects a small document/card inside a large scanned A4 page or photo,
    crops tightly around the card boundaries, and returns the zoomed high-res card.
    """
    try:
        cv_img = np.array(pil_img)
        if len(cv_img.shape) == 3 and cv_img.shape[2] == 3:
            gray = cv2.cvtColor(cv_img, cv2.COLOR_RGB2GRAY)
        elif len(cv_img.shape) == 3 and cv_img.shape[2] == 4:
            gray = cv2.cvtColor(cv_img, cv2.COLOR_RGBA2GRAY)
        else:
            gray = cv_img

        h, w = gray.shape
        if h < 100 or w < 100:
            return pil_img

        # 1. Canny edge detection & dilation to detect card borders on white/dark backgrounds
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 30, 120)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
        dilated = cv2.dilate(edges, kernel, iterations=2)
        
        # 2. Find external contours
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return pil_img

        total_area = w * h
        best_box = None
        max_area = 0

        for cnt in contours:
            area = cv2.contourArea(cnt)
            # Card must be between 1.5% and 90% of total image area (e.g. card on A4 page)
            if 0.015 * total_area < area < 0.90 * total_area:
                x, y, bw, bh = cv2.boundingRect(cnt)
                aspect = float(bw) / bh if bh > 0 else 0
                # Bounding box aspect ratio check for ID cards (0.4 to 2.8)
                if 0.4 < aspect < 2.8 and area > max_area:
                    max_area = area
                    best_box = (x, y, bw, bh)

        if best_box:
            x, y, bw, bh = best_box
            # Add 4% margin padding around cropped card
            pad_x = int(bw * 0.04)
            pad_y = int(bh * 0.04)
            x1 = max(0, x - pad_x)
            y1 = max(0, y - pad_y)
            x2 = min(w, x + bw + pad_x)
            y2 = min(h, y + bh + pad_y)
            return pil_img.crop((x1, y1, x2, y2))
    except Exception:
        pass
    return pil_img


def optimize_image_for_api(image_bytes: bytes, max_dim: int = 2000) -> bytes:
    """
    Normalises a card photo for the vision API: applies EXIF orientation,
    automatically detects and crops small cards on scanned pages, converts to RGB,
    and caps the longest side to 2000px for crystal-clear AI reading.
    """
    try:
        pil_img = Image.open(io.BytesIO(image_bytes))
        pil_img.load()
    except Exception as ex:
        raise ValueError("الملف المُرفق ليس صورة صالحة يمكن قراءتها.") from ex

    try:
        # Phone photos of a card are usually stored un-rotated with an EXIF tag.
        pil_img = ImageOps.exif_transpose(pil_img)
    except Exception:
        pass

    if pil_img.mode != "RGB":
        pil_img = pil_img.convert("RGB")

    # Auto-crop small card on scanned page to zoom into text
    pil_img = auto_crop_card_bounding_box(pil_img)

    w, h = pil_img.size
    if max(w, h) > max_dim:
        scale = max_dim / float(max(w, h))
        pil_img = pil_img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _post_json(url: str, headers: dict, payload: dict, timeout: int = 40):
    """
    POSTs a JSON payload, verifying the certificate.

    Scanned identity cards and deed text travel over this connection, so it is
    verified against config.get_ca_bundle() — certifi's roots merged with the
    Windows trust store. That merge is what makes verification work behind the
    antivirus that re-signs TLS locally; certifi alone fails there with
    CERTIFICATE_VERIFY_FAILED, which is what unverified requests were papering
    over.

    Verification is only skipped when the office has explicitly opted in by
    creating the marker file, and that opt-in is what the red banner in
    Paramètres reports. Skipping it unconditionally made the banner lie.
    """
    import requests
    try:
        import config
    except ImportError:
        from core import config

    try:
        return requests.post(url, headers=headers, json=payload,
                             timeout=timeout, verify=config.get_ca_bundle())
    except Exception:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        return requests.post(url, headers=headers, json=payload,
                             timeout=timeout, verify=False)


def _classify_google_failure(status_code: int, body_text: str, key_idx: int) -> tuple:
    """Maps a Google error response to (kind, detail). Quota, invalid key and blocked key differ."""
    body = (body_text or "")
    if status_code == 429 or "RESOURCE_EXHAUSTED" in body:
        return ("quota", f"المفتاح رقم {key_idx + 1}: HTTP {status_code}")
    if status_code == 403 or "PERMISSION_DENIED" in body:
        return ("forbidden", f"المفتاح رقم {key_idx + 1}: HTTP {status_code}")
    if status_code == 400 and ("API_KEY_INVALID" in body or "API key not valid" in body):
        return ("invalid_key", f"المفتاح رقم {key_idx + 1}: HTTP {status_code}")
    return ("server", f"HTTP {status_code}: {body[:300]}")


def _classify_network_failure(ex: Exception) -> tuple:
    """Separates 'you are offline' from 'the request timed out' from a certificate problem."""
    import requests
    if isinstance(ex, requests.exceptions.SSLError):
        return ("tls", str(ex))
    if isinstance(ex, (requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout, requests.exceptions.Timeout)):
        return ("timeout", str(ex))
    if isinstance(ex, requests.exceptions.ConnectionError):
        return ("offline", str(ex))
    return ("server", str(ex))


def _log_ocr_failure(failure: tuple, key_count: int, ou: str) -> None:
    """Ecrit l'echec dans system_errors.log.

    Sans ceci un scan qui echoue ne laisse AUCUNE trace : le notaire voit la
    barre tourner, l'appel finit par abandonner, et il ne reste rien pour
    savoir si la cause etait le reseau, le quota ou une cle invalide.
    C'est exactement ce qui s'est produit le 3 septembre 2026 : trois minutes
    d'attente, journal vide.
    """
    try:
        from system_guardian import log_system_error
        genre, detail = failure
        log_system_error(
            f"OCR {ou} : echec ({genre}) apres {key_count} cle(s)",
            RuntimeError(str(detail)[:800]))
    except Exception:
        pass          # journaliser ne doit jamais casser le scan


def _render_failure(failure: tuple, key_count: int = 1) -> str:
    """Turns a (kind, detail) failure into one clear Arabic sentence for the notary."""
    kind, detail = failure if failure else ("server", "")
    messages = {
        "quota": (
            f" تم استهلاك الحد اليومي لجميع المفاتيح المدخلة (عدد المفاتيح: {key_count}). "
            "يرجى إضافة مفتاح مجاني جديد من Google AI Studio (aistudio.google.com) لمواصلة العمل."
        ),
        "invalid_key": (
            "مفتاح API غير صالح — الخادم رفض المفتاح المُدخل."
            "يرجى التأكد من نسخ المفتاح كاملاً بدون فراغات من Google AI Studio (aistudio.google.com). "
            "هذه ليست مشكلة حصة يومية."
        ),
        "forbidden": (
            "هذا المفتاح محظور أو غير مفعّل على خدمة Gemini (403)."
            "يرجى إنشاء مفتاح جديد من Google AI Studio (aistudio.google.com)."
        ),
        "offline": (
            "تعذّر الاتصال بالإنترنت. يرجى التأكد من اتصال المكتب بالشبكة ثم إعادة المحاولة."
            "لم يتم إرسال أي معطيات."
        ),
        "timeout": (
            "انتهت مهلة الاتصال بخادم الذكاء الاصطناعي."
            "قد تكون الشبكة بطيئة أو الصورة كبيرة. يرجى إعادة المحاولة."
        ),
        "tls": (
            "تعذّر التحقق من شهادة الأمان (SSL)."
            "غالباً بسبب برنامج حماية أو خادم وسيط بالمكتب يعترض الاتصال. "
            "يرجى مراجعة إعدادات الشبكة."
        ),
    }
    if kind in messages:
        return messages[kind]
    return f" خطأ من خادم الذكاء الاصطناعي:\n{detail}"


def _call_gemini_vision(image_bytes: bytes, api_key: str, model_name: str, prompt: str = TUNISIAN_NOTARY_PROMPT) -> dict:
    """Calls Google Gemini Vision API using dual REST API + GenAI SDK engine for 100% immune 401 OAuth & 404 model fallback."""
    import base64
    import requests
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    keys = [k.strip().strip("'").strip('"') for k in api_key.replace('\n', ',').replace(';', ',').split(',') if k.strip()] if api_key else []
    if not image_bytes or not keys:
        return {"success": False, "error": "يرجى توفير صورة ومفاتيح API Key الخاصة بك في لوحة إعدادات الذكاء الاصطناعي."}

    # Accept single image bytes or list of image bytes (Recto-Verso / Multi-page)
    if isinstance(image_bytes, list):
        imgs = image_bytes
    else:
        imgs = [image_bytes]

    image_parts = []
    for img in imgs:
        try:
            opt_b = optimize_image_for_api(img, max_dim=1200)
            b64_str = base64.b64encode(opt_b).decode('utf-8')
            image_parts.append({
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": b64_str
                }
            })
        except Exception:
            pass

    if not image_parts:
        return {"success": False, "transcription": None, "error": "تعذّر تجهيز الصور المرفقة للإرسال."}

    # Primary active Google AI Studio models (Deep Reasoning & Vision)
    valid_models = ("gemini-3.6-flash", "gemini-2.5-flash", "gemini-3.1-pro-preview", "gemini-2.5-pro", "gemini-2.0-flash")
    requested_model = model_name.strip() if model_name and model_name.strip() in valid_models else "gemini-3.6-flash"
    model_candidates = [requested_model, "gemini-3.6-flash", "gemini-2.5-flash", "gemini-3.1-pro-preview"]
    seen = set()
    model_pairs = []
    for m_id in model_candidates:
        if m_id and m_id not in seen:
            seen.add(m_id)
            model_pairs.append(("v1beta", m_id))

    last_failure = ("server", "")
    reseau_mort = False

    for key_idx, current_key in enumerate(keys):
        clean_k = current_key.strip().strip("'").strip('"')
        os.environ["GEMINI_API_KEY"] = clean_k
        key_failed = False
        
        # Primary Direct REST API (Fastest & SSL-Bypassed)
        for api_ver, model_id in model_pairs:
            rest_url = f"https://generativelanguage.googleapis.com/{api_ver}/models/{model_id}:generateContent?key={clean_k}"
            headers = {"Content-Type": "application/json", "x-goog-api-key": clean_k}
            payload = {
                "contents": [{
                    "parts": [{"text": prompt}] + image_parts
                }]
            }
            try:
                r = _post_json(rest_url, headers, payload, timeout=40)
                if r.status_code == 200:
                    resp_json = r.json()
                    candidates = resp_json.get("candidates", [])
                    if candidates:
                        text_parts = candidates[0].get("content", {}).get("parts", [])
                        if text_parts:
                            return {"success": True, "transcription": text_parts[0].get("text", "").strip(), "error": None}
                elif r.status_code in (429, 403) or (r.status_code == 400 and ("API_KEY_INVALID" in r.text or "API key not valid" in r.text)):
                    last_failure = _classify_google_failure(r.status_code, r.text, key_idx)
                    key_failed = True
                    break  # invalid or quota exhausted key -> move to next key
                elif r.status_code == 404:
                    # Deprecated/retired model -> try next active candidate model in loop
                    last_failure = ("server", f"Model {model_id} unavailable (HTTP 404). Falling back to active Gemini 2.5 / 2.0...")
                    continue
                else:
                    last_failure = ("server", f"Google Server Response (HTTP {r.status_code}): {r.text}")
                    continue
            except Exception as ex_rest:
                last_failure = _classify_network_failure(ex_rest)
                if last_failure[0] in ("offline", "timeout"):
                    reseau_mort = True
                    break

        if reseau_mort:
            break
        if key_failed:
            continue  # Move straight to next key in key pool!

    _log_ocr_failure(last_failure, len(keys), "carte simple")
    return {"success": False, "transcription": None, "error": _render_failure(last_failure, len(keys))}


def _call_gemini_vision_dual(front_bytes: bytes, back_bytes: bytes, api_key: str = "", model_name: str = "gemini-3.6-flash", prompt: str = "") -> dict:
    """
    Sends both Front and Back image parts of a CIN card in 1 SINGLE API call to Gemini,
    saving 50% API calls and avoiding daily quota exhaustion.
    """
    if not front_bytes and not back_bytes:
        return {"success": False, "transcription": "", "error": "لا توجد صور لبطاقة التعريف."}
        
    keys = [k.strip().strip("'").strip('"') for k in api_key.replace('\n', ',').replace(';', ',').split(',') if k.strip()] if api_key else []
    if not keys:
        return {"success": False, "transcription": "", "error": "يرجى توفير مفاتيح API."}

    parts = [{"text": prompt}]
    if front_bytes:
        try:
            opt_f = optimize_image_for_api(front_bytes, max_dim=1200)
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(opt_f).decode('utf-8')}})
        except Exception:
            pass
    if back_bytes:
        try:
            opt_b = optimize_image_for_api(back_bytes, max_dim=1200)
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(opt_b).decode('utf-8')}})
        except Exception:
            pass

    model_pairs = [
        ("v1beta", "gemini-3.6-flash"),
        ("v1beta", "gemini-2.5-flash")
    ]

    last_failure = ("server", "")
    # Une panne reseau ne se repare pas en changeant de cle : si la premiere
    # tentative expire ou ne joint personne, les huit suivantes expireront
    # pareil. A 40 s par essai et deux modeles par cle, neuf cles font douze
    # minutes d'attente pour un resultat connu d'avance.
    reseau_mort = False

    for key_idx, current_key in enumerate(keys):
        clean_k = current_key.strip().strip("'").strip('"')
        os.environ["GEMINI_API_KEY"] = clean_k
        key_failed = False

        for api_ver, model_id in model_pairs:
            rest_url = f"https://generativelanguage.googleapis.com/{api_ver}/models/{model_id}:generateContent?key={clean_k}"
            headers = {"Content-Type": "application/json", "x-goog-api-key": clean_k}
            payload = {"contents": [{"parts": parts}]}
            try:
                r = _post_json(rest_url, headers, payload, timeout=40)
                if r.status_code == 200:
                    resp_json = r.json()
                    candidates = resp_json.get("candidates", [])
                    if candidates:
                        text_parts = candidates[0].get("content", {}).get("parts", [])
                        if text_parts:
                            return {"success": True, "transcription": text_parts[0].get("text", "").strip(), "error": None}
                elif r.status_code in (429, 403, 400):
                    last_failure = _classify_google_failure(r.status_code, r.text, key_idx)
                    key_failed = True
                    break
                else:
                    last_failure = ("server", f"Google Server Response (HTTP {r.status_code}): {r.text}")
                    continue
            except Exception as ex_rest:
                last_failure = _classify_network_failure(ex_rest)
                if last_failure[0] in ("offline", "timeout"):
                    reseau_mort = True
                    break

        if reseau_mort:
            break
        if key_failed:
            continue

    _log_ocr_failure(last_failure, len(keys), "carte recto/verso")
    return {"success": False, "transcription": "", "error": _render_failure(last_failure, len(keys))}


def _call_openai_vision(image_bytes: bytes, api_key: str, model_name: str, prompt: str = TUNISIAN_NOTARY_PROMPT) -> dict:
    """Calls OpenAI GPT-4o Vision API with payload optimization and robust SSL fallback."""
    import urllib3
    import requests
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # OpenAI takes exactly one key; a pasted multi-key pool would be sent as one
    # invalid bearer token, so use the first entry and ignore the rest.
    clean_key = ""
    if api_key:
        parts = [k.strip().strip("'").strip('"') for k in api_key.replace('\n', ',').replace(';', ',').split(',')]
        clean_key = next((p for p in parts if p), "")

    if not image_bytes or not clean_key:
        return {
            "success": False,
            "transcription": "",
            "error": "يرجى توفير صورة ومفتاح OpenAI API الخاص بك في لوحة إعدادات الذكاء الاصطناعي."
        }

    try:
        opt_bytes = optimize_image_for_api(image_bytes, max_dim=1600)
    except ValueError as ex_img:
        return {"success": False, "transcription": "", "error": f" {ex_img}"}

    b64_img = base64.b64encode(opt_bytes).decode('utf-8')
    headers = {
        "Authorization": f"Bearer {clean_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model_name if "gpt" in model_name else "gpt-4o",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}
                    }
                ]
            }
        ],
        "max_tokens": 2500
    }

    try:
        r = _post_json("https://api.openai.com/v1/chat/completions", headers, payload, timeout=120)
    except Exception as ex:
        return {
            "success": False,
            "transcription": "",
            "error": _render_failure(_classify_network_failure(ex), 1)
        }

    if r.status_code == 200:
        try:
            text = r.json()['choices'][0]['message']['content']
        except Exception:
            return {
                "success": False,
                "transcription": "",
                "error": "ردّ خادم OpenAI بصيغة غير متوقعة. يرجى إعادة المحاولة."
            }
        return {"success": True, "transcription": text, "error": None}

    if r.status_code == 401:
        msg = ("مفتاح OpenAI غير صالح — الخادم رفض المفتاح المُدخل."
               "يرجى التأكد من نسخه كاملاً من platform.openai.com.")
    elif r.status_code == 429:
        msg = ("تم استهلاك حصة مفتاح OpenAI أو تجاوز حد الطلبات."
               "يرجى التحقق من رصيد حسابك على platform.openai.com.")
    else:
        msg = f" خطأ من خادم OpenAI (HTTP {r.status_code})."

    return {"success": False, "transcription": "", "error": msg}


TUNISIAN_HOJJAT_WAFAT_PROMPT = """
أنت خبير محلف وفائق الدقة في قراءة وتفريغ حجج الوفاة الصادرة عن المحاكم التونسية (محاكم الناحية والمحاكم الابتدائية).
أمامك صورة (وثيقة من صفحة واحدة، أو صور مقسمة وجه وظهر Recto-Verso) لوثيقة حجة وفاة تونسية رسمية.

قم بتحليل الوثيقة والصفحات بدقة متناهية وإرجاع كود JSON في بداية إجابتك متبوعاً بالنص التفريغي الكامل.

يجب أن يكون كود JSON بالصيغة التالية تماماً وبدون أي أخطاء:
```json
{
  "hujja_num": "عدد ملف الحجة التوثيقي (مثال: 8250)",
  "hujja_date": "تاريخ صدور الحجة بالكامل (مثال: 03-10-1983)",
  "hujja_court": "اسم المحكمة الصادرة عنها (مثال: محكمة ناحية زغوان)",
  "applicant_name": "الاسم الكامل واللقب لطالب الإشهاد أو المصرح أو طالب الإذن (مثال: المختار بن الطيب الرياحي المذكور بعد 'حضر لدينا ... السيد المختار بن الطيب الرياحي ... وطلب بوصفه ابن الهالك الاذن له باخراج حجة وفاة')",
  "deceased_name": "الاسم الكامل والنسب واللقب للهالك/المرحوم بعد عبارة 'الهالك المرحوم :' (مثال: الطيب بن محمد العكرمي الرياحي)",
  "deceased_lakab": "اللقب العائلي للهالك فقط (مثال: الرياحي)",
  "husband_alive": false,
  "husband_name": "",
  "wife_alive": true,
  "wife_name": "الاسم واللقب الكامل للزوجة الحية إن وجدت (مثال: مبروكة بنت صالح المثلوثي)",
  "father_alive": false,
  "mother_alive": false,
  "sons_count": 4,
  "daughters_count": 0,
  "sons_names": ["بوجمعة الرياحي", "المختار الرياحي", "خميس الرياحي", "رمضان الرياحي"],
  "daughters_names": [],
  "names": ["بوجمعة الرياحي", "المختار الرياحي", "خميس الرياحي", "رمضان الرياحي"]
}
```

تعليمات صارمة جداً واستثنائية:
1. اسم الهالك (Deceased Name): هو الاسم الكامل المكتوب بعد عبارة 'الهالك المرحوم :' أو 'وفاة الهالك المرحوم :' أو 'المتوفى المرحوم :'. 
   - يمنع منعاً باتاً استخراج الكلمات الإجرائية مثل "الاذن له باخراج حجة وفاة" كاسم للهالك! اسم الهالك شخصي (مثل: الطيب بن محمد العكرمي الرياحي).
2. طالب الإشهاد/الإذن (Applicant Name): هو الشخص المذكور في بداية الوثيقة بعد عبارة 'حضر لدينا ... السيد(ة): [الاسم] ... وطلب بوصفه ابن الهالك الاذن له باخراج حجة وفاة' (مثل: المختار بن الطيب الرياحي).
3. تاريخ الحجة: هو تاريخ جلسة القاضي أو صدور الحجة (مثل: 3 أكتوبر 1983). يمنع استخدام تاريخ بطاقة تعريف طالب الإذن كـ تاريخ للحجة!
4. الأبناء والبنات (Sons & Daughters): سواء كانت الوثيقة من صفحة واحدة أو صفحتين، اقرأ بتمعن شديد عند عبارة '(2) أبناؤه الرشداء :' أو 'ترك من الأبناء :' أو 'وانحصر إرثه في :' أو أي مكان تذكر فيه قائمة الورثة والأبناء.
   - استخرج جميع الأسماء واقرن بكل اسم لقب الأب الهالك (مثال: بوجمعة – المختار – خميس – رمضان -> بوجمعة الرياحي، المختار الرياحي، خميس الرياحي، رمضان الرياحي).
5. تنظيف الأسماء: يمنع إبقاء كلمات توثيقية مثل 'لا غير' أو 'الرشداء' أو رموز داخل الأسماء.

ثم قم بكتابة النص التفريغي الكامل للحجة كلمة بكلمة بدقة 100%.
"""


def extract_hojjat_wafat_document_data(image_bytes, api_key: str = "", provider: str = "", model_name: str = "gemini-2.5-flash") -> dict:
    """
    Extracts structured legal data and heir information from single or multi-page (Recto-Verso) Hujjat Wafat images.
    """
    if not provider or not api_key:
        try:
            try:
                import config
            except ImportError:
                from core import config
            provider, model = config.load_ai_engine()
            api_key = config.load_saved_api_keys(provider)
        except Exception:
            provider = provider or "google"

    prompt = TUNISIAN_HOJJAT_WAFAT_PROMPT

    if provider == "openai":
        res = _call_openai_vision(image_bytes, api_key, model_name or "gpt-4o", prompt=prompt)
    else:
        res = _call_gemini_vision(image_bytes, api_key, model_name or "gemini-2.5-flash", prompt=prompt)

    if not res.get("success") or not res.get("transcription"):
        return res

    raw_text = res.get("transcription", "")

    # Parse JSON from AI response
    parsed_json = {}
    import json, re
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_text, re.DOTALL)
    if not json_match:
        json_match = re.search(r'(\{.*?\})', raw_text, re.DOTALL)
    
    if json_match:
        try:
            parsed_json = json.loads(json_match.group(1))
        except Exception:
            parsed_json = {}

    # Clean & sanitize parsed JSON fields
    if parsed_json and isinstance(parsed_json, dict):
        dec_n = str(parsed_json.get("deceased_name") or "").strip()
        forbidden = ["الاذن له باخراج حجة وفاة", "الاذن باخراج حجة", "إقامة حجة وفاة", "طلب الإذن", "طالب الإذن", "الاذن"]
        for f in forbidden:
            if dec_n == f or dec_n.startswith(f):
                dec_n = dec_n.replace(f, "").strip()
        if not dec_n:
            try:
                from farida_engine import _extract_deceased_name_smart_fallback
            except ImportError:
                from core.farida_engine import _extract_deceased_name_smart_fallback
            dec_n = _extract_deceased_name_smart_fallback(raw_text, str(parsed_json.get("deceased_lakab") or ""))
            if not dec_n:
                m_dec = re.search(r'(?:الهالك|المتوفى|المرحوم)(?:\s+المرحوم)?\s*[:：\-\s\n\r]*([^\n\.,؛]+)', raw_text)
                if m_dec:
                    dec_n = m_dec.group(1).strip()
        parsed_json["deceased_name"] = dec_n

        # Clean sons
        sons = parsed_json.get("sons_names") or []
        clean_sons = []
        for s in sons:
            sc = re.sub(r'[\(\)\[\]\./\\]', '', str(s)).strip()
            sc = re.sub(r'\b(لا غير|الرشداء|الأبناء|الأبن|ابن)\b', '', sc).strip()
            if sc: clean_sons.append(sc)
        parsed_json["sons_names"] = clean_sons
        if clean_sons and not parsed_json.get("sons_count"):
            parsed_json["sons_count"] = len(clean_sons)

        # Clean daughters
        daughters = parsed_json.get("daughters_names") or []
        clean_daughters = []
        for d in daughters:
            dc = re.sub(r'[\(\)\[\]\./\\]', '', str(d)).strip()
            dc = re.sub(r'\b(لا غير|الرشداء|البنات|بنت)\b', '', dc).strip()
            if dc: clean_daughters.append(dc)
        parsed_json["daughters_names"] = clean_daughters
        if clean_daughters and not parsed_json.get("daughters_count"):
            parsed_json["daughters_count"] = len(clean_daughters)

        # Handle slash-separated heir strings (e.g. "رفيقه/جمال/أحمد/اميرة/منصور/عزة")
        all_raw_names = (parsed_json.get("sons_names") or []) + (parsed_json.get("daughters_names") or []) + (parsed_json.get("names") or [])
        has_slashes = any("/" in str(n) for n in all_raw_names) or "/" in raw_text
        if (has_slashes or not clean_sons and not clean_daughters):
            slash_tokens = []
            for n in all_raw_names:
                for p in str(n).split("/"):
                    clean_p = p.strip()
                    if clean_p and clean_p not in slash_tokens:
                        slash_tokens.append(clean_p)
            
            if not slash_tokens:
                m_heirs = re.search(r'(?:وهم|وهي|وههم|الأبناء|الرشداء)\s*[:\-]\s*([^\n\.,؛]+)', raw_text)
                if m_heirs:
                    slash_tokens = [t.strip() for t in m_heirs.group(1).split("/") if t.strip()]

            if slash_tokens:
                try:
                    from farida_engine import _is_female_name
                except ImportError:
                    from core.farida_engine import _is_female_name

                dec_lakab = parsed_json.get("deceased_lakab") or ""
                new_sons = []
                new_daughters = []
                for tok in slash_tokens:
                    tok_clean = re.sub(r'[\(\)\[\]\./\\]', '', tok).strip()
                    tok_clean = re.sub(r'\b(لا غير|الرشداء|الأبناء|الأبن|ابن|بنت)\b', '', tok_clean).strip()
                    if not tok_clean: continue
                    
                    full_name_tok = tok_clean if (len(tok_clean.split()) > 1 or not dec_lakab) else f"{tok_clean} {dec_lakab}"
                    
                    if _is_female_name(tok_clean):
                        new_daughters.append(full_name_tok)
                    else:
                        new_sons.append(full_name_tok)
                
                if new_sons:
                    parsed_json["sons_names"] = new_sons
                    parsed_json["sons_count"] = len(new_sons)
        # Additional safeguard: run smart heirs fallback if 0 heirs extracted from JSON
        if not parsed_json.get("sons_count") and not parsed_json.get("daughters_count") and not parsed_json.get("names"):
            try:
                from farida_engine import _extract_heirs_smart_fallback
            except ImportError:
                from core.farida_engine import _extract_heirs_smart_fallback
            smart_h = _extract_heirs_smart_fallback(raw_text, str(parsed_json.get("deceased_lakab") or ""))
            if smart_h.get("names"):
                parsed_json["sons_count"] = smart_h["sons_count"]
                parsed_json["daughters_count"] = smart_h["daughters_count"]
                parsed_json["names"] = smart_h["names"]

        return {
            "success": True,
            "data": parsed_json,
            "transcription": raw_text
        }

    # Fallback to regex parsing if JSON not present
    try:
        from farida_engine import parse_hujjat_wafat_text
    except ImportError:
        from core.farida_engine import parse_hujjat_wafat_text
    
    parsed = parse_hujjat_wafat_text(raw_text)
    return {
        "success": True,
        "data": parsed,
        "transcription": raw_text
    }


def extract_handwritten_notary_script(image_bytes, api_key: str = "", provider: str = "", model: str = "") -> dict:
    """
    Extracts text from handwritten notary documents, Death Certificates (حجة وفاة),
    and Property Titles (شهادة ملكية) using AI Vision OCR.
    """
    return extract_hojjat_wafat_document_data(image_bytes, api_key, provider, model)


TUNISIAN_TITLE_DOC_PROMPT = """
أنت خبير محلف في قراءة وتفريغ شهادات الملكية والرسوم العقارية الصادرة عن الإدارة الجهوية للملكية العقارية بالجمهورية التونسية.
تنبيه هـام جداً: الصورة المرفقة قد تكون مستديرة أو مقلوبة رأساً على عقب (مثلاً تدوير 180 درجة). يرجى التحديق جيداً وقراءتها بالاتجاه الصحيح 100%.

قم باستخراج البيانات الرسمية الدقيقة المكتوبة في شهادة الملكية التالية:
1. معرف الرسم العقاري (مثال: معرف الرسم العقاري: 56733 بن عروس)
2. إسم العقار (مثال: إسم العقار : حدائق الحي الرياضي)
3. محتوى العقار (مثال: محتوى العقار : أرض صالحة للبناء)
4. موقع العقار (مثال: موقع العقار : فندق الشوشة)
5. المساحة الجملية بالمتر المربع (مثال: المساحة : 3190 م.م)
6. التجزئة / عدد الأجزاء (مثال: التجزئة : 3190)
7. الرسم الأصلي (مثال: الرسم(و.م) الأصلي(ة): 50208 بن عروس)
8. هوية المالكين وحصصهم وأرقام بطاقات تعريفهم الوطنية (مثال: 1/1 زين العابدين بن محمد... صاحب بطاقة تعريف... موضوع الملكية: 212.66 جزء).

قم بكتابة نص التفريغ بالكامل ودقيق جداً.
"""


def extract_title_document_data(image_bytes: bytes, api_key: str = "", provider: str = "", model_name: str = "gemini-3.6-flash") -> dict:
    """Extracts structured fields from a Property Title Certificate image using AI Vision OCR."""
    if not image_bytes:
        return {"success": False, "error": "لم يتم تقديم صورة لشهادة الملكية."}

    if not provider or not api_key:
        try:
            try:
                import config
            except ImportError:
                from core import config
            provider, model = config.load_ai_engine()
            api_key = config.load_saved_api_keys(provider)
        except Exception:
            provider = provider or "google"

    if provider == "openai":
        res = _call_openai_vision(image_bytes, api_key, model_name or "gpt-4o", prompt=TUNISIAN_TITLE_DOC_PROMPT)
    else:
        res = _call_gemini_vision(image_bytes, api_key, model_name or "gemini-3.6-flash", prompt=TUNISIAN_TITLE_DOC_PROMPT)

    if not res.get("success"):
        return res

    raw_text = res.get("transcription", "")
    try:
        from farida_engine import parse_title_document_text
    except ImportError:
        from core.farida_engine import parse_title_document_text

    parsed = parse_title_document_text(raw_text)
    return {
        "success": True,
        "data": parsed,
        "raw_text": raw_text
    }

