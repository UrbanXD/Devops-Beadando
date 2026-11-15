from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth import router as auth_router
from app.conversion import router as conversion_router
from app.database import get_db

app = FastAPI(
    title="PDF ↔ DOCX konverter API",
    description="Felhasználói fiókok kezelése és PDF ↔ DOCX dokumentumkonverzió.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth_router)
app.include_router(conversion_router)


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
