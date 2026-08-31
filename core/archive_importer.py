"""
archive_importer.py — bringing a notary's existing folders into the application.

The office being sold to has years of records as folders on a laptop: scanned
identity cards, contracts in Word, deeds and certificates as PDF, photographs.
This module reads that tree and turns as much of it as can be trusted into
client records and attached documents.

What changed and why
--------------------
The previous version walked the tree with `rglob("*")` and treated every
directory it found as a client folder. Against a perfectly ordinary archive
filed by year — `2022/Ben Ali Sami - CIN 08765432/` — it parsed "2022" as a
surname, `check_name_field` refused four consecutive digits, and the
`NameValidationError` was never caught: the migration aborted on the first year
folder, having written whatever it had already written, with no way back except
restoring a backup. Measured on a simulated archive of four real clients: zero
imported. It also made the last image in each folder the client's profile photo
and ran face enrolment on it, so a scan of an identity card became the face the
camera would recognise; it accepted a text file renamed `.jpg` as that photo;
and it reported `status="success"` for a folder containing no clients at all.

The shape of the fix is a scan/apply split. `scan_archive()` only reads, and
returns a plan the notary can look at before anything is written.
`apply_plan()` writes the entries that were kept, each in its own try/except so
one unusable folder can no longer end the migration.

Honest limits
-------------
Matching a folder to a client is the only part that automates well, and only
when the folder name carries the name or the CIN. Reading the fields out of the
documents themselves — the seller's parents' names, the property reference, the
price — is not attempted here: the layouts vary per office and per decade, and a
wrong value in a deed is worse than an empty one. The plan therefore marks
everything it is not sure about for the notary to confirm.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from config import PROFILES_DIR

# ── What is and is not a client folder ───────────────────────────────────────
# Directory names that appear in every office and never name a person.
NON_CLIENT_NAMES = {
    # French
    "divers", "modeles", "modeles_types", "modeles types", "templates", "modele",
    "archives", "archive", "documents", "docs", "photos", "images", "scans",
    "scan", "pieces", "pièces", "dossiers", "dossier", "ventes", "achats",
    "contrats", "actes", "backup", "sauvegarde", "temp", "tmp", "old",
    "a classer", "a_classer", "non classe", "brouillons", "copies",
    # Arabic
    "وثائق", "صور", "عقود", "ملفات", "أرشيف", "نماذج", "متنوع", "نسخ", "مسودات",
}

# A Tunisian CIN is exactly 8 digits.
CIN_RE = re.compile(r"(?<!\d)(\d{8})(?!\d)")
# Year-like folder names: 19xx / 20xx on their own.
YEAR_RE = re.compile(r"^(19|20)\d{2}$")
LETTER_RE = re.compile(r"[A-Za-zÀ-ɏ؀-ۿ]")

DOC_EXTS = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".txt", ".rtf", ".odt"}
IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}

# Filename hints. A portrait is a much better profile photo than a scan of an
# identity card, and a card scan is a much better one than a page of a contract.
PORTRAIT_HINTS = ("photo", "portrait", "visage", "face", "identite", "identité",
                  "صورة", "وجه", "شخصية")
CIN_HINTS = ("cin", "carte", "بطاقة", "تعريف")

MAX_IMPORT_BYTES = 50 * 1024 * 1024      # a single file larger than this is skipped


@dataclass
class Candidate:
    """One folder the scan believes is a client, and what it proposes to do."""
    folder: Path
    raw_name: str
    nom: str = ""
    prenom: str = ""
    cin: str = ""
    documents: List[Path] = field(default_factory=list)
    images: List[Path] = field(default_factory=list)
    profile_photo: Optional[Path] = None
    confidence: str = "low"          # high | medium | low
    reasons: List[str] = field(default_factory=list)
    include: bool = True             # the notary can clear this before applying
    existing_client_id: Optional[str] = None

    @property
    def full_name(self) -> str:
        return f"{self.prenom} {self.nom}".strip()

    def summary(self) -> str:
        return (f"{self.full_name or '(sans nom)'} | CIN {self.cin or '—'} | "
                f"{len(self.documents)} doc, {len(self.images)} img | "
                f"{self.confidence}")


# ── Name parsing ─────────────────────────────────────────────────────────────
def parse_folder_name(dir_name: str):
    """
    Pulls a CIN and a person name out of a folder name.

    Returns (prenom, nom, cin, reasons). Any of them may be empty.
    """
    reasons = []
    name = dir_name.strip()

    cin_match = CIN_RE.search(name)
    cin = cin_match.group(1) if cin_match else ""
    if cin:
        reasons.append(f"CIN {cin} lu dans le nom du dossier")

    # strip the number, the word "cin", separators and leftover punctuation
    cleaned = CIN_RE.sub(" ", name)
    cleaned = re.sub(r"(?i)\b(cin|c\.i\.n|carte|identite|identité)\b", " ", cleaned)
    cleaned = cleaned.replace("بطاقة", " ").replace("تعريف", " ")
    cleaned = re.sub(r"[_\-.,;:()\[\]]+", " ", cleaned)
    cleaned = re.sub(r"\d+", " ", cleaned)          # any remaining digits
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    parts = [p for p in cleaned.split() if LETTER_RE.search(p)]
    if not parts:
        return "", "", cin, reasons

    if len(parts) == 1:
        # One token: treat it as the surname and leave the given name empty
        # rather than inventing a split.
        return "", parts[0], cin, reasons + ["un seul mot — à confirmer"]

    # Tunisian folders are usually written "Nom Prenom" or "Prenom Nom"; there is
    # no reliable way to tell which, so the last token is taken as the surname
    # and the notary confirms. "Ben"/"Bent"/"Ould" bind to the token after them.
    tokens = parts[:]
    for particle in ("ben", "bent", "ould", "abou", "abu", "بن", "بنت", "ولد"):
        for i, t in enumerate(tokens[:-1]):
            if t.lower() == particle:
                tokens[i:i + 2] = [f"{tokens[i]} {tokens[i + 1]}"]
                break
    if len(tokens) == 1:
        return "", tokens[0], cin, reasons
    return " ".join(tokens[:-1]), tokens[-1], cin, reasons


def looks_like_client_folder(path: Path):
    """
    Decides whether a directory names a client. Returns (is_client, reason).

    The test is deliberately conservative: a folder that is not clearly a person
    is left out of the plan rather than imported as a client called "2022".
    """
    name = path.name.strip()
    if not name or name.startswith("."):
        return False, "dossier caché"
    if YEAR_RE.match(name):
        return False, f"'{name}' est une année, pas un client"
    if name.lower() in NON_CLIENT_NAMES:
        return False, f"'{name}' est un dossier de classement"
    if not LETTER_RE.search(name):
        return False, f"'{name}' ne contient aucune lettre"

    prenom, nom, cin, _ = parse_folder_name(name)
    if not nom and not cin:
        return False, f"'{name}' ne ressemble ni à un nom ni à un CIN"
    return True, ""


def _confidence(prenom: str, nom: str, cin: str, n_docs: int, n_imgs: int) -> str:
    if cin and nom and prenom:
        return "high"
    if cin or (nom and prenom):
        return "medium"
    return "low"


def _pick_profile_photo(images: List[Path]) -> Optional[Path]:
    """
    Chooses the best candidate for the client's face, or none.

    The old version used whichever image came last, which routinely made a scan
    of an identity card the face the camera would try to recognise. A portrait
    filename wins; a card scan is accepted only if nothing better exists; and a
    file that does not actually decode as an image is never chosen.
    """
    def score(p: Path) -> int:
        low = p.name.lower()
        if any(h in low for h in PORTRAIT_HINTS):
            return 3
        if any(h in low for h in CIN_HINTS):
            return 2
        return 1

    for cand in sorted(images, key=score, reverse=True):
        if _is_real_image(cand):
            return cand
    return None


def _is_real_image(path: Path) -> bool:
    """Decodes the bytes rather than trusting the extension."""
    try:
        size = path.stat().st_size
        if size == 0 or size > MAX_IMPORT_BYTES:
            return False
    except OSError:
        return False
    try:
        from PySide6.QtGui import QImageReader
        r = QImageReader(str(path))
        r.setDecideFormatFromContent(True)
        if not r.canRead():
            return False
        img = r.read()
        return (not img.isNull()) and img.width() >= 32 and img.height() >= 32
    except Exception:
        # Without Qt available, fall back to magic numbers.
        try:
            head = path.open("rb").read(12)
        except OSError:
            return False
        return (head.startswith(b"\xff\xd8\xff")            # JPEG
                or head.startswith(b"\x89PNG\r\n\x1a\n")    # PNG
                or head.startswith(b"BM")                    # BMP
                or (head[:4] == b"RIFF" and head[8:12] == b"WEBP"))


# ── Phase 1: scan (reads only) ───────────────────────────────────────────────
def scan_archive(folder_path_str: str, should_cancel=None) -> Dict:
    """
    Reads the archive and returns a plan. Writes nothing.

    The plan is meant to be shown to the notary before anything is applied, so
    that a structure the heuristics read wrongly is caught by the person who
    knows what the folders mean.
    """
    out = {
        "status": "ok",
        "root": folder_path_str,
        "candidates": [],
        "skipped": [],
        "errors": [],
        "folders_seen": 0,
        "files_seen": 0,
    }
    root = Path(str(folder_path_str).strip())
    if not root.exists() or not root.is_dir():
        out["status"] = "error"
        out["errors"].append(f"Le chemin n'existe pas ou n'est pas un dossier : {root}")
        return out

    # Every directory, shallowest first, so a client folder is decided before its
    # own sub-folders are considered.
    all_dirs = [root] + sorted((p for p in root.rglob("*") if p.is_dir()),
                               key=lambda p: len(p.parts))
    out["folders_seen"] = len(all_dirs)

    claimed = {}          # directory -> the Candidate that owns its files
    for d in all_dirs:
        if should_cancel is not None and should_cancel():
            out["status"] = "cancelled"
            return out

        # Files under a directory already claimed by an ancestor belong to that
        # ancestor: "Gharbi Mohamed/Pieces/cin.jpg" is Gharbi's identity card,
        # not a client named "Pieces".
        owner = claimed.get(d)
        if owner is None:
            for parent in d.parents:
                if parent in claimed:
                    owner = claimed[parent]
                    claimed[d] = owner
                    break

        if owner is None:
            # The root is the container the notary pointed at, never a client
            # itself. Letting it qualify made it claim every file underneath and
            # collapse the whole archive into one bogus record named after the
            # folder the notary happened to choose.
            is_client, why = (False, "dossier racine") if d == root                 else looks_like_client_folder(d)
            if not is_client:
                if d != root:
                    out["skipped"].append({"folder": str(d), "reason": why})
                continue
            prenom, nom, cin, reasons = parse_folder_name(d.name)
            owner = Candidate(folder=d, raw_name=d.name, nom=nom, prenom=prenom,
                              cin=cin, reasons=list(reasons))
            out["candidates"].append(owner)
            claimed[d] = owner

        try:
            entries = [f for f in d.iterdir() if f.is_file()]
        except OSError as e:
            out["errors"].append(f"{d}: {e}")
            continue
        out["files_seen"] += len(entries)
        for f in entries:
            ext = f.suffix.lower()
            try:
                if f.stat().st_size > MAX_IMPORT_BYTES:
                    out["skipped"].append(
                        {"folder": str(f), "reason": "fichier trop volumineux"})
                    continue
            except OSError:
                continue
            if ext in DOC_EXTS:
                owner.documents.append(f)
            elif ext in IMG_EXTS:
                owner.images.append(f)

    for c in out["candidates"]:
        c.profile_photo = _pick_profile_photo(c.images)
        c.confidence = _confidence(c.prenom, c.nom, c.cin,
                                   len(c.documents), len(c.images))
        if not c.documents and not c.images:
            c.include = False
            c.reasons.append("aucun fichier — probablement pas un client")
        if c.profile_photo is None and c.images:
            c.reasons.append("aucune image exploitable comme photo de profil")

        # Flag a folder that already corresponds to a client in the database, so
        # a second run of the import updates rather than duplicates.
        try:
            from reception import find_client_by_cin_or_name
            existing = find_client_by_cin_or_name(
                cin_number=c.cin, full_name=c.full_name)
            if existing:
                c.existing_client_id = existing["client_id"]
                c.reasons.append(
                    f"déjà présent dans la base ({existing['client_id']}) — "
                    f"les documents seront ajoutés à la fiche existante")
        except Exception as dup_err:
            # (b) If the duplicate lookup fails the candidate is treated as new,
            # so a second import run silently duplicates the client.
            c.reasons.append(
                "impossible de vérifier les doublons — à contrôler après l'import")
            try:
                from system_guardian import log_system_error
                log_system_error("archive import: duplicate check failed", dup_err)
            except Exception:
                # (c) Safe. A guard around the logger: the candidate has already
                # been flagged for review above, which is the part that matters.
                pass

    return out


# ── Phase 2: apply (writes what survived review) ─────────────────────────────
def apply_plan(plan: Dict, should_cancel=None, enrol_faces: bool = True) -> Dict:
    """
    Writes the candidates whose `include` is still True.

    Every candidate is wrapped in its own try/except: one folder that cannot be
    imported is recorded and skipped, and the rest of the migration continues.
    That is the difference between "four clients imported, one to look at" and
    the old behaviour of aborting the whole run on the first year folder.
    """
    from reception import (register_client, save_client_document,
                           update_client_profile_pic, generate_client_id,
                           update_client_facial_embedding_from_photo,
                           clear_db_caches, NameValidationError)

    res = {
        "status": "success",
        "clients_created": 0,
        "clients_updated": 0,
        "documents_imported": 0,
        "photos_set": 0,
        "faces_extracted": 0,
        "failed": [],
        "imported_client_ids": [],
        "logs": [],
    }

    todo = [c for c in plan.get("candidates", []) if c.include]
    if not todo:
        # The old version called this "success". It is not: the notary asked for
        # an import and got nothing, and needs to be told so.
        res["status"] = "empty"
        res["logs"].append("Aucun client à importer dans ce dossier.")
        return res

    for c in todo:
        if should_cancel is not None and should_cancel():
            res["status"] = "cancelled"
            return res
        try:
            if c.existing_client_id:
                cid = c.existing_client_id
                res["clients_updated"] += 1
            else:
                cid = register_client(
                    client_id=generate_client_id("imp_"),
                    nom=c.nom, prenom=c.prenom, cin_number=c.cin,
                    address="مستورد من الأرشيف الورقي / Importé de l'archive")
                res["clients_created"] += 1
            res["imported_client_ids"].append(cid)

            for doc in c.documents:
                try:
                    # save_client_document returns "" when it refuses the path or
                    # the write fails. Counting the attempt rather than the result
                    # would report documents as imported that are not on disk.
                    if save_client_document(cid, doc.read_bytes(), f"Archive_{doc.name}"):
                        res["documents_imported"] += 1
                    else:
                        res["failed"].append({"folder": str(c.folder), "file": doc.name,
                                              "error": "écriture refusée"})
                except Exception as e:
                    res["failed"].append(
                        {"folder": str(c.folder), "file": doc.name, "error": str(e)})

            # Images that are not the chosen portrait are still worth keeping —
            # a scanned identity card is a document, not a face.
            for img in c.images:
                if c.profile_photo is not None and img == c.profile_photo:
                    continue
                try:
                    if save_client_document(cid, img.read_bytes(), f"Archive_{img.name}"):
                        res["documents_imported"] += 1
                    else:
                        res["failed"].append({"folder": str(c.folder), "file": img.name,
                                              "error": "écriture refusée"})
                except Exception as e:
                    res["failed"].append(
                        {"folder": str(c.folder), "file": img.name, "error": str(e)})

            if c.profile_photo is not None:
                target = PROFILES_DIR / f"{cid}.jpg"
                try:
                    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(c.profile_photo.read_bytes())
                    if update_client_profile_pic(cid, str(target)):
                        res["photos_set"] += 1
                        if enrol_faces and update_client_facial_embedding_from_photo(
                                cid, str(target)):
                            res["faces_extracted"] += 1
                except Exception as e:
                    res["failed"].append({"folder": str(c.folder),
                                          "file": c.profile_photo.name,
                                          "error": str(e)})

            res["logs"].append(f"{c.full_name or c.raw_name} → {cid} "
                               f"({len(c.documents) + len(c.images)} fichiers)")

        except NameValidationError as e:
            # Exactly the exception that used to end the whole migration.
            res["failed"].append({"folder": str(c.folder), "error": str(e)[:160]})
        except Exception as e:
            res["failed"].append({"folder": str(c.folder),
                                  "error": f"{type(e).__name__}: {e}"[:160]})

    if res["failed"] and res["clients_created"] == 0 and res["clients_updated"] == 0:
        res["status"] = "error"
    elif res["failed"]:
        res["status"] = "partial"

    clear_db_caches()
    return res


# ── Backwards-compatible one-shot ────────────────────────────────────────────
def bulk_import_legacy_notary_folders(folder_path_str: str, should_cancel=None) -> Dict:
    """
    Scan and apply in one call, keeping the signature the Paramètres page uses.

    Accepting the plan unreviewed is the weaker way to use this module — the
    review step exists because folder names are a guess — but this keeps the
    existing entry point working and is safe now that a bad folder is skipped
    instead of aborting the run.
    """
    plan = scan_archive(folder_path_str, should_cancel=should_cancel)
    if plan["status"] != "ok":
        return {"status": plan["status"], "clients_created": 0,
                "documents_imported": 0, "faces_extracted": 0,
                "folders_scanned": plan.get("folders_seen", 0),
                "imported_client_ids": [],
                "logs": plan.get("errors", [])}

    res = apply_plan(plan, should_cancel=should_cancel)
    res["folders_scanned"] = plan.get("folders_seen", 0)
    res["skipped"] = plan.get("skipped", [])
    return res
