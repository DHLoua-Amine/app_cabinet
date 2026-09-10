"""
system_guardian.py — 30-Year Stability, Auto-Backup, Recovery & Crash Prevention Engine
Built for a Tunisian notarial office; the office's own identity lives in
core/office_profile.py rather than in the code.
"""

import os
import re
import sys
import shutil
import sqlite3
import datetime
import zipfile
import traceback
from pathlib import Path
import threading
import time
from functools import wraps

class _SortieAvalee:
    encoding = "utf-8"
    errors = "replace"
    def write(self, _t=""): return len(_t) if _t else 0
    def flush(self): return None
    def writelines(self, l): pass
    def isatty(self): return False
    def fileno(self):
        import io as _io
        raise _io.UnsupportedOperation("fileno")
    def close(self): return None
    @property
    def closed(self): return False

def _assainir_sorties():
    for nom in ("stdout", "stderr"):
        flux = getattr(sys, nom, None)
        if flux is None or not hasattr(flux, "write"):
            setattr(sys, nom, _SortieAvalee())

_assainir_sorties()

_guardian_cache = {}
_guardian_cache_lock = threading.Lock()

def local_cache(ttl=60):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = (args, tuple(sorted(kwargs.items())))
            now = time.time()
            func_name = func.__name__
            with _guardian_cache_lock:
                if func_name in _guardian_cache:
                    if cache_key in _guardian_cache[func_name]:
                        val, expires = _guardian_cache[func_name][cache_key]
                        if now < expires:
                            return val
            result = func(*args, **kwargs)
            with _guardian_cache_lock:
                if func_name not in _guardian_cache:
                    _guardian_cache[func_name] = {}
                _guardian_cache[func_name][cache_key] = (result, now + ttl)
            return result
        wrapper.invalidate = lambda: clear_guardian_cache(func.__name__)
        return wrapper
    return decorator


def clear_guardian_cache(func_name: str = None) -> None:
    """
    Drops cached results, for one function or for all of them.

    Nothing invalidated this cache before, so any setter that changed the state a
    cached getter reads stayed invisible for up to its TTL. See
    set_external_backup_dir() for what that cost.
    """
    with _guardian_cache_lock:
        if func_name is None:
            _guardian_cache.clear()
        else:
            _guardian_cache.pop(func_name, None)

# Add root path
root_dir = Path(__file__).resolve().parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from config import DATA_DIR, PROFILES_DIR, DOCUMENTS_DIR, LOGS_DIR

BACKUPS_DIR = DATA_DIR / "backups"
BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)
ERROR_LOG_PATH = LOGS_DIR / "system_errors.log"



_SENTRY_INITIALIZED = False

def init_sentry() -> bool:
    """
    Safely initializes Sentry SDK error tracking if SENTRY_DSN is configured.
    Guarded to never break local offline testing or throw network errors.
    """
    global _SENTRY_INITIALIZED
    if _SENTRY_INITIALIZED:
        return True

    from config import SENTRY_DSN
    if not SENTRY_DSN or not SENTRY_DSN.strip():
        return False

    try:
        import sentry_sdk
        from version import __version__
        sentry_sdk.init(
            dsn=SENTRY_DSN.strip(),
            traces_sample_rate=0.2,
            release=f"cabinet-notarial-zarai@{__version__}",
            environment="production",
            send_default_pii=False,
        )
        _SENTRY_INITIALIZED = True
        return True
    except Exception:
        return False

# ── Redaction ────────────────────────────────────────────────────────────────
# Exception text is written verbatim to system_errors.log, and that log is what
# the diagnostic export sends out of the office. Anything that looks like a
# credential is masked on the way in, so a secret cannot reach the file at all
# rather than being filtered later and hoping every reader remembers to.

