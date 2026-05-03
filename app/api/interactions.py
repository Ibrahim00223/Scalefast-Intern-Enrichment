import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.interaction import INTERACTION_STATUSES, INTERACTION_TYPES, Interaction
from app.schemas.interaction import InteractionCreate, InteractionListOut, InteractionOut, InteractionUpdate

router = APIRouter(prefix="/interactions", tags=["interactions"])


@router.get("/meta")
async def get_meta():
    return {"types": INTERACTION_TYPES, "statuses": INTERACTION_STATUSES}


@router.post("", response_model=InteractionOut, status_code=201)
async def create_interaction(body: InteractionCreate, db: AsyncSession = Depends(get_db)):
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


@router.get("", response_model=InteractionListOut)
async def list_interactions(
    lead_id: uuid.UUID | None = Query(None),
    type: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
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


@router.get("/{interaction_id}", response_model=InteractionOut)
async def get_interaction(interaction_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    interaction = await db.get(Interaction, interaction_id)
    if not interaction:
        raise HTTPException(status_code=404, detail="Interaction not found.")
    return interaction


@router.patch("/{interaction_id}", response_model=InteractionOut)
async def update_interaction(interaction_id: uuid.UUID, body: InteractionUpdate, db: AsyncSession = Depends(get_db)):
    interaction = await db.get(Interaction, interaction_id)
    if not interaction:
        raise HTTPException(status_code=404, detail="Interaction not found.")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(interaction, field, value)
    await db.commit()
    await db.refresh(interaction)
    return interaction


@router.delete("/{interaction_id}", status_code=204)
async def delete_interaction(interaction_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    interaction = await db.get(Interaction, interaction_id)
    if not interaction:
        raise HTTPException(status_code=404, detail="Interaction not found.")
    await db.delete(interaction)
    await db.commit()
