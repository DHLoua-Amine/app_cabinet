"""
contract_templates.py — Standard Core Templates for Tunisian Notary Contracts (عدول الإشهاد)
Supports 4 core contract types:
1. عقد بيع (Sale Contract)
2. عقد هبة (Donation Contract)
3. عقد مقاسمة (Partition/Division Contract)
4. عقد تنازل (Waiver/Relinquishment Contract)
"""

import re
import datetime

CONTRACT_CATEGORIES = {
    "العقود العقارية والتفويت": [
        "عقد بيع",
        "عقد هبة",
        "عقد مقاسمة",
        "تنازل",
        "وعد بالبيع",
        "التزام بالبيع",
        "إسقاط",
        "إشهاد بالحوز",
        "معاوضة",
        "عقد كراء توثيقي",
        "عقد رهن عقاري"
    ],
    "الأحوال الشخصية والتركات": [
        "عقد صداق وزواج",
        "توكيل",
        "تكليف وتوكيل",
        "حجة وفاة",
        "فريضة شرعية",
        "فريضة جزئية",
        "عقد وصية",
        "عقد تخارج من التركة"
    ],
    "التعهدات والالتزامات والصلح": [
        "اتفاق",
        "وصل خلاص",
        "إسقاط دعوى",
        "عقد إقرار بدين والتزام",
        "عقد تأسيس شركة",
        "عقد بيع أصل تجاري"
    ]
}

def populate_categorized_contract_types(combo, first_item=None, default_selected=None):
    """
    Populates any QComboBox with ALL contract types categorized into sections
    matching CONTRACT_CATEGORIES. Section headers are unselectable.
    """
    from PySide6.QtCore import Qt
    combo.blockSignals(True)
    combo.clear()

    if first_item:
        combo.addItem(first_item, "")

    for cat_name, contracts in CONTRACT_CATEGORIES.items():
        combo.addItem(f"── {cat_name} ──", "HEADER")
        row = combo.count() - 1
        model = combo.model()
        if hasattr(model, "item"):
            it = model.item(row)
            if it:
                it.setFlags(Qt.ItemFlag.NoItemFlags)

        for c in contracts:
            combo.addItem(f"   {c}", c)

    combo.blockSignals(False)

    if default_selected:
        idx = combo.findData(default_selected)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        else:
            for i in range(combo.count()):
                if default_selected.strip() in combo.itemText(i):
                    combo.setCurrentIndex(i)
                    break

CONTRACT_TYPES = {
    "عقد بيع": "عقد بيع",
    "عقد هبة": "عقد هبة",
    "عقد مقاسمة": "عقد مقاسمة",
    "تنازل": "تنازل",
    "وعد بالبيع": "وعد بالبيع",
    "التزام بالبيع": "التزام بالبيع",
    "إسقاط": "إسقاط",
    "إشهاد بالحوز": "إشهاد بالحوز",
    "معاوضة": "معاوضة",
    "عقد كراء توثيقي": "عقد كراء توثيقي",
    "عقد رهن عقاري": "عقد رهن عقاري",
    "عقد صداق وزواج": "عقد صداق وزواج",
    "توكيل": "توكيل",
    "تكليف وتوكيل": "تكليف وتوكيل",
    "حجة وفاة": "حجة وفاة",
    "فريضة شرعية": "فريضة شرعية",
    "فريضة جزئية": "فريضة جزئية",
    "عقد وصية": "عقد وصية",
    "عقد تخارج من التركة": "عقد تخارج من التركة",
    "اتفاق": "اتفاق",
    "وصل خلاص": "وصل خلاص",
    "إسقاط دعوى": "إسقاط دعوى",
    "عقد تأسيس شركة": "عقد تأسيس شركة",
    "عقد بيع أصل تجاري": "عقد بيع أصل تجاري",
    "عقد إقرار بدين والتزام": "عقد إقرار بدين والتزام"
}

# ── OFFICIAL HEADER & FOOTER BOXES MATCHING IMAGE 1 ──
# The header and footer are no longer literals naming one notary: they are
# rendered from the office profile, which the office fills in from Paramètres.
# Kept as module attributes so existing callers keep working.
# ── Deux actes retirés du menu, volontairement ───────────────────────────────
# كتب تكميلي (acte complémentaire) et كتب توضيحي (acte explicatif) étaient
# proposés au notaire mais n'avaient AUCUNE branche dans
# build_multi_party_contract_text(). Aucun des drapeaux is_* ne correspondant à
# leur libellé, ils retombaient sur la branche par défaut — celle de la vente —
# et produisaient mot pour mot un acte de vente : rôles البائع / المشتري,
# clause « باع واحال », prix encaissé. Un notaire demandant un acte explicatif
# obtenait donc un acte déclarant une cession et un prix.
#
# Ils sont retirés plutôt que réécrits : ces deux actes se réfèrent à un acte
# antérieur qu'ils complètent ou clarifient, et leur formulation consacrée n'a
# pas été vérifiée auprès d'un notaire. Inventer une clause plausible dans un
# logiciel notarial est plus dangereux que ne pas proposer le type.
#
# Pour les rétablir : remettre leur libellé dans CONTRACT_CATEGORIES et
# CONTRACT_TYPES ci-dessus, ET ajouter la branche correspondante dans
# build_multi_party_contract_text() — sans quoi le repli sur la vente
# recommencera silencieusement.
_ACTES_RETIRES = ("كتب تكميلي", "كتب توضيحي")


def _office_header():
    import office_profile
    return office_profile.header_html()


def _office_footer():
    import office_profile
    return office_profile.footer_html()


def __getattr__(name):
    """Renders NOTARY_HEADER_HTML / NOTARY_FOOTER_HTML on access."""
    if name == "NOTARY_HEADER_HTML":
        return _office_header()
    if name == "NOTARY_FOOTER_HTML":
        return _office_footer()
    raise AttributeError(name)


def get_party_role_names(contract_type: str) -> tuple:
    """
    Returns (party1_sing, party1_plur, party2_sing, party2_plur, allow_multi_party)
    """
    c = contract_type or "عقد بيع"
    if "هبة" in c:
        return ("الواهب", "الواهبون", "الموهوب له", "الموهوب لهم", True)
    elif "تنازل" in c and "إسقاط" not in c:
        return ("المتنازل", "المتنازلون", "المتنازل له", "المتنازل لهم", True)
    elif "إسقاط وتنازل" in c:
        return ("المسقط المتنازل", "المسقطون المتنازلون", "المسقط له المتنازل له", "المسقط لهم المتنازل لهم", True)
    elif "دعوى" in c:
        return ("الشاكي المسقط", "الشاكون المسقطون", "المستفيد من الإسقاط", "المستفيدون من الإسقاط", True)
    elif "إسقاط" in c or "اسقاط" in c:
        return ("المسقط", "المسقطون", "المسقط له", "المسقط لهم", True)
    elif "التزام بالبيع" in c:
        return ("الملتزم بالبيع", "الملتزمون بالبيع", "الملتزم له بالبيع", "الملتزم لهم بالبيع", True)
    elif "وعد" in c:
        return ("الواعد بالبيع", "الواعدون بالبيع", "الموعود له بالبيع", "الموعود لهم بالبيع", True)
    elif "حوز" in c:
        return ("طالب الإشهاد بالحوز", "طالبو الإشهاد بالحوز", "الشاهد الأول", "الشاهدان المكلفان", True)
    elif "تكليف" in c:
        return ("المكلف", "المكلفون", "الأستاذ الوكيل", "الأساتذة الوكلاء", True)
    elif "اتفاق" in c:
        return ("الطرف الأول", "الطرف الأول", "الطرف الثاني", "الطرف الثاني", True)
    elif "وصل" in c or "إبراء" in c:
        return ("الدائن المقر بالقبض", "الدائنون المقرون بالقبض", "المدين المبرأ", "المدينون المبرؤون", True)
    elif "مقاسمة" in c:
        return ("المتقاسم الأول", "المتقاسمون الأوائل", "المتقاسم الثاني", "المتقاسمون الثواني", True)
    elif "معاوضة" in c:
        return ("المتبادل الأول", "المتبادلون الأوائل", "المتبادل الثاني", "المتبادلون الثواني", True)
    elif "كراء" in c:
        return ("المؤجر", "المؤجرون", "المستأجر", "المستأجرون", True)
    elif "رهن" in c:
        return ("الراهن", "الراهنون", "المرتهن", "المرتهنون", True)
    elif "صداق" in c or "زواج" in c:
        return ("الزوج", "الزوج", "الزوجة", "الزوجة", False)
    elif "توكيل" in c:
        return ("الموكل", "الموكلون", "الوكيل", "الوكلاء", True)
    elif "وفاة" in c or "فريضة" in c:
        return ("طالب الإشهاد", "طالبو الإشهاد", "الموروث الهالك", "الهالك", False)
    elif "وصية" in c:
        return ("الموصي", "الموصون", "الموصى له", "الموصى لهم", True)
    elif "تخارج" in c:
        return ("المتخارج", "المتخارجون", "المتخارج له", "المتخارج لهم", True)
    elif "شركة" in c:
        return ("الشريك الأول", "الشركاء المؤسسون", "الشريك الثاني", "باقي الشركاء", True)
    elif "أصل تجاري" in c:
        return ("البائع للأصل التجاري", "البائعون للأصل التجاري", "المشتري للأصل التجاري", "المشترون للأصل التجاري", True)
    elif "إقرار بدين" in c or "دين" in c:
        return ("المدين", "المدينون", "الدائن", "الدائنون", True)
    else:
        return ("البائع", "البائعون", "المشتري", "المشترون", True)

# ── FEMALE FIRST NAMES DETECTOR FOR TUNISIAN LEGAL GENDER ACCORD ──
FEMALE_NAMES_SET = {
    "وصال", "مريم", "فاطمة", "زكية", "منى", "سارة", "أمل", "أميرة", "هدى", "ريم",
    "إيناس", "نسرين", "لبنى", "نجوى", "يسرى", "سلمى", "شيماء", "عبير", "إيمان", "منال",
    "سمية", "ولاء", "إلهام", "ندى", "سميرة", "وفاء", "نعيمة", "جميلة", "زينب", "نادية",
    "سليمة", "ليلى", "سعاد", "كوثر", "دليلة", "حسناء", "أسمهان", "هناء", "ليلي", "فتحية",
    "راضية", "وسيلة", "رجاء", "لطيفة", "سامية", "ناجية", "صليحة", "ناهد", "مبروكة", "أسماء",
    "خديجة", "آسيا", "سندس", "غادة", "خلود", "سوار", "صفاء", "وئام", "ياسمين", "زينوبة", "أنيسة"
}

def detect_tunisian_gender(name: str) -> str:
    """Returns 'F' for Female or 'M' for Male based on Tunisian proper noun analysis."""
    if not name:
        return "M"
    first_word = str(name).strip().split()[0]
    if first_word in FEMALE_NAMES_SET or first_word.endswith("ة"):
        return "F"
    return "M"

# ── CORE TEMPLATES DEFINITIONS WITH GENDER ACCORD TAGS ──

TEMPLATE_SALE = """الحمد لله في يوم {day_words} من {hijri_date} هـ الموافق لـ {gregorian_date} {notary_block} انعقد بين الطرف الأول {party1_role}: {party1_name} {party1_born_prefix} {party1_birthplace} في {party1_birthdate} {party1_nat} {party1_job} {party1_cin_prefix} {party1_cin} مؤرخة في {party1_cin_date} {party1_resident_prefix} {party1_addr}. الطرف الثاني {party2_role}: {party2_name} {party2_born_prefix} {party2_birthplace} في {party2_birthdate} {party2_nat} {party2_job} {party2_cin_prefix} {party2_cin} مؤرخة في {party2_cin_date} {party2_resident_prefix} {party2_addr}. اللذان اتفقا. الفصل الأول: باع واحال الطرف الأول تحت سائر الضمانات الفعلية والقانونية للطرف الثاني الذي قبل جميع {property_desc}. الفصل الثاني: تم البيع نظير مبلغ جملي قدره {price_words} ({price_num} دينار) قبضها البائع بذكره. الفصل الثالث: انجرار الملكية {ownership_origin}. وأبرم العقد بين طرفيه وتلي فوافقا وأمضيا واقتطعت فيه بطاقة نقل عدد ................ خالص معلوم نقلها بالقباضة المالية بـ{tax_office} بتاريخ ................ وصل عدد ................م. ورسم بدفتر مسودات أولهما صحيفة ................ عدد ................ أجره والمصاريف القانونية دنانير والله الموفق."""

TEMPLATE_HIBA = """الحمد لله في يوم {day_words} من {hijri_date} هـ الموافق لـ {gregorian_date} {notary_block} انعقد بين الطرف الأول {party1_role}: {party1_name} {party1_born_prefix} {party1_birthplace} في {party1_birthdate} {party1_nat} {party1_job} {party1_cin_prefix} {party1_cin} مؤرخة في {party1_cin_date} {party1_resident_prefix} {party1_addr}. الطرف الثاني {party2_role}: {party2_name} {party2_born_prefix} {party2_birthplace} في {party2_birthdate} {party2_nat} {party2_job} {party2_cin_prefix} {party2_cin} مؤرخة في {party2_cin_date} {party2_resident_prefix} {party2_addr}. اتفقا. الفصل الأول: وهبت وسلمت وحوزت الطرف الأول تحت سائر الضمانات الفعلية والقانونية للطرف الثاني الذي قبل جميع {property_desc}. الفصل الثاني: قيمة العقار الموهوب {price_words} ({price_num} دينار). الفصل الثالث: انجرار الملكية {ownership_origin}. الفصل الرابع: يعفي الطرفان السيد حافظ الملكية العقارية من اعتبار الوصف والتحديد والتخصيص ويطلبان ترسيم الهبة في حدود ما ذكر. وأبرم العقد بين طرفيه وتلي فوافقا وأمضيا واقتطعت فيه بطاقة نقل عدد ................ خالص معلوم نقلها بالقباضة المالية بـ{tax_office} بتاريخ ................ وصل عدد ................م. ورسم بدفتر مسودات أولهما صحيفة ................ عدد ................ أجره والمصاريف القانونية دنانير والله الموفق."""

