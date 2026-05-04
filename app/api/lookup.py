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


@router.post("", response_model=LookupResult)
async def lookup_single(body: LookupRequest, db: AsyncSession = Depends(get_db)):
    return await lookup_lead(
        first_name=body.first_name,
        last_name=body.last_name,
        linkedin_url=body.linkedin_url,
        session=db,
    )


@router.post("/columns")
async def get_columns(file: UploadFile = File(...)):
    """Return the list of columns detected in a CSV or Excel file."""
    content = await file.read()
    df = _read_file(content, file.filename or "")
    return {"columns": list(df.columns)}


@router.post("/batch")
async def lookup_batch(
    file: UploadFile = File(...),
    col_first_name: str = Form(""),
    col_last_name: str = Form(""),
    col_linkedin_url: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    """
    Batch lookup. Column names can be passed explicitly via form fields
    (col_first_name, col_last_name, col_linkedin_url). If omitted, the
    endpoint falls back to common aliases.
    """
    content = await file.read()
    df = _read_file(content, file.filename or "")
    df = df.where(pd.notnull(df), None)
    cols_lower = {c.lower().strip(): c for c in df.columns}

    def find_col(explicit: str, *aliases):
        if explicit and explicit in df.columns:
            return explicit
        for k in aliases:
            if k in cols_lower:
                return cols_lower[k]
        return None

    last_col = find_col(col_last_name, "last_name", "nom", "last name", "lastname", "surname")
    first_col = find_col(col_first_name, "first_name", "prenom", "prénom", "first name", "firstname")
    linkedin_col = find_col(col_linkedin_url, "linkedin_url", "linkedin", "linkedin url")

    if not last_col or not first_col:
        raise HTTPException(
            status_code=422,
            detail=f"Colonnes 'last_name' et 'first_name' introuvables. "
                   f"Colonnes détectées : {list(df.columns)}"
        )

    rows: list[BatchLookupRow] = []
    for i, row in df.iterrows():
        last = row.get(last_col) or ""
        first = row.get(first_col) or ""
        linkedin = row.get(linkedin_col) if linkedin_col else None

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
