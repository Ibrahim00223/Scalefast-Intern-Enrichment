import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CompanyCreate(BaseModel):
    """Données requises pour créer une nouvelle entreprise."""

    company_name: str = Field(..., description="Nom de l'entreprise.", examples=["Scalefast"])
    linkedin_url: str | None = Field(
        None,
        description="URL de la page entreprise LinkedIn. Normalisée automatiquement. Doit être unique.",
        examples=["https://www.linkedin.com/company/scalefast"],
    )
    linkedin_id: str | None = Field(None, description="Identifiant numérique LinkedIn de l'entreprise.", examples=["12345678"])
    location: str | None = Field(None, description="Localisation du siège social.", examples=["Madrid, Espagne"])
    industry: str | None = Field(None, description="Secteur d'activité.", examples=["E-commerce / SaaS"])
    number_of_employees: int | None = Field(None, description="Effectif approximatif.", examples=[150], ge=0)


class CompanyUpdate(BaseModel):
    """Champs modifiables d'une entreprise (tous optionnels)."""

    company_name: str | None = Field(None, description="Nom de l'entreprise.")
    linkedin_url: str | None = Field(None, description="URL LinkedIn (normalisée automatiquement).")
    linkedin_id: str | None = Field(None, description="Identifiant numérique LinkedIn.")
    location: str | None = Field(None, description="Localisation.")
    industry: str | None = Field(None, description="Secteur d'activité.")
    number_of_employees: int | None = Field(None, description="Effectif.", ge=0)


class CompanyOut(BaseModel):
    """Représentation complète d'une entreprise retournée par l'API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Identifiant unique (UUID v4).")
    company_name: str = Field(..., description="Nom de l'entreprise.")
    linkedin_url: str | None = Field(None, description="URL normalisée de la page LinkedIn.")
    linkedin_id: str | None = Field(None, description="Identifiant numérique LinkedIn.")
    location: str | None = Field(None, description="Localisation.")
    industry: str | None = Field(None, description="Secteur d'activité.")
    number_of_employees: int | None = Field(None, description="Effectif.")
    created_at: datetime = Field(..., description="Date de création (UTC).")
    updated_at: datetime = Field(..., description="Date de dernière modification (UTC).")


class CompanyListOut(BaseModel):
    """Réponse paginée pour la liste des entreprises."""

    total: int = Field(..., description="Nombre total d'entreprises correspondant aux filtres.")
    page: int = Field(..., description="Numéro de la page courante.")
    page_size: int = Field(..., description="Nombre de résultats par page.")
    items: list[CompanyOut] = Field(..., description="Liste des entreprises de la page courante.")
