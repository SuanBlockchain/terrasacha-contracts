"""
Session Cleanup Service

Background service that automatically:
1. Syncs is_locked field with active session state
2. Cleans up expired sessions from in-memory storage
3. Maintains consistency between database and memory

This service runs periodically to ensure wallet lock state
stays synchronized with actual session state.
"""

from datetime import datetime, timezone
import logging

from api.database.models import WalletMongo, WalletSessionMongo
from api.services.session_manager import get_session_manager
from api.database.multi_tenant_manager import get_multi_tenant_db_manager

logger = logging.getLogger(__name__)


class SessionCleanupService:
    """
    Service for automatic session cleanup and synchronization.

    This service ensures that:
    - Wallets with no active sessions have is_locked=True
    - Expired sessions are removed from memory
    - Database state matches in-memory state
    """

    @staticmethod
    async def cleanup_expired_sessions(tenant_id: str) -> dict[str, int]:
        """
        Clean up expired sessions and synchronize wallet lock state for a specific tenant.

        This method:
        1. Initializes the tenant database
        2. Finds all wallets in the tenant's database
        3. Checks if each wallet has active sessions
        4. Sets is_locked=True if no active sessions exist
        5. Removes expired sessions from in-memory storage

        Args:
            tenant_id: The tenant identifier for multi-tenant database access

        Returns:
            Dictionary with cleanup statistics:
            - wallets_locked: Number of wallets that were locked
            - sessions_removed_from_memory: Number of sessions removed from memory
            - wallets_checked: Total number of wallets checked
        """
        try:
            # Initialize tenant database
            db_manager = get_multi_tenant_db_manager()
            await db_manager.get_tenant_database(tenant_id)

            session_manager = get_session_manager()
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            wallets_locked = 0
            sessions_removed_from_memory = 0
            wallets_checked = 0

            # Get all wallets for this tenant
            wallets = await WalletMongo.find_all().to_list()
            wallets_checked = len(wallets)

            for wallet in wallets:
                # Count active (non-revoked, non-expired) sessions for this wallet
                active_sessions_count = await WalletSessionMongo.find(
                    WalletSessionMongo.wallet_id == wallet.id,
                    WalletSessionMongo.revoked == False,
                    WalletSessionMongo.expires_at > now
                ).count()

                # If no active sessions and wallet is unlocked, lock it
                if active_sessions_count == 0 and not wallet.is_locked:
                    wallet.is_locked = True
                    wallet.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    await wallet.save()
                    wallets_locked += 1
                    logger.info(f"Auto-locked wallet {wallet.name} (id: {wallet.id}) - no active sessions")

            # Clean up expired sessions from in-memory storage
            # Get all sessions from database that are expired or revoked
            expired_or_revoked_sessions = await WalletSessionMongo.find(
                {
                    "$or": [
                        {"revoked": True},
                        {"expires_at": {"$lt": now}}
                    ]
                }
            ).to_list()

            for session in expired_or_revoked_sessions:
                # Remove from in-memory storage if present
                if session_manager.get_session(session.jti) is not None:
                    session_manager.remove_session(session.jti)
                    sessions_removed_from_memory += 1
                    logger.debug(f"Removed expired/revoked session {session.jti} from memory")

            logger.info(
                f"Session cleanup completed: {wallets_locked} wallets locked, "
                f"{sessions_removed_from_memory} sessions removed from memory, "
                f"{wallets_checked} wallets checked"
            )

            return {
                "wallets_locked": wallets_locked,
                "sessions_removed_from_memory": sessions_removed_from_memory,
                "wallets_checked": wallets_checked
            }

        except Exception as e:
            logger.error(f"Session cleanup failed: {str(e)}", exc_info=True)
            raise

    @staticmethod
    async def get_cleanup_stats(tenant_id: str) -> dict[str, int]:
        """
        Get statistics about sessions that need cleanup for a specific tenant.

        Args:
            tenant_id: The tenant identifier for multi-tenant database access

        Returns:
            Dictionary with statistics:
            - total_sessions: Total sessions in database
            - active_sessions: Non-revoked, non-expired sessions
            - expired_sessions: Expired but not revoked sessions
            - revoked_sessions: Explicitly revoked sessions
            - wallets_unlocked: Wallets with is_locked=False
            - wallets_with_active_sessions: Wallets that have active sessions
        """
        # Initialize tenant database
        db_manager = get_multi_tenant_db_manager()
        await db_manager.get_tenant_database(tenant_id)

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        total_sessions = await WalletSessionMongo.find_all().count()

        active_sessions = await WalletSessionMongo.find(
            WalletSessionMongo.revoked == False,
            WalletSessionMongo.expires_at > now
        ).count()

        expired_sessions = await WalletSessionMongo.find(
            WalletSessionMongo.revoked == False,
            WalletSessionMongo.expires_at <= now
        ).count()

        revoked_sessions = await WalletSessionMongo.find(
            WalletSessionMongo.revoked == True
        ).count()

        wallets_unlocked = await WalletMongo.find(
            WalletMongo.is_locked == False
        ).count()

        # Count wallets with at least one active session
        wallets_with_sessions = set()
        active_session_docs = await WalletSessionMongo.find(
            WalletSessionMongo.revoked == False,
            WalletSessionMongo.expires_at > now
        ).to_list()

        for session in active_session_docs:
            wallets_with_sessions.add(session.wallet_id)

        return {
            "total_sessions": total_sessions,
            "active_sessions": active_sessions,
            "expired_sessions": expired_sessions,
            "revoked_sessions": revoked_sessions,
            "wallets_unlocked": wallets_unlocked,
            "wallets_with_active_sessions": len(wallets_with_sessions)
        }


# Singleton instance
_cleanup_service = SessionCleanupService()


def get_cleanup_service() -> SessionCleanupService:
    """Get the singleton SessionCleanupService instance."""
    return _cleanup_service
