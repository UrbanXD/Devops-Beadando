import os
from pathlib import Path


DATABASE_URL = os.getenv("DATABASE_URL")
STORAGE_PATH = Path(os.getenv("STORAGE_PATH", "storage")).expanduser()
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))
REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/api/auth"
REFRESH_COOKIE_SECURE = os.getenv("REFRESH_COOKIE_SECURE", "false").lower() in {
    "1",
    "true",
    "yes",
}
JWT_ALGORITHM = "HS256"

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL must be configured")

if len(JWT_SECRET_KEY) < 32:
    raise RuntimeError("JWT_SECRET_KEY must contain at least 32 characters")

if ACCESS_TOKEN_EXPIRE_MINUTES < 1:
    raise RuntimeError("ACCESS_TOKEN_EXPIRE_MINUTES must be greater than zero")

if REFRESH_TOKEN_EXPIRE_DAYS < 1:
    raise RuntimeError("REFRESH_TOKEN_EXPIRE_DAYS must be greater than zero")
