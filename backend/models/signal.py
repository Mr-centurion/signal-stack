from typing import Optional
from datetime import datetime, timezone
from sqlalchemy import String, Text, ForeignKey, DateTime, Float, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.models.base import Base

class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[Optional[int]] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    source_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"), nullable=True, index=True)
    crawl_run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("crawl_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    
    category: Mapped[str] = mapped_column(String(50), nullable=False) # customers, competitors, market, internal
    status: Mapped[str] = mapped_column(String(30), default="candidate", nullable=False) # candidate | verified | rejected
    headline: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Grounded Evidence (Section 1)
    what_happened: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_snippet: Mapped[str] = mapped_column(Text, nullable=False) # Verbatim from article body
    source_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    publisher_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True) # Direct publisher article URL
    publisher_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True) # E.g. BBC, Times Higher Education
    published_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True) # Real published date (NULL if unknown)
    when_published: Mapped[Optional[str]] = mapped_column(String(50), nullable=True) # Formatted date string or "unknown"
    discovery_date: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    verification_status: Mapped[str] = mapped_column(String(50), default="single_source", nullable=False) # primary_source | corroborated | single_source | unverified
    is_paywalled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Event & Competitor Classification
    linked_competitor: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    event_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True) # regulatory_change, market_data, product_launch, pricing_change, partnership, hiring, funding_or_ma, customer_complaint, other
    customer_quote: Mapped[Optional[str]] = mapped_column(Text, nullable=True) # Customer's own words
    unmet_need: Mapped[Optional[str]] = mapped_column(Text, nullable=True)     # Customer complaint/unmet need
    
    # Development Gate (Phase 3 Rule 1)
    is_discrete_event: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    event_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Strategic Interpretation (Section 1 - Strictly Separated from Facts)
    why_it_matters: Mapped[Optional[str]] = mapped_column(Text, nullable=True) # Must reference profile fact or interview answer
    referenced_profile_fact: Mapped[Optional[str]] = mapped_column(Text, nullable=True) # Specific fact or QA topic cited
    business_area: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    direction: Mapped[str] = mapped_column(String(20), default="neutral", nullable=False) # opportunity | threat | neutral
    urgency: Mapped[str] = mapped_column(String(20), default="monitor", nullable=False)    # immediate | this_quarter | monitor
    what_to_consider: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    verified_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    interpretation: Mapped[str] = mapped_column(Text, nullable=False, default="") # Full analytical breakdown
    
    # Multi-dimensional Scores & Priority Ranking (Section 2)
    source_reliability: Mapped[float] = mapped_column(Float, nullable=False, default=0.5) # 0.0 - 1.0 based on domain hierarchy
    evidence_strength: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)  # 0.0 - 1.0 (0.3 if paywalled/headline only)
    strategic_relevance: Mapped[float] = mapped_column(Float, nullable=False, default=0.5) # 0.0 - 1.0 tied to company profile
    priority_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)      # Weighted priority formula result
    why_important: Mapped[Optional[str]] = mapped_column(Text, nullable=True)              # Top contributing factors breakdown
    
    impact: Mapped[str] = mapped_column(String(20), nullable=False, default="medium") # low, medium, high, critical
    is_background: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False) # True if > 90 days and not ongoing
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    company: Mapped["Company"] = relationship("Company", back_populates="signals")
    document: Mapped[Optional["Document"]] = relationship("Document", back_populates="signals")
    source: Mapped[Optional["Source"]] = relationship("Source")
    crawl_run: Mapped[Optional["CrawlRun"]] = relationship("CrawlRun")

    @property
    def age_days(self) -> Optional[int]:
        if not self.published_date:
            return None
        pub_dt = self.published_date if self.published_date.tzinfo else self.published_date.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - pub_dt
        return max(0, delta.days)

    @property
    def age_display(self) -> str:
        days = self.age_days
        if days is None:
            return "date unknown"
        if days == 0:
            return "today"
        if days == 1:
            return "1 day old"
        return f"{days} days old"
