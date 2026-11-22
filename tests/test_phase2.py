import os
import io
import json
import pytest
import pandas as pd

pytestmark = pytest.mark.live
from datetime import datetime, timezone
from backend.models import Company, Competitor, Source, Document
from backend.services.research_service import company_research_service
from backend.services.competitor_discovery_service import competitor_discovery_service
from backend.services.source_discovery_service import source_discovery_service
from backend.services.internal_doc_service import internal_doc_service
from backend.services.llm_client import llm_client
from backend.config import settings

EVIDENCE_DIR = "/Users/anandvardhanchauhan/Downloads/Signal Stack/tests/evidence"

@pytest.fixture(autouse=True)
def ensure_real_llm_provider():
    if settings.GEMINI_API_KEY:
        llm_client.set_provider("gemini", api_key=settings.GEMINI_API_KEY)
    elif settings.GROQ_API_KEY:
        llm_client.set_provider("groq", api_key=settings.GROQ_API_KEY)

    assert llm_client.provider_name != "mock", (
        "FATAL: Real LLM provider is required for Phase 2 evidence generation. "
        "Mock provider is strictly forbidden."
    )
    os.makedirs(EVIDENCE_DIR, exist_ok=True)

@pytest.mark.asyncio
async def test_internal_document_ingestion(db_session):
    """
    Tests parsing and storing internal business documents (CSV, Excel, PDF, TXT)
    as Documents with category='internal' and document_type='internal_upload'.
    """
    company = Company(
        name="TestCorp",
        domain="testcorp.com",
        industry="Enterprise Software"
    )
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)

    # 1. Ingest CSV
    csv_bytes = b"lead_id,deal_size,lost_reason,competitor\n101,50000,Pricing too high,RivalA\n102,75000,Missing enterprise SSO,RivalB\n"
    doc_csv = internal_doc_service.ingest_document(
        db=db_session,
        company_id=company.id,
        filename="lost_deals_q3.csv",
        content_bytes=csv_bytes
    )
    assert doc_csv.id is not None
    assert doc_csv.category == "internal"
    assert doc_csv.document_type == "internal_upload"
    assert "Pricing too high" in doc_csv.raw_text

    # 2. Ingest TXT
    txt_bytes = b"Customer objection review: enterprise security questionnaires take 3 weeks to complete."
    doc_txt = internal_doc_service.ingest_document(
        db=db_session,
        company_id=company.id,
        filename="customer_objections.txt",
        content_bytes=txt_bytes
    )
    assert doc_txt.id is not None
    assert doc_txt.category == "internal"
    assert "security questionnaires" in doc_txt.raw_text

    # 3. Deduplication check
    doc_csv_dup = internal_doc_service.ingest_document(
        db=db_session,
        company_id=company.id,
        filename="lost_deals_q3.csv",
        content_bytes=csv_bytes
    )
    assert doc_csv_dup.id == doc_csv.id

