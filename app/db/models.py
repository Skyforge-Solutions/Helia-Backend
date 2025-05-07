# app/db/models.py
from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    ForeignKey,
    JSON,
    Boolean,
    UniqueConstraint,
    Index,
    Integer,
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

Base = declarative_base() 


class User(Base):
    __tablename__ = "users"

    id               = Column(String, primary_key=True, index=True)
    email            = Column(String, unique=True, index=True, nullable=False)
    password         = Column(String, nullable=False)
    name             = Column(String, nullable=True)
    age              = Column(String, nullable=True)
    occupation       = Column(String, nullable=True)
    tone_preference  = Column(String, nullable=True)
    tech_familiarity = Column(String, nullable=True)
    parent_type      = Column(String, nullable=True)
    time_with_kids   = Column(String, nullable=True)
    children         = Column(JSON, nullable=True)
    is_active        = Column(Boolean, default=False)
    is_verified      = Column(Boolean, default=False)
    credits_remaining = Column(Integer, nullable=False, default=100)
    dodo_customer_id = Column(String, nullable=True, index=True)

    sessions = relationship(
        "ChatSession",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    
    refresh_tokens = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    
    credit_purchases = relationship(
        "CreditPurchase",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    
    __table_args__=(
        Index("idx_users_email_verified", "email", "is_verified"),
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

    __table_args__ = (
        Index(
            "idx_chat_sessions_by_user_updated",
            "user_id",
            "updated_at",
            postgresql_ops={"updated_at": "DESC"}
        ),
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id        = Column(String, primary_key=True, index=True)
    chat_id   = Column(String, ForeignKey("chat_sessions.id"), nullable=False, index=True)
    role      = Column(String, nullable=False)
    content   = Column(Text, nullable=False)
    image_url = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("ChatSession", back_populates="messages")

    __table_args__ = (
        Index(
            "idx_chat_messages_by_chat_time",
            "chat_id",
            "timestamp"
        ),
    )


class EmailChangeRequest(Base):
    __tablename__ = "email_change_requests"
    __table_args__ = (
        UniqueConstraint("new_email"),
        Index(
            "idx_email_change_user_expires",
            "user_id", "verified", "expires_at",
            postgresql_ops={"expires_at": "DESC"}
        ),
    )
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    new_email = Column(String, unique=True, nullable=False)
    otp_hash = Column(String, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    verified = Column(Boolean, default=False)
    user = relationship("User")


class UsedPWResetToken(Base):
    __tablename__ = "used_pw_reset_tokens"
    jti = Column(String, primary_key=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String, nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Boolean, default=False)
    issued_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="refresh_tokens")

    __table_args__ = (
        Index(
            "idx_valid_refresh_tokens",
            "user_id",
            "expires_at",
            postgresql_where=(revoked == False),
        ),
    )

class EmailVerificationRequest(Base):
    __tablename__ = "email_verification_requests"
    __table_args__ = (
        Index(
            "idx_email_verification_user_expires",
            "user_id", "verified", "expires_at",
            postgresql_ops={"expires_at": "DESC"}
        ),
    )
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    email = Column(String, nullable=False)
    otp_hash = Column(String, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    verified = Column(Boolean, default=False)
    
    user = relationship("User")

class CreditPurchase(Base):
    __tablename__ = "credit_purchases"
    
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    credits = Column(Integer, nullable=False)
    amount_cents = Column(Integer, nullable=False)
    currency = Column(String, nullable=False)
    payment_id = Column(String, nullable=False, unique=True)
    status = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    product_id = Column(Text, nullable=False)
    
    user = relationship("User", back_populates="credit_purchases")
    
    __table_args__ = (
        Index("idx_credit_purchases_user", "user_id"),
    )
