from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import sys
import os
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# Add parent directory to path to fix imports when running directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Now we can import from app
from app.api.chat import router as chat_router
from app.api.auth import router as auth_router
from app.api.billing import router as billing_router
from app.api.webhooks import router as webhook_router
from app.db.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize the database
    logger.info("Initializing database...")
    await init_db()
    
    # Check for required environment variables
    for var in ["DODO_PAYMENTS_API_KEY", "DODO_WEBHOOK_SECRET", "DODO_BASE_URL"]:
        if not os.getenv(var):
            logger.warning(f"Environment variable {var} is not set")
    
    logger.info("Application startup complete")
    yield
    logger.info("Application shutdown")
   
app = FastAPI(lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# a health check endpoint on / 
@app.get("/")
async def health_check():
    return {"status": "ok"}

# API routers
app.include_router(auth_router, prefix="/api", tags=["authentication"])
app.include_router(chat_router, prefix="/api", tags=["chat"])
app.include_router(billing_router, prefix="/api/billing", tags=["billing"])
app.include_router(webhook_router, prefix="/api/webhook", tags=["webhooks"])

# This block allows the server to be run directly using 'python app/main.py'
if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