TEMPLATE_MOUKASSMA = """الحمد لله في يوم {day_words} من {hijri_date} هـ الموافق لـ {gregorian_date} {notary_block} انعقد بين المتقاسمين: الطرف الأول: {party1_name} {party1_born_prefix} {party1_birthplace} في {party1_birthdate} {party1_nat} {party1_job} {party1_cin_prefix} {party1_cin} مؤرخة في {party1_cin_date} {party1_resident_prefix} {party1_addr}. الطرف الثاني: {party2_name} {party2_born_prefix} {party2_birthplace} في {party2_birthdate} {party2_nat} {party2_job} {party2_cin_prefix} {party2_cin} مؤرخة في {party2_cin_date} {party2_resident_prefix} {party2_addr}. اتّفقا على المقاسمة الرضائية كما يلي: الفصل الأول: أخرج وانفرد الطرف الأول بجميع المناب الحاصل له في {property_desc}. الفصل الثاني: أخرج وانفرد الطرف الثاني بجميع منابه في قسمة المشترك المذكور تحت سائر الضمانات القانونية. الفصل الثالث: قيمة المشترك ومناب الطرفين تم تقديره بـ {price_words} ({price_num} دينار) وتراضيا على التعديل بدون معدل. الفصل الرابع: انجرار الملكية {ownership_origin}. الفصل الخامس: يعفي الطرفان السيد حافظ الملكية العقارية من اعتبار الوصف والتحديد والتخصيص ويطلبان ترسيم المقاسمة في حدود ما ذكر. وأبرم العقد بين طرفيه وتلي فوافقا وأمضيا واقتطعت فيه بطاقة نقل عدد ................ خالص معلوم نقلها بالقباضة المالية بـ{tax_office} بتاريخ ................ وصل عدد ................م. ورسم بدفتر مسودات أولهما صحيفة ................ عدد ................ أجره والمصاريف القانونية دنانير والله الموفق."""

TEMPLATE_TANAZOL = """الحمد لله في يوم {day_words} من {hijri_date} هـ الموافق لـ {gregorian_date} {notary_block} انعقد بين الطرف الأول {party1_role}: {party1_name} {party1_born_prefix} {party1_birthplace} في {party1_birthdate} {party1_nat} {party1_job} {party1_cin_prefix} {party1_cin} مؤرخة في {party1_cin_date} {party1_resident_prefix} {party1_addr}. الطرف الثاني {party2_role}: {party2_name} {party2_born_prefix} {party2_birthplace} في {party2_birthdate} {party2_nat} {party2_job} {party2_cin_prefix} {party2_cin} مؤرخة في {party2_cin_date} {party2_resident_prefix} {party2_addr}. اتفقا. الفصل الأول: تنازل الطرف الأول واسقط جميع حقوقه ومناباته الفعلية والقانونية للطرف الثاني الذي قبل جميع {property_desc}. الفصل الثاني: تم هذا التنازل {price_words} (بقيمة {price_num} دينار). الفصل الثالث: انجرار الملكية والحق المتنازل عنه {ownership_origin}. الفصل الرابع: يعفي الطرفان السيد حافظ الملكية العقارية من اعتبار الوصف والتحديد والتخصيص ويطلبان ترسيم التنازل في حدود ما ذكر. وأبرم العقد بين طرفيه وتلي فوافقا وأمضيا واقتطعت فيه بطاقة نقل عدد ................ خالص معلوم نقلها بالقباضة المالية بـ{tax_office} بتاريخ ................ وصل عدد ................م. ورسم بدفتر مسودات أولهما صحيفة ................ عدد ................ أجره والمصاريف القانونية دنانير والله الموفق."""

TEMPLATE_MAAWADA = """الحمد لله في يوم {day_words} من {hijri_date} هـ الموافق لـ {gregorian_date} {notary_block} انعقد بين المتبادلين: الطرف الأول: {party1_name} {party1_born_prefix} {party1_birthplace} في {party1_birthdate} {party1_nat} {party1_job} {party1_cin_prefix} {party1_cin} مؤرخة في {party1_cin_date} {party1_resident_prefix} {party1_addr}. الطرف الثاني: {party2_name} {party2_born_prefix} {party2_birthplace} في {party2_birthdate} {party2_nat} {party2_job} {party2_cin_prefix} {party2_cin} مؤرخة في {party2_cin_date} {party2_resident_prefix} {party2_addr}. اتّفقا على المعاوضة وتبادل العقارات كما يلي: الفصل الأول: عاوض وسلم الطرف الأول للطرف الثاني الذي قبل جميع {property_desc}. الفصل الثاني: عاوض وسلم الطرف الثاني للطرف الأول العقار المقابل بقيمة {price_words} ({price_num} دينار). الفصل الثالث: انجرار الملكية {ownership_origin}. وأبرم العقد بين طرفيه وتلي فوافقا وأمضيا واقتطعت فيه بطاقة نقل عدد ................ خالص معلوم نقلها بالقباضة المالية بـ{tax_office} بتاريخ ................ وصل عدد ................م. ورسم بدفتر مسودات أولهما صحيفة ................ عدد ................ أجره والمصاريف القانونية دنانير والله الموفق."""

TEMPLATE_KERAA = """الحمد لله في يوم {day_words} من {hijri_date} هـ الموافق لـ {gregorian_date} {notary_block} انعقد بين الطرف الأول المؤجر: {party1_name} {party1_born_prefix} {party1_birthplace} في {party1_birthdate} {party1_nat} {party1_job} {party1_cin_prefix} {party1_cin} مؤرخة في {party1_cin_date} {party1_resident_prefix} {party1_addr}. الطرف الثاني المستأجر: {party2_name} {party2_born_prefix} {party2_birthplace} في {party2_birthdate} {party2_nat} {party2_job} {party2_cin_prefix} {party2_cin} مؤرخة في {party2_cin_date} {party2_resident_prefix} {party2_addr}. اتفقا على عقد الكراء التوثيقي التالي: الفصل الأول: سوغ المؤجر للمستأجر المكاني الذي قبل جميع {property_desc}. الفصل الثاني: قدر الكراء الشهري بـ {price_words} ({price_num} دينار) يدفع بداية كل شهر. الفصل الثالث: مدة الكراء سنة واحدة قابلة للتجديد بالتراضي. وأبرم العقد بين طرفيه وتلي فوافقا وأمضيا واقتطعت فيه بطاقة نقل عدد ................ خالص معلوم نقلها بالقباضة المالية بـ{tax_office} بتاريخ ................ وصل عدد ................م. ورسم بدفتر مسودات أولهما صحيفة ................ عدد ................ أجره والمصاريف القانونية دنانير والله الموفق."""

TEMPLATE_RAHN = """الحمد لله في يوم {day_words} من {hijri_date} هـ الموافق لـ {gregorian_date} {notary_block} انعقد بين الطرف الأول الراهن: {party1_name} {party1_born_prefix} {party1_birthplace} في {party1_birthdate} {party1_nat} {party1_job} {party1_cin_prefix} {party1_cin} مؤرخة في {party1_cin_date} {party1_resident_prefix} {party1_addr}. الطرف الثاني المرتهن: {party2_name} {party2_born_prefix} {party2_birthplace} في {party2_birthdate} {party2_nat} {party2_job} {party2_cin_prefix} {party2_cin} مؤرخة في {party2_cin_date} {party2_resident_prefix} {party2_addr}. اتفقا على الرهن العقاري التوثيقي: الفصل الأول: رهن وسجل الطرف الأول لفائدة الطرف الثاني ضماناً لوفاء الدين العقار التالي: {property_desc}. الفصل الثاني: مبلغ الدين المضمون بالرهن قدره {price_words} ({price_num} دينار). الفصل الثالث: انجرار الملكية {ownership_origin}. وأبرم العقد بين طرفيه وتلي فوافقا وأمضيا واقتطعت فيه بطاقة نقل عدد ................ خالص معلوم نقلها بالقباضة المالية بـ{tax_office} بتاريخ ................ وصل عدد ................م. ورسم بدفتر مسودات أولهما صحيفة ................ عدد ................ أجره والمصاريف القانونية دنانير والله الموفق."""

TEMPLATE_ZAWADJ = """الحمد لله في يوم {day_words} من {hijri_date} هـ الموافق لـ {gregorian_date} {notary_block} انعقد عقد الزواج والصداق الشرعي بين الزوج: {party1_name} المولود بـ {party1_birthplace} في {party1_birthdate} {party1_nat} {party1_job} بطاقة تعريفه عدد {party1_cin} مؤرخة في {party1_cin_date} قاطن بـ {party1_addr}. والزوجة: {party2_name} المولودة بـ {party2_birthplace} في {party2_birthdate} {party2_nat} {party2_job} بطاقة تعريفها عدد {party2_cin} مؤرخة في {party2_cin_date} قاطنة بـ {party2_addr}. اتفقا على عقد الزواج الشرعي والتوثيقي: الفصل الأول: رغبا في الزواج الشرعي وقبلا ببعضهما وفق أحكام مجلة الأحوال الشخصية التونسية. الفصل الثاني: الصداق المسمى بينهما قدره {price_words} ({price_num} دينار) قبضته الزوجة بذراعها. وأبرم العقد وتلي فوافقا وأمضيا بحضور الشاهدين المكلفين والله الموفق."""

TEMPLATE_TAWKEEL = """الحمد لله في يوم {day_words} من {hijri_date} هـ الموافق لـ {gregorian_date} {notary_block} أقام التوكيل التوثيقي الموكل: {party1_name} {party1_born_prefix} {party1_birthplace} في {party1_birthdate} {party1_nat} {party1_job} {party1_cin_prefix} {party1_cin} مؤرخة في {party1_cin_date} {party1_resident_prefix} {party1_addr}. لفائدة الوكيل: {party2_name} {party2_born_prefix} {party2_birthplace} في {party2_birthdate} {party2_nat} {party2_job} {party2_cin_prefix} {party2_cin} مؤرخة في {party2_cin_date} {party2_resident_prefix} {party2_addr}. اتفقا على التوكيل: الفصل الأول: وكل الموكل الوكيل المذكور في القيام بكافة الإجراءات التوثيقية والإدارية والقانونية الخاصة بـ {property_desc}. الفصل الثاني: للوكيل حق التوقيع والتمثيل أمام كافة الإدارات والقباضات المالية والمحاكم وحافظ الملكية العقارية. وأبرم التوكيل وتلي فوافقا وأمضيا والله الموفق."""

TEMPLATE_HOJJAT_WAFAT = """الحمد لله في يوم {day_words} من {hijri_date} هـ الموافق لـ {gregorian_date} {notary_block}.
حضَرَ لدينا نحن:
{party1_name} {party1_born_prefix} {party1_birthplace} في {party1_birthdate} {party1_nat} {party1_job} {party1_cin_prefix} {party1_cin} مؤرخة في {party1_cin_date} {party1_resident_prefix} {party1_addr} بوصفه(ا) مصرحاً بالوفاة.
كما حضَرَ لدينا الشاهدان الإثنين المكلفان شرعاً وقانوناً:
الأول: السيد ........................
والثاني: السيد ........................
وذكَرا أنهما يعرفان الهالك(ة) المرحوم(ة): {party2_name} {party2_born_prefix} {party2_birthplace} في {party2_birthdate} {party2_nat} {party2_job} {party2_cin_prefix} {party2_cin} مؤرخة في {party2_cin_date} {party2_resident_prefix} {party2_addr} معرفة تامة وشَهِدا بأنه(ا) توفي(ت) بـ {party2_birthplace} بتاريخ {party2_birthdate} حسبما هو مضمن برسم وفاته(ا) عدد ................ المحرر من ضابط الحالة المدنية ببلدية ................ .
وقَد ترَك(ت) ورثته(ا) الشرعيين الآتي ذكرهم: {property_desc} ولا غَير.
هذا ما تم تلقيه وتلي فوافقوا وأمضوا ورسم بدفتر مسودات أولهما صحيفة ................ تحت عدد ................ أجره والمصاريف القانونية دنانير والله الموفق."""

TEMPLATE_WASSIYA = """الحمد لله في يوم {day_words} من {hijri_date} هـ الموافق لـ {gregorian_date} {notary_block} حرر هذا الإشهاد بالوصية الصادرة عن الموصي: {party1_name} {party1_born_prefix} {party1_birthplace} في {party1_birthdate} {party1_nat} {party1_job} {party1_cin_prefix} {party1_cin} مؤرخة في {party1_cin_date} {party1_resident_prefix} {party1_addr}. لفائدة الموصى له: {party2_name} {party2_born_prefix} {party2_birthplace} في {party2_birthdate} {party2_nat} {party2_job} {party2_cin_prefix} {party2_cin} مؤرخة في {party2_cin_date} {party2_resident_prefix} {party2_addr}. اتفقا على الوصية: الفصل الأول: أوصى الموصي بعد وفاته وخروجاً من الثلث الشرعي بجميع {property_desc}. الفصل الثاني: قيمة الموصى به تقديرياً بـ {price_words} ({price_num} دينار). الفصل الثالث: انجرار ملكية الموصى به {ownership_origin}. وأبرم العقد وتلي فوافقا وأمضيا والله الموفق."""

TEMPLATE_TAKHAROUJ = """الحمد لله في يوم {day_words} من {hijri_date} هـ الموافق لـ {gregorian_date} {notary_block} انعقد بين المتخارج: {party1_name} {party1_born_prefix} {party1_birthplace} في {party1_birthdate} {party1_nat} {party1_job} {party1_cin_prefix} {party1_cin} مؤرخة في {party1_cin_date} {party1_resident_prefix} {party1_addr}. وباقي الورثة المتخارج لهم: {party2_name} {party2_born_prefix} {party2_birthplace} في {party2_birthdate} {party2_nat} {party2_job} {party2_cin_prefix} {party2_cin} مؤرخة في {party2_cin_date} {party2_resident_prefix} {party2_addr}. اتفقا على التخارج من التركة: الفصل الأول: تخارج المتخارج واسقط جميع مناباته وحقوقه الإرثية في تركة موروثهم لفائدة باقي الورثة المتخارج لهم في {property_desc}. الفصل الثاني: تم هذا التخارج مقابل بدل تخارج قدره {price_words} ({price_num} دينار). الفصل الثالث: انجرار الملكية والتركة {ownership_origin}. وأبرم العقد وتلي فوافقا وأمضيا والله الموفق."""

TEMPLATE_COMPANY = """الحمد لله في يوم {day_words} من {hijri_date} هـ الموافق لـ {gregorian_date} {notary_block} أقيم القانون الأساسي لتأسيس الشركة بين الشركاء المؤسسين: الشريك الأول: {party1_name} {party1_born_prefix} {party1_birthplace} في {party1_birthdate} {party1_nat} {party1_job} {party1_cin_prefix} {party1_cin} مؤرخة في {party1_cin_date} {party1_resident_prefix} {party1_addr}. الشريك الثاني: {party2_name} {party2_born_prefix} {party2_birthplace} في {party2_birthdate} {party2_nat} {party2_job} {party2_cin_prefix} {party2_cin} مؤرخة في {party2_cin_date} {party2_resident_prefix} {party2_addr}. اتفقوا على تأسيس شركة ذات مسؤولية محدودة: الفصل الأول: موضوع الشركة وغرضها التجاري والصناعي هو {property_desc}. الفصل الثاني: رأس مال الشركة المحدد قدره بـ {price_words} ({price_num} دينار) مقسم إلى حصص متساوية بين الشركاء. وأبرم العقد وتلي فوافقوا وأمضوا والله الموفق."""

