import office_profile
import io
import copy
import datetime

# reportlab costs ~0.6 s to import and is only needed while a PDF is actually being
# produced, so it loads on demand instead of at application start.
#
# A module-level __getattr__ (PEP 562) would NOT work here: it fires only for attribute
# access on the module object, never for the global-name lookups these functions do —
# those raise NameError. So the names are published into module globals explicitly.
_REPORTLAB_READY = False


def _ensure_reportlab():
    """Imports reportlab once and publishes its names as module globals."""
    global _REPORTLAB_READY
    if _REPORTLAB_READY:
        return
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, LongTable, TableStyle,
        HRFlowable, KeepTogether
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    globals().update(
        A4=A4, SimpleDocTemplate=SimpleDocTemplate, Paragraph=Paragraph,
        Spacer=Spacer, Table=Table, LongTable=LongTable, TableStyle=TableStyle,
        HRFlowable=HRFlowable, KeepTogether=KeepTogether,
        getSampleStyleSheet=getSampleStyleSheet, ParagraphStyle=ParagraphStyle,
        colors=colors,
    )
    _REPORTLAB_READY = True


def generate_pdf_bilan(
    start_date_str: str,
    end_date_str: str,
    tot_inflows: float,
    tot_expenses: float,
    tot_salaries: float,
    net_result: float,
    tot_receivables: float,
    inflows_list: list,
    expenses_list: list,
    salaries_list: list,
    receivables_list: list
) -> bytes:
    _ensure_reportlab()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=colors.HexColor('#0f172a'),
        alignment=1
    )

    subtitle_style = ParagraphStyle(
        'DocSubTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=16,
        textColor=colors.HexColor('#0284c7'),
        alignment=1
    )

    h2_style = ParagraphStyle(
        'SectionH2',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=15,
        textColor=colors.HexColor('#1e293b'),
        spaceBefore=10,
        spaceAfter=6
    )

    normal_style = ParagraphStyle(
        'DocNormal',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#334155')
    )

    normal_bold = ParagraphStyle(
        'DocNormalBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#0f172a')
    )

    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=11,
        textColor=colors.white,
        alignment=1
    )

    style_exp_amt = ParagraphStyle('ExpAmtStyle', parent=normal_style, textColor=colors.HexColor('#b91c1c'), alignment=2)
    style_sal_amt = ParagraphStyle('SalAmtStyle', parent=normal_style, textColor=colors.HexColor('#4338ca'), alignment=2)
    style_right_num = ParagraphStyle('RightNumStyle', parent=normal_style, alignment=2)
    style_rem_amt = ParagraphStyle('RemAmtStyle', parent=normal_style, textColor=colors.HexColor('#0369a1'), alignment=2)

    elements = []

    # 1. Header Block
    elements.append(Paragraph("REPUBLIQUE TUNISIENNE — OFFICE NOTARIAL", subtitle_style))
    prof = office_profile.load()
    notary_name_fr = (prof.get("notary_name_fr") or prof.get("notary_name") or "").strip()
    pdf_header_title = f"ETUDE NOTARIALE DE MAITRE {notary_name_fr.upper()}" if notary_name_fr else "ETUDE NOTARIALE"
    elements.append(Paragraph(pdf_header_title, title_style))
    elements.append(Spacer(1, 4))
    elements.append(Paragraph("BILAN FINANCIER & COMPTABILITE DU CABINET", ParagraphStyle('SubHeader', parent=subtitle_style, textColor=colors.HexColor('#475569'), fontSize=11)))
    elements.append(Spacer(1, 6))

    now_str = datetime.datetime.now().strftime("%d/%m/%Y a %H:%M")
    period_info = f"<b>Periode du bilan :</b> {start_date_str} au {end_date_str} | <b>Edite le :</b> {now_str}"
    elements.append(Paragraph(period_info, ParagraphStyle('Period', parent=normal_style, alignment=1)))
    elements.append(Spacer(1, 10))
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#0284c7'), spaceAfter=12))

    # 2. Executive Summary Cards (Table)
    summary_data = [
        [
            Paragraph("<b>Recettes Encaissees (Honoraires)</b>", table_header_style),
            Paragraph("<b>Depenses de Fonctionnement</b>", table_header_style),
            Paragraph("<b>Salaires & Avances Employes</b>", table_header_style),
        ],
        [
            Paragraph(f"<font size=12 color='#065f46'><b>+{tot_inflows:.3f} DT</b></font>", ParagraphStyle('C1', parent=normal_style, alignment=1)),
            Paragraph(f"<font size=12 color='#991b1b'><b>-{tot_expenses:.3f} DT</b></font>", ParagraphStyle('C2', parent=normal_style, alignment=1)),
            Paragraph(f"<font size=12 color='#3730a3'><b>-{tot_salaries:.3f} DT</b></font>", ParagraphStyle('C3', parent=normal_style, alignment=1)),
        ]
    ]

    t_summary = Table(summary_data, colWidths=[175, 175, 175])
    t_summary.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e293b')),
        ('BACKGROUND', (0, 1), (0, 1), colors.HexColor('#dcfce7')),
        ('BACKGROUND', (1, 1), (1, 1), colors.HexColor('#fee2e2')),
        ('BACKGROUND', (2, 1), (2, 1), colors.HexColor('#e0e7ff')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e1')),
    ]))
    elements.append(t_summary)
    elements.append(Spacer(1, 12))

    # Net Result Banner
    net_color = "#065f46" if net_result >= 0 else "#991b1b"
    net_bg = "#dcfce7" if net_result >= 0 else "#fee2e2"
    net_data = [
        [
            Paragraph(f"<b>RESULTAT NET DU CABINET :</b>", ParagraphStyle('NetLbl', parent=normal_bold, fontSize=11)),
            Paragraph(f"<font size=14 color='{net_color}'><b>{net_result:+.3f} DT</b></font>", ParagraphStyle('NetVal', parent=normal_bold, alignment=2)),
        ],
        [
            Paragraph(f"<b>Creances Clients (Mnt Restant a Recouvrer) :</b>", ParagraphStyle('RecLbl', parent=normal_style, fontSize=10)),
            Paragraph(f"<font size=11 color='#0284c7'><b>{tot_receivables:.3f} DT</b></font>", ParagraphStyle('RecVal', parent=normal_bold, alignment=2)),
        ]
    ]
    t_net = Table(net_data, colWidths=[340, 185])
    t_net.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(net_bg)),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#f8fafc')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e1')),
    ]))
    elements.append(t_net)
    elements.append(Spacer(1, 14))

    # 3. Section: Journal des Depenses
    if expenses_list:
        elements.append(Paragraph("1. Detail des Depenses de Fonctionnement (Charges)", h2_style))
        exp_table_data = [[
            Paragraph("<b>Date</b>", table_header_style),
            Paragraph("<b>Categorie</b>", table_header_style),
            Paragraph("<b>Description / Motif</b>", table_header_style),
            Paragraph("<b>Montant (DT)</b>", table_header_style),
        ]]
        for exp in expenses_list:
            edate = str(exp.get("created_at", ""))
            ecat = str(exp.get("category", ""))
            edesc = str(exp.get("description", ""))
            eamt = float(exp.get("amount") or 0.0)
            exp_table_data.append([
                Paragraph(edate, normal_style),
                Paragraph(ecat, normal_style),
                Paragraph(edesc, normal_style),
                Paragraph(f"<b>-{eamt:.3f} DT</b>", style_exp_amt),
            ])
        t_exp = LongTable(exp_table_data, colWidths=[100, 130, 200, 95], repeatRows=1)
        t_exp.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#334155')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('PADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(t_exp)
        elements.append(Spacer(1, 14))

    # 4. Section: Journal des Salaires
    if salaries_list:
        elements.append(Paragraph("2. Detail des Salaires et Avances du Personnel", h2_style))
        sal_table_data = [[
            Paragraph("<b>Date</b>", table_header_style),
            Paragraph("<b>Employe</b>", table_header_style),
            Paragraph("<b>Fonction / Role</b>", table_header_style),
            Paragraph("<b>Notes</b>", table_header_style),
            Paragraph("<b>Montant (DT)</b>", table_header_style),
        ]]
        for sal in salaries_list:
            sdate = str(sal.get("payment_date", ""))
            sname = str(sal.get("employee_name", ""))
            srole = str(sal.get("role", ""))
            snote = str(sal.get("notes", ""))
            samt = float(sal.get("amount") or 0.0)
            sal_table_data.append([
                Paragraph(sdate, normal_style),
                Paragraph(sname, normal_bold),
                Paragraph(srole, normal_style),
                Paragraph(snote, normal_style),
                Paragraph(f"<b>-{samt:.3f} DT</b>", style_sal_amt),
            ])
        t_sal = LongTable(sal_table_data, colWidths=[80, 110, 110, 130, 95], repeatRows=1)
        t_sal.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#334155')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('PADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(t_sal)
        elements.append(Spacer(1, 14))

    # 5. Section: Creances Clients (Reste a Payer)
    if receivables_list:
        elements.append(Paragraph("3. Detail des Creances Clients (Reste a Payer sur Dossiers)", h2_style))
        rec_table_data = [[
            Paragraph("<b>N° Dossier</b>", table_header_style),
            Paragraph("<b>Client</b>", table_header_style),
            Paragraph("<b>Total (DT)</b>", table_header_style),
            Paragraph("<b>Avance (DT)</b>", table_header_style),
            Paragraph("<b>Reste a Payer (DT)</b>", table_header_style),
        ]]
        for rec in receivables_list:
            cid = str(rec.get("case_id", ""))
            cname = str(rec.get("client_name", ""))
            tot = float(rec.get("total_amount") or 0.0)
            av = float(rec.get("avance_amount") or 0.0)
            rem = float(rec.get("reste") or 0.0)
            rec_table_data.append([
                Paragraph(cid, normal_bold),
                Paragraph(cname, normal_style),
                Paragraph(f"{tot:.3f} DT", style_right_num),
                Paragraph(f"{av:.3f} DT", style_right_num),
                Paragraph(f"<b>{rem:.3f} DT</b>", style_rem_amt),
            ])
        t_rec = LongTable(rec_table_data, colWidths=[90, 165, 90, 90, 90], repeatRows=1)
        t_rec.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0369a1')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f9ff')]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('PADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(t_rec)
        elements.append(Spacer(1, 20))

    prof = office_profile.load()
    notary_name_fr = (prof.get("notary_name_fr") or prof.get("notary_name") or "").strip()
    sig_notary_title = f"Maitre {notary_name_fr}" if notary_name_fr else "Le Notaire"
    sig_data = [
        [
            Paragraph("<b>Verification Comptable</b><br/>Etude Notariale", ParagraphStyle('Sig1', parent=normal_style)),
            Paragraph(f"<b>Cachet et Signature du Notaire</b><br/>{sig_notary_title}", ParagraphStyle('Sig2', parent=normal_bold, alignment=2)),
        ]
    ]
    t_sig = Table(sig_data, colWidths=[260, 265])
    t_sig.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('PADDING', (0, 0), (-1, -1), 10),
    ]))
    elements.append(KeepTogether([t_sig]))

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


