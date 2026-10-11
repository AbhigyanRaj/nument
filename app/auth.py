# Login and sign-up: email + password, hashed, with a secure session cookie.
# Also creates the optional demo account on startup.

"""Email + password accounts with server-side sessions (argon2id hashes, SHA-256 token hashes,
httpOnly cookie). With REQUIRE_AUTH=false the contract endpoints stay open; login gates the UI."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlmodel import Field as SQLField
from sqlmodel import SQLModel, select

from app.config import get_settings
from app.db import get_session

COOKIE = "nument_session"
_hasher = PasswordHasher()
_DUMMY = _hasher.hash("timing-equaliser-password")


class User(SQLModel, table=True):
    __tablename__ = "users"
    id: int | None = SQLField(default=None, primary_key=True)
    email: str = SQLField(index=True, unique=True)
    password_hash: str
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(UTC))


class UserSession(SQLModel, table=True):
    __tablename__ = "user_sessions"
    id: int | None = SQLField(default=None, primary_key=True)
    token_hash: str = SQLField(index=True, unique=True)
    user_id: int
    expires_at: datetime


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=10, max_length=200)


router = APIRouter(prefix="/auth", tags=["auth"])


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _check_origin(request: Request) -> None:
    if request.headers.get("x-requested-with", "").lower() != "nument":
        raise HTTPException(403, "missing X-Requested-With header")


def _start_session(response: Response, user_id: int) -> None:
    settings = get_settings()
    token = secrets.token_urlsafe(32)
    with get_session() as s:
        s.add(
            UserSession(
                token_hash=_hash_token(token),
                user_id=user_id,
                expires_at=datetime.now(UTC) + timedelta(hours=settings.session_ttl_hours),
            )
        )
        s.commit()
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
        max_age=settings.session_ttl_hours * 3600,
    )


def current_user(token: str | None) -> User | None:
    if not token:
        return None
    with get_session() as s:
        sess = s.exec(
            select(UserSession).where(UserSession.token_hash == _hash_token(token))
        ).first()
        if not sess:
            return None
        expires = sess.expires_at if sess.expires_at.tzinfo else sess.expires_at.replace(tzinfo=UTC)
        if expires < datetime.now(UTC):
            return None
        return s.get(User, sess.user_id)


def ensure_demo_user() -> None:
    settings = get_settings()
    email, password = settings.demo_email.strip().lower(), settings.demo_password.get_secret_value()
    if not email or len(password) < 10:
        return
    with get_session() as s:
        if not s.exec(select(User).where(User.email == email)).first():
            s.add(User(email=email, password_hash=_hasher.hash(password)))
            s.commit()


@router.post("/signup")
def signup(body: Credentials, request: Request, response: Response):
    _check_origin(request)
    if not get_settings().allow_signup:
        raise HTTPException(403, "sign-up is disabled")
    email = body.email.strip().lower()
    if "@" not in email:
        raise HTTPException(422, "enter a valid email address")
    with get_session() as s:
        if s.exec(select(User).where(User.email == email)).first():
            raise HTTPException(409, "an account with that email already exists")
        user = User(email=email, password_hash=_hasher.hash(body.password))
        s.add(user)
        s.commit()
        s.refresh(user)
    _start_session(response, user.id)
    return {"email": email}


@router.post("/login")
def login(body: Credentials, request: Request, response: Response):
    _check_origin(request)
    email = body.email.strip().lower()
    with get_session() as s:
        user = s.exec(select(User).where(User.email == email)).first()
    try:
        _hasher.verify(user.password_hash if user else _DUMMY, body.password)
    except VerifyMismatchError:
        user = None
    if not user:
        raise HTTPException(401, "email or password is incorrect")
    _start_session(response, user.id)
    return {"email": user.email}


@router.post("/logout")
def logout(request: Request, response: Response, nument_session: str | None = Cookie(default=None)):
    _check_origin(request)
    if nument_session:
        with get_session() as s:
            for sess in s.exec(
                select(UserSession).where(UserSession.token_hash == _hash_token(nument_session))
            ):
                s.delete(sess)
            s.commit()
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(nument_session: str | None = Cookie(default=None)):
    user = current_user(nument_session)
    if not user:
        raise HTTPException(401, "not signed in")
    return {"email": user.email}
