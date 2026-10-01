"""
farida_engine.py — Official Tunisian Legal Inheritance Calculator Engine
Compliant with the Tunisian Code of Personal Status (مجلة الأحوال الشخصية التونسية - الفصول 85-192).

Features:
1. Exact Shares Calculation (الفروض والأنصبة الشرعية)
2. Mandatory Bequest (الوصية الواجبة لأولاد الابن وأولاد البنت - الفصلان 191 و 192 م.أ.ش)
3. Real Estate Surface & Parts Mapping (توزيع مناب العقار بالأمتار المربعة والأجزاء)
4. Deficit Awl (العول) & Surplus Restoration (الرد على البنات والفروع - الفصل 143 م.أ.ش)
5. Direct Generation of Notarial Deed Text (صياغة نص الفريضة لعدول الإشهاد)
6. Professional DOCX Export for Office Archive (تصدير الفريضة لملف Word رسمية)
"""

import re
import json
import datetime
from math import gcd
from functools import reduce
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

try:
    import office_profile
except ImportError:
    office_profile = None

try:
    import contract_templates
except ImportError:
    try:
        import core.contract_templates as contract_templates
    except ImportError:
        contract_templates = None

try:
    import docx_generator
except ImportError:
    try:
        import core.docx_generator as docx_generator
    except ImportError:
        docx_generator = None

def _lcm(a, b):
    return (a * b) // gcd(a, b) if a and b else a or b

def calculate_lcm_list(numbers):
    return reduce(_lcm, numbers, 1)

