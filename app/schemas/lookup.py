import uuid

from pydantic import BaseModel, Field

from app.schemas.lead import LeadOut


class LookupRequest(BaseModel):
    """Paramètres d'une vérification unitaire."""

    first_name: str = Field(..., description="Prénom du contact à rechercher.", examples=["Jean"])
    last_name: str = Field(..., description="Nom de famille du contact à rechercher.", examples=["Dupont"])
    linkedin_url: str | None = Field(
        None,
        description=(
            "URL LinkedIn du contact (optionnel). "
            "Si fournie, une correspondance exacte est d'abord tentée avant la recherche fuzzy. "
            "L'URL est normalisée automatiquement vers `https://www.linkedin.com/in/<slug>`."
        ),
        examples=["https://www.linkedin.com/in/jeandupont"],
    )


class LookupResult(BaseModel):
    """Résultat d'une vérification de lead."""

    found: bool = Field(..., description="Indique si un lead correspondant a été trouvé en base.")
    score: float = Field(
        ...,
        description=(
            "Score de correspondance entre 0.0 et 1.0. "
            "`1.0` = correspondance LinkedIn exacte. "
            "Valeur entre 0 et 1 pour une correspondance fuzzy sur le nom."
        ),
        examples=[0.94],
    )
    match_type: str | None = Field(
        None,
        description=(
            "Méthode de correspondance utilisée : "
            "`linkedin_exact` (URL LinkedIn identique) ou "
            "`name_fuzzy` (correspondance fuzzy sur nom + prénom). "
            "`null` si aucun lead trouvé."
        ),
        examples=["linkedin_exact"],
    )
    lead: LeadOut | None = Field(
        None,
        description="Fiche complète du lead trouvé. `null` si `found` est `false`.",
    )


class BatchLookupRow(BaseModel):
    """Résultat pour une ligne d'un fichier batch."""

    row_index: int = Field(..., description="Numéro de ligne dans le fichier source (commence à 2, en-tête = ligne 1).")
    first_name: str = Field(..., description="Prénom lu dans le fichier source.")
    last_name: str = Field(..., description="Nom lu dans le fichier source.")
    linkedin_url: str | None = Field(None, description="URL LinkedIn lue dans le fichier source.")
    found: bool = Field(..., description="Indique si un lead correspondant a été trouvé.")
    score: float = Field(..., description="Score de correspondance (0.0–1.0).")
    match_type: str | None = Field(None, description="Méthode de correspondance (`linkedin_exact` ou `name_fuzzy`).")
    matched_lead_id: uuid.UUID | None = Field(None, description="UUID du lead trouvé en base.")
