from __future__ import annotations

from datetime import date, datetime
from pydantic import BaseModel, model_validator

VALID_TYPES = {"annual", "sick", "unpaid", "maternity", "paternity", "other"}
VALID_STATUSES = {"pending", "approved", "rejected", "cancelled"}


class LeaveRequestCreate(BaseModel):
    employee_id: str
    leave_type: str
    date_from: date
    date_to: date
    days_count: float
    reason: str | None = None
    spot_reference: str | None = None
    spot_diagnosis: str | None = None

    @model_validator(mode="after")
    def validate_all(self) -> "LeaveRequestCreate":
        if self.leave_type not in VALID_TYPES:
            raise ValueError(f"leave_type mora biti eden od: {', '.join(VALID_TYPES)}")
        if self.date_to < self.date_from:
            raise ValueError("date_to mora biti >= date_from")
        if self.days_count <= 0:
            raise ValueError("days_count mora biti pozitiven")
        return self


class LeaveRequestOut(BaseModel):
    id: str
    employee_id: str
    leave_type: str
    date_from: date
    date_to: date
    days_count: float
    reason: str | None
    spot_reference: str | None
    spot_diagnosis: str | None
    status: str
    approved_by: str | None
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime
