import io

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.lookup import BatchLookupResult, BatchLookupRow, LookupRequest, LookupResult
from app.services.lookup import lookup_contact
from app.services.normalization import normalize_linkedin_url

router = APIRouter(prefix="/lookup", tags=["lookup"])


@router.post("", response_model=LookupResult)
async def lookup_single(body: LookupRequest, db: AsyncSession = Depends(get_db)):
    return await lookup_contact(
        nom=body.nom,
        prenom=body.prenom,
        linkedin_url=body.linkedin_url,
        session=db,
    )


@router.post("/batch")
async def lookup_batch(
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

    # Detect nom/prenom/linkedin columns (case-insensitive)
    col_map: dict[str, str] = {}
    for col in df.columns:
        cl = col.lower().strip()
        if cl in ("nom", "last name", "last_name", "lastname", "surname") and "nom" not in col_map:
            col_map["nom"] = col
        elif cl in ("prenom", "prénom", "first name", "first_name", "firstname") and "prenom" not in col_map:
            col_map["prenom"] = col
        elif cl in ("linkedin_url", "linkedin", "linkedin url", "profil linkedin") and "linkedin_url" not in col_map:
            col_map["linkedin_url"] = col

    if "nom" not in col_map or "prenom" not in col_map:
        raise HTTPException(
            status_code=422,
            detail=f"Could not detect 'nom' and 'prenom' columns. Found: {list(df.columns)}",
        )

    rows: list[BatchLookupRow] = []
    for i, row in df.iterrows():
        nom = row.get(col_map["nom"]) or ""
        prenom = row.get(col_map["prenom"]) or ""
        linkedin = row.get(col_map.get("linkedin_url", "")) if "linkedin_url" in col_map else None

        if not nom or not prenom:
            rows.append(
                BatchLookupRow(
                    row_index=int(i) + 2,
                    nom=nom,
                    prenom=prenom,
                    linkedin_url=linkedin,
                    found=False,
                    score=0.0,
                    match_type=None,
                    matched_contact_id=None,
                )
            )
            continue

        result = await lookup_contact(nom=nom, prenom=prenom, linkedin_url=linkedin, session=db)
        rows.append(
            BatchLookupRow(
                row_index=int(i) + 2,
                nom=nom,
                prenom=prenom,
                linkedin_url=linkedin,
                found=result.found,
                score=result.score,
                match_type=result.match_type,
                matched_contact_id=result.contact.id if result.contact else None,
            )
        )

    found_count = sum(1 for r in rows if r.found)

    # Build enriched CSV for download
    out_df = df.copy()
    out_df["found"] = [r.found for r in rows]
    out_df["score"] = [r.score for r in rows]
    out_df["match_type"] = [r.match_type or "" for r in rows]
    out_df["matched_contact_id"] = [str(r.matched_contact_id) if r.matched_contact_id else "" for r in rows]

    csv_buffer = io.StringIO()
    out_df.to_csv(csv_buffer, index=False)
    csv_buffer.seek(0)

    return StreamingResponse(
        io.BytesIO(csv_buffer.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=lookup_result.csv"},
    )
