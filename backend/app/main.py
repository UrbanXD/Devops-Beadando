from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="PDF ↔ DOCX konverter API",
    description="Kezdő API a PDF és DOCX dokumentumok konvertálásához.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/api/health", tags=["rendszer"])
def health() -> dict[str, str]:
    """Egyszerű liveness ellenőrzés a helyi környezethez."""
    return {"status": "ok", "service": "converter-api"}
