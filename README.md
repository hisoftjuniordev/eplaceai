# 🇸🇮 SI Payroll AI

**AI-powered mini ERP za upravljanje slovenskih plač** — pogovarjajte se z bazo podatkov v naravnem jeziku.

🌐 **Demo:** [eplaceai-production.up.railway.app](https://eplaceai-production.up.railway.app)

---

## Kaj je to?

SI Payroll AI je spletna aplikacija, ki omogoča upravljanje kadrovskih in plačilnih podatkov slovenskega podjetja prek **pogovora v naravnem jeziku**. Namesto da bi ročno pregledovali tabele in pisali SQL, preprosto vprašate:

> *"Kakšna je bruto plača Janeza Novaka za april 2026?"*
> *"Kdo ima potni nalog in dopust na isti dan?"*
> *"Prikaži vse bolniške odsotnosti za april."*

Sistem razume vprašanje, samodejno izvede pravo SQL poizvedbo in odgovori v slovenščini — v realnem času.

---

## Arhitektura

```
Uporabnik (brskalnik)
        │
        ▼
┌───────────────────┐
│   FastAPI backend │  ← Python 3.12, uvicorn
│   src/api.py      │
└────────┬──────────┘
         │  SSE (Server-Sent Events)
         ▼
┌───────────────────┐     ┌─────────────────────────┐
│   Agent loop      │────▶│  OpenRouter API (gratis) │
│   (tool calling)  │     │  meta-llama-3.3-70b      │
└────────┬──────────┘     │  deepseek-r1, mistral-7b │
         │                └─────────────────────────┘
         │  ob rate-limitu ▼
         │           ┌──────────────┐
         │           │  Groq API    │
         │           │  llama-3.3-70b│
         │           └──────────────┘
         │
         ▼
┌───────────────────┐
│   PostgreSQL 16   │  ← asyncpg connection pool
│   Railway managed │
└───────────────────┘
```

Vzporedno deluje tudi **MCP strežnik** (`src/main.py`) — stdio vmesnik za integracijo z AI agenti (Claude Desktop, MCP odjemalci).

---

## Kako deluje (korak za korakom)

1. **Uporabnik** vnese vprašanje v slovenščini prek spletnega vmesnika
2. **FastAPI** sprejme zahtevo na `/api/chat` in odpre SSE tok
3. **Agent loop** pošlje sporočilo LLM-u (OpenRouter → Groq fallback)
4. **LLM** razume namen in pokliče ustrezno orodje (tool calling / function calling)
5. **Backend** izvede SQL poizvedbo na PostgreSQL prek asyncpg
6. **Rezultati** se vrnejo LLM-u, ki sestavi odgovor v naravnem jeziku
7. **SSE tok** sproti pošilja vse korake (razmišljanje, SQL, rezultat) v terminal desno
8. **Odgovor** se izpiše v klepet, SQL poizvedbe so vidne v živo

---

## Zmogljivosti

| Modul | Opis |
|---|---|
| **Zaposleni** | Iskanje, filtriranje po oddelku, podrobnosti posameznika |
| **Obračun plač** | Bruto/neto, prispevki (22,10 % / 16,10 %), dohodnina po SI zakonodaji |
| **Dopusti** | Letni, bolniška, materinski, neplačani — status in stanje |
| **Prisotnost** | Evidenca ur, nadure po mesecih |
| **Potni nalogi** | Destinacije, datumi, dnevnice |
| **Konflikti** | Samodejno zaznavanje prekrivanj med potnimi nalogi in dopusti |

---

## Tehnološki sklad

| Plast | Tehnologija |
|---|---|
| Backend | Python 3.12, FastAPI, uvicorn |
| Baza | PostgreSQL 16, asyncpg |
| AI | OpenRouter (meta-llama, deepseek, mistral) + Groq (llama-3.3-70b) |
| MCP | `mcp[cli]` — stdio strežnik za AI agente |
| Frontend | Vanilla JS, SSE streaming, dark terminal UI |
| Deployment | Docker, Railway (app + managed Postgres) |
| Konfiguracija | pydantic-settings, python-dotenv |

---

## Statistike kode

| Datoteka / modul | Vrstice |
|---|---|
| `src/api.py` — FastAPI + agent loop + SSE | 865 |
| `src/tools/write_tools.py` — MCP write operacije | 378 |
| `src/tools/workflow_tools.py` — potrjevanje, izvoz | 247 |
| `src/tools/read_tools.py` — MCP read operacije | 246 |
| `seed.py` — testni podatki (8 zaposlenih) | 290 |
| `src/services/si_rules.py` — slovenska zakonodaja | 117 |
| `src/services/conflict_detector.py` | 104 |
| `static/index.html` — celoten frontend | 685 |
| `schema/init.sql` — shema baze | 142 |
| Testi (`tests/`) | ~400 |
| **Skupaj** | **~4.300 vrstic** |

---

## Struktura projekta

```
si-payroll-mcp/
├── src/
│   ├── api.py              # FastAPI app, SSE agent loop, SQL orodja
│   ├── main.py             # MCP stdio strežnik
│   ├── config.py           # Nastavitve (pydantic-settings)
│   ├── database.py         # asyncpg connection pool
│   ├── models/             # Pydantic modeli (employee, payroll, leave…)
│   ├── services/           # Poslovna logika (SI pravila, konflikti, eDavki)
│   ├── tools/              # MCP orodja (read, write, workflow)
│   ├── validators/         # Validacija EMŠO, vnosov
│   └── audit/              # Revizijska sled
├── static/
│   └── index.html          # Celoten frontend (HTML + CSS + JS)
├── schema/
│   └── init.sql            # PostgreSQL shema
├── tests/                  # pytest testi
├── seed.py                 # Nalaganje testnih podatkov
├── Dockerfile              # Produkcijska slika
├── docker-compose.yml      # Lokalni razvoj (PostgreSQL)
├── railway.json            # Railway deployment config
└── pyproject.toml          # Python odvisnosti
```

---

## Lokalni razvoj

```bash
# 1. Kloniraj repozitorij
git clone https://github.com/hisoftjuniordev/eplaceai.git
cd eplaceai

# 2. Kopiraj .env in nastavi ključe
cp .env.example .env
# Vnesi OPENROUTER_API_KEY in/ali GROQ_API_KEY

# 3. Zaženi PostgreSQL
docker compose up -d db

# 4. Namesti odvisnosti
pip install -e .

# 5. Naloži testne podatke
python seed.py

# 6. Zaženi aplikacijo
uvicorn src.api:app --reload

# Odpri: http://localhost:8000
```

---

## Okoljske spremenljivke

| Spremenljivka | Opis | Obvezno |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | Da |
| `OPENROUTER_API_KEY` | Ključ za OpenRouter (brezplačni modeli) | Priporočeno |
| `GROQ_API_KEY` | Ključ za Groq (hiter fallback) | Priporočeno |
| `OPENROUTER_MODEL` | Primarni model (privzeto: meta-llama-3.3-70b:free) | Ne |

Brez API ključev aplikacija deluje v **demo načinu** — SQL poizvedbe se izvajajo, odgovori so generirani s ključnimi besedami brez LLM-a.

---

## Deployment (Railway)

1. Fork tega repozitorija
2. Ustvari nov projekt na [railway.app](https://railway.app)
3. Poveži GitHub repozitorij
4. Dodaj **PostgreSQL plugin**
5. Nastavi spremenljivke: `DATABASE_URL=${{Postgres.DATABASE_URL}}`, `OPENROUTER_API_KEY`, `GROQ_API_KEY`
6. Po zagonu odpri **Console** in zaženi: `python seed.py`

---

## Avtor

Razvito kot demonstracijski projekt za slovensko zakonodajo o plačah z integracijo modernih AI tehnologij (LLM tool calling, MCP, SSE streaming).

**Stack:** Python · FastAPI · PostgreSQL · OpenRouter · Groq · Railway · Docker