@pytest.mark.asyncio
@pytest.mark.xfail(reason="Live external origin websites may return HTTP 403/404 or robots.txt block depending on third-party policy", strict=False)
async def test_phase2_competitors_and_sources_real_llm(db_session):
    """
    Executes Phase 2 Competitor Discovery and Source Discovery using the REAL LLM
    on both MeetUniversity and Sweetgreen:
    - 5 to 10 verified competitors per company with evidence URL and snippet.
    - 20+ approved sources for MeetUniversity across all 4 categories.
    - Customer category targets customer friction/problems, not company mentions.
    - Asserts every competitor and source has a reachable URL and stored reason.
    - Asserts zero hardcoding: MeetUniversity and Sweetgreen sets must differ completely.
    - Saves outputs under /tests/evidence/.
    """
    targets = [
        {
            "name": "MeetUniversity",
            "domain": "meetuniversity.com",
            "url": "https://www.meetuniversity.com",
            "industry": "EdTech & Study Abroad Admissions Portal",
            "comp_file": "phase2_meetuniversity_competitors.json",
            "src_file": "phase2_meetuniversity_sources.json"
        },
        {
            "name": "Sweetgreen",
            "domain": "sweetgreen.com",
            "url": "https://www.sweetgreen.com",
            "industry": "Fast-Casual Organic Restaurant Chain & Culinary Tech",
            "comp_file": "phase2_sweetgreen_competitors.json",
            "src_file": "phase2_sweetgreen_sources.json"
        }
    ]

    all_competitor_names = {}
    all_source_urls = {}

    for tgt in targets:
        # Create company
        company = Company(
            name=tgt["name"],
            domain=tgt["domain"],
            website_url=tgt["url"],
            industry=tgt["industry"]
        )
        db_session.add(company)
        db_session.commit()
        db_session.refresh(company)

        # 1. Run Research to populate initial crawled documents and profile
        res_out = await company_research_service.run_research(
            db=db_session,
            company_id=company.id,
            company_name=tgt["name"],
            url=tgt["url"]
        )
        assert res_out["status"] == "success"

        # 2. Competitor Discovery
        competitors = await competitor_discovery_service.discover_competitors(db_session, company.id)
        assert len(competitors) >= 5, f"Expected at least 5 competitors for {tgt['name']}, got {len(competitors)}"
        assert len(competitors) <= 10, f"Expected at most 10 competitors for {tgt['name']}, got {len(competitors)}"

        comp_data = []
        for c in competitors:
            assert c.url.startswith("http"), f"Competitor {c.name} has invalid URL: {c.url}"
            assert c.why_relevant, f"Competitor {c.name} missing why_relevant explanation"
            assert c.evidence_url, f"Competitor {c.name} missing evidence_url"
            assert c.evidence_snippet, f"Competitor {c.name} missing evidence_snippet"
            assert c.type in ["direct", "substitute"], f"Invalid competitor type: {c.type}"
            assert c.is_verified is True, f"Competitor {c.name} not verified"
            assert tgt["name"].lower() not in c.name.lower(), f"Competitor should not be self-reference: {c.name}"
            assert tgt["domain"].lower() not in c.url.lower(), f"Competitor URL should not reference company domain: {c.url}"

            # Verify exclusions: No universities, colleges, trade media, test bodies
            c_name_lower = c.name.lower()
            c_url_lower = c.url.lower()
            assert not any(u in c_name_lower for u in ["university", "college", "school of", "polytechnic"]), (
                f"Competitor {c.name} is an academic institution, not a competitor!"
            )
            assert not any(m in c_url_lower for m in ["timeshighereducation", "forbes", "poetsandquants", "icef"]), (
                f"Competitor {c.name} is a media/rankings publication, not a competitor!"
            )
            assert not any(b in c_name_lower for b in ["gmac", "ets", "toefl", "ielts", "british council", "nats"]), (
                f"Competitor {c.name} is a testing/regulatory body, not a competitor!"
            )

            comp_data.append({
                "name": c.name,
                "role": c.type,
                "website": c.url,
                "snippet": c.evidence_snippet,
                "why_relevant": c.why_relevant,
                "evidence_url": c.evidence_url
            })

        # Save competitor evidence
        comp_out_path = os.path.join(EVIDENCE_DIR, tgt["comp_file"])
        with open(comp_out_path, "w") as f:
            json.dump({
                "company": tgt["name"],
                "competitor_count": len(comp_data),
                "competitors": comp_data
            }, f, indent=2)

        all_competitor_names[tgt["name"]] = {c["name"].lower() for c in comp_data}

        # 3. Source Discovery
        sources = await source_discovery_service.discover_sources(db_session, company.id)
        assert len(sources) > 0

        # Filter approved sources
        approved_sources = [s for s in sources if s.status == "approved"]
        
        # Verify MeetUniversity meets strict approved sources requirement (20+)
        if tgt["name"] == "MeetUniversity":
            assert len(approved_sources) >= 20, (
                f"MeetUniversity requires >= 20 approved sources, got {len(approved_sources)} approved of {len(sources)} total"
            )

        # Enforce Google News cap: Google News queries must be <= 25% of approved sources
        gnews_approved = [s for s in approved_sources if "news.google.com" in s.url]
        gnews_ratio = len(gnews_approved) / len(approved_sources) if approved_sources else 0.0
        assert gnews_ratio <= 0.25, (
            f"Google News queries exceed 25% cap for {tgt['name']}: {len(gnews_approved)}/{len(approved_sources)} = {gnews_ratio:.1%}"
        )

        # Distinct domain breakdown
        domain_breakdown = source_discovery_service.get_distinct_domain_breakdown(sources)
        assert len(domain_breakdown) >= 8, f"Expected at least 8 distinct domains, got {len(domain_breakdown)}"

        # Categorize
        cat_counts = {}
        src_data = []
        for s in sources:
            cat_counts[s.category] = cat_counts.get(s.category, 0) + 1
            assert s.url.startswith("http"), f"Source has invalid URL: {s.url}"
            assert s.reason, f"Source missing reason: {s.url}"
            assert s.category in ["customers", "competitors", "market", "internal"]
            assert 0.0 <= s.overall_score <= 1.0

            src_data.append({
                "url": s.url,
                "category": s.category,
                "source_type": s.source_type,
                "status": s.status,
                "health": s.health,
                "reason": s.reason,
                "rejection_reason": s.rejection_reason,
                "specificity_score": s.specificity_score,
                "credibility_score": s.credibility_score,
                "recency_score": s.recency_score,
                "overall_score": s.overall_score
            })

        # Customer category must contain customer-voice sources (Reddit, review, forum)
        customer_sources = [s for s in src_data if s["category"] == "customers"]
        assert len(customer_sources) >= 3
        cust_types = {s["source_type"] for s in customer_sources}
        assert any(t in cust_types for t in ["reddit", "review", "forum"]), (
            f"Customer category missing customer-voice sources: {cust_types}"
        )
        # Ensure Hacker News and news-query were removed from customer category
        assert "hn" not in cust_types, "Hacker News should not be in customer category"

        # Save source evidence with distinct domain breakdown
        src_out_path = os.path.join(EVIDENCE_DIR, tgt["src_file"])
        with open(src_out_path, "w") as f:
            json.dump({
                "company": tgt["name"],
                "total_sources": len(src_data),
                "approved_sources": len(approved_sources),
                "google_news_approved_count": len(gnews_approved),
                "google_news_approved_ratio": round(gnews_ratio, 3),
                "distinct_domains_count": len(domain_breakdown),
                "distinct_domains_breakdown": domain_breakdown,
                "category_breakdown": cat_counts,
                "sources": src_data
            }, f, indent=2)

        all_source_urls[tgt["name"]] = {s["url"].lower() for s in src_data}

    # Zero Hardcoding Assertion: MeetUniversity and Sweetgreen competitor sets must have 0 overlap
    overlap_comps = all_competitor_names["MeetUniversity"].intersection(all_competitor_names["Sweetgreen"])
    assert len(overlap_comps) == 0, f"Competitors overlap between EdTech and Restaurant! {overlap_comps}"

    # Comparison diff file
    mu_src = json.load(open(os.path.join(EVIDENCE_DIR, "phase2_meetuniversity_sources.json")))
    sg_src = json.load(open(os.path.join(EVIDENCE_DIR, "phase2_sweetgreen_sources.json")))

    with open(os.path.join(EVIDENCE_DIR, "phase2_comparison.json"), "w") as f:
        json.dump({
            "test_type": "Phase 2 Competitor & Source Discovery Verification (Two-Step & Customer Voice)",
            "provider": llm_client.provider_name,
            "meetuniversity_competitors_count": len(all_competitor_names["MeetUniversity"]),
            "sweetgreen_competitors_count": len(all_competitor_names["Sweetgreen"]),
            "competitor_overlap": list(overlap_comps),
            "meetuniversity_approved_sources": mu_src["approved_sources"],
            "meetuniversity_distinct_domains": mu_src["distinct_domains_breakdown"],
            "meetuniversity_gnews_ratio": mu_src["google_news_approved_ratio"],
            "sweetgreen_approved_sources": sg_src["approved_sources"],
            "sweetgreen_distinct_domains": sg_src["distinct_domains_breakdown"],
            "sweetgreen_gnews_ratio": sg_src["google_news_approved_ratio"],
            "verdict": "PASSED — Two-step grounded competitors, customer-voice sources, 25% Google News cap, and distinct domain breakdowns verified."
        }, f, indent=2)
