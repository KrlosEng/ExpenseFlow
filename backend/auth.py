"""
Autenticación de ExpenseFlow.

- Contraseñas con scrypt (librería estándar), sal aleatoria por usuario.
- Sesión: JWT firmado (HS256) guardado en una cookie HttpOnly + SameSite=Lax,
  así el JavaScript del navegador nunca ve el token.
- Límite de intentos en login/registro (en memoria; en serverless es por instancia).
"""
import base64
import hashlib
import hmac
import logging
import os
import re
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Literal

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator

try:
    from database import get_db, seed_user_data
except ImportError:
    from backend.database import get_db, seed_user_data

Currency = Literal["COP", "USD", "EUR", "MXN"]

log = logging.getLogger("expenseflow.auth")

COOKIE_NAME = "ef_session"
SESSION_DAYS = 7
IS_DEPLOYED = bool(os.environ.get("VERCEL")) or os.environ.get("ENV") == "production"
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "1" if IS_DEPLOYED else "0") == "1"

SECRET_KEY = os.environ.get("SECRET_KEY", "")
if not SECRET_KEY:
    if IS_DEPLOYED:
        raise RuntimeError(
            "Falta la variable de entorno SECRET_KEY "
            "(genera una con: python -c \"import secrets; print(secrets.token_urlsafe(48))\")"
        )
    SECRET_KEY = secrets.token_urlsafe(48)
    log.warning("SECRET_KEY no definida: se usa una temporal y las sesiones se pierden al reiniciar.")

# --- Contraseñas ---
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, dklen=32, **_SCRYPT)

    def b64(raw: bytes) -> str:
        return base64.b64encode(raw).decode()

    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${b64(salt)}${b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt),
                                n=int(n), r=int(r), p=int(p), dklen=len(expected))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


# Hash ficticio para que el login tarde lo mismo exista o no el correo
_DUMMY_HASH = hash_password(secrets.token_hex(8))

# --- Límite de intentos ---
RATE_LIMIT = 10          # intentos
RATE_WINDOW = 5 * 60     # segundos
_attempts = defaultdict(deque)


def rate_limit(request: Request):
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    q = _attempts[ip]
    while q and now - q[0] > RATE_WINDOW:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Demasiados intentos. Espera unos minutos.")
    q.append(now)


# --- Sesión ---
def _issue_session(response: Response, user_id: int):
    exp = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    token = jwt.encode({"sub": str(user_id), "exp": exp}, SECRET_KEY, algorithm="HS256")
    response.set_cookie(
        COOKIE_NAME, token, max_age=SESSION_DAYS * 86400, httponly=True,
        secure=COOKIE_SECURE, samesite="lax", path="/",
    )


def current_user(request: Request) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="No has iniciado sesión")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada")
    with get_db() as db:
        user = db.fetchone("SELECT id, email, name, currency FROM users WHERE id = ?", (user_id,))
    if not user:
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada")
    return user


# --- Modelos ---
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Credentials(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL_RE.match(v):
            raise ValueError("correo inválido")
        return v


class Registration(Credentials):
    name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=128)
    sample_data: bool = False
    currency: Currency = "COP"

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("no puede estar vacío")
        return v


# --- Rutas ---
router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", status_code=201, dependencies=[Depends(rate_limit)])
def register(data: Registration, response: Response):
    with get_db() as db:
        if db.fetchone("SELECT id FROM users WHERE email = ?", (data.email,)):
            raise HTTPException(status_code=409, detail="Ya existe una cuenta con ese correo")
        user_id = db.insert(
            "INSERT INTO users (email, name, password_hash, currency) VALUES (?, ?, ?, ?)",
            (data.email, data.name, hash_password(data.password), data.currency),
        )
        seed_user_data(db, user_id, with_samples=data.sample_data)
    _issue_session(response, user_id)
    return {"id": user_id, "email": data.email, "name": data.name, "currency": data.currency}


@router.post("/login", dependencies=[Depends(rate_limit)])
def login(data: Credentials, response: Response):
    with get_db() as db:
        user = db.fetchone("SELECT id, email, name, currency, password_hash FROM users WHERE email = ?", (data.email,))
    ok = verify_password(data.password, user["password_hash"] if user else _DUMMY_HASH)
    if not user or not ok:
        raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos")
    _issue_session(response, user["id"])
    return {"id": user["id"], "email": user["email"], "name": user["name"], "currency": user["currency"]}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"message": "Sesión cerrada"}


@router.get("/me")
def me(user: dict = Depends(current_user)):
    return user


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    currency: Currency | None = None


@router.put("/me")
def update_me(data: ProfileUpdate, user: dict = Depends(current_user)):
    """Cambia el nombre o la moneda con que se muestran los montos (no convierte los montos guardados)."""
    with get_db() as db:
        if data.name is not None:
            db.execute("UPDATE users SET name = ? WHERE id = ?", (data.name.strip(), user["id"]))
        if data.currency is not None:
            db.execute("UPDATE users SET currency = ? WHERE id = ?", (data.currency, user["id"]))
        return db.fetchone("SELECT id, email, name, currency FROM users WHERE id = ?", (user["id"],))
