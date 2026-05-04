"""new schema: companies, leads, interactions

Revision ID: 002
Revises: 001
Create Date: 2026-05-03
"""

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    # Drop old contacts table
    op.execute("DROP TABLE IF EXISTS contacts CASCADE")

    # ── Companies ────────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            company_name        TEXT NOT NULL,
            linkedin_url        TEXT UNIQUE,
            linkedin_id         TEXT,
            location            TEXT,
            industry            TEXT,
            number_of_employees INTEGER,
            created_at          TIMESTAMPTZ DEFAULT now(),
            updated_at          TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("CREATE INDEX IF NOT EXISTS idx_companies_name ON companies USING GIN (lower(company_name) gin_trgm_ops)")

    # ── Leads ─────────────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            last_name               TEXT NOT NULL,
            first_name              TEXT NOT NULL,
            full_name               TEXT GENERATED ALWAYS AS (trim(first_name || ' ' || last_name)) STORED,
            last_name_normalized    TEXT GENERATED ALWAYS AS (lower(trim(last_name))) STORED,
            first_name_normalized   TEXT GENERATED ALWAYS AS (lower(trim(first_name))) STORED,
            company_id              UUID REFERENCES companies(id) ON DELETE SET NULL,
            company_name            TEXT,
            job_title               TEXT,
            location                TEXT,
            linkedin_id             TEXT,
            linkedin_url            TEXT UNIQUE,
            created_at              TIMESTAMPTZ DEFAULT now(),
            updated_at              TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("CREATE INDEX IF NOT EXISTS idx_leads_last_name_trgm  ON leads USING GIN (last_name_normalized gin_trgm_ops)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_leads_first_name_trgm ON leads USING GIN (first_name_normalized gin_trgm_ops)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_leads_linkedin        ON leads (linkedin_url) WHERE linkedin_url IS NOT NULL")
    op.execute("CREATE INDEX IF NOT EXISTS idx_leads_company_id      ON leads (company_id) WHERE company_id IS NOT NULL")

    # ── Interactions ──────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS interactions (
            id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            lead_id     UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
            type        TEXT NOT NULL CHECK (type IN ('appel', 'mail')),
            status      TEXT NOT NULL CHECK (status IN (
                            'NRP 1', 'NRP 2', 'NRP 3', 'NRP 4',
                            'Messagerie', 'Numéro Invalide', 'A Répondu',
                            'Mauvais Interlocuteur', 'Intérêts pour plus tard'
                        )),
            timestamp   TIMESTAMPTZ,
            infos       TEXT,
            created_at  TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("CREATE INDEX IF NOT EXISTS idx_interactions_lead_id ON interactions (lead_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_interactions_status  ON interactions (status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS interactions CASCADE")
    op.execute("DROP TABLE IF EXISTS leads CASCADE")
    op.execute("DROP TABLE IF EXISTS companies CASCADE")
