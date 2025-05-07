"""
Payment-related Pydantic schemas for request and response validation.
"""
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class CreditPlan(BaseModel):
    """Schema for credit plans/bundles offered to users."""
    id: str = Field(..., description="Unique identifier for the credit plan in Dodo Payments")
    name: str = Field(..., description="Display name of the credit plan")
    price: int = Field(..., gt=0, description="Price in smallest currency unit (cents/paise)")
    credits: int = Field(..., gt=0, description="Number of credits provided with this plan")
    description: Optional[str] = Field(None, description="Detailed description of the credit plan")

class CreateCheckoutRequest(BaseModel):
    """Request schema for creating a checkout session."""
    product_id: str = Field(..., description="ID of the credit plan product to purchase")

class CheckoutResponse(BaseModel):
    """Response schema for checkout creation."""
    payment_link: str = Field(..., description="URL to the payment checkout page")
    payment_id: str = Field(..., description="Unique identifier for the payment in Dodo Payments")

class WebhookPayload(BaseModel):
    """Basic schema for Dodo webhook payload validation."""
    type: str = Field(..., description="Type of webhook event (e.g., payment.succeeded)")
    data: dict = Field(..., description="Event data containing payment details")

class CreditPurchaseResponse(BaseModel):
    """Schema for credit purchase details."""
    id: str = Field(..., description="Unique identifier for the purchase")
    user_id: str = Field(..., description="ID of the user who made the purchase")
    credits: int = Field(..., gt=0, description="Number of credits purchased")
    amount_cents: int = Field(..., gt=0, description="Amount paid in smallest currency unit")
    currency: str = Field(..., min_length=3, max_length=3, description="Currency code (e.g., USD, INR)")
    status: str = Field(..., description="Payment status (pending, succeeded, failed, expired)")
    created_at: datetime = Field(..., description="When the purchase was created")
    
    class Config:
        from_attributes = True 