# python-docx costs ~0.6 s and is only needed while a Word document is being built.
# This block used to run at import, which meant every page that touches pdf_generator —
# Comptabilite among them — paid for it on first open. Same shape as _ensure_reportlab().
docx = None
_DOCX_READY = False


def _ensure_docx() -> bool:
    """Loads python-docx once and publishes its names as module globals."""
    global _DOCX_READY
    if _DOCX_READY:
        return docx is not None
    try:
        import docx as _docx
        from docx.shared import Pt, Inches, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.enum.table import WD_TABLE_ALIGNMENT
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        globals().update(
            docx=_docx, Pt=Pt, Inches=Inches, RGBColor=RGBColor,
            WD_ALIGN_PARAGRAPH=WD_ALIGN_PARAGRAPH, WD_TABLE_ALIGNMENT=WD_TABLE_ALIGNMENT,
            OxmlElement=OxmlElement, qn=qn,
        )
    except ImportError:
        globals()["docx"] = None
    _DOCX_READY = True
    return docx is not None

def apply_run_font(run, font_name="Traditional Arabic", size_pt=13, is_bold=False):
    run.font.name = font_name
    run.font.size = Pt(size_pt)
    run.font.bold = is_bold
    run.font.color.rgb = RGBColor(0, 0, 0)
    rPr = run._r.get_or_add_rPr()
    rFonts = OxmlElement('w:rFonts')
    rFonts.set(qn('w:ascii'), font_name)
    rFonts.set(qn('w:hAnsi'), font_name)
    rFonts.set(qn('w:cs'), font_name)
    rPr.append(rFonts)
    rtl = OxmlElement('w:rtl')
    rPr.append(rtl)
    if is_bold:
        bCs = OxmlElement('w:bCs')
        rPr.append(bCs)


