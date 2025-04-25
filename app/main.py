from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.chat import router as chat_router
from app.api.auth import router as auth_router
from app.db.session import init_db
import uvicorn


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize the database
    await init_db()
    yield
   


app = FastAPI(lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers
app.include_router(auth_router, prefix="/api/auth", tags=["authentication"])
app.include_router(chat_router, prefix="/api", tags=["chat"])

# This block allows the server to be run directly using 'python app/main.py'
if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
