"""Slovenska plačilna pravila 2026.

Vse stopnje so zbrane tukaj — posodobi samo to datoteko ko se zakonodaja spremeni.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

# ── Prispevki ─────────────────────────────────────────────────────────────────
EMPLOYEE_CONTRIBUTION_RATE = Decimal("0.2210")   # 22.10 %
EMPLOYER_CONTRIBUTION_RATE = Decimal("0.1610")   # 16.10 %

# ── Dohodninske lestvice (letna osnova, mejna stopnja) ────────────────────────
# (zgornja_meja_EUR | None za zadnji razred, stopnja)
INCOME_TAX_BRACKETS: list[tuple[Decimal | None, Decimal]] = [
    (Decimal("8500"),  Decimal("0.16")),
    (Decimal("26500"), Decimal("0.26")),
    (Decimal("53000"), Decimal("0.33")),
    (Decimal("75000"), Decimal("0.39")),
    (None,             Decimal("0.50")),
]

# ── Potni nalogi — dnevnice (Uredba o povračilu stroškov, 2026) ───────────────
DAILY_ALLOWANCE_FULL = Decimal("21.39")   # 100 % (12–24 ur ali > 24 ur)
DAILY_ALLOWANCE_HALF = Decimal("10.70")  # 50 % polne dnevnice, zaokroženo
KM_RATE_PERSONAL_CAR = Decimal("0.37")   # € / km za osebni avto

# ── Bolniška nadomestila ──────────────────────────────────────────────────────
SICK_PAY_EMPLOYER_RATE = Decimal("0.80")  # 80 % osnove, 1.–30. dan

# ── Dodatki k urni postavki ───────────────────────────────────────────────────
OVERTIME_SUPPLEMENT = Decimal("0.30")    # +30 % nad osnovo
NIGHT_SUPPLEMENT    = Decimal("0.30")    # +30 %
WEEKEND_SUPPLEMENT  = Decimal("0.50")    # +50 %
HOLIDAY_SUPPLEMENT  = Decimal("0.50")    # +50 %


def _round2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_progressive_tax(annual_taxable: Decimal) -> Decimal:
    """Izračunaj letno dohodnino po progresivnih lestvicah."""
    tax = Decimal("0")
    previous_limit = Decimal("0")

    for upper, rate in INCOME_TAX_BRACKETS:
        if upper is None:
            taxable_in_bracket = annual_taxable - previous_limit
        else:
            taxable_in_bracket = min(annual_taxable, upper) - previous_limit

        if taxable_in_bracket <= 0:
            break

        tax += taxable_in_bracket * rate
        if upper is not None:
            previous_limit = upper

    return _round2(tax)


def calculate_monthly_income_tax(monthly_gross: Decimal) -> Decimal:
    """Akontacija dohodnine za en mesec (letna osnova / 12)."""
    # Osnova za dohodnino = bruto − prispevki zaposlenega
    monthly_contributions = _round2(monthly_gross * EMPLOYEE_CONTRIBUTION_RATE)
    monthly_taxable = monthly_gross - monthly_contributions
    annual_taxable = monthly_taxable * 12
    annual_tax = calculate_progressive_tax(annual_taxable)
    return _round2(annual_tax / 12)


def calculate_gross_to_net(
    base_salary: Decimal,
    overtime_pay: Decimal = Decimal("0"),
    night_pay: Decimal = Decimal("0"),
    weekend_pay: Decimal = Decimal("0"),
    holiday_pay: Decimal = Decimal("0"),
    travel_allowance: Decimal = Decimal("0"),
    leave_pay: Decimal = Decimal("0"),
    sick_pay: Decimal = Decimal("0"),
    bonus: Decimal = Decimal("0"),
) -> dict[str, Decimal]:
    """Izračunaj bruto → neto razčlenitev po slovenskih predpisih."""
    gross = _round2(
        base_salary + overtime_pay + night_pay + weekend_pay + holiday_pay
        + travel_allowance + leave_pay + sick_pay + bonus
    )
    employee_contributions = _round2(gross * EMPLOYEE_CONTRIBUTION_RATE)
    employer_contributions = _round2(gross * EMPLOYER_CONTRIBUTION_RATE)
    taxable_base = gross - employee_contributions
    income_tax = calculate_monthly_income_tax(gross)
    net = _round2(taxable_base - income_tax)
    total_cost = _round2(gross + employer_contributions)

    return {
        "gross_salary": gross,
        "employee_contributions": employee_contributions,
        "employer_contributions": employer_contributions,
        "taxable_base": taxable_base,
        "income_tax": income_tax,
        "net_salary": net,
        "total_employer_cost": total_cost,
    }


def calculate_daily_allowance(date_from: date, date_to: date) -> Decimal:
    """Izračunaj skupno dnevnico za potni nalog."""
    days = (date_to - date_from).days + 1
    if days <= 0:
        return Decimal("0")
    # Zadnji dan se šteje kot < 12 ur (polovična dnevnica)
    if days == 1:
        return _round2(DAILY_ALLOWANCE_HALF)
    full_days = days - 1
    return _round2(full_days * DAILY_ALLOWANCE_FULL + DAILY_ALLOWANCE_HALF)
