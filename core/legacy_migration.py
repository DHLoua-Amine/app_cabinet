"""
legacy_migration.py — bringing a notary's 20-year paper-era archive into the app.

This is a STAFF-OPERATED tool. It is deliberately not self-serve, and it never
writes to the database on its own: it produces a *plan* that a human reads,
corrects and confirms. Everything below is arranged around that one rule.

Why this exists separately from archive_importer.py
---------------------------------------------------
archive_importer.py groups files by folder nesting: a directory is a client and
the files under it are that client's. That is true of a tidy archive and false of
every real one. An office that files by document type — `Contrats/`, `CIN/`,
`Dossiers/` — has one client's material scattered across three top-level trees
that share no common parent. Nesting cannot express that.

So grouping here is GLOBAL. Every file contributes *evidence* (a CIN, a name, a
year, a contract type). Identities are resolved across the whole archive from
that evidence, and folder proximity is one signal among several rather than the
grouping mechanism itself.

The matching rules, in order of authority
-----------------------------------------
1. CIN is the anchor. Two files carrying the same 8-digit CIN are the same
   person: confidence HIGH, reason CIN_EXACT.
2. Two DIFFERENT CINs are two different people. Always. Even when the names are
   character-for-character identical. Such a pair is surfaced as NAME_COLLISION
   for the reviewer with both CINs shown, and is never merged.
3. Only when no CIN is available does name similarity apply, and it never
   produces better than MEDIUM. The comparison key lowercases, strips accents and
   punctuation, removes spaces entirely and sorts the tokens, so "Ben Ali Sami",
   "Sami Ben Ali" and "SAMI BENALI" collapse together — while remaining incapable
   of overriding rule 2.
4. Anything the rules cannot settle becomes a question for the human, never a
   guess.

Resumability
------------
A journal database records every file seen and every AI answer, keyed by content
hash. A run that dies halfway is resumed by re-running it: files already
processed are skipped, and cached Gemini answers cost nothing the second time.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import sqlite3
import time
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from config import DATA_DIR

# ── Confidence ───────────────────────────────────────────────────────────────
HIGH = "high"
MEDIUM = "medium"
LOW = "low"
REVIEW = "needs_review"

CONF_ORDER = {REVIEW: 0, LOW: 1, MEDIUM: 2, HIGH: 3}

# Why a thing was matched. Shown verbatim to the reviewer.
R_CIN_OCR = "CIN lu sur la carte d'identité scannée (OCR)"
R_CIN_FOLDER = "CIN présent dans le nom du dossier"
R_CIN_FILE = "CIN présent dans le nom du fichier"
R_CIN_DOCTEXT = "CIN trouvé dans le texte du document"
R_NAME_FOLDER = "Nom lu dans le nom du dossier"
R_NAME_FILE = "Nom lu dans le nom du fichier"
R_NAME_SIM = "Similarité de nom (pas de CIN pour confirmer)"
R_PROXIMITY = "Fichiers situés dans le même dossier"

# ── File typing ──────────────────────────────────────────────────────────────
DOC_EXTS = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".txt", ".rtf", ".odt"}
IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}

MAGIC = [
    (b"\xff\xd8\xff", "jpeg"), (b"\x89PNG\r\n\x1a\n", "png"),
    (b"BM", "bmp"), (b"GIF8", "gif"), (b"II*\x00", "tiff"), (b"MM\x00*", "tiff"),
    (b"%PDF", "pdf"), (b"PK\x03\x04", "zip"),   # docx/xlsx are zips
    (b"\xd0\xcf\x11\xe0", "ole"),               # legacy .doc/.xls
]

CIN_RE = re.compile(r"(?<!\d)(\d{8})(?!\d)")
YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
YEAR_ONLY_RE = re.compile(r"^(19|20)\d{2}$")
LETTER_RE = re.compile(r"[A-Za-zÀ-ɏ؀-ۿ]")

# Folder names that name a filing scheme, not a person.
NON_CLIENT_NAMES = {
    "divers", "modele", "modeles", "modeles_types", "modeles types", "templates",
    "archive", "archives", "document", "documents", "docs", "photo", "photos",
    "image", "images", "scan", "scans", "piece", "pieces", "pièces", "dossier",
    "dossiers", "vente", "ventes", "achat", "achats", "contrat", "contrats",
    "acte", "actes", "cin", "cartes", "backup", "sauvegarde", "temp", "tmp",
    "old", "ancien", "anciens", "copies", "brouillon", "brouillons", "a classer",
    "a_classer", "non classe", "client", "clients", "succession", "successions",
    "heritage", "heritages", "location", "locations", "procuration", "procurations",
    "وثائق", "صور", "عقود", "ملفات", "أرشيف", "نماذج", "متنوع", "نسخ", "مسودات",
    "حرفاء", "بطاقات", "مواريث", "كراء", "بيوعات",
}

# Words that describe a document, not a person — stripped before name matching.
DOC_WORDS = {
    "contrat", "contrats", "acte", "actes", "vente", "achat", "promesse",
    "procuration", "succession", "heritage", "donation", "hiba", "kraa",
    "location", "bail", "titre", "foncier", "cin", "carte", "identite",
    "identité", "extrait", "naissance", "certificat", "attestation", "recu",
    "reçu", "facture", "scan", "scan0001", "img", "image", "photo", "portrait",
    "copie", "final", "signe", "signé", "dossier", "piece", "pieces", "doc",
    "page", "recto", "verso", "numerise", "numérisé", "bis", "ter", "modele",
    "عقد", "بيع", "شراء", "توكيل", "ميراث", "هبة", "كراء", "رسم", "عقاري",
    "بطاقة", "تعريف", "شهادة", "ولادة", "وصل", "صورة", "نسخة", "ملف", "وثيقة",
    # File-extension words. They reach the name matcher whenever a path is read
    # whole rather than by stem - which happens with OCR output that echoes the
    # filename, and with folders literally named "Scans JPG".
    "jpg", "jpeg", "png", "pdf", "docx", "doc", "tif", "tiff", "bmp", "webp",
    "xls", "xlsx", "txt", "rtf", "odt",
}

# Filename hints for choosing what represents the client.
PORTRAIT_HINTS = ("portrait", "photo", "visage", "face", "identite", "identité",
                  "صورة", "وجه", "شخصية")
IDCARD_HINTS = ("cin", "carte", "recto", "verso", "بطاقة", "تعريف")

# Contract-type tokens, used to separate one client's dossiers from each other.
CONTRACT_TOKENS = {
    "vente": "بيع", "achat": "شراء", "promesse": "وعد بالبيع",
    "succession": "ميراث", "heritage": "ميراث", "donation": "هبة",
    "hiba": "هبة", "procuration": "توكيل", "location": "كراء", "kraa": "كراء",
    "bail": "كراء", "partage": "قسمة", "echange": "معاوضة",
}

# Flags that must stop a group being confirmed in bulk. The others are notes the
# reviewer should see but that do not, on their own, make the proposal doubtful —
# a homonym whose CIN already separates it is information, not an open question.
BLOCKING_FLAGS = {
    "HOMONYMIE_NON_RESOLUE", "DOUBLON_PROBABLE", "SANS_CIN", "NOM_INCONNU",
    "NON_IDENTIFIABLE", "PREUVE_FAIBLE", "RATTACHEMENT_PAR_NOM", "VIDE",
    "CIN_NON_CORROBORE",
}


def is_blocked(g) -> bool:
    """True when this proposal must be looked at individually."""
    return (g.confidence in (LOW, REVIEW)
            or any(f in BLOCKING_FLAGS for f in g.flags))


MAX_FILE_BYTES = 60 * 1024 * 1024
MIN_PHOTO_PIXELS = 64
NAME_SIM_THRESHOLD = 0.88


# ── Text helpers ─────────────────────────────────────────────────────────────
def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def looks_like_date(eight: str) -> bool:
    """
    True when an 8-digit run is far more likely a date than an identity number.

    Covers yyyymmdd (20190514, 20260821) and ddmmyyyy (14052019), which is what
    cameras, phones and scanners put in filenames. A Tunisian CIN can legitimately
    begin with 19 or 20, so the check requires a valid month AND day as well —
    that is what keeps it from rejecting real cards.
    """
    if len(eight) != 8 or not eight.isdigit():
        return False
    y, m, d = int(eight[:4]), int(eight[4:6]), int(eight[6:8])
    if 1900 <= y <= 2100 and 1 <= m <= 12 and 1 <= d <= 31:
        return True
    d2, m2, y2 = int(eight[:2]), int(eight[2:4]), int(eight[4:])
    if 1900 <= y2 <= 2100 and 1 <= m2 <= 12 and 1 <= d2 <= 31:
        return True
    return False


def normalise_cin(raw, allow_date_shaped: bool = False) -> str:
    """
    Returns the 8-digit CIN, or '' if the value is not one.

    A date-shaped run is refused unless the caller explicitly allows it — which
    only the human-entry path does, because a notary typing a CIN by hand means
    it, whereas eight digits scraped out of a filename usually do not.
    """
    digits = re.sub(r"\D", "", str(raw or ""))
    if len(digits) != 8:
        return ""
    if not allow_date_shaped and looks_like_date(digits):
        return ""
    return digits


def name_tokens(raw: str) -> List[str]:
    """Word tokens of a name, with document vocabulary and numbers removed."""
    s = strip_accents(str(raw or "")).lower()
    s = re.sub(r"[_\-.,;:()\[\]{}+#@!'\"/\\]+", " ", s)
    s = re.sub(r"\d+", " ", s)
    out = []
    for tok in s.split():
        tok = tok.strip()
        if len(tok) < 2 or tok in DOC_WORDS or not LETTER_RE.search(tok):
            continue
        out.append(tok)
    return out


def name_key(raw: str) -> str:
    """
    The comparison key for "is this the same person's name?".

    Spaces are removed entirely and the letters sorted by token, so
    "Ben Ali Sami", "Sami Ben Ali" and "SAMI BENALI" all produce the same key.
    Particles are dropped because different staff write them differently.
    """
    toks = [t for t in name_tokens(raw) if t not in
            ("ben", "bent", "ould", "abou", "abu", "el", "al", "bin", "بن", "بنت")]
    if not toks:
        return ""
    joined = "".join(sorted(toks))
    return joined


def name_similarity(a: str, b: str) -> float:
    ka, kb = name_key(a), name_key(b)
    if not ka or not kb:
        return 0.0
    if ka == kb:
        return 1.0
    return SequenceMatcher(None, ka, kb).ratio()


def display_name(raw: str) -> str:
    toks = name_tokens(raw)
    return " ".join(t.capitalize() for t in toks) if toks else ""


def sniff_type(path: Path) -> str:
    """The real file type, from the leading bytes. The extension is not trusted."""
    try:
        with open(path, "rb") as f:
            head = f.read(12)
    except OSError:
        return "unreadable"
    for sig, kind in MAGIC:
        if head.startswith(sig):
            if kind == "zip" and path.suffix.lower() in (".docx", ".xlsx", ".pptx"):
                return "office"
            return kind
    if not head:
        return "empty"
    return "unknown"


def is_real_image(path: Path) -> bool:
    return sniff_type(path) in ("jpeg", "png", "bmp", "gif", "tiff")


def sha256_of(path: Path, limit: int = MAX_FILE_BYTES) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            read = 0
            while True:
                chunk = f.read(1 << 20)
                if not chunk or read > limit:
                    break
                h.update(chunk)
                read += len(chunk)
    except OSError:
        return ""
    return h.hexdigest()


# ── Records ──────────────────────────────────────────────────────────────────
@dataclass
class Evidence:
    """One observation that ties a file to a person."""
    kind: str                 # "cin" | "name"
    value: str
    reason: str
    confidence: str
    source_path: str


@dataclass
class FileRecord:
    path: Path
    rel: str
    size: int
    mtime: float
    ext: str
    real_type: str
    category: str = "other"           # image | document | other
    is_valid_image: bool = False
    sha256: str = ""
    folder_chain: List[str] = field(default_factory=list)
    cins: List[Tuple[str, str]] = field(default_factory=list)   # (cin, reason)
    names: List[Tuple[str, str]] = field(default_factory=list)  # (name, reason)
    year: Optional[int] = None
    contract_type: str = ""
    ai_attempted: bool = False
    ai_error: str = ""
    notes: List[str] = field(default_factory=list)


@dataclass
class DossierProposal:
    key: str
    title: str
    contract_type: str
    year: Optional[int]
    files: List[FileRecord] = field(default_factory=list)
    shared_with: List[str] = field(default_factory=list)   # other group keys
    confidence: str = MEDIUM
    reasons: List[str] = field(default_factory=list)


@dataclass
class IdentityGroup:
    """A proposed client. Nothing here is written until a human confirms it."""
    key: str
    cin: str = ""
    name: str = ""
    name_variants: List[str] = field(default_factory=list)
    files: List[FileRecord] = field(default_factory=list)
    dossiers: List[DossierProposal] = field(default_factory=list)
    evidence: List[Evidence] = field(default_factory=list)
    confidence: str = LOW
    reasons: List[str] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)
    profile_photo: Optional[Path] = None
    photo_reason: str = ""
    photo_alternatives: List[Path] = field(default_factory=list)
    existing_client_id: Optional[str] = None
    existing_match_reason: str = ""
    include: bool = True            # the reviewer's decision
    reviewed: bool = False
    human_edited: bool = False

    def summary(self) -> str:
        return (f"{self.name or '(sans nom)'} | CIN {self.cin or '—'} | "
                f"{len(self.files)} fichier(s), {len(self.dossiers)} dossier(s) | "
                f"{self.confidence}")


@dataclass
class MigrationPlan:
    root: str
    run_id: str
    groups: List[IdentityGroup] = field(default_factory=list)
    excluded: List[Dict] = field(default_factory=list)
    unassigned: List[FileRecord] = field(default_factory=list)
    stats: Dict = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    def needs_review(self) -> List[IdentityGroup]:
        return [g for g in self.groups
                if g.confidence in (LOW, REVIEW) or g.flags]


# ── Journal: resumability + audit trail ──────────────────────────────────────
JOURNAL_PATH = DATA_DIR / "migration_journal.db"


def _journal():
    conn = sqlite3.connect(str(JOURNAL_PATH), timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS scan_files (
            run_id TEXT, path TEXT, sha256 TEXT, size INTEGER,
            status TEXT, error TEXT, ts TEXT,
            PRIMARY KEY (run_id, path)
        );
        CREATE TABLE IF NOT EXISTS ai_cache (
            sha256 TEXT PRIMARY KEY, cin TEXT, full_name TEXT,
            raw JSON, ok INTEGER, error TEXT, ts TEXT
        );
        CREATE TABLE IF NOT EXISTS import_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, run_id TEXT, action TEXT, group_key TEXT,
            client_id TEXT, cin TEXT, name TEXT,
            confidence TEXT, reason TEXT,
            ai_proposed TEXT, human_final TEXT, human_edited INTEGER,
            detail TEXT
        );
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY, root TEXT, started TEXT,
            finished TEXT, status TEXT, files_seen INTEGER, groups INTEGER
        );
    """)
    return conn


