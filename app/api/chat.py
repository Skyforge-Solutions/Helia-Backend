import asyncio
from fastapi import (
    APIRouter, Depends, HTTPException,
     UploadFile, File, Form
)
from typing import List, Optional
from fastapi.responses import StreamingResponse
from typing import List, Optional
from uuid import uuid4

from app.schemas.chat import ChatRequest
from app.schemas.models import ChatSessionSchema, ChatMessageSchema, UserSchema
from app.db.crud import (
    get_or_create_session,
    list_sessions,
    add_message,
    get_messages,
    update_user_profile,
    update_session_name,
    delete_chat_session,
    get_chat_session
)
from app.chains.base import get_chat_chain, chat_memory_store
from app.utils.auth import get_current_user
from app.services.azure_blob import upload_image_and_get_url

router = APIRouter()

# ─── MAIN ENDPOINT ──────────────────────────────────────────────────────────────
@router.post("/chat/send", response_model=None)
async def send_chat(
    chat_id:  str = Form(...),
    model_id: str = Form(...),
    message:  str = Form(...),
    image: Optional[UploadFile] = File(None),
    current_user: UserSchema = Depends(get_current_user),
):
    """
    • Accepts multipart/form-data so a file can be sent along with the text fields.
    • If an image is provided, it is validated & uploaded to Azure Blob Storage
      and the resulting public URL is stored in `chat_messages.image_url`.
    """

    # 1) Ownership / authorisation ------------------------------------------------
    session = await get_chat_session(chat_id)
    if session and session.user_id != current_user.id:
        raise HTTPException(403, "Not authorized to access this chat")

    # 2) Ensure chat session exists ----------------------------------------------
    await get_or_create_session(current_user.id, chat_id)

    # 3) Handle optional image upload --------------------------------------------
    image_url: Optional[str] = None
    if image:
        try:
            file_bytes = await image.read()
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
    await add_message(chat_id, "user", message, image_url)

    # 5) Build personalised chain -------------------------------------------------
    user_profile = {k: v for k, v in current_user.__dict__.items()
                    if not k.startswith("_")}

    chain  = await get_chat_chain(chat_id, model_id, user_profile)
    memory = chat_memory_store.get(chat_id)

    # 6) SSE streaming back to client --------------------------------------------
    async def event_stream():
        collected: list[str] = []
        history = memory.chat_memory.messages if memory else []

        async for chunk in chain.astream(
            {"input": message, "history": history},
            config={"configurable": {"memory": memory}},
        ):
            token = chunk.content
            collected.append(token)
            yield f"data: {token}\n\n"
            await asyncio.sleep(0)            # flush

        full = "".join(collected)
        await add_message(chat_id, "assistant", full)
        yield "event: end\ndata: END\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/sessions", response_model=List[ChatSessionSchema])
async def get_sessions(current_user: UserSchema = Depends(get_current_user)):
    return await list_sessions(current_user.id)

@router.post("/sessions", response_model=ChatSessionSchema,status_code=201)
async def create_session(name: Optional[str] = "New Chat", current_user: UserSchema = Depends(get_current_user)):
    session = await get_or_create_session(current_user.id, chat_id=str(uuid4()), name=name)
    return session

@router.put("/sessions/{chat_id}", response_model=ChatSessionSchema)
async def rename_session(chat_id: str, name: str, current_user: UserSchema = Depends(get_current_user)):
    # Check ownership
    session = await get_chat_session(chat_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    session = await update_session_name(chat_id, name)
    return session  

@router.delete("/sessions/{chat_id}", response_model=dict)
async def delete_session(chat_id: str, current_user: UserSchema = Depends(get_current_user)):
    # Check ownership
    session = await get_chat_session(chat_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    success = await delete_chat_session(chat_id)
    return {"status": "success", "message": "Chat session deleted"}

@router.get("/sessions/{chat_id}", response_model=ChatSessionSchema)
async def get_session(chat_id: str, current_user: UserSchema = Depends(get_current_user)):
    session = await get_chat_session(chat_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return session

@router.get("/history/{chat_id}", response_model=List[ChatMessageSchema])
async def get_history(chat_id: str, current_user: UserSchema = Depends(get_current_user)):
    # Check ownership
    session = await get_chat_session(chat_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    msgs = await get_messages(chat_id)
    return msgs

@router.put("/users/me", response_model=UserSchema)
async def update_my_profile(profile_data: dict, current_user: UserSchema = Depends(get_current_user)):
    # Update the current user's profile
    user = await update_user_profile(current_user.id, profile_data)
    return user

@router.get("/users/me", response_model=UserSchema)
async def get_my_profile(current_user: UserSchema = Depends(get_current_user)):
    return current_user