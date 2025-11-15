"""add_built_and_signed_transaction_status

Revision ID: 432bee626562
Revises: f17d6a2fa8b5
Create Date: 2025-11-15 10:06:59.979633

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '432bee626562'
down_revision: Union[str, Sequence[str], None] = 'f17d6a2fa8b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Add BUILT and SIGNED enum values to TransactionStatus."""
    # Add new enum values to transactionstatus enum type
    # Note: PostgreSQL enum values cannot be removed, so downgrade will require recreating the enum
    # Values must be UPPERCASE to match existing enum values
    op.execute("ALTER TYPE transactionstatus ADD VALUE IF NOT EXISTS 'BUILT' BEFORE 'PENDING'")
    op.execute("ALTER TYPE transactionstatus ADD VALUE IF NOT EXISTS 'SIGNED' AFTER 'BUILT'")


def downgrade() -> None:
    """Downgrade schema - Cannot remove enum values in PostgreSQL."""
    # PostgreSQL does not support removing enum values
    # To downgrade, you would need to:
    # 1. Create a new enum type without 'built' and 'signed'
    # 2. Alter the column to use the new type
    # 3. Drop the old type
    # This is complex and risky, so we'll pass here
    # If needed, handle this manually in production
    pass
