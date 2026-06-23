from __future__ import annotations

from datetime import date, datetime
from pydantic import BaseModel, model_validator

VALID_TRANSPORT = {"personal_car", "public", "company"}
VALID_STATUSES = {"draft", "approved", "rejected", "settled"}


class TravelOrderCreate(BaseModel):
    employee_id: str
    destination: str
    date_from: date
    date_to: date
    purpose: str | None = None
    transport_type: str | None = None
    km_total: float | None = None
    accommodation: float = 0.0

    @model_validator(mode="after")
    def dates_valid(self) -> "TravelOrderCreate":
        if self.date_to < self.date_from:
            raise ValueError("date_to mora biti >= date_from")
        return self

    @model_validator(mode="after")
    def transport_valid(self) -> "TravelOrderCreate":
        if self.transport_type is not None and self.transport_type not in VALID_TRANSPORT:
            raise ValueError(f"transport_type mora biti eden od: {', '.join(VALID_TRANSPORT)}")
        return self


class TravelOrderOut(BaseModel):
    id: str
    employee_id: str
    destination: str
    purpose: str | None
    date_from: date
    date_to: date
    transport_type: str | None
    km_total: float | None
    daily_allowance: float | None
    accommodation: float
    status: str
    approved_by: str | None
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime
