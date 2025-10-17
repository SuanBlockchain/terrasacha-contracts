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


# @app.post("/heroes/", response_model=HeroPublic)
# async def create_hero(hero: HeroCreate):
#     hashed_password = hero.password + "notreallyhashed"
#     with Session(engine) as session:
#         extra_data = {"hashed_password": hashed_password}
#         db_hero = Hero.model_validate(hero, update=extra_data)
#         session.add(db_hero)
#         session.commit()
#         session.refresh(db_hero)
#         return db_hero

# @app.get("/heroes/", response_model=list[Hero])
# def read_heroes(offset: int = 0, limit: int= Query(default=100, le=100)):
#     with Session(engine) as session:
#         heroes = session.exec(select(Hero).offset(offset).limit(limit)).all()
#         return heroes

# @app.get("/heroes/{hero_id}", response_model=HeroPublic)
# def read_hero(hero_id: int):
#     with Session(engine) as session:
#         hero = session.get(Hero, hero_id)
#         if not hero:
#             raise HTTPException(status_code=404, detail="Hero not found")
#         return hero


# @app.patch("/heroes/{hero_id}", response_model=HeroPublic)
# def update_hero(hero_id: int, hero: HeroUpdate):
#     with Session(engine) as session:
#         db_hero = session.get(Hero, hero_id)
#         if not db_hero:
#             raise HTTPException(status_code=404, detail="Hero not found")
#         hero_data = hero.model_dump(exclude_unset=True)
#         extra_data = {}
#         if "password" in hero_data:
#             hashed_password = hero_data["password"] + "notreallyhashed"
#             extra_data["hashed_password"] = hashed_password
#         db_hero.sqlmodel_update(hero_data, update = extra_data)
#         session.add(db_hero)
#         session.commit()
#         session.refresh(db_hero)
#         return db_hero