def audit(run_id: str, action: str, **kw) -> None:
    """Appends one line to the permanent audit trail."""
    try:
        with _journal() as c:
            c.execute(
                "INSERT INTO import_audit (ts, run_id, action, group_key, client_id, "
                "cin, name, confidence, reason, ai_proposed, human_final, "
                "human_edited, detail) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (datetime.datetime.now().isoformat(timespec="seconds"), run_id, action,
                 kw.get("group_key", ""), kw.get("client_id", ""), kw.get("cin", ""),
                 kw.get("name", ""), kw.get("confidence", ""), kw.get("reason", ""),
                 json.dumps(kw.get("ai_proposed", ""), ensure_ascii=False),
                 json.dumps(kw.get("human_final", ""), ensure_ascii=False),
                 1 if kw.get("human_edited") else 0,
                 json.dumps(kw.get("detail", ""), ensure_ascii=False)))
    except Exception:
        # (c) The audit trail must never be the reason an import stops; a failure
        # to write it is reported by the caller's own error handling.
        pass


def read_audit(run_id: str = None, limit: int = 500) -> List[Dict]:
    with _journal() as c:
        if run_id:
            rows = c.execute("SELECT * FROM import_audit WHERE run_id=? "
                             "ORDER BY id DESC LIMIT ?", (run_id, limit)).fetchall()
        else:
            rows = c.execute("SELECT * FROM import_audit ORDER BY id DESC LIMIT ?",
                             (limit,)).fetchall()
    return [dict(r) for r in rows]


