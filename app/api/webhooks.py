"""
Webhook endpoints for handling notifications from external services.
"""
from fastapi import APIRouter, Request, Header, HTTPException, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import json
import os
import logging
from standardwebhooks import Webhook

from app.db.session import get_db
from app.db.models import CreditPurchase
from app.db.crud import get_user_profile

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/dodo")
async def dodo_webhook(
    request: Request,
    webhook_id: str = Header(None, alias="webhook-id"),
    webhook_signature: str = Header(None, alias="webhook-signature"),
    webhook_timestamp: str = Header(None, alias="webhook-timestamp"), 
    db: AsyncSession = Depends(get_db)
):
    """
    Handles webhook events from Dodo Payments.
    
    The main purpose is to process completed payments and credit the user's account.
    This function:
    1. Verifies the webhook signature
    2. Processes payment.succeeded events
    3. Updates the credit purchase record
    4. Credits the user's account
    """
    # Get the raw payload
    payload = await request.body()
    
    # Log the incoming webhook (excluding sensitive data)
    logger.info(f"Received Dodo webhook with ID: {webhook_id}")
    
    # Verify webhook signature using standardwebhooks
    webhook_secret = os.getenv("DODO_WEBHOOK_SECRET")
    if not webhook_secret:
        logger.error("Missing DODO_WEBHOOK_SECRET environment variable")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook verification configuration error"
        )
    
    # Prepare webhook signature verification
    webhook = Webhook(webhook_secret)
    
    headers = {
        "webhook-id": webhook_id,
        "webhook-signature": webhook_signature,
        "webhook-timestamp": webhook_timestamp,
    }
    
    # Verify the signature with raw bytes instead of decoded string
    try:
        # Use raw payload bytes for verification
        await webhook.verify(payload, headers)
        # Only decode after verification for processing
        raw_body = payload.decode('utf-8')
    except Exception as e:
        logger.error(f"Webhook signature verification failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid signature: {str(e)}"
        )
    
    # Process the event payload
    try:
        event_data = json.loads(raw_body)
        event_type = event_data.get("type", "unknown")
        logger.info(f"Processing webhook event type: {event_type}")
        
        # Handle payment events
        if event_type == "payment.succeeded":
            await process_successful_payment(event_data, db)
            return {"status": "success", "event_type": event_type}
        elif event_type == "payment.failed":
            await process_failed_payment(event_data, db)
            return {"status": "success", "event_type": event_type}
        elif event_type == "payment.expired":
            await process_expired_payment(event_data, db)
            return {"status": "success", "event_type": event_type}
        
        # Handle other event types as needed
        logger.info(f"No specific handler for event type: {event_type}")
        return {"status": "received", "message": "Event acknowledged but not processed"}
    
    except json.JSONDecodeError:
        logger.error("Failed to parse webhook payload as JSON")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload"
        )
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process webhook"
        )

async def process_successful_payment(event_data, db):
    """Process a payment.succeeded event"""
    payment_data = event_data.get("data", {})
    payment_id = payment_data.get("payment_id")
    
    if not payment_id:
        logger.error("Missing payment_id in payment.succeeded event")
        return
    
    # Find the purchase record
    stmt = select(CreditPurchase).where(CreditPurchase.payment_id == payment_id)
    purchase = (await db.execute(stmt)).scalar_one_or_none()
    
    if not purchase:
        logger.error(f"No purchase record found for payment_id: {payment_id}")
        return
    
    # Idempotency check - only process if not already marked as succeeded
    if purchase.status == "succeeded":
        logger.info(f"Payment already processed: {payment_id}")
        return
    
    # Update purchase status
    purchase.status = "succeeded"
    
    # Update user credits
    user = await get_user_profile(purchase.user_id, db)
    if not user:
        logger.error(f"User not found for purchase: {purchase.id}, user_id: {purchase.user_id}")
        return
    
    # Credit the user's account
    previous_credits = user.credits_remaining
    user.credits_remaining += purchase.credits
    
    # Commit the changes
    await db.commit()
    
    logger.info(
        f"Credits added: User {user.id} credited with {purchase.credits} credits. "
        f"Balance: {previous_credits} -> {user.credits_remaining}"
    )

async def process_failed_payment(event_data, db):
    """Process a payment.failed event"""
    payment_data = event_data.get("data", {})
    payment_id = payment_data.get("payment_id")
    
    if not payment_id:
        logger.error("Missing payment_id in payment.failed event")
        return
    
    # Find the purchase record
    stmt = select(CreditPurchase).where(CreditPurchase.payment_id == payment_id)
    purchase = (await db.execute(stmt)).scalar_one_or_none()
    
    if not purchase:
        logger.error(f"No purchase record found for payment_id: {payment_id}")
        return
    
    # Idempotency check - only process if not already marked as failed
    if purchase.status == "failed":
        logger.info(f"Payment already marked as failed: {payment_id}")
        return
    
    # Update purchase status
    purchase.status = "failed"
    await db.commit()
    
    logger.info(f"Payment failed: purchase_id={purchase.id}, payment_id={payment_id}")

async def process_expired_payment(event_data, db):
    """Process a payment.expired event"""
    payment_data = event_data.get("data", {})
    payment_id = payment_data.get("payment_id")
    
    if not payment_id:
        logger.error("Missing payment_id in payment.expired event")
        return
    
    # Find the purchase record
    stmt = select(CreditPurchase).where(CreditPurchase.payment_id == payment_id)
    purchase = (await db.execute(stmt)).scalar_one_or_none()
    
    if not purchase:
        logger.error(f"No purchase record found for payment_id: {payment_id}")
        return
    
    # Idempotency check - only process if not already marked as expired
    if purchase.status == "expired":
        logger.info(f"Payment already marked as expired: {payment_id}")
        return
    
    # Update purchase status
    purchase.status = "expired"
    await db.commit()
    
    logger.info(f"Payment expired: purchase_id={purchase.id}, payment_id={payment_id}") 