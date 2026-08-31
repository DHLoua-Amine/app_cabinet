"""
make_licence.py — the developer's licence issuer. NEVER SHIP THIS.

This holds the private key. A build that included it would let any client mint
their own licences, which is the same as having no licensing at all.

    Keep this file and zarai_licence_key.pem outside the dist folder.
    Back the key up. Losing it means you can never issue a licence again for
    installations that already carry the matching public key.

FIRST TIME
    python tools/make_licence.py --init
        Creates the private key and prints the public key. Paste that public key
        into core/licensing.py PUBLIC_KEY_B64, then build. Do this ONCE: every
        licence you ever issue is verified against that public key.

ISSUING A LICENCE
    The client installs, opens Paramètres → Licence, and reads you their
    Machine ID. Then:

    python tools/make_licence.py --machine A1B2-C3D4-E5F6 \
                                --office "Maitre Ben Salah, Sousse"

    Optional --expires 2027-12-31 for a subscription; omit for perpetual.
    Send them the printed ZARAI-LIC-1... line. They paste it and press Activer.
"""

import argparse
import base64
import datetime
import json
import sys
from pathlib import Path

KEY_PATH = Path(__file__).resolve().parent / "zarai_licence_key.pem"
LICENCE_PREFIX = "ZARAI-LIC-1"


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def init_key(force: bool = False) -> int:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    if KEY_PATH.exists() and not force:
        print(f"A key already exists at {KEY_PATH}")
        print("Refusing to overwrite it: every licence you have already issued")
        print("was signed with it. Use --force only if you truly mean to start")
        print("over and re-issue every client's licence.")
        return 1

    key = Ed25519PrivateKey.generate()
    KEY_PATH.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()))
    pub = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)

    print(f"Private key written to {KEY_PATH}")
    print("  -> BACK THIS UP. Keep it off the internet and out of the build.\n")
    print("Paste this into core/licensing.py:\n")
    print(f'PUBLIC_KEY_B64 = "{_b64e(pub)}"\n')
    return 0


def load_key():
    from cryptography.hazmat.primitives import serialization
    if not KEY_PATH.exists():
        print(f"No private key at {KEY_PATH}. Run --init first.")
        sys.exit(1)
    return serialization.load_pem_private_key(KEY_PATH.read_bytes(), password=None)


def issue(machine: str, office: str, expires: str = "") -> int:
    machine = (machine or "").strip().upper()
    if not machine:
        print("A machine id is required (--machine).")
        return 1
    if expires:
        try:
            datetime.date.fromisoformat(expires)
        except ValueError:
            print(f"--expires must be YYYY-MM-DD, got {expires!r}")
            return 1

    key = load_key()
    payload = {"machine": machine,
               "office": (office or "").strip(),
               "issued": datetime.date.today().isoformat(),
               "expires": expires or ""}
    payload_b64 = _b64e(json.dumps(payload, separators=(",", ":"),
                                   sort_keys=True, ensure_ascii=False).encode("utf-8"))
    sig = key.sign(payload_b64.encode("ascii"))
    licence = f"{LICENCE_PREFIX}.{payload_b64}.{_b64e(sig)}"

    print("\n" + "=" * 72)
    print(f"  Office  : {payload['office'] or '(unnamed)'}")
    print(f"  Machine : {machine}")
    print(f"  Expires : {expires or 'never'}")
    print("=" * 72)
    print("\nSend the client this single line:\n")
    print(licence)
    print()

    log = KEY_PATH.with_name("issued_licences.log")
    try:
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M}\t{machine}\t"
                    f"{payload['office']}\t{expires or 'perpetual'}\n")
        print(f"(recorded in {log.name} — your record of who has what)")
    except Exception as e:
        print(f"(could not write the issue log: {e})")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Issue Cabinet Notarial licences.")
    ap.add_argument("--init", action="store_true", help="create the signing key")
    ap.add_argument("--force", action="store_true", help="overwrite an existing key")
    ap.add_argument("--machine", help="the client's Machine ID")
    ap.add_argument("--office", default="", help="office name, for your records")
    ap.add_argument("--expires", default="", help="YYYY-MM-DD, or omit for perpetual")
    args = ap.parse_args()

    if args.init:
        return init_key(args.force)
    if args.machine:
        return issue(args.machine, args.office, args.expires)
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
