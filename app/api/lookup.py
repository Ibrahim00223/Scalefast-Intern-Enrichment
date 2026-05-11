import io

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.lookup import BatchLookupRow, LookupRequest, LookupResult
from app.services.lookup import lookup_lead

router = APIRouter(prefix="/lookup", tags=["lookup"])


def _read_file(content: bytes, filename: str) -> pd.DataFrame:
    if filename.endswith(".csv"):
        return pd.read_csv(io.BytesIO(content), dtype=str)
    elif filename.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(content), dtype=str)
    else:
        raise HTTPException(status_code=400, detail="Seuls les fichiers .csv et .xlsx/.xls sont supportés.")


@router.post(
    "",
    response_model=LookupResult,
    summary="Vérification unitaire d'un lead",
    responses={
        200: {"description": "Résultat de la vérification (lead trouvé ou non)."},
    },
)
async def lookup_single(body: LookupRequest, db: AsyncSession = Depends(get_db)):
    """
    Vérifie si un lead existe en base à partir de son **prénom**, **nom** et optionnellement
    son **URL LinkedIn**.

    ### Logique de matching (deux passes)

    1. **LinkedIn exact** — si une URL LinkedIn est fournie, une correspondance exacte est
       d'abord recherchée après normalisation de l'URL. Si trouvée → `score = 1.0`,
       `match_type = "linkedin_exact"`.

    2. **Fuzzy nom + prénom** — si pas de match LinkedIn, une recherche fuzzy est lancée
       via `pg_trgm` (seuil : `similarity > 0.55` sur **nom ET prénom**), puis les candidats
       sont re-scorés avec `rapidfuzz.token_sort_ratio`. Le meilleur score est retourné.
       `match_type = "name_fuzzy"`.

    ### Valeurs du score

    | Score | Interprétation |
    |-------|---------------|
    | `1.0` | Correspondance LinkedIn exacte |
    | `0.85–0.99` | Très forte correspondance fuzzy |
    | `0.65–0.84` | Correspondance probable |
    | `< 0.55` | En dessous du seuil — retourné comme non trouvé |

    ### cURL

    ```bash
    # Lookup avec LinkedIn URL
    curl -X POST "{{BASE_URL}}/api/v1/lookup" \\
      -H "Content-Type: application/json" \\
      -d '{"first_name":"Jean","last_name":"Dupont","linkedin_url":"https://www.linkedin.com/in/jeandupont"}'

    # Lookup nom + prénom uniquement
    curl -X POST "{{BASE_URL}}/api/v1/lookup" \\
      -H "Content-Type: application/json" \\
      -d '{"first_name":"Jean","last_name":"Dupont"}'
    ```
    """
    return await lookup_lead(
        first_name=body.first_name,
        last_name=body.last_name,
        linkedin_url=body.linkedin_url,
        session=db,
    )


@router.post(
    "/columns",
    summary="Détecter les colonnes d'un fichier",
    responses={
        200: {"description": "Liste des noms de colonnes détectés dans le fichier."},
        400: {"description": "Format de fichier non supporté."},
    },
)
async def get_columns(file: UploadFile = File(..., description="Fichier CSV ou Excel (.xlsx/.xls) à analyser.")):
    """
    Retourne la liste des colonnes détectées dans un fichier CSV ou Excel,
    sans effectuer aucune vérification en base.

    Utilisé par l'interface pour alimenter le sélecteur de mapping de colonnes
    avant de lancer un lookup batch.

    ### Formats supportés
    - `.csv` (encodage UTF-8 recommandé)
    - `.xlsx` / `.xls`

    ### Exemple de réponse
    ```json
    { "columns": ["Prénom", "Nom", "Entreprise", "LinkedIn URL", "Poste"] }
    ```

    ### cURL
    ```bash
    curl -X POST "{{BASE_URL}}/api/v1/lookup/columns" \\
      -F "file=@/chemin/vers/contacts.csv"
    ```
    """
    content = await file.read()
    df = _read_file(content, file.filename or "")
    return {"columns": list(df.columns)}


