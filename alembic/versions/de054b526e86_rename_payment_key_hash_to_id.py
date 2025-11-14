"""rename_payment_key_hash_to_id

Revision ID: de054b526e86
Revises: 15b3f199b90e
Create Date: 2025-11-13 20:05:02.172668

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'de054b526e86'
down_revision: Union[str, Sequence[str], None] = '15b3f199b90e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rename payment_key_hash to id in wallets table."""

    # Rename the primary key column in wallets table
    # The column still contains the payment key hash value, but is now called 'id'
    op.alter_column('wallets', 'payment_key_hash', new_column_name='id')


def downgrade() -> None:
    """Revert id back to payment_key_hash."""

    # Rename back to payment_key_hash
    op.alter_column('wallets', 'id', new_column_name='payment_key_hash')
