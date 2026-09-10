"""
db_client.py — talks to the office's database server as if it were local.

The whole point of this module is that reception.py does not change. Its ~60
data functions use `with get_db_cursor(commit=True) as cursor:` and then
`cursor.execute(...)`, `cursor.fetchone()["n"]`, `cursor.rowcount`. So this
presents that exact surface over a socket:

    RemoteConnection.cursor()  ->  RemoteCursor
    RemoteCursor.execute/executemany/fetchone/fetchall/rowcount/description
    rows behave like sqlite3.Row: r["full_name"], r[0], dict(r), r.keys()

pandas is also handled: read_sql_query() on a non-SQLAlchemy connection asks for
.cursor(), calls execute(), then reads .description and .fetchall(), which is
why description is implemented rather than stubbed.
"""

from __future__ import annotations

import os
import socket
import sqlite3
import threading

from db_server import (PROTOCOL_VERSION, DEFAULT_PORT, encode_params,
                       encode_value, decode_value, is_ddl)
from db_crypto import (CryptoError, derive_key, recv_plain, recv_sealed,
                       send_plain, send_sealed)


class RemoteDatabaseError(Exception):
    """The server refused or could not run the statement."""


class Row:
    """
    A stand-in for sqlite3.Row.

    reception.py reads rows both ways — `r["client_id"]` and `dict(r)` — and
    pandas indexes them positionally, so all three have to work.
    """

    __slots__ = ("_cols", "_vals", "_index")

    def __init__(self, cols, vals):
        self._cols = cols
        self._vals = vals
        self._index = {c: i for i, c in enumerate(cols)}

    def __getitem__(self, key):
        if isinstance(key, str):
            try:
                return self._vals[self._index[key]]
            except KeyError:
                raise IndexError(f"no such column: {key}")
        return self._vals[key]

    def keys(self):
        return list(self._cols)

    def __iter__(self):
        return iter(self._vals)

    def __len__(self):
        return len(self._vals)

    def __contains__(self, key):
        return key in self._index

    def get(self, key, default=None):
        return self._vals[self._index[key]] if key in self._index else default

    def __repr__(self):
        return f"Row({dict(zip(self._cols, self._vals))})"


class RemoteCursor:
    def __init__(self, conn: "RemoteConnection"):
        self._conn = conn
        self._rows = []
        self._cols = None
        self.rowcount = -1
        self.lastrowid = None

    @property
    def description(self):
        # pandas reads this to name the DataFrame's columns.
        if self._cols is None:
            return None
        return [(c, None, None, None, None, None, None) for c in self._cols]

    def execute(self, sql, params=()):
        if is_ddl(sql):
            # The server owns the schema, so a workstation's CREATE TABLE IF NOT
            # EXISTS is not an error to report — it is a statement about a table
            # that already exists, made by a machine with no say in the matter.
            # Skipping it here avoids a round trip per statement (34 of them on
            # every startup) and leaves the modules that create tables lazily —
            # office_profile, record_edits — working unchanged.
            self._absorb({"ok": True, "rows": None, "cols": None,
                          "rowcount": 0, "lastrowid": None})
            return self
        res = self._conn._call({"op": "execute", "sql": sql,
                                "params": encode_params(params)})
        self._absorb(res)
        return self

    def executemany(self, sql, seq_of_params):
        if is_ddl(sql):
            self._absorb({"ok": True, "rows": None, "cols": None,
                          "rowcount": 0, "lastrowid": None})
            return self
        res = self._conn._call({"op": "executemany", "sql": sql,
                                "seq": [encode_params(p) for p in seq_of_params]})
        self._absorb(res)
        return self

    def _absorb(self, res):
        self._cols = res.get("cols")
        raw = res.get("rows")
        self._rows = ([Row(self._cols, [decode_value(v) for v in r]) for r in raw]
                      if raw is not None else [])
        self.rowcount = res.get("rowcount", -1)
        self.lastrowid = res.get("lastrowid")

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def fetchall(self):
        out, self._rows = self._rows, []
        return out

    def fetchmany(self, size=1):
        out, self._rows = self._rows[:size], self._rows[size:]
        return out

    def __iter__(self):
        return iter(self.fetchall())

    def close(self):
        self._rows = []