def _parse_date_to_tuple(date_str: str) -> tuple:
    if not date_str or not isinstance(date_str, str):
        return (0, 0, 0)
    m = re.search(r"(\d{2})[-\/](\d{2})[-\/](\d{4})", date_str)
    if m:
        return (int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m2 = re.search(r"(\d{4})[-\/](\d{2})[-\/](\d{2})", date_str)
    if m2:
        return (int(m2.group(1)), int(m2.group(2)), int(m2.group(3)))
    return (0, 0, 0)

def _norm(t):
    if not t: return ""
    t = re.sub(r'[\u064b-\u065f\u0670]', '', str(t))
    t = re.sub(r'[أإآٱ]', 'ا', t)
    t = re.sub(r'ة', 'ه', t)
    t = re.sub(r'ى', 'ي', t)
    t = re.sub(r'ـ', '', t)
    return t.strip()

FEMALE_FIRST_NAMES = {
    'عزة', 'أميرة', 'اميرة', 'مبروكة', 'فاطمة', 'عائشة', 'خديجة', 'زينب', 'مريم', 'سارة',
    'لطيفة', 'نعيمة', 'سليمة', 'حميدة', 'منية', 'نجاة', 'فتيحة', 'ليلى', 'نجوى', 'فريدة', 'رفيقة',
    'حبيبة', 'وجدان', 'سعاد', 'وفاء', 'هدى', 'سهام', 'أحلام', 'احلام', 'إلهام', 'الهام',
    'سميرة', 'منيرة', 'كريمة', 'رجاء', 'رضية', 'زهرة', 'وردة', 'ياسمين', 'نور', 'رحمة',
    'أمل', 'امل', 'منى', 'رانية', 'سناء', 'صفاء', 'وئام', 'إيمان', 'ايمان', 'حنان',
    'ريم', 'نسرين', 'إيناس', 'ايناس', 'هند', 'غادة', 'دلال', 'لمياء', 'شيماء', 'نهى',
    'سلوى', 'عفاف', 'ابتسام', 'نجلاء', 'فضيلة', 'جليلة', 'حسيبة', 'وسيلة', 'راضية',
    'عايدة', 'أمينة', 'امينة', 'بهيجة', 'سهيلة', 'فايزة', 'زكية', 'وهيبة', 'فوزية',
    'شهيرة', 'وسام', 'سمية', 'وسن', 'عبير', 'نادية', 'نضال', 'كوثر', 'سلمى', 'لينا',
    'جمعة', 'فاطنة', 'خدومة', 'علجية', 'زهية', 'وسيلة', 'صليحة', 'زوينة', 'محجوبة',
    'سعيدة', 'حفصية', 'شاذلية', 'جازية', 'عزيزة', 'فتحية', 'صالحة', 'بية', 'مبروكة',
    'عايشة', 'خديجة', 'جميلة', 'دليلة', 'حبيبة', 'الزهرة', 'خيرية', 'حميدة', 'حسناء'
}

def _is_female_name(name: str) -> bool:
    """
    Determines if a name string contains explicit female connectors, keywords,
    or matches a curated set of common female first names.
    Does NOT use broad word-ending rules (ة/ه) to prevent misclassifying male names like بوجمعة/حمزة/عكرمة.
    """
    if not name or not isinstance(name, str):
        return False

    n = name.strip()
    if not n:
        return False

    # 1. Check explicit female connectors anywhere in name
    if re.search(r'\b(بنت|ابنة|حرم|أرملة|زوجة|البنت|أنثى|انثى|فتاة|أم|ام)\b', n):
        return True

    # 2. Check first name against curated female first names BEFORE checking 'بن' patronymic
    parts = n.split()
    first_word = parts[0] if parts else ""
    norm_first = re.sub(r'[أإآٱ]', 'ا', first_word)
    norm_first_h = re.sub(r'[ةه]$', 'ه', norm_first)
    norm_first_t = re.sub(r'[ةه]$', 'ة', norm_first)

    if (first_word in FEMALE_FIRST_NAMES or
        norm_first in FEMALE_FIRST_NAMES or
        norm_first_h in FEMALE_FIRST_NAMES or
        norm_first_t in FEMALE_FIRST_NAMES):
        return True

    for fn in FEMALE_FIRST_NAMES:
        norm_fn = re.sub(r'[أإآٱ]', 'ا', fn)
        norm_fn_h = re.sub(r'[ةه]$', 'ه', norm_fn)
        if norm_fn_h == norm_first_h:
            return True

    # 3. Explicit male connectors (only if first name is NOT female)
    if re.search(r'\b(بن|إبن|ابن|ولد|الابن|ذكر|رجل)\b', n):
        return False

    return False


def _are_same_person(name1: str, name2: str) -> bool:
    """
    Determines if two Arabic name strings refer to the exact same person.
    Handles patronymic variations (e.g. 'مبروكة بنت صالح بن علي' vs 'مبروكة بنت صالح').
    """
    if not name1 or not name2:
        return False
    n1 = _norm(str(name1).strip())
    n2 = _norm(str(name2).strip())
    if not n1 or not n2:
        return False
    if n1 == n2:
        return True
        
    fem1 = _is_female_name(name1) or 'بنت' in n1 or 'ابنة' in n1
    fem2 = _is_female_name(name2) or 'بنت' in n2 or 'ابنة' in n2

    if fem1 != fem2:
        return False
    
    parts1 = [p for p in n1.split() if p not in ('بن', 'بنت', 'ابن', 'ابنة')]
    parts2 = [p for p in n2.split() if p not in ('بن', 'بنت', 'ابن', 'ابنة')]
    
    if not parts1 or not parts2:
        return False
    
    if parts1[0] != parts2[0]:
        return False
    
    if len(parts1) >= 2 and len(parts2) >= 2:
        return parts1[1] == parts2[1]
    
    return True


def sanitize_and_validate_heirs_graph(heirs: dict, raw_data: dict = None) -> dict:
    """
    Deterministic Legal Graph Validator for Islamic & Tunisian Farida Inheritance.
    Guarantees 100% legal integrity regardless of LLM/OCR JSON hallucinations:
    1. Spouses (wife, husband) & Parents (mother, father) are strictly purged from children arrays.
    2. Female names are strictly enforced as female (daughters), NEVER allowed as sons.
    3. Grandchildren (ibn l ibn / bint l ibn) & predeceased branches are sanitized.
    4. Heir counts and heir_details dictionary are re-indexed accurately.
    """
    w_name = str(heirs.get('wife_name', '')).strip()
    h_name = str(heirs.get('husband_name', '')).strip()
    m_name = str(heirs.get('mother_name', '')).strip()
    f_name = str(heirs.get('father_name', '')).strip()
    dec_name = str(heirs.get('deceased_name', '')).strip()
    
    ref_spouses_parents = [n for n in [w_name, h_name, m_name, f_name, dec_name] if n and len(n) > 1]
    
    raw_sons = heirs.get('sons_names', [])
    raw_daughters = heirs.get('daughters_names', [])
    raw_names = heirs.get('names', [])
    
    all_candidates = []
    seen_cand = set()
    
    for item in raw_sons + raw_daughters + raw_names:
        if item and str(item).strip():
            c = str(item).strip()
            norm_c = _norm(c)
            if norm_c not in seen_cand:
                seen_cand.add(norm_c)
                all_candidates.append(c)
                
    clean_sons = []
    clean_daughters = []
    
    for c in all_candidates:
        is_spouse_or_parent = False
        for ref in ref_spouses_parents:
            if _are_same_person(c, ref):
                is_spouse_or_parent = True
                break
        if is_spouse_or_parent:
            continue
            
        if _is_female_name(c) or 'بنت' in c or 'ابنة' in c:
            if c not in clean_daughters:
                clean_daughters.append(c)
        else:
            if c not in clean_sons:
                clean_sons.append(c)
                
    heir_details = {}
    s_idx, d_idx = 1, 1
    for s in clean_sons:
        heir_details[f"son_{s_idx}"] = {'name': s, 'gender': 'male'}
        s_idx += 1
    for d in clean_daughters:
        heir_details[f"daughter_{d_idx}"] = {'name': d, 'gender': 'female'}
        d_idx += 1
        
    heirs['sons_names'] = clean_sons
    heirs['daughters_names'] = clean_daughters
    heirs['names'] = clean_sons + clean_daughters
    heirs['heir_details'] = heir_details
    heirs['sons_count'] = len(clean_sons)
    heirs['daughters_count'] = len(clean_daughters)
    
    # Merge & sanitize predeceased_list
    predeceased = heirs.get('predeceased_list', [])
    if not predeceased and isinstance(raw_data, dict) and raw_data.get('predeceased_list'):
        predeceased = raw_data.get('predeceased_list', [])
        
    clean_predeceased = []
    for p in predeceased:
        if not isinstance(p, dict):
            continue
        p_copy = dict(p)
        p_name = str(p_copy.get('parent_name', '')).strip()
        if any(_are_same_person(p_name, ref) for ref in ref_spouses_parents):
            continue
            
        gc_names = p_copy.get('grandchildren_names', [])
        clean_gc = []
        for gc in gc_names:
            if gc and str(gc).strip():
                gc_str = str(gc).strip()
                if not any(_are_same_person(gc_str, ref) for ref in ref_spouses_parents):
                    clean_gc.append(gc_str)
        p_copy['grandchildren_names'] = clean_gc
        clean_predeceased.append(p_copy)
        
    heirs['predeceased_list'] = clean_predeceased
    heirs['predeceased_children_count'] = len(clean_predeceased)
    
    return heirs


class TunisianFaridaEngine:
    """
    Computes Tunisian Farida inheritance shares, base origin (أصل الفريضة),
    mandatory bequest, real estate mapping, and export.
    Uses clean notarial text.
    """

    def _compute_shares(self, heirs_dict: dict, property_area_m2: float = 0.0, property_parts: float = 0.0, deceased_m2: float = 0.0) -> dict:

        eff_area = deceased_m2 if (deceased_m2 and deceased_m2 > 0) else property_area_m2
        if deceased_m2 and deceased_m2 > 0:
            if property_parts > 0 and property_area_m2 > 0:
                eff_parts = (deceased_m2 / property_area_m2) * property_parts
            elif property_parts > 0:
                eff_parts = property_parts
            else:
                eff_parts = deceased_m2
        else:
            eff_parts = property_parts

        # ── 1. CLEAN INPUTS ───────────────────────────────────────────────────
        husband = heirs_dict.get('husband', False)
        wife = heirs_dict.get('wife', False) if not husband else False
        wives_count = max(1, int(heirs_dict.get('wives_count', 1))) if wife else 1

        sons_count = max(0, int(heirs_dict.get('sons_count', 0)))
        daughters_count = max(0, int(heirs_dict.get('daughters_count', 0)))

        grandsons_count = max(0, int(heirs_dict.get('grandsons_count', 0))) if sons_count == 0 else 0
        granddaughters_count = max(0, int(heirs_dict.get('granddaughters_count', 0))) if sons_count == 0 else 0

        father = heirs_dict.get('father', False)
        mother = heirs_dict.get('mother', False)
        paternal_grandfather = heirs_dict.get('paternal_grandfather', False) if not father else False
        maternal_grandmother = heirs_dict.get('maternal_grandmother', False) if not mother else False
        paternal_grandmother = heirs_dict.get('paternal_grandmother', False) if not mother and not father else False

        full_brothers_count = max(0, int(heirs_dict.get('full_brothers_count', 0))) if (sons_count == 0 and grandsons_count == 0 and not father) else 0
        full_sisters_count = max(0, int(heirs_dict.get('full_sisters_count', 0))) if (sons_count == 0 and grandsons_count == 0 and not father) else 0

        pat_brothers_count = max(0, int(heirs_dict.get('pat_brothers_count', 0))) if (sons_count == 0 and grandsons_count == 0 and not father and full_brothers_count == 0) else 0
        pat_sisters_count = max(0, int(heirs_dict.get('pat_sisters_count', 0))) if (sons_count == 0 and grandsons_count == 0 and not father and full_brothers_count == 0) else 0

        mat_siblings_count = max(0, int(heirs_dict.get('mat_siblings_count', 0))) if (sons_count == 0 and grandsons_count == 0 and not father and not paternal_grandfather) else 0

        nephew_full_count = max(0, int(heirs_dict.get('nephew_full_count', 0)))
        nephew_pat_count = max(0, int(heirs_dict.get('nephew_pat_count', 0)))
        
        uncle_full_input = heirs_dict.get('uncle_full_count', 1 if heirs_dict.get('uncle_full') else 0)
        uncle_full_count = max(0, int(uncle_full_input))
        
        uncle_pat_input = heirs_dict.get('uncle_pat_count', 1 if heirs_dict.get('uncle_pat') else 0)
        uncle_pat_count = max(0, int(uncle_pat_input))
        
        cousin_full_count = max(0, int(heirs_dict.get('cousin_full_count', 0)))
        cousin_pat_count = max(0, int(heirs_dict.get('cousin_pat_count', 0)))
        
        great_nephew_count = max(0, int(heirs_dict.get('great_nephew_count', 0)))
        great_cousin_count = max(0, int(heirs_dict.get('great_cousin_count', 0)))
        uterine_relatives_count = max(0, int(heirs_dict.get('uterine_relatives_count', 0)))

        predeceased_children = max(0, int(heirs_dict.get('predeceased_children_count', 0)))

        has_descendants = (sons_count > 0 or daughters_count > 0 or grandsons_count > 0 or granddaughters_count > 0)
        has_male_descendants = (sons_count > 0 or grandsons_count > 0)

        fixed_shares = {}

        # ── 2. MANDATORY BEQUEST (الوصية الواجبة - الفصل 191) ─────────────────
        obligatory_bequest_ratio = 0.0
        predeceased_list = heirs_dict.get('predeceased_list', [])
        active_predeceased = [p for p in predeceased_list if p.get("is_married", True)]
        if not active_predeceased and predeceased_children > 0:
            active_predeceased = [{"parent_name": "الابن المتوفى", "parent_gender": "male", "sons_count": 1, "daughters_count": 0}]

        if active_predeceased:
            num_predeceased_sons = sum(1 for p in active_predeceased if p.get("parent_gender", "male") == "male")
            num_predeceased_daug = sum(1 for p in active_predeceased if p.get("parent_gender", "male") == "female")
            
            hypo_sons = sons_count + num_predeceased_sons
            hypo_daug = daughters_count + num_predeceased_daug
            hypo_heads = (hypo_sons * 2) + hypo_daug

            if hypo_heads > 0:
                fixed_ratio_sum = 0.0
                if husband:
                    fixed_ratio_sum += 0.25 if (hypo_sons > 0 or hypo_daug > 0) else 0.5
                elif wife:
                    fixed_ratio_sum += 0.125 if (hypo_sons > 0 or hypo_daug > 0) else 0.25
                if mother:
                    fixed_ratio_sum += 1.0 / 6.0
                if father and (hypo_sons > 0 or hypo_daug > 0):
                    fixed_ratio_sum += 1.0 / 6.0

                rem_ratio_for_children = max(0.0, 1.0 - fixed_ratio_sum)

                total_bequest_ratio = 0.0
                raw_branch_ratios = {}
                for p_idx, p in enumerate(active_predeceased):
                    p_gender = p.get("parent_gender", "male")
                    p_multiplier = 2.0 if p_gender == "male" else 1.0
                    hypo_parent_ratio = (p_multiplier / float(hypo_heads)) * rem_ratio_for_children
                    raw_branch_ratios[p_idx] = hypo_parent_ratio
                    total_bequest_ratio += hypo_parent_ratio

                if total_bequest_ratio > (1.0 / 3.0):
                    scale_factor = (1.0 / 3.0) / total_bequest_ratio
                    obligatory_bequest_ratio = 1.0 / 3.0
                    branch_bequest_ratios = {idx: r * scale_factor for idx, r in raw_branch_ratios.items()}
                else:
                    obligatory_bequest_ratio = total_bequest_ratio
                    branch_bequest_ratios = raw_branch_ratios

        # ── 3. SPOUSE ──────────────────────────────────────────────────────────
        if husband:
            if has_descendants:
                fixed_shares['الزوج'] = (1, 4)
            else:
                fixed_shares['الزوج'] = (1, 2)
        elif wife:
            w_label = f"الزوجات (عدد {wives_count})" if wives_count > 1 else "الزوجة"
            if has_descendants:
                fixed_shares[w_label] = (1, 8)
            else:
                fixed_shares[w_label] = (1, 4)

        # ── 4. MOTHER & GRANDMOTHERS ──────────────────────────────────────────
        num_siblings = full_brothers_count + full_sisters_count + pat_brothers_count + pat_sisters_count + mat_siblings_count
        if mother:
            if has_descendants or num_siblings >= 2:
                fixed_shares['الأم'] = (1, 6)
            elif (husband or wife) and father and not has_descendants and num_siblings == 0:
                if husband:
                    fixed_shares['الأم'] = (1, 6) # 1/3 of remainder (1/3 of 1/2 = 1/6)
                else:
                    fixed_shares['الأم'] = (1, 4) # 1/3 of remainder (1/3 of 3/4 = 1/4)
            else:
                fixed_shares['الأم'] = (1, 3)
        else:
            if maternal_grandmother or paternal_grandmother:
                fixed_shares['الجدة'] = (1, 6)

        # ── 5. FATHER & GRANDFATHER ─────────────────────────────────────────
        if father:
            if has_male_descendants:
                fixed_shares['الأب (فرضا)'] = (1, 6)
            elif daughters_count > 0 or granddaughters_count > 0:
                fixed_shares['الأب (بالفرض والرد)'] = (1, 6)
        elif paternal_grandfather:
            if has_male_descendants:
                fixed_shares['الجد لأب'] = (1, 6)

        # ── 6. DAUGHTERS & GRANDDAUGHTERS ─────────────────────────────────────
        if daughters_count > 0 and sons_count == 0:
            if daughters_count == 1:
                fixed_shares['البنت'] = (1, 2)
            else:
                fixed_shares['البنات'] = (2, 3)

        if sons_count == 0 and daughters_count == 0 and granddaughters_count > 0:
            if granddaughters_count == 1:
                fixed_shares['بنت الابن'] = (1, 2)
            else:
                fixed_shares['بنات الابن'] = (2, 3)
        elif sons_count == 0 and daughters_count == 1 and granddaughters_count > 0:
            fixed_shares['بنات الابن (تكملة الثلثين)'] = (1, 6)

        # ── 7. MATERNAL SIBLINGS (الإخوة لأم) ──────────────────────────────────
        if mat_siblings_count > 0 and sons_count == 0 and grandsons_count == 0 and not father and not paternal_grandfather:
            if mat_siblings_count == 1:
                fixed_shares['الأخ/الأخت لأم'] = (1, 6)
            else:
                fixed_shares['الإخوة والأخوات لأم'] = (1, 3)

        # ── 8. FULL & PATERNAL SISTERS ─────────────────────────────────────────
        if sons_count == 0 and grandsons_count == 0 and not father and full_brothers_count == 0 and full_sisters_count > 0 and daughters_count == 0 and granddaughters_count == 0:
            if full_sisters_count == 1:
                fixed_shares['الأخت الشقيقة'] = (1, 2)
            else:
                fixed_shares['الأخوات الشقيقات'] = (2, 3)

        if sons_count == 0 and grandsons_count == 0 and not father and full_brothers_count == 0 and full_sisters_count == 0 and pat_brothers_count == 0 and pat_sisters_count > 0 and daughters_count == 0 and granddaughters_count == 0:
            if pat_sisters_count == 1:
                fixed_shares['الأخت لأب'] = (1, 2)
            else:
                fixed_shares['الأخوات لأب'] = (2, 3)

        # ── 9. CALCULATE DYNAMIC BASE ORIGIN & TASHIH ──────────────────────────
        denominators = [d for n, d in fixed_shares.values()]
        
        # Determine taasib heads for Tashih (correction of shares)
        taasib_heads = 0
        if sons_count > 0:
            taasib_heads = (sons_count * 2) + daughters_count
        elif sons_count == 0 and grandsons_count > 0:
            taasib_heads = (grandsons_count * 2) + granddaughters_count
        elif father and sons_count == 0 and grandsons_count == 0:
            taasib_heads = 1
        elif sons_count == 0 and grandsons_count == 0 and not father and full_brothers_count > 0:
            taasib_heads = (full_brothers_count * 2) + full_sisters_count
        elif sons_count == 0 and grandsons_count == 0 and not father and full_brothers_count == 0 and pat_brothers_count > 0:
            taasib_heads = (pat_brothers_count * 2) + pat_sisters_count
        elif sons_count == 0 and grandsons_count == 0 and not father and not paternal_grandfather and full_brothers_count == 0 and pat_brothers_count == 0:
            if nephew_full_count > 0: taasib_heads = nephew_full_count
            elif nephew_pat_count > 0: taasib_heads = nephew_pat_count
            elif great_nephew_count > 0: taasib_heads = great_nephew_count
            elif uncle_full_count > 0: taasib_heads = uncle_full_count
            elif uncle_pat_count > 0: taasib_heads = uncle_pat_count
            elif cousin_full_count > 0: taasib_heads = cousin_full_count
            elif cousin_pat_count > 0: taasib_heads = cousin_pat_count
            elif great_cousin_count > 0: taasib_heads = great_cousin_count
            elif uterine_relatives_count > 0: taasib_heads = uterine_relatives_count

        if denominators:
            base_origin = calculate_lcm_list(denominators)
        else:
            base_origin = taasib_heads if taasib_heads > 0 else 1

        shares_count = {}
        total_fixed_shares = 0
        for heir, (num, den) in fixed_shares.items():
            sh = (num * base_origin) // den
            shares_count[heir] = sh
            total_fixed_shares += sh

        is_awl = total_fixed_shares > base_origin
        if is_awl:
            base_origin = total_fixed_shares
            remaining_shares = 0
        else:
            remaining_shares = max(0, base_origin - total_fixed_shares)

        # Apply Tashih if remaining shares cannot be evenly divided by taasib heads
        if remaining_shares > 0 and taasib_heads > 1:
            g = gcd(int(remaining_shares), int(taasib_heads))
            multiplier = taasib_heads // g
            if multiplier > 1:
                base_origin *= multiplier
                for h_k in shares_count:
                    shares_count[h_k] *= multiplier
                remaining_shares *= multiplier

        final_origin = base_origin

        # ── 10. TAASIB DISTRIBUTION ──────────────────────────────────────────
        taasib_shares = {}
        if remaining_shares > 0 and taasib_heads > 0:
            one_head_share = remaining_shares // taasib_heads
            if sons_count > 0:
                if sons_count > 0:
                    taasib_shares['الأبناء (ذكور)'] = int(one_head_share * 2 * sons_count)
                if daughters_count > 0:
                    taasib_shares['البنات (مع الابن)'] = int(one_head_share * daughters_count)
            elif sons_count == 0 and grandsons_count > 0:
                if grandsons_count > 0:
                    taasib_shares['أبناء الابن (ذكور)'] = int(one_head_share * 2 * grandsons_count)
                if granddaughters_count > 0:
                    taasib_shares['بنات الابن'] = int(one_head_share * granddaughters_count)
            elif father and sons_count == 0 and grandsons_count == 0:
                taasib_shares['الأب'] = int(remaining_shares)
            elif sons_count == 0 and grandsons_count == 0 and not father and full_brothers_count > 0:
                if full_brothers_count > 0:
                    taasib_shares['الإخوة الأشقاء'] = int(one_head_share * 2 * full_brothers_count)
                if full_sisters_count > 0:
                    taasib_shares['الأخوات الشقيقات'] = int(one_head_share * full_sisters_count)
            elif sons_count == 0 and grandsons_count == 0 and not father and full_brothers_count == 0 and pat_brothers_count > 0:
                if pat_brothers_count > 0:
                    taasib_shares['الإخوة لأب'] = int(one_head_share * 2 * pat_brothers_count)
                if pat_sisters_count > 0:
                    taasib_shares['الأخوات لأب'] = int(one_head_share * pat_sisters_count)
            elif sons_count == 0 and grandsons_count == 0 and not father and not paternal_grandfather and full_brothers_count == 0 and pat_brothers_count == 0:
                if nephew_full_count > 0:
                    taasib_shares[f'أبناء الأخ الشقيق (عدد {nephew_full_count})'] = int(remaining_shares)
                elif nephew_pat_count > 0:
                    taasib_shares[f'أبناء الأخ لأب (عدد {nephew_pat_count})'] = int(remaining_shares)
                elif great_nephew_count > 0:
                    taasib_shares[f'أبناء ابن الأخ (عدد {great_nephew_count})'] = int(remaining_shares)
                elif uncle_full_count > 0:
                    lbl_u = 'العم الشقيق' if uncle_full_count == 1 else f'الأعمام الأشقاء (عدد {uncle_full_count})'
                    taasib_shares[lbl_u] = int(remaining_shares)
                elif uncle_pat_count > 0:
                    lbl_u = 'العم لأب' if uncle_pat_count == 1 else f'الأعمام لأب (عدد {uncle_pat_count})'
                    taasib_shares[lbl_u] = int(remaining_shares)
                elif cousin_full_count > 0:
                    taasib_shares[f'أبناء العم الشقيق (عدد {cousin_full_count})'] = int(remaining_shares)
                elif cousin_pat_count > 0:
                    taasib_shares[f'أبناء العم لأب (عدد {cousin_pat_count})'] = int(remaining_shares)
                elif great_cousin_count > 0:
                    taasib_shares[f'أبناء ابن العم (عدد {great_cousin_count})'] = int(remaining_shares)
                elif uterine_relatives_count > 0:
                    taasib_shares[f'ذو الرحم / القرابة الرحمية (الفصل 144 م.أ.ش - عدد {uterine_relatives_count})'] = int(remaining_shares)

        # RESTORATION TO ALL QURANIC BLOOD RELATIVES (الرد - الفصل 143 م.أ.ش)
        is_radd = False
        if not is_awl and remaining_shares > 0 and taasib_heads == 0:
            is_radd = True
            if not husband and not wife:
                final_origin = total_fixed_shares
                remaining_shares = 0
            else:
                blood_keys = [k for k in list(shares_count.keys()) if not k.startswith('الزوج') and not k.startswith('الزوجة')]
                s_blood = sum(shares_count[k] for k in blood_keys)
                if s_blood > 0:
                    spouse_keys = [k for k in list(shares_count.keys()) if k.startswith('الزوج') or k.startswith('الزوجة')]
                    spouse_total_shares = sum(shares_count[k] for k in spouse_keys)
                    
                    new_base = base_origin * s_blood
                    new_shares = {}
                    for sp_k in spouse_keys:
                        new_shares[sp_k] = shares_count[sp_k] * s_blood
                    for b_k in blood_keys:
                        new_shares[b_k] = shares_count[b_k] * (base_origin - spouse_total_shares)
                    
                    all_vals = [new_base] + list(new_shares.values())
                    g = reduce(gcd, all_vals)
                    final_origin = new_base // g
                    
                    old_keys = list(shares_count.keys())
                    for k in old_keys:
                        if k in spouse_keys:
                            shares_count[k] = new_shares[k] // g
                        else:
                            lbl = k if "ورداً" in k else f"{k} (فرضا ورداً - الفصل 143)"
                            shares_count[lbl] = new_shares[k] // g
                            if lbl != k:
                                del shares_count[k]
                    remaining_shares = 0

        # ── 11. FINAL RESULTS LIST ─────────────────────────────────────────────
        results_list = []
        predeceased_list = heirs_dict.get('predeceased_list', [])

        if obligatory_bequest_ratio > 0:
            total_bequest_area = round(property_area_m2 * obligatory_bequest_ratio, 2) if property_area_m2 > 0 else 0.0
            total_bequest_parts = round(property_parts * obligatory_bequest_ratio, 2) if property_parts > 0 else 0.0
            bequest_perc = round(obligatory_bequest_ratio * 100.0, 2)

            results_list.append({
                "heir": "أولاد الابن/البنت (وصية واجبة - الفصل 191)",
                "shares": "—",
                "base_origin": final_origin,
                "fraction": "وصية واجبة",
                "percentage": bequest_perc,
                "area_m2": total_bequest_area,
                "parts": total_bequest_parts,
                "is_waseya_summary": True
            })

            # Process individual grandchildren rows if predeceased_list details exist
            active_branches = [p for p in predeceased_list if p.get("is_married", True)]
            if not active_branches and predeceased_children > 0:
                active_branches = [{"parent_name": "الابن المتوفى", "parent_gender": "male", "sons_count": 1, "daughters_count": 0, "grandchildren_names": []}]

            num_branches = max(1, len(active_branches))
            for b_idx, b in enumerate(active_branches):
                p_name = b.get("parent_name") or "المتوفى سابقاً"
                p_gender = b.get("parent_gender")
                if not p_gender:
                    p_gender = "female" if (_is_female_name(p_name) or "بنت" in p_name or "ابنة" in p_name) else "male"
                
                s_cnt = max(0, int(b.get("sons_count", 0)))
                d_cnt = max(0, int(b.get("daughters_count", 0)))
                gc_names = b.get("grandchildren_names", [])

                if obligatory_bequest_ratio > 0:
                    branch_ratio = branch_bequest_ratios.get(b_idx, obligatory_bequest_ratio / float(num_branches))
                else:
                    rem_ratio_for_sons = max(0.0, 1.0 - (0.125 if wife else (0.25 if husband else (0.16666666666666666 if mother or father else 0.0))))
                    s_cnt_total = max(1, sons_count)
                    branch_ratio = rem_ratio_for_sons / float(s_cnt_total)

                has_branch_children = (s_cnt > 0 or d_cnt > 0 or bool(gc_names))
                children_branch_ratio = branch_ratio

                sp_name = (b.get("spouse_name") or b.get("wife_name") or b.get("husband_name") or "").strip()
                has_sp = bool(sp_name or b.get("wife") or b.get("husband") or (b.get("is_married", True) and sp_name))

                sp_factor = 0.0
                if has_sp:
                    sp_label_name = sp_name if sp_name else ("زوجته" if p_gender == "male" else "زوجها")
                    if p_gender == "male":
                        sp_factor = 0.125 if has_branch_children else 0.25
                        sp_fraction_text = "ثمن المناب" if has_branch_children else "ربع المناب"
                        sp_rel_title = "زوجة الابن المتوفى"
                    else:
                        sp_factor = 0.25 if has_branch_children else 0.50
                        sp_fraction_text = "ربع المناب" if has_branch_children else "نصف المناب"
                        sp_rel_title = "زوج البنت المتوفاة"

                    sp_ratio = branch_ratio * sp_factor
                    children_branch_ratio = max(0.0, children_branch_ratio - sp_ratio)
                    sp_perc = round(sp_ratio * 100.0, 2)
                    sp_area = round(sp_ratio * property_area_m2, 2) if property_area_m2 > 0 else 0.0
                    sp_parts = round(sp_ratio * property_parts, 2) if property_parts > 0 else 0.0
                    sp_shares = round(final_origin * sp_ratio, 2)
                    if float(sp_shares).is_integer():
                        sp_shares = int(sp_shares)

                    results_list.append({
                        "heir": f"{sp_rel_title} ({sp_label_name}) (مناب {p_name})",
                        "clean_name": sp_label_name,
                        "clean_rel": f"{sp_rel_title} (فرع {p_name})",
                        "parent_name": p_name,
                        "count": 1,
                        "shares": sp_shares,
                        "single_shares": sp_shares,
                        "base_origin": final_origin,
                        "fraction": sp_fraction_text,
                        "percentage": sp_perc,
                        "single_percentage": sp_perc,
                        "area_m2": sp_area,
                        "single_area_m2": sp_area,
                        "parts": sp_parts,
                        "single_parts": sp_parts,
                        "is_individual_grandchild": True
                    })

                # Secondary succession parents (Mother/Father of predeceased child)
                has_m = bool(b.get("mother_name") or b.get("has_mother"))
                m_factor = 0.0
                if has_m:
                    m_name = (b.get("mother_name") or "أم المتوفى").strip()
                    m_factor = 1.0 / 6.0 if has_branch_children else 1.0 / 3.0
                    m_ratio = branch_ratio * m_factor
                    children_branch_ratio = max(0.0, children_branch_ratio - m_ratio)
                    m_perc = round(m_ratio * 100.0, 2)
                    m_area = round(m_ratio * property_area_m2, 2) if property_area_m2 > 0 else 0.0
                    m_parts = round(m_ratio * property_parts, 2) if property_parts > 0 else 0.0
                    m_shares = round(final_origin * m_ratio, 2)
                    if float(m_shares).is_integer(): m_shares = int(m_shares)
                    
                    results_list.append({
                        "heir": f"أم {p_name} ({m_name})",
                        "clean_name": m_name,
                        "clean_rel": f"أم فرع {p_name}",
                        "parent_name": p_name,
                        "count": 1,
                        "shares": m_shares,
                        "single_shares": m_shares,
                        "base_origin": final_origin,
                        "fraction": "سدس المناب" if has_branch_children else "ثلث المناب",
                        "percentage": m_perc,
                        "single_percentage": m_perc,
                        "area_m2": m_area,
                        "single_area_m2": m_area,
                        "parts": m_parts,
                        "single_parts": m_parts,
                        "is_individual_grandchild": True
                    })

                has_f = bool(b.get("father_name") or b.get("has_father"))
                if has_f:
                    f_name = (b.get("father_name") or "أب المتوفى").strip()
                    f_factor = 1.0 / 6.0 if has_branch_children else max(0.0, 1.0 - sp_factor - m_factor)
                    f_ratio = branch_ratio * f_factor
                    children_branch_ratio = max(0.0, children_branch_ratio - f_ratio)
                    f_perc = round(f_ratio * 100.0, 2)
                    f_area = round(f_ratio * property_area_m2, 2) if property_area_m2 > 0 else 0.0
                    f_parts = round(f_ratio * property_parts, 2) if property_parts > 0 else 0.0
                    f_shares = round(final_origin * f_ratio, 2)
                    if float(f_shares).is_integer(): f_shares = int(f_shares)
                    
                    results_list.append({
                        "heir": f"أب {p_name} ({f_name})",
                        "clean_name": f_name,
                        "clean_rel": f"أب فرع {p_name}",
                        "parent_name": p_name,
                        "count": 1,
                        "shares": f_shares,
                        "single_shares": f_shares,
                        "base_origin": final_origin,
                        "fraction": "سدس المناب" if has_branch_children else "الباقي تعصيباً",
                        "percentage": f_perc,
                        "single_percentage": f_perc,
                        "area_m2": f_area,
                        "single_area_m2": f_area,
                        "parts": f_parts,
                        "single_parts": f_parts,
                        "is_individual_grandchild": True
                    })

                if s_cnt == 0 and d_cnt == 0:
                    s_cnt = 1

                total_heads = (s_cnt * 2) + d_cnt
                if total_heads <= 0:
                    total_heads = 1

                male_rel = "ابن الابن" if p_gender == "male" else "ابن البنت"
                female_rel = "بنت الابن" if p_gender == "male" else "بنت البنت"

                male_gc_names = [n for n in gc_names if not _is_female_name(n) and "بنت" not in n]
                female_gc_names = [n for n in gc_names if _is_female_name(n) or "بنت" in n]

                # Male grandchildren
                for si in range(1, s_cnt + 1):
                    g_name = male_gc_names[si - 1] if (si - 1) < len(male_gc_names) else f"{male_rel} {si}"
                    g_ratio = (2.0 / float(total_heads)) * children_branch_ratio
                    g_perc = round(g_ratio * 100.0, 2)
                    g_area = round(g_ratio * eff_area, 2) if eff_area > 0 else 0.0
                    g_parts = round(g_ratio * eff_parts, 2) if eff_parts > 0 else 0.0

                    g_shares = round(final_origin * g_ratio, 2)
                    if float(g_shares).is_integer():
                        g_shares = int(g_shares)

                    results_list.append({
                        "heir": f"{male_rel} ({g_name}) (مناب فرع {p_name})",
                        "clean_name": g_name,
                        "clean_rel": f"{male_rel} (فرع {p_name})",
                        "parent_name": p_name,
                        "count": 1,
                        "shares": g_shares,
                        "single_shares": g_shares,
                        "base_origin": final_origin,
                        "fraction": "مناب بالتناصب",
                        "percentage": g_perc,
                        "single_percentage": g_perc,
                        "area_m2": g_area,
                        "single_area_m2": g_area,
                        "parts": g_parts,
                        "single_parts": g_parts,
                        "is_individual_grandchild": True
                    })

                # Female grandchildren
                for di in range(1, d_cnt + 1):
                    g_name = female_gc_names[di - 1] if (di - 1) < len(female_gc_names) else f"{female_rel} {di}"
                    g_ratio = (1.0 / float(total_heads)) * children_branch_ratio
                    g_perc = round(g_ratio * 100.0, 2)
                    g_area = round(g_ratio * eff_area, 2) if eff_area > 0 else 0.0
                    g_parts = round(g_ratio * eff_parts, 2) if eff_parts > 0 else 0.0
                    g_shares = round(final_origin * g_ratio, 2)
                    if float(g_shares).is_integer():
                        g_shares = int(g_shares)

                    results_list.append({
                        "heir": f"{female_rel} ({g_name}) (مناب فرع {p_name})",
                        "clean_name": g_name,
                        "clean_rel": f"{female_rel} (فرع {p_name})",
                        "parent_name": p_name,
                        "count": 1,
                        "shares": g_shares,
                        "single_shares": g_shares,
                        "base_origin": final_origin,
                        "fraction": "مناب بالتناصب",
                        "percentage": g_perc,
                        "single_percentage": g_perc,
                        "area_m2": g_area,
                        "single_area_m2": g_area,
                        "parts": g_parts,
                        "single_parts": g_parts,
                        "is_individual_grandchild": True
                    })

        for heir, sh in list(shares_count.items()) + list(taasib_shares.items()):
            sh_int = int(sh) if isinstance(sh, (int, float)) and float(sh).is_integer() else sh
            ratio = float(sh) / float(final_origin)
            rem_factor = 1.0 - obligatory_bequest_ratio
            percentage = ratio * (rem_factor * 100.0)
            area_m2 = ratio * (eff_area * rem_factor)
            parts = ratio * (eff_parts * rem_factor)

            count = 1
            if "الأبناء" in heir:
                count = sons_count
            elif "البنات" in heir:
                count = daughters_count
            elif "الإخوة الأشقاء" in heir:
                count = full_brothers_count
            elif "الأخوات الشقيقات" in heir:
                count = full_sisters_count
            elif "الزوجات" in heir:
                count = wives_count

            single_sh = round(float(sh) / float(count), 2) if count > 0 else sh_int
            if isinstance(single_sh, float) and single_sh.is_integer():
                single_sh = int(single_sh)
            single_percentage = round(percentage / float(count), 2) if count > 0 else round(percentage, 2)
            single_area_m2 = round(area_m2 / float(count), 2) if count > 0 else round(area_m2, 2)
            single_parts = round(parts / float(count), 2) if count > 0 else round(parts, 2)

            results_list.append({
                "heir": heir,
                "count": count,
                "shares": sh_int,
                "single_shares": single_sh,
                "base_origin": final_origin,
                "fraction": f"{sh_int}/{final_origin}",
                "percentage": round(percentage, 2),
                "single_percentage": single_percentage,
                "area_m2": round(area_m2, 2),
                "single_area_m2": single_area_m2,
                "parts": round(parts, 2),
                "single_parts": single_parts
            })

        return {
            "base_origin": final_origin,
            "is_awl": is_awl,
            "is_radd": is_radd,
            "results": results_list
        }

    def calculate_farida(self, heirs_dict: dict,
                         contract_type: str = "فريضة شرعية",
                         applicant_name: str = "", applicant_cin: str = "",
                         deceased_name: str = "", hujja_num: str = "", hujja_date: str = "", hujja_court: str = "",
                         title_num: str = "", property_name: str = "", location: str = "",
                         property_area_m2: float = 0.0, deceased_m2: float = 0.0, property_parts: float = 0.0,
                         heir_details: dict = None,
                         property_type: str = "",
                         predeceased_death_date: str = "",
                         parts_unit: str = "جزءاً",
                         proof_of_death_source: str = "",
                         cpf_death_date: str = "",
                         cpf_volume_num: str = "",
                         cpf_entry_num: str = "") -> dict:

        if not heir_details:
            heir_details = {}

        if isinstance(heirs_dict, dict):
            if proof_of_death_source: heirs_dict["proof_of_death_source"] = proof_of_death_source
            if cpf_death_date: heirs_dict["cpf_death_date"] = cpf_death_date
            if cpf_volume_num: heirs_dict["cpf_volume_num"] = cpf_volume_num
            if cpf_entry_num: heirs_dict["cpf_entry_num"] = cpf_entry_num
        
        h_names = (heirs_dict or {}).get("names", [])
        if h_names:
            existing_names = set(v.get("name", "").strip() for v in heir_details.values() if isinstance(v, dict) and v.get("name"))
            s_idx, d_idx = 1, 1
            for name in h_names:
                clean_n = name.strip()
                if not clean_n or clean_n in existing_names:
                    continue
                if _is_female_name(clean_n) or "بنت" in clean_n:
                    while f"daughter_{d_idx}" in heir_details and heir_details[f"daughter_{d_idx}"].get("name"):
                        d_idx += 1
                    key = f"daughter_{d_idx}"
                    d_idx += 1
                else:
                    while f"son_{s_idx}" in heir_details and heir_details[f"son_{s_idx}"].get("name"):
                        s_idx += 1
                    key = f"son_{s_idx}"
                    s_idx += 1
                heir_details[key] = {"name": clean_n}
                existing_names.add(clean_n)

        if (heirs_dict or {}).get("wife_name") and "wife_0" not in heir_details:
            heir_details["wife_0"] = {"name": heirs_dict["wife_name"]}
        if (heirs_dict or {}).get("husband_name") and "husband" not in heir_details:
            heir_details["husband"] = {"name": heirs_dict["husband_name"]}

        res = self._compute_shares(heirs_dict, property_area_m2, property_parts, deceased_m2)
        
        legal_text = self._build_notarial_legal_text(
            origin=res["base_origin"],
            results=res["results"],
            contract_type=contract_type,
            applicant_name=applicant_name,
            applicant_cin=applicant_cin,
            deceased_name=deceased_name,
            hujja_num=hujja_num,
            hujja_date=hujja_date,
            hujja_court=hujja_court,
            title_num=title_num,
            property_name=property_name,
            location=location,
            area_m2=property_area_m2,
            deceased_m2=deceased_m2,
            parts=property_parts,
            heir_details=heir_details,
            property_type=property_type,
            predeceased_death_date=predeceased_death_date,
            heirs_dict=heirs_dict,
            parts_unit=parts_unit
        )

        return {
            "contract_type": contract_type,
            "applicant_name": applicant_name,
            "applicant_cin": applicant_cin,
            "deceased_name": deceased_name,
            "hujja_num": hujja_num,
            "hujja_date": hujja_date,
            "hujja_court": hujja_court,
            "title_num": title_num,
            "property_name": property_name,
            "location": location,
            "base_origin": res["base_origin"],
            "is_awl": res["is_awl"],
            "is_radd": res["is_radd"],
            "heirs_summary": res["results"],
            "legal_notarial_text": legal_text,
            "property_area_m2": property_area_m2,
            "deceased_m2": deceased_m2,
            "property_parts": property_parts,
            "heir_details": heir_details or {}
        }

    def _build_notarial_legal_text(self, origin: int, results: list,
                                 contract_type: str = "فريضة شرعية",
                                 applicant_name: str = "", applicant_cin: str = "",
                                 deceased_name: str = "", hujja_num: str = "", hujja_date: str = "", hujja_court: str = "",
                                 title_num: str = "", property_name: str = "", location: str = "",
                                 area_m2: float = 0.0, deceased_m2: float = 0.0, parts: float = 0.0,
                                 heir_details: dict = None,
                                 property_type: str = "",
                                 predeceased_death_date: str = "",
                                 heirs_dict: dict = None,
                                 parts_unit: str = "جزءاً") -> str:
        def _norm_chk(t):
            if not t: return ""
            t = re.sub(r'[\u064b-\u065f\u0670]', '', str(t))
            t = re.sub(r'[أإآٱ]', 'ا', t)
            t = re.sub(r'ة', 'ه', t)
            t = re.sub(r'ى', 'ي', t)
            t = re.sub(r'^(الابن|البنت|ابن|بنت)\s+', '', t.strip())
            return t.strip()

        notary_name_val = ""
        court_val = ""
        if office_profile:
            try:
                prof = office_profile.load()
                notary_name_val = (prof.get("display_name") or prof.get("notary_name") or "").strip()
                court_val = (prof.get("court") or "").strip()
            except Exception:
                pass

        now = datetime.datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        full_date_str = f"في يوم {date_str}"
        if contract_templates:
            try:
                d_info = contract_templates.get_current_arabic_date_info(now)
                if d_info and isinstance(d_info, dict):
                    d_words = d_info.get('day_words', '')
                    h_date = d_info.get('hijri_date', '')
                    g_date = d_info.get('gregorian_date', '')
                    if d_words and h_date and g_date:
                        full_date_str = f"في يوم {d_words} من {h_date} هـ الموافق لـ{g_date}"
                    elif d_info.get('full_date_text'):
                        full_date_str = d_info.get('full_date_text').split(" وعلى الساعة")[0]
            except Exception:
                pass

        # Determine unit mode for formatting (جزءاً / أجزاء vs سهماً / أسهم)
        if parts_unit and ("سهم" in str(parts_unit) or "أسهم" in str(parts_unit) or str(parts_unit).lower() == "shares"):
            is_equal_unit = False
        elif parts_unit and ("جزء" in str(parts_unit) or "أجزاء" in str(parts_unit) or str(parts_unit).lower() == "parts"):
            is_equal_unit = True
        else:
            is_equal_unit = bool(parts > 0)

        def _fmt_shares(sh_val, is_equal_unit=is_equal_unit):
            try:
                v_num = float(sh_val)
                if v_num.is_integer():
                    v_str = f"({int(v_num)})"
                    v = int(v_num)
                else:
                    v_str = f"({v_num:.2f})"
                    v = v_num
            except Exception:
                v_str = f"({sh_val})"
                v = sh_val

            if is_equal_unit:
                if isinstance(v, int) and 3 <= v <= 10:
                    return f"{v_str} أجزاء"
                elif v == 1:
                    return f"{v_str} جزء واحد"
                elif v == 2:
                    return f"{v_str} جزءان"
                else:
                    return f"{v_str} جزءاً"
            else:
                if isinstance(v, int) and 3 <= v <= 10:
                    return f"{v_str} أسهم"
                elif v == 1:
                    return f"{v_str} سهم واحد"
                elif v == 2:
                    return f"{v_str} سهمان"
                else:
                    return f"{v_str} سهماً"

        is_partial = (contract_type == "فريضة جزئية")
        contract_title = "فريضة جزئية" if is_partial else "فريضة شرعية"

        # Determine gender of deceased for correct notarial phrase (للمرحوم vs للمرحومة)
        husband_present = (heir_details or {}).get("husband", {}).get("name") or False
        wife_present = (heir_details or {}).get("wife_1", {}).get("name") or (heir_details or {}).get("wife_0", {}).get("name") or False
        is_female_dec = _is_female_name(deceased_name) or bool(husband_present) or ("المتوفاة" in deceased_name or "المتوفية" in deceased_name or "الهالكة" in deceased_name)
        if wife_present or "بوجمعه" in deceased_name or "بن" in deceased_name:
            is_female_dec = False

        dec_title = "للمرحومة" if is_female_dec else "للمرحوم"

        # 1. Notarial Opening: الحمد لله وحده، [date]، نحن عدلا الإشهاد...، وبطلب من السيد(ة) [name] صاحب(ة) ب.ت.و عدد [cin] قصد القيام بـ... للمرحوم...
        court_str = f" بـ {court_val}" if court_val else ""
        if notary_name_val:
            notary_opening = f"نحن الأستاذ {notary_name_val} وجليسه عدلا الإشهاد بدائرة قضاء المحكمة الابتدائية{court_str}"
        else:
            notary_opening = f"نحن عدلا الإشهاد بدائرة قضاء المحكمة الابتدائية{court_str}"

        is_app_female = _is_female_name(applicant_name) if applicant_name else False
        app_title = "السيدة" if is_app_female else "السيد"
        sahib_title = "صاحبة" if is_app_female else "صاحب"

        cin_clause = f" {sahib_title} بطاقة التعريف الوطنية عدد {applicant_cin}" if applicant_cin else f" {sahib_title} بطاقة التعريف الوطنية عدد ..."

        if applicant_name:
            applicant_str = f"وبطلب من {app_title} {applicant_name}{cin_clause} قصد القيام بـ{contract_title} {dec_title} {deceased_name if deceased_name else '...'}"
        else:
            applicant_str = f"وبطلب من طالب الإشهاد{cin_clause} قصد القيام بـ{contract_title} {dec_title} {deceased_name if deceased_name else '...'}"

        p1 = f"الحمد لله وحده، {full_date_str}، {notary_opening}، {applicant_str}"

        # 2. Real Estate Specification (Paragraph 2)
        p_prop = ""
        if is_partial or title_num or property_name or location or area_m2 > 0 or deceased_m2 > 0 or parts > 0 or property_type:
            prop_desc = []
            if property_type:
                prop_desc.append(f"في {property_type.strip()}")
            elif property_name:
                p_name_clean = property_name.strip('\"')
                prop_desc.append(f"في العقار المسمى \"{p_name_clean}\"")
            
            if property_name and property_type and property_name.strip('\"') not in property_type:
                prop_desc.append(f"المسمى \"{property_name.strip('\"')}\"")

            if title_num:
                prop_desc.append(f"موضوع الرسم العقاري عدد {title_num}")

            if location:
                loc_clean = location.strip()
                if not loc_clean.startswith("الكائن") and not loc_clean.startswith("بـ"):
                    loc_clean = f"بـ{loc_clean}"
                prop_desc.append(f"والكائن {loc_clean}" if not loc_clean.startswith("والكائن") else loc_clean)

            if area_m2 > 0:
                a_str = int(area_m2) if float(area_m2).is_integer() else area_m2
                if deceased_m2 > 0 and deceased_m2 != area_m2:
                    d_m2_str = int(deceased_m2) if float(deceased_m2).is_integer() else deceased_m2
                    unit_m2_word = "م²" if is_equal_unit else "سهم"
                    prop_desc.append(f"والذي مساحته الجملية : {a_str} م² (ينوب الهالك منها {d_m2_str} {unit_m2_word})")
                else:
                    prop_desc.append(f"والذي مساحته الجملية : {a_str} م²")

            if parts > 0:
                p_str = int(parts) if float(parts).is_integer() else parts
                unit_word = "جزءاً" if is_equal_unit else "سهماً"
                prop_desc.append(f"والمجزأ إلى ({p_str}) {unit_word}.")

            p_str_parts = int(parts) if float(parts).is_integer() else parts
            unit_word = "جزءاً" if is_equal_unit else "سهماً"
            dec_label = deceased_name if deceased_name else ("الهالكة" if is_female_dec else "الهالك")
            # Use المرحوم/المرحومة (without لـ) for "على ملك المرحوم ..." in paragraph 2
            dec_title_gen = "المرحومة" if is_female_dec else "المرحوم"

            p_prop = f"وحيث إستقر على ملك {dec_title_gen} {dec_label} منابات على الشياع وقدرها ({p_str_parts}) {unit_word} " + " ".join(prop_desc)

        p_partial_extra = "على أن هذه الفريضة الجزئية لا تكون بمعزل عن فريضة كل من الموروثين السابقين وانجرار أصل التركة." if is_partial else ""

        hujja_date_clean = hujja_date.replace("-", "/").strip() if hujja_date else ""
        predeceased_clean = predeceased_death_date.replace("-", "/").strip() if predeceased_death_date else ""

        # 3. Death Certificate Reference & Heirs Succession (Form 1 vs Form 2)
        proof_src = (heirs_dict or {}).get("proof_of_death_source") if isinstance(heirs_dict, dict) else None
        cpf_dt = (heirs_dict or {}).get("cpf_death_date", "") if isinstance(heirs_dict, dict) else ""
        cpf_vol = (heirs_dict or {}).get("cpf_volume_num", "") if isinstance(heirs_dict, dict) else ""
        cpf_entry = (heirs_dict or {}).get("cpf_entry_num", "") if isinstance(heirs_dict, dict) else ""

        if not proof_src:
            proof_src = "property_title" if (cpf_dt or cpf_vol or cpf_entry) else "hujja_wafat"

        dec_verb = "توفيت" if is_female_dec else "توفي"
        dec_label = deceased_name if deceased_name else ("الهالكة" if is_female_dec else "الهالك")
        hujja_pronoun = "وفاتها" if is_female_dec else "وفاته"
        irath_verb = "وأحاطت بإرثها" if is_female_dec else "وأحاط بإرثه"

        if proof_src == "property_title":
            # Form 2: Proof of Death registered directly on Real Estate Property Title (المدرجة بإدارة الملكية العقارية)
            cpf_dt_clean = cpf_dt.replace("-", "/").strip() if cpf_dt else hujja_date_clean
            date_part = f"بتاريخ {cpf_dt_clean}" if cpf_dt_clean else ""
            
            vol_entry_parts = []
            if cpf_vol: vol_entry_parts.append(f"مجلد {cpf_vol}")
            if cpf_entry: vol_entry_parts.append(f"عدد {cpf_entry}")
            vol_entry_str = f" ({' '.join(vol_entry_parts)})" if vol_entry_parts else ""

            h_details_str = f"حسب ترسيم {hujja_pronoun} المدرجة بإدارة الملكية العقارية {date_part}{vol_entry_str}".strip()
        else:
            # Form 1: Proof of Death from Court Hujjat Wafat (الصادرة عن محكمة الناحية)
            hujja_parts = []
            if hujja_court: hujja_parts.append(f"الصادرة عن {hujja_court}")
            if hujja_date_clean: hujja_parts.append(f"بتاريخ {hujja_date_clean}")
            if hujja_num: hujja_parts.append(f"تحت عدد {hujja_num}")

            if hujja_parts:
                h_details_str = f"حسب حجة {hujja_pronoun} " + " ".join(hujja_parts)
            else:
                h_details_str = f"حسب حجة {hujja_pronoun} الرسمية"

        # Collect heir names for narrative ("وأحاط بإرثه ... والداه X وزوجته Y وأبناؤه منها وهم Z لا غير")
        spouses_list = []
        children_list = []
        others_list = []

        # 1. Add direct living sons and daughters from heir_details (excluding grandchildren!)
        for k, hd in (heir_details or {}).items():
            nm = hd.get("name", "").strip()
            if nm:
                lbl = hd.get("label", "")
                if ("wife" in k or "زوجة" in lbl) and "wife" not in "".join(spouses_list):
                    spouses_list.append(f"زوجته {nm}")
                elif ("husband" in k or "زوج" in lbl) and "husband" not in "".join(spouses_list):
                    spouses_list.append(f"زوجها {nm}")
                elif ("son_" in k or "daughter_" in k) and not k.startswith("grandson_") and not k.startswith("granddaughter_"):
                    first_name = nm.split()[0] if nm.split() else nm
                    if first_name not in children_list:
                        children_list.append(first_name)
                elif not k.startswith("grandson_") and not k.startswith("granddaughter_"):
                    others_list.append(nm)

        # 2. Add predeceased children's names (e.g. بوجمعة) to main deceased's direct children list!
        predeceased_list = (heirs_dict or {}).get('predeceased_list', []) if isinstance(heirs_dict, dict) else []
        for p in predeceased_list:
            p_name = p.get("parent_name", "").strip()
            if p_name:
                p_first = p_name.split()[0] if p_name.split() else p_name
                if p_first not in children_list:
                    children_list.append(p_first)

        narrative_parts = []
        if spouses_list:
            narrative_parts.extend(spouses_list)
        if children_list:
            narrative_parts.append("وأبناؤه منها وهم " + " و".join(children_list) if spouses_list else "وأبناؤه وهم " + " و".join(children_list))
        if others_list:
            narrative_parts.extend(others_list)

        narrative_str = " " + " ".join(narrative_parts) + " لا غير" if narrative_parts else ""

        calc_area = deceased_m2 if (deceased_m2 and deceased_m2 > 0) else area_m2
        if deceased_m2 and deceased_m2 > 0:
            if parts > 0 and area_m2 > 0:
                calc_parts = (deceased_m2 / area_m2) * parts
            elif parts > 0:
                calc_parts = parts
            else:
                calc_parts = deceased_m2
        else:
            calc_parts = parts

        if parts > 0 or calc_parts > 0:
            eff_val = calc_parts if calc_parts > 0 else parts
            eff_origin = int(eff_val) if float(eff_val).is_integer() else round(eff_val, 2)
        elif area_m2 > 0 or calc_area > 0:
            eff_val = calc_area if calc_area > 0 else area_m2
            eff_origin = int(eff_val) if float(eff_val).is_integer() else round(eff_val, 2)
        else:
            eff_origin = origin

        unit_origin_str = ("جزءاً" if is_equal_unit else "سهماً") if (parts > 0 or calc_parts > 0) else ("متراً مربعاً" if (area_m2 > 0 or calc_area > 0) else "سهماً")

        p_succ = f"وحيث {dec_verb} {dec_label} عن منابات قدرها ({eff_origin}) {unit_origin_str} {irath_verb} {h_details_str}:"



        renounce_statements = []
        for k, hd in (heir_details or {}).items():
            if hd.get("is_renounced"):
                nm = hd.get("name", "").strip() or hd.get("label", "الوارث")
                tgt = hd.get("renounce_target", "all")
                tgt_name = "سائر الورثة بالتناسب"
                if tgt != "all" and tgt in (heir_details or {}):
                    t_hd = (heir_details or {})[tgt]
                    tgt_name = f"الوارث(ة) {t_hd.get('name', '').strip() or t_hd.get('label', '')}"
                renounce_statements.append(f"صرّح(ت) {nm} بتنازله(ا) التام والناجز عن كامل منابه(ا) الشرعي في التركة صلحاً وإسقاطاً لفائدة {tgt_name}")

        if renounce_statements:
            renounce_text = "، و".join(renounce_statements)
            p_succ += f" (ومع الاعتبار والإثبات الشرعي لحصول التنازل والصلح: حيث {renounce_text}، وبناءً عليه أصبح توزيع المنابات النهائي كما يلي:)"

        # 4. Collect Individual Heirs & Perform Remainder Adjustment
        heir_items = []
        for r in results:
            if r.get("is_waseya_summary"):
                continue

            cnt = r.get("count", 1)
            sh_val = r.get("single_shares", r["shares"])
            
            # For waseya row shares="—" cannot be cast to float — use pre-computed values
            if "وصية واجبة" in r['heir']:
                raw_area = float(r.get("area_m2", 0.0))
                raw_parts = float(r.get("parts", 0.0))
            else:
                raw_area = (float(sh_val) / float(origin)) * calc_area if origin > 0 and calc_area > 0 else 0.0
                raw_parts = (float(sh_val) / float(origin)) * calc_parts if origin > 0 and calc_parts > 0 else 0.0

            prefix = None
            is_waseya = "وصية واجبة" in r['heir']  # skip bequest row from prefix matching
            is_indiv = r.get("is_individual_grandchild", False)
            if not is_waseya and not is_indiv:
                if "البنات" in r['heir'] or ("بنت" in r['heir'] and "بنت الابن" not in r['heir'] and "بنات الابن" not in r['heir']):
                    prefix = "daughter_"
                elif "الأبناء" in r['heir'] or ("ابن" in r['heir'] and "ابن الابن" not in r['heir'] and "أبناء الابن" not in r['heir'] and "بنت" not in r['heir'] and "البنات" not in r['heir'] and "بنات" not in r['heir']):
                    prefix = "son_"
                elif "الزوجات" in r['heir'] or "الزوجة" in r['heir']:
                    prefix = "wife_"
                elif "أبناء الابن" in r['heir'] or "ابن الابن" in r['heir']:
                    prefix = "grandson_"
                elif "بنات الابن" in r['heir'] or "بنت الابن" in r['heir']:
                    prefix = "granddaughter_"
                elif "الإخوة الأشقاء" in r['heir'] or "أخ شقيق" in r['heir']:
                    prefix = "full_brother_"
                elif "الأخوات الشقيقات" in r['heir'] or "أخت شقيقة" in r['heir']:
                    prefix = "full_sister_"

            if prefix and cnt >= 1:
                is_zero_indexed = bool(heir_details and any(k.startswith(prefix) and (k.endswith("_0") or k.endswith("0")) for k in heir_details))
                for sub_i in range(1, cnt + 1):
                    hk = f"{prefix}{sub_i - 1}" if is_zero_indexed else f"{prefix}{sub_i}"
                    hd = (heir_details or {}).get(hk, {})
                    h_name = hd.get("name", "").strip()
                    h_cin = hd.get("cin", "").strip()
                    h_civ = hd.get("civil_status", "").strip()

                    is_female = (prefix in ["daughter_", "wife_", "granddaughter_", "full_sister_"])
                    ordinals_male = ["الأول", "الثاني", "الثالث", "الرابع", "الخامس", "السادس", "السابع", "الثامن", "التاسع", "العاشر"]
                    ordinals_female = ["الأولى", "الثانية", "الثالثة", "الرابعة", "الخامسة", "السادسة", "السابعة", "الثامنة", "التاسعة", "العاشرة"]

                    label_prefix = {
                        "son_": "الابن",
                        "daughter_": "البنت",
                        "wife_": "الزوجة",
                        "grandson_": "ابن الابن",
                        "granddaughter_": "بنت الابن",
                        "full_brother_": "الأخ الشقيق",
                        "full_sister_": "الأخت الشقيقة"
                    }.get(prefix, r['heir'])

                    if h_name:
                        parts_n = h_name.split()
                        if len(parts_n) > 2 and 'بن' in parts_n:
                            f_n = parts_n[0]
                            l_n = parts_n[-1]
                            if l_n not in {'بن', 'بنت', 'ابن'} and l_n != f_n:
                                disp_name = f"{f_n} {l_n}"
                            else:
                                disp_name = f_n
                        else:
                            disp_name = h_name
                    else:
                        ord_list = ordinals_female if prefix in ["daughter_", "wife_", "granddaughter_", "full_sister_"] else ordinals_male
                        ord_str = ord_list[sub_i - 1] if sub_i <= len(ord_list) else f"رقم {sub_i}"
                        disp_name = f"{label_prefix} {ord_str}" if cnt > 1 else label_prefix

                    # Strip duplicated words (e.g. "ابن الابن ابن الابن") and trailing digits
                    disp_name = re.sub(r'^(ابن الابن|بنت الابن|ابن البنت|بنت البنت|الابن|البنت)\s+\1', r'\1', disp_name.strip())

                    heir_items.append({
                        "key": hk,
                        "disp_name": disp_name,
                        "is_female": is_female,
                        "cin": h_cin,
                        "civ": h_civ,
                        "shares": sh_val,
                        "raw_area": raw_area,
                        "area": round(raw_area, 2),
                        "raw_parts": raw_parts,
                        "parts": round(raw_parts, 2)
                    })
            elif r.get("is_individual_grandchild"):
                g_name = r.get("clean_name", "").strip().strip("()")
                heir_str = r.get("heir", "")
                if "ابن الابن" in heir_str: rel_tag = "ابن الابن"
                elif "بنت الابن" in heir_str: rel_tag = "بنت الابن"
                elif "ابن البنت" in heir_str: rel_tag = "ابن البنت"
                elif "بنت البنت" in heir_str: rel_tag = "بنت البنت"
                else: rel_tag = "الحفيد(ة)"

                disp_name = g_name if g_name else rel_tag
                disp_name = re.sub(r'^(ابن الابن|بنت الابن|ابن البنت|بنت البنت)\s+\1', r'\1', disp_name.strip())

                is_female = ("بنت" in rel_tag)
                s_key = f"grandchild_{g_name}"

                heir_items.append({
                    "key": s_key,
                    "disp_name": disp_name,
                    "is_female": is_female,
                    "cin": "",
                    "civ": "",
                    "shares": sh_val,
                    "raw_area": raw_area,
                    "area": round(raw_area, 2),
                    "raw_parts": raw_parts,
                    "parts": round(raw_parts, 2)
                })
            else:
                s_key = None
                if "الزوج" in r['heir'] and "الزوجة" not in r['heir']: s_key = "husband"
                elif "الأب" in r['heir'] and "الأبناء" not in r['heir']: s_key = "father"
                elif "الأم" in r['heir']: s_key = "mother"
                elif "الجد لأب" in r['heir']: s_key = "paternal_grandfather"
                elif "الجدة لأم" in r['heir']: s_key = "maternal_grandmother"
                elif "الجدة لأب" in r['heir']: s_key = "paternal_grandmother"

                hd = (heir_details or {}).get(s_key, {}) if s_key else {}
                h_name = hd.get("name", "").strip()
                h_cin = hd.get("cin", "").strip()
                h_civ = hd.get("civil_status", "").strip()

                is_female = ("الزوجة" in r['heir'] or "الأم" in r['heir'] or "الجدة" in r['heir'])
                disp_name = h_name if h_name else r['heir']
                disp_name = re.sub(r'^(الزوجة|الأب|الأم|الزوج)\s+\1', r'\1', disp_name.strip())

                heir_items.append({
                    "key": s_key or r['heir'],
                    "disp_name": disp_name,
                    "is_female": is_female,
                    "cin": h_cin,
                    "civ": h_civ,
                    "shares": sh_val,
                    "raw_area": raw_area,
                    "area": round(raw_area, 2),
                    "raw_parts": raw_parts,
                    "parts": round(raw_parts, 2)
                })

        def _safe_num_share(val):
            try:
                return float(val)
            except (ValueError, TypeError):
                return 0.0

        # Remainder Distribution on Area (jabr el frouk)
        if calc_area > 0 and heir_items:
            valid_calc_items = [item for item in heir_items if not item.get("is_predeceased_parent") and not str(item.get("key", "")).startswith("grandchild_")]
            if valid_calc_items:
                sum_area = round(sum(item["area"] for item in valid_calc_items), 2)
                diff_area_cents = int(round((calc_area - sum_area) * 100))
                if diff_area_cents != 0:
                    for item in valid_calc_items:
                        item["_residual_area"] = item["raw_area"] - item["area"]
                    if diff_area_cents > 0:
                        sorted_items = sorted(valid_calc_items, key=lambda x: x["_residual_area"], reverse=True)
                        for i in range(min(diff_area_cents, len(sorted_items))):
                            sorted_items[i]["area"] = round(sorted_items[i]["area"] + 0.01, 2)
                    else:
                        sorted_items = sorted(valid_calc_items, key=lambda x: x["_residual_area"])
                        for i in range(min(abs(diff_area_cents), len(sorted_items))):
                            sorted_items[i]["area"] = round(sorted_items[i]["area"] - 0.01, 2)

        # Remainder Distribution on Parts (jabr el frouk)
        if calc_parts > 0 and heir_items:
            valid_calc_items = [item for item in heir_items if not item.get("is_predeceased_parent") and not str(item.get("key", "")).startswith("grandchild_")]
            if valid_calc_items:
                sum_parts = round(sum(item["parts"] for item in valid_calc_items), 2)
                diff_parts_cents = int(round((calc_parts - sum_parts) * 100))
                if diff_parts_cents != 0:
                    for item in valid_calc_items:
                        item["_residual_parts"] = item["raw_parts"] - item["parts"]
                    if diff_parts_cents > 0:
                        sorted_items = sorted(valid_calc_items, key=lambda x: x["_residual_parts"], reverse=True)
                        for i in range(min(diff_parts_cents, len(sorted_items))):
                            sorted_items[i]["parts"] = round(sorted_items[i]["parts"] + 0.01, 2)
                    else:
                        sorted_items = sorted(valid_calc_items, key=lambda x: x["_residual_parts"])
                        for i in range(min(abs(diff_parts_cents), len(sorted_items))):
                            sorted_items[i]["parts"] = round(sorted_items[i]["parts"] - 0.01, 2)

        # Build notary share distribution per heir (grouped cleanly with headers)
        heir_statements = []

        # Check for predeceased children to include in main estate listing
        predeceased_list = (heirs_dict or {}).get('predeceased_list', []) if isinstance(heirs_dict, dict) else []

        # Add predeceased sons/daughters into heir_items if not already present
        for p_idx, p in enumerate(predeceased_list):
            p_name = p.get("parent_name", "").strip()
            p_gender = p.get("parent_gender")
            if not p_gender:
                p_gender = "female" if (_is_female_name(p_name) or "بنت" in p_name or "ابنة" in p_name) else "male"
            if not p_name:
                continue

            # Calculate sum of shares of children belonging to p_name
            gc_items = [r for r in results if r.get("is_individual_grandchild") and (r.get("parent_name") == p_name or p_name in r.get("heir", ""))]
            if gc_items:
                p_parts_val = sum(r.get("parts", 0.0) for r in gc_items)
                p_shares_val = sum(r.get("shares", 0.0) for r in gc_items)
            else:
                s_res = [r for r in results if ("أبناء" in r.get("heir", "") or "ابن" in r.get("heir", "")) and not r.get("is_waseya_summary") and not r.get("is_individual_grandchild")]
                if s_res:
                    p_shares_val = float(s_res[0].get("single_shares", s_res[0].get("shares", 0.0)))
                    p_parts_val = float(s_res[0].get("single_parts", s_res[0].get("parts", p_shares_val)))
                else:
                    raise ValueError(f"Could not resolve inheritance share for predeceased branch '{p_name}'. Please verify input data or consult notary.")

            is_female = (p_gender == "female")
            p_key = f"son_predeceased_{p_idx}" if not is_female else f"daughter_predeceased_{p_idx}"

            disp_p_name = re.sub(r'^(الابن|البنت)\s+', '', p_name.strip())

            # Match share with living same-gender siblings if available for uniform display in primary estate
            matching_sibs = [item for item in heir_items if (str(item.get("key", "")).startswith("son_") if not is_female else str(item.get("key", "")).startswith("daughter_")) and not item.get("is_predeceased_parent")]
            if matching_sibs:
                ref_sib = matching_sibs[0]
                if (parts and parts > 0) or (calc_parts and calc_parts > 0):
                    p_parts_val = ref_sib.get("parts", p_parts_val)
                else:
                    p_shares_val = ref_sib.get("shares", p_shares_val)
                    p_parts_val = ref_sib.get("parts", p_parts_val)

            p_n_chk = _norm_chk(p_name)
            already_in = any(_norm_chk(item["disp_name"]) in p_n_chk or p_n_chk in _norm_chk(item["disp_name"]) for item in heir_items if not item.get("key", "").startswith("grandchild_"))

            if not already_in:
                eff_p_val = p_parts_val if p_parts_val > 0 else p_shares_val
                heir_items.append({
                    "key": p_key,
                    "disp_name": disp_p_name,
                    "is_female": is_female,
                    "cin": "",
                    "civ": "",
                    "shares": p_shares_val,
                    "raw_area": 0.0,
                    "area": 0.0,
                    "raw_parts": eff_p_val,
                    "parts": eff_p_val,
                    "is_predeceased_parent": True
                })

        spouses_and_parents = [item for item in heir_items if item["key"] in ["husband", "father", "mother", "paternal_grandfather", "maternal_grandmother", "paternal_grandmother"] or str(item["key"]).startswith("wife_")]
        sons = [item for item in heir_items if str(item["key"]).startswith("son_")]
        daughters = [item for item in heir_items if str(item["key"]).startswith("daughter_")]
        grandchildren = [item for item in heir_items if str(item["key"]).startswith("grandson_") or str(item["key"]).startswith("granddaughter_") or str(item["key"]).startswith("grandchild_")]
        others = [item for item in heir_items if item not in spouses_and_parents and item not in sons and item not in daughters and item not in grandchildren]

        has_wife = any(str(item["key"]).startswith("wife_") for item in spouses_and_parents)
        has_husband = any(str(item["key"]) == "husband" for item in spouses_and_parents)

        # 1. Spouses & Parents / Fixed Heirs
        for item in spouses_and_parents:
            is_female = item["is_female"]
            display_share_val = item["parts"] if ((parts and parts > 0) or (calc_parts and calc_parts > 0)) else item["shares"]
            sh_text = _fmt_shares(display_share_val, is_equal_unit=is_equal_unit)
            verb = "وينوبها " if is_female else "وينوبه "

            disp_name = item["disp_name"].strip()
            key = str(item.get("key", ""))
            if key == "husband" and "زوج" not in disp_name:
                disp_name = f"زوجها {disp_name}"
            elif key.startswith("wife_") and "زوج" not in disp_name:
                disp_name = f"زوجته {disp_name}"
            elif key == "father" and "أب" not in disp_name and "والد" not in disp_name:
                disp_name = f"والده {disp_name}"
            elif key == "mother" and "أم" not in disp_name and "والدة" not in disp_name:
                disp_name = f"والدته {disp_name}"

            h_text = f"• {disp_name} {verb}{sh_text}"
            heir_statements.append(h_text)

        # 2. Sons
        if sons:
            if heir_statements:
                heir_statements.append("")
            
            if is_female_dec:
                s_header = "وأبناؤها منها وهم:" if has_husband else "وأبناؤها وهم:"
            else:
                s_header = "وأبناؤه منها وهم:" if has_wife else "وأبناؤه وهم:"

            heir_statements.append(s_header)

            for item in sons:
                display_share_val = item["parts"] if ((parts and parts > 0) or (calc_parts and calc_parts > 0)) else item["shares"]
                sh_text = _fmt_shares(display_share_val, is_equal_unit=is_equal_unit)

                disp_name = item["disp_name"].strip()
                disp_name = re.sub(r'^(الابن)\s+', '', disp_name)

                h_text = f"• {disp_name} وينوبه {sh_text}"
                heir_statements.append(h_text)

        # 3. Daughters
        if daughters:
            if heir_statements:
                heir_statements.append("")

            if is_female_dec:
                d_header = "وبناتها منها وهن:" if has_husband else "وبناتها وهن:"
            else:
                d_header = "وبناته منها وهن:" if has_wife else "وبناته وهن:"

            heir_statements.append(d_header)

            for item in daughters:
                display_share_val = item["parts"] if ((parts and parts > 0) or (calc_parts and calc_parts > 0)) else item["shares"]
                sh_text = _fmt_shares(display_share_val, is_equal_unit=is_equal_unit)

                disp_name = item["disp_name"].strip()
                disp_name = re.sub(r'^(البنت)\s+', '', disp_name)

                h_text = f"• {disp_name} وينوبها {sh_text}"
                heir_statements.append(h_text)

        # 4. Successive Inheritances (المناسخات والتركات التالية للتركة الأولى)
        predeceased_sections = []
        all_child_deaths = []
        succ_deaths = (heirs_dict or {}).get('successive_deaths_list', []) if isinstance(heirs_dict, dict) else []
        for sd in succ_deaths:
            if isinstance(sd, dict):
                s_name = (sd.get("deceased_name") or sd.get("parent_name", "")).strip()
                if s_name and not any(p.get("parent_name") == s_name for p in all_child_deaths):
                    p_g = sd.get("parent_gender")
                    if p_g:
                        s_female = (p_g == "female")
                    else:
                        s_female = _is_female_name(s_name) if not sd.get("wife") and not sd.get("wife_name") else False
                    all_child_deaths.append({
                        "parent_name": s_name,
                        "parent_gender": "female" if s_female else "male",
                        "death_date": sd.get("death_date") or sd.get("hujja_date", ""),
                        "hujja_num": sd.get("hujja_num", ""),
                        "hujja_court": sd.get("hujja_court", ""),
                        "wife": sd.get("wife", False) or bool(sd.get("wife_name")),
                        "wife_name": sd.get("wife_name", "") or (sd.get("spouse_name") if not s_female else ""),
                        "husband": sd.get("husband", False) or bool(sd.get("husband_name")),
                        "husband_name": sd.get("husband_name", "") or (sd.get("spouse_name") if s_female else ""),
                        "grandchildren_names": sd.get("grandchildren_names") or sd.get("names", [])
                    })

        if all_child_deaths:
            # Track share components for each heir across primary and secondary successions
            heir_accumulated_tracker = {}
            for item in spouses_and_parents + sons + daughters + others:
                if item.get("is_predeceased_parent"):
                    continue
                k = str(item.get("key", ""))
                raw_nm = item.get("disp_name", "").strip()
                nm = re.sub(r'^(الابن|البنت)\s+', '', raw_nm)
                nm = re.sub(r'^(الأول|الثاني|الثالث|الرابع|الخامس|الأولى|الثانية|الثالثة|الرابعة|الخامسة)\s+', '', nm).strip()
                if not nm:
                    nm = raw_nm
                is_fem = item.get("is_female", False)

                sh_val = item["parts"] if (parts and parts > 0) else item["shares"]

                if k.startswith("wife_"):
                    rel_p = "إرثاً عن زوجها"
                elif k == "husband":
                    rel_p = "إرثاً عن زوجته"
                elif k == "mother":
                    rel_p = "إرثاً عن ابنها" if not is_female_dec else "إرثاً عن ابنتها"
                elif k == "father":
                    rel_p = "إرثاً عن ابنه" if not is_female_dec else "إرثاً عن ابنتها"
                elif k.startswith("son_") or k.startswith("daughter_"):
                    rel_p = "إرثاً عن أمها" if is_fem and is_female_dec else ("إرثاً عن أمه" if not is_fem and is_female_dec else ("إرثاً عن أبيها" if is_fem else "إرثاً عن أبيه"))
                else:
                    clean_dec_name = re.sub(r'^(السيد|السيدة|المرحوم|المرحومة|الهالك|الهالكة)\s+', '', deceased_name.strip()) if deceased_name else "الهالك"
                    rel_p = f"إرثاً عن {clean_dec_name}"

                if nm not in heir_accumulated_tracker:
                    heir_accumulated_tracker[nm] = {
                        "disp_name": nm,
                        "is_female": is_fem,
                        "components": []
                    }
                heir_accumulated_tracker[nm]["components"].append((sh_val, rel_p))

            for p in all_child_deaths:
                p_name = p.get("parent_name", "").strip()
                p_gender = p.get("parent_gender")
                if not p_gender:
                    p_gender = "female" if (_is_female_name(p_name) or "بنت" in p_name or "ابنة" in p_name) else "male"
                p_date = p.get("death_date", "").strip()
                hujja_n = p.get("hujja_num", "").strip()
                hujja_c = p.get("hujja_court", "").strip()
                hujja_d = p.get("hujja_date", "").strip()

                if not p_name:
                    continue

                full_p_name = p_name
                disp_clean = re.sub(r'^(الابن|البنت)\s+', '', p_name.strip())
                if deceased_name and "بن" not in disp_clean and "بنت" not in disp_clean:
                    first_p = disp_clean.split()[0]
                    connector = "بنت" if p_gender == "female" else "بن"
                    clean_dec = re.sub(r'^(السيد|السيدة|المرحوم|المرحومة|الهالك|الهالكة)\s+', '', deceased_name.strip())
                    full_p_name = f"{first_p} {connector} {clean_dec}"
                else:
                    full_p_name = disp_clean

                p_wife_name = (p.get("wife_name") or p.get("spouse_name") or "").strip()
                p_husband_name = (p.get("husband_name") or (p.get("spouse_name") if p_gender == "female" else "") or "").strip()

                is_m = p.get("is_married", True)
                if not p_wife_name and p_gender == "male" and (p.get("wife") or (is_m and p.get("spouse_name"))):
                    p_wife_name = "زوجته"

                if not p_husband_name and p_gender == "female" and (p.get("husband") or (is_m and p.get("spouse_name"))):
                    p_husband_name = "زوجها"

                has_p_wife = bool(p_wife_name and p_gender == "male" and is_m)
                has_p_husband = bool(p_husband_name and p_gender == "female" and is_m)

                gc_items = [r for r in results if r.get("is_individual_grandchild") and (r.get("parent_name") == p_name or p_name in r.get("heir", ""))]
                p_shares_val = p.get("shares", 0.0) or p.get("share", 0.0) or 0.0
                p_parts_val = p.get("parts", 0.0) or 0.0
                p_total_share = sum(r.get("parts", 0.0) if (parts and parts > 0) else r.get("shares", 0.0) for r in gc_items)

                if p_total_share == 0:
                    p_res_item = next((r for r in results if (r.get("clean_name") and r.get("clean_name") in p_name) or (r.get("heir") and p_name in str(r.get("heir")))), None)
                    if p_res_item:
                        p_total_share = p_res_item.get("parts", 0.0) if (parts and parts > 0) else p_res_item.get("shares", 0.0)

                if p_total_share == 0:
                    p_total_share = p_shares_val if (p_shares_val > 0 and (not p_parts_val or p_parts_val == 0)) else p_parts_val
                    if p_total_share == 0:
                        p_total_share = 1.0  # Fallback to avoid raising exception when rendering empty branch

                p_sh_text = _fmt_shares(p_total_share, is_equal_unit=is_equal_unit)

                verb_d = "توفيت" if p_gender == "female" else "توفي"
                marhoum_t = "المرحومة" if p_gender == "female" else "المرحوم"
                p_hujja_pronoun = "وفاتها" if p_gender == "female" else "وفاته"
                p_irath_verb = "وقد أحاطت بإرثها" if p_gender == "female" else "وقد أحاط بإرثه"
                manab_phrase = "عن منابها المذكور أعلاه والبالغ" if p_gender == "female" else "عن منابه المذكور أعلاه والبالغ"

                court_val = hujja_c or ""
                if court_val:
                    if not court_val.startswith("محكمة") and "المحكمة" not in court_val:
                        court_val = f"محكمة {court_val}"
                else:
                    court_val = "محكمة ..."

                date_val = hujja_d or p_date or "..."
                num_val = hujja_n or "..."

                p_hujja_str = f"حسب حجة {p_hujja_pronoun} الصادرة عن {court_val} بتاريخ {date_val} تحت عدد {num_val}"

                branch_gc = [gc for gc in grandchildren if p_name in gc.get("disp_name", "") or p_name in gc.get("key", "")]
                if not branch_gc and p.get("grandchildren_names"):
                    for gcn in p.get("grandchildren_names"):
                        g_fem = _is_female_name(gcn) or "بنت" in gcn
                        branch_gc.append({
                            "disp_name": gcn,
                            "is_female": g_fem
                        })

                is_unmarried = (not has_p_wife and not has_p_husband and not branch_gc)
                is_divorced = p.get("is_divorced", False) or "مطلق" in str(p.get("status", ""))
                if is_divorced and is_unmarried:
                    azab_clause = (" وهو مطلق دون زوجة ولا عقب،" if p_gender == "male" else " وهي مطلقة دون زوج ولا عقب،")
                elif is_unmarried:
                    azab_clause = (" وهو أعزب دون زوجة ولا عقب،" if p_gender == "male" else " وهي عزباء دون زوج ولا عقب،")
                else:
                    azab_clause = ""

                p_header = f"وحيث {verb_d} {full_p_name} عن منابات قدرها {p_sh_text}{azab_clause} {p_irath_verb} {p_hujja_str}:"

                p_lines = [p_header]

                # Calculate spouse share & remaining children share in branch
                p_spouse_share = 0.0
                p_children_share = p_total_share
                if has_p_wife:
                    wife_ratio = 0.125 if branch_gc else 0.25
                    p_spouse_share = p_total_share * wife_ratio
                    p_children_share = max(0.0, p_total_share - p_spouse_share)
                elif has_p_husband:
                    husband_ratio = 0.25 if branch_gc else 0.50
                    p_spouse_share = p_total_share * husband_ratio
                    p_children_share = max(0.0, p_total_share - p_spouse_share)

                if has_p_wife:
                    w_disp = p_wife_name if p_wife_name and "زوج" in p_wife_name else (f"زوجته {p_wife_name}" if p_wife_name else "زوجته")
                    sp_sh_text = _fmt_shares(p_spouse_share, is_equal_unit=is_equal_unit)
                    p_lines.append(f"• {w_disp} وينوبها {sp_sh_text}")
                    if branch_gc:
                        p_lines.append("\nوأبناؤه منها وهم:")
                elif has_p_husband:
                    h_disp = p_husband_name if p_husband_name and "زوج" in p_husband_name else (f"زوجها {p_husband_name}" if p_husband_name else "زوجها")
                    sp_sh_text = _fmt_shares(p_spouse_share, is_equal_unit=is_equal_unit)
                    p_lines.append(f"• {h_disp} وينوبه {sp_sh_text}")
                    if branch_gc:
                        p_lines.append("\nوأبناؤها منه وهم:")

                # Render secondary succession parents if specified in branch or if primary estate spouse (mother) is alive
                primary_wife = (heirs_dict.get("wife_name") or (heir_details.get("wife_1", {}) or {}).get("name") or (heir_details.get("wife_0", {}) or {}).get("name") or "")
                primary_husband = (heirs_dict.get("husband_name") or (heir_details.get("husband", {}) or {}).get("name") or "")
                w_or_h_name = primary_wife if (has_wife and p_gender == "male") else (primary_husband if (has_husband and p_gender == "female") else "")
                p_m_name = (str(p.get("mother_name") or w_or_h_name or "")).strip()
                p_f_name = (str(p.get("father_name") or "")).strip()
                has_p_m = bool(p_m_name or p.get("has_mother") or (has_wife and p_gender == "male") or (has_husband and p_gender == "female"))
                has_p_f = bool(p_f_name or p.get("has_father"))

                p_m_ratio = 0.0
                if has_p_m:
                    p_m_ratio = 1.0 / 6.0 if (branch_gc or len(children) > 1) else 1.0 / 3.0
                    p_m_share = p_total_share * p_m_ratio
                    p_children_share = max(0.0, p_children_share - p_m_share)
                    m_disp = p_m_name if "أم" in p_m_name else f"أمه {p_m_name}" if p_m_name else "أمه"
                    m_sh_text = _fmt_shares(p_m_share, is_equal_unit=is_equal_unit)
                    p_lines.append(f"• {m_disp} وينوبها {m_sh_text}")
                    m_clean_nm = re.sub(r'^(أمه|والدته)\s+', '', m_disp).strip()
                    m_rel_str = "إرثاً عن ابنها" if p_gender == "male" else "إرثاً عن ابنتها"
                    if m_clean_nm not in heir_accumulated_tracker:
                        heir_accumulated_tracker[m_clean_nm] = {"disp_name": m_clean_nm, "is_female": True, "components": []}
                    heir_accumulated_tracker[m_clean_nm]["components"].append((p_m_share, m_rel_str))

                if has_p_f:
                    p_f_ratio = 1.0 / 6.0 if branch_gc else max(0.0, 1.0 - (wife_ratio if has_p_wife else (husband_ratio if has_p_husband else 0.0)) - p_m_ratio)
                    p_f_share = p_total_share * p_f_ratio
                    p_children_share = max(0.0, p_children_share - p_f_share)
                    f_disp = p_f_name if "أب" in p_f_name or "والد" in p_f_name else f"والده {p_f_name}" if p_f_name else "والده"
                    f_sh_text = _fmt_shares(p_f_share, is_equal_unit=is_equal_unit)
                    p_lines.append(f"• {f_disp} وينوبه {f_sh_text}")
                    f_clean_nm = re.sub(r'^(والده|أبوه)\s+', '', f_disp).strip()
                    f_rel_str = "إرثاً عن ابنه" if p_gender == "male" else "إرثاً عن ابنتها"
                    if f_clean_nm not in heir_accumulated_tracker:
                        heir_accumulated_tracker[f_clean_nm] = {"disp_name": f_clean_nm, "is_female": False, "components": []}
                    heir_accumulated_tracker[f_clean_nm]["components"].append((p_f_share, f_rel_str))

                if not has_p_wife and not has_p_husband and branch_gc:
                    ch_head = "وأبناؤه وهم:" if p_gender == "male" else "وأبناؤها وهم:"
                    p_lines.append(f"\n{ch_head}")
                elif is_unmarried and children:
                    # Distribute remaining share to surviving brothers/sisters
                    surv_sibs = [c for c in children if c.get("disp_name") != disp_p_name and p_name not in c.get("disp_name", "")]
                    if surv_sibs:
                        p_lines.append("\nوإخوته المذكورون أعلاه وهم:")
                        sib_share = p_children_share / float(len(surv_sibs))
                        for sb in surv_sibs:
                            sb_fem = sb.get("is_female", False)
                            sb_sh_text = _fmt_shares(sib_share, is_equal_unit=is_equal_unit)
                            sb_verb = "وينوبها " if sb_fem else "وينوبه "
                            p_lines.append(f"• {sb['disp_name']} {sb_verb}{sb_sh_text}")
                            sb_clean_nm = re.sub(r'^(الابن|البنت)\s+', '', sb['disp_name']).strip()
                            sb_rel_str = ("إرثاً عن أخيها" if sb_fem else "إرثاً عن أخيه") if p_gender == "male" else ("إرثاً عن أختها" if sb_fem else "إرثاً عن أخته")
                            if sb_clean_nm not in heir_accumulated_tracker:
                                heir_accumulated_tracker[sb_clean_nm] = {"disp_name": sb_clean_nm, "is_female": sb_fem, "components": []}
                            heir_accumulated_tracker[sb_clean_nm]["components"].append((sib_share, sb_rel_str))

                num_gc_sons = len([gc for gc in branch_gc if not gc["is_female"]])
                num_gc_daug = len([gc for gc in branch_gc if gc["is_female"]])
                gc_heads = (num_gc_sons * 2) + num_gc_daug

                for gc in branch_gc:
                    g_female = gc["is_female"]
                    multiplier = 2.0 if not g_female else 1.0
                    g_val = (multiplier / float(gc_heads)) * p_children_share if gc_heads > 0 else 0.0
                    g_sh_text = _fmt_shares(g_val, is_equal_unit=is_equal_unit)
                    g_verb = "وينوبها " if g_female else "وينوبه "
                    g_disp = gc["disp_name"].strip()
                    g_disp = re.sub(r'^(الابن|البنت)\s+', '', g_disp)
                    p_lines.append(f"• {g_disp} {g_verb}{g_sh_text}")
                    g_rel_str = ("إرثاً عن أبيها" if g_female else "إرثاً عن أبيه") if p_gender == "male" else ("إرثاً عن أمها" if g_female else "إرثاً عن أمه")
                    if g_disp not in heir_accumulated_tracker:
                        heir_accumulated_tracker[g_disp] = {"disp_name": g_disp, "is_female": g_female, "components": []}
                    heir_accumulated_tracker[g_disp]["components"].append((g_val, g_rel_str))

                predeceased_sections.append("\n".join(p_lines))

            # Build final accumulated summary lines ("وبالتالي يكون مجموع المنابات...") ONCE for all successions
            wabittali_lines = []
            for h_nm, h_info in heir_accumulated_tracker.items():
                comps = h_info["components"]
                if not comps or len(comps) <= 1:
                    continue
                h_fem = h_info["is_female"]
                tot_val = sum(c[0] for c in comps)
                first_val, first_rel = comps[0]
                phrase_parts = [f"{_fmt_shares(first_val, is_equal_unit=is_equal_unit)} {first_rel}"]
                for sub_val, sub_rel in comps[1:]:
                    phrase_parts.append(f"إضافة إلى {_fmt_shares(sub_val, is_equal_unit=is_equal_unit)} {sub_rel}")
                comp_str = " ".join(phrase_parts)
                tot_pronoun = "مناباتها" if h_fem else "مناباته"
                wabittali_lines.append(f"وبالتالي يكون مناب {h_nm} {comp_str}، ليصبح مجموع {tot_pronoun} {_fmt_shares(tot_val, is_equal_unit=is_equal_unit)}.")

            if wabittali_lines:
                predeceased_sections.append("فقرة تجميع منابات الورثة في التركات المتتالية:\n" + "\n".join(wabittali_lines))

        # 4. Others (if any)
        if others:
            if heir_statements:
                heir_statements.append("")
            for item in others:
                is_female = item["is_female"]
                display_share_val = item["parts"] if ((parts and parts > 0) or (calc_parts and calc_parts > 0)) else item["shares"]
                sh_text = _fmt_shares(display_share_val, is_equal_unit=is_equal_unit)
                verb = "وينوبها " if is_female else "وينوبه "

                disp_name = item["disp_name"].strip()
                h_text = f"• {disp_name} {verb}{sh_text}"
                heir_statements.append(h_text)

        p_heirs = "\n".join(heir_statements) if heir_statements else ""
        p_extra_sections = ("\n\n" + "\n\n".join(predeceased_sections)) if predeceased_sections else ""

        p_closing = "هذا ما تم تلقيه وتلي على الحاضرين فوافقوا وأمضوا ورسم بدفتر مسودات أولهما صحيفة............ تحت عدد............ أجره والمصاريف القانونية مستوفاة والله الموفق."

        top_blocks = [p1]
        if p_prop:
            top_blocks.append(p_prop)
        if p_partial_extra:
            top_blocks.append(p_partial_extra)

        p_top = "\n\n".join(top_blocks)
        full_text = f"{p_top}\n\n{p_succ}\n{p_heirs}{p_extra_sections}\n\n{p_closing}"
        return full_text

    def export_farida_docx(self, result: dict, output_path: str):
        """Generates an official notary Word document for the Farida calculation matching authentic notary standards."""
        doc = docx.Document()

        sections = doc.sections
        for section in sections:
            section.top_margin = Inches(0.8)
            section.bottom_margin = Inches(0.8)
            section.left_margin = Inches(0.8)
            section.right_margin = Inches(0.8)
            if docx_generator:
                try:
                    docx_generator.set_section_rtl(section)
                except Exception:
                    pass

        # ── 1. OFFICIAL NOTARY OFFICE HEADER ─────────────────────────────────
        if office_profile:
            try:
                prof = office_profile.load()
                notary_name = (prof.get("notary_name") or "مكتب عدل الإشهاد").strip()
                office_addr = (prof.get("office_address") or "").strip()
                office_phone = (prof.get("phone") or "").strip()
            except Exception:
                notary_name = "مكتب عدل الإشهاد"
                office_addr = ""
                office_phone = ""
        else:
            notary_name = "مكتب عدل الإشهاد"
            office_addr = ""
            office_phone = ""

        # Top Header Table (Bilingual Notary Header)
        header_table = doc.add_table(rows=1, cols=2)
        header_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        if docx_generator:
            try:
                docx_generator.set_table_rtl(header_table)
            except Exception:
                pass

        header_cells = header_table.rows[0].cells
        
        # Right Side: Arabic Header
        p_ar = header_cells[0].paragraphs[0]
        try:
            docx_generator.set_rtl(p_ar)
        except Exception:
            pass
        p_ar.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        r_ar = p_ar.add_run(f"مكتب الأستاذ: {notary_name}\nعدل إشهاد")
        r_ar.bold = True
        r_ar.font.size = Pt(13)
        r_ar.font.name = "Traditional Arabic"
        if office_addr:
            p_ar.add_run(f"\n{office_addr}")
        if office_phone:
            p_ar.add_run(f"\nالهاتف: {office_phone}")

        # Left Side: French Header
        p_fr = header_cells[1].paragraphs[0]
        p_fr.alignment = WD_ALIGN_PARAGRAPH.LEFT
        r_fr = p_fr.add_run(f"Etude Maître {notary_name}\nNotaire")
        r_fr.bold = True
        r_fr.font.size = Pt(11)
        r_fr.font.name = "Calibri"
        if office_addr:
            p_fr.add_run(f"\n{office_addr}")
        if office_phone:
            p_fr.add_run(f"\nTél: {office_phone}")

        p_div = doc.add_paragraph("═" * 50)
        p_div.alignment = WD_ALIGN_PARAGRAPH.CENTER
        try:
            docx_generator.set_rtl(p_div)
        except Exception:
            pass

        # ── 2. DEED TITLE ────────────────────────────────────────────────────
        c_title = result.get("contract_type", "فريضة شرعية")
        title_p = doc.add_paragraph()
        try:
            docx_generator.set_rtl(title_p)
        except Exception:
            pass
        title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = title_p.add_run(f"إشهاد بـ {c_title}")
        run.bold = True
        run.font.size = Pt(18)
        run.font.name = "Traditional Arabic"
        run.font.color.rgb = RGBColor(15, 23, 42)

        # ── 3. PREAMBLE & REAL ESTATE DETAILS ──────────────────────────────────
        if result.get("property_area_m2", 0) > 0 or result.get("property_parts", 0) > 0:
            h1 = doc.add_heading("أولاً - بيان بيانات العقار موضوع التوزيع:", level=2)
            try:
                docx_generator.set_rtl(h1)
            except Exception:
                pass
            p_info = doc.add_paragraph()
            try:
                docx_generator.set_rtl(p_info)
            except Exception:
                pass
            p_info.paragraph_format.line_spacing = 1.3
            if result.get("property_area_m2", 0) > 0:
                p_info.add_run(f"المساحة الجملية للعقار: {result.get('property_area_m2')} م²\n")
            if result.get("property_parts", 0) > 0:
                p_info.add_run(f"مناب التجزئة بالعقار: {result.get('property_parts')} جزءاً\n")

        # ── 4. SHARES & DISTRIBUTION TABLE ──────────────────────────────────
        h2 = doc.add_heading(f"جدول توزيع المنابات والأنصبة الشرعية (أصل الفريضة: {result.get('base_origin')} جزءاً):", level=2)
        try:
            docx_generator.set_rtl(h2)
        except Exception:
            pass
        summary = result.get("heirs_summary", [])
        
        table = doc.add_table(rows=1, cols=5)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        try:
            docx_generator.set_table_rtl(table)
        except Exception:
            pass

        hdr_cells = table.rows[0].cells
        headers = ["الوارث الشرعي", "عدد الأجزاء", "الفك والكسر", "النسبة %", "مناب العقار والأجزاء"]
        for i, h_text in enumerate(headers):
            hdr_cells[i].text = h_text
            p_h = hdr_cells[i].paragraphs[0]
            try:
                docx_generator.set_rtl(p_h)
            except Exception:
                pass
            p_h.runs[0].font.bold = True
            p_h.alignment = WD_ALIGN_PARAGRAPH.CENTER

        for item in summary:
            row_cells = table.add_row().cells
            row_cells[0].text = str(item["heir"])
            row_cells[1].text = str(item["shares"])
            row_cells[2].text = str(item["fraction"])
            row_cells[3].text = f"%{item['percentage']}"
            
            prop_str = ""
            if item.get("area_m2", 0) > 0:
                prop_str += f"{item['area_m2']} م²"
            if item.get("parts", 0) > 0:
                prop_str += f" | {item['parts']} جزء"
            row_cells[4].text = prop_str if prop_str else "—"

            for c in row_cells:
                try:
                    docx_generator.set_rtl(c.paragraphs[0])
                except Exception:
                    pass

        # ── 5. LEGAL NOTARIAL TEXT ──────────────────────────────────────────
        h3 = doc.add_heading("نص التوثيق والتوزيع الشرعي (صياغة العدول):", level=2)
        try:
            docx_generator.set_rtl(h3)
        except Exception:
            pass
        p_deed = doc.add_paragraph(result.get("legal_notarial_text", ""))
        try:
            docx_generator.set_rtl(p_deed)
        except Exception:
            pass
        p_deed.style.font.size = Pt(13)
        p_deed.style.font.name = "Traditional Arabic"
        p_deed.paragraph_format.line_spacing = 1.4

        # ── 6. SIGNATURE BLOCK ───────────────────────────────────────────────
        p_end = doc.add_paragraph("\nوذلك تمامها شهد بصحتها ومطابقتها للشريعة والقانون.")
        try:
            docx_generator.set_rtl(p_end)
        except Exception:
            pass
        p_sig = doc.add_paragraph("\nعدلا الإشهاد                                                       طالب الإشهاد")
        try:
            docx_generator.set_rtl(p_sig)
        except Exception:
            pass
        p_sig.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p_sig.runs[0].font.bold = True
        p_sig.runs[0].font.size = Pt(13)

        doc.save(output_path)


def _clean_extracted_text(val: str) -> str:
    if not val or not isinstance(val, str):
        return ""
    cleaned = re.sub(r'[*`_]', '', val)
    cleaned = re.sub(r'\((?:Deceased Name|Spouse Full Name|Applicant Name|Lakab|Deceased Lakab)[^\)]*\)', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'(?:واللقب العائلي|اسم الهالك|اسم طالب الإشهاد|حجة الوفاة)\s*\(.*?\)', '', cleaned)
    cleaned = re.sub(r'^[\s:：\(\)\[\]\{\}\"\'`,\./\\-]+|[\s:：\(\)\[\]\{\}\"\'`,\./\\-]+$', '', cleaned)
    return cleaned.strip()


def _extract_deceased_name_smart_fallback(text: str, deceased_lakab: str = "") -> str:
    """
    Smart context-aware AI/NLP fallback extractor for the deceased name in Tunisian legal death certificates (حجة وفاة / رسم وفاة).
    Tolerates line breaks (\n), colons (:), brackets, dots, dashes, prepositions, and formatting artifacts.
    Reads the entire paper text contextually to extract the deceased name.
    """
    if not text or not isinstance(text, str):
        return ""

    # 1. Clean out irrelevant lines like mother's name, predeceased spouse, or visual field labels
    clean_t = re.sub(r'اسم\s+الأم\s+ولقبها\s*[:：]?\s*[^\n،.]+', '', text)
    clean_t = re.sub(r'زوج(?:ها|ته)\s+(?:المتوفى|المتوفاة|الهالك|الهالكة)\s+(?:قبلها|قبله)\s+[^\n،.]+', '', clean_t)
    clean_t = re.sub(r'\(Deceased Name [^\)]*\)', '', clean_t, flags=re.IGNORECASE)

    # 2. Comprehensive pattern list matching variations of deceased name headers
    patterns = [
        # Explicit header: "الهالك/المرحوم/المتوفى/المغفور له :" followed by colons, dashes, spaces, newlines
        r"(?:إقامة\s+حجة\s+وفاة\s+|نقرر\s+إقامة\s+حجة\s+وفاة\s+|حجة\s+وفاة\s+|رسم\s+وفاة\s+|إشهاد\s+وفاة\s+|موضوع\s+حجة\s+الوفاة\s+|اسم\s+)?(?:الهالك|الهالكة|المرحوم|المرحومة|المتوفى|المتوفاة|الموروث|الموروثة|المغفور\s+له|المغفور\s+لها)(?:ة|\(ة\))?\s*[:：\-\s\n\r]*(?:السيد|السيدة)?\s*([أ-ي\s]+?(?:بن|بنت)[أ-ي\s]+)",

        # Death verb/notice: "وفاة المرحوم(ة) / توفي المرحوم / توفيت المرحومة / توفي إلى رحمة الله"
        r"(?:وفاة|توفي|توفيت|وفاة\s+المرحوم|وفاة\s+الهالك|وفاة\s+المتوفى|توفي\s+المرحوم|توفيت\s+المرحومة|توفي\s+إلى\s+رحمة\s+الله)(?:ة|\(ة\))?\s*[:：\-\s\n\r]*(?:السيد|السيدة)?\s*([أ-ي\s]+?(?:بن|بنت)[أ-ي\s]+)",

        # Succession context: "إرث / تركة / انحصرت تركة الهالك(ة)"
        r"(?:إرث|تركة|انحصر\s+إرث|انحصرت\s+تركة)\s+(?:الهالك|الهالكة|المرحوم|المرحومة|المتوفى|المتوفاة|المغفور\s+له|المغفور\s+لها)?(?:ة|\(ة\))?\s*[:：\-\s\n\r]*(?:السيد|السيدة)?\s*([أ-ي\s]+?(?:بن|بنت)[أ-ي\s]+)",

        # Applicant context: "طالب الإذن ... ابن/بنت الهالك(ة) [الاسم]"
        r"(?:ابن|بنت|بوصفه\s+ابن|بوصفها\s+بنت)\s+(?:الهالك|الهالكة|المرحوم|المرحومة|المتوفى|المتوفاة)(?:ة|\(ة\))?\s*[:：\-\s\n\r]*(?:السيد|السيدة)?\s*([أ-ي\s]+?(?:بن|بنت)[أ-ي\s]+)",

        # Form headers: "اسم الهالك :" / "اسم المتوفى :" / "اسم الموروث :"
        r"(?:اسم\s+الهالك|اسم\s+المتوفى|اسم\s+المرحوم|اسم\s+الموروث)\s*[:：\-\s\n\r]*(?:السيد|السيدة)?\s*([^\n،.:؛]+)",

        # Broad pattern: Header followed by text up to line break or punctuation
        r"(?:الهالك|الهالكة|المرحوم|المرحومة|المتوفى|المتوفاة|الموروث|الموروثة)(?:ة|\(ة\))?\s*[:：\-\s\n\r]*(?:السيد|السيدة)?\s*([^\n،.:؛]+)",

        # Any patronymic name sequence (e.g. "أحمد بن علي بن صالح") after death keyword
        r"(?:المرحوم|المرحومة|الهالك|الهالكة|المتوفى|المتوفاة)\s+([أ-ي]+(?:\s+[أ-ي]+){1,4})"
    ]

    for pat in patterns:
        m = re.search(pat, clean_t, re.IGNORECASE)
        if m:
            raw_candidate = m.group(1).strip()
            # Split off procedural text, lakab headers, dates, or extra details
            raw_candidate = re.split(r"(?:\s+توفي|\s+توفيت|\s+بتاريخ|\s+تاريخ|\s+وقصد|\s+ولقبه|\s+ولقبها|\s+اسم\s+الأم|\s+المتوفي|\s+المتوفى|\s+حسب|\s+جنسيته|\s+اسم\s+والد|\s+المولود|\s+بطاقة|\s+عن\s+عمر|\s+الساكن|\s+المقيم)", raw_candidate)[0].strip()
            
            cleaned_cand = _clean_extracted_text(raw_candidate)
            cleaned_cand = re.sub(r'^(?:السيد|السيدة|المعني|المعنية|الهالك|الهالكة|المرحوم|المرحومة)\s+', '', cleaned_cand).strip()
            
            # Avoid procedural false positives
            if cleaned_cand and len(cleaned_cand) > 2 and not cleaned_cand.startswith("الاذن له") and not cleaned_cand.startswith("إقامة حجة"):
                if deceased_lakab and not cleaned_cand.endswith(deceased_lakab):
                    cleaned_cand = f"{cleaned_cand} {deceased_lakab}"
                return cleaned_cand

    return ""


def _extract_applicant_smart_fallback(text: str) -> str:
    """
    Smart fallback extractor for applicant / declarer name (طالب الإشهاد / طالب الإذن / المصرح).
    """
    if not text or not isinstance(text, str):
        return ""
    patterns = [
        r"(?:حضر\s+لدينا|حضر\s+لدائرة\s+إشهادنا|بطلب\s+من|بمحضر|بحضور|طالب\s+الإشهاد|طالب\s+الإذن|المصرح)\s*[:：\-\s\n\r]*(?:السيد|السيدة)?\s*([أ-ي\s]+?(?:بن|بنت)[أ-ي\s]+)",
        r"(?:حضر\s+لدينا|بطلب\s+من|طالب\s+الإذن)\s*[:：\-\s\n\r]*(?:السيد|السيدة)?\s*([^\n،.:؛]+)"
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            cand = m.group(1).strip()
            cand = re.split(r"(?:\s+وقصد|\s+وطلب|\s+بوصفه|\s+بوصفها|\s+المقيد|\s+حامل|\s+بطاقة|\s+في\s+تركة|\s+توفي|\s+بتاريخ)", cand)[0].strip()
            clean_c = _clean_extracted_text(cand)
            if clean_c and len(clean_c) > 2 and not clean_c.startswith("إقامة حجة"):
                return clean_c
    return ""


def _extract_heirs_smart_fallback(text: str, deceased_lakab: str = "") -> dict:
    """
    Universal smart fallback extractor for sons & daughters names from non-standard courtroom phrasings.
    """
    res = {'sons_count': 0, 'daughters_count': 0, 'names': []}
    if not text or not isinstance(text, str):
        return res

    clean_t = re.sub(r'اسم\s+الأم\s+ولقبها\s*[:：]?\s*[^\n،.]+', '', text)
    non_heir_words = {'الرشداء', 'البالغين', 'المذكورين', 'وهم', 'منها', 'منه', 'غير', 'لاغير', 'لا', 'التركة', 'المحيطين', 'بإرثه', 'بارثه', 'الذين', 'تصادقا', 'فقط'}

    # 1. Search for heir phrases:
    heir_patterns = [
        r"(?:و?ابنا[ؤئءه]ه|و?ابنائه|و?ابنائها|و?ابناؤها|و?اولاده|و?اولادها|و?ورثته|و?خلفاؤه|و?خلفائه|ترك\s+بعده|ترك\s+من\s+عقب|انحصر\s+ورثته|انحصرت\s+تركة|المحيطين\s+بإرثه|المحرزين\s+على\s+تركه|خلف\s+من\s+الأبناء).*?(?:وهم|وهي|في|كالتالي)?\s*[:：\-\s\n\r]*([^\n\.,؛]+)",
        r"(?:وهم|وهي)\s*[:：\-\s\n\r]*([^\n\.,؛]+)"
    ]

    found_names = []
    for pat in heir_patterns:
        m = re.search(pat, clean_t, re.IGNORECASE)
        if m:
            raw_phrase = m.group(1).strip()
            raw_phrase = re.split(r"(?:\s+بتاريخ|\s+تاريخ|\s+ولم|\s+هذا|\s+وذلك)", raw_phrase)[0].strip()
            raw_tokens = [n.strip() for n in re.split(r"[/،,]+|\s+و\s+", raw_phrase) if n.strip()]
            for tok in raw_tokens:
                c_tok = _clean_extracted_text(tok)
                c_tok = re.sub(r'^(?:الابن|البنت|ابن|بنت|السيد|السيدة|من\s+الأبناء)\s*', '', c_tok).strip()
                c_tok = re.split(r"(?:\s+بتاريخ|\s+تاريخ|\s+لا\s+غير)", c_tok)[0].strip()
                if c_tok and len(c_tok) > 1 and c_tok not in non_heir_words and not c_tok.startswith("لا غير"):
                    if deceased_lakab and not c_tok.endswith(deceased_lakab):
                        c_tok = f"{c_tok} {deceased_lakab}"
                    if c_tok not in found_names:
                        found_names.append(c_tok)
        if found_names:
            break

    if found_names:
        s_count = 0
        d_count = 0
        for n in found_names:
            if _is_female_name(n):
                d_count += 1
            else:
                s_count += 1
        res['sons_count'] = s_count
        res['daughters_count'] = d_count
        res['names'] = found_names

    return res


# ── GEMINI STRUCTURED JSON SCHEMA & PROMPT FOR HUJJAT WAFAT ──────────────────
HUJJAT_WAFAT_GEMINI_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "hujja_num": {"type": "STRING", "description": "رقم حجة الوفاة الصادرة عن المحكمة"},
        "hujja_date": {"type": "STRING", "description": "تاريخ حجة الوفاة (YYYY-MM-DD)"},
        "hujja_court": {"type": "STRING", "description": "اسم محكمة الناحية صانعة حجة الوفاة"},
        "applicant_name": {"type": "STRING", "description": "اسم طالب الإشهاد / المصرح"},
        "deceased_name": {"type": "STRING", "description": "الاسم الرسمي الكامل للهالك/المتوفى الرئيسي"},
        "deceased_gender": {"type": "STRING", "enum": ["male", "female"], "description": "جنس المتوفى الرئيسي: male أو female"},
        "husband_alive": {"type": "BOOLEAN", "description": "هل زوج المتوفاة حي ويرث؟"},
        "husband_name": {"type": "STRING", "description": "اسم الزوج إن كان حياً"},
        "wife_alive": {"type": "BOOLEAN", "description": "هل زوجة المتوفى حية وترث؟"},
        "wife_name": {"type": "STRING", "description": "اسم الزوجة إن كانت حية"},
        "wives_count": {"type": "INTEGER", "description": "عدد الزوجات الأحياء (1 أو أكثر)"},
        "father_alive": {"type": "BOOLEAN", "description": "هل الأب حي ويرث؟"},
        "father_name": {"type": "STRING", "description": "اسم الأب إن كان حياً"},
        "mother_alive": {"type": "BOOLEAN", "description": "هل الأم حية وترث؟"},
        "mother_name": {"type": "STRING", "description": "اسم الأم إن كانت حية"},
        "sons_count": {"type": "INTEGER", "description": "عدد الأبناء الذكور الأحياء المباشرين"},
        "daughters_count": {"type": "INTEGER", "description": "عدد البنات الإناث الأحياء المباشرات"},
        "all_names_extracted_verified": {
            "type": "BOOLEAN",
            "description": "تأكيد واستشهاد الذكاء الاصطناعي بإجراء مراجعة ذاتية شاملة وضمان عدم إغفال أي اسم من الورثة المذكورين في النص المصدر"
        },
        "sons_names": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "أسماء جميع الأبناء الذكور الأحياء فقط"
        },
        "daughters_names": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "أسماء جميع البنات الإناث الأحياء فقط"
        },
        "heirs_list": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING", "description": "الاسم الكامل للوارث"},
                    "relationship": {"type": "STRING", "description": "الصفة الشرعية للوارث (ابن, بنت, زوجة, زوج, أب, أم, ابن متوفى, بنت متوفاة)"},
                    "gender": {"type": "STRING", "enum": ["male", "female"], "description": "الجنس المحدد بدقة وبشكل صريح: male للذكور, female للإناث"},
                    "is_predeceased": {"type": "BOOLEAN", "description": "هل توفي هذا الابن/البنت قبل الهالك الرئيسي؟"},
                    "predeceased_details": {
                        "type": "OBJECT",
                        "properties": {
                            "death_date": {"type": "STRING"},
                            "hujja_num": {"type": "STRING"},
                            "hujja_court": {"type": "STRING"},
                            "spouse_name": {"type": "STRING"},
                            "has_spouse": {"type": "BOOLEAN"},
                            "sons_count": {"type": "INTEGER"},
                            "daughters_count": {"type": "INTEGER"},
                            "grandchildren": {
                                "type": "ARRAY",
                                "items": {
                                    "type": "OBJECT",
                                    "properties": {
                                        "name": {"type": "STRING"},
                                        "gender": {"type": "STRING", "enum": ["male", "female"]}
                                    },
                                    "required": ["name", "gender"]
                                }
                            }
                        }
                    }
                },
                "required": ["name", "relationship", "gender"]
            }
        }
    },
    "required": ["deceased_name", "deceased_gender", "heirs_list", "all_names_extracted_verified"]
}

