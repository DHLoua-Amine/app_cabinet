"""
office_profile.py — who the office is, so the app is not one notary's app.

Every generated deed opened with the same fixed sentence:

    نحن عبد الحميد زارعي وجليسه عدلا الإشهاد بدائرة قضاء المحكمة الابتدائية
    بين عروس المكتب عدد 10 المركب الصحي الزارعي شارع الحرية المحمدية بن عروس

That name, that court, that office number, that address and the tax office in
the closing clause were written into sixteen contract templates, the PDF
letterhead, the signature block, the login window and the Scanner's document
headers. Selling the app to a second notary meant editing eight source files.

The office's identity now lives in the database — the shared one, so the notaire
build and the secrétaire build agree — and is edited from Paramètres. The
templates carry placeholders and are filled at generation time.

Nothing here is per-client. This is the office issuing the deed, not a party to
it.
"""

from __future__ import annotations

# The keys, their default (empty) value, and how each is described to the notary.
FIELDS = [
    ("notary_title",    "الأستاذ",
     "اللقب المهني", "Titre professionnel"),
    ("notary_name",     "",
     "الاسم واللقب الكامل لعدل الإشهاد", "Nom et prénom du notaire"),
    ("notary_cin",      "",
     "رقم بطاقة تعريف عدل الإشهاد", "CIN du notaire"),
    ("court",           "",
     "دائرة قضاء المحكمة الابتدائية بـ", "Tribunal de première instance de"),
    ("office_number",   "",
     "عدد المكتب", "Numéro du bureau"),
    ("office_address",  "",
     "عنوان المكتب (كما يُكتب في العقد)", "Adresse du bureau (telle qu'écrite dans l'acte)"),
    ("letterhead_address", "",
     "العنوان المختصر للترويسة", "Adresse courte pour l'en-tête"),
    ("phone",           "",
     "الهاتف", "Téléphone"),
    ("tax_office",      "",
     "القباضة المالية بـ", "Recette des finances de"),
    # The printed letterhead carries a French column beside the Arabic one, so
    # the office's French rendering of its own details belongs here too rather
    # than being transliterated on the fly.
    ("notary_name_fr",  "",
     "الاسم بالفرنسية (للترويسة)", "Nom du notaire (en-tête français)"),
    ("court_fr",        "",
     "المحكمة بالفرنسية", "Tribunal (français)"),
    ("address_fr",      "",
     "العنوان بالفرنسية", "Adresse (français)"),
    ("jaliss_title",   "الأستاذ",
     "لقب الجليس (عدل الإشهاد الثاني)", "Titre du co-notaire"),
    ("jaliss_name",    "",
     "اسم ولقب الجليس (عدل الإشهاد الثاني)", "Nom du co-notaire"),
    ("jaliss_cin",     "",
     "رقم بطاقة تعريف الجليس", "CIN du co-notaire"),
]

DEFAULTS = {k: d for k, d, _ar, _fr in FIELDS}
_SETTING_PREFIX = "office."


def _cursor(commit: bool = False):
    import reception
    return reception.get_db_cursor(commit=commit)


