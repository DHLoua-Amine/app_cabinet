"""
permissions.py — what each role is allowed to do, and the enforcement primitive.

The old auth.py described two roles in its docstring and never enforced either of
them: `auth_logged_in` was set to False at construction and no line of code
anywhere in the app ever set it to True, and `is_patron()` / `is_receptionniste()`
had zero call sites. Access control was, in practice, absent.

This module is the single source of truth for the answer to "may the current user
do X". It deliberately knows nothing about Qt: the same check runs whether the
caller is a button handler, an Excel export, or a direct function call, which is
what stops a hidden button from being the only thing standing between the
secretary and the office's revenue.

Enforcement happens in two shapes:

  @require(Cap.X)   — the function refuses outright and raises PermissionDenied.
                      Used where the whole result is privileged (revenue, the
                      receivables ledger, expenses, salaries).

  redact(rows, ...) — the function still returns, with the privileged columns
                      stripped. Used where the secretary legitimately needs the
                      record but not its money: she must be able to see and work
                      a dossier without being shown the office's figures.
"""

from __future__ import annotations

import threading


class PermissionDenied(PermissionError):
    """Raised when the signed-in role may not perform the requested action."""

    def __init__(self, capability: str, role: str | None = None):
        self.capability = capability
        self.role = role
        super().__init__(
            f"role {role!r} is not permitted to {capability!r}")


# ── Roles ────────────────────────────────────────────────────────────────────
ROLE_ADMIN = "admin"            # le notaire / le patron
ROLE_SECRETARY = "secretary"    # la secrétaire / الكاتبة

ROLE_LABELS = {
    ROLE_ADMIN: ("Notaire (administrateur)", "الأستاذ (المدير)"),
    ROLE_SECRETARY: ("Secrétaire", "الكاتبة"),
}


# ── Capabilities ─────────────────────────────────────────────────────────────
class Cap:
    """Every distinct thing the app can be asked to do that is worth gating."""

    # Day-to-day work — the secretary's job.
    VIEW_CLIENTS = "view_clients"
    EDIT_CLIENTS = "edit_clients"
    DELETE_CLIENTS = "delete_clients"
    VIEW_DOSSIERS = "view_dossiers"
    CREATE_DOSSIER = "create_dossier"
    EDIT_DOSSIER = "edit_dossier"
    DELETE_DOSSIER = "delete_dossier"
    RECORD_PAYMENT = "record_payment"
    LOG_PRESENCE = "log_presence"
    USE_SCANNER = "use_scanner"

    # Money — the notary's alone.
    VIEW_FINANCE = "view_finance"                 # the Comptabilité page at all
    VIEW_REVENUE = "view_revenue"                 # income roll-ups, profit
    VIEW_RECEIVABLES = "view_receivables"         # who owes the office what
    VIEW_EXPENSES = "view_expenses"               # charges and salaries
    MANAGE_EXPENSES = "manage_expenses"           # recording charges/salaries
    # Correcting a figure that is ALREADY recorded is a different act from
    # recording one: it rewrites history rather than adding to it, and it is
    # the act an audit would question. It gets its own capability so it can
    # never be granted as a side effect of granting data entry.
    EDIT_FINANCE_ENTRY = "edit_finance_entry"     # correcting a recorded charge/salary
    EXPORT_FINANCE = "export_finance"             # the financial Excel/PDF report
    VIEW_DOSSIER_AMOUNTS = "view_dossier_amounts"  # ONE dossier's own total/avance/reste
    # A list of every dossier with its amount is a revenue report wearing a
    # different hat: the column sums to the office's turnover. It is therefore
    # gated separately from the single-dossier figure the secretary needs in
    # front of her to type a payment into.
    VIEW_DOSSIER_AMOUNTS_BULK = "view_dossier_amounts_bulk"

    # Administration.
    MANAGE_USERS = "manage_users"                 # create/reset other accounts
    MANAGE_BACKUP = "manage_backup"               # backup, restore, USB
    MANAGE_API_KEYS = "manage_api_keys"
    MANAGE_CAMERA = "manage_camera"


