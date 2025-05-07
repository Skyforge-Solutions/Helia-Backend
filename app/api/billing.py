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
from app.db.models import CreditPurchase, User

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

async def get_or_create_dodo_customer(user_model: User, db: AsyncSession) -> tuple[any, bool]:
    """
    Helper function to get or create a Dodo customer.
    Returns the Dodo customer object and a boolean indicating if user_model.dodo_customer_id was newly set.
    """
    dodo_customer_id_was_updated = False
    try:
        if user_model.dodo_customer_id:
            logger.info(f"User {user_model.id} attempting to retrieve Dodo customer ID: {user_model.dodo_customer_id}")
            # Dodo SDK methods are synchronous, not async
            dodo_customer_obj = client.customers.retrieve(customer_id=user_model.dodo_customer_id)
            return dodo_customer_obj, dodo_customer_id_was_updated # False, as ID already existed

        # No Dodo customer ID stored, create a new one
        logger.info(f"No Dodo customer ID for user {user_model.id}. Creating new Dodo customer.")
        try:
            dodo_customer_obj = client.customers.create(
                email=user_model.email,
                name=user_model.name or "HeliaChat User"
            )
        except Exception as e_create: # Replace with specific ConflictError if available
            # This is a placeholder for Dodo's specific conflict error
            # e.g., if isinstance(e_create, dodopayments.ConflictError) or (isinstance(e_create, dodopayments.APIStatusError) and e_create.status_code == 409):
            if "conflict" in str(e_create).lower() or (hasattr(e_create, "status_code") and e_create.status_code == 409): # Heuristic
                logger.warning(f"Conflict during Dodo customer creation for user {user_model.id}. Attempting to retrieve.")
                # Attempt to retrieve, assuming another request created it.
                # This requires Dodo to return the customer_id or have it derivable,
                # or that we use user.email if Dodo allows lookup by email (less ideal for uniqueness).
                # For now, we assume if creation failed due to conflict, we might not have the ID to retrieve yet.
                # A more robust solution might involve Dodo supporting idempotent creation via a request ID.
                # Re-raising for now, or you might try a retrieve if your user_model.id is intended as a unique key at Dodo.
                # If you can't reliably get the ID after a conflict, this specific idempotency handling is tricky.
                # Let's assume for now the NotFoundError path below will handle a retry if ID was somehow set by another request but not committed yet.
                # A simpler first step is just to let the create fail on conflict if Dodo doesn't offer idempotent keys.
                # For a robust solution for 409, you'd typically try to retrieve the customer by a natural key if possible (e.g. email),
                # or ensure your initial user.id mapping to dodo_customer_id is robust.
                # Given the current structure, if create fails with conflict, the dodo_customer_id won't be set.
                # The safest is to ensure your user_model.id is unique at Dodo, which is what we tried to enforce before.
                # Dodo's API for `create` (email, name) doesn't take `customer_id`.
                # If Dodo doesn't allow setting customer_id on create, then true idempotency via client-side ID is not possible.
                # We rely on Dodo generating the ID.
                # If conflict occurs, the best is probably to try retrieve by email if Dodo supports that, or fail.
                # For simplicity, let's log and re-raise for now. The calling function can handle it.
                logger.error(f"Dodo customer creation conflict for user {user_model.id}. Details: {e_create}")
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Customer already being created. Please try again shortly.")
            raise e_create # Re-raise other creation errors

        logger.info(f"Created Dodo customer {dodo_customer_obj.customer_id} for user {user_model.id}. Assigning to user model.")
        user_model.dodo_customer_id = dodo_customer_obj.customer_id
        dodo_customer_id_was_updated = True
        return dodo_customer_obj, dodo_customer_id_was_updated

    except NotFoundError:
        logger.warning(f"Dodo customer ID {user_model.dodo_customer_id if user_model.dodo_customer_id else 'N/A'} for user {user_model.id} not found. Creating a new one.")
        # If retrieve failed (either because ID was invalid or user_model.dodo_customer_id was None and we tried to create)
        dodo_customer_obj = client.customers.create(
            email=user_model.email,
            name=user_model.name or "HeliaChat User"
        )
        logger.info(f"Successfully created new Dodo customer {dodo_customer_obj.customer_id} for user {user_model.id} after previous one was not found or didn't exist.")
        user_model.dodo_customer_id = dodo_customer_obj.customer_id
        dodo_customer_id_was_updated = True
        return dodo_customer_obj, dodo_customer_id_was_updated
    except Exception as e:
        logger.error(f"Unexpected error in get_or_create_dodo_customer for user {user_model.id}: {str(e)}")
        raise # Re-raise the exception to be caught by the endpoint's error handler

