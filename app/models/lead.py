import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    last_name: Mapped[str] = mapped_column(Text, nullable=False)
    first_name: Mapped[str] = mapped_column(Text, nullable=False)
    # GENERATED columns — managed by PostgreSQL, declared here for read access
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    last_name_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    first_name_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    company_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True)
    company_name: Mapped[str | None] = mapped_column(Text, nullable=True)  # denormalized fallback
    job_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    linkedin_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    company: Mapped["Company | None"] = relationship("Company", back_populates="leads")
    interactions: Mapped[list["Interaction"]] = relationship("Interaction", back_populates="lead", lazy="select")
