# app/schemas/models.py
from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional, Literal
from datetime import datetime

# ----- AUTH: PASSWORD RELATED SCHEMAS -----

class PasswordUpdate(BaseModel):
    """Schema for updating user password."""
    current_password: str = Field(..., min_length=6, description="Current password for verification")
    new_password: str = Field(..., min_length=6, description="New password to set")

class PWResetRequestIn(BaseModel):
    """Schema for requesting a password reset."""
    email: EmailStr = Field(..., description="Email address for the account")

class PWResetVerifyIn(BaseModel):
    """Schema for verifying a password reset token and setting a new password."""
    token: str = Field(..., description="Password reset token received by email")
    new_password: str = Field(..., min_length=6, description="New password to set")

# ----- AUTH: EMAIL RELATED SCHEMAS -----

class EmailVerificationVerifyIn(BaseModel):
    """Schema for verifying a user's email with OTP."""
    email: EmailStr = Field(..., description="Email address to verify")
    otp: str = Field(..., min_length=4, max_length=8, description="One-time password received via email")

class EmailChangeRequestIn(BaseModel):
    """Schema for requesting an email change."""
    new_email: EmailStr = Field(..., description="New email address to change to")
    current_password: str = Field(..., min_length=6, description="Current password for verification")

class EmailChangeVerifyIn(BaseModel):
    """Schema for verifying an email change with OTP."""
    otp: str = Field(..., min_length=4, max_length=8, description="One-time password received via email")

# ----- AUTH: TOKEN RELATED SCHEMAS -----

class TokenRefreshRequest(BaseModel):
    """Schema for refreshing an access token using a refresh token."""
    refresh_token: str = Field(..., description="Valid refresh token")

class Token(BaseModel):
    """Base token response schema."""
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field("bearer", description="Token type")

class AuthResponse(BaseModel):
    """Response schema for successful authentication."""
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field("bearer", description="Token type")
    user_name: str = Field(..., description="User's display name")

    class Config: 
        from_attributes = True

class TokenData(BaseModel):
    """Internal schema for JWT token payload."""
    email: Optional[str] = Field(None, description="User's email")
    user_id: Optional[str] = Field(None, description="User's ID")

# ----- USER RELATED SCHEMAS -----

class ChildInfo(BaseModel):
    """Schema for child information in user profile."""
    name: str = Field(..., description="Child's name")
    age: int = Field(..., ge=0, lt=18, description="Child's age in years")
    gender: str = Field(..., description="Child's gender")
    description: Optional[str] = Field(None, description="Additional information about the child")

class UserBase(BaseModel):
    """Base schema for user with only email."""
    email: EmailStr = Field(..., description="User's email address")

class UserCreate(UserBase):
    """Schema for creating a new user."""
    password: str = Field(..., min_length=6, description="User's password")
    name: Optional[str] = Field(None, description="User's full name")
    age: Optional[str] = Field(None, description="User's age group")
    occupation: Optional[str] = Field(None, description="User's occupation")
    tone_preference: Optional[str] = Field(None, description="Preferred conversation tone")
    tech_familiarity: Optional[str] = Field(None, description="Level of technology familiarity")
    parent_type: Optional[str] = Field(None, description="Type of parent")
    time_with_kids: Optional[str] = Field(None, description="Time spent with children")
    children: Optional[List[ChildInfo]] = Field(None, description="Information about children")

class UserLogin(UserBase):
    """Schema for user login."""
    password: str = Field(..., min_length=6, description="User's password")

class UserSchema(UserBase):
    """Schema for user data returned from database."""
    id: str = Field(..., description="User's unique identifier")
    password: str = Field(..., description="User's hashed password (used internally)", exclude=True)
    name: Optional[str] = Field(None, description="User's full name")
    age: Optional[str] = Field(None, description="User's age group")
    occupation: Optional[str] = Field(None, description="User's occupation")
    tone_preference: Optional[str] = Field(None, description="Preferred conversation tone")
    tech_familiarity: Optional[str] = Field(None, description="Level of technology familiarity")
    parent_type: Optional[str] = Field(None, description="Type of parent")
    time_with_kids: Optional[str] = Field(None, description="Time spent with children")
    children: Optional[List[ChildInfo]] = Field(None, description="Information about children")
    is_active: bool = Field(True, description="Whether the user account is active")
    is_verified: bool = Field(False, description="Whether the user's email has been verified")
    credits_remaining: int = Field(100, description="Number of credits available for the user")

    class Config:
        from_attributes = True

class UserProfileUpdate(BaseModel):
    """Schema for updating user profile fields."""
    name: Optional[str] = Field(None, description="User's full name")
    age: Optional[str] = Field(None, description="User's age group")
    occupation: Optional[str] = Field(None, description="User's occupation")
    tone_preference: Optional[str] = Field(None, description="Preferred conversation tone")
    tech_familiarity: Optional[str] = Field(None, description="Level of technology familiarity")
    parent_type: Optional[str] = Field(None, description="Type of parent")
    time_with_kids: Optional[str] = Field(None, description="Time spent with children")
    children: Optional[List[ChildInfo]] = Field(None, description="Information about children")

# ----- CHAT RELATED SCHEMAS -----

class ChatSessionSchema(BaseModel):
    """Schema for chat session information."""
    id: str = Field(..., description="Chat session unique identifier")
    user_id: str = Field(..., description="User ID who owns the chat session")
    name: str = Field(..., description="Chat session name or title")
    created_at: datetime = Field(..., description="When the chat session was created")
    updated_at: Optional[datetime] = Field(None, description="When the chat session was last updated")

    class Config:
        from_attributes = True

class ChatMessageSchema(BaseModel):
    """Schema for chat message information."""
    id: str = Field(..., description="Message unique identifier")
    chat_id: str = Field(..., description="Chat session this message belongs to")
    role: Literal["user", "assistant"] = Field(..., description="Message author role")
    content: str = Field(..., description="Message content")
    image_url: Optional[str] = Field(None, description="URL to attached image if any")
    timestamp: datetime = Field(..., description="When the message was created")

    class Config:
        from_attributes = True