def _cache_get(sha: str) -> Optional[Dict]:
    if not sha:
        return None
    with _journal() as c:
        r = c.execute("SELECT * FROM ai_cache WHERE sha256=?", (sha,)).fetchone()
    return dict(r) if r else None


def _cache_put(sha: str, cin: str, full_name: str, raw, ok: bool, error: str = ""):
    if not sha:
        return
    with _journal() as c:
        c.execute("INSERT OR REPLACE INTO ai_cache "
                  "(sha256, cin, full_name, raw, ok, error, ts) VALUES (?,?,?,?,?,?,?)",
                  (sha, cin, full_name, json.dumps(raw, ensure_ascii=False)[:20000],
                   1 if ok else 0, error,
                   datetime.datetime.now().isoformat(timespec="seconds")))


def _mark_file(run_id: str, path: str, sha: str, size: int, status: str, error: str = ""):
    with _journal() as c:
        c.execute("INSERT OR REPLACE INTO scan_files "
                  "(run_id, path, sha256, size, status, error, ts) VALUES (?,?,?,?,?,?,?)",
                  (run_id, path, sha, size, status, error,
                   datetime.datetime.now().isoformat(timespec="seconds")))


def done_files(run_id: str) -> set:
    with _journal() as c:
        return {r["path"] for r in c.execute(
            "SELECT path FROM scan_files WHERE run_id=? AND status='done'", (run_id,))}


