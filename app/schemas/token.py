import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class APITokenCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    expires_in_days: int | None = Field(None, ge=1, le=365)


class APITokenCreateOut(BaseModel):
    token: str
    token_prefix: str
    expires_at: datetime | None = None


class APITokenOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    token_prefix: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None
