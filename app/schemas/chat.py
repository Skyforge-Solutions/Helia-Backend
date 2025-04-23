from pydantic import BaseModel
from typing import Optional

class ChatRequest(BaseModel):
    chat_id: str
    model_id: str
    message: str
    image_url: Optional[str] = None

class ChatMessageResponse(BaseModel):
    id: str
    chat_id: str
    role: str  # "user" or "assistant"
    content: str
    image_url: Optional[str] = None
    timestamp: str

    class Config:
        from_attributes = True