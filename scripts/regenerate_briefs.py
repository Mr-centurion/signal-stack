import asyncio
import os
import re
from backend.database import SessionLocal
from backend.models import Company, Brief, Signal
from backend.services.brief_service import brief_service
from backend.services.llm_client import llm_client

async def run_regeneration():
    db = SessionLocal()
    os.makedirs("reports", exist_ok=True)

    companies_info = [
        (1, "meetuniversity", "MeetUniversity"),
        (2, "sweetgreen", "Sweetgreen"),
        (3, "posthog", "PostHog"),
        (4, "linear", "Linear"),
    ]

    models_used = {}

    print("=" * 80)
    print("STARTING AUTONOMOUS BRIEF REGENERATION FOR ALL FOUR COMPANIES")
    print("=" * 80)

    for cid, slug, name in companies_info:
        comp = db.query(Company).filter_by(id=cid).first()
        if not comp:
            print(f"[ERROR] Company {cid} ({name}) not found in DB.")
            continue

        print(f"\n--- Generating Brief for {name} (ID: {cid}) ---")
        brief = await brief_service.generate_monday_brief(db, cid)
        model = getattr(llm_client, "last_model_used", "gemini-robotics-er-2-preview")
        models_used[name] = model

        # Write markdown export
        md_path = f"reports/{slug}_brief.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(brief.markdown_export)

        # Write HTML export
        html_path = f"reports/{slug}_brief.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(brief.html_export)

        print(f"Exported {name} brief to {md_path} and {html_path}.")
        print(f"Model used for {name}: {model}")
        print(f"Verification Report: {brief.validator_report}")

    db.close()

    print("\n" + "=" * 80)
    print("MODEL USAGE REPORT")
    print("=" * 80)
    for name, model in models_used.items():
        print(f"Company: {name:<16} | Model Used: {model}")

    # Read and print the full Markdown text of meetuniversity_brief.md
    print("\n" + "=" * 80)
    print("FULL MARKDOWN TEXT OF reports/meetuniversity_brief.md")
    print("=" * 80)
    with open("reports/meetuniversity_brief.md", "r", encoding="utf-8") as f:
        mu_md = f.read()
    print(mu_md)
    print("=" * 80)

    # Grep check across all four reports
    print("\n" + "=" * 80)
    print("CROSS-BRIEF LEAKAGE AUDIT (Nigeria, Ibadan, and Cross-Company Names)")
    print("=" * 80)
    
    files = [
        "reports/meetuniversity_brief.md",
        "reports/sweetgreen_brief.md",
        "reports/posthog_brief.md",
        "reports/linear_brief.md"
    ]

    leakage_terms = ["nigeria", "ibadan"]
    company_names = ["meetuniversity", "sweetgreen", "posthog", "linear"]

    leakages_found = []
    for filepath in files:
        target_comp = os.path.basename(filepath).replace("_brief.md", "")
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()

        for idx, line in enumerate(lines, start=1):
            line_lower = line.lower()
            # Check Nigeria / Ibadan
            for term in leakage_terms:
                if term in line_lower:
                    leakages_found.append((filepath, idx, term, line.strip()))

            # Check cross-company names (other companies appearing where they shouldn't)
            for other_comp in company_names:
                if other_comp != target_comp and other_comp in line_lower:
                    leakages_found.append((filepath, idx, f"cross-company:{other_comp}", line.strip()))

    if not leakages_found:
        print("PASSED: Zero leakage detected. No mentions of 'Nigeria', 'Ibadan', or cross-company names found in any brief.")
    else:
        print(f"WARNING: Found {len(leakages_found)} potential leakage items:")
        for fp, ln, term, text in leakages_found:
            print(f"  {fp}:{ln} [{term}] -> {text}")

if __name__ == "__main__":
    asyncio.run(run_regeneration())
