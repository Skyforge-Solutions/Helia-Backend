import asyncio
from uuid import uuid4
from typing import List, Optional
import logging

from fastapi import (
    APIRouter, 
    Depends, 
    HTTPException,
    UploadFile, 
    File, 
    Form,
    status
)

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import StreamingResponse

from app.db.session import get_db
from app.utils.auth import get_current_user
from app.services.azure_blob import upload_image_and_get_url
from app.schemas.models import ChatSessionSchema, ChatMessageSchema, UserSchema,UserProfileUpdate
from app.chains.base import get_chat_chain, chat_memory_store
from app.db.crud import (
    get_or_create_session,
    list_sessions,
    add_message,
    get_messages,
    update_user_profile,
    update_session_name,
    delete_chat_session,
    get_chat_session,
    get_chat_session_owned,
)

from openai import BadRequestError
from app.utils.content_filter import get_content_filter_response 

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter()

# ─── MAIN ENDPOINT ──────────────────────────────────────────────────────────────
@router.post("/chat/send", response_model=None)
async def send_chat(
    chat_id:  str = Form(...),
    model_id: str = Form(...),
    message:  str = Form(...),
    image: Optional[UploadFile] = File(None),
    current_user: UserSchema = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):

    # 1) ownership check + lazy creation ------------------------------------------------
    session = await get_chat_session(chat_id, session=db)
    if session and session.user_id != current_user.id:
        raise HTTPException(403, "Not authorized to access this chat")

    # 1.5) Credit check - NEW CODE ------------------------------------------------
    if current_user.credits_remaining <= 0:
        logger.info(f"User {current_user.id} attempted to chat with no credits")
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="You have run out of credits. Please purchase more to continue chatting."
        )

    # 2) Ensure chat session exists ----------------------------------------------
    await get_or_create_session(current_user.id, chat_id, session=db)

    # 3) Handle optional image upload --------------------------------------------
    image_url: Optional[str] = None
    if image:
        file_bytes = await image.read()
        try:
            image_url = await upload_image_and_get_url(
                file_bytes,
                mime_type     = image.content_type,
                user_id       = current_user.id,
                original_name = image.filename,
            )
        except ValueError as ve:
            raise HTTPException(400, str(ve))
        except Exception as e:
            raise HTTPException(500, "Image upload failed") from e

    # 4) Persist the *user* message (text + optional url) -------------------------
    await add_message(
        chat_id=chat_id,
        role="user",
        content=message,
        session=db,
        image_url=image_url,
    )

    # 5) Build personalised chain -------------------------------------------------
    user_profile = {
        "name": current_user.name,
        "age": current_user.age,
        "occupation": current_user.occupation,
        "tone_preference": current_user.tone_preference,
        "tech_familiarity": current_user.tech_familiarity,
        "parent_type": current_user.parent_type,
        "time_with_kids": current_user.time_with_kids,
        "children": current_user.children,
}
    logger.debug(f"User profile for chat {chat_id}: {user_profile}")

    # Update memory management
    from app.chains.base import touch_memory , manage_memory_size
    touch_memory(chat_id)
    manage_memory_size()

    chain  = await get_chat_chain(chat_id, model_id, user_profile, session=db)
    memory = chat_memory_store.get(chat_id)
    if memory:
        logger.debug(f'Memory for chat {chat_id} found, messages: {len(memory.chat_memory.messages)}')
    else:
        logger.debug(f'Memory for chat {chat_id} not found, creating new one')

    # 6) SSE streaming back to client --------------------------------------------
    async def event_stream():
        collected: list[str] = []
        success = False  # Track if we successfully generated a response
        history = memory.chat_memory.messages if memory else []

        try:
            async for chunk in chain.astream(
                {"input": message, "history": history},
                config={"configurable": {"memory": memory}},
            ):
                token = chunk.content
                collected.append(token)
                # split into lines to preserve markdown
                for line in token.splitlines():
                    yield f"data: {line}\n"
                yield "data: \n"
                await asyncio.sleep(0)

            full = "".join(collected)
            await add_message(
                chat_id=chat_id,
                role="assistant",
                content=full,
                session=db
            )
            
            # Mark as success since we reached this point
            success = True
            
            # Deduct credit for successful response
            current_user.credits_remaining -= 1
            # Update user in database to ensure credits change is persisted
            await update_user_profile(
                current_user.id, 
                {"credits_remaining": current_user.credits_remaining}, 
                session=db
            )
            logger.info(f"Deducted 1 credit from user {current_user.id}, remaining: {current_user.credits_remaining}")
            
            yield "event: end\ndata: END\n\n"
        except BadRequestError as e:
            if e.code == "content_filter":
                # Use the utility function to get a dynamic, model-specific response
                response = get_content_filter_response(e, model_id)
                # Stream the response in SSE format
                for line in response.splitlines():
                    yield f"data: {line}\n"
                yield "data: \n"
                # Persist the response to the database
                await add_message(
                    chat_id=chat_id,
                    role="assistant",
                    content=response,
                    session=db
                )
                
                # Mark as success since we did provide a response
                success = True
                
                # Deduct credit for content filter response
                current_user.credits_remaining -= 1
                # Update user in database to ensure credits change is persisted
                await update_user_profile(
                    current_user.id, 
                    {"credits_remaining": current_user.credits_remaining}, 
                    session=db
                )
                logger.info(f"Deducted 1 credit from user {current_user.id}, remaining: {current_user.credits_remaining}")
                
                yield "event: end\ndata: END\n\n"
            else:
                # For other BadRequestErrors, re-raise the exception
                raise e
        except Exception as e:
            # If we get any other exception, log it but don't deduct credits
            logger.error(f"Error in chat stream for user {current_user.id}, chat {chat_id}: {str(e)}")
            # We don't deduct credits for errors
            if not success:
                yield f"data: An error occurred: {str(e)}\n"
                yield "event: error\ndata: ERROR\n\n"
            raise

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
        },
    )






