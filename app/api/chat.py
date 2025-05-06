import asyncio
from uuid import uuid4
from typing import List, Optional

from fastapi import (
    APIRouter, 
    Depends, 
    HTTPException,
    UploadFile, 
    File, 
    Form
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
    session = await get_chat_session(chat_id,db)
    if session and session.user_id != current_user.id:
        raise HTTPException(403, "Not authorized to access this chat")

    # 2) Ensure chat session exists ----------------------------------------------
    await get_or_create_session(current_user.id, chat_id,db)

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
    print(f"User profile: {user_profile}")

    # Update memory management
    from app.chains.base import touch_memory , manage_memory_size
    touch_memory(chat_id)
    manage_memory_size()

    chain  = await get_chat_chain(chat_id, model_id, user_profile,db)
    memory = chat_memory_store.get(chat_id)
    if memory:
        print(f'memory for chat {chat_id} found, messages: {len(memory.chat_memory.messages)}')
    else:
        print(f'memory for chat {chat_id} not found, creating new one')

    # 6) SSE streaming back to client --------------------------------------------
    async def event_stream():
        collected: list[str] = []
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
                yield "event: end\ndata: END\n\n"
            else:
                # For other BadRequestErrors, re-raise the exception
                raise e

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
    return await list_sessions(current_user.id,db)

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
    if not await get_chat_session_owned(chat_id, current_user.id, db):
        raise HTTPException(404, "Chat session not found")
    return await update_session_name(chat_id, name, db)

@router.delete("/sessions/{chat_id}", response_model=dict)
async def delete_session(
    chat_id: str, 
    current_user: UserSchema = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    ):
    # Check ownership
    if not await get_chat_session_owned(chat_id, current_user.id, db):
        raise HTTPException(404, "Chat session not found")
    await delete_chat_session(chat_id, db)
    return {"status": "success", "message": "Chat session deleted"}

@router.get("/sessions/{chat_id}", response_model=ChatSessionSchema)
async def get_session(
    chat_id: str, 
    current_user: UserSchema = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session_obj = await get_chat_session_owned(chat_id, current_user.id, db)
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
    session_obj = await get_chat_session_owned(chat_id, current_user.id, db)
    if not session_obj:
        raise HTTPException(404, "Chat session not found")
    return await get_messages(chat_id, db)

@router.put("/users/me", response_model=UserSchema)
async def update_my_profile(
    profile_data: UserProfileUpdate, 
    current_user: UserSchema = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Update the current user's profile
    profile_dict = profile_data.model_dump(exclude_unset=True)
    return await update_user_profile(current_user.id, profile_dict, db)

@router.get("/users/me", response_model=UserSchema)
async def get_my_profile(current_user: UserSchema = Depends(get_current_user)):
    return current_user