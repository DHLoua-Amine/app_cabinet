"""
cin_extractor.py — AI Extractor for Tunisian National Identity Cards (بطاقات التعريف الوطنية التونسية)
Supports Gemini Vision & OpenAI Vision for extracting 8-digit CIN, names, dates, job, and address.
"""

import json
import re
from ocr_engine import _call_gemini_vision, _call_openai_vision
from contract_templates import clean_and_verify_tunisian_entities

TUNISIAN_CIN_PROMPT = """
أنت خبير فائق الدقة في قراءة واستخراج البيانات من بطاقات التعريف الوطنية التونسية (Carte Nationale d'Identité Tunisienne).
أمامك صورة لبطاقة تعريف وطنية تونسية (الوجه الأمامي، الوجه الخلفي، أو كلاهما).

المطلوب منك استخراج المعطيات بدقة 100% وإرجاع كود JSON محدد فقط بالشكل التالي:

```json
{
  "cin_number": "رقم بطاقة التعريف متكون من 8 أرقام بالضبط (مثال: 02998019)",
  "full_name": "الاسم الثلاثي/الرباعي الرسمي الكامل للإشهاد والتواثيق المكون من: الاسم الشخصي + سطر بن/بنت + اللقب (مثال للرجال: محمد الطيب بن محمد بن البشير ابن الحاج مبارك / مثال للنساء: وفاء بنت حسن بن محمد ابن الحاج)",
  "first_name": "الاسم الشخصي المكتوب في سطر الاسم (مثال: محمد الطيب / وفاء)",
  "father_name": "اسم الأب المكتوب في سطر ابن/بنت (مثال: محمد / حسن)",
  "grandfather_name": "اسم الجد المكتوب في سطر ابن/بنت (مثال: البشير / محمد)",
  "father_line": "السطر الكامل المكتوب في سطر ابن/بنت (مثال: بن محمد بن البشير / بنت حسن بن محمد)",
  "last_name": "اللقب المكتوب في سطر اللقب (مثال: ابن الحاج مبارك / ابن الحاج)",
  "husband_name": "اسم الزوج المكتوب في سطر حرم إن وجد (مثل: محمد الطيب بن الحاج مبارك) أو اتركه فارغاً",
  "birth_date": "تاريخ الولادة YYYY/MM/DD",
  "birth_place": "مكان الولادة",
  "issue_date": "تاريخ إصدار بطاقة التعريف المكتوب خلف البطاقة بجانب الختم مثل: تونس في 25 ديسمبر 2024 أو YYYY/MM/DD",
  "job": "المهنة المكتوبة خلف البطاقة",
  "address": "العنوان الكامل المكتوب خلف البطاقة"
}
```

قواعد صارمة جداً واستثنائية لبطاقات التعريف التونسية:
1. التمييز بين بطاقات الرجال والنساء (Sex & Gender Distinction):
   - للرجال (Men): سطر 3 يحتوي على كلمة "بن" (مثال: "بن محمد بن البشير"). التركيبة الكاملة للاسم ("full_name"): [الاسم الشخصي] + " " + [سطر بن] + " " + [اللقب] (مثال: "محمد الطيب بن محمد بن البشير ابن الحاج مبارك").
   - للنساء (Women): سطر 3 يحتوي على كلمة "بنت" (مثال: "بنت حسن بن محمد"). التركيبة الكاملة للاسم ("full_name"): [الاسم الشخصي] + " " + [سطر بنت] + " " + [اللقب] (مثال: "وفاء بنت حسن بن محمد ابن الحاج").
2. سطر "حرم" لاسم الزوج (Married Women):
   - للنساء المتزوجات، يوجد سطر رابع يسمى "حرم ...". هذا السطر هو اسم الزوج فقط وليس اسم المرأة ولا أباها ولا لقبها!
   - يمنع منعاً باتاً إدخال اسم الزوج الموجود في سطر "حرم" ضمن "full_name" أو "last_name" أو "father_name"! اترك "husband_name" لحفظ اسم الزوج إن وجد.
3. قراءة اللقب بالضبط دون نقصان:
   - اللقب قد يبدأ بـ "ابن الحاج" أو "ابن الحاج مبارك" أو "الحاج". اقرأ اللقب المكتوب في سطر "اللقب" بالكامل دون اختصار.
4. عدم إسقاط سطر الأب والجد (سطر ابن / بنت):
   - يمنع منعاً باتاً حذف أو إسقاط سطر الأب والجد "بن محمد بن البشير" أو "بنت حسن بن محمد" من "full_name"!
5. حظر التواريخ الوهمية: يمنع كتابة أي تاريخ افتراضي وهمي مثل "1999/01/01". إذا لم تجد التاريخ اترك الحقل فارغاً "".
6. اكتب الإجابة في صيغة JSON فقط دون أي كلام آخر.
"""