class RemoteConnection:
    """
    One TCP connection to the office server, used like a sqlite3 connection.

    Held per thread by reception.get_connection(), exactly as the local
    connection was, so a transaction belongs to the thread that opened it.
    """

    def __init__(self, host: str, port: int = DEFAULT_PORT, token: str = "",
                 timeout: float = 15.0):
        self.host = host
        self.port = int(port)
        self.token = token
        self.timeout = timeout
        self.row_factory = None          # accepted and ignored; rows are already Rows
        self.role = ""
        self.display_name = ""
        self.capabilities = set()
        self._sock = None
        self._key = None
        self._tx = 0          # frames sent on this connection
        self._rx = 0          # frames received; both are authenticated data,
                              # so a replayed or reordered frame fails to open
        self._lock = threading.RLock()
        self._connect()

    # -- transport ---------------------------------------------------------
    def _connect(self):
        """
        Handshake, then a sealed channel.

        The token is never sent. Both sides derive the same key from it and the
        session id the server issues, so proving we hold the token IS being able
        to produce a frame the server can decrypt.
        """
        import base64
        s = socket.create_connection((self.host, self.port), timeout=self.timeout)
        s.settimeout(self.timeout)
        self._sock = s
        self._tx = self._rx = 0
        try:
            send_plain(s, {"op": "hello", "protocol": PROTOCOL_VERSION})
            reply = recv_plain(s)
        except Exception as e:
            self._reset()
            raise RemoteDatabaseError(f"no answer from the office server: {e}") from e
        if not reply or not reply.get("ok"):
            self._reset()
            raise RemoteDatabaseError(
                (reply or {}).get("error") or "the server refused the connection")
        if reply.get("protocol") != PROTOCOL_VERSION:
            self._reset()
            raise RemoteDatabaseError(
                f"server speaks protocol {reply.get('protocol')}, this app speaks "
                f"{PROTOCOL_VERSION} — the two machines are on different versions "
                f"of the application")
        session_b64 = reply.get("session") or ""
        try:
            session_id = base64.b64decode(session_b64)
        except Exception:
            self._reset()
            raise RemoteDatabaseError("the server sent an unusable session id")
        if len(session_id) < 16:
            self._reset()
            raise RemoteDatabaseError("the server sent a short session id")
        self._key = derive_key(self.token, session_id)

        try:
            send_sealed(s, self._key, self._tx, {"op": "auth"})
            self._tx += 1
            ack = recv_sealed(s, self._key, self._rx)
            self._rx += 1
        except CryptoError:
            self._reset()
            # The only way this fails is a key mismatch, and the only input to
            # the key we control is the token.
            raise RemoteDatabaseError(
                "the office server rejected this machine — the access key does "
                "not match")
        except Exception as e:
            self._reset()
            raise RemoteDatabaseError(f"the handshake failed: {e}") from e
        if not ack or not ack.get("ok"):
            self._reset()
            raise RemoteDatabaseError(
                (ack or {}).get("error") or "the server refused the connection")

    def _call(self, msg: dict) -> dict:
        with self._lock:
            if self._sock is None:
                self._connect()
            try:
                send_sealed(self._sock, self._key, self._tx, msg)
                self._tx += 1
                res = recv_sealed(self._sock, self._key, self._rx)
                self._rx += 1
            except Exception as e:
                # One reconnect attempt: a laptop that slept, or the office
                # switch blinking, should not surface as a database error.
                self._reset()
                try:
                    self._connect()
                    send_sealed(self._sock, self._key, self._tx, msg)
                    self._tx += 1
                    res = recv_sealed(self._sock, self._key, self._rx)
                    self._rx += 1
                except Exception as e2:
                    raise RemoteDatabaseError(
                        f"lost the connection to the office server "
                        f"({self.host}:{self.port}): {e2 or e}") from e2
            if res is None:
                self._reset()
                raise RemoteDatabaseError("the office server closed the connection")
            if not res.get("ok"):
                # Re-raise as the sqlite3 error the caller would have seen
                # locally, so every `except sqlite3.OperationalError` in
                # reception.py keeps working unchanged.
                err = res.get("error") or "unknown database error"
                name = res.get("exc") or ""
                exc = getattr(sqlite3, name, None)
                if isinstance(exc, type) and issubclass(exc, Exception):
                    raise exc(err)
                raise sqlite3.DatabaseError(err)
            return res

    def _reset(self):
        try:
            if self._sock:
                self._sock.close()
        except Exception:
            pass
        self._sock = None
        self._key = None
        self._tx = self._rx = 0

    # -- signing in ---------------------------------------------------------
    def login(self, username: str, password: str) -> dict:
        """
        Signs a user in ON THE SERVER, which then enforces their role.

        The credentials go over the sealed channel; the password hash stays on
        the server and app_users is never queried across the network.
        """
        res = self._call({"op": "login", "username": username,
                          "password": password})
        self.role = res.get("role") or ""
        self.display_name = res.get("display_name") or ""
        self.capabilities = set(res.get("capabilities") or [])
        return res

    def logout(self):
        try:
            self._call({"op": "logout"})
        except Exception:
            # (c) Safe: the connection is being discarded anyway.
            pass
        self.role = ""
        self.capabilities = set()

    # -- sqlite3.Connection surface ---------------------------------------
    def cursor(self):
        return RemoteCursor(self)

    def execute(self, sql, params=()):
        return RemoteCursor(self).execute(sql, params)

    def executemany(self, sql, seq):
        return RemoteCursor(self).executemany(sql, seq)

    def commit(self):
        self._call({"op": "commit"})

    def rollback(self):
        self._call({"op": "rollback"})

    def close(self):
        self._reset()

    def ping(self) -> bool:
        try:
            self._call({"op": "ping"})
            return True
        except Exception:
            return False

    def sync_photo(self, photo_path: str) -> bool:
        """Transfers a profile photo binary file to the office server's disk."""
        if not photo_path or not os.path.exists(photo_path):
            return False
        try:
            filename = os.path.basename(photo_path)
            with open(photo_path, "rb") as f:
                raw_bytes = f.read()
            res = self._call({
                "op": "sync_photo",
                "filename": filename,
                "data": encode_value(raw_bytes)
            })
            return bool(res and res.get("ok"))
        except Exception as e:
            from system_guardian import log_system_error
            log_system_error("sync_photo failed", e)
            return False

    def cache_generation(self) -> int:
        try:
            res = self._call({"op": "get_cache_gen"})
            return res.get("gen", 0) if res else 0
        except Exception:
            return 0

    def fetch_photo(self, photo_path: str) -> str:
        """Fetches a profile photo binary from the server and saves it to local disk."""
        if not photo_path:
            return ""
        if os.path.exists(photo_path):
            return photo_path
        
        filename = os.path.basename(photo_path)
        from config import PROFILES_DIR
        PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        local_target = PROFILES_DIR / filename
        if local_target.exists() and os.path.getsize(local_target) > 0:
            return str(local_target)
        
        try:
            res = self._call({"op": "get_photo", "path": photo_path})
            if res and res.get("ok") and res.get("data"):
                raw_bytes = decode_value(res["data"])
                with open(local_target, "wb") as f:
                    f.write(raw_bytes)
                return str(local_target)
        except Exception as e:
            from system_guardian import log_system_error
            log_system_error("fetch_photo failed", e)
        return photo_path

    def get_unknown_visitors(self) -> list:
        try:
            res = self._call({"op": "get_unknown_visitors"})
            return res.get("visitors", []) if res else []
        except Exception:
            return []

    def push_unknown_visitor(self, visitor: dict) -> bool:
        try:
            res = self._call({"op": "push_unknown_visitor", "visitor": visitor})
            return bool(res and res.get("ok"))
        except Exception:
            return False

    def purge_unknown_visitor(self, client_ids: list) -> bool:
        try:
            res = self._call({"op": "purge_unknown_visitor", "client_ids": client_ids})
            return bool(res and res.get("ok"))
        except Exception:
            return False

    def push_live_detection(self, detection: dict) -> bool:
        try:
            res = self._call({"op": "push_live_detection", "detection": detection})
            return bool(res and res.get("ok"))
        except Exception:
            return False

    def get_live_detection(self, since: float = 0) -> list:
        try:
            res = self._call({"op": "get_live_detection", "since": since})
            return res.get("detections", []) if res else []
        except Exception:
            return []



def probe(host: str, port: int, token: str, timeout: float = 6.0) -> tuple:
    """
    Tests a server address without disturbing anything. Returns (ok, message).

    Used by Paramètres so the notary finds out the address is wrong while
    setting it up, rather than the next morning when nothing loads.
    """
    try:
        conn = RemoteConnection(host, port, token, timeout=timeout)
    except RemoteDatabaseError as e:
        return (False, str(e))
    except OSError as e:
        return (False, f"no answer from {host}:{port} ({e.__class__.__name__})")
    except Exception as e:
        return (False, f"{type(e).__name__}: {e}")
    try:
        cur = conn.execute("SELECT COUNT(*) AS n FROM clients")
        n = cur.fetchone()["n"]
        return (True, f"connected — {n} client(s) in the office database")
    except Exception as e:
        return (False, f"connected, but the database could not be read: {e}")
    finally:
        conn.close()