TEMPLATE_FONDS_COMMERCE = """الحمد لله في يوم {day_words} من {hijri_date} هـ الموافق لـ {gregorian_date} {notary_block} انعقد بين البائع للأصل التجاري: {party1_name} {party1_born_prefix} {party1_birthplace} في {party1_birthdate} {party1_nat} {party1_job} {party1_cin_prefix} {party1_cin} مؤرخة في {party1_cin_date} {party1_resident_prefix} {party1_addr}. والمشتري للأصل التجاري: {party2_name} {party2_born_prefix} {party2_birthplace} في {party2_birthdate} {party2_nat} {party2_job} {party2_cin_prefix} {party2_cin} مؤرخة في {party2_cin_date} {party2_resident_prefix} {party2_addr}. اتفقا على بيع الأصل التجاري: الفصل الأول: باع واحيل للأصل التجاري بجميع عناصر المادية والمعنوية الكائن بـ {property_desc}. الفصل الثاني: تم البيع نظير مبلغ جملي قدره {price_words} ({price_num} دينار). الفصل الثالث: انجرار ملكية الأصل التجاري {ownership_origin}. وأبرم العقد وتلي فوافقا وأمضيا والله الموفق."""

TEMPLATE_IKRAR_DAIN = """الحمد لله في يوم {day_words} من {hijri_date} هـ الموافق لـ {gregorian_date} {notary_block} انعقد بين المدين المقر بالدين: {party1_name} {party1_born_prefix} {party1_birthplace} في {party1_birthdate} {party1_nat} {party1_job} {party1_cin_prefix} {party1_cin} مؤرخة في {party1_cin_date} {party1_resident_prefix} {party1_addr}. والدائن المقر له بالدين: {party2_name} {party2_born_prefix} {party2_birthplace} في {party2_birthdate} {party2_nat} {party2_job} {party2_cin_prefix} {party2_cin} مؤرخة في {party2_cin_date} {party2_resident_prefix} {party2_addr}. اتفقا على الإقرار بالدين والتعهد بالوفاء: الفصل الأول: أقر اعترف المدين بذمته الشاغلة بمبلغ الدين المستحق للدائن بسبب {property_desc}. الفصل الثاني: مبلغ الدين المحرر قدره {price_words} ({price_num} دينار) يتعهد المدين بوفائه في التاريخ المحدد. وأبرم الإشهاد وتلي فوافقا وأمضيا والله الموفق."""

TEMPLATE_WAAD_BAY3 = """الحمد لله في يوم {day_words} من {hijri_date} هـ الموافق لـ {gregorian_date} {notary_block} انعقد بين الطرف الأول الواعد بالبيع: {party1_name} {party1_born_prefix} {party1_birthplace} في {party1_birthdate} {party1_nat} {party1_job} {party1_cin_prefix} {party1_cin} مؤرخة في {party1_cin_date} {party1_resident_prefix} {party1_addr}. الطرف الثاني الموعود له بالبيع: {party2_name} {party2_born_prefix} {party2_birthplace} في {party2_birthdate} {party2_nat} {party2_job} {party2_cin_prefix} {party2_cin} مؤرخة في {party2_cin_date} {party2_resident_prefix} {party2_addr}. اتفقا على عقد الوعد بالبيع التوثيقي: الفصل الأول: وعد والتزم الواعد بالبيع بأن يبيع وينقل ملكية العقار التالي {property_desc} لفائدة الموعود له بالبيع الذي قبل ذلك. الفصل الثاني: تم هذا الوعد بالبيع نظير مبلغ جملي قدره {price_words} ({price_num} دينار). الفصل الثالث: انجرار الملكية {ownership_origin}. وأبرم العقد بين طرفيه وتلي فوافقا وأمضيا واقتطعت فيه بطاقة نقل عدد ................ خالص معلوم نقلها بالقباضة المالية بـ{tax_office} بتاريخ ................ وصل عدد ................م. ورسم بدفتر مسودات أولهما صحيفة ................ عدد ................ أجره والمصاريف القانونية دنانير والله الموفق."""

TEMPLATE_ISKAT = """الحمد لله في يوم {day_words} من {hijri_date} هـ الموافق لـ {gregorian_date} {notary_block} انعقد بين الطرف الأول المسقط: {party1_name} {party1_born_prefix} {party1_birthplace} في {party1_birthdate} {party1_nat} {party1_job} {party1_cin_prefix} {party1_cin} مؤرخة في {party1_cin_date} {party1_resident_prefix} {party1_addr}. الطرف الثاني المسقط له: {party2_name} {party2_born_prefix} {party2_birthplace} في {party2_birthdate} {party2_nat} {party2_job} {party2_cin_prefix} {party2_cin} مؤرخة في {party2_cin_date} {party2_resident_prefix} {party2_addr}. اتفقا على الإسقاط التوثيقي: الفصل الأول: أسقط الطرف الأول والغي وسحب كافة حقوقه ومناباته والدعاوى الخاصة بـ {property_desc} لفائدة الطرف الثاني الذي قبل ذلك. الفصل الثاني: تم هذا الإسقاط مقابل بدل إسقاط قدره {price_words} ({price_num} دينار). الفصل الثالث: انجرار الملكية {ownership_origin}. وأبرم العقد بين طرفيه وتلي فوافقا وأمضيا واقتطعت فيه بطاقة نقل عدد ................ خالص معلوم نقلها بالقباضة المالية بـ{tax_office} بتاريخ ................ وصل عدد ................م. ورسم بدفتر مسودات أولهما صحيفة ................ عدد ................ أجره والمصاريف القانونية دنانير والله الموفق."""

TEMPLATE_FARIDA_CHAR3EYA = """فريضة شرعية

الحمد لله وحده في يوم {day_words} من {hijri_date} هـ الموافق لـ {gregorian_date} {notary_block} وبطلب من {party1_name} {party1_born_prefix} {party1_birthplace} في {party1_birthdate} {party1_nat} {party1_job} {party1_cin_prefix} {party1_cin} مؤرخة في {party1_cin_date} {party1_resident_prefix} {party1_addr} قصد القيام بفريضة شرعية للمتوفى {party2_name} موضوع {property_desc}. وحيث توفي الهالك المذكور واطردت وتحددت منابات ورثته الشرعيين حسب حجة وفاته الصادرة في الغرض. هذا ما تم تلقيه وتلي فوافقوا وأمضوا ورسم بدفتر مسودات أولهما صحيفة ................ تحت عدد ................ أجره والمصاريف القانونية دنانير والله الموفق."""

TEMPLATE_FARIDA_JOZ2EYA = """فريضة جزئية

الحمد لله وحده في يوم {day_words} من {hijri_date} هـ الموافق لـ {gregorian_date} {notary_block} وبطلب من {party1_name} {party1_born_prefix} {party1_birthplace} في {party1_birthdate} {party1_nat} {party1_job} {party1_cin_prefix} {party1_cin} مؤرخة في {party1_cin_date} {party1_resident_prefix} {party1_addr} قصد القيام بفريضة جزئية للمتوفى {party2_name} موضوع {property_desc}. وحيث توفي الهالك المذكور واطردت وتحددت منابات ورثته الشرعيين حسب حجة وفاته الصادرة في الغرض. هذا ما تم تلقيه وتلي فوافقوا وأمضوا ورسم بدفتر مسودات أولهما صحيفة ................ تحت عدد ................ أجره والمصاريف القانونية دنانير والله الموفق."""

TEMPLATES_MAP = {
    "عقد بيع": TEMPLATE_SALE,
    "عقد هبة": TEMPLATE_HIBA,
    "عقد مقاسمة": TEMPLATE_MOUKASSMA,
    "عقد تنازل": TEMPLATE_TANAZOL,
    "عقد وعد بالبيع": TEMPLATE_WAAD_BAY3,
    "عقد إسقاط": TEMPLATE_ISKAT,
    "عقد معاوضة": TEMPLATE_MAAWADA,
    "عقد كراء توثيقي": TEMPLATE_KERAA,
    "عقد رهن عقاري": TEMPLATE_RAHN,
    "عقد صداق وزواج": TEMPLATE_ZAWADJ,
    "عقد توكيل": TEMPLATE_TAWKEEL,
    "حجة وفاة": TEMPLATE_HOJJAT_WAFAT,
    "فريضة شرعية": TEMPLATE_FARIDA_CHAR3EYA,
    "فريضة جزئية": TEMPLATE_FARIDA_JOZ2EYA,
    "عقد وصية": TEMPLATE_WASSIYA,
    "عقد تخارج من التركة": TEMPLATE_TAKHAROUJ,
    "عقد تأسيس شركة": TEMPLATE_COMPANY,
    "عقد بيع أصل تجاري": TEMPLATE_FONDS_COMMERCE,
    "عقد إقرار بدين والتزام": TEMPLATE_IKRAR_DAIN,
}

DAYS_AR = {
    "Monday": "الإثنين", "Tuesday": "الثلاثاء", "Wednesday": "الأربعاء",
    "Thursday": "الخميس", "Friday": "الجمعة", "Saturday": "السبت", "Sunday": "الأحد"
}

DAY_ORDINALS_AR = {
    1: "الأول", 2: "الثاني", 3: "الثالث", 4: "الرابع", 5: "الخامس",
    6: "السادس", 7: "السابع", 8: "الثامن", 9: "التاسع", 10: "العاشر",
    11: "الحادي عشر", 12: "الثاني عشر", 13: "الثالث عشر", 14: "الرابع عشر", 15: "الخامس عشر",
    16: "السادس عشر", 17: "السابع عشر", 18: "الثامن عشر", 19: "التاسع عشر", 20: "العشرين",
    21: "الحادي والعشرين", 22: "الثاني والعشرين", 23: "الثالث والعشرين", 24: "الرابع والعشرين", 25: "الخامس والعشرين",
    26: "السادس والعشرين", 27: "السابع والعشرين", 28: "الثامن والعشرين", 29: "التاسع والعشرين", 30: "الثلاثين", 31: "الحادي وثلاثين"
}

MONTHS_AR = {
    1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل", 5: "مايو", 6: "يونيو",
    7: "يوليو", 8: "أوت", 9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر", 12: "ديسمبر"
}

YEARS_WORDS_AR = {
    2020: "ألفين وعشرين", 2021: "ألفين وإحدى وعشرين", 2022: "ألفين واثنتين وعشرين",
    2023: "ألفين وثلاث وعشرين", 2024: "ألفين وأربع وعشرين", 2025: "ألفين وخمس وعشرين",
    2026: "ألفين وست وعشرين", 2027: "ألفين وسبع وعشرين", 2028: "ألفين وثمان وعشرين",
    2029: "ألفين وتسع وعشرين", 2030: "ألفين وثلاثين"
}

HIJRI_MONTHS_AR = {
    1: "محرم", 2: "صفر", 3: "ربيع الأول", 4: "ربيع الثاني",
    5: "جمادى الأولى", 6: "جمادى الثانية", 7: "رجب", 8: "شعبان",
    9: "رمضان", 10: "شوال", 11: "ذو القعدة", 12: "ذو الحجة"
}

HIJRI_YEARS_AR = {
    1440: "أربعين وأربعمائة وألف",
    1441: "إحدى وأربعين وأربعمائة وألف",
    1442: "اثنتين وأربعين وأربعمائة وألف",
    1443: "ثلاث وأربعين وأربعمائة وألف",
    1444: "أربع وأربعين وأربعمائة وألف",
    1445: "خمس وأربعين وأربعمائة وألف",
    1446: "ست وأربعين وأربعمائة وألف",
    1447: "سبع وأربعين وأربعمائة وألف",
    1448: "ثمان وأربعين وأربعمائة وألف",
    1449: "تسع وأربعين وأربعمائة وألف",
    1450: "خمسين وأربعمائة وألف",
    1451: "إحدى وخمسين وأربعمائة وألف",
    1452: "اثنتين وخمسين وأربعمائة وألف",
    1453: "ثلاث وخمسين وأربعمائة وألف",
    1454: "أربع وخمسين وأربعمائة وألف",
    1455: "خمس وخمسين وأربعمائة وألف"
}

def gregorian_to_hijri(dt):
    """Converts a Gregorian date/datetime object to Hijri (year, month, day)."""
    import datetime
    if isinstance(dt, datetime.datetime):
        dt = dt.date()
    y, m, d = dt.year, dt.month, dt.day
    if (y > 1582) or (y == 1582 and m > 10) or (y == 1582 and m == 10 and d > 14):
        jd = int((1461 * (y + 4800 + int((m - 14) / 12))) / 4) + \
             int((367 * (m - 2 - 12 * (int((m - 14) / 12)))) / 12) - \
             int((3 * (int((y + 4900 + int((m - 14) / 12)) / 100))) / 4) + d - 32075
    else:
        jd = 367 * y - int((7 * (y + 5001 + int((m - 9) / 7))) / 4) + \
             int((275 * m) / 9) + d + 1729777

    l = jd - 1948440 + 10632
    n = int((l - 1) / 10631)
    l = l - 10631 * n + 354
    j = (int((10985 - l) / 5316)) * (int((50 * l) / 17719)) + (int(l / 5670)) * (int((43 * l) / 15238))
    l = l - (int((30 - j) / 15)) * (int((17719 * j) / 50)) - (int(j / 16)) * (int((15238 * j) / 43)) + 29
    h_m = int((24 * l) / 709)
    h_d = l - int((709 * h_m) / 24)
    h_y = 30 * n + j - 30
    return h_y, h_m, h_d

HOURS_AR = {
    1: "الأولى", 2: "الثانية", 3: "الثالثة", 4: "الرابعة", 5: "الخامسة",
    6: "السادسة", 7: "السابعة", 8: "الثامنة", 9: "التاسعة", 10: "العاشرة",
    11: "الحادية عشرة", 12: "الثانية عشرة"
}

def convert_arabic_time_to_words(hour: int, minute: int) -> str:
    hr_12 = hour % 12
    if hr_12 == 0: hr_12 = 12
    hr_word = HOURS_AR.get(hr_12, f"{hr_12}")
    
    if minute == 0:
        min_word = "تماماً"
    elif minute == 15:
        min_word = "والربع"
    elif minute == 20:
        min_word = "والثلث"
    elif minute == 30:
        min_word = "والنصف"
    elif minute == 45:
        min_word = "إلا الربع"
    else:
        units = minute % 10
        tens = minute // 10
        u_words = ["", "واحدة", "اثنتين", "ثلاث", "أربع", "خمس", "ست", "سبع", "ثماني", "تسع"]
        t_words = ["", "عشرة", "عشرين", "ثلاثين", "أربعين", "خمسين"]
        if tens == 1 and units > 0:
            m_str = f"{u_words[units]} عشرة دقيقة"
        elif tens > 1 and units > 0:
            m_str = f"{u_words[units]} و{t_words[tens]} دقيقة"
        elif tens > 1 and units == 0:
            m_str = f"{t_words[tens]} دقيقة"
        else:
            m_str = f"{units} دقائق"
        min_word = f"و{m_str}"
        
    period_str = "صباحاً" if hour < 12 else "مساءً"
    return f"على الساعة {hr_word} {min_word} {period_str}"

