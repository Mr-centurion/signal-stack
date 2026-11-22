from datetime import datetime, timezone
from backend.models import (
    Company, ProfileFact, InterviewQA, Source, CrawlRun, Document,
    Signal, Brief, ActionItem, SchedulerLog, Setting
)

def test_models_creation_and_relations(db_session):
    # 1. Company
    company = Company(
        name="Nova Robotics",
        domain="novarobotics.example.com",
        industry="Autonomous Robotics",
        description="Warehouse automation robotics manufacturer."
    )
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)
    assert company.id is not None
    assert company.created_at is not None

    # 2. ProfileFact
    fact = ProfileFact(
        company_id=company.id,
        category="customers",
        fact_type="fact",
        text="Target customer segment is tier-1 3PL operators.",
        source="Founder Intake",
        confidence_score=1.0
    )
    db_session.add(fact)

    # 3. InterviewQA
    qa = InterviewQA(
        company_id=company.id,
        question="What is the average sales cycle length?",
        answer="6 to 9 months due to enterprise procurement cycles.",
        category="internal"
    )
    db_session.add(qa)

    # 4. Source
    source = Source(
        company_id=company.id,
        url="https://novarobotics.example.com/press.xml",
        category="competitors",
        reason="Official press release feed.",
        status="active",
        health="healthy"
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    assert source.id is not None

    # 5. CrawlRun
    crawl_run = CrawlRun(
        company_id=company.id,
        source_id=source.id,
        status="completed",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        documents_found=1
    )
    db_session.add(crawl_run)
    db_session.commit()
    db_session.refresh(crawl_run)

    # 6. Document
    doc = Document(
        company_id=company.id,
        source_id=source.id,
        crawl_run_id=crawl_run.id,
        url="https://novarobotics.example.com/press/v2-launch",
        content_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        title="Nova Launches V2 Arm",
        raw_text="Nova Robotics today unveiled its next-generation heavy payload robotic arm.",
        first_seen=datetime.now(timezone.utc)
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    # 7. Signal
    signal = Signal(
        company_id=company.id,
        document_id=doc.id,
        category="competitors",
        headline="Nova unveils heavy payload arm",
        summary="Nova announced high payload robotic arm.",
        evidence_snippet="Nova Robotics today unveiled its next-generation heavy payload robotic arm.",
        source_url=doc.url,
        discovery_date=datetime.now(timezone.utc),
        verified_flag=True,
        interpretation="Expands competitive footprint into heavy palletizing.",
        source_reliability=0.9,
        evidence_strength=0.95,
        strategic_relevance=0.88,
        impact="high",
        urgency="medium"
    )
    db_session.add(signal)

    # 8. Brief
    brief = Brief(
        company_id=company.id,
        week_label="Week 47, 2026",
        generated_date=datetime.now(timezone.utc),
        executive_summary="Major competitive launch by Nova Robotics observed.",
        customer_updates="Stable.",
        competitor_updates="Nova launched V2 payload arm.",
        market_updates="No regulatory shifts.",
        internal_updates="On track.",
        nothing_happened_flag=False
    )
    db_session.add(brief)
    db_session.commit()
    db_session.refresh(brief)

    # 9. ActionItem
    action = ActionItem(
        company_id=company.id,
        brief_id=brief.id,
        title="Update battlecards for Nova V2",
        description="Highlight payload limitations vs our flagship model.",
        priority="high",
        status="open"
    )
    db_session.add(action)

    # 10. SchedulerLog
    log = SchedulerLog(
        job_id="test_job",
        run_at=datetime.now(timezone.utc),
        status="success",
        duration_ms=45,
        details="Crawled 1 source."
    )
    db_session.add(log)

    # 11. Setting
    setting = Setting(
        key="active_provider",
        value="mock",
        description="Active provider in test suite"
    )
    db_session.add(setting)
    db_session.commit()

    # Verify cascading relationships
    reloaded_company = db_session.query(Company).filter_by(id=company.id).first()
    assert len(reloaded_company.profile_facts) == 1
    assert len(reloaded_company.interview_qas) == 1
    assert len(reloaded_company.sources) == 1
    assert len(reloaded_company.signals) == 1
    assert len(reloaded_company.briefs) == 1
    assert len(reloaded_company.action_items) == 1
