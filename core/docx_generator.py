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


# Chaine de repli des polices arabes, de la plus souhaitable a la plus sure.
#
# « Simplified Arabic » etait ecrite en dur. Elle est livree avec Microsoft
# Office, PAS avec Windows : sur le poste d'un notaire sans Office, Word
# substituait une police au hasard. Le texte restait juste — un .docx stocke
# de l'Unicode, jamais des glyphes — mais l'acte ne ressemblait plus a rien.
#
# On choisit donc, au moment de generer, la premiere police REELLEMENT
# installee sur la machine du notaire. Arial ferme la marche : presente sur
# tout Windows depuis toujours, et correcte en arabe.
CHAINE_POLICES_ARABES = (
    "Simplified Arabic",
    "Traditional Arabic",
    "Arabic Typesetting",
    "Amiri",
    "Segoe UI",
    "Arial",
)

_police_retenue = None


def polices_installees():
    """Noms des polices connues de Windows, en minuscules."""
    noms = set()
    try:
        import winreg
        for ruche, chemin in ((winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
                              (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts")):
            try:
                with winreg.OpenKey(ruche, chemin) as k:
                    for i in range(winreg.QueryInfoKey(k)[1]):
                        nom = winreg.EnumValue(k, i)[0]
                        noms.add(nom.split(" (")[0].strip().lower())
            except OSError:
                continue
    except Exception:
        pass
    return noms


def police_arabe():
    """La premiere police de la chaine qui existe sur cette machine.

    Calculee une fois par session : lire le registre a chaque paragraphe d'un
    acte de trente pages couterait cher pour un resultat invariable."""
    global _police_retenue
    if _police_retenue:
        return _police_retenue
    dispo = polices_installees()
    for nom in CHAINE_POLICES_ARABES:
        if not dispo or nom.lower() in dispo:
            # `not dispo` : registre illisible. On garde le premier choix plutot
            # que de degrader sur une simple panne de lecture.
            _police_retenue = nom
            return nom
    _police_retenue = CHAINE_POLICES_ARABES[-1]
    return _police_retenue


def set_rtl(paragraph):
    """Sets Right-to-Left paragraph formatting for Arabic text in docx."""
    pPr = paragraph._p.get_or_add_pPr()
    bidi = OxmlElement('w:bidi')
    bidi.set(qn('w:val'), '1')
    pPr.append(bidi)


def set_run_font(run, font_name=None, size_pt=14, bold=False, color_rgb=(0, 0, 0)):
    font_name = font_name or police_arabe()
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


def format_legal_paragraph(paragraph, text, font_name=None, base_size=14):
    font_name = font_name or police_arabe()
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
        set_run_font(run, font_name=police_arabe(), size_pt=18, bold=True)

    # Process paragraphs
    lines = contract_text.split("\n")
    for line in lines:
        clean_line = line.strip()
        if not clean_line:
            continue
        p = doc.add_paragraph()
        format_legal_paragraph(p, clean_line, font_name=police_arabe(), base_size=14)

    doc.save(output_path)
    print(f"[DOCX Generator] Created: {output_path}")
    return True
