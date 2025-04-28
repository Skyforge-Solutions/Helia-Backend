from uuid import uuid4
from sqlalchemy.future import select
from sqlalchemy import func
from app.db.session import AsyncSessionLocal, AsyncSession
from app.db.models import User, ChatSession, ChatMessage, UsedPWResetToken, RefreshToken,EmailVerificationRequest
from app.utils.password import get_password_hash, verify_password
from app.db.models import EmailChangeRequest
from datetime import datetime, timedelta, timezone

OTP_TTL_MIN = 15

async def get_or_create_user(user_id: str, profile: dict) -> User:
    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
        if user:
            return user
        user = User(id=user_id, **profile)
        session.add(user)
        await session.commit()
        return user

async def get_or_create_session(user_id: str, chat_id: str, name: str = "New ChatSession") -> ChatSession:
    async with AsyncSessionLocal() as session:
        cs = await session.get(ChatSession, chat_id)
        if cs:
            # bump updated_at
            cs.updated_at = func.now()
            await session.commit()
            await session.refresh(cs)
            return cs
        cs = ChatSession(id=chat_id, user_id=user_id, name=name)
        session.add(cs)
        await session.commit()
        await session.refresh(cs)
        return cs

async def list_sessions(user_id: str) -> list[ChatSession]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(ChatSession.updated_at.desc())
        )
        return result.scalars().all()

async def add_message(chat_id: str, role: str, content: str, image_url: str = None) -> ChatMessage:
    async with AsyncSessionLocal() as session:
        msg = ChatMessage(
            id=str(uuid4()),
            chat_id=chat_id,
            role=role,
            content=content,
            image_url=image_url
        )
        session.add(msg)
        await session.commit()
        return msg

async def get_messages(chat_id: str) -> list[ChatMessage]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ChatMessage)
            .where(ChatMessage.chat_id == chat_id)
            .order_by(ChatMessage.timestamp)
        )
        return result.scalars().all()

async def update_user_profile(user_id: str, profile: dict) -> User:
    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
        if not user:
            return None
            
        # Update user attributes from profile dict
        for key, value in profile.items():
            if hasattr(user, key):
                setattr(user, key, value)
                
        await session.commit()
        return user

async def get_user_profile(user_id: str) -> User:
    async with AsyncSessionLocal() as session:
        return await session.get(User, user_id)

async def update_session_name(chat_id: str, name: str) -> ChatSession:
    async with AsyncSessionLocal() as session:
        chat_session = await session.get(ChatSession, chat_id)
        if not chat_session:
            return None
        
        chat_session.name = name
        chat_session.updated_at = func.now()
        await session.commit()
        await session.refresh(chat_session)
        return chat_session

async def delete_chat_session(chat_id: str) -> bool:
    async with AsyncSessionLocal() as session:
        chat_session = await session.get(ChatSession, chat_id)
        if not chat_session:
            return False
        
        # Delete from memory store if exists
        from app.chains.base import chat_memory_store
        if chat_id in chat_memory_store:
            del chat_memory_store[chat_id]
        
        # The cascade will handle message deletion
        await session.delete(chat_session)
        await session.commit()
        return True

async def get_chat_session(chat_id: str) -> ChatSession:
    async with AsyncSessionLocal() as session:
        return await session.get(ChatSession, chat_id)

async def get_user_by_email(email: str, session: AsyncSession = None) -> User:
    """Get a user by email with improved session handling."""
    # If no external session is provided, create a new one
    if session is None:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(User).where(User.email == email)
            )
            return result.scalars().first()
    else:
        # Use the provided session
        result = await session.execute(
            select(User).where(User.email == email)
        )
        return result.scalars().first()

async def create_user(email: str, password: str, profile: dict = None) -> User:
    async with AsyncSessionLocal() as session:
        # Generate a unique user ID
        user_id = str(uuid4())
        
        # Hash the password
        hashed_password = get_password_hash(password)
        
        # Create default profile if none provided
        if profile is None:
            profile = {}
        
        # Remove email from profile to avoid duplicate keyword argument
        profile.pop('email', None)
            
        # Create the user with required fields and any optional profile fields
        user = User(
            id=user_id,
            email=email,
            password=hashed_password,
            **profile
        )
        
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user

