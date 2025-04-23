from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from typing import List, Optional
from uuid import uuid4

from app.schemas.chat import ChatRequest, ChatMessageResponse
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

router = APIRouter()

@router.post("/chat/send", response_model=None)
async def send_chat(req: ChatRequest, current_user: UserSchema = Depends(get_current_user)):
    # Ensure this chat belongs to the current user
    session = await get_chat_session(req.chat_id)
    if session and session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this chat")

    # Get or create session for this user
    await get_or_create_session(current_user.id, req.chat_id)

    # persist user message
    await add_message(req.chat_id, "user", req.message, req.image_url)

    # Get user profile for personalization
    user_profile = current_user.__dict__ if current_user else {}
    
    # Await the chain to get the runnable object
    chain = await get_chat_chain(
        chat_id=req.chat_id,
        model_id=req.model_id,
        user_profile=user_profile
    )
    
    # Get the memory for this chat
    memory = chat_memory_store.get(req.chat_id)

    # stream tokens
    async def event_stream():
        collected = []
        # Get messages from memory to provide as history
        history = memory.chat_memory.messages if memory else []
        
        # Pass both input AND history to the chain
        async for chunk in chain.astream(
            {"input": req.message, "history": history},
            config={"configurable": {"memory": memory}}
        ):
            token = chunk.content
            collected.append(token)
            yield f"data: {token}\n\n"
        # after streaming, persist assistant message
        full = "".join(collected)
        await add_message(req.chat_id, "assistant", full)
        yield "event: end\ndata: END\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@router.get("/sessions", response_model=List[ChatSessionSchema])
async def get_sessions(current_user: UserSchema = Depends(get_current_user)):
    return await list_sessions(current_user.id)

@router.post("/sessions", response_model=ChatSessionSchema)
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