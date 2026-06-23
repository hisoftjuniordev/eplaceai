"""Read-only MCP tools — no mutations, no audit logging."""
from __future__ import annotations

from datetime import date
from typing import Any

from mcp.server.fastmcp import FastMCP

import src.database as db


def _row(record: Any) -> dict | None:
    if record is None:
        return None
    return _serialise(dict(record))


def _rows(records: list[Any]) -> list[dict]:
    return [_serialise(dict(r)) for r in records]


def _serialise(d: dict) -> dict:
    """Convert UUIDs, Decimals, dates to JSON-safe types."""
    import uuid
    from decimal import Decimal
    from datetime import date, time, datetime

    out: dict = {}
    for k, v in d.items():
        if isinstance(v, uuid.UUID):
            out[k] = str(v)
        elif isinstance(v, Decimal):
            out[k] = float(v)
        elif isinstance(v, (date, time, datetime)):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    async def get_employee(
        employee_id: str | None = None,
        emso: str | None = None,
    ) -> dict | None:
        """Vrni podatke o zaposlenem po ID-ju ali EMŠO."""
        if employee_id:
            rec = await db.fetchrow(
                "SELECT * FROM employees WHERE id = $1::uuid", employee_id
            )
        elif emso:
            rec = await db.fetchrow("SELECT * FROM employees WHERE emso = $1", emso)
        else:
            raise ValueError("Podati moraš employee_id ali emso")
        return _row(rec)

    @mcp.tool()
    async def list_employees(
        department: str | None = None,
        is_active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Seznam zaposlenih z opcijskimi filtri."""
        conditions: list[str] = []
        args: list[Any] = []
        idx = 1

        if department is not None:
            conditions.append(f"department = ${idx}")
            args.append(department)
            idx += 1
        if is_active is not None:
            conditions.append(f"is_active = ${idx}")
            args.append(is_active)
            idx += 1

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        args += [limit, offset]
        query = (
            f"SELECT * FROM employees {where} "
            f"ORDER BY last_name, first_name "
            f"LIMIT ${idx} OFFSET ${idx + 1}"
        )
        return _rows(await db.fetch(query, *args))

    @mcp.tool()
    async def get_attendance(
        employee_id: str,
        date_from: str,
        date_to: str,
    ) -> list[dict]:
        """Evidenca delovnega časa zaposlenega za dano obdobje."""
        rows = await db.fetch(
            "SELECT * FROM attendance "
            "WHERE employee_id = $1::uuid AND date BETWEEN $2 AND $3 "
            "ORDER BY date",
            employee_id, date_from, date_to,
        )
        return _rows(rows)

    @mcp.tool()
    async def get_travel_orders(
        employee_id: str | None = None,
        status: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict]:
        """Seznam potnih nalogov z opcijskimi filtri."""
        conditions: list[str] = []
        args: list[Any] = []
        idx = 1

        if employee_id:
            conditions.append(f"employee_id = ${idx}::uuid")
            args.append(employee_id)
            idx += 1
        if status:
            conditions.append(f"status = ${idx}")
            args.append(status)
            idx += 1
        if date_from:
            conditions.append(f"date_from >= ${idx}")
            args.append(date_from)
            idx += 1
        if date_to:
            conditions.append(f"date_to <= ${idx}")
            args.append(date_to)
            idx += 1

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        query = f"SELECT * FROM travel_orders {where} ORDER BY date_from DESC"
        return _rows(await db.fetch(query, *args))

    @mcp.tool()
    async def get_leave_requests(
        employee_id: str | None = None,
        leave_type: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        """Seznam odsotnosti (dopusti, bolniške) z opcijskimi filtri."""
        conditions: list[str] = []
        args: list[Any] = []
        idx = 1

        if employee_id:
            conditions.append(f"employee_id = ${idx}::uuid")
            args.append(employee_id)
            idx += 1
        if leave_type:
            conditions.append(f"leave_type = ${idx}")
            args.append(leave_type)
            idx += 1
        if status:
            conditions.append(f"status = ${idx}")
            args.append(status)
            idx += 1

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        query = f"SELECT * FROM leave_requests {where} ORDER BY date_from DESC"
        return _rows(await db.fetch(query, *args))

    @mcp.tool()
    async def get_payroll_run(
        employee_id: str,
        period_month: int,
        period_year: int,
    ) -> dict | None:
        """Pridobi obračun plače za zaposlenega in dano obdobje."""
        rec = await db.fetchrow(
            "SELECT * FROM payroll_runs "
            "WHERE employee_id = $1::uuid AND period_month = $2 AND period_year = $3",
            employee_id, period_month, period_year,
        )
        return _row(rec)

    @mcp.tool()
    async def get_payroll_summary(
        period_month: int,
        period_year: int,
        department: str | None = None,
    ) -> dict:
        """Agregatni povzetek plač za celotno podjetje ali oddelek."""
        if department:
            row = await db.fetchrow(
                """
                SELECT
                    COUNT(*)::int              AS employee_count,
                    SUM(pr.gross_salary)       AS total_gross,
                    SUM(pr.net_salary)         AS total_net,
                    SUM(pr.employee_contributions) AS total_emp_contrib,
                    SUM(pr.employer_contributions) AS total_er_contrib,
                    SUM(pr.income_tax)         AS total_income_tax
                FROM payroll_runs pr
                JOIN employees e ON e.id = pr.employee_id
                WHERE pr.period_month = $1 AND pr.period_year = $2
                  AND e.department = $3
                  AND pr.status != 'cancelled'
                """,
                period_month, period_year, department,
            )
        else:
            row = await db.fetchrow(
                """
                SELECT
                    COUNT(*)::int              AS employee_count,
                    SUM(gross_salary)          AS total_gross,
                    SUM(net_salary)            AS total_net,
                    SUM(employee_contributions) AS total_emp_contrib,
                    SUM(employer_contributions) AS total_er_contrib,
                    SUM(income_tax)            AS total_income_tax
                FROM payroll_runs
                WHERE period_month = $1 AND period_year = $2
                  AND status != 'cancelled'
                """,
                period_month, period_year,
            )
        return _serialise(dict(row)) if row else {}

    @mcp.tool()
    async def get_employee_balance(employee_id: str) -> dict:
        """Stanje dopustov zaposlenega: porabljeni, preostali, načrtovani."""
        rows = await db.fetch(
            """
            SELECT
                leave_type,
                status,
                SUM(days_count) AS days
            FROM leave_requests
            WHERE employee_id = $1::uuid
            GROUP BY leave_type, status
            ORDER BY leave_type, status
            """,
            employee_id,
        )
        balance: dict[str, dict[str, float]] = {}
        for r in rows:
            lt = r["leave_type"]
            st = r["status"]
            days = float(r["days"] or 0)
            if lt not in balance:
                balance[lt] = {}
            balance[lt][st] = days
        return balance
