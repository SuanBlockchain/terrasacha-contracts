#!/bin/bash
set -e

echo "🚀 Starting Terrasacha API (MongoDB-only)"
echo "📊 No migrations needed - MongoDB schema-less architecture"
exec uvicorn api.main:app --host 0.0.0.0 --port 8000
