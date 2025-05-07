"""
Billing API endpoints for managing credit purchases and user billing.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
from uuid import uuid4
import logging

from dodopayments import NotFoundError
from app.services.dodo_client import client, is_client_configured
from app.utils.auth import get_current_user
from app.db.session import get_db
from app.schemas.models import UserSchema
from app.schemas.payment import (
    CreditPlan, 
    CreateCheckoutRequest, 
    CheckoutResponse, 
    CreditPurchaseResponse
)
from app.db.models import CreditPurchase

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter()

# Credit plans configuration
# These should match the products created in your Dodo Payments dashboard
CREDIT_PLANS = [
    CreditPlan(
        id="pdt_RGfyUv4Fg7BRfqWsIpPjN",  # Replace with your actual product ID from Dodo
        name="100 Credits",
        price=500,  # Price in cents/paise
        credits=100,
        description="Basic package with 100 credits for chat interactions",
    ),
    CreditPlan(
        id="pdt_n5TReSvCC0x4GWsglIO6l",  # Replace with your actual product ID from Dodo
        name="500 Credits",
        price=1000,  # Price in cents/paise
        credits=500,
        description="Premium package with 500 credits for chat interactions",
    ),
]

# Product ID to credits mapping
PRODUCT_CREDIT_MAP = {plan.id: plan.credits for plan in CREDIT_PLANS}

@router.get("/plans", response_model=List[CreditPlan], tags=["billing"])
async def get_plans():
    """
    Returns available credit plans that users can purchase.
    """
    return CREDIT_PLANS

@router.get("/credits", tags=["billing"])
async def get_credits(current_user: UserSchema = Depends(get_current_user)):
    """
    Returns the current user's credit balance.
    """
    return {"credits_remaining": current_user.credits_remaining}

def get_or_create_dodo_customer(user):
    """
    Helper function to get or create a Dodo customer.
    Uses the correct retrieve() method and handles NotFoundError.
    """
    try:
        return client.customers.retrieve(customer_id=user.id)
    except NotFoundError:
        # Customer doesn't exist, create one
        logger.info(f"Creating new Dodo customer for user: {user.id}")
        return client.customers.create(
            body={
                "customer_id": user.id,
                "email": user.email,
                "name": user.name or "HeliaChat User"
            }
        )

@router.post("/create-checkout", response_model=CheckoutResponse, status_code=status.HTTP_201_CREATED, tags=["billing"])
async def create_checkout(
    request: CreateCheckoutRequest,
    current_user: UserSchema = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Creates a payment checkout session with Dodo Payments and returns a payment link.
    """
    # Verify Dodo client is configured
    if not is_client_configured():
        logger.error("Dodo Payments API is not properly configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment service is currently unavailable"
        )
    
    # Validate product ID
    if request.product_id not in PRODUCT_CREDIT_MAP:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid product ID"
        )
    
    credits = PRODUCT_CREDIT_MAP[request.product_id]
    
    try:
        # First, ensure customer exists in Dodo's system
        dodo_customer = get_or_create_dodo_customer(current_user)
        
        # Create payment with Dodo
        payment_result = client.payments.create(
            billing={
                "city": "Default City",
                "country": "IN",  # ISO country code
                "state": "Default State",
                "street": "123 Default Street",
                "zipcode": "560001",  # Already a string, keeping it consistent
            },
            product_cart=[{"product_id": request.product_id, "quantity": 1}],
            customer={"customer_id": current_user.id},
            metadata={"user_id": str(current_user.id), "credits": str(credits)},
            payment_link=True,
            return_url="https://heliachat.com/checkout-success"  # Customize your return URL
        )
        
        # Create pending purchase record in database
        purchase = CreditPurchase(
            id=str(uuid4()),
            user_id=current_user.id,
            credits=credits,
            amount_cents=payment_result.total_amount,
            currency=payment_result.currency,
            payment_id=payment_result.payment_id,
            status="pending",
            product_id=request.product_id
        )
        
        db.add(purchase)
        await db.commit()
        
        logger.info(f"Created checkout for user {current_user.id}, payment ID: {payment_result.payment_id}")
        
        return {
            "payment_link": payment_result.payment_link,
            "payment_id": payment_result.payment_id
        }
        
    except Exception as e:
        logger.error(f"Error creating checkout: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create payment checkout"
        )

@router.get("/purchases", response_model=List[CreditPurchaseResponse], tags=["billing"])
async def get_purchase_history(
    current_user: UserSchema = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns the user's credit purchase history.
    """
    stmt = select(CreditPurchase).where(
        CreditPurchase.user_id == current_user.id
    ).order_by(CreditPurchase.created_at.desc())
    
    result = await db.execute(stmt)
    purchases = result.scalars().all()
    
    return purchases