def get_current_arabic_date_info(dt = None, hijri_day_ordinal: str = None, hijri_month: str = None, hijri_year: int = None) -> dict:
    """Returns day name, Hijri date, Gregorian date, and time spelled out 100% in formal Arabic words."""
    import datetime
    if dt is None:
        dt = datetime.datetime.now()
    elif isinstance(dt, datetime.date) and not isinstance(dt, datetime.datetime):
        dt = datetime.datetime.combine(dt, datetime.time(9, 0))

    day_name = DAYS_AR.get(dt.strftime("%A"), "الإثنين")
    greg_day_word = DAY_ORDINALS_AR.get(dt.day, f"لـ {dt.day}")
    greg_month = MONTHS_AR.get(dt.month, "أوت")
    greg_year_word = YEARS_WORDS_AR.get(dt.year, f"سنة {dt.year}")
    
    # Auto-calculate Hijri if parameters omitted or default
    h_y, h_m, h_d = gregorian_to_hijri(dt)
    
    # If today 2026-09-14 default, preset ordinal if specified, else use exact calculated ordinal
    if hijri_day_ordinal is None:
        hijri_day_ordinal = DAY_ORDINALS_AR.get(h_d, f"{h_d}")
    if hijri_month is None:
        hijri_month = HIJRI_MONTHS_AR.get(h_m, "ربيع الأول")
    if hijri_year is None:
        hijri_year = h_y

    hijri_year_word = HIJRI_YEARS_AR.get(hijri_year, f"{hijri_year}")
    time_words = convert_arabic_time_to_words(dt.hour, dt.minute)

    full_date_text = f"في يوم {day_name} {hijri_day_ordinal} من {hijri_month} سنة {hijri_year_word} هـ الموافق لـ{greg_day_word} من {greg_month} سنة {greg_year_word} و{time_words}"
    full_date_text_no_time = f"في يوم {day_name} {hijri_day_ordinal} من {hijri_month} سنة {hijri_year_word} هـ الموافق لـ{greg_day_word} من {greg_month} سنة {greg_year_word}"

    return {
        "day_words": f"{day_name} {hijri_day_ordinal}",
        "hijri_date": f"{hijri_month} سنة {hijri_year_word}",
        "gregorian_date": f"{greg_day_word} من {greg_month} سنة {greg_year_word}",
        "time_str": time_words,
        "full_date_text": full_date_text,
        "full_date_text_no_time": full_date_text_no_time
    }


def get_default_variables(contract_type: str = "عقد بيع", dt=None) -> dict:
    """Returns a clean default dictionary of variables with auto-computed date for filling notary templates."""
    date_info = get_current_arabic_date_info(dt=dt)
    return {
        "contract_type": contract_type,
        "date_info": date_info,
        "day_words": date_info["day_words"],
        "hijri_date": date_info["hijri_date"],
        "gregorian_date": date_info["gregorian_date"],
        "hijri_date": date_info["hijri_date"],
        "gregorian_date": date_info["gregorian_date"],
        "time_str": date_info["time_str"],
        # Filled from the office profile so a template rendered directly still
        # names the right office instead of a hardcoded one.
        "notary_block": __import__("office_profile").notary_block(),
        "tax_office": __import__("office_profile").tax_office_name(),
        
        # Party 1 (Seller / Donor / Assignor / Partition Party 1)
        "party1_name": "",
        "party1_birthplace": "",
        "party1_birthdate": "",
        "party1_nat": "تونسي الجنسية",
        "party1_job": "",
        "party1_cin": "",
        "party1_cin_date": "",
        "party1_addr": "",
        
        # Party 2 (Buyer / Donee / Assignee / Partition Party 2)
        "party2_name": "",
        "party2_birthplace": "",
        "party2_birthdate": "",
        "party2_nat": "تونسية الجنسية",
        "party2_job": "",
        "party2_cin": "",
        "party2_cin_date": "",
        "party2_addr": "",
        
        # Property / Object
        "property_desc": "",
        
        # Price / Value
        "price_words": "",
        "price_num": "",
        
        # Ownership Origin
        "ownership_origin": "",
        
        # Tax & Book details
        "transfer_card_num": "",
        "tax_date": "",
        "receipt_num": "",
        "draft_page": "",
        "draft_num": "",
    }


NUMERAL_WORDS_AR = ["أولاً", "ثانياً", "ثالثاً", "رابعاً", "خامساً", "سادساً", "سابعاً", "ثامناً", "تاسعاً", "عاشراً"]

def format_single_party_text(party_dict: dict) -> str:
    if not party_dict:
        return "........................"
    name = str(party_dict.get("full_name") or party_dict.get("name") or "").strip()
    prenom = str(party_dict.get("prenom") or "").strip()
    nom = str(party_dict.get("nom") or "").strip()
    father = str(party_dict.get("father_name") or party_dict.get("father") or "").strip()
    gfather = str(party_dict.get("grandfather_name") or party_dict.get("grandfather") or "").strip()

    if not name or "...." in name:
        name = "........................"

    gender = detect_tunisian_gender(name or prenom)
    bin_word = "بنت" if gender == "F" else "بن"

    # Construct full legal parentage name if father/grandfather names exist
    if prenom and nom and father and gfather:
        full_display_name = f"{prenom} {bin_word} {father} {bin_word} {gfather} {nom}"
    elif prenom and nom and father:
        full_display_name = f"{prenom} {bin_word} {father} {nom}"
    elif name and father and gfather and father not in name:
        full_display_name = f"{name} {bin_word} {father} {bin_word} {gfather}"
    else:
        full_display_name = name
    
    if gender == "F":
        born_prefix = "المولودة بـ"
        nat = str(party_dict.get("nationality") or "تونسية الجنسية").strip()
        cin_prefix = "بطاقة تعريفها عدد"
        resident_prefix = "قاطنة بـ"
        title_prefix = "السيدة:"
    else:
        born_prefix = "المولود بـ"
        nat = str(party_dict.get("nationality") or "تونسي الجنسية").strip()
        cin_prefix = "بطاقة تعريفه عدد"
        resident_prefix = "قاطن بـ"
        title_prefix = "السيد:"
        
    bplace = str(party_dict.get("birth_place") or party_dict.get("birthplace") or "").strip()
    bdate = str(party_dict.get("birth_date") or party_dict.get("birthdate") or "").strip()
    job = str(party_dict.get("job") or party_dict.get("profession") or "").strip()
    cin = str(party_dict.get("cin_number") or party_dict.get("cin") or "").strip()
    cin_date = str(party_dict.get("cin_issue_date") or party_dict.get("issue_date") or party_dict.get("cin_date") or "").strip()
    cin_place = str(party_dict.get("cin_issue_place") or party_dict.get("issue_place") or party_dict.get("cin_place") or "").strip()
    cin_date_place = str(party_dict.get("cin_date_place") or "").strip()
    addr = str(party_dict.get("address") or party_dict.get("addr") or "").strip()

    parts = [f"{title_prefix} {full_display_name}"]

    if bplace and "...." not in bplace and bdate and "...." not in bdate:
        parts.append(f"{born_prefix} {bplace} في {bdate}")
    elif bplace and "...." not in bplace:
        parts.append(f"{born_prefix} {bplace}")
    elif bdate and "...." not in bdate:
        parts.append(f"المولود في {bdate}" if gender == "M" else f"المولودة في {bdate}")
    else:
        parts.append(f"{born_prefix} ........................")

    if nat and "...." not in nat:
        parts.append(nat)

    if job and "...." not in job:
        parts.append(job)

    if cin and "...." not in cin:
        cin_str = f"{cin_prefix} {cin}"
        if cin_date and "...." not in cin_date:
            cin_str += f" مؤرخة في {cin_date}"
            if cin_place and "...." not in cin_place:
                cin_str += f" بـ {cin_place}"
        elif cin_date_place and "...." not in cin_date_place:
            cin_str += f" مؤرخة في {cin_date_place}"
        parts.append(cin_str)
    else:
        parts.append(f"{cin_prefix} ................")

    if addr and "...." not in addr:
        parts.append(f"{resident_prefix} {addr}")
    else:
        parts.append(f"{resident_prefix} ........................")

    return " ".join(parts)


def number_to_arabic_words(number: int | float | str) -> str:
    """Converts a numeric amount to formal Arabic words (Tafqeed)."""
    try:
        if isinstance(number, str):
            clean = re.sub(r"[^\d.]", "", number)
            if not clean:
                return ""
            num = float(clean)
        else:
            num = float(number)
            
        dinars = int(num)
        millimes = int(round((num - dinars) * 1000))
        
        if dinars == 0 and millimes == 0:
            return "صفر دينار"
            
        units = ["", "واحد", "اثنان", "ثلاثة", "أربعة", "خمسة", "ستة", "سبعة", "ثمانية", "تسعة"]
        teens = ["عشرة", "أحد عشر", "اثنا عشر", "ثلاثة عشر", "أربعة عشر", "خمسة عشر", "ستة عشر", "سبعة عشر", "ثمانية عشر", "تسعة عشر"]
        tens = ["", "عشرة", "عشرون", "ثلاثون", "أربعون", "خمسون", "ستون", "سبعون", "ثمانون", "تسعون"]
        hundreds = ["", "مائة", "مائتان", "ثلاثمائة", "أربعمائة", "خمسمائة", "ستمائة", "سبعمائة", "ثمانمائة", "تسعمائة"]
        
        def _convert_below_1000(n):
            if n == 0:
                return ""
            h = n // 100
            rem = n % 100
            res = []
            if h > 0:
                res.append(hundreds[h])
            if rem > 0:
                if rem < 10:
                    res.append(units[rem])
                elif rem < 20:
                    res.append(teens[rem - 10])
                else:
                    u = rem % 10
                    t = rem // 10
                    if u > 0:
                        res.append(f"{units[u]} و{tens[t]}")
                    else:
                        res.append(tens[t])
            return " و".join(res)

        parts = []
        th = dinars // 1000
        rem_d = dinars % 1000
        
        if th > 0:
            if th == 1:
                parts.append("ألف")
            elif th == 2:
                parts.append("ألفان")
            elif 3 <= th <= 10:
                parts.append(f"{units[th]} آلاف")
            else:
                parts.append(f"{_convert_below_1000(th)} ألف")
                
        if rem_d > 0:
            parts.append(_convert_below_1000(rem_d))
            
        d_str = " و".join(parts) if parts else ""
        if d_str:
            d_str += " دينار"
            
        m_str = ""
        if millimes > 0:
            m_words = _convert_below_1000(millimes)
            m_str = f"{m_words} مليم"
            
        if d_str and m_str:
            return f"{d_str} و{m_str}"
        elif d_str:
            return d_str
        elif m_str:
            return m_str
        return ""
    except Exception:
        return ""


def format_money_words_and_numbers(price_words: str, price_num: str) -> str:
    """
    Guarantees money is ALWAYS formatted with BOTH letters and numbers:
    e.g. 'خمسة آلاف دينار (5000 د.ت)'
    """
    p_num_clean = str(price_num or "").replace("دينار", "").replace("د.ت", "").replace("د", "").strip()
    p_words_clean = str(price_words or "").strip()

    # If price_words is missing or contains pure numbers e.g. "5000", convert to Arabic words
    if p_num_clean and (not p_words_clean or re.match(r"^[\d.,\s]+$", p_words_clean)):
        p_words_clean = number_to_arabic_words(p_num_clean)
    elif not p_num_clean and p_words_clean and re.match(r"^[\d.,\s]+$", p_words_clean):
        p_num_clean = p_words_clean
        p_words_clean = number_to_arabic_words(p_num_clean)

    if p_words_clean and "دينار" not in p_words_clean and "مليم" not in p_words_clean:
        p_words_clean += " دينار"

    if p_words_clean and p_num_clean:
        return f"{p_words_clean} ({p_num_clean} د.ت)"
    elif p_words_clean:
        return p_words_clean
    elif p_num_clean:
        words = number_to_arabic_words(p_num_clean)
        if words:
            if "دينار" not in words and "مليم" not in words:
                words += " دينار"
            return f"{words} ({p_num_clean} د.ت)"
        return f"{p_num_clean} د.ت"
    return ""


