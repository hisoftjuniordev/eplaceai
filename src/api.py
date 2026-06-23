"""FastAPI web backend — natural language interface to the SI Payroll database.

Exposes a single SSE streaming endpoint /api/chat that:
1. Accepts a natural language message
2. Calls Claude claude-sonnet-4-6 with tool definitions
3. Executes SQL tools against PostgreSQL
4. Streams log events (tool calls, SQL, results) + final response
"""
from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import asyncpg
import openai
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

import src.database as database
from src.config import settings

# ── App lifecycle ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Log masked URL so Railway logs show which host is being targeted
    db_url = settings.database_url
    masked = db_url.split("@")[-1] if "@" in db_url else db_url
    print(f"Connecting to DB: …@{masked}")
    for attempt in range(1, 7):
        try:
            database._pool = await asyncpg.create_pool(
                dsn=db_url,
                min_size=settings.db_min_pool,
                max_size=settings.db_max_pool,
            )
            print("DB connection pool established.")
            break
        except Exception as exc:
            if attempt == 6:
                raise RuntimeError(f"DB unreachable after 6 attempts: {exc}") from exc
            wait = 2 ** attempt
            print(f"DB connect attempt {attempt} failed ({exc}), retrying in {wait}s…")
            await asyncio.sleep(wait)

    # Apply schema if tables don't exist yet (first deploy on a fresh DB)
    tables_exist = await database._pool.fetchval(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'employees')"
    )
    if not tables_exist:
        print("Fresh DB detected — applying schema…")
        schema_sql = (Path(__file__).parent.parent / "schema" / "init.sql").read_text()
        await database._pool.execute(schema_sql)
        print("Schema applied. Run 'python seed.py' to populate with test data.")
    else:
        print("Schema already present.")

    yield
    if database._pool:
        await database._pool.close()


app = FastAPI(title="SI Payroll AI", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

STATIC_DIR = Path(__file__).parent.parent / "static"

# ── Serialisation ─────────────────────────────────────────────────────────────

def _s(v: Any) -> Any:
    if isinstance(v, UUID):
        return str(v)
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, time, datetime)):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: _s(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_s(x) for x in v]
    return v

def row(r: Any) -> dict | None:
    return _s(dict(r)) if r else None

def rows(rs: list) -> list[dict]:
    return [_s(dict(r)) for r in rs]

# ── SQL tool implementations ───────────────────────────────────────────────────

async def _tool_search_employees(
    name: str | None = None,
    department: str | None = None,
    is_active: bool | None = None,
    emit=None,
) -> list[dict]:
    conds, args, i = [], [], 1
    if name:
        conds.append(f"LOWER(first_name || ' ' || last_name) LIKE LOWER(${i})")
        args.append(f"%{name}%"); i += 1
    if department:
        conds.append(f"department = ${i}"); args.append(department); i += 1
    if is_active is not None:
        conds.append(f"is_active = ${i}"); args.append(is_active); i += 1
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    sql = (
        f"SELECT id, first_name, last_name, department, job_title, "
        f"base_salary, is_active, hire_date, email "
        f"FROM employees {where} ORDER BY last_name, first_name"
    )
    if emit:
        await emit({"type": "sql", "query": sql, "params": [str(a) for a in args]})
    result = rows(await database.fetch(sql, *args))
    if emit:
        await emit({"type": "sql_result", "rows": len(result)})
    return result


async def _tool_get_employee_details(employee_id: str, emit=None) -> dict | None:
    sql = "SELECT * FROM employees WHERE id = $1::uuid"
    if emit:
        await emit({"type": "sql", "query": sql, "params": [employee_id]})
    result = row(await database.fetchrow(sql, employee_id))
    if emit:
        await emit({"type": "sql_result", "rows": 1 if result else 0})
    return result


