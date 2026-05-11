import io
import uuid

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.api.deps import get_db
from app.models.lead import Lead
from app.schemas.lead import LeadCreate, LeadListOut, LeadOut, LeadUpdate, LeadWithCompanyAndInteractions
from app.services.normalization import normalize_linkedin_url

router = APIRouter(prefix="/leads", tags=["leads"])


@router.post(
    "",
    response_model=LeadOut,
    status_code=201,
    summary="Creer un lead",
    responses={
        201: {"description": "Lead cree avec succes."},
        409: {"description": "Un lead avec cette URL LinkedIn existe deja."},
    },
)
async def create_lead(body: LeadCreate, db: AsyncSession = Depends(get_db)):
    """
    Cree un nouveau lead en base.

    - L'URL LinkedIn est normalisee automatiquement (lowercase, sans parametres query,
      gestion des prefixes langue `/in/`, `/pub/`, etc.).
    - Les colonnes `full_name`, `last_name_normalized` et `first_name_normalized` sont
      calculees automatiquement par PostgreSQL (`GENERATED ALWAYS AS`).
    - Si une URL LinkedIn est fournie, elle doit etre unique en base (contrainte `UNIQUE`).

    ### cURL
    ```bash
    curl -X POST "{{BASE_URL}}/api/v1/leads" \\
      -H "Content-Type: application/json" \\
      -d '{
        "first_name": "Jean",
        "last_name": "Dupont",
        "company_name": "Scalefast",
        "job_title": "GTM Engineer",
        "location": "Paris, France",
        "linkedin_url": "https://www.linkedin.com/in/jeandupont"
      }'
    ```
    """
    linkedin = normalize_linkedin_url(body.linkedin_url)
    lead = Lead(
        last_name=body.last_name,
        first_name=body.first_name,
        company_id=body.company_id,
        company_name=body.company_name,
        job_title=body.job_title,
        location=body.location,
        linkedin_id=body.linkedin_id,
        linkedin_url=linkedin,
    )
    db.add(lead)
    try:
        await db.commit()
        await db.refresh(lead)
    except Exception as exc:
        await db.rollback()
        msg = str(exc)
        if "linkedin_url" in msg or "unique" in msg.lower():
            raise HTTPException(status_code=409, detail="Un lead avec cette URL LinkedIn existe deja.")
        raise HTTPException(status_code=500, detail=f"Erreur base de donnees : {msg[:200]}")
    return lead


