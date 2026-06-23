"""Write / mutation MCP tools — all mutations are audit-logged."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from mcp.server.fastmcp import FastMCP

import src.database as db
from src.audit.logger import log_action
from src.services.si_rules import calculate_daily_allowance
from src.validators.emso_validator import validate_emso
from src.validators.input_validators import validate_iban, validate_positive_amount


def _serialise(d: dict) -> dict:
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
    async def create_employee(
        first_name: str,
        last_name: str,
        hire_date: str,
        base_salary: float,
        emso: str | None = None,
        davcna_stevilka: str | None = None,
        date_of_birth: str | None = None,
        address: str | None = None,
        city: str | None = None,
        postal_code: str | None = None,
        phone: str | None = None,
        email: str | None = None,
        department: str | None = None,
        job_title: str | None = None,
        employment_type: str | None = None,
        contract_hours: float = 40.0,
        bank_account: str | None = None,
    ) -> dict:
        """Dodaj novega zaposlenega. Validira EMŠO in IBAN."""
        if emso:
            validate_emso(emso)
        if bank_account:
            bank_account = validate_iban(bank_account)
        validate_positive_amount(base_salary, "base_salary")

        rec = await db.fetchrow(
            """
            INSERT INTO employees
                (first_name, last_name, hire_date, base_salary, emso, davcna_stevilka,
                 date_of_birth, address, city, postal_code, phone, email,
                 department, job_title, employment_type, contract_hours, bank_account)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)
            RETURNING *
            """,
            first_name, last_name, hire_date, Decimal(str(base_salary)),
            emso, davcna_stevilka, date_of_birth, address, city, postal_code,
            phone, email, department, job_title, employment_type,
            Decimal(str(contract_hours)), bank_account,
        )
        result = _serialise(dict(rec))
        await log_action(
            table_name="employees",
            record_id=result["id"],
            operation="insert",
            new_values=result,
            agent_tool="create_employee",
        )
        return result

    @mcp.tool()
    async def update_employee(
        employee_id: str,
        first_name: str | None = None,
        last_name: str | None = None,
        emso: str | None = None,
        base_salary: float | None = None,
        department: str | None = None,
        job_title: str | None = None,
        is_active: bool | None = None,
        termination_date: str | None = None,
        bank_account: str | None = None,
        address: str | None = None,
        city: str | None = None,
        postal_code: str | None = None,
        phone: str | None = None,
        email: str | None = None,
        employment_type: str | None = None,
        contract_hours: float | None = None,
    ) -> dict:
        """Posodobi podatke zaposlenega. Pošlji samo polja, ki jih želiš spremeniti."""
        old = await db.fetchrow("SELECT * FROM employees WHERE id = $1::uuid", employee_id)
        if old is None:
            raise ValueError(f"Zaposleni z ID {employee_id} ne obstaja")

        if emso:
            validate_emso(emso)
        if bank_account:
            bank_account = validate_iban(bank_account)
        if base_salary is not None:
            validate_positive_amount(base_salary, "base_salary")

        sets: list[str] = ["updated_at = NOW()"]
        args: list[Any] = []
        idx = 1

        mapping = {
            "first_name": first_name, "last_name": last_name, "emso": emso,
            "base_salary": Decimal(str(base_salary)) if base_salary is not None else None,
            "department": department, "job_title": job_title, "is_active": is_active,
            "termination_date": termination_date, "bank_account": bank_account,
            "address": address, "city": city, "postal_code": postal_code,
            "phone": phone, "email": email, "employment_type": employment_type,
            "contract_hours": Decimal(str(contract_hours)) if contract_hours is not None else None,
        }
        for col, val in mapping.items():
            if val is not None:
                sets.append(f"{col} = ${idx}")
                args.append(val)
                idx += 1

        args.append(employee_id)
        rec = await db.fetchrow(
            f"UPDATE employees SET {', '.join(sets)} WHERE id = ${idx}::uuid RETURNING *",
            *args,
        )
        result = _serialise(dict(rec))
        await log_action(
            table_name="employees",
            record_id=employee_id,
            operation="update",
            old_values=_serialise(dict(old)),
            new_values=result,
            agent_tool="update_employee",
        )
        return result

    @mcp.tool()
    async def create_attendance(
        employee_id: str,
        date: str,
        clock_in: str | None = None,
        clock_out: str | None = None,
        hours_worked: float | None = None,
        hours_overtime: float = 0.0,
        hours_night: float = 0.0,
        hours_weekend: float = 0.0,
        hours_holiday: float = 0.0,
        status: str = "present",
        notes: str | None = None,
    ) -> dict:
        """Vnesi evidenco delovnega časa za zaposlenega."""
        rec = await db.fetchrow(
            """
            INSERT INTO attendance
                (employee_id, date, clock_in, clock_out, hours_worked, hours_overtime,
                 hours_night, hours_weekend, hours_holiday, status, notes)
            VALUES ($1::uuid,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
            RETURNING *
            """,
            employee_id, date, clock_in, clock_out,
            Decimal(str(hours_worked)) if hours_worked is not None else None,
            Decimal(str(hours_overtime)), Decimal(str(hours_night)),
            Decimal(str(hours_weekend)), Decimal(str(hours_holiday)),
            status, notes,
        )
        result = _serialise(dict(rec))
        await log_action(
            table_name="attendance",
            record_id=result["id"],
            operation="insert",
            new_values=result,
            agent_tool="create_attendance",
        )
        return result

    @mcp.tool()
    async def create_travel_order(
        employee_id: str,
        destination: str,
        date_from: str,
        date_to: str,
        purpose: str | None = None,
        transport_type: str | None = None,
        km_total: float | None = None,
        accommodation: float = 0.0,
    ) -> dict:
        """Ustvari potni nalog in avtomatsko izračunaj dnevnico."""
        from datetime import date as ddate
        d_from = ddate.fromisoformat(date_from)
        d_to = ddate.fromisoformat(date_to)
        if d_to < d_from:
            raise ValueError("date_to mora biti >= date_from")

        daily_allowance = calculate_daily_allowance(d_from, d_to)

        rec = await db.fetchrow(
            """
            INSERT INTO travel_orders
                (employee_id, destination, purpose, date_from, date_to,
                 transport_type, km_total, daily_allowance, accommodation)
            VALUES ($1::uuid,$2,$3,$4,$5,$6,$7,$8,$9)
            RETURNING *
            """,
            employee_id, destination, purpose, d_from, d_to,
            transport_type,
            Decimal(str(km_total)) if km_total is not None else None,
            Decimal(str(daily_allowance)),
            Decimal(str(accommodation)),
        )
        result = _serialise(dict(rec))
        await log_action(
            table_name="travel_orders",
            record_id=result["id"],
            operation="insert",
            new_values=result,
            agent_tool="create_travel_order",
        )
        return result

    @mcp.tool()
    async def create_leave_request(
        employee_id: str,
        leave_type: str,
        date_from: str,
        date_to: str,
        days_count: float,
        reason: str | None = None,
        spot_reference: str | None = None,
        spot_diagnosis: str | None = None,
    ) -> dict:
        """Zahtevaj dopust ali bolniško. Preveri prekrivanje z obstoječimi dopusti."""
        from datetime import date as ddate
        d_from = ddate.fromisoformat(date_from)
        d_to = ddate.fromisoformat(date_to)
        if d_to < d_from:
            raise ValueError("date_to mora biti >= date_from")

        # Check for overlapping approved leaves
        overlap = await db.fetchrow(
            """
            SELECT id FROM leave_requests
            WHERE employee_id = $1::uuid
              AND status = 'approved'
              AND date_from <= $3 AND date_to >= $2
            LIMIT 1
            """,
            employee_id, d_from, d_to,
        )
        if overlap:
            raise ValueError(
                f"Zaposleni že ima odobreno odsotnost v tem obdobju ({date_from} – {date_to})"
            )

        rec = await db.fetchrow(
            """
            INSERT INTO leave_requests
                (employee_id, leave_type, date_from, date_to, days_count,
                 reason, spot_reference, spot_diagnosis)
            VALUES ($1::uuid,$2,$3,$4,$5,$6,$7,$8)
            RETURNING *
            """,
            employee_id, leave_type, d_from, d_to,
            Decimal(str(days_count)), reason, spot_reference, spot_diagnosis,
        )
        result = _serialise(dict(rec))
        await log_action(
            table_name="leave_requests",
            record_id=result["id"],
            operation="insert",
            new_values=result,
            agent_tool="create_leave_request",
        )
        return result

    @mcp.tool()
    async def approve_leave(
        leave_request_id: str,
        status: str,
        approved_by: str,
    ) -> dict:
        """Odobri ali zavrni zahtevo za odsotnost. status: 'approved' ali 'rejected'."""
        if status not in ("approved", "rejected"):
            raise ValueError("status mora biti 'approved' ali 'rejected'")

        old = await db.fetchrow(
            "SELECT * FROM leave_requests WHERE id = $1::uuid", leave_request_id
        )
        if old is None:
            raise ValueError(f"Zahteva za odsotnost {leave_request_id} ne obstaja")

        rec = await db.fetchrow(
            """
            UPDATE leave_requests
            SET status = $1, approved_by = $2::uuid, approved_at = NOW(), updated_at = NOW()
            WHERE id = $3::uuid
            RETURNING *
            """,
            status, approved_by, leave_request_id,
        )
        result = _serialise(dict(rec))
        await log_action(
            table_name="leave_requests",
            record_id=leave_request_id,
            operation="update",
            old_values=_serialise(dict(old)),
            new_values=result,
            agent_tool="approve_leave",
        )
        return result

    @mcp.tool()
    async def create_payroll_run(
        employee_id: str,
        period_month: int,
        period_year: int,
        bonus: float = 0.0,
        travel_allowance: float = 0.0,
    ) -> dict:
        """Ustvari nov obračun plače za zaposlenega (status='draft'). Pred tem preveri, da ni duplikata."""
        existing = await db.fetchrow(
            """
            SELECT id FROM payroll_runs
            WHERE employee_id = $1::uuid AND period_month = $2 AND period_year = $3
            """,
            employee_id, period_month, period_year,
        )
        if existing:
            raise ValueError(
                f"Obračun za {period_month}/{period_year} že obstaja. "
                f"Uporabi calculate_payroll({existing['id']}) za izračun."
            )

        emp = await db.fetchrow(
            "SELECT base_salary FROM employees WHERE id = $1::uuid AND is_active = TRUE",
            employee_id,
        )
        if emp is None:
            raise ValueError(f"Aktiven zaposleni z ID {employee_id} ne obstaja")

        rec = await db.fetchrow(
            """
            INSERT INTO payroll_runs
                (employee_id, period_month, period_year, base_salary, bonus, travel_allowance)
            VALUES ($1::uuid,$2,$3,$4,$5,$6)
            RETURNING *
            """,
            employee_id, period_month, period_year,
            emp["base_salary"],
            Decimal(str(bonus)),
            Decimal(str(travel_allowance)),
        )
        result = _serialise(dict(rec))
        await log_action(
            table_name="payroll_runs",
            record_id=result["id"],
            operation="insert",
            new_values=result,
            agent_tool="create_payroll_run",
        )
        return result
