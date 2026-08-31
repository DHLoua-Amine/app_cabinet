"""
licensing.py — ties an installation to one machine.

WHAT THIS IS FOR

The application is sold per office. Without this, the dist folder is a USB stick
away from running anywhere forever: there was no activation, no key, no check.

WHAT THIS IS NOT

It is not copy protection in the absolute sense, and nothing claiming to be that
would be honest. This is a PyInstaller build; its bytecode can be extracted and a
check can be patched out by someone who wants to badly enough. What this stops is
the realistic case — a client copying the folder to a colleague's machine — by
making the copy simply refuse to activate.

HOW IT WORKS

Offline, by signature. The developer holds an Ed25519 private key that never
ships. The application carries only the public key. A licence is a short signed
text naming the machine it belongs to:

    ZARAI-LIC-1.<payload>.<signature>

The payload names the machine fingerprint, the office, and an optional expiry.
A licence for machine A verifies only on machine A, and a licence cannot be
forged without the private key. No internet is needed at any point, which
matters for an office whose connection is not dependable.

THE LINE THIS DOES NOT CROSS

An unlicensed application NEVER blocks access to records the office has already
created. A notary must always be able to open, read, print and export their own
deeds — those are legal documents, and holding them hostage over a licence
dispute would be indefensible. What an expired licence stops is the creation of
NEW records. That is enough to get a phone call the same morning, and it leaves
the office's existing archive untouched.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import json
import subprocess
import sys

# ── The developer's public key ───────────────────────────────────────────────
# Replace with the public half printed by tools/make_licence.py --init. The
# private half stays on the developer's machine and is never distributed; a
# build that shipped it would let anyone mint their own licences.
PUBLIC_KEY_B64 = "4mcDQB0-j5CbXBq1vaZoMn1fdjij4rXVcfipT8Sm6hk"

LICENCE_PREFIX = "ZARAI-LIC-1"

# Status values
ACTIVE = "active"
EXPIRED = "expired"
INVALID = "invalid"
WRONG_MACHINE = "wrong_machine"
UNLICENSED = "unlicensed"


# ── Machine fingerprint ──────────────────────────────────────────────────────
# Populated on first use and never invalidated: see machine_fingerprint().
_FINGERPRINT_CACHE = None

# (stat_signature, status_dict) for the licence file. A licence that is added,
# replaced or deleted changes the file's (mtime, size), so the cache reloads;
# an os.stat costs microseconds against status()'s ~1 s.
_STATUS_CACHE = None


def _machine_guid() -> str:
    """Windows' own installation id. Survives disk and hardware changes."""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             r"SOFTWARE\Microsoft\Cryptography")
        try:
            return str(winreg.QueryValueEx(key, "MachineGuid")[0])
        finally:
            winreg.CloseKey(key)
    except Exception:
        return ""


