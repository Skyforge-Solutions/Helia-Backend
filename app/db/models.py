# app/db/models.py
from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    ForeignKey,
    JSON,
    Boolean,
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id               = Column(String, primary_key=True, index=True)
    email            = Column(String, unique=True, index=True, nullable=False)
    password         = Column(String, nullable=False)
    name             = Column(String, nullable=True)  # Changed from not null to nullable
    age              = Column(String, nullable=True)
    occupation       = Column(String, nullable=True)
    tone_preference  = Column(String, nullable=True)
    tech_familiarity = Column(String, nullable=True)
    parent_type      = Column(String, nullable=True)
    time_with_kids   = Column(String, nullable=True)
    children         = Column(JSON, nullable=True)  # list of dicts
    is_active        = Column(Boolean, default=True)

    sessions = relationship(
        "ChatSession",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id         = Column(String, primary_key=True, index=True)
    user_id    = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    name       = Column(String, default="New Chat", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user     = relationship("User", back_populates="sessions")
    messages = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id        = Column(String, primary_key=True, index=True)
    chat_id   = Column(String, ForeignKey("chat_sessions.id"), nullable=False, index=True)
    role      = Column(String, nullable=False)  # "user" or "assistant"
    content   = Column(Text, nullable=False)
    image_url = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("ChatSession", back_populates="messages")