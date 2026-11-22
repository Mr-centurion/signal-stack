import pytest
import json
from backend.database import SessionLocal
from backend.models import Company, Source, ContextChangeReport
from backend.services.context_change_service import context_change_service
from backend.services.llm_client import llm_client

@pytest.mark.needs_data
@pytest.mark.asyncio
async def test_context_change_reassessment_and_diff():
    """
    Demonstrates Context Change on MeetUniversity:
    - Changes strategic priority to US & European STEM graduate programs.
    - Re-scores every source's relevance against the new context.
    - Recommends removal of misaligned sources and addition of new targets.
    - Verifies ContextChangeReport is stored with diff metrics.
    - Verifies zero auto-deletion (sources marked rejected, never deleted).
    """
    llm_client.set_provider("mock")
    db = SessionLocal()

    company = db.query(Company).filter_by(id=1).first()
    if not company:
        db.close()
        pytest.skip("requires pre-populated database: copy data/demo/signal_stack_demo.db over signal_stack.db")

    sources_count = db.query(Source).filter_by(company_id=1, status="approved").count()
    if sources_count == 0:
        db.close()
        pytest.skip("requires pre-populated database: copy data/demo/signal_stack_demo.db over signal_stack.db")

    change_desc = (
        "Strategic shift: MeetUniversity is pivoting from broad undergraduate counseling in India "
        "to specialized US and European STEM graduate admissions (AI, Data Science, Robotics), "
        "targeting tier-1 international engineering applicants and institutional corporate sponsors."
    )

    print("\n" + "=" * 80)
    print(f"RUNNING CONTEXT-CHANGE STRATEGIC REASSESSMENT FOR: {company.name}")
    print(f"Strategic Shift: {change_desc}")
    print("=" * 80)

    # Execute context change reassessment
    report = await context_change_service.reassess_context(
        db=db,
        company_id=1,
        change_type="strategic_shift",
        change_description=change_desc
    )

    assert report is not None
    assert isinstance(report, ContextChangeReport)
    assert report.company_id == 1
    assert report.sources_before_count > 0

    removed_recs = json.loads(report.removed_recommendations_json)
    added_recs = json.loads(report.added_recommendations_json)
    metrics = json.loads(report.metrics_json)

    print("\n--- CONTEXT CHANGE METRICS ---")
    print(f"Sources Audited:              {metrics.get('sources_audited')}")
    print(f"Sources Retained:             {metrics.get('sources_retained_count')}")
    print(f"Recommended Removals:         {metrics.get('sources_recommended_removal')}")
    print(f"Recommended Additions:        {metrics.get('sources_recommended_addition')}")
    print(f"Sources Before Count:         {report.sources_before_count}")
    print(f"Sources Projected After:      {report.sources_after_count}")

    print("\n--- RECOMMENDED REMOVALS (MISALIGNED WITH NEW STEM STRATEGY) ---")
    for r in removed_recs[:5]:
        print(f"[-] ID #{r.get('id')} | Category: {r.get('category')} | Score: {r.get('relevance_score')}")
        print(f"    URL: {r.get('source_url')}")
        print(f"    Reason: {r.get('reason')}\n")

    print("--- RECOMMENDED ADDITIONS (NEW CANDIDATE TARGETS) ---")
    for a in added_recs[:5]:
        print(f"[+] ID #{a.get('id')} | Category: {a.get('category')}")
        print(f"    URL: {a.get('source_url')}")
        print(f"    Reason: {a.get('reason')}\n")

    # Verify Accept / Dismiss workflow preserves sources
    if removed_recs:
        first_rem = removed_recs[0]
        src_id = first_rem.get("source_id")
        res_accept = context_change_service.accept_recommendation(db, report.id, "remove", first_rem.get("id"))
        assert res_accept["status"] == "success"
        
        # Verify source is NOT deleted from DB
        src_check = db.query(Source).filter_by(id=src_id).first()
        assert src_check is not None, "Source must NEVER be deleted from database"
        assert src_check.status == "rejected"
        assert "Rejected via Context Change" in (src_check.rejection_reason or "")
        
        # Reset back to approved for subsequent tests
        src_check.status = "approved"
        db.commit()

    print("=" * 80 + "\n")
    db.close()
