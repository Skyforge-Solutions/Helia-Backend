from datetime import datetime, timedelta , timezone
from typing import Optional
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import os
import uuid
from uuid import uuid4
from app.schemas.models import TokenData
from app.db.session import get_db, AsyncSession

# JWT Settings
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable not set")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 hours
PW_RESET_SCOPE = "pw_reset"
PW_RESET_TTL_MIN = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

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

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        user_id: str = payload.get("user_id")
        if email is None or user_id is None:
            raise credentials_exception
        token_data = TokenData(email=email, user_id=user_id)
    except JWTError:
        raise credentials_exception
    
    # Import here to avoid circular imports
    from app.db.crud import get_user_by_email
    
    # Pass the session explicitly
    user = await get_user_by_email(token_data.email, session=db)
    if user is None:
        raise credentials_exception
    
    return user

def generate_user_id():
    return str(uuid.uuid4())

# oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

# def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
#     to_encode = data.copy()
#     if expires_delta:
#         expire = datetime.now(timezone.utc) + expires_delta
#     else:
#         expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
#     to_encode.update({"exp": expire})
#     encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
#     return encoded_jwt

# async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
#     credentials_exception = HTTPException(
#         status_code=status.HTTP_401_UNAUTHORIZED,
#         detail="Could not validate credentials",
#         headers={"WWW-Authenticate": "Bearer"},
#     )
#     try:
#         payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
#         email: str = payload.get("sub")
#         user_id: str = payload.get("user_id")
#         if email is None or user_id is None:
#             raise credentials_exception
#         token_data = TokenData(email=email, user_id=user_id)
#     except JWTError:
#         raise credentials_exception
    
#     # Import here to avoid circular imports
#     from app.db.crud import get_user_by_email
    
#     # Pass the session explicitly
#     user = await get_user_by_email(token_data.email, session=db)
#     if user is None:
#         raise credentials_exception
    
#     return user

# def generate_user_id():
#     return str(uuid.uuid4())