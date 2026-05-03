import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    nom: Mapped[str] = mapped_column(Text, nullable=False)
    prenom: Mapped[str] = mapped_column(Text, nullable=False)
    # nom_normalized and prenom_normalized are GENERATED columns in PostgreSQL.
    # We declare them as server_default so SQLAlchemy doesn't try to insert them.
    nom_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    prenom_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    linkedin_url: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    company: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
