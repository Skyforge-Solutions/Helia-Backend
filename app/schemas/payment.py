"""
Payment-related Pydantic schemas for request and response validation.
"""
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class CreditPlan(BaseModel):
    """Schema for credit plans/bundles offered to users"""
    id: str
    name: str
    price: int  # Price in smallest currency unit (cents)
    credits: int
    description: Optional[str] = None

class CreateCheckoutRequest(BaseModel):
    """Request schema for creating a checkout session"""
    product_id: str

class CheckoutResponse(BaseModel):
    """Response schema for checkout creation"""
    payment_link: str
    payment_id: str

class WebhookPayload(BaseModel):
    """Basic schema for Dodo webhook payload validation"""
    type: str
    data: dict

class CreditPurchaseResponse(BaseModel):
    """Schema for credit purchase details"""
    id: str
    user_id: str
    credits: int
    amount_cents: int
    currency: str
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True 