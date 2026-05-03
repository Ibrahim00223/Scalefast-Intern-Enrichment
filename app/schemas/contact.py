import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ContactCreate(BaseModel):
    nom: str
    prenom: str
    linkedin_url: str | None = None
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    job_title: str | None = None
    source: str | None = None


class ContactUpdate(BaseModel):
    nom: str | None = None
    prenom: str | None = None
    linkedin_url: str | None = None
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    job_title: str | None = None
    source: str | None = None


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nom: str
    prenom: str
    linkedin_url: str | None
    email: str | None
    phone: str | None
    company: str | None
    job_title: str | None
    source: str | None
    created_at: datetime
    updated_at: datetime


class ContactListOut(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[ContactOut]
