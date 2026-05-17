"""
JWT HS256 implémenté en pure Python stdlib (hmac + hashlib).
Pas de dépendance à `cryptography` ou `python-jose`.
"""
import base64
import hashlib
import hmac
import json
import time
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext

from config import settings

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


# ── Pure-Python JWT HS256 ─────────────────────────────────────────────────────

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * padding)


def _sign(header_b64: str, payload_b64: str, secret: str) -> str:
    msg = f"{header_b64}.{payload_b64}".encode()
    sig = hmac.new(secret.encode(), msg, hashlib.sha256).digest()
    return _b64url_encode(sig)


def create_access_token(username: str, expires_in_minutes: Optional[int] = None) -> str:
    minutes = expires_in_minutes or settings.access_token_expire_minutes
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url_encode(json.dumps({
        "sub": username,
        "exp": int(time.time()) + minutes * 60,
        "iat": int(time.time()),
    }).encode())
    signature = _sign(header, payload, settings.secret_key)
    return f"{header}.{payload}.{signature}"


def _decode_token(token: str) -> dict:
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except ValueError:
        raise ValueError("Malformed token")

    expected_sig = _sign(header_b64, payload_b64, settings.secret_key)
    if not hmac.compare_digest(expected_sig, sig_b64):
        raise ValueError("Invalid signature")

    payload = json.loads(_b64url_decode(payload_b64))
    if payload.get("exp", 0) < int(time.time()):
        raise ValueError("Token expired")
    return payload


# ── Password utilities ────────────────────────────────────────────────────────

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


# ── FastAPI dependency ────────────────────────────────────────────────────────

def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token invalide ou expiré",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = _decode_token(token)
        username = payload.get("sub")
        if not username:
            raise exc
        return username
    except ValueError:
        raise exc
