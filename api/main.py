from pathlib import Path
from contextlib import asynccontextmanager
import asyncio

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


# Load environment variables from .env file
PROJECT_ROOT = Path(__file__).parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
load_dotenv(ENV_FILE)

from api.config import settings
from api.database.connection import get_db_manager, get_session
from api.routers.api_v1.api import api_router
from api.utils.security import generate_api_key
from api.services.session_manager import get_session_manager


# from db.dblib import engine
# from db.models.models import Hero, HeroCreate, HeroPublic, HeroUpdate


async def session_cleanup_background_task(session_manager):
    """
    Background task to periodically clean up expired sessions.

    Runs every 5 minutes to remove expired sessions from memory.
    """
    CLEANUP_INTERVAL_SECONDS = 5 * 60  # 5 minutes

    while True:
        try:
            await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
            count = session_manager.cleanup_expired()
            if count > 0:
                print(f"🧹 Cleaned up {count} expired session(s)")
        except asyncio.CancelledError:
            raise  # Allow task cancellation
        except Exception as e:
            print(f"⚠️  Error in session cleanup task: {str(e)}")
            # Continue running despite errors


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    Handles startup/shutdown events and background tasks.
    """
    import os

    # Startup
    print("\n" + "=" * 60)
    print(f"🚀 Starting {settings.api_title} v{settings.api_version}")
    print("=" * 60)
    print(f"Environment: {settings.environment}")
    print(f"Network: {os.getenv('network', 'NOT SET')}")
    print(f"API Key configured: {'Yes' if settings.api_key_dev else 'No'}")

    # Initialize database connection
    try:
        from api.config import db_settings
        db_manager = get_db_manager()
        db_manager.get_async_engine()
        print(f"✅ Database connected: {db_settings.postgres_db}@{db_settings.postgres_host}")
    except Exception as e:
        print(f"⚠️  Database connection failed: {str(e)}")
        print("   API will start but database operations will fail")

    # Check for wallet mnemonics
    wallet_mnemonics = [k for k in os.environ.keys() if "wallet_mnemonic" in k]
    print(f"Wallet mnemonics found: {len(wallet_mnemonics)}")
    if wallet_mnemonics:
        print(
            f"  Wallets: {', '.join([k.replace('wallet_mnemonic_', '') for k in wallet_mnemonics if k != 'wallet_mnemonic'])}"
        )

    print(f"\n📚 API Documentation: http://127.0.0.1:8000/docs")
    print("=" * 60 + "\n")

    # Start background cleanup task
    session_manager = get_session_manager()
    cleanup_task = asyncio.create_task(session_cleanup_background_task(session_manager))
    print("✅ Background session cleanup task started")

    yield  # Application runs here

    # Shutdown
    print("\n" + "=" * 60)
    print("🛑 Shutting down API")
    print("=" * 60)

    # Cancel background task
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        print("✅ Background cleanup task stopped")

    # Close database connections
    try:
        db_manager = get_db_manager()
        await db_manager.close()
        print("✅ Database connections closed")
    except Exception as e:
        print(f"⚠️  Error closing database: {str(e)}")

    print("=" * 60 + "\n")


app = FastAPI(
    title=settings.api_title,
    description=settings.api_description,
    version=settings.api_version,
    contact=settings.contact,
    lifespan=lifespan,
)

root_router = APIRouter()


@app.get("/")
async def root():
    """Basic HTML response."""
    body = (
        "<html>"
        "<body style='padding: 10px;'>"
        "<h1>Welcome to the Terrasacha Backend API</h1>"
        "<div>"
        "Check the docs: <a href='/docs'>here</a>"
        "</div>"
        "</body>"
        "</html>"
    )

    return HTMLResponse(content=body)


@app.get("/generate-api-key")
async def get_new_api_key():
    api_key = generate_api_key()

    return {"api_key": api_key}


@app.get("/health")
async def health_check(session: AsyncSession = Depends(get_session)):
    """
    Health check endpoint that tests database connectivity.

    Returns:
        - status: "healthy" if database is accessible
        - database: connection status and details
        - version: API version
    """
    from api.config import db_settings

    health_status = {
        "status": "healthy",
        "api_version": settings.api_version,
        "environment": settings.environment,
        "database": {
            "connected": False,
            "host": db_settings.postgres_host,
            "database": db_settings.postgres_db,
        }
    }

    try:
        # Test database connection with a simple query
        result = await session.execute(text("SELECT version()"))
        db_version = result.scalar()

        health_status["database"]["connected"] = True
        health_status["database"]["version"] = db_version

        return JSONResponse(content=health_status, status_code=200)

    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["database"]["error"] = str(e)

        return JSONResponse(content=health_status, status_code=503)


app.include_router(root_router)
app.include_router(api_router, prefix=settings.API_V1_STR)
