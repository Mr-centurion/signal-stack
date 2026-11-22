from typing import Optional, List
from datetime import datetime
from sqlalchemy import String, Text, ForeignKey, DateTime, Integer, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.models.base import Base, TimestampMixin

class Source(Base, TimestampMixin):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False) # customers, competitors, market, internal
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, default="rss") # rss, news_query, reddit, hn, web_page, internal_upload
    reason: Mapped[str] = mapped_column(Text, nullable=False) # LLM generated rationale why this source matters
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="approved") # discovered | approved | rejected
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    health: Mapped[str] = mapped_column(String(20), nullable=False, default="healthy") # healthy | degraded | dead
    
    # Granular scoring dimensions
    specificity_score: Mapped[float] = mapped_column(Float, default=0.8, nullable=False)
    credibility_score: Mapped[float] = mapped_column(Float, default=0.8, nullable=False)
    recency_score: Mapped[float] = mapped_column(Float, default=0.8, nullable=False)
    overall_score: Mapped[float] = mapped_column(Float, default=0.8, nullable=False)

    http_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    content_length: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_crawled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # HTTP Caching & Deduplication Headers (ETag, If-Modified-Since)
    etag: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_modified_header: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    company: Mapped["Company"] = relationship("Company", back_populates="sources")
    crawl_runs: Mapped[List["CrawlRun"]] = relationship("CrawlRun", back_populates="source")
    documents: Mapped[List["Document"]] = relationship("Document", back_populates="source")
