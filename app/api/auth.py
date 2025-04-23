from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta

from app.schemas.models import UserCreate, UserSchema, Token
from app.db.crud import create_user, authenticate_user, get_user_by_email
from app.utils.auth import create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES, get_current_user
from app.db.session import get_db, AsyncSession

router = APIRouter()

@router.post("/register", response_model=UserSchema)
async def register_user(user: UserCreate, db: AsyncSession = Depends(get_db)):
    # Check if email already exists
    db_user = await get_user_by_email(user.email, session=db)
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create new user (password will be hashed in the crud function)
    user_data = user.model_dump()  # Using model_dump() instead of dict() for Pydantic v2
    password = user_data.pop("password")
    created_user = await create_user(email=user.email, password=password, profile=user_data)
    
    return created_user

@router.post("/token", response_model=Token)
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
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserSchema)
async def read_users_me(current_user: UserSchema = Depends(get_current_user)):
    return current_user