async def _tool_get_leave_balance(employee_id: str, emit=None) -> dict:
    sql = (
        "SELECT leave_type, status, SUM(days_count)::float AS days "
        "FROM leave_requests "
        "WHERE employee_id = $1::uuid "
        "GROUP BY leave_type, status "
        "ORDER BY leave_type, status"
    )
    if emit:
        await emit({"type": "sql", "query": sql, "params": [employee_id]})
    result_rows = await database.fetch(sql, employee_id)
    balance: dict = {}
    for r in result_rows:
        lt = r["leave_type"]
        if lt not in balance:
            balance[lt] = {}
        balance[lt][r["status"]] = float(r["days"] or 0)
    if emit:
        await emit({"type": "sql_result", "rows": len(result_rows)})
    return balance


async def _tool_get_payroll_run(
    employee_id: str, period_month: int, period_year: int, emit=None
) -> dict | None:
    sql = (
        "SELECT pr.*, e.first_name, e.last_name "
        "FROM payroll_runs pr "
        "JOIN employees e ON e.id = pr.employee_id "
        "WHERE pr.employee_id = $1::uuid AND pr.period_month = $2 AND pr.period_year = $3"
    )
    if emit:
        await emit({"type": "sql", "query": sql, "params": [employee_id, period_month, period_year]})
    result = row(await database.fetchrow(sql, employee_id, period_month, period_year))
    if emit:
        await emit({"type": "sql_result", "rows": 1 if result else 0})
    return result


async def _tool_get_payroll_summary(
    period_month: int, period_year: int, department: str | None = None, emit=None
) -> dict:
    if department:
        sql = (
            "SELECT COUNT(*)::int AS employee_count, "
            "SUM(pr.gross_salary)::float AS total_gross, "
            "SUM(pr.net_salary)::float AS total_net, "
            "SUM(pr.employee_contributions)::float AS total_emp_contrib, "
            "SUM(pr.employer_contributions)::float AS total_er_contrib, "
            "SUM(pr.income_tax)::float AS total_income_tax "
            "FROM payroll_runs pr JOIN employees e ON e.id = pr.employee_id "
            "WHERE pr.period_month = $1 AND pr.period_year = $2 "
            "AND e.department = $3 AND pr.status != 'cancelled'"
        )
        if emit:
            await emit({"type": "sql", "query": sql, "params": [period_month, period_year, department]})
        r = await database.fetchrow(sql, period_month, period_year, department)
    else:
        sql = (
            "SELECT COUNT(*)::int AS employee_count, "
            "SUM(gross_salary)::float AS total_gross, "
            "SUM(net_salary)::float AS total_net, "
            "SUM(employee_contributions)::float AS total_emp_contrib, "
            "SUM(employer_contributions)::float AS total_er_contrib, "
            "SUM(income_tax)::float AS total_income_tax "
            "FROM payroll_runs "
            "WHERE period_month = $1 AND period_year = $2 AND status != 'cancelled'"
        )
        if emit:
            await emit({"type": "sql", "query": sql, "params": [period_month, period_year]})
        r = await database.fetchrow(sql, period_month, period_year)
    result = _s(dict(r)) if r else {}
    if emit:
        await emit({"type": "sql_result", "rows": result.get("employee_count", 0)})
    return result


async def _tool_get_attendance_summary(
    employee_id: str, date_from: str, date_to: str, emit=None
) -> dict:
    sql = (
        "SELECT status, COUNT(*) AS days, "
        "SUM(hours_worked)::float AS total_hours, "
        "SUM(hours_overtime)::float AS overtime_hours "
        "FROM attendance "
        "WHERE employee_id = $1::uuid AND date BETWEEN $2 AND $3 "
        "GROUP BY status ORDER BY status"
    )
    if emit:
        await emit({"type": "sql", "query": sql, "params": [employee_id, date_from, date_to]})
    result_rows = await database.fetch(sql, employee_id, date_from, date_to)
    summary = {r["status"]: {"days": int(r["days"]), "hours": float(r["total_hours"] or 0),
                               "overtime": float(r["overtime_hours"] or 0)}
               for r in result_rows}
    if emit:
        await emit({"type": "sql_result", "rows": len(result_rows)})
    return summary


