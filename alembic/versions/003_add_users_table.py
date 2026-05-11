"""add users table for admin space

Revision ID: 003
Revises: 002
Create Date: 2026-05-11
"""

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            name          TEXT NOT NULL,
            email         TEXT NOT NULL UNIQUE,
            role          TEXT NOT NULL DEFAULT 'readonly' CHECK (role IN ('admin', 'agent', 'readonly')),
            is_active     BOOLEAN NOT NULL DEFAULT TRUE,
            google_sub    TEXT UNIQUE,
            created_at    TIMESTAMPTZ DEFAULT now(),
            updated_at    TIMESTAMPTZ DEFAULT now(),
            last_login_at TIMESTAMPTZ
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users (lower(email))")
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_role_active ON users (role, is_active)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS users CASCADE")
