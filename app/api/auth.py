from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
from app.schemas.models import UserCreate, UserSchema, AuthResponse, PWResetRequestIn, PWResetVerifyIn, TokenRefreshRequest
from app.db.crud import (
    create_user, authenticate_user, get_user_by_email, is_token_used, store_used_jti,
    store_refresh_token, get_refresh_token, revoke_refresh_token, get_user_profile
)
from app.utils.auth import (
    create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES, get_current_user, 
    create_pw_reset_token, decode_pw_reset_token, create_refresh_token, decode_refresh_token
)
from app.db.session import get_db, AsyncSession
from app.db.models import User
from app.schemas.models import (
    PasswordUpdate,
    EmailChangeRequestIn,
    EmailChangeVerifyIn,
)
from app.utils.password import verify_password, get_password_hash
from app.utils.otp import gen_otp, mail_otp, mail_reset_link
from app.db.crud import (
    create_email_change_request,
    get_latest_pending_email_request,
    mark_email_request_verified,
)
from datetime import datetime, timedelta, timezone
import os

router = APIRouter()

@router.post("/register", response_model=UserSchema,status_code=status.HTTP_201_CREATED)
async def register_user(user: UserCreate, db: AsyncSession = Depends(get_db)):
    db_user = await get_user_by_email(user.email, session=db)
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    
    user_data = user.model_dump() 
    password = user_data.pop("password")
    created_user = await create_user(email=user.email, password=password, profile=user_data)
    
    return created_user

@router.post("/token", response_model=AuthResponse)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(form_data.username, form_data.password, session=db)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create access token with user email as subject and user_id as additional claim
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email, "user_id": user.id},
        expires_delta=access_token_expires
    )
    
    # Create refresh token
    refresh_token, expires_at = create_refresh_token(
        data={"sub": user.email, "user_id": user.id}
    )
    
    # Store refresh token in database
    await store_refresh_token(user.id, refresh_token, expires_at, session=db)
    
    return {
        "access_token": access_token, 
        "refresh_token": refresh_token,
        "user_name": user.name
    }

@router.post("/token/refresh", response_model=AuthResponse)
async def refresh_token(
    body: TokenRefreshRequest,
    db: AsyncSession = Depends(get_db)
):
    # Decode the refresh token
    payload = decode_refresh_token(body.refresh_token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if token exists in database and is not revoked
    token_obj = await get_refresh_token(body.refresh_token, session=db)
    if not token_obj:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get user data
    user_id = payload.get("user_id")
    email = payload.get("sub")
    
    if not user_id or not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get user from database
    user = await get_user_profile(user_id)
    if not user or user.email != email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Security: Revoke the old refresh token (token rotation)
    await revoke_refresh_token(body.refresh_token, session=db)
    
    # Create new access token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email, "user_id": user.id},
        expires_delta=access_token_expires
    )
    
    # Create new refresh token
    new_refresh_token, expires_at = create_refresh_token(
        data={"sub": user.email, "user_id": user.id}
    )
    
    # Store new refresh token in database
    await store_refresh_token(user.id, new_refresh_token, expires_at, session=db)
    
    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "user_name": user.name
    }

@router.get("/me", response_model=UserSchema)
async def read_users_me(current_user: UserSchema = Depends(get_current_user)):
    return current_user


@router.patch("/password", status_code=204)
async def update_password(
    body: PasswordUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(body.current_password, current_user.password):
        raise HTTPException(status_code=400, detail="Current password incorrect")

    current_user.password = get_password_hash(body.new_password)
    await db.commit()
    return None  # 204 No Content

# -----------------------------------------------------------
#  EMAIL CHANGE – STEP 1 (request)
# -----------------------------------------------------------
@router.post("/email/request", status_code=202)
async def email_change_request(
    body: EmailChangeRequestIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Password check
    if not verify_password(body.current_password, current_user.password):
        raise HTTPException(status_code=400, detail="Current password incorrect")

    # Email uniqueness
    if await get_user_by_email(body.new_email, session=db):
        raise HTTPException(status_code=400, detail="Email already in use")

    # Prevent changing to the same email
    if body.new_email == current_user.email:
        raise HTTPException(status_code=400, detail="New email is the same as current email")

    # Generate OTP
    otp = gen_otp()

    # Check for existing pending request
    existing_req = await get_latest_pending_email_request(current_user.id, db)
    if existing_req:
        # Update existing request
        existing_req.new_email = body.new_email
        existing_req.otp_hash = get_password_hash(otp)
        existing_req.expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        existing_req.verified = False
        await db.commit()
        await db.refresh(existing_req)
    else:
        # Create new request
        await create_email_change_request(current_user, body.new_email, otp, db)

    # Send OTP
    mail_otp(body.new_email, otp)

    return {"message": "OTP sent to new email"}

# -----------------------------------------------------------
#  EMAIL CHANGE – STEP 2 (verify OTP)
# -----------------------------------------------------------
@router.post("/email/verify", status_code=204)
async def email_change_verify(
    body: EmailChangeVerifyIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    req = await get_latest_pending_email_request(current_user.id, db)
    if not req:
        raise HTTPException(status_code=404, detail="No pending request")

    if req.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="OTP expired")

    if not verify_password(body.otp, req.otp_hash):
        raise HTTPException(status_code=400, detail="Invalid OTP")

    await mark_email_request_verified(req, db)
    return None  # 204


@router.post("/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
async def pw_reset_request(
    body: PWResetRequestIn,
    db: AsyncSession = Depends(get_db),
):
    user = await get_user_by_email(body.email, session=db)
    if user:
        raw_token = create_pw_reset_token(user.id)
        url = f"test/reset/{raw_token}"
        mail_reset_link(user.email, url)
    return {"message": "If that e-mail exists, a reset link was sent"}

@router.post("/password-reset/verify", status_code=status.HTTP_204_NO_CONTENT)
async def pw_reset_verify(
    body: PWResetVerifyIn,
    db: AsyncSession = Depends(get_db),
):
    payload = decode_pw_reset_token(body.token)
    if await is_token_used(payload["jti"], db):
        raise HTTPException(status_code=400, detail="Link already used")
    user = await db.get(User, payload["sub"])
    if not user:
        raise HTTPException(status_code=400, detail="User not found")
    user.password = get_password_hash(body.new_password)
    await store_used_jti(payload["jti"], datetime.fromtimestamp(payload["exp"], timezone.utc), db)
    await db.commit()
    return None