async def _tool_get_leave_requests(
    employee_id: str | None = None,
    leave_type: str | None = None,
    status: str | None = None,
    emit=None,
) -> list[dict]:
    conds, args, i = [], [], 1
    if employee_id:
        conds.append(f"lr.employee_id = ${i}::uuid"); args.append(employee_id); i += 1
    if leave_type:
        conds.append(f"lr.leave_type = ${i}"); args.append(leave_type); i += 1
    if status:
        conds.append(f"lr.status = ${i}"); args.append(status); i += 1
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    sql = (
        f"SELECT lr.*, e.first_name || ' ' || e.last_name AS employee_name "
        f"FROM leave_requests lr JOIN employees e ON e.id = lr.employee_id "
        f"{where} ORDER BY lr.date_from DESC LIMIT 20"
    )
    if emit:
        await emit({"type": "sql", "query": sql, "params": [str(a) for a in args]})
    result = rows(await database.fetch(sql, *args))
    if emit:
        await emit({"type": "sql_result", "rows": len(result)})
    return result


async def _tool_detect_conflicts(
    date_from: str | None = None, date_to: str | None = None, emit=None
) -> list[dict]:
    cond = ""
    args: list = []
    if date_from:
        cond += " AND to_.date_from >= $1"
        args.append(date.fromisoformat(date_from) if isinstance(date_from, str) else date_from)
    if date_to:
        cond += f" AND to_.date_to <= ${len(args)+1}"
        args.append(date.fromisoformat(date_to) if isinstance(date_to, str) else date_to)
    sql = (
        f"SELECT e.first_name || ' ' || e.last_name AS employee, "
        f"to_.destination, to_.date_from AS travel_from, to_.date_to AS travel_to, "
        f"lr.leave_type, lr.date_from AS leave_from, lr.date_to AS leave_to "
        f"FROM travel_orders to_ "
        f"JOIN employees e ON e.id = to_.employee_id "
        f"JOIN leave_requests lr ON lr.employee_id = to_.employee_id "
        f"AND lr.status = 'approved' AND lr.date_from <= to_.date_to AND lr.date_to >= to_.date_from "
        f"WHERE to_.status != 'cancelled' {cond}"
    )
    if emit:
        await emit({"type": "sql", "query": sql, "params": [str(a) for a in args]})
    result = rows(await database.fetch(sql, *args))
    if emit:
        await emit({"type": "sql_result", "rows": len(result)})
    return result


TOOL_MAP = {
    "search_employees": _tool_search_employees,
    "get_employee_details": _tool_get_employee_details,
    "get_leave_balance": _tool_get_leave_balance,
    "get_payroll_run": _tool_get_payroll_run,
    "get_payroll_summary": _tool_get_payroll_summary,
    "get_attendance_summary": _tool_get_attendance_summary,
    "get_leave_requests": _tool_get_leave_requests,
    "detect_conflicts": _tool_detect_conflicts,
}

# ── Claude tool schemas ───────────────────────────────────────────────────────

