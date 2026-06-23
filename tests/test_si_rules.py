"""Tests for Slovenian payroll rules — pure functions, no DB."""
from __future__ import annotations

from decimal import Decimal
from datetime import date

import pytest

from src.services.si_rules import (
    calculate_gross_to_net,
    calculate_progressive_tax,
    calculate_monthly_income_tax,
    calculate_daily_allowance,
    EMPLOYEE_CONTRIBUTION_RATE,
    EMPLOYER_CONTRIBUTION_RATE,
    DAILY_ALLOWANCE_FULL,
    DAILY_ALLOWANCE_HALF,
)


def test_contribution_rates():
    result = calculate_gross_to_net(Decimal("3000"))
    # 22.10 %
    assert float(result["employee_contributions"]) == round(3000 * 0.2210, 2)
    # 16.10 %
    assert float(result["employer_contributions"]) == round(3000 * 0.1610, 2)


def test_net_equals_gross_minus_deductions():
    result = calculate_gross_to_net(Decimal("3000"))
    expected_net = round(
        float(result["gross_salary"])
        - float(result["employee_contributions"])
        - float(result["income_tax"]),
        2,
    )
    assert abs(float(result["net_salary"]) - expected_net) < 0.01


def test_zero_salary():
    result = calculate_gross_to_net(Decimal("0"))
    assert result["gross_salary"] == 0
    assert result["net_salary"] == 0
    assert result["income_tax"] == 0


def test_progressive_tax_first_bracket():
    # Annual taxable 6000 € → entirely in 16 % bracket
    tax = calculate_progressive_tax(Decimal("6000"))
    assert tax == Decimal("960.00")


def test_progressive_tax_crosses_brackets():
    # 12000 € annual → 8500 * 0.16 + 3500 * 0.26
    expected = round(8500 * 0.16 + 3500 * 0.26, 2)
    tax = calculate_progressive_tax(Decimal("12000"))
    assert float(tax) == expected


def test_progressive_tax_top_bracket():
    # 100000 € — hand-verified: 8500*16%+18000*26%+26500*33%+22000*39%+25000*50%
    tax = calculate_progressive_tax(Decimal("100000"))
    assert tax == Decimal("35865.00")


def test_daily_allowance_one_day():
    d = date(2026, 3, 10)
    result = calculate_daily_allowance(d, d)
    assert result == DAILY_ALLOWANCE_HALF  # 10.70


def test_daily_allowance_two_days():
    result = calculate_daily_allowance(date(2026, 3, 10), date(2026, 3, 11))
    # 1 full day + half day = 21.39 + 10.70 = 32.09
    assert result == Decimal("32.09")


def test_daily_allowance_three_days():
    result = calculate_daily_allowance(date(2026, 3, 10), date(2026, 3, 12))
    # 2 full days + half day = 42.78 + 10.70 = 53.48
    assert result == Decimal("53.48")


def test_total_employer_cost():
    result = calculate_gross_to_net(Decimal("3000"))
    expected = round(3000 + 3000 * float(EMPLOYER_CONTRIBUTION_RATE), 2)
    assert abs(float(result["total_employer_cost"]) - expected) < 0.01


def test_bonus_added_to_gross():
    base = calculate_gross_to_net(Decimal("3000"))
    with_bonus = calculate_gross_to_net(Decimal("3000"), bonus=Decimal("500"))
    assert with_bonus["gross_salary"] == base["gross_salary"] + 500