@router.get(
    "",
    response_model=LeadListOut,
    summary="Lister les leads",
)
async def list_leads(
    q: str | None = Query(
        None,
        description=(
            "Recherche textuelle. Interroge simultanement : nom (fuzzy via `pg_trgm`), "
            "prenom (fuzzy), nom d'entreprise (`ILIKE`) et intitule de poste (`ILIKE`). "
            "Exemple : `dupont`, `scalefast`, `gtm`."
        ),
    ),
    company_id: uuid.UUID | None = Query(None, description="Filtre par UUID d'entreprise associee."),
    page: int = Query(1, ge=1, description="Numero de page (commence a 1)."),
    page_size: int = Query(20, ge=1, le=100, description="Nombre de resultats par page (max 100)."),
    db: AsyncSession = Depends(get_db),
):
    """
    Retourne la liste paginee des leads, avec filtres optionnels.

    La recherche par `q` utilise `pg_trgm` sur les noms normalises (seuil `similarity > 0.3`)
    combinee a `ILIKE` sur l'entreprise et le poste.

    ### cURL
    ```bash
    # Tous les leads (page 1)
    curl "{{BASE_URL}}/api/v1/leads?page=1&page_size=20"

    # Recherche fuzzy
    curl "{{BASE_URL}}/api/v1/leads?q=dupont&page=1"

    # Filtrer par entreprise
    curl "{{BASE_URL}}/api/v1/leads?company_id=<uuid>"
    ```
    """
    stmt = select(Lead)
    if company_id:
        stmt = stmt.where(Lead.company_id == company_id)
    if q:
        q_lower = q.lower()
        stmt = stmt.where(
            or_(
                func.similarity(Lead.last_name_normalized, q_lower) > 0.3,
                func.similarity(Lead.first_name_normalized, q_lower) > 0.3,
                Lead.company_name.ilike(f"%{q}%"),
                Lead.job_title.ilike(f"%{q}%"),
            )
        )

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    items = (await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return LeadListOut(total=total, page=page, page_size=page_size, items=list(items))


@router.get(
    "/{lead_id}/full",
    response_model=LeadWithCompanyAndInteractions,
    summary="Recuperer un lead complet avec entreprise et interactions",
    responses={
        200: {"description": "Fiche complete du lead avec entreprise et interactions."},
        404: {"description": "Lead introuvable."},
    },
)
async def get_lead_full(lead_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Retourne la fiche complete d'un lead a partir de son UUID, incluant :
    - Les donnees du lead
    - Les donnees de l'entreprise associee (si elle existe)
    - Toutes les interactions du lead

    ### cURL
    ```bash
    curl "{{BASE_URL}}/api/v1/leads/{lead_id}/full"
    ```
    """
    result = await db.execute(
        select(Lead)
        .options(joinedload(Lead.company), joinedload(Lead.interactions))
        .where(Lead.id == lead_id)
    )
    lead = result.scalar_one_or_none()

    if not lead:
        raise HTTPException(status_code=404, detail="Lead introuvable.")

    return LeadWithCompanyAndInteractions.model_validate(lead)


@router.get(
    "/{lead_id}",
    response_model=LeadOut,
    summary="Recuperer un lead par ID",
    responses={
        200: {"description": "Fiche complete du lead."},
        404: {"description": "Lead introuvable."},
    },
)
async def get_lead(lead_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Retourne la fiche complete d'un lead a partir de son UUID.

    ### cURL
    ```bash
    curl "{{BASE_URL}}/api/v1/leads/<lead_id>"
    ```
    """
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead introuvable.")
    return lead


@router.patch(
    "/{lead_id}",
    response_model=LeadOut,
    summary="Mettre a jour un lead",
    responses={
        200: {"description": "Lead mis a jour."},
        404: {"description": "Lead introuvable."},
    },
)
async def update_lead(lead_id: uuid.UUID, body: LeadUpdate, db: AsyncSession = Depends(get_db)):
    """
    Met a jour partiellement un lead (seuls les champs fournis dans le body sont modifies).

    - L'URL LinkedIn est normalisee si fournie.
    - Les colonnes generees (`full_name`, `last_name_normalized`, `first_name_normalized`)
      sont recalculees automatiquement par PostgreSQL lors du `UPDATE`.

    ### cURL
    ```bash
    curl -X PATCH "{{BASE_URL}}/api/v1/leads/<lead_id>" \\
      -H "Content-Type: application/json" \\
      -d '{"job_title": "Senior GTM Engineer", "location": "Lyon, France"}'
    ```
    """
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead introuvable.")
    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "linkedin_url":
            value = normalize_linkedin_url(value)
        if field in ("full_name", "last_name_normalized", "first_name_normalized"):
            continue
        setattr(lead, field, value)
    await db.commit()
    await db.refresh(lead)
    return lead


@router.delete(
    "/{lead_id}",
    status_code=204,
    summary="Supprimer un lead",
    responses={
        204: {"description": "Lead supprime (les interactions associees sont supprimees en cascade)."},
        404: {"description": "Lead introuvable."},
    },
)
async def delete_lead(lead_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Supprime un lead et toutes ses interactions associees (cascade `ON DELETE CASCADE`).

    ### cURL
    ```bash
    curl -X DELETE "{{BASE_URL}}/api/v1/leads/<lead_id>"
    ```
    """
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead introuvable.")
    await db.delete(lead)
    await db.commit()


@router.post(
    "/import",
    status_code=200,
    summary="Importer des leads depuis un fichier",
    responses={
        200: {"description": "Rapport d'import : nombre de leads crees, ignores et erreurs."},
        400: {"description": "Format de fichier non supporte."},
    },
)
async def import_leads(
    file: UploadFile = File(..., description="Fichier CSV ou Excel contenant les leads a importer."),
    db: AsyncSession = Depends(get_db),
):
    """
    Importe des leads en masse depuis un fichier CSV ou Excel.

    ### Colonnes reconnues automatiquement

    | Champ | Alias acceptes |
    |-------|---------------|
    | `last_name` | `nom`, `last name`, `lastname`, `surname` |
    | `first_name` | `prenom`, `prénom`, `first name`, `firstname` |
    | `company_name` | `company`, `entreprise` |
    | `job_title` | `poste`, `titre`, `title` |
    | `location` | `localisation` |
    | `linkedin_url` | `linkedin` |
    | `linkedin_id` | - |

    ### Comportement

    - Les lignes sans `last_name` **et** `first_name` sont ignorees (`skipped`).
    - Les doublons LinkedIn URL sont signales dans `errors` sans bloquer l'import.
    - La reponse indique le nombre de leads `created`, `skipped` et les `errors` detaillees.

    ### Exemple de reponse
    ```json
    {
      "filename": "leads_mai_2026.csv",
      "total_rows": 150,
      "created": 142,
      "skipped": 5,
      "errors": [{"row": 12, "error": "duplicate key value violates unique constraint"}]
    }
    ```

    ### cURL
    ```bash
    curl -X POST "{{BASE_URL}}/api/v1/leads/import" \\
      -F "file=@/chemin/vers/leads.csv"
    ```
    """
    content = await file.read()
    filename = file.filename or ""
    if filename.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(content), dtype=str)
    elif filename.endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(content), dtype=str)
    else:
        raise HTTPException(status_code=400, detail="Seuls les fichiers .csv et .xlsx/.xls sont supportes.")

    df = df.where(pd.notnull(df), None)
    cols = {c.lower().strip(): c for c in df.columns}

    def get(row, *keys):
        for k in keys:
            if k in cols:
                v = row.get(cols[k])
                return v if v and str(v).strip() else None
        return None

    created, skipped, errors = 0, 0, []
    for i, row in df.iterrows():
        row = row.to_dict()
        last = get(row, "last_name", "nom", "last name", "lastname", "surname")
        first = get(row, "first_name", "prenom", "prénom", "first name", "firstname")
        if not last or not first:
            skipped += 1
            continue
        try:
            linkedin = normalize_linkedin_url(get(row, "linkedin_url", "linkedin"))
            lead = Lead(
                last_name=last,
                first_name=first,
                company_name=get(row, "company_name", "company", "entreprise"),
                job_title=get(row, "job_title", "poste", "titre", "title"),
                location=get(row, "location", "localisation"),
                linkedin_id=get(row, "linkedin_id"),
                linkedin_url=linkedin,
            )
            db.add(lead)
            await db.flush()
            created += 1
        except Exception as e:
            await db.rollback()
            errors.append({"row": int(i) + 2, "error": str(e)})

    await db.commit()
    return {"filename": filename, "total_rows": len(df), "created": created, "skipped": skipped, "errors": errors}