CLAUDE_TOOLS: list[dict] = [
    {
        "name": "search_employees",
        "description": "Poišči zaposlene po imenu, oddelku ali statusu aktivnosti. Uporabi za poizvedbe o zaposlenih.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Del imena ali priimka (npr. 'Ana' ali 'Kovač')"},
                "department": {"type": "string", "description": "Ime oddelka (npr. 'IT', 'Finance', 'HR')"},
                "is_active": {"type": "boolean", "description": "True za aktivne, False za nekdanje zaposlene"},
            },
        },
    },
    {
        "name": "get_employee_details",
        "description": "Pridobi popolne podatke o zaposlenem po UUID-ju.",
        "input_schema": {
            "type": "object",
            "properties": {
                "employee_id": {"type": "string", "description": "UUID zaposlenega"},
            },
            "required": ["employee_id"],
        },
    },
    {
        "name": "get_leave_balance",
        "description": "Prikaži stanje dopustov zaposlenega — koliko dni je porabil, koliko mu ostane.",
        "input_schema": {
            "type": "object",
            "properties": {
                "employee_id": {"type": "string", "description": "UUID zaposlenega"},
            },
            "required": ["employee_id"],
        },
    },
    {
        "name": "get_payroll_run",
        "description": "Pridobi podroben obračun plače za zaposlenega za določen mesec in leto.",
        "input_schema": {
            "type": "object",
            "properties": {
                "employee_id": {"type": "string", "description": "UUID zaposlenega"},
                "period_month": {"type": "integer", "description": "Mesec (1-12)"},
                "period_year": {"type": "integer", "description": "Leto (npr. 2026)"},
            },
            "required": ["employee_id", "period_month", "period_year"],
        },
    },
    {
        "name": "get_payroll_summary",
        "description": "Agregatni povzetek plač za celotno podjetje ali oddelek za določen mesec.",
        "input_schema": {
            "type": "object",
            "properties": {
                "period_month": {"type": "integer", "description": "Mesec (1-12)"},
                "period_year": {"type": "integer", "description": "Leto (npr. 2026)"},
                "department": {"type": "string", "description": "Opcijski filter na oddelek"},
            },
            "required": ["period_month", "period_year"],
        },
    },
    {
        "name": "get_attendance_summary",
        "description": "Povzetek delovnega časa zaposlenega za obdobje — prisotnost, odsotnost, nadure.",
        "input_schema": {
            "type": "object",
            "properties": {
                "employee_id": {"type": "string", "description": "UUID zaposlenega"},
                "date_from": {"type": "string", "description": "Začetni datum (YYYY-MM-DD)"},
                "date_to": {"type": "string", "description": "Končni datum (YYYY-MM-DD)"},
            },
            "required": ["employee_id", "date_from", "date_to"],
        },
    },
    {
        "name": "get_leave_requests",
        "description": "Seznam zahtev za dopust ali bolniško odsotnost z možnimi filtri.",
        "input_schema": {
            "type": "object",
            "properties": {
                "employee_id": {"type": "string", "description": "UUID zaposlenega (opcijsko)"},
                "leave_type": {"type": "string", "description": "Vrsta: annual, sick, unpaid, maternity, paternity"},
                "status": {"type": "string", "description": "Status: pending, approved, rejected, cancelled"},
            },
        },
    },
    {
        "name": "detect_conflicts",
        "description": "Poišči neskladja — prekrivanja med potnimi nalogi in dopusti.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date_from": {"type": "string", "description": "Začetek obdobja (YYYY-MM-DD)"},
                "date_to": {"type": "string", "description": "Konec obdobja (YYYY-MM-DD)"},
            },
        },
    },
]

SYSTEM_PROMPT = """Si AI asistent za slovenski plačilni sistem (SI Payroll ERP). Odgovarjaš VEDNO v slovenščini.
IMPORTANT: Always respond in Slovenian language only. Never use English in your final response to the user.

Imaš dostop do baze podatkov z:
- Zaposlenimi (osebni podatki, plača, oddelek)
- Evidenco prisotnosti (ure, nadure)
- Dopusti in bolniške
- Potni nalogi
- Obračuni plač (bruto, neto, prispevki po slovenskem zakonu)

Navodila:
1. Vedno uporabi orodja da pridobiš dejanske podatke — ne ugibaj.
2. Ko vrneš podatke o plači, vedno navedi bruto, neto, prispevke in dohodnino.
3. Odgovori naj bodo konkretni z dejanskimi vrednostmi iz baze.
4. Če ne najdeš zaposlenega po imenu, ga najprej poišči z search_employees.
5. Odgovori jedrnato in prijazno.

Današnji datum: """ + datetime.now().strftime("%d.%m.%Y")

# ── OpenAI-compatible tool schemas ────────────────────────────────────────────

OPENAI_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": t["name"],
            "description": t["description"],
            "parameters": t["input_schema"],
        },
    }
    for t in CLAUDE_TOOLS
]

# OpenRouter free-model fallback chain (tried in order on rate-limit)
OPENROUTER_MODELS = [
    settings.openrouter_model,
    "meta-llama/llama-3.3-70b-instruct:free",
    "deepseek/deepseek-r1-0528:free",
    "mistralai/mistral-7b-instruct:free",
]

# ── Core agent loop (any OpenAI-compatible client) ────────────────────────────

