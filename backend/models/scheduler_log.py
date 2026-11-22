from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Text, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column
from backend.models.base import Base

class SchedulerLog(Base):
    """
    Audit log for scheduled jobs.
    Tracks execution status, timings, errors, and collected records.
    """
    __tablename__ = "scheduler_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job: Mapped[str] = mapped_column(String(100), nullable=False, index=True, default="weekly_intelligence_brief")
    job_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True) # for backwards compatibility
    company: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    company_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    scheduled_for: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    started: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="success") # success | failed | skipped
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    records_collected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Backwards compatibility fields
    run_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=False, default="")
