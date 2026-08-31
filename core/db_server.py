"""
db_server.py — the office's single database, served over the local network.

THE PROBLEM THIS SOLVES

Until now every install kept its own database under %LOCALAPPDATA%. Two machines
meant two unrelated offices: the secretary registered a client, it saved to HER
database, and the notary's app never saw it and never would. The role separation
was written as though both roles shared one database, but nothing made that true.

The obvious shortcut — point both installs at the same file on a Windows share —
is the one thing SQLite explicitly warns against. WAL mode needs shared memory
(the -shm file), which does not work across SMB, and two machines writing to one
file over a network is a corruption risk, not a theoretical concern.

THE SHAPE OF THE FIX

One machine in the office runs this server. It is the only process that ever
opens the database file, and it opens it on its OWN local disk, where WAL is
exactly the supported case. Every other machine talks to it over TCP.

    secretary's laptop ─┐
                        ├──TCP──►  db_server  ──►  reception.db  (local disk)
    notary's laptop ────┘

Each client socket gets its own SQLite connection on the server, so a
transaction opened by the secretary is hers alone and SQLite arbitrates between
them the way it is designed to. Nothing in reception.py changes: the client side
presents the same cursor API those ~60 functions already use.

WHAT THIS IS NOT

This is a database transport, not an application server. It executes the SQL the
client sends. A workstation on the office LAN with the shared token can therefore
run any query — role separation is still enforced in the client process, as it
was before. Moving the capability checks to this side is the next step, and the
reason this server exists at all: it is the place where that becomes possible.
Until then, treat the token as what it is — access to the office's data.
"""

from __future__ import annotations

import base64
import json
import socket
import sqlite3
import threading
import traceback

from db_crypto import (CryptoError, derive_key, new_session_id, recv_plain,
                       recv_sealed, send_plain, send_sealed)

PROTOCOL_VERSION = 2
DEFAULT_PORT = 8765
_MAX_FRAME = 64 * 1024 * 1024          # a face embedding blob is ~1 KB; 64 MB is generous


# ── Wire encoding ────────────────────────────────────────────────────────────
# JSON cannot carry bytes, and the clients table stores face embeddings as BLOBs.
# Anything that is not JSON-native travels base64-tagged and comes back as bytes.

def encode_value(v):
    if isinstance(v, (bytes, bytearray, memoryview)):
        return {"__b64__": base64.b64encode(bytes(v)).decode("ascii")}
    return v


def decode_value(v):
    if isinstance(v, dict) and "__b64__" in v:
        return base64.b64decode(v["__b64__"])
    return v


def encode_params(params):
    if params is None:
        return None
    if isinstance(params, dict):
        return {k: encode_value(x) for k, x in params.items()}
    return [encode_value(x) for x in params]


def decode_params(params):
    if params is None:
        return ()
    if isinstance(params, dict):
        return {k: decode_value(x) for k, x in params.items()}
    return tuple(decode_value(x) for x in params)


def send_frame(sock: socket.socket, obj: dict) -> None:
    """
    Length-prefixed JSON, IN THE CLEAR.

    Used only for the opening handshake, which carries no secret. Every frame
    after it goes through db_crypto.send_sealed. Do not use this for anything
    that must not be read off the wire.
    """
    payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    sock.sendall(len(payload).to_bytes(8, "big") + payload)


def recv_frame(sock: socket.socket):
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


# ── Statement classification ─────────────────────────────────────────────────
# The schema belongs to the machine that holds the file. A workstation asking to
# CREATE, ALTER or DROP anything is either confused or hostile: an audit found
# that any machine holding the office token could DROP TABLE and destroy the
# register. Reads and row-level writes are the whole of a workstation's job.
#
# ATTACH is included because it would let a client mount a second database file
# from the server's disk and copy the office's records out of it.
_DDL_KEYWORDS = (
    "create", "drop", "alter", "attach", "detach", "vacuum", "reindex",
    "truncate", "replace into sqlite_", "analyze",
)


