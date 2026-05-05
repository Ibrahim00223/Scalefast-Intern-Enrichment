import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.interaction import INTERACTION_STATUSES, INTERACTION_TYPES


class InteractionCreate(BaseModel):
    """Données requises pour enregistrer une nouvelle interaction."""

    lead_id: uuid.UUID = Field(..., description="UUID du lead concerné par cette interaction.")
    type: str = Field(
        ...,
        description=f"Canal de l'interaction. Valeurs acceptées : `{'`, `'.join(INTERACTION_TYPES)}`.",
        examples=["appel"],
    )
    status: str = Field(
        ...,
        description=f"Résultat de l'interaction. Valeurs acceptées : `{'`, `'.join(INTERACTION_STATUSES)}`.",
        examples=["NRP 1"],
    )
    timestamp: datetime | None = Field(
        None,
        description="Date et heure de l'interaction (ISO 8601, UTC). Si omis, non renseigné.",
        examples=["2026-05-05T10:30:00Z"],
    )
    infos: str | None = Field(None, description="Notes libres sur l'interaction.", examples=["Messagerie pleine, rappeler demain"])

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in INTERACTION_TYPES:
            raise ValueError(f"type doit être l'un de : {INTERACTION_TYPES}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in INTERACTION_STATUSES:
            raise ValueError(f"status doit être l'un de : {INTERACTION_STATUSES}")
        return v


class InteractionUpdate(BaseModel):
    """Champs modifiables d'une interaction (tous optionnels)."""

    type: str | None = Field(None, description=f"Canal. Valeurs acceptées : `{'`, `'.join(INTERACTION_TYPES)}`.")
    status: str | None = Field(None, description=f"Résultat. Valeurs acceptées : `{'`, `'.join(INTERACTION_STATUSES)}`.")
    timestamp: datetime | None = Field(None, description="Date et heure de l'interaction (ISO 8601).")
    infos: str | None = Field(None, description="Notes libres.")

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str | None) -> str | None:
        if v is not None and v not in INTERACTION_TYPES:
            raise ValueError(f"type doit être l'un de : {INTERACTION_TYPES}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None and v not in INTERACTION_STATUSES:
            raise ValueError(f"status doit être l'un de : {INTERACTION_STATUSES}")
        return v


class InteractionOut(BaseModel):
    """Représentation complète d'une interaction."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Identifiant unique (UUID v4).")
    lead_id: uuid.UUID = Field(..., description="UUID du lead associé.")
    type: str = Field(..., description="Canal : `appel` ou `mail`.")
    status: str = Field(..., description="Résultat de l'interaction.")
    timestamp: datetime | None = Field(None, description="Date et heure de l'interaction.")
    infos: str | None = Field(None, description="Notes libres.")
    created_at: datetime = Field(..., description="Date d'enregistrement en base (UTC).")


class InteractionListOut(BaseModel):
    """Réponse paginée pour la liste des interactions."""

    total: int = Field(..., description="Nombre total d'interactions correspondant aux filtres.")
    page: int = Field(..., description="Numéro de la page courante.")
    page_size: int = Field(..., description="Nombre de résultats par page.")
    items: list[InteractionOut] = Field(..., description="Liste des interactions de la page courante.")
