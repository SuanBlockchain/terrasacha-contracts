#!/bin/bash

# Stop All Terrasacha Docker Containers
# This script stops and optionally removes all local development containers

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
API_CONTAINER="terrasacha-api"
POSTGRES_CONTAINER="terrasacha-postgres"
NETWORK_NAME="terrasacha-network"
VOLUME_NAME="terrasacha-contracts_postgres_data"  # Using existing docker-compose volume

echo -e "${BLUE}=== Terrasacha Docker Cleanup ===${NC}\n"

# Parse command line arguments
REMOVE_CONTAINERS=false
REMOVE_VOLUMES=false
REMOVE_NETWORK=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --remove|-r)
            REMOVE_CONTAINERS=true
            shift
            ;;
        --remove-volumes|-rv)
            REMOVE_CONTAINERS=true
            REMOVE_VOLUMES=true
            shift
            ;;
        --full-cleanup|-f)
            REMOVE_CONTAINERS=true
            REMOVE_VOLUMES=true
            REMOVE_NETWORK=true
            shift
            ;;
        --help|-h)
            echo "Usage: ./stop-all.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --remove, -r          Stop and remove containers"
            echo "  --remove-volumes, -rv Stop, remove containers and volumes (deletes data!)"
            echo "  --full-cleanup, -f    Stop, remove everything including network"
            echo "  --help, -h            Show this help message"
            echo ""
            echo "Examples:"
            echo "  ./stop-all.sh                Just stop containers"
            echo "  ./stop-all.sh --remove       Stop and remove containers"
            echo "  ./stop-all.sh --full-cleanup Complete cleanup"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Stop containers
echo -e "${YELLOW}Stopping containers...${NC}"

if docker ps --format '{{.Names}}' | grep -q "^${API_CONTAINER}$"; then
    echo "  Stopping $API_CONTAINER..."
    docker stop $API_CONTAINER
    echo -e "  ${GREEN}✓${NC} $API_CONTAINER stopped"
else
    echo "  $API_CONTAINER is not running"
fi

if docker ps --format '{{.Names}}' | grep -q "^${POSTGRES_CONTAINER}$"; then
    echo "  Stopping $POSTGRES_CONTAINER..."
    docker stop $POSTGRES_CONTAINER
    echo -e "  ${GREEN}✓${NC} $POSTGRES_CONTAINER stopped"
else
    echo "  $POSTGRES_CONTAINER is not running"
fi

# Remove containers if requested
if [ "$REMOVE_CONTAINERS" = true ]; then
    echo ""
    echo -e "${YELLOW}Removing containers...${NC}"

    if docker ps -a --format '{{.Names}}' | grep -q "^${API_CONTAINER}$"; then
        echo "  Removing $API_CONTAINER..."
        docker rm $API_CONTAINER
        echo -e "  ${GREEN}✓${NC} $API_CONTAINER removed"
    fi

    if docker ps -a --format '{{.Names}}' | grep -q "^${POSTGRES_CONTAINER}$"; then
        echo "  Removing $POSTGRES_CONTAINER..."
        docker rm $POSTGRES_CONTAINER
        echo -e "  ${GREEN}✓${NC} $POSTGRES_CONTAINER removed"
    fi
fi

# Remove volumes if requested
if [ "$REMOVE_VOLUMES" = true ]; then
    echo ""
    echo -e "${RED}Removing volumes (this will delete all database data!)...${NC}"
    read -p "Are you sure? (yes/no): " confirm

    if [ "$confirm" = "yes" ]; then
        if docker volume ls --format '{{.Name}}' | grep -q "^${VOLUME_NAME}$"; then
            echo "  Removing volume $VOLUME_NAME..."
            docker volume rm $VOLUME_NAME
            echo -e "  ${GREEN}✓${NC} Volume removed"
        else
            echo "  Volume $VOLUME_NAME does not exist"
        fi
    else
        echo "  Volume removal cancelled"
    fi
fi

# Remove network if requested
if [ "$REMOVE_NETWORK" = true ]; then
    echo ""
    echo -e "${YELLOW}Removing network...${NC}"

    if docker network ls --format '{{.Name}}' | grep -q "^${NETWORK_NAME}$"; then
        # Check if any containers are still using the network
        NETWORK_IN_USE=$(docker network inspect $NETWORK_NAME --format '{{range .Containers}}{{.Name}} {{end}}' 2>/dev/null || echo "")

        if [ -z "$NETWORK_IN_USE" ]; then
            echo "  Removing network $NETWORK_NAME..."
            docker network rm $NETWORK_NAME
            echo -e "  ${GREEN}✓${NC} Network removed"
        else
            echo -e "  ${YELLOW}⚠${NC}  Network still in use by: $NETWORK_IN_USE"
            echo "  Network not removed"
        fi
    else
        echo "  Network $NETWORK_NAME does not exist"
    fi
fi

# Summary
echo ""
echo -e "${GREEN}=== Cleanup Complete ===${NC}"

# Show what's left
RUNNING_CONTAINERS=$(docker ps --filter "name=terrasacha" --format '{{.Names}}' | wc -l)
ALL_CONTAINERS=$(docker ps -a --filter "name=terrasacha" --format '{{.Names}}' | wc -l)

echo ""
echo "Status:"
echo "  Running containers: $RUNNING_CONTAINERS"
echo "  Total containers: $ALL_CONTAINERS"

if [ "$REMOVE_CONTAINERS" = false ] && [ $ALL_CONTAINERS -gt 0 ]; then
    echo ""
    echo -e "${YELLOW}Tip: Use './stop-all.sh --remove' to remove stopped containers${NC}"
fi

if [ "$REMOVE_VOLUMES" = false ]; then
    echo ""
    echo -e "${YELLOW}Database volume is preserved. To remove it, use '--remove-volumes'${NC}"
fi

echo ""
echo "To start services again:"
echo "  ./run-postgres.sh"
echo "  ./run-api.sh"
