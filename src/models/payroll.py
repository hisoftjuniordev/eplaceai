from __future__ import annotations

from datetime import datetime
from typing import Any
from pydantic import BaseModel, field_validator


class PayrollRunCreate(BaseModel):
    employee_id: str
    period_month: int
    period_year: int
    bonus: float = 0.0
    travel_allowance: float = 0.0

    @field_validator("period_month")
    @classmethod
    def valid_month(cls, v: int) -> int:
        if not 1 <= v <= 12:
            raise ValueError("period_month mora biti med 1 in 12")
        return v

    @field_validator("period_year")
    @classmethod
    def valid_year(cls, v: int) -> int:
        if v < 2020:
            raise ValueError("period_year mora biti >= 2020")
        return v


class PayrollRunOut(BaseModel):
    id: str
    employee_id: str
    period_month: int
    period_year: int
    base_salary: float
    overtime_pay: float
    night_pay: float
    weekend_pay: float
    holiday_pay: float
    travel_allowance: float
    leave_pay: float
    sick_pay: float
    bonus: float
    deductions: dict[str, Any] | None
    gross_salary: float | None
    net_salary: float | None
    employee_contributions: float | None
    employer_contributions: float | None
    income_tax: float | None
    status: str
    rek1_exported: bool
    edavki_sent: bool
    created_at: datetime
    updated_at: datetime
