from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, field_validator


class EmployeeCreate(BaseModel):
    first_name: str
    last_name: str
    hire_date: date
    base_salary: float
    emso: str | None = None
    davcna_stevilka: str | None = None
    date_of_birth: date | None = None
    address: str | None = None
    city: str | None = None
    postal_code: str | None = None
    country_code: str = "SI"
    phone: str | None = None
    email: str | None = None
    department: str | None = None
    job_title: str | None = None
    employment_type: str | None = None  # PDI / DP / SP / NAP
    contract_hours: float = 40.0
    tax_card: dict[str, Any] | None = None
    bank_account: str | None = None

    @field_validator("employment_type")
    @classmethod
    def valid_employment_type(cls, v: str | None) -> str | None:
        if v is not None and v not in ("PDI", "DP", "SP", "NAP"):
            raise ValueError("employment_type mora biti eden od: PDI, DP, SP, NAP")
        return v

    @field_validator("base_salary")
    @classmethod
    def positive_salary(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("base_salary mora biti pozitivna")
        return v


class EmployeeUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    emso: str | None = None
    davcna_stevilka: str | None = None
    date_of_birth: date | None = None
    address: str | None = None
    city: str | None = None
    postal_code: str | None = None
    phone: str | None = None
    email: str | None = None
    department: str | None = None
    job_title: str | None = None
    hire_date: date | None = None
    termination_date: date | None = None
    employment_type: str | None = None
    contract_hours: float | None = None
    base_salary: float | None = None
    tax_card: dict[str, Any] | None = None
    is_active: bool | None = None
    bank_account: str | None = None


class EmployeeOut(BaseModel):
    id: str
    first_name: str
    last_name: str
    emso: str | None
    davcna_stevilka: str | None
    date_of_birth: date | None
    address: str | None
    city: str | None
    postal_code: str | None
    country_code: str
    phone: str | None
    email: str | None
    department: str | None
    job_title: str | None
    hire_date: date
    termination_date: date | None
    employment_type: str | None
    contract_hours: float
    base_salary: float
    tax_card: dict[str, Any] | None
    is_active: bool
    bank_account: str | None
    created_at: datetime
    updated_at: datetime
