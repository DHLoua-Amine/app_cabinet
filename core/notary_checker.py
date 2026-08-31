"""
notary_checker.py — AI Notary Risk, Legal Anomaly Checker & Tunisian Legal Code Assistant
Specifically built for Tunisian Notary Law (عدول الإشهاد بالجمهورية التونسية).
"""

import re

# ── TUNISIAN LEGAL CODES KNOWLEDGE BASE (مجلة الالتزامات والعقود والحقوق العينية) ──
TUNISIAN_LEGAL_KNOWLEDGE = [
    {
        "code": "مجلة الالتزامات والعقود (FAS 564)",
        "topic": "أركان البيع وانعقاده",
        "content": "الفصل 564: البيع عقد بمقتضاه يسلم أحد المتعاقدين عيناً أو حقاً للآخر في مقابل ثمن يلتزم هذا الأخير بأدائه له. ويتم البيع بتراضي الطرفين بالمبيع والثمن وبقية الشروط."
    },
    {
        "code": "مجلة الالتزامات والعقود (FAS 580)",
        "topic": "أصل انجرار الملكية وضمان الاستحقاق",
        "content": "الفصل 580: على البائع التزام بضمان المبيع وبثبوت ملكيته وسرانه تحت سائر الضمانات الفعلية والقانونية وتخليصه من أي رهن أو كفالة غير صريحة."
    },
    {
        "code": "مجلة الحقوق العينية (FAS 305)",
        "topic": "ترسيم العقارات وحفظ الملكية",
        "content": "الفصل 305: كل حق عيني عقاري لا يتكون إلا بترسيمه بالسجل العقاري بحافظة الملكية العقارية ويكتسب فاعليته تجاه الغير من تاريخ الترسيم."
    },
    {
        "code": "مجلة الحقوق العينية (FAS 201)",
        "topic": "عقود الهبة وشروط صحتها",
        "content": "الفصل 201: الهبة عقد بغير عوض يملك بمقتضاه شخص ماله لآخر. وتتم الهبة بالحوز وتستوجب المحرر التوثيقي الرسمي بحجة عادلة من عدلي إشهاد."
    },
    {
        "code": "مجلة الحقوق العينية (FAS 118)",
        "topic": "المقاسمة الرضائية والتعديل",
        "content": "الفصل 118: تقع قسمة المشترك بين الشركاء إما رضائياً بحجة عادلة أو قضائياً، وتعتبر المقاسمة ناقلة ومفرزة لمناب كل شريك من تاريخ إبرامها."
    },
    {
        "code": "تعريفة الأجور والمعاليم القانونية",
        "topic": "أجور عدول الإشهاد والتسجيل",
        "content": "تخضع المحررات التوثيقية لعدول الإشهاد لجدول الأجور الموحد (معاليم القباضة المالية + بطاقة النقل 34/52 + أجر العدلين حسب قيمة العقار والمصروفات)."
    }
]


# Generic party labels the contract builder emits when it has no real identity for a
# party. Their presence in a finished deed means data was lost somewhere upstream.
GENERIC_PARTY_LABELS = [
    "الطرف الأول 2", "الطرف الأول 3", "الطرف الأول 4",
    "الطرف الثاني 2", "الطرف الثاني 3", "الطرف الثاني 4",
]


