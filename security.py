"""
Auth model
----------
The browser never talks to this API directly. The flow is:

  Browser --(session cookie)--> chatbot.php --(signed JWT, server-to-server)--> FastAPI

`chatbot.php` already knows who is logged in via PHP's own session
(`$_SESSION['student_id']`, `$_SESSION['university_id']`, etc.) and the
tenant's `db_name`. It mints a short-lived JWT (HS256, ~60s expiry) with
that information and sends it in the `Authorization: Bearer <token>` header
on every call to this API. The API trusts nothing else about the caller's
identity — role, user id and db_name are always read from the verified
token, never from the JSON body.
"""
from dataclasses import dataclass
from typing import Optional

import jwt
from fastapi import Header, HTTPException

from config import settings

ALLOWED_ROLES = {"student", "teacher", "admin", "university"}


@dataclass
class AuthContext:
    role: str
    user_id: int
    db_name: str
    university_id: Optional[int] = None
    lang: str = "fr"
    display_name: Optional[str] = None


def _decode(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["exp", "iat", "sub", "role", "db"]},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token.")

    # Belt-and-braces: reject tokens minted with a suspiciously long lifetime,
    # in case JWT_MAX_AGE_SECONDS was misconfigured on the PHP side.
    if payload["exp"] - payload["iat"] > settings.JWT_MAX_AGE_SECONDS + 5:
        raise HTTPException(status_code=401, detail="Token lifetime too long.")

    if payload.get("role") not in ALLOWED_ROLES:
        raise HTTPException(status_code=401, detail="Unknown role.")

    return payload


def get_auth_context(authorization: str = Header(None)) -> AuthContext:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    token = authorization.split(" ", 1)[1].strip()
    payload = _decode(token)

    return AuthContext(
        role=payload["role"],
        user_id=int(payload["sub"]),
        db_name=payload["db"],
        university_id=payload.get("university_id"),
        lang=payload.get("lang", settings.DEFAULT_LANG),
        display_name=payload.get("name"),
    )


def require_role(ctx: AuthContext, *roles: str):
    if ctx.role not in roles:
        raise HTTPException(status_code=403, detail="Not authorized for this action.")
