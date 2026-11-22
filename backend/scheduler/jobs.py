import time
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models import Company, SchedulerLog
from backend.crawler.engine import crawl_service
from backend.services.brief_service import brief_service
from backend.services.email_delivery_service import email_delivery_service
from backend.services.monthly_audit_service import monthly_audit_service

async def run_company_weekly_brief_job(company_id: int, scheduled_for: Optional[datetime] = None) -> SchedulerLog:
    """
    Weekly Intelligence Brief job per company:
    1. Crawls approved sources and detects changes.
    2. Analyzes and ranks verified signals.
    3. Generates 10-section Monday Brief with provenance.
    4. Delivers via SMTP if configured, otherwise logs 'delivery skipped: SMTP not configured'.
    5. Records full audit entry in SchedulerLog.
    Never raises an uncaught exception so the scheduler survives failures.
    """
    sched_time = scheduled_for or datetime.now(timezone.utc)
    start_time = datetime.now(timezone.utc)
    t0 = time.time()
    
    db: Session = SessionLocal()
    company_name = f"Company #{company_id}"
    log_status = "success"
    err_msg = None
    records_count = 0
    details = ""

    try:
        company = db.query(Company).filter_by(id=company_id).first()
        if not company:
            raise ValueError(f"Company ID {company_id} not found in database.")
        company_name = company.name

        # 1. Run crawl over approved sources
        crawl_run = await crawl_service.crawl_company(db, company_id)
        records_count = (crawl_run.items_new or 0) + (crawl_run.items_changed or 0)

        # 2. Generate and persist Monday Brief
        brief = await brief_service.generate_monday_brief(db, company_id)

        # 3. Handle Delivery
        cfg = company.get_settings()
        recipient_override = cfg.get("delivery_email")
        delivery_res = email_delivery_service.send_brief_email(
            company_name=company.name,
            week_label=brief.week_label,
            html_content=brief.html_export,
            recipient_override=recipient_override
        )

        details = (
            f"Brief #{brief.id} generated successfully for {company_name}. "
            f"CrawlRun #{crawl_run.id} collected {records_count} records. "
            f"Delivery status: {delivery_res.get('status')} ({delivery_res.get('reason') or delivery_res.get('details') or 'ok'})."
        )
    except Exception as e:
        log_status = "failed"
        err_msg = str(e)
        details = f"Job execution failed: {err_msg}"
        print(f"[SCHEDULER JOB ERROR] Weekly brief failed for {company_name}: {err_msg}")
    finally:
        finish_time = datetime.now(timezone.utc)
        duration = int((time.time() - t0) * 1000)
        
        log_entry = SchedulerLog(
            job="weekly_intelligence_brief",
            job_id=f"weekly_brief_{company_id}",
            company=company_name,
            company_id=company_id,
            scheduled_for=sched_time,
            started=start_time,
            finished=finish_time,
            status=log_status,
            error=err_msg,
            records_collected=records_count,
            run_at=start_time,
            duration_ms=duration,
            details=details
        )
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)
        db.close()
        return log_entry

async def run_company_monthly_audit_job(company_id: int, scheduled_for: Optional[datetime] = None) -> SchedulerLog:
    """
    Monthly Signal Stack Audit job per company:
    1. Audits sources for dead URLs, duplicates, inactive feeds, and declining relevance.
    2. Re-runs autonomous discovery to propose fresh candidate sources.
    3. Persists SourceHealthReport with recommendations (never auto-deletes).
    4. Records execution log in SchedulerLog.
    Never raises an uncaught exception.
    """
    sched_time = scheduled_for or datetime.now(timezone.utc)
    start_time = datetime.now(timezone.utc)
    t0 = time.time()
    
    db: Session = SessionLocal()
    company_name = f"Company #{company_id}"
    log_status = "success"
    err_msg = None
    records_count = 0
    details = ""

    try:
        company = db.query(Company).filter_by(id=company_id).first()
        if not company:
            raise ValueError(f"Company ID {company_id} not found in database.")
        company_name = company.name

        # Execute monthly audit
        report = await monthly_audit_service.run_audit(db, company_id)
        records_count = report.total_sources_audited
        details = f"Health Report #{report.id}: {report.summary}"
    except Exception as e:
        log_status = "failed"
        err_msg = str(e)
        details = f"Audit execution failed: {err_msg}"
        print(f"[SCHEDULER JOB ERROR] Monthly audit failed for {company_name}: {err_msg}")
    finally:
        finish_time = datetime.now(timezone.utc)
        duration = int((time.time() - t0) * 1000)
        
        log_entry = SchedulerLog(
            job="monthly_signal_audit",
            job_id=f"monthly_audit_{company_id}",
            company=company_name,
            company_id=company_id,
            scheduled_for=sched_time,
            started=start_time,
            finished=finish_time,
            status=log_status,
            error=err_msg,
            records_collected=records_count,
            run_at=start_time,
            duration_ms=duration,
            details=details
        )
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)
        db.close()
        return log_entry
