import os
import json
import asyncio
from datetime import datetime, timezone
import urllib.parse

from backend.database import SessionLocal, init_db
from backend.models import Company, Source, Signal, Competitor, InterviewQA, ProfileFact, Brief
from backend.services.pipeline_service import one_click_pipeline_service
from backend.services.llm_client import llm_client
from backend.config import settings

async def run_linear():
    init_db()
    db = SessionLocal()

    # Configure live provider
    if settings.GEMINI_API_KEY:
        llm_client.set_provider("gemini", api_key=settings.GEMINI_API_KEY)
    elif settings.GROQ_API_KEY:
        llm_client.set_provider("groq", api_key=settings.GROQ_API_KEY)
    else:
        llm_client.set_provider("mock")

    company_name = "Linear"
    website_url = "https://linear.app"
    industry = "Issue Tracking & Project Management Software"

    print("=" * 80)
    print(f"RUNNING ONE-CLICK ONBOARD AND RUN PIPELINE FOR: {company_name} ({website_url})")
    print(f"Provider: {llm_client.provider_name}")
    print("=" * 80)

    result = await one_click_pipeline_service.run_pipeline(
        db=db,
        name=company_name,
        url=website_url,
        industry=industry,
        skip_interview=True,
        interview_answers=None
    )

    company_id = result.get("company_id")
    stages = result.get("stages", [])

    print("\n--- STAGE EXECUTION RESULTS ---")
    for s in stages:
        st_name = s.get("stage", "").upper()
        status = s.get("status", "").upper()
        details = s.get("details", "")
        err = s.get("error")
        err_msg = f" | ERROR: {err}" if err else ""
        print(f"[{status}] {st_name}: {details}{err_msg}")

    # Query final records for Linear
    company = db.query(Company).filter_by(id=company_id).first()
    comps = db.query(Competitor).filter_by(company_id=company_id).all()
    sources = db.query(Source).filter_by(company_id=company_id, status="approved").all()
    signals = db.query(Signal).filter_by(company_id=company_id).all()
    brief = db.query(Brief).filter_by(company_id=company_id).order_by(Brief.id.desc()).first()

    print("\n--- DISCOVERED COMPETITORS (CAPPED AT 10, ZERO SELF-REFERENCE) ---")
    print(f"Total Competitors: {len(comps)}")
    for c in comps:
        print(f"  • {c.name} ({c.type}): {c.url} - {c.why_relevant}")

    print("\n--- APPROVED SOURCES BY CATEGORY ---")
    src_by_cat = {}
    for s in sources:
        src_by_cat.setdefault(s.category, []).append(s)
    
    for cat in ['customers', 'competitors', 'market', 'internal']:
        cat_srcs = src_by_cat.get(cat, [])
        domains = set()
        for s in cat_srcs:
            p = urllib.parse.urlparse(s.url)
            domains.add(p.netloc.lower().replace("www.", ""))
        print(f"  Category '{cat}': {len(cat_srcs)} approved sources across {len(domains)} distinct domains: {domains}")

    print("\n--- SIGNALS COLLECTED (VERIFIED PASSING GATE) ---")
    sig_by_cat = {}
    for sig in signals:
        sig_by_cat.setdefault(sig.category, []).append(sig)

    print(f"Total Verified Signals: {len(signals)}")
    for cat in ['customers', 'competitors', 'market', 'internal']:
        cat_sigs = sig_by_cat.get(cat, [])
        print(f"  Category '{cat}': {len(cat_sigs)} signals")
        for s in cat_sigs[:3]:
            print(f"    - [Signal #{s.id}] {s.headline} ({s.publisher_name}, {s.when_published or 'date unknown'})")

    if brief:
        print("\n" + "=" * 80)
        print(f"EXECUTIVE BRIEF #{brief.id} FOR {company_name.upper()}:")
        print("=" * 80)
        print(f"\n1. EXECUTIVE SUMMARY:\n{brief.executive_summary}\n")
        print(f"2. CUSTOMER SIGNALS:\n{brief.customer_signals}\n")
        print(f"3. COMPETITOR INTELLIGENCE:\n{brief.competitor_intelligence}\n")
        print(f"4. MARKET & REGULATORY:\n{brief.market_intelligence}\n")
        print(f"5. INTERNAL DATA:\n{brief.internal_intelligence}\n")
        print(f"6. OPPORTUNITIES:\n{brief.opportunities}\n")
        print(f"7. RISKS & THREATS:\n{brief.risks_threats}\n")
        print(f"8. RECOMMENDED ACTIONS:\n{brief.recommended_actions}\n")
        print(f"9. WHAT WE SHOULD WATCH:\n{brief.what_we_should_watch}\n")

    db.close()

if __name__ == "__main__":
    asyncio.run(run_linear())
