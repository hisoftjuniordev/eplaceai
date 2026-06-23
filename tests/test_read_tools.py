"""Read tool integration tests (requires DB)."""
from __future__ import annotations

import pytest
import src.database as db


@pytest.mark.asyncio
async def test_get_employee_by_id(pool, employee):
    from src.tools.read_tools import register
    from unittest.mock import MagicMock

    mcp = MagicMock()
    tools = {}

    def fake_tool():
        def decorator(fn):
            tools[fn.__name__] = fn
            return fn
        return decorator

    mcp.tool = fake_tool
    register(mcp)

    result = await tools["get_employee"](employee_id=str(employee["id"]))
    assert result is not None
    assert result["first_name"] == "Ana"
    assert result["last_name"] == "Kovač"


@pytest.mark.asyncio
async def test_get_employee_by_emso(pool, employee):
    from src.tools.read_tools import register
    from unittest.mock import MagicMock

    mcp = MagicMock()
    tools = {}

    def fake_tool():
        def decorator(fn):
            tools[fn.__name__] = fn
            return fn
        return decorator

    mcp.tool = fake_tool
    register(mcp)

    result = await tools["get_employee"](emso="0101990500006")
    assert result is not None
    assert result["id"] == str(employee["id"])


@pytest.mark.asyncio
async def test_get_employee_not_found(pool, employee):
    from src.tools.read_tools import register
    from unittest.mock import MagicMock

    mcp = MagicMock()
    tools = {}

    def fake_tool():
        def decorator(fn):
            tools[fn.__name__] = fn
            return fn
        return decorator

    mcp.tool = fake_tool
    register(mcp)

    result = await tools["get_employee"](employee_id="00000000-0000-0000-0000-000000000000")
    assert result is None


@pytest.mark.asyncio
async def test_list_employees_filter_department(pool, employee):
    from src.tools.read_tools import register
    from unittest.mock import MagicMock

    mcp = MagicMock()
    tools = {}

    def fake_tool():
        def decorator(fn):
            tools[fn.__name__] = fn
            return fn
        return decorator

    mcp.tool = fake_tool
    register(mcp)

    results = await tools["list_employees"](department="IT")
    assert len(results) == 1
    assert results[0]["department"] == "IT"

    results_hr = await tools["list_employees"](department="HR")
    assert len(results_hr) == 0


@pytest.mark.asyncio
async def test_get_employee_balance_empty(pool, employee):
    from src.tools.read_tools import register
    from unittest.mock import MagicMock

    mcp = MagicMock()
    tools = {}

    def fake_tool():
        def decorator(fn):
            tools[fn.__name__] = fn
            return fn
        return decorator

    mcp.tool = fake_tool
    register(mcp)

    balance = await tools["get_employee_balance"](employee_id=str(employee["id"]))
    assert isinstance(balance, dict)
    assert balance == {}


@pytest.mark.asyncio
async def test_get_payroll_summary(pool, employee, payroll_run):
    from src.tools.read_tools import register
    from unittest.mock import MagicMock

    mcp = MagicMock()
    tools = {}

    def fake_tool():
        def decorator(fn):
            tools[fn.__name__] = fn
            return fn
        return decorator

    mcp.tool = fake_tool
    register(mcp)

    summary = await tools["get_payroll_summary"](period_month=3, period_year=2026)
    # Draft runs are not excluded from summary (only 'cancelled' are)
    assert summary["employee_count"] == 1
