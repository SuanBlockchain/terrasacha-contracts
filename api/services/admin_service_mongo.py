"""
Admin Service - MongoDB/Beanie Version

Centralized business logic for administrative session management operations.
Handles session queries, cleanup, and management across all tenants.
"""

from datetime import datetime, timezone, timedelta

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

        Returns:
            dict with cleanup counts:
            - memory_cleaned: Sessions removed from memory
            - db_cleaned: Sessions marked as revoked in database
        """
        # Cleanup memory first
        session_manager = get_session_manager()
        memory_cleaned = session_manager.cleanup_expired()

        # Mark expired sessions as revoked in MongoDB
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Find all expired, non-revoked sessions
        expired_sessions = await WalletSessionMongo.find(
            WalletSessionMongo.expires_at < now,
            WalletSessionMongo.revoked == False
        ).to_list()

        # Update each one
        db_cleaned = 0
        for session_doc in expired_sessions:
            session_doc.revoked = True
            session_doc.revoked_at = now
            await session_doc.save()
            db_cleaned += 1

        return {
            "memory_cleaned": memory_cleaned,
            "db_cleaned": db_cleaned
        }

    async def purge_old_revoked_sessions(self, retention_days: int = 30):
        """
        Permanently delete old revoked sessions from database.

        This is different from cleanup - it DELETES revoked sessions after
        a retention period, rather than just marking them as revoked.

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
        """
        # Calculate cutoff date
        cutoff_date = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=retention_days)

        # Find old revoked sessions
        old_revoked_sessions = await WalletSessionMongo.find(
            WalletSessionMongo.revoked == True,  # noqa: E712
            WalletSessionMongo.revoked_at < cutoff_date
        ).to_list()

        # Delete them permanently
        purged_count = 0
        for session_doc in old_revoked_sessions:
            await session_doc.delete()
            purged_count += 1

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

        Returns:
            dict with cleared counts:
            - memory_cleared: Sessions removed from memory
            - db_revoked: Sessions marked as revoked in database
        """
        # Get all non-revoked sessions
        active_sessions = await WalletSessionMongo.find(
            WalletSessionMongo.revoked == False
        ).to_list()

        # Mark all as revoked
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        db_revoked = 0
        for session_doc in active_sessions:
            session_doc.revoked = True
            session_doc.revoked_at = now
            await session_doc.save()
            db_revoked += 1

        # Clear all from memory
        session_manager = get_session_manager()
        memory_cleared = session_manager.clear_all()

        return {
            "memory_cleared": memory_cleared,
            "db_revoked": db_revoked
        }