def build_multi_party_contract_text(
    contract_type: str,
    party1_list: list,
    party2_list: list,
    procuration_text: str = "",
    property_desc: str = "",
    price_words: str = "",
    price_num: str = "",
    ownership_origin: str = "",
    extra_foussoul: list = None,
    witness1_info: dict = None,
    witness2_info: dict = None,
    contract_vars: dict = None
) -> str:
    contract_vars = contract_vars or {}
    if "date_info" in contract_vars and isinstance(contract_vars["date_info"], dict):
        date_info = contract_vars["date_info"]
    elif "custom_date" in contract_vars and contract_vars["custom_date"]:
        date_info = get_current_arabic_date_info(dt=contract_vars["custom_date"])
    else:
        date_info = get_current_arabic_date_info()
    
    is_waad = "وعد" in contract_type and "التزام" not in contract_type
    is_iltizam_bay3 = "التزام بالبيع" in contract_type
    is_iskat_daawa = "دعوى" in contract_type
    is_iskat_tanazol = "إسقاط وتنازل" in contract_type
    is_iskat = ("إسقاط" in contract_type or "اسقاط" in contract_type) and "دعوى" not in contract_type and "تنازل" not in contract_type
    is_ichhad_hawz = "حوز" in contract_type
    is_takleef = "تكليف" in contract_type
    is_ittifaq = "اتفاق" in contract_type
    is_wassl_khalass = "وصل" in contract_type or "إبراء" in contract_type or "ابراء" in contract_type
    is_hiba = "هبة" in contract_type
    is_tanazol = "تنازل" in contract_type and "إسقاط" not in contract_type
    is_moukassma = "مقاسمة" in contract_type
    is_maawada = "معاوضة" in contract_type
    is_keraa = "كراء" in contract_type
    is_rahn = "رهن" in contract_type
    is_zawadj = "صداق" in contract_type or "زواج" in contract_type
    is_tawkeel = "توكيل" in contract_type and "تكليف" not in contract_type
    is_farida = "فريضة" in contract_type
    is_hojjat_wafat = "وفاة" in contract_type and not is_farida
    is_wassiya = "وصية" in contract_type
    is_takharouj = "تخارج" in contract_type
    is_company = "شركة" in contract_type
    is_fonds = "أصل تجاري" in contract_type
    is_sale = "بيع" in contract_type and not is_waad and not is_fonds and not is_iltizam_bay3
    is_ikrar = "إقرار بدين" in contract_type or "دين" in contract_type

    # The deed records the day, not the hour: the office asked for the time to
    # come out of the preamble. get_current_arabic_date_info() still returns
    # time_str for any caller that wants it.
    full_date_str = (date_info.get("full_date_text_no_time")
                     or f"في يوم {date_info['day_words']} من {date_info['hijri_date']} "
                        f"هـ الموافق لـ {date_info['gregorian_date']}")
    # Who is officiating comes from the office profile, not from this file.
    import office_profile
    preamble_head = f"الحمد لله {full_date_str} {office_profile.notary_block()}"
    tax_office = office_profile.tax_office_name()

    p1_count = len(party1_list) if party1_list else 1
    p1_info = party1_list[0] if party1_list else {}
    p2_count = len(party2_list) if party2_list else 1
    p2_info = party2_list[0] if party2_list else {}

    # ── NON-FOUSSOUL DEED TYPES (إشهاد بالحوز، تكليف، إسقاط، توكيل، حجة وفاة، فريضة، وصل خلاص) ──
    if is_ichhad_hawz or is_takleef or is_iskat_daawa or is_tawkeel or is_iskat or is_hojjat_wafat or is_farida or is_wassl_khalass:
        p_desc_clean = re.sub(r"^\s*\*{0,2}الفصل\s*(الأول|الاول)\*{0,2}\s*:\s*", "", property_desc).strip()
        p_desc_clean = p_desc_clean.replace("\n- ", "، ").replace("\n", " ").replace("- ", " ").replace("  ", " ")
        p_desc_clean = re.sub(r"\s+", " ", p_desc_clean).strip()

        price_str = format_money_words_and_numbers(price_words, price_num)

        if is_ichhad_hawz:
            p1_name = p1_info.get("full_name") or p1_info.get("name", "")
            g1 = detect_tunisian_gender(p1_name)
            p1_str = format_single_party_text(p1_info)
            
            p2_str = format_single_party_text(p2_info)
            w2_str = format_single_party_text(witness2_info) if witness2_info else ""
            witnesses_text = f"حضر لدينا أولاً {p2_str}"
            if w2_str:
                witnesses_text += f" وثانياً {w2_str}."
            else:
                witnesses_text += "."
            
            declarant_title = "الطالبة" if g1 == "F" else "الطالب"
            declarant_verb = "أنها مالكة" if g1 == "F" else "أنه مالك"
            owner_status = "بصفة مالكة" if g1 == "F" else "بصفة مالك"

            body = (
                f"{preamble_head} بطلب من {p1_str}. "
                f"{witnesses_text} "
                f"وصرحت {declarant_title} {declarant_verb} للعقار المتمثل في {p_desc_clean} "
                f"{owner_status} منذ سنوات بحكم المعرفة والقرابة والجوار، "
                f"وأشهد المذكوران أعلاه بصحة تصريحات {declarant_title} بحكم المعرفة والقرابة والجوار. "
                f"هذا ما تم تلقيه وتلي فوافقوا وأمضوا ورسم بدفتر مسودات أولهما صحيفة ................ تحت عدد ................ أجره والمصاريف القانونية دنانير والله الموفق."
            )
            return body

        elif is_takleef:
            if len(party1_list) > 1:
                p1_items = []
                for idx, p in enumerate(party1_list):
                    num_w = NUMERAL_WORDS_AR[idx] if idx < len(NUMERAL_WORDS_AR) else f"الطرف {idx+1}"
                    formatted = format_single_party_text(p).replace("السيد: ", "").replace("السيدة: ", "")
                    p1_items.append(f"{num_w}: {formatted}")
                p1_str = " ".join(p1_items)
            else:
                p1_str = format_single_party_text(p1_info)

            p2_name = format_single_party_text(p2_info).replace("السيد: ", "").replace("السيدة: ", "")
            p2_addr = p2_info.get("address") or p2_info.get("addr") or ""
            addr_clause = f" الكائن مكتبه بـ {p2_addr}" if p2_addr and "...." not in p2_addr else ""

            body = (
                f"{preamble_head} حضر لدينا: {p1_str}. "
                f"الذين أشهدوا بتكليف وتوكيل الأستاذ: {p2_name}{addr_clause} "
                f"لتمثيلهم والنيابة عنهم لدى سائر الإدارات ورفع الدعاوى القضائية لاستصدار {p_desc_clean}. "
                f"هذا ما تم تلقيه وتلي فوافقوا وأمضوا ورسم بدفتر مسودات أولهما صحيفة ................ تحت عدد ................ أجره والمصاريف القانونية دنانير والله الموفق."
            )
            return body

        elif is_iskat or is_iskat_daawa:
            p1_str = format_single_party_text(p1_info)
            p2_str = format_single_party_text(p2_info)
            
            witness_part = ""
            if witness1_info:
                w1_str = format_single_party_text(witness1_info)
                witness_part += f" المعرف بـ {w1_str}"
                if witness2_info:
                    w2_str = format_single_party_text(witness2_info)
                    witness_part += f" وثانياً {w2_str}"

            # Clean p_desc_clean to avoid repetitive AI summaries or double prefixes
            p_desc_text = p_desc_clean
            p_desc_text = re.sub(r"^(تنازل\s+وإسقاط\s+حق(\s+في\s+التتبع\s+القضائي)?(\s+في\s+خصوص)?\s*)+", "", p_desc_text).strip()
            p_desc_text = re.sub(r"^(إسقاط\s+دعوى(\s+في\s+خصوص)?\s*)+", "", p_desc_text).strip()
            
            if p_desc_text:
                if p_desc_text.startswith("في خصوص") or p_desc_text.startswith("في شأن"):
                    desc_part = f" {p_desc_text}"
                else:
                    desc_part = f" في خصوص {p_desc_text}"
            else:
                desc_part = ""

            price_clause = f" مقابل تعويض وبدل قدره {price_str}" if price_str else ""

            body = (
                f"{preamble_head} حضر لدينا: {p1_str}.{witness_part} "
                f"وصرح أنه أسقط حقه في التتبع القضائي لـ {p2_str}، "
                f"وهذا تنازل عن كل حقوقه في الغرض{desc_part}{price_clause}. "
                f"هذا ما تم تلقيه وتلي فوافقوا وأمضوا ورسم بدفتر مسودات أولهما صحيفة ................ تحت عدد ................ أجره والمصاريف القانونية دنانير والله الموفق."
            )
            return body

        elif is_wassl_khalass:
            p1_str = format_single_party_text(p1_info)
            p2_str = format_single_party_text(p2_info)
            orig_text = ownership_origin.strip() or property_desc.strip()
            orig_clean = re.sub(r"^\s*\*{0,2}الفصل\s*(الأول|الاول)\*{0,2}\s*:\s*", "", orig_text).strip()
            intro_ref = f" حيث أبرم المذكورين عقد بيع بحجة عادلة {orig_clean} تخلد بذمة المشترين دين جل أجله وبناء عليه:" if orig_clean else ""
            
            price_text = f"مبلغ {price_str} نقداً" if price_str else "المبلغ المستحق نقداً"
            body = (
                f"{preamble_head} حضر لدينا: {p1_str}. "
                f"الطرف الثاني: {p2_str}.{intro_ref} "
                f"قبض الطرف الأول أعلاه {price_text}، "
                f"وأبرأ البائع ذمة المشترين في المبلغ المذكور بقيمة ثمن العقار في العقد المذكور بالمساحة الواردة به وبقي تعديل الثمن المرتبط بالمساحة سارياً بين أطراف العقد لحين صدور شهادة ملكية تثبت المساحة تفصيلاً. "
                f"هذا ما تم تلقيه ومعاينته وأبرم وتلي فوافقا وأمضيا ورسم بدفتر مسودات أولهما صحيفة ................ تحت عدد ................ أجره والمصاريف القانونية دنانير والله الموفق."
            )
            return body

        elif is_hojjat_wafat:
            p1_str = format_single_party_text(p1_info)
            w1_str = format_single_party_text(witness1_info) if witness1_info else (format_single_party_text(p2_info) if p2_info else "")
            w2_str = format_single_party_text(witness2_info) if witness2_info else ""

            death_act_num = contract_vars.get("death_act_num") or contract_vars.get("act_num") or "........"
            municipality = contract_vars.get("municipality") or contract_vars.get("city") or "........"
            death_date = contract_vars.get("death_date") or "........"
            deceased_name = p2_info.get("full_name") or p2_info.get("name") or contract_vars.get("deceased_name") or "........"

            g1 = detect_tunisian_gender(p1_info.get("full_name") or p1_info.get("name", ""))
            declarant_role = "بوصفها مصرحة بالوفاة" if g1 == "F" else "بوصفه مصرحاً بالوفاة"

            witness_block = ""
            if w1_str:
                witness_block = f"كما حضر لدينا الشاهدان: الأول: {w1_str}"
                if w2_str:
                    witness_block += f"، والثاني: {w2_str}"
                witness_block += "."

            body = (
                f"{preamble_head} حضر لدينا: {p1_str} {declarant_role}. "
                f"{witness_block} "
                f"وذكروا أنهم يعرفون المتوفى: {deceased_name} معرفة تامة وشهدوا بأنه توفي بـ {municipality} بتاريخ {death_date} حسبما هو مضمن برسم وفاته عدد {death_act_num} المحرر من ضابط الحالة المدنية ببلدية {municipality}. "
                f"وقد ترك ورثته الشرعيين الآتي ذكرهم: {p_desc_clean} ولا غير. "
                f"هذا ما تم تلقيه وتلي فوافقوا وأمضوا ورسم بدفتر مسودات أولهما صحيفة ................ تحت عدد ................ أجره والمصاريف القانونية دنانير والله الموفق."
            )
            return body

        elif is_farida:
            return build_farida_contract_text(
                contract_type=contract_type,
                applicant_info=p1_info,
                deceased_info=p2_info,
                hojjat_wafat_details=contract_vars.get("hojjat_wafat_ref") or contract_vars.get("hujja_num") or "",
                property_title_details=p_desc_clean,
                total_shares=contract_vars.get("total_shares") or price_num or "",
                shares_breakdown=contract_vars.get("shares_breakdown") or price_words or "",
                wasiya_wajiba_text=contract_vars.get("wasiya_wajiba_text") or "",
                successive_deaths_text=contract_vars.get("successive_deaths_text") or "",
                ownership_origin=ownership_origin
            )

        elif is_tawkeel:
            p1_str = format_single_party_text(p1_info)
            p2_str = format_single_party_text(p2_info)
            body = (
                f"{preamble_head} أقام التوكيل التوثيقي الموكل: {p1_str}. "
                f"لفائدة الوكيل: {p2_str}. "
                f"الذين أشهدوا بتوكيل الوكيل المذكور في القيام بكافة الإجراءات التوثيقية والإدارية والقانونية الخاصة بـ {p_desc_clean}، "
                f"وله حق التوقيع والتمثيل أمام كافة الإدارات والقباضات المالية والمحاكم وحافظ الملكية العقارية. "
                f"وأبرم التوكيل وتلي فوافقا وأمضيا ورسم بدفتر مسودات أولهما صحيفة ................ تحت عدد ................ أجره والمصاريف القانونية دنانير والله الموفق."
            )
            return body
    
    # Party 1 Section
    p1_count = len(party1_list) if party1_list else 1
    p1_info = party1_list[0] if party1_list else {}
    name1 = p1_info.get("full_name") or p1_info.get("name", "")
    g1 = detect_tunisian_gender(name1)

    if p1_count == 1:
        if is_waad: p1_role = "الواعدة بالبيع" if g1 == "F" else "الواعد بالبيع"
        elif is_iltizam_bay3: p1_role = "الملتزمة بالبيع" if g1 == "F" else "الملتزم بالبيع"
        elif is_iskat_daawa: p1_role = "الشاكية المسقطة" if g1 == "F" else "الشاكي المسقط"
        elif is_iskat_tanazol: p1_role = "المسقطة المتنازلة" if g1 == "F" else "المسقط المتنازل"
        elif is_iskat: p1_role = "المسقطة" if g1 == "F" else "المسقط"
        elif is_ichhad_hawz: p1_role = "طالبة الإشهاد بالحوز" if g1 == "F" else "طالب الإشهاد بالحوز"
        elif is_takleef: p1_role = "المكلفة" if g1 == "F" else "المكلف"
        elif is_ittifaq: p1_role = ""
        elif is_wassl_khalass: p1_role = "الدائنة المقرة بالقبض" if g1 == "F" else "الدائن المقر بالقبض"
        elif is_hiba: p1_role = "الواهبة" if g1 == "F" else "الواهب"
        elif is_tanazol: p1_role = "المتنازلة" if g1 == "F" else "المتنازل"
        elif is_moukassma: p1_role = "الطرف الأول المتقاسم"
        elif is_maawada: p1_role = "الطرف الأول المتبادل"
        elif is_keraa: p1_role = "المؤجرة" if g1 == "F" else "المؤجر"
        elif is_rahn: p1_role = "الراهنة" if g1 == "F" else "الراهن"
        elif is_zawadj: p1_role = "الزوج"
        elif is_tawkeel: p1_role = "الموكلة" if g1 == "F" else "الموكل"
        elif is_hojjat_wafat: p1_role = "طالب الإشهاد"
        elif is_wassiya: p1_role = "الموصية" if g1 == "F" else "الموصي"
        elif is_takharouj: p1_role = "المتخارجة" if g1 == "F" else "المتخارج"
        elif is_company: p1_role = "الشريك الأول المؤسس"
        elif is_fonds: p1_role = "البائع للأصل التجاري"
        elif is_ikrar: p1_role = "المدين المقر بالدين"
        else: p1_role = "البائعة" if g1 == "F" else "البائع"

        p1_role_str = f" {p1_role}" if p1_role else ""
        p1_section = f"انعقد بين الطرف الأول{p1_role_str}: {format_single_party_text(p1_info)}"
    else:
        genders = [detect_tunisian_gender(p.get("full_name") or p.get("name", "")) for p in party1_list]
        if is_hiba: p1_role = "الواهبات" if all(g == "F" for g in genders) else "الواهبون"
        elif is_tanazol: p1_role = "المتنازلات" if all(g == "F" for g in genders) else "المتنازلون"
        elif is_moukassma: p1_role = "المتقاسم الأول"
        elif is_zawadj: p1_role = "الزوج"
        elif is_keraa: p1_role = "المؤجرون"
        elif is_rahn: p1_role = "الراهنون"
        elif is_tawkeel: p1_role = "الموكلون"
        elif is_takleef: p1_role = "المكلفون"
        elif is_company: p1_role = "الشركاء المؤسسون"
        else: p1_role = "البائعات" if all(g == "F" for g in genders) else "البائعين"
        p1_items = []
        for idx, p_info in enumerate(party1_list):
            g = genders[idx]
            n_w = NUMERAL_WORDS_AR[idx] if idx < len(NUMERAL_WORDS_AR) else f"الطرف {idx+1}"
            t_prefix = "السيدة:" if g == "F" else "السيد:"
            p1_items.append(f"{n_w} {t_prefix} {format_single_party_text(p_info).replace('السيدة: ', '').replace('السيد: ', '')}")
        p1_section = f"انعقد بين الطرف الأول {p1_role}: " + " ".join(p1_items)
        
    if procuration_text and procuration_text.strip():
        p1_section += f" {procuration_text.strip()}."
        
    # Party 2 Section
    p2_count = len(party2_list) if party2_list else 1
    p2_info = party2_list[0] if party2_list else {}
    name2 = p2_info.get("full_name") or p2_info.get("name", "")
    g2 = detect_tunisian_gender(name2)

    # Title Examination & Intro Preamble Clause
    is_real_estate = any([is_sale, is_hiba, is_moukassma, is_tanazol, is_maawada, is_rahn, is_iltizam_bay3, is_ichhad_hawz, is_iskat_tanazol, "وعد" in contract_type, "إسقاط" in contract_type or "اسقاط" in contract_type])
    title_exam_sentence = ""
    if is_iltizam_bay3:
        p_orig_clean = re.sub(r"^\s*\*{0,2}فصل\s*تمهيدي\*{0,2}\s*:\s*", "", ownership_origin).strip()
        p_orig_clean = p_orig_clean.replace("\n", " ").replace("  ", " ").strip()
        if p_orig_clean and "........" not in p_orig_clean:
            title_exam_sentence = f"فصل تمهيدي: حيث استقر على ملك الطرف الأول بالشراء {p_orig_clean} وعليه اتفقا على:"
        else:
            title_exam_sentence = "فصل تمهيدي: حيث استقر على ملك الطرف الأول بالشراء أرض فلاحية وعليه اتفقا على:"
    elif is_wassl_khalass:
        orig_text = ownership_origin.strip() or property_desc.strip()
        orig_clean = re.sub(r"^\s*\*{0,2}الفصل\s*(الأول|الاول)\*{0,2}\s*:\s*", "", orig_text).strip()
        if orig_clean and "........" not in orig_clean and "قبض" not in orig_clean and "أبرأ" not in orig_clean:
            title_exam_sentence = f"حيث أبرم المذكورين عقد بيع بحجة عادلة {orig_clean} تخلد بذمة المشترين دين جل أجله وبناء عليه:"
        else:
            title_exam_sentence = "حيث أبرم المذكورين عقد بيع بحجة عادلة حررناها بتاريخ سابق مسجلة تخلد بذمة المشترين دين جل أجله وبناء عليه:"
    elif is_real_estate and "بعد الاطلاع على رسم الملكية" not in property_desc:
        p_title = contract_vars.get("property_title") or contract_vars.get("property_name") or ""
        t_foncier = contract_vars.get("titre_foncier") or contract_vars.get("tf_number") or contract_vars.get("title_num") or contract_vars.get("title_number") or ""
        t_gov = contract_vars.get("titre_gov") or contract_vars.get("wilaya") or ""
        p_loc = contract_vars.get("property_location") or contract_vars.get("location") or ""
        p_area = contract_vars.get("property_area") or contract_vars.get("area") or ""

        title_part = f"المسمى {p_title} " if p_title else ""
        num_part = f"موضوع الرسم العقاري عدد {t_foncier} " if t_foncier else "موضوع الرسم العقاري عدد ................ "
        gov_part = f"{t_gov} " if t_gov else ""
        loc_part = f"الكائن بـ{p_loc} " if p_loc else "الكائن بـ................ "
        area_part = f"مساحته {p_area} متر مربع " if p_area else "مساحته ................ متر مربع "

        title_exam_sentence = f"بعد الاطلاع على رسم الملكية للعقار {title_part}{num_part}{gov_part}{loc_part}{area_part}وإشعار الطرفين بحالته القانونية اتفقا على:"

    if p2_count == 1:
        if is_waad: p2_role = "الموعود لها بالبيع" if g2 == "F" else "الموعود له بالبيع"
        elif is_iltizam_bay3: p2_role = "الملتزم لها بالبيع" if g2 == "F" else "الملتزم له بالبيع"
        elif is_iskat_daawa: p2_role = "المستفيدة من الإسقاط" if g2 == "F" else "المستفيد من الإسقاط"
        elif is_iskat_tanazol: p2_role = "المسقط لها المتنازل لها" if g2 == "F" else "المسقط له المتنازل له"
        elif is_iskat: p2_role = "المسقط لها" if g2 == "F" else "المسقط له"
        elif is_ichhad_hawz: p2_role = "الشاهد الأول"
        elif is_takleef: p2_role = "الأستاذ الوكيل"
        elif is_ittifaq: p2_role = ""
        elif is_wassl_khalass: p2_role = "المدينة المبرأة" if g2 == "F" else "المدين المبرأ"
        elif is_hiba: p2_role = "الموهوب لها" if g2 == "F" else "الموهوب له"
        elif is_tanazol: p2_role = "المتنازل لها" if g2 == "F" else "المتنازل له"
        elif is_moukassma: p2_role = "الطرف الثاني المتقاسم"
        elif is_maawada: p2_role = "الطرف الثاني المتبادل"
        elif is_keraa: p2_role = "المستأجرة" if g2 == "F" else "المستأجر"
        elif is_rahn: p2_role = "المرتهنة" if g2 == "F" else "المرتهن"
        elif is_zawadj: p2_role = "الزوجة"
        elif is_tawkeel: p2_role = "الوكيلة" if g2 == "F" else "الوكيل"
        elif is_hojjat_wafat: p2_role = "الموروث الهالك"
        elif is_wassiya: p2_role = "الموصى لها" if g2 == "F" else "الموصى له"
        elif is_takharouj: p2_role = "المتخارج لهم"
        elif is_company: p2_role = "الشريك الثاني المؤسس"
        elif is_fonds: p2_role = "المشتري للأصل التجاري"
        elif is_ikrar: p2_role = "الدائن المقر له بالدين"
        else: p2_role = "المشترية" if g2 == "F" else "المشتري"

        p2_role_str = f" {p2_role}" if p2_role else ""
        agree_tail = "الذين اتفقوا على:" if (p1_count > 1 or p2_count > 1) else "اللذان اتفقا على:"
        if title_exam_sentence:
            p2_section = f"الطرف الثاني{p2_role_str}: {format_single_party_text(p2_info)}. {title_exam_sentence}"
        else:
            p2_section = f"الطرف الثاني{p2_role_str}: {format_single_party_text(p2_info)} {agree_tail}"
    else:
        genders2 = [detect_tunisian_gender(p.get("full_name") or p.get("name", "")) for p in party2_list]
        if is_waad: p2_role = "الموعود لهن بالبيع" if all(g == "F" for g in genders2) else "الموعود لهم بالبيع"
        elif is_iskat: p2_role = "المسقط لهن" if all(g == "F" for g in genders2) else "المسقط لهم"
        elif is_hiba: p2_role = "الموهوب لهن" if all(g == "F" for g in genders2) else "الموهوب لهم"
        elif is_tanazol: p2_role = "المتنازل لهن" if all(g == "F" for g in genders2) else "المتنازل لهم"
        elif is_moukassma: p2_role = "المتقاسم الثاني"
        elif is_zawadj: p2_role = "الزوجة"
        elif is_keraa: p2_role = "المستأجرون"
        elif is_rahn: p2_role = "المرتهنون"
        elif is_tawkeel: p2_role = "الوكلاء"
        elif is_takleef: p2_role = "الأساتذة الوكلاء"
        elif is_company: p2_role = "باقي الشركاء"
        else: p2_role = "المشتريات" if all(g == "F" for g in genders2) else "المشترين"
        p2_items = []
        for idx, p_info in enumerate(party2_list):
            g = genders2[idx]
            n_w = ["أولاً", "ثانياً", "ثالثاً", "رابعاً", "خامساً"][idx] if idx < 5 else f"الطرف {idx+1}"
            t_prefix = "السيدة:" if g == "F" else "السيد:"
            p2_items.append(f"{n_w} {t_prefix} {format_single_party_text(p_info).replace('السيدة: ', '').replace('السيد: ', '')}")

        if title_exam_sentence:
            p2_section = f"الطرف الثاني {p2_role}: " + " ".join(p2_items) + f". {title_exam_sentence}"
        else:
            p2_section = f"الطرف الثاني {p2_role}: " + " ".join(p2_items) + " الذين اتفقوا."

    # Clean price format e.g. خمسة آلاف دينار (5000 د.ت)
    price_str = format_money_words_and_numbers(price_words, price_num)
    price_str = re.sub(r"^\s*\*{0,2}الفصل\s*الثاني\*{0,2}\s*:\s*", "", price_str).strip()

    # Chapter 1
    p_desc_clean = re.sub(r"^\s*\*{0,2}الفصل\s*(الأول|الاول)\*{0,2}\s*:\s*", "", property_desc).strip()
    p_desc_clean = re.sub(r"^جميع\s+", "", p_desc_clean).strip()
    p_desc_clean = p_desc_clean.replace("\n- ", "، ").replace("\n", " ").replace("- ", " ").replace("  ", " ")
    p_desc_clean = re.sub(r"\s+", " ", p_desc_clean).strip()

    # Determine Party 2 acceptance grammar (التي قبلت / الذي قبل / الذين قبلوا)
    if p2_count > 1:
        p2_accept = "الذين قبلوا"
    elif g2 == "F" or any(fem_kw in p2_role for fem_kw in ["الموهوب لها", "المشترية", "المتنازل لها", "المكترية", "الموعود لها", "المسقط لها"]):
        p2_accept = "التي قبلت"
    else:
        p2_accept = "الذي قبل"

    if is_waad:
        ch1 = f"الفصل الأول: وعد والتزم الواعد بالبيع بأن يبيع وينقل ملكية العقار التالي {p_desc_clean} لفائدة الموعود له بالبيع {p2_accept} ذلك."
    elif is_iltizam_bay3:
        ch1 = f"الفصل الأول: التزم الطرف الأول أعلاه تحت سائر الضمانات الفعلية والقانونية للطرف الثاني الذي ارتضى بعد المعاينة ببيع {p_desc_clean}."
    elif is_iskat_daawa:
        ch1 = f"الفصل الأول: أسقط وتنازل الشاكي عن جميع الحقوق المدنية والجزائية والمطالب القضائية المترتبة على الشكوى والنزاع المتعلق بـ {p_desc_clean}."
    elif is_iskat_tanazol:
        ch1 = f"الفصل الأول: أسقط وتنازل الطرف الأول عن كافة حقوقه ومناباته والدعاوى المترتبة على {p_desc_clean} لفائدة الطرف الثاني {p2_accept} ذلك."
    elif is_iskat:
        ch1 = f"الفصل الأول: أسقط الطرف الأول والغي وسحب كافة حقوقه ومناباته والدعاوى الخاصة بـ {p_desc_clean} لفائدة الطرف الثاني {p2_accept} ذلك."
    elif is_ichhad_hawz:
        ch1 = f"الفصل الأول: صرح طالب الإشهاد بأنه مالك وحائز للعقار المتمثل في {p_desc_clean} بصفته مالكاً وحائزاً منذ سنوات بحكم المعرفة والقرابة والجوار."
    elif is_takleef:
        ch1 = f"الفصل الأول: أشهد المكلفون بتكليف وتوكيل الأستاذ المحامي/الوكيل لتمثيلهم والنيابة عنهم لدى سائر الإدارات والمحاكم ورفع الدعاوى القضائية لـ {p_desc_clean}."
    elif is_ittifaq:
        ch1 = f"الفصل الأول: سلم الطرف الأول المبلغ المالي التوثيقي المتفق عليه للطرف الثاني بخصوص {p_desc_clean}."
    elif is_wassl_khalass:
        ch1 = f"الفصل الأول: قبض الطرف الأول أعلاه مبلغ {price_str} نقداً."
    elif is_hiba:
        sale_verb = "وهبوا وسلموا وحوزوا الطرف الأول بالتساوي بينهم تحت سائر الضمانات الفعلية والقانونية" if p1_count > 1 else "وهبت وسلمت وحوزت الطرف الأول، تحت سائر الضمانات الفعلية والقانونية،"
        ch1 = f"الفصل الأول: {sale_verb} للطرف الثاني {p2_accept} جميع {p_desc_clean}."
    elif is_zawadj:
        ch1 = f"الفصل الأول: رغبا في الزواج الشرعي وقبلا ببعضهما وفق أحكام مجلة الأحوال الشخصية التونسية."
    elif is_tawkeel:
        ch1 = f"الفصل الأول: وكل الموكل الوكيل المذكور في القيام بكافة الإجراءات التوثيقية والإدارية والقانونية الخاصة بـ {p_desc_clean}."
    elif is_hojjat_wafat:
        ch1 = f"الفصل الأول: ثبتت وفاة الهالك وانحصار ورثته الشرعيين في {p_desc_clean}."
    elif is_wassiya:
        ch1 = f"الفصل الأول: أوصى الموصي بعد وفاته وخروجاً من الثلث الشرعي بجميع {p_desc_clean}."
    elif is_takharouj:
        ch1 = f"الفصل الأول: تخارج المتخارج واسقط جميع مناباته وحقوقه الإرثية في تركة موروثهم لفائدة باقي الورثة المتخارج لهم في {p_desc_clean}."
    elif is_company:
        ch1 = f"الفصل الأول: اتفق الشركاء على تأسيس شركة ذات مسؤولية محدودة غرضها {p_desc_clean}."
    elif is_fonds:
        ch1 = f"الفصل الأول: باع واحيل للأصل التجاري بجميع عناصره المادية والمعنوية الكائن بـ {p_desc_clean}."
    elif is_ikrar:
        ch1 = f"الفصل الأول: أقر واعترف المدين بذمته الشاغلة بمبلغ الدين المستحق للدائن بسبب {p_desc_clean}."
    elif is_keraa:
        ch1 = f"الفصل الأول: سوغ المؤجر للمستأجر المكان الكائن بـ {p_desc_clean}."
    elif is_rahn:
        ch1 = f"الفصل الأول: رهن وسجل الطرف الأول لفائدة الطرف الثاني ضماناً لوفاء الدين العقار التالي: {p_desc_clean}."
    elif is_maawada:
        ch1 = f"الفصل الأول: عاوض وسلم الطرف الأول للطرف الثاني {p2_accept} جميع {p_desc_clean}."
    elif is_moukassma:
        ch1 = f"الفصل الأول: أخرج وانفرد الطرف الأول بجميع المناب الحاصل له في {p_desc_clean}."
    elif is_tanazol:
        ch1 = f"الفصل الأول: تنازل واسقط الطرف الأول عن جميع حقوقه ومناباته الفعلية والقانونية للطرف الثاني {p2_accept} جميع {p_desc_clean}."
    else:
        sale_verb = "باعوا واحالوا الطرف الأول بالتساوي بينهم تحت سائر الضمانات الفعلية والقانونية" if p1_count > 1 else "باع واحال الطرف الأول تحت سائر الضمانات الفعلية والقانونية"
        ch1 = f"الفصل الأول: {sale_verb} للطرف الثاني {p2_accept} جميع {p_desc_clean}."

    # Chapter 2 uses price_str computed above as خمسة آلاف دينار (5000 د.ت)

    if is_zawadj:
        ch2 = f"الفصل الثاني: الصداق المسمى بينهما قدره {price_str} قبضته الزوجة بذراعها."
    elif is_iltizam_bay3:
        ch2 = f"الفصل الثاني: تم الاتفاق نظير ثمن جملي قدره {price_str} قبضها البائع نقداً."
    elif is_iskat_daawa:
        ch2 = f"الفصل الثاني: يعتبر هذا الإسقاط إسقاطاً لحق التتبع القضائي بعد التوصل بالتعويض والإنفاق التام."
    elif is_ichhad_hawz:
        ch2 = f"الفصل الثاني: أشهد الشاهدان المذكوران بصحة تصريحات الطالب بحكم المعرفة والقرابة والجوار."
    elif is_takleef:
        ch2 = f"الفصل الثاني: للوكيل حق التوقيع والتمثيل أمام كافة الإدارات والقباضات المالية والمحاكم وحافظ الملكية العقارية."
    elif is_ittifaq:
        ch2 = f"الفصل الثاني: تم الاتفاق على المساهمة والالتزام قدره {price_str}."
    elif is_wassl_khalass:
        ch2 = f"الفصل الثاني: أبرأ البائع ذمة المشترين في المبلغ المذكور وقدره {price_str} بقيمة ثمن العقار."
    elif is_hiba:
        ch2 = f"الفصل الثاني: تم تقدير قيمة العقار الموهوب بـ {price_str}."
    elif is_tawkeel:
        ch2 = f"الفصل الثاني: للوكيل حق التوقيع والتمثيل أمام كافة الإدارات والقباضات المالية والمحاكم وحافظ الملكية العقارية."
    elif is_hojjat_wafat:
        ch2 = f"الفصل الثاني: المتروك ومنابات الورثة التقديرية بـ {price_str}."
    elif is_wassiya:
        ch2 = f"الفصل الثاني: قيمة الموصى به تقديرياً بـ {price_str}."
    elif is_takharouj:
        ch2 = f"الفصل الثاني: تم هذا التخارج مقابل بدل تخارج قدره {price_str}."
    elif is_company:
        ch2 = f"الفصل الثاني: رأس مال الشركة المحدد قدره بـ {price_str} مقسم إلى حصص متساوية بين الشركاء."
    elif is_fonds:
        ch2 = f"الفصل الثاني: تم البيع نظير ثمن جملي قدره {price_str}."
    elif is_ikrar:
        ch2 = f"الفصل الثاني: مبلغ الدين المحرر قدره {price_str} يتعهد المدين بوفائه في التاريخ المحدد."
    elif is_keraa:
        ch2 = f"الفصل الثاني: قدر الكراء الشهري بـ {price_str} يدفع بداية كل شهر."
    elif is_rahn:
        ch2 = f"الفصل الثاني: مبلغ الدين المضمون بالرهن قدره {price_str}."
    elif is_maawada:
        ch2 = f"الفصل الثاني: عاوض وسلم الطرف الثاني للطرف الأول العقار المقابل بقيمة {price_str}."
    elif is_moukassma:
        ch2 = f"الفصل الثاني: أخرج وانفرد الطرف الثاني بجميع منابه في قسمة المشترك المذكور تحت سائر الضمانات القانونية."
    elif is_tanazol:
        ch2 = f"الفصل الثاني: تم هذا التنازل {price_str}."
    else:
        receipt_verb = ("قبضها البائعات بالتساوي بينهن." if p1_role == "البائعات" else "قبضها البائعون بالتساوي بينهم.") if p1_count > 1 else "قبضها البائع بذكره."
        ch2 = f"الفصل الثاني: تم البيع نظير مبلغ جملي قدره {price_str} {receipt_verb}"
    
    # Chapter 3 (ONLY INCLUDED IF OWNERSHIP ORIGIN IS NOT EMPTY!)
    ch3 = ""
    p_origin_clean = re.sub(r"^\s*\*{0,2}الفصل\s*الثالث\*{0,2}\s*:\s*", "", ownership_origin).strip()
    p_origin_clean = p_origin_clean.replace("\n", " ").replace("  ", " ").strip()
    p_origin_clean = re.sub(r"\s+", " ", p_origin_clean)
    if is_iltizam_bay3:
        ch3 = "الفصل الثالث: يتم إبرام عقد بيع وجوباً بعد استصدار عقد بيع شراء الطرف الأول أعلاه."
    elif is_wassl_khalass:
        ch3 = ""
    elif p_origin_clean and "........" not in p_origin_clean and len(p_origin_clean) > 3:
        ch3 = f"الفصل الثالث: انجرار الملكية {p_origin_clean}."

    # Extra Spoken Chapters (الفصل الرابع، الفصل الخامس...)
    # Entries originate from an AI response, so the shape is not guaranteed. A
    # malformed entry is skipped rather than allowed to raise while building a deed.
    extra_ch_text = ""
    if extra_foussoul:
        extra_parts = []
        for idx, item in enumerate(extra_foussoul):
            if isinstance(item, dict):
                num = item.get("number") or (idx + 1)
                title = item.get("title") or f"الفصل {num}"
                cnt = str(item.get("content") or "").strip()
            elif isinstance(item, str):
                title = f"الفصل {idx + 1}"
                cnt = item.strip()
            else:
                continue
            if cnt:
                title_clean = re.sub(r"^\s*\*{0,2}|\*{0,2}\s*$", "", str(title)).strip()
                extra_parts.append(f"{title_clean}: {cnt}")
        if extra_parts:
            extra_ch_text = " ".join(extra_parts)
    
    # Closing Paragraph
    if witness1_info and witness1_info.get("name"):
        w1_name = witness1_info.get("name", "........................")
        w1_cin = witness1_info.get("cin", "........................")
        w2_name = (witness2_info or {}).get("name", "........................")
        w2_cin = (witness2_info or {}).get("cin", "........................")
        witness_clause = f" بحضور الشاهدين المكلفين بالإشهاد: الأول السيد: {w1_name} (ب ت و: {w1_cin}) والثاني السيد: {w2_name} (ب ت و: {w2_cin})"
    elif contract_type and ("زواج" in str(contract_type) or "وفاة" in str(contract_type)):
        witness_clause = " بحضور الشاهدين المكلفين بالإشهاد"
    else:
        witness_clause = ""

    if is_wassl_khalass or is_iltizam_bay3:
        closing = "هذا ما تم تلقيه ومعاينته وأبرم وتلي فوافقا وأمضيا ورسم بدفتر مسودات أولهما صحيفة ................ تحت عدد ................ أجره والمصاريف القانونية دنانير والله الموفق."
    else:
        closing = f"وأبرم العقد بين طرفيه وتلي فوافقا وأمضيا{witness_clause} واقتطعت فيه بطاقة نقل عدد ................ خالص معلوم نقلها بالقباضة المالية بـ{tax_office} بتاريخ ................ وصل عدد ................م. ورسم بدفتر مسودات أولهما صحيفة ................ عدد ................ أجره والمصاريف القانونية دنانير والله الموفق."

    # Join active sections into 1 SINGLE CONTINUOUS PARAGRAPH
    custom_body = ""
    if "الفصل الأول" in property_desc or "الفصل الاول" in property_desc:
        custom_body = property_desc.strip()
    elif extra_ch_text and ("الفصل الأول" in extra_ch_text or "الفصل الاول" in extra_ch_text):
        custom_body = extra_ch_text.strip()

    if custom_body:
        # Custom dictated or extracted chapters provided (e.g. الفصل الأول through الفصل الخامس).
        # Use custom_body directly so no rigid structure or duplicate default chapters are forced!
        custom_body = re.sub(r"وأبرم العقد بين طرفيه.*", "", custom_body).strip()
        custom_body = re.sub(r"واقتطعت فيه بطاقة نقل.*", "", custom_body).strip()
        custom_body = re.sub(r"ورسم بدفتر مسودات.*", "", custom_body).strip()
        parts = [preamble_head, p1_section, p2_section, custom_body]
    else:
        parts = [preamble_head, p1_section, p2_section, ch1, ch2]
        if ch3:
            parts.append(ch3)
        if extra_ch_text:
            extra_ch_text = re.sub(r"وأبرم العقد بين طرفيه.*", "", extra_ch_text).strip()
            extra_ch_text = re.sub(r"واقتطعت فيه بطاقة نقل.*", "", extra_ch_text).strip()
            extra_ch_text = re.sub(r"ورسم بدفتر مسودات.*", "", extra_ch_text).strip()
            if extra_ch_text:
                parts.append(extra_ch_text)
    
    # ALWAYS append the clean, standardized blank dots template closing paragraph!
    parts.append(closing)

    full_p = " ".join(parts)
    full_p = _clean_text_entity(full_p)
    full_p = re.sub(r"\s+", " ", full_p).strip()
    return full_p


