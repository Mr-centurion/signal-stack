import json
from typing import List, Optional, Dict, Any
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.models.base import Base, TimestampMixin

DEFAULT_COMPANY_SETTINGS = {
    "brief_day": "mon",                 # mon, tue, wed, thu, fri, sat, sun
    "brief_time": "06:00",               # HH:MM
    "timezone": "UTC",                   # e.g. UTC, US/Eastern, Europe/London, Asia/Kolkata
    "monitoring_frequency": "daily",      # 6h, 12h, daily, weekly
    "source_refresh_frequency": "daily",  # daily, weekly, monthly
    "monthly_audit_day": 1,              # 1 - 28
    "delivery_email": "",
    "inactivity_threshold_weeks": 4
}

class Company(Base, TimestampMixin):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    website_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    industry: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    intelligence_profile: Mapped[Optional[str]] = mapped_column(Text, nullable=True) # Merged structured profile JSON
    settings_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True) # Schedule & audit configuration

    def get_settings(self) -> Dict[str, Any]:
        """Returns company settings with standard defaults populated."""
        cfg = dict(DEFAULT_COMPANY_SETTINGS)
        if self.settings_json:
            try:
                parsed = json.loads(self.settings_json)
                if isinstance(parsed, dict):
                    cfg.update(parsed)
            except Exception:
                pass
        return cfg

    def set_settings(self, new_settings: Dict[str, Any]) -> None:
        """Updates company settings dictionary and serializes to JSON."""
        current = self.get_settings()
        current.update(new_settings)
        self.settings_json = json.dumps(current)

    # Relationships
    profile_facts: Mapped[List["ProfileFact"]] = relationship("ProfileFact", back_populates="company", cascade="all, delete-orphan")
    interview_qas: Mapped[List["InterviewQA"]] = relationship("InterviewQA", back_populates="company", cascade="all, delete-orphan")
    competitors: Mapped[List["Competitor"]] = relationship("Competitor", back_populates="company", cascade="all, delete-orphan")
    sources: Mapped[List["Source"]] = relationship("Source", back_populates="company", cascade="all, delete-orphan")
    crawl_runs: Mapped[List["CrawlRun"]] = relationship("CrawlRun", back_populates="company", cascade="all, delete-orphan")
    documents: Mapped[List["Document"]] = relationship("Document", back_populates="company", cascade="all, delete-orphan")
    signals: Mapped[List["Signal"]] = relationship("Signal", back_populates="company", cascade="all, delete-orphan")
    briefs: Mapped[List["Brief"]] = relationship("Brief", back_populates="company", cascade="all, delete-orphan")
    action_items: Mapped[List["ActionItem"]] = relationship("ActionItem", back_populates="company", cascade="all, delete-orphan")