_SECRET_PATTERNS = [
    # key=value / key: value, for the field names that carry credentials
    re.compile(r"(?i)(\b(?:password|passwd|pwd|mot\s*de\s*passe|secret|token|"
               r"api[_-]?key|apikey|authorization|auth|bearer|recovery[_-]?code)"
               r"\s*[:=]\s*(?:Bearer\s+|Basic\s+)?)([^\s,;'\"]{3,})"),
    # Google API keys are recognisable on their own
    re.compile(r"\bAIza[0-9A-Za-z_\-]{10,}"),
    # OpenAI style
    re.compile(r"\bsk-[A-Za-z0-9]{16,}"),
    # the app's own sealed-key envelope, and PBKDF2 hashes
    re.compile(r"\bZKEY[01]:[A-Za-z0-9+/=]{8,}"),
    re.compile(r"\bpbkdf2_sha256\$[0-9]+\$[0-9a-f]+\$[0-9a-f]+"),
]


def redact_secrets(text: str) -> str:
    """Masks anything credential-shaped. Never raises; returns text unchanged on error."""
    try:
        out = str(text)
        out = _SECRET_PATTERNS[0].sub(lambda m: m.group(1) + "***REDACTED***", out)
        for pat in _SECRET_PATTERNS[1:]:
            out = pat.sub("***REDACTED***", out)
        return out
    except Exception:
        # (c) Safe: logging must not become the thing that fails. The unredacted
        # text is still better than losing the diagnostic entirely.
        return str(text)

