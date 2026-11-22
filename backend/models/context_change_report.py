from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Text, DateTime, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.models.base import Base

class ContextChangeReport(Base):
    __tablename__ = "context_change_reports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=lambda: datetime.now(timezone.utc), 
        nullable=False
    )
    
    change_type: Mapped[str] = mapped_column(String(100), nullable=False) # 'profile_update', 'interview_update', 'strategic_shift'
    change_description: Mapped[str] = mapped_column(Text, nullable=False)
    
    before_context_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    after_context_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    
    sources_before_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sources_after_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    removed_recommendations_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    added_recommendations_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    competitors_diff_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    metrics_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    # Relationships
    company: Mapped["Company"] = relationship("Company")
