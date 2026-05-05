import io
import uuid

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.lead import Lead
from app.schemas.lead import LeadCreate, LeadListOut, LeadOut, LeadUpdate
from app.services.normalization import normalize_linkedin_url

router = APIRouter(prefix="/leads", tags=["leads"])


@router.post(
    "",
    response_model=LeadOut,
    status_code=201,
    summary="Créer un lead",
    responses={
        201: {"description": "Lead créé avec succès."},
        409: {"description": "Un lead avec cette URL LinkedIn existe déjà."},
    },
)
async def create_lead(body: LeadCreate, db: AsyncSession = Depends(get_db)):
    """
    Crée un nouveau lead en base.

    - L'URL LinkedIn est normalisée automatiquement (lowercase, sans paramètres query,
      gestion des préfixes langue `/in/`, `/pub/`, etc.).
    - Les colonnes `full_name`, `last_name_normalized` et `first_name_normalized` sont
      calculées automatiquement par PostgreSQL (`GENERATED ALWAYS AS`).
    - Si une URL LinkedIn est fournie, elle doit être unique en base (contrainte `UNIQUE`).
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
            raise HTTPException(status_code=409, detail="Un lead avec cette URL LinkedIn existe déjà.")
        raise HTTPException(status_code=500, detail=f"Erreur base de données : {msg[:200]}")
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
            "Recherche textuelle. Interroge simultanément : nom (fuzzy via `pg_trgm`), "
            "prénom (fuzzy), nom d'entreprise (`ILIKE`) et intitulé de poste (`ILIKE`). "
            "Exemple : `dupont`, `scalefast`, `gtm`."
        ),
    ),
    company_id: uuid.UUID | None = Query(None, description="Filtre par UUID d'entreprise associée."),
    page: int = Query(1, ge=1, description="Numéro de page (commence à 1)."),
    page_size: int = Query(20, ge=1, le=100, description="Nombre de résultats par page (max 100)."),
    db: AsyncSession = Depends(get_db),
):
    """
    Retourne la liste paginée des leads, avec filtres optionnels.

    La recherche par `q` utilise `pg_trgm` sur les noms normalisés (seuil `similarity > 0.3`)
    combinée à `ILIKE` sur l'entreprise et le poste.
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
    "/{lead_id}",
    response_model=LeadOut,
    summary="Récupérer un lead par ID",
    responses={
        200: {"description": "Fiche complète du lead."},
        404: {"description": "Lead introuvable."},
    },
)
async def get_lead(lead_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Retourne la fiche complète d'un lead à partir de son UUID."""
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead introuvable.")
    return lead


@router.patch(
    "/{lead_id}",
    response_model=LeadOut,
    summary="Mettre à jour un lead",
    responses={
        200: {"description": "Lead mis à jour."},
        404: {"description": "Lead introuvable."},
    },
)
async def update_lead(lead_id: uuid.UUID, body: LeadUpdate, db: AsyncSession = Depends(get_db)):
    """
    Met à jour partiellement un lead (seuls les champs fournis dans le body sont modifiés).

    - L'URL LinkedIn est normalisée si fournie.
    - Les colonnes générées (`full_name`, `last_name_normalized`, `first_name_normalized`)
      sont recalculées automatiquement par PostgreSQL lors du `UPDATE`.
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
        204: {"description": "Lead supprimé (les interactions associées sont supprimées en cascade)."},
        404: {"description": "Lead introuvable."},
    },
)
async def delete_lead(lead_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Supprime un lead et toutes ses interactions associées (cascade `ON DELETE CASCADE`).
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
        200: {"description": "Rapport d'import : nombre de leads créés, ignorés et erreurs."},
        400: {"description": "Format de fichier non supporté."},
    },
)
async def import_leads(
    file: UploadFile = File(..., description="Fichier CSV ou Excel contenant les leads à importer."),
    db: AsyncSession = Depends(get_db),
):
    """
    Importe des leads en masse depuis un fichier CSV ou Excel.

    ### Colonnes reconnues automatiquement

    | Champ | Alias acceptés |
    |-------|---------------|
    | `last_name` | `nom`, `last name`, `lastname`, `surname` |
    | `first_name` | `prenom`, `prénom`, `first name`, `firstname` |
    | `company_name` | `company`, `entreprise` |
    | `job_title` | `poste`, `titre`, `title` |
    | `location` | `localisation` |
    | `linkedin_url` | `linkedin` |
    | `linkedin_id` | — |

    ### Comportement

    - Les lignes sans `last_name` **et** `first_name` sont ignorées (`skipped`).
    - Les doublons LinkedIn URL sont signalés dans `errors` sans bloquer l'import.
    - La réponse indique le nombre de leads `created`, `skipped` et les `errors` détaillées.

    ### Exemple de réponse
    ```json
    {
      "filename": "leads_mai_2026.csv",
      "total_rows": 150,
      "created": 142,
      "skipped": 5,
      "errors": [{"row": 12, "error": "duplicate key value violates unique constraint"}]
    }
    ```
    """
    content = await file.read()
    filename = file.filename or ""
    if filename.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(content), dtype=str)
    elif filename.endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(content), dtype=str)
    else:
        raise HTTPException(status_code=400, detail="Seuls les fichiers .csv et .xlsx/.xls sont supportés.")

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
        last  = get(row, "last_name", "nom", "last name", "lastname", "surname")
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
