import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.company import CompanyOut


class LeadCreate(BaseModel):
    """Données requises pour créer un nouveau lead."""

    last_name: str = Field(..., description="Nom de famille.", examples=["Dupont"])
    first_name: str = Field(..., description="Prénom.", examples=["Jean"])
    company_id: uuid.UUID | None = Field(None, description="UUID de l'entreprise associée (optionnel).")
    company_name: str | None = Field(
        None,
        description="Nom de l'entreprise en texte libre (dénormalisé). Utilisé si `company_id` n'est pas renseigné.",
        examples=["Scalefast"],
    )
    job_title: str | None = Field(None, description="Intitulé du poste.", examples=["GTM Engineer"])
    location: str | None = Field(None, description="Localisation géographique.", examples=["Paris, France"])
    linkedin_id: str | None = Field(None, description="Identifiant numérique LinkedIn.", examples=["123456789"])
    linkedin_url: str | None = Field(
        None,
        description=(
            "URL du profil LinkedIn. Normalisée automatiquement vers "
            "`https://www.linkedin.com/in/<slug>`. Doit être unique en base."
        ),
        examples=["https://www.linkedin.com/in/jeandupont"],
    )


class LeadUpdate(BaseModel):
    """Champs modifiables d'un lead (tous optionnels — seuls les champs fournis sont mis à jour)."""

    last_name: str | None = Field(None, description="Nom de famille.")
    first_name: str | None = Field(None, description="Prénom.")
    company_id: uuid.UUID | None = Field(None, description="UUID de l'entreprise associée.")
    company_name: str | None = Field(None, description="Nom de l'entreprise (texte libre).")
    job_title: str | None = Field(None, description="Intitulé du poste.")
    location: str | None = Field(None, description="Localisation géographique.")
    linkedin_id: str | None = Field(None, description="Identifiant numérique LinkedIn.")
    linkedin_url: str | None = Field(None, description="URL du profil LinkedIn (normalisée automatiquement).")


class LeadOut(BaseModel):
    """Représentation complète d'un lead retourné par l'API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Identifiant unique du lead (UUID v4).")
    last_name: str = Field(..., description="Nom de famille (valeur originale, non normalisée).")
    first_name: str = Field(..., description="Prénom (valeur originale, non normalisée).")
    full_name: str = Field(..., description="Nom complet calculé automatiquement par PostgreSQL (`first_name + last_name`).")
    company_id: uuid.UUID | None = Field(None, description="UUID de l'entreprise associée.")
    company_name: str | None = Field(None, description="Nom de l'entreprise (texte libre dénormalisé).")
    job_title: str | None = Field(None, description="Intitulé du poste.")
    location: str | None = Field(None, description="Localisation géographique.")
    linkedin_id: str | None = Field(None, description="Identifiant numérique LinkedIn.")
    linkedin_url: str | None = Field(None, description="URL normalisée du profil LinkedIn.")
    created_at: datetime = Field(..., description="Date de création de l'enregistrement (UTC).")
    updated_at: datetime = Field(..., description="Date de dernière modification (UTC).")


class LeadWithCompanyOut(LeadOut):
    """Lead avec la fiche entreprise associée incluse."""

    company: CompanyOut | None = Field(None, description="Fiche complète de l'entreprise associée.")


class LeadWithCompanyAndInteractions(LeadWithCompanyOut):
    """Lead avec la fiche entreprise associée et toutes les interactions incluses."""

    interactions: list[InteractionOut] = []


class LeadListOut(BaseModel):
    """Réponse paginée pour la liste des leads."""

    total: int = Field(..., description="Nombre total de leads correspondant aux filtres.")
    page: int = Field(..., description="Numéro de la page courante.")
    page_size: int = Field(..., description="Nombre de résultats par page.")
    items: list[LeadOut] = Field(..., description="Liste des leads de la page courante.")
