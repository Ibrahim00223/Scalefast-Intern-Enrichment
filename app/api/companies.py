import io
import uuid

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.company import Company
from app.schemas.company import CompanyCreate, CompanyListOut, CompanyOut, CompanyUpdate
from app.services.normalization import normalize_linkedin_url

router = APIRouter(prefix="/companies", tags=["companies"])


@router.post(
    "",
    response_model=CompanyOut,
    status_code=201,
    summary="Créer une entreprise",
    responses={
        201: {"description": "Entreprise créée avec succès."},
        409: {"description": "Une entreprise avec cette URL LinkedIn existe déjà."},
    },
)
async def create_company(body: CompanyCreate, db: AsyncSession = Depends(get_db)):
    """
    Crée une nouvelle entreprise en base.

    L'URL LinkedIn est normalisée automatiquement. Si fournie, elle doit être unique.

    ### cURL
    ```bash
    curl -X POST "{{BASE_URL}}/api/v1/companies" \\
      -H "Content-Type: application/json" \\
      -d '{
        "company_name": "Scalefast",
        "linkedin_url": "https://www.linkedin.com/company/scalefast",
        "location": "Madrid, Espagne",
        "industry": "E-commerce / SaaS",
        "number_of_employees": 150
      }'
    ```
    """
    linkedin = normalize_linkedin_url(body.linkedin_url)
    company = Company(
        company_name=body.company_name,
        linkedin_url=linkedin,
        linkedin_id=body.linkedin_id,
        location=body.location,
        industry=body.industry,
        number_of_employees=body.number_of_employees,
    )
    db.add(company)
    try:
        await db.commit()
        await db.refresh(company)
    except Exception as exc:
        await db.rollback()
        msg = str(exc)
        if "linkedin_url" in msg or "unique" in msg.lower():
            raise HTTPException(status_code=409, detail="Une entreprise avec cette URL LinkedIn existe déjà.")
        raise HTTPException(status_code=500, detail=f"Erreur base de données : {msg[:200]}")
    return company


@router.get(
    "",
    response_model=CompanyListOut,
    summary="Lister les entreprises",
)
async def list_companies(
    q: str | None = Query(
        None,
        description="Recherche par nom d'entreprise (`ILIKE %q%`). Exemple : `scalefast`.",
    ),
    page: int = Query(1, ge=1, description="Numéro de page (commence à 1)."),
    page_size: int = Query(20, ge=1, le=100, description="Résultats par page (max 100)."),
    db: AsyncSession = Depends(get_db),
):
    """
    Retourne la liste paginée des entreprises, avec filtre optionnel par nom.

    ### cURL
    ```bash
    # Toutes les entreprises
    curl "{{BASE_URL}}/api/v1/companies?page=1&page_size=20"

    # Recherche par nom
    curl "{{BASE_URL}}/api/v1/companies?q=scalefast"
    ```
    """
    stmt = select(Company)
    if q:
        stmt = stmt.where(Company.company_name.ilike(f"%{q}%"))

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    items = (await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return CompanyListOut(total=total, page=page, page_size=page_size, items=list(items))


@router.get(
    "/{company_id}",
    response_model=CompanyOut,
    summary="Récupérer une entreprise par ID",
    responses={
        200: {"description": "Fiche complète de l'entreprise."},
        404: {"description": "Entreprise introuvable."},
    },
)
async def get_company(company_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Retourne la fiche complète d'une entreprise à partir de son UUID.

    ### cURL
    ```bash
    curl "{{BASE_URL}}/api/v1/companies/<company_id>"
    ```
    """
    company = await db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Entreprise introuvable.")
    return company


@router.patch(
    "/{company_id}",
    response_model=CompanyOut,
    summary="Mettre à jour une entreprise",
    responses={
        200: {"description": "Entreprise mise à jour."},
        404: {"description": "Entreprise introuvable."},
    },
)
async def update_company(company_id: uuid.UUID, body: CompanyUpdate, db: AsyncSession = Depends(get_db)):
    """
    Met à jour partiellement une entreprise (seuls les champs fournis sont modifiés).

    L'URL LinkedIn est normalisée si fournie.

    ### cURL
    ```bash
    curl -X PATCH "{{BASE_URL}}/api/v1/companies/<company_id>" \\
      -H "Content-Type: application/json" \\
      -d '{"number_of_employees": 200, "industry": "E-commerce"}'
    ```
    """
    company = await db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Entreprise introuvable.")
    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "linkedin_url":
            value = normalize_linkedin_url(value)
        setattr(company, field, value)
    await db.commit()
    await db.refresh(company)
    return company


@router.delete(
    "/{company_id}",
    status_code=204,
    summary="Supprimer une entreprise",
    responses={
        204: {"description": "Entreprise supprimée. Les leads rattachés ont leur `company_id` mis à NULL."},
        404: {"description": "Entreprise introuvable."},
    },
)
async def delete_company(company_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Supprime une entreprise. Les leads qui y étaient rattachés conservent leur `company_name`
    mais leur `company_id` est mis à `NULL` (contrainte `ON DELETE SET NULL`).

    ### cURL
    ```bash
    curl -X DELETE "{{BASE_URL}}/api/v1/companies/<company_id>"
    ```
    """
    company = await db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Entreprise introuvable.")
    await db.delete(company)
    await db.commit()


@router.post(
    "/import",
    status_code=200,
    summary="Importer des entreprises depuis un fichier",
    responses={
        200: {"description": "Rapport d'import."},
        400: {"description": "Format de fichier non supporté."},
    },
)
async def import_companies(
    file: UploadFile = File(..., description="Fichier CSV ou Excel contenant les entreprises à importer."),
    db: AsyncSession = Depends(get_db),
):
    """
    Importe des entreprises en masse depuis un fichier CSV ou Excel.

    ### Colonnes reconnues automatiquement

    | Champ | Alias acceptés |
    |-------|---------------|
    | `company_name` | `company`, `entreprise`, `société`, `name` |
    | `linkedin_url` | `linkedin` |
    | `linkedin_id` | — |
    | `location` | `localisation` |
    | `industry` | `secteur` |
    | `number_of_employees` | `employees`, `effectif` |

    Les lignes sans `company_name` sont ignorées.

    ### cURL
    ```bash
    curl -X POST "{{BASE_URL}}/api/v1/companies/import" \\
      -F "file=@/chemin/vers/companies.csv"
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
        name = get(row, "company_name", "company", "entreprise", "société", "name")
        if not name:
            skipped += 1
            continue
        try:
            linkedin = normalize_linkedin_url(get(row, "linkedin_url", "linkedin"))
            company = Company(
                company_name=name,
                linkedin_url=linkedin,
                linkedin_id=get(row, "linkedin_id"),
                location=get(row, "location", "localisation"),
                industry=get(row, "industry", "secteur"),
                number_of_employees=int(get(row, "number_of_employees", "employees", "effectif") or 0) or None,
            )
            db.add(company)
            await db.flush()
            created += 1
        except Exception as e:
            await db.rollback()
            errors.append({"row": int(i) + 2, "error": str(e)})

    await db.commit()
    return {"filename": filename, "total_rows": len(df), "created": created, "skipped": skipped, "errors": errors}
