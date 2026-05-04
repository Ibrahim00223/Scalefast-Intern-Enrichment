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


@router.post("", response_model=LeadOut, status_code=201)
async def create_lead(body: LeadCreate, db: AsyncSession = Depends(get_db)):
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


@router.get("", response_model=LeadListOut)
async def list_leads(
    q: str | None = Query(None, description="Search by name, company, job title"),
    company_id: uuid.UUID | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
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


@router.get("/{lead_id}", response_model=LeadOut)
async def get_lead(lead_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found.")
    return lead


@router.patch("/{lead_id}", response_model=LeadOut)
async def update_lead(lead_id: uuid.UUID, body: LeadUpdate, db: AsyncSession = Depends(get_db)):
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found.")
    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "linkedin_url":
            value = normalize_linkedin_url(value)
        # Skip GENERATED columns — PostgreSQL recomputes them automatically
        if field in ("full_name", "last_name_normalized", "first_name_normalized"):
            continue
        setattr(lead, field, value)
    await db.commit()
    await db.refresh(lead)
    return lead


@router.delete("/{lead_id}", status_code=204)
async def delete_lead(lead_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found.")
    await db.delete(lead)
    await db.commit()


@router.post("/import", status_code=200)
async def import_leads(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    content = await file.read()
    filename = file.filename or ""
    if filename.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(content), dtype=str)
    elif filename.endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(content), dtype=str)
    else:
        raise HTTPException(status_code=400, detail="Only .csv and .xlsx/.xls files are supported.")

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
