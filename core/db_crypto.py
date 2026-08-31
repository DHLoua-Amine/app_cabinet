"""
db_crypto.py — the office link, encrypted.

WHY

An interception test on the previous protocol recovered, in plain text, from a
relay sitting between a workstation and the server: the access token, a client's
CIN number, and a client's name. Anyone able to watch the office network — a
laptop on the same Wi-Fi, a mirrored switch port — could read every deed, every
amount and every identity card number the office handled, and then reuse the
token themselves.

WHAT THIS DOES

Every frame after the opening handshake is sealed with AES-256-GCM, which gives
confidentiality and integrity together: a watcher learns nothing, and a tampered
frame is rejected rather than acted upon.

THE KEY

Derived with HKDF-SHA256 from the office's shared token AND a random session id
the server issues per connection:

    key = HKDF(token, salt=session_id, info="zarai-db-v1")

Two consequences worth stating. First, the token itself never travels — the
client proves it knows the token by producing a frame the server can decrypt, so
there is nothing on the wire to steal. Second, because the session id is fresh
each connection, the key is fresh each connection, so frames captured today
cannot be replayed against tomorrow's session. Within a session, a frame counter
in the authenticated data stops replay and reordering.

WHAT THIS IS NOT

Not TLS, and not a public-key system. Both sides must already share the token,
which is exactly the situation here: the notary types it into each machine once.
There is no certificate to manage, which for a two-person office is the right
trade — a PKI nobody maintains protects nothing.
"""

from __future__ import annotations

import json
import os
import socket

NONCE_BYTES = 12
SESSION_ID_BYTES = 16
KEY_BYTES = 32
_MAX_FRAME = 64 * 1024 * 1024
_HKDF_INFO = b"zarai-db-v1"


class CryptoError(Exception):
    """A frame could not be decrypted: wrong token, tampering, or replay."""


def derive_key(token: str, session_id: bytes) -> bytes:
    """The per-connection key. Same inputs on both sides, never transmitted."""
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
    return HKDF(algorithm=hashes.SHA256(), length=KEY_BYTES,
                salt=session_id, info=_HKDF_INFO).derive(
                    (token or "").encode("utf-8"))


def _aead(key: bytes):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    return AESGCM(key)


# ── Plaintext framing, used only for the handshake ───────────────────────────
# The handshake carries no secret: a protocol number and a random session id.
# Everything after it is sealed.

def send_plain(sock: socket.socket, obj: dict) -> None:
    payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    sock.sendall(len(payload).to_bytes(8, "big") + payload)


def recv_plain(sock: socket.socket):
    header = _recv_exactly(sock, 8)
    if header is None:
        return None
    size = int.from_bytes(header, "big")
    if size <= 0 or size > _MAX_FRAME:
        raise ValueError(f"refusing a {size}-byte frame")
    body = _recv_exactly(sock, size)
    if body is None:
        return None
    return json.loads(body.decode("utf-8"))


def _recv_exactly(sock: socket.socket, n: int):
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(min(65536, n - len(buf)))
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)


# ── Sealed framing ───────────────────────────────────────────────────────────
def send_sealed(sock: socket.socket, key: bytes, seq: int, obj: dict) -> None:
    """
    [8-byte length][12-byte nonce][ciphertext+tag]

    The frame counter travels as authenticated data rather than as content, so a
    frame replayed out of order fails to decrypt instead of being executed.
    """
    plaintext = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    nonce = os.urandom(NONCE_BYTES)
    ct = _aead(key).encrypt(nonce, plaintext, seq.to_bytes(8, "big"))
    body = nonce + ct
    sock.sendall(len(body).to_bytes(8, "big") + body)


def recv_sealed(sock: socket.socket, key: bytes, seq: int):
    header = _recv_exactly(sock, 8)
    if header is None:
        return None
    size = int.from_bytes(header, "big")
    if size <= NONCE_BYTES or size > _MAX_FRAME:
        raise CryptoError(f"refusing a {size}-byte frame")
    body = _recv_exactly(sock, size)
    if body is None:
        return None
    nonce, ct = body[:NONCE_BYTES], body[NONCE_BYTES:]
    try:
        plaintext = _aead(key).decrypt(nonce, ct, seq.to_bytes(8, "big"))
    except Exception as e:
        # Wrong token, a tampered frame, or a replayed one. They are
        # indistinguishable here, and deliberately reported as one thing: a
        # detailed reason would help someone probing the port.
        raise CryptoError("the frame could not be decrypted") from e
    return json.loads(plaintext.decode("utf-8"))


def new_session_id() -> bytes:
    return os.urandom(SESSION_ID_BYTES)
