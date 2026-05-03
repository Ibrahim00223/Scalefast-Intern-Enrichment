import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.interaction import INTERACTION_STATUSES, INTERACTION_TYPES


class InteractionCreate(BaseModel):
    lead_id: uuid.UUID
    type: str
    status: str
    timestamp: datetime | None = None
    infos: str | None = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in INTERACTION_TYPES:
            raise ValueError(f"type must be one of {INTERACTION_TYPES}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in INTERACTION_STATUSES:
            raise ValueError(f"status must be one of {INTERACTION_STATUSES}")
        return v


class InteractionUpdate(BaseModel):
    type: str | None = None
    status: str | None = None
    timestamp: datetime | None = None
    infos: str | None = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str | None) -> str | None:
        if v is not None and v not in INTERACTION_TYPES:
            raise ValueError(f"type must be one of {INTERACTION_TYPES}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None and v not in INTERACTION_STATUSES:
            raise ValueError(f"status must be one of {INTERACTION_STATUSES}")
        return v


class InteractionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lead_id: uuid.UUID
    type: str
    status: str
    timestamp: datetime | None
    infos: str | None
    created_at: datetime


class InteractionListOut(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[InteractionOut]