_CACHED_NOTARY_TEMPLATE_BYTES = None
_CACHED_NOTARY_DOC_OBJ = None

def _get_base_notary_template_bytes() -> bytes:
    _ensure_docx()
    global _CACHED_NOTARY_TEMPLATE_BYTES
    if _CACHED_NOTARY_TEMPLATE_BYTES is not None:
        return _CACHED_NOTARY_TEMPLATE_BYTES

    if docx is None:
        return b""

    doc = docx.Document()
    for section in doc.sections:
        section.top_margin = Inches(0.6)
        section.bottom_margin = Inches(0.6)
        section.left_margin = Inches(0.6)
        section.right_margin = Inches(0.6)

    tbl_hdr = doc.add_table(rows=1, cols=3)
    tbl_hdr.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr_cells = tbl_hdr.rows[0].cells

    # Left Cell (French)
    p_fr = hdr_cells[0].paragraphs[0]
    p_fr.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p_fr.paragraph_format.line_spacing = 1.0
    p_fr.paragraph_format.space_before = Pt(0)
    p_fr.paragraph_format.space_after = Pt(0)
    r_fr = p_fr.add_run(office_profile.letterhead_fr())
    apply_run_font(r_fr, font_name="Arial", size_pt=9.5, is_bold=True)

    # Center Cell
    p_ctr = hdr_cells[1].paragraphs[0]
    p_ctr.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_ctr.paragraph_format.line_spacing = 1.0
    p_ctr.paragraph_format.space_before = Pt(0)
    p_ctr.paragraph_format.space_after = Pt(0)
    r_ctr = p_ctr.add_run("|\nالحمد لله وحده")
    apply_run_font(r_ctr, font_name="Arial", size_pt=11, is_bold=True)

    # Right Cell (Arabic)
    p_ar = hdr_cells[2].paragraphs[0]
    p_ar.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p_ar.paragraph_format.line_spacing = 1.0
    p_ar.paragraph_format.space_before = Pt(0)
    p_ar.paragraph_format.space_after = Pt(0)
    r_ar = p_ar.add_run(office_profile.letterhead())
    apply_run_font(r_ar, font_name="Arial", size_pt=9.5, is_bold=True)

    buf = io.BytesIO()
    doc.save(buf)
    _CACHED_NOTARY_TEMPLATE_BYTES = buf.getvalue()
    return _CACHED_NOTARY_TEMPLATE_BYTES