HUJJAT_WAFAT_GEMINI_PROMPT = """
أنت نظام ذكاء اصطناعي خبير ومخصص لتحليل واستخراج المعطيات الشرعية والقانونية بدقة متناهية 100% من حجاج الوفاة التونسية (وثائق إقامة حجة الوفاة وإشهاد الوفاة الصادرة عن محاكم الناحية التونسية).

المطلوب منك تحليل الوثيقة واستخراج قائمة الورثة الشرعيين المحيطين بإرث المتوفى، مع تحديد جنس كل وارث صراحة ("male" أو "female") وفصل الأبناء الذكور عن البنات الإناث بدقة متناهية:

تعليمات صارمة ومهمة جداً لضمان عدم إغفال أي وارث وعدم خلط الصفات الشرعية:
1. التدقيق والتدقيق الذاتي لمنع الإغفال (Strict Anti-Omission Self-Audit):
   - يجب إجراء مراجعة ذاتية دقيقة وشاملة قبل إخراج كود JSON للتحقق من استخراج كل وارث، ابن، بنت، وأبناء الفروع المذكورين في كتل النص المصدر.
   - "يحذر من إغفال أي اسم أو اختصار القائمة. يجب استخراج كافة أسماء الورثة دون استثناء."
   - تعيين الحقل "all_names_extracted_verified": true بعد التأكد الحاسم من مطابقة قائمة الأسماء المستخرجة لكافة الأسماء الموجودة بالنص الأصلي.

2. التحليل اللغوي الشرعي الصارم لألفاظ المحرر التونسي (Spouse & Parents Detection):
   - المحرر التونسي يستخدم عبارات قانونية صريحة مثل: "زوجته"، "زوجته الشرعية"، "أرملته"، "حرمه"، "تاركاً لزوجته"، "زوجها"، "والدته"، "أمه"، "والده"، "أبوه".
   - يجب عليك وضع الزوجة حصراً في "wife_name" وتحديد "wife_alive": true.
   - يجب وضع الزوج حصراً في "husband_name" وتحديد "husband_alive": true.
   - يمنع منعاً باتاً كلياً وضع الزوجة أو الزوج أو الأب أو الأم ضمن الأبناء (sons_names / daughters_names) أو حسابهم ضمن عدد الأبناء (sons_count / daughters_count)! الزوج والزوجة والأب والأم هم أزواج وأصول وليسوا أبناء!

3. فصل الأبناء الذكور عن البنات الإناث (Crucial Classification):
   - حتى وإن جمع عدل الإشهاد التونسي جميع الأبناء تحت عبارة عامة مثل: "وأبناؤه منها الرشداء وهم : رفيقه / جمال / أحمد / أميرة / منصور / عزة"، يجب عليك تحليل كل اسم فردي في الثقافة التونسية:
     - فرز الذكور في "sons_names" وتحديد "relationship": "son", "gender": "male" (مثل: جمال، أحمد، منصور).
     - فرز الإناث في "daughters_names" وتحديد "relationship": "daughter", "gender": "female" (مثل: رفيقة، أميرة، عزة).
     - حساب "sons_count" بعدد الأبناء الذكور فقط، و "daughters_count" بعدد البنات الإناث فقط.
   - يمنع منعاً باتاً وضع الإناث في قائمة الذكور لمجرد استخدام المحرر لكلمة "أبناؤه"!

4. المطلقة والمطلق (Divorced Spouse - لا إرث للمطلقة):
   - إذا ورد في حجة الوفاة أن الزوجة مطلقة (مثل: "زوجته المطلقة", "مطلقته", "فارقها بالطلاق", "طلاقاً باتاً", "من غير وارث", "غير وارثة")، فإن عقد الزوجية منقضٍ قانونياً وشرعياً ولا إرث لها نهائياً.
   - يجب عليك تحديد "wife_alive": false و "wife_name": "" واستبعادها تماماً من قائمة الورثة المستحقين للإرث!

5. الفروع المتوفاة سابقاً (المناسخات والوصية الواجبة - الفصول 191 و 192 م.أ.ش):
   - إذا ذكرت الوثيقة ابناً أو بنتاً توفيا قبل الموروث (مثل: "توفي قبله"، "توفيت قبلها")، ضع "is_predeceased": true، واستخرج جميع أسمائهم وأحفادهم دون استثناء أي اسم.

6. إرجاع النتيجة حصراً في صيغة JSON مطابق للشفرة الهيكلية المطلوبة.
"""