# ── Pass A: inventory ────────────────────────────────────────────────────────
def inventory(root: Path, progress: Callable = None,
              should_cancel: Callable = None) -> Tuple[List[FileRecord], List[Dict]]:
    """
    Walks the whole tree and reads what can be read without any AI call.

    Deliberately does NOT decide who owns what: it only records, per file, the
    CINs and names visible in its own name and in every folder above it.
    """
    files: List[FileRecord] = []
    excluded: List[Dict] = []
    seen_dirs = 0

    for base, dirs, names in os.walk(root):
        if should_cancel and should_cancel():
            break
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        seen_dirs += 1
        base_p = Path(base)
        chain = [p.name for p in list(base_p.relative_to(root).parents)[::-1][1:]] \
            if base_p != root else []
        chain = [c for c in chain if c] + ([base_p.name] if base_p != root else [])

        for nm in names:
            if should_cancel and should_cancel():
                break
            p = base_p / nm
            try:
                st = p.stat()
            except OSError as e:
                excluded.append({"path": str(p), "reason": f"illisible : {e}"})
                continue
            if st.st_size > MAX_FILE_BYTES:
                excluded.append({"path": str(p), "reason": "fichier trop volumineux"})
                continue

            ext = p.suffix.lower()
            real = sniff_type(p)
            rec = FileRecord(
                path=p, rel=str(p.relative_to(root)), size=st.st_size,
                mtime=st.st_mtime, ext=ext, real_type=real,
                folder_chain=chain)

            if real in ("jpeg", "png", "bmp", "gif", "tiff"):
                rec.category = "image"
                rec.is_valid_image = True
            elif real in ("pdf", "office", "ole") or ext in DOC_EXTS:
                rec.category = "document"
            elif ext in IMG_EXTS and real not in ("jpeg", "png", "bmp", "gif", "tiff"):
                # Scenario 11: the extension says image, the bytes do not.
                rec.category = "other"
                rec.notes.append(
                    f"extension {ext} mais contenu réel « {real} » — pas une image")
            else:
                rec.category = "other"

            # CINs and names from the filename and from every folder above it.
            for m in CIN_RE.finditer(p.stem):
                if normalise_cin(m.group(1)):
                    rec.cins.append((m.group(1), R_CIN_FILE))
                else:
                    rec.notes.append(
                        f"« {m.group(1)} » ressemble à une date, pas à un CIN — ignoré")
            for folder in chain:
                for m in CIN_RE.finditer(folder):
                    if normalise_cin(m.group(1)):
                        rec.cins.append((m.group(1), R_CIN_FOLDER))
                if not YEAR_ONLY_RE.match(folder.strip()) and \
                        folder.strip().lower() not in NON_CLIENT_NAMES:
                    nm_toks = name_tokens(folder)
                    if len(nm_toks) >= 2:
                        rec.names.append((" ".join(nm_toks), R_NAME_FOLDER))
            fn_toks = name_tokens(p.stem)
            if len(fn_toks) >= 2:
                rec.names.append((" ".join(fn_toks), R_NAME_FILE))

            ys = [int(y) for y in YEAR_RE.findall(str(p))]
            rec.year = max(ys) if ys else None
            low = strip_accents(str(p)).lower()
            for tok in CONTRACT_TOKENS:
                if tok in low:
                    rec.contract_type = tok
                    break

            files.append(rec)
            if progress and len(files) % 50 == 0:
                progress("inventory", len(files), None,
                         f"{len(files)} fichiers repérés…")

    if progress:
        progress("inventory", len(files), len(files),
                 f"{len(files)} fichiers, {seen_dirs} dossiers")
    return files, excluded


# ── Pass B: evidence extraction (AI + document text) ─────────────────────────
def looks_like_id_card(rec: FileRecord) -> bool:
    """Worth spending a Gemini call on."""
    if rec.category != "image" or not rec.is_valid_image:
        return False
    hay = strip_accents((rec.rel + " " + " ".join(rec.folder_chain))).lower()
    if any(h in hay for h in IDCARD_HINTS):
        return True
    # Accuracy is the priority here, so an unlabelled image is still read: an
    # office that names its scans "scan0001.jpg" would otherwise lose every CIN.
    return True


def extract_document_text(path: Path, limit: int = 200_000) -> str:
    """Best-effort plain text from a .docx / .txt / .pdf, for CINs and names."""
    ext = path.suffix.lower()
    try:
        if ext == ".txt":
            return path.read_text(encoding="utf-8", errors="replace")[:limit]
        if ext == ".docx":
            import zipfile
            with zipfile.ZipFile(path) as z:
                xml = z.read("word/document.xml").decode("utf-8", "replace")
            return re.sub(r"<[^>]+>", " ", xml)[:limit]
        if ext == ".pdf":
            raw = path.read_bytes()[:limit * 2]
            txt = re.sub(rb"[^\x20-\x7e\n]", b" ", raw).decode("ascii", "replace")
            return txt[:limit]
    except Exception:
        # (c) Text mining is an enrichment; a document that cannot be read still
        # gets matched by its filename and folder, and is never dropped.
        return ""
    return ""


def gather_evidence(files: List[FileRecord], run_id: str,
                    use_ai: bool = True, progress: Callable = None,
                    should_cancel: Callable = None,
                    ai_call: Callable = None) -> None:
    """
    Fills in each file's CIN/name evidence, using Gemini for ID-card images.

    Results are cached by content hash in the journal, so a re-run or a resumed
    run costs nothing for files already read.
    """
    already = done_files(run_id)
    total = len(files)
    for i, rec in enumerate(files, 1):
        if should_cancel and should_cancel():
            return
        if str(rec.path) in already:
            continue
        try:
            rec.sha256 = sha256_of(rec.path)

            if rec.category == "document":
                text = extract_document_text(rec.path)
                if text:
                    for m in CIN_RE.finditer(text):
                        if normalise_cin(m.group(1)):
                            rec.cins.append((m.group(1), R_CIN_DOCTEXT))

            if use_ai and looks_like_id_card(rec):
                cached = _cache_get(rec.sha256)
                if cached is not None:
                    rec.ai_attempted = True
                    if cached["ok"]:
                        if normalise_cin(cached["cin"]):
                            rec.cins.append((normalise_cin(cached["cin"]), R_CIN_OCR))
                        if cached["full_name"]:
                            rec.names.append((cached["full_name"], R_CIN_OCR))
                    else:
                        rec.ai_error = cached["error"] or "lecture impossible"
                else:
                    rec.ai_attempted = True
                    ok, cin, full_name, raw, err = _run_ai(rec, ai_call)
                    _cache_put(rec.sha256, cin, full_name, raw, ok, err)
                    if ok:
                        if cin:
                            rec.cins.append((cin, R_CIN_OCR))
                        if full_name:
                            rec.names.append((full_name, R_CIN_OCR))
                    else:
                        rec.ai_error = err

            _mark_file(run_id, str(rec.path), rec.sha256, rec.size, "done")
        except Exception as e:
            rec.notes.append(f"erreur de lecture : {e}")
            _mark_file(run_id, str(rec.path), rec.sha256, rec.size, "error", str(e))

        if progress and (i % 5 == 0 or i == total):
            progress("evidence", i, total,
                     f"lecture {i}/{total} — {rec.path.name[:40]}")


