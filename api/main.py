from pathlib import Path
from contextlib import asynccontextmanager
import asyncio

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, Depends
from fastapi.responses import HTMLResponse, JSONResponse


# Load environment variables from .env file
PROJECT_ROOT = Path(__file__).parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
load_dotenv(ENV_FILE)

from api.config import settings
from api.routers.api_v1.api import api_router
from api.utils.security import generate_api_key
from api.services.session_manager import get_session_manager
from api.services.session_cleanup_service import get_cleanup_service


# from db.dblib import engine
# from db.models.models import Hero, HeroCreate, HeroPublic, HeroUpdate


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
    print(f"Admin API Key configured: {'Yes' if settings.admin_api_key else 'No'}")

    # Initialize MongoDB multi-tenant database
    try:
        from api.database.multi_tenant_manager import get_multi_tenant_db_manager
        db_manager = get_multi_tenant_db_manager()
        await db_manager.initialize()
        print(f"✅ MongoDB multi-tenant database initialized")
        print(f"   Admin database: terrasacha_admin")
        print(f"   Architecture: MongoDB-only (PostgreSQL removed)")
    except Exception as e:
        print(f"❌ MongoDB initialization failed: {str(e)}")
        print("   MONGODB_ADMIN_URI environment variable must be set")
        raise  # Fail fast if MongoDB is not available

    # Check for wallet mnemonics
    wallet_mnemonics = [k for k in os.environ.keys() if "wallet_mnemonic" in k]
    print(f"Wallet mnemonics found: {len(wallet_mnemonics)}")
    if wallet_mnemonics:
        print(
            f"  Wallets: {', '.join([k.replace('wallet_mnemonic_', '') for k in wallet_mnemonics if k != 'wallet_mnemonic'])}"
        )

    print(f"\n📚 API Documentation: http://127.0.0.1:8000/docs")
    print("=" * 60 + "\n")

    # Start background session cleanup task
    cleanup_task = None
    cleanup_interval_minutes = int(os.getenv("SESSION_CLEANUP_INTERVAL_MINUTES", "5"))

    async def periodic_session_cleanup():
        """Run session cleanup periodically."""
        while True:
            try:
                await asyncio.sleep(cleanup_interval_minutes * 60)  # Convert minutes to seconds
                cleanup_service = get_cleanup_service()
                stats = await cleanup_service.cleanup_expired_sessions()
                print(
                    f"🧹 Session cleanup: {stats['wallets_locked']} wallets locked, "
                    f"{stats['sessions_removed_from_memory']} sessions removed"
                )
            except asyncio.CancelledError:
                print("Session cleanup task cancelled")
                break
            except Exception as e:
                print(f"⚠️  Session cleanup error: {str(e)}")

    # Start cleanup task
    cleanup_task = asyncio.create_task(periodic_session_cleanup())
    print(f"✅ Session cleanup task started (runs every {cleanup_interval_minutes} minutes)")
    print("ℹ️  MongoDB TTL index also auto-deletes expired sessions from database")

    yield  # Application runs here

    # Shutdown
    print("\n" + "=" * 60)
    print("🛑 Shutting down API")
    print("=" * 60)

    # Cancel cleanup task
    if cleanup_task:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
        print("✅ Session cleanup task stopped")

    # Close MongoDB connections
    try:
        from api.database.multi_tenant_manager import get_multi_tenant_db_manager
        db_manager = get_multi_tenant_db_manager()
        await db_manager.close()
        print("✅ MongoDB connections closed")
    except Exception as e:
        print(f"⚠️  Error closing MongoDB: {str(e)}")

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
async def health_check():
    """
    Health check endpoint that tests MongoDB connectivity.

    Returns:
        - status: "healthy" if MongoDB is accessible
        - database: MongoDB connection status
        - api_version: API version
        - environment: Current environment
    """
    health_status = {
        "status": "healthy",
        "api_version": settings.api_version,
        "environment": settings.environment,
        "database": {
            "type": "MongoDB",
            "connected": False,
        }
    }

    try:
        # Test MongoDB connection by counting tenants
        from api.database.models import Tenant

        tenant_count = await Tenant.count()

        health_status["database"]["connected"] = True
        health_status["database"]["tenant_count"] = tenant_count
        health_status["database"]["architecture"] = "Multi-tenant"

        return JSONResponse(content=health_status, status_code=200)

    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["database"]["error"] = str(e)

        return JSONResponse(content=health_status, status_code=503)


app.include_router(root_router)
app.include_router(api_router, prefix=settings.API_V1_STR)
