"""rename read to is_read

Revision ID: d4c789122916
Revises: 99c9bc980e1c
Create Date: 2026-11-08 19:27:28.821870

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4c789122916'
down_revision = '99c9bc980e1c'
branch_labels = None
depends_on = None


def upgrade():

    with op.batch_alter_table(
        'chat_messages',
        schema=None
    ) as batch_op:

        batch_op.alter_column(
            'read',
            new_column_name='is_read'
        )

    with op.batch_alter_table(
        'users',
        schema=None
    ) as batch_op:

        batch_op.alter_column(
            'first_purchase_used',
            existing_type=sa.BOOLEAN(),
            nullable=False,
            existing_server_default=sa.text('false')
        )

    # ### end Alembic commands ###


def downgrade():

    with op.batch_alter_table(
        'users',
        schema=None
    ) as batch_op:

        batch_op.alter_column(
            'first_purchase_used',
            existing_type=sa.BOOLEAN(),
            nullable=True,
            existing_server_default=sa.text('false')
        )

    with op.batch_alter_table(
        'chat_messages',
        schema=None
    ) as batch_op:

        batch_op.alter_column(
            'is_read',
            new_column_name='read'
        )

    # ### end Alembic commands ###
