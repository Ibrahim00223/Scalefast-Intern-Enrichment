from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import companies, interactions, leads, lookup

DESCRIPTION = """
## Présentation

**Intern Enrichment** est un système interne Scalefast permettant de **vérifier si un contact
est déjà présent en base de données** avant toute action commerciale ou appel à un provider
d'enrichissement externe.

---

## Flux principal

1. **Lookup unitaire** — soumettre `first_name` + `last_name` + `linkedin_url` (optionnel)
   → réponse immédiate avec score de correspondance.

2. **Lookup batch** — importer un fichier CSV ou Excel, mapper les colonnes, lancer la vérification
   en masse → CSV résultat enrichi avec colonnes `found`, `score`, `match_type`, `matched_lead_id`.

3. **CRUD Leads / Companies / Interactions** — alimenter et maintenir la base de données interne.

---

## Logique de matching

| Passe | Condition | Score |
|-------|-----------|-------|
| **LinkedIn exact** | URL normalisée identique | `1.0` |
| **Fuzzy nom** | `pg_trgm similarity > 0.55` sur nom **ET** prénom, puis `rapidfuzz token_sort_ratio` | `0.0 – 1.0` |

Les URLs LinkedIn sont normalisées automatiquement vers `https://www.linkedin.com/in/<slug>`
(gestion des préfixes langue, `/pub/`, paramètres query, trailing slash).

---

## Schéma de données

```
Companies  ──< Leads ──< Interactions
```

- **Company** : entreprise (nom, secteur, effectif, LinkedIn)
- **Lead** : contact individuel, rattaché optionnellement à une Company
- **Interaction** : historique d'un contact (appel / mail) avec statut métier
"""

TAGS_METADATA = [
    {
        "name": "lookup",
        "description": (
            "Vérification de l'existence d'un lead en base. "
            "Deux modes : **unitaire** (JSON) et **batch** (CSV/Excel multipart). "
            "L'endpoint `/columns` permet de détecter les colonnes d'un fichier avant le batch."
        ),
    },
    {
        "name": "leads",
        "description": (
            "CRUD complet sur les leads (contacts individuels). "
            "Supporte la recherche fuzzy par nom via `pg_trgm`. "
            "Import en masse via fichier CSV ou Excel (`/import`)."
        ),
    },
    {
        "name": "companies",
        "description": (
            "CRUD complet sur les entreprises. "
            "Chaque lead peut être rattaché à une company via `company_id`. "
            "Import en masse via fichier CSV ou Excel (`/import`)."
        ),
    },
    {
        "name": "interactions",
        "description": (
            "Historique des interactions commerciales liées à un lead. "
            "Types possibles : `appel`, `mail`. "
            "Statuts possibles : NRP 1–4, Messagerie, Numéro Invalide, A Répondu, "
            "Mauvais Interlocuteur, Intérêts pour plus tard. "
            "L'endpoint `/meta` retourne les listes de valeurs valides."
        ),
    },
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="Intern Enrichment — Scalefast",
    description=DESCRIPTION,
    version="0.2.0",
    openapi_tags=TAGS_METADATA,
    contact={"name": "Scalefast GTM Team"},
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(companies.router, prefix="/api/v1")
app.include_router(leads.router, prefix="/api/v1")
app.include_router(interactions.router, prefix="/api/v1")
app.include_router(lookup.router, prefix="/api/v1")

STATIC_DIR = Path(__file__).parent.parent / "static"


@app.get("/", include_in_schema=False)
async def root():
    return FileResponse(str(STATIC_DIR / "index.html"))


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