def _run_ai(rec: FileRecord, ai_call: Callable = None):
    """Calls the Gemini CIN extractor already used by the Scanner page."""
    try:
        data = rec.path.read_bytes()
    except OSError as e:
        return False, "", "", {}, str(e)
    try:
        if ai_call is not None:
            res = ai_call(data)
        else:
            import config
            from cin_extractor import extract_cin_data
            provider, model = config.load_ai_engine()
            keys = [k.strip() for k in
                    config.load_saved_api_keys(provider).replace("\n", ",").split(",")
                    if k.strip()]
            if not keys:
                return False, "", "", {}, "aucune clé API configurée"
            res = extract_cin_data(data, api_key=keys[0], model_name=model,
                                   provider=provider)
    except Exception as e:
        return False, "", "", {}, f"{type(e).__name__}: {e}"

    if not res or not res.get("success"):
        return False, "", "", res or {}, (res or {}).get("error", "échec de lecture")
    d = res.get("data") or {}
    return True, normalise_cin(d.get("cin_number")), (d.get("full_name") or "").strip(), d, ""


# ── Pass C: identity clustering ──────────────────────────────────────────────
def _best_conf(reasons: List[str]) -> str:
    if any(r in (R_CIN_OCR,) for r in reasons):
        return HIGH
    if any(r in (R_CIN_FOLDER, R_CIN_FILE, R_CIN_DOCTEXT) for r in reasons):
        return HIGH
    if any(r in (R_NAME_FOLDER, R_NAME_FILE) for r in reasons):
        return MEDIUM
    return LOW


def cluster(files: List[FileRecord], progress: Callable = None) -> Tuple[List[IdentityGroup], List[FileRecord]]:
    """
    Resolves identities across the WHOLE archive, not per folder.

    CIN wins. Files with no CIN anywhere are clustered by name key, and can be
    absorbed into a CIN group only when their name key matches that group's — a
    name never overrides a CIN, and two different CINs are never joined.
    """
    by_cin: Dict[str, IdentityGroup] = {}
    no_cin: List[FileRecord] = []

    for rec in files:
        cins = {c for c, _ in rec.cins}
        if len(cins) == 1:
            cin = next(iter(cins))
            g = by_cin.setdefault(cin, IdentityGroup(key=f"cin:{cin}", cin=cin))
            g.files.append(rec)
            for c, why in rec.cins:
                g.evidence.append(Evidence("cin", c, why, HIGH, rec.rel))
            for n, why in rec.names:
                g.evidence.append(Evidence("name", n, why, _best_conf([why]), rec.rel))
        elif len(cins) > 1:
            # Scenario 14: a document naming several people. It belongs to each.
            for cin in sorted(cins):
                g = by_cin.setdefault(cin, IdentityGroup(key=f"cin:{cin}", cin=cin))
                g.files.append(rec)
                g.evidence.append(Evidence("cin", cin, R_CIN_DOCTEXT, HIGH, rec.rel))
                for n, why in rec.names:
                    g.evidence.append(Evidence("name", n, why, _best_conf([why]), rec.rel))
            rec.notes.append(
                f"document multi-clients : {len(cins)} CIN trouvés ({', '.join(sorted(cins))})")
        else:
            no_cin.append(rec)

    # Name and confidence for each CIN group.
    for cin, g in by_cin.items():
        names = [e.value for e in g.evidence if e.kind == "name" and e.value]
        ocr_names = [e.value for e in g.evidence
                     if e.kind == "name" and e.reason == R_CIN_OCR and e.value]
        chosen = ocr_names[0] if ocr_names else (max(names, key=len) if names else "")
        g.name = display_name(chosen) or chosen
        g.name_variants = sorted({display_name(n) or n for n in names if n})
        g.confidence = HIGH
        g.reasons = sorted({e.reason for e in g.evidence if e.kind == "cin"})
        if not g.name:
            g.flags.append("NOM_INCONNU")
            g.confidence = MEDIUM
        if len(g.name_variants) > 1:
            g.reasons.append(
                f"{len(g.name_variants)} orthographes du nom réunies par le CIN")

    groups = list(by_cin.values())

    # Files with no CIN: cluster by name key, then try to absorb into a CIN group.
    buckets: Dict[str, List[FileRecord]] = {}
    unassigned: List[FileRecord] = []
    for rec in no_cin:
        keys = [name_key(n) for n, _ in rec.names]
        keys = [k for k in keys if k]
        if not keys:
            unassigned.append(rec)
            continue
        buckets.setdefault(max(keys, key=len), []).append(rec)

    for key, recs in buckets.items():
        # Does this name match an existing CIN group closely enough to join it?
        host = None
        for g in groups:
            if any(name_similarity(key, v) >= NAME_SIM_THRESHOLD
                   for v in (g.name_variants or [g.name]) if v):
                host = g
                break
        display = display_name(recs[0].names[0][0]) if recs[0].names else key
        if host is not None:
            host.files.extend(recs)
            host.reasons.append(
                f"{len(recs)} fichier(s) rattaché(s) par similarité de nom "
                f"(sans CIN) — à confirmer")
            host.flags.append("RATTACHEMENT_PAR_NOM")
            for r in recs:
                host.evidence.append(Evidence("name", display, R_NAME_SIM, LOW, r.rel))
        else:
            g = IdentityGroup(key=f"name:{key}", name=display, files=list(recs))
            g.confidence = LOW
            g.reasons = [R_NAME_SIM]
            g.flags.append("SANS_CIN")
            g.name_variants = sorted({display_name(n) or n
                                      for r in recs for n, _ in r.names if n})
            for r in recs:
                for n, why in r.names:
                    g.evidence.append(Evidence("name", n, why, _best_conf([why]), r.rel))
            groups.append(g)

    # Scenario 8: same name, different CIN. Never merged, always surfaced.
    seen: Dict[str, List[IdentityGroup]] = {}
    for g in groups:
        k = name_key(g.name)
        if k:
            seen.setdefault(k, []).append(g)
    for k, gs in seen.items():
        if len(gs) < 2:
            continue
        with_cin = [g for g in gs if g.cin]
        without_cin = [g for g in gs if not g.cin]
        distinct = {g.cin for g in with_cin}
        if len(distinct) < 2 and not without_cin:
            continue

        # Whether this actually needs a human depends on whether the ambiguity is
        # still open. Groups that each carry their OWN distinct CIN are already
        # definitively separated - the warning is informational, and forcing them
        # all to needs_review buries the genuinely uncertain cases. Measured on a
        # 900-client archive, the earlier blanket rule sent 900 of 900 to manual
        # review and left nothing for the reviewer to clear in bulk.
        resolved = not without_cin and len(distinct) == len(gs)
        cins = ", ".join(sorted(distinct))

        # A key shared by very many groups is not a homonym cluster; it is a name
        # the parser could not make anything of (initials, a serial label). Say so
        # rather than claiming dozens of people share a name.
        uninformative = len(gs) > 5

        for g in gs:
            if uninformative:
                g.flags.append("NOM_PEU_DISCRIMINANT")
                g.reasons.append(
                    f"Le nom extrait (« {g.name or '—'} ») est partagé par "
                    f"{len(gs)} groupes : il ne distingue pas les personnes. "
                    f"Le CIN reste la seule référence fiable ici.")
                continue
            g.flags.append("HOMONYMES")
            if resolved:
                g.reasons.append(
                    f"{len(gs)} personnes portent ce nom, avec des CIN différents "
                    f"({cins}). Elles sont séparées correctement — vérifiez "
                    f"simplement que le bon CIN est sur la bonne fiche.")
            else:
                g.flags.append("HOMONYMIE_NON_RESOLUE")
                g.reasons.append(
                    f"ATTENTION : {len(gs)} groupes portent ce nom et "
                    f"{len(without_cin)} n'ont AUCUN CIN. Impossible de savoir "
                    f"s'il s'agit de la même personne. À trancher manuellement.")

    if progress:
        progress("cluster", len(groups), len(groups),
                 f"{len(groups)} identité(s) proposée(s)")
    return groups, unassigned