def log_system_error(err_title: str, exception_obj: Exception):
    """Logs system errors into system_errors.log with automatic 5MB log rotation."""
    try:
        # Auto-rotate log file if larger than 5MB to keep disk usage lightweight for 30+ years
        if ERROR_LOG_PATH.exists() and ERROR_LOG_PATH.stat().st_size > 5 * 1024 * 1024:
            try:
                old_log = LOGS_DIR / f"system_errors_old_{datetime.date.today()}.log"
                ERROR_LOG_PATH.rename(old_log)
            except Exception as rot_err:
                # Deliberately not routed through log_system_error: we are inside
                # it. The log simply keeps growing; stderr makes that visible.
                print(f"[GUARDIAN] could not rotate the error log: {rot_err}",
                      file=sys.stderr)

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Redacted BEFORE it reaches the file, so a credential that happened to
        # appear in an exception message never lands in the log that the
        # diagnostic export sends out of the office.
        err_msg = redact_secrets(
            f"\n[{timestamp}] ERROR: {err_title}\n{str(exception_obj)}\n"
            f"{traceback.format_exc()}\n{'-'*60}")
        with open(ERROR_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(err_msg)
    except Exception as write_err:
        # The logger cannot log its own failure. Without this the office could run
        # for months with an unwritable log directory and never know.
        print(f"[GUARDIAN] could not write to the error log "
              f"({ERROR_LOG_PATH}): {write_err}", file=sys.stderr)
        print(f"[GUARDIAN] the error it was trying to record: "
              f"{err_title}: {exception_obj}", file=sys.stderr)

    # Report exception asynchronously to Sentry if DSN is configured
    try:
        if _SENTRY_INITIALIZED:
            import sentry_sdk
            sentry_sdk.capture_exception(exception_obj)
    except Exception:
        # Genuinely safe to ignore. Telemetry is optional, entirely best-effort,
        # and an office with no internet must not be slowed down or bothered by
        # a reporting endpoint it cannot reach.
        pass


class BackupCancelled(Exception):
    """Raised when a backup is abandoned because the application is closing."""
    pass


def create_full_system_backup(backup_name_prefix: str = "auto_backup", should_cancel=None) -> Path:
    """
    Creates a compressed ZIP backup of the SQLite database, client profiles, and documents.
    """
    zip_filename = None
    try:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = BACKUPS_DIR / f"{backup_name_prefix}_{timestamp}.zip"
        
        db_path = DATA_DIR / "reception.db"
        
        temp_db_snapshot = BACKUPS_DIR / f"temp_snap_{timestamp}.db"
        try:
            # 1. Atomic SQLite Online Backup (Thread-safe & WAL compliant)
            if db_path.exists():
                import sqlite3
                src_conn = sqlite3.connect(str(db_path), timeout=20)
                try:
                    src_conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
                except Exception as ckpt_err:
                    # Not fatal - the online backup below copies WAL content too -
                    # but a checkpoint that keeps failing means something is
                    # holding the database, and that is worth knowing about before
                    # it turns into a failed backup.
                    log_system_error("backup: WAL checkpoint failed", ckpt_err)
                dst_conn = sqlite3.connect(str(temp_db_snapshot))

                # Copy in page batches so a shutdown can interrupt the snapshot itself,
                # not only the file walks below. On a 25 MB database this is the single
                # longest step, so without this the app still waits it out.
                def _snapshot_progress(status, remaining, total):
                    if should_cancel is not None and should_cancel():
                        raise BackupCancelled()

                src_conn.backup(dst_conn, pages=256, progress=_snapshot_progress)
                dst_conn.close()
                src_conn.close()

                if should_cancel is not None and should_cancel():
                    raise BackupCancelled()

                if temp_db_snapshot.exists():
                    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        zipf.write(temp_db_snapshot, arcname="reception.db")
                        if should_cancel is not None and should_cancel():
                            raise BackupCancelled()
                        
                        # 2. Backup Client Profiles
                        if PROFILES_DIR.exists():
                            for root, _, files in os.walk(PROFILES_DIR):
                                if should_cancel is not None and should_cancel():
                                    raise BackupCancelled()
                                for file in files:
                                    fp = Path(root) / file
                                    arc = fp.relative_to(DATA_DIR)
                                    zipf.write(fp, arcname=str(arc))
                                    
                        # 3. Backup Documents (up to 50MB per file)
                        if DOCUMENTS_DIR.exists():
                            for root, _, files in os.walk(DOCUMENTS_DIR):
                                if should_cancel is not None and should_cancel():
                                    raise BackupCancelled()
                                for file in files:
                                    fp = Path(root) / file
                                    if fp.stat().st_size < 50 * 1024 * 1024:
                                        arc = fp.relative_to(DATA_DIR)
                                        zipf.write(fp, arcname=str(arc))
        except BackupCancelled:
            # Shutting down: drop the partial archive rather than leaving a
            # truncated zip that looks like a real backup.
            try:
                if zip_filename.exists():
                    zip_filename.unlink(missing_ok=True)
            except Exception as rm_err:
                log_system_error("backup: could not remove the cancelled archive",
                                 rm_err)
            raise
        finally:
            if temp_db_snapshot.exists():
                try:
                    temp_db_snapshot.unlink(missing_ok=True)
                except Exception as rm_err:
                    # This file is the size of the whole database. One left behind
                    # per run fills the disk quickly and quietly.
                    log_system_error("backup: could not remove the temporary "
                                     "database snapshot", rm_err)

        # Never let an unusable archive survive to become "the newest backup".
        # Any exception raised inside the `with zipfile.ZipFile(...)` block above still
        # closes the archive on the way out, which writes a valid but EMPTY 22-byte zip.
        # That file then sorted first by mtime and silently became the restore source.
        ok, reason = validate_backup_archive(zip_filename)
        if not ok:
            try:
                if zip_filename.exists():
                    zip_filename.unlink(missing_ok=True)
            except Exception as rm_err:
                # The archive failed validation AND could not be deleted, so an
                # unusable backup is now sitting in the backups folder. Restore
                # validates before using anything, but this must not be silent.
                log_system_error("backup: an INVALID archive could not be removed "
                                 f"({zip_filename})", rm_err)
            log_system_error("Backup produced an unusable archive",
                             Exception(f"{zip_filename.name}: {reason} (deleted)"))
            print(f"[SYSTEM GUARDIAN] BACKUP FAILED: {reason} — archive deleted, not kept.")
            return None

        # Prune old backups if count > 30
        prune_old_backups(max_keep=30)

        # Mirror backup to external hard drive / USB drive if available
        # Only a configured-but-failing external drive is worth reporting; "no USB set up"
        # is the normal case and also returns False.
        if get_external_backup_dir() and not mirror_backup_to_external_drive(zip_filename):
            print("[SYSTEM GUARDIAN] backup created, but the external-drive copy FAILED — "
                  "the off-site copy is missing.")

        return zip_filename
    except Exception as e:
        # Same reasoning as above: a failed run must not leave a partial/empty zip behind.
        try:
            if zip_filename is not None and zip_filename.exists():
                zip_filename.unlink(missing_ok=True)
        except Exception as rm_err:
            log_system_error("backup: could not remove the partial archive after "
                             "a failed run", rm_err)
        log_system_error("Failed to create system backup", e)
        return None


EXTERNAL_CFG_PATH = DATA_DIR / "external_backup_path.txt"

@local_cache(ttl=60)
def get_external_backup_dir() -> Path:
    """Gets the configured external hard drive / USB backup path."""
    if EXTERNAL_CFG_PATH.exists():
        try:
            p = EXTERNAL_CFG_PATH.read_text(encoding="utf-8").strip()
            if p:
                return Path(p)
        except Exception as read_err:
            # Falling through to drive auto-detection below would mirror the
            # office's backups to whatever removable drive happens to be plugged
            # in - not necessarily the one the notary configured.
            log_system_error("could not read the configured external backup path; "
                             "falling back to auto-detection", read_err)
            
    # Auto-detect plugged USB / External drives (E:\, F:\, D:\)
    for drive in ["E:\\", "F:\\", "D:\\", "G:\\"]:
        if os.path.exists(drive):
            ext_dir = Path(drive) / "Sauvegardes_Notaire_Zarai"
            return ext_dir
            
    return None


def set_external_backup_dir(path_str: str) -> bool:
    """
    Saves the external drive path, and makes the new value take effect at once.

    Two things used to go wrong here. The path was written to disk but
    get_external_backup_dir() is cached for 60 seconds and nothing cleared that
    cache, so a backup made in the minute after configuring the drive read the
    OLD value - usually None - and quietly skipped the off-site copy while the
    screen said the path had been saved. And any existing path was accepted,
    including a path to a FILE, because the caller only checked .exists();
    mirroring into a file then fails on every backup thereafter.
    """
    cleaned = (path_str or "").strip()
    if not cleaned:
        log_system_error("set_external_backup_dir refused an empty path",
                         ValueError("empty path"))
        return False

    target = Path(cleaned)
    if target.exists() and not target.is_dir():
        log_system_error("set_external_backup_dir refused a non-directory",
                         NotADirectoryError(cleaned))
        return False

    try:
        EXTERNAL_CFG_PATH.write_text(cleaned, encoding="utf-8")
    except Exception as e:
        log_system_error("Failed to set external backup path", e)
        return False

    # The write is only half the job: the cached reader has to be told, or the
    # next backup mirrors to wherever the drive used to be.
    clear_guardian_cache("get_external_backup_dir")
    return True


def mirror_backup_to_external_drive(zip_path: Path):
    """Automatically copies a generated backup ZIP to the external hard drive if attached."""
    ext_dir = get_external_backup_dir()
    if not ext_dir:
        return False
        
    try:
        ext_dir.mkdir(parents=True, exist_ok=True)
        target_file = ext_dir / zip_path.name
        shutil.copy2(zip_path, target_file)
        print(f"[SYSTEM GUARDIAN] Mirrored backup to External Hard Drive: {target_file}")
        return True
    except Exception as e:
        log_system_error("Failed to mirror backup to external drive", e)
        return False


def prune_old_backups(max_keep: int = 30):
    """Keeps the most recent `max_keep` backups and removes older ones to save disk space."""
    try:
        backups = sorted(list(BACKUPS_DIR.glob("*.zip")), key=os.path.getmtime)
        if len(backups) > max_keep:
            to_remove = backups[:-max_keep]
            for b in to_remove:
                try:
                    b.unlink()
                except Exception as rm_err:
                    # Silently failing here means the retention policy is not
                    # running at all and the backups folder grows without bound.
                    log_system_error(f"could not prune old backup {b.name}", rm_err)
    except Exception as e:
        log_system_error("Failed to prune old backups", e)


@local_cache(ttl=60)
def verify_database_integrity() -> bool:
    """
    Verifies SQLite database integrity using PRAGMA quick_check.
    Auto-restores from latest valid ZIP backup if database is corrupted.
    """
    db_path = DATA_DIR / "reception.db"
    if not db_path.exists():
        return restore_from_latest_backup()
        
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA quick_check;")
        res = cursor.fetchone()
        conn.close()
        
        if res and res[0] == "ok":
            return True
        else:
            log_system_error("Database Integrity Check Failed", Exception(f"PRAGMA result: {res}"))
            return restore_from_latest_backup()
    except Exception as e:
        log_system_error("Database Corrupted Exception", e)
        return restore_from_latest_backup()


# A real backup carries at least an SQLite database. An empty zip is 22 bytes (just the
# end-of-central-directory record), and a database with only the schema is a few KB, so
# anything under this is certainly not a usable backup.
MIN_BACKUP_BYTES = 1024
MIN_DB_ENTRY_BYTES = 4096


def validate_backup_archive(zip_path) -> tuple:
    """
    Answers "could this archive actually restore the office's data?".

    Returns (ok, reason). A backup only counts as usable when it opens as a zip, passes
    testzip(), and genuinely contains a reception.db of plausible size. The 22-byte empty
    archive that prompted this check passes zipfile.is_zipfile() and extracts without
    error, so file-level checks alone are not enough — the database entry must be there.
    """
    zip_path = Path(zip_path)
    try:
        if not zip_path.exists():
            return False, "file does not exist"

        size = zip_path.stat().st_size
        if size < MIN_BACKUP_BYTES:
            return False, f"only {size} bytes (minimum {MIN_BACKUP_BYTES})"

        if not zipfile.is_zipfile(zip_path):
            return False, "not a valid zip archive"

        with zipfile.ZipFile(zip_path, "r") as zipf:
            corrupt = zipf.testzip()
            if corrupt is not None:
                return False, f"corrupt entry: {corrupt}"

            names = zipf.namelist()
            if not names:
                return False, "archive is empty (0 entries)"

            db_entry = next((n for n in names if Path(n).name == "reception.db"), None)
            if db_entry is None:
                return False, f"no reception.db inside ({len(names)} other entries)"

            db_size = zipf.getinfo(db_entry).file_size
            if db_size < MIN_DB_ENTRY_BYTES:
                return False, f"reception.db is only {db_size} bytes"

        return True, f"ok ({size} bytes, database {db_size} bytes)"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def restore_from_latest_backup() -> bool:
    """
    Restores from the newest backup that actually passes validation.

    The previous version took backups[0] — newest by mtime — and extracted it with no
    checks, though its docstring promised a "valid" archive. A 22-byte empty zip (what a
    failed backup used to leave behind) opens cleanly and extracts zero files, so this
    printed "Successfully restored" and returned True having restored nothing. That is
    the disaster-recovery path, so it failed on the one day it mattered. Every candidate
    is now validated and unusable ones are skipped rather than trusted.
    """
    try:
        backups = sorted(BACKUPS_DIR.glob("*.zip"), key=os.path.getmtime, reverse=True)
    except Exception as e:
        log_system_error("Failed to list backups", e)
        return False

    if not backups:
        print(f"[SYSTEM GUARDIAN] RESTORE FAILED: no backup archives in {BACKUPS_DIR}. "
              f"The database could not be recovered automatically.")
        return False

    rejected = []
    for candidate in backups:
        ok, reason = validate_backup_archive(candidate)
        if not ok:
            rejected.append(f"{candidate.name}: {reason}")
            continue
        try:
            with zipfile.ZipFile(candidate, "r") as zipf:
                zipf.extractall(DATA_DIR)
        except Exception as e:
            log_system_error(f"Failed to extract backup {candidate.name}", e)
            rejected.append(f"{candidate.name}: extraction failed ({e})")
            continue

        for r in rejected:
            print(f"[SYSTEM GUARDIAN] skipped unusable backup - {r}")
        print(f"[SYSTEM GUARDIAN] Successfully restored system from {candidate.name}")
        return True

    log_system_error(
        "RESTORE FAILED: no valid backup",
        Exception(f"{len(backups)} archive(s) checked, none usable: " + "; ".join(rejected)),
    )
    print(f"[SYSTEM GUARDIAN] RESTORE FAILED: checked {len(backups)} archive(s), "
          f"none contained a usable database:")
    for r in rejected:
        print(f"[SYSTEM GUARDIAN]   - {r}")
    return False


def cleanup_temporary_files():
    """Cleans up temporary cache files, Playwright test screenshots, and orphaned temp images."""
    _cleanup_failures = []
    try:
        # Clean temp directory in DATA_DIR
        temp_dir = DATA_DIR / "temp"
        if temp_dir.exists():
            for item in temp_dir.glob("*"):
                try:
                    if item.is_file():
                        # Delete if older than 2 hours
                        if (datetime.datetime.now().timestamp() - item.stat().st_mtime) > 7200:
                            item.unlink()
                except Exception as rm_err:
                    # A file held open by another process is ordinary here, so one
                    # log line per file would be noise. Counted and reported once
                    # below instead.
                    _cleanup_failures.append(f"{item.name}: {rm_err}")
        if _cleanup_failures:
            log_system_error(
                f"temp cleanup: {len(_cleanup_failures)} file(s) could not be "
                f"removed",
                OSError("; ".join(_cleanup_failures[:10])))
    except Exception as e:
        log_system_error("Temporary files cleanup error", e)


def run_startup_health_check():
    """
    Main system guardian entry point.
    Runs on application launch to verify DB health, clean temp files, initialize Sentry, and trigger background daily backup.
    """
    if not init_sentry():
        print("[SYSTEM GUARDIAN] crash reporting is NOT active for this session.")
    cleanup_temporary_files()
    db_ok = verify_database_integrity()
    
    # Check if a backup was made today; run in background thread to prevent UI freezing
    today_str = datetime.date.today().strftime("%Y%m%d")
    today_backups = list(BACKUPS_DIR.glob(f"*{today_str}*.zip"))
    
    if not today_backups:
        import threading
        threading.Thread(target=create_full_system_backup, args=("daily_auto_backup",), daemon=True).start()
        
    return db_ok


import atexit

def _on_app_exit():
    """Clean shutdown handler flushing WAL checkpoints on exit."""
    try:
        db_path = DATA_DIR / "reception.db"
        if db_path.exists():
            import sqlite3
            conn = sqlite3.connect(str(db_path), timeout=5)
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            conn.close()
    except Exception as exit_err:
        # The app is closing, so nothing can be shown - but a checkpoint that
        # never succeeds leaves a growing -wal file beside the database.
        log_system_error("shutdown: final WAL checkpoint failed", exit_err)

atexit.register(_on_app_exit)

if __name__ == "__main__":
    print("=== TESTING SYSTEM GUARDIAN ===")
    ok = run_startup_health_check()
    print(f"Database Integrity & Recovery Status: {'OK' if ok else 'RESTORED/INITIALIZED'}")
    b_path = create_full_system_backup("manual_test")
    print(f"Created Backup: {b_path}")
