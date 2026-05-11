import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.user import USER_ROLES


class UserCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    email: str = Field(..., min_length=3, max_length=320)
    role: str = Field(default="readonly", pattern="^(admin|agent|readonly)$")
    is_active: bool = True


class UserRoleUpdate(BaseModel):
    role: str = Field(..., pattern="^(admin|agent|readonly)$", description=f"Valeurs autorisees: {', '.join(USER_ROLES)}")


class UserStatusUpdate(BaseModel):
    is_active: bool


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    role: str
    is_active: bool
    google_sub: str | None = None
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None


class UserListOut(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[UserOut]
