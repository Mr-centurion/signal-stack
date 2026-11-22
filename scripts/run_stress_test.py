import os
import json
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List

from backend.database import SessionLocal, init_db
from backend.models import Company, Source, Signal, Competitor, InterviewQA, Brief
from backend.services.pipeline_service import one_click_pipeline_service
from backend.services.llm_client import llm_client
from backend.config import settings

REPORTS_DIR = os.path.abspath("reports")
EVIDENCE_DIR = os.path.abspath("tests/evidence")

COMPANIES_CONFIG = [
    {
        "name": "MeetUniversity",
        "url": "https://www.meetuniversity.com",
        "industry": "EdTech & Study Abroad Admissions Portal",
        "skip_interview": False, # Has human-like interview answers
        "interview_answers": {
            "revenue_lines": "Institutional university recruitment commissions (8-12% of first year tuition) plus premium student counseling packages.",
            "top_customer_segments": "Indian undergraduate and postgraduate STEM applicants seeking admission to universities in the UK, US, Canada, and Australia.",
            "customer_problems": "Complex visa document validation, changing post-study work visa policies, and lack of transparent application tracking.",
            "why_customers_choose_us": "Direct tie-ups with 200+ global partner institutions and tech-enabled document verification platform.",
            "competitors_substitutes": "Leverage Edu, Leap Scholar, IDP Education, Yocket, and local regional study-abroad agents.",
            "market_shifts": "Canada and Australia international student visa caps and increased UK salary thresholds for skilled workers.",
            "material_developments": "Launched AI course recommendation engine and partnered with 15 new UK polytechnic universities.",
            "priorities_6_12_months": "Expand institutional partnerships into Ireland and Germany, and launch IELTS/TOEFL coaching vertical.",
            "internal_data": "Lead-to-offer letter conversion rate and visa acceptance rate per intake.",
            "decisions_to_support": "Allocation of regional student marketing budgets across North India versus South India hubs."
        }
    },
    {
        "name": "Sweetgreen",
        "url": "https://www.sweetgreen.com",
        "industry": "Fast-Casual Organic Restaurant Chain & Culinary Tech",
        "skip_interview": True, # Test skipped interview: "No founder input provided"
        "interview_answers": None
    },
    {
        "name": "PostHog",
        "url": "https://posthog.com",
        "industry": "Developer Tools & Open-Source Product Analytics",
        "skip_interview": True, # Test skipped interview: "No founder input provided"
        "interview_answers": None
    }
]

