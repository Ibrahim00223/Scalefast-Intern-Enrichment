import uuid

from pydantic import BaseModel

from app.schemas.lead import LeadOut


class LookupRequest(BaseModel):
    first_name: str
    last_name: str
    linkedin_url: str | None = None


class LookupResult(BaseModel):
    found: bool
    score: float
    match_type: str | None  # "linkedin_exact" | "name_fuzzy" | None
    lead: LeadOut | None


class BatchLookupRow(BaseModel):
    row_index: int
    first_name: str
    last_name: str
    linkedin_url: str | None
    found: bool
    score: float
    match_type: str | None
    matched_lead_id: uuid.UUID | None
