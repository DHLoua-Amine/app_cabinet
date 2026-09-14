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
from math import gcd
from functools import reduce
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

def _lcm(a, b):
    return (a * b) // gcd(a, b) if a and b else a or b

def calculate_lcm_list(numbers):
    return reduce(_lcm, numbers, 1)

class TunisianFaridaEngine:
    """
    Computes Tunisian Farida inheritance shares, base origin (أصل الفريضة),
    mandatory bequest, real estate mapping, and export.
    Uses clean notarial text.
    """

    def _compute_shares(self, heirs_dict: dict, property_area_m2: float = 0.0, property_parts: float = 0.0) -> dict:

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

        # ── 2. MANDATORY BEQUEST (الوصية الواجبة) ──────────────────────────────
        obligatory_bequest_ratio = 0.0
        if predeceased_children > 0:
            obligatory_bequest_ratio = 1.0 / 3.0

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
                fixed_shares['الأب (فرضا وتعصيبا)'] = (1, 6)
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
                    taasib_shares['البنات (مع الإبن تعصيبا)'] = int(one_head_share * daughters_count)
            elif sons_count == 0 and grandsons_count > 0:
                if grandsons_count > 0:
                    taasib_shares['أبناء الابن (ذكور)'] = int(one_head_share * 2 * grandsons_count)
                if granddaughters_count > 0:
                    taasib_shares['بنات الابن (تعصيبا)'] = int(one_head_share * granddaughters_count)
            elif father and sons_count == 0 and grandsons_count == 0:
                taasib_shares['الأب (تعصيبا)'] = int(remaining_shares)
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

        # RESTORATION TO DAUGHTERS & BLOOD RELATIVES (الرد على البنات - الفصل 143 م.أ.ش)
        is_radd = False
        if not is_awl and remaining_shares > 0 and taasib_heads == 0:
            is_radd = True
            if daughters_count > 0:
                if 'البنت' in shares_count:
                    shares_count['البنت (فرضا ورداً - الفصل 143)'] = shares_count.pop('البنت') + remaining_shares
                elif 'البنات' in shares_count:
                    shares_count['البنات (فرضا ورداً - الفصل 143)'] = shares_count.pop('البنات') + remaining_shares

        # ── 11. FINAL RESULTS LIST ─────────────────────────────────────────────
        results_list = []
        if obligatory_bequest_ratio > 0:
            results_list.append({
                "heir": "أولاد الابن/البنت (وصية واجبة - الفصل 191)",
                "shares": "—",
                "base_origin": final_origin,
                "fraction": "1/3 الثلث",
                "percentage": 33.33,
                "area_m2": round(property_area_m2 * (1.0 / 3.0), 2) if property_area_m2 > 0 else 0.0,
                "parts": round(property_parts * (1.0 / 3.0), 2) if property_parts > 0 else 0.0
            })

        for heir, sh in list(shares_count.items()) + list(taasib_shares.items()):
            sh_int = int(sh) if isinstance(sh, (int, float)) and float(sh).is_integer() else sh
            ratio = float(sh) / float(final_origin)
            percentage = ratio * (66.67 if obligatory_bequest_ratio > 0 else 100.0)
            area_m2 = ratio * (property_area_m2 * (2.0/3.0 if obligatory_bequest_ratio > 0 else 1.0))
            parts = ratio * (property_parts * (2.0/3.0 if obligatory_bequest_ratio > 0 else 1.0))

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
                         property_area_m2: float = 0.0, property_parts: float = 0.0,
                         heir_details: dict = None,
                         property_type: str = "مسكن رئيسي",
                         predeceased_death_date: str = "") -> dict:

        res = self._compute_shares(heirs_dict, property_area_m2, property_parts)
        
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
            parts=property_parts,
            heir_details=heir_details,
            property_type=property_type,
            predeceased_death_date=predeceased_death_date
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
            "property_parts": property_parts,
            "heir_details": heir_details or {}
        }

    def _build_notarial_legal_text(self, origin: int, results: list,
                                 contract_type: str = "فريضة شرعية",
                                 applicant_name: str = "", applicant_cin: str = "",
                                 deceased_name: str = "", hujja_num: str = "", hujja_date: str = "", hujja_court: str = "",
                                 title_num: str = "", property_name: str = "", location: str = "",
                                 area_m2: float = 0.0, parts: float = 0.0,
                                 heir_details: dict = None,
                                 property_type: str = "",
                                 predeceased_death_date: str = "") -> str:
        lines = []
        import datetime
        try:
            import office_profile
            prof = office_profile.load()
            name_val = (prof.get("display_name") or prof.get("notary_name") or "").strip()
            notary_title = f"الأستاذ(ة) {name_val}" if name_val else "عدل الإشهاد"
            court_val = (prof.get("court") or "").strip()
            court_str = f" بـ {court_val}" if court_val else ""
        except Exception:
            notary_title = "عدل الإشهاد"
            court_str = ""

        now = datetime.datetime.now()
        date_str = now.strftime("%Y-%m-%d")

        is_partial = (contract_type == "فريضة جزئية")
        contract_title = "فريضة جزئية" if is_partial else "فريضة شرعية"
        
        # 1. Official Notarial Opening
        if "الأستاذ" in notary_title:
            p1 = f"الحمد لله وحده، في يوم [التاريخ] الموافق لـ {date_str}، نحن {notary_title} وجليسه عدلا الإشهاد بدائرة قضاء المحكمة الابتدائية{court_str}."
        else:
            p1 = f"الحمد لله وحده، في يوم [التاريخ] الموافق لـ {date_str}، نحن عدلا الإشهاد بدائرة قضاء المحكمة الابتدائية{court_str}."
        if applicant_name:
            cin_str = f" صاحب(ة) بطاقة التعريف الوطنية عدد {applicant_cin}" if applicant_cin else ""
            p1 += f"\nوبطلب من السيد(ة): {applicant_name}{cin_str}، قصد القيام بـ{contract_title}"
        else:
            p1 += f"\nوبطلب من طالب الإشهاد قصد القيام بـ{contract_title}"
            
        if deceased_name:
            p1 += f" للمتوفى (أو المتوفية): {deceased_name}."
        else:
            p1 += f" للمتوفى (أو المتوفية)."
        lines.append(p1)

        # 2. Real Estate Specification (For Partial Farida)
        if is_partial or title_num or property_name:
            prop_desc = []
            if title_num: prop_desc.append(f"موضوع الرسم العقاري عدد {title_num}")
            if property_name: prop_desc.append(f"المسمى \"{property_name}\"")
            if location: prop_desc.append(f"الكائن بـ {location}")
            if area_m2 > 0: prop_desc.append(f"والبالغ جملة مساحته {area_m2} م²")
            if parts > 0: prop_desc.append(f"والمجزأ إلى {parts} جزءاً")
            
            if prop_desc:
                lines.append(f"موضوع العقار: " + " ".join(prop_desc) + ".")

        if is_partial:
            lines.append("على أن هذه الفريضة الجزئية لا تكون بمعزل عن فريضة كل من الموروثين السابقين وانجرار أصل التركة.")

        # 3. Death Certificate Reference & Heirs Succession
        hujja_parts = []
        if hujja_num: hujja_parts.append(f"عدد {hujja_num}")
        if hujja_court: hujja_parts.append(f"الصادرة عن {hujja_court}")
        if hujja_date: hujja_parts.append(f"بتاريخ {hujja_date}")
        
        hujja_str = " ".join(hujja_parts) if hujja_parts else "المستندة إلى حجة الوفاة الرسمية"
        
        lines.append(f"وحيث ثبتت وفاة الهالك وأحاط بإرثه حسب {hujja_str}، وانحصار ورثته الشرعيين ومناب كل واحد منهم على قاعدة للذكر مثل حظ الأنثيين في الفريضة التوثيقية المخرجة من أصل ({origin}) سهماً كما يلي:")

        # 4. Heir Shares Breakdown (Individually Itemized Rows - No Group Summaries, No Emojis)
        item_counter = 1
        for r in results:
            cnt = r.get("count", 1)
            single_shares = r.get("single_shares", r["shares"])
            single_perc = r.get("single_percentage", r["percentage"])
            single_area = r.get("single_area_m2", 0.0)
            single_parts = r.get("single_parts", 0.0)

            prefix = None
            if "الأبناء" in r['heir'] or ("ابن" in r['heir'] and "ابن الابن" not in r['heir'] and "بنت" not in r['heir']):
                prefix = "son_"
            elif "البنات" in r['heir'] or ("بنت" in r['heir'] and "بنت الابن" not in r['heir']):
                prefix = "daughter_"
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
                for sub_i in range(1, cnt + 1):
                    hk = f"{prefix}{sub_i}"
                    hd = (heir_details or {}).get(hk, {})
                    h_name = hd.get("name", "").strip()
                    h_cin = hd.get("cin", "").strip()
                    h_civ = hd.get("civil_status", "").strip()

                    is_female = (prefix in ["daughter_", "wife_", "granddaughter_", "full_sister_"])
                    owner_word = "صاحبة" if is_female else "صاحب"
                    share_verb = "ينحصر منابها الشرعي" if is_female else "ينحصر منابه الشرعي"
                    area_word = "ومساحتها" if is_female else "ومساحته"
                    parts_word = "ومنابها" if is_female else "ومنابه"

                    label_prefix = "الابن" if prefix == "son_" else ("البنت" if prefix == "daughter_" else ("الزوجة" if prefix == "wife_" else "الوارث"))
                    disp_name = f"{label_prefix} {h_name}" if h_name else f"{label_prefix} {sub_i}"
                    cin_str = ""
                    if h_cin: cin_str += f" ({owner_word} بطاقة التعريف الوطنية عدد {h_cin})"
                    if h_civ: cin_str += f" (ومضمون ولادته/وفاته {h_civ})"

                    line = f"{item_counter}. {disp_name}{cin_str}: {share_verb} في ({single_shares}) سهماً من أصل ({origin}) سهماً، بنسبة (%{single_perc})."
                    if single_area > 0:
                        line += f" {area_word} ({single_area} م²)."
                    if single_parts > 0:
                        line += f" {parts_word} ({single_parts} جزءاً)."
                    lines.append(line)
                    item_counter += 1
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
                owner_word = "صاحبة" if is_female else "صاحب"
                share_verb = "ينحصر منابها الشرعي" if is_female else "ينحصر منابه الشرعي"

                disp_name = f"{r['heir']} {h_name}".strip() if h_name else r['heir']
                cin_str = ""
                if h_cin: cin_str += f" ({owner_word} بطاقة التعريف الوطنية عدد {h_cin})"
                if h_civ: cin_str += f" (ومضمون ولادته/وفاته {h_civ})"

                line = f"{item_counter}. {disp_name}{cin_str}: {share_verb} في ({r['shares']}) سهماً من أصل ({origin}) سهماً، بنسبة (%{r['percentage']})."
                if r.get("area_m2", 0) > 0:
                    line += f" ومساحته(ا) ({r['area_m2']} م²)."
                if r.get("parts", 0) > 0:
                    line += f" ومنابه(ا) ({r['parts']} جزءاً)."
                lines.append(line)
                item_counter += 1

        # 5. Fiscal System & Property Classification
        if property_type == "مسكن رئيسي":
            lines.append("النظام الجبائي والإعفاءات: يستفيد الورثة من الإعفاء الجبائي المقرر للمسكن الرئيسي للمتوفى في حدود ألف متر مربع (1000 م²) طبق أحكام مجلة معاليم التسجيل والطابع الجبائي.")
        elif property_type == "أرض فلاحية":
            lines.append("النظام الجبائي والحيطة: تخضع الفريضة لمقتضيات الحفاظ على الأراضي الفلاحية والمساحات المسقية وقوانين التجزئة الفلاحية.")

        # 6. Official Closing & Draft Registry Book Recording
        lines.append(
            "هذا ما تم تلقيه وتلي على الحاضرين فوافقوا وأمضوا ورسم بدفتر مسودات أولهما صحيفة............ "
            "تحت عدد............ أجره والمصاريف القانونية مستوفاة والله الموفق."
        )
        return "\n\n".join(lines)

    def export_farida_docx(self, result: dict, output_path: str):
        """Generates an official notary Word document for the Farida calculation matching authentic notary standards."""
        doc = docx.Document()

        sections = doc.sections
        for section in sections:
            section.top_margin = Inches(0.8)
            section.bottom_margin = Inches(0.8)
            section.left_margin = Inches(0.8)
            section.right_margin = Inches(0.8)
            try:
                import docx_generator
                docx_generator.set_section_rtl(section)
            except Exception:
                pass

        # ── 1. OFFICIAL NOTARY OFFICE HEADER ─────────────────────────────────
        try:
            import office_profile
            prof = office_profile.load()
            notary_name = (prof.get("notary_name") or "مكتب عدل الإشهاد").strip()
            office_addr = (prof.get("office_address") or "").strip()
            office_phone = (prof.get("phone") or "").strip()
        except Exception:
            notary_name = "مكتب عدل الإشهاد"
            office_addr = ""
            office_phone = ""

        # Top Header Table (Bilingual Notary Header)
        header_table = doc.add_table(rows=1, cols=2)
        header_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        try:
            import docx_generator
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

        # ── 3. REAL ESTATE DETAILS (IF APPLICABLE) ───────────────────────────
        if result.get("property_area_m2", 0) > 0 or result.get("property_parts", 0) > 0:
            h1 = doc.add_heading("أولاً - بيان بيانات العقار والتجزئة:", level=2)
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
        h2 = doc.add_heading(f"جدول توزيع المنابات والأنصبة الشرعية (أصل الفريضة: {result.get('base_origin')} سهماً):", level=2)
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
        headers = ["الوارث الشرعي", "عدد السهام", "الفك والكسر", "النسبة %", "مناب العقار والأجزاء"]
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
    cleaned = cleaned.strip(" :：\n\t\"'")
    return cleaned


