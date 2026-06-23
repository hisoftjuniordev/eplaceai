"""Audit logger — writes every mutation to migration_log."""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import src.database as db


def _json_default(obj: Any) -> Any:
    if isinstance(obj, UUID):
        return str(obj)
    from datetime import date, time, datetime
    from decimal import Decimal
    if isinstance(obj, (date, time, datetime)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serialisable")


async def log_action(
    *,
    table_name: str,
    record_id: str,
    operation: str,               # insert / update / delete
    old_values: dict | None = None,
    new_values: dict | None = None,
    performed_by: str = "agent",
    agent_tool: str,
) -> None:
    await db.execute(
        """
        INSERT INTO migration_log
            (table_name, record_id, operation, old_values, new_values, performed_by, agent_tool)
        VALUES ($1, $2::uuid, $3, $4, $5, $6, $7)
        """,
        table_name,
        record_id,
        operation,
        json.dumps(old_values, default=_json_default) if old_values is not None else None,
        json.dumps(new_values, default=_json_default) if new_values is not None else None,
        performed_by,
        agent_tool,
    )