# ── The grant table ──────────────────────────────────────────────────────────
# The admin gets everything. The secretary's set is written out in full rather
# than as "everything except", so adding a new capability defaults to denied for
# her instead of silently granted.
_SECRETARY_CAPS = frozenset({
    Cap.VIEW_CLIENTS, Cap.EDIT_CLIENTS,
    Cap.VIEW_DOSSIERS, Cap.CREATE_DOSSIER, Cap.EDIT_DOSSIER,
    Cap.RECORD_PAYMENT, Cap.LOG_PRESENCE,
    Cap.VIEW_DOSSIER_AMOUNTS,
})

_ALL_CAPS = frozenset(
    v for k, v in vars(Cap).items() if not k.startswith("_") and isinstance(v, str))

GRANTS = {
    ROLE_ADMIN: _ALL_CAPS,
    ROLE_SECRETARY: _SECRETARY_CAPS,
}

# Columns that carry money and must never reach a role without the capability.
MONEY_COLUMNS = (
    "total_amount", "avance_amount", "remaining", "reste",
    "montant", "amount", "amount_paid", "total_estimated",
    "montant_avances", "montant_total", "revenue", "profit",
)


# ── The current session ──────────────────────────────────────────────────────
class _Session:
    """
    Who is signed in, for this process.

    Deliberately process-global and thread-safe rather than passed around: the
    alternative is threading a user object through every call site in the app,
    and any site that forgot to would silently become an unguarded hole.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self.username: str | None = None
        self.role: str | None = None
        self.display: str = ""
        self.logged_in: bool = False

    def sign_in(self, username: str, role: str, display: str = ""):
        if role not in GRANTS:
            raise ValueError(f"unknown role {role!r}")
        with self._lock:
            self.username = username
            self.role = role
            self.display = display
            self.logged_in = True

    def sign_out(self):
        with self._lock:
            self.username = None
            self.role = None
            self.display = ""
            self.logged_in = False

    def capabilities(self) -> frozenset:
        with self._lock:
            if not self.logged_in or self.role is None:
                return frozenset()
            return GRANTS.get(self.role, frozenset())


session = _Session()


def has(capability: str) -> bool:
    """True when the signed-in role holds this capability. Never raises."""
    return capability in session.capabilities()


def require(capability: str):
    """
    Decorator: refuse the call unless the signed-in role holds `capability`.

    This sits on the data-layer function, not on the button, so the guard holds
    for every route into it — the page, an export, another page reusing the same
    helper, or a future caller nobody has written yet.
    """
    def decorator(func):
        from functools import wraps

        @wraps(func)
        def wrapper(*args, **kwargs):
            if capability not in session.capabilities():
                raise PermissionDenied(capability, session.role)
            return func(*args, **kwargs)

        wrapper.__required_capability__ = capability
        return wrapper
    return decorator


def check(capability: str):
    """Imperative form of `require`, for use inside a function body."""
    if capability not in session.capabilities():
        raise PermissionDenied(capability, session.role)


def redact(rows, capability: str = Cap.VIEW_DOSSIER_AMOUNTS, columns=MONEY_COLUMNS):
    """
    Strips money columns from a list of dict rows unless the role may see them.

    Used where denying the whole call would break legitimate work: the secretary
    needs the dossier list to do her job, she just must not be shown what each
    one is worth. Returns the rows untouched when the capability is held.
    """
    if has(capability):
        return rows
    out = []
    for row in rows:
        try:
            clean = dict(row)
        except (TypeError, ValueError):
            out.append(row)
            continue
        for col in columns:
            if col in clean:
                clean[col] = None
        out.append(clean)
    return out


def describe(role: str | None = None) -> str:
    """Human-readable summary of a role's grants, for the report and the UI."""
    role = role or session.role
    caps = sorted(GRANTS.get(role, frozenset()))
    return f"{role}: {len(caps)} capabilities -> {', '.join(caps)}"