async def authenticate_user(email: str, password: str, session: AsyncSession = None) -> User:
    """Authenticate a user with improved session handling."""
    user = await get_user_by_email(email, session)
    if not user:
        return None
    if not verify_password(password, user.password):
        return None
    if not user.is_active or not user.is_verified:
        return None
    return user

async def create_email_change_request(user, new_email: str, otp_plain: str, session: AsyncSession):
    req = EmailChangeRequest(
        id=str(uuid4()),
        user_id=user.id,
        new_email=new_email,
        otp_hash=get_password_hash(otp_plain),
        expires_at=datetime.utcnow() + timedelta(minutes=OTP_TTL_MIN),
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)
    return req

async def get_latest_pending_email_request(user_id: str, session: AsyncSession):
    result = await session.execute(
        select(EmailChangeRequest)
        .where(
            EmailChangeRequest.user_id == user_id,
            EmailChangeRequest.verified == False,
        )
        .order_by(EmailChangeRequest.expires_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()

async def mark_email_request_verified(req: EmailChangeRequest, session: AsyncSession):
    req.verified = True
    req.user.email = req.new_email
    await session.commit()

async def is_token_used(jti: str, session: AsyncSession) -> bool:
    result = await session.execute(
        select(UsedPWResetToken).where(UsedPWResetToken.jti == jti)
    )
    return result.scalar_one_or_none() is not None

async def store_used_jti(jti: str, expires_at: datetime, session: AsyncSession):
    token = UsedPWResetToken(jti=jti, expires_at=expires_at)
    session.add(token)
    await session.commit()

# Refresh token CRUD operations
async def store_refresh_token(user_id: str, token: str, expires_at: datetime, session: AsyncSession = None) -> RefreshToken:
    """Store a refresh token in the database."""
    close_session = False
    if session is None:
        session = AsyncSessionLocal()
        close_session = True
    
    try:
        refresh_token = RefreshToken(
            id=str(uuid4()),
            user_id=user_id,
            token=token,
            expires_at=expires_at
        )
        session.add(refresh_token)
        await session.commit()
        await session.refresh(refresh_token)
        return refresh_token
    finally:
        if close_session:
            await session.close()

async def get_refresh_token(token: str, session: AsyncSession = None) -> RefreshToken:
    """Get a refresh token by its value."""
    close_session = False
    if session is None:
        session = AsyncSessionLocal()
        close_session = True
    
    try:
        result = await session.execute(
            select(RefreshToken)
            .where(RefreshToken.token == token, RefreshToken.revoked == False)
        )
        return result.scalar_one_or_none()
    finally:
        if close_session:
            await session.close()

async def revoke_refresh_token(token: str, session: AsyncSession = None) -> bool:
    """Mark a refresh token as revoked."""
    close_session = False
    if session is None:
        session = AsyncSessionLocal()
        close_session = True
    
    try:
        result = await session.execute(
            select(RefreshToken)
            .where(RefreshToken.token == token)
        )
        refresh_token = result.scalar_one_or_none()
        
        if not refresh_token:
            return False
            
        refresh_token.revoked = True
        await session.commit()
        return True
    finally:
        if close_session:
            await session.close()

async def create_email_verification_request(user, email: str, otp_plain: str, session: AsyncSession):
    req = EmailVerificationRequest(
        id=str(uuid4()),
        user_id=user.id,
        email=email,
        otp_hash=get_password_hash(otp_plain),
        expires_at= datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MIN),
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)
    return req

async def get_latest_pending_verification_request(user_id: str, session: AsyncSession):
    result = await session.execute(
        select(EmailVerificationRequest)
        .where(
            EmailVerificationRequest.user_id == user_id,
            EmailVerificationRequest.verified == False,
        )
        .order_by(EmailVerificationRequest.expires_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()

async def mark_email_verification_verified(req: EmailVerificationRequest, session: AsyncSession):
    req.verified = True
    req.user.is_verified = True
    req.user.is_active = True
    await session.commit()