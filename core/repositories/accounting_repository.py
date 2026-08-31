"""
core/repositories/accounting_repository.py — Data Repository for Expenses & Salary Accounting Operations.
Encapsulates database operations for expenses and salaries.
"""

from typing import Optional, Dict, List, Any
import reception


class AccountingRepository:
    """Encapsulates CRUD queries for expenses and salaries."""

    @staticmethod
    def get_all_expenses(limit: int = 500) -> List[Dict[str, Any]]:
        """Fetches recent expenses records."""
        with reception.get_db_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM expenses ORDER BY id DESC LIMIT ?",
                (limit,)
            )
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def get_total_expenses_sum() -> float:
        """Calculates total amount of all recorded expenses."""
        with reception.get_db_cursor() as cursor:
            cursor.execute("SELECT SUM(amount) AS total FROM expenses")
            row = cursor.fetchone()
            return float(row["total"]) if row and row["total"] else 0.0

    @staticmethod
    def get_all_salaries(limit: int = 500) -> List[Dict[str, Any]]:
        """Fetches recent salary records."""
        with reception.get_db_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM salaries ORDER BY id DESC LIMIT ?",
                (limit,)
            )
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def get_total_salaries_sum() -> float:
        """Calculates total amount of all recorded salary payments."""
        with reception.get_db_cursor() as cursor:
            cursor.execute("SELECT SUM(amount) AS total FROM salaries")
            row = cursor.fetchone()
            return float(row["total"]) if row and row["total"] else 0.0
