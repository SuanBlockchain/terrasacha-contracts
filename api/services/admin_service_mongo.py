"""
Admin Service - MongoDB/Beanie Version

Centralized business logic for administrative session management operations.
Handles session queries, cleanup, and management across all tenants.

Performance Optimizations:
- Uses bulk update_many() instead of N+1 individual save() operations
- Uses bulk delete_many() for purging old sessions
- Leverages MongoDB compound indexes for efficient queries
"""

from datetime import datetime, timezone, timedelta

from beanie.operators import Set

from api.database.models import WalletSessionMongo, WalletMongo
from api.services.session_manager import get_session_manager


class AdminSessionService:
    """Service for admin session management operations"""

    async def list_all_sessions(self, skip: int = 0, limit: int = 100):
        """
        Get all sessions with wallet information.

        Args:
            skip: Number of records to skip (pagination)
            limit: Maximum number of records to return

        Returns:
            List of tuples: (WalletSessionMongo, wallet_name, in_memory)
        """
        # Get all sessions sorted by creation date (newest first)
        sessions = await WalletSessionMongo.find_all()\
            .sort(-WalletSessionMongo.created_at)\
            .skip(skip)\
            .limit(limit)\
            .to_list()

        # For each session, get wallet name and check memory
        session_manager = get_session_manager()
        results = []

        for session_doc in sessions:
            # Get wallet to fetch name
            wallet = await WalletMongo.get(session_doc.wallet_id)
            wallet_name = wallet.name if wallet else None

            # Check if session is in memory
            in_memory = session_manager.session_exists(session_doc.jti)

            results.append((session_doc, wallet_name, in_memory))

        return results

    async def count_sessions(self):
        """
        Get session counts (total, active, expired, in-memory).

        Returns:
            dict with session counts:
            - total: Total sessions in database
            - active: Non-revoked sessions
            - expired: Expired but not yet revoked
            - in_memory: Sessions currently in memory
        """
        # Total sessions
        total_count = await WalletSessionMongo.count()

        # Active (non-revoked) sessions
        active_count = await WalletSessionMongo.find(
            WalletSessionMongo.revoked == False
        ).count()

        # Expired but not revoked
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        expired_count = await WalletSessionMongo.find(
            WalletSessionMongo.expires_at < now,
            WalletSessionMongo.revoked == False
        ).count()

        # In-memory count
        session_manager = get_session_manager()
        in_memory_count = session_manager.get_session_count()

        return {
            "total": total_count,
            "active": active_count,
            "expired": expired_count,
            "in_memory": in_memory_count
        }

    async def cleanup_expired_sessions(self):
        """
        Cleanup expired sessions from memory and mark as revoked in DB.

        NOTE: With TTL index enabled, MongoDB automatically deletes expired
        sessions within 60 seconds. This method provides manual cleanup for
        immediate consistency between memory and database.

        Performance: Uses bulk update_many() instead of N+1 individual saves.

        Returns:
            dict with cleanup counts:
            - memory_cleaned: Sessions removed from memory
            - db_cleaned: Sessions marked as revoked in database
        """
        # Cleanup memory first
        session_manager = get_session_manager()
        memory_cleaned = session_manager.cleanup_expired()

        # Mark expired sessions as revoked in MongoDB using bulk operation
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Use bulk update instead of N+1 pattern
        result = await WalletSessionMongo.find(
            WalletSessionMongo.expires_at < now,
            WalletSessionMongo.revoked == False
        ).update_many(Set({
            WalletSessionMongo.revoked: True,
            WalletSessionMongo.revoked_at: now
        }))

        db_cleaned = result.modified_count if result else 0

        return {
            "memory_cleaned": memory_cleaned,
            "db_cleaned": db_cleaned
        }

    async def purge_old_revoked_sessions(self, retention_days: int = 30):
        """
        Permanently delete old revoked sessions from database.

        This is different from cleanup - it DELETES revoked sessions after
        a retention period, rather than just marking them as revoked.

        NOTE: With TTL index, expired sessions are auto-deleted. This method
        handles purging REVOKED sessions that haven't expired yet but are
        older than the retention period.

        Performance: Uses bulk delete_many() instead of N+1 individual deletes.

        Best practices:
        - Keep revoked sessions for audit trail (30-90 days)
        - Then permanently delete to prevent database bloat
        - Run this periodically (e.g., daily or weekly)

        Args:
            retention_days: How many days to keep revoked sessions before deletion
                           Default: 30 days

        Returns:
            dict with:
            - purged_count: Number of sessions permanently deleted
            - cutoff_date: Sessions revoked before this date were deleted
            - retention_days: Retention period used
        """
        # Calculate cutoff date
        cutoff_date = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=retention_days)

        # Use bulk delete instead of N+1 pattern
        result = await WalletSessionMongo.find(
            WalletSessionMongo.revoked == True,  # noqa: E712
            WalletSessionMongo.revoked_at < cutoff_date
        ).delete_many()

        purged_count = result.deleted_count if result else 0

        return {
            "purged_count": purged_count,
            "cutoff_date": cutoff_date,
            "retention_days": retention_days
        }

    async def revoke_session_by_jti(self, jti: str) -> bool:
        """
        Force revoke a specific session by JTI.

        Args:
            jti: JWT ID of session to revoke

        Returns:
            True if session was found and revoked, False if not found
        """
        # Find session by JTI
        session_doc = await WalletSessionMongo.find_one(
            WalletSessionMongo.jti == jti
        )

        if not session_doc:
            return False

        # Mark as revoked in MongoDB
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        session_doc.revoked = True
        session_doc.revoked_at = now
        await session_doc.save()

        # Remove from memory
        session_manager = get_session_manager()
        session_manager.remove_session(jti)

        return True

    async def clear_all_sessions(self):
        """
        Emergency: Clear ALL sessions (memory + DB).

        WARNING: This logs out ALL users immediately. Use only in emergencies.

        Performance: Uses bulk update_many() instead of N+1 individual saves.

        Returns:
            dict with cleared counts:
            - memory_cleared: Sessions removed from memory
            - db_revoked: Sessions marked as revoked in database
        """
        # Mark all non-revoked sessions as revoked using bulk operation
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Use bulk update instead of N+1 pattern
        result = await WalletSessionMongo.find(
            WalletSessionMongo.revoked == False
        ).update_many(Set({
            WalletSessionMongo.revoked: True,
            WalletSessionMongo.revoked_at: now
        }))

        db_revoked = result.modified_count if result else 0

        # Clear all from memory
        session_manager = get_session_manager()
        memory_cleared = session_manager.clear_all()

        return {
            "memory_cleared": memory_cleared,
            "db_revoked": db_revoked
        }
