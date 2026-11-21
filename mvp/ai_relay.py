"""A bounded, token-gated relay for one FounderRadar OpenAI project."""
from contextlib import closing
from datetime import datetime, timezone
from hmac import compare_digest
import os
from pathlib import Path
import sqlite3

from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from mvp.ai import AnalysisInput, MODEL_DEFAULT, provider_result, validate_input

MAX_BODY = 65_000


def reserve_call(path, budget):
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=10)) as connection, connection:
        connection.execute("CREATE TABLE IF NOT EXISTS usage (record INTEGER PRIMARY KEY, calls INTEGER NOT NULL)")
        connection.execute("INSERT OR IGNORE INTO usage VALUES (1, 0)")
        cursor = connection.execute("UPDATE usage SET calls = calls + 1 WHERE record = 1 AND calls < ?", (budget,))
        return cursor.rowcount == 1


def allowed(authorization, expected, expires):
    if len(expected) < 32 or not expires:
        return False
    if not authorization.startswith("Bearer "):
        return False
    try:
        deadline = datetime.fromisoformat(expires.replace("Z", "+00:00"))
        if deadline.tzinfo is None or datetime.now(timezone.utc) >= deadline:
            return False
    except ValueError:
        return False
    return compare_digest(authorization[7:].encode(), expected.encode())


def settings():
    return (
        os.environ.get("FOUNDERRADAR_PROJECT_OPENAI_KEY", ""),
        os.environ.get("FOUNDERRADAR_JURY_TOKEN", ""),
        os.environ.get("FOUNDERRADAR_JURY_EXPIRES", ""),
        os.environ.get("FOUNDERRADAR_PROJECT_MODEL", MODEL_DEFAULT),
    )


async def health(request):
    key, token, expires, _ = settings()
    ready = bool(key and allowed("Bearer " + token, token, expires))
    return JSONResponse({"service": "founderradar-project-ai", "ready": ready}, status_code=200 if ready else 503)


async def insights(request: Request):
    key, token, expires, model = settings()
    if not key or len(token) < 32 or not expires:
        return JSONResponse({"error": "Projektserver nicht konfiguriert."}, status_code=503)
    if not allowed(request.headers.get("authorization", ""), token, expires):
        return JSONResponse({"error": "Jury-Zugang ungültig oder abgelaufen."}, status_code=401)
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_BODY:
            return JSONResponse({"error": "Anfrage zu groß."}, status_code=413)
        body.extend(chunk)
    try:
        data = AnalysisInput.model_validate_json(bytes(body))
        validate_input(data)
    except (ValidationError, ValueError):
        return JSONResponse({"error": "Ungültiges Quellenformat."}, status_code=422)
    try:
        budget = max(1, min(1_000, int(os.environ.get("FOUNDERRADAR_AI_BUDGET", "80"))))
        path = Path(os.environ.get("FOUNDERRADAR_RELAY_DB", ".relay-state/usage.sqlite3"))
        available = await run_in_threadpool(reserve_call, path, budget)
    except (ValueError, OSError, sqlite3.Error):
        return JSONResponse({"error": "Projektkontingent vorübergehend nicht verfügbar."}, status_code=503)
    if not available:
        return JSONResponse({"error": "Projektkontingent aufgebraucht."}, status_code=429)
    try:
        result = await run_in_threadpool(provider_result, data, key, model)
    except ValueError:
        return JSONResponse({"error": "Projekt-KI konnte keinen gültigen Entwurf liefern."}, status_code=502)
    return JSONResponse(result.model_dump(mode="json"), headers={"Cache-Control": "no-store"})


app = Starlette(routes=[
    Route("/healthz", health, methods=["GET"]),
    Route("/v1/founderradar/insights", insights, methods=["POST"]),
])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.environ.get("FOUNDERRADAR_RELAY_HOST", "127.0.0.1"),
                port=int(os.environ.get("PORT", "8077")), access_log=False)
