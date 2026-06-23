from __future__ import annotations

from datetime import date, datetime, time
from pydantic import BaseModel, field_validator

VALID_STATUSES = {"present", "absent", "sick", "leave", "travel", "unexcused"}


class AttendanceCreate(BaseModel):
    employee_id: str
    date: date
    clock_in: time | None = None
    clock_out: time | None = None
    hours_worked: float | None = None
    hours_overtime: float = 0.0
    hours_night: float = 0.0
    hours_weekend: float = 0.0
    hours_holiday: float = 0.0
    status: str = "present"
    notes: str | None = None

    @field_validator("status")
    @classmethod
    def valid_status(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(f"status mora biti eden od: {', '.join(VALID_STATUSES)}")
        return v


class AttendanceOut(BaseModel):
    id: str
    employee_id: str
    date: date
    clock_in: time | None
    clock_out: time | None
    hours_worked: float | None
    hours_overtime: float
    hours_night: float
    hours_weekend: float
    hours_holiday: float
    status: str
    notes: str | None
    created_at: datetime
