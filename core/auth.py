"""
auth.py — real authentication for Cabinet Notarial Zarai.

What this replaces
------------------
The previous version declared two roles in its docstring and enforced neither.
`session_state.auth_logged_in` was initialised to False and no line anywhere in
the application ever set it to True; `is_patron()` and `is_receptionniste()` had
zero call sites. Both accounts shipped with the same password, `your-password-here`,
written in clear text in the source file, and any password the notary chose was
written back to config.json in clear text next to it.

What this does instead
----------------------
* Accounts live in the shared database, not in the source file and not in a
  per-machine JSON file, so the notaire build and the secrétaire build see the
  same accounts and a password change on one is immediately true on the other.
* Passwords are stored as PBKDF2-HMAC-SHA256 with a per-user random salt. The
  clear text is never written anywhere, which also means it cannot be recovered
  — only reset, which is why the recovery paths below exist.
* Both roles have a real recovery route: the notary holds a recovery code issued
  at setup, and the secretary's password can be reset by the notary. Neither
  path can end in "the office is locked out of its own records".

Sessions are held in `permissions.session`; this module only decides whether a
credential is genuine.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import secrets
import string
from pathlib import Path

import permissions
from permissions import ROLE_ADMIN, ROLE_SECRETARY

# ── Password hashing ─────────────────────────────────────────────────────────
# PBKDF2 is in the standard library, so this adds no dependency to an offline
# desktop install. 260,000 iterations costs a fraction of a second on the office
# hardware, which is unnoticeable on a login and expensive in bulk.
_ALGO = "pbkdf2_sha256"
_ITERATIONS = 260_000
_SALT_BYTES = 16


def hash_password(password: str, salt: bytes | None = None,
                  iterations: int = _ITERATIONS) -> str:
    """Returns a self-describing hash string: algo$iterations$salt$digest."""
    if salt is None:
        salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{_ALGO}${iterations}${salt.hex()}${digest.hex()}"


def verify_hash(password: str, stored: str) -> bool:
    """Constant-time check of a password against a stored hash string."""
    if not stored or not password:
        return False
    try:
        algo, iters, salt_hex, digest_hex = stored.split("$")
        if algo != _ALGO:
            return False
        expected = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iters))
        # compare_digest, not ==, so a wrong password cannot be narrowed down by
        # timing how long the comparison took.
        return hmac.compare_digest(expected.hex(), digest_hex)
    except (ValueError, AttributeError):
        return False


# ── Recovery codes ───────────────────────────────────────────────────────────
# Shown to the notary once, at setup, and stored only as a hash. Grouped in
# blocks because it will be written down on paper and typed back months later.
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no I/O/0/1 — misread on paper
_CODE_BLOCKS = 4
_CODE_BLOCK_LEN = 5


def generate_recovery_code() -> str:
    blocks = ["".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_BLOCK_LEN))
              for _ in range(_CODE_BLOCKS)]
    return "-".join(blocks)


def _normalise_code(code: str) -> str:
    """Ignores dashes, spaces and case, so the paper copy is forgiving to type."""
    return "".join(ch for ch in (code or "").upper() if ch in _CODE_ALPHABET)


# ── User store ───────────────────────────────────────────────────────────────
_USERS_TABLE = "app_users"


def _cursor(commit: bool = False):
    import reception
    return reception.get_db_cursor(commit=commit)


def init_user_store() -> None:
    """Creates the accounts table. Safe to call repeatedly."""
    with _cursor(commit=True) as c:
        c.execute(f"""
            CREATE TABLE IF NOT EXISTS {_USERS_TABLE} (
                username        TEXT PRIMARY KEY,
                role            TEXT NOT NULL,
                display_name    TEXT DEFAULT '',
                password_hash   TEXT NOT NULL,
                recovery_hash   TEXT DEFAULT '',
                must_change     INTEGER DEFAULT 0,
                failed_attempts INTEGER DEFAULT 0,
                created_at      TEXT,
                updated_at      TEXT
            )
        """)


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_user(username: str) -> dict | None:
    import reception
    if reception.is_remote():
        u = str(username).strip().lower()
        if u in (DEFAULT_ADMIN, DEFAULT_SECRETARY):
            r = ROLE_ADMIN if u == DEFAULT_ADMIN else ROLE_SECRETARY
            return {"username": u, "role": r, "display_name": "", "must_change": 0}
        return None
    init_user_store()
    with _cursor() as c:
        row = c.execute(
            f"SELECT * FROM {_USERS_TABLE} WHERE username=?",
            (str(username).strip().lower(),)).fetchone()
    return dict(row) if row else None


def list_users() -> list:
    import reception
    if reception.is_remote():
        import office_profile
        prof = office_profile.load()
        notary_disp = office_profile.display_name(prof) or "عدل الإشهاد"
        return [
            {"username": DEFAULT_ADMIN, "role": permissions.ROLE_ADMIN, "display_name": notary_disp},
            {"username": DEFAULT_SECRETARY, "role": permissions.ROLE_SECRETARY, "display_name": "الكاتبة / Secrétaire"}
        ]
    init_user_store()
    with _cursor() as c:
        rows = c.execute(
            f"SELECT username, role, display_name, must_change, updated_at "
            f"FROM {_USERS_TABLE} ORDER BY role DESC, username").fetchall()
    return [dict(r) for r in rows]


def user_count() -> int:
    import reception
    if reception.is_remote():
        return 2
    init_user_store()
    with _cursor() as c:
        return c.execute(f"SELECT COUNT(*) AS n FROM {_USERS_TABLE}").fetchone()["n"]


def create_user(username: str, password: str, role: str, display_name: str = "",
                recovery_code=None, must_change: bool = False) -> bool:
    """Creates an account. Returns False if the username is already taken."""
    init_user_store()
    uname = str(username).strip().lower()
    if not uname or role not in permissions.GRANTS:
        return False
    if get_user(uname) is not None:
        return False
    with _cursor(commit=True) as c:
        c.execute(
            f"INSERT INTO {_USERS_TABLE} "
            f"(username, role, display_name, password_hash, recovery_hash, "
            f" must_change, failed_attempts, created_at, updated_at) "
            f"VALUES (?,?,?,?,?,?,0,?,?)",
            (uname, role, display_name, hash_password(password),
             hash_password(_normalise_code(recovery_code)) if recovery_code else "",
             1 if must_change else 0, _now(), _now()))
    return True


def set_password(username: str, new_password: str) -> bool:
    """Unconditional password write. Callers are responsible for authorising it."""
    init_user_store()
    uname = str(username).strip().lower()
    with _cursor(commit=True) as c:
        c.execute(
            f"UPDATE {_USERS_TABLE} SET password_hash=?, must_change=0, "
            f"failed_attempts=0, updated_at=? WHERE username=?",
            (hash_password(new_password), _now(), uname))
        return c.rowcount > 0


def change_own_password(username: str, current_password: str, new_password: str) -> bool:
    """Changes a password only when the current one is presented correctly."""
    user = get_user(username)
    if user is None or not verify_hash(current_password, user["password_hash"]):
        return False
    return set_password(username, new_password)


# ── Login ────────────────────────────────────────────────────────────────────
def _remote_authenticate(username: str, password: str):
    """
    Signs in against the office server rather than pulling app_users across it.

    On a workstation the accounts table is not reachable — deliberately, so that
    password hashes never travel — so the verification happens where the file
    is. Returns a row-shaped dict, or None.
    """
    import reception
    reception.set_remote_identity(username, password)
    try:
        conn = reception.get_connection()
        res = conn.login(username, password)
    except Exception as e:
        reception.clear_remote_identity()
        from system_guardian import log_system_error
        log_system_error("office server refused the sign-in", e)
        return None
    if not res or not res.get("ok"):
        reception.clear_remote_identity()
        return None
    return {"username": str(username).strip().lower(),
            "role": res.get("role") or "",
            "display_name": res.get("display_name") or "",
            "must_change": 0}


def authenticate(username: str, password: str):
    """Returns the user row on success, None on failure. Does not open a session."""
    try:
        import reception
        if reception.is_remote():
            return _remote_authenticate(username, password)
    except Exception:
        # (c) Safe: falls through to the local path, which fails closed if the
        # accounts table genuinely cannot be read.
        pass
    user = get_user(username)
    if user is None:
        # Spend the same work as a real check so a missing username and a wrong
        # password take the same time and cannot be told apart.
        hash_password(password or "")
        return None
    if not verify_hash(password, user["password_hash"]):
        with _cursor(commit=True) as c:
            c.execute(f"UPDATE {_USERS_TABLE} SET failed_attempts=failed_attempts+1 "
                      f"WHERE username=?", (user["username"],))
        return None
    with _cursor(commit=True) as c:
        c.execute(f"UPDATE {_USERS_TABLE} SET failed_attempts=0 WHERE username=?",
                  (user["username"],))
    return user


def login(username: str, password: str) -> bool:
    """Authenticates and, on success, opens the process-wide session."""
    user = authenticate(username, password)
    if user is None:
        return False
    permissions.session.sign_in(user["username"], user["role"], user["display_name"])
    return True


def logout() -> None:
    permissions.session.sign_out()


def is_logged_in() -> bool:
    return permissions.session.logged_in


def get_role():
    return permissions.session.role


def is_admin() -> bool:
    return permissions.session.role == ROLE_ADMIN


def is_secretary() -> bool:
    return permissions.session.role == ROLE_SECRETARY


# Kept so any older reference keeps meaning what it used to mean.
def is_patron() -> bool:
    return is_admin()


def is_receptionniste() -> bool:
    return is_secretary()


# ── Recovery ─────────────────────────────────────────────────────────────────
def reset_password_with_recovery_code(username: str, code: str, new_password: str):
    """
    The notary's own way back in when the password is forgotten.

    On success the used code is replaced by a freshly generated one, which is
    returned so it can be shown once and written down again. A code that has
    been used is therefore dead, and there is always exactly one live code.
    Returns (ok, new_code).
    """
    user = get_user(username)
    if user is None:
        return False, None
    stored = user.get("recovery_hash") or ""
    if not stored or not verify_hash(_normalise_code(code), stored):
        return False, None

    fresh = generate_recovery_code()
    with _cursor(commit=True) as c:
        c.execute(
            f"UPDATE {_USERS_TABLE} SET password_hash=?, recovery_hash=?, "
            f"must_change=0, failed_attempts=0, updated_at=? WHERE username=?",
            (hash_password(new_password), hash_password(_normalise_code(fresh)),
             _now(), user["username"]))
    return True, fresh


def issue_recovery_code(username: str):
    """Generates and stores a new recovery code, returning the clear text once."""
    if get_user(username) is None:
        return None
    code = generate_recovery_code()
    with _cursor(commit=True) as c:
        c.execute(f"UPDATE {_USERS_TABLE} SET recovery_hash=?, updated_at=? "
                  f"WHERE username=?",
                  (hash_password(_normalise_code(code)), _now(),
                   str(username).strip().lower()))
    return code


def admin_reset_password(target_username: str, new_password: str) -> bool:
    """
    The secretary's way back in: the notary resets it for her.

    Guarded by the capability rather than by the caller being polite about it, so
    this refuses even if some future screen calls it without checking first.
    """
    permissions.check(permissions.Cap.MANAGE_USERS)
    target = get_user(target_username)
    if target is None:
        return False
    # The notary resetting the notary's own password is what the recovery code is
    # for; this path exists for the accounts under the notary's authority.
    if target["role"] == ROLE_ADMIN and target["username"] != permissions.session.username:
        return False
    return set_password(target_username, new_password)


# ── First run ────────────────────────────────────────────────────────────────
DEFAULT_ADMIN = "patron"
DEFAULT_SECRETARY = "secretaire"


def bootstrap(admin_password=None, secretary_password=None) -> dict:
    """
    Creates the two accounts on a database that has none yet.

    Returns the clear-text credentials exactly once, for the setup screen to show
    and the notary to write down. Nothing here is persisted in clear text.
    """
    init_user_store()
    if user_count() > 0:
        return {}

    admin_pw = admin_password or _temp_password()
    sec_pw = secretary_password or _temp_password()
    code = generate_recovery_code()

    # A failed create_user would otherwise leave the office with credentials on
    # screen that do not open anything.
    if not create_user(DEFAULT_ADMIN, admin_pw, ROLE_ADMIN,
                       "عدل الإشهاد", recovery_code=code,
                       must_change=admin_password is None):
        raise RuntimeError("could not create the administrator account")
    if not create_user(DEFAULT_SECRETARY, sec_pw, ROLE_SECRETARY,
                       "الاستقبال / الكاتبة",
                       must_change=secretary_password is None):
        raise RuntimeError("could not create the secretary account")
    return {
        "admin_username": DEFAULT_ADMIN,
        "admin_password": admin_pw,
        "secretary_username": DEFAULT_SECRETARY,
        "secretary_password": sec_pw,
        "recovery_code": code,
    }


def _temp_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def migrate_legacy_passwords() -> list:
    """
    Carries the office's existing passwords over, then destroys the clear text.

    The old build kept chosen passwords in config.json under `custom_passwords`,
    in clear text. Whatever the notary and secretary are currently typing keeps
    working after this upgrade; the clear-text copy does not survive it.
    """
    init_user_store()
    conf = load_config()
    legacy = conf.get("custom_passwords") or {}
    moved = []
    mapping = {"patron": DEFAULT_ADMIN, "secretaire": DEFAULT_SECRETARY}
    for old_name, clear in list(legacy.items()):
        uname = mapping.get(str(old_name).strip().lower())
        if not uname or not clear:
            continue
        if get_user(uname) is not None:
            set_password(uname, clear)
            moved.append(uname)
    if legacy:
        conf["custom_passwords"] = {}
        _write_config(conf)
    return moved


# ── config.json — now only language, never credentials ───────────────────────
CONFIG_FILE = Path(__file__).resolve().parent.parent / "config.json"


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError) as read_err:
            # (b) A corrupt config silently resets the office to Arabic; without
            # this, a notary whose language keeps reverting has nothing to look at.
            print(f"[AUTH] could not read {CONFIG_FILE}: {read_err}", file=sys.stderr)
    return {"lang": "ar", "custom_passwords": {}}


def _write_config(conf: dict) -> None:
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(conf, f, indent=4, ensure_ascii=False)
    except OSError as write_err:
        # (b) The language choice is not kept and nothing says so.
        print(f"[AUTH] could not write {CONFIG_FILE}: {write_err}", file=sys.stderr)


def save_config(lang: str, passwords=None) -> None:
    """`passwords` is accepted and ignored — credentials no longer live here."""
    conf = load_config()
    conf["lang"] = lang
    conf["custom_passwords"] = {}
    _write_config(conf)


class LocalSession:
    """Kept for the language preference the pages read; auth state moved out."""

    def __init__(self):
        conf = load_config()
        self.lang = conf.get("lang", "ar")

    # The pages still reach for these; they now mirror the real session.
    @property
    def auth_logged_in(self) -> bool:
        return permissions.session.logged_in

    @property
    def auth_role(self):
        return permissions.session.role

    @property
    def auth_display(self) -> str:
        return permissions.session.display

    @property
    def auth_username(self):
        return permissions.session.username


session_state = LocalSession()


def update_language(lang: str) -> None:
    session_state.lang = lang
    save_config(lang)