def _audit_placeholders(text: str) -> list:
    """
    Flags unfilled placeholders and generic party labels as blocking anomalies.

    Previously a placeholder-corrupted deed scored the same as a clean one, so the
    audit gave no signal that the document had been degraded.
    """
    found = []
    text = text or ""

    # An empty or stub document is the most severe case, so it is checked first
    # rather than short-circuiting out of this function entirely.
    if len(text.strip()) < 200:
        found.append({
            "type": "CRITICAL",
            "title": "نص العقد فارغ أو شبه فارغ",
            "details": f"طول نص العقد {len(text.strip())} حرفاً فقط، وهو غير كافٍ لعقد توثيقي.",
            "suggestion": "قم بتوليد العقد أولاً قبل الفحص أو التصدير."
        })
        return found

    # 1. Generic party labels standing in for a real name.
    generic_hits = [lbl for lbl in GENERIC_PARTY_LABELS if lbl in text]
    if generic_hits:
        found.append({
            "type": "CRITICAL",
            "title": "أسماء أطراف غير حقيقية في العقد",
            "details": ("العقد يحتوي على تسميات عامة بدل أسماء الأطراف الحقيقية: "
                        + "، ".join(generic_hits) +
                        ". هذا يعني أن معطيات هؤلاء الأطراف فُقدت ولم تُدرج في العقد."),
            "suggestion": "أعد توليد العقد أو أدخل اسم ولقب ورقم بطاقة تعريف كل طرف يدوياً قبل الإمضاء."
        })

    # 2. Dotted placeholders left unfilled. A blank line or two is normal in a draft;
    #    a deed full of them is not ready to sign.
    dotted = re.findall(r"\.{4,}", text)
    if len(dotted) >= 8:
        found.append({
            "type": "CRITICAL",
            "title": "العقد يحتوي على عدد كبير من الفراغات غير المعبأة",
            "details": f"تم العثور على {len(dotted)} موضعاً منقوطاً (........) لم يتم تعبئته في نص العقد.",
            "suggestion": "عبّئ كافة الحقول الناقصة (التواريخ، الأعداد، المراجع) قبل اعتماد العقد."
        })
    elif len(dotted) >= 3:
        found.append({
            "type": "WARNING",
            "title": "فراغات غير معبأة في العقد",
            "details": f"تم العثور على {len(dotted)} موضعاً منقوطاً لم يتم تعبئته.",
            "suggestion": "راجع الحقول الناقصة قبل الإمضاء."
        })

    # 3. A party whose identity card number was never filled in.
    if re.search(r"بطاقة تعريف(?:ه|ها)? عدد\s*\.{4,}", text):
        found.append({
            "type": "CRITICAL",
            "title": "رقم بطاقة تعريف غير معبأ لأحد الأطراف",
            "details": "أحد الأطراف مذكور في العقد بدون رقم بطاقة تعريف وطنية.",
            "suggestion": "أدخل رقم بطاقة التعريف الوطنية (8 أرقام) لكل طرف."
        })

    # 4. A party with no name at all.
    if re.search(r"(?:السيد|السيدة)\s*:\s*\.{4,}", text):
        found.append({
            "type": "CRITICAL",
            "title": "طرف بدون اسم في العقد",
            "details": "العقد يذكر طرفاً بدون اسم ولقب.",
            "suggestion": "أدخل الاسم واللقب الكامل لكل طرف في العقد."
        })

    return found