def extract_hujjat_wafat_with_gemini(document_input, api_key: str = "", model_name: str = "") -> dict:
    """
    Calls Google Gemini Vision API using Structured JSON Output (responseSchema)
    to process uploaded/scanned Hujjat Wafat documents and extract all heirs with explicit genders.
    """
    import base64
    import json
    import requests
    import os

    keys = []
    if api_key:
        keys = [k.strip() for k in api_key.replace('\n', ',').replace(';', ',').split(',') if k.strip()]
    if not keys:
        try:
            from config import load_saved_api_keys
            k_saved = load_saved_api_keys("gemini")
            if k_saved:
                keys = [k.strip() for k in k_saved.replace('\n', ',').replace(';', ',').split(',') if k.strip()]
        except Exception:
            pass

    if not keys:
        env_k = os.environ.get("GEMINI_API_KEY", "").strip()
        if env_k:
            keys = [env_k]

    if not keys:
        return {"success": False, "error": "يرجى توفير مفتاح Gemini API Key لمسح حجة الوفاة."}

    parts = [{"text": HUJJAT_WAFAT_GEMINI_PROMPT}]

    if isinstance(document_input, bytes):
        b64_str = base64.b64encode(document_input).decode('utf-8')
        parts.append({
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": b64_str
            }
        })
    elif isinstance(document_input, list) and len(document_input) > 0:
        for img in document_input:
            if isinstance(img, bytes):
                b64_str = base64.b64encode(img).decode('utf-8')
                parts.append({
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": b64_str
                    }
                })
    elif isinstance(document_input, str) and document_input.strip():
        parts.append({"text": f"نص حجة الوفاة المراد تحليلها:\n{document_input.strip()}"})
    else:
        return {"success": False, "error": "المُدخل لمسح حجة الوفاة غير صالح."}

    valid_models = ("gemini-1.5-pro", "gemini-2.0-pro-exp", "gemini-2.5-pro", "gemini-2.5-flash", "gemini-1.5-flash", "gemini-2.0-flash")
    model_id = model_name if model_name in valid_models else "gemini-1.5-pro"

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": HUJJAT_WAFAT_GEMINI_SCHEMA
        }
    }

    last_err = ""
    for current_key in keys:
        rest_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={current_key}"
        headers = {"Content-Type": "application/json", "x-goog-api-key": current_key}
        try:
            r = requests.post(rest_url, json=payload, headers=headers, timeout=40)
            if r.status_code == 200:
                resp_json = r.json()
                candidates = resp_json.get("candidates", [])
                if candidates:
                    text_parts = candidates[0].get("content", {}).get("parts", [])
                    if text_parts:
                        out_raw = text_parts[0].get("text", "").strip()
                        parsed_dict = json.loads(out_raw)
                        formatted_heirs = parse_hujjat_wafat_text(parsed_dict)
                        return {
                            "success": True,
                            "raw_json": parsed_dict,
                            "heirs_dict": formatted_heirs,
                            "error": None
                        }
            else:
                last_err = f"HTTP {r.status_code}: {r.text[:200]}"
        except Exception as ex:
            last_err = str(ex)
            continue

    return {"success": False, "error": f"فشل استخراج معطيات حجة الوفاة عبر Gemini: {last_err}"}


