"""Workflow MCP tools — payroll calculation, export, validation, conflict detection."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from mcp.server.fastmcp import FastMCP

import src.database as db
from src.audit.logger import log_action
from src.services import conflict_detector, edavki_service, payroll_service
from src.services.si_rules import EMPLOYEE_CONTRIBUTION_RATE, EMPLOYER_CONTRIBUTION_RATE


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
    async def calculate_payroll(payroll_run_id: str) -> dict:
        """Izračunaj bruto → neto plačo za obstoječ obračun. Status se nastavi na 'calculated'."""
        run = await db.fetchrow(
            "SELECT * FROM payroll_runs WHERE id = $1::uuid", payroll_run_id
        )
        if run is None:
            raise ValueError(f"Obračun {payroll_run_id} ne obstaja")
        if run["status"] not in ("draft", "calculated"):
            raise ValueError(
                f"Obračun je v statusu '{run['status']}' in ga ni mogoče ponovno izračunati"
            )

        breakdown = await payroll_service.build_payroll_breakdown(payroll_run_id)

        old = _serialise(dict(run))
        await db.execute(
            """
            UPDATE payroll_runs SET
                gross_salary           = $1,
                net_salary             = $2,
                employee_contributions = $3,
                employer_contributions = $4,
                income_tax             = $5,
                deductions             = $6::jsonb,
                status                 = 'calculated',
                updated_at             = NOW()
            WHERE id = $7::uuid
            """,
            breakdown["gross_salary"],
            breakdown["net_salary"],
            breakdown["employee_contributions"],
            breakdown["employer_contributions"],
            breakdown["income_tax"],
            f'{{"employee_contributions": {breakdown["employee_contributions"]}, '
            f'"income_tax": {breakdown["income_tax"]}}}',
            payroll_run_id,
        )

        updated = await db.fetchrow(
            "SELECT * FROM payroll_runs WHERE id = $1::uuid", payroll_run_id
        )
        result = _serialise(dict(updated))
        await log_action(
            table_name="payroll_runs",
            record_id=payroll_run_id,
            operation="update",
            old_values=old,
            new_values=result,
            agent_tool="calculate_payroll",
        )
        return {**result, "breakdown": breakdown}

    @mcp.tool()
    async def generate_payslip(payroll_run_id: str) -> dict:
        """Generiraj plačilno listo v JSON formatu (PDF ni podprt v v1)."""
        run = await db.fetchrow(
            """
            SELECT pr.*, e.first_name, e.last_name, e.department, e.job_title,
                   e.bank_account, e.employment_type
            FROM payroll_runs pr
            JOIN employees e ON e.id = pr.employee_id
            WHERE pr.id = $1::uuid
            """,
            payroll_run_id,
        )
        if run is None:
            raise ValueError(f"Obračun {payroll_run_id} ne obstaja")
        if run["status"] == "draft":
            raise ValueError("Najprej izračunaj plačo z calculate_payroll()")

        def f(col: str) -> float:
            v = run[col]
            return float(v) if v is not None else 0.0

        return {
            "payslip": {
                "period": f"{run['period_month']:02d}/{run['period_year']}",
                "employee": {
                    "name": f"{run['first_name']} {run['last_name']}",
                    "department": run["department"],
                    "job_title": run["job_title"],
                    "bank_account": run["bank_account"],
                    "employment_type": run["employment_type"],
                },
                "earnings": {
                    "base_salary": f("base_salary"),
                    "overtime_pay": f("overtime_pay"),
                    "night_pay": f("night_pay"),
                    "weekend_pay": f("weekend_pay"),
                    "holiday_pay": f("holiday_pay"),
                    "travel_allowance": f("travel_allowance"),
                    "leave_pay": f("leave_pay"),
                    "sick_pay": f("sick_pay"),
                    "bonus": f("bonus"),
                    "gross_salary": f("gross_salary"),
                },
                "deductions": {
                    "employee_contributions_22_10pct": f("employee_contributions"),
                    "income_tax_akontacija": f("income_tax"),
                },
                "net_salary": f("net_salary"),
                "employer_cost": {
                    "gross_salary": f("gross_salary"),
                    "employer_contributions_16_10pct": f("employer_contributions"),
                    "total": round(f("gross_salary") + f("employer_contributions"), 2),
                },
                "status": run["status"],
            }
        }

    @mcp.tool()
    async def export_rek1(period_month: int, period_year: int) -> dict:
        """Pripravi REK-1 XML datoteko za oddajo na eDavki portal."""
        count = await db.fetchval(
            """
            SELECT COUNT(*) FROM payroll_runs
            WHERE period_month = $1 AND period_year = $2
              AND status IN ('calculated', 'confirmed', 'paid')
            """,
            period_month, period_year,
        )
        if not count:
            raise ValueError(
                f"Ni izračunanih obračunov za {period_month}/{period_year}. "
                "Najprej izračunaj plače z calculate_payroll()."
            )

        out_path = await edavki_service.build_rek1_xml(period_month, period_year)
        return {
            "status": "success",
            "file": str(out_path),
            "records": count,
            "period": f"{period_month:02d}/{period_year}",
            "note": "Datoteko ročno naloži na https://edavki.durs.si/",
        }

    @mcp.tool()
    async def export_edavki(period_month: int, period_year: int) -> dict:
        """Alias za export_rek1 — pripravi REK-1 datoteko za eDavki."""
        return await export_rek1(period_month, period_year)

    @mcp.tool()
    async def detect_conflicts(
        employee_id: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict]:
        """Poišči neskladja med evidenco prisotnosti, dopusti in potnimi nalogi."""
        return await conflict_detector.find_conflicts(
            employee_id=employee_id,
            date_from=date_from,
            date_to=date_to,
        )

    @mcp.tool()
    async def validate_payroll(payroll_run_id: str) -> dict:
        """Validiraj obračun pred potrditvijo — preveri matematično pravilnost in manjkajoče vrednosti."""
        run = await db.fetchrow(
            "SELECT * FROM payroll_runs WHERE id = $1::uuid", payroll_run_id
        )
        if run is None:
            raise ValueError(f"Obračun {payroll_run_id} ne obstaja")

        errors: list[str] = []
        warnings: list[str] = []

        if run["status"] == "draft":
            errors.append("Obračun še ni izračunan — pokliči calculate_payroll() najprej")

        required_fields = ["gross_salary", "net_salary", "employee_contributions",
                           "employer_contributions", "income_tax"]
        for field in required_fields:
            if run[field] is None:
                errors.append(f"Manjka vrednost za '{field}'")

        if not errors:
            gross = float(run["gross_salary"])
            emp_c = float(run["employee_contributions"])
            er_c  = float(run["employer_contributions"])
            tax   = float(run["income_tax"])
            net   = float(run["net_salary"])

            expected_emp_c = round(gross * float(EMPLOYEE_CONTRIBUTION_RATE), 2)
            expected_er_c  = round(gross * float(EMPLOYER_CONTRIBUTION_RATE), 2)

            if abs(emp_c - expected_emp_c) > 0.02:
                errors.append(
                    f"Prispevki zaposlenega ({emp_c}) ne ustrezajo stopnji 22.10% "
                    f"(pričakovano {expected_emp_c})"
                )
            if abs(er_c - expected_er_c) > 0.02:
                errors.append(
                    f"Prispevki delodajalca ({er_c}) ne ustrezajo stopnji 16.10% "
                    f"(pričakovano {expected_er_c})"
                )

            expected_net = round(gross - emp_c - tax, 2)
            if abs(net - expected_net) > 0.02:
                warnings.append(
                    f"Neto plača ({net}) se razlikuje od pričakovane vrednosti ({expected_net})"
                )

            if net < 0:
                errors.append("Neto plača je negativna — preveri odbitke")

        return {
            "payroll_run_id": payroll_run_id,
            "status": run["status"],
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }
