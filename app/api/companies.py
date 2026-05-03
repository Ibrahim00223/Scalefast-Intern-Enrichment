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


@router.post("", response_model=CompanyOut, status_code=201)
async def create_company(body: CompanyCreate, db: AsyncSession = Depends(get_db)):
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
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A company with this LinkedIn URL already exists.")
    return company


@router.get("", response_model=CompanyListOut)
async def list_companies(
    q: str | None = Query(None, description="Search by company name"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Company)
    if q:
        stmt = stmt.where(Company.company_name.ilike(f"%{q}%"))

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    items = (await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return CompanyListOut(total=total, page=page, page_size=page_size, items=list(items))


@router.get("/{company_id}", response_model=CompanyOut)
async def get_company(company_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    company = await db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found.")
    return company


@router.patch("/{company_id}", response_model=CompanyOut)
async def update_company(company_id: uuid.UUID, body: CompanyUpdate, db: AsyncSession = Depends(get_db)):
    company = await db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found.")
    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "linkedin_url":
            value = normalize_linkedin_url(value)
        setattr(company, field, value)
    await db.commit()
    await db.refresh(company)
    return company


@router.delete("/{company_id}", status_code=204)
async def delete_company(company_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    company = await db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found.")
    await db.delete(company)
    await db.commit()


@router.post("/import", status_code=200)
async def import_companies(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
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
