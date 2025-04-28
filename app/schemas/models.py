# app/schemas/models.py
from pydantic import BaseModel, EmailStr
from typing import List, Optional, Literal
from datetime import datetime

from pydantic import BaseModel, EmailStr, constr

class PasswordUpdate(BaseModel):
    current_password: constr(min_length=6)
    new_password: constr(min_length=6)

class EmailChangeRequestIn(BaseModel):
    new_email: EmailStr
    current_password: constr(min_length=6)

class EmailChangeVerifyIn(BaseModel):
    otp: constr(min_length=4, max_length=8)

class PWResetRequestIn(BaseModel):
    email: EmailStr

class PWResetVerifyIn(BaseModel):
    token: str
    new_password: constr(min_length=6)

class TokenRefreshRequest(BaseModel):
    refresh_token: str

class EmailVerificationVerifyIn(BaseModel):
    email: EmailStr
    otp: constr(min_length=4, max_length=8)

class ChildInfo(BaseModel):
    name: str
    age: int
    gender: str
    description: Optional[str] = None

class UserBase(BaseModel):
    email: EmailStr

class UserCreate(UserBase):
    password: str
    name: Optional[str] = None
    age: Optional[str] = None
    occupation: Optional[str] = None
    tone_preference: Optional[str] = None
    tech_familiarity: Optional[str] = None
    parent_type: Optional[str] = None
    time_with_kids: Optional[str] = None
    children: Optional[List[ChildInfo]] = None

class UserLogin(UserBase):
    password: str

class UserSchema(UserBase):
    id: str
    name: Optional[str] = None
    age: Optional[str] = None
    occupation: Optional[str] = None
    tone_preference: Optional[str] = None
    tech_familiarity: Optional[str] = None
    parent_type: Optional[str] = None
    time_with_kids: Optional[str] = None
    children: Optional[List[ChildInfo]] = None
    is_active: bool = True
    is_verified: bool = False

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_name: str

    class Config: 
        from_attributes = True

class TokenData(BaseModel):
    email: Optional[str] = None
    user_id: Optional[str] = None

class ChatSessionSchema(BaseModel):
    id: str
    user_id: str
    name: str
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True

class ChatMessageSchema(BaseModel):
    id: str
    chat_id: str
    role: Literal["user","assistant"]
    content: str
    image_url: Optional[str]
    timestamp: datetime

    class Config:
        from_attributes = True