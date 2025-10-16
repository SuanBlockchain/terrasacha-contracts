# Database Layer

This directory contains the database layer for the Terrasacha Contracts project, built with SQLModel, PostgreSQL, and Alembic for migrations.

## Structure

```
src/database/
├── __init__.py
├── models.py           # SQLModel database models
├── connection.py       # Database connection management
├── repositories/       # Data access layer
│   ├── __init__.py
│   ├── base.py        # Base repository with CRUD operations
│   ├── wallet.py      # Wallet repository
│   ├── contract.py    # Contract repository
│   ├── protocol.py    # Protocol repository
│   ├── project.py     # Project repository
│   └── transaction.py # Transaction repository
└── README.md
```

## Database Models

### Core Models
- **Wallet**: Stores wallet information with encrypted mnemonics
- **Contract**: Generic contract registry for compiled contracts
- **Protocol**: Protocol contract instances with on-chain state
- **Project**: Carbon credit project contracts
- **Transaction**: Transaction history tracking
- **UTXO**: UTXO tracking for contracts and compilation
- **Token**: NFT and token tracking (protocol, project, grey tokens)
- **Stakeholder**: Project stakeholder participation
- **Certification**: Carbon credit certifications
- **InvestorSale**: Grey token sales through investor contracts

## Setup

### 1. Start PostgreSQL

Using Docker Compose:
```bash
docker compose up -d db
```

### 2. Configuration

Database settings are loaded from `src/cardano_offchain/menu/.env`:

```env
POSTGRES_USER=terrasacha
POSTGRES_PASSWORD=terrasacha
POSTGRES_DB=terrasacha_db
POSTGRES_PORT=5432
```

### 3. Run Migrations

```bash
# Create a new migration after model changes
uv run alembic revision --autogenerate -m "Description of changes"

# Apply migrations
uv run alembic upgrade head

# Rollback one migration
uv run alembic downgrade -1

# Check current migration version
uv run alembic current

# View migration history
uv run alembic history
```

## Usage

### Using the Database Manager

```python
from api.database.connection import DatabaseManager

# Initialize database manager
db_manager = DatabaseManager()

# Get async session
async with db_manager.get_session() as session:
    # Use session here
    pass
```

### Using Repositories

```python
from api.database.connection import get_db_manager
from api.database.repositories import WalletRepository, ContractRepository
from api.database.models import Wallet, NetworkType

# Get database manager
db_manager = get_db_manager()

# Use repository
async with db_manager.get_session() as session:
    wallet_repo = WalletRepository(session)

    # Create a wallet
    wallet = Wallet(
        name="admin",
        network=NetworkType.TESTNET,
        mnemonic_encrypted="...",
        enterprise_address="addr_test...",
        staking_address="addr_test...",
        payment_key_hash="...",
        is_default=True
    )
    created_wallet = await wallet_repo.create(wallet)

    # Get wallet by name
    wallet = await wallet_repo.get_by_name("admin")

    # Get default wallet
    default_wallet = await wallet_repo.get_default()

    # List all wallets
    wallets = await wallet_repo.get_all(skip=0, limit=100)
```

### With FastAPI

```python
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from api.database.connection import get_session
from api.database.repositories import WalletRepository

@app.get("/wallets")
async def list_wallets(session: AsyncSession = Depends(get_session)):
    wallet_repo = WalletRepository(session)
    wallets = await wallet_repo.get_all()
    return wallets
```

## Repository Pattern

All repositories inherit from `BaseRepository` which provides:

- `create(obj)` - Create a new record
- `get(id)` - Get record by ID
- `get_all(skip, limit)` - Get all records with pagination
- `update(id, **kwargs)` - Update record
- `delete(id)` - Delete record
- `count()` - Count total records

Specific repositories add domain-specific methods:

**WalletRepository**:
- `get_by_name(name)` - Get wallet by name
- `get_by_address(address)` - Get wallet by address
- `get_default()` - Get default wallet
- `set_default(wallet_id)` - Set wallet as default
- `get_by_network(network)` - Get wallets by network

**ContractRepository**:
- `get_by_policy_id(policy_id)` - Get contract by policy ID
- `get_by_name(name)` - Get contract by name
- `get_by_type(contract_type, network)` - Get contracts by type

**ProtocolRepository**:
- `get_by_nft_policy(policy_id)` - Get protocol by NFT policy
- `get_active()` - Get active protocols
- `get_by_wallet(wallet_id)` - Get protocols by wallet

**ProjectRepository**:
- `get_by_name(name)` - Get project by name
- `get_by_project_id(project_id)` - Get by on-chain ID
- `get_by_protocol(protocol_id)` - Get projects by protocol
- `get_by_state(state)` - Get projects by state
- `get_active()` - Get active projects

**TransactionRepository**:
- `get_by_tx_id(tx_id)` - Get transaction by ID
- `get_by_wallet(wallet_id, limit)` - Get wallet transactions
- `get_by_status(status)` - Get transactions by status
- `get_pending()` - Get pending transactions
- `get_recent(limit)` - Get recent transactions

## Database Schema Highlights

### Relationships
- Wallets → Protocols (one-to-many)
- Wallets → Transactions (one-to-many)
- Contracts → Protocols (one-to-many)
- Contracts → Projects (one-to-many)
- Protocols → Projects (one-to-many)
- Projects → Stakeholders (one-to-many)
- Projects → Certifications (one-to-many)
- Projects → Tokens (one-to-many)
- Projects → InvestorSales (one-to-many)

### Indexes
- All primary relationships have foreign key indexes
- Unique constraints on policy IDs, wallet names, transaction IDs
- Performance indexes on frequently queried fields (addresses, policy IDs, statuses)

## Migration Best Practices

1. **Always review auto-generated migrations** before applying them
2. **Test migrations on development database** before production
3. **Create descriptive migration messages** explaining what changed
4. **Never edit applied migrations** - create new ones instead
5. **Keep models and migrations in sync** - run `alembic revision --autogenerate` after model changes

## Troubleshooting

### Connection Issues
```bash
# Check if PostgreSQL is running
docker ps | grep terrasacha-postgres

# View PostgreSQL logs
docker logs terrasacha-postgres

# Connect to PostgreSQL directly
docker exec -it terrasacha-postgres psql -U terrasacha -d terrasacha_db
```

### Migration Issues
```bash
# View current migration state
uv run alembic current

# View migration history
uv run alembic history --verbose

# Rollback to specific version
uv run alembic downgrade <revision>

# Mark migration as applied without running it
uv run alembic stamp <revision>
```

### Database Inspection
```sql
-- List all tables
\dt

-- Describe table structure
\d table_name

-- View indexes
\di

-- Check alembic version
SELECT * FROM alembic_version;
```
