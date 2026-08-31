"""
core/repositories/checkin_repository.py — Data Repository for Reception Check-Ins & Presence Records.
Encapsulates all SQL queries related to `check_ins` and presence tracking.
"""

from typing import Optional, Dict, List, Any
import sqlite3
import datetime
import reception


class CheckInRepository:
    """Encapsulates CRUD queries for reception check-ins."""

    @staticmethod
    def get_todays_check_ins() -> List[Dict[str, Any]]:
        """Fetches all check-in records for today."""
        today_str = datetime.date.today().isoformat()
        with reception.get_db_cursor() as cursor:
            cursor.execute(
                "SELECT c.*, cl.full_name, cl.cin_number, cl.phone "
                "FROM check_ins c "
                "LEFT JOIN clients cl ON c.client_id = cl.client_id "
                "WHERE date(c.timestamp) = ? ORDER BY c.timestamp DESC",
                (today_str,)
            )
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def count_todays_visits() -> int:
        """Returns total check-ins count for today."""
        today_str = datetime.date.today().isoformat()
        with reception.get_db_cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS total FROM check_ins WHERE date(timestamp) = ?",
                (today_str,)
            )
            row = cursor.fetchone()
            return row["total"] if row else 0

    @staticmethod
    def get_filtered(date_from: str = "", date_to: str = "", search_term: str = "",
                     guichet: str = "", payment_status: str = "") -> List[Dict[str, Any]]:
        """Delegates filtered check-in queries cleanly."""
        return reception.get_check_ins_filtered(
            date_from=date_from,
            date_to=date_to,
            search_term=search_term,
            guichet=guichet,
            payment_status=payment_status
        )
