"""
Chat-related Pydantic schemas for request and response validation.
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class ChatSendForm(BaseModel):
    """
    Schema for the chat form data submitted via multipart/form-data.
    Note: image is handled as a multipart file upload outside this model.
    """
    chat_id: str = Field(..., description="ID of the chat session")
    model_id: str = Field(..., description="ID of the AI model to use")
    message: str = Field(..., min_length=1, description="User's message content")

# Note: This model is used internally or for JSON payloads as alternative to form
class ChatRequest(BaseModel):
    """
    Schema for chat requests submitted as JSON body instead of form data.
    Includes optional image_url for cases where the image is already uploaded.
    """
    chat_id: str = Field(..., description="ID of the chat session")
    model_id: str = Field(..., description="ID of the AI model to use") 
    message: str = Field(..., min_length=1, description="User's message content")
    image_url: Optional[str] = Field(None, description="URL to an already uploaded image")

# Note: This is for simple responses that don't need the full ChatMessageSchema
class ChatMessageResponse(BaseModel):
    """
    Simplified schema for chat message responses.
    Uses string timestamp format instead of datetime object.
    """
    id: str = Field(..., description="Message unique identifier")
    chat_id: str = Field(..., description="Chat session this message belongs to")
    role: str = Field(..., description="Message author role (user or assistant)")
    content: str = Field(..., description="Message content")
    image_url: Optional[str] = Field(None, description="URL to attached image if any")
    timestamp: str = Field(..., description="When the message was created (ISO format)")

    class Config:
        from_attributes = True