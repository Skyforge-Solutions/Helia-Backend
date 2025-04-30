from datetime import datetime, timedelta, timezone
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
import sqlalchemy
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.session import get_db
from app.utils.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    create_refresh_token,
    create_pw_reset_token,
    decode_refresh_token,
    decode_pw_reset_token,
    get_current_user,
)
from app.utils.password import verify_password, get_password_hash
from app.utils.otp import gen_otp, mail_otp, mail_reset_link
from app.schemas.models import (
    AuthResponse,
    EmailChangeRequestIn,
    EmailChangeVerifyIn,
    PasswordUpdate,
    PWResetRequestIn,
    PWResetVerifyIn,
    TokenRefreshRequest,
    EmailVerificationVerifyIn,
    UserCreate,
    UserSchema,
)
from app.db.crud import (
    authenticate_user,
    create_email_change_request,
    create_email_verification_request,
    create_user,
    get_latest_pending_email_request,
    get_latest_pending_verification_request,
    get_refresh_token,
    get_user_by_email,
    get_user_profile,
    is_token_used,
    mark_email_request_verified,
    mark_email_verification_verified,
    revoke_refresh_token,
    store_refresh_token,
    store_used_jti,
)

OTP_TTL_MIN = 15

router = APIRouter(prefix="/auth", tags=["authentication"])


# ──f─────────────────────────── register  ───────────────────────────────────────


@router.post("/register", response_model=UserSchema, status_code=201)
async def register_user(
    body: UserCreate,
    db:   AsyncSession = Depends(get_db),
):
    # Change this line to search for both verified and unverified users
    existing = await get_user_by_email(body.email, db, verified_only=False)
    
    if existing and existing.is_verified:
        raise HTTPException(400, "Email already registered")

    if existing and not existing.is_verified:
        # Update password if provided again (optional)
        if body.password:
            existing.password = get_password_hash(body.password)
        user = existing
    else:
        profile = body.model_dump(exclude={"password"})
        user    = await create_user(body.email, body.password, db, profile)

    otp = gen_otp()

    # invalidate any previous request and create a fresh one
    prev = await get_latest_pending_verification_request(user.id, db)
    if prev:
        prev.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()  # Don't forget to commit changes
    
    await create_email_verification_request(user, user.email, otp, db)
    mail_otp(user.email, otp)

    return user

# ─────────f──────────────── e-mail verification (initial) ──────────────────────
@router.post("/verify-email", status_code=204)
async def verify_email(body: EmailVerificationVerifyIn, db: AsyncSession = Depends(get_db)):
    print("verify_email", body)
    user = await get_user_by_email(body.email, db,verified_only=False)
    if not user:
        raise HTTPException(404, "User not found")

    req = await get_latest_pending_verification_request(user.id, db)
    if not req or req.expires_at < datetime.now(timezone.utc):
        raise HTTPException(400, "OTP expired or no pending request")

    if not verify_password(body.otp, req.otp_hash):
        raise HTTPException(400, "Invalid OTP")

    await mark_email_verification_verified(req, db)


# ─────────f──────────────── email change (2-step) ──────────────────────────────
@router.post("/email/request", status_code=202)
async def email_change_request(
    body: EmailChangeRequestIn,
    current: UserSchema      = Depends(get_current_user),
    db:      AsyncSession    = Depends(get_db),
):
    # 1) Authenticate & validate
    if not verify_password(body.current_password, current.password):
        raise HTTPException(400, "Current password incorrect")
    
    # 2) Basic sanity checks
    if body.new_email == current.email:
        raise HTTPException(400, "New email is the same as current email")

     # Check if email already in use by a verified user
    if await get_user_by_email(body.new_email, db):
        raise HTTPException(400, "Email already in use")

    # 3) Check for existing pending change-requests
    now = datetime.now(timezone.utc)

    from sqlalchemy import select
    from app.db.models import EmailChangeRequest
    
    stmt = select(EmailChangeRequest).where(
        EmailChangeRequest.new_email == body.new_email,
        EmailChangeRequest.verified == False,
        EmailChangeRequest.expires_at > now
    )
    
    pending = (await db.execute(stmt)).scalar_one_or_none()
    otp  = gen_otp()
    
    try:
        # If pending exists for another user
        if pending and pending.user_id != current.id:
            raise HTTPException(400, "That email is already pending verification by another user")
            
        # If pending exists for this user, update it
        if pending and pending.user_id == current.id:
            pending.otp_hash = get_password_hash(otp)
            pending.expires_at = now + timedelta(minutes=OTP_TTL_MIN)
            await db.commit()
        else:
            # 4) Create a fresh request
            req = EmailChangeRequest(
                id=str(uuid4()),
                user_id=current.id,
                new_email=body.new_email,
                otp_hash=get_password_hash(otp),
                expires_at=now + timedelta(minutes=OTP_TTL_MIN),
                verified=False
            )
            db.add(req)
            await db.commit()
            
        # 5) Send OTP to the new email
        mail_otp(body.new_email, otp)
        return {"message": "OTP sent to new email"}
    except sqlalchemy.exc.IntegrityError as e:
        # DB-level guard: Catch uniqueness violation
        if "email_change_requests_new_email_active_idx" in str(e) or "email_change_requests_new_email_key" in str(e):
            # Handle the race condition - another request slipped through
            await db.rollback()
            raise HTTPException(400, "That email is already pending verification by another user")
        # Re-raise any other integrity errors
        raise

