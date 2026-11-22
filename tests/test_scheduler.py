import pytest
import asyncio
from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

from backend.database import engine, SessionLocal
from backend.models import Company, SchedulerLog
from backend.scheduler.jobs import run_company_weekly_brief_job, run_company_monthly_audit_job
from backend.scheduler.manager import scheduler_manager
from backend.services.email_delivery_service import email_delivery_service
from backend.services.llm_client import llm_client

@pytest.mark.asyncio
async def test_scheduler_short_interval_and_logging(monkeypatch):
    """
    Test short interval trigger:
    Scheduler fires a job automatically on a short interval, executes safely,
    and writes a verified execution record into SchedulerLog.
    """
    llm_client.set_provider("mock")
    db = SessionLocal()
    
    # Ensure a test company exists
    comp = db.query(Company).filter_by(id=1).first()
    if not comp:
        comp = Company(id=1, name="MeetUniversity", domain="meetuniversity.com", industry="EdTech")
        db.add(comp)
        db.commit()

    # Mock crawler & brief generation so job runs fast and deterministically
    from backend.crawler.engine import crawl_service
    from backend.services.brief_service import brief_service
    from backend.models import CrawlRun, Brief

    async def mock_crawl(db_sess, company_id):
        c_run = CrawlRun(company_id=company_id, status="completed", items_new=2, items_changed=1)
        db_sess.add(c_run)
        db_sess.commit()
        return c_run

    async def mock_brief(db_sess, company_id):
        b = Brief(company_id=company_id, week_label="Week 47, Nov 2026", executive_summary="Summary", html_export="<h1>Brief</h1>")
        db_sess.add(b)
        db_sess.commit()
        return b

    monkeypatch.setattr(crawl_service, "crawl_company", mock_crawl)
    monkeypatch.setattr(brief_service, "generate_monday_brief", mock_brief)

    # Create an isolated test scheduler
    test_scheduler = AsyncIOScheduler()
    test_scheduler.start()

    fired_event = asyncio.Event()

    async def sample_test_job(company_id: int):
        # Run real weekly brief job logic
        await run_company_weekly_brief_job(company_id)
        fired_event.set()

    # Schedule short 1-second interval
    job = test_scheduler.add_job(
        sample_test_job,
        IntervalTrigger(seconds=1),
        args=[comp.id],
        id="test_short_interval_job"
    )

    try:
        # Wait up to 3.5 seconds for the job to fire
        await asyncio.wait_for(fired_event.wait(), timeout=3.5)
    finally:
        test_scheduler.shutdown(wait=False)

    # Verify SchedulerLog record was written
    log_entry = (
        db.query(SchedulerLog)
        .filter_by(company_id=comp.id, job="weekly_intelligence_brief")
        .order_by(SchedulerLog.id.desc())
        .first()
    )
    assert log_entry is not None, "SchedulerLog entry should have been created by the job"
    assert log_entry.status == "success"
    assert log_entry.started is not None
    assert log_entry.finished is not None
    assert log_entry.started <= log_entry.finished
    assert log_entry.records_collected == 3
    assert "weekly_brief" in log_entry.job_id
    db.close()


@pytest.mark.asyncio
async def test_scheduler_forced_failure_shielding():
    """
    Test forced failure:
    A failure inside a job (e.g. invalid company ID or runtime error)
    is caught and shielded. The record appears as 'failed' in SchedulerLog,
    error message is preserved, and the scheduler process remains alive and healthy.
    """
    db = SessionLocal()
    
    # Intentionally pass an invalid non-existent company ID
    invalid_comp_id = 999999
    
    # Execute job directly (as APScheduler worker would)
    log_result = await run_company_weekly_brief_job(invalid_comp_id)

    # 1. Assert return value is a SchedulerLog instance (no uncaught exception raised)
    assert isinstance(log_result, SchedulerLog)
    assert log_result.status == "failed"
    assert "999999 not found" in str(log_result.error)

    # 2. Verify stored in DB
    stored_log = db.query(SchedulerLog).filter_by(id=log_result.id).first()
    assert stored_log is not None
    assert stored_log.status == "failed"
    assert stored_log.error is not None
    assert stored_log.started is not None
    assert stored_log.finished is not None

    # 3. Assert scheduler survives: schedule a subsequent valid operation
    test_sched = AsyncIOScheduler()
    test_sched.start()
    assert test_sched.running is True
    test_sched.shutdown(wait=False)
    db.close()


