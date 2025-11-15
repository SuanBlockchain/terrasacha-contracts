"""make_tx_hash_nullable

Revision ID: 983801d57edd
Revises: 432bee626562
Create Date: 2025-11-15 10:19:39.902319

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '983801d57edd'
down_revision: Union[str, Sequence[str], None] = '432bee626562'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Make tx_hash nullable for two-stage transaction flow."""
    # In two-stage flow, tx_hash is only available after signing, not during build
    # So it needs to be nullable
    op.alter_column('transactions', 'tx_hash',
                    existing_type=sa.String(),
                    nullable=True)


def downgrade() -> None:
    """Downgrade schema - Make tx_hash NOT NULL again."""
    # Note: This will fail if there are any NULL values in the column
    # You would need to populate them first
    op.alter_column('transactions', 'tx_hash',
                    existing_type=sa.String(),
                    nullable=False)
