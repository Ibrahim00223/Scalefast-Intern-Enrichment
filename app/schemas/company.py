import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CompanyCreate(BaseModel):
    company_name: str
    linkedin_url: str | None = None
    linkedin_id: str | None = None
    location: str | None = None
    industry: str | None = None
    number_of_employees: int | None = None


class CompanyUpdate(BaseModel):
    company_name: str | None = None
    linkedin_url: str | None = None
    linkedin_id: str | None = None
    location: str | None = None
    industry: str | None = None
    number_of_employees: int | None = None


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_name: str
    linkedin_url: str | None
    linkedin_id: str | None
    location: str | None
    industry: str | None
    number_of_employees: int | None
    created_at: datetime
    updated_at: datetime


class CompanyListOut(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[CompanyOut]