@router.get("/sessions", response_model=List[ChatSessionSchema])
async def get_sessions(
    current_user: UserSchema = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await list_sessions(current_user.id, session=db)

@router.post("/sessions", response_model=ChatSessionSchema,status_code=201)
async def create_session(
    name: Optional[str] = "New Chat", 
    current_user: UserSchema = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await get_or_create_session(
        current_user.id, 
        chat_id=str(uuid4()), 
        session=db,
        name=name,
    )
    return session

@router.put("/sessions/{chat_id}", response_model=ChatSessionSchema)
async def rename_session(
    chat_id: str, 
    name: str, 
    current_user: UserSchema = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Check ownership
    if not await get_chat_session_owned(chat_id, current_user.id, session=db):
        raise HTTPException(404, "Chat session not found")
    return await update_session_name(chat_id, name, session=db)

@router.delete("/sessions/{chat_id}", response_model=dict)
async def delete_session(
    chat_id: str, 
    current_user: UserSchema = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    ):
    # Check ownership
    if not await get_chat_session_owned(chat_id, current_user.id, session=db):
        raise HTTPException(404, "Chat session not found")
    await delete_chat_session(chat_id, session=db)
    return {"status": "success", "message": "Chat session deleted"}

@router.get("/sessions/{chat_id}", response_model=ChatSessionSchema)
async def get_session(
    chat_id: str, 
    current_user: UserSchema = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session_obj = await get_chat_session_owned(chat_id, current_user.id, session=db)
    if not session_obj:
        raise HTTPException(404, "Chat session not found")
    return session_obj

@router.get("/history/{chat_id}", response_model=List[ChatMessageSchema])
async def get_history(
    chat_id: str, 
    current_user: UserSchema = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Check ownership
    session_obj = await get_chat_session_owned(chat_id, current_user.id, session=db)
    if not session_obj:
        raise HTTPException(404, "Chat session not found")
    return await get_messages(chat_id, session=db)

@router.put("/users/me", response_model=UserSchema)
async def update_my_profile(
    profile_data: UserProfileUpdate, 
    current_user: UserSchema = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Update the current user's profile
    profile_dict = profile_data.model_dump(exclude_unset=True)
    return await update_user_profile(current_user.id, profile_dict, session=db)

@router.get("/users/me", response_model=UserSchema)
async def get_my_profile(current_user: UserSchema = Depends(get_current_user)):
    return current_user