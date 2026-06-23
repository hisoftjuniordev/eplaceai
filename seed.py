"""Seed the si_payroll database with realistic Slovenian test data.

Run: python seed.py
"""
from __future__ import annotations

import asyncio
import asyncpg
from decimal import Decimal
from pathlib import Path

DB_URL = "postgresql://postgres:password@localhost:5432/si_payroll"

# All EMŠOs are checksum-verified
EMPLOYEES = [
    {
        "first_name": "Ana",       "last_name": "Kovač",
        "emso": "0101990500011",   "date_of_birth": "1990-01-01",
        "hire_date": "2018-03-15", "base_salary": 3200.00,
        "department": "IT",        "job_title": "Razvijalec programske opreme",
        "employment_type": "PDI",  "email": "ana.kovac@podjetje.si",
        "bank_account": "SI56020360253863406",
    },
    {
        "first_name": "Janez",     "last_name": "Novak",
        "emso": "1506985500007",   "date_of_birth": "1985-06-15",
        "hire_date": "2015-01-10", "base_salary": 4500.00,
        "department": "Finance",   "job_title": "Finančni analitik",
        "employment_type": "PDI",  "email": "janez.novak@podjetje.si",
        "bank_account": "SI56020360253863406",
    },
    {
        "first_name": "Peter",     "last_name": "Horvat",
        "emso": "2203978500000",   "date_of_birth": "1978-03-22",
        "hire_date": "2010-06-01", "base_salary": 5800.00,
        "department": "Management","job_title": "Direktor IT",
        "employment_type": "PDI",  "email": "peter.horvat@podjetje.si",
    },
    {
        "first_name": "Marija",    "last_name": "Kovac",
        "emso": "0508992500003",   "date_of_birth": "1992-08-05",
        "hire_date": "2020-09-01", "base_salary": 2800.00,
        "department": "HR",        "job_title": "Kadrovska specialistka",
        "employment_type": "PDI",  "email": "marija.kovac@podjetje.si",
    },
    {
        "first_name": "Tina",      "last_name": "Potočnik",
        "emso": "1211988500008",   "date_of_birth": "1988-11-12",
        "hire_date": "2017-04-15", "base_salary": 3600.00,
        "department": "IT",        "job_title": "Vodja projektov",
        "employment_type": "PDI",  "email": "tina.potocnik@podjetje.si",
    },
    {
        "first_name": "Luka",      "last_name": "Zupan",
        "emso": "2507995500005",   "date_of_birth": "1995-07-25",
        "hire_date": "2022-01-10", "base_salary": 2600.00,
        "department": "Finance",   "job_title": "Računovodja",
        "employment_type": "PDI",  "email": "luka.zupan@podjetje.si",
    },
    {
        "first_name": "Eva",       "last_name": "Šimić",
        "emso": "0903982500001",   "date_of_birth": "1982-03-09",
        "hire_date": "2013-08-20", "base_salary": 3900.00,
        "department": "HR",        "job_title": "Vodja kadrov",
        "employment_type": "PDI",  "email": "eva.simic@podjetje.si",
    },
    {
        "first_name": "Rok",       "last_name": "Kranjc",
        "emso": "1712993500007",   "date_of_birth": "1993-12-17",
        "hire_date": "2021-03-01", "base_salary": 2950.00,
        "department": "IT",        "job_title": "DevOps inženir",
        "employment_type": "PDI",  "email": "rok.kranjc@podjetje.si",
    },
]


