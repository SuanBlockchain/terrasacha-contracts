# Terrasacha API

FastAPI application for managing carbon credit tokens and NFTs on the Cardano blockchain.

## Quick Start

### Development Server

Run the development server from the project root:

```bash
uv run fastapi dev api/main.py
```

The server will start at:
- **API**: http://127.0.0.1:8000
- **Interactive Docs**: http://127.0.0.1:8000/docs
- **Alternative Docs**: http://127.0.0.1:8000/redoc

### Production Server

For production deployment:

```bash
uv run fastapi run api/main.py
```

Or with uvicorn directly:

```bash
uv run uvicorn api.main:app --host 0.0.0.0 --port 8000
```

## Configuration

API settings are configured in `api/config.py`:

### Hardcoded Settings (versioned with code)
- `api_title`: "Terrasacha API"
- `api_description`: Full API description
- `api_version`: "1.0.0"
- Contact information

### Environment Settings (from .env file)
- `ENVIRONMENT`: development, staging, or production (default: development)
- `API_PORT`: Server port (default: 8000)
- `POSTGRES_*`: Database connection settings

## Project Structure

```
api/
├── __init__.py          # Package initialization
├── main.py              # FastAPI application entry point
├── config.py            # Application settings
├── database/            # Database connection and models
│   ├── connection.py    # Database manager and settings
│   ├── models.py        # SQLModel database models
│   └── repositories/    # Data access layer
└── utils/               # Utility functions
    └── security.py      # Security helpers (API keys, etc.)
```

## API Endpoints

### Current Endpoints

- `GET /` - Welcome page with link to documentation
- `GET /generate-api-key` - Generate a new API key
- `GET /docs` - Interactive API documentation (Swagger UI)
- `GET /redoc` - Alternative API documentation (ReDoc)

## Development

### Adding New Endpoints

1. Create a new router in `api/routers/` (create folder if needed)
2. Define your endpoints using FastAPI decorators
3. Include the router in `api/main.py`

Example:

```python
from fastapi import APIRouter

router = APIRouter(prefix="/projects", tags=["projects"])

@router.get("/")
async def list_projects():
    return {"projects": []}

# In api/main.py:
from api.routers import projects
app.include_router(projects.router)
```

### Database Sessions

Use the dependency injection for database sessions:

```python
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from api.database.connection import get_session

@router.get("/items")
async def get_items(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Item))
    return result.scalars().all()
```

## Environment Variables

Required variables in `.env`:

```bash
# Database
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=your_user
POSTGRES_PASSWORD=your_password
POSTGRES_DB=terrasacha_db

# API
ENVIRONMENT=development
API_PORT=8000
```

## Testing

Run API tests:

```bash
uv run pytest tests/api/
```

## Deployment

For production deployment, consider:

1. **Use a production ASGI server** (Gunicorn + Uvicorn workers)
2. **Set environment variables** for production database
3. **Enable HTTPS** with reverse proxy (nginx/caddy)
4. **Configure CORS** if needed for frontend
5. **Set up logging** and monitoring
6. **Use database migrations** with Alembic

Example production command with Gunicorn:

```bash
gunicorn api.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```
