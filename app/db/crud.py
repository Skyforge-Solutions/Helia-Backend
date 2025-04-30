from typing import List, Optional
from uuid import uuid4
from sqlalchemy.future import select
from sqlalchemy import func
from app.db.session import AsyncSession
from app.db.models import User, ChatSession, ChatMessage, UsedPWResetToken, RefreshToken,EmailVerificationRequest
from app.utils.password import get_password_hash, verify_password
from app.db.models import EmailChangeRequest
from datetime import datetime, timedelta, timezone


OTP_TTL_MIN = 5


# ──────────────────────────  Chat sessions & messages  ──────────────────────
async def get_or_create_session(
        user_id: str, 
        chat_id: str, 
        session: AsyncSession, 
        name: str = "New Chat"
    ) -> ChatSession:
        """Get or create a chat session."""
        name = "New Chat" if not name else (name[:35] + "..." if len(name) > 35 else name)
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

async def list_sessions(
        user_id: str,
        session: AsyncSession,
        limit: int = 20
    ) -> List[ChatSession]:
        stmt = (
            select(ChatSession.id,
                ChatSession.name,
                ChatSession.created_at,
                ChatSession.updated_at)
            .where(ChatSession.user_id == user_id)
            .order_by(ChatSession.updated_at.desc())
            .limit(limit)
        )
        rows = (await session.execute(stmt)).all()
        return [
            ChatSession(
                id=r.id,
                user_id=user_id,
                name=r.name,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            for r in rows
        ]

async def add_message(
        chat_id: str, 
        role: str, 
        content: str, 
        session: AsyncSession, 
        image_url: str = None
    ) -> ChatMessage:
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

async def get_messages(
        chat_id: str,
        session: AsyncSession
    ) -> List[ChatMessage]:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.chat_id == chat_id)
            .order_by(ChatMessage.timestamp.desc())
        )
        msgs = (await session.execute(stmt)).scalars().all()
        return list(reversed(msgs))

async def get_chat_session_owned(
    chat_id: str,
    user_id: str,
    session: AsyncSession,
) -> Optional[ChatSession]:
    stmt = select(ChatSession).where(
        ChatSession.id == chat_id,
        ChatSession.user_id == user_id,
    )
    return (await session.execute(stmt)).scalar_one_or_none()

async def update_session_name(
        chat_id: str, 
        name: str,
        session: AsyncSession,
    ) -> Optional[ChatSession]:
        cs = await session.get(ChatSession, chat_id)
        if not cs:
            return None
        
        cs.name = name
        cs.updated_at = func.now()
        await session.commit()
        await session.refresh(cs)
        return cs

async def delete_chat_session(
        chat_id: str,
        session: AsyncSession,
    ) -> bool:
    cs = await session.get(ChatSession, chat_id)
    if not cs:
        return False

    # remove from in-memory store
    from app.chains.base import chat_memory_store
    chat_memory_store.pop(chat_id, None)

    await session.delete(cs)
    await session.commit()
    return True

async def get_chat_session(
        chat_id: str,
        session: AsyncSession,
    ) -> Optional[ChatSession]:
        return await session.get(ChatSession, chat_id)

# ─────────────────────────────  Users & auth  ───────────────────────────────

async def get_user_by_email(
        email: str, 
        session: AsyncSession,
        verified_only: bool = True
    ) -> Optional[User]:
        """Get a user by email with improved session handling."""
        stmt = select(User).where(User.email == email)
        if verified_only:
            stmt = stmt.where(User.is_verified == True)  # idx_users_email_verified
        
        return (await session.execute(stmt)).scalar_one_or_none()