def compute_emso_check(first12: str) -> int:
    weights = [7, 6, 5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    total = sum(int(first12[i]) * weights[i] for i in range(12))
    remainder = total % 11
    return 0 if remainder == 0 else 11 - remainder


async def seed(conn: asyncpg.Connection) -> None:
    print("🗑️  Čistim obstoječe podatke…")
    await conn.execute(
        "TRUNCATE migration_log, payroll_runs, leave_requests, "
        "travel_orders, attendance, employees RESTART IDENTITY CASCADE"
    )

    print("👥 Vnašam zaposlene…")
    from datetime import date as ddate2
    emp_ids: dict[str, str] = {}
    for e in EMPLOYEES:
        rec = await conn.fetchrow(
            """
            INSERT INTO employees
                (first_name, last_name, emso, date_of_birth, hire_date, base_salary,
                 department, job_title, employment_type, email, bank_account)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
            RETURNING id
            """,
            e["first_name"], e["last_name"], e["emso"],
            ddate2.fromisoformat(e["date_of_birth"]),
            ddate2.fromisoformat(e["hire_date"]),
            Decimal(str(e["base_salary"])),
            e["department"], e["job_title"], e["employment_type"],
            e["email"], e.get("bank_account"),
        )
        emp_ids[e["email"]] = str(rec["id"])
        print(f"  ✅ {e['first_name']} {e['last_name']} ({e['department']})")

    # Helper aliases
    ana    = emp_ids["ana.kovac@podjetje.si"]
    janez  = emp_ids["janez.novak@podjetje.si"]
    peter  = emp_ids["peter.horvat@podjetje.si"]
    marija = emp_ids["marija.kovac@podjetje.si"]
    tina   = emp_ids["tina.potocnik@podjetje.si"]
    luka   = emp_ids["luka.zupan@podjetje.si"]
    eva    = emp_ids["eva.simic@podjetje.si"]
    rok    = emp_ids["rok.kranjc@podjetje.si"]

    print("\n🏖️  Vnašam dopuste…")
    leaves = [
        # Ana — odobreni letni dopust julij
        (ana,   "annual", "2026-07-07", "2026-07-18", 10.0, "Letni dopust", "approved", peter),
        # Janez — prošnja za dopust
        (janez, "annual", "2026-08-03", "2026-08-14", 10.0, "Poletni dopust", "approved", peter),
        # Peter — sick leave
        (peter, "sick",   "2026-05-12", "2026-05-16",  5.0, "Angina", "approved", eva),
        # Marija — dopust
        (marija,"annual", "2026-06-23", "2026-06-27",  5.0, "Kratki dopust", "pending", None),
        # Tina — materinski dopust
        (tina,  "maternity","2026-09-01","2027-03-01", 130.0,"Porodniški dopust","approved",peter),
        # Luka — bolniška
        (luka,  "sick",   "2026-04-21", "2026-04-23",  3.0, "Prehlad", "approved", eva),
        # Rok — odobreni dopust
        (rok,   "annual", "2026-07-20", "2026-07-31", 10.0, "Letni dopust", "approved", peter),
    ]
    from datetime import date as ddate, datetime as dt_cls
    for emp_id, lt, df, dt2, days, reason, status, approver in leaves:
        approved_at = dt_cls.now() if status in ("approved", "rejected") else None
        await conn.execute(
            """
            INSERT INTO leave_requests
                (employee_id, leave_type, date_from, date_to, days_count, reason, status,
                 approved_by, approved_at)
            VALUES ($1::uuid,$2,$3,$4,$5,$6,$7,$8::uuid,$9)
            """,
            emp_id, lt, ddate.fromisoformat(df), ddate.fromisoformat(dt2),
            Decimal(str(days)), reason, status, approver, approved_at,
        )
    print(f"  ✅ {len(leaves)} zapisov")

    print("\n✈️  Vnašam potne naloge…")
    travels = [
        (janez, "München", "2026-04-14", "2026-04-16", "Partnerska konferenca SAP", "personal_car", 320.0, 0.0),
        (peter, "Bruselj",  "2026-05-05", "2026-05-07", "EU davčni forum",            "public",       0.0,  180.0),
        (ana,   "Zagreb",  "2026-03-10", "2026-03-10", "Delavnica UX",               "personal_car", 140.0, 0.0),
        (eva,   "Dunaj",   "2026-06-02", "2026-06-03", "HR konferenca",              "public",       0.0,   95.0),
    ]
    for emp_id, dest, df, dt, purpose, transport, km, accommodation in travels:
        from datetime import date as ddate
        d_from = ddate.fromisoformat(df)
        d_to   = ddate.fromisoformat(dt)
        days   = (d_to - d_from).days + 1
        allowance = Decimal("10.70") if days == 1 else Decimal("21.39") * (days - 1) + Decimal("10.70")
        await conn.execute(
            """
            INSERT INTO travel_orders
                (employee_id, destination, purpose, date_from, date_to,
                 transport_type, km_total, daily_allowance, accommodation, status)
            VALUES ($1::uuid,$2,$3,$4,$5,$6,$7,$8,$9,'approved')
            """,
            emp_id, dest, purpose, d_from, d_to,
            transport, Decimal(str(km)), allowance, Decimal(str(accommodation)),
        )
    print(f"  ✅ {len(travels)} potnih nalogov")

    print("\n📊 Vnašam evidenco prisotnosti (april–junij 2026)…")
    from datetime import date as ddate, timedelta
    attendance_count = 0
    for emp_id in [ana, janez, marija, luka, rok]:
        d = ddate(2026, 4, 1)
        while d <= ddate(2026, 6, 20):
            if d.weekday() < 5:  # weekday only
                import random; random.seed(str(emp_id) + str(d))
                overtime = Decimal(str(round(random.uniform(0, 1.5) if random.random() > 0.7 else 0, 2)))
                await conn.execute(
                    """
                    INSERT INTO attendance
                        (employee_id, date, clock_in, clock_out, hours_worked,
                         hours_overtime, status)
                    VALUES ($1::uuid,$2,'08:00','16:30',8.5,$3,'present')
                    ON CONFLICT (employee_id, date) DO NOTHING
                    """,
                    emp_id, d, overtime,
                )
                attendance_count += 1
            d += timedelta(days=1)
    print(f"  ✅ {attendance_count} zapisov prisotnosti")

    print("\n💰 Vnašam in računam obračune plač (april 2026)…")
    all_emps = [ana, janez, peter, marija, tina, luka, eva, rok]
    salaries = {
        ana: 3200.0, janez: 4500.0, peter: 5800.0, marija: 2800.0,
        tina: 3600.0, luka: 2600.0, eva: 3900.0, rok: 2950.0,
    }

    from src.services.si_rules import calculate_gross_to_net

    for emp_id in all_emps:
        base = Decimal(str(salaries[emp_id]))
        overtime = Decimal("0")
        # Add overtime for some
        if emp_id in (ana, rok):
            overtime = Decimal("250")

        breakdown = calculate_gross_to_net(base_salary=base, overtime_pay=overtime)

        import json as _json
        deductions = _json.dumps({
            "employee_contributions": float(breakdown["employee_contributions"]),
            "income_tax": float(breakdown["income_tax"]),
        })
        await conn.execute(
            """
            INSERT INTO payroll_runs
                (employee_id, period_month, period_year, base_salary, overtime_pay,
                 gross_salary, net_salary, employee_contributions, employer_contributions,
                 income_tax, status, deductions)
            VALUES ($1::uuid,4,2026,$2,$3,$4,$5,$6,$7,$8,'confirmed',$9::jsonb)
            """,
            emp_id, base, overtime,
            breakdown["gross_salary"], breakdown["net_salary"],
            breakdown["employee_contributions"], breakdown["employer_contributions"],
            breakdown["income_tax"], deductions,
        )

    # March 2026 payroll too
    for emp_id in [ana, janez, peter]:
        base = Decimal(str(salaries[emp_id]))
        breakdown = calculate_gross_to_net(base_salary=base)
        import json as _json
        deductions = _json.dumps({
            "employee_contributions": float(breakdown["employee_contributions"]),
            "income_tax": float(breakdown["income_tax"]),
        })
        await conn.execute(
            """
            INSERT INTO payroll_runs
                (employee_id, period_month, period_year, base_salary,
                 gross_salary, net_salary, employee_contributions, employer_contributions,
                 income_tax, status, deductions)
            VALUES ($1::uuid,3,2026,$2,$3,$4,$5,$6,$7,'paid',$8::jsonb)
            """,
            emp_id, base,
            breakdown["gross_salary"], breakdown["net_salary"],
            breakdown["employee_contributions"], breakdown["employer_contributions"],
            breakdown["income_tax"], deductions,
        )
    print(f"  ✅ {len(all_emps)} obračunov za april + 3 za marec")

    print("\n✨ Baza uspešno zapolnjena!")
    print(f"   Zaposleni: {len(EMPLOYEES)}")
    print(f"   Dopusti:   {len(leaves)}")
    print(f"   Potni nalogi: {len(travels)}")
    print(f"   Prisotnost: {attendance_count} dni")
    print(f"   Obračuni:  {len(all_emps) + 3}")


async def main():
    print("🔗 Vzpostavljam povezavo z bazo…")
    conn = await asyncpg.connect(DB_URL)
    try:
        schema = (Path(__file__).parent / "schema" / "init.sql").read_text()
        # Drop and recreate schema
        await conn.execute("""
            DROP TABLE IF EXISTS migration_log, payroll_runs, leave_requests,
                travel_orders, attendance, employees CASCADE
        """)
        await conn.execute(schema)
        await seed(conn)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
