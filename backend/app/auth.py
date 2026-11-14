from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import RefreshSession, User
from app.schemas import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.security import (
    create_access_token,
    create_refresh_session,
    get_current_user,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.settings import (
    REFRESH_COOKIE_NAME,
    REFRESH_COOKIE_PATH,
    REFRESH_COOKIE_SECURE,
    REFRESH_TOKEN_EXPIRE_DAYS,
)


router = APIRouter(prefix="/api/auth", tags=["hitelesítés"])
DatabaseSession = Annotated[Session, Depends(get_db)]


def set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=REFRESH_COOKIE_SECURE,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        httponly=True,
        secure=REFRESH_COOKIE_SECURE,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
    )


def invalid_refresh_response() -> JSONResponse:
    response = JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": "Érvénytelen vagy lejárt refresh token."},
    )
    clear_refresh_cookie(response)
    return response


def revoke_active_family(database: Session, family_id: str, revoked_at: datetime) -> None:
    database.execute(
        update(RefreshSession)
        .where(
            RefreshSession.family_id == family_id,
            RefreshSession.revoked_at.is_(None),
        )
        .values(revoked_at=revoked_at)
    )
    database.commit()


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    request: RegisterRequest,
    response: Response,
    database: DatabaseSession,
) -> TokenResponse:
    email = str(request.email).strip().lower()
    existing_user = database.scalar(select(User).where(User.email == email))
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ezzel az e-mail-címmel már van fiók.",
        )

    user = User(email=email, password_hash=hash_password(request.password))
    database.add(user)
    try:
        database.flush()
        refresh_token, refresh_session = create_refresh_session(user.id)
        database.add(refresh_session)
        database.commit()
    except IntegrityError:
        database.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ezzel az e-mail-címmel már van fiók.",
        ) from None

    database.refresh(user)
    set_refresh_cookie(response, refresh_token)
    return TokenResponse(access_token=create_access_token(user.id))


@router.post("/login", response_model=TokenResponse)
def login(
    request: LoginRequest,
    response: Response,
    database: DatabaseSession,
) -> TokenResponse:
    email = str(request.email).strip().lower()
    user = database.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Hibás e-mail-cím vagy jelszó.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    refresh_token, refresh_session = create_refresh_session(user.id)
    database.add(refresh_session)
    database.commit()
    set_refresh_cookie(response, refresh_token)
    return TokenResponse(access_token=create_access_token(user.id))


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    request: Request,
    response: Response,
    database: DatabaseSession,
) -> TokenResponse | JSONResponse:
    raw_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not raw_token:
        return invalid_refresh_response()

    refresh_session = database.scalar(
        select(RefreshSession).where(
            RefreshSession.token_hash == hash_refresh_token(raw_token)
        )
    )
    if refresh_session is None:
        return invalid_refresh_response()

    now = datetime.now(timezone.utc)
    if refresh_session.revoked_at is not None:
        revoke_active_family(database, refresh_session.family_id, now)
        return invalid_refresh_response()

    if refresh_session.expires_at <= now:
        refresh_session.revoked_at = now
        database.commit()
        return invalid_refresh_response()

    rotation = database.execute(
        update(RefreshSession)
        .where(
            RefreshSession.id == refresh_session.id,
            RefreshSession.revoked_at.is_(None),
            RefreshSession.expires_at > now,
        )
        .values(revoked_at=now)
    )
    if rotation.rowcount != 1:
        database.rollback()
        revoke_active_family(database, refresh_session.family_id, now)
        return invalid_refresh_response()

    next_refresh_token, next_refresh_session = create_refresh_session(
        refresh_session.user_id,
        family_id=refresh_session.family_id,
    )
    database.add(next_refresh_session)
    database.commit()

    user = database.get(User, refresh_session.user_id)
    if user is None:
        return invalid_refresh_response()

    set_refresh_cookie(response, next_refresh_token)
    return TokenResponse(access_token=create_access_token(user.id))


@router.post("/logout", tags=["hitelesítés"])
def logout(
    request: Request,
    response: Response,
    database: DatabaseSession,
) -> dict[str, str]:
    raw_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if raw_token:
        refresh_session = database.scalar(
            select(RefreshSession).where(
                RefreshSession.token_hash == hash_refresh_token(raw_token)
            )
        )
        if refresh_session is not None and refresh_session.revoked_at is None:
            refresh_session.revoked_at = datetime.now(timezone.utc)
            database.commit()

    clear_refresh_cookie(response)
    return {"status": "logged_out"}


@router.get("/me", response_model=UserResponse)
def get_me(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    return current_user
