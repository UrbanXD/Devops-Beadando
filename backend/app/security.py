import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import uuid4

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import RefreshSession, User
from app.settings import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    JWT_ALGORITHM,
    JWT_SECRET_KEY,
    REFRESH_TOKEN_EXPIRE_DAYS,
)


password_hasher = PasswordHash.recommended()
bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return password_hasher.verify(password, password_hash)


def create_access_token(user_id: int) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": str(user_id), "exp": expires_at}
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_refresh_session(
    user_id: int,
    family_id: str | None = None,
) -> tuple[str, RefreshSession]:
    token = secrets.token_urlsafe(48)
    now = datetime.now(timezone.utc)
    session = RefreshSession(
        user_id=user_id,
        family_id=family_id or str(uuid4()),
        token_hash=hash_refresh_token(token),
        expires_at=now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )
    return token, session


def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
    database: Annotated[Session, Depends(get_db)],
) -> User:
    def unauthorized() -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Érvénytelen vagy lejárt bejelentkezési token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if credentials is None:
        raise unauthorized()

    try:
        payload = jwt.decode(
            credentials.credentials,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
        )
        subject = payload.get("sub")
        user_id = int(subject)
    except (jwt.InvalidTokenError, TypeError, ValueError):
        raise unauthorized() from None

    user = database.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise unauthorized()

    return user


def get_optional_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
    database: Annotated[Session, Depends(get_db)],
) -> User | None:
    if credentials is None:
        return None

    try:
        return get_current_user(credentials, database)
    except HTTPException:
        return None
