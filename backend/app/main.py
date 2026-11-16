import time
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth import router as auth_router
from app.conversion import router as conversion_router
from app.database import get_db
from app.observability import (
    is_observed_api_route,
    log_event,
    metrics_app,
    record_http_request,
    request_id_context,
)

app = FastAPI(
    title="PDF ↔ DOCX konverter API",
    description="Felhasználói fiókok kezelése és PDF ↔ DOCX dokumentumkonverzió.",
    version="0.1.0",
)

app.mount("/metrics", metrics_app, name="metrics")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["X-Request-ID"],
)

app.include_router(auth_router)
app.include_router(conversion_router)


@app.middleware("http")
async def observe_api_requests(request: Request, call_next) -> Response:
    request_id = uuid4().hex
    request_token = request_id_context.set(request_id)
    started_at = time.perf_counter()
    response: Response | None = None
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        try:
            route = getattr(request.scope.get("route"), "path", None)
            if isinstance(route, str) and is_observed_api_route(route):
                duration_seconds = time.perf_counter() - started_at
                record_http_request(
                    method=request.method,
                    route=route,
                    status=status_code,
                    duration_seconds=duration_seconds,
                )
                log_event(
                    "http_request_completed",
                    method=request.method,
                    route=route,
                    status=status_code,
                    duration_ms=round(duration_seconds * 1000, 2),
                )
            if response is not None:
                response.headers["X-Request-ID"] = request_id
        finally:
            request_id_context.reset(request_token)


@app.get("/api/health", tags=["rendszer"])
def health() -> dict[str, str]:
    """Egyszerű liveness ellenőrzés a helyi környezethez."""
    return {"status": "ok", "service": "converter-api"}


@app.get("/api/health/ready", tags=["rendszer"])
def readiness(database: Session = Depends(get_db)) -> dict[str, str]:
    """Jelzi, ha az API és az adatbázis is elérhető."""
    try:
        database.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Az adatbázis nem érhető el.",
        ) from None
    return {"status": "ready", "service": "converter-api"}