_CACHED_NOTARY_DOC_OBJ = None

def _get_base_notary_doc_obj():
    _ensure_docx()
    global _CACHED_NOTARY_DOC_OBJ
    if _CACHED_NOTARY_DOC_OBJ is not None:
        return _CACHED_NOTARY_DOC_OBJ
    b = _get_base_notary_template_bytes()
    if b:
        _CACHED_NOTARY_DOC_OBJ = docx.Document(io.BytesIO(b))
    return _CACHED_NOTARY_DOC_OBJ


def generate_docx_from_transcription(title: str, text: str, metadata: dict = None) -> bytes:
    """Generates an official Microsoft Word (.docx) document matching Image 1 exact notary layout."""
    _ensure_docx()
    if docx is None:
        return b""

    base_obj = _get_base_notary_doc_obj()
    doc = copy.deepcopy(base_obj) if base_obj is not None else docx.Document()

    doc.add_paragraph() # Spacer

    # 2. MAIN TITLE (Centered & BOLD 20pt)
    clean_title = title.replace("— " + office_profile.office_title(), "").strip()
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_t = p_title.add_run(clean_title)
    run_t.font.name = "Traditional Arabic"
    run_t.font.size = Pt(20)
    run_t.font.bold = True
    run_t.font.color.rgb = RGBColor(0, 0, 0)

    # 3. BODY TEXT & PARAGRAPHS WITH INLINE BOLDING (Gras) & CROWDED PARAGRAPH SPACING
    bold_phrases = [
        "الحمد لله في", "الحمد لله،", office_profile.notary_block()[:40],
        "انعقد بين الطرف الأول البائعين", "انعقد بين الطرف الأول البائع", "انعقد بين الطرف الأول الواهب", "انعقد بين الطرف الأول المتنازل", "انعقد بين الطرف الأول",
        "الطرف الأول البائعين", "الطرف الأول البائع", "الطرف الأول الواهب", "الطرف الأول المتنازل", "الطرف الأول",
        "أولا السيدة:", "ثانيا السيدة:", "ثالثا السيدة:", "رابعا السيدة:",
        "الطرف الثاني المشترية:", "الطرف الثاني المشتري:", "الطرف الثاني الموهوب له:", "الطرف الثاني المتنازل له:", "الطرف الثاني",
        "الفصل الأول:", "الفصل الثاني:", "الفصل الثالث:", "الفصل الرابع:", "الفصل الخامس:", "الفصل السادس:",
        "وأبرم العقد بين طرفيه", "وأبرم العقد", "ورسم بدفتر مسودات أولهما", "ورسم بدفتر مسودات"
    ]

    lines = text.split("\n")
    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue
            
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.line_spacing = 1.15
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(3)
        
        # Inline bold parsing for phrases
        curr_text = line_str
        while curr_text:
            earliest_pos = -1
            found_phrase = None
            for bp in bold_phrases:
                pos = curr_text.find(bp)
                if pos != -1 and (earliest_pos == -1 or pos < earliest_pos):
                    earliest_pos = pos
                    found_phrase = bp
                    
            if earliest_pos == -1:
                r_norm = p.add_run(curr_text)
                apply_run_font(r_norm, font_name="Traditional Arabic", size_pt=13, is_bold=False)
                break
            else:
                if earliest_pos > 0:
                    r_pre = p.add_run(curr_text[:earliest_pos])
                    apply_run_font(r_pre, font_name="Traditional Arabic", size_pt=13, is_bold=False)
                    
                phrase_end = earliest_pos + len(found_phrase)
                if phrase_end < len(curr_text) and curr_text[phrase_end] == ":":
                    phrase_end += 1
                    
                r_b = p.add_run(curr_text[earliest_pos:phrase_end])
                apply_run_font(r_b, font_name="Traditional Arabic", size_pt=13.5, is_bold=True)
                
                curr_text = curr_text[phrase_end:]

    doc.add_paragraph() # Spacer

    # 4. BOTTOM FOOTER TABLE (Bordered Box with 2 Columns)
    tbl_ftr = doc.add_table(rows=1, cols=2)
    tbl_ftr.alignment = WD_TABLE_ALIGNMENT.CENTER
    ftr_cells = tbl_ftr.rows[0].cells
    
    # Left Footer Cell
    p_f1 = ftr_cells[0].paragraphs[0]
    p_f1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_f1 = p_f1.add_run("الأستاذ سامي الجوادي\nب ت و ع 04481027دد")
    r_f1.font.name = "Traditional Arabic"
    r_f1.font.size = Pt(12)
    r_f1.font.bold = True
    r_f1.font.color.rgb = RGBColor(0, 0, 0)
    
    # Right Footer Cell
    p_f2 = ftr_cells[1].paragraphs[0]
    p_f2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_f2 = p_f2.add_run(office_profile.signature_block())
    r_f2.font.name = "Traditional Arabic"
    r_f2.font.size = Pt(12)
    r_f2.font.bold = True
    r_f2.font.color.rgb = RGBColor(0, 0, 0)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.getvalue()