@router.post("/email/verify", status_code=204)
async def email_change_verify(
    body: EmailChangeVerifyIn,
    current: UserSchema = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 1) Lookup the single most-recent pending request for this user
    req = await get_latest_pending_email_request(current.id, db)
    
    # 2) Existence & TTL check
    now = datetime.now(timezone.utc)
    if not req or req.expires_at < now:
        raise HTTPException(400, "OTP expired or no pending request")
    
    # 3) OTP check
    if not verify_password(body.otp, req.otp_hash):
        raise HTTPException(400, "Invalid OTP")
    
    # 4) Mark verified and update user's email
    req.verified = True
    req.user.email = req.new_email
    await db.commit()
    
    return None  # 204 No Content

# ──────────f─────────────── password reset (e-mail link) ───────────────────────
@router.post("/password-reset/request", status_code=202)
async def pw_reset_request(body: PWResetRequestIn, db: AsyncSession = Depends(get_db)):
    user = await get_user_by_email(body.email, db)
    if user:
        token = create_pw_reset_token(user.id)
        mail_reset_link(user.email, f"https://app/reset/{token}")
    # respond the same either way
    return {"message": "If that e-mail exists, a reset link was sent"}

@router.post("/password-reset/verify", status_code=204)
async def pw_reset_verify(body: PWResetVerifyIn, db: AsyncSession = Depends(get_db)):
    payload = decode_pw_reset_token(body.token)
    if await is_token_used(payload["jti"], db):
        raise HTTPException(400, "Link already used")

    user = await get_user_profile(payload["sub"], db)
    if not user:
        raise HTTPException(400, "User not found")

    user.password = get_password_hash(body.new_password)
    await store_used_jti(payload["jti"], datetime.fromtimestamp(payload["exp"], timezone.utc), db)




# ───────────────────────────── login  ──────────────────────────────────────────
@router.post("/token", response_model=AuthResponse)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db:   AsyncSession              = Depends(get_db),
):
    user = await authenticate_user(form.username, form.password, session=db)
    if not user:
        raise HTTPException(401, "Incorrect credentials or account not verified")

    access_token = create_access_token(
        {"sub": user.email, "user_id": user.id},
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    refresh_token, exp = create_refresh_token({"sub": user.email, "user_id": user.id})
    await store_refresh_token(user.id, refresh_token, exp, db)

    return {
        "access_token":  access_token,
        "refresh_token": refresh_token,
        "user_name":     user.name or "User",
    }

# ───────────────────────── token refresh  ──────────────────────────────────────
@router.post("/token/refresh", response_model=AuthResponse)
async def refresh(body: TokenRefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = decode_refresh_token(body.refresh_token)
    if not payload:
        raise HTTPException(401, "Invalid refresh token")

    user_id = payload["user_id"]
    user    = await get_user_profile(user_id, db)
    if not user:
        raise HTTPException(401, "User not found")

    # rotate token
    if not await revoke_refresh_token(body.refresh_token, db):
        raise HTTPException(401, "Token has been revoked")

    access_token = create_access_token(
        {"sub": user.email, "user_id": user.id},
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    new_refresh, exp = create_refresh_token({"sub": user.email, "user_id": user.id})
    await store_refresh_token(user.id, new_refresh, exp, db)

    return {
        "access_token": access_token,
        "refresh_token": new_refresh,
        "token_type": "bearer",
        "user_name": user.name,
    }

# ─────────────────────────── user profile  ─────────────────────────────────────
@router.get("/me", response_model=UserSchema)
async def me(
    current: UserSchema = Depends(get_current_user)
    ):
        return current

@router.patch("/password", status_code=204)
async def change_password(
    body: PasswordUpdate,
    current: User             = Depends(get_current_user),
    db:     AsyncSession      = Depends(get_db),
):
    if not verify_password(body.current_password, current.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password incorrect",
        )
    current.password = get_password_hash(body.new_password)
    await db.commit()


