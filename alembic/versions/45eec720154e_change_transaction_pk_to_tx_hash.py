"""change_transaction_pk_to_tx_hash

Revision ID: 45eec720154e
Revises: 983801d57edd
Create Date: 2025-11-15 11:28:48.884631

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '45eec720154e'
down_revision: Union[str, Sequence[str], None] = '983801d57edd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Change primary key from id to tx_hash."""
    # Step 0: Delete any transactions with NULL tx_hash (incomplete/invalid transactions)
    op.execute("DELETE FROM transactions WHERE tx_hash IS NULL")

    # Step 1: Make tx_hash NOT NULL (all transactions should have tx_hash from build stage)
    op.alter_column('transactions', 'tx_hash',
                    existing_type=sa.String(),
                    nullable=False)

    # Step 2: Drop the unique index on tx_hash (will be replaced by primary key)
    op.drop_index('ix_transactions_tx_hash', table_name='transactions')

    # Step 3: Drop the primary key constraint on id
    op.execute('ALTER TABLE transactions DROP CONSTRAINT transactions_pkey')

    # Step 4: Add primary key constraint on tx_hash
    op.create_primary_key('transactions_pkey', 'transactions', ['tx_hash'])

    # Step 5: Drop the id column (no longer needed)
    op.drop_column('transactions', 'id')


def downgrade() -> None:
    """Downgrade schema - Restore id as primary key."""
    # WARNING: This downgrade will lose the original id values
    # Only use in development/testing

    # Step 1: Add id column back as serial (auto-increment)
    op.add_column('transactions', sa.Column('id', sa.Integer(), autoincrement=True))

    # Step 2: Populate id column with sequential values
    op.execute('CREATE SEQUENCE transactions_id_seq')
    op.execute("SELECT setval('transactions_id_seq', (SELECT COUNT(*) FROM transactions))")
    op.execute("UPDATE transactions SET id = nextval('transactions_id_seq')")

    # Step 3: Drop primary key on tx_hash
    op.execute('ALTER TABLE transactions DROP CONSTRAINT transactions_pkey')

    # Step 4: Make id the primary key
    op.create_primary_key('transactions_pkey', 'transactions', ['id'])

    # Step 5: Make tx_hash nullable and add unique index
    op.alter_column('transactions', 'tx_hash',
                    existing_type=sa.String(),
                    nullable=True)
    op.create_index('ix_transactions_tx_hash', 'transactions', ['tx_hash'], unique=True)
