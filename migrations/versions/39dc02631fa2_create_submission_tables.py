"""create submission tables

Revision ID: 39dc02631fa2
Revises: 67f5c259c29b
Create Date: 2026-08-30 19:49:53.474003

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '39dc02631fa2'
down_revision: Union[str, Sequence[str], None] = '67f5c259c29b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add widget_field_id column to existing widget_field table and make it unique
    op.add_column(
        'widget_field',
        sa.Column('widget_field_id', sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()"))
    )
    op.create_unique_constraint('uq_widget_field_widget_field_id', 'widget_field', ['widget_field_id'])

    # 2. Create submission table
    op.create_table(
        'submission',
        sa.Column('submission_id', sa.UUID(), nullable=False),
        sa.Column('widget_id', sa.UUID(), nullable=False),
        sa.Column('idempotency_key', sa.String(length=255), nullable=False),
        sa.Column('country', sa.String(length=100), nullable=True),
        sa.Column('city', sa.String(length=100), nullable=True),
        sa.Column('region', sa.String(length=100), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        sa.Column('notification_status', sa.String(length=50), nullable=False),
        sa.Column('notification_attempts', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['widget_id'], ['widget.widget_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('submission_id'),
        sa.UniqueConstraint('widget_id', 'idempotency_key', name='uq_submission_widget_id_idempotency_key')
    )
    op.create_index('ix_submission_widget_id', 'submission', ['widget_id'], unique=False)
    op.create_index('ix_submission_widget_id_created_at', 'submission', ['widget_id', 'created_at'], unique=False)

    # 3. Create submission_field_value table
    op.create_table(
        'submission_field_value',
        sa.Column('submission_field_value_id', sa.UUID(), nullable=False),
        sa.Column('submission_id', sa.UUID(), nullable=False),
        sa.Column('widget_field_id', sa.UUID(), nullable=False),
        sa.Column('value_text', sa.Text(), nullable=True),
        sa.Column('value_number', sa.Float(), nullable=True),
        sa.Column('value_boolean', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['submission_id'], ['submission.submission_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['widget_field_id'], ['widget_field.widget_field_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('submission_field_value_id'),
        sa.UniqueConstraint('submission_id', 'widget_field_id', name='uq_submission_field_value_sub_wf')
    )
    op.create_index('ix_submission_field_value_submission_id', 'submission_field_value', ['submission_id'], unique=False)
    op.create_index('ix_submission_field_value_widget_field_id', 'submission_field_value', ['widget_field_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_submission_field_value_widget_field_id', table_name='submission_field_value')
    op.drop_index('ix_submission_field_value_submission_id', table_name='submission_field_value')
    op.drop_table('submission_field_value')

    op.drop_index('ix_submission_widget_id_created_at', table_name='submission')
    op.drop_index('ix_submission_widget_id', table_name='submission')
    op.drop_table('submission')

    op.drop_constraint('uq_widget_field_widget_field_id', 'widget_field', type_='unique')
    op.drop_column('widget_field', 'widget_field_id')