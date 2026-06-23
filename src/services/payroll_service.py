"""Payroll calculation service — ties attendance data to si_rules."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

import src.database as db
from src.services.si_rules import calculate_gross_to_net


async def build_payroll_breakdown(payroll_run_id: str) -> dict[str, Any]:
    """Load a payroll_run row and compute gross→net. Returns the full breakdown dict."""
    run = await db.fetchrow(
        "SELECT * FROM payroll_runs WHERE id = $1::uuid", payroll_run_id
    )
    if run is None:
        raise ValueError(f"Obračun {payroll_run_id} ne obstaja")

    def d(col: str) -> Decimal:
        v = run[col]
        return Decimal(str(v)) if v is not None else Decimal("0")

    result = calculate_gross_to_net(
        base_salary=d("base_salary"),
        overtime_pay=d("overtime_pay"),
        night_pay=d("night_pay"),
        weekend_pay=d("weekend_pay"),
        holiday_pay=d("holiday_pay"),
        travel_allowance=d("travel_allowance"),
        leave_pay=d("leave_pay"),
        sick_pay=d("sick_pay"),
        bonus=d("bonus"),
    )
    return {k: float(v) for k, v in result.items()}
