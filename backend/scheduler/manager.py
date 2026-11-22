import time
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import zoneinfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import engine, SessionLocal
from backend.models import Company, SchedulerLog
from backend.scheduler.jobs import run_company_weekly_brief_job, run_company_monthly_audit_job

class SchedulerManager:
    """
    Persistent Background Orchestration Engine:
    - Backed by SQLite SQLAlchemyJobStore so all jobs survive process restarts.
    - Manages Per-Company Weekly Intelligence Brief jobs.
    - Manages Per-Company Monthly Signal Stack Audit jobs.
    - Dynamic rescheduling when company settings change.
    - Manual immediate triggers from UI and REST API.
    - Robust exception shielding and full telemetry logging in SchedulerLog.
    """
    def __init__(self):
        jobstores = {
            "default": SQLAlchemyJobStore(engine=engine)
        }
        self.scheduler = AsyncIOScheduler(jobstores=jobstores)

    def start(self):
        """Starts the persistent scheduler and synchronizes jobs for all companies."""
        if not self.scheduler.running:
            self.scheduler.start()
            self.sync_all_company_jobs()

    def shutdown(self):
        """Gracefully halts scheduler execution."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def sync_all_company_jobs(self):
        """Ensures every company in the database has registered weekly and monthly jobs."""
        db: Session = SessionLocal()
        try:
            companies = db.query(Company).all()
            for comp in companies:
                self.reschedule_company_jobs(comp.id, db=db)
        except Exception as e:
            print(f"[SCHEDULER SYNC WARNING] Failed to sync company jobs: {e}")
        finally:
            db.close()

    def reschedule_company_jobs(self, company_id: int, db: Optional[Session] = None):
        """
        Reads company settings from DB and schedules:
        1. Weekly Intelligence Brief job (per configured day, time, and timezone).
        2. Monthly Signal Stack Audit job (per configured day of month and timezone).
        """
        should_close = False
        if not db:
            db = SessionLocal()
            should_close = True

        try:
            company = db.query(Company).filter_by(id=company_id).first()
            if not company:
                return

            cfg = company.get_settings()
            b_day = cfg.get("brief_day", "mon").lower()
            b_time = cfg.get("brief_time", "06:00")
            tz_str = cfg.get("timezone", "UTC")
            audit_day = int(cfg.get("monthly_audit_day", 1))

            # Parse hour and minute
            try:
                parts = b_time.split(":")
                hour = int(parts[0])
                minute = int(parts[1]) if len(parts) > 1 else 0
            except Exception:
                hour, minute = 6, 0

            # Safe timezone parse
            try:
                tz = zoneinfo.ZoneInfo(tz_str)
            except Exception:
                tz = zoneinfo.ZoneInfo("UTC")

            # 1. Schedule Weekly Intelligence Brief Job
            weekly_job_id = f"weekly_brief_{company_id}"
            self.scheduler.add_job(
                run_company_weekly_brief_job,
                CronTrigger(day_of_week=b_day, hour=hour, minute=minute, timezone=tz),
                args=[company_id],
                id=weekly_job_id,
                replace_existing=True,
                name=f"Weekly Brief: {company.name}"
            )

            # 2. Schedule Monthly Signal Stack Audit Job
            monthly_job_id = f"monthly_audit_{company_id}"
            # Ensure day is between 1 and 28 to avoid month-end rollover issues
            valid_day = max(1, min(28, audit_day))
            self.scheduler.add_job(
                run_company_monthly_audit_job,
                CronTrigger(day=valid_day, hour=hour, minute=minute, timezone=tz),
                args=[company_id],
                id=monthly_job_id,
                replace_existing=True,
                name=f"Monthly Audit: {company.name}"
            )

            print(f"[SCHEDULER] Rescheduled jobs for {company.name} (Weekly: {b_day} {hour:02d}:{minute:02d} {tz_str}, Monthly: Day {valid_day})")
        except Exception as e:
            print(f"[SCHEDULER RESCHEDULE ERROR] Company #{company_id}: {e}")
        finally:
            if should_close:
                db.close()

    async def trigger_weekly_brief_now(self, company_id: int) -> SchedulerLog:
        """Manually triggers the weekly intelligence brief job immediately."""
        return await run_company_weekly_brief_job(company_id)

    async def trigger_monthly_audit_now(self, company_id: int) -> SchedulerLog:
        """Manually triggers the monthly source audit job immediately."""
        return await run_company_monthly_audit_job(company_id)

    def list_jobs(self) -> List[Dict[str, Any]]:
        """Returns structured metadata of all active registered persistent jobs."""
        jobs = []
        for j in self.scheduler.get_jobs():
            next_run = getattr(j, "next_run_time", None)
            jobs.append({
                "id": j.id,
                "name": j.name,
                "next_run_time": next_run.isoformat() if next_run else None,
                "trigger": str(j.trigger),
                "args": j.args
            })
        return jobs

scheduler_manager = SchedulerManager()