TUNISIAN_LOCATION_FIXES = {
    r"جبنـي(انة)?": "جبنيانة",
    r"طريق\s*جبنـي": "طريق جبنيانة",
    r"سيدي\s*بوزيد": "سيدي بوزيد",
    r"المنصورية": "المنصورية",
    r"فوشانة": "فوشانة",
    r"المحمدية": "المحمدية",
    r"بن\s*عروس": "بن عروس",
    r"الدهماني": "الدهماني",
    r"منوبة": "منوبة",
    r"أريانة": "أريانة",
    r"الكاف": "الكاف",
}

ARABIC_NAME_NORM_RULES = [
    (r"\bيصف\b", "يوسف"),
    (r"\bيوسف\b", "يوسف"),
    (r"\bعبدالرحمان\b", "عبد الرحمن"),
    (r"\bعبدالحميد\b", "عبد الحميد"),
    (r"\bعبدالقادر\b", "عبد القادر"),
    (r"\bعبدالمجيد\b", "عبد المجيد"),
    (r"\bعبدالله\b", "عبد الله"),
    (r"\bعبدالعزيز\b", "عبد العزيز"),
    (r"\bعبدالرزاق\b", "عبد الرزاق"),
    (r"\bعبدالستار\b", "عبد الستار"),
    (r"\bعبدالكريم\b", "عبد الكريم"),
    (r"\bعبدالسلام\b", "عبد السلام"),
    (r"\bابراهيم\b", "إبراهيم"),
    (r"\bاسماعيل\b", "إسماعيل"),
    # Fix surname "أمين الحاج" -> "ابن الحاج"
    (r"\bأمين\s*الحاج\b", "ابن الحاج"),
    (r"\bامين\s*الحاج\b", "ابن الحاج"),
    # Fix "حرم" being appended to female names:
    (r"\s*حرم\s+[^\n,،\.]+", ""),
    # Fix "1999/01/01" dummy dates:
    (r"1999/01/01", ""),
    # Spoken audio phonetic normalizations:
    (r"\bانجر\s*الملك\b", "انجرار الملكية"),
    (r"\bانجر\s*الملكية\b", "انجرار الملكية"),
    (r"\binjirar\s*almilkiya\b", "انجرار الملكية"),
    (r"\b(و?بعد)\s*الاطلاع\s*على\s*رسم\s*الملكية\s*للعقار\b", r"\1 الاطلاع على رسم الملكية للعقارية"),
    (r"\b(أعفى|اعفى|يعفى)\s*(الطرفان|الطرفين)\s*(السيد\s*حافظ\s*الملكية\s*العقارية\s*)+", "يعفى الطرفان السيد حافظ الملكية العقارية "),
    (r"\b(السيد\s*حافظ\s*الملكية\s*العقارية\s*){2,}", "السيد حافظ الملكية العقارية "),
    (r"\bيعفوا\s*الطرفين\b", "يعفيان"),
    (r"\bيعفوا\s*الطرفان\b", "يعفيان"),
    (r"\bبعفوا\b", "يعفيان"),
    (r"\bيعفوا\b", "يعفيان"),
    (r"\bحافظ\s*ميك\s*العقاري\b", "حافظ الملكية العقارية"),
    (r"\bميك\s*العقاري\b", "الملكية العقارية"),
    (r"\bحافظ\s*ميك\b", "حافظ الملكية العقارية"),
    # Speech-to-Text Garbled Audio Contextual Repairs:
    (r"\bمن\s*جراء\s*(ملكية|المدنية|الملكية|الملك)\b", "انجرار الملكية"),
    (r"\b(وحيازتها|بحضر\s*حرارتها|بحجة\s*حرارتها|بحجة\s*حريتها)\s*في\b", "بحجة حررناها في"),
    (r"\bمسجل\s*(ببفوه\s*شرفيه|ببفوجه|بفوشانة)\b", "مسجل بقباضة فوشانة في"),
    (r"\b(وسعدني|وسعة\s*كذا\s*كذا|وسعة\s*عدد)\b", "وصل عدد"),
    (r"\bمودع\s*مجلد\b", "مودع بمجلد"),
    (r"\b(وافق|أعفى|اعفى|يعفوا)\s*(الطرفان|الطرفين)\s*السيد\s*(حقل|حق|حافظ)\s*(الملكية|المك)\s*(العقارية)?\b", "يعفى الطرفان السيد حافظ الملكية العقارية"),
    (r"\b(واعتباره\s*فصل|وتعتبر\s*الفصول|تعتبر\s*الفصول)\b", "من اعتبار الوصف"),
    (r"\bفي\s*حدود\s*ما\s*ذكرت\b", "في حدود ما ذكر"),
    (r"\bو?تعهدا\s*بتسليم\s*الهبة\b", "ويطلبان ترسيم الهبة"),
    (r"\bتسليم\s*الهبة\b", "ترسيم الهبة"),
    (r"\bوأمضايا\b", "وأمضيا"),
    (r"\bويطلباني\b", "ويطلبان"),
    (r"\bيطلباني\b", "ويطلبان"),
    (r"\bتولي\s*فوا\s*فقا\b", "وتلي فوافقا"),
    (r"\bتولي\s*فوافقا\b", "وتلي فوافقا"),
    # Audio Speech Typos & Legal Grammar Corrections:
    (r"\bو?التنقيص\b", "والتشخيص"),
    (r"\bالتنقيص\b", "والتشخيص"),
    (r"\bوهبت\s*وسلمت\s*وحولت\b", "وهبت وسلمت وحوزت"),
    (r"\bوهبوا\s*وسلموا\s*وحولوا\b", "وهبوا وسلموا وحوزوا"),
    (r"\bباع\s*واحال\s*وحول\b", "باع واحال وحوز"),
    (r"\bوحولت\b", "وحوزت"),
    # Non-breaking space for dates so numbers never detach to the next line (e.g. 16 أوت 2002 -> 16\u00a0أوت\u00a02002):
    (r"(\b\d{1,2})\s+(أوت|يناير|فبراير|مارس|أبريل|مايو|يونيو|يوليو|سبتمبر|أكتوبر|نوفمبر|ديسمبر)\s+(\d{4})\b", "\\1\u00a0\\2\u00a0\\3"),
]


