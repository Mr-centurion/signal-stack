import os
import json
import asyncio
from datetime import datetime, timezone
import urllib.parse

from backend.database import SessionLocal, init_db
from backend.models import Company, Source, Signal, Competitor, InterviewQA, ProfileFact, Brief
from backend.services.source_discovery_service import source_discovery_service
from backend.services.competitor_discovery_service import competitor_discovery_service
from backend.services.brief_service import brief_service
from backend.services.context_change_service import context_change_service
from backend.services.llm_client import llm_client
from backend.config import settings

async def remediate_data_integrity():
    init_db()
    db = SessionLocal()

    print("\n" + "=" * 80)
    print("STEP 1: DATA INTEGRITY REMEDIATION")
    print("=" * 80)

    # 1. Deduplicate & Tag Interview QAs for MeetUniversity
    mu = db.query(Company).filter_by(id=1).first()
    if mu:
        all_qas = db.query(InterviewQA).filter_by(company_id=mu.id).order_by(InterviewQA.id.asc()).all()
        print(f"MeetUniversity initial QAs count: {len(all_qas)}")
        seen_topics = set()
        kept_qas = []
        for q in all_qas:
            if q.topic in seen_topics:
                print(f"  Removing duplicate QA #{q.id} for topic '{q.topic}'")
                db.delete(q)
            else:
                seen_topics.add(q.topic)
                # Tag simulated test answers as [TEST FIXTURE]
                if q.answer and not q.answer.startswith("[TEST FIXTURE]"):
                    q.answer = f"[TEST FIXTURE] {q.answer}"
                kept_qas.append(q)
        db.commit()
        print(f"MeetUniversity QAs after deduplication: {len(kept_qas)} (all tagged [TEST FIXTURE])")

    # 2. Competitor Self-Reference Exclusion & 10-Cap across ALL companies
    for c in db.query(Company).all():
        comps = db.query(Competitor).filter_by(company_id=c.id).order_by(
            Competitor.is_verified.desc(),
            (Competitor.type == 'direct').desc(),
            Competitor.id.asc()
        ).all()
        print(f"\nCompany #{c.id} ({c.name}): Initial competitors: {len(comps)}")
        
        # Self-exclusion check
        valid_comps = []
        for comp in comps:
            is_self = competitor_discovery_service.is_excluded_entity(comp.name, comp.url, c.domain, c.name)
            if is_self:
                print(f"  [SELF-EXCLUSION] Removing competitor #{comp.id} '{comp.name}' ({comp.url}) from {c.name}'s list")
                db.delete(comp)
            else:
                valid_comps.append(comp)
        db.commit()

        # Hard cap at top 10
        if len(valid_comps) > 10:
            to_keep = valid_comps[:10]
            to_drop = valid_comps[10:]
            for d in to_drop:
                print(f"  [CAP AT 10] Pruning competitor #{d.id} '{d.name}'")
                db.delete(d)
            db.commit()
            print(f"  Final competitors count for {c.name}: {len(to_keep)}")
        else:
            print(f"  Final competitors count for {c.name}: {len(valid_comps)}")

    # 3. Re-run source discovery to guarantee >= 4 distinct market domains and customer coverage
    print("\n" + "=" * 80)
    print("STEP 2: COVERAGE ENHANCEMENT (>= 4 MARKET DOMAINS & CUSTOMER SOURCES)")
    print("=" * 80)

    for c in db.query(Company).all():
        print(f"\nDiscovering enhanced sources for #{c.id} ({c.name})...")
        await source_discovery_service.discover_sources(db, c.id)
        
        # Verify category and distinct domains
        for cat in ['customers', 'competitors', 'market', 'internal']:
            srcs = db.query(Source).filter_by(company_id=c.id, category=cat, status='approved').all()
            domains = set()
            for s in srcs:
                p = urllib.parse.urlparse(s.url)
                d = p.netloc.lower().replace("www.", "")
                domains.add(d)
            print(f"  Category '{cat}': {len(srcs)} approved sources across {len(domains)} distinct domains: {domains}")

    # 4. Context-Change Evidence: German-universities pivot on MeetUniversity
    print("\n" + "=" * 80)
    print("STEP 3: CONTEXT-CHANGE STRATEGIC PIVOT (GERMAN UNIVERSITIES)")
    print("=" * 80)
    
    german_pivot_desc = (
        "Strategic shift: MeetUniversity is pivoting from UK/Canada general counseling "
        "to specialized German public tuition-free STEM university admissions (DAAD guidelines, "
        "APS certificate validation, TestDaF/IELTS requirements, and English-taught Master's degrees)."
    )

    pivot_report = await context_change_service.reassess_context(
        db=db,
        company_id=1,
        change_type="strategic_shift",
        change_description=german_pivot_desc
    )

    evidence_data = {
        "report_id": pivot_report.id,
        "company_id": pivot_report.company_id,
        "change_type": pivot_report.change_type,
        "change_description": pivot_report.change_description,
        "sources_before_count": pivot_report.sources_before_count,
        "sources_after_count": pivot_report.sources_after_count,
        "metrics": json.loads(pivot_report.metrics_json),
        "removed_recommendations": json.loads(pivot_report.removed_recommendations_json),
        "added_recommendations": json.loads(pivot_report.added_recommendations_json),
        "competitors_diff": json.loads(pivot_report.competitors_diff_json)
    }

    os.makedirs("tests/evidence", exist_ok=True)
    evidence_path = os.path.abspath("tests/evidence/phase6_context_change.json")
    with open(evidence_path, "w", encoding="utf-8") as f:
        json.dump(evidence_data, f, indent=2)
    print(f"Saved ContextChangeReport to: {evidence_path}")

    # Print full report
    print("\n" + "-" * 60)
    print("FULL CONTEXT-CHANGE REPORT (GERMAN UNIVERSITIES PIVOT):")
    print("-" * 60)
    print(f"Strategic Shift:\n{pivot_report.change_description}\n")
    print(f"Sources Before Count:    {pivot_report.sources_before_count}")
    print(f"Sources Projected After: {pivot_report.sources_after_count}")
    print(f"Sources Retained:        {evidence_data['metrics'].get('sources_retained_count')}")
    print(f"Sources Marked Removal:  {evidence_data['metrics'].get('sources_recommended_removal')}")
    print(f"Sources Recommended Add: {evidence_data['metrics'].get('sources_recommended_addition')}")
    
    print("\nSources Marked No Longer Useful (With Reason):")
    for r in evidence_data["removed_recommendations"][:5]:
        print(f"  [-] ID #{r['id']} ({r['category']}): {r['source_url']}")
        print(f"      Reason: {r['reason']}")

    print("\nNew Sources Recommended Aligned with Strategy:")
    for a in evidence_data["added_recommendations"][:5]:
        print(f"  [+] ID #{a['id']} ({a['category']}): {a['source_url']}")
        print(f"      Reason: {a['reason']}")

    print("\nCompetitors Diff:")
    print(f"  Before Count: {evidence_data['competitors_diff'].get('competitors_before_count')}")
    print(f"  Projected After Count: {evidence_data['competitors_diff'].get('competitors_after_count')}")
    print("  Competitors Removed:")
    for cr in evidence_data['competitors_diff'].get('competitors_removed', []):
        print(f"    [-] {cr['name']}: {cr['reason']}")
    print("  Competitors Added:")
    for ca in evidence_data['competitors_diff'].get('competitors_added', []):
        print(f"    [+] {ca['name']}: {ca['reason']}")
    print("-" * 60)

    # 5. Regenerate MeetUniversity brief without fixture answers
    print("\n" + "=" * 80)
    print("STEP 4: REGENERATE MEETUNIVERSITY BRIEF EXCLUDING FIXTURE ANSWERS")
    print("=" * 80)

    new_brief = await brief_service.generate_monday_brief(db, company_id=1)
    print(f"Generated clean Brief #{new_brief.id} for MeetUniversity.")

    # Export to reports
    signals = db.query(Signal).filter_by(company_id=1).all()
    os.makedirs("reports", exist_ok=True)
    md_content = brief_service.generate_markdown_export(new_brief, mu, signals)
    html_content = brief_service.generate_html_export(new_brief, mu, signals)

    with open("reports/meetuniversity_brief.md", "w", encoding="utf-8") as f:
        f.write(md_content)
    with open("reports/meetuniversity_brief.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    print("Exported clean briefs to reports/meetuniversity_brief.md and .html")

    db.close()
    print("\nREMEDIATION COMPLETE.")

if __name__ == "__main__":
    asyncio.run(remediate_data_integrity())