def is_ddl(sql: str) -> bool:
    """
    True for a statement that changes the schema rather than the data.

    Deliberately conservative and keyword-based: this decides what a remote
    machine may run, so anything ambiguous is treated as schema.
    """
    text = (sql or "").lstrip()
    # strip leading comments so "/* x */ DROP TABLE" is still seen as DDL
    while True:
        if text.startswith("--"):
            nl = text.find("\n")
            if nl == -1:
                return False
            text = text[nl + 1:].lstrip()
            continue
        if text.startswith("/*"):
            end = text.find("*/")
            if end == -1:
                return False
            text = text[end + 2:].lstrip()
            continue
        break
    low = text.lower()
    if low.startswith("pragma"):
        # Read-only pragmas are how the app checks integrity and column lists.
        # A pragma that ASSIGNS (has "=") changes how the database behaves and
        # is the server's business alone.
        return "=" in low.split("pragma", 1)[1]
    return any(low.startswith(k) for k in _DDL_KEYWORDS)


# ── Limits ───────────────────────────────────────────────────────────────────
# A notarial office runs two or three machines. Each opens a connection per
# working thread — the window, the camera service, an export — so the real
# ceiling is a couple of dozen. An audit opened 120 sockets and the server took
# all of them, each with its own thread and SQLite connection; a loop on any LAN
# machine could have exhausted the server that way.
MAX_CLIENTS = 24
MAX_CLIENTS_PER_IP = 8

# Repeated failures from one address, and how long that address is then refused.
AUTH_FAIL_THRESHOLD = 10
AUTH_FAIL_WINDOW_S = 300.0
AUTH_BLOCK_S = 300.0


def is_local_peer(ip: str) -> bool:
    """
    True for an address on a private network or the machine itself.

    The office server has no business answering a public address. Even bound to
    one interface this is worth checking: a machine can be moved onto a hotspot
    or a VPN without anyone thinking about the database it is serving.
    """
    try:
        import ipaddress
        a = ipaddress.ip_address(str(ip))
    except Exception:
        return False
    if a.is_loopback or a.is_link_local:
        return True
    # ipaddress.is_private is too broad for this question: it also covers the
    # documentation and benchmarking ranges (192.0.2.0/24, 198.51.100.0/24,
    # 203.0.113.0/24, 198.18.0.0/15), which are not office networks. Only the
    # three RFC 1918 blocks are.
    for block in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"):
        if a in ipaddress.ip_network(block):
            return True
    return False