def _assemble_tunisian_full_name(extracted: dict) -> str:
    fname = str(extracted.get("first_name", "")).strip()
    lname = str(extracted.get("last_name", "")).strip()
    fatname = str(extracted.get("father_name", "")).strip()
    gfatname = str(extracted.get("grandfather_name", "")).strip()
    father_line = str(extracted.get("father_line", "")).strip()
    raw_full = str(extracted.get("full_name", "")).strip()

    from contract_templates import FEMALE_NAMES_SET
    is_female = False
    if fname:
        first_w = fname.split()[0]
        if first_w in FEMALE_NAMES_SET or first_w.endswith("ة"):
            is_female = True
    if "بنت" in father_line or "بنت" in raw_full:
        is_female = True

    connector = "بنت" if is_female else "بن"
    raw_full = re.sub(r"\s*حرم\s+[^\n,،\.]+", "", raw_full).strip()

    lineage = ""
    if father_line:
        clean_fatline = re.sub(r"\s*حرم\s+[^\n,،\.]+", "", father_line).strip()
        lineage = clean_fatline
    elif fatname and gfatname:
        fat_clean = re.sub(r"^(بن|بنت)\s+", "", fatname).strip()
        gfat_clean = re.sub(r"^(بن|بنت)\s+", "", gfatname).strip()
        lineage = f"{connector} {fat_clean} بن {gfat_clean}"
    elif fatname:
        fat_clean = re.sub(r"^(بن|بنت)\s+", "", fatname).strip()
        lineage = f"{connector} {fat_clean}"

    if fname and lname and lineage:
        if gfatname and gfatname not in raw_full:
            return re.sub(r"\s+", " ", f"{fname} {lineage} {lname}").strip()
        if fatname and fatname not in raw_full:
            return re.sub(r"\s+", " ", f"{fname} {lineage} {lname}").strip()

    return re.sub(r"\s+", " ", raw_full or f"{fname} {lname}").strip()


def extract_cin_data(
    image_bytes: bytes,
    api_key: str = "",
    model_name: str = "gemini-2.5-flash",
    provider: str = "gemini"
) -> dict:
    """
    Calls AI Vision API to extract structured fields from a Tunisian CIN Card image.
    """
    if not image_bytes:
        return {"success": False, "error": "لم يتم تقديم صورة لبطاقة التعريف."}
        
    if provider == "openai":
        res = _call_openai_vision(image_bytes, api_key, model_name, prompt=TUNISIAN_CIN_PROMPT)
    else:
        res = _call_gemini_vision(image_bytes, api_key, model_name, prompt=TUNISIAN_CIN_PROMPT)
        
    if not res.get("success"):
        return res
        
    raw_text = res.get("transcription", "")
    
    # Robust JSON block finder
    extracted = {}
    json_match = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", raw_text, re.DOTALL)
    if not json_match:
        json_match = re.search(r"(\{[\s\S]*?\})", raw_text)
        
    if json_match:
        try:
            parsed = json.loads(json_match.group(1))
            if isinstance(parsed, dict):
                extracted = parsed
        except Exception as parse_err:
            try:
                from system_guardian import log_system_error
                log_system_error("CIN extraction: model response was not valid JSON",
                                 parse_err)
            except Exception:
                pass

    # Regex Fallback Extraction if JSON parsing fails or keys are missing
    cin_nums = re.findall(r"\b\d{8}\b", raw_text)
    if cin_nums and not extracted.get("cin_number"):
        extracted["cin_number"] = cin_nums[0]

    # Assemble complete legal full_name ensuring father/grandfather lineage is preserved
    extracted["full_name"] = _assemble_tunisian_full_name(extracted)

    # Normalize place names & proper nouns using contract_templates cleaner
    cleaned_data = clean_and_verify_tunisian_entities(extracted)
    
    # Ensure mandatory keys exist
    for k in ["cin_number", "full_name", "first_name", "last_name", "birth_date", "birth_place", "issue_date", "job", "address"]:
        if k not in cleaned_data:
            cleaned_data[k] = ""
            
    return {
        "success": True,
        "data": cleaned_data,
        "raw_text": raw_text
    }


def extract_cin_dual_faces(
    front_bytes: bytes,
    back_bytes: bytes,
    api_key: str = "",
    model_name: str = "gemini-3.6-flash",
    provider: str = "gemini"
) -> dict:
    """
    Extracts and merges structured fields from both Front and Back sides of a Tunisian CIN Card in 1 SINGLE API call.
    """
    if provider == "gemini" and (front_bytes or back_bytes):
        from ocr_engine import _call_gemini_vision_dual
        res = _call_gemini_vision_dual(front_bytes, back_bytes, api_key, model_name, TUNISIAN_CIN_PROMPT)
        if res.get("success"):
            raw_text = res.get("transcription", "")
            extracted = {}
            json_match = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", raw_text, re.DOTALL)
            if not json_match:
                json_match = re.search(r"(\{[\s\S]*?\})", raw_text)
            if json_match:
                try:
                    extracted = json.loads(json_match.group(1))
                except Exception:
                    extracted = {}
            cleaned_data = clean_and_verify_tunisian_entities(extracted)
            for k in ["cin_number", "full_name", "first_name", "last_name", "birth_date", "birth_place", "issue_date", "job", "address"]:
                if k not in cleaned_data:
                    cleaned_data[k] = ""
            return {"success": True, "data": cleaned_data, "raw_text": raw_text}

    # Fallback to separate face extraction if provider != gemini
    front_res = extract_cin_data(front_bytes, api_key, model_name, provider) if front_bytes else {"data": {}}
    back_res = extract_cin_data(back_bytes, api_key, model_name, provider) if back_bytes else {"data": {}}

    f_data = front_res.get("data", {}) if front_res.get("success") else {}
    b_data = back_res.get("data", {}) if back_res.get("success") else {}

    merged = {}
    for k in ["cin_number", "full_name", "first_name", "last_name", "father_name", "grandfather_name", "birth_date", "birth_place", "issue_date", "job", "address"]:
        val = f_data.get(k) or b_data.get(k) or ""
        merged[k] = val

    is_ok = bool(front_res.get("success") or back_res.get("success"))
    err = None if is_ok else (front_res.get("error") or back_res.get("error") or "فشل قراءة وتحديد معطيات بطاقة التعريف.")
    return {"success": is_ok, "error": err, "data": merged, "raw_text": ""}
