-- SI Payroll MCP — database schema

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── Employees ─────────────────────────────────────────────────────────────────
CREATE TABLE employees (
    id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    first_name       VARCHAR(100) NOT NULL,
    last_name        VARCHAR(100) NOT NULL,
    emso             VARCHAR(13)  UNIQUE,
    davcna_stevilka  VARCHAR(15),
    date_of_birth    DATE,
    address          VARCHAR(200),
    city             VARCHAR(100),
    postal_code      VARCHAR(10),
    country_code     CHAR(2)      DEFAULT 'SI',
    phone            VARCHAR(30),
    email            VARCHAR(150) UNIQUE,
    department       VARCHAR(100),
    job_title        VARCHAR(150),
    hire_date        DATE         NOT NULL,
    termination_date DATE,
    employment_type  VARCHAR(20),          -- 'PDI','DP','SP','NAP'
    contract_hours   NUMERIC(4,1) DEFAULT 40,
    base_salary      NUMERIC(10,2) NOT NULL,
    tax_card         JSONB,
    is_active        BOOLEAN      DEFAULT TRUE,
    bank_account     VARCHAR(34),
    created_at       TIMESTAMP    DEFAULT NOW(),
    updated_at       TIMESTAMP    DEFAULT NOW()
);

-- ── Attendance ────────────────────────────────────────────────────────────────
CREATE TABLE attendance (
    id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id    UUID         NOT NULL REFERENCES employees(id),
    date           DATE         NOT NULL,
    clock_in       TIME,
    clock_out      TIME,
    hours_worked   NUMERIC(4,2),
    hours_overtime NUMERIC(4,2) DEFAULT 0,
    hours_night    NUMERIC(4,2) DEFAULT 0,
    hours_weekend  NUMERIC(4,2) DEFAULT 0,
    hours_holiday  NUMERIC(4,2) DEFAULT 0,
    status         VARCHAR(20)  DEFAULT 'present',  -- present/absent/sick/leave/travel/unexcused
    notes          TEXT,
    created_at     TIMESTAMP    DEFAULT NOW(),
    UNIQUE (employee_id, date)
);

CREATE INDEX idx_attendance_employee_date ON attendance(employee_id, date);

-- ── Travel orders ─────────────────────────────────────────────────────────────
CREATE TABLE travel_orders (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id     UUID         NOT NULL REFERENCES employees(id),
    destination     VARCHAR(200) NOT NULL,
    purpose         TEXT,
    date_from       DATE         NOT NULL,
    date_to         DATE         NOT NULL,
    transport_type  VARCHAR(20),           -- 'personal_car','public','company'
    km_total        NUMERIC(6,1),
    daily_allowance NUMERIC(6,2),
    accommodation   NUMERIC(6,2) DEFAULT 0,
    status          VARCHAR(20)  DEFAULT 'draft',  -- draft/approved/rejected/settled
    approved_by     UUID         REFERENCES employees(id),
    approved_at     TIMESTAMP,
    created_at      TIMESTAMP    DEFAULT NOW(),
    updated_at      TIMESTAMP    DEFAULT NOW()
);

CREATE INDEX idx_travel_employee ON travel_orders(employee_id);
CREATE INDEX idx_travel_dates    ON travel_orders(date_from, date_to);

-- ── Leave requests ────────────────────────────────────────────────────────────
CREATE TABLE leave_requests (
    id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id    UUID         NOT NULL REFERENCES employees(id),
    leave_type     VARCHAR(30)  NOT NULL,  -- annual/sick/unpaid/maternity/paternity/other
    date_from      DATE         NOT NULL,
    date_to        DATE         NOT NULL,
    days_count     NUMERIC(4,1) NOT NULL,
    reason         TEXT,
    spot_reference VARCHAR(50),
    spot_diagnosis VARCHAR(10),
    status         VARCHAR(20)  DEFAULT 'pending',  -- pending/approved/rejected/cancelled
    approved_by    UUID         REFERENCES employees(id),
    approved_at    TIMESTAMP,
    created_at     TIMESTAMP    DEFAULT NOW(),
    updated_at     TIMESTAMP    DEFAULT NOW()
);

CREATE INDEX idx_leave_employee ON leave_requests(employee_id);
CREATE INDEX idx_leave_dates    ON leave_requests(date_from, date_to);

-- ── Payroll runs ──────────────────────────────────────────────────────────────
CREATE TABLE payroll_runs (
    id                    UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id           UUID          NOT NULL REFERENCES employees(id),
    period_month          INTEGER       NOT NULL CHECK (period_month BETWEEN 1 AND 12),
    period_year           INTEGER       NOT NULL CHECK (period_year >= 2020),
    base_salary           NUMERIC(10,2) NOT NULL,
    overtime_pay          NUMERIC(10,2) DEFAULT 0,
    night_pay             NUMERIC(10,2) DEFAULT 0,
    weekend_pay           NUMERIC(10,2) DEFAULT 0,
    holiday_pay           NUMERIC(10,2) DEFAULT 0,
    travel_allowance      NUMERIC(10,2) DEFAULT 0,
    leave_pay             NUMERIC(10,2) DEFAULT 0,
    sick_pay              NUMERIC(10,2) DEFAULT 0,
    bonus                 NUMERIC(10,2) DEFAULT 0,
    deductions            JSONB,
    gross_salary          NUMERIC(10,2),
    net_salary            NUMERIC(10,2),
    employee_contributions NUMERIC(10,2),
    employer_contributions NUMERIC(10,2),
    income_tax            NUMERIC(10,2),
    status                VARCHAR(20)   DEFAULT 'draft',  -- draft/calculated/confirmed/paid/cancelled
    rek1_exported         BOOLEAN       DEFAULT FALSE,
    edavki_sent           BOOLEAN       DEFAULT FALSE,
    created_at            TIMESTAMP     DEFAULT NOW(),
    updated_at            TIMESTAMP     DEFAULT NOW(),
    UNIQUE (employee_id, period_year, period_month)
);

CREATE INDEX idx_payroll_employee_period ON payroll_runs(employee_id, period_year, period_month);

-- ── Audit / migration log ─────────────────────────────────────────────────────
CREATE TABLE migration_log (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    table_name   VARCHAR(50) NOT NULL,
    record_id    UUID        NOT NULL,
    operation    VARCHAR(20) NOT NULL,  -- insert/update/delete
    old_values   JSONB,
    new_values   JSONB,
    performed_by VARCHAR(100),
    agent_tool   VARCHAR(100),
    timestamp    TIMESTAMP   DEFAULT NOW()
);

CREATE INDEX idx_migration_log_record   ON migration_log(record_id);
CREATE INDEX idx_migration_log_table_ts ON migration_log(table_name, timestamp DESC);
