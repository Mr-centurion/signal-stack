import pytest
import json
from backend.database import SessionLocal
from backend.models import Company, Source, SourceHealthReport
from backend.services.monthly_audit_service import monthly_audit_service
from backend.services.llm_client import llm_client

@pytest.mark.needs_data
@pytest.mark.asyncio
async def test_monthly_audit_meetuniversity_and_print_report():
    """
    Runs Monthly Signal Stack Audit on MeetUniversity (company_id=1).
    Checks dead URLs, duplicates, inactive sources, declining relevance,
    runs discovery for candidate sources, and prints full health report.
    """
    llm_client.set_provider("mock")
    db = SessionLocal()

    company = db.query(Company).filter_by(id=1).first()
    if not company:
        db.close()
        pytest.skip("requires pre-populated database: copy data/demo/signal_stack_demo.db over signal_stack.db")

    print("\n" + "=" * 80)
    print(f"RUNNING MONTHLY SOURCE HEALTH AUDIT FOR: {company.name} (ID: {company.id})")
    print("=" * 80)

    # Execute monthly audit
    report = await monthly_audit_service.run_audit(db, company_id=1)

    assert report is not None
    assert isinstance(report, SourceHealthReport)
    assert report.total_sources_audited > 0
    assert report.company_id == 1

    recommendations = json.loads(report.recommendations_json)
    assert isinstance(recommendations, list)
    assert len(recommendations) > 0
    assert "Inactivity and relevance trends need" in report.summary

    # Ensure KEEP recommendations are informational and never marked 'accepted'
    for r in recommendations:
        if r.get("action") == "keep":
            assert r.get("status") != "accepted", "KEEP recommendations must be informational, never accepted"

    print("\n--- SOURCE HEALTH AUDIT METRICS ---")
    print(f"Total Sources Audited:   {report.total_sources_audited}")
    print(f"Healthy / Active:        {report.healthy_sources_count}")
    print(f"Dead / Broken URLs:      {report.dead_sources_count}")
    print(f"Blocked by robots.txt:   {report.blocked_sources_count}")
    print(f"Duplicate Sources:       {report.duplicate_sources_count}")
    print(f"Inactive Feeds (4+ wks): {report.inactive_sources_count}")
    print(f"Declining Relevance:     {report.declining_sources_count}")
    print(f"\nExecutive Audit Summary:\n{report.summary}")

    print("\n--- ACTIONABLE RECOMMENDATIONS (ADD / REMOVE / KEEP) ---")
    for rec in recommendations:
        rec_id = rec.get("id")
        action = rec.get("action", "").upper()
        url = rec.get("url", "")
        reason = rec.get("reason", "")
        status = rec.get("status", "")
        print(f"[{action}] ID #{rec_id} | Status: {status}")
        print(f"  URL: {url}")
        print(f"  Reason: {reason}\n")

    print("=" * 80 + "\n")
    db.close()


def test_audit_recommendation_accept_and_dismiss_preserves_sources():
    """
    Tests that accepting a removal recommendation does NOT delete the source from the DB,
    satisfying the strict constraint 'never auto-delete'. Instead, status is set to 'rejected'.
    Also tests dismissing a recommendation.
    """
    db = SessionLocal()

    # Ensure company #1 exists for foreign key validity
    comp = db.query(Company).filter_by(id=1).first()
    if not comp:
        comp = Company(id=1, name="Test Company", domain="example.com", description="Test fixture company")
        db.add(comp)
        db.commit()

    # Create a dummy health report with sample recommendations
    sample_recs = [
        {
            "id": 1,
            "action": "remove",
            "source_id": 99998,
            "url": "https://example.com/dead-feed.rss",
            "reason": "URL returned HTTP 404 dead",
            "status": "pending"
        },
        {
            "id": 2,
            "action": "add",
            "source_id": None,
            "url": "https://example.com/fresh-edtech.rss",
            "reason": "Discovered high-relevance RSS feed",
            "status": "pending"
        }
    ]

    # Add a mock source to verify it is NOT deleted
    mock_src = db.query(Source).filter_by(id=99998).first()
    if not mock_src:
        mock_src = Source(
            id=99998,
            company_id=1,
            url="https://example.com/dead-feed.rss",
            category="competitors",
            status="approved",
            reason="Original approved test source"
        )
        db.add(mock_src)
        db.commit()

    report = SourceHealthReport(
        company_id=1,
        total_sources_audited=10,
        dead_sources_count=1,
        blocked_sources_count=0,
        duplicate_sources_count=0,
        inactive_sources_count=0,
        declining_sources_count=0,
        healthy_sources_count=9,
        summary="Test Health Report",
        recommendations_json=json.dumps(sample_recs),
        audit_metrics_json="{}"
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    # 1. Test Accept 'remove' recommendation
    res_accept = monthly_audit_service.accept_recommendation(db, report.id, rec_id=1)
    assert res_accept["status"] == "success"
    assert res_accept["recommendation"]["status"] == "accepted"

    # Verify source was NOT deleted, but updated to rejected
    src_after = db.query(Source).filter_by(id=99998).first()
    assert src_after is not None, "Source must NEVER be deleted from DB (foreign key & history preservation)"
    assert src_after.status == "rejected"
    assert "Rejected via Monthly Audit" in (src_after.rejection_reason or "")

    # 2. Test Dismiss 'add' recommendation
    res_dismiss = monthly_audit_service.dismiss_recommendation(db, report.id, rec_id=2)
    assert res_dismiss["status"] == "success"
    assert res_dismiss["recommendation"]["status"] == "dismissed"

    # Cleanup mock data
    db.delete(report)
    db.delete(mock_src)
    db.commit()
    db.close()
