import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.company import CompanyOut


class LeadCreate(BaseModel):
    last_name: str
    first_name: str
    company_id: uuid.UUID | None = None
    company_name: str | None = None
    job_title: str | None = None
    location: str | None = None
    linkedin_id: str | None = None
    linkedin_url: str | None = None


class LeadUpdate(BaseModel):
    last_name: str | None = None
    first_name: str | None = None
    company_id: uuid.UUID | None = None
    company_name: str | None = None
    job_title: str | None = None
    location: str | None = None
    linkedin_id: str | None = None
    linkedin_url: str | None = None


class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    last_name: str
    first_name: str
    full_name: str
    company_id: uuid.UUID | None
    company_name: str | None
    job_title: str | None
    location: str | None
    linkedin_id: str | None
    linkedin_url: str | None
    created_at: datetime
    updated_at: datetime


class LeadWithCompanyOut(LeadOut):
    company: CompanyOut | None = None


class LeadListOut(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[LeadOut]
