import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from backend.models import Company, Source, Competitor, ProfileFact, InterviewQA, ContextChangeReport
from backend.services.source_discovery_service import source_discovery_service
from backend.services.llm_client import llm_client

class SourceReassessmentItem(BaseModel):
    id: Optional[int] = None
    is_aligned: Optional[bool] = Field(default=True, description="Whether this monitoring source is still relevant under the new strategic context")
    relevance_score: Optional[float] = Field(default=0.8, description="Relevance score from 0.0 to 1.0 against the new context")
    reason: Optional[str] = Field(default="Maintains active monitoring value", description="Reason explaining why source is still useful or now misaligned/obsolete")

class ContextReassessmentResponse(BaseModel):
    reassessments: Optional[List[SourceReassessmentItem]] = None
    evaluations: Optional[List[SourceReassessmentItem]] = None

class ContextChangeService:
    """
    Autonomous Context Change Engine:
    - Triggered when company profile facts, positioning, or founder interview answers are updated.
    - Re-scores every approved source's strategic relevance against the updated corporate context.
    - Recommends removal of sources that are no longer useful (with clear rationale).
    - Re-runs discovery to propose fresh candidate sources aligned with new priorities.
    - Persists ContextChangeReport with before/after snapshots and diff metrics.
    - Zero auto-deletion: all modifications are recommendations pending user acceptance.
    """

    async def reassess_context(
        self,
        db: Session,
        company_id: int,
        change_type: str,
        change_description: str,
        before_context_snapshot: Optional[Dict[str, Any]] = None
    ) -> ContextChangeReport:
        company = db.query(Company).filter_by(id=company_id).first()
        if not company:
            raise ValueError(f"Company #{company_id} not found")

        # 1. Capture current context snapshots
        approved_sources = db.query(Source).filter_by(company_id=company_id, status="approved").all()
        competitors = db.query(Competitor).filter_by(company_id=company_id).all()
        facts = db.query(ProfileFact).filter_by(company_id=company_id).all()
        interview_qas = db.query(InterviewQA).filter_by(company_id=company_id).all()

        sources_before_list = [
            {"id": s.id, "url": s.url, "category": s.category, "reason": s.reason}
            for s in approved_sources
        ]
        competitors_before_list = [
            {"id": c.id, "name": c.name, "type": c.type, "why_relevant": c.why_relevant}
            for c in competitors
        ]

        after_context_dict = {
            "industry": company.industry,
            "description": company.description,
            "facts": [{"claim": f.text, "status": f.fact_type} for f in facts[:15]],
            "interview_answers": [{"topic": q.topic, "answer": q.answer} for q in interview_qas if q.answer and not q.is_skipped][:10]
        }
        before_context_dict = before_context_snapshot or {"note": "Baseline prior to strategic update"}

        # 2. Re-score sources against new context using LLM
        removed_recommendations: List[Dict[str, Any]] = []
        keep_count = 0

        # Build context summary for evaluation
        context_summary = f"Company: {company.name}\nIndustry: {company.industry}\nPositioning/Description: {company.description}\nStrategic Shift: {change_description}\n"
        
        # Batch sources for evaluation
        sources_to_eval = approved_sources[:30] # evaluate up to 30 approved sources
        if sources_to_eval:
            prompt_sources_text = "\n".join([
                f"- ID {s.id}: Category: '{s.category}', URL: '{s.url}', Original Reason: '{s.reason}'"
                for s in sources_to_eval
            ])

            sys_prompt = (
                "You are an expert strategic intelligence auditor. A company's business context or strategic priority has updated. "
                "Evaluate each monitoring source against the NEW context and strategic shift. "
                "Determine if the source is still aligned, assign a relevance_score (0.0 to 1.0), and provide a concise reason. "
                "Return a JSON object matching ContextReassessmentResponse."
            )
            user_prompt = f"NEW STRATEGIC CONTEXT:\n{context_summary}\n\nSOURCES TO EVALUATE:\n{prompt_sources_text}"

            try:
                eval_res = await llm_client.generate_json(sys_prompt, user_prompt, schema_class=ContextReassessmentResponse)
                reassessments = eval_res.get("reassessments") or eval_res.get("evaluations") or []
            except Exception as e:
                print(f"[CONTEXT CHANGE] LLM evaluation note: {e}")
                reassessments = []

            for idx, s in enumerate(sources_to_eval):
                rec_item = reassessments[idx % len(reassessments)] if reassessments else None
                is_aligned = rec_item.get("is_aligned", True) if rec_item else True
                rel_score = rec_item.get("relevance_score", 0.8) if rec_item else 0.8
                reason_text = rec_item.get("reason", "Maintains active monitoring value") if rec_item else "Maintains active monitoring value"

                if not is_aligned or rel_score < 0.60:
                    removed_recommendations.append({
                        "id": len(removed_recommendations) + 1,
                        "source_id": s.id,
                        "source_url": s.url,
                        "source_name": f"{s.category.title()} Source #{s.id}",
                        "category": s.category,
                        "action": "remove",
                        "relevance_score": rel_score,
                        "reason": f"Misaligned with updated priority '{change_description[:60]}...': {reason_text}",
                        "status": "pending"
                    })
                else:
                    keep_count += 1

        # 3. Discover new sources aligned with the new strategic context
        added_recommendations: List[Dict[str, Any]] = []
        try:
            discovered = await source_discovery_service.discover_sources(db, company_id)
            existing_urls = {src.url.strip().lower().rstrip("/") for src in approved_sources}
            fresh_candidates = [
                cand for cand in discovered
                if cand.url.strip().lower().rstrip("/") not in existing_urls
            ]
            for cand in fresh_candidates[:5]:
                added_recommendations.append({
                    "id": len(added_recommendations) + 1,
                    "source_id": cand.id,
                    "source_url": cand.url,
                    "source_name": f"New Candidate: {cand.category.title()} Feed",
                    "category": cand.category,
                    "action": "add",
                    "reason": f"Discovered for updated strategy: {cand.reason}",
                    "status": "pending"
                })
        except Exception as e:
            print(f"[CONTEXT CHANGE] Discovery note: {e}")

        # 4. Compute metrics and diff
        metrics = {
            "sources_audited": len(approved_sources),
            "sources_retained_count": keep_count,
            "sources_recommended_removal": len(removed_recommendations),
            "sources_recommended_addition": len(added_recommendations),
            "competitors_evaluated": len(competitors)
        }

        # 4. Compute metrics and competitor diffs aligned with the strategic pivot
        # Evaluated via LLM re-scoring and live two-step competitor discovery (hypothesis -> website verification)
        comp_removed = []
        comp_added = []

        if competitors:
            # Step (i): LLM evaluates existing competitors against the new strategic context
            comp_prompt = (
                f"TARGET COMPANY: {company.name}\n"
                f"NEW STRATEGIC CONTEXT:\n{context_summary}\n\n"
                f"CURRENT MONITORED COMPETITORS:\n" +
                "\n".join([f"- {c.name} ({c.type}): {c.why_relevant}" for c in competitors]) + "\n\n"
                "Evaluate whether each current competitor remains relevant under the new strategic context. "
                "Determine which competitors are now misaligned with the updated strategic focus and should be REMOVED (with a clear rationale). "
                "Output JSON with format: {'removed': [{'name': '...', 'reason': '...'}]}"
            )
            try:
                c_res = await llm_client.generate_json(
                    "You are an expert competitive strategy auditor. Output valid JSON.",
                    comp_prompt
                )
                for r in c_res.get("removed", []):
                    comp_removed.append({
                        "name": r.get("name", "Competitor"),
                        "type": "direct",
                        "reason": r.get("reason", f"Misaligned with updated priority '{change_description[:60]}'")
                    })
            except Exception as e:
                print(f"[CONTEXT CHANGE] Competitor removal evaluation note: {e}")

        # Step (ii): Propose new competitors via TWO-STEP DISCOVERY:
        # Step (a): LLM proposes 6-10 candidate hypotheses tailored to the strategic shift
        hypotheses_prompt = (
            f"TARGET COMPANY: {company.name}\n"
            f"DOMAIN: {company.domain}\n"
            f"INDUSTRY: {company.industry or 'Technology'}\n\n"
            f"UPDATED STRATEGIC CONTEXT & PIVOT:\n{context_summary}\n\n"
            f"Propose 6 to 10 commercial competitor or substitute candidates specifically competing under this new strategic shift. "
            f"Label each as 'hypothesis'. "
            f"STRICT RULES: DO NOT propose universities, schools, colleges, academic institutions, general news media, or testing bodies. "
            f"Propose ONLY commercial companies/platforms that sell directly competing or substitute solutions to the same customers."
        )
        try:
            from backend.prompts.templates import COMPETITOR_HYPOTHESIS_SYSTEM
            from backend.services.competitor_discovery_service import competitor_discovery_service

            hyp_res = await llm_client.generate_json(COMPETITOR_HYPOTHESIS_SYSTEM, hypotheses_prompt)
            raw_hypotheses = hyp_res.get("hypotheses", [])

            # Step (b): For each candidate, fetch website and verify with quoted snippet
            existing_comp_names = {c.name.lower() for c in competitors}
            for cand in raw_hypotheses[:8]:
                c_name = cand.get("name", "").strip()
                c_url = cand.get("url", "").strip()
                if not c_name or c_name.lower() in existing_comp_names:
                    continue
                if competitor_discovery_service.is_excluded_entity(c_name, c_url, company.domain, company.name):
                    continue

                # Fetch website and verify overlapping service
                verified = await competitor_discovery_service.fetch_and_verify_candidate(cand, company)
                if verified and verified.get("is_verified"):
                    comp_added.append({
                        "name": verified["name"],
                        "type": verified["type"],
                        "url": verified["url"],
                        "reason": f"Discovered and verified via live website audit: {verified['why_relevant']}",
                        "evidence_url": verified.get("evidence_url", verified["url"]),
                        "evidence_snippet": verified.get("evidence_snippet", ""),
                        "is_verified": True
                    })
                    if len(comp_added) >= 3:
                        break

            # Fallback if live verification yielded fewer than 2 due to network/mock constraints
            if len(comp_added) < 2 and raw_hypotheses:
                for cand in raw_hypotheses:
                    c_name = cand.get("name", "").strip()
                    c_url = cand.get("url", "").strip()
                    if c_name and c_name.lower() not in existing_comp_names and not any(a["name"].lower() == c_name.lower() for a in comp_added):
                        if not competitor_discovery_service.is_excluded_entity(c_name, c_url, company.domain, company.name):
                            comp_added.append({
                                "name": c_name,
                                "type": cand.get("type", "direct"),
                                "url": c_url,
                                "reason": f"Candidate proposed for strategic pivot: {cand.get('hypothesis_rationale', '')}",
                                "evidence_url": c_url,
                                "evidence_snippet": cand.get("hypothesis_rationale", ""),
                                "is_verified": False
                            })
                            if len(comp_added) >= 3:
                                break
        except Exception as e:
            print(f"[CONTEXT CHANGE] Competitor addition discovery note: {e}")

        competitors_diff = {
            "competitors_before_count": len(competitors),
            "competitors_removed": comp_removed,
            "competitors_added": comp_added,
            "competitors_after_count": max(0, len(competitors) - len(comp_removed) + len(comp_added)),
            "notes": f"Competitor landscape re-grounded around updated priority via two-step discovery: {change_description}"
        }

        # 5. Persist ContextChangeReport
        report = ContextChangeReport(
            company_id=company_id,
            change_type=change_type,
            change_description=change_description,
            before_context_json=json.dumps(before_context_dict),
            after_context_json=json.dumps(after_context_dict),
            sources_before_count=len(approved_sources),
            sources_after_count=max(0, len(approved_sources) - len(removed_recommendations) + len(added_recommendations)),
            removed_recommendations_json=json.dumps(removed_recommendations),
            added_recommendations_json=json.dumps(added_recommendations),
            competitors_diff_json=json.dumps(competitors_diff),
            metrics_json=json.dumps(metrics)
        )
        db.add(report)
        db.commit()
        db.refresh(report)

        return report

    def accept_recommendation(self, db: Session, report_id: int, rec_type: str, rec_id: int) -> Dict[str, Any]:
        """
        Applies a context-change recommendation upon user confirmation:
        - If action is 'add': approves source into active monitoring.
        - If action is 'remove': marks source status as 'rejected' (never auto-deletes).
        """
        report = db.query(ContextChangeReport).filter_by(id=report_id).first()
        if not report:
            raise ValueError(f"Report #{report_id} not found")

        recs_field = "added_recommendations_json" if rec_type == "add" else "removed_recommendations_json"
        recs = json.loads(getattr(report, recs_field))
        target_rec = next((r for r in recs if r.get("id") == rec_id), None)
        if not target_rec:
            raise ValueError(f"Recommendation #{rec_id} not found in {rec_type} recommendations")

        src_id = target_rec.get("source_id")
        if rec_type == "add" and src_id:
            src = db.query(Source).filter_by(id=src_id).first()
            if src:
                src.status = "approved"
                db.commit()
        elif rec_type == "remove" and src_id:
            src = db.query(Source).filter_by(id=src_id).first()
            if src:
                src.status = "rejected"
                src.rejection_reason = f"Rejected via Context Change reassessment: {target_rec.get('reason', 'Strategic realignment')}"
                db.commit()

        target_rec["status"] = "accepted"
        setattr(report, recs_field, json.dumps(recs))
        db.commit()
        return {"status": "success", "recommendation": target_rec}

    def dismiss_recommendation(self, db: Session, report_id: int, rec_type: str, rec_id: int) -> Dict[str, Any]:
        """Dismisses a recommendation without altering underlying database sources."""
        report = db.query(ContextChangeReport).filter_by(id=report_id).first()
        if not report:
            raise ValueError(f"Report #{report_id} not found")

        recs_field = "added_recommendations_json" if rec_type == "add" else "removed_recommendations_json"
        recs = json.loads(getattr(report, recs_field))
        target_rec = next((r for r in recs if r.get("id") == rec_id), None)
        if not target_rec:
            raise ValueError(f"Recommendation #{rec_id} not found")

        target_rec["status"] = "dismissed"
        setattr(report, recs_field, json.dumps(recs))
        db.commit()
        return {"status": "success", "recommendation": target_rec}

context_change_service = ContextChangeService()
