"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-05-03
"""

revision = "001"
down_revision = None
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    op.execute("""
        CREATE TABLE contacts (
            id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            nom                 TEXT NOT NULL,
            prenom              TEXT NOT NULL,
            nom_normalized      TEXT GENERATED ALWAYS AS (lower(trim(nom))) STORED,
            prenom_normalized   TEXT GENERATED ALWAYS AS (lower(trim(prenom))) STORED,
            linkedin_url        TEXT UNIQUE,
            email               TEXT,
            phone               VARCHAR(50),
            company             TEXT,
            job_title           TEXT,
            source              VARCHAR(100),
            created_at          TIMESTAMPTZ DEFAULT now(),
            updated_at          TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("""
        CREATE INDEX idx_contacts_nom_trgm
            ON contacts USING GIN (nom_normalized gin_trgm_ops)
    """)
    op.execute("""
        CREATE INDEX idx_contacts_prenom_trgm
            ON contacts USING GIN (prenom_normalized gin_trgm_ops)
    """)
    op.execute("""
        CREATE INDEX idx_contacts_linkedin
            ON contacts (linkedin_url)
            WHERE linkedin_url IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS contacts")