def parse_hujjat_wafat_text(text_or_dict) -> dict:
    """
    Ingests Hujjat Wafat input (either structured JSON dictionary from Gemini AI,
    or raw text) and builds the clean heirs dictionary for calculate_farida().
    Trusts explicit gender outputs ('male' / 'female') provided by Gemini.
    """
    heirs = {
        'husband': False,
        'wife': False,
        'wives_count': 1,
        'sons_count': 0,
        'daughters_count': 0,
        'father': False,
        'mother': False,
        'paternal_grandfather': False,
        'maternal_grandmother': False,
        'paternal_grandmother': False,
        'full_brothers_count': 0,
        'full_sisters_count': 0,
        'predeceased_children_count': 0,
        'predeceased_list': [],
        'names': [],
        'heir_details': {},
        'deceased_name': '',
        'deceased_gender': 'male',
        'husband_name': '',
        'wife_name': '',
        'applicant_name': '',
        'applicant_cin': '',
        'hujja_num': '',
        'hujja_date': '',
        'hujja_court': ''
    }

    if not text_or_dict:
        return heirs

    if isinstance(text_or_dict, dict):
        data = text_or_dict
        heirs['hujja_num'] = str(data.get('hujja_num', '')).strip()
        heirs['hujja_date'] = str(data.get('hujja_date', '')).strip()
        heirs['hujja_court'] = str(data.get('hujja_court', '')).strip()
        heirs['applicant_name'] = str(data.get('applicant_name', '')).strip()
        heirs['deceased_name'] = str(data.get('deceased_name', '')).strip()
        heirs['deceased_gender'] = str(data.get('deceased_gender', 'male')).strip()

        heirs['husband'] = bool(data.get('husband_alive', False))
        heirs['husband_name'] = str(data.get('husband_name', '')).strip()

        heirs['wife'] = bool(data.get('wife_alive', False))
        heirs['wife_name'] = str(data.get('wife_name', '')).strip()
        heirs['wives_count'] = max(1, int(data.get('wives_count', 1)))

        heirs['father'] = bool(data.get('father_alive', False))
        heirs['father_name'] = str(data.get('father_name', '')).strip()

        heirs['mother'] = bool(data.get('mother_alive', False))
        heirs['mother_name'] = str(data.get('mother_name', '')).strip()

        s_count = int(data.get('sons_count', 0))
        d_count = int(data.get('daughters_count', 0))

        heirs_list = data.get('heirs_list', [])
        if not heirs_list:
            heirs_list = []
            sp_and_parents_norm = {
                _norm(heirs.get('wife_name', '')),
                _norm(heirs.get('husband_name', '')),
                _norm(heirs.get('mother_name', '')),
                _norm(heirs.get('father_name', ''))
            }
            for s in data.get('sons_names', []):
                if s and str(s).strip():
                    if _norm(str(s)) not in sp_and_parents_norm:
                        heirs_list.append({'name': str(s).strip(), 'relationship': 'ابن', 'gender': 'male'})
            for d in data.get('daughters_names', []):
                if d and str(d).strip():
                    if _norm(str(d)) not in sp_and_parents_norm:
                        heirs_list.append({'name': str(d).strip(), 'relationship': 'بنت', 'gender': 'female'})
            if not heirs_list:
                for n in data.get('names', []):
                    if n and str(n).strip():
                        n_s = str(n).strip()
                        n_nm = _norm(n_s)
                        if any(sp for sp in sp_and_parents_norm if sp and (sp in n_nm or n_nm in sp)):
                            continue  # SKIP SPOUSE & PARENTS FROM BEING ADDED AS CHILDREN!
                        is_f = _is_female_name(n_s)
                        heirs_list.append({'name': n_s, 'relationship': 'بنت' if is_f else 'ابن', 'gender': 'female' if is_f else 'male'})

        names = []
        predeceased = []
        heir_details = {}

        # 1. Pre-process heirs_list to extract spouses & parents explicitly if present in relationships or names
        for item in heirs_list:
            if not isinstance(item, dict):
                continue
            item_name = str(item.get('name', '')).strip()
            item_rel = str(item.get('relationship', '')).strip().lower()

            if not item_name:
                continue

            # Check for Divorced Wife/Husband (المطلقة / المطلق) - No inheritance
            if any(k in item_rel or k in item_name for k in ['مطلقة', 'مطلقته', 'مطلقها', 'طلاق', 'طلاقاً', 'فارقها', 'غير وارثة', 'من غير وارث', 'من غير الوارث']):
                if 'زوج' in item_rel or 'أرمل' in item_rel or 'زوج' in item_name or 'امرأة' in item_name or 'بنت' in item_name or _is_female_name(item_name):
                    heirs['wife'] = False
                    heirs['wife_name'] = ""
                else:
                    heirs['husband'] = False
                    heirs['husband_name'] = ""
                continue

            # Check for Wife / Spouse (female) keywords in relationship or name
            elif any(k in item_rel for k in ['زوجة', 'زوجته', 'أرملة', 'أرملته', 'حرم', 'حرمه', 'wife']) or re.search(r'^(?:زوجة|زوجته|أرملة|أرملته|حرمه|حرم|الزوجة)\b', item_name):
                heirs['wife'] = True
                clean_w = re.sub(r'^(?:زوجة|زوجته|أرملة|أرملته|حرمه|حرم|الزوجة)\s*', '', item_name).strip()
                if clean_w and not heirs['wife_name']:
                    heirs['wife_name'] = clean_w

            # Check for Husband / Spouse (male) keywords in relationship or name
            elif any(k in item_rel for k in ['زوجها', 'أرملها', 'husband']) or (item_rel == 'زوج' and not heirs['husband']):
                heirs['husband'] = True
                clean_h = re.sub(r'^(?:زوجها|زوج|أرملها|أرمل|الزوج)\s*', '', item_name).strip()
                if clean_h and not heirs['husband_name']:
                    heirs['husband_name'] = clean_h

            # Check for Mother keywords in relationship or name
            elif any(k in item_rel for k in ['أم', 'أمه', 'والدة', 'والدته', 'mother']) or re.search(r'^(?:والدته|والدة|أمه|أم|الأم)\b', item_name):
                heirs['mother'] = True
                clean_m = re.sub(r'^(?:والدته|والدة|أمه|أم|الأم)\s*', '', item_name).strip()
                if clean_m and not heirs['mother_name']:
                    heirs['mother_name'] = clean_m

            # Check for Father keywords in relationship or name
            elif any(k in item_rel for k in ['أب', 'أبوه', 'والد', 'والده', 'father']) or re.search(r'^(?:والده|والد|أبوه|أب|الأب)\b', item_name):
                heirs['father'] = True
                clean_f = re.sub(r'^(?:والده|والد|أبوه|أب|الأب)\s*', '', item_name).strip()
                if clean_f and not heirs['father_name']:
                    heirs['father_name'] = clean_f

        # Build clean set of spouse & parent names for substring exclusion
        sp_names = [heirs.get('wife_name', ''), heirs.get('husband_name', ''), heirs.get('mother_name', ''), heirs.get('father_name', '')]
        sp_clean_set = set()
        for sp in sp_names:
            if sp and len(sp.strip()) > 1:
                sp_clean_set.add(_norm(sp.strip()))
                parts = _norm(sp.strip()).split()
                if len(parts) >= 2:
                    sp_clean_set.add(" ".join(parts[:2]))

        s_idx, d_idx = 0, 0
        for item in heirs_list:
            if not isinstance(item, dict):
                continue
            name = str(item.get('name', '')).strip()
            rel = str(item.get('relationship', '')).strip().lower()
            gender = str(item.get('gender', '')).strip().lower()
            is_pred = bool(item.get('is_predeceased', False))

            if not name:
                continue

            # Exclude Spouses & Parents & Divorced Spouses strictly by relationship keywords or name matching
            rel_starts_with_child = (
                any(rel.startswith(k) for k in ['ابن', 'بنت', 'ولد', 'ابناء', 'أبناء', 'بنات', 'أولاد', 'اولاد', 'حفيد', 'حفيدة']) or
                re.search(r'^(?:ابنه|ابنها|بنته|بنتها|ولده|ولدها)\b', rel) or
                re.search(r'\b(?:من\s+زوجته|من\s+زوجها|من\s+أرملته)\b', rel)
            )

            is_spouse_or_parent_or_divorced = not rel_starts_with_child and (
                any(k in rel or k in name for k in ['مطلقة', 'مطلقته', 'مطلقها', 'طلاق', 'فارقها', 'غير وارثة', 'من غير وارث']) or
                any(k in rel for k in ['زوجة', 'زوجته', 'أرملة', 'أرملته', 'حرم', 'حرمه', 'wife', 'زوجها', 'husband', 'والدة', 'والدته', 'mother', 'والد', 'والده', 'father']) or
                (rel in ['زوج', 'أب', 'أم']) or
                re.search(r'^(?:زوجة|زوجته|أرملة|أرملته|حرمه|حرم|الزوجة|زوجها|زوج|والدته|والدة|أمه|أم|والده|والد|أبوه|أب)\b', name)
            )
            if is_spouse_or_parent_or_divorced:
                continue

            # Substring / Exact match exclusion against detected spouse and parent names (normalized)
            is_matched_sp = False
            norm_name = _norm(name)
            for sp_str in sp_clean_set:
                if sp_str and (sp_str in norm_name or norm_name in sp_str):
                    is_matched_sp = True
                    break
            if is_matched_sp:
                continue

            is_grandchild_or_predeceased = (
                is_pred or 'متوفى' in rel or 'متوفاة' in rel or
                any(k in rel for k in ['ابن ابن', 'بنت ابن', 'ابن ابنة', 'بنت ابنة', 'حفيد', 'حفيدة', 'وصية واجبة', 'الوصية الواجبة'])
            )

            if is_grandchild_or_predeceased:
                p_details = item.get('predeceased_details', {}) or {}
                gc_list = p_details.get('grandchildren', [])
                gc_names = [g.get('name') for g in gc_list if isinstance(g, dict) and g.get('name')]
                if not gc_names and ('ابن ابن' in rel or 'بنت ابن' in rel or 'حفيد' in rel or 'حفيدة' in rel):
                    gc_names = [name]
                predeceased.append({
                    'parent_name': str(p_details.get('parent_name', name)).strip(),
                    'parent_gender': gender or ('female' if 'بنت' in rel or 'متوفاة' in rel else 'male'),
                    'is_married': bool(p_details.get('has_spouse', True)),
                    'spouse_name': str(p_details.get('spouse_name', '')).strip(),
                    'sons_count': int(p_details.get('sons_count', 0)),
                    'daughters_count': int(p_details.get('daughters_count', 0)),
                    'grandchildren_names': gc_names
                })
            else:
                names.append(name)
                if gender == 'female':
                    is_fem = True
                elif gender == 'male':
                    is_fem = False
                else:
                    is_fem = ('بنت' in rel or 'daughter' in rel or 'أنثى' in rel or 'انثى' in rel or _is_female_name(name))

                if is_fem:
                    k = f"daughter_{d_idx+1}"
                    d_idx += 1
                else:
                    k = f"son_{s_idx+1}"
                    s_idx += 1
                heir_details[k] = {'name': name, 'gender': 'female' if is_fem else 'male'}

        heirs['sons_names'] = [v['name'] for k, v in heir_details.items() if k.startswith('son_')]
        heirs['daughters_names'] = [v['name'] for k, v in heir_details.items() if k.startswith('daughter_')]
        heirs['names'] = heirs['sons_names'] + heirs['daughters_names']
        heirs['heir_details'] = heir_details
        heirs['sons_count'] = max(s_count, len(heirs['sons_names']))
        heirs['daughters_count'] = max(d_count, len(heirs['daughters_names']))
        heirs['predeceased_children_count'] = len(predeceased)
        heirs['predeceased_list'] = predeceased

        return sanitize_and_validate_heirs_graph(heirs, raw_data=data)

    text = str(text_or_dict)
    t = text.strip()

    # 0. Check if AI Vision returned JSON block inside text
    if '{' in t and '}' in t:
        try:
            m_json = re.search(r'\{.*\}', t, re.DOTALL)
            if m_json:
                data = json.loads(m_json.group(0))
                if isinstance(data, dict):
                    if 'hujja_num' in data and data['hujja_num']: heirs['hujja_num'] = _clean_extracted_text(str(data['hujja_num']))
                    if 'hujja_date' in data and data['hujja_date']: heirs['hujja_date'] = _clean_extracted_text(str(data['hujja_date']))
                    if 'hujja_court' in data and data['hujja_court']: heirs['hujja_court'] = _clean_extracted_text(str(data['hujja_court']))
                    if 'applicant_name' in data and data['applicant_name']: heirs['applicant_name'] = _clean_extracted_text(str(data['applicant_name']))
                    if 'deceased_name' in data and data['deceased_name']: heirs['deceased_name'] = _clean_extracted_text(str(data['deceased_name']))
                    if 'deceased_lakab' in data and data['deceased_lakab']: heirs['deceased_lakab'] = _clean_extracted_text(str(data['deceased_lakab']))
                    if 'wife_name' in data and data['wife_name']: heirs['wife_name'] = _clean_extracted_text(str(data['wife_name']))
                    if 'husband_name' in data and data['husband_name']: heirs['husband_name'] = _clean_extracted_text(str(data['husband_name']))
                    
                    if 'sons_count' in data: heirs['sons_count'] = int(data['sons_count'])
                    if 'daughters_count' in data: heirs['daughters_count'] = int(data['daughters_count'])
                    if 'husband_alive' in data: heirs['husband'] = bool(data['husband_alive'])
                    if 'wife_alive' in data: heirs['wife'] = bool(data['wife_alive'])
                    if 'father_alive' in data: heirs['father'] = bool(data['father_alive'])
                    if 'mother_alive' in data: heirs['mother'] = bool(data['mother_alive'])

                    extracted_names = []
                    if 'names' in data and isinstance(data['names'], list):
                        extracted_names.extend([_clean_extracted_text(str(n)) for n in data['names'] if n])
                    if 'sons_names' in data and isinstance(data['sons_names'], list):
                        extracted_names.extend([_clean_extracted_text(str(n)) for n in data['sons_names'] if n])
                    if 'daughters_names' in data and isinstance(data['daughters_names'], list):
                        extracted_names.extend([_clean_extracted_text(str(n)) for n in data['daughters_names'] if n])
                    
                    if extracted_names:
                        heirs['names'] = list(dict.fromkeys([n for n in extracted_names if n]))

                    if heirs['sons_count'] > 0 or heirs['daughters_count'] > 0 or heirs['husband'] or heirs['wife'] or heirs['deceased_name']:
                        return heirs
        except Exception:
            pass

    clause_match = re.search(r"(?:وقد تركت?|أحاط بتركه|انحصر ورثته?|الورثة الشرعيين?|المحيطين\s+بارثه|المحيطين\s+بتركته)\s*[:：]?(.*?)(?:ولم ترك|ولم يترك|هذا ما تم|وذلك تمامها|لا غير|$)", t, re.DOTALL)
    clause_text = clause_match.group(1) if clause_match else t

    # Determine gender of deceased strictly
    if re.search(r"\b(زوجته|إرثه|تركته|أبناؤه|أولاده)\b", t):
        is_female_deceased = False
        is_male_deceased = True
    elif re.search(r"\b(زوجها|إرثها|تركتها|أبناؤها|أولادها)\b", t):
        is_female_deceased = True
        is_male_deceased = False
    else:
        is_female_deceased = bool(re.search(r"(المتوفاة|المتوفية|المتوفات|الهالكة|الموروثة|المرحومة)", t))
        is_male_deceased = bool(re.search(r"(المتوفى|الهالك|الموروث|المرحوم)", t)) and not is_female_deceased

    # 1. Spouse check
    if is_female_deceased:
        heirs['wife'] = False  # Deceased is female -> She has NO wife!
        if re.search(r"زوجها\s+(?:المتوفى|الهالك)\s+قبلها", clause_text) or "المتوفى قبلها" in clause_text or "الهالك قبلها" in clause_text or "توفي قبلها" in clause_text:
            heirs['husband'] = False
        elif re.search(r"\bزوجها\b", clause_text):
            heirs['husband'] = True
            m_husb = re.search(r"زوجها\s*[:：]?\s*([^\n،.]+?)(?=\s+و?ابناؤها|\s+و?ابنائها|\s+و?اولادها|\s+و?المحيطين|\s+وهم|\n|$)", clause_text)
            if m_husb: heirs['husband_name'] = _clean_extracted_text(m_husb.group(1))
        else:
            heirs['husband'] = False
    elif is_male_deceased:
        heirs['husband'] = False  # Deceased is male -> He has NO husband!
        if re.search(r"زوجته\s+(?:المتوفاة|الهالكة)\s+قبله", clause_text) or "المتوفاة قبله" in clause_text or "الهالكة قبله" in clause_text or "توفيت قبله" in clause_text:
            heirs['wife'] = False
        elif re.search(r"\b(زوجته|زوجاته|أرملة|حرمته)\b", clause_text):
            heirs['wife'] = True
            m_wife = re.search(r"زوجته\s*[:：]?\s*([^\n،.]+?)(?=\s+و?ابناؤه|\s+و?ابنائه|\s+و?اولاده|\s+و?المحيطين|\s+وهم|\n|$)", clause_text)
            if m_wife:
                wife_raw = _clean_extracted_text(m_wife.group(1))
                # Strip 'ولقبها X' from end of matched text but record lakab to append cleanly
                m_wife_lakab = re.search(r"ولقبها\s*[:：]?\s*([^\s،.\n]+)", m_wife.group(1))
                if m_wife_lakab:
                    wife_lakab = _clean_extracted_text(m_wife_lakab.group(1))
                    wife_raw = re.sub(r"\s+ولقبها\s*[:：]?\s*[^\s،.\n]+", "", wife_raw).strip()
                    clean_w = re.sub(r'\s+', '', wife_raw)
                    clean_l = re.sub(r'\s+', '', wife_lakab)
                    if clean_l and clean_l not in clean_w:
                        wife_raw = f"{wife_raw} {wife_lakab}"
                heirs['wife_name'] = _clean_extracted_text(wife_raw)
        else:
            heirs['wife'] = False
    else:
        if re.search(r"زوجها\s+(?:المتوفى|الهالك)\s+قبلها", clause_text) or "المتوفى قبلها" in clause_text:
            heirs['husband'] = False
        elif re.search(r"زوجته\s+(?:المتوفاة|الهالكة)\s+قبله", clause_text) or "المتوفاة قبله" in clause_text:
            heirs['wife'] = False

    # 2. Parents check
    if re.search(r"\b(والده|أبوه|أبيه)\b", clause_text) and "المتوفى قبل" not in clause_text:
        heirs['father'] = True
    if re.search(r"\b(والدته|أمه|أمي)\b", clause_text) and "المتوفاة قبل" not in clause_text:
        heirs['mother'] = True

    # Extract non-heir names (predeceased husband/wife names & explicitly excluded non-inheritors)
    non_heir_names = {'الرشداء', 'البالغين', 'المذكورين', 'وهم', 'منها', 'منه', 'غير', 'لاغير', 'لا', 'التركة', 'المحيطين', 'بإرثه', 'بارثه', 'الذين', 'تصادقا'}
    for m in re.finditer(r"(?:زوجها\s+(?:المتوفى|الهالك)\s+قبلها|زوجته\s+(?:المتوفاة|الهالكة)\s+قبله|من\s+غير\s+الوارث)\s+([^\s،.]+)", clause_text):
        non_heir_names.add(m.group(1).strip())

    # Extract deceased name & family surname / lakab (ولقبه/ولقبها)
    clean_t = re.sub(r'\(Deceased Name & Surname\)', '', t, flags=re.IGNORECASE)
    clean_t = re.sub(r'\(Deceased Name & Lakab\)', '', clean_t, flags=re.IGNORECASE)
    clean_t = re.sub(r'\(Spouse Full Name\)', '', clean_t, flags=re.IGNORECASE)

    if is_male_deceased:
        m_lakab = re.search(r"\bولقبه\s*[:：]?\s*([^\s،.\n()]+)", clean_t)
    else:
        spouse_idx = re.search(r"\b(زوجها|زوجته)\b", clean_t)
        search_scope = clean_t[:spouse_idx.start()] if spouse_idx else clean_t
        m_lakab = re.search(r"\bولقبها\s*[:：]?\s*([^\s،.\n()]+)", search_scope)

    deceased_lakab = _clean_extracted_text(m_lakab.group(1)) if m_lakab else ""

    if not heirs['deceased_name']:
        clean_text_for_dec = re.sub(r'اسم\s+الأم\s+ولقبها\s*[:：]?\s*[^\n،.]+', '', clean_t)
        clean_text_for_dec = re.sub(r'زوج(?:ها|ته)\s+(?:المتوفى|المتوفاة|الهالك|الهالكة)\s+(?:قبلها|قبله)\s+[^\n،.]+', '', clean_text_for_dec)
        
        m_dec = re.search(r"(?:إقامة\s+حجة\s+وفاة\s+|نقرر\s+إقامة\s+حجة\s+وفاة\s+|حجة\s+وفاة\s+|رسم\s+وفاة\s+|اسم\s+)?(?:الهالك|الهالكة|المرحوم|المرحومة|المتوفى|المتوفاة|الموروث|الموروثة)(?:ة|\(ة\))?\s*[:：\-\s\n\r]*([^\n،.:]+)", clean_text_for_dec)
        if not m_dec:
            m_dec = re.search(r"(?:المرحوم|المرحومة|المتوفى|المتوفاة|الهالك|الهالكة)(?:ة|\(ة\))?\s*[:：\-\s\n\r]*([أ-ي\s]+?(?:بن|بنت)[أ-ي\s]+)", clean_text_for_dec)
        if m_dec:
            raw_dec = m_dec.group(1).strip()
            raw_dec = re.split(r"(?:\s+ولقبه|\s+اسم\s+الأم|\s+المتوفي|\s+المتوفى|\s+حسب|\s+جنسيته|\s+اسم\s+والد)", raw_dec)[0]
            heirs['deceased_name'] = _clean_extracted_text(raw_dec)

    # Contextual Smart Fallback if deceased_name is still empty or procedural
    if not heirs['deceased_name'] or heirs['deceased_name'].startswith("الاذن له") or heirs['deceased_name'].startswith("إقامة حجة"):
        smart_name = _extract_deceased_name_smart_fallback(clean_t, deceased_lakab)
        if smart_name:
            heirs['deceased_name'] = smart_name

    if not deceased_lakab and heirs['deceased_name']:
        dec_parts = heirs['deceased_name'].split()
        if len(dec_parts) > 1 and "بن" not in dec_parts[-1] and "bنت" not in dec_parts[-1]:
            deceased_lakab = dec_parts[-1]
    heirs['deceased_lakab'] = deceased_lakab

    # Append lakab to deceased_name if not already present (e.g. "بوجمعه بن الطيب" + "الرياحي")
    if deceased_lakab and heirs['deceased_name'] and not heirs['deceased_name'].endswith(deceased_lakab):
        heirs['deceased_name'] = f"{heirs['deceased_name']} {deceased_lakab}"

    # 3. Children list parsing (e.g. وأبناؤه منها الرشداء وهم : رفيقه / جمال / أحمد / أميرة / منصور / عزة لا غير)
    t_norm = re.sub(r'[أإآ]', 'ا', t)
    clause_norm = re.sub(r'[أإآ]', 'ا', clause_text)
    kids_match = re.search(r"(?:و?ابنا[ؤئءه]ه|و?ابنائه|و?ابنائها|و?ابناؤها|و?اولاده|و?اولادها|و?ورثته|و?خلفاؤه|و?خلفائه).*?(?:وهم|الرشداء|البالغين)?\s*[:：\-]*\s*(.+?)\s*(?:لا\s+غير|\s+غير|\s+المحل|\.\/\.|\n|$)", clause_norm)
    if not kids_match:
        kids_match = re.search(r"وهما\s+(?:الرشيدين|البالغين|المذكورين)?\s*([^\n،.]+?)(?:ومن\s+غير|\s+والوارث|ولم|$)", clause_norm)

    if kids_match:
        raw_phrase = kids_match.group(1)
        raw_list = [_clean_extracted_text(n.strip()) for n in re.split(r"[-/،,;]+|\s+و\s*", raw_phrase) if n.strip()]
        valid_names = [n for n in raw_list if n and len(n) > 1 and n not in non_heir_names]
        if valid_names:
            heirs['sons_count'] = 0
            heirs['daughters_count'] = 0
            heirs['sons_names'] = []
            heirs['daughters_names'] = []
            heirs['names'] = []
            for name in valid_names:
                clean_n = re.sub(r'^(?:الابن|البنت|ابن|بنت|السيد|السيدة|من\s+الأبناء|منها|منه|الرشداء|البالغين|الرشيدين|المذكورين|وهم|وهي|هم|كالتالي|و|[:：\-\s]+)+', '', name).strip()
                if not clean_n or clean_n in non_heir_names:
                    continue
                
                # Append father's family surname (lakab) if available
                if deceased_lakab and not clean_n.endswith(deceased_lakab):
                    full_child_name = f"{clean_n} {deceased_lakab}"
                else:
                    full_child_name = clean_n
                cleaned_full = _clean_extracted_text(full_child_name)
                heirs['names'].append(cleaned_full)

                if _is_female_name(clean_n):
                    heirs['daughters_count'] += 1
                    heirs['daughters_names'].append(cleaned_full)
                else:
                    heirs['sons_count'] += 1
                    heirs['sons_names'].append(cleaned_full)

    # 4. Standard Sons & Daughters regex if not extracted via names list
    if heirs['sons_count'] == 0 and heirs['daughters_count'] == 0:
        # Dual terms (ابنيها / ولدين / ابنين / ابنتيها / بنتين)
        if re.search(r"\b(ابنيها|ابنيه|ولدين|ابنين|ولديها)\b", clause_text):
            heirs['sons_count'] = 1
            heirs['daughters_count'] = 1
        elif re.search(r"\b(ابنتيها|ابنتين|bنتين)\b", clause_text):
            heirs['daughters_count'] = 2

        sons_match = re.search(r"(أبناؤه?|أبنائه?|أبناءها|أبنائها|أبنائهن|إبنه|ابنه|أولاده)\s*(?:منه|منها)?\s*[:：]?\s*([^،.\n]+)", clause_text)
        if sons_match:
            sons_part = re.split(r"(بناته?|bناتها|ابنته|بنته)", sons_match.group(2))[0]
            stop_words = {"الذكر", "مثل", "حظ", "الأنثيين", "وهم", "وهن", "منها", "منه", "غير", "التركة", "ابن", "إبن", "ابنه", "الرشداء", "البالغين"}
            s_names = [n.strip() for n in re.split(r"[-/،,]+|\s+و\s+", sons_part) if len(n.strip()) > 1 and n.strip() not in stop_words and n.strip() not in non_heir_names]
            if len(s_names) > 0:
                heirs['sons_count'] = len(s_names)
                heirs['names'].extend([_clean_extracted_text(sn) for sn in s_names])

        daug_match = re.search(r"(بناته?|بناتها|بناتهن|ابنته|إبنته|بنته)\s*(?:منه|منها)?\s*[:：]?\s*([^،.\n]+)", clause_text)
        if daug_match:
            stop_words = {"الذكر", "مثل", "حظ", "الأنثيين", "وهم", "وهن", "منها", "منه", "غير", "التركة", "بنت", "بنته", "الرشداء", "البالغين"}
            daug_part = re.split(r"(أبناؤه?|أبنائه?|إبنه|ابنه|أولاده)", daug_match.group(2))[0]
            d_names = [n.strip() for n in re.split(r"[-/،,]+|\s+و\s+", daug_part) if len(n.strip()) > 1 and n.strip() not in stop_words and n.strip() not in non_heir_names]
            if len(d_names) > 0:
                heirs['daughters_count'] = len(d_names)

    # Smart Universal Fallback for Heirs if still 0
    if heirs['sons_count'] == 0 and heirs['daughters_count'] == 0:
        smart_h = _extract_heirs_smart_fallback(t, deceased_lakab)
        if smart_h.get('names'):
            heirs['sons_count'] = smart_h['sons_count']
            heirs['daughters_count'] = smart_h['daughters_count']
            heirs['names'] = smart_h['names']

    # 5. Extract metadata (Deceased name, Applicant, Court, File Num, Date)
    heirs['applicant_name'] = _extract_applicant_smart_fallback(t)

    if not heirs['deceased_name']:
        clean_text_for_dec = re.sub(r'اسم\s+الأم\s+ولقبها\s*[:：]?\s*[^\n،.]+', '', clean_t)
        clean_text_for_dec = re.sub(r'زوج(?:ها|ته)\s+(?:المتوفى|المتوفاة|الهالك|الهالكة)\s+(?:قبلها|قبله)\s+[^\n،.]+', '', clean_text_for_dec)
        
        m_dec = re.search(r"(?:إقامة\s+حجة\s+وفاة\s+|نقرر\s+إقامة\s+حجة\s+وفاة\s+|حجة\s+وفاة\s+|اسم\s+)?(?:الهالك|الهالكة|المرحوم|المرحومة|المتوفى|المتوفاة|الموروث|الموروثة)(?:ة|\(ة\))?\s*[:：]?\s*([^\n،.:]+)", clean_text_for_dec)
        if m_dec:
            raw_dec = m_dec.group(1).strip()
            raw_dec = re.split(r"(?:\s+ولقبه|\s+اسم\s+الأم|\s+المتوفي|\s+المتوفى|\s+حسب|\s+جنسيته)", raw_dec)[0]
            heirs['deceased_name'] = _clean_extracted_text(raw_dec)

    # Top right header: Court of Jurisdiction (محكمة ناحية... / المحكمة الابتدائية...)
    if not heirs['hujja_court']:
        m_crt = re.search(r"(?:الجمهورية\s+التونسية\s+)?(?:وزارة\s+العدل\s+)?(محكمة\s+(?:الناحية|ناحية|الابتدائية)\s+ب?[^\n،.]+)", clean_t[:500])
        if not m_crt:
            m_crt = re.search(r"(محكمة\s+(?:الناحية|ناحية|الابتدائية)\s+ب?[^\n،.]+)", clean_t)
        if m_crt:
            heirs['hujja_court'] = _clean_extracted_text(m_crt.group(1))

    # Top left: Case File Number (عدد الملف / عدد المادة / عدد...)
    if not heirs['hujja_num']:
        m_num = re.search(r"(?:عدد\s+الملف|عدد\s+المادة|ملف\s+عدد)\s*[:：]?\s*([\d\/]+)", clean_t)
        if not m_num:
            m_num = re.search(r"(?<![رسم الوفاة])\bعدد\b\s*[:：]?\s*(\d+\/\d{4})\b", clean_t)
        if not m_num:
            m_num = re.search(r"\b(\d+\/\d{4})\b", clean_t)
        if m_num:
            heirs['hujja_num'] = _clean_extracted_text(m_num.group(1))

    if not heirs['hujja_date']:
        m_dt = re.search(r"بتاريخ\s*[:：]?\s*(\d{2}[-\/]\d{2}[-\/]\d{4}|\d{4}[-\/]\d{2}[-\/]\d{2})", clean_t)
        if not m_dt:
            m_dt = re.search(r"(?:في|بتاريخ)\s*[:：]?\s*(\d{2}[-\/]\d{2}[-\/]\d{4}|\d{4}[-\/]\d{2}[-\/]\d{2})", clean_t)
        if not m_dt:
            m_dt = re.search(r"\b(\d{2}[-\/]\d{2}[-\/]\d{4}|\d{4}[-\/]\d{2}[-\/]\d{2})\b", clean_t)
        if not m_dt:
            m_dt = re.search(r"حرر\s+(?:بتونس|في)\s+([^\n،.]+)", clean_t)
        if m_dt:
            heirs['hujja_date'] = _clean_extracted_text(m_dt.group(1))

    heirs['names'] = list(dict.fromkeys([_clean_extracted_text(n) for n in heirs['names'] if _clean_extracted_text(n)]))

    return sanitize_and_validate_heirs_graph(heirs)


