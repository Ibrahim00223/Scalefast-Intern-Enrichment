import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

INTERACTION_TYPES = ["appel", "mail"]

INTERACTION_STATUSES = [
    "NRP 1",
    "NRP 2",
    "NRP 3",
    "NRP 4",
    "Messagerie",
    "Numéro Invalide",
    "A Répondu",
    "Mauvais Interlocuteur",
    "Intérêts pour plus tard",
]


class Interaction(Base):
    __tablename__ = "interactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)       # appel | mail
    status: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    infos: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lead: Mapped["Lead"] = relationship("Lead", back_populates="interactions")