async def _run_agent_with_client(
    client: openai.AsyncOpenAI,
    model: str,
    messages: list[dict],
    emit,
) -> bool:
    """Run the tool-calling loop. Returns True on success, raises on failure."""
    MAX_ITERATIONS = 8
    for iteration in range(1, MAX_ITERATIONS + 1):
        await emit({"type": "thinking", "text": f"Kličem {model} (krog {iteration})…"})

        response = await client.chat.completions.create(
            model=model,
            max_tokens=2048,
            tools=OPENAI_TOOLS,
            tool_choice="auto",
            messages=messages,
        )

        msg = response.choices[0].message
        finish = response.choices[0].finish_reason

        if finish in ("stop", "end_turn") or not msg.tool_calls:
            await emit({"type": "response", "text": msg.content or "Ni odgovora."})
            return True

        if msg.content:
            await emit({"type": "partial_text", "text": msg.content})

        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ],
        })

        for tc in msg.tool_calls:
            tool_name = tc.function.name
            try:
                tool_args = json.loads(tc.function.arguments)
                if not isinstance(tool_args, dict):
                    tool_args = {}
            except json.JSONDecodeError:
                tool_args = {}
            # Strip null values — Groq passes null for omitted optional params
            tool_args = {k: v for k, v in tool_args.items() if v is not None}

            await emit({"type": "tool_call", "tool": tool_name, "args": tool_args})

            try:
                fn = TOOL_MAP.get(tool_name)
                if fn is None:
                    raise ValueError(f"Neznano orodje: {tool_name}")
                result = await fn(**tool_args, emit=emit)
                result_str = json.dumps(result, ensure_ascii=False, default=str)
                await emit({"type": "tool_success", "tool": tool_name,
                            "preview": result_str[:300] + ("…" if len(result_str) > 300 else "")})
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result_str})
            except Exception as exc:
                err = str(exc)
                await emit({"type": "tool_error", "tool": tool_name, "error": err})
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": f"Napaka: {err}"})

    return True


# ── Agent entry point: OpenRouter → Groq → demo ───────────────────────────────

async def run_agent(message: str, history: list[dict], queue: asyncio.Queue) -> None:
    async def emit(event: dict):
        await queue.put(event)

    base_messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for h in history[-10:]:
        base_messages.append({"role": h["role"], "content": h["content"]})
    base_messages.append({"role": "user", "content": message})

    # ── 1. Try OpenRouter models in sequence ──────────────────────────────────
    or_key = settings.openrouter_api_key or os.environ.get("OPENROUTER_API_KEY", "")
    if or_key:
        tried = []
        for model in dict.fromkeys(OPENROUTER_MODELS):  # deduplicate, preserve order
            if model in tried:
                continue
            tried.append(model)
            client = openai.AsyncOpenAI(
                api_key=or_key,
                base_url="https://openrouter.ai/api/v1",
                default_headers={"HTTP-Referer": "http://localhost:8000", "X-Title": "SI Payroll MCP"},
            )
            try:
                await _run_agent_with_client(client, model, list(base_messages), emit)
                await queue.put(None)
                return
            except openai.RateLimitError:
                await emit({"type": "thinking", "text": f"{model} — rate limit, preizkušam naslednji model…"})
            except openai.AuthenticationError:
                await emit({"type": "error", "text": "Neveljaven OpenRouter API ključ."})
                break
            except Exception as e:
                await emit({"type": "thinking", "text": f"{model} — napaka ({type(e).__name__}), preizkušam naslednji…"})

    # ── 2. Try Groq ───────────────────────────────────────────────────────────
    groq_key = settings.groq_api_key or os.environ.get("GROQ_API_KEY", "")
    if groq_key:
        await emit({"type": "thinking", "text": "Preklop na Groq (llama-3.3-70b)…"})
        groq_client = openai.AsyncOpenAI(
            api_key=groq_key,
            base_url="https://api.groq.com/openai/v1",
        )
        try:
            await _run_agent_with_client(groq_client, "llama-3.3-70b-versatile", list(base_messages), emit)
            await queue.put(None)
            return
        except Exception as e:
            await emit({"type": "thinking", "text": f"Groq napaka ({type(e).__name__}), preklop na demo…"})

    # ── 3. Demo fallback ──────────────────────────────────────────────────────
    await emit({"type": "thinking", "text": "Preklop na demo način…"})
    await run_demo_agent(message, history, queue)
    return



