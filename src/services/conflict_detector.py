"""Detects scheduling conflicts between attendance, leave, and travel records."""
from __future__ import annotations

from typing import Any

import src.database as db


async def find_conflicts(
    employee_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict[str, Any]]:
    """Find scheduling conflicts for one or all employees in a date range."""
    conflicts: list[dict] = []

    # ── 1. Travel order overlaps with approved leave ───────────────────────────
    cond_travel = ""
    args_travel: list = []
    if employee_id:
        cond_travel = "AND to_.employee_id = $1::uuid"
        args_travel.append(employee_id)
    if date_from:
        cond_travel += f" AND to_.date_from >= ${len(args_travel)+1}"
        args_travel.append(date_from)
    if date_to:
        cond_travel += f" AND to_.date_to <= ${len(args_travel)+1}"
        args_travel.append(date_to)

    travel_leave_rows = await db.fetch(
        f"""
        SELECT
            e.first_name || ' ' || e.last_name AS employee,
            to_.destination,
            to_.date_from AS travel_from,
            to_.date_to   AS travel_to,
            lr.leave_type,
            lr.date_from  AS leave_from,
            lr.date_to    AS leave_to
        FROM travel_orders to_
        JOIN employees e ON e.id = to_.employee_id
        JOIN leave_requests lr
          ON lr.employee_id = to_.employee_id
         AND lr.status = 'approved'
         AND lr.date_from <= to_.date_to
         AND lr.date_to   >= to_.date_from
        WHERE to_.status != 'cancelled'
        {cond_travel}
        """,
        *args_travel,
    )
    for r in travel_leave_rows:
        conflicts.append({
            "type": "travel_leave_overlap",
            "employee": r["employee"],
            "detail": (
                f"Potni nalog v {r['destination']} ({r['travel_from']} – {r['travel_to']}) "
                f"se prekriva z {r['leave_type']} odsotnostjo "
                f"({r['leave_from']} – {r['leave_to']})"
            ),
        })

    # ── 2. Attendance marked present but leave is approved ─────────────────────
    cond_att = ""
    args_att: list = []
    if employee_id:
        cond_att = "AND a.employee_id = $1::uuid"
        args_att.append(employee_id)
    if date_from:
        cond_att += f" AND a.date >= ${len(args_att)+1}"
        args_att.append(date_from)
    if date_to:
        cond_att += f" AND a.date <= ${len(args_att)+1}"
        args_att.append(date_to)

    att_leave_rows = await db.fetch(
        f"""
        SELECT
            e.first_name || ' ' || e.last_name AS employee,
            a.date,
            a.status AS attendance_status,
            lr.leave_type
        FROM attendance a
        JOIN employees e ON e.id = a.employee_id
        JOIN leave_requests lr
          ON lr.employee_id = a.employee_id
         AND lr.status = 'approved'
         AND a.date BETWEEN lr.date_from AND lr.date_to
        WHERE a.status = 'present'
        {cond_att}
        """,
        *args_att,
    )
    for r in att_leave_rows:
        conflicts.append({
            "type": "attendance_leave_mismatch",
            "employee": r["employee"],
            "detail": (
                f"Evidenca kaže prisotnost dne {r['date']}, "
                f"vendar je odobren {r['leave_type']} dopust"
            ),
        })

    return conflicts