def clean_and_verify_tunisian_entities(data):
    """
    Cleans, verifies, and normalizes Tunisian geographical locations and Arabic proper nouns.
    Purges any occurrences of 'غير مذكور' or '[غير واضح]'.
    Works on either a dictionary of variables or a text string.
    """
    if isinstance(data, dict):
        cleaned = {}
        for k, v in data.items():
            if isinstance(v, str):
                cleaned[k] = _clean_text_entity(v)
            else:
                cleaned[k] = v
        return cleaned
    elif isinstance(data, str):
        return _clean_text_entity(data)
    return data


def _clean_text_entity(text: str) -> str:
    if not text:
        return text
    
    res = text
    # Clean location typos
    for pat, rep in TUNISIAN_LOCATION_FIXES.items():
        res = re.sub(pat, rep, res)
        
    # Clean proper nouns
    for pat, rep in ARABIC_NAME_NORM_RULES:
        res = re.sub(pat, rep, res)

    # Apply comprehensive dynamic Gender Grammar Engine for Party 1 & Party 2
    res = _apply_gender_grammar_corrections(res)

    # Strip unnecessary parentheses around dates (preserve parentheses around price numbers)
    res = re.sub(r"\((\d{1,2}/\d{1,2}/\d{2,4})\)", r"\1", res)

    # Strip verbose spelled-out words before stamp numbers, receipt numbers, and years only
    res = re.sub(r"[\u064b-\u0652]", "", res)  # strip diacritics / tanween for clean matching
    res = re.sub(r"\b(في|بتاريخ)\s+[أ-ي\s]{4,60}?\b(\d{1,2}/\d{1,2}/\d{2,4})\b", r"\1 \2", res)
    res = re.sub(r"\b(وصل\s+عدد|عدد|مجلد|سنة)\s+[أ-ي\s]{2,30}?\b(\d+)\b", r"\1 \2", res)

    # Clean all variations of "غير مذكور" and "غير واضح" completely
    res = re.sub(r"غير مذكور بالكلمات", "", res)
    res = re.sub(r"غير مذكور", "", res)
    res = re.sub(r"غير محدد", "", res)
    res = re.sub(r"\[غير واضح\]", "", res)
    res = re.sub(r"\(غير واضح\)", "", res)
    res = re.sub(r"غير واضح", "", res)
    # Strip stray stamp numbers attached to dates (e.g. '2024/12/25 20205' -> '2024/12/25')
    res = re.sub(r"(\d{4}/\d{1,2}/\d{1,2})\s+\d{4,6}\b", r"\1", res)
    res = re.sub(r"\s+", " ", res).strip()
    return res


