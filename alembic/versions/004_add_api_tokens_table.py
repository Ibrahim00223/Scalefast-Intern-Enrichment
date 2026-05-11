"""add api tokens table

Revision ID: 004
Revises: 003
Create Date: 2026-05-11
"""

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS api_tokens (
            id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name         TEXT NOT NULL,
            token_prefix TEXT NOT NULL,
            token_hash   TEXT NOT NULL UNIQUE,
            is_active    BOOLEAN NOT NULL DEFAULT TRUE,
            created_at   TIMESTAMPTZ DEFAULT now(),
            updated_at   TIMESTAMPTZ DEFAULT now(),
            expires_at   TIMESTAMPTZ,
            last_used_at TIMESTAMPTZ,
            revoked_at   TIMESTAMPTZ
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_api_tokens_user_id ON api_tokens (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_api_tokens_hash ON api_tokens (token_hash)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS api_tokens CASCADE")