def detect_lan_address() -> str:
    """
    The address other machines in the office would use to reach this one.

    Asks the routing table rather than resolving the hostname, which on Windows
    frequently answers with a virtual adapter (VirtualBox, WSL, a VPN) that no
    workstation can reach.
    """
    import socket as _s
    try:
        probe = _s.socket(_s.AF_INET, _s.SOCK_DGRAM)
        try:
            probe.connect(("10.255.255.255", 1))
            ip = probe.getsockname()[0]
        finally:
            probe.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    try:
        for info in _s.getaddrinfo(_s.gethostname(), None, _s.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                return ip
    except Exception:
        pass
    return ""


# ── Who may touch what ───────────────────────────────────────────────────────
# An audit connected with the office token and ran
#     SELECT employee_name, amount FROM salaries
# and got the payroll back. Role separation lived entirely in the client process,
# so anyone holding the token — which the secretary needs in order to work at all
# — could read every figure in the office by talking to the port directly.
#
# The server now authenticates the PERSON, not just the machine, and checks each
# statement against the tables it touches. Two consequences:
#
#   * app_users is unreachable over the network at any role. Signing in is an
#     operation the server performs against its own database; password hashes no
#     longer travel at all.
#   * A capability revoked in permissions.GRANTS is now revoked in fact, not
#     merely hidden behind a button that is not drawn.
#
# Column-level rules — the secretary may record one dossier's payment but not see
# turnover across all of them — remain in reception.redact() on the client. This
# is table-level, and is the boundary that matters for the payroll.
_PROTECTED_TABLES = {
    "salaries":     {"read": "view_expenses", "write": "manage_expenses"},
    "expenses":     {"read": "view_expenses", "write": "manage_expenses"},
    # The corrections log carries before/after money values.
    "record_edits": {"read": "view_finance", "write": None},
    # Never, for anyone: signing in is an op, not a query.
    "app_users":    {"read": "__never__", "write": "__never__"},
}

_TABLE_RE = None


def _table_pattern():
    global _TABLE_RE
    if _TABLE_RE is None:
        import re
        # Every position where SQLite names a table. Scans the whole statement,
        # so a table hidden inside a subquery is found too.
        _TABLE_RE = re.compile(
            r"\b(?:from|join|into|update|table)\s+[\"'`\[]?([A-Za-z_][A-Za-z0-9_]*)",
            re.IGNORECASE)
    return _TABLE_RE


def tables_touched(sql: str) -> set:
    """Every table named anywhere in the statement, lowercased."""
    return {m.lower() for m in _table_pattern().findall(sql or "")}


def is_write(sql: str) -> bool:
    head = (sql or "").lstrip().lower()
    return head.startswith(("insert", "update", "delete", "replace"))


def authorise(sql: str, capabilities) -> tuple:
    """
    (allowed, reason). `capabilities` is the signed-in role's set, or None when
    no one has signed in on this connection.

    Statements touching no protected table are allowed on the token alone: that
    keeps the Paramètres connection test and the startup check working before
    anyone has typed a password.
    """
    touched = tables_touched(sql) & set(_PROTECTED_TABLES)
    if not touched:
        return (True, "")
    writing = is_write(sql)
    for name in sorted(touched):
        needed = _PROTECTED_TABLES[name]["write" if writing else "read"]
        if needed is None:
            continue
        if needed == "__never__":
            return (False, f"'{name}' is not accessible over the network")
        if capabilities is None:
            return (False, f"'{name}' requires a signed-in user")
        if needed not in capabilities:
            return (False, f"'{name}' requires the '{needed}' permission")
    return (True, "")




# ── Who wrote the corrections log ────────────────────────────────────────────
# The log said who changed a figure, and it believed the workstation. The name
# came from permissions.session.username, evaluated in the CLIENT process, and
# travelled as an ordinary INSERT parameter — so a machine talking to the port
# could sign a correction with any name, or none, and the log recorded it as
# fact. An audit trail that the audited party writes is not an audit trail.
#
# Since the server authenticates the person, it knows who is on this socket. It
# now writes that name itself and ignores whatever the client sent. Two further
# rules follow from the log being a log:
#
#   * the log is append-only over the network — UPDATE and DELETE are refused,
#     so a line cannot be rewritten or removed after the fact;
#   * an INSERT with no signed-in user is refused, because an unattributed
#     correction is worth less than no correction at all.
AUDIT_TABLE = "record_edits"
AUDIT_AUTHOR_COLUMN = "edited_by"

_AUDIT_INSERT_RE = None
_AUDIT_HEAD_RE = None


def _audit_res():
    global _AUDIT_INSERT_RE, _AUDIT_HEAD_RE
    if _AUDIT_INSERT_RE is None:
        import re
        _AUDIT_INSERT_RE = re.compile(
            r"insert\s+(?:or\s+\w+\s+)?into\s+[\"'`\[]?" + AUDIT_TABLE +
            r"[\"'`\]]?\s*\(([^)]*)\)", re.IGNORECASE | re.DOTALL)
        _AUDIT_HEAD_RE = re.compile(r"^\s*(insert|update|delete)\b", re.IGNORECASE)
    return _AUDIT_INSERT_RE, _AUDIT_HEAD_RE


def audit_author_index(sql: str):
    """
    Position of edited_by in an INSERT INTO record_edits (...) column list.

    None when the statement does not name its columns: without a column list the
    position can only be guessed from the table's declared order, and guessing
    wrong would stamp the author over somebody's data.
    """
    ins_re, _ = _audit_res()
    m = ins_re.search(sql or "")
    if not m:
        return None
    cols = [c.strip().strip('"').strip("'").strip("`").strip("[]").lower()
            for c in m.group(1).split(",")]
    if AUDIT_AUTHOR_COLUMN not in cols:
        return None
    return cols.index(AUDIT_AUTHOR_COLUMN)


def _stamp_row(params, idx, who):
    """Replaces one positional parameter with the verified name."""
    if params is None:
        return None
    if isinstance(params, dict):
        out = dict(params)
        out[AUDIT_AUTHOR_COLUMN] = who
        return out
    row = list(params)
    if idx < len(row):
        row[idx] = who
    return row


def enforce_audit_identity(msg: dict, who: str) -> tuple:
    """
    (ok, msg, reason). Returns the message to execute, with the author replaced.

    Statements that do not touch the corrections log are returned untouched.
    """
    sql = msg.get("sql") or ""
    if AUDIT_TABLE not in (sql or "").lower():
        return (True, msg, "")
    if AUDIT_TABLE not in tables_touched(sql):
        return (True, msg, "")

    _, head_re = _audit_res()
    head = head_re.match(sql)
    verb = (head.group(1).lower() if head else "")

    if verb in ("update", "delete"):
        return (False, msg,
                "the corrections log is append-only — it cannot be changed "
                "or deleted over the network")

    if verb != "insert":
        return (True, msg, "")

    if not who:
        return (False, msg,
                "writing to the corrections log requires a signed-in user")

    idx = audit_author_index(sql)
    if idx is None:
        return (False, msg,
                "an entry in the corrections log must name its columns, "
                f"including '{AUDIT_AUTHOR_COLUMN}'")

    out = dict(msg)
    if msg.get("op") == "executemany":
        out["seq"] = [_stamp_row(p, idx, who) for p in (msg.get("seq") or [])]
    else:
        out["params"] = _stamp_row(msg.get("params"), idx, who)
    return (True, out, "")


# ── The server ───────────────────────────────────────────────────────────────
class DatabaseServer:
    """
    Serves one SQLite file to the office LAN.

    Runs as a daemon thread inside the application on the machine designated as
    the server, so the office does not have to install or administer a service.
    The trade-off is stated plainly in Paramètres: that machine must stay logged
    in with the application open.
    """

    def __init__(self, db_path: str, token: str, host: str = "auto",
                 port: int = DEFAULT_PORT, on_event=None):
        self.db_path = str(db_path)
        self.token = str(token or "")
        # "auto" binds the office LAN address only. Binding 0.0.0.0 also exposed
        # the database on any hotspot or VPN the machine happened to join.
        self.requested_host = host or "auto"
        self.host = host
        self.port = int(port)
        self._sock = None
        self._thread = None
        self._running = threading.Event()
        self._clients = 0
        self._clients_lock = threading.Lock()
        self._on_event = on_event
        self._auth_failures = {}        # ip -> [timestamps]
        self._blocked_until = {}        # ip -> monotonic deadline
        self._per_ip = {}               # ip -> live connection count
        self._refused = 0               # connections turned away by a limit
        self.last_error = ""

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> bool:
        if self._running.is_set():
            return True
        bind_to = self.requested_host
        if bind_to in ("", "auto", None):
            bind_to = detect_lan_address()
            if not bind_to:
                # No usable LAN address. Refusing to fall back to 0.0.0.0 is
                # deliberate: silently listening on every interface is the thing
                # this setting exists to prevent, and a machine with no network
                # cannot serve anyone anyway.
                self.last_error = ("no local network address was found — this "
                                   "machine does not appear to be on a network")
                self._event("error", self.last_error)
                return False
        self.host = bind_to
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # SO_EXCLUSIVEADDRUSE, not SO_REUSEADDR. On Windows SO_REUSEADDR lets
            # a SECOND process bind the same address and port while the first is
            # still listening, and incoming connections may go to either — so any
            # local program could quietly stand in front of the office database.
            # Testing this port showed several listeners on one address at once.
            excl = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
            if excl is not None:
                s.setsockopt(socket.SOL_SOCKET, excl, 1)
            else:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((bind_to, self.port))
            s.listen(16)
            s.settimeout(1.0)
        except OSError as e:
            # The commonest cause is a DHCP lease that moved the machine to a
            # new address since the setting was saved. Say so, rather than
            # leaving the office to guess at "cannot bind".
            self.last_error = (f"could not listen on {bind_to}:{self.port} — "
                               f"{type(e).__name__}: {e}. If this machine's IP "
                               f"address has changed, re-save the server "
                               f"settings in Paramètres.")
            self._event("error", self.last_error)
            return False
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            self._event("error", self.last_error)
            return False
        self._sock = s
        self._running.set()
        self._thread = threading.Thread(target=self._accept_loop,
                                        name="db-server", daemon=True)
        self._thread.start()
        self._event("started", f"{self.host}:{self.port}")
        return True

    def stop(self):
        self._running.clear()
        try:
            if self._sock:
                self._sock.close()
        except Exception:
            # (c) Safe: we are shutting down and the socket may already be gone.
            pass
        if self._thread is not None:
            self._thread.join(timeout=3.0)
        self._event("stopped", "")

    @property
    def running(self) -> bool:
        return self._running.is_set()

    @property
    def client_count(self) -> int:
        with self._clients_lock:
            return self._clients

    @property
    def refused_count(self) -> int:
        with self._clients_lock:
            return self._refused

    def blocked_addresses(self) -> list:
        """Addresses currently being refused after repeated failures."""
        import time as _t
        now = _t.monotonic()
        with self._clients_lock:
            return [ip for ip, until in self._blocked_until.items() if until > now]

    def _event(self, kind, detail):
        if self._on_event:
            try:
                self._on_event(kind, detail)
            except Exception:
                # (c) Safe: a listener that raises must not take the server down.
                pass

    def _admit(self, conn, addr) -> bool:
        """
        Decides whether to talk to this peer at all, before spending a thread.

        Everything here is cheap and happens before any parsing, so a machine
        hammering the port cannot make the server do work on its behalf.
        """
        import time as _t
        ip = str(addr[0]) if addr else "?"

        def refuse(reason):
            self._refused += 1
            self._event("refused", f"{ip} ({reason})")
            try:
                conn.close()
            except Exception:
                # (c) Safe: the peer is being dropped either way.
                pass
            return False

        if not is_local_peer(ip):
            return refuse("not a local address")

        now = _t.monotonic()
        with self._clients_lock:
            until = self._blocked_until.get(ip, 0.0)
            if until > now:
                return refuse(f"blocked for another {int(until - now)}s")
            if self._clients >= MAX_CLIENTS:
                return refuse(f"server full ({MAX_CLIENTS} connections)")
            if self._per_ip.get(ip, 0) >= MAX_CLIENTS_PER_IP:
                return refuse(f"too many connections from this machine "
                              f"({MAX_CLIENTS_PER_IP})")
        return True

    def _note_auth_failure(self, addr):
        """
        Records a rejected connection, and stops answering a machine that keeps
        guessing.

        Before this, a wrong token could be tried 230 times a second, forever,
        and nothing anywhere said so. The office's own machine typing its key
        wrongly a few times is normal; ten failures inside five minutes is not,
        and is worth both a pause and a line in the system log.
        """
        import time as _t
        ip = str(addr[0]) if addr else "?"
        now = _t.monotonic()
        with self._clients_lock:
            hits = [t for t in self._auth_failures.get(ip, [])
                    if now - t < AUTH_FAIL_WINDOW_S]
            hits.append(now)
            self._auth_failures[ip] = hits
            n = len(hits)
            blocked = n >= AUTH_FAIL_THRESHOLD
            if blocked:
                self._blocked_until[ip] = now + AUTH_BLOCK_S
                self._auth_failures[ip] = []
        self._event("auth_failed", f"{ip} (attempt {n})")
        if blocked:
            self._event("blocked", f"{ip} for {int(AUTH_BLOCK_S)}s")
            try:
                from system_guardian import log_system_error
                log_system_error(
                    "office server: repeated rejected connections",
                    Exception(f"{n} failed authentications from {ip} within "
                              f"{int(AUTH_FAIL_WINDOW_S)}s — that address is "
                              f"now refused for {int(AUTH_BLOCK_S)}s"))
            except Exception:
                # (c) Safe: the event above already reached Paramètres.
                pass

    # -- accept ------------------------------------------------------------
    def _accept_loop(self):
        while self._running.is_set():
            try:
                conn, addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            except Exception:
                continue
            if not self._admit(conn, addr):
                continue
            threading.Thread(target=self._serve_client, args=(conn, addr),
                             daemon=True).start()

    # -- one client, one SQLite connection ---------------------------------
    def _serve_client(self, sock: socket.socket, addr):
        """
        Each workstation gets its own SQLite connection for the life of the
        socket. That is what makes multi-statement transactions correct: a
        BEGIN…COMMIT from one machine cannot be interleaved with another's.

        The exchange is sealed from the second frame onward. The handshake sends
        a protocol number and a random session id, neither of which is a secret;
        the key is then derived from that id and the office token on both sides.
        The token itself is never transmitted, so there is nothing on the wire
        for a listener to capture and reuse.
        """
        db = None
        authed = False
        key = None
        rx = tx = 0
        # Who is signed in ON THIS CONNECTION. None until a login op succeeds.
        caps = None
        who = ""
        ip = str(addr[0]) if addr else "?"
        with self._clients_lock:
            self._clients += 1
            self._per_ip[ip] = self._per_ip.get(ip, 0) + 1
        self._event("connect", ip)
        try:
            sock.settimeout(300.0)

            # ── handshake, in the clear ─────────────────────────────────────
            hello = recv_plain(sock)
            if not hello or hello.get("op") != "hello":
                self._event("rejected", f"{addr[0]} (no handshake)")
                return
            client_proto = hello.get("protocol")
            session_id = new_session_id()
            send_plain(sock, {"ok": True, "protocol": PROTOCOL_VERSION,
                              "session": base64.b64encode(session_id).decode("ascii")})
            if client_proto != PROTOCOL_VERSION:
                # Said plainly, because "could not decrypt" would send a notary
                # hunting for a network fault when the real answer is that two
                # machines are on different versions of the application.
                self._event("rejected",
                            f"{addr[0]} protocol {client_proto} != {PROTOCOL_VERSION}")
                return
            key = derive_key(self.token, session_id)

            # ── everything below is sealed ──────────────────────────────────
            while self._running.is_set():
                try:
                    msg = recv_sealed(sock, key, rx)
                except socket.timeout:
                    continue
                except CryptoError:
                    # Being unable to decrypt IS the failed authentication: the
                    # peer does not hold the office token.
                    self._event("rejected", f"{addr[0]} (bad token)")
                    self._note_auth_failure(addr)
                    break
                except Exception:
                    break
                if msg is None:
                    break
                rx += 1

                op = msg.get("op")

                if op == "auth":
                    # Reaching here already proves the token: the frame
                    # decrypted. This step exists so the client gets a clear
                    # confirmation rather than inferring success from silence.
                    authed = True
                    db = sqlite3.connect(self.db_path, timeout=30,
                                         check_same_thread=False)
                    db.row_factory = sqlite3.Row
                    db.execute("PRAGMA journal_mode=WAL;")
                    db.execute("PRAGMA synchronous=NORMAL;")
                    db.execute("PRAGMA foreign_keys=ON;")
                    db.execute("PRAGMA busy_timeout=30000;")
                    send_sealed(sock, key, tx, {"ok": True,
                                                "protocol": PROTOCOL_VERSION})
                    tx += 1
                    continue

                if not authed:
                    send_sealed(sock, key, tx, {"ok": False,
                                                "error": "not authenticated"})
                    tx += 1
                    break

                if op == "login":
                    caps, who, reply = self._login(db, msg)
                    self._event("login" if caps is not None else "login_failed",
                                f"{ip} {msg.get('username', '?')}")
                    send_sealed(sock, key, tx, reply)
                    tx += 1
                    continue

                if op == "logout":
                    caps, who = None, ""
                    send_sealed(sock, key, tx, {"ok": True})
                    tx += 1
                    continue

                if op in ("execute", "executemany"):
                    allowed, why = authorise(msg.get("sql") or "", caps)
                    if not allowed:
                        self._event("denied", f"{ip} {who or 'anonymous'}: {why}")
                        send_sealed(sock, key, tx, {
                            "ok": False, "exc": "OperationalError",
                            "error": f"permission denied — {why}"})
                        tx += 1
                        continue
                    # The author of a correction is decided here, from the login
                    # on this socket, not from what the workstation sent.
                    ok_audit, msg, why_audit = enforce_audit_identity(msg, who)
                    if not ok_audit:
                        self._event("audit_refused",
                                    f"{ip} {who or 'anonymous'}: {why_audit}")
                        send_sealed(sock, key, tx, {
                            "ok": False, "exc": "OperationalError",
                            "error": f"permission denied — {why_audit}"})
                        tx += 1
                        continue

                send_sealed(sock, key, tx, self._handle(db, msg))
                tx += 1
        except Exception:
            self._event("error", traceback.format_exc()[-400:])
        finally:
            try:
                if db is not None:
                    db.close()
            except Exception:
                pass
            try:
                sock.close()
            except Exception:
                pass
            with self._clients_lock:
                self._clients -= 1
                left = self._per_ip.get(ip, 1) - 1
                if left > 0:
                    self._per_ip[ip] = left
                else:
                    self._per_ip.pop(ip, None)
            self._event("disconnect", ip)

    def _login(self, db, msg) -> tuple:
        """
        Verifies a username and password against the server's own accounts.

        The client never sees app_users. It sends credentials over the sealed
        channel and receives a role; the hash comparison happens here, on the
        machine that owns the file.
        """
        username = str(msg.get("username") or "").strip().lower()
        password = str(msg.get("password") or "")
        fail = (None, "", {"ok": False, "error": "invalid username or password"})
        if not username or not password:
            return fail
        try:
            row = db.execute(
                "SELECT username, role, display_name, password_hash "
                "FROM app_users WHERE username=?", (username,)).fetchone()
        except Exception as e:
            return (None, "", {"ok": False, "error": f"accounts unavailable: {e}"})

        try:
            import auth as _auth
            if row is None:
                # Spend the same work as a real check so a missing username and
                # a wrong password take the same time.
                _auth.hash_password(password)
                return fail
            if not _auth.verify_hash(password, row["password_hash"]):
                return fail
        except Exception as e:
            return (None, "", {"ok": False, "error": f"could not verify: {e}"})

        try:
            import permissions as _perm
            caps = set(_perm.GRANTS.get(row["role"], frozenset()))
        except Exception:
            caps = set()
        return (caps, username,
                {"ok": True, "role": row["role"],
                 "display_name": row["display_name"] or "",
                 "capabilities": sorted(caps)})

    def _handle(self, db, msg) -> dict:
        op = msg.get("op")
        try:
            if op in ("execute", "executemany"):
                sql = msg.get("sql") or ""
                if is_ddl(sql):
                    # Reported as an OperationalError because that is what a
                    # local SQLite would raise for a rejected schema change, and
                    # the callers in reception.py already handle that shape.
                    head = " ".join(sql.split()[:3])
                    self._event("ddl_refused", head)
                    return {"ok": False, "exc": "OperationalError",
                            "error": ("schema changes are not permitted from a "
                                      f"workstation (refused: {head})")}

            if op == "execute":
                cur = db.execute(msg.get("sql") or "",
                                 decode_params(msg.get("params")))
                return self._result(cur)

            if op == "executemany":
                seq = [decode_params(p) for p in (msg.get("seq") or [])]
                cur = db.executemany(msg.get("sql") or "", seq)
                return {"ok": True, "rows": None, "cols": None,
                        "rowcount": cur.rowcount, "lastrowid": cur.lastrowid}

            if op == "commit":
                db.commit()
                return {"ok": True}

            if op == "rollback":
                db.rollback()
                return {"ok": True}

            if op == "ping":
                return {"ok": True}

            return {"ok": False, "error": f"unknown op {op!r}"}
        except Exception as e:
            # The client re-raises this as the matching sqlite3 error, so callers
            # in reception.py see what they would have seen locally.
            return {"ok": False, "error": f"{type(e).__name__}: {e}",
                    "exc": type(e).__name__}

    @staticmethod
    def _result(cur) -> dict:
        cols = [d[0] for d in cur.description] if cur.description else None
        rows = None
        if cols is not None:
            rows = [[encode_value(v) for v in tuple(r)] for r in cur.fetchall()]
        return {"ok": True, "rows": rows, "cols": cols,
                "rowcount": cur.rowcount, "lastrowid": cur.lastrowid}