def _apply_gender_grammar_corrections(text: str) -> str:
    if not text:
        return text
    
    res = text

    # Strip space before punctuation marks (e.g. "16/08/2002 ،" -> "16/08/2002،")
    res = re.sub(r"\s+([،,.:؛!؟])", r"\1", res)

    # Standard Notarial Terminology Correction
    res = re.sub(r"\bرسم\s*الملكية\s*للعقارية\b", "رسم الملكية للعقار", res)
    res = re.sub(r"\bللعقارية\b", "للعقار", res)
    res = re.sub(r"\bتحت\s*[أا]تم\s*الضمانات\b", "تحت سائر الضمانات", res)

    # Ensure square meters are written out in full as متر مربع as requested
    res = re.sub(r"\bم\.م\b", "متر مربع", res)

    # Detect Party 1 gender from Preamble header
    p1_male_header = bool(re.search(r"الطرف\s*الأول\s*(?:البائع|الواهب|المتنازل|المؤجر|المقاسم|السيد)\b", res))
    p1_female_header = bool(re.search(r"الطرف\s*الأول\s*(?:البائعة|الواهبة|المتنازلة|المؤجرة|المقاسمة|السيدة)", res)) and not p1_male_header

    # Detect Party 2 gender from Preamble header
    p2_female_header = bool(re.search(r"الطرف\s*الثاني\s*(?:المشترية|الموهوب\s*لها|المتنازل\s*لها|المكترية|السيدة|بنت)", res))
    p2_male_header = bool(re.search(r"الطرف\s*الثاني\s*(?:المشتري|الموهوب\s*له|المتنازل\s*له|المكترى|السيد)", res)) and not p2_female_header

    # Correct Party 1 if Male
    if p1_male_header:
        res = re.sub(r"\bوهبت\s*وسلمت\s*وحوزت\s*الطرف\s*الأول\s*الواهبة\b", "وهب وسلم وحوز الطرف الأول الواهب", res)
        res = re.sub(r"\bوهبت\s*وسلمت\s*وحوزت\s*الطرف\s*الأول\b", "وهب وسلم وحوز الطرف الأول", res)
        res = re.sub(r"\bباعت\s*واحالت\s*الطرف\s*الأول\s*البائعة\b", "باع واحال الطرف الأول البائع", res)
        res = re.sub(r"\bالطرف\s*الأول\s*الواهبة\b", "الطرف الأول الواهب", res)
        res = re.sub(r"\bالطرف\s*الأول\s*البائعة\b", "الطرف الأول البائع", res)
        res = re.sub(r"\bجميع\s*مناباتها\b", "جميع مناباته", res)
        res = re.sub(r"\bتحت\s*سائر\s*ضماناتها\b", "تحت سائر ضماناته", res)

    # Correct Party 1 if Female
    if p1_female_header:
        res = re.sub(r"\bباع\s*واحال\s*الطرف\s*الأول\b", "باعت واحالت الطرف الأول", res)
        res = re.sub(r"\bوهب\s*وسلم\s*وحوز\s*الطرف\s*الأول\b", "وهبت وسلمت وحوزت الطرف الأول", res)
        res = re.sub(r"\bعاوض\s*وسلم\s*الطرف\s*الأول\b", "عاوضت وسلمت الطرف الأول", res)
        res = re.sub(r"\bتنازل\s*واسقط\s*الطرف\s*الأول\b", "تنازلت واسقطت الطرف الأول", res)

    # Correct Party 2 if Female
    if p2_female_header:
        res = re.sub(r"\b(ل?لطرف\s*الثاني)\s*الموهوب\s*له\s*الذي\s*قبل\b", r"\1 الموهوب لها التي قبلت", res)
        res = re.sub(r"\b(ل?لطرف\s*الثاني)\s*الذي\s*قبل\b", r"\1 التي قبلت", res)
        res = re.sub(r"\b(ل?لطرف\s*الثاني)\s*المشتري\s*الذي\s*اشترى\b", r"\1 المشترية التي اشترت", res)
        res = re.sub(r"\b(ل?لطرف\s*الثاني)\s*الذي\s*اشترى\b", r"\1 التي اشترت", res)
        res = re.sub(r"\b(ل?لطرف\s*الثاني)\s*الذي\s*تسلم\b", r"\1 التي تسلمت", res)

    # Correct Party 2 if Male
    if p2_male_header:
        res = re.sub(r"\b(ل?لطرف\s*الثاني)\s*الموهوب\s*لها\s*التي\s*قبلت\b", r"\1 الموهوب له الذي قبل", res)
        res = re.sub(r"\b(ل?لطرف\s*الثاني)\s*المشترية\s*التي\s*اشترت\b", r"\1 المشتري الذي اشترى", res)

    return res


def format_arabic_price(amount) -> str:
    """
    Formats a numeric price into formal Arabic words + parenthesized number.
    e.g. 5000 -> 'خمسة آلاف دينار (5000)'
    """
    if amount is None or amount == "":
        return ""
    try:
        val = float(str(amount).replace(",", ".").replace("دينار", "").strip())
    except (ValueError, TypeError):
        return str(amount)

    units = {
        0: "صفر", 1: "واحد", 2: "اثنان", 3: "ثلاثة", 4: "أربعة",
        5: "خمسة", 6: "ستة", 7: "سبعة", 8: "ثمانية", 9: "تسعة",
        10: "عشرة", 11: "أحد عشر", 12: "اثنا عشر", 13: "ثلاثة عشر",
        14: "أربعة عشر", 15: "خمسة عشر", 16: "ستة عشر", 17: "سبعة عشر",
        18: "ثمانية عشر", 19: "تسعة عشر"
    }
    tens = {2: "عشرون", 3: "ثلاثون", 4: "أربعون", 5: "خمسون", 6: "ستون", 7: "سبعون", 8: "ثمانون", 9: "تسعون"}
    hundreds = {1: "مائة", 2: "مائتان", 3: "ثلاثمائة", 4: "أربعمائة", 5: "خمسمائة", 6: "ستمائة", 7: "سبعمائة", 8: "ثمانمائة", 9: "تسعمائة"}

    int_val = int(val)
    frac_val = int(round((val - int_val) * 1000))

    def _num_to_words(n: int) -> str:
        if n in units:
            return units[n]
        if n < 100:
            u, t = n % 10, n // 10
            return f"{units[u]} و{tens[t]}" if u else tens[t]
        if n < 1000:
            h, rem = n // 100, n % 100
            h_str = hundreds[h]
            return f"{h_str} و{_num_to_words(rem)}" if rem else h_str
        if n < 1000000:
            k, rem = n // 1000, n % 1000
            if k == 1:
                k_str = "ألف"
            elif k == 2:
                k_str = "ألفان"
            elif 3 <= k <= 10:
                k_str = f"{units[k]} آلاف"
            else:
                k_str = f"{_num_to_words(k)} ألف"
            return f"{k_str} و{_num_to_words(rem)}" if rem else k_str
        if n < 1000000000:
            m, rem = n // 1000000, n % 1000000
            if m == 1:
                m_str = "مليون"
            elif m == 2:
                m_str = "مليونان"
            elif 3 <= m <= 10:
                m_str = f"{units[m]} ملايين"
            else:
                m_str = f"{_num_to_words(m)} مليون"
            return f"{m_str} و{_num_to_words(rem)}" if rem else m_str
        return str(n)

    words = _num_to_words(int_val) + " دينار"
    if frac_val > 0:
        words += f" و{_num_to_words(frac_val)} مليم"

    num_fmt = f"{val:g}"
    return f"{words} ({num_fmt})"


def format_surface_area(area_m2) -> str:
    """
    Formats a numeric surface area in square meters.
    e.g. 250 -> '250 متر مربع'
    """
    if not area_m2:
        return ""
    return f"{area_m2} متر مربع"


def build_farida_contract_text(
    contract_type: str,
    applicant_info: dict,
    deceased_info: dict,
    hojjat_wafat_details: str = "",
    property_title_details: str = "",
    total_shares: str = "",
    shares_breakdown: str = "",
    wasiya_wajiba_text: str = "",
    successive_deaths_text: str = "",
    ownership_origin: str = ""
) -> str:
    """
    Assembles an authentic Tunisian Notary Farida Act (فريضة شرعية / فريضة جزئية)
    without chapters (الفصول) as a continuous legal narrative text, matching official notary deeds.
    """
    date_info = get_current_arabic_date_info()
    import office_profile
    full_date_str = (date_info.get("full_date_text_no_time")
                     or f"في يوم {date_info['day_words']} من {date_info['hijri_date']} "
                        f"هـ الموافق لـ {date_info['gregorian_date']}")
    
    farida_type_title = "فريضة جزئية" if "جزئية" in contract_type else "فريضة شرعية"
    preamble = f"{farida_type_title}\n\nالحمد لله وحده {full_date_str} {office_profile.notary_block()}"
    
    p1_formatted = format_single_party_text(applicant_info or {})
    
    d_name = deceased_info.get("full_name") or deceased_info.get("name") or "........................"
    
    prop_str = property_title_details.strip() if property_title_details else "........................"
    hojjat_str = hojjat_wafat_details.strip() if hojjat_wafat_details else ""
    
    header_block = f"{preamble} وبطلب من {p1_formatted} قصد القيام بـ{farida_type_title} للمتوفى {d_name} موضوع {prop_str}."
    
    paragraphs = [header_block]
    
    if hojjat_str:
        paragraphs.append(f"وحيث توفي الموروث المذكور واحيط بإرثه وتحددت ورثته حسب حجة وفاته {hojjat_str}.")
    elif ownership_origin and ownership_origin.strip():
        paragraphs.append(f"وحيث توفي الموروث المذكور واحيط بإرثه {ownership_origin.strip()}.")
    else:
        paragraphs.append("وحيث توفي الموروث المذكور واحيط بإرثه وتحددت منابات ورثته الشرعيين.")
        
    if successive_deaths_text and successive_deaths_text.strip():
        paragraphs.append(f"{successive_deaths_text.strip()}")
        
    if total_shares and total_shares.strip():
        paragraphs.append(f"عن عدد أسهم إجمالي قدره {total_shares.strip()} سهماً.")
        
    if wasiya_wajiba_text and wasiya_wajiba_text.strip():
        paragraphs.append(f"وتم إخراج الوصية الواجبة لفائدة الأحفاد المستحقين: {wasiya_wajiba_text.strip()}")
        
    if shares_breakdown and shares_breakdown.strip():
        clean_breakdown = re.sub(r"^\s*\*{0,2}الفصل\s*(الأول|الاول|الثاني|الثالث)\*{0,2}\s*:\s*", "", shares_breakdown.strip())
        paragraphs.append(f"وتحددت وانحصرت منابات الورثة الشرعيين وتأصيل الفريضة كما يلي: {clean_breakdown}")
        
    closing = "هذا ما تم تلقيه وتلي فوافقوا وأمضوا ورسم بدفتر مسودات أولهما صحيفة ................ تحت عدد ................ أجره والمصاريف القانونية دنانير والله الموفق."
    paragraphs.append(closing)
    
    full_text = "\n\n".join(paragraphs)
    return _clean_text_entity(full_text)

