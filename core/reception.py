# Annotations are not evaluated at import time, so `-> pd.DataFrame` below does not
# force pandas to load just to define the functions.
from __future__ import annotations

import os
import sqlite3
import datetime
import shutil

import permissions
import licensing
from permissions import Cap
import numpy as np
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from contextlib import contextmanager
import threading
import time
from functools import wraps

# Local in-memory thread-safe cache replacing st.cache_data under Qt
_db_cache = {}
_cache_lock = threading.Lock()

def local_cache(ttl=60):
    """Un décorateur de cache simple et thread-safe pour remplacer st.cache_data sous Qt."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            key_args = []
            for arg in args:
                if isinstance(arg, np.ndarray):
                    key_args.append(arg.tobytes())
                else:
                    key_args.append(arg)
            key_kwargs = []
            for k, v in sorted(kwargs.items()):
                if isinstance(v, np.ndarray):
                    key_kwargs.append((k, v.tobytes()))
                else:
                    key_kwargs.append((k, v))
            cache_key = (tuple(key_args), tuple(key_kwargs))
            
            now = time.time()
            func_name = func.__name__
            
            with _cache_lock:
                if func_name in _db_cache:
                    if cache_key in _db_cache[func_name]:
                        val, expires = _db_cache[func_name][cache_key]
                        if now < expires:
                            return val
            
            result = func(*args, **kwargs)
            
            with _cache_lock:
                if func_name not in _db_cache:
                    _db_cache[func_name] = {}
                _db_cache[func_name][cache_key] = (result, now + ttl)
            
            return result
        return wrapper
    return decorator

from config import DATA_DIR, PROFILES_DIR, DOCUMENTS_DIR
from system_guardian import log_system_error

DB_PATH = DATA_DIR / "reception.db"
_thread_local = threading.local()
_init_db_lock = threading.Lock()
# Reentrant: init_db() and run_daily_archiving_if_needed() nest their write blocks,
# which would deadlock on a plain Lock.
_db_write_lock = threading.RLock()

# Global connection registry to track and safely close connections across ALL threads
_active_connections = set()
_conn_registry_lock = threading.Lock()

# The signed-in user, remembered so that every connection this process opens —
# the window's, the camera service's, an export thread's — signs in as the same
# person. Without it only the thread that happened to run the login would be
# allowed near a protected table. The password is held in memory for the life of
# the session only, and travels solely over the sealed channel.
_remote_identity = {"username": "", "password": ""}


def set_remote_identity(username: str, password: str) -> None:
    _remote_identity["username"] = username or ""
    _remote_identity["password"] = password or ""


def clear_remote_identity() -> None:
    _remote_identity["username"] = ""
    _remote_identity["password"] = ""


def _remote_connection():
    """
    The office server, for a machine running as a workstation.

    Returned in place of a local SQLite connection, and deliberately so: every
    function in this module goes through get_connection() or get_db_cursor(),
    so swapping what those return is what makes the secretary's laptop and the
    notary's laptop share one database instead of quietly keeping two.
    """
    import config
    cfg = config.load_network_config()
    from db_client import RemoteConnection
    conn = RemoteConnection(cfg.get("host") or "127.0.0.1",
                            cfg.get("port") or config.DEFAULT_DB_PORT,
                            cfg.get("token") or "")
    u, pw = _remote_identity["username"], _remote_identity["password"]
    if u and pw:
        try:
            conn.login(u, pw)
        except Exception as e:
            # Not fatal: the connection still works for everything that is not
            # role-restricted, and the refusal will be explicit and specific
            # when a protected table is actually reached.
            log_system_error("could not sign in to the office server", e)
    return conn


def is_remote() -> bool:
    """True when this machine reads and writes over the network, not on disk."""
    try:
        import config
        return config.is_workstation()
    except Exception:
        return False


def get_connection():
    """Returns a thread-safe active SQLite connection configured with WAL mode and 64MB RAM cache."""
    conn = getattr(_thread_local, "conn", None)
    if conn is not None:
        try:
            conn.execute("SELECT 1;")
            return conn
        except Exception:
            try:
                conn.close()
            except Exception:
                # (c) Safe. The connection failed to configure; closing it is a
                # courtesy and there is nothing useful to do if that also fails.
                pass
            _thread_local.conn = None

    if is_remote():
        # No local fallback on purpose. Silently opening a local database here
        # is exactly the failure this whole mechanism exists to prevent: the
        # workstation would appear to work while writing to a file nobody else
        # reads. A connection failure must surface as a connection failure.
        conn = _remote_connection()
        _thread_local.conn = conn
        return conn

    try:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA cache_size=-64000;")
        conn.execute("PRAGMA temp_store=MEMORY;")
        # Enforce the FOREIGN KEY constraints the schema already declares. Without
        # this they are decorative and a case can point at a client that never existed.
        conn.execute("PRAGMA foreign_keys=ON;")
        _thread_local.conn = conn
    except Exception:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
        conn.row_factory = sqlite3.Row
        _thread_local.conn = conn

    with _conn_registry_lock:
        _active_connections.add(conn)
    return conn

@contextmanager
def get_db_cursor(commit: bool = False):
    """Context manager for safe, thread-locked, auto-committing, auto-rolling back SQLite cursors."""
    if commit:
        _db_write_lock.acquire()
    conn = get_connection()
    cursor = conn.cursor()
    try:
        yield cursor
        if commit:
            conn.commit()
    except Exception as e:
        try:
            conn.rollback()
        except Exception as rb_err:
            # (b) A rollback that fails leaves the transaction state unknown, which
            # is exactly the situation worth knowing about after a money write.
            log_system_error("transaction rollback failed", rb_err)
        log_system_error("SQLite Transaction Rollback Exception", e)
        raise
    finally:
        # Close only the cursor. The connection is cached per-thread and shared with
        # every other cursor in flight, so closing it here invalidated theirs — which
        # is what stopped init_db() from ever completing.
        try:
            cursor.close()
        except Exception:
            # (c) Safe, and deliberate - see the note above. The cursor may already
            # be invalid because the connection is shared; there is nothing useful
            # to do and nothing is lost.
            pass
        if commit:
            _db_write_lock.release()

def close_all_sqlite_connections():
    """Ferme proprement toutes les connexions SQLite actives sur TOUS les threads et flushe le journal WAL."""
    global _DB_INITIALIZED
    with _conn_registry_lock:
        conns = list(_active_connections)
        _active_connections.clear()

    for conn in conns:
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        except Exception:
            pass
        try:
            conn.close()
        except Exception as close_err:
            log_system_error("could not close sqlite connection", close_err)

    _thread_local.conn = None
    _DB_INITIALIZED = False

def serialize_embedding(embedding: np.ndarray) -> bytes:
    if embedding is None:
        return b""
    try:
        arr = embedding.flatten().astype(np.float32)
        if len(arr) > 128:
            arr = arr[:128]
        arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
        norm = np.linalg.norm(arr)
        if norm > 0:
            arr = arr / norm
        return arr.tobytes()
    except Exception as e:
        log_system_error("Embedding Serialization Error", e)
        return b""

def deserialize_embedding(blob: bytes) -> Optional[np.ndarray]:
    if not blob or len(blob) == 0:
        return None
    try:
        arr = np.frombuffer(blob, dtype=np.float32)
        if len(arr) >= 128:
            arr = arr[:128]
            arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
            norm = np.linalg.norm(arr)
            if norm > 0:
                return arr / norm
        return None
    except Exception as e:
        log_system_error("Embedding Deserialization Error", e)
        return None

class NameValidationError(ValueError):
    """Raised when a name field carries an identity number instead of a name."""
    pass


def check_name_field(value: str, field_label: str = "الاسم") -> str:
    """
    Rejects a CIN-looking string in a name field.

    Bulk imports have written the identity number into `nom`/`full_name` while leaving
    `cin_number` empty, which makes the client unsearchable by either name or CIN.
    Four or more consecutive digits is never part of a Tunisian personal name, so it is
    refused at the write path rather than discovered later in a deed.
    """
    import re
    v = (value or "").strip()
    if not v:
        return v
    if re.search(r"\d{4,}", v):
        raise NameValidationError(
            f"لا يمكن تسجيل رقم بطاقة التعريف داخل خانة {field_label} ('{v[:40]}'). "
            f"يرجى كتابة الاسم في خانة الاسم ورقم البطاقة في خانة رقم بطاقة التعريف."
        )
    return v


_id_lock = threading.Lock()


def unique_file_stamp() -> str:
    """
    A stamp that is unique even for two files saved in the same instant.

    Receipts and generated contracts were named with int(time.time()), which has
    one-SECOND resolution: 50 saves of a file with the same name produced one
    filename and 49 silent overwrites. A notary attaching several proofs to one
    expense, or generating a contract for several clients in a loop, kept only the
    last one and was told each had been saved.

    Readable date and time first so the folder still sorts chronologically, then
    milliseconds, then random hex for the case where even the millisecond ties.
    """
    import secrets
    now = datetime.datetime.now()
    return f"{now.strftime('%Y%m%d_%H%M%S')}_{now.microsecond // 1000:03d}_{secrets.token_hex(3)}"


def generate_client_id(prefix: str = "") -> str:
    """
    Returns a client id that is not already in the clients table.

    Every caller used to build its own id as
    `str(int(time.time() * 1000) % 10000000)`. Two clients created in the same
    millisecond got the same id, and because update_client_civil_status runs an UPDATE
    when the id already exists, the second one silently overwrote the first: name, CIN,
    phone and address replaced, dossiers left attached to the wrong person, success
    message shown. Registering twelve clients back to back produced nine rows.

    The candidate is checked against the database under a lock, and the random suffix
    means two processes racing on the same millisecond do not produce the same value.
    """
    import random
    init_db()
    with _id_lock:
        for attempt in range(200):
            base = int(time.time() * 1000) % 10000000
            # first attempt keeps the familiar short form; later ones add entropy
            candidate = f"{prefix}{base}" if attempt == 0 else f"{prefix}{base}{random.randint(0, 999):03d}"
            try:
                with get_db_cursor() as cursor:
                    cursor.execute("SELECT 1 FROM clients WHERE client_id=?", (candidate,))
                    if cursor.fetchone() is None:
                        return candidate
            except Exception as e:
                log_system_error("generate_client_id lookup failed", e)
                raise
            time.sleep(0.001)
    # 200 collisions in a row means something is badly wrong; refuse rather than overwrite.
    raise RuntimeError("could not allocate a unique client_id after 200 attempts")


_DB_INITIALIZED = False

def init_db():
    global _DB_INITIALIZED
    if _DB_INITIALIZED:
        return
    if is_remote():
        # A workstation does not build a schema. It used to send all 34 CREATE
        # statements to the server on every launch: pointless, slow, and the
        # reason the server had to accept schema changes from the network at all.
        _DB_INITIALIZED = True
        return
    with _init_db_lock:
        if _DB_INITIALIZED:
            return
        try:
            with get_db_cursor(commit=True) as cursor:
                # Clients Table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS clients (
                        client_id TEXT PRIMARY KEY,
                        nom TEXT DEFAULT '',
                        prenom TEXT DEFAULT '',
                        full_name TEXT DEFAULT '',
                        phone TEXT DEFAULT '',
                        face_embedding BLOB,
                    created_at TEXT,
                    profile_pic_path TEXT,
                    documents_dir TEXT,
                    maiden_name TEXT DEFAULT '',
                    birth_date TEXT DEFAULT '',
                    birth_place TEXT DEFAULT '',
                    cin_number TEXT DEFAULT '',
                    cin_date_place TEXT DEFAULT '',
                    marital_status TEXT DEFAULT '',
                    matrimonial_regime TEXT DEFAULT '',
                    profession TEXT DEFAULT '',
                    address TEXT DEFAULT '',
                    legal_role TEXT DEFAULT '',
                    company_name TEXT DEFAULT '',
                    company_rc TEXT DEFAULT ''
                )
            """)

                # Alter table check for civil status fields in clients
                cursor.execute("PRAGMA table_info(clients)")
                existing_cols = [r["name"] for r in cursor.fetchall()]
                new_cols = [
                    ("nom", "TEXT DEFAULT ''"),
                    ("prenom", "TEXT DEFAULT ''"),
                    ("full_name", "TEXT DEFAULT ''"),
                    ("phone", "TEXT DEFAULT ''"),
                    ("face_embedding", "BLOB"),
                    ("profile_pic_path", "TEXT DEFAULT ''"),
                    ("documents_dir", "TEXT DEFAULT ''"),
                    ("maiden_name", "TEXT DEFAULT ''"),
                    ("birth_date", "TEXT DEFAULT ''"),
                    ("birth_place", "TEXT DEFAULT ''"),
                    ("cin_number", "TEXT DEFAULT ''"),
                    ("cin_date_place", "TEXT DEFAULT ''"),
                    ("marital_status", "TEXT DEFAULT ''"),
                    ("matrimonial_regime", "TEXT DEFAULT ''"),
                    ("profession", "TEXT DEFAULT ''"),
                    ("address", "TEXT DEFAULT ''"),
                    ("legal_role", "TEXT DEFAULT ''"),
                    ("company_name", "TEXT DEFAULT ''"),
                    ("company_rc", "TEXT DEFAULT ''"),
                    ("titre_foncier", "TEXT DEFAULT ''"),
                    ("wilaya", "TEXT DEFAULT ''"),
                    ("father_name", "TEXT DEFAULT ''"),
                    ("grandfather_name", "TEXT DEFAULT ''"),
                    ("cin_issue_date", "TEXT DEFAULT ''"),
                    ("cin_issue_place", "TEXT DEFAULT ''"),
                    ("notes", "TEXT DEFAULT ''"),
                ]
                for col_name, col_def in new_cols:
                    if col_name not in existing_cols:
                        cursor.execute(f"ALTER TABLE clients ADD COLUMN {col_name} {col_def}")

                # Check-ins Table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS check_ins (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        client_id TEXT,
                        window_number TEXT DEFAULT 'Guichet 1',
                        timestamp TEXT,
                        confidence_score REAL DEFAULT 1.0,
                        status TEXT DEFAULT 'Passage',
                        payment_status TEXT DEFAULT 'غير خالص / En attente',
                        avance_amount REAL DEFAULT 0.0,
                        total_amount REAL DEFAULT 0.0,
                        payment_notes TEXT DEFAULT '',
                        FOREIGN KEY(client_id) REFERENCES clients(client_id)
                    )
                """)

                cursor.execute("PRAGMA table_info(check_ins)")
                c_cols = [r["name"] for r in cursor.fetchall()]
                if "payment_status" not in c_cols:
                    cursor.execute("ALTER TABLE check_ins ADD COLUMN payment_status TEXT DEFAULT 'غير خالص / En attente'")
                if "avance_amount" not in c_cols:
                    cursor.execute("ALTER TABLE check_ins ADD COLUMN avance_amount REAL DEFAULT 0.0")
                if "total_amount" not in c_cols:
                    cursor.execute("ALTER TABLE check_ins ADD COLUMN total_amount REAL DEFAULT 0.0")
                if "payment_notes" not in c_cols:
                    cursor.execute("ALTER TABLE check_ins ADD COLUMN payment_notes TEXT DEFAULT ''")

                # Monthly Visit Aggregation Table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS monthly_visit_stats (
                        annee_mois TEXT PRIMARY KEY,
                        nombre_visites INTEGER DEFAULT 0,
                        montant_avances REAL DEFAULT 0.0,
                        montant_total REAL DEFAULT 0.0
                    )
                """)

                # System Settings Table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS system_settings (
                        setting_key TEXT PRIMARY KEY,
                        setting_value TEXT
                    )
                """)

                # Cases Table
                for tbl in ["cases"]:
                    cursor.execute(f"""
                        CREATE TABLE IF NOT EXISTS {tbl} (
                            case_id TEXT PRIMARY KEY,
                            client_id TEXT,
                            service_type TEXT,
                            title TEXT,
                            description TEXT,
                            status TEXT DEFAULT 'جديد',
                            created_at TEXT,
                            total_amount REAL DEFAULT 0.0,
                            avance_amount REAL DEFAULT 0.0,
                            payment_status TEXT DEFAULT 'غير خالص',
                            payment_notes TEXT DEFAULT '',
                            FOREIGN KEY(client_id) REFERENCES clients(client_id)
                        )
                    """)

                    cursor.execute(f"PRAGMA table_info({tbl})")
                    cols = [r["name"] for r in cursor.fetchall()]
                    for col_name, col_def in [
                        ("total_amount", "REAL DEFAULT 0.0"),
                        ("avance_amount", "REAL DEFAULT 0.0"),
                        ("payment_status", "TEXT DEFAULT 'غير خالص'"),
                        ("payment_notes", "TEXT DEFAULT ''"),
                        ("party1_name", "TEXT DEFAULT ''"),
                        ("party2_name", "TEXT DEFAULT ''"),
                    ]:
                        if col_name not in cols:
                            cursor.execute(f"ALTER TABLE {tbl} ADD COLUMN {col_name} {col_def}")

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS case_clients (
                        case_id TEXT,
                        client_id TEXT,
                        PRIMARY KEY (case_id, client_id),
                        FOREIGN KEY (case_id) REFERENCES cases (case_id),
                        FOREIGN KEY (client_id) REFERENCES clients (client_id)
                    )
                """)

                # case_payments and client_services are both cascaded into by
                # delete_client, but neither was ever created here.  The existing
                # office database has them (an older build made them), so the gap
                # only shows on a CLEAN install — the secretaire's machine — where
                # every cascade DELETE hits "no such table", is swallowed by the
                # inner handler, and the deletion silently leaves money and service
                # rows behind.  Definitions match the ones already in the office
                # database exactly, so the two installations stay compatible.
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS case_payments (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        case_id TEXT NOT NULL,
                        client_id TEXT NOT NULL,
                        total_estimated REAL DEFAULT 0.0,
                        amount_paid REAL DEFAULT 0.0,
                        payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        notes TEXT,
                        FOREIGN KEY (case_id) REFERENCES cases (case_id),
                        FOREIGN KEY (client_id) REFERENCES clients (client_id)
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS client_services (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        client_id TEXT NOT NULL,
                        service_type TEXT NOT NULL,
                        description TEXT,
                        status TEXT DEFAULT 'En cours',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (client_id) REFERENCES clients (client_id)
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS fees (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        case_id TEXT,
                        client_id TEXT,
                        service_name TEXT DEFAULT '',
                        fee_amount REAL DEFAULT 0.0,
                        paid_amount REAL DEFAULT 0.0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        notes TEXT DEFAULT ''
                    )
                """)

                # Expenses Table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS expenses (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        description TEXT DEFAULT '',
                        category TEXT DEFAULT 'Divers / متنوع',
                        amount REAL DEFAULT 0.0,
                        created_at TEXT,
                        photo_path TEXT DEFAULT ''
                    )
                """)

                # Salaries Table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS salaries (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        employee_name TEXT DEFAULT '',
                        role TEXT DEFAULT 'Secrétaire / كاتبة',
                        amount REAL DEFAULT 0.0,
                        payment_date TEXT,
                        notes TEXT DEFAULT '',
                        photo_path TEXT DEFAULT ''
                    )
                """)

                # Indexes
                # Created here rather than lazily, so a workstation — which
                # never issues DDL — can read them from the first launch.
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS record_edits (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        table_name TEXT, row_id TEXT, field TEXT,
                        old_value TEXT, new_value TEXT,
                        edited_by TEXT, edited_at TEXT)
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS system_settings (
                        setting_key TEXT PRIMARY KEY,
                        setting_value TEXT)
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_check_ins_timestamp ON check_ins(timestamp DESC)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_check_ins_client_id ON check_ins(client_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_client_id ON cases(client_id)")

                # 'client_cases' was an exact duplicate of 'cases' with no unique data.
                # Five readers summed the two tables, so any row landing here doubled the
                # case counts and the daily revenue. Nothing writes to it any more, so it
                # is removed on first run.
                cursor.execute("DROP INDEX IF EXISTS idx_client_cases_client_id")
                cursor.execute("DROP TABLE IF EXISTS client_cases")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_created_at ON cases(created_at DESC)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_status ON cases(status)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_clients_created_at ON clients(created_at DESC)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_clients_cin_number ON clients(cin_number)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_clients_nom_prenom ON clients(nom, prenom)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_clients_phone ON clients(phone)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_expenses_created_at ON expenses(created_at DESC)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_salaries_payment_date ON salaries(payment_date DESC)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_check_ins_payment_status ON check_ins(payment_status)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_case_payments_client_id ON case_payments(client_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_client_services_client_id ON client_services(client_id)")
            # ── with block exits here; conn.commit() runs in get_db_cursor.__exit__ ──
            # Only mark the DB as initialized AFTER the commit succeeds.
            # Setting this flag inside the with block meant it could be True
            # before the commit, so other threads skipped init while the tables
            # hadn't been committed yet, and a failed commit left the flag stuck
            # at True with no way to retry.
            _DB_INITIALIZED = True
        except Exception as e:
            _DB_INITIALIZED = False   # allow a clean retry on next call
            log_system_error("Failed to initialize SQLite database", e)
            # Swallowing this left the application running against a database with no
            # tables, so every later query failed with its own unrelated error and the
            # real cause was buried. The caller has to be able to stop cleanly.
            raise

def ensure_indexes():
    """Garantit l'existence de tous les index SQLite au demarrage."""
    try:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_check_ins_timestamp ON check_ins(timestamp DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_check_ins_client_id ON check_ins(client_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_client_id ON cases(client_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_created_at ON cases(created_at DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_status ON cases(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_clients_created_at ON clients(created_at DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_clients_cin_number ON clients(cin_number)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_clients_nom_prenom ON clients(nom, prenom)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_clients_phone ON clients(phone)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_expenses_created_at ON expenses(created_at DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_salaries_payment_date ON salaries(payment_date DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_check_ins_payment_status ON check_ins(payment_status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_case_payments_client_id ON case_payments(client_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_client_services_client_id ON client_services(client_id)")
    except Exception as e:
        log_system_error("ensure_indexes failed", e)

_cache_generation = 0


def clear_db_caches():
    global _cache_generation
    with _cache_lock:
        _db_cache.clear()
        # Bumped on every invalidation so long-running consumers (the camera thread
        # holds the face-embedding matrix for its whole session) can notice that
        # a client was enrolled or deleted without re-querying on every frame.
        _cache_generation += 1


def cache_generation() -> int:
    """Monotonic counter; changes whenever cached data was invalidated."""
    if is_remote():
        try:
            conn = get_connection()
            if hasattr(conn, "cache_generation"):
                return conn.cache_generation()
        except Exception:
            pass
    return _cache_generation

@licensing.require_licence
@permissions.require(Cap.EDIT_CLIENTS)
def register_client(
    client_id: str = "", nom: str = "", prenom: str = "", phone: str = "",
    face_embedding: np.ndarray = None, profile_pic_path: str = "",
    cin_number: str = "", titre_foncier: str = "", profession: str = "", address: str = ""
) -> str:
    init_db()
    # Refuse an identity number in a name field before it reaches the database.
    check_name_field(nom, "اللقب")
    check_name_field(prenom, "الاسم")
    caller_supplied_id = bool(client_id and str(client_id).strip())
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full_name = f"{prenom} {nom}".strip()
    emb_blob = serialize_embedding(face_embedding) if face_embedding is not None else b""

    # Uniqueness is settled by the PRIMARY KEY, not by a prior lookup.
    #
    # This used to be INSERT OR REPLACE with an id built from the millisecond clock, so
    # two clients created in the same millisecond silently replaced one another — twelve
    # registrations produced nine rows. Looking the id up first is not enough either:
    # between the check and the insert another thread can claim the same id. A plain
    # INSERT lets the database reject the duplicate, and a generated id simply retries.
    last_err = None
    for _ in range(50):
        cid = str(client_id) if caller_supplied_id else generate_client_id()
        doc_dir = str(DOCUMENTS_DIR / cid)
        try:
            with get_db_cursor(commit=True) as cursor:
                cursor.execute("""
                    INSERT INTO clients
                    (client_id, nom, prenom, full_name, phone, face_embedding, created_at, profile_pic_path, documents_dir, cin_number, titre_foncier, profession, address)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (cid, nom, prenom, full_name, phone, emb_blob, now_str, profile_pic_path, doc_dir, cin_number, titre_foncier, profession, address))
            clear_db_caches()
            return cid
        except sqlite3.IntegrityError as e:
            last_err = e
            if caller_supplied_id:
                # The caller named this id and it is already taken. Never overwrite.
                log_system_error("register_client: supplied client_id already exists", e)
                raise ClientIdConflict(f"client_id {cid!r} already exists") from e
            continue        # a generated id lost a race; take a fresh one
        except Exception as e:
            log_system_error("register_client failed", e)
            return cid
    log_system_error("register_client: no free client_id", last_err)
    raise ClientIdConflict("could not allocate a free client_id after 50 attempts")

class ClientIdConflict(Exception):
    """Raised when a NEW client would land on an id that already belongs to someone."""
    pass


@permissions.require(Cap.EDIT_CLIENTS)
def update_client_civil_status(
    client_id: str, nom: str, prenom: str, phone: str,
    maiden_name: str, birth_date: str, birth_place: str,
    cin_number: str, cin_date_place: str, marital_status: str,
    matrimonial_regime: str, profession: str, address: str,
    legal_role: str, company_name: str, company_rc: str,
    titre_foncier: str = "", wilaya: str = "", is_new: bool = False,
    father_name: str = "", grandfather_name: str = "",
    cin_issue_date: str = "", cin_issue_place: str = "",
    notes: str = ""
) -> bool:
    init_db()
    check_name_field(nom, "اللقب")
    check_name_field(prenom, "الاسم")
    full_name = f"{prenom} {nom}".strip() or "حريف جديد"
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    doc_dir = str(DOCUMENTS_DIR / client_id)

    try:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute("SELECT client_id, full_name FROM clients WHERE client_id = ?", (client_id,))
            exists = cursor.fetchone()

            # A caller saving a NEW client must never land on an existing row. Silently
            # UPDATEing it replaced a real client's identity with someone else's while
            # their dossiers stayed attached, and reported success.
            if exists and is_new:
                raise ClientIdConflict(
                    f"client_id {client_id!r} already belongs to "
                    f"{exists['full_name']!r}; refusing to overwrite")

            if not exists:
                cursor.execute("""
                    INSERT INTO clients 
                    (client_id, nom, prenom, full_name, phone, maiden_name, birth_date, birth_place,
                     cin_number, cin_date_place, marital_status, matrimonial_regime, profession, address,
                     legal_role, company_name, company_rc, titre_foncier, wilaya, created_at, documents_dir, face_embedding,
                     father_name, grandfather_name, cin_issue_date, cin_issue_place, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    client_id, nom, prenom, full_name, phone, maiden_name, birth_date, birth_place,
                    cin_number, cin_date_place, marital_status, matrimonial_regime, profession, address,
                    legal_role, company_name, company_rc, titre_foncier, wilaya, now_str, doc_dir, b"",
                    father_name, grandfather_name, cin_issue_date, cin_issue_place, notes
                ))
            else:
                cursor.execute("""
                    UPDATE clients
                    SET nom=?, prenom=?, full_name=?, phone=?,
                        maiden_name=?, birth_date=?, birth_place=?,
                        cin_number=?, cin_date_place=?, marital_status=?,
                        matrimonial_regime=?, profession=?, address=?,
                        legal_role=?, company_name=?, company_rc=?,
                        titre_foncier=?, wilaya=?,
                        father_name=?, grandfather_name=?, cin_issue_date=?, cin_issue_place=?, notes=?
                    WHERE client_id=?
                """, (
                    nom, prenom, full_name, phone,
                    maiden_name, birth_date, birth_place,
                    cin_number, cin_date_place, marital_status,
                    matrimonial_regime, profession, address,
                    legal_role, company_name, company_rc,
                    titre_foncier, wilaya,
                    father_name, grandfather_name, cin_issue_date, cin_issue_place, notes,
                    client_id
                ))
        clear_db_caches()
        return True
    except ClientIdConflict:
        # Must reach the caller: this is a refusal to destroy data, not a write failure.
        raise
    except Exception as e:
        log_system_error("update_client_civil_status failed", e)
        return False

def find_client_by_cin_or_name(cin_number: str = "", full_name: str = "") -> Optional[Dict]:
    init_db()
    cin_clean = cin_number.strip() if cin_number else ""
    name_clean = full_name.strip() if full_name else ""
    
    try:
        with get_db_cursor() as cursor:
            if cin_clean:
                cursor.execute("SELECT * FROM clients WHERE cin_number = ? AND cin_number != ''", (cin_clean,))
                r = cursor.fetchone()
                if r:
                    return dict(r)
                    
            if name_clean:
                cursor.execute("SELECT * FROM clients WHERE full_name LIKE ? OR (nom || ' ' || prenom) LIKE ?", (f"%{name_clean}%", f"%{name_clean}%"))
                r = cursor.fetchone()
                if r:
                    return dict(r)
    except Exception as e:
        log_system_error("find_client_by_cin_or_name failed", e)
    return None

def resolve_photo_path(photo_path: str) -> str:
    """Resolves local photo path. If running remotely and photo is missing locally, fetches it from server."""
    if not photo_path:
        return ""
    if os.path.exists(photo_path):
        return photo_path
    if is_remote():
        try:
            conn = get_connection()
            if hasattr(conn, "fetch_photo"):
                local_p = conn.fetch_photo(photo_path)
                if local_p and os.path.exists(local_p):
                    return local_p
        except Exception as e:
            log_system_error("fetch_photo failed in resolve_photo_path", e)
    return photo_path

@permissions.require(Cap.EDIT_CLIENTS)
def update_client_profile_pic(client_id: str, profile_pic_path: str) -> bool:
    init_db()
    try:
        if is_remote() and profile_pic_path and Path(profile_pic_path).exists():
            try:
                conn = get_connection()
                if hasattr(conn, "sync_photo"):
                    conn.sync_photo(profile_pic_path)
            except Exception as sync_err:
                log_system_error("sync_photo failed in update_client_profile_pic", sync_err)

        with get_db_cursor(commit=True) as cursor:
            cursor.execute("UPDATE clients SET profile_pic_path=? WHERE client_id=?", (profile_pic_path, client_id))

        if profile_pic_path and Path(profile_pic_path).exists():
            if not update_client_facial_embedding_from_photo(client_id, profile_pic_path):
                log_system_error(
                    "profile picture saved but face embedding not refreshed",
                    Exception(f"client_id={client_id!r} path={profile_pic_path!r}"))
        return True
    except Exception as e:
        log_system_error("update_client_profile_pic failed", e)
        return False

# Why an enrolment failed, so the screen can say something useful instead of
# "success". The old code collapsed every one of these into a bare False, and the
# async wrapper did not even return that.
ENROL_OK = ""
ENROL_NO_FILE = "no_file"        # the path does not exist
ENROL_UNREADABLE = "unreadable"  # not an image, or corrupted
ENROL_NO_FACE = "no_face"        # a real image, but no face in it
ENROL_NOT_SAVED = "not_saved"    # a face was found, but the row did not update
ENROL_ERROR = "error"            # the engine or the database raised


def enrol_face_from_photo(client_id: str, photo_path: str) -> Tuple[bool, str]:
    """
    Extracts the face vector and stores it. Returns (ok, reason).

    `reason` is one of the ENROL_* codes above and is "" on success, so a caller
    can tell "there is no face in this photo" from "the file is not an image"
    from "the database refused the write" — all three of which used to be a
    single False that nobody looked at.
    """
    if not photo_path or not Path(photo_path).exists():
        return False, ENROL_NO_FILE
    try:
        if is_remote():
            try:
                conn = get_connection()
                if hasattr(conn, "sync_photo"):
                    conn.sync_photo(photo_path)
            except Exception as sync_err:
                log_system_error("sync_photo failed in enrol_face_from_photo", sync_err)

        import cv2
        img_bgr = cv2.imread(str(photo_path))
        if img_bgr is None:
            return False, ENROL_UNREADABLE
        from face_engine import FaceEngine
        fe = FaceEngine()
        dets = fe.detect_and_extract(img_bgr)
        if not dets:
            return False, ENROL_NO_FACE
        emb_blob = serialize_embedding(dets[0]["embedding"])
        with get_db_cursor(commit=True) as cursor:
            cursor.execute("UPDATE clients SET face_embedding=? WHERE client_id=?",
                           (emb_blob, client_id))
            if cursor.rowcount is not None and cursor.rowcount <= 0:
                # A face was extracted but no client row matched, so nothing was
                # enrolled. Reporting success here would be the same class of lie.
                log_system_error("enrol_face_from_photo matched no client",
                                 Exception(f"client_id={client_id!r}"))
                return False, ENROL_NOT_SAVED
        clear_db_caches()
        return True, ENROL_OK
    except Exception as e:
        log_system_error("enrol_face_from_photo failed", e)
        return False, ENROL_ERROR


@permissions.require(Cap.EDIT_CLIENTS)
def update_client_facial_embedding_from_photo(client_id: str, photo_path: str) -> bool:
    """Boolean form, kept for callers that only need to know whether it worked."""
    ok, _reason = enrol_face_from_photo(client_id, photo_path)
    return ok


@permissions.require(Cap.EDIT_CLIENTS)
def update_client_facial_embedding_from_photo_async(client_id: str, photo_path: str,
                                                    on_done=None):
    """
    Runs the enrolment off the calling thread and reports the REAL outcome.

    This used to `return True` unconditionally, before the worker had run a single
    line. Called with a path that does not exist it still returned True, and the
    Fiche Client told the notary "Photo et empreinte faciale mises a jour avec
    succes !" for a client who was never enrolled and would never be recognised.

    There is no meaningful boolean to return at dispatch time, so this returns the
    worker thread and nothing else. `on_done(ok, reason)` is called from that
    worker thread when the work has actually finished — a Qt caller must marshal
    back to the UI thread before touching widgets.
    """
    import threading

    def _run():
        try:
            ok, reason = enrol_face_from_photo(client_id, photo_path)
        except Exception as e:
            log_system_error("async face enrolment crashed", e)
            ok, reason = False, ENROL_ERROR
        if on_done is not None:
            try:
                on_done(ok, reason)
            except Exception as e:
                log_system_error("face enrolment callback failed", e)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t

@local_cache(ttl=60)
def get_all_clients_summary(limit: int = 100) -> List[Dict]:
    clients = []
    try:
        init_db()
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT client_id, nom, prenom, full_name, phone, cin_number, titre_foncier, profession, profile_pic_path, created_at 
                FROM clients 
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            for r in rows:
                clients.append(dict(r))
    except Exception as e:
        log_system_error("get_all_clients_summary failed", e)
        raise DataUnavailable("le répertoire des clients est illisible", "clients") from e
    return clients

def search_cases(search_text: str = "", status: str = "", service_type: str = "",
                 date_from: str = "", date_to: str = "", limit: int = 5000) -> List[Dict]:
    """
    Filters dossiers in SQL instead of scanning every row in Python.

    The Registre page loaded all 20,000 cases and filtered them in a Python loop on the
    UI thread, freezing the window for up to 614 ms on every keystroke or dropdown
    change. SQLite does the same work against its indexes.
    """
    # Opening the database is itself a read that can fail on a corrupt file, and
    # it happens before the query below is even built, so it needs the same
    # reporting as the query itself.
    try:
        init_db()
    except Exception as e:
        log_system_error("search_cases: could not open the database", e)
        raise DataUnavailable("le registre est illisible", "cases_search") from e
    where, params = [], []

    if search_text:
        q = f"%{search_text.strip()}%"
        where.append("(c.case_id LIKE ? OR c.title LIKE ? OR c.service_type LIKE ? "
                     "OR c.status LIKE ? OR c.description LIKE ? OR COALESCE(c.party1_name,'') LIKE ? "
                     "OR COALESCE(c.party2_name,'') LIKE ? OR COALESCE(cl.full_name,'') LIKE ? "
                     "OR COALESCE(cl.cin_number,'') LIKE ? OR COALESCE(cl.phone,'') LIKE ? "
                     "OR COALESCE(cl.nom,'') LIKE ? OR COALESCE(cl.prenom,'') LIKE ? "
                     "OR COALESCE(cl.titre_foncier,'') LIKE ?)")
        params += [q, q, q, q, q, q, q, q, q, q, q, q, q]
    if status:
        where.append("c.status LIKE ?")
        params.append(f"%{status}%")
    if service_type:
        where.append("c.service_type LIKE ?")
        params.append(f"%{service_type}%")
    if date_from:
        # Comparing the column directly instead of date(column): wrapping the column in a
        # function stops SQLite using idx_cases_created_at and forces a full table scan.
        # Applying date() to the parameter is free and keeps the index in play.
        # created_at is stored as 'YYYY-MM-DD HH:MM:SS', which sorts chronologically.
        where.append("c.created_at >= date(?)")
        params.append(date_from)
    if date_to:
        # '< next day' rather than '<= that day' so the whole end day is included even
        # though the stored values carry a time component.
        where.append("c.created_at < date(?, '+1 day')")
        params.append(date_to)

    sql = """
        SELECT c.*, COALESCE(cl.full_name, c.client_id, '') AS client_name
        FROM cases c
        LEFT JOIN clients cl ON c.client_id = cl.client_id
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY c.created_at DESC LIMIT ?"
    params.append(limit)

    out = []
    try:
        with get_db_cursor() as cursor:
            cursor.execute(sql, params)
            out = [dict(r) for r in cursor.fetchall()]
    except Exception as e:
        log_system_error("search_cases failed", e)
        raise DataUnavailable("la recherche de dossiers a échoué", "cases_search") from e
    # Money is stripped here, at the source, rather than by whichever screen
    # happens to render it. Every route to this list - the Registre page, the
    # Excel export, any future caller - gets the same redacted rows.
    return permissions.redact(out, Cap.VIEW_DOSSIER_AMOUNTS_BULK)


@local_cache(ttl=60)
def count_clients() -> int:
    """Total client count, so a truncated list can tell the user what it is hiding."""
    try:
        init_db()
        with get_db_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS n FROM clients")
            return int(cursor.fetchone()["n"])
    except Exception as e:
        log_system_error("count_clients failed", e)
        raise DataUnavailable("le nombre de clients est illisible", "clients_count") from e


@local_cache(ttl=60)
def count_check_ins() -> int:
    """Total presence-log count, for the same reason as count_clients()."""
    try:
        init_db()
        with get_db_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS n FROM check_ins")
            return int(cursor.fetchone()["n"])
    except Exception as e:
        log_system_error("count_check_ins failed", e)
        raise DataUnavailable("presence total unreadable", "total") from e


@local_cache(ttl=60)
def count_check_ins_today() -> int:
    """
    Today's presence count, straight from the database.

    The Journal page used to count today's visits inside the 200 rows it had
    loaded, so on a day busier than the page size it reported the page size
    instead of the day's real traffic.
    """
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    try:
        init_db()
        with get_db_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS n FROM check_ins WHERE timestamp LIKE ?",
                           (today + "%",))
            return int(cursor.fetchone()["n"])
    except Exception as e:
        log_system_error("count_check_ins_today failed", e)
        raise DataUnavailable("today total unreadable", "today") from e


@local_cache(ttl=30)
def search_clients_summary(query_str: str) -> List[Dict]:
    q = f"%{query_str.strip()}%"
    clients = []
    try:
        init_db()
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT client_id, nom, prenom, full_name, phone, cin_number, titre_foncier, profession, profile_pic_path, created_at 
                FROM clients 
                WHERE client_id LIKE ? 
                   OR nom LIKE ? 
                   OR prenom LIKE ? 
                   OR full_name LIKE ? 
                   OR phone LIKE ?
                   OR cin_number LIKE ?
                   OR profession LIKE ?
                   OR titre_foncier LIKE ?
                ORDER BY created_at DESC
            """, (q, q, q, q, q, q, q, q))
            rows = cursor.fetchall()
            for r in rows:
                clients.append(dict(r))
    except Exception as e:
        log_system_error("search_clients_summary failed", e)
        raise DataUnavailable("la recherche de clients a échoué", "clients_search") from e
    return clients

@local_cache(ttl=3600)
def get_client_name_map() -> Dict[str, str]:
    """
    client_id -> display name, and nothing else.

    The camera thread needs names to label recognised faces. It used to call
    get_all_clients(), which returns every column of every client including the
    embedding blobs — 1.3 s at 10,000 clients, on the thread that is supposed to be
    watching the door. This reads three small columns instead.
    """
    out = {}
    try:
        init_db()
        with get_db_cursor() as cursor:
            cursor.execute("SELECT client_id, full_name, nom, prenom FROM clients")
            for r in cursor.fetchall():
                name = (r["full_name"] or "").strip()
                if not name:
                    name = f"{(r['prenom'] or '').strip()} {(r['nom'] or '').strip()}".strip()
                out[r["client_id"]] = name
    except Exception as e:
        log_system_error("get_client_name_map failed", e)
        raise DataUnavailable("les noms des clients sont illisibles", "clients") from e
    return out


@local_cache(ttl=3600)
def get_all_face_embeddings() -> Tuple[List[str], Optional[np.ndarray]]:
    """
    Retourne la liste des client_id et la matrice NumPy 2D normalisee des embeddings faciaux.
    Mise en cache en memoire (TTL 1h), invalidee immediatement lors de l'ajout/modification d'un client.
    """
    init_db()
    ids = []
    embs = []
    try:
        with get_db_cursor() as cursor:
            cursor.execute("SELECT client_id, face_embedding FROM clients WHERE face_embedding IS NOT NULL AND LENGTH(face_embedding) > 0")
            rows = cursor.fetchall()
            for r in rows:
                if r["face_embedding"]:
                    arr = deserialize_embedding(r["face_embedding"])
                    if arr is not None and len(arr) == 128:
                        ids.append(r["client_id"])
                        embs.append(arr)
        if embs:
            matrix = np.vstack(embs).astype(np.float32)
            norms = np.linalg.norm(matrix, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            matrix_norm = matrix / norms
            return ids, matrix_norm
    except Exception as e:
        log_system_error("get_all_face_embeddings failed", e)
    return [], None

@local_cache(ttl=5)
def get_all_clients() -> List[Dict]:
    clients = []
    try:
        init_db()
        with get_db_cursor() as cursor:
            cursor.execute("SELECT * FROM clients ORDER BY created_at DESC")
            rows = cursor.fetchall()

            for r in rows:
                c = dict(r)
                c["embedding"] = deserialize_embedding(r["face_embedding"]) if r["face_embedding"] else None
                clients.append(c)
    except Exception as e:
        log_system_error("get_all_clients failed", e)
        raise DataUnavailable("le répertoire des clients est illisible", "clients") from e
    return clients

def get_client_by_id(client_id: str) -> Optional[Dict]:
    try:
        init_db()
        with get_db_cursor() as cursor:
            cursor.execute("SELECT * FROM clients WHERE client_id=?", (client_id,))
            r = cursor.fetchone()
            if not r:
                return None
            c = dict(r)
            c["embedding"] = deserialize_embedding(r["face_embedding"]) if r["face_embedding"] else None
            return c
    except Exception as e:
        log_system_error("get_client_by_id failed", e)
        raise DataUnavailable("la fiche client est illisible", "client") from e

@permissions.require(Cap.DELETE_CLIENTS)
def delete_client(client_id: str) -> bool:
    init_db()
    try:
        with get_db_cursor(commit=True) as cursor:
            # Children first, parent last — with foreign_keys=ON the parent row cannot
            # be removed while dependants still reference it.
            # case_payments and client_services were previously missed, leaving a
            # deleted client's money rows behind and distorting the accounts.
            ALLOWED_CASCADE_TABLES = {"case_payments", "client_services", "check_ins", "cases"}
            for table in ("case_payments", "client_services", "check_ins", "cases"):
                if table not in ALLOWED_CASCADE_TABLES:
                    continue
                try:
                    cursor.execute(f"DELETE FROM {table} WHERE client_id=?", (client_id,))
                except Exception as e_tbl:
                    log_system_error(f"delete_client: cascade into {table} failed", e_tbl)
            cursor.execute("DELETE FROM clients WHERE client_id=?", (client_id,))
            # Deleting a client_id that is not present is a perfectly successful DELETE of
            # zero rows. Returning True for that made the Fiche say "client deleted" about
            # a client it had not deleted, so the row count decides the answer.
            removed = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0

        if removed == 0:
            log_system_error("delete_client matched no rows",
                             Exception(f"client_id={client_id!r} not found"))
            return False

        _log_record_edit("clients", client_id, "DELETED_CLIENT", f"client_id={client_id}", "REMOVED")

        pic = PROFILES_DIR / f"{client_id}.jpg"
        if pic.exists():
            pic.unlink(missing_ok=True)

        # The client's document folder was left behind on every deletion, so the
        # scanned CIN copies, contracts and attachments of a client the notary
        # believed erased stayed readable on disk indefinitely.  Resolve it and
        # refuse to touch anything that does not sit directly inside
        # DOCUMENTS_DIR, so a malformed client_id can never delete a wider tree.
        try:
            base = DOCUMENTS_DIR.resolve()
            cdir = (DOCUMENTS_DIR / str(client_id)).resolve()
            if cdir.parent == base and cdir != base and cdir.is_dir():
                shutil.rmtree(cdir, ignore_errors=True)
                if cdir.exists():
                    log_system_error("delete_client: document folder not fully removed",
                                     OSError(str(cdir)))
            elif cdir.exists():
                log_system_error("delete_client: refused to remove document folder",
                                 ValueError(f"{client_id!r} -> {cdir}"))
        except Exception as e_dir:
            log_system_error("delete_client: document folder cleanup failed", e_dir)

        # Drop the cached lookups — above all the face-embedding matrix, which has a
        # one-hour TTL. Without this the deleted client stayed in the matrix and the
        # camera kept recognising and greeting someone who no longer exists.
        clear_db_caches()
        return True
    except Exception as e:
        log_system_error("delete_client failed", e)
        return False

class DataUnavailable(RuntimeError):
    """
    A query FAILED. Not the same thing as a query that found nothing.

    The presence functions used to answer a dropped table, a locked file or a
    corrupt row with an empty DataFrame and a zero, which the Journal page then
    rendered as a calm "0 visits" -- identical to a quiet Sunday. The office had
    no way to tell a broken database from an empty one. These functions now
    raise instead, and the page shows an error state.

    `code` is a language-neutral identifier. The screen translates it; the
    message itself is for the log, so no French sentence ends up embedded in an
    Arabic one.
    """

    def __init__(self, message: str = "", code: str = ""):
        super().__init__(message)
        self.code = code

def log_check_in(client_id: str, location: str, confidence: float, status: str) -> bool:
    init_db()
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    annee_mois = now_str[:7]
    try:
        with get_db_cursor(commit=True) as cursor:
            # Check if client_id exists in clients table to satisfy FOREIGN KEY(client_id)
            cursor.execute("SELECT 1 FROM clients WHERE client_id=?", (client_id,))
            if cursor.fetchone() is None:
                # Client does not exist in clients table; return False gracefully rather than triggering Foreign Key IntegrityError
                return False

            # Deduplicate visits within 15 seconds to prevent duplicate logs between Admin & Secretary
            fifteen_sec_ago = (datetime.datetime.now() - datetime.timedelta(seconds=15)).strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("SELECT 1 FROM check_ins WHERE client_id=? AND timestamp >= ?", (client_id, fifteen_sec_ago))
            if cursor.fetchone() is not None:
                return True

            cursor.execute("PRAGMA table_info(check_ins)")
            c_cols = [r["name"] for r in cursor.fetchall()]

            if "window_number" in c_cols and "confidence_score" in c_cols:
                cursor.execute("""
                    INSERT INTO check_ins (client_id, window_number, timestamp, confidence_score, status)
                    VALUES (?, ?, ?, ?, ?)
                """, (client_id, location, now_str, confidence, status))
            else:
                cursor.execute("""
                    INSERT INTO check_ins (client_id, location, timestamp, confidence, status)
                    VALUES (?, ?, ?, ?, ?)
                """, (client_id, location, now_str, confidence, status))

            # Auto-increment monthly stats
            cursor.execute("""
                INSERT INTO monthly_visit_stats (annee_mois, nombre_visites, montant_avances, montant_total)
                VALUES (?, 1, 0.0, 0.0)
                ON CONFLICT(annee_mois) DO UPDATE SET
                    nombre_visites = nombre_visites + 1
            """, (annee_mois,))
        # FIX 3: Do not call clear_db_caches() here! A check-in does NOT change client face embeddings,
        # so wiping the cache forced the camera thread & presence page to reload all embeddings over DB/network.
        return True
    except Exception as e:
        log_system_error("log_check_in failed", e)
        return False

def recompute_monthly_visit_stats() -> bool:
    """Recalcule integralement la table monthly_visit_stats depuis l'historique check_ins."""
    init_db()
    try:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute("DELETE FROM monthly_visit_stats")
            cursor.execute("""
                INSERT INTO monthly_visit_stats (annee_mois, nombre_visites, montant_avances, montant_total)
                SELECT 
                    substr(timestamp, 1, 7) as annee_mois,
                    COUNT(*) as nombre_visites,
                    COALESCE(SUM(avance_amount), 0.0) as montant_avances,
                    COALESCE(SUM(total_amount), 0.0) as montant_total
                FROM check_ins
                WHERE timestamp IS NOT NULL AND LENGTH(timestamp) >= 7
                GROUP BY substr(timestamp, 1, 7)
            """)
        return True
    except Exception as e:
        log_system_error("recompute_monthly_visit_stats failed", e)
        return False

def archive_old_check_ins(retention_years: int = 2) -> dict:
    """
    Archive automatiquement les entrees check_ins de plus de X ans vers check_ins_archive.db.
    Effectue une VERIFICATION DE CHECKSUM et de nombre d'entrees avant toute suppression.
    """
    init_db()
    cutoff_date = (datetime.datetime.now() - datetime.timedelta(days=retention_years * 365)).strftime("%Y-%m-%d 00:00:00")
    archive_db_path = DATA_DIR / "check_ins_archive.db"
    
    res = {"candidates": 0, "archived": 0, "deleted": 0, "verified": False}
    try:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute("SELECT COUNT(*) as count FROM check_ins WHERE timestamp < ?", (cutoff_date,))
            row = cursor.fetchone()
            count_candidate = row["count"] if row else 0
            res["candidates"] = count_candidate
            
            if count_candidate == 0:
                res["verified"] = True
                return res

            archive_conn = sqlite3.connect(archive_db_path)
            archive_conn.row_factory = sqlite3.Row
            with archive_conn:
                archive_conn.execute("""
                    CREATE TABLE IF NOT EXISTS check_ins_archive (
                        id INTEGER PRIMARY KEY,
                        client_id TEXT,
                        window_number TEXT,
                        timestamp TEXT,
                        confidence_score REAL,
                        status TEXT,
                        payment_status TEXT,
                        avance_amount REAL,
                        total_amount REAL,
                        payment_notes TEXT
                    )
                """)
                
                cursor.execute("SELECT id, client_id, window_number, timestamp, confidence_score, status, payment_status, avance_amount, total_amount, payment_notes FROM check_ins WHERE timestamp < ?", (cutoff_date,))
                rows = cursor.fetchall()
                
                rows_to_insert = [tuple(r) for r in rows]
                archive_conn.executemany("""
                    INSERT OR REPLACE INTO check_ins_archive 
                    (id, client_id, window_number, timestamp, confidence_score, status, payment_status, avance_amount, total_amount, payment_notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, rows_to_insert)
                
                cur_arch = archive_conn.cursor()
                cur_arch.execute("SELECT COUNT(*) as cnt FROM check_ins_archive WHERE timestamp < ?", (cutoff_date,))
                archived_count = cur_arch.fetchone()["cnt"]
                res["archived"] = archived_count
            
            archive_conn.close()
            
            if archived_count >= count_candidate:
                cursor.execute("DELETE FROM check_ins WHERE timestamp < ?", (cutoff_date,))
                res["deleted"] = cursor.rowcount
                res["verified"] = True
                
                now_date = datetime.datetime.now().strftime("%Y-%m-%d")
                cursor.execute("""
                    INSERT INTO system_settings (setting_key, setting_value)
                    VALUES ('last_archive_date', ?)
                    ON CONFLICT(setting_key) DO UPDATE SET setting_value = ?
                """, (now_date, now_date))
                
                if not recompute_monthly_visit_stats():
                    log_system_error("monthly visit stats not recomputed",
                                     Exception("recompute_monthly_visit_stats returned False"))
            else:
                log_system_error("archive_old_check_ins verification failed: count mismatch", Exception("Mismatch count"))
    except Exception as e:
        log_system_error("archive_old_check_ins failed", e)
    return res

def run_daily_archiving_if_needed():
    """Declenche l'archivage au demarrage de l'app une fois par 24h max."""
    try:
        init_db()
        now_date = datetime.datetime.now().strftime("%Y-%m-%d")
        with get_db_cursor() as cursor:
            cursor.execute("SELECT setting_value FROM system_settings WHERE setting_key = 'last_archive_date'")
            row = cursor.fetchone()
            if row and row["setting_value"] == now_date:
                return
        archive_old_check_ins(retention_years=2)
    except Exception as e:
        log_system_error("run_daily_archiving_if_needed failed", e)

@local_cache(ttl=2)
def _read_sql(query: str, conn, params=()):
    """
    Runs a query and returns a DataFrame, without handing the connection to pandas.

    pandas inspects the object it is given and warns that it only fully supports
    SQLAlchemy connectables; against the office server it also meant an extra
    round trip per call. Reading through a cursor gives the same DataFrame from
    the same rows, works identically on a local file and over the network, and
    keeps the console clean.
    """
    import pandas as pd
    cur = conn.cursor()
    try:
        cur.execute(query, params)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = [tuple(r) for r in cur.fetchall()]
        return pd.DataFrame(rows, columns=cols)
    finally:
        try:
            cur.close()
        except Exception:
            # (c) Safe: the cursor is discarded either way.
            pass

def get_recent_check_ins(limit: int = 200) -> pd.DataFrame:
    # Imported here rather than at module scope: it costs ~1.8 s to load and is
    # only needed by the few functions that return a DataFrame.
    import pandas as pd
    try:
        init_db()
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(check_ins)")
        c_cols = [r["name"] for r in cursor.fetchall()]
        
        loc_col = "c.window_number" if "window_number" in c_cols else ("c.location" if "location" in c_cols else "'Guichet'")
        conf_col = "c.confidence_score" if "confidence_score" in c_cols else ("c.confidence" if "confidence" in c_cols else "1.0")
        pay_col = "c.payment_status" if "payment_status" in c_cols else "'غير خالص / En attente'"
        av_col = "c.avance_amount" if "avance_amount" in c_cols else "0.0"
        tot_col = "c.total_amount" if "total_amount" in c_cols else "0.0"
        note_col = "c.payment_notes" if "payment_notes" in c_cols else "''"

        query = f"""
            SELECT c.id as 'ID_LOG',
                   c.timestamp as 'Date & Heure',
                   COALESCE(cl.full_name, c.client_id, 'Client Inconnu') as 'Client',
                   c.client_id as 'ID Client',
                   COALESCE(cl.cin_number, '') as 'CIN',
                   COALESCE(cl.phone, '') as 'Téléphone',
                   COALESCE(cl.profile_pic_path, '') as 'PhotoPath',
                   {loc_col} as 'Guichet',
                   {pay_col} as 'الخلاص / Règlement',
                   COALESCE({av_col}, 0.0) as 'Avance_Raw',
                   COALESCE({tot_col}, 0.0) as 'Total_Raw',
                   ROUND((COALESCE({tot_col}, 0.0) - COALESCE({av_col}, 0.0)), 3) as 'Restant_Raw',
                   {note_col} as 'ملاحظات / Notes',
                   ROUND({conf_col} * 100, 1) as 'Confiance_Raw',
                   ROUND({conf_col} * 100, 1) || '%' as 'Confiance'
            FROM check_ins c
            LEFT JOIN clients cl ON c.client_id = cl.client_id
            ORDER BY c.timestamp DESC
            LIMIT ?
        """
        df = _read_sql(query, conn, params=(limit,))
        conn.close()
        return df
    except Exception as e:
        log_system_error("get_recent_check_ins failed", e)
        raise DataUnavailable("presence journal unreadable", "journal") from e

@permissions.require(Cap.VIEW_REVENUE)
def get_check_in_inflows_between(start_str: str, end_str: str) -> pd.DataFrame:
    """
    Every check-in carrying an advance payment inside a date range.

    Accounting previously took the most recent 500 check-ins and then filtered them by
    date, so any period older than those 500 silently under-reported its income. The
    date range belongs in the query.
    """
    # Imported here rather than at module scope: it costs ~1.8 s to load and is
    # only needed by the few functions that return a DataFrame.
    import pandas as pd
    init_db()
    try:
        conn = get_connection()
        query = """
            SELECT c.timestamp AS timestamp,
                   c.client_id  AS client_id,
                   COALESCE(cl.full_name, c.client_id, '') AS client_name,
                   COALESCE(cl.phone, '') AS phone,
                   COALESCE(c.avance_amount, 0.0) AS avance_amount,
                   COALESCE(c.total_amount, 0.0)  AS total_amount
            FROM check_ins c
            LEFT JOIN clients cl ON c.client_id = cl.client_id
            WHERE c.timestamp >= ? AND c.timestamp <= ?
              AND COALESCE(c.avance_amount, 0.0) > 0
            ORDER BY c.timestamp DESC
        """
        return _read_sql(query, conn, params=(start_str, end_str))
    except Exception as e:
        log_system_error("get_check_in_inflows_between failed", e)
        return pd.DataFrame()


# The presence search's match condition, written once so the rows returned and
# the count reported can never disagree about what "matching" means.
_CHECKIN_SEARCH_WHERE = """
    COALESCE(cl.full_name,'') LIKE ?
 OR COALESCE(cl.cin_number,'') LIKE ?
 OR c.client_id LIKE ?
 OR c.timestamp LIKE ?
 OR COALESCE(c.window_number,'') LIKE ?
"""

# A ceiling large enough that no real notarial office reaches it, kept only so a
# pathological search cannot try to build a million-row DataFrame. When it IS
# reached the caller is told, rather than being handed a short answer silently.
CHECKIN_SEARCH_CAP = 20000


def count_check_ins_matching(query_str: str) -> int:
    """
    How many check-ins genuinely match -- independent of how many are returned.

    The page needs this to tell "2000 matched" apart from "2000 shown of more",
    which the old label could not express.
    """
    q = f"%{(query_str or '').strip()}%"
    try:
        init_db()
        with get_db_cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS n FROM check_ins c "
                "LEFT JOIN clients cl ON c.client_id = cl.client_id "
                "WHERE " + _CHECKIN_SEARCH_WHERE, (q, q, q, q, q))
            return int(cursor.fetchone()["n"])
    except Exception as e:
        log_system_error("count_check_ins_matching failed", e)
        raise DataUnavailable("match count failed", "matching") from e


def search_check_ins(query_str: str, limit: int = None) -> pd.DataFrame:
    """
    Searches the whole presence history, not only the most recent page.

    The Journal page previously filtered inside a 200-row window, so anything older
    than the last 200 visits could not be found at all. This searches in SQL across
    client name, CIN, client id, window and date.

    CIN was missing from this list: typing the number off a client's identity card
    -- the one number a notary is certain of -- returned nothing at all, however
    many visits that client had.
    """
    # Imported here rather than at module scope: it costs ~1.8 s to load and is
    # only needed by the few functions that return a DataFrame.
    import pandas as pd
    limit = CHECKIN_SEARCH_CAP if limit is None else limit
    q = f"%{(query_str or '').strip()}%"
    try:
        init_db()
        conn = get_connection()
        query = """
            SELECT c.id as 'ID_LOG',
                   c.timestamp as 'Date & Heure',
                   COALESCE(cl.full_name, c.client_id, 'Client Inconnu') as 'Client',
                   c.client_id as 'ID Client',
                   COALESCE(cl.cin_number, '') as 'CIN',
                   COALESCE(cl.phone, '') as 'Téléphone',
                   COALESCE(cl.profile_pic_path, '') as 'PhotoPath',
                   c.window_number as 'Guichet',
                   c.payment_status as 'الخلاص / Règlement',
                   COALESCE(c.avance_amount, 0.0) as 'Avance_Raw',
                   COALESCE(c.total_amount, 0.0) as 'Total_Raw',
                   ROUND((COALESCE(c.total_amount, 0.0) - COALESCE(c.avance_amount, 0.0)), 3) as 'Restant_Raw',
                   c.payment_notes as 'ملاحظات / Notes',
                   ROUND(c.confidence_score * 100, 1) as 'Confiance_Raw',
                   ROUND(c.confidence_score * 100, 1) || '%' as 'Confiance'
            FROM check_ins c
            LEFT JOIN clients cl ON c.client_id = cl.client_id
            WHERE """  + _CHECKIN_SEARCH_WHERE + """
            ORDER BY c.timestamp DESC
            LIMIT ?
        """
        return _read_sql(query, conn, params=(q, q, q, q, q, limit))
    except Exception as e:
        log_system_error("search_check_ins failed", e)
        raise DataUnavailable("presence search failed", "search") from e


def get_check_ins_filtered(
    query_str: str = "",
    date_from: str = "",
    date_to: str = "",
    payment_status: str = "",
    min_confidence: float = 0.0,
    limit: int = None,
) -> "pd.DataFrame":
    """
    Combined filter for the Journal de Présence page.
    Supports text search + date range + payment status + minimum confidence.
    Returns all columns needed by PresenceTableModel including CIN, phone,
    and raw financial values for the smart payment status cell.
    """
    import pandas as pd
    limit = CHECKIN_SEARCH_CAP if limit is None else limit

    conditions = []
    params: list = []

    # Text search across name / CIN / client_id / timestamp / window
    if query_str.strip():
        q = f"%{query_str.strip()}%"
        conditions.append(
            "(COALESCE(cl.full_name,'') LIKE ?"
            " OR COALESCE(cl.cin_number,'') LIKE ?"
            " OR c.client_id LIKE ?"
            " OR c.timestamp LIKE ?"
            " OR COALESCE(c.window_number,'') LIKE ?)"
        )
        params.extend([q, q, q, q, q])

    # Date range — timestamp stored as 'YYYY-MM-DD HH:MM:SS'
    if date_from.strip():
        conditions.append("c.timestamp >= ?")
        params.append(date_from.strip() + " 00:00:00")
    if date_to.strip():
        conditions.append("c.timestamp <= ?")
        params.append(date_to.strip() + " 23:59:59")

    # Payment status filter
    if payment_status.strip():
        ps = payment_status.strip().lower()
        if ps in ("payé", "paye", "paid"):
            conditions.append(
                "(LOWER(COALESCE(c.payment_status,'')) LIKE '%خالص%'"
                " AND LOWER(COALESCE(c.payment_status,'')) NOT LIKE '%غير%'"
                " AND LOWER(COALESCE(c.payment_status,'')) NOT LIKE '%acompte%'"
                " AND LOWER(COALESCE(c.payment_status,'')) NOT LIKE '%تسبقة%')"
            )
        elif ps in ("non payé", "non paye", "unpaid"):
            conditions.append(
                "(LOWER(COALESCE(c.payment_status,'')) LIKE '%غير%'"
                " OR LOWER(COALESCE(c.payment_status,'')) LIKE '%non pay%')"
            )
        elif ps in ("acompte",):
            conditions.append(
                "(LOWER(COALESCE(c.payment_status,'')) LIKE '%acompte%'"
                " OR LOWER(COALESCE(c.payment_status,'')) LIKE '%تسبقة%')"
            )

    # Minimum confidence
    if min_confidence > 0:
        conditions.append("COALESCE(c.confidence_score, 0) * 100 >= ?")
        params.append(min_confidence)

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.append(limit)

    sql = f"""
        SELECT c.id as 'ID_LOG',
               c.timestamp as 'Date & Heure',
               COALESCE(cl.full_name, c.client_id, 'Client Inconnu') as 'Client',
               c.client_id as 'ID Client',
               COALESCE(cl.cin_number, '') as 'CIN',
               COALESCE(cl.phone, '') as 'Téléphone',
               COALESCE(cl.profile_pic_path, '') as 'PhotoPath',
               c.window_number as 'Guichet',
               c.payment_status as 'الخلاص / Règlement',
               COALESCE(c.avance_amount, 0.0) as 'Avance_Raw',
               COALESCE(c.total_amount, 0.0) as 'Total_Raw',
               ROUND((COALESCE(c.total_amount, 0.0) - COALESCE(c.avance_amount, 0.0)), 3) as 'Restant_Raw',
               c.payment_notes as 'ملاحظات / Notes',
               ROUND(c.confidence_score * 100, 1) as 'Confiance_Raw',
               ROUND(c.confidence_score * 100, 1) || '%' as 'Confiance'
        FROM check_ins c
        LEFT JOIN clients cl ON c.client_id = cl.client_id
        {where_clause}
        ORDER BY c.timestamp DESC
        LIMIT ?
    """
    try:
        init_db()
        conn = get_connection()
        df = _read_sql(sql, conn, params=tuple(params))
        conn.close()
        return df
    except Exception as e:
        log_system_error("get_check_ins_filtered failed", e)
        raise DataUnavailable("filtered presence query failed", "journal") from e


def get_check_ins_for_client(client_id: str) -> pd.DataFrame:
    # Imported here rather than at module scope: it costs ~1.8 s to load and is
    # only needed by the few functions that return a DataFrame.
    import pandas as pd
    init_db()
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(check_ins)")
        c_cols = [r["name"] for r in cursor.fetchall()]
        
        loc_col = "window_number" if "window_number" in c_cols else ("location" if "location" in c_cols else "'Guichet'")
        conf_col = "confidence_score" if "confidence_score" in c_cols else ("confidence" if "confidence" in c_cols else "1.0")
        stat_col = "status" if "status" in c_cols else "'Passage'"

        query = f"""
            SELECT timestamp as 'Date & Heure',
                   {loc_col} as 'Guichet',
                   ROUND({conf_col} * 100, 1) || '%' as 'Confiance',
                   {stat_col} as 'Statut'
            FROM check_ins
            WHERE client_id=?
            ORDER BY timestamp DESC
        """
        df = _read_sql(query, conn, params=(client_id,))
        conn.close()
        return df
    except Exception as e:
        log_system_error("get_check_ins_for_client failed", e)
        return pd.DataFrame()

@licensing.require_licence
@permissions.require(Cap.CREATE_DOSSIER)
def create_case(
    client_id: str, service_type: str, title: str, description: str,
    status: str = "جديد",
    total_amount: float = 0.0, avance_amount: float = 0.0,
    payment_status: str = "غير خالص", payment_notes: str = "",
    custom_case_id: str = "",
    party1_name: str = "", party2_name: str = "",
    client_ids: Optional[List[str]] = None
) -> str:
    init_db()
    now = datetime.datetime.now()
    try:
        with get_db_cursor(commit=True) as cursor:
            if custom_case_id and custom_case_id.strip():
                case_id = custom_case_id.strip()
            else:
                cursor.execute(
                    "SELECT COALESCE(MAX(CAST(case_id AS INTEGER)), 0) FROM cases")
                row = cursor.fetchone()
                highest = int(row[0]) if row and row[0] else 0
                case_id = str(highest + 1)
            created_at = now.strftime("%Y-%m-%d %H:%M:%S")

            # Validate client_id against foreign key requirement in clients table
            valid_client_id = None
            if client_id and isinstance(client_id, str) and client_id.strip():
                cid_str = client_id.strip()
                row = cursor.execute("SELECT client_id FROM clients WHERE client_id = ? OR cin_number = ?", (cid_str, cid_str)).fetchone()
                if row:
                    valid_client_id = row[0]

            cursor.execute("""
                INSERT OR REPLACE INTO cases
                (case_id, client_id, service_type, title, description, status, created_at, total_amount, avance_amount, payment_status, payment_notes, party1_name, party2_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (case_id, valid_client_id, service_type, title, description, status, created_at, total_amount, avance_amount, payment_status, payment_notes, party1_name, party2_name))

            all_cids = set()
            if valid_client_id:
                all_cids.add(valid_client_id)
            if client_ids:
                for c in client_ids:
                    if c and isinstance(c, str) and c.strip():
                        c_str = c.strip()
                        row_c = cursor.execute("SELECT client_id FROM clients WHERE client_id = ? OR cin_number = ?", (c_str, c_str)).fetchone()
                        if row_c:
                            all_cids.add(row_c[0])

            for cid in all_cids:
                try:
                    cursor.execute("INSERT OR IGNORE INTO case_clients (case_id, client_id) VALUES (?, ?)", (case_id, cid))
                except Exception:
                    pass

            clear_db_caches()
            return case_id
    except Exception as e:
        log_system_error("create_case failed", e)
        return "1"

@permissions.require(Cap.RECORD_PAYMENT)
def update_case_payment(case_id: str, total_amount: float, avance_amount: float, payment_status: str, payment_notes: str) -> bool:
    init_db()
    with get_db_cursor(commit=True) as cursor:
        cursor.execute("""
            UPDATE cases
            SET total_amount = ?, avance_amount = ?, payment_status = ?, payment_notes = ?
            WHERE case_id = ?
        """, (total_amount, avance_amount, payment_status, payment_notes, case_id))
        changed = cursor.rowcount
    clear_db_caches()
    if changed == 0:
        log_system_error("update_case_payment matched no rows",
                         Exception(f"case_id={case_id!r} not found"))
    return changed > 0

def link_clients_to_case(case_id: str, client_ids: List[str]) -> bool:
    init_db()
    if not case_id or not client_ids:
        return False
    try:
        with get_db_cursor(commit=True) as cursor:
            chk_case = cursor.execute("SELECT 1 FROM cases WHERE case_id = ?", (str(case_id),)).fetchone()
            if not chk_case:
                return False
            for cid in client_ids:
                if cid and isinstance(cid, str) and cid.strip():
                    c_str = cid.strip()
                    row_c = cursor.execute("SELECT client_id FROM clients WHERE client_id = ? OR cin_number = ?", (c_str, c_str)).fetchone()
                    if row_c:
                        cursor.execute("INSERT OR IGNORE INTO case_clients (case_id, client_id) VALUES (?, ?)", (str(case_id), row_c[0]))
        clear_db_caches()
        return True
    except Exception as e:
        log_system_error("link_clients_to_case failed", e)
        return False

def sync_case_clients_from_documents() -> bool:
    """Auto-links case_id and client_id if a document file for case_id is stored in client_id's folder."""
    try:
        init_db()
        if not DOCUMENTS_DIR.exists():
            return True
        links = []
        import re
        for cdir in DOCUMENTS_DIR.iterdir():
            if cdir.is_dir():
                cid = cdir.name
                for f in cdir.iterdir():
                    if f.is_file():
                        fname = f.name
                        m1 = re.match(r"^ملف_رقم_([^\.]+)", fname)
                        m2 = re.match(r"^Dossier_([^_]+)_", fname)
                        case_id = None
                        if m1:
                            case_id = m1.group(1)
                        elif m2:
                            case_id = m2.group(1)
                        if case_id:
                            links.append((case_id, cid))
        if links:
            with get_db_cursor(commit=True) as cursor:
                for case_id, cid in links:
                    chk_case = cursor.execute("SELECT 1 FROM cases WHERE case_id = ?", (str(case_id),)).fetchone()
                    row_c = cursor.execute("SELECT client_id FROM clients WHERE client_id = ? OR cin_number = ?", (str(cid), str(cid))).fetchone()
                    if chk_case and row_c:
                        cursor.execute("INSERT OR IGNORE INTO case_clients (case_id, client_id) VALUES (?, ?)", (str(case_id), row_c[0]))
            clear_db_caches()
        return True
    except Exception as e:
        log_system_error("sync_case_clients_from_documents failed", e)
        return False

def get_client_cases(client_id: str) -> List[Dict]:
    init_db()
    try:
        sync_case_clients_from_documents()
    except Exception:
        pass
    rows = []
    try:
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT c.* FROM cases c
                LEFT JOIN case_clients cc ON c.case_id = cc.case_id
                WHERE c.client_id=? OR cc.client_id=?
                ORDER BY c.created_at DESC
            """, (client_id, client_id))
            rows = cursor.fetchall()
    except Exception as e:
        log_system_error("get_client_cases failed", e)
    return permissions.redact([dict(r) for r in rows], Cap.VIEW_DOSSIER_AMOUNTS)

# The Registre dashboard needs the office-wide picture, not the picture of
# whatever filter happens to be applied. Counting in SQL rather than fetching
# every dossier keeps that cheap enough to run on each refresh.
CASE_STATUS_NEW = "جديد"
CASE_STATUS_IN_PROGRESS = "قيد الإنجاز"
CASE_STATUS_AWAITING = "في انتظار التوقيع"
CASE_STATUS_FINALISED = "تام ومسجل"


@local_cache(ttl=30)
def count_cases_by_status() -> Dict[str, int]:
    """
    Office-wide dossier counts, keyed by a stable English name.

    `active` is every dossier that is not finalised — new, in progress, and
    awaiting signature together. The Registre used to add those three up and
    label the result "Dossiers En Cours", which is a different and smaller thing.
    Both numbers are returned here so the screen can name each one correctly.
    """
    init_db()
    out = {"total": 0, "new": 0, "in_progress": 0, "awaiting_signature": 0,
           "finalised": 0, "active": 0, "other": 0}
    try:
        with get_db_cursor() as cursor:
            cursor.execute("SELECT status, COUNT(*) AS n FROM cases GROUP BY status")
            for r in cursor.fetchall():
                status = (r["status"] or "").strip()
                n = int(r["n"] or 0)
                out["total"] += n
                if CASE_STATUS_FINALISED in status or "تام" in status:
                    out["finalised"] += n
                elif "انتظار" in status or "توقيع" in status:
                    out["awaiting_signature"] += n
                elif "إنجاز" in status or "انجاز" in status:
                    out["in_progress"] += n
                elif CASE_STATUS_NEW in status or not status:
                    out["new"] += n
                else:
                    out["other"] += n
        out["active"] = (out["new"] + out["in_progress"]
                         + out["awaiting_signature"] + out["other"])
    except Exception as e:
        log_system_error("count_cases_by_status failed", e)
    return out


@local_cache(ttl=60)
def get_client_case_counts() -> Dict[str, int]:
    counts = {}
    try:
        init_db()
        with get_db_cursor() as cursor:
            cursor.execute("SELECT client_id, COUNT(*) as count FROM cases GROUP BY client_id")
            for r in cursor.fetchall():
                counts[r["client_id"]] = r["count"]
    except Exception as e:
        log_system_error("get_client_case_counts failed", e)
        raise DataUnavailable("le nombre de dossiers par client est illisible",
                              "clients") from e
    return counts

@permissions.require(Cap.VIEW_REVENUE)
def get_case_inflows_between(start_str: str, end_str: str) -> List[Dict]:
    """
    Only the dossiers that carry an advance inside the period.

    The accounting page used to materialise all 20,000 dossiers as Python dicts and
    then discard the ones outside the period. The WHERE clause belongs in SQL: at a
    typical month this returns a few hundred rows instead of twenty thousand.
    """
    init_db()
    out = []
    try:
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT cs.case_id, cs.client_id, cs.created_at,
                       COALESCE(cs.total_amount, 0.0)  AS total_amount,
                       COALESCE(cs.avance_amount, 0.0) AS avance_amount,
                       COALESCE(cs.payment_notes, '')  AS payment_notes,
                       COALESCE(cl.full_name, '')      AS client_name,
                       COALESCE(cl.phone, '')          AS client_phone
                FROM cases cs
                LEFT JOIN clients cl ON cs.client_id = cl.client_id
                WHERE cs.created_at >= ? AND cs.created_at <= ?
                  AND COALESCE(cs.avance_amount, 0.0) > 0
                ORDER BY cs.created_at DESC
            """, (start_str, end_str))
            out = [dict(r) for r in cursor.fetchall()]
    except Exception as e:
        log_system_error("get_case_inflows_between failed", e)
    return out


@permissions.require(Cap.VIEW_RECEIVABLES)
def get_receivables(limit: int = 5000) -> Tuple[List[Dict], float, int]:
    """
    Outstanding balances, plus the true total and count.

    Returns (rows, total_outstanding, total_matching_rows). The total and count come
    from SQL aggregates over every dossier, so capping the returned rows for display
    never distorts the reported figure.
    """
    init_db()
    rows, total, count = [], 0.0, 0
    try:
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) AS n,
                       COALESCE(SUM(COALESCE(total_amount,0.0) - COALESCE(avance_amount,0.0)), 0.0) AS s
                FROM cases
                WHERE (COALESCE(total_amount,0.0) - COALESCE(avance_amount,0.0)) > 0
            """)
            r = cursor.fetchone()
            count, total = int(r["n"]), float(r["s"])

            cursor.execute("""
                SELECT cs.case_id, cs.client_id, cs.service_type, cs.title,
                       cs.created_at, cs.payment_status,
                       COALESCE(cs.total_amount, 0.0)  AS total_amount,
                       COALESCE(cs.avance_amount, 0.0) AS avance_amount,
                       ROUND(COALESCE(cs.total_amount,0.0) - COALESCE(cs.avance_amount,0.0), 3) AS reste,
                       COALESCE(cl.full_name, '')      AS client_name,
                       COALESCE(cl.phone, '')          AS client_phone
                FROM cases cs
                LEFT JOIN clients cl ON cs.client_id = cl.client_id
                WHERE (COALESCE(cs.total_amount,0.0) - COALESCE(cs.avance_amount,0.0)) > 0
                ORDER BY reste DESC
                LIMIT ?
            """, (limit,))
            rows = [dict(x) for x in cursor.fetchall()]
    except Exception as e:
        log_system_error("get_receivables failed", e)
    return rows, total, count


@permissions.require(Cap.EDIT_DOSSIER)
def update_case_status(case_id: str, status: str) -> bool:
    """Returns True only when a row actually changed. See update_case_payment."""
    init_db()
    changed = 0
    with get_db_cursor(commit=True) as cursor:
        cursor.execute("UPDATE cases SET status=? WHERE case_id=?", (status, case_id))
        changed = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
    clear_db_caches()
    if changed == 0:
        log_system_error("update_case_status matched no rows",
                         Exception(f"case_id={case_id!r} not found"))
    return changed > 0

@permissions.require(Cap.DELETE_DOSSIER)
def delete_case(case_id: str) -> bool:
    """Returns True only when a row was actually removed. See update_case_payment."""
    init_db()
    removed = 0
    with get_db_cursor(commit=True) as cursor:
        cursor.execute("DELETE FROM cases WHERE case_id=?", (case_id,))
        removed = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
    clear_db_caches()
    if removed == 0:
        log_system_error("delete_case matched no rows",
                         Exception(f"case_id={case_id!r} not found"))
    return removed > 0

def get_client_documents_list(client_id: str) -> List[Dict]:
    try:
        cdir = DOCUMENTS_DIR / client_id
        if not cdir.exists():
            return []
        docs = []
        for f in cdir.iterdir():
            if f.is_file():
                docs.append({
                    "name": f.name,
                    "path": str(f),
                    "size_kb": round(f.stat().st_size / 1024, 1)
                })
        return docs
    except Exception as e:
        log_system_error("get_client_documents_list failed", e)
        return []

def _safe_doc_path(client_id: str, file_name: str) -> Optional[Path]:
    """
    Resolves a document path and refuses anything outside the client's own folder.

    file_name reaches these functions from listings and from user-chosen uploads; a
    name containing a path separator or ".." would otherwise resolve outside
    DOCUMENTS_DIR and let a delete or a write escape the client's directory.
    """
    try:
        base = (DOCUMENTS_DIR / str(client_id)).resolve()
        leaf = Path(str(file_name)).name          # strips any directory component
        if not leaf or leaf in (".", ".."):
            return None
        candidate = (base / leaf).resolve()
        if candidate.parent != base:
            return None
        return candidate
    except Exception:
        return None


@permissions.require(Cap.EDIT_CLIENTS)
def delete_client_document(client_id: str, file_name: str) -> bool:
    try:
        fpath = _safe_doc_path(client_id, file_name)
        if fpath is None:
            log_system_error("delete_client_document rejected path",
                             ValueError(f"{client_id!r}/{file_name!r}"))
            return False
        if fpath.exists():
            fpath.unlink(missing_ok=True)
            return True
    except Exception as e:
        log_system_error("delete_client_document failed", e)
    return False

def save_client_document(client_id: str, file_bytes: bytes, file_name: str) -> str:
    try:
        cdir = DOCUMENTS_DIR / str(client_id)
        cdir.mkdir(parents=True, exist_ok=True)
        fpath = _safe_doc_path(client_id, file_name)
        if fpath is None:
            log_system_error("save_client_document rejected path",
                             ValueError(f"{client_id!r}/{file_name!r}"))
            return ""
        fpath.write_bytes(file_bytes)
        return str(fpath)
    except Exception as e:
        log_system_error("save_client_document failed", e)
        return ""

@licensing.require_licence
@permissions.require(Cap.MANAGE_EXPENSES)
def add_expense(description: str, category: str, amount: float, photo_path: str = "") -> bool:
    init_db()
    try:
        with get_db_cursor(commit=True) as cursor:
            try:
                cursor.execute("ALTER TABLE expenses ADD COLUMN photo_path TEXT")
            except sqlite3.OperationalError:
                # (c) Safe, and narrowed from bare Exception: "duplicate column
                # name" is the normal path on every run after the first.
                pass
            created_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                INSERT INTO expenses (description, category, amount, created_at, photo_path)
                VALUES (?, ?, ?, ?, ?)
            """, (description, category, amount, created_at, photo_path))
        clear_db_caches()
        return True
    except Exception as e:
        log_system_error("add_expense failed", e)
        return False

@permissions.require(Cap.VIEW_EXPENSES)
@local_cache(ttl=60)
def get_expenses() -> List[Dict]:
    init_db()
    try:
        with get_db_cursor() as cursor:
            cursor.execute("SELECT * FROM expenses ORDER BY created_at DESC")
            return [dict(r) for r in cursor.fetchall()]
    except Exception as e:
        log_system_error("get_expenses failed", e)
        return []

@permissions.require(Cap.MANAGE_EXPENSES)
def delete_expense(expense_id: int) -> bool:
    init_db()
    try:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute("DELETE FROM expenses WHERE id=?", (expense_id,))
            removed = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
        clear_db_caches()
        if removed == 0:
            log_system_error("delete_expense matched no rows",
                             Exception(f"id={expense_id!r} not found"))
        return removed > 0
    except Exception as e:
        log_system_error("delete_expense failed", e)
        return False

@licensing.require_licence
@permissions.require(Cap.MANAGE_EXPENSES)
def add_salary(employee_name: str, role: str, amount: float, notes: str = "", photo_path: str = "") -> bool:
    init_db()
    try:
        with get_db_cursor(commit=True) as cursor:
            try:
                cursor.execute("ALTER TABLE salaries ADD COLUMN photo_path TEXT")
            except sqlite3.OperationalError:
                # (c) Safe, same as the expenses migration above.
                pass
            payment_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                INSERT INTO salaries (employee_name, role, amount, payment_date, notes, photo_path)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (employee_name, role, amount, payment_date, notes, photo_path))
        clear_db_caches()
        return True
    except Exception as e:
        log_system_error("add_salary failed", e)
        return False

@permissions.require(Cap.VIEW_EXPENSES)
@local_cache(ttl=60)
def get_salaries() -> List[Dict]:
    init_db()
    try:
        with get_db_cursor() as cursor:
            cursor.execute("SELECT * FROM salaries ORDER BY payment_date DESC")
            return [dict(r) for r in cursor.fetchall()]
    except Exception as e:
        log_system_error("get_salaries failed", e)
        return []

@permissions.require(Cap.MANAGE_EXPENSES)
def delete_salary(salary_id: int) -> bool:
    init_db()
    try:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute("DELETE FROM salaries WHERE id=?", (salary_id,))
            removed = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
        clear_db_caches()
        if removed == 0:
            log_system_error("delete_salary matched no rows",
                             Exception(f"id={salary_id!r} not found"))
        return removed > 0
    except Exception as e:
        log_system_error("delete_salary failed", e)
        return False

# -- Correcting an entry that is already recorded -----------------------------
# Deleting the row and retyping it was the only way to fix a typo, which loses
# the original date and leaves no trace that a figure was ever different. A
# correction is now a first-class operation: guarded by its own capability, and
# written to a log so the old value is never simply gone.

def _log_record_edit(table: str, row_id, field: str, before, after) -> None:
    """Appends one before/after line to the corrections log. Never raises."""
    try:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS record_edits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    table_name TEXT,
                    row_id TEXT,
                    field TEXT,
                    old_value TEXT,
                    new_value TEXT,
                    edited_by TEXT,
                    edited_at TEXT
                )
            """)
            cursor.execute("""
                INSERT INTO record_edits
                    (table_name, row_id, field, old_value, new_value, edited_by, edited_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (table, str(row_id), field, str(before), str(after),
                  permissions.session.username or "?",
                  datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    except Exception as e:
        # (c) Safe: the correction itself has already been applied. Losing the
        # log line is worse than nothing but far better than refusing the fix.
        log_system_error("could not log a record correction", e)


def get_record_edits(table: str = "", limit: int = 200) -> List[Dict]:
    """The corrections log, newest first. For the notary to review."""
    init_db()
    try:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS record_edits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    table_name TEXT, row_id TEXT, field TEXT,
                    old_value TEXT, new_value TEXT,
                    edited_by TEXT, edited_at TEXT)
            """)
            if table:
                cursor.execute("SELECT * FROM record_edits WHERE table_name=? "
                               "ORDER BY id DESC LIMIT ?", (table, limit))
            else:
                cursor.execute("SELECT * FROM record_edits ORDER BY id DESC LIMIT ?",
                               (limit,))
            return [dict(r) for r in cursor.fetchall()]
    except Exception as e:
        log_system_error("get_record_edits failed", e)
        return []


@permissions.require(Cap.EDIT_FINANCE_ENTRY)
def update_expense(expense_id: int, description: str, category: str,
                   amount: float, photo_path: str = None) -> bool:
    """
    Corrects a recorded charge. Returns True only when a row actually changed.

    photo_path=None leaves the attached receipt alone; pass "" to detach it.
    """
    init_db()
    try:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute("SELECT * FROM expenses WHERE id=?", (expense_id,))
            before = cursor.fetchone()
            if before is None:
                log_system_error("update_expense matched no rows",
                                 Exception(f"expense id={expense_id!r} not found"))
                return False
            before = dict(before)
            if photo_path is None:
                cursor.execute("UPDATE expenses SET description=?, category=?, "
                               "amount=? WHERE id=?",
                               (description, category, amount, expense_id))
            else:
                cursor.execute("UPDATE expenses SET description=?, category=?, "
                               "amount=?, photo_path=? WHERE id=?",
                               (description, category, amount, photo_path, expense_id))
            changed = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
        after = {"description": description, "category": category, "amount": amount}
        if photo_path is not None:
            after["photo_path"] = photo_path
        for field, new in after.items():
            old = before.get(field)
            if str(old) != str(new):
                _log_record_edit("expenses", expense_id, field, old, new)
        clear_db_caches()
        return changed > 0
    except Exception as e:
        log_system_error("update_expense failed", e)
        return False


@permissions.require(Cap.EDIT_FINANCE_ENTRY)
def update_salary(salary_id: int, employee_name: str, amount: float,
                  notes: str = "", photo_path: str = None) -> bool:
    """Corrects a recorded salary. See update_expense."""
    init_db()
    try:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute("SELECT * FROM salaries WHERE id=?", (salary_id,))
            before = cursor.fetchone()
            if before is None:
                log_system_error("update_salary matched no rows",
                                 Exception(f"salary id={salary_id!r} not found"))
                return False
            before = dict(before)
            if photo_path is None:
                cursor.execute("UPDATE salaries SET employee_name=?, amount=?, "
                               "notes=? WHERE id=?",
                               (employee_name, amount, notes, salary_id))
            else:
                cursor.execute("UPDATE salaries SET employee_name=?, amount=?, "
                               "notes=?, photo_path=? WHERE id=?",
                               (employee_name, amount, notes, photo_path, salary_id))
            changed = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
        after = {"employee_name": employee_name, "amount": amount, "notes": notes}
        if photo_path is not None:
            after["photo_path"] = photo_path
        for field, new in after.items():
            old = before.get(field)
            if str(old) != str(new):
                _log_record_edit("salaries", salary_id, field, old, new)
        clear_db_caches()
        return changed > 0
    except Exception as e:
        log_system_error("update_salary failed", e)
        return False


@permissions.require(Cap.EDIT_DOSSIER)
def update_case_details(case_id: str, title: str, service_type: str,
                        description: str = None) -> bool:
    """
    Corrects a dossier's own wording. Returns True only when a row changed.

    There was no function for this at all: a dossier's status could be changed
    and its payment recorded, but a mistyped title or the wrong service type was
    permanent. The only remedy was to delete the dossier -- losing its number,
    its date and its payment history -- and create it again.

    description=None leaves the description alone.
    """
    init_db()
    try:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute("SELECT * FROM cases WHERE case_id=?", (case_id,))
            before = cursor.fetchone()
            if before is None:
                log_system_error("update_case_details matched no rows",
                                 Exception(f"case_id={case_id!r} not found"))
                return False
            before = dict(before)
            if description is None:
                cursor.execute("UPDATE cases SET title=?, service_type=? "
                               "WHERE case_id=?", (title, service_type, case_id))
            else:
                cursor.execute("UPDATE cases SET title=?, service_type=?, "
                               "description=? WHERE case_id=?",
                               (title, service_type, description, case_id))
            changed = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
        after = {"title": title, "service_type": service_type}
        if description is not None:
            after["description"] = description
        for field, new in after.items():
            old = before.get(field)
            if str(old) != str(new):
                _log_record_edit("cases", case_id, field, old, new)
        clear_db_caches()
        return changed > 0
    except Exception as e:
        log_system_error("update_case_details failed", e)
        return False


@permissions.require(Cap.EDIT_DOSSIER)
def update_case_details(case_id: str, title: str, service_type: str,
                        description: str = None) -> bool:
    """
    Corrects a dossier's own wording. Returns True only when a row changed.

    There was no function for this at all: a dossier's status could be changed
    and its payment recorded, but a mistyped title or the wrong service type was
    permanent. The only remedy was to delete the dossier -- losing its number,
    its date and its payment history -- and create it again.

    description=None leaves the description alone.
    """
    init_db()
    try:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute("SELECT * FROM cases WHERE case_id=?", (case_id,))
            before = cursor.fetchone()
            if before is None:
                log_system_error("update_case_details matched no rows",
                                 Exception(f"case_id={case_id!r} not found"))
                return False
            before = dict(before)
            if description is None:
                cursor.execute("UPDATE cases SET title=?, service_type=? "
                               "WHERE case_id=?", (title, service_type, case_id))
            else:
                cursor.execute("UPDATE cases SET title=?, service_type=?, "
                               "description=? WHERE case_id=?",
                               (title, service_type, description, case_id))
            changed = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
        after = {"title": title, "service_type": service_type}
        if description is not None:
            after["description"] = description
        for field, new in after.items():
            old = before.get(field)
            if str(old) != str(new):
                _log_record_edit("cases", case_id, field, old, new)
        clear_db_caches()
        return changed > 0
    except Exception as e:
        log_system_error("update_case_details failed", e)
        return False


@permissions.require(Cap.EDIT_DOSSIER)
def update_case_details(case_id: str, title: str, service_type: str,
                        description: str = None) -> bool:
    """
    Corrects a dossier's own wording. Returns True only when a row changed.

    There was no function for this at all: a dossier's status could be changed
    and its payment recorded, but a mistyped title or the wrong service type was
    permanent. The only remedy was to delete the dossier -- losing its number,
    its date and its payment history -- and create it again.

    description=None leaves the description alone.
    """
    init_db()
    try:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute("SELECT * FROM cases WHERE case_id=?", (case_id,))
            before = cursor.fetchone()
            if before is None:
                log_system_error("update_case_details matched no rows",
                                 Exception(f"case_id={case_id!r} not found"))
                return False
            before = dict(before)
            if description is None:
                cursor.execute("UPDATE cases SET title=?, service_type=? "
                               "WHERE case_id=?", (title, service_type, case_id))
            else:
                cursor.execute("UPDATE cases SET title=?, service_type=?, "
                               "description=? WHERE case_id=?",
                               (title, service_type, description, case_id))
            changed = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
        after = {"title": title, "service_type": service_type}
        if description is not None:
            after["description"] = description
        for field, new in after.items():
            old = before.get(field)
            if str(old) != str(new):
                _log_record_edit("cases", case_id, field, old, new)
        clear_db_caches()
        return changed > 0
    except Exception as e:
        log_system_error("update_case_details failed", e)
        return False


def startup_initialise():
    """
    Prepares the database for use. Call this once, explicitly, from main().

    This work used to run at module import wrapped in `except Exception: pass`, so a
    locked file or a full disk left the app running with no schema and no indexes. The
    user then met a cascade of unrelated errors instead of one clear message.

    A schema failure is fatal and propagates, because nothing in the app works without
    tables. Missing indexes or a skipped archiving pass only make the app slower, so
    those are reported and the app still starts.
    """
    init_db()          # fatal on failure — raises

    if is_remote():
        # The server prepared and checked its own database when it started.
        # A workstation only needs to know it can reach it.
        with get_db_cursor() as cursor:
            cursor.execute("SELECT 1")
        return

    # A file can be damaged in a way SQLite does not notice on an ordinary SELECT:
    # the page holding a table's rows is overwritten, the query still succeeds and
    # returns nothing, and the office is shown an empty register. quick_check reads
    # the whole file and reports that damage. It costs ~0.3 s on a 15 MB database
    # (10 000 clients, 20 000 dossiers, 50 000 check-ins), which is worth paying
    # once at startup to never open on silently truncated books.
    try:
        with get_db_cursor() as cursor:
            verdict = cursor.execute("PRAGMA quick_check").fetchone()[0]
    except Exception as e:
        log_system_error("startup integrity check could not run", e)
        raise DataUnavailable("la base de données est illisible", "integrity") from e
    if str(verdict).strip().lower() != "ok":
        log_system_error("startup integrity check FAILED",
                         Exception(str(verdict)[:400]))
        raise DataUnavailable("la base de données est endommagée", "integrity")

    for step in (ensure_indexes, run_daily_archiving_if_needed):
        try:
            step()
        except Exception as e:
            log_system_error(f"startup step {step.__name__} failed (non-fatal)", e)
            print(f"[startup] {step.__name__} failed, continuing: {e}")
