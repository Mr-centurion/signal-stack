from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Text, DateTime, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.models.base import Base

class SourceHealthReport(Base):
    __tablename__ = "source_health_reports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=lambda: datetime.now(timezone.utc), 
        nullable=False
    )
    
    total_sources_audited: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    dead_sources_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    blocked_sources_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_sources_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    inactive_sources_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    declining_sources_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    healthy_sources_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    recommendations_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]") # List of recommendation dicts
    audit_metrics_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}") # Breakdown per source URL

    # Relationships
    company: Mapped["Company"] = relationship("Company")