def generate_pdf_from_transcription(title: str, text: str) -> bytes:
    """Generates a styled PDF document from transcribed Arabic text."""
    _ensure_reportlab()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36
    )
    styles = getSampleStyleSheet()

    h_style = ParagraphStyle(
        'HeaderStyle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=16, leading=20, alignment=1, textColor=colors.HexColor('#0f172a')
    )
    sub_style = ParagraphStyle(
        'SubStyle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=12, leading=16, alignment=1, textColor=colors.HexColor('#0284c7')
    )
    body_style = ParagraphStyle(
        'BodyStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=10, leading=14, alignment=2, textColor=colors.HexColor('#1e293b')
    )
    h2_style = ParagraphStyle(
        'H2Style', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=11, leading=15, alignment=2, textColor=colors.HexColor('#0f172a')
    )

    elements = [
        Paragraph("Republique Tunisienne - Etude Notariale", h_style),
        Paragraph(f"Transcription Document Handwritten: {title}", sub_style),
        Spacer(1, 15),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor('#cbd5e1'), spaceAfter=15)
    ]

    for line in text.split("\n"):
        line_str = line.strip()
        if not line_str:
            continue
        if line_str.startswith("#") or line_str.startswith("---") or line_str.startswith("###"):
            clean = line_str.replace("#", "").replace("-", "").strip()
            elements.append(Paragraph(f"<b>{clean}</b>", h2_style))
            elements.append(Spacer(1, 4))
        else:
            elements.append(Paragraph(line_str, body_style))
            elements.append(Spacer(1, 4))

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


