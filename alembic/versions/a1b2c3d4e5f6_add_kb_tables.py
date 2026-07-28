"""Add knowledge base tables: kb_labels and children

Adds the label knowledge base to the same database as the customer data,
in its own set of tables. Purely additive — the six customer tables from
revision fe08a3da6d37 are untouched.

Revision ID: a1b2c3d4e5f6
Revises: fe08a3da6d37
Create Date: 2026-07-27 23:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'fe08a3da6d37'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'kb_labels',
        sa.Column('label_id', sa.String(length=100), nullable=False),
        sa.Column('display_name', sa.String(length=255), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('severity', sa.String(length=50), nullable=False),
        sa.Column('priority_rank', sa.Integer(), nullable=False),
        sa.Column('fact_id', sa.String(length=100), nullable=False),
        sa.Column('condition', sa.Text(), nullable=False),
        sa.Column('condition_human', sa.Text(), nullable=False),
        sa.Column('what_it_means_cibil', sa.Text(), nullable=False),
        sa.Column('why_it_matters', sa.Text(), nullable=False),
        sa.Column('personalized_response_template', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('label_id'),
    )
    op.create_index(op.f('ix_kb_labels_category'), 'kb_labels', ['category'], unique=False)
    op.create_index(op.f('ix_kb_labels_severity'), 'kb_labels', ['severity'], unique=False)
    op.create_index(op.f('ix_kb_labels_priority_rank'), 'kb_labels', ['priority_rank'], unique=False)

    op.create_table(
        'kb_mitigation_steps',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('label_id', sa.String(length=100), nullable=False),
        sa.Column('step_order', sa.Integer(), nullable=False),
        sa.Column('step_text', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['label_id'], ['kb_labels.label_id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_kb_mitigation_steps_label_id'), 'kb_mitigation_steps', ['label_id'], unique=False
    )

    op.create_table(
        'kb_facts_to_cite',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('label_id', sa.String(length=100), nullable=False),
        sa.Column('fact_name', sa.String(length=100), nullable=False),
        sa.ForeignKeyConstraint(['label_id'], ['kb_labels.label_id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_kb_facts_to_cite_label_id'), 'kb_facts_to_cite', ['label_id'], unique=False
    )

    op.create_table(
        'kb_reason_codes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('label_id', sa.String(length=100), nullable=False),
        sa.Column('reason_code', sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(['label_id'], ['kb_labels.label_id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_kb_reason_codes_label_id'), 'kb_reason_codes', ['label_id'], unique=False
    )

    op.create_table(
        'kb_sources',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('label_id', sa.String(length=100), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('url', sa.String(length=1000), nullable=False),
        sa.ForeignKeyConstraint(['label_id'], ['kb_labels.label_id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_kb_sources_label_id'), 'kb_sources', ['label_id'], unique=False)

    op.create_table(
        'kb_meta',
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.Column('value', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('key'),
    )


def downgrade() -> None:
    op.drop_table('kb_meta')
    op.drop_index(op.f('ix_kb_sources_label_id'), table_name='kb_sources')
    op.drop_table('kb_sources')
    op.drop_index(op.f('ix_kb_reason_codes_label_id'), table_name='kb_reason_codes')
    op.drop_table('kb_reason_codes')
    op.drop_index(op.f('ix_kb_facts_to_cite_label_id'), table_name='kb_facts_to_cite')
    op.drop_table('kb_facts_to_cite')
    op.drop_index(op.f('ix_kb_mitigation_steps_label_id'), table_name='kb_mitigation_steps')
    op.drop_table('kb_mitigation_steps')
    op.drop_index(op.f('ix_kb_labels_priority_rank'), table_name='kb_labels')
    op.drop_index(op.f('ix_kb_labels_severity'), table_name='kb_labels')
    op.drop_index(op.f('ix_kb_labels_category'), table_name='kb_labels')
    op.drop_table('kb_labels')
