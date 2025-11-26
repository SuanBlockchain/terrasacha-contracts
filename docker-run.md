# Running Docker Containers Independently

This guide shows how to run the FastAPI and PostgreSQL services independently without docker-compose.

## Prerequisites

- Docker installed and running
- `.env` file configured (copy from `.env.example`)

## Quick Start

### Option 1: Using Helper Scripts (Recommended)

```bash
# Start PostgreSQL
./run-postgres.sh

# Start FastAPI (in another terminal)
./run-api.sh

# Stop all containers
./stop-all.sh
```

### Option 2: Manual Docker Commands

See detailed commands below.

---

## PostgreSQL Container

### Build PostgreSQL Image

```bash
docker build -f Dockerfile.postgres -t terrasacha-postgres:latest .
```

### Run PostgreSQL Container

```bash
docker run -d \
  --name terrasacha-postgres \
  --network terrasacha-network \
  -e POSTGRES_USER=terrasacha \
  -e POSTGRES_PASSWORD=changeme \
  -e POSTGRES_DB=terrasacha_db \
  -p 5432:5432 \
  -v terrasacha-contracts_postgres_data:/var/lib/postgresql/data \
  terrasacha-postgres:latest
```

### Environment Variables

You can customize these values:
- `POSTGRES_USER` - Database user (default: terrasacha)
- `POSTGRES_PASSWORD` - Database password (default: changeme)
- `POSTGRES_DB` - Database name (default: terrasacha_db)
- `PGDATA` - Data directory (default: /var/lib/postgresql/data/pgdata)

### Check PostgreSQL Status

```bash
# View logs
docker logs terrasacha-postgres

# Check if running
docker ps | grep terrasacha-postgres

# Access PostgreSQL shell
docker exec -it terrasacha-postgres psql -U terrasacha -d terrasacha_db
```

---

## FastAPI Container

### Build FastAPI Image

```bash
docker build -t terrasacha-api:latest .
```

### Run FastAPI Container

```bash
docker run -d \
  --name terrasacha-api \
  --network terrasacha-network \
  -p 8000:8000 \
  --env-file .env \
  -e POSTGRES_HOST=terrasacha-postgres \
  -e POSTGRES_USER=terrasacha \
  -e POSTGRES_PASSWORD=changeme \
  -e POSTGRES_DB=terrasacha_db \
  -e POSTGRES_PORT=5432 \
  terrasacha-api:latest
```

**Note**: The FastAPI container connects to PostgreSQL using the container name `terrasacha-postgres` as the hostname.

### Check FastAPI Status

```bash
# View logs
docker logs terrasacha-api

# Follow logs
docker logs -f terrasacha-api

# Check if running
docker ps | grep terrasacha-api
```

### Access the API

- API Documentation: http://localhost:8000/docs
- API Homepage: http://localhost:8000

---

## Docker Network

Both containers need to be on the same network to communicate. Create the network first:

```bash
# Create network (only needed once)
docker network create terrasacha-network

# List networks
docker network ls

# Inspect network
docker network inspect terrasacha-network
```

---

## Container Management

### Stop Containers

```bash
# Stop FastAPI
docker stop terrasacha-api

# Stop PostgreSQL
docker stop terrasacha-postgres
```

### Remove Containers

```bash
# Remove FastAPI
docker rm terrasacha-api

# Remove PostgreSQL
docker rm terrasacha-postgres
```

### Remove Everything (Clean Slate)

```bash
# Stop and remove all containers
docker stop terrasacha-api terrasacha-postgres
docker rm terrasacha-api terrasacha-postgres

# Remove network
docker network rm terrasacha-network

# Remove volume (WARNING: This deletes all database data)
docker volume rm terrasacha-contracts_postgres_data

# Remove images
docker rmi terrasacha-api:latest terrasacha-postgres:latest
```

---

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker logs terrasacha-api
docker logs terrasacha-postgres

# Check if ports are in use
lsof -i :8000
lsof -i :5432
```

### Database Connection Issues

1. Ensure PostgreSQL container is running:
   ```bash
   docker ps | grep terrasacha-postgres
   ```

2. Verify both containers are on the same network:
   ```bash
   docker network inspect terrasacha-network
   ```

3. Check environment variables in FastAPI container:
   ```bash
   docker exec terrasacha-api env | grep POSTGRES
   ```

### Reset Database

```bash
# Stop and remove PostgreSQL container
docker stop terrasacha-postgres
docker rm terrasacha-postgres

# Remove volume
docker volume rm terrasacha-postgres-data

# Start fresh
./run-postgres.sh
```

---

## AWS Copilot Deployment

For production deployment with AWS Copilot:

1. **Database**: Use AWS RDS instead of the local PostgreSQL container
2. **FastAPI**: Deploy using `Dockerfile` (not Dockerfile.postgres)
3. **Environment**: Configure production environment variables in AWS Copilot

```bash
# Initialize Copilot (if not already done)
copilot init

# Deploy to AWS
copilot deploy
```

The `Dockerfile` is already configured for production deployment with uvicorn.