def generate_client_fiche_pdf(client_data: dict, cases_list: list) -> bytes:
    """Generates an official PDF summary document for a client and their dossiers."""
    _ensure_reportlab()
    import office_profile
    profile = office_profile.load()
    office_title = profile.get("office_title") or "Cabinet Notarial"
    notary_name = profile.get("notary_name") or "Le Notaire"

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36
    )
    styles = getSampleStyleSheet()

    h_style = ParagraphStyle(
        'HeaderStyle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=18, leading=22, alignment=1, textColor=colors.HexColor('#0f172a')
    )
    sub_style = ParagraphStyle(
        'SubStyle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=13, leading=17, alignment=1, textColor=colors.HexColor('#0284c7')
    )
    body_style = ParagraphStyle(
        'BodyStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=10, leading=14, textColor=colors.HexColor('#1e293b')
    )
    bold_style = ParagraphStyle(
        'BoldStyle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, leading=14, textColor=colors.HexColor('#0f172a')
    )

    full_name = client_data.get('full_name', '') or 'Client Sans Nom'
    cin = client_data.get('cin', '') or 'N/A'
    phone = client_data.get('phone', '') or 'N/A'
    address = client_data.get('address', '') or 'N/A'
    dob = client_data.get('birth_date', '') or 'N/A'

    elements = [
        Paragraph(office_title, h_style),
        Spacer(1, 4),
        Paragraph(f"Notaire: {notary_name}", sub_style),
        Spacer(1, 10),
        HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#0284c7'), spaceAfter=15),
        Paragraph(f"<b>FICHE INDIVIDUELLE DU CLIENT</b>", ParagraphStyle('T', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=14, leading=18, alignment=1, textColor=colors.HexColor('#0f172a'))),
        Spacer(1, 12),
    ]

    # Client details table
    info_data = [
        [Paragraph("<b>Nom & Prénom:</b>", bold_style), Paragraph(full_name, body_style), Paragraph("<b>N° CIN:</b>", bold_style), Paragraph(cin, body_style)],
        [Paragraph("<b>Téléphone:</b>", bold_style), Paragraph(phone, body_style), Paragraph("<b>Date de Naissance:</b>", bold_style), Paragraph(dob, body_style)],
        [Paragraph("<b>Adresse:</b>", bold_style), Paragraph(address, body_style), Paragraph("", body_style), Paragraph("", body_style)]
    ]
    info_table = Table(info_data, colWidths=[110, 150, 110, 150])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#cbd5e1')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 20))

    # Dossiers section
    elements.append(Paragraph("<b>HISTORIQUE DES DOSSIERS NOTARIÉS</b>", ParagraphStyle('T2', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=12, leading=16, textColor=colors.HexColor('#0f172a'))))
    elements.append(Spacer(1, 8))

    case_rows = [[Paragraph("<b>N° Dossier</b>", bold_style), Paragraph("<b>Type d'Acte / Contrat</b>", bold_style), Paragraph("<b>Date</b>", bold_style), Paragraph("<b>Statut</b>", bold_style)]]
    if cases_list:
        for c in cases_list:
            cid = str(c.get("case_id", ""))
            stype = str(c.get("service_type", "") or c.get("title", ""))
            cdate = str(c.get("created_at", "")).split()[0]
            cstat = str(c.get("status", ""))
            case_rows.append([
                Paragraph(cid, body_style),
                Paragraph(stype, body_style),
                Paragraph(cdate, body_style),
                Paragraph(cstat, body_style)
            ])
    else:
        case_rows.append([Paragraph("Aucun dossier enregistré", body_style), Paragraph("-", body_style), Paragraph("-", body_style), Paragraph("-", body_style)])

    cases_table = Table(case_rows, colWidths=[90, 240, 90, 100])
    cases_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#e2e8f0')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(cases_table)
    elements.append(Spacer(1, 30))

    # Signature block
    sig_data = [["", f"Fait à le {datetime.date.today().strftime('%d/%m/%Y')}\nLe Notaire\n{notary_name}"]]
    sig_table = Table(sig_data, colWidths=[300, 220])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (1,0), (1,0), 'RIGHT'),
        ('TEXTCOLOR', (1,0), (1,0), colors.HexColor('#0f172a')),
        ('FONTNAME', (1,0), (1,0), 'Helvetica-Bold'),
    ]))
    elements.append(sig_table)

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()