@router.post("/create-checkout", response_model=CheckoutResponse, status_code=status.HTTP_201_CREATED, tags=["billing"])
async def create_checkout(
    request: CreateCheckoutRequest,
    current_user_schema: UserSchema = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Creates a payment checkout session with Dodo Payments and returns a payment link.
    """
    # 1. Initial checks (Dodo client, product ID)
    if not is_client_configured():
        logger.error("Dodo Payments API is not properly configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment service is currently unavailable"
        )
    
    if request.product_id not in PRODUCT_CREDIT_MAP:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid product ID"
        )
    
    credits = PRODUCT_CREDIT_MAP[request.product_id]
    
    try:
        # 2. Fetch user model
        user_stmt = select(User).where(User.id == current_user_schema.id)
        user_result = await db.execute(user_stmt)
        user_model = user_result.scalar_one_or_none()

        if not user_model:
             # This should ideally not happen if get_current_user ensures user exists
             logger.error(f"User not found in DB for ID: {current_user_schema.id} during checkout.")
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
        # 3. Get or create Dodo customer
        # This function now returns (dodo_customer_object, was_id_updated_on_model_flag)
        dodo_customer_obj, dodo_id_was_set = await get_or_create_dodo_customer(user_model, db)
        
        # 4. Commit if Dodo customer ID was newly assigned to our user_model
        if dodo_id_was_set:
            try:
                await db.commit()
                await db.refresh(user_model)
                logger.info(f"Committed dodo_customer_id {user_model.dodo_customer_id} for user {user_model.id}")
            except Exception as e_commit: # Catch potential commit errors
                await db.rollback()
                logger.error(f"DB commit error after setting Dodo ID for user {user_model.id}: {e_commit}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save customer information.")

        # 5. Ensure we have a valid dodo_customer_id to proceed
        if not user_model.dodo_customer_id: # Should be set by get_or_create_dodo_customer
            logger.error(f"Failed to obtain or set a Dodo customer ID for user {user_model.id}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to process customer information with payment provider.")

        # 6. Create payment with Dodo
        # Dodo SDK methods are synchronous
        payment_result = client.payments.create(
            billing={
                "city": "Default City", 
                "country": "IN", 
                "state": "Default State",
                "street": "123 Default Street",
                "zipcode": "560001", 
            },
            product_cart=[{"product_id": request.product_id, "quantity": 1}],
            customer={"customer_id": user_model.dodo_customer_id},
            metadata={"user_id": str(user_model.id), "credits": str(credits)},
            payment_link=True,
            return_url="https://heliachat.com/checkout-success"
        )
        
        # For debugging - uncomment if needed to see available fields
        # logger.info(f"Payment result fields: {payment_result.model_dump() if hasattr(payment_result, 'model_dump') else dir(payment_result)}")
        
        # 7. Create pending purchase record in our database
        purchase = CreditPurchase(
            id=str(uuid4()),
            user_id=current_user_schema.id, # or user_model.id
            credits=credits,
            amount_cents=payment_result.total_amount,
            currency="INR",  # Hardcoded as INR since Dodo response doesn't include currency
            payment_id=payment_result.payment_id,
            status="pending",
            product_id=request.product_id
        )
        
        db.add(purchase)
        await db.commit() # Commit the credit purchase
        
        logger.info(f"Created checkout and pending purchase for user {user_model.id}, Dodo payment ID: {payment_result.payment_id}")
        
        return CheckoutResponse(
            payment_link=payment_result.payment_link,
            payment_id=payment_result.payment_id
        )
        
    # 2. More granular error handling for the endpoint
    except HTTPException: # Allow FastAPI's HTTPExceptions to propagate
        raise
    except NotFoundError as e: # If get_or_create_dodo_customer re-raised it somehow (should be handled within)
        logger.error(f"Dodo API NotFoundError during checkout for user {current_user_schema.id}: {e}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment provider resource not found.")
    # Add other specific Dodo API errors if needed
    # except dodopayments.APIConnectionError as e:
    #     logger.error(f"Dodo API ConnectionError during checkout for user {current_user_schema.id}: {e}")
    #     raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Payment provider unavailable.")
    except Exception as e: # Catch-all for other unexpected errors
        logger.error(f"Unexpected error during create_checkout for user {current_user_schema.id}: {str(e)}", exc_info=True)
        # Rollback in case of an error during the transaction, though commit for user_model might have happened.
        # A more sophisticated unit-of-work pattern might be needed if multiple commits are problematic.
        await db.rollback() 
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while creating the payment checkout."
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
