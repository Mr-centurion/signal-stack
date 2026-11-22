from typing import Optional, List
from datetime import datetime, timezone
from sqlalchemy import String, Text, ForeignKey, DateTime, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.models.base import Base

class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), nullable=True, index=True)
    crawl_run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("crawl_runs.id", ondelete="SET NULL"), nullable=True)

    url: Mapped[str] = mapped_column(String(1024), nullable=False, index=True)
    canonical_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(50), default="market", nullable=False) # customers, competitors, market, internal
    document_type: Mapped[str] = mapped_column(String(50), default="web_page", nullable=False) # web_page, internal_upload, feed_item
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True) # SHA-256
    simhash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True) # MinHash/Shingle representation for near-dedup
    title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True) # Filename, byte size, sheet name, diff metadata
    published_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    is_snapshot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    duplicate_of_id: Mapped[Optional[int]] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    company: Mapped["Company"] = relationship("Company", back_populates="documents")
    source: Mapped[Optional["Source"]] = relationship("Source", back_populates="documents")
    crawl_run: Mapped[Optional["CrawlRun"]] = relationship("CrawlRun", back_populates="documents")
    signals: Mapped[List["Signal"]] = relationship("Signal", back_populates="document")
