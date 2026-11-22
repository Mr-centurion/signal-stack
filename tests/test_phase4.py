import asyncio
import json
import os
import sys
from datetime import datetime, timezone

from backend.database import SessionLocal
from backend.models import Company, Competitor, Document, Signal, Brief, ActionItem, ProfileFact, InterviewQA
from backend.services.app_store_service import app_store_service
from backend.services.analysis_engine import analysis_engine
from backend.services.brief_service import brief_service
from backend.services.llm_client import llm_client

async def main():
    print("=== PHASE 4: ANALYSIS, RANKING & 10-SECTION MONDAY BRIEF TEST ===")
    db = SessionLocal()

    # 1. Check LLM provider
    provider = llm_client.provider_name
    print(f"[TEST CHECK] LLM Provider active: {provider}")
    assert provider in ["gemini", "groq"], f"Real LLM provider required, got {provider}"

    # 2. Find MeetUniversity
    company = db.query(Company).filter(Company.name.ilike("%meetuniversity%")).first()
    if not company:
        print("[ERROR] MeetUniversity not found in database. Exiting.")
        sys.exit(1)
    print(f"[TARGET COMPANY] ID: {company.id} | Name: {company.name} | Domain: {company.domain}")

    # 3. Discover & Ingest Competitor App Store Reviews (Customer Voice)
    print("\n--- STEP 1: App Store Customer Voice Discovery ---")
    app_signals = await app_store_service.ingest_competitor_app_reviews(db, company.id)
    print(f"[APP STORE RESULTS] Discovered & ingested {len(app_signals)} customer voice signals from App Store reviews.")

    # 4. Run Analysis & Ranking Engine
    print("\n--- STEP 2: Analysis & Priority Ranking Engine ---")
    ranked_signals = await analysis_engine.analyze_and_rank_company_signals(db, company.id)
    print(f"[ANALYSIS RESULTS] Analyzed & ranked {len(ranked_signals)} signals for {company.name}.")
    assert len(ranked_signals) > 0, "Expected at least 1 ranked signal"

    # Inspect top ranked signal
    top_signal = ranked_signals[0]
    print(f"\n[TOP RANKED SIGNAL #{top_signal.id}]")
    print(f"  Headline: {top_signal.headline}")
    print(f"  Priority Score: {top_signal.priority_score:.3f}")
    print(f"  Reliability Score: {top_signal.source_reliability:.2f}")
    print(f"  Evidence Strength: {top_signal.evidence_strength:.2f}")
    print(f"  Strategic Relevance: {top_signal.strategic_relevance:.2f}")
    print(f"  Event Type: {top_signal.event_type}")
    print(f"  Direction: {top_signal.direction} | Urgency: {top_signal.urgency} | Impact: {top_signal.impact}")
    print(f"  Why Important: {top_signal.why_important}")
    print(f"  Anchored Profile Fact: {top_signal.referenced_profile_fact}")
    print(f"  Why It Matters: {top_signal.why_it_matters}")
    print(f"  Evidence Snippet (Body): \"{top_signal.evidence_snippet[:120]}...\"")
    print(f"  Age (Days): {top_signal.age_days} | Is Background (>90d): {top_signal.is_background}")

    # Verify orthogonal scores
    assert top_signal.source_reliability is not None
    assert top_signal.evidence_strength is not None
    assert top_signal.strategic_relevance is not None
    assert top_signal.priority_score is not None
    assert top_signal.why_important is not None and len(top_signal.why_important) > 0
    assert top_signal.referenced_profile_fact is not None and len(top_signal.referenced_profile_fact) > 0

    # Save sample ranked signal evidence
    os.makedirs("tests/evidence", exist_ok=True)
    sample_signal_data = {
        "signal_id": top_signal.id,
        "headline": top_signal.headline,
        "category": top_signal.category,
        "event_type": top_signal.event_type,
        "verification_status": top_signal.verification_status,
        "scores": {
            "priority_score": top_signal.priority_score,
            "source_reliability": top_signal.source_reliability,
            "evidence_strength": top_signal.evidence_strength,
            "strategic_relevance": top_signal.strategic_relevance,
            "impact": top_signal.impact,
            "urgency": top_signal.urgency,
            "direction": top_signal.direction
        },
        "why_important_breakdown": top_signal.why_important,
        "separation_of_evidence": {
            "what_happened": top_signal.what_happened,
            "when_published": top_signal.when_published,
            "publisher_name": top_signal.publisher_name,
            "publisher_url": top_signal.publisher_url or top_signal.source_url,
            "verbatim_body_snippet": top_signal.evidence_snippet
        },
        "separation_of_interpretation": {
            "why_it_matters": top_signal.why_it_matters,
            "referenced_profile_fact": top_signal.referenced_profile_fact,
            "business_area": top_signal.business_area,
            "what_to_consider": top_signal.what_to_consider
        },
        "recency": {
            "published_date": top_signal.published_date.isoformat() if top_signal.published_date else None,
            "age_days": top_signal.age_days,
            "is_background_flag": top_signal.is_background
        }
    }
    with open("tests/evidence/phase4_sample_ranked_signal.json", "w") as f:
        json.dump(sample_signal_data, f, indent=2)
    print("  -> Saved sample ranked signal to tests/evidence/phase4_sample_ranked_signal.json")

    # 5. Generate 10-Section Monday Brief
    print("\n--- STEP 3: 10-Section Monday Strategic Brief Generation ---")
    brief = await brief_service.generate_monday_brief(db, company.id)
    print(f"[BRIEF GENERATED] ID: {brief.id} | Cycle: {brief.week_label}")
    print(f"[CITATION & PROVENANCE AUDIT]: {brief.validator_report}")

    print("\n--- BRIEF SECTIONS AUDIT ---")
    print(f"1. Executive Summary: {len(brief.executive_summary)} chars")
    print(f"2. Customer Signals: {len(brief.customer_signals)} chars")
    print(f"3. Competitor Intelligence: {len(brief.competitor_intelligence)} chars")
    print(f"4. Market Intelligence: {len(brief.market_intelligence)} chars")
    print(f"5. Internal Intelligence: {len(brief.internal_intelligence)} chars -> \"{brief.internal_intelligence}\"")
    print(f"6. Opportunities: {len(brief.opportunities)} chars")
    print(f"7. Risks & Threats: {len(brief.risks_threats)} chars")
    print(f"8. Recommended Actions: {len(brief.recommended_actions)} chars")
    print(f"9. What We Should Watch: {len(brief.what_we_should_watch)} chars")
    print(f"10. Source Appendix: {len(brief.source_appendix)} chars")

    # Verify Section 5 handles no internal docs uploaded
    internal_docs_count = db.query(Document).filter_by(company_id=company.id, category="internal").count()
    if internal_docs_count == 0:
        assert "no internal data uploaded" in brief.internal_intelligence.lower(), "Expected explicit 'No internal data uploaded'"

    # Verify ActionItems created
    action_items = db.query(ActionItem).filter_by(brief_id=brief.id).all()
    print(f"\n[ACTION ITEMS TRACKING] Created {len(action_items)} action items for Brief #{brief.id}:")
    for ai in action_items:
        print(f"  - [{ai.priority.upper()}] {ai.title} | Owner: {ai.owner_role} | Status: {ai.status} | Reason: {ai.reason}")
    assert len(action_items) > 0, "Expected at least 1 ActionItem created"

    # Verify Exports
    assert brief.html_export is not None and len(brief.html_export) > 500, "Expected non-empty HTML export"
    assert brief.markdown_export is not None and len(brief.markdown_export) > 500, "Expected non-empty Markdown export"

    with open("tests/evidence/phase4_brief_export.html", "w") as f:
        f.write(brief.html_export)
    with open("tests/evidence/phase4_brief_export.md", "w") as f:
        f.write(brief.markdown_export)
    with open("tests/evidence/phase4_brief_v2.md", "w") as f:
        f.write(brief.markdown_export)

    print("\n==================== COMPLETE MONDAY BRIEF MARKDOWN ====================")
    print(brief.markdown_export)
    print("========================================================================\n")

    brief_evidence = {
        "company_name": company.name,
        "brief_id": brief.id,
        "week_label": brief.week_label,
        "generated_date": brief.generated_date.isoformat(),
        "validator_report": brief.validator_report,
        "sections": {
            "1_executive_summary": brief.executive_summary,
            "2_customer_signals": brief.customer_signals,
            "3_competitor_intelligence": brief.competitor_intelligence,
            "4_market_intelligence": brief.market_intelligence,
            "5_internal_intelligence": brief.internal_intelligence,
            "6_opportunities": json.loads(brief.opportunities) if brief.opportunities.startswith("[") else brief.opportunities,
            "7_risks_threats": brief.risks_threats,
            "8_recommended_actions": json.loads(brief.recommended_actions) if brief.recommended_actions.startswith("[") else brief.recommended_actions,
            "9_what_we_should_watch": brief.what_we_should_watch,
            "10_source_appendix": json.loads(brief.source_appendix) if brief.source_appendix.startswith("[") else brief.source_appendix
        },
        "action_items_count": len(action_items),
        "html_export_length": len(brief.html_export),
        "markdown_export_length": len(brief.markdown_export)
    }
    with open("tests/evidence/phase4_meetuniversity_brief.json", "w") as f:
        json.dump(brief_evidence, f, indent=2)
    print("\n  -> Saved full brief evidence to tests/evidence/phase4_meetuniversity_brief.json")
    print("  -> Saved HTML export to tests/evidence/phase4_brief_export.html")
    print("  -> Saved Markdown export to tests/evidence/phase4_brief_export.md")

    print("\n=== ALL PHASE 4 VALIDATIONS PASSED SUCCESSFULLY ===")
    db.close()

if __name__ == "__main__":
    asyncio.run(main())