def _ensure_table():
    with _cursor(commit=True) as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS system_settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT
            )
        """)


def load() -> dict:
    """The office profile, with empty strings for anything not yet filled in."""
    prof = dict(DEFAULTS)
    try:
        _ensure_table()
        with _cursor() as c:
            rows = c.execute(
                "SELECT setting_key, setting_value FROM system_settings "
                "WHERE setting_key LIKE ?", (_SETTING_PREFIX + "%",)).fetchall()
        for r in rows:
            key = r["setting_key"][len(_SETTING_PREFIX):]
            if key in prof:
                prof[key] = r["setting_value"] or ""
    except Exception as e:
        try:
            from system_guardian import log_system_error
            log_system_error("could not read the office profile", e)
        except Exception:
            # (c) Safe: the defaults below are still returned, and is_configured()
            # will report the profile as unset so the notary is prompted.
            pass
    return prof


def save(values: dict) -> bool:
    """Writes the office profile. Returns False if nothing could be written."""
    try:
        _ensure_table()
        with _cursor(commit=True) as c:
            for k in DEFAULTS:
                if k in values:
                    c.execute(
                        "INSERT OR REPLACE INTO system_settings "
                        "(setting_key, setting_value) VALUES (?, ?)",
                        (_SETTING_PREFIX + k, str(values.get(k) or "").strip()))
        return True
    except Exception as e:
        try:
            from system_guardian import log_system_error
            log_system_error("could not save the office profile", e)
        except Exception:
            pass
        return False


def is_configured(prof: dict = None) -> bool:
    """True once the office has told us who it is."""
    prof = prof if prof is not None else load()
    return bool((prof.get("notary_name") or "").strip())


def missing_fields(prof: dict = None) -> list:
    """The fields a deed needs that are still blank, for the reviewer to see."""
    prof = prof if prof is not None else load()
    needed = ("notary_name", "court", "office_number", "office_address")
    return [k for k in needed if not (prof.get(k) or "").strip()]


# ── The sentences the templates need ─────────────────────────────────────────
# A blank field leaves the dotted placeholder a notary would write by hand, so an
# unconfigured office produces an obviously-incomplete deed rather than a deed
# that silently carries someone else's name.
BLANK = "................"


def _or_blank(v) -> str:
    v = (v or "").strip()
    return v if v else BLANK


def notary_block(prof: dict = None) -> str:
    """
    The opening identification of the officiating notary.

    Reproduces exactly the wording the templates used, with the office's own
    details substituted:
        نحن {name} وجليسه عدلا الإشهاد بدائرة قضاء المحكمة الابتدائية {court}
        المكتب عدد {n} {address}.
    """
    prof = prof if prof is not None else load()
    return (f"نحن {_or_blank(prof.get('notary_name'))} وجليسه عدلا الإشهاد "
            f"بدائرة قضاء المحكمة الابتدائية {_or_blank(prof.get('court'))} "
            f"المكتب عدد {_or_blank(prof.get('office_number'))} "
            f"{_or_blank(prof.get('office_address'))}.")


def tax_office_name(prof: dict = None) -> str:
    prof = prof if prof is not None else load()
    return _or_blank(prof.get("tax_office"))


def display_name(prof: dict = None) -> str:
    """"الأستاذ فلان" — for window titles, document headers and the signature."""
    prof = prof if prof is not None else load()
    name = (prof.get("notary_name") or "").strip()
    if not name:
        return "مكتب التوثيق"
    title = (prof.get("notary_title") or "").strip()
    return f"{title} {name}".strip()


def office_title(prof: dict = None) -> str:
    """"مكتب الأستاذ فلان" — used as a document title suffix."""
    prof = prof if prof is not None else load()
    name = (prof.get("notary_name") or "").strip()
    return f"مكتب {display_name(prof)}" if name else "مكتب التوثيق"


def letterhead(prof: dict = None) -> str:
    """The block printed at the top-right of a generated PDF or Word file."""
    prof = prof if prof is not None else load()
    name = (prof.get("notary_name") or "").strip()
    title = (prof.get("notary_title") or "الأستاذ").strip()
    line1 = f"مكــتب {title} {name}".strip() if name else "مكــتب الأســتاذ"
    lines = [line1, "عدل إشهــــاد"]
    addr = (prof.get("letterhead_address") or prof.get("office_address") or "").strip()
    if addr:
        lines.append(addr)
    phone = (prof.get("phone") or "").strip()
    if phone:
        lines.append(f"الهاتف {phone}")
    return "\n".join(lines)


def signature_block(prof: dict = None) -> str:
    """The closing signature line of a generated deed."""
    prof = prof if prof is not None else load()
    out = display_name(prof)
    cin = (prof.get("notary_cin") or "").strip()
    if cin:
        out += f"\nب ت و ع {cin}"
    return out


# ── The printed letterhead and signature footer ──────────────────────────────
def header_html(prof: dict = None) -> str:
    """
    The bordered three-column header printed above a generated deed.

    Arabic on the right, "الحمد لله وحده" in the middle, French on the left —
    the layout the office already used, with its own details rather than one
    particular notary's.
    """
    prof = prof if prof is not None else load()
    name_ar = _or_blank(prof.get("notary_name"))
    addr_ar = (prof.get("letterhead_address") or prof.get("office_address") or "").strip()
    phone = (prof.get("phone") or "").strip()
    name_fr = (prof.get("notary_name_fr") or "").strip()
    court_fr = (prof.get("court_fr") or "").strip()
    addr_fr = (prof.get("address_fr") or "").strip()

    ar_lines = ["<div>مكــتب الأســتاذ</div>",
                f'<div style="font-weight:900;">{name_ar}</div>',
                "<div>عدل إشهــــاد</div>"]
    if addr_ar:
        ar_lines.append(f"<div>{addr_ar}</div>")
    if phone:
        ar_lines.append(f"<div>الهاتف {phone}</div>")

    fr_lines = []
    if name_fr:
        fr_lines.append(f"<div>MAITRE {name_fr}</div>")
    fr_lines.append('<div style="font-weight:900;">NOTAIRE</div>')
    if court_fr:
        fr_lines.append(f"<div>Cir Tribunal Pre inst {court_fr}</div>")
    if addr_fr:
        fr_lines.append(f"<div>{addr_fr}</div>")
    if phone:
        fr_lines.append(f"<div>Tel: {phone}</div>")

    # Percent-formatting is the wrong tool for a string full of CSS percentages
    # (width="33%"): every one of them has to be doubled or the format call
    # fails. Substituting named markers avoids the whole class of bug.
    tpl = """
