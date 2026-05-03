import uuid

from pydantic import BaseModel

from app.schemas.contact import ContactOut


class LookupRequest(BaseModel):
    nom: str
    prenom: str
    linkedin_url: str | None = None


class LookupResult(BaseModel):
    found: bool
    score: float
    match_type: str | None  # "linkedin_exact" | "name_fuzzy" | None
    contact: ContactOut | None


class BatchLookupRow(BaseModel):
    row_index: int
    nom: str
    prenom: str
    linkedin_url: str | None
    found: bool
    score: float
    match_type: str | None
    matched_contact_id: uuid.UUID | None


class BatchLookupResult(BaseModel):
    total_rows: int
    found_count: int
    not_found_count: int
    rows: list[BatchLookupRow]
