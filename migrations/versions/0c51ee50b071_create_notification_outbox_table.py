"""create notification outbox table

Revision ID: 0c51ee50b071
Revises: 39dc02631fa2
Create Date: 2026-08-30 20:04:05.179365

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0c51ee50b071'
down_revision: Union[str, Sequence[str], None] = '39dc02631fa2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create notification_outbox table
    op.create_table(
        'notification_outbox',
        sa.Column('outbox_id', sa.UUID(), nullable=False),
        sa.Column('submission_id', sa.UUID(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('available_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['submission_id'], ['submission.submission_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('outbox_id'),
        sa.UniqueConstraint('submission_id', name='uq_notification_outbox_submission_id')
    )
    op.create_index('ix_notification_outbox_submission_id', 'notification_outbox', ['submission_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_notification_outbox_submission_id', table_name='notification_outbox')
    op.drop_table('notification_outbox')