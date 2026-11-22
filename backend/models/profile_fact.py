from typing import Literal, Optional
from sqlalchemy import String, Text, ForeignKey, Float, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.models.base import Base, TimestampMixin

class ProfileFact(Base, TimestampMixin):
    __tablename__ = "profile_facts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False) # customers, competitors, market, internal
    field_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True) # business_lines, customer_segments, etc.
    fact_type: Mapped[str] = mapped_column(String(20), nullable=False, default="fact") # fact | assumption
    text: Mapped[str] = mapped_column(Text, nullable=False)
    source_origin: Mapped[str] = mapped_column(String(50), default="research", nullable=False) # research | interview | edited
    evidence_snippet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(512), nullable=True) # e.g., "Founder Interview", "Website crawl", etc.
    confidence_score: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_anchored: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    company: Mapped["Company"] = relationship("Company", back_populates="profile_facts")
