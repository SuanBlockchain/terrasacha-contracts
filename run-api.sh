#!/bin/bash

# Run FastAPI Container for Local Development
# This script starts the FastAPI container and connects it to PostgreSQL
# For production, use AWS Copilot deployment

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
CONTAINER_NAME="terrasacha-api"
IMAGE_NAME="terrasacha-api:latest"
NETWORK_NAME="terrasacha-network"
POSTGRES_CONTAINER="terrasacha-postgres"

# API configuration
API_PORT=${API_PORT:-8000}

echo -e "${GREEN}Starting FastAPI container for local development...${NC}"

# Check if .env file exists
if [ ! -f .env ]; then
    echo -e "${RED}ERROR: .env file not found!${NC}"
    echo "Please create a .env file from .env.example"
    echo "  cp .env.example .env"
    exit 1
fi

# Create network if it doesn't exist
if ! docker network inspect $NETWORK_NAME &> /dev/null; then
    echo -e "${YELLOW}Creating Docker network: $NETWORK_NAME${NC}"
    docker network create $NETWORK_NAME
fi

# Check if PostgreSQL is running
if ! docker ps --format '{{.Names}}' | grep -q "^${POSTGRES_CONTAINER}$"; then
    echo -e "${YELLOW}PostgreSQL container is not running${NC}"
    echo "Starting PostgreSQL first..."
    ./run-postgres.sh
    echo ""
    sleep 2
fi

# Check if container already exists
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${YELLOW}Container $CONTAINER_NAME already exists${NC}"

    # Check if it's running
    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo -e "${GREEN}Container is already running${NC}"
        docker logs --tail 10 $CONTAINER_NAME
        echo ""
        echo -e "${GREEN}API is available at: http://localhost:$API_PORT${NC}"
        echo -e "${GREEN}API Documentation: http://localhost:$API_PORT/docs${NC}"
        exit 0
    else
        echo -e "${YELLOW}Starting existing container...${NC}"
        docker start $CONTAINER_NAME
        echo -e "${GREEN}Container started successfully${NC}"
        docker logs --tail 10 $CONTAINER_NAME
        echo ""
        echo -e "${GREEN}API is available at: http://localhost:$API_PORT${NC}"
        echo -e "${GREEN}API Documentation: http://localhost:$API_PORT/docs${NC}"
        exit 0
    fi
fi

# Build the image if it doesn't exist
if ! docker images --format '{{.Repository}}:{{.Tag}}' | grep -q "^${IMAGE_NAME}$"; then
    echo -e "${YELLOW}Building FastAPI image...${NC}"
    docker build -t $IMAGE_NAME .
fi

# Get PostgreSQL credentials from .env file
POSTGRES_HOST=${POSTGRES_HOST:-$POSTGRES_CONTAINER}
POSTGRES_USER=$(grep POSTGRES_USER .env | cut -d '=' -f2 | tr -d '[:space:]')
POSTGRES_PASSWORD=$(grep POSTGRES_PASSWORD .env | cut -d '=' -f2 | tr -d '[:space:]')
POSTGRES_DB=$(grep POSTGRES_DB .env | cut -d '=' -f2 | tr -d '[:space:]')
POSTGRES_PORT=${POSTGRES_PORT:-5432}

# Run the container
echo -e "${GREEN}Running new FastAPI container...${NC}"
docker run -d \
  --name $CONTAINER_NAME \
  --network $NETWORK_NAME \
  -p $API_PORT:8000 \
  --env-file .env \
  -e POSTGRES_HOST=$POSTGRES_HOST \
  -e POSTGRES_USER=${POSTGRES_USER:-terrasacha} \
  -e POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-changeme} \
  -e POSTGRES_DB=${POSTGRES_DB:-terrasacha_db} \
  -e POSTGRES_PORT=$POSTGRES_PORT \
  --restart unless-stopped \
  $IMAGE_NAME

# Wait for API to be ready
echo -e "${YELLOW}Waiting for API to be ready...${NC}"
sleep 3

# Check if container is running
if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${GREEN}FastAPI container started successfully!${NC}"
    echo ""
    echo "API Information:"
    echo "  URL: http://localhost:$API_PORT"
    echo "  Documentation: http://localhost:$API_PORT/docs"
    echo "  Redoc: http://localhost:$API_PORT/redoc"
    echo ""
    echo "Container Information:"
    echo "  Database Host: $POSTGRES_HOST"
    echo "  Database: ${POSTGRES_DB:-terrasacha_db}"
    echo ""
    echo "Useful commands:"
    echo "  View logs: docker logs -f $CONTAINER_NAME"
    echo "  Stop: docker stop $CONTAINER_NAME"
    echo "  Restart: docker restart $CONTAINER_NAME"
    echo ""
    echo -e "${YELLOW}Recent logs:${NC}"
    docker logs --tail 15 $CONTAINER_NAME
else
    echo -e "${RED}Failed to start FastAPI container${NC}"
    docker logs $CONTAINER_NAME
    exit 1
fi
