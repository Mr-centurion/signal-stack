import os
import re
import json
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse
from sqlalchemy.orm import Session

from backend.models import Company, ProfileFact, InterviewQA, Competitor, Source, CrawlRun, Signal, Brief
from backend.services.research_service import company_research_service
from backend.services.competitor_discovery_service import competitor_discovery_service
from backend.services.source_discovery_service import source_discovery_service
from backend.crawler.engine import crawl_service
from backend.services.analysis_engine import analysis_engine
from backend.services.brief_service import brief_service

class OneClickPipelineService:
    """
    Unified One-Click Onboard & Intelligence Pipeline:
    Executes the complete strategic intelligence lifecycle for any company:
    1. Research & Profile (Crawling, Verified Facts vs Assumptions)
    2. Adaptive Interview (Human-answered, or explicitly skipped: 'No founder input provided')
    3. Competitor Discovery (Two-stage hypotheses + quote-verified websites)
    4. Source Discovery (4 categories: customers, competitors, market, internal)
    5. Crawl Engine (Change detection, snapshot diffs, publisher token resolution)
    6. Analysis Engine (Development gate, taxonomy, multi-factor priority ranking, verification caps)
    7. Monday Intelligence Brief (10 sections, claim audit, source appendix, markdown & HTML exports)
    """

    async def run_pipeline(
        self,
        db: Session,
        name: str,
        url: str,
        industry: Optional[str] = None,
        interview_answers: Optional[Dict[str, str]] = None,
        skip_interview: bool = True
    ) -> Dict[str, Any]:
        stages: List[Dict[str, Any]] = []
        parsed = urlparse(url if url.startswith("http") else f"https://{url}")
        domain = parsed.netloc or url

        # -------------------------------------------------------------
        # STAGE 1: Company Registration & Deep Research
        # -------------------------------------------------------------
        stage_research = {"stage": "research", "status": "running", "details": "Initiating deep research..."}
        stages.append(stage_research)
        try:
            company = db.query(Company).filter_by(name=name).first()
            if not company:
                company = Company(
                    name=name,
                    domain=domain,
                    website_url=url,
                    industry=industry or "Technology"
                )
                db.add(company)
                db.commit()
                db.refresh(company)
            else:
                company.website_url = url
                if industry:
                    company.industry = industry
                db.commit()

            research_res = await company_research_service.run_research(db, company.id, name, url)
            stage_research["status"] = "completed"
            stage_research["details"] = (
                f"Crawled {research_res.get('pages_crawled', 1)} pages. "
                f"Extracted {research_res.get('verified_facts_count', 0)} verified facts, "
                f"{research_res.get('assumptions_count', 0)} assumptions."
            )
        except Exception as e:
            stage_research["status"] = "failed"
            stage_research["error"] = str(e)
            print(f"[PIPELINE ERROR: RESEARCH] {e}")
            return {"status": "failed", "failed_stage": "research", "stages": stages}

        await asyncio.sleep(0.5)

        # -------------------------------------------------------------
        # STAGE 2: Profile & Facts
        # -------------------------------------------------------------
        stage_profile = {"stage": "profile", "status": "running", "details": "Structuring verified company dossier..."}
        stages.append(stage_profile)
        try:
            facts_count = db.query(ProfileFact).filter_by(company_id=company.id).count()
            stage_profile["status"] = "completed"
            stage_profile["details"] = f"Structured intelligence profile anchored with {facts_count} verified facts & hypotheses."
        except Exception as e:
            stage_profile["status"] = "failed"
            stage_profile["error"] = str(e)

        await asyncio.sleep(0.5)

        # -------------------------------------------------------------
        # STAGE 3: Interview (Human-answered or explicitly skipped)
        # -------------------------------------------------------------
        stage_interview = {"stage": "interview", "status": "running", "details": "Processing executive input..."}
        stages.append(stage_interview)
        try:
            if interview_answers and len(interview_answers) > 0:
                # Deduplicate and sync interview answers: never duplicate question rows
                existing_qas = {qa.topic: qa for qa in db.query(InterviewQA).filter_by(company_id=company.id).all()}
                # Remove duplicate topic entries if any exist
                all_company_qas = db.query(InterviewQA).filter_by(company_id=company.id).order_by(InterviewQA.id.asc()).all()
                seen_topics = set()
                for q_item in all_company_qas:
                    if q_item.topic in seen_topics:
                        db.delete(q_item)
                    else:
                        seen_topics.add(q_item.topic)
                db.commit()

                answered_count = 0
                for topic, ans_text in interview_answers.items():
                    if ans_text and ans_text.strip():
                        clean_ans = ans_text.strip()
                        if topic in existing_qas:
                            qa = existing_qas[topic]
                            qa.answer = clean_ans
                            qa.is_skipped = False
                            qa.updated_at = datetime.now(timezone.utc)
                        else:
                            qa = InterviewQA(
                                company_id=company.id,
                                topic=topic,
                                category="internal",
                                question=f"Executive input on {topic}",
                                answer=clean_ans,
                                is_skipped=False,
                                created_at=datetime.now(timezone.utc),
                                updated_at=datetime.now(timezone.utc)
                            )
                            db.add(qa)
                        answered_count += 1
                db.commit()
                stage_interview["status"] = "completed"
                stage_interview["details"] = f"Recorded {answered_count} executive strategic inputs (max 10 topics)."
            else:
                # Strictly NEVER invent answers: record as explicitly skipped
                stage_interview["status"] = "skipped"
                stage_interview["details"] = "No founder input provided (relying strictly on verified profile facts)."
        except Exception as e:
            stage_interview["status"] = "failed"
            stage_interview["error"] = str(e)

        await asyncio.sleep(0.5)

        # -------------------------------------------------------------
        # STAGE 4: Competitor Discovery (Hypotheses + Web Verification)
        # -------------------------------------------------------------
        stage_comp = {"stage": "competitors", "status": "running", "details": "Discovering competitors via 2-stage verification..."}
        stages.append(stage_comp)
        try:
            comps = await competitor_discovery_service.discover_competitors(db, company.id)
            stage_comp["status"] = "completed"
            stage_comp["count"] = len(comps)
            stage_comp["details"] = f"Discovered and verified {len(comps)} direct and substitute competitors with quote evidence."
        except Exception as e:
            stage_comp["status"] = "failed"
            stage_comp["error"] = str(e)
            print(f"[PIPELINE ERROR: COMPETITORS] {e}")

        await asyncio.sleep(0.5)

        # -------------------------------------------------------------
        # STAGE 5: Source Discovery (4 Categories)
        # -------------------------------------------------------------
        stage_src = {"stage": "sources", "status": "running", "details": "Discovering signal sources across 4 categories..."}
        stages.append(stage_src)
        try:
            sources = await source_discovery_service.discover_sources(db, company.id)
            approved = [s for s in sources if s.status == "approved"]
            stage_src["status"] = "completed"
            stage_src["count"] = len(approved)
            stage_src["details"] = f"Approved {len(approved)} signal sources across customers, competitors, market, and internal."
        except Exception as e:
            stage_src["status"] = "failed"
            stage_src["error"] = str(e)
            print(f"[PIPELINE ERROR: SOURCES] {e}")

        await asyncio.sleep(0.5)

        # -------------------------------------------------------------
        # STAGE 6: Crawl Engine & Change Detection
        # -------------------------------------------------------------
        stage_crawl = {"stage": "crawl", "status": "running", "details": "Fetching approved sources and detecting changes..."}
        stages.append(stage_crawl)
        try:
            crawl_run = await crawl_service.crawl_company(db, company.id)
            new_items = crawl_run.items_new or 0
            changed_items = crawl_run.items_changed or 0
            stage_crawl["status"] = "completed"
            stage_crawl["details"] = f"CrawlRun #{crawl_run.id} finished. {new_items} new items, {changed_items} changed developments."
        except Exception as e:
            stage_crawl["status"] = "failed"
            stage_crawl["error"] = str(e)
            print(f"[PIPELINE ERROR: CRAWL] {e}")

        await asyncio.sleep(0.5)

        # -------------------------------------------------------------
        # STAGE 7: Strategic Analysis & Multi-Factor Ranking
        # -------------------------------------------------------------
        stage_analysis = {"stage": "analysis", "status": "running", "details": "Filtering development gate and ranking priority..."}
        stages.append(stage_analysis)
        try:
            signals = await analysis_engine.analyze_and_rank_company_signals(db, company.id)
            stage_analysis["status"] = "completed"
            stage_analysis["signals_count"] = len(signals)
            stage_analysis["details"] = f"Extracted and priority-ranked {len(signals)} verified signals with orthogonal metric scoring."
        except Exception as e:
            stage_analysis["status"] = "failed"
            stage_analysis["error"] = str(e)
            print(f"[PIPELINE ERROR: ANALYSIS] {e}")

        await asyncio.sleep(0.5)

        # -------------------------------------------------------------
        # STAGE 8: Monday Intelligence Brief Generation & Exports
        # -------------------------------------------------------------
        stage_brief = {"stage": "brief", "status": "running", "details": "Synthesizing 10-section executive brief..."}
        stages.append(stage_brief)
        try:
            brief = await brief_service.generate_monday_brief(db, company.id)
            stage_brief["status"] = "completed"
            stage_brief["brief_id"] = brief.id
            stage_brief["week_label"] = brief.week_label

            # Export to /reports/
            slug = re.sub(r"[^a-zA-Z0-9_-]", "_", company.name.lower())
            reports_dir = os.path.abspath("reports")
            os.makedirs(reports_dir, exist_ok=True)
            
            md_path = os.path.join(reports_dir, f"{slug}_brief.md")
            html_path = os.path.join(reports_dir, f"{slug}_brief.html")

            with open(md_path, "w", encoding="utf-8") as f:
                f.write(f"# Monday Intelligence Brief: {company.name}\n\n")
                f.write(f"**Week Label:** {brief.week_label}\n\n")
                f.write(f"## Executive Summary\n{brief.executive_summary}\n\n")
                f.write(f"## Customer Signals & Voice\n{brief.customer_signals}\n\n")
                f.write(f"## Competitor Intelligence\n{brief.competitor_intelligence}\n\n")
                f.write(f"## Market & Regulatory Shifts\n{brief.market_intelligence}\n\n")
                f.write(f"## Internal Business Intelligence\n{brief.internal_intelligence}\n\n")
                f.write(f"## Actionable Opportunities\n{brief.opportunities}\n\n")
                f.write(f"## Strategic Risks & Threats\n{brief.risks_threats}\n\n")
                f.write(f"## Recommended Actions This Week\n{brief.recommended_actions}\n\n")
                f.write(f"## What We Should Watch\n{brief.what_we_should_watch}\n\n")
                f.write(f"## Source Provenance Appendix\n```json\n{brief.source_appendix}\n```\n")

            with open(html_path, "w", encoding="utf-8") as f:
                f.write(brief.html_export or f"<html><body><h1>{company.name} Brief</h1></body></html>")

            stage_brief["details"] = f"Brief #{brief.id} synthesized. Exported to reports/{slug}_brief.md and .html."
        except Exception as e:
            stage_brief["status"] = "failed"
            stage_brief["error"] = str(e)
            print(f"[PIPELINE ERROR: BRIEF] {e}")

        return {
            "status": "success",
            "company_id": company.id,
            "company_name": company.name,
            "stages": stages
        }

one_click_pipeline_service = OneClickPipelineService()
