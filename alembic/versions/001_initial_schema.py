"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-05-20

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "admin_users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_admin_users_username", "admin_users", ["username"], unique=True)

    op.create_table(
        "form_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.String(36), nullable=False),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("property_address", sa.Text(), nullable=False),
        sa.Column("guest_label", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("single_use", sa.Boolean(), default=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_form_links_public_id", "form_links", ["public_id"], unique=True)
    op.create_index("ix_form_links_token", "form_links", ["token"], unique=True)

    op.create_table(
        "submissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.String(36), nullable=False),
        sa.Column("form_link_id", sa.Integer(), sa.ForeignKey("form_links.id"), unique=True),
        sa.Column("last_name", sa.String(128), nullable=False),
        sa.Column("first_name", sa.String(128), nullable=False),
        sa.Column("gender", sa.String(32), nullable=False),
        sa.Column("nationality", sa.String(128), nullable=False),
        sa.Column("date_of_birth", sa.String(16), nullable=False),
        sa.Column("country_of_residence", sa.String(128), nullable=False),
        sa.Column("children_under_18", sa.Integer(), default=0),
        sa.Column("arrival_date", sa.String(16), nullable=False),
        sa.Column("departure_date", sa.String(16), nullable=False),
        sa.Column("id_document_type", sa.String(64), nullable=False),
        sa.Column("id_document_number", sa.String(128), nullable=False),
        sa.Column("certify_accurate", sa.Boolean(), default=False),
        sa.Column("accept_internal_rules", sa.Boolean(), default=False),
        sa.Column("accept_terms", sa.Boolean(), default=False),
        sa.Column("signature_path", sa.String(512), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_submissions_public_id", "submissions", ["public_id"], unique=True)

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.String(36), nullable=False),
        sa.Column("submission_id", sa.Integer(), sa.ForeignKey("submissions.id"), unique=True),
        sa.Column("pdf_path", sa.String(512), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_documents_public_id", "documents", ["public_id"], unique=True)


def downgrade() -> None:
    op.drop_table("documents")
    op.drop_table("submissions")
    op.drop_table("form_links")
    op.drop_table("admin_users")
