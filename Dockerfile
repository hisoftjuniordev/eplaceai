FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY src/ ./src/
COPY static/ ./static/
COPY schema/ ./schema/
COPY seed.py .

# Env vars are injected by the platform (Railway/Render) — no .env copy
ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
