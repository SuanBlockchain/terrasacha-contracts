"""
Multi-Tenant Database Manager

Manages multiple MongoDB connections for database-per-tenant architecture.
Uses lazy initialization and connection pooling per tenant.
"""

from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from typing import Dict, Optional, Any
import asyncio
import os


class MultiTenantDatabaseManager:
    """Manages database connections per tenant with lazy initialization"""

    def __init__(self, admin_connection_string: str):
        """
        Initialize multi-tenant database manager

        Args:
            admin_connection_string: MongoDB URI for admin database
        """
        self.admin_connection_string = admin_connection_string
        self.client: Optional[AsyncIOMotorClient] = None
        self._tenant_clients: Dict[str, AsyncIOMotorClient] = {}
        self._tenant_databases: Dict[str, Any] = {}
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self):
        """Initialize admin database with Tenant and ApiKey models"""
        if self._initialized:
            return

        # Create shared client for all databases
        self.client = AsyncIOMotorClient(
            self.admin_connection_string,
            maxPoolSize=50,  # Total pool size across all tenants
            minPoolSize=5,
            maxIdleTimeMS=300000,  # 5 minutes
        )

        # Initialize admin database
        admin_db = self.client["terrasacha_admin"]

        from api.database.models import Tenant, ApiKey
        await init_beanie(
            database=admin_db,
            document_models=[Tenant, ApiKey]
        )

        self._initialized = True

    async def get_tenant_database(self, tenant_id: str):
        """
        Get or initialize database for specific tenant

        Args:
            tenant_id: Unique tenant identifier

        Returns:
            Initialized Beanie database for tenant

        Raises:
            ValueError: If tenant not found or inactive
        """
        from api.database.models import Tenant

        # Check cache first
        if tenant_id in self._tenant_databases:
            return self._tenant_databases[tenant_id]

        async with self._lock:
            # Double-check after acquiring lock
            if tenant_id in self._tenant_databases:
                return self._tenant_databases[tenant_id]

            # Validate tenant exists and is active
            tenant = await Tenant.find_one(Tenant.tenant_id == tenant_id)
            if not tenant:
                raise ValueError(f"Tenant not found: {tenant_id}")
            if not tenant.is_active:
                raise ValueError(f"Tenant inactive: {tenant_id}")
            if tenant.is_suspended:
                raise ValueError(f"Tenant suspended: {tenant_id}")

            # Get tenant's MongoDB connection string from environment
            connection_string_var = f"MONGODB_URI_{tenant_id.upper()}"
            connection_string = os.getenv(connection_string_var)

            if not connection_string:
                raise ValueError(
                    f"MongoDB connection string not found for tenant {tenant_id}. "
                    f"Expected environment variable: {connection_string_var}"
                )

            # Create tenant-specific client or use shared client
            # Using shared client for better resource utilization
            tenant_db = self.client[tenant.database_name]

            # Initialize Beanie for tenant database with MongoDB models
            try:
                from api.database.models import WalletMongo, WalletSessionMongo, TransactionMongo

                # Initialize with available Beanie models
                await init_beanie(
                    database=tenant_db,
                    document_models=[WalletMongo, WalletSessionMongo, TransactionMongo]
                )
            except ImportError:
                # Models not yet migrated to Beanie
                await init_beanie(
                    database=tenant_db,
                    document_models=[]
                )

            # Cache the initialized database
            self._tenant_databases[tenant_id] = tenant_db

        return self._tenant_databases[tenant_id]

    async def close(self):
        """Close all database connections"""
        if self.client:
            self.client.close()

        for client in self._tenant_clients.values():
            client.close()


# Global instance
_multi_tenant_db_manager: Optional[MultiTenantDatabaseManager] = None


def get_multi_tenant_db_manager() -> MultiTenantDatabaseManager:
    """Get global multi-tenant database manager instance"""
    global _multi_tenant_db_manager
    if _multi_tenant_db_manager is None:
        admin_uri = os.getenv("MONGODB_ADMIN_URI")
        if not admin_uri:
            raise ValueError("MONGODB_ADMIN_URI environment variable not set")
        _multi_tenant_db_manager = MultiTenantDatabaseManager(admin_uri)
    return _multi_tenant_db_manager
