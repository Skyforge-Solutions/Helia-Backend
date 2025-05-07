"""
Dodo Payments API client wrapper.
This file contains the client instance used throughout the application
to interact with the Dodo Payments API.
"""
from dodopayments import DodoPayments
import os
import logging

# Configure logging
logger = logging.getLogger(__name__)

# Initialize client with environment-based configuration
try:
    client = DodoPayments(
        bearer_token=os.getenv("DODO_PAYMENTS_API_KEY"),
        environment="test" if "test" in os.getenv("DODO_BASE_URL", "") else "live"
    )
    logger.info(f"Dodo Payments client initialized in {'test' if 'test' in os.getenv('DODO_BASE_URL', '') else 'live'} mode")
except Exception as e:
    logger.error(f"Failed to initialize Dodo Payments client: {str(e)}")
    raise

# Function to check if client is properly configured
def is_client_configured():
    """Check if the Dodo client is properly configured with API keys."""
    return bool(os.getenv("DODO_PAYMENTS_API_KEY")) and bool(os.getenv("DODO_WEBHOOK_SECRET")) 