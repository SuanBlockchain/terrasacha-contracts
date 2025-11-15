"""add_two_stage_transaction_fields

Revision ID: f17d6a2fa8b5
Revises: de054b526e86
Create Date: 2025-11-15 10:02:13.544708

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'f17d6a2fa8b5'
down_revision: Union[str, Sequence[str], None] = 'de054b526e86'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Add two-stage transaction flow fields."""
    # Add new columns for two-stage transaction flow
    op.add_column('transactions', sa.Column('unsigned_cbor', sa.String(), nullable=True))
    op.add_column('transactions', sa.Column('signed_cbor', sa.String(), nullable=True))
    op.add_column('transactions', sa.Column('from_address_index', sa.Integer(), nullable=True))
    op.add_column('transactions', sa.Column('from_address', sa.String(), nullable=True))
    op.add_column('transactions', sa.Column('to_address', sa.String(), nullable=True))
    op.add_column('transactions', sa.Column('amount_lovelace', sa.Integer(), nullable=True))
    op.add_column('transactions', sa.Column('estimated_fee', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema - Remove two-stage transaction flow fields."""
    # Remove columns added for two-stage transaction flow
    op.drop_column('transactions', 'estimated_fee')
    op.drop_column('transactions', 'amount_lovelace')
    op.drop_column('transactions', 'to_address')
    op.drop_column('transactions', 'from_address')
    op.drop_column('transactions', 'from_address_index')
    op.drop_column('transactions', 'signed_cbor')
    op.drop_column('transactions', 'unsigned_cbor')
