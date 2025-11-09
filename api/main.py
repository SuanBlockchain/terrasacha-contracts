from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI
from fastapi.responses import HTMLResponse


# Load environment variables from .env file
PROJECT_ROOT = Path(__file__).parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
load_dotenv(ENV_FILE)

from api.config import settings
from api.database.connection import get_db_manager
from api.routers.api_v1.api import api_router
from api.utils.security import generate_api_key


# from db.dblib import engine
# from db.models.models import Hero, HeroCreate, HeroPublic, HeroUpdate

app = FastAPI(
    title=settings.api_title,
    description=settings.api_description,
    version=settings.api_version,
    contact=settings.contact,
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


app.include_router(root_router)
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.on_event("startup")
async def startup_event():
    """Log startup information and initialize database"""
    import os

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
        # Test connection by getting engine
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


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup database connections on shutdown"""
    print("\n" + "=" * 60)
    print("🛑 Shutting down API")
    print("=" * 60)

    # Close database connections
    try:
        db_manager = get_db_manager()
        await db_manager.close()
        print("✅ Database connections closed")
    except Exception as e:
        print(f"⚠️  Error closing database: {str(e)}")

    print("=" * 60 + "\n")
