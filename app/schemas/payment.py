"""
Payment-related Pydantic schemas for request and response validation.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
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

class BillingAddress(BaseModel):
    """Schema for billing address information."""
    city: str = Field(..., description="City name")
    country: str = Field(..., description="Country code (ISO alpha-2)")
    state: str = Field(..., description="State or province")
    street: str = Field(..., description="Street address")
    zipcode: str = Field(..., description="Postal or ZIP code")

class CustomerDetails(BaseModel):
    """Schema for customer details."""
    customer_id: str = Field(..., description="Unique identifier for the customer")
    email: str = Field(..., description="Email address of the customer")
    name: str = Field(..., description="Name of the customer")

class RefundInfo(BaseModel):
    """Schema for refund information."""
    refund_id: str = Field(..., description="Unique identifier for the refund")
    amount: int = Field(..., description="Refunded amount")
    currency: str = Field(..., description="Currency code (ISO)")
    status: str = Field(..., description="Status of the refund")
    created_at: datetime = Field(..., description="When the refund was created")
    payment_id: str = Field(..., description="ID of the payment that was refunded")
    business_id: str = Field(..., description="ID of the business")
    reason: Optional[str] = Field(None, description="Reason for refund")

class PaymentDetailResponse(BaseModel):
    """Schema for payment details response."""
    payment_id: str = Field(..., description="Unique identifier for the payment")
    business_id: str = Field(..., description="ID of the business")
    total_amount: int = Field(..., description="Total amount in smallest currency unit")
    currency: str = Field(..., description="Currency code (ISO)")
    status: str = Field(..., description="Payment status")
    created_at: datetime = Field(..., description="When the payment was created")
    updated_at: Optional[datetime] = Field(None, description="When the payment was last updated")
    customer: CustomerDetails = Field(..., description="Customer information")
    billing: BillingAddress = Field(..., description="Billing address information")
    payment_method: Optional[str] = Field(None, description="Payment method used")
    payment_method_type: Optional[str] = Field(None, description="Specific type of payment method")
    refunds: List[RefundInfo] = Field(default_factory=list, description="List of refunds")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    settlement_amount: int = Field(..., description="Settlement amount")
    settlement_currency: str = Field(..., description="Settlement currency code")
    tax: Optional[int] = Field(None, description="Tax amount in smallest currency unit")

class InvoiceResponse(BaseModel):
    """Schema for invoice response."""
    invoice_url: str = Field(..., description="URL to download the invoice PDF") 