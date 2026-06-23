"""Shared pytest fixtures — asyncpg pool against a test database.

DB fixtures (raw_pool, pool, employee, payroll_run) are NOT autouse.
Pure unit tests (test_si_rules) never touch the DB.
"""
from __future__ import annotations

import os
import pytest_asyncio
import asyncpg
from pathlib import Path

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/si_payroll_test",
)

SCHEMA_PATH = Path(__file__).parent.parent / "schema" / "init.sql"


@pytest_asyncio.fixture(scope="session")
async def raw_pool():
    """Create test DB and schema once per session."""
    base_url = TEST_DB_URL.rsplit("/", 1)[0] + "/postgres"
    try:
        conn = await asyncpg.connect(base_url)
        await conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = 'si_payroll_test' AND pid <> pg_backend_pid()"
        )
        await conn.execute("DROP DATABASE IF EXISTS si_payroll_test")
        await conn.execute("CREATE DATABASE si_payroll_test")
        await conn.close()
    except Exception:
        pass

    pool = await asyncpg.create_pool(dsn=TEST_DB_URL, min_size=1, max_size=5)
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    async with pool.acquire() as conn:
        await conn.execute(schema_sql)
    yield pool
    await pool.close()


@pytest_asyncio.fixture()
async def pool(raw_pool, monkeypatch):
    """Patch src.database._pool and truncate all tables before each DB test."""
    import src.database as database
    monkeypatch.setattr(database, "_pool", raw_pool)

    async with raw_pool.acquire() as conn:
        await conn.execute(
            "TRUNCATE migration_log, payroll_runs, leave_requests, "
            "travel_orders, attendance, employees RESTART IDENTITY CASCADE"
        )
    return raw_pool


@pytest_asyncio.fixture()
async def employee(pool):
    """Insert and return a basic test employee."""
    import src.database as db

    rec = await db.fetchrow(
        """
        INSERT INTO employees (first_name, last_name, hire_date, base_salary, emso,
                               department, email)
        VALUES ('Ana', 'Kovač', '2020-01-01', 3000.00, '0101990500011',
                'IT', 'ana.kovac@test.si')
        RETURNING *
        """,
    )
    return dict(rec)


@pytest_asyncio.fixture()
async def payroll_run(pool, employee):
    """Insert a draft payroll run for the test employee."""
    import src.database as db

    rec = await db.fetchrow(
        """
        INSERT INTO payroll_runs (employee_id, period_month, period_year, base_salary)
        VALUES ($1::uuid, 3, 2026, 3000.00)
        RETURNING *
        """,
        employee["id"],
    )
    return dict(rec)
