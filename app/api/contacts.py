import io
import uuid

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.contact import Contact
from app.schemas.contact import ContactCreate, ContactListOut, ContactOut, ContactUpdate
from app.services.normalization import normalize_linkedin_url, normalize_name

router = APIRouter(prefix="/contacts", tags=["contacts"])

# Column name variants for auto-detection during CSV/Excel import
_COLUMN_ALIASES: dict[str, list[str]] = {
    "nom": ["nom", "last name", "last_name", "lastname", "surname", "family name", "name"],
    "prenom": ["prenom", "prénom", "first name", "first_name", "firstname", "given name"],
    "linkedin_url": ["linkedin_url", "linkedin", "linkedin url", "profil linkedin", "url linkedin"],
    "email": ["email", "e-mail", "mail", "courriel"],
    "phone": ["phone", "téléphone", "telephone", "tel", "mobile"],
    "company": ["company", "entreprise", "société", "societe", "organization", "org"],
    "job_title": ["job_title", "job title", "poste", "titre", "fonction", "title", "role"],
    "source": ["source"],
}


def _detect_column_mapping(columns: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    lower_cols = {c.lower().strip(): c for c in columns}
    for field, aliases in _COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in lower_cols:
                mapping[field] = lower_cols[alias]
                break
    return mapping


def _build_contact_from_row(row: dict, mapping: dict[str, str]) -> dict:
    data = {}
    for field, col in mapping.items():
        val = row.get(col)
        if pd.isna(val) if val is not None else False:
            val = None
        data[field] = val if val else None
    return data


@router.post("", response_model=ContactOut, status_code=201)
async def create_contact(body: ContactCreate, db: AsyncSession = Depends(get_db)):
    linkedin = normalize_linkedin_url(body.linkedin_url)
    contact = Contact(
        nom=body.nom,
        prenom=body.prenom,
        nom_normalized=normalize_name(body.nom),
        prenom_normalized=normalize_name(body.prenom),
        linkedin_url=linkedin,
        email=body.email,
        phone=body.phone,
        company=body.company,
        job_title=body.job_title,
        source=body.source,
    )
    db.add(contact)
    try:
        await db.commit()
        await db.refresh(contact)
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A contact with this LinkedIn URL already exists.")
    return contact


@router.get("", response_model=ContactListOut)
async def list_contacts(
    q: str | None = Query(None, description="Search by name, company or email"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Contact)
    if q:
        q_lower = q.lower()
        stmt = stmt.where(
            or_(
                func.similarity(Contact.nom_normalized, q_lower) > 0.3,
                func.similarity(Contact.prenom_normalized, q_lower) > 0.3,
                Contact.email.ilike(f"%{q}%"),
                Contact.company.ilike(f"%{q}%"),
            )
        )

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(stmt)).scalars().all()

    return ContactListOut(total=total, page=page, page_size=page_size, items=list(items))


@router.patch("/{contact_id}", response_model=ContactOut)
async def update_contact(
    contact_id: uuid.UUID, body: ContactUpdate, db: AsyncSession = Depends(get_db)
):
    contact = await db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found.")

    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "linkedin_url":
            value = normalize_linkedin_url(value)
        if field == "nom" and value:
            contact.nom_normalized = normalize_name(value)
        if field == "prenom" and value:
            contact.prenom_normalized = normalize_name(value)
        setattr(contact, field, value)

    await db.commit()
    await db.refresh(contact)
    return contact


@router.delete("/{contact_id}", status_code=204)
async def delete_contact(contact_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    contact = await db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found.")
    await db.delete(contact)
    await db.commit()


@router.post("/import", status_code=200)
async def import_contacts(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    content = await file.read()
    filename = file.filename or ""

    if filename.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(content), dtype=str)
    elif filename.endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(content), dtype=str)
    else:
        raise HTTPException(status_code=400, detail="Only .csv and .xlsx/.xls files are supported.")

    df = df.where(pd.notnull(df), None)
    mapping = _detect_column_mapping(list(df.columns))

    if "nom" not in mapping or "prenom" not in mapping:
        raise HTTPException(
            status_code=422,
            detail=f"Could not detect 'nom' and 'prenom' columns. Found columns: {list(df.columns)}",
        )

    created = 0
    skipped = 0
    errors: list[dict] = []

    for i, row in df.iterrows():
        try:
            data = _build_contact_from_row(row.to_dict(), mapping)
            if not data.get("nom") or not data.get("prenom"):
                skipped += 1
                continue

            linkedin = normalize_linkedin_url(data.get("linkedin_url"))
            contact = Contact(
                nom=data["nom"],
                prenom=data["prenom"],
                nom_normalized=normalize_name(data["nom"]),
                prenom_normalized=normalize_name(data["prenom"]),
                linkedin_url=linkedin,
                email=data.get("email"),
                phone=data.get("phone"),
                company=data.get("company"),
                job_title=data.get("job_title"),
                source=data.get("source") or "import",
            )
            db.add(contact)
            await db.flush()
            created += 1
        except Exception as e:
            await db.rollback()
            errors.append({"row": int(i) + 2, "error": str(e)})

    await db.commit()
    return {
        "filename": filename,
        "total_rows": len(df),
        "created": created,
        "skipped": skipped,
        "errors": errors,
    }
