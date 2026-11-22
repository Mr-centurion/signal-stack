import json
import asyncio
from backend.database import SessionLocal
from backend.models import Company, ProfileFact, Document
from backend.services.research_service import company_research_service

async def main():
    print("=" * 80)
    print("RE-RUNNING MEETUNIVERSITY DEEP RESEARCH FROM SCRATCH")
    print("=" * 80)

    db = SessionLocal()
    company = db.query(Company).filter_by(id=1).first()
    assert company is not None, "Company #1 MeetUniversity must exist"

    print(f"Company: {company.name}")
    print(f"URL:     {company.website_url or 'https://meetuniv.com'}")
    print("Executing polite crawl, entity disambiguation, and snippet-grounded profile extraction...\n")

    res = await company_research_service.run_research(
        db=db,
        company_id=1,
        company_name=company.name,
        url="https://www.meetuniversity.com"
    )

    print(f"Research Status: {res.get('status')}")
    print(f"Crawled Documents: {res.get('crawled_documents')}")

    facts = db.query(ProfileFact).filter_by(company_id=1, source_origin="research").all()
    verified_facts = [f for f in facts if f.fact_type == "fact"]
    assumption_facts = [f for f in facts if f.fact_type == "assumption"]

    print(f"\nTotal Profile Facts Stored: {len(facts)}")
    print(f"Verified Facts (Grounded in site snippets): {len(verified_facts)}")
    print(f"Assumptions (Inferred / ungrounded):        {len(assumption_facts)}")

    print("\n--- VERIFIED FACTS CARRYING SITE VERBATIM SNIPPETS ---")
    all_verified_have_snippets = True
    for idx, vf in enumerate(verified_facts):
        has_snippet = bool(vf.evidence_snippet and len(vf.evidence_snippet.strip()) >= 8)
        if not has_snippet:
            all_verified_have_snippets = False
        print(f"[{idx+1}] Category: {vf.category} | Field: {vf.field_name}")
        print(f"    Claim: \"{vf.text}\"")
        print(f"    Evidence Snippet: \"{vf.evidence_snippet}\"")
        print(f"    Source URL: {vf.source_url}")
        print(f"    Snippet Grounded: {'YES' if has_snippet else 'NO - FAILED'}\n")

    print(f"All Verified Facts Carry Valid Site Snippet: {all_verified_have_snippets}")
    assert all_verified_have_snippets, "Violation: a verified fact exists without a valid site snippet!"

    print("-" * 80)
    db.close()

if __name__ == "__main__":
    asyncio.run(main())