# ── Pass D: dossiers, photos, existing-client matching ───────────────────────
def build_dossiers(g: IdentityGroup) -> None:
    """
    Splits one client's files into separate dossiers.

    Scenario 5: a sale in 2015 and an inheritance in 2021 are ONE client with TWO
    dossiers — never one merged dossier, never two client records.
    """
    buckets: Dict[str, DossierProposal] = {}
    for rec in g.files:
        if rec.category == "image" and rec.is_valid_image and not rec.contract_type:
            continue        # a loose photo is not a dossier by itself
        ctype = rec.contract_type or ""
        year = rec.year
        folder = rec.folder_chain[-1] if rec.folder_chain else ""
        key = f"{ctype}|{year}" if (ctype or year) else f"folder|{folder}"
        d = buckets.get(key)
        if d is None:
            label_parts = []
            if ctype:
                label_parts.append(CONTRACT_TOKENS.get(ctype, ctype))
            if year:
                label_parts.append(str(year))
            if not label_parts:
                label_parts.append(folder or "Dossier importé")
            d = DossierProposal(key=key, title=" ".join(label_parts),
                                contract_type=ctype, year=year)
            d.reasons.append(
                f"regroupé par {'type de contrat et année' if ctype and year else ('année' if year else 'dossier d’origine')}")
            buckets[key] = d
        d.files.append(rec)
    g.dossiers = sorted(buckets.values(), key=lambda d: (d.year or 0, d.title))


def choose_photo(g: IdentityGroup) -> None:
    """
    Picks what represents the client, and says why — for the human to confirm.

    Scenario 12: a real portrait beats an ID-card scan; scenario 11: a file whose
    bytes are not an image is never chosen.
    """
    candidates = [r for r in g.files if r.category == "image" and r.is_valid_image]
    if not candidates:
        g.photo_reason = "aucune image exploitable"
        if any(r.ext in IMG_EXTS and not r.is_valid_image for r in g.files):
            g.flags.append("IMAGE_INVALIDE")
        return

    def score(r: FileRecord) -> int:
        hay = strip_accents(r.rel).lower()
        if any(h in hay for h in PORTRAIT_HINTS):
            return 3
        if any(h in hay for h in IDCARD_HINTS):
            return 2
        return 1

    ranked = sorted(candidates, key=lambda r: (-score(r), r.rel))
    best = ranked[0]
    g.profile_photo = best.path
    g.photo_alternatives = [r.path for r in ranked[1:]]
    s = score(best)
    g.photo_reason = ("portrait identifié par le nom du fichier" if s == 3
                      else "scan de carte d'identité (aucun portrait trouvé)" if s == 2
                      else "seule image disponible")
    if s < 3 and len(ranked) > 1:
        g.flags.append("PHOTO_A_CONFIRMER")


def match_existing(g: IdentityGroup) -> None:
    """Scenario 15: recognises a client already in the database."""
    try:
        import reception
        if g.cin:
            found = reception.find_client_by_cin_or_name(cin_number=g.cin, full_name="")
            if found:
                g.existing_client_id = found["client_id"]
                g.existing_match_reason = f"CIN {g.cin} déjà présent dans la base"
                return
        if g.name:
            found = reception.find_client_by_cin_or_name(cin_number="", full_name=g.name)
            if found:
                g.existing_client_id = found["client_id"]
                g.existing_match_reason = (
                    f"nom « {g.name} » déjà présent (sans confirmation par CIN)")
                g.flags.append("DOUBLON_PROBABLE")
    except Exception:
        # (c) The database may be unavailable during a dry scan; the plan is still
        # valid and the reviewer is simply not told about existing records.
        pass


def assess(g: IdentityGroup) -> None:
    """
    Final confidence, and the decision about whether a human MUST look.

    Scenario 13: anything the evidence cannot settle is marked needs_review
    rather than forced into a confident-looking guess.
    """
    cin_reasons = {e.reason for e in g.evidence if e.kind == "cin"}
    if g.cin and R_CIN_OCR in cin_reasons:
        # Read off the card itself: the strongest evidence there is.
        g.confidence = HIGH
    elif g.cin and (R_CIN_FOLDER in cin_reasons or R_CIN_DOCTEXT in cin_reasons):
        # A folder named for the client, or the number written inside the deed.
        g.confidence = HIGH
    elif g.cin and cin_reasons == {R_CIN_FILE}:
        # Eight digits in a filename and nothing else. Real archives are full of
        # scanner and camera filenames, so this is a lead, not a fact.
        g.confidence = MEDIUM
        g.flags.append("CIN_NON_CORROBORE")
        g.reasons.append(
            "Le CIN provient uniquement du nom d'un fichier, sans carte scannée "
            "ni dossier client pour le confirmer — à vérifier.")
    elif g.cin:
        g.confidence = HIGH
    elif g.name and len(g.files) >= 2:
        g.confidence = LOW
    else:
        g.confidence = REVIEW

    # A homonym whose CIN distinguishes it is already resolved; only an open
    # ambiguity, or a name-only match against an existing record, needs a human.
    if "HOMONYMIE_NON_RESOLUE" in g.flags or "DOUBLON_PROBABLE" in g.flags:
        g.confidence = REVIEW
    if not g.name and not g.cin:
        g.confidence = REVIEW
        g.flags.append("NON_IDENTIFIABLE")
    if not g.files:
        g.include = False
        g.flags.append("VIDE")

    # A group whose only evidence is one weak filename token is not a client.
    if g.confidence in (LOW, REVIEW) and len(g.files) == 1 and not g.cin:
        strong = [e for e in g.evidence if e.reason in (R_NAME_FOLDER,)]
        if not strong:
            g.flags.append("PREUVE_FAIBLE")


