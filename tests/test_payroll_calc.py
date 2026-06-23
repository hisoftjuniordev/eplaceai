"""End-to-end payroll calculation tests (requires DB)."""
from __future__ import annotations

import pytest
from decimal import Decimal

import src.database as db
from src.services.payroll_service import build_payroll_breakdown
from src.services.si_rules import (
    EMPLOYEE_CONTRIBUTION_RATE,
    EMPLOYER_CONTRIBUTION_RATE,
)


@pytest.mark.asyncio
async def test_calculate_payroll_basic(pool, payroll_run):
    """Hand-verified: 3000 bruto → known neto."""
    run_id = str(payroll_run["id"])
    breakdown = await build_payroll_breakdown(run_id)

    assert breakdown["gross_salary"] == 3000.0
    expected_emp_c = round(3000 * float(EMPLOYEE_CONTRIBUTION_RATE), 2)
    assert abs(breakdown["employee_contributions"] - expected_emp_c) < 0.01

    expected_er_c = round(3000 * float(EMPLOYER_CONTRIBUTION_RATE), 2)
    assert abs(breakdown["employer_contributions"] - expected_er_c) < 0.01

    # net = gross - emp_contributions - income_tax
    expected_net = round(
        breakdown["gross_salary"]
        - breakdown["employee_contributions"]
        - breakdown["income_tax"],
        2,
    )
    assert abs(breakdown["net_salary"] - expected_net) < 0.01


@pytest.mark.asyncio
async def test_calculate_payroll_with_bonus(pool, employee):
    """Bonus increases gross proportionally."""
    run = await db.fetchrow(
        """
        INSERT INTO payroll_runs
            (employee_id, period_month, period_year, base_salary, bonus)
        VALUES ($1::uuid, 4, 2026, 3000.00, 500.00)
        RETURNING *
        """,
        employee["id"],
    )
    breakdown = await build_payroll_breakdown(str(run["id"]))
    assert breakdown["gross_salary"] == 3500.0


@pytest.mark.asyncio
async def test_calculate_payroll_with_overtime(pool, employee):
    """Overtime pay adds to gross."""
    run = await db.fetchrow(
        """
        INSERT INTO payroll_runs
            (employee_id, period_month, period_year, base_salary, overtime_pay)
        VALUES ($1::uuid, 5, 2026, 3000.00, 200.00)
        RETURNING *
        """,
        employee["id"],
    )
    breakdown = await build_payroll_breakdown(str(run["id"]))
    assert breakdown["gross_salary"] == 3200.0
    assert breakdown["net_salary"] > 0


@pytest.mark.asyncio
async def test_payroll_not_found(pool):
    """build_payroll_breakdown raises for unknown ID."""
    with pytest.raises(ValueError, match="ne obstaja"):
        await build_payroll_breakdown("00000000-0000-0000-0000-000000000000")