def parse_hujjat_wafat_text(text: str) -> dict:
    """
    Parses a Hujjat Wafat / Death Certificate text (or Vision OCR result)
    extracting surviving heirs from clauses like:
    "وقد تركت : ابنيها من زوجها المتوفى قبلها الطاهر الثوشاني وهما الرشيدين سعاد وجلول ومن غير الوارث عادل والوارث لا غير..."
    
    Returns a dictionary ready for calculate_farida!
    """
    if not text or not isinstance(text, str):
        return {}

    t = text.strip()
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
        'names': [],
        'deceased_name': '',
        'deceased_lakab': '',
        'husband_name': '',
        'wife_name': '',
        'applicant_name': '',
        'applicant_cin': '',
        'hujja_num': '',
        'hujja_date': '',
        'hujja_court': ''
    }

    import re, json

    # 0. Check if AI Vision returned JSON block inside text
    if '{' in t and '}' in t:
        try:
            m_json = re.search(r'\{.*\}', t, re.DOTALL)
            if m_json:
                data = json.loads(m_json.group(0))
                if isinstance(data, dict):
                    if 'sons_count' in data: heirs['sons_count'] = int(data['sons_count'])
                    if 'daughters_count' in data: heirs['daughters_count'] = int(data['daughters_count'])
                    if 'husband_alive' in data: heirs['husband'] = bool(data['husband_alive'])
                    if 'wife_alive' in data: heirs['wife'] = bool(data['wife_alive'])
                    if 'father_alive' in data: heirs['father'] = bool(data['father_alive'])
                    if 'mother_alive' in data: heirs['mother'] = bool(data['mother_alive'])
                    if 'deceased_name' in data: heirs['deceased_name'] = _clean_extracted_text(data['deceased_name'])
                    if 'wife_name' in data: heirs['wife_name'] = _clean_extracted_text(data['wife_name'])
                    if 'husband_name' in data: heirs['husband_name'] = _clean_extracted_text(data['husband_name'])
                    if 'applicant_name' in data: heirs['applicant_name'] = _clean_extracted_text(data['applicant_name'])
                    if 'hujja_date' in data: heirs['hujja_date'] = _clean_extracted_text(data['hujja_date'])
                    if heirs['sons_count'] > 0 or heirs['daughters_count'] > 0 or heirs['husband'] or heirs['wife']:
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
            if m_wife: heirs['wife_name'] = _clean_extracted_text(m_wife.group(1))
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

    # Common female names in Tunisia & feminine gender endings
    female_names = {'سعاد', 'فاطمة', 'مريم', 'عائشة', 'أميرة', 'اميرة', 'نادرة', 'سارة', 'ليلى', 'منيرة', 'وسيلة', 'نعيمة', 'خديجة', 'زينب', 'لطيفة', 'سامية', 'سلمى', 'هناء', 'رباب', 'نجلاء', 'سميرة', 'جنات', 'آسية', 'اسية', 'سمية', 'إلهام', 'الهام', 'حياة', 'نبيلة', 'جميلة', 'سليمة', 'مبروكة', 'صالحة', 'وجدان', 'فوزية', 'عزيزة', 'رفيقه', 'رفيقة', 'عزة', 'مامييه', 'مبروكه'}

    # Extract non-heir names (predeceased husband/wife names & explicitly excluded non-inheritors)
    non_heir_names = {'الرشداء', 'البالغين', 'المذكورين', 'وهم', 'منها', 'منه', 'غير', 'لاغير', 'لا', 'التركة', 'المحيطين', 'بإرثه', 'بارثه', 'الذين', 'تصادقا'}
    for m in re.finditer(r"(?:زوجها\s+(?:المتوفى|الهالك)\s+قبلها|زوجته\s+(?:المتوفاة|الهالكة)\s+قبله|من\s+غير\s+الوارث)\s+([^\s،.]+)", clause_text):
        non_heir_names.add(m.group(1).strip())

    # Extract deceased name & family surname / lakab (ولقبه/ولقبها)
    if not heirs['deceased_name']:
        clean_text_for_dec = re.sub(r'اسم\s+الأم\s+ولقبها\s*[:：]?\s*[^\n،.]+', '', t)
        clean_text_for_dec = re.sub(r'زوج(?:ها|ته)\s+(?:المتوفى|المتوفاة|الهالك|الهالكة)\s+(?:قبلها|قبله)\s+[^\n،.]+', '', clean_text_for_dec)
        
        m_dec = re.search(r"(?:إقامة\s+حجة\s+وفاة\s+|نقرر\s+إقامة\s+حجة\s+وفاة\s+|اسم\s+)?(?:الهالك|الهالكة|المرحوم|المرحومة|المتوفى|المتوفاة|الموروث|الموروثة)(?:ة|\(ة\))?\s*[:：]?\s*([^\n،.:]+)", clean_text_for_dec)
        if m_dec:
            raw_dec = m_dec.group(1).strip()
            raw_dec = re.split(r"(?:\s+ولقبه|\s+اسم\s+الأم|\s+المتوفي|\s+المتوفى|\s+حسب|\s+جنسيته)", raw_dec)[0]
            heirs['deceased_name'] = _clean_extracted_text(raw_dec)

    m_lakab = re.search(r"ولقبه(?:ا)?\s*[:：]?\s*([^\s،.\n]+)", t)
    deceased_lakab = _clean_extracted_text(m_lakab.group(1)) if m_lakab else ""
    if not deceased_lakab and heirs['deceased_name']:
        dec_parts = heirs['deceased_name'].split()
        if len(dec_parts) > 1 and "بن" not in dec_parts[-1] and "بنت" not in dec_parts[-1]:
            deceased_lakab = dec_parts[-1]
    heirs['deceased_lakab'] = deceased_lakab

    # 3. Children list parsing (e.g. وأبناؤه منها الرشداء وهم : رفيقه / جمال / أحمد / أميرة / منصور / عزة لا غير)
    t_norm = re.sub(r'[أإآ]', 'ا', t)
    clause_norm = re.sub(r'[أإآ]', 'ا', clause_text)
    kids_match = re.search(r"(?:و?ابنا[ؤئءه]ه|و?ابنائه|و?ابنائها|و?ابناؤها|و?اولاده|و?اولادها|و?ورثته|و?خلفاؤه|و?خلفائه).*?وهم\s*[:：]?\s*(.+?)\s*(?:لا\s+غير|\s+غير|\s+المحل|\.\/\.|\n|$)", clause_norm)
    if not kids_match:
        kids_match = re.search(r"وهما\s+(?:الرشيدين|البالغين|المذكورين)?\s*([^\n،.]+?)(?:ومن\s+غير|\s+والوارث|ولم|$)", clause_norm)

    if kids_match:
        raw_phrase = kids_match.group(1)
        raw_list = [_clean_extracted_text(n.strip()) for n in re.split(r"[/،,]+|\s+و\s+", raw_phrase) if n.strip()]
        valid_names = [n for n in raw_list if n and len(n) > 1 and n not in non_heir_names]
        if valid_names:
            heirs['sons_count'] = 0
            heirs['daughters_count'] = 0
            heirs['names'] = []
            male_exceptions = {'حمزة', 'عطية', 'طه', 'وجيه', 'قتادة', 'أسامة', 'اسامة', 'عبيدة', 'عمران'}
            for name in valid_names:
                clean_n = re.sub(r'[أإآ]', 'ا', name)
                if name not in male_exceptions and clean_n not in male_exceptions and (name in female_names or clean_n in female_names or name.endswith('ة') or name.endswith('ه') or name.endswith('اء')):
                    heirs['daughters_count'] += 1
                else:
                    heirs['sons_count'] += 1
                
                # Append father's family surname (lakab) if available
                if deceased_lakab and not name.endswith(deceased_lakab):
                    full_child_name = f"{name} {deceased_lakab}"
                else:
                    full_child_name = name
                heirs['names'].append(full_child_name)

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
            sons_part = re.split(r"(بناته?|بناتها|ابنته|بنته)", sons_match.group(2))[0]
            stop_words = {"الذكر", "مثل", "حظ", "الأنثيين", "وهم", "وهن", "منها", "منه", "غير", "التركة", "ابن", "إبن", "ابنه"}
            s_names = [n.strip() for n in re.split(r"[،,و\s]+", sons_part) if len(n.strip()) > 2 and n.strip() not in stop_words and n.strip() not in non_heir_names]
            if len(s_names) > 0:
                heirs['sons_count'] = len(s_names)
                heirs['names'].extend(s_names)

        daug_match = re.search(r"(بناته?|بناتها|بناتهن|ابنته|إبنته|بنته)\s*(?:منه|منها)?\s*[:：]?\s*([^،.\n]+)", clause_text)
        if daug_match:
            stop_words = {"الذكر", "مثل", "حظ", "الأنثيين", "وهم", "وهن", "منها", "منه", "غير", "التركة", "بنت", "بنته"}
            daug_part = re.split(r"(أبناؤه?|أبنائه?|إبنه|ابنه|أولاده)", daug_match.group(2))[0]
            d_names = [n.strip() for n in re.split(r"[،,و\s]+", daug_part) if len(n.strip()) > 2 and n.strip() not in stop_words and n.strip() not in non_heir_names]
            if len(d_names) > 0:
                heirs['daughters_count'] = len(d_names)

    # 5. Extract metadata (Deceased name, Court from top right, Case File Num from top left, Date)
    heirs['applicant_name'] = ""
    heirs['applicant_cin'] = ""

    if not heirs['deceased_name']:
        clean_text_for_dec = re.sub(r'اسم\s+الأم\s+ولقبها\s*[:：]?\s*[^\n،.]+', '', t)
        clean_text_for_dec = re.sub(r'زوج(?:ها|ته)\s+(?:المتوفى|المتوفاة|الهالك|الهالكة)\s+(?:قبلها|قبله)\s+[^\n،.]+', '', clean_text_for_dec)
        
        m_dec = re.search(r"(?:إقامة\s+حجة\s+وفاة\s+|نقرر\s+إقامة\s+حجة\s+وفاة\s+|اسم\s+)?(?:الهالك|الهالكة|المرحوم|المرحومة|المتوفى|المتوفاة|الموروث|الموروثة)(?:ة|\(ة\))?\s*[:：]?\s*([^\n،.:]+)", clean_text_for_dec)
        if m_dec:
            raw_dec = m_dec.group(1).strip()
            raw_dec = re.split(r"(?:\s+ولقبه|\s+اسم\s+الأم|\s+المتوفي|\s+المتوفى|\s+حسب|\s+جنسيته)", raw_dec)[0]
            heirs['deceased_name'] = _clean_extracted_text(raw_dec)

    # Top right header: Court of Jurisdiction (محكمة ناحية... / المحكمة الابتدائية...)
    if not heirs['hujja_court']:
        m_crt = re.search(r"(?:الجمهورية\s+التونسية\s+)?(?:وزارة\s+العدل\s+)?(محكمة\s+(?:الناحية|ناحية|الابتدائية)\s+[^\n،.]+)", t[:500])
        if not m_crt:
            m_crt = re.search(r"(محكمة\s+(?:الناحية|ناحية|الابتدائية)\s+[^\n،.]+)", t)
        if m_crt: heirs['hujja_court'] = _clean_extracted_text(m_crt.group(1))

    # Top left: Case File Number (عدد الملف / عدد المادة / عدد...)
    if not heirs['hujja_num']:
        m_num = re.search(r"(?:عدد\s+الملف|عدد\s+المادة|ملف\s+عدد|عدد)\s*[:：]?\s*([\d\/]+)", t)
        if not m_num:
            m_num = re.search(r"\b(\d+\/\d{4})\b", t)
        if m_num: heirs['hujja_num'] = _clean_extracted_text(m_num.group(1))

    if not heirs['hujja_date']:
        m_dt = re.search(r"بتاريخ\s*[:：]?\s*(\d{2}-\d{2}-\d{4}|\d{4}-\d{2}-\d{2})", t)
        if not m_dt:
            m_dt = re.search(r"حرر\s+(?:بتونس|في)\s+([^\n،.]+)", t)
        if m_dt: heirs['hujja_date'] = _clean_extracted_text(m_dt.group(1))
        m_dt = re.search(r"حرر\s+(?:بتونس|في)\s+([^\n،.]+)", t)
    if m_dt: heirs['hujja_date'] = _clean_extracted_text(m_dt.group(1))

    heirs['names'] = list(dict.fromkeys([_clean_extracted_text(n) for n in heirs['names'] if _clean_extracted_text(n)]))

    return heirs


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