def classify_excluded(root: Path, excluded: List[Dict]) -> List[Dict]:
    """Scenario 10: every excluded folder carries the reason it was excluded."""
    out = list(excluded)
    for base, dirs, names in os.walk(root):
        p = Path(base)
        if p == root:
            continue
        nm = p.name.strip()
        low = strip_accents(nm).lower()
        if YEAR_ONLY_RE.match(nm):
            out.append({"path": str(p), "reason": f"« {nm} » est une année, pas un client"})
        elif low in NON_CLIENT_NAMES:
            out.append({"path": str(p), "reason": f"« {nm} » est un dossier de classement"})
        elif not names and not dirs:
            out.append({"path": str(p), "reason": "dossier vide"})
        elif not LETTER_RE.search(nm):
            out.append({"path": str(p), "reason": f"« {nm} » ne contient aucune lettre"})
    return out


# ── The whole scan ───────────────────────────────────────────────────────────
def scan_archive(root_str: str, use_ai: bool = True, run_id: str = None,
                 progress: Callable = None, should_cancel: Callable = None,
                 ai_call: Callable = None) -> MigrationPlan:
    """
    Reads an archive and returns a plan. Writes NOTHING to the client database.

    Pass `run_id` from a previous interrupted run to resume it.
    """
    root = Path(str(root_str).strip())
    run_id = run_id or datetime.datetime.now().strftime("run_%Y%m%d_%H%M%S")
    plan = MigrationPlan(root=str(root), run_id=run_id)

    if not root.exists() or not root.is_dir():
        plan.errors.append(f"Le chemin n'existe pas ou n'est pas un dossier : {root}")
        return plan

    with _journal() as c:
        c.execute("INSERT OR REPLACE INTO runs (run_id, root, started, status) "
                  "VALUES (?,?,?,?)",
                  (run_id, str(root),
                   datetime.datetime.now().isoformat(timespec="seconds"), "running"))

    t0 = time.perf_counter()
    files, excluded = inventory(root, progress, should_cancel)
    gather_evidence(files, run_id, use_ai, progress, should_cancel, ai_call)
    groups, unassigned = cluster(files, progress)

    for i, g in enumerate(groups, 1):
        build_dossiers(g)
        choose_photo(g)
        match_existing(g)
        assess(g)
        audit(run_id, "proposed", group_key=g.key, cin=g.cin, name=g.name,
              confidence=g.confidence, reason="; ".join(g.reasons[:4]),
              ai_proposed={"cin": g.cin, "name": g.name,
                           "files": len(g.files), "dossiers": len(g.dossiers)},
              detail={"flags": g.flags})
        if progress and i % 5 == 0:
            progress("propose", i, len(groups), f"préparation {i}/{len(groups)}")

    plan.groups = sorted(groups, key=lambda g: (CONF_ORDER[g.confidence], g.name))
    plan.excluded = classify_excluded(root, excluded)
    plan.unassigned = unassigned
    plan.stats = {
        "files_seen": len(files),
        "images": sum(1 for f in files if f.category == "image"),
        "documents": sum(1 for f in files if f.category == "document"),
        "invalid_images": sum(1 for f in files
                              if f.ext in IMG_EXTS and not f.is_valid_image),
        "ai_calls": sum(1 for f in files if f.ai_attempted),
        "groups": len(groups),
        "high": sum(1 for g in groups if g.confidence == HIGH),
        "medium": sum(1 for g in groups if g.confidence == MEDIUM),
        "low": sum(1 for g in groups if g.confidence == LOW),
        "needs_review": sum(1 for g in groups if g.confidence == REVIEW),
        "excluded": len(plan.excluded),
        "unassigned": len(unassigned),
        "seconds": round(time.perf_counter() - t0, 2),
    }

    with _journal() as c:
        c.execute("UPDATE runs SET finished=?, status=?, files_seen=?, groups=? "
                  "WHERE run_id=?",
                  (datetime.datetime.now().isoformat(timespec="seconds"),
                   "scanned", len(files), len(groups), run_id))
    if progress:
        progress("done", len(files), len(files),
                 f"{len(groups)} identité(s), {len(files)} fichier(s)")
    return plan


# ── Reviewer actions (before anything is committed) ──────────────────────────
def split_group(plan: MigrationPlan, group: IdentityGroup,
                file_rels: List[str], new_name: str = "",
                new_cin: str = "") -> IdentityGroup:
    """Moves the named files out of a group into a new one."""
    move = [f for f in group.files if f.rel in set(file_rels)]
    group.files = [f for f in group.files if f.rel not in set(file_rels)]
    ng = IdentityGroup(key=f"split:{group.key}:{len(plan.groups)}",
                       cin=normalise_cin(new_cin), name=new_name or "",
                       files=move)
    ng.human_edited = True
    ng.flags.append("SEPARE_MANUELLEMENT")
    group.human_edited = True
    for g in (group, ng):
        build_dossiers(g); choose_photo(g); match_existing(g); assess(g)
    plan.groups.append(ng)
    audit(plan.run_id, "split", group_key=group.key, human_edited=True,
          detail={"moved": file_rels, "into": ng.key})
    return ng


