from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import os
import pathlib
from dotenv import load_dotenv
from app.db.models import Base
import sys

# Get the project root directory and load environment variables with explicit path
base_dir = pathlib.Path(__file__).parent.parent.parent.absolute()
env_path = base_dir / ".env"
load_dotenv(dotenv_path=env_path)

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError(f"DATABASE_URL environment variable is not set. Check your .env file at {env_path}")

# For Neon database connections, we'll configure SSL via connect_args instead of URL parameters
# Remove any existing sslmode from the URL if it exists
if 'sslmode=' in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.split('?')[0]

# Prepare SSL settings for asyncpg
ssl_mode = None
if 'neon.tech' in DATABASE_URL:
    ssl_mode = True  # Enable SSL for Neon database connections

# Configure engine with proper connection pool settings
try:
    engine = create_async_engine(
        DATABASE_URL,
        echo=False, 
        future=True,
        # Configure connection pooling properly
        pool_size=20,
        max_overflow=20,
        pool_pre_ping=True,  # Test connections before using them
        pool_recycle=3600,   # Recycle connections after 1 hour
        connect_args={
            "server_settings": {"application_name": "HeliaChat"},
            **({"ssl": ssl_mode} if ssl_mode else {})
        },
    )
except Exception as e:
    print(f"Error creating database engine: {e}")
    sys.exit(1)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

async def get_db():
    """Dependency to get an async database session."""
    session = AsyncSessionLocal()
    try:
        yield session
    finally:
        await session.close()

async def init_db():
    # create tables on startup
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("Database tables created successfully")
    except Exception as e:
        print(f"Error initializing database: {e}")
        # Depending on your error handling strategy, you might want to exit or continue
        # If this is a critical error, exit the application
        sys.exit(1)