import os
import shutil
import json
import asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

async def main():
    print("=" * 80)
    print("RUNNING MEETUNIVERSITY GERMAN-PIVOT CONTEXT CHANGE REASSESSMENT (ON DB COPY)")
    print("=" * 80)

    # 1. Create a COPY of the DB to avoid modifying signal_stack.db
    original_db = "signal_stack.db"
    copy_db = "signal_stack_test_copy.db"
    shutil.copyfile(original_db, copy_db)
    print(f"Created database copy: {copy_db} from {original_db}")

    # Set up engine and session pointing to signal_stack_test_copy.db
    engine = create_engine(f"sqlite:///{copy_db}", echo=False)
    Session = sessionmaker(bind=engine)
    db = Session()

    from backend.models import Company, Source, Competitor, ContextChangeReport
    from backend.services.context_change_service import context_change_service

    company = db.query(Company).filter_by(id=1).first()
    assert company is not None, "MeetUniversity record must exist in DB copy"

    pivot_description = (
        "Strategic pivot: MeetUniversity is pivoting focus to German public universities, "
        "tuition-free education counseling, blocked accounts, and German student visa requirements "
        "(APS certificate and TestAS), expanding operations into Berlin and Munich."
    )

    print(f"Target Monitored Company: {company.name}")
    print(f"Strategic Pivot Context:  {pivot_description}\n")

    # 2. Run LLM-driven context reassessment with two-step live competitor discovery
    report = await context_change_service.reassess_context(
        db=db,
        company_id=1,
        change_type="strategic_pivot",
        change_description=pivot_description
    )

    # 3. Save full report to tests/evidence/phase8_context_change.json
    evidence_dir = "tests/evidence"
    os.makedirs(evidence_dir, exist_ok=True)
    evidence_path = os.path.join(evidence_dir, "phase8_context_change.json")

    report_dict = {
        "report_id": report.id,
        "company_id": report.company_id,
        "change_type": report.change_type,
        "change_description": report.change_description,
        "sources_before_count": report.sources_before_count,
        "sources_after_count": report.sources_after_count,
        "metrics": json.loads(report.metrics_json),
        "competitors_diff": json.loads(report.competitors_diff_json),
        "removed_source_recommendations": json.loads(report.removed_recommendations_json),
        "added_source_recommendations": json.loads(report.added_recommendations_json),
        "before_context": json.loads(report.before_context_json),
        "after_context": json.loads(report.after_context_json)
    }

    with open(evidence_path, "w", encoding="utf-8") as f:
        json.dump(report_dict, f, indent=2)

    print(f"Saved full context change report to: {evidence_path}")
    print("\n" + "-" * 80)
    print("PHASE 8 CONTEXT CHANGE AUDIT SUMMARY:")
    print(f"Sources Before Count:         {report.sources_before_count}")
    print(f"Sources Recommended Removal:  {len(report_dict['removed_source_recommendations'])}")
    print(f"Sources Recommended Addition: {len(report_dict['added_source_recommendations'])}")
    print(f"Competitors Before Count:     {report_dict['competitors_diff']['competitors_before_count']}")
    print(f"Competitors Removed:          {len(report_dict['competitors_diff']['competitors_removed'])}")
    print(f"Competitors Added:            {len(report_dict['competitors_diff']['competitors_added'])}")

    print("\n--- NEW COMPETITORS DISCOVERED VIA TWO-STEP DISCOVERY ---")
    for comp in report_dict['competitors_diff']['competitors_added']:
        print(f"[+] Name: {comp.get('name')}")
        print(f"    Type: {comp.get('type')}")
        print(f"    URL:  {comp.get('url')}")
        print(f"    Reason: {comp.get('reason')}")
        if comp.get('evidence_snippet'):
            print(f"    Verbatim Snippet: \"{comp.get('evidence_snippet')}\"")
        print()

    print("--- REMOVED COMPETITORS (MISALIGNED WITH GERMAN PIVOT) ---")
    for comp in report_dict['competitors_diff']['competitors_removed']:
        print(f"[-] Name: {comp.get('name')}")
        print(f"    Reason: {comp.get('reason')}\n")

    print("-" * 80 + "\n")
    db.close()
    engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