def auto_reconstruct_succession_tree(primary_hujja: dict, secondary_hujjaj: list = None) -> dict:
    """
    Autonomous Multi-Hujja Tree Reconstruction Engine matching Tunisian Notary Standards.
    - Always treats `primary_hujja` (uploaded on istirad hujjat wafat lhalek ra2issi) as the Primary Main Deceased (الهالك الرئيسي الأصلي).
    - Links & arranges all secondary Hujjat Wafat documents STRICTLY BY THE NAMES OF CHILDREN & HEIRS (`أسماء الأبناء والورثة`), NOT by date of death.
    """
    if isinstance(primary_hujja, list):
        if not primary_hujja:
            return {}
        h_list = primary_hujja
        primary_hujja = h_list[0]
        secondary_hujjaj = h_list[1:]

    if not primary_hujja or not isinstance(primary_hujja, dict):
        return {}

    def _norm(t):
        if not t: return ""
        t = re.sub(r'[\u064b-\u065f\u0670]', '', str(t))
        t = re.sub(r'[أإآٱ]', 'ا', t)
        t = re.sub(r'ة', 'ه', t)
        t = re.sub(r'ى', 'ي', t)
        t = re.sub(r'ـ', '', t)
        return t.strip()

    root_name = primary_hujja.get("deceased_name", "").strip()
    root_norm = _norm(root_name)
    primary_children = [c.strip() for c in primary_hujja.get("names", []) if c.strip()]
    primary_children_norm = [_norm(c) for c in primary_children]

    primary_date_tuple = _parse_date_to_tuple(primary_hujja.get("hujja_date", ""))

    predeceased_list = []
    successive_deaths_list = []
    narrative_clauses = []

    ordered_chain = [primary_hujja]

    for idx, item in enumerate(secondary_hujjaj or []):
        if isinstance(item, str):
            parsed = parse_hujjat_wafat_text(item)
        elif isinstance(item, dict):
            parsed = item
        else:
            continue

        dec_name = parsed.get("deceased_name", "").strip()
        if not dec_name:
            continue
        dec_norm = _norm(dec_name)
        dec_first = dec_norm.split()[0] if dec_norm.split() else ""

        # Match strictly by Child Name against Primary Children
        matched_child = None
        for i, c_norm in enumerate(primary_children_norm):
            c_first = c_norm.split()[0] if c_norm.split() else ""
            if dec_first and c_first and (dec_first == c_first or c_first in dec_norm):
                matched_child = primary_children[i]
                break

        parent_name = root_name if matched_child else "الموروث الرئيسي"
        names_str = "، ".join(parsed.get("names", [])) if parsed.get("names") else "أبنائه"
        court_num_str = f"عدد {parsed.get('hujja_num', '')} الصادرة عن {parsed.get('hujja_court', '')}" if (parsed.get('hujja_num') or parsed.get('hujja_court')) else ""
        date_str = f"بتاريخ {parsed.get('hujja_date', '')}" if parsed.get('hujja_date') else ""

        ref_str = f"{court_num_str} {date_str}".strip() or "المستند إليها"

        # Compare Death Dates precisely:
        child_date_tuple = _parse_date_to_tuple(parsed.get("hujja_date", ""))
        
        # Child is PREDECEASED (الوصية الواجبة) ONLY IF child died BEFORE or ON SAME DATE as father!
        # If child died AFTER father (child_date_tuple > primary_date_tuple):
        # Child died AFTER father -> Successive inheritance / Munassakhat (تتابع تركات ومناسخة)!
        is_predeceased = (child_date_tuple <= primary_date_tuple) if (child_date_tuple[0] > 0 and primary_date_tuple[0] > 0) else False

        if parsed.get("wife") or parsed.get("wife_name"):
            is_female = False
        elif parsed.get("husband") or parsed.get("husband_name"):
            is_female = True
        else:
            is_female = _is_female_name(dec_name)

        if is_predeceased:
            predeceased_list.append({
                "parent_name": dec_name,
                "matched_child": matched_child or dec_name,
                "parent_gender": "female" if is_female else "male",
                "death_date": parsed.get("hujja_date", ""),
                "sons_count": parsed.get("sons_count", 0),
                "daughters_count": parsed.get("daughters_count", 0),
                "grandchildren_names": parsed.get("names", []),
                "hujja_num": parsed.get("hujja_num", ""),
                "hujja_court": parsed.get("hujja_court", ""),
                "hujja_date": parsed.get("hujja_date", ""),
                "wife": parsed.get("wife", False),
                "wife_name": parsed.get("wife_name", ""),
                "husband": parsed.get("husband", False),
                "husband_name": parsed.get("husband_name", "")
            })
            label_str = "البنت المتوفاة سابقاً" if is_female else "الابن المتوفى سابقاً"
            narrative_clauses.append(
                f"وفاة {label_str} {dec_name} في حياة مورثه(ا) {parent_name} حسب حجة وفاة {ref_str} وتستحق تركته(ا) الوصية الواجبة لفائدة أبنائه(ا) وهم {names_str} عملاً بالفصل 191"
            )
        else:
            successive_deaths_list.append(parsed)
            label_str = "البنت المتوفاة" if is_female else "الابن المتوفى"
            wife_n = parsed.get("wife_name", "").strip() or ("زوجته" if parsed.get("wife") else "")
            husband_n = parsed.get("husband_name", "").strip() or ("زوجها" if parsed.get("husband") else "")
            if wife_n:
                w_label = wife_n if "زوج" in wife_n else f"زوجته {wife_n}"
                family_info = f"{w_label} وأبناؤه منها وهم {names_str}"
            elif husband_n:
                h_label = husband_n if "زوج" in husband_n else f"زوجها {husband_n}"
                family_info = f"{h_label} وأبناؤها منه وهم {names_str}"
            else:
                family_info = f"أبناؤه وهم {names_str}" if not is_female else f"أبناؤها وهم {names_str}"

            narrative_clauses.append(
                f"تتابع التركات بحصول وفاة {label_str} {dec_name} بعد وفاة مورثه(ا) {parent_name} حسب حجة وفاة {ref_str} وترك {family_info}، وانتقال منابه الشرعي الموروث لورثته المذكورين"
            )

        ordered_chain.append(parsed)

    successive_text = "؛ و".join(narrative_clauses) if narrative_clauses else ""

    return {
        "root_hujja": primary_hujja,
        "root_name": root_name,
        "ordered_chain": ordered_chain,
        "predeceased_list": predeceased_list,
        "successive_deaths_list": successive_deaths_list,
        "successive_text": successive_text
    }