<div style="border:2px solid #000000; padding:10px 16px; margin-bottom:20px; direction:rtl; font-family:'Traditional Arabic', serif;">
    <table width="100%" border="0" cellpadding="0" cellspacing="0">
        <tr>
            <td width="33%" align="right" valign="middle" style="line-height:1.3; font-size:12px; font-weight:800; color:#000000;">
                @@AR@@
            </td>
            <td width="33%" align="center" valign="middle" style="font-size:14px; font-weight:900; color:#000000;">
                <div style="font-size:16px;">|</div>
                <div>الحمد لله وحده</div>
            </td>
            <td width="33%" align="left" valign="middle" dir="ltr" style="line-height:1.3; font-size:12px; font-weight:800; color:#000000;">
                @@FR@@
            </td>
        </tr>
    </table>
</div>
"""
    joiner = chr(10) + " " * 16
    return (tpl.replace("@@AR@@", joiner.join(ar_lines))
               .replace("@@FR@@", joiner.join(fr_lines)))


def footer_html(prof: dict = None) -> str:
    """The bordered signature block printed under a generated deed."""
    prof = prof if prof is not None else load()
    name = display_name(prof)
    cin = (prof.get("notary_cin") or "").strip()
    cin_line = f"<div>ب ت و ع {cin}دد</div>" if cin else ""
    tpl = """
<div style="margin-top:30px; border:2px solid #000000; padding:10px 16px; direction:rtl; font-family:'Traditional Arabic', serif;">
    <table width="100%" border="0" cellpadding="0" cellspacing="0">
        <tr>
            <td width="48%" align="center" valign="middle" style="font-weight:900; font-size:14px; color:#000000; line-height:1.5;">
                <div>@@NAME@@</div>
                @@CIN@@
            </td>
            <td width="4%" align="center" valign="middle" style="font-size:20px; font-weight:bold;">|</td>
            <td width="48%" align="center" valign="middle" style="font-weight:900; font-size:14px; color:#000000; line-height:1.5;">
                <div>الشــاهدان</div>
            </td>
        </tr>
    </table>
</div>
"""
    return tpl.replace("@@NAME@@", name).replace("@@CIN@@", cin_line)


def letterhead_fr(prof: dict = None) -> str:
    """The French column of the printed letterhead."""
    prof = prof if prof is not None else load()
    lines = []
    name = (prof.get("notary_name_fr") or "").strip()
    if name:
        lines.append(f"MAITRE {name}")
    else:
        lines.append("MAITRE Notaire")
    lines.append("NOTAIRE")
    court = (prof.get("court_fr") or "").strip()
    if court:
        lines.append(f"Cir Tribunal Pre inst {court}")
    addr = (prof.get("address_fr") or "").strip()
    if addr:
        lines.append(addr)
    phone = (prof.get("phone") or "").strip()
    if phone:
        lines.append(f"Tel: {phone}")
    return "\n".join(lines)


def jaliss_signature_block(prof: dict = None) -> str:
    """The signature line of the co-notary / seated assistant (الجليس)."""
    prof = prof if prof is not None else load()
    name = (prof.get("jaliss_name") or "").strip()
    title = (prof.get("jaliss_title") or "الأستاذ").strip()
    cin = (prof.get("jaliss_cin") or "").strip()
    
    if name:
        out = f"{title} {name}".strip()
    else:
        out = "الجليس (عدل الإشهاد الثاني)"
    
    if cin:
        out += f"\nب ت و ع {cin}دد"
    else:
        out += "\nب ت و ع ................"
    return out