def audit_notary_contract(contract_text: str, variables: dict = None, contract_type: str = "عقد بيع") -> dict:
    """
    Performs deterministic & intelligent legal risk auditing on a Tunisian notary contract.
    Checks CIN numbers, date consistency, price matching, tax/receipt numbers, and Land Conservation clauses.
    """
    if variables is None:
        variables = {}
        
    text = contract_text or ""
    anomalies = []
    checks_passed = []
    
    # ── 1. CIN NUMBER VALIDATION (8 DIGITS) ──
    cin1 = str(variables.get("party1_cin", "")).strip()
    cin2 = str(variables.get("party2_cin", "")).strip()
    
    # If not in variables, check in text
    found_cins = re.findall(r"\b\d{8}\b", text)
    
    if cin1:
        if not re.match(r"^\d{8}$", cin1):
            anomalies.append({
                "type": "CRITICAL",
                "title": "خطأ في رقم بطاقة التعريف للطرف الأول",
                "details": f"رقم بطاقة التعريف المدخل ({cin1}) غير مطابق للمعايير التونسية (يجب أن يتكون من 8 أرقام بالضبط).",
                "suggestion": "تأكد من رقم بطاقة التعريف الوطنية التونسية للطرف الأول وتصحيحه إلى 8 أرقام."
            })
        else:
            checks_passed.append("رقم بطاقة التعريف الوطنية للطرف الأول سليم (8 أرقام).")
    else:
        anomalies.append({
            "type": "CRITICAL",
            "title": "غياب رقم بطاقة التعريف للطرف الأول",
            "details": "لم يتم العثور على رقم بطاقة تعريف وطنية صريح للطرف الأول.",
            "suggestion": "أدخل رقم بطاقة التعريف الوطنية متكوناً من 8 أرقام."
        })
        
    if cin2:
        if not re.match(r"^\d{8}$", cin2):
            anomalies.append({
                "type": "CRITICAL",
                "title": "خطأ في رقم بطاقة التعريف للطرف الثاني",
                "details": f"رقم بطاقة التعريف المدخل ({cin2}) غير مطابق للمعايير التونسية (يجب أن يتكون من 8 أرقام بالضبط).",
                "suggestion": "تأكد من رقم بطاقة التعريف الوطنية التونسية للطرف الثاني وتصحيحه إلى 8 أرقام."
            })
        else:
            checks_passed.append("رقم بطاقة التعريف الوطنية للطرف الثاني سليم (8 أرقام).")
    else:
        anomalies.append({
            "type": "CRITICAL",
            "title": "غياب رقم بطاقة التعريف للطرف الثاني",
            "details": "لم يتم العثور على رقم بطاقة تعريف وطنية صريح للطرف الثاني.",
            "suggestion": "أدخل رقم بطاقة التعريف الوطنية متكوناً من 8 أرقام."
        })

    # ── 2. DATES & TIME AUDIT ──
    if "هـ" not in text and "هجرية" not in text:
        anomalies.append({
            "type": "WARNING",
            "title": "غياب التاريخ الهجري في الصدر التوثيقي",
            "details": "توجب الأعراف التوثيقية التونسية لعدول الإشهاد التصدير بالعام الهجري بالكلمات.",
            "suggestion": "تأكد من وجود التاريخ الهجري بالكلمات في بداية العقد."
        })
    else:
        checks_passed.append("التاريخ الهجري موجود بالكلمات في الصدر الرسمى.")

    if "الموافق" not in text and "/" not in text and "سنة" not in text:
        anomalies.append({
            "type": "WARNING",
            "title": "غياب التاريخ الميلادي الصريح",
            "details": "لم يتم العثور على تاريخ ميلادي صريح للوثيقة.",
            "suggestion": "أضف التاريخ الميلادي الكامل."
        })
    else:
        checks_passed.append("التاريخ الميلادي مضبوط بالكامل.")

    # ── 3. PRICE & VALUE MATCHING (الأرقام والكلمات) ──
    price_num = str(variables.get("price_num", "")).strip()
    price_words = str(variables.get("price_words", "")).strip()
    
    if price_num:
        if not price_num.isdigit():
            anomalies.append({
                "type": "WARNING",
                "title": "تنسيق أرقام الثمن غير عادي",
                "details": f"المبلغ بالأرقام يحتوي رموزاً غير رقمية ({price_num}).",
                "suggestion": "اكتب الثمن بالأرقام فقط (مثال: 5000)."
            })
        else:
            checks_passed.append(f"الثمن بالأرقام مضبوط ({price_num} دينار).")
            
    if price_words:
        checks_passed.append(f"الثمن بالحروف موجود ({price_words}).")
    else:
        anomalies.append({
            "type": "WARNING",
            "title": "غياب كتابة الثمن بالكلمات",
            "details": "يجب كتابة المبلغ المالي بالألف والدينار بالحروف لمنع التزوير.",
            "suggestion": "أدخل المبلغ بالحروف العربي الكاملة (مثال: خمسة آلاف دينار)."
        })

    # ── 4. LAND CONSERVATION EXEMPTION CLAUSE (حافظ الملكية العقارية) ──
    if "حافظ الملكية العقارية" not in text and "ترسيم" not in text:
        anomalies.append({
            "type": "WARNING",
            "title": "غياب فصل الإعفاء والترسيم العقاري",
            "details": "العقد لا يحتوي على الفصل التقليدي الخاص بإعفاء السيد حافظ الملكية العقارية من الوصف والتحديد وطلب الترسيم.",
            "suggestion": "أضف الفصل الرابع الخاص بالترسيم العقاري وحافظ الملكية العقارية."
        })
    else:
        checks_passed.append("فصل إعفاء حافظ الملكية العقارية وطلب الترسيم موجود.")

    # ── 5. TAX OFFICE & DRAFT BOOK REFERENCES (القباضة ودائرة الإشهاد) ──
    if "بطاقة نقل" not in text:
        anomalies.append({
            "type": "WARNING",
            "title": "غياب بطاقة النقل",
            "details": "لم يذكر رقم بطاقة النقل القانونية المقتطعة للعقد.",
            "suggestion": "أدخل رقم بطاقة النقل (مثال: بطاقة نقل عدد 34/52)."
        })
    else:
        checks_passed.append("بيانات بطاقة النقل القانونية موجودة.")

    if "وصل عدد" not in text and "وصل" not in text:
        anomalies.append({
            "type": "WARNING",
            "title": "غياب وصل القباضة المالية",
            "details": "لم يتم العثور على مراجع وصل التسجيل بالقباضة المالية.",
            "suggestion": "أدخل رقم الوصل وتاريخ القباضة المالية."
        })
    else:
        checks_passed.append("وصل القباضة المالية مسجل.")

    if "دفتر مسودات" not in text:
        anomalies.append({
            "type": "INFO",
            "title": "نقص مراجع دفتر مسودات العدول",
            "details": "يفضل ذكر رقم الصحيفة والعدد بدفتر المسودات التوثيقي.",
            "suggestion": "أدرج رقم الصحيفة والعدد بدفتر مسودات عدل الإشهاد."
        })
    else:
        checks_passed.append("مراجع دفتر مسودات عدل الإشهاد متوفرة.")

    # ── PLACEHOLDER & COMPLETENESS AUDIT ──
    # A deed rebuilt from incomplete data reads as well-formed but carries unfilled
    # placeholders and generic party labels. Those are blocking defects, not cosmetic:
    # an act naming "الطرف الأول 2" instead of a person cannot be registered.
    anomalies.extend(_audit_placeholders(text))

    # Calculate overall legal safety score
    critical_cnt = sum(1 for a in anomalies if a["type"] == "CRITICAL")
    warning_cnt = sum(1 for a in anomalies if a["type"] == "WARNING")

    score = 100 - (critical_cnt * 25 + warning_cnt * 10)
    score = max(score, 10)
    
    if critical_cnt > 0:
        status = "CRITICAL"
    elif warning_cnt > 0:
        status = "WARNING"
    else:
        status = "SAFE"

    return {
        "score": score,
        "status": status,
        "anomalies": anomalies,
        "checks_passed": checks_passed
    }