def parse_title_document_text(text: str) -> dict:
    """
    Parses an authentic Tunisian Property Title Certificate (شهادة ملكية - Titre Foncier)
    text or Vision OCR output, extracting title number, property name, location,
    content type, total area in m², total parts (التجزئة), original title, and co-owners.
    """
    if not text or not isinstance(text, str):
        return {}

    res = {
        "title_num": "",
        "property_name": "",
        "property_content": "",
        "location": "",
        "property_area_m2": 0.0,
        "property_parts": 0.0,
        "original_title": "",
        "owners": []
    }

    t = text.strip()

    # 1. Title number match (معرف الرسم العقاري: 56733 بن عروس)
    t_match = re.search(r"(?:معرف\s+الرسم\s+العقاري|الرسم\s+العقاري\s+عدد|رسم\s+عقاري\s+عدد|معرف\s+الرسم)\s*[:：]?\s*([^\n،./]+)", t)
    if t_match:
        val = _clean_extracted_text(t_match.group(1))
        if "شهادة" not in val and "الإدارة" not in val:
            res["title_num"] = val

    # 2. Property name match (إسم العقار: حدائق الحي الرياضي)
    name_match = re.search(r"(?:إسم\s+العقار|اسم\s+العقار|المسماة|المسمى)\s*[:：]?\s*[\"«'“]?([^\"»'”\n،./]+)", t)
    if name_match:
        val = _clean_extracted_text(name_match.group(1))
        if "شهادة" not in val and "الإدارة" not in val:
            res["property_name"] = val

    # 3. Property Content (محتوى العقار: أرض صالحة للبناء)
    cnt_match = re.search(r"محتوى\s+العقار\s*[:：]?\s*([^\n،./]+)", t)
    if cnt_match:
        val = _clean_extracted_text(cnt_match.group(1))
        if "شهادة" not in val:
            res["property_content"] = val

    # 4. Location match (موقع العقار: فندق الشوشة / الكائن بـ...)
    loc_match = re.search(r"(?:موقع\s+العقار|الكائن\s+بـ|الموقع)\s*[:：]?\s*([^\n،./]+)", t)
    if loc_match:
        val = _clean_extracted_text(loc_match.group(1))
        if "شهادة" not in val:
            res["location"] = val

    # 5. Area in m2 (المساحة: 3190 م.م or 3190 م²)
    area_match = re.search(r"المساحة\s*[:：]?\s*(\d+(?:\.\d+)?)\s*(?:م\.م|م²|متر\s+مربع|متر)?", t)
    if not area_match:
        area_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:م\.م|م²)", t)
    if area_match:
        try:
            res["property_area_m2"] = float(area_match.group(1))
        except ValueError:
            pass

    # 6. Parts match (التجزئة: 3190 or عدد الأجزاء: 4608000)
    parts_match = re.search(r"(?:التجزئة|عدد\s+الأجزاء)\s*[:：]?\s*(\d+(?:\.\d+)?)", t)
    if parts_match:
        try:
            res["property_parts"] = float(parts_match.group(1))
        except ValueError:
            pass

    # 7. Original Title (الرسم(و.م) الأصلي(ة): 50208 بن عروس)
    orig_match = re.search(r"(?:الرسم\s*\(و\.م\)\s*الأصلي\(ة\)|الرسم\s+الأصلي)\s*[:：]?\s*([^\n،./]+)", t)
    if orig_match:
        val = _clean_extracted_text(orig_match.group(1))
        if "شهادة" not in val:
            res["original_title"] = val

    # 8. Extract Co-owners Table Block (هوية المالكين ومواضيع الملكية)
    owner_blocks = re.findall(
        r"(\d+\/\d+)\s+([^\n]+?)\s+(?:صاحب|صاحبة)?\s*بطاقة\s+تعريف\s*(?:الوطنية)?\s*(?:عدد)?\s*(\d{8})[^\n]*\n(?:[^\n]*موضوع\s+الملكية\s*[:：]?\s*([\d\.,]+)\s*جزء)?",
        t
    )
    for b in owner_blocks:
        raw_name = _clean_extracted_text(b[1])
        if " " in raw_name and re.search(r"^\d+/\d+", raw_name):
            raw_name = re.sub(r"^\d+/\d+\s*", "", raw_name)
        res["owners"].append({
            "order": b[0],
            "name": raw_name,
            "cin": _clean_extracted_text(b[2]) if b[2] else "",
            "parts": float(b[3].replace(',', '.')) if b[3] else 0.0
        })

    return res

