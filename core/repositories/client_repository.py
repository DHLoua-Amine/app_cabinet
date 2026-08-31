"""
core/repositories/client_repository.py — Data Repository for Client Database Operations.
Encapsulates all SQL queries related to the `clients` table.
"""

from typing import Optional, Dict, List, Any
import sqlite3
import reception


class ClientRepository:
    """Encapsulates CRUD queries for clients."""

    @staticmethod
    def get_by_id(client_id: str) -> Optional[Dict[str, Any]]:
        """Fetches a single client row by client_id."""
        with reception.get_db_cursor() as cursor:
            cursor.execute("SELECT * FROM clients WHERE client_id=?", (str(client_id).strip(),))
            row = cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    def find_by_cin_or_name(term: str) -> List[Dict[str, Any]]:
        """Searches clients by CIN or name matching term."""
        term_clean = str(term).strip()
        if not term_clean:
            return []
        pattern = f"%{term_clean}%"
        with reception.get_db_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM clients WHERE cin_number LIKE ? OR full_name LIKE ? OR (nom || ' ' || prenom) LIKE ?",
                (pattern, pattern, pattern)
            )
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def count_all() -> int:
        """Returns total number of clients registered."""
        with reception.get_db_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS total FROM clients")
            row = cursor.fetchone()
            return row["total"] if row else 0

    @staticmethod
    def get_all(limit: int = 1000, offset: int = 0) -> List[Dict[str, Any]]:
        """Returns paginated clients list ordered by created_at DESC."""
        with reception.get_db_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM clients ORDER BY rowid DESC LIMIT ? OFFSET ?",
                (limit, offset)
            )
            rows = cursor.fetchall()
            return [dict(r) for r in rows]