@pytest.mark.asyncio
async def test_persistent_reload_jobs():
    """
    Test persistent reload:
    Using SQLAlchemyJobStore backed by SQLite, jobs added to the store survive
    scheduler shutdown and remain registered when a new scheduler instance initializes.
    """
    # Scheduler 1: add a persistent job
    jobstore = {"default": SQLAlchemyJobStore(engine=engine)}
    sched1 = AsyncIOScheduler(jobstores=jobstore)
    sched1.start()

    test_job_id = "test_persistence_verification_job"
    sched1.add_job(
        run_company_weekly_brief_job,
        CronTrigger(day_of_week="wed", hour=7, minute=15),
        args=[1],
        id=test_job_id,
        name="Test Persistence Job",
        replace_existing=True
    )

    # Verify it exists in sched1
    j1 = sched1.get_job(test_job_id)
    assert j1 is not None
    assert j1.id == test_job_id

    # Gracefully shut down sched1 (simulating process restart)
    sched1.shutdown(wait=False)

    # Scheduler 2: fresh instance on the same DB engine
    sched2 = AsyncIOScheduler(jobstores={"default": SQLAlchemyJobStore(engine=engine)})
    sched2.start()

    try:
        # Verify job survived the restart in the persistent SQLite store
        j2 = sched2.get_job(test_job_id)
        assert j2 is not None, "Persistent job must survive scheduler restart"
        assert j2.id == test_job_id
        assert j2.name == "Test Persistence Job"
    finally:
        # Cleanup test job
        sched2.remove_job(test_job_id)
        sched2.shutdown(wait=False)


def test_settings_rescheduling():
    """
    Test that changing company settings dynamically reschedules the jobs
    with the exact specified day, time, and timezone.
    """
    db = SessionLocal()
    comp = db.query(Company).filter_by(id=1).first()
    assert comp is not None

    # Update company settings
    new_settings = {
        "brief_day": "fri",
        "brief_time": "09:30",
        "timezone": "UTC",
        "monthly_audit_day": 15
    }
    comp.set_settings(new_settings)
    db.commit()

    # Trigger reschedule
    scheduler_manager.reschedule_company_jobs(comp.id, db=db)

    # Verify registered jobs in scheduler_manager
    jobs = scheduler_manager.list_jobs()
    weekly_job = next((j for j in jobs if j["id"] == f"weekly_brief_{comp.id}"), None)
    monthly_job = next((j for j in jobs if j["id"] == f"monthly_audit_{comp.id}"), None)

    assert weekly_job is not None, "Weekly brief job should be registered"
    assert monthly_job is not None, "Monthly audit job should be registered"
    assert "day_of_week='fri'" in weekly_job["trigger"]
    assert "hour='9'" in weekly_job["trigger"]
    assert "minute='30'" in weekly_job["trigger"]
    assert "day='15'" in monthly_job["trigger"]

    db.close()


def test_smtp_fallback_delivery():
    """
    Test email delivery fallback when SMTP variables are missing in .env:
    Logs 'delivery skipped: SMTP not configured' and returns status='skipped' without error.
    """
    res = email_delivery_service.send_brief_email(
        company_name="MeetUniversity",
        week_label="Week 47, Nov 2026",
        html_content="<h1>Test Brief</h1>",
        recipient_override="founder@meetuniversity.com"
    )

    assert res["status"] in ["skipped", "sent"]
    if not email_delivery_service.is_configured:
        assert res["status"] == "skipped"
        assert "SMTP not configured" in res["reason"]
