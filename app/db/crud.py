from uuid import uuid4
from sqlalchemy.future import select
from sqlalchemy import func
from app.db.session import AsyncSessionLocal, AsyncSession
from app.db.models import User, ChatSession, ChatMessage
from app.utils.password import get_password_hash, verify_password

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
            return cs
        cs = ChatSession(id=chat_id, user_id=user_id, name=name)
        session.add(cs)
        await session.commit()
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
    return user