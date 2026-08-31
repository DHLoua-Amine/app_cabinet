"""
farida_engine.py — Official Tunisian Legal Inheritance Calculator Engine
Compliant with the Tunisian Code of Personal Status (مجلة الأحوال الشخصية التونسية - الفصول 85-192).

Features:
1. Exact Shares Calculation (الفروض والأنصبة الشرعية)
2. Pre-estate Deductions (الخصوم والديون ومصاريف الجنازة قبل قسمة التركة - الفصل 87 م.أ.ش)
3. Mandatory Bequest (الوصية الواجبة لأولاد الابن وأولاد البنت - الفصلان 191 و 192 م.أ.ش)
4. Real Estate Surface & Parts Mapping (توزيع مناب العقار بالأمتار المربعة والأجزاء)
5. Deficit Awl (العول) & Surplus Restoration (الرد على البنات والفروع - الفصل 143 م.أ.ش)
6. Direct Generation of Notarial Deed Text (صياغة نص الفريضة لعدول الإشهاد)
7. Professional DOCX Export for Office Archive (تصدير الفريضة لملف Word رسمية)
"""

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
    pre-estate deductions, obligatory bequest, real estate mapping, and export.
    Uses TND currency format and clean notarial text.
    """

    def calculate_farida(self, heirs_dict: dict, gross_estate: float = 0.0,
                         funeral_expenses: float = 0.0, debts: float = 0.0,
                         property_area_m2: float = 0.0, property_parts: float = 0.0) -> dict:

        # ── 1. DEDUCTIONS & NET ESTATE ─────────────────────────────────────────
        total_deductions = max(0.0, float(funeral_expenses)) + max(0.0, float(debts))
        net_estate = max(0.0, float(gross_estate) - total_deductions)

        # ── 2. CLEAN INPUTS ───────────────────────────────────────────────────
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
        uncle_full = heirs_dict.get('uncle_full', False)
        uncle_pat = heirs_dict.get('uncle_pat', False)
        cousin_full_count = max(0, int(heirs_dict.get('cousin_full_count', 0)))
        cousin_pat_count = max(0, int(heirs_dict.get('cousin_pat_count', 0)))

        predeceased_children = max(0, int(heirs_dict.get('predeceased_children_count', 0)))

        has_descendants = (sons_count > 0 or daughters_count > 0 or grandsons_count > 0 or granddaughters_count > 0)
        has_male_descendants = (sons_count > 0 or grandsons_count > 0)

        fixed_shares = {}

        # ── 3. MANDATORY BEQUEST (الوصية الواجبة) ──────────────────────────────
        obligatory_bequest_amount = 0.0
        estate_for_heirs = net_estate
        if predeceased_children > 0 and net_estate > 0:
            obligatory_bequest_amount = net_estate * (1.0 / 3.0)
            estate_for_heirs = net_estate - obligatory_bequest_amount

        # ── 4. SPOUSE ──────────────────────────────────────────────────────────
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

        # ── 5. MOTHER & GRANDMOTHERS ──────────────────────────────────────────
        num_siblings = full_brothers_count + full_sisters_count + pat_brothers_count + pat_sisters_count + mat_siblings_count
        if mother:
            if has_descendants or num_siblings >= 2:
                fixed_shares['الأم'] = (1, 6)
            else:
                fixed_shares['الأم'] = (1, 3)
        else:
            if maternal_grandmother or paternal_grandmother:
                fixed_shares['الجدة'] = (1, 6)

        # ── 6. FATHER & GRANDFATHER ─────────────────────────────────────────
        if father:
            if has_male_descendants:
                fixed_shares['الأب (فرضا)'] = (1, 6)
            elif daughters_count > 0 or granddaughters_count > 0:
                fixed_shares['الأب (فرضا وتعصيبا)'] = (1, 6)
        elif paternal_grandfather:
            if has_male_descendants:
                fixed_shares['الجد لأب'] = (1, 6)

        # ── 7. DAUGHTERS & GRANDDAUGHTERS ─────────────────────────────────────
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

        # ── 8. MATERNAL SIBLINGS (الإخوة لأم) ──────────────────────────────────
        if mat_siblings_count > 0 and sons_count == 0 and grandsons_count == 0 and not father and not paternal_grandfather:
            if mat_siblings_count == 1:
                fixed_shares['الأخ/الأخت لأم'] = (1, 6)
            else:
                fixed_shares['الإخوة والأخوات لأم'] = (1, 3)

        # ── 9. FULL & PATERNAL SISTERS ─────────────────────────────────────────
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

        # ── 10. CALCULATE BASE ORIGIN & AWL ───────────────────────────────────
        denominators = [d for n, d in fixed_shares.values()]
        base_origin = calculate_lcm_list(denominators) if denominators else 24

        shares_count = {}
        total_fixed_shares = 0
        for heir, (num, den) in fixed_shares.items():
            sh = (num * base_origin) // den
            shares_count[heir] = sh
            total_fixed_shares += sh

        is_awl = total_fixed_shares > base_origin
        final_origin = total_fixed_shares if is_awl else base_origin
        remaining_shares = max(0, base_origin - total_fixed_shares)

        # ── 11. TAASIB & EXTENDED AGNATES (العصوبة بالذات وبالغير) ──────────────
        taasib_shares = {}
        
        if sons_count > 0:
            total_heads = (sons_count * 2) + daughters_count
            if total_heads > 0 and remaining_shares > 0:
                head_value = remaining_shares / float(total_heads)
                if sons_count > 0:
                    taasib_shares['الأبناء (ذكور)'] = round(head_value * 2 * sons_count, 2)
                if daughters_count > 0:
                    taasib_shares['البنات (مع الإبن تعصيبا)'] = round(head_value * daughters_count, 2)
                remaining_shares = 0

        elif sons_count == 0 and grandsons_count > 0:
            total_heads = (grandsons_count * 2) + granddaughters_count
            if total_heads > 0 and remaining_shares > 0:
                head_value = remaining_shares / float(total_heads)
                if grandsons_count > 0:
                    taasib_shares['أبناء الابن (ذكور)'] = round(head_value * 2 * grandsons_count, 2)
                if granddaughters_count > 0:
                    taasib_shares['بنات الابن (تعصيبا)'] = round(head_value * granddaughters_count, 2)
                remaining_shares = 0

        elif father and sons_count == 0 and grandsons_count == 0:
            if remaining_shares > 0:
                taasib_shares['الأب (تعصيبا)'] = remaining_shares
                remaining_shares = 0

        elif sons_count == 0 and grandsons_count == 0 and not father and full_brothers_count > 0:
            total_heads = (full_brothers_count * 2) + full_sisters_count
            if total_heads > 0 and remaining_shares > 0:
                head_value = remaining_shares / float(total_heads)
                if full_brothers_count > 0:
                    taasib_shares['الإخوة الأشقاء'] = round(head_value * 2 * full_brothers_count, 2)
                if full_sisters_count > 0:
                    taasib_shares['الأخوات الشقيقات'] = round(head_value * full_sisters_count, 2)
                remaining_shares = 0

        elif sons_count == 0 and grandsons_count == 0 and not father and full_brothers_count == 0 and pat_brothers_count > 0:
            total_heads = (pat_brothers_count * 2) + pat_sisters_count
            if total_heads > 0 and remaining_shares > 0:
                head_value = remaining_shares / float(total_heads)
                if pat_brothers_count > 0:
                    taasib_shares['الإخوة لأب'] = round(head_value * 2 * pat_brothers_count, 2)
                if pat_sisters_count > 0:
                    taasib_shares['الأخوات لأب'] = round(head_value * pat_sisters_count, 2)
                remaining_shares = 0

        # EXTENDED AGNATES (أبناء الإخوة والعمومة عصبة بالنفس)
        elif remaining_shares > 0 and sons_count == 0 and grandsons_count == 0 and not father and not paternal_grandfather and full_brothers_count == 0 and pat_brothers_count == 0:
            if nephew_full_count > 0:
                taasib_shares[f'أبناء الأخ الشقيق (عدد {nephew_full_count})'] = remaining_shares
                remaining_shares = 0
            elif nephew_pat_count > 0:
                taasib_shares[f'أبناء الأخ لأب (عدد {nephew_pat_count})'] = remaining_shares
                remaining_shares = 0
            elif uncle_full:
                taasib_shares['العم الشقيق'] = remaining_shares
                remaining_shares = 0
            elif uncle_pat:
                taasib_shares['العم لأب'] = remaining_shares
                remaining_shares = 0
            elif cousin_full_count > 0:
                taasib_shares[f'أبناء العم الشقيق (عدد {cousin_full_count})'] = remaining_shares
                remaining_shares = 0
            elif cousin_pat_count > 0:
                taasib_shares[f'أبناء العم لأب (عدد {cousin_pat_count})'] = remaining_shares
                remaining_shares = 0

        # RESTORATION TO DAUGHTERS & BLOOD RELATIVES (الرد على البنات - الفصل 143 م.أ.ش)
        is_radd = False
        if not is_awl and remaining_shares > 0 and sons_count == 0 and grandsons_count == 0 and not father and full_brothers_count == 0 and pat_brothers_count == 0:
            is_radd = True
            if daughters_count > 0:
                if 'البنت' in shares_count:
                    shares_count['البنت (فرضا ورداً - الفصل 143)'] = shares_count.pop('البنت') + remaining_shares
                elif 'البنات' in shares_count:
                    shares_count['البنات (فرضا ورداً - الفصل 143)'] = shares_count.pop('البنات') + remaining_shares
                remaining_shares = 0

        # ── 11. FINAL RESULTS LIST ─────────────────────────────────────────────
        results_list = []
        if obligatory_bequest_amount > 0:
            results_list.append({
                "heir": "أولاد الابن/البنت (وصية واجبة - الفصل 191)",
                "shares": "—",
                "base_origin": final_origin,
                "fraction": "1/3 الثلث",
                "percentage": 33.33,
                "amount": round(obligatory_bequest_amount, 3),
                "area_m2": round(property_area_m2 * (1.0 / 3.0), 2) if property_area_m2 > 0 else 0.0,
                "parts": round(property_parts * (1.0 / 3.0), 2) if property_parts > 0 else 0.0
            })

        for heir, sh in list(shares_count.items()) + list(taasib_shares.items()):
            ratio = sh / float(final_origin)
            percentage = ratio * (66.67 if obligatory_bequest_amount > 0 else 100.0)
            amount = ratio * estate_for_heirs
            area_m2 = ratio * (property_area_m2 * (2.0/3.0 if obligatory_bequest_amount > 0 else 1.0))
            parts = ratio * (property_parts * (2.0/3.0 if obligatory_bequest_amount > 0 else 1.0))

            count = 1
            if "الأبناء" in heir:
                count = sons_count
            elif "البنات" in heir:
                count = daughters_count
            elif "الإخوة الأشقاء" in heir:
                count = full_brothers_count
            elif "الأخوات الشقيقات" in heir:
                count = full_sisters_count

            single_sh = round(sh / float(count), 3) if count > 0 else sh
            single_percentage = round(percentage / float(count), 2) if count > 0 else percentage
            single_amount = round(amount / float(count), 3) if count > 0 else amount
            single_area_m2 = round(area_m2 / float(count), 2) if count > 0 else area_m2
            single_parts = round(parts / float(count), 2) if count > 0 else parts

            results_list.append({
                "heir": heir,
                "count": count,
                "shares": sh,
                "single_shares": single_sh,
                "base_origin": final_origin,
                "fraction": f"{sh}/{final_origin}",
                "percentage": round(percentage, 2),
                "single_percentage": single_percentage,
                "amount": round(amount, 3),
                "single_amount": single_amount,
                "area_m2": round(area_m2, 2),
                "single_area_m2": single_area_m2,
                "parts": round(parts, 2),
                "single_parts": single_parts
            })

        legal_summary_text = self._build_notarial_legal_text(
            gross_estate, total_deductions, net_estate, final_origin, results_list, property_area_m2, property_parts
        )

        return {
            "gross_estate": gross_estate,
            "funeral_expenses": funeral_expenses,
            "debts": debts,
            "total_deductions": total_deductions,
            "net_estate": net_estate,
            "base_origin": final_origin,
            "is_awl": is_awl,
            "is_radd": is_radd,
            "heirs_summary": results_list,
            "legal_notarial_text": legal_summary_text,
            "property_area_m2": property_area_m2,
            "property_parts": property_parts
        }

    def _build_notarial_legal_text(self, gross: float, deductions: float, net: float, origin: int, results: list, area_m2: float, parts: float) -> str:
        lines = []
        if gross > 0:
            lines.append(f"أولاً - التركة والتكاليف: بلغت التركة الجملية للهالك ({gross:,.3f} TND)، وبعد طرح التكاليف والديون ومصاريف الجنازة المقدرة بـ ({deductions:,.3f} TND)، استقر صافي التركة المعد للقسمة على ({net:,.3f} TND).")
        lines.append(f"ثانياً - انحصار الورثة والفريضة: ثبتت وفاة الهالك وانحصار ورثته الشرعيين ومناب كل واحد منهم في الفريضة التوثيقية المخرجة من أصل ({origin}) سهماً كما يلي:")
        
        for r in results:
            cnt = r.get("count", 1)
            if cnt > 1:
                unit_label = "لكل ابن واحد" if "الأبناء" in r['heir'] else ("لكل بنت واحدة" if "البنات" in r['heir'] else f"لكل فرد - عدد {cnt}")
                item_str = f"• {r['heir']} (عدد {cnt}): استحق {unit_label} ({r['single_shares']}) سهماً من أصل ({origin}) سهماً بنسبة ({r['single_percentage']}%)، وبما يعادل مبلغ ({r['single_amount']:,.3f} TND)."
                if area_m2 > 0:
                    item_str += f" ومساحة ({r['single_area_m2']} م² {unit_label}). ومناب المجموع الجملي ({r['area_m2']} م²)."
                if parts > 0:
                    item_str += f" ومناب ({r['single_parts']} جزءاً {unit_label})."
            else:
                item_str = f"• {r['heir']}: استحق ({r['shares']}) سهماً من أصل ({origin}) سهماً بنسبة ({r['percentage']}%)، وبما يعادل مبلغ ({r['amount']:,.3f} TND)."
                if area_m2 > 0:
                    item_str += f" ومساحة ({r['area_m2']} م²)."
                if parts > 0:
                    item_str += f" ومناب ({r['parts']} جزءاً من رسم التجزئة)."
            lines.append(item_str)

        lines.append("وعليه استقرت الفريضة التوثيقية التونسية وتم توزيع التركة طبقا للأحكام الشرعية والقانونية والله الموفق.")
        return "\n".join(lines)

    def export_farida_docx(self, result: dict, output_path: str):
        """Generates an official notary Word document for the Farida calculation."""
        doc = docx.Document()

        sections = doc.sections
        for section in sections:
            section.top_margin = Inches(0.8)
            section.bottom_margin = Inches(0.8)
            section.left_margin = Inches(0.8)
            section.right_margin = Inches(0.8)

        title_p = doc.add_paragraph()
        title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = title_p.add_run("الجمهورية التونسية\nمكتب عدل الإشهاد\nحجة وفاة وإشهاد بالفريضة الشرعية")
        run.bold = True
        run.font.size = Pt(16)
        run.font.name = "Traditional Arabic"
        run.font.color.rgb = RGBColor(15, 23, 42)

        doc.add_paragraph("─" * 45).alignment = WD_ALIGN_PARAGRAPH.CENTER

        doc.add_heading("1. بيان التركة والتكاليف والديون:", level=2)
        p_info = doc.add_paragraph()
        p_info.add_run(f"• إجمالي التركة الجملي: {result.get('gross_estate', 0):,.3f} TND\n")
        p_info.add_run(f"• مصاريف الجنازة والديون: {result.get('total_deductions', 0):,.3f} TND\n")
        p_info.add_run(f"• صافي التركة المستحقة للقسمة: {result.get('net_estate', 0):,.3f} TND\n").bold = True

        doc.add_heading(f"2. جدول توزيع السهام (أصل الفريضة: {result.get('base_origin')} سهماً):", level=2)
        summary = result.get("heirs_summary", [])
        
        table = doc.add_table(rows=1, cols=6)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        hdr_cells = table.rows[0].cells
        headers = ["الوارث الشرعي", "السهام", "المخرج", "النسبة", "المبلغ بالدينار", "المناب بالعقار"]
        for i, h_text in enumerate(headers):
            hdr_cells[i].text = h_text
            hdr_cells[i].paragraphs[0].runs[0].font.bold = True
            hdr_cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

        for item in summary:
            row_cells = table.add_row().cells
            row_cells[0].text = str(item["heir"])
            row_cells[1].text = str(item["shares"])
            row_cells[2].text = str(item["fraction"])
            row_cells[3].text = f"%{item['percentage']}"
            row_cells[4].text = f"{item['amount']:,.3f} TND"
            
            prop_str = ""
            if item.get("area_m2", 0) > 0:
                prop_str += f"{item['area_m2']} م²"
            if item.get("parts", 0) > 0:
                prop_str += f" | {item['parts']} جزء"
            row_cells[5].text = prop_str if prop_str else "—"

        doc.add_heading("3. النص التوثيقي الرسمي لحجة الوفاة:", level=2)
        p_deed = doc.add_paragraph(result.get("legal_notarial_text", ""))
        p_deed.style.font.size = Pt(12)
        p_deed.style.font.name = "Traditional Arabic"

        doc.add_paragraph("\n\nعدلا الإشهاد                                   طالب الإشهاد").alignment = WD_ALIGN_PARAGRAPH.RIGHT

        doc.save(output_path)

