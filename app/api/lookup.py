import io

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.lookup import BatchLookupRow, LookupRequest, LookupResult
from app.services.lookup import lookup_lead

router = APIRouter(prefix="/lookup", tags=["lookup"])


@router.post("", response_model=LookupResult)
async def lookup_single(body: LookupRequest, db: AsyncSession = Depends(get_db)):
    return await lookup_lead(
        first_name=body.first_name,
        last_name=body.last_name,
        linkedin_url=body.linkedin_url,
        session=db,
    )


@router.post("/batch")
async def lookup_batch(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
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

    def find_col(*keys):
        for k in keys:
            if k in cols:
                return cols[k]
        return None

    last_col = find_col("last_name", "nom", "last name", "lastname", "surname")
    first_col = find_col("first_name", "prenom", "prénom", "first name", "firstname")
    linkedin_col = find_col("linkedin_url", "linkedin", "linkedin url")

    if not last_col or not first_col:
        raise HTTPException(status_code=422, detail=f"Colonnes 'last_name' et 'first_name' introuvables. Colonnes détectées : {list(df.columns)}")

    rows: list[BatchLookupRow] = []
    for i, row in df.iterrows():
        last = row.get(last_col) or ""
        first = row.get(first_col) or ""
        linkedin = row.get(linkedin_col) if linkedin_col else None

        if not last or not first:
            rows.append(BatchLookupRow(row_index=int(i)+2, first_name=first, last_name=last, linkedin_url=linkedin, found=False, score=0.0, match_type=None, matched_lead_id=None))
            continue

        result = await lookup_lead(first_name=first, last_name=last, linkedin_url=linkedin, session=db)
        rows.append(BatchLookupRow(
            row_index=int(i)+2, first_name=first, last_name=last, linkedin_url=linkedin,
            found=result.found, score=result.score, match_type=result.match_type,
            matched_lead_id=result.lead.id if result.lead else None,
        ))

    out_df = df.copy()
    out_df["found"] = [r.found for r in rows]
    out_df["score"] = [r.score for r in rows]
    out_df["match_type"] = [r.match_type or "" for r in rows]
    out_df["matched_lead_id"] = [str(r.matched_lead_id) if r.matched_lead_id else "" for r in rows]

    buf = io.StringIO()
    out_df.to_csv(buf, index=False)
    buf.seek(0)

    return StreamingResponse(
        io.BytesIO(buf.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=lookup_result.csv"},
    )