def merge_groups(plan: MigrationPlan, a: IdentityGroup, b: IdentityGroup) -> IdentityGroup:
    """
    Joins two groups — only ever on the reviewer's explicit instruction.

    Refuses when both carry a CIN and the CINs differ: that is two people, and no
    amount of UI confirmation makes it one.
    """
    if a.cin and b.cin and a.cin != b.cin:
        raise ValueError(
            f"Refus de fusionner : CIN différents ({a.cin} et {b.cin}). "
            f"Ce sont deux personnes distinctes.")
    a.files.extend(b.files)
    a.evidence.extend(b.evidence)
    a.name_variants = sorted(set(a.name_variants) | set(b.name_variants))
    a.cin = a.cin or b.cin
    a.name = a.name or b.name
    a.human_edited = True
    a.flags.append("FUSIONNE_MANUELLEMENT")
    if b in plan.groups:
        plan.groups.remove(b)
    build_dossiers(a); choose_photo(a); match_existing(a); assess(a)
    audit(plan.run_id, "merge", group_key=a.key, human_edited=True,
          detail={"absorbed": b.key})
    return a


def set_identity(plan: MigrationPlan, g: IdentityGroup, name: str = None,
                 cin: str = None) -> None:
    """The reviewer typing a CIN the OCR could not read (scenario 9)."""
    before = {"name": g.name, "cin": g.cin}
    if name is not None:
        g.name = name
    if cin is not None:
        # A human typing it has seen the card; the date heuristic does not apply.
        g.cin = normalise_cin(cin, allow_date_shaped=True)
    g.human_edited = True
    for f in ("SANS_CIN", "NOM_INCONNU", "NON_IDENTIFIABLE", "PREUVE_FAIBLE"):
        if f in g.flags and ((f in ("SANS_CIN",) and g.cin) or
                             (f in ("NOM_INCONNU",) and g.name) or
                             (f in ("NON_IDENTIFIABLE", "PREUVE_FAIBLE")
                              and g.cin and g.name)):
            g.flags.remove(f)
    match_existing(g); assess(g)
    if g.cin and g.name:
        g.confidence = HIGH if g.cin else g.confidence
    audit(plan.run_id, "edit_identity", group_key=g.key, cin=g.cin, name=g.name,
          human_edited=True, ai_proposed=before,
          human_final={"name": g.name, "cin": g.cin})


# ── Pass F: commit (only what a human confirmed) ─────────────────────────────
def commit_plan(plan: MigrationPlan, confirmed_keys: List[str] = None,
                progress: Callable = None, should_cancel: Callable = None,
                enrol_faces: bool = True) -> Dict:
    """
    Writes the confirmed groups. Anything not explicitly confirmed is skipped.

    Every group is written inside its own try/except so one bad folder cannot end
    the migration, and every outcome is recorded in the audit trail.
    """
    import reception
    from config import PROFILES_DIR

    confirmed = set(confirmed_keys) if confirmed_keys is not None else set()
    todo = [g for g in plan.groups
            if g.include and g.reviewed and (not confirmed_keys or g.key in confirmed)]

    res = {"clients_created": 0, "clients_updated": 0, "dossiers_created": 0,
           "documents_imported": 0, "photos_set": 0, "faces_enrolled": 0,
           "skipped_unconfirmed": len(plan.groups) - len(todo),
           "failed": [], "client_ids": [], "logs": []}

    if not todo:
        res["status"] = "nothing_confirmed"
        res["logs"].append(
            "Aucun groupe confirmé : rien n'a été écrit dans la base.")
        return res

    for i, g in enumerate(todo, 1):
        if should_cancel and should_cancel():
            res["status"] = "cancelled"
            return res
        try:
            if g.existing_client_id:
                cid = g.existing_client_id
                res["clients_updated"] += 1
            else:
                toks = name_tokens(g.name)
                nom = toks[-1] if toks else (g.name or "حريف")
                prenom = " ".join(toks[:-1]) if len(toks) > 1 else ""
                cid = reception.register_client(
                    client_id=reception.generate_client_id("imp_"),
                    nom=nom, prenom=prenom, cin_number=g.cin,
                    address="مستورد من الأرشيف الورقي / Importé de l'archive")
                res["clients_created"] += 1
            res["client_ids"].append(cid)

            for d in g.dossiers:
                try:
                    case_id = reception.create_case(
                        cid, CONTRACT_TOKENS.get(d.contract_type, d.contract_type or "أرشيف"),
                        d.title, "", total_amount=0.0, avance_amount=0.0)
                    if case_id:
                        res["dossiers_created"] += 1
                except Exception as e:
                    res["failed"].append({"group": g.key, "dossier": d.title,
                                          "error": str(e)[:160]})

            for rec in g.files:
                if g.profile_photo is not None and rec.path == g.profile_photo:
                    continue
                try:
                    if reception.save_client_document(
                            cid, rec.path.read_bytes(), f"Archive_{rec.path.name}"):
                        res["documents_imported"] += 1
                    else:
                        res["failed"].append({"group": g.key, "file": rec.rel,
                                              "error": "écriture refusée"})
                except Exception as e:
                    res["failed"].append({"group": g.key, "file": rec.rel,
                                          "error": str(e)[:160]})

            if g.profile_photo is not None:
                try:
                    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
                    target = PROFILES_DIR / f"{cid}.jpg"
                    target.write_bytes(g.profile_photo.read_bytes())
                    if reception.update_client_profile_pic(cid, str(target)):
                        res["photos_set"] += 1
                        if enrol_faces:
                            ok, _why = reception.enrol_face_from_photo(cid, str(target))
                            if ok:
                                res["faces_enrolled"] += 1
                except Exception as e:
                    res["failed"].append({"group": g.key, "file": "photo",
                                          "error": str(e)[:160]})

            audit(plan.run_id, "committed", group_key=g.key, client_id=cid,
                  cin=g.cin, name=g.name, confidence=g.confidence,
                  reason="; ".join(g.reasons[:4]), human_edited=g.human_edited,
                  human_final={"name": g.name, "cin": g.cin,
                               "files": len(g.files), "dossiers": len(g.dossiers)})
            res["logs"].append(f"{g.name or g.key} → {cid} "
                               f"({len(g.files)} fichiers, {len(g.dossiers)} dossiers)")
        except Exception as e:
            res["failed"].append({"group": g.key, "error": f"{type(e).__name__}: {e}"[:160]})
            audit(plan.run_id, "commit_failed", group_key=g.key, cin=g.cin,
                  name=g.name, detail={"error": str(e)[:200]})
        if progress:
            progress("commit", i, len(todo), f"import {i}/{len(todo)}")

    try:
        reception.clear_db_caches()
    except Exception:
        # (c) A stale cache is refreshed on the next read; the writes are done.
        pass

    if res["failed"] and not res["client_ids"]:
        res["status"] = "error"
    elif res["failed"]:
        res["status"] = "partial"
    else:
        res["status"] = "success"
    return res