async def create_user(
        email: str, 
        password: str, 
        session: AsyncSession, 
        profile: Optional[dict] = None
    ) -> User:
        profile = profile.copy() if profile else {}
        profile.pop("email", None)
        profile.pop("password", None)
        user = User(
            id=str(uuid4()),
            email=email,
            password=get_password_hash(password),
            **profile,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user

async def authenticate_user(
        email: str, 
        password: str, 
        session: AsyncSession,
    ) -> Optional[User]:
        """Authenticate a user with improved session handling."""
        user = await get_user_by_email(email, session)
        if not user:
            return None
        if not verify_password(password, user.password):
            return None
        if not user.is_active or not user.is_verified:
            return None
        return user

async def update_user_profile(
        user_id: str, 
        profile: dict,
        session: AsyncSession,
    ) -> Optional[User]:
        user = await session.get(User, user_id)
        if not user:
            return None
            
        # Update user attributes from profile dict
        for key, value in profile.items():
            if hasattr(user, key):
                setattr(user, key, value)
                
        await session.commit()
        await session.refresh(user)
        return user

async def get_user_profile(
        user_id: str,
        session: AsyncSession
    ) -> Optional[User]:
        return await session.get(User, user_id)

async def get_or_create_user(
        user_id: str,
        profile: dict,
        session: AsyncSession,
    ) -> User:
        user = await session.get(User, user_id)
        if user:
            return user

        user = User(id=user_id, **profile)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


# ------------------------------------OTP / e-mail change / verification --------------------------------------- #

async def create_email_change_request(
        user: User, 
        new_email: str, 
        otp_plain: str, 
        session: AsyncSession
    ):
    req = EmailChangeRequest(
        id=str(uuid4()),
        user_id=user.id,
        new_email=new_email,
        otp_hash=get_password_hash(otp_plain),
        expires_at= datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MIN),
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)
    return req

async def get_latest_pending_email_request(
        user_id: str, 
        session: AsyncSession
    ):
        stmt = (
            select(EmailChangeRequest)
            .where(EmailChangeRequest.user_id == user_id,
                EmailChangeRequest.verified == False)
            .order_by(EmailChangeRequest.expires_at.desc())       # idx_email_change_user_expires
            .limit(1)
        )
        return (await session.execute(stmt)).scalar_one_or_none()

async def get_latest_pending_verification_request(
        user_id: str, 
        session: AsyncSession
    ):
        stmt = (
            select(EmailVerificationRequest)
            .where(EmailVerificationRequest.user_id == user_id,
                EmailVerificationRequest.verified == False,
            )
            .order_by(
                EmailVerificationRequest.expires_at.desc() , # idx_email_verification_user_expires
            )  
            .limit(1)
        )
        return (await session.execute(stmt)).scalar_one_or_none()

async def create_email_verification_request(
        user: User, 
        email: str, 
        otp_plain: str, 
        session: AsyncSession
    ):
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

async def mark_email_request_verified(
        req: EmailChangeRequest, 
        session: AsyncSession,
    ):
        req.verified = True
        req.user.email = req.new_email
        await session.commit()

async def mark_email_verification_verified(
        req: EmailVerificationRequest, 
        session: AsyncSession
    ):
        req.verified = True
        req.user.is_verified = True
        req.user.is_active = True
        await session.commit()

# -----Refresh-token helpers (use partial index on token WHERE revoked = false)-------- #

async def store_refresh_token(
        user_id: str, 
        token: str, 
        expires_at: datetime, 
        session: AsyncSession = None
    ) -> RefreshToken:
        """Store a refresh token in the database."""
        rt = RefreshToken(
            id=str(uuid4()),
            user_id=user_id,
            token=token,
            expires_at=expires_at,
        )
        session.add(rt)
        await session.commit()
        await session.refresh(rt)
        return rt

async def get_refresh_token(
        token: str, 
        session: AsyncSession,
    ) -> Optional[RefreshToken]:
        """Get a refresh token by its value."""
        stmt = select(RefreshToken).where(
            RefreshToken.token == token,
            RefreshToken.revoked == False,
        )
        return (await session.execute(stmt)).scalar_one_or_none()

async def revoke_refresh_token(
        token: str, 
        session: AsyncSession
    ) -> bool:
        """Mark a refresh token as revoked."""
        tok = await get_refresh_token(token, session)
        if not tok:
            return False
        tok.revoked = True
        await session.commit()
        return True

# ──────────────────────────  Reset-token helpers  ───────────────────────────

async def is_token_used(
        jti: str, 
        session: AsyncSession
    ) -> bool:
        stmt = select(UsedPWResetToken).where(UsedPWResetToken.jti == jti)
        return (await session.execute(stmt)).scalar_one_or_none() is not None

async def store_used_jti(
        jti: str, 
        expires_at: datetime, 
        session: AsyncSession,
    ):
        token = UsedPWResetToken(jti=jti, expires_at=expires_at)
        session.add(token)
        await session.commit()
