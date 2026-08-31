"""
db_service.py — owns the single DatabaseServer instance for this process.

Kept apart from db_server.py so the server object has one obvious home: main()
starts it, Paramètres asks it whether it is running and how many machines are
connected, and shutdown stops it. Nothing else constructs one.
"""

from __future__ import annotations

import threading

_server = None
_lock = threading.RLock()
_events = []
_EVENTS_MAX = 60


def _record(kind, detail):
    _events.append((kind, detail))
    del _events[:-_EVENTS_MAX]


def recent_events():
    return list(_events)


def get_server():
    with _lock:
        return _server


def is_running() -> bool:
    srv = get_server()
    return bool(srv and srv.running)


def client_count() -> int:
    srv = get_server()
    return srv.client_count if srv else 0


def bound_address() -> str:
    """The address the server is really listening on, for Paramètres to show.

    Not the configured value: with "auto" the two differ, and the notary needs
    the real one to type into the other machine.
    """
    srv = get_server()
    return f"{srv.host}:{srv.port}" if srv and srv.running else ""


def refused_count() -> int:
    srv = get_server()
    return srv.refused_count if srv else 0


def blocked_addresses() -> list:
    srv = get_server()
    return srv.blocked_addresses() if srv else []


def start_if_server() -> tuple:
    """
    Starts serving when this machine is configured as the office server.

    Returns (started, note): started is None when this machine is not a server
    at all — the ordinary standalone case, which is not an error and must not be
    reported as one.
    """
    import config
    cfg = config.load_network_config()
    if cfg.get("mode") != config.MODE_SERVER:
        return (None, "")

    token = cfg.get("token") or ""
    if not token:
        # Refusing to serve without a token is deliberate. An open port carrying
        # the office's client records to anyone on the network is worse than a
        # server that did not start.
        return (False, "no access token is set for this office server")

    # In server mode the config's "host" is the address to LISTEN on; empty
    # means auto-detect the office LAN address. It was previously ignored
    # entirely, so a server could not be pinned to an interface even when the
    # office wanted it on one.
    return start(str(config.DB_PATH if hasattr(config, "DB_PATH")
                     else config.DATA_DIR / "reception.db"),
                 token, int(cfg.get("port") or config.DEFAULT_DB_PORT),
                 bind=(cfg.get("host") or "auto"))


def start(db_path: str, token: str, port: int, bind: str = "auto") -> tuple:
    global _server
    with _lock:
        if _server is not None and _server.running:
            return (True, f"already serving on port {_server.port}")
        from db_server import DatabaseServer
        srv = DatabaseServer(db_path=db_path, token=token, host=bind,
                             port=port, on_event=_record)
        ok = srv.start()
        _server = srv if ok else None
        if ok:
            return (True, f"serving {db_path} on {srv.host}:{port}")
        return (False, srv.last_error or "could not bind the port")


def stop():
    global _server
    with _lock:
        if _server is not None:
            try:
                _server.stop()
            except Exception:
                # (c) Safe: we are shutting down either way.
                pass
            _server = None
