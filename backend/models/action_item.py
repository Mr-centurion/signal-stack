from typing import Optional
from datetime import datetime, timezone
from sqlalchemy import String, Text, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.models.base import Base

class ActionItem(Base):
    __tablename__ = "action_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    brief_id: Mapped[Optional[int]] = mapped_column(ForeignKey("briefs.id", ondelete="SET NULL"), nullable=True, index=True)
    
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True) # Strategic rationale for recommendation
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="medium") # low, medium, high
    owner_role: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)       # Suggested owner role (e.g. VP Product, Head of Strategy, VP Marketing)
    due_date: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)          # e.g. "This Friday", "Within 14 days"
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")     # open, in_progress, completed
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    company: Mapped["Company"] = relationship("Company", back_populates="action_items")
    brief: Mapped[Optional["Brief"]] = relationship("Brief", back_populates="action_items")
