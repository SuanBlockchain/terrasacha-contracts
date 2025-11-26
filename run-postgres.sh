#!/bin/bash

# Run PostgreSQL Container for Local Development
# This script starts a PostgreSQL container for local testing only
# For production, use AWS RDS or another managed database service

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
CONTAINER_NAME="terrasacha-postgres"
IMAGE_NAME="terrasacha-postgres:latest"
NETWORK_NAME="terrasacha-network"
VOLUME_NAME="terrasacha-contracts_postgres_data"  # Using existing docker-compose volume

# Database configuration (can be overridden by environment variables)
POSTGRES_USER=${POSTGRES_USER:-terrasacha}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-changeme}
POSTGRES_DB=${POSTGRES_DB:-terrasacha_db}
POSTGRES_PORT=${POSTGRES_PORT:-5432}

echo -e "${GREEN}Starting PostgreSQL container for local development...${NC}"

# Create network if it doesn't exist
if ! docker network inspect $NETWORK_NAME &> /dev/null; then
    echo -e "${YELLOW}Creating Docker network: $NETWORK_NAME${NC}"
    docker network create $NETWORK_NAME
fi

# Check if container already exists
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${YELLOW}Container $CONTAINER_NAME already exists${NC}"

    # Check if it's running
    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo -e "${GREEN}Container is already running${NC}"
        docker logs --tail 5 $CONTAINER_NAME
        exit 0
    else
        echo -e "${YELLOW}Starting existing container...${NC}"
        docker start $CONTAINER_NAME
        echo -e "${GREEN}Container started successfully${NC}"
        docker logs --tail 5 $CONTAINER_NAME
        exit 0
    fi
fi

# Build the image if it doesn't exist
if ! docker images --format '{{.Repository}}:{{.Tag}}' | grep -q "^${IMAGE_NAME}$"; then
    echo -e "${YELLOW}Building PostgreSQL image...${NC}"
    docker build -f Dockerfile.postgres -t $IMAGE_NAME .
fi

# Run the container
echo -e "${GREEN}Running new PostgreSQL container...${NC}"
docker run -d \
  --name $CONTAINER_NAME \
  --network $NETWORK_NAME \
  -e POSTGRES_USER=$POSTGRES_USER \
  -e POSTGRES_PASSWORD=$POSTGRES_PASSWORD \
  -e POSTGRES_DB=$POSTGRES_DB \
  -p $POSTGRES_PORT:5432 \
  -v $VOLUME_NAME:/var/lib/postgresql/data \
  --restart unless-stopped \
  $IMAGE_NAME

# Wait for PostgreSQL to be ready
echo -e "${YELLOW}Waiting for PostgreSQL to be ready...${NC}"
sleep 3

# Check if container is running
if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${GREEN}PostgreSQL container started successfully!${NC}"
    echo ""
    echo "Connection details:"
    echo "  Host: localhost"
    echo "  Port: $POSTGRES_PORT"
    echo "  Database: $POSTGRES_DB"
    echo "  User: $POSTGRES_USER"
    echo "  Password: $POSTGRES_PASSWORD"
    echo ""
    echo "To view logs: docker logs -f $CONTAINER_NAME"
    echo "To stop: docker stop $CONTAINER_NAME"
    echo "To access psql: docker exec -it $CONTAINER_NAME psql -U $POSTGRES_USER -d $POSTGRES_DB"
else
    echo -e "${RED}Failed to start PostgreSQL container${NC}"
    docker logs $CONTAINER_NAME
    exit 1
fi