# ── Demo agent (no API key required) ─────────────────────────────────────────

async def run_demo_agent(message: str, history: list[dict], queue: asyncio.Queue) -> None:
    """Keyword-based fallback when ANTHROPIC_API_KEY is not set.
    Runs real SQL queries and emits full terminal events — only the LLM layer is missing."""

    async def emit(event: dict):
        await queue.put(event)

    msg = message.lower()

    await emit({"type": "thinking", "text": "Demo način (brez API ključa) — analiziram vprašanje…"})

    try:
        # ── Detect name lookup ────────────────────────────────────────────────
        name_hint: str | None = None
        for word in message.split():
            if len(word) >= 3 and word[0].isupper() and word.isalpha():
                name_hint = word
                break

        # ── Route by keyword ─────────────────────────────────────────────────
        is_payroll = any(kw in msg for kw in ["plač", "placa", "bruto", "neto", "obračun", "payroll", "dohodnin", "prispevk"])
        is_leave   = any(kw in msg for kw in ["dopust", "bolni", "odsot", "leave", "malica"])
        is_attend  = any(kw in msg for kw in ["prisotnost", "ure", "nadure", "evidenc", "attendance"])
        is_conflict= any(kw in msg for kw in ["konflikt", "prekrivanje", "neskladj", "conflict"])
        is_travel  = any(kw in msg for kw in ["potni", "potovanje", "travel", "dieta", "km"])
        is_empl    = any(kw in msg for kw in ["zaposleni", "zaposlen", "employees", "seznam", "kdo", "oddelek", "department"])

        if is_conflict:
            await emit({"type": "tool_call", "tool": "detect_conflicts", "args": {}})
            conflicts = await _tool_detect_conflicts(emit=emit)
            if conflicts:
                lines = ["**Zaznana neskladja med potnimi nalogi in dopusti:**\n"]
                for c in conflicts:
                    lines.append(
                        f"- **{c['employee']}**: potovanje v **{c['destination']}** "
                        f"({c['travel_from']} – {c['travel_to']}) se prekriva z "
                        f"{c['leave_type']} ({c['leave_from']} – {c['leave_to']})"
                    )
                await emit({"type": "response", "text": "\n".join(lines)})
            else:
                await emit({"type": "response", "text": "Ni zaznanih neskladij med potnimi nalogi in dopusti."})

        elif is_payroll and name_hint:
            await emit({"type": "thinking", "text": f"Iščem zaposlenega '{name_hint}'…"})
            await emit({"type": "tool_call", "tool": "search_employees", "args": {"name": name_hint}})
            emps = await _tool_search_employees(name=name_hint, emit=emit)
            if not emps:
                await emit({"type": "response", "text": f"Zaposlenega z imenom '{name_hint}' ni v bazi."})
            else:
                emp = emps[0]
                month, year = _guess_period(msg)
                await emit({"type": "tool_call", "tool": "get_payroll_run",
                            "args": {"employee_id": emp["id"], "period_month": month, "period_year": year}})
                pr = await _tool_get_payroll_run(employee_id=emp["id"], period_month=month, period_year=year, emit=emit)
                if pr:
                    lines = [
                        f"**Obračun plače — {emp['first_name']} {emp['last_name']} ({month}/{year}):**\n",
                        f"- Osnovna plača: **{pr['base_salary']:,.2f} €**",
                        f"- Bruto plača: **{pr['gross_salary']:,.2f} €**",
                        f"- Prispevki zaposlenega (22,10 %): **{pr['employee_contributions']:,.2f} €**",
                        f"- Prispevki delodajalca (16,10 %): **{pr['employer_contributions']:,.2f} €**",
                        f"- Dohodnina: **{pr['income_tax']:,.2f} €**",
                        f"- **Neto plača: {pr['net_salary']:,.2f} €**",
                        f"- Status: {pr['status']}",
                    ]
                    await emit({"type": "response", "text": "\n".join(lines)})
                else:
                    await emit({"type": "response",
                                "text": f"Za {emp['first_name']} {emp['last_name']} ni obračuna za {month}/{year}."})

        elif is_payroll:
            month, year = _guess_period(msg)
            dept: str | None = None
            for d in ["IT", "Finance", "HR", "Management"]:
                if d.lower() in msg:
                    dept = d
                    break
            args: dict = {"period_month": month, "period_year": year}
            if dept:
                args["department"] = dept
            await emit({"type": "tool_call", "tool": "get_payroll_summary", "args": args})
            result = await _tool_get_payroll_summary(**args, emit=emit)
            if result and result.get("employee_count"):
                lines = [
                    f"**Povzetek plač{f' — oddelek {dept}' if dept else ''} za {month}/{year}:**\n",
                    f"- Število zaposlenih: **{result['employee_count']}**",
                    f"- Skupni bruto: **{result.get('total_gross', 0):,.2f} €**",
                    f"- Skupni neto: **{result.get('total_net', 0):,.2f} €**",
                    f"- Prispevki zaposlenih: **{result.get('total_emp_contrib', 0):,.2f} €**",
                    f"- Prispevki delodajalcev: **{result.get('total_er_contrib', 0):,.2f} €**",
                    f"- Dohodnina skupaj: **{result.get('total_income_tax', 0):,.2f} €**",
                ]
                await emit({"type": "response", "text": "\n".join(lines)})
            else:
                await emit({"type": "response", "text": f"Za {month}/{year} ni obračunov{f' za oddelek {dept}' if dept else ''}."})

        elif is_leave:
            status: str | None = None
            if any(kw in msg for kw in ["čakajoč", "pending", "čaka", "neodob"]):
                status = "pending"
            elif any(kw in msg for kw in ["odobren", "approved"]):
                status = "approved"
            leave_type: str | None = None
            if "bolni" in msg:
                leave_type = "sick"
            elif "letni" in msg or "annual" in msg:
                leave_type = "annual"
            elif "materinsk" in msg or "porodniš" in msg:
                leave_type = "maternity"

            call_args: dict = {}
            if status: call_args["status"] = status
            if leave_type: call_args["leave_type"] = leave_type
            if name_hint:
                await emit({"type": "tool_call", "tool": "search_employees", "args": {"name": name_hint}})
                emps = await _tool_search_employees(name=name_hint, emit=emit)
                if emps:
                    call_args["employee_id"] = emps[0]["id"]

            await emit({"type": "tool_call", "tool": "get_leave_requests", "args": call_args})
            leaves = await _tool_get_leave_requests(**call_args, emit=emit)
            if leaves:
                lines = [f"**Zahteve za dopust ({len(leaves)}):**\n"]
                for lr in leaves[:15]:
                    lines.append(
                        f"- **{lr['employee_name']}** — {lr['leave_type']}, "
                        f"{lr['date_from']} do {lr['date_to']} ({lr['days_count']} dni), "
                        f"status: **{lr['status']}**"
                    )
                await emit({"type": "response", "text": "\n".join(lines)})
            else:
                await emit({"type": "response", "text": "Ni zahtev za dopust po teh kriterijih."})

        elif is_empl or name_hint:
            dept_filter: str | None = None
            for d in ["IT", "Finance", "HR", "Management"]:
                if d.lower() in msg:
                    dept_filter = d
                    break

            call_kw: dict = {}
            if name_hint and not is_empl:
                call_kw["name"] = name_hint
            if dept_filter:
                call_kw["department"] = dept_filter

            await emit({"type": "tool_call", "tool": "search_employees", "args": call_kw})
            emps = await _tool_search_employees(**call_kw, emit=emit)
            if emps:
                lines = [f"**Zaposleni{f' — oddelek {dept_filter}' if dept_filter else ''} ({len(emps)}):**\n"]
                for emp in emps:
                    active = "✓" if emp.get("is_active") else "✗"
                    lines.append(
                        f"- {active} **{emp['first_name']} {emp['last_name']}** "
                        f"({emp['department']}) — {emp['job_title']}, "
                        f"plača: **{emp['base_salary']:,.2f} €**"
                    )
                await emit({"type": "response", "text": "\n".join(lines)})
            else:
                await emit({"type": "response", "text": "Ni zadetkov po teh kriterijih."})

        else:
            # Default fallback — show overview
            await emit({"type": "thinking", "text": "Nalagam pregled baze…"})
            await emit({"type": "tool_call", "tool": "search_employees", "args": {}})
            emps = await _tool_search_employees(emit=emit)
            month, year = 4, 2026
            await emit({"type": "tool_call", "tool": "get_payroll_summary",
                        "args": {"period_month": month, "period_year": year}})
            summary = await _tool_get_payroll_summary(period_month=month, period_year=year, emit=emit)
            lines = [
                "**Demo način** — dodajte `ANTHROPIC_API_KEY` v `.env` za polno AI izkušnjo.\n",
                f"**Pregled sistema ({datetime.now().strftime('%d.%m.%Y')}):**\n",
                f"- Zaposlenih: **{len(emps)}**",
            ]
            if summary and summary.get("employee_count"):
                lines += [
                    f"- Obračuni april 2026: **{summary['employee_count']}** zaposlenih",
                    f"- Skupni bruto april: **{summary.get('total_gross', 0):,.2f} €**",
                    f"- Skupni neto april: **{summary.get('total_net', 0):,.2f} €**",
                ]
            lines.append("\n*Poskusite vprašati: 'seznam zaposlenih', 'plače april', 'dopusti', 'konflikti'*")
            await emit({"type": "response", "text": "\n".join(lines)})

    except Exception as exc:
        await emit({"type": "error", "text": f"Napaka v demo načinu: {exc}"})

    await queue.put(None)


