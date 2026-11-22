from typing import Optional, List
from datetime import datetime, timezone
from sqlalchemy import String, Text, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.models.base import Base

class Brief(Base):
    __tablename__ = "briefs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    week_label: Mapped[str] = mapped_column(String(50), nullable=False) # e.g. "Week 47, 2026"
    generated_date: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    
    # 10 Standard Structural Intelligence Sections
    executive_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)      # Section 1: Top 5 by priority (age <= 90d)
    customer_signals: Mapped[str] = mapped_column(Text, default="", nullable=False)       # Section 2: Customer Voice & App Store reviews
    competitor_intelligence: Mapped[str] = mapped_column(Text, default="", nullable=False)# Section 3: Verified competitor movements
    market_intelligence: Mapped[str] = mapped_column(Text, default="", nullable=False)    # Section 4: Regulatory, policy & macro data
    internal_intelligence: Mapped[str] = mapped_column(Text, default="", nullable=False)  # Section 5: Internal business intelligence / uploads
    opportunities: Mapped[str] = mapped_column(Text, default="[]", nullable=False)        # Section 6: At least 3 strategic opportunities
    risks_threats: Mapped[str] = mapped_column(Text, default="", nullable=False)          # Section 7: Strategic risks & threats
    recommended_actions: Mapped[str] = mapped_column(Text, default="[]", nullable=False)  # Section 8: Recommended actions this week with owner roles
    what_we_should_watch: Mapped[str] = mapped_column(Text, default="", nullable=False)   # Section 9: Emerging trends and watchlist items
    source_appendix: Mapped[str] = mapped_column(Text, default="[]", nullable=False)      # Section 10: Complete source provenance table
    
    # Legacy compatibility fields (mapped to maintain SQLite table compatibility)
    customer_updates: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default="")
    competitor_updates: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default="")
    market_updates: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default="")
    internal_updates: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default="")

    # Validation & Multi-Format Exports
    validator_report: Mapped[Optional[str]] = mapped_column(Text, nullable=True) # Signal ID citation & provenance audit
    raw_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)         # Full structured JSON payload
    html_export: Mapped[Optional[str]] = mapped_column(Text, nullable=True)      # Standalone email-ready HTML with inline CSS
    markdown_export: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # GitHub Flavored Markdown document
    
    nothing_happened_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    company: Mapped["Company"] = relationship("Company", back_populates="briefs")
    action_items: Mapped[List["ActionItem"]] = relationship("ActionItem", back_populates="brief", cascade="all, delete-orphan")
