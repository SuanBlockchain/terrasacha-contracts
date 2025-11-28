#!/bin/bash
set -e

echo "🔄 Running database migrations..."
alembic upgrade head

echo "✅ Migrations complete"
echo "🚀 Starting API server..."
exec uvicorn api.main:app --host 0.0.0.0 --port 8000