def _guess_period(msg: str) -> tuple[int, int]:
    """Extract month/year from message text, default to April 2026."""
    months = {
        "januar": 1, "februar": 2, "marec": 3, "april": 4, "maj": 5, "junij": 6,
        "julij": 7, "avgust": 8, "september": 9, "oktober": 10, "november": 11, "december": 12,
    }
    month, year = 4, 2026
    for name, num in months.items():
        if name in msg:
            month = num
            break
    import re
    m = re.search(r"\b(202\d)\b", msg)
    if m:
        year = int(m.group(1))
    return month, year


# ── API endpoints ─────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


@app.post("/api/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    queue: asyncio.Queue = asyncio.Queue()
    agent_fn = run_agent

    async def generate():
        task = asyncio.create_task(agent_fn(request.message, request.history, queue))
        total_wait = 0
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=20.0)
                    total_wait = 0
                except asyncio.TimeoutError:
                    total_wait += 20
                    if total_wait >= 300:
                        yield f"data: {json.dumps({'type': 'error', 'text': 'Timeout'})}\n\n"
                        break
                    # SSE comment — keeps Railway/proxy connection alive without sending data
                    yield ": keepalive\n\n"
                    continue
                if event is None:
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    break
                yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
        finally:
            task.cancel()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/debug")