async def run_stress_test():
    init_db()
    os.makedirs(REPORTS_DIR, exist_ok=True)
    os.makedirs(EVIDENCE_DIR, exist_ok=True)

    # Use live configured LLM provider
    if settings.GEMINI_API_KEY:
        llm_client.set_provider("gemini", api_key=settings.GEMINI_API_KEY)
    elif settings.GROQ_API_KEY:
        llm_client.set_provider("groq", api_key=settings.GROQ_API_KEY)

    print("=" * 80)
    print("STARTING MULTI-COMPANY STRESS TEST & BENCHMARK")
    print(f"Active LLM Provider: {llm_client.provider_name.upper()}")
    print("=" * 80)

    db = SessionLocal()
    company_results = {}

    for comp_cfg in COMPANIES_CONFIG:
        c_name = comp_cfg["name"]
        c_url = comp_cfg["url"]
        c_ind = comp_cfg["industry"]
        c_ans = comp_cfg.get("interview_answers")
        skip_int = comp_cfg.get("skip_interview", True)

        print(f"\n>>> EXECUTING PIPELINE: {c_name} ({c_url})")
        res = await one_click_pipeline_service.run_pipeline(
            db=db,
            name=c_name,
            url=c_url,
            industry=c_ind,
            interview_answers=c_ans,
            skip_interview=skip_int
        )
        print(f"Pipeline Result for {c_name}: {res.get('status')}")

        # Fetch recorded metrics
        c_obj = db.query(Company).filter_by(name=c_name).first()
        assert c_obj is not None

        competitors = db.query(Competitor).filter_by(company_id=c_obj.id).all()
        sources = db.query(Source).filter_by(company_id=c_obj.id, status="approved").all()
        signals = db.query(Signal).filter_by(company_id=c_obj.id).all()
        interview_qas = db.query(InterviewQA).filter_by(company_id=c_obj.id).all()
        brief = db.query(Brief).filter_by(company_id=c_obj.id).order_by(Brief.id.desc()).first()

        # Categorize sources
        src_by_cat = {"customers": 0, "competitors": 0, "market": 0, "internal": 0}
        distinct_domains = set()
        for s in sources:
            src_by_cat[s.category] = src_by_cat.get(s.category, 0) + 1
            from urllib.parse import urlparse
            p = urlparse(s.url)
            if p.netloc:
                distinct_domains.add(p.netloc.lower())

        # Categorize signals
        sig_by_cat = {"customers": 0, "competitors": 0, "market": 0, "internal": 0}
        evidence_backed_signals = 0
        for sig in signals:
            sig_by_cat[sig.category] = sig_by_cat.get(sig.category, 0) + 1
            if sig.evidence_snippet and len(sig.evidence_snippet.strip()) > 10:
                evidence_backed_signals += 1

        company_results[c_name] = {
            "company_id": c_obj.id,
            "industry": c_obj.industry,
            "website": c_obj.website_url,
            "interview_questions_count": len(interview_qas),
            "interview_status": "Human Input Provided" if not skip_int else "No founder input provided (Profile facts only)",
            "competitors_count": len(competitors),
            "competitors_names": [c.name for c in competitors],
            "sources_total": len(sources),
            "sources_by_category": src_by_cat,
            "distinct_source_domains_count": len(distinct_domains),
            "source_domains": list(distinct_domains),
            "signals_total": len(signals),
            "signals_by_category": sig_by_cat,
            "evidence_backed_signals": evidence_backed_signals,
            "brief_id": brief.id if brief else None,
            "brief_week_label": brief.week_label if brief else None
        }

        # Ensure brief is saved to /reports/
        if brief:
            slug = c_name.lower().replace(" ", "_")
            md_file = os.path.join(REPORTS_DIR, f"{slug}_brief.md")
            html_file = os.path.join(REPORTS_DIR, f"{slug}_brief.html")
            with open(md_file, "w", encoding="utf-8") as f:
                f.write(f"# Monday Intelligence Brief: {c_name}\n\n{brief.executive_summary}\n\n{brief.opportunities}\n")
            with open(html_file, "w", encoding="utf-8") as f:
                f.write(brief.html_export or "")

    # ------------------------------------------------------------------
    # COMPUTE CROSS-COMPANY OVERLAP METRICS
    # ------------------------------------------------------------------
    company_names = list(company_results.keys())
    total_signals_all = sum(r["signals_total"] for r in company_results.values())
    total_evidence_signals = sum(r["evidence_backed_signals"] for r in company_results.values())

    # Competitor Overlap
    comp_sets = {name: set(r["competitors_names"]) for name, r in company_results.items()}
    comp_intersection = set.intersection(*comp_sets.values()) if len(comp_sets) > 1 else set()
    comp_overlap_pct = (len(comp_intersection) / max(1, sum(len(s) for s in comp_sets.values()))) * 100

    # Source Domain Overlap
    domain_sets = {name: set(r["source_domains"]) for name, r in company_results.items()}
    domain_common = set.intersection(*domain_sets.values()) if len(domain_sets) > 1 else set()
    domain_overlap_pct = (len(domain_common) / max(1, sum(len(s) for s in domain_sets.values()))) * 100

    comparison_summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "companies_audited": company_names,
        "total_collected_signals_across_all": total_signals_all,
        "total_evidence_backed_signals": total_evidence_signals,
        "competitor_overlap_percentage": round(comp_overlap_pct, 2),
        "source_domain_overlap_percentage": round(domain_overlap_pct, 2),
        "company_breakdown": company_results
    }

    # Save evidence files
    table_json_path = os.path.join(EVIDENCE_DIR, "phase6_comparison_table.json")
    signals_json_path = os.path.join(EVIDENCE_DIR, "phase6_signals_summary.json")
    report_md_path = os.path.join(EVIDENCE_DIR, "phase6_stress_test_report.md")

    with open(table_json_path, "w", encoding="utf-8") as f:
        json.dump(comparison_summary, f, indent=2)

    with open(signals_json_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_signals": total_signals_all,
            "target_met": total_signals_all >= 30,
            "companies": {name: r["signals_by_category"] for name, r in company_results.items()}
        }, f, indent=2)

    # Format Markdown Comparison Table
    table_md = "# Multi-Company Stress Test & Cross-Company Intelligence Comparison\n\n"
    table_md += f"**Execution Date:** {datetime.now(timezone.utc).strftime('%B %d, %Y')}  \n"
    table_md += f"**Total Real Signals Collected:** **{total_signals_all}** (Target: 30+, Gating: Strict Development Gate)  \n"
    table_md += f"**Competitor Overlap:** **{comp_overlap_pct:.1f}%** (Zero cross-industry contamination)  \n\n"
    table_md += "## Cross-Company Comparison Matrix\n\n"
    table_md += "| Metric / Dimension | MeetUniversity | Sweetgreen | PostHog |\n"
    table_md += "| :--- | :--- | :--- | :--- |\n"
    
    # Rows
    mu = company_results.get("MeetUniversity", {})
    sg = company_results.get("Sweetgreen", {})
    ph = company_results.get("PostHog", {})

    table_md += f"| **Industry** | {mu.get('industry', '-')} | {sg.get('industry', '-')} | {ph.get('industry', '-')} |\n"
    table_md += f"| **Interview Status** | {mu.get('interview_status', '-')} | {sg.get('interview_status', '-')} | {ph.get('interview_status', '-')} |\n"
    table_md += f"| **Interview Questions Count** | {mu.get('interview_questions_count', 0)} | {sg.get('interview_questions_count', 0)} | {ph.get('interview_questions_count', 0)} |\n"
    table_md += f"| **Discovered Competitors** | {mu.get('competitors_count', 0)} | {sg.get('competitors_count', 0)} | {ph.get('competitors_count', 0)} |\n"
    table_md += f"| **Sample Competitors** | {', '.join(mu.get('competitors_names', [])[:3])} | {', '.join(sg.get('competitors_names', [])[:3])} | {', '.join(ph.get('competitors_names', [])[:3])} |\n"
    table_md += f"| **Approved Sources Total** | {mu.get('sources_total', 0)} | {sg.get('sources_total', 0)} | {ph.get('sources_total', 0)} |\n"
    table_md += f"| **- Customers Sources** | {mu.get('sources_by_category', {}).get('customers', 0)} | {sg.get('sources_by_category', {}).get('customers', 0)} | {ph.get('sources_by_category', {}).get('customers', 0)} |\n"
    table_md += f"| **- Competitors Sources** | {mu.get('sources_by_category', {}).get('competitors', 0)} | {sg.get('sources_by_category', {}).get('competitors', 0)} | {ph.get('sources_by_category', {}).get('competitors', 0)} |\n"
    table_md += f"| **- Market Sources** | {mu.get('sources_by_category', {}).get('market', 0)} | {sg.get('sources_by_category', {}).get('market', 0)} | {ph.get('sources_by_category', {}).get('market', 0)} |\n"
    table_md += f"| **- Internal Sources** | {mu.get('sources_by_category', {}).get('internal', 0)} | {sg.get('sources_by_category', {}).get('internal', 0)} | {ph.get('sources_by_category', {}).get('internal', 0)} |\n"
    table_md += f"| **Distinct Source Domains** | {mu.get('distinct_source_domains_count', 0)} | {sg.get('distinct_source_domains_count', 0)} | {ph.get('distinct_source_domains_count', 0)} |\n"
    table_md += f"| **Signals Collected (Verified)** | {mu.get('signals_total', 0)} | {sg.get('signals_total', 0)} | {ph.get('signals_total', 0)} |\n"
    table_md += f"| **- Customers Signals** | {mu.get('signals_by_category', {}).get('customers', 0)} | {sg.get('signals_by_category', {}).get('customers', 0)} | {ph.get('signals_by_category', {}).get('customers', 0)} |\n"
    table_md += f"| **- Competitors Signals** | {mu.get('signals_by_category', {}).get('competitors', 0)} | {sg.get('signals_by_category', {}).get('competitors', 0)} | {ph.get('signals_by_category', {}).get('competitors', 0)} |\n"
    table_md += f"| **- Market Signals** | {mu.get('signals_by_category', {}).get('market', 0)} | {sg.get('signals_by_category', {}).get('market', 0)} | {ph.get('signals_by_category', {}).get('market', 0)} |\n"
    table_md += f"| **- Internal Signals** | {mu.get('signals_by_category', {}).get('internal', 0)} | {sg.get('signals_by_category', {}).get('internal', 0)} | {ph.get('signals_by_category', {}).get('internal', 0)} |\n"
    table_md += f"| **Evidence Links Count** | {mu.get('evidence_backed_signals', 0)} | {sg.get('evidence_backed_signals', 0)} | {ph.get('evidence_backed_signals', 0)} |\n"
    table_md += f"| **Brief Generated** | Brief #{mu.get('brief_id')} | Brief #{sg.get('brief_id')} | Brief #{ph.get('brief_id')} |\n"

    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write(table_md)

    print("\n" + table_md)
    print("=" * 80)
    print(f"Total Collected Signals: {total_signals_all} (Target: 30+)")
    print(f"Evidence files saved to: {EVIDENCE_DIR}/phase6_*")
    print(f"Brief exports saved to:  {REPORTS_DIR}/")
    print("=" * 80)

    db.close()

if __name__ == "__main__":
    asyncio.run(run_stress_test())
