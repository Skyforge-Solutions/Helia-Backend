from datetime import datetime, timedelta , timezone
from typing import Optional
import os
from uuid import uuid4

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from app.schemas.models import TokenData
from app.db.session import get_db, AsyncSession
from app.db.crud import get_user_profile 


# ─────────────────────────  JWT / constant config  ────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable not set")

REFRESH_TOKEN_SECRET = os.getenv("REFRESH_TOKEN_SECRET", SECRET_KEY)

ALGORITHM                    = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES  = 20
REFRESH_TOKEN_EXPIRE_DAYS    = 7
PW_RESET_SCOPE               = "pw_reset"
PW_RESET_TTL_MIN             = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

# ─────────────────────────────  helpers  ──────────────────────────────────────

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

def _encode(
        payload: dict, 
        key: str, 
        ttl: timedelta,
    ) -> str:
        payload = {**payload, "exp": _utc_now() + ttl}
        return jwt.encode(payload, key, algorithm=ALGORITHM)

def create_access_token(
        data: dict,
        expires_delta: Optional[timedelta] = None
    ) -> str:
        ttl = expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        return _encode(data, SECRET_KEY, ttl)


def create_refresh_token(
        data: dict,
        expires_delta: Optional[timedelta] = None
    ) -> tuple[str, datetime]:
    ttl = expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    exp = _utc_now() + ttl
    token = jwt.encode(
        {**data, "exp": exp, "jti": str(uuid4())},
        REFRESH_TOKEN_SECRET,
        algorithm=ALGORITHM,
    )
    return token, exp


def decode_refresh_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, REFRESH_TOKEN_SECRET, algorithms=[ALGORITHM])
    except JWTError:
        return None


# def create_pw_reset_token(user_id: str) -> str:
#     return create_access_token(
#         {
#         "sub": user_id, 
#          "scope": PW_RESET_SCOPE, 
#          "jti": str(uuid4())
#          },
#         timedelta(minutes=PW_RESET_TTL_MIN),
#     )

def create_pw_reset_token(user_id: str) -> str:
    """Generate a JWT for password reset with user_id, scope, and unique jti."""
    return create_access_token(
        data={
            "sub": user_id,
            "scope": PW_RESET_SCOPE,
            "jti": str(uuid4()),
        },
        expires_delta=timedelta(minutes=PW_RESET_TTL_MIN),
    )

def decode_pw_reset_token(token: str) -> dict:
    """Verify JWT signature, expiration, and scope; return payload."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=400, detail="Link invalid or expired")
    if payload.get("scope") != PW_RESET_SCOPE:
        raise HTTPException(status_code=400, detail="Wrong token scope")
    return payload


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db:    AsyncSession = Depends(get_db),
):
    cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("user_id")
        if user_id is None:
            raise cred_exc
    except JWTError:
        raise cred_exc

    user = await get_user_profile(user_id, db)
    if user is None or not user.is_active or not user.is_verified:
        raise cred_exc
    return user
