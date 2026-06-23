"""Write tool integration tests (requires DB)."""
from __future__ import annotations

import pytest
import src.database as db
from src.validators.emso_validator import validate_emso
from src.validators.input_validators import validate_iban


# ── EMŠO validator unit tests ─────────────────────────────────────────────────

def test_emso_valid():
    # Known valid EMŠO (checksum verified)
    assert validate_emso("0101990500011") == "0101990500011"


def test_emso_wrong_length():
    with pytest.raises(ValueError, match="13"):
        validate_emso("123456789")


def test_emso_non_numeric():
    with pytest.raises(ValueError):
        validate_emso("010199050000A")


def test_emso_bad_checksum():
    with pytest.raises(ValueError, match="kontrolna cifra"):
        validate_emso("0101990500019")  # wrong last digit (correct is 1)


# ── IBAN validator unit tests ─────────────────────────────────────────────────

def test_iban_valid_si():
    # Valid Slovenian IBAN
    iban = "SI56020360253863406"
    assert validate_iban(iban) == iban


def test_iban_invalid():
    with pytest.raises(ValueError):
        validate_iban("SI56INVALID0000000")


# ── create_employee integration ───────────────────────────────────────────────

def _make_tools(module_name):
    from unittest.mock import MagicMock
    import importlib
    module = importlib.import_module(module_name)
    mcp = MagicMock()
    tools = {}

    def fake_tool():
        def decorator(fn):
            tools[fn.__name__] = fn
            return fn
        return decorator

    mcp.tool = fake_tool
    module.register(mcp)
    return tools


@pytest.mark.asyncio
async def test_create_employee_success(pool):
    tools = _make_tools("src.tools.write_tools")
    result = await tools["create_employee"](
        first_name="Janez",
        last_name="Novak",
        hire_date="2025-01-01",
        base_salary=2800.0,
        emso="0101990500011",
        department="Finance",
    )
    assert result["first_name"] == "Janez"
    assert result["id"] is not None

    # Audit log entry must exist
    log = await db.fetchrow(
        "SELECT * FROM migration_log WHERE record_id = $1::uuid",
        result["id"],
    )
    assert log is not None
    assert log["operation"] == "insert"
    assert log["agent_tool"] == "create_employee"


@pytest.mark.asyncio
async def test_create_employee_invalid_emso(pool):
    tools = _make_tools("src.tools.write_tools")
    with pytest.raises(ValueError, match="kontrolna cifra"):
        await tools["create_employee"](
            first_name="Bad",
            last_name="Emso",
            hire_date="2025-01-01",
            base_salary=2000.0,
            emso="0101990500009",
        )


@pytest.mark.asyncio
async def test_create_leave_overlap_blocked(pool, employee):
    """Creating overlapping approved leaves must fail."""
    tools = _make_tools("src.tools.write_tools")

    leave = await tools["create_leave_request"](
        employee_id=str(employee["id"]),
        leave_type="annual",
        date_from="2026-07-01",
        date_to="2026-07-10",
        days_count=8,
    )

    # Approve it
    await tools["approve_leave"](
        leave_request_id=leave["id"],
        status="approved",
        approved_by=str(employee["id"]),
    )

    # Try overlapping leave — must raise
    with pytest.raises(ValueError, match="že ima odobreno odsotnost"):
        await tools["create_leave_request"](
            employee_id=str(employee["id"]),
            leave_type="annual",
            date_from="2026-07-05",
            date_to="2026-07-15",
            days_count=7,
        )


@pytest.mark.asyncio
async def test_create_payroll_run_no_duplicate(pool, employee, payroll_run):
    """Second payroll run for same period must fail."""
    tools = _make_tools("src.tools.write_tools")
    with pytest.raises(ValueError, match="že obstaja"):
        await tools["create_payroll_run"](
            employee_id=str(employee["id"]),
            period_month=3,
            period_year=2026,
        )


@pytest.mark.asyncio
async def test_update_employee_captures_audit(pool, employee):
    """update_employee must log old and new values."""
    tools = _make_tools("src.tools.write_tools")
    result = await tools["update_employee"](
        employee_id=str(employee["id"]),
        department="HR",
    )
    assert result["department"] == "HR"

    log = await db.fetchrow(
        "SELECT * FROM migration_log WHERE record_id = $1::uuid AND operation = 'update'",
        employee["id"],
    )
    assert log is not None
    import json
    old = json.loads(log["old_values"])
    new = json.loads(log["new_values"])
    assert old["department"] == "IT"
    assert new["department"] == "HR"
