"""migrate_wallet_id_to_pkh

Revision ID: 15b3f199b90e
Revises: 2d78829cde30
Create Date: 2025-11-01 12:32:11.160029

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '15b3f199b90e'
down_revision: Union[str, Sequence[str], None] = '2d78829cde30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Migrate wallets table to use payment_key_hash as primary key instead of id.

    Steps:
    1. Create temporary columns in related tables for new PKH foreign keys
    2. Populate temporary columns by joining with wallets
    3. Drop old foreign key constraints
    4. Drop old wallet_id columns
    5. Rename temporary columns to wallet_id
    6. Drop old primary key from wallets and create new one
    7. Create new foreign key constraints
    """

    # Step 1: Add temporary columns in related tables
    op.add_column('wallet_sessions', sa.Column('wallet_id_new', sa.String(), nullable=True))
    op.add_column('protocols', sa.Column('wallet_id_new', sa.String(), nullable=True))
    op.add_column('transactions', sa.Column('wallet_id_new', sa.String(), nullable=True))

    # Step 2: Populate new columns by joining with wallets table
    op.execute("""
        UPDATE wallet_sessions ws
        SET wallet_id_new = w.payment_key_hash
        FROM wallets w
        WHERE ws.wallet_id = w.id
    """)

    op.execute("""
        UPDATE protocols p
        SET wallet_id_new = w.payment_key_hash
        FROM wallets w
        WHERE p.wallet_id = w.id
    """)

    op.execute("""
        UPDATE transactions t
        SET wallet_id_new = w.payment_key_hash
        FROM wallets w
        WHERE t.wallet_id = w.id
    """)

    # Step 3: Drop old foreign key constraints
    op.drop_constraint('wallet_sessions_wallet_id_fkey', 'wallet_sessions', type_='foreignkey')
    op.drop_constraint('protocols_wallet_id_fkey', 'protocols', type_='foreignkey')
    op.drop_constraint('transactions_wallet_id_fkey', 'transactions', type_='foreignkey')

    # Step 4: Drop old wallet_id columns
    op.drop_column('wallet_sessions', 'wallet_id')
    op.drop_column('protocols', 'wallet_id')
    op.drop_column('transactions', 'wallet_id')

    # Step 5: Rename temporary columns to wallet_id
    op.alter_column('wallet_sessions', 'wallet_id_new', new_column_name='wallet_id')
    op.alter_column('protocols', 'wallet_id_new', new_column_name='wallet_id')
    op.alter_column('transactions', 'wallet_id_new', new_column_name='wallet_id')

    # Step 6: Make columns non-nullable where appropriate
    op.alter_column('wallet_sessions', 'wallet_id', nullable=False)
    op.alter_column('protocols', 'wallet_id', nullable=False)
    # transactions.wallet_id stays nullable

    # Step 7: Drop old primary key and id column from wallets
    op.drop_constraint('wallets_pkey', 'wallets', type_='primary')
    op.drop_column('wallets', 'id')

    # Step 8: Create new primary key on payment_key_hash
    op.create_primary_key('wallets_pkey', 'wallets', ['payment_key_hash'])

    # Step 9: Create new foreign key constraints
    op.create_foreign_key(
        'wallet_sessions_wallet_id_fkey',
        'wallet_sessions', 'wallets',
        ['wallet_id'], ['payment_key_hash'],
        ondelete='CASCADE'
    )

    op.create_foreign_key(
        'protocols_wallet_id_fkey',
        'protocols', 'wallets',
        ['wallet_id'], ['payment_key_hash']
    )

    op.create_foreign_key(
        'transactions_wallet_id_fkey',
        'transactions', 'wallets',
        ['wallet_id'], ['payment_key_hash']
    )

    # Step 10: Create indexes
    op.create_index(op.f('ix_wallet_sessions_wallet_id'), 'wallet_sessions', ['wallet_id'])
    op.create_index(op.f('ix_wallets_payment_key_hash'), 'wallets', ['payment_key_hash'])


def downgrade() -> None:
    """
    Downgrade: Revert wallets table to use integer id as primary key.

    WARNING: This will reassign new IDs to wallets, breaking existing references!
    This is a destructive operation and should only be used in development.
    """

    # Step 1: Drop indexes
    op.drop_index(op.f('ix_wallets_payment_key_hash'), 'wallets')
    op.drop_index(op.f('ix_wallet_sessions_wallet_id'), 'wallet_sessions')

    # Step 2: Drop foreign key constraints
    op.drop_constraint('transactions_wallet_id_fkey', 'transactions', type_='foreignkey')
    op.drop_constraint('protocols_wallet_id_fkey', 'protocols', type_='foreignkey')
    op.drop_constraint('wallet_sessions_wallet_id_fkey', 'wallet_sessions', type_='foreignkey')

    # Step 3: Drop primary key from wallets
    op.drop_constraint('wallets_pkey', 'wallets', type_='primary')

    # Step 4: Add back id column with autoincrement
    op.add_column('wallets', sa.Column('id', sa.Integer(), autoincrement=True, nullable=False))

    # Step 5: Create primary key on id
    op.create_primary_key('wallets_pkey', 'wallets', ['id'])

    # Step 6: Add temporary integer columns in related tables
    op.add_column('wallet_sessions', sa.Column('wallet_id_new', sa.Integer(), nullable=True))
    op.add_column('protocols', sa.Column('wallet_id_new', sa.Integer(), nullable=True))
    op.add_column('transactions', sa.Column('wallet_id_new', sa.Integer(), nullable=True))

    # Step 7: Populate new columns by joining
    op.execute("""
        UPDATE wallet_sessions ws
        SET wallet_id_new = w.id
        FROM wallets w
        WHERE ws.wallet_id = w.payment_key_hash
    """)

    op.execute("""
        UPDATE protocols p
        SET wallet_id_new = w.id
        FROM wallets w
        WHERE p.wallet_id = w.payment_key_hash
    """)

    op.execute("""
        UPDATE transactions t
        SET wallet_id_new = w.id
        FROM wallets w
        WHERE t.wallet_id = w.payment_key_hash
    """)

    # Step 8: Drop old wallet_id columns
    op.drop_column('wallet_sessions', 'wallet_id')
    op.drop_column('protocols', 'wallet_id')
    op.drop_column('transactions', 'wallet_id')

    # Step 9: Rename temporary columns
    op.alter_column('wallet_sessions', 'wallet_id_new', new_column_name='wallet_id')
    op.alter_column('protocols', 'wallet_id_new', new_column_name='wallet_id')
    op.alter_column('transactions', 'wallet_id_new', new_column_name='wallet_id')

    # Step 10: Make columns non-nullable where appropriate
    op.alter_column('wallet_sessions', 'wallet_id', nullable=False)
    op.alter_column('protocols', 'wallet_id', nullable=False)

    # Step 11: Create foreign key constraints
    op.create_foreign_key(
        'wallet_sessions_wallet_id_fkey',
        'wallet_sessions', 'wallets',
        ['wallet_id'], ['id'],
        ondelete='CASCADE'
    )

    op.create_foreign_key(
        'protocols_wallet_id_fkey',
        'protocols', 'wallets',
        ['wallet_id'], ['id']
    )

    op.create_foreign_key(
        'transactions_wallet_id_fkey',
        'transactions', 'wallets',
        ['wallet_id'], ['id']
    )

    # Step 12: Create index
    op.create_index(op.f('ix_wallet_sessions_wallet_id'), 'wallet_sessions', ['wallet_id'])
