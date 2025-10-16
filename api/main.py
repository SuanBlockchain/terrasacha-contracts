
from fastapi import APIRouter, FastAPI
from fastapi.responses import HTMLResponse

from api.config import settings
from api.utils.security import generate_api_key
from api.routers.api_v1.api import api_router


# from db.dblib import engine
# from db.models.models import Hero, HeroCreate, HeroPublic, HeroUpdate

app = FastAPI(
    title=settings.api_title,
    description=settings.api_description,
    version=settings.api_version,
    contact=settings.contact,
)

root_router = APIRouter()

app.include_router(root_router)
app.include_router(api_router, prefix=settings.API_V1_STR)


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


# @app.on_event("startup")
# async def startup_event():
#     print(f"Starting {settings.api_title} v{settings.api_version}")
#     print(f"Environment: {settings.environment}")
#     print(f"Database: {settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}")

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
