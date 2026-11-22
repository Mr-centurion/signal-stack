import re
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
import httpx
import feedparser
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models import Company, Source, CrawlResult, Signal, SourceHealthReport
from backend.services.source_discovery_service import source_discovery_service
from backend.crawler.robots import robots_manager

class MonthlyAuditService:
    """
    Autonomous Monthly Signal Stack Audit Engine:
    - Verifies URL health (HTTP codes, timeouts, dead redirects, RSS bozo).
    - Checks robots.txt policy compliance (distinct 'blocked_by_robots' status).
    - Detects duplicate monitoring targets.
    - Identifies inactive feeds (zero items collected in N weeks).
    - Detects declining relevance (falling ratio of signals to crawled items).
    - Re-runs discovery to propose fresh candidate sources.
    - Emits actionable recommendations ('add', 'remove', 'keep') with rationales.
    - Persists SourceHealthReport in database.
    - Provides accept/dismiss workflows that never auto-delete.
    """

    async def check_url_liveness(self, url: str, source_type: str) -> Dict[str, Any]:
        """Tests whether a URL or feed endpoint is reachable and alive, and honors robots.txt."""
        # 1. Robots.txt Compliance Check
        if not robots_manager.can_fetch(url):
            return {
                "is_alive": False,
                "is_blocked_by_robots": True,
                "status_code": 403,
                "error": "Disallowed by origin robots.txt policy"
            }

        # 2. RSS / Atom Feed Check
        if source_type == "rss" or any(url.lower().endswith(ext) for ext in [".xml", ".rss", ".atom"]) or "feed" in url.lower():
            try:
                feed = feedparser.parse(url)
                http_status = getattr(feed, "status", None)
                if http_status and http_status >= 400:
                    return {"is_alive": False, "is_blocked_by_robots": (http_status == 403), "status_code": http_status, "error": f"HTTP {http_status}"}
                if feed.bozo and not feed.entries and not getattr(feed, "feed", None):
                    return {"is_alive": False, "is_blocked_by_robots": False, "status_code": 500, "error": f"RSS parse error: {feed.bozo_exception}"}
                return {"is_alive": True, "status_code": http_status or 200, "entries_count": len(feed.entries)}
            except Exception as e:
                return {"is_alive": False, "is_blocked_by_robots": False, "status_code": None, "error": str(e)}

        # 3. Standard HTML / Web Check
        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True, headers={"User-Agent": settings.USER_AGENT}) as client:
                resp = await client.get(url)
                if resp.status_code >= 400:
                    return {"is_alive": False, "is_blocked_by_robots": (resp.status_code == 403), "status_code": resp.status_code, "error": f"HTTP {resp.status_code}"}
                return {"is_alive": True, "status_code": resp.status_code, "final_url": str(resp.url)}
        except Exception as e:
            return {"is_alive": False, "is_blocked_by_robots": False, "status_code": None, "error": str(e)}

    async def run_audit(self, db: Session, company_id: int) -> SourceHealthReport:
        """Executes full monthly audit across company sources and discovers candidates."""
        company = db.query(Company).filter_by(id=company_id).first()
        if not company:
            raise ValueError(f"Company {company_id} not found")

        cfg = company.get_settings()
        inactivity_weeks = int(cfg.get("inactivity_threshold_weeks", 4))
        cutoff_date = datetime.now(timezone.utc) - timedelta(weeks=inactivity_weeks)

        def to_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
            if not dt:
                return None
            if dt.tzinfo is not None:
                return dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt

        cutoff_naive = to_naive_utc(cutoff_date)

        # Audit ONLY approved sources
        approved_sources = db.query(Source).filter_by(company_id=company_id, status="approved").all()

        dead_sources = []
        blocked_sources = []
        duplicate_sources = []
        inactive_sources = []
        declining_sources = []
        healthy_sources = []

        recommendations: List[Dict[str, Any]] = []
        audit_metrics: Dict[str, Any] = {}

        # 1. Audit Existing Approved Sources
        seen_urls = {}
        for s in approved_sources:
            norm_url = s.url.strip().lower().rstrip("/")
            source_metric = {
                "source_id": s.id,
                "url": s.url,
                "category": s.category,
                "type": s.source_type
            }

            # A. Check Duplicate
            if norm_url in seen_urls:
                orig_id = seen_urls[norm_url]
                duplicate_sources.append(s)
                source_metric["issue"] = "duplicate"
                source_metric["original_source_id"] = orig_id
                recommendations.append({
                    "id": len(recommendations) + 1,
                    "source_id": s.id,
                    "source_url": s.url,
                    "source_name": f"{s.category.title()} Feed #{s.id}",
                    "category": s.category,
                    "action": "remove",
                    "reason": f"Duplicate source target: identical URL to existing source #{orig_id}.",
                    "status": "pending"
                })
                audit_metrics[s.url] = source_metric
                continue
            seen_urls[norm_url] = s.id

            # B. Check Liveness & Robots Blocked Status
            liveness = await self.check_url_liveness(s.url, s.source_type)
            source_metric["liveness"] = liveness
            if not liveness.get("is_alive"):
                if liveness.get("is_blocked_by_robots") or "robots.txt" in str(liveness.get("error", "")).lower() or liveness.get("status_code") == 403:
                    blocked_sources.append(s)
                    s.health = "blocked_by_robots"
                    source_metric["issue"] = "blocked_by_robots"
                    recommendations.append({
                        "id": len(recommendations) + 1,
                        "source_id": s.id,
                        "source_url": s.url,
                        "source_name": f"{s.category.title()} Source #{s.id}",
                        "category": s.category,
                        "action": "remove",
                        "reason": f"Blocked by origin robots.txt policy: {liveness.get('error', 'Disallowed')}.",
                        "status": "pending"
                    })
                else:
                    dead_sources.append(s)
                    s.health = "dead"
                    source_metric["issue"] = "dead_url"
                    recommendations.append({
                        "id": len(recommendations) + 1,
                        "source_id": s.id,
                        "source_url": s.url,
                        "source_name": f"{s.category.title()} Source #{s.id}",
                        "category": s.category,
                        "action": "remove",
                        "reason": f"Dead endpoint: {liveness.get('error', 'Unreachable')} (HTTP status {liveness.get('status_code')}).",
                        "status": "pending"
                    })
                audit_metrics[s.url] = source_metric
                continue

            # C. Check Inactivity
            recent_crawls = db.query(CrawlResult).filter(
                CrawlResult.source_id == s.id,
                CrawlResult.items_found > 0
            ).all()
            
            # Check last crawled date or recent signals
            is_inactive = False
            if s.last_crawled_at and to_naive_utc(s.last_crawled_at) < cutoff_naive:
                is_inactive = True
            elif not recent_crawls and s.created_at and to_naive_utc(s.created_at) < cutoff_naive:
                is_inactive = True

            if is_inactive:
                inactive_sources.append(s)
                s.health = "degraded"
                source_metric["issue"] = "inactive"
                recommendations.append({
                    "id": len(recommendations) + 1,
                    "source_id": s.id,
                    "source_url": s.url,
                    "source_name": f"{s.category.title()} Source #{s.id}",
                    "category": s.category,
                    "action": "remove",
                    "reason": f"Inactive source: zero new developments or crawl items detected over the past {inactivity_weeks} weeks.",
                    "status": "pending"
                })
                audit_metrics[s.url] = source_metric
                continue

            # D. Check Declining Relevance
            total_results = db.query(CrawlResult).filter_by(source_id=s.id).all()
            signals_count = db.query(Signal).filter_by(source_id=s.id).count()
            total_items = sum(r.items_found for r in total_results) if total_results else 0
            
            relevance_rate = (signals_count / total_items) if total_items > 0 else 0.5
            source_metric["total_items_crawled"] = total_items
            source_metric["signals_generated"] = signals_count
            source_metric["relevance_rate"] = round(relevance_rate, 2)

            if total_items >= 6 and relevance_rate < 0.10:
                declining_sources.append(s)
                s.health = "degraded"
                source_metric["issue"] = "declining_relevance"
                recommendations.append({
                    "id": len(recommendations) + 1,
                    "source_id": s.id,
                    "source_url": s.url,
                    "source_name": f"{s.category.title()} Source #{s.id}",
                    "category": s.category,
                    "action": "remove",
                    "reason": f"Declining relevance: only {relevance_rate:.0%} of crawled items ({signals_count}/{total_items}) passed the strategic intelligence gate.",
                    "status": "pending"
                })
                audit_metrics[s.url] = source_metric
                continue

            # E. Healthy Source (KEEP recommendations are informational and never marked 'accepted')
            healthy_sources.append(s)
            s.health = "healthy"
            recommendations.append({
                "id": len(recommendations) + 1,
                "source_id": s.id,
                "source_url": s.url,
                "source_name": f"{s.category.title()} Source #{s.id}",
                "category": s.category,
                "action": "keep",
                "reason": f"Source is verified active and delivering high-yield {s.category} signals.",
                "status": "info"
            })
            audit_metrics[s.url] = source_metric

        # 2. Re-run Discovery for New Candidate Sources
        try:
            discovered = await source_discovery_service.discover_sources(db, company_id)
            existing_urls = {src.url.strip().lower().rstrip("/") for src in approved_sources}
            new_candidates = [
                cand for cand in discovered
                if cand.url.strip().lower().rstrip("/") not in existing_urls
            ]
            # Recommend top candidate additions
            for cand in new_candidates[:4]:
                recommendations.append({
                    "id": len(recommendations) + 1,
                    "source_id": cand.id,
                    "source_url": cand.url,
                    "source_name": f"Candidate: {cand.category.title()} Feed",
                    "category": cand.category,
                    "action": "add",
                    "reason": f"Autonomous discovery identified high-specificity source ({cand.specificity_score:.2f}) for '{cand.category}': {cand.reason}",
                    "status": "pending"
                })
        except Exception as e:
            print(f"[MONTHLY AUDIT] Candidate discovery note: {e}")

        # 3. Formulate Executive Narrative Summary with History Trend Note
        total_audited = len(approved_sources)
        healthy_count = len(healthy_sources)
        dead_count = len(dead_sources)
        blocked_count = len(blocked_sources)
        dup_count = len(duplicate_sources)
        inactive_count = len(inactive_sources)
        declining_count = len(declining_sources)

        now_utc = datetime.now(timezone.utc)
        comp_created = company.created_at
        if comp_created and comp_created.tzinfo is None:
            comp_created = comp_created.replace(tzinfo=timezone.utc)
        history_days = max(1, (now_utc - comp_created).days) if comp_created else 1
        history_note = f"Inactivity and relevance trends need {inactivity_weeks} weeks of history; currently {history_days} days."
        audit_metrics["history_note"] = history_note

        summary = (
            f"Monthly audit completed across {total_audited} approved sources for {company.name}. "
            f"Health status: {healthy_count} healthy, {dead_count} dead URLs, {blocked_count} blocked by robots.txt, "
            f"{dup_count} duplicate endpoints, {inactive_count} inactive feeds (> {inactivity_weeks}w), "
            f"and {declining_count} sources with declining strategic relevance. "
            f"Generated {len(recommendations)} actionable recommendations. Sources are preserved and never auto-deleted.\n"
            f"Note: {history_note}"
        )

        report = SourceHealthReport(
            company_id=company_id,
            created_at=datetime.now(timezone.utc),
            total_sources_audited=total_audited,
            dead_sources_count=dead_count,
            blocked_sources_count=blocked_count,
            duplicate_sources_count=dup_count,
            inactive_sources_count=inactive_count,
            declining_sources_count=declining_count,
            healthy_sources_count=healthy_count,
            summary=summary,
            recommendations_json=json.dumps(recommendations),
            audit_metrics_json=json.dumps(audit_metrics)
        )
        db.add(report)
        db.commit()
        db.refresh(report)

        return report

    def accept_recommendation(self, db: Session, report_id: int, rec_id: int) -> Dict[str, Any]:
        """
        Applies a recommendation upon user confirmation:
        - If action is 'add': approves source into active monitoring.
        - If action is 'remove': marks source status as 'rejected' (never auto-deletes).
        """
        report = db.query(SourceHealthReport).filter_by(id=report_id).first()
        if not report:
            raise ValueError(f"Report {report_id} not found")

        recs = json.loads(report.recommendations_json)
        target_rec = None
        for r in recs:
            if r.get("id") == rec_id:
                target_rec = r
                break

        if not target_rec:
            raise ValueError(f"Recommendation {rec_id} not found in report {report_id}")

        action = target_rec.get("action")
        src_id = target_rec.get("source_id")

        if action == "add" and src_id:
            src = db.query(Source).filter_by(id=src_id).first()
            if src:
                src.status = "approved"
                db.commit()
        elif action == "remove" and src_id:
            src = db.query(Source).filter_by(id=src_id).first()
            if src:
                src.status = "rejected"
                src.rejection_reason = f"Rejected via Monthly Audit: {target_rec.get('reason', 'Deactivated via Monthly Health Audit')}"
                db.commit()

        target_rec["status"] = "accepted"
        report.recommendations_json = json.dumps(recs)
        db.commit()
        return {"status": "success", "recommendation": target_rec}

    def dismiss_recommendation(self, db: Session, report_id: int, rec_id: int) -> Dict[str, Any]:
        """Dismisses recommendation without altering underlying sources."""
        report = db.query(SourceHealthReport).filter_by(id=report_id).first()
        if not report:
            raise ValueError(f"Report {report_id} not found")

        recs = json.loads(report.recommendations_json)
        target_rec = None
        for r in recs:
            if r.get("id") == rec_id:
                target_rec = r
                break

        if not target_rec:
            raise ValueError(f"Recommendation {rec_id} not found")

        target_rec["status"] = "dismissed"
        report.recommendations_json = json.dumps(recs)
        db.commit()
        return {"status": "success", "recommendation": target_rec}

monthly_audit_service = MonthlyAuditService()
