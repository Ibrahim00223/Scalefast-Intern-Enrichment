import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.interaction import INTERACTION_STATUSES, INTERACTION_TYPES, Interaction
from app.schemas.interaction import InteractionCreate, InteractionListOut, InteractionOut, InteractionUpdate

router = APIRouter(prefix="/interactions", tags=["interactions"])


@router.get(
    "/meta",
    summary="Valeurs valides pour type et statut",
)
async def get_meta():
    """
    Retourne les listes de valeurs autorisées pour les champs `type` et `status`.

    Utile pour alimenter dynamiquement des listes déroulantes dans l'interface.

    ### Exemple de réponse
    ```json
    {
      "types": ["appel", "mail"],
      "statuses": ["NRP 1", "NRP 2", "NRP 3", "NRP 4", "Messagerie",
                   "Numéro Invalide", "A Répondu", "Mauvais Interlocuteur",
                   "Intérêts pour plus tard"]
    }
    ```
    """
    return {"types": INTERACTION_TYPES, "statuses": INTERACTION_STATUSES}


@router.post(
    "",
    response_model=InteractionOut,
    status_code=201,
    summary="Enregistrer une interaction",
    responses={
        201: {"description": "Interaction créée."},
        422: {"description": "Type ou statut invalide."},
    },
)
async def create_interaction(body: InteractionCreate, db: AsyncSession = Depends(get_db)):
    """
    Enregistre une nouvelle interaction commerciale liée à un lead.

    - **`type`** doit être `appel` ou `mail`.
    - **`status`** doit être l'une des valeurs retournées par `GET /interactions/meta`.
    - **`timestamp`** est optionnel ; si omis, la date n'est pas renseignée.
    - **`infos`** est un champ texte libre pour les notes.
    """
    interaction = Interaction(
        lead_id=body.lead_id,
        type=body.type,
        status=body.status,
        timestamp=body.timestamp,
        infos=body.infos,
    )
    db.add(interaction)
    await db.commit()
    await db.refresh(interaction)
    return interaction


@router.get(
    "",
    response_model=InteractionListOut,
    summary="Lister les interactions",
)
async def list_interactions(
    lead_id: uuid.UUID | None = Query(None, description="Filtrer par UUID de lead."),
    type: str | None = Query(None, description="Filtrer par type : `appel` ou `mail`."),
    status: str | None = Query(None, description="Filtrer par statut (valeur exacte)."),
    page: int = Query(1, ge=1, description="Numéro de page."),
    page_size: int = Query(20, ge=1, le=100, description="Résultats par page (max 100)."),
    db: AsyncSession = Depends(get_db),
):
    """
    Retourne la liste paginée des interactions, triées par date de création décroissante.

    Tous les filtres sont optionnels et cumulables.
    """
    stmt = select(Interaction)
    if lead_id:
        stmt = stmt.where(Interaction.lead_id == lead_id)
    if type:
        stmt = stmt.where(Interaction.type == type)
    if status:
        stmt = stmt.where(Interaction.status == status)

    stmt = stmt.order_by(Interaction.created_at.desc())
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    items = (await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return InteractionListOut(total=total, page=page, page_size=page_size, items=list(items))


@router.get(
    "/{interaction_id}",
    response_model=InteractionOut,
    summary="Récupérer une interaction par ID",
    responses={
        200: {"description": "Fiche complète de l'interaction."},
        404: {"description": "Interaction introuvable."},
    },
)
async def get_interaction(interaction_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Retourne le détail d'une interaction à partir de son UUID."""
    interaction = await db.get(Interaction, interaction_id)
    if not interaction:
        raise HTTPException(status_code=404, detail="Interaction introuvable.")
    return interaction


@router.patch(
    "/{interaction_id}",
    response_model=InteractionOut,
    summary="Mettre à jour une interaction",
    responses={
        200: {"description": "Interaction mise à jour."},
        404: {"description": "Interaction introuvable."},
        422: {"description": "Type ou statut invalide."},
    },
)
async def update_interaction(interaction_id: uuid.UUID, body: InteractionUpdate, db: AsyncSession = Depends(get_db)):
    """Met à jour partiellement une interaction (seuls les champs fournis sont modifiés)."""
    interaction = await db.get(Interaction, interaction_id)
    if not interaction:
        raise HTTPException(status_code=404, detail="Interaction introuvable.")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(interaction, field, value)
    await db.commit()
    await db.refresh(interaction)
    return interaction


@router.delete(
    "/{interaction_id}",
    status_code=204,
    summary="Supprimer une interaction",
    responses={
        204: {"description": "Interaction supprimée."},
        404: {"description": "Interaction introuvable."},
    },
)
async def delete_interaction(interaction_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Supprime définitivement une interaction."""
    interaction = await db.get(Interaction, interaction_id)
    if not interaction:
        raise HTTPException(status_code=404, detail="Interaction introuvable.")
    await db.delete(interaction)
    await db.commit()