@router.post(
    "/batch",
    summary="Vérification en lot (CSV / Excel)",
    responses={
        200: {"description": "Fichier CSV résultat avec les colonnes `found`, `score`, `match_type`, `matched_lead_id` ajoutées."},
        400: {"description": "Format de fichier non supporté."},
        422: {"description": "Colonnes `first_name` / `last_name` introuvables dans le fichier."},
    },
)
async def lookup_batch(
    file: UploadFile = File(..., description="Fichier CSV ou Excel contenant les contacts à vérifier."),
    col_first_name: str = Form(
        "",
        description=(
            "Nom exact de la colonne contenant les prénoms. "
            "Si vide, l'endpoint tente de détecter automatiquement parmi : "
            "`first_name`, `prenom`, `prénom`, `firstname`, `first name`."
        ),
    ),
    col_last_name: str = Form(
        "",
        description=(
            "Nom exact de la colonne contenant les noms. "
            "Si vide, détection automatique parmi : "
            "`last_name`, `nom`, `lastname`, `surname`, `last name`."
        ),
    ),
    col_linkedin_url: str = Form(
        "",
        description=(
            "Nom exact de la colonne contenant les URLs LinkedIn (optionnel). "
            "Si vide, détection automatique parmi : `linkedin_url`, `linkedin`, `linkedin url`."
        ),
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Vérifie en masse l'existence de leads à partir d'un fichier CSV ou Excel.

    ### Étapes

    1. Uploader le fichier via `POST /lookup/columns` pour récupérer les noms de colonnes.
    2. Sélectionner les colonnes prénom, nom et LinkedIn URL.
    3. Appeler cet endpoint avec le fichier + les paramètres de mapping.

    ### Résultat

    Le fichier original est retourné en CSV avec **4 colonnes ajoutées** en fin de fichier :

    | Colonne | Type | Description |
    |---------|------|-------------|
    | `found` | bool | `True` si un lead correspondant a été trouvé |
    | `score` | float | Score de correspondance (0.0–1.0) |
    | `match_type` | str | `linkedin_exact`, `name_fuzzy` ou vide |
    | `matched_lead_id` | UUID | ID du lead trouvé en base |

    ### Performances

    Chaque ligne génère 1–2 requêtes SQL. Pour des fichiers très larges (> 5 000 lignes),
    prévoir un temps de traitement proportionnel.

    ### cURL
    ```bash
    # Avec mapping de colonnes explicite
    curl -X POST "{{BASE_URL}}/api/v1/lookup/batch" \\
      -F "file=@/chemin/vers/contacts.csv" \\
      -F "col_first_name=Prénom" \\
      -F "col_last_name=Nom" \\
      -F "col_linkedin_url=LinkedIn URL" \\
      -o lookup_result.csv

    # Avec noms de colonnes standards (détection automatique)
    curl -X POST "{{BASE_URL}}/api/v1/lookup/batch" \\
      -F "file=@/chemin/vers/contacts.xlsx" \\
      -o lookup_result.csv
    ```
    """
    content = await file.read()
    df = _read_file(content, file.filename or "")
    df = df.where(pd.notnull(df), None)
    cols_lower = {c.lower().strip(): c for c in df.columns}

    def clean_cell(value) -> str | None:
        if value is None or pd.isna(value):
            return None
        text = str(value).strip()
        return text if text else None

    def find_col(explicit: str, *aliases):
        if explicit and explicit in df.columns:
            return explicit
        for k in aliases:
            if k in cols_lower:
                return cols_lower[k]
        return None

    last_col    = find_col(col_last_name,    "last_name", "nom", "last name", "lastname", "surname")
    first_col   = find_col(col_first_name,   "first_name", "prenom", "prénom", "first name", "firstname")
    linkedin_col = find_col(col_linkedin_url, "linkedin_url", "linkedin", "linkedin url")

    if not last_col or not first_col:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Colonnes 'last_name' et 'first_name' introuvables. "
                f"Colonnes détectées : {list(df.columns)}"
            ),
        )

    rows: list[BatchLookupRow] = []
    for i, row in df.iterrows():
        last = clean_cell(row.get(last_col)) or ""
        first = clean_cell(row.get(first_col)) or ""
        linkedin = clean_cell(row.get(linkedin_col)) if linkedin_col else None

        if not last or not first:
            rows.append(BatchLookupRow(
                row_index=int(i) + 2, first_name=first, last_name=last,
                linkedin_url=linkedin, found=False, score=0.0,
                match_type=None, matched_lead_id=None,
            ))
            continue

        result = await lookup_lead(first_name=first, last_name=last, linkedin_url=linkedin, session=db)
        rows.append(BatchLookupRow(
            row_index=int(i) + 2, first_name=first, last_name=last, linkedin_url=linkedin,
            found=result.found, score=result.score, match_type=result.match_type,
            matched_lead_id=result.lead.id if result.lead else None,
        ))

    out_df = df.copy()
    out_df["found"]           = [r.found for r in rows]
    out_df["score"]           = [r.score for r in rows]
    out_df["match_type"]      = [r.match_type or "" for r in rows]
    out_df["matched_lead_id"] = [str(r.matched_lead_id) if r.matched_lead_id else "" for r in rows]

    buf = io.StringIO()
    out_df.to_csv(buf, index=False)
    buf.seek(0)

    return StreamingResponse(
        io.BytesIO(buf.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=lookup_result.csv"},
    )