def _volume_serial() -> str:
    """The system drive's serial. Changes if the disk is replaced or reformatted."""
    try:
        out = subprocess.run(["cmd", "/c", "vol", "C:"], capture_output=True,
                             text=True, timeout=8,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for line in (out.stdout or "").splitlines():
            if "-" in line and ":" in line:
                return line.rsplit(":", 1)[-1].strip()
    except Exception:
        pass
    return ""


def machine_fingerprint() -> str:
    """
    A stable id for this machine, shown to the notary as XXXX-XXXX-XXXX.

    Built from Windows' MachineGuid and the system volume serial. Copying the
    application folder to another PC changes both, so the licence stops matching
    — which is the whole point. Replacing the system disk also changes it; that
    is a support call and a free re-issue, not a lockout, because an unlicensed
    app still opens the office's records.
    """
    global _FINGERPRINT_CACHE
    if _FINGERPRINT_CACHE is not None:
        return _FINGERPRINT_CACHE

    parts = [_machine_guid(), _volume_serial()]
    raw = "|".join(p for p in parts if p)
    if not raw:
        # Nothing identifiable — better a constant that fails closed on the
        # developer's side than a random value that changes every launch and
        # makes the notary re-activate daily.
        raw = "UNIDENTIFIED-MACHINE"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()
    # Neither the MachineGuid nor the volume serial can change while this
    # process is running — replacing the system disk requires a reboot. Reading
    # them costs ~590 ms because the serial comes from a `cmd /c vol` child
    # process, so without this cache every guarded call paid for a subprocess.
    _FINGERPRINT_CACHE = "-".join(digest[i:i + 4] for i in (0, 4, 8))
    return _FINGERPRINT_CACHE


# ── Licence text ─────────────────────────────────────────────────────────────
def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def parse_licence(text: str):
    """Splits a licence string into (payload_dict, signature). Never raises."""
    try:
        text = "".join((text or "").split())
        prefix, payload_b64, sig_b64 = text.split(".", 2)
        if prefix != LICENCE_PREFIX:
            return (None, None)
        payload = json.loads(_b64d(payload_b64).decode("utf-8"))
        return (payload, (_b64d(sig_b64), payload_b64))
    except Exception:
        return (None, None)


def verify_licence(text: str, fingerprint: str = None) -> dict:
    """
    Checks a licence and says exactly what is wrong with it.

    Returns {"status": ..., "office": ..., "expires": ..., "detail": ...}.
    """
    fingerprint = fingerprint or machine_fingerprint()
    payload, sig = parse_licence(text)
    if payload is None:
        return {"status": INVALID, "detail": "the licence text is not readable"}

    if not PUBLIC_KEY_B64:
        return {"status": INVALID,
                "detail": "this build carries no verification key"}

    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        pub = Ed25519PublicKey.from_public_bytes(_b64d(PUBLIC_KEY_B64))
        signature, payload_b64 = sig
        pub.verify(signature, payload_b64.encode("ascii"))
    except Exception:
        return {"status": INVALID,
                "detail": "the signature does not match — this licence was not "
                          "issued for this application"}

    if str(payload.get("machine", "")).strip().upper() != fingerprint.upper():
        return {"status": WRONG_MACHINE,
                "office": payload.get("office", ""),
                "detail": "this licence belongs to a different machine"}

    expires = (payload.get("expires") or "").strip()
    if expires:
        try:
            end = datetime.date.fromisoformat(expires)
            if datetime.date.today() > end:
                return {"status": EXPIRED, "office": payload.get("office", ""),
                        "expires": expires,
                        "detail": f"the licence expired on {expires}"}
        except ValueError:
            return {"status": INVALID, "detail": "unreadable expiry date"}

    return {"status": ACTIVE, "office": payload.get("office", ""),
            "expires": expires, "detail": "licence valid"}


# ── Stored state ─────────────────────────────────────────────────────────────
def _paths():
    import config
    return (config.DATA_DIR / "licence.txt", config.DATA_DIR / "install.json")


def save_licence(text: str) -> bool:
    lic_path, _ = _paths()
    try:
        lic_path.write_text((text or "").strip(), encoding="utf-8")
        return True
    except Exception:
        return False


def load_licence() -> str:
    lic_path, _ = _paths()
    try:
        if lic_path.exists():
            return lic_path.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return ""


def _first_run_date() -> datetime.date:
    """
    When this installation was first used, for the trial window.

    Stored beside the data. Deleting it restarts the trial, which is a hole a
    determined person could use — and an acceptable one: the trial exists so a
    notary can evaluate the software, not as the paid protection. The signature
    check is what protects the sale.
    """
    _, inst = _paths()
    today = datetime.date.today()
    try:
        if inst.exists():
            data = json.loads(inst.read_text(encoding="utf-8"))
            return datetime.date.fromisoformat(data["first_run"])
    except Exception:
        pass
    try:
        inst.write_text(json.dumps({"first_run": today.isoformat()}),
                        encoding="utf-8")
    except Exception:
        pass
    return today


def _licence_signature():
    """(mtime, size) of the licence file, or None when there is no licence."""
    try:
        lic_path, _ = _paths()
        st = lic_path.stat()
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def _remember(sig, res):
    """Stores a status result against the licence file's stat signature."""
    global _STATUS_CACHE
    _STATUS_CACHE = (sig, dict(res))
    return res


def status() -> dict:
    """
    What this installation is entitled to right now.

    Returns the status dict. Every fresh installation without a valid activation key
    is UNLICENSED. Only a cryptographically signed key matching this machine ID sets ACTIVE.
    """
    global _STATUS_CACHE
    sig = _licence_signature()
    if _STATUS_CACHE is not None and _STATUS_CACHE[0] == sig:
        return dict(_STATUS_CACHE[1])

    try:
        text = load_licence()
        if text:
            res = verify_licence(text)
            res.setdefault("machine", machine_fingerprint())
            res["days_left"] = 0
            return _remember(sig, res)
        return _remember(sig, {
            "status": UNLICENSED, "days_left": 0, "office": "",
            "machine": machine_fingerprint(),
            "detail": "this installation is not licensed — an activation key is required"})
    except Exception as e:
        return _remember(sig, {
            "status": UNLICENSED, "days_left": 0, "office": "",
            "machine": machine_fingerprint(),
            "detail": f"licence check failed: {e}"})


def is_licensed() -> bool:
    return status().get("status") == ACTIVE


def may_create_records() -> bool:
    """
    Whether NEW records may be created.

    Reading, printing and exporting are never gated on this — see the module
    docstring. Only creation stops.
    """
    return is_licensed()


class LicenceRequired(PermissionError):
    """
    Raised when NEW work is attempted on an unlicensed installation.

    Subclasses PermissionError deliberately: the screens that already handle a
    role refusal handle this the same way, and an unhandled one still surfaces
    as a refusal rather than a crash.
    """

    def __init__(self, detail: str = ""):
        self.detail = detail
        super().__init__(detail or "this installation is not licensed")


def require_licence(fn):
    """
    Guards the creation of new records.

    Applied only to functions that CREATE. Reading, printing, exporting and
    correcting existing records are never guarded — an office must always be
    able to reach the deeds it has already drawn up, licence or no licence.
    """
    import functools

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        st = status()
        if st.get("status") != ACTIVE:
            raise LicenceRequired(st.get("detail") or "unlicensed")
        return fn(*args, **kwargs)

    wrapper.__wrapped__ = fn
    return wrapper


def activate(text: str) -> tuple:
    """Validates then stores a licence. Returns (ok, message)."""
    res = verify_licence(text)
    if res.get("status") != ACTIVE:
        return (False, res.get("detail") or "licence refused")
    if not save_licence(text):
        return (False, "the licence could not be saved to disk")
    return (True, res.get("office") or "activated")
