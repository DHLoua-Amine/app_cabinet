"""
docx_generator.py — Module for generating perfectly formatted Microsoft Word (.docx) 
notary deeds matching official Tunisian Notary typography standards (عدول الإشهاد).
"""

import os
import re
from pathlib import Path

try:
    import docx
    from docx.shared import Pt, Inches, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.style import WD_STYLE_TYPE
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False


def set_rtl(paragraph):
    """Sets Right-to-Left paragraph formatting for Arabic text in docx."""
    pPr = paragraph._p.get_or_add_pPr()
    bidi = OxmlElement('w:bidi')
    bidi.set(qn('w:val'), '1')
    pPr.append(bidi)


def set_run_font(run, font_name="Simplified Arabic", size_pt=14, bold=False, color_rgb=(0, 0, 0)):
    """Sets exact font, size, weight, and bidi properties for a run of Arabic text."""
    run.font.name = font_name
    run.font.size = Pt(size_pt)
    run.bold = bold
    if color_rgb:
        run.font.color.rgb = RGBColor(*color_rgb)
    
    # Force Arabic CS font name in XML
    rPr = run._r.get_or_add_rPr()
    rFonts = OxmlElement('w:rFonts')
    rFonts.set(qn('w:ascii'), font_name)
    rFonts.set(qn('w:hAnsi'), font_name)
    rFonts.set(qn('w:cs'), font_name)
    rPr.append(rFonts)


def format_legal_paragraph(paragraph, text, font_name="Simplified Arabic", base_size=14):
    """
    Parses text and applies bolding to key legal keywords (e.g. الطرف الأول, الفصل الأول...)
    and sets Full Justification and RTL alignment.
    """
    set_rtl(paragraph)
    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    paragraph.paragraph_format.line_spacing = 1.15
    paragraph.paragraph_format.space_after = Pt(4)
    paragraph.paragraph_format.space_before = Pt(0)

    # Keywords to auto-bold in legal text
    bold_patterns = r"(الطرف الأول[^\:\n]*\:|الطرف الثاني[^\:\n]*\:|الفصل الأول[^\:\n]*\:|الفصل الثاني[^\:\n]*\:|الفصل الثالث[^\:\n]*\:|الفصل الرابع[^\:\n]*\:|الفصل الخامس[^\:\n]*\:|الفصل السادس[^\:\n]*\:|الفصل السابع[^\:\n]*\:|الفصل الثامن[^\:\n]*\:|الحمد لله|موضوع العقار|ثمن البيع|التزام|إشهاد)"
    
    parts = re.split(bold_patterns, text)
    for part in parts:
        if not part:
            continue
        is_bold_keyword = bool(re.match(bold_patterns, part))
        run = paragraph.add_run(part)
        set_run_font(run, font_name=font_name, size_pt=base_size, bold=is_bold_keyword)


def create_notary_deed_docx(contract_title: str, contract_text: str, output_path: str) -> bool:
    """
    Generates a beautifully formatted Microsoft Word (.docx) document 
    matching official Tunisian notary deed typography.
    """
    if not DOCX_AVAILABLE:
        print("[DOCX Generator] python-docx not installed.")
        return False

    doc = docx.Document()
    
    # Page Margins (Normal 1 inch / 2.54 cm)
    sections = doc.sections
    for section in sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)

    # Title / Header
    if contract_title:
        title_p = doc.add_paragraph()
        set_rtl(title_p)
        title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        title_p.paragraph_format.space_after = Pt(12)
        run = title_p.add_run(contract_title)
        set_run_font(run, font_name="Simplified Arabic", size_pt=18, bold=True)

    # Process paragraphs
    lines = contract_text.split("\n")
    for line in lines:
        clean_line = line.strip()
        if not clean_line:
            continue
        p = doc.add_paragraph()
        format_legal_paragraph(p, clean_line, font_name="Simplified Arabic", base_size=14)

    doc.save(output_path)
    print(f"[DOCX Generator] Created: {output_path}")
    return True