async def debug_info() -> dict:
    env_file = Path(__file__).resolve().parent.parent / ".env"
    or_key = settings.openrouter_api_key or os.environ.get("OPENROUTER_API_KEY", "")
    groq_key = settings.groq_api_key or os.environ.get("GROQ_API_KEY", "")
    return {
        "openrouter_key": or_key[:12] + "…" if or_key else "EMPTY",
        "openrouter_model": settings.openrouter_model,
        "openrouter_fallback_models": OPENROUTER_MODELS,
        "groq_key": groq_key[:12] + "…" if groq_key else "EMPTY",
        "env_file_path": str(env_file),
        "env_file_exists": env_file.exists(),
        "cwd": os.getcwd(),
    }


@app.get("/api/stats")
async def stats() -> dict:
    """Quick database stats for the UI header."""
    r = await database.fetchrow(
        "SELECT "
        "(SELECT COUNT(*) FROM employees WHERE is_active) AS employees, "
        "(SELECT COUNT(*) FROM payroll_runs WHERE status != 'cancelled') AS payroll_runs, "
        "(SELECT COUNT(*) FROM leave_requests WHERE status = 'pending') AS pending_leaves"
    )
    return _s(dict(r)) if r else {}


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = STATIC_DIR / "index.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>static/index.html not found</h1>", status_code=404)
