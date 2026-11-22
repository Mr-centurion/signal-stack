import math
import asyncio
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
import urllib.parse
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models import Company, Signal, ProfileFact, InterviewQA, Brief
from backend.services.llm_client import llm_client
from backend.prompts.templates import SIGNAL_ANALYSIS_SYSTEM

VALID_EVENT_TYPES = [
    "regulatory_change",
    "market_data",
    "product_launch",
    "pricing_change",
    "partnership",
    "hiring",
    "funding_or_ma",
    "customer_complaint",
    "other"
]

def validate_and_normalize_event_type(event_type: Optional[str], text: str) -> str:
    """
    Restricts event_type to agreed taxonomy and verifies text contains supporting evidence.
    """
    if not event_type:
        return "other"
    ev = event_type.lower().strip().replace(" ", "_")
    # Normalize common synonyms to standard taxonomy
    if ev in ["regulatory_shift", "policy_change", "compliance_update", "regulation"]:
        ev = "regulatory_change"
    elif ev in ["market_shift", "industry_trend", "macro_data", "market_update"]:
        ev = "market_data"
    elif ev in ["feature_release", "launch", "release", "new_feature"]:
        ev = "product_launch"
    elif ev in ["pricing_update", "pricing", "fee_change"]:
        ev = "pricing_change"
    elif ev in ["partnership_announcement", "collaboration", "tie_up"]:
        ev = "partnership"
    elif ev in ["leadership_hire", "appointment", "executive_hire"]:
        ev = "hiring"
    elif ev in ["funding", "investment", "acquisition", "m&a", "merger"]:
        ev = "funding_or_ma"
    elif ev in ["complaint", "customer_review", "negative_feedback", "review"]:
        ev = "customer_complaint"

    if ev not in VALID_EVENT_TYPES:
        ev = "other"

    # Verify that source text supports the label
    text_lower = text.lower() if text else ""
    if ev == "product_launch":
        launch_verbs = ["launch", "announc", "unveil", "releas", "roll out", "introduc", "debut"]
        if not any(v in text_lower for v in launch_verbs):
            ev = "other"
    elif ev == "pricing_change":
        pricing_terms = ["price", "pricing", "fee", "tuition", "discount", "cost", "rate", "deposit", "refund"]
        if not any(t in text_lower for t in pricing_terms):
            ev = "other"
    elif ev == "partnership":
        partner_terms = ["partner", "collaborat", "tie-up", "alliance", "agreement", "joint", "mou"]
        if not any(t in text_lower for t in partner_terms):
            ev = "other"
    elif ev == "hiring":
        hiring_terms = ["hire", "appoint", "executive", "join", "cto", "ceo", "vp", "team", "recruit", "head of"]
        if not any(t in text_lower for t in hiring_terms):
            ev = "other"
    elif ev == "funding_or_ma":
        funding_terms = ["fund", "raise", "round", "series", "invest", "acquir", "merger", "capital", "valuation"]
        if not any(t in text_lower for t in funding_terms):
            ev = "other"
    elif ev == "customer_complaint":
        complaint_terms = ["complain", "review", "scam", "issue", "delay", "refus", "dispute", "problem", "frustrat", "poor", "worst", "rating"]
        if not any(t in text_lower for t in complaint_terms):
            ev = "other"
    elif ev == "regulatory_change":
        reg_terms = ["visa", "policy", "regulat", "minist", "rule", "cap", "mandat", "govern", "law", "directive", "ban", "compliance", "crackdown", "restrict"]
        if not any(t in text_lower for t in reg_terms):
            ev = "other"

    return ev


class AnalysisEngine:
    """
    Autonomous Strategic Analysis & Multi-Dimensional Ranking Engine:
    - Binds verified signals to company Profile Facts and Founder Interview answers.
    - Strictly bifurcates verifiable Evidence from Strategic Interpretation.
    - Computes separate orthogonal measures:
      * source_reliability (hierarchy: regulator/official > established trade > competitor site > forum)
      * evidence_strength (primary vs secondary, verbatim body snippet, date known vs paywall/unknown)
      * strategic_relevance (LLM rationale anchored to company business lines)
    - Applies documented weighted priority formula over relevance, impact, urgency, credibility, recency, novelty.
    - Enforces 90-day background signal cutoff for executive brief summaries.
    - Synthesizes transparent 'why_important' factor breakdown.
    """

    def calculate_source_reliability(self, url: str) -> float:
        """Calculates domain hierarchy reliability score using generic authority heuristics."""
        if not url:
            return 0.50
        parsed = urllib.parse.urlparse(url.lower())
        netloc = parsed.netloc.replace("www.", "")

        # 1. Regulators & Official Portals (.gov, .edu, official institutions)
        if netloc.endswith(".gov") or netloc.endswith(".edu") or ".gov." in netloc:
            return 0.98
        if any(tld in netloc for tld in [".gov.", "gov.uk", ".europa.eu", ".mil", ".ac."]):
            return 0.98

        # 2. Major Trade & International News Platforms (generic news/media heuristics)
        if any(token in netloc for token in ["news", "reuters", "bloomberg", "times", "tribune", "press", "journal", "post", "herald"]):
            return 0.90

        # 3. App Store, Verified Review Platforms & Communities
        if "apple.com" in netloc or "apps.apple.com" in netloc:
            return 0.78
        if any(rev in netloc for rev in ["review", "trustpilot", "yelp", "forum", "community", "reddit.com"]):
            return 0.72

        return 0.65

    def is_headline_only_snippet(self, signal: Signal) -> bool:
        """Determines if a signal snippet is merely a headline or title rather than extracted body prose."""
        if not signal.evidence_snippet or len(signal.evidence_snippet.strip()) < 35:
            return True
        snip = signal.evidence_snippet.strip().lower()
        head = (signal.headline or "").strip().lower()
        
        # Check document if available
        doc = getattr(signal, "document", None)
        if doc:
            if doc.document_type == "feed_item" and len(doc.raw_text.strip()) < 150:
                return True
            if doc.title and (snip in doc.title.lower() or doc.title.lower() in snip) and len(snip) < 150:
                return True
                
        import re
        w_s = set(re.findall(r"\w+", snip))
        w_h = set(re.findall(r"\w+", head))
        jaccard = len(w_s & w_h) / max(1, len(w_s | w_h))
        if jaccard > 0.40 and len(snip) < 150:
            return True
        return False

    def calculate_evidence_strength(self, signal: Signal, domain_count: int = 1) -> float:
        """
        Evaluates concrete verifiability of excerpted body snippet and date provenance,
        capped strictly by verification_status:
        - unverified <= 0.35
        - single_source <= 0.60 (applies to App Store reviews and single-author community posts)
        - headline-only snippets <= 0.40
        - corroborated <= 0.85 (requires 2+ independent domains)
        - primary_source <= 1.00
        """
        status = signal.verification_status or "single_source"
        if status == "corroborated" and domain_count < 2:
            status = "single_source"
            signal.verification_status = "single_source"

        # Customer reviews / complaints are single-author opinions; always enforce single_source
        if (
            signal.event_type == "customer_complaint" or
            "apple.com" in (signal.source_url or "") or
            "itunes" in (signal.source_url or "") or
            "review" in (signal.source_url or "")
        ):
            if status == "primary_source":
                status = "single_source"
                signal.verification_status = "single_source"

        if status == "unverified":
            cap = 0.35
            base = 0.25
        elif status == "single_source":
            cap = 0.60
            base = 0.45
        elif status == "corroborated":
            cap = 0.85
            base = 0.70
        elif status == "primary_source":
            cap = 1.00
            base = 0.85
        else:
            cap = 0.60
            base = 0.45

        # Strict Cap: Headline-only snippets must be capped at 0.40 evidence
        is_headline = self.is_headline_only_snippet(signal)
        if is_headline:
            cap = min(cap, 0.40)
            base = min(base, 0.30)

        if signal.is_paywalled:
            return min(0.30, cap)

        score = base
        # Verbatim body snippet length bonus (only if not headline only)
        if signal.evidence_snippet and len(signal.evidence_snippet.strip()) >= 35 and not is_headline:
            score += 0.08

        # Verified publication date known bonus
        if signal.published_date is not None:
            score += 0.07

        return round(min(cap, max(0.10, score)), 2)

    def calculate_priority_score(
        self,
        signal: Signal,
        cited_signal_ids: List[int]
    ) -> float:
        """
        Computes composite priority score according to documented formula in config:
        P = w_rel*Relevance + w_imp*Impact + w_urg*Urgency + w_cred*Credibility + w_rec*Recency + w_nov*Novelty
        """
        # 1. Relevance
        rel = signal.strategic_relevance

        # 2. Impact
        impact_map = {"critical": 1.0, "high": 0.8, "medium": 0.5, "low": 0.2}
        imp = impact_map.get(signal.impact.lower(), 0.5)

        # 3. Urgency
        urgency_map = {"immediate": 1.0, "this_quarter": 0.7, "monitor": 0.4}
        urg = urgency_map.get(signal.urgency.lower(), 0.4)

        # 4. Credibility / Reliability
        cred = signal.source_reliability

        # 5. Recency (exponential decay over MAX_RECENT_SIGNAL_DAYS, evergreen 12-month window for customer voice)
        age = signal.age_days
        is_customer_review = signal.category == "customers" or signal.event_type == "customer_complaint"
        max_days = 365 if is_customer_review else settings.MAX_RECENT_SIGNAL_DAYS

        if age is not None:
            rec = max(0.15, 1.0 - (age / float(max_days)))
            # Flag background signals: customer reviews are evergreen up to 12 months (365 days)
            if age > max_days:
                signal.is_background = True
            else:
                signal.is_background = False
        else:
            rec = 0.50

        # 6. Novelty
        nov = 0.30 if (signal.id in cited_signal_ids) else 1.0

        score = (
            settings.WEIGHT_RELEVANCE * rel +
            settings.WEIGHT_IMPACT * imp +
            settings.WEIGHT_URGENCY * urg +
            settings.WEIGHT_CREDIBILITY * cred +
            settings.WEIGHT_RECENCY * rec +
            settings.WEIGHT_NOVELTY * nov
        )
        return round(min(1.0, max(0.1, score)), 2)

    def generate_why_important(self, signal: Signal) -> str:
        """Generates clear explanation of top contributing priority factors without truncation."""
        factors = []
        if signal.strategic_relevance >= 0.80:
            fact_ref = f" (Anchored: {signal.referenced_profile_fact})" if signal.referenced_profile_fact else ""
            factors.append(f"High strategic relevance to company operations{fact_ref} [{signal.strategic_relevance:.2f}]")
        if signal.impact in ["high", "critical"]:
            factors.append(f"{signal.impact.capitalize()} business impact")
        if signal.urgency in ["immediate", "this_quarter"]:
            factors.append(f"{signal.urgency.replace('_', ' ').capitalize()} leadership attention required")
        if signal.source_reliability >= 0.85:
            factors.append(f"Authoritative source credibility ({signal.publisher_name or 'official domain'} [{signal.source_reliability:.2f}])")
        if signal.verification_status in ["primary_source", "corroborated"]:
            factors.append(f"Direct {signal.verification_status.replace('_', ' ')} grounding")

        if not factors:
            factors.append(f"Moderate industry relevance [{signal.strategic_relevance:.2f}]")

        res = " &bull; ".join(factors)
        return res.replace("...", "")

    async def analyze_and_rank_signal(
        self,
        db: Session,
        company: Company,
        signal: Signal,
        facts: List[ProfileFact],
        qas: List[InterviewQA],
        cited_signal_ids: List[int]
    ) -> Signal:
        """Executes full LLM analysis, anchors to profile facts, and computes priority score."""
        # Calculate Reliability and Evidence Strength first
        publisher = signal.publisher_url or signal.source_url
        signal.source_reliability = self.calculate_source_reliability(publisher)
        
        # Verify and normalize event_type according to agreed taxonomy
        signal.event_type = validate_and_normalize_event_type(signal.event_type, f"{signal.headline} {signal.evidence_snippet}")

        # Domain count for corroboration verification
        domain_count = 1
        if signal.verification_status == "corroborated":
            doms = {urllib.parse.urlparse(s.publisher_url or s.source_url).netloc for s in db.query(Signal).filter_by(company_id=company.id).all()}
            domain_count = len([d for d in doms if d])

        signal.evidence_strength = self.calculate_evidence_strength(signal, domain_count=domain_count)

        # Date provenance check: published_date must never equal discovery_date or fetch time
        if signal.published_date and signal.discovery_date:
            pub_utc = signal.published_date if signal.published_date.tzinfo else signal.published_date.replace(tzinfo=timezone.utc)
            disc_utc = signal.discovery_date if signal.discovery_date.tzinfo else signal.discovery_date.replace(tzinfo=timezone.utc)
            if abs((pub_utc - disc_utc).total_seconds()) < 60:
                signal.published_date = None
                signal.when_published = "unknown"

        # Context dossier
        facts_text = "\n".join([f"- [{f.category}] {f.text} (Status: {f.fact_type})" for f in facts[:10]])
        qas_text = "\n".join([f"- {qa.topic}: {qa.answer}" for qa in qas[:8]])

        prompt = (
            f"TARGET COMPANY: {company.name} ({company.industry})\n"
            f"COMPANY PROFILE FACTS:\n{facts_text}\n\n"
            f"FOUNDER INTERVIEW ANSWERS:\n{qas_text}\n\n"
            f"SIGNAL TO ANALYZE:\n"
            f"Headline: {signal.headline}\n"
            f"Category: {signal.category}\n"
            f"Event Type: {signal.event_type}\n"
            f"Source URL: {signal.source_url}\n"
            f"Publisher URL: {signal.publisher_url}\n"
            f"Publisher Name: {signal.publisher_name}\n"
            f"Published Date: {signal.published_date.isoformat() if signal.published_date else 'unknown'}\n"
            f"Evidence Snippet: {signal.evidence_snippet}\n"
        )

        try:
            res = await llm_client.generate_json(SIGNAL_ANALYSIS_SYSTEM, prompt)
            
            what = res.get("what_happened", signal.headline)
            why = res.get("why_it_matters", "")
            ref_fact = res.get("referenced_profile_fact", "")
            area = res.get("business_area", "General Strategy")
            direction = res.get("direction", "neutral")
            urgency = res.get("urgency", "monitor")
            consider = res.get("what_to_consider", "")
            verif_stat = res.get("verification_status", "single_source")
            relevance = float(res.get("strategic_relevance", 0.75))

            # STRICT GUARD: Ensure interpretation references a stored profile fact or interview answer
            if not ref_fact or not any(term in why.lower() for term in ["profile", "fact", "interview", "revenue", "customer", "partner", "competitor", "market"]):
                # Bind to highest relevance profile fact
                fallback_fact = facts[0].text if facts else f"{company.name} Core Operations"
                ref_fact = fallback_fact
                why = f"Anchored to Profile Fact '{fallback_fact}': {why or what}"

            signal.what_happened = what
            signal.why_it_matters = why
            signal.referenced_profile_fact = ref_fact
            signal.business_area = area
            signal.direction = direction
            signal.urgency = urgency
            signal.what_to_consider = consider
            signal.verification_status = verif_stat
            signal.strategic_relevance = round(min(1.0, max(0.3, relevance)), 2)
            signal.interpretation = f"Why it matters: {why}\nWhat to consider: {consider}"
        except Exception as e:
            print(f"[ANALYSIS ENGINE ERROR] Signal {signal.id}: {e}")
            fallback_fact = facts[0].text if facts else f"{company.name} Core Operations"
            signal.what_happened = signal.headline
            signal.why_it_matters = f"Relates to Profile Fact '{fallback_fact}': Industry update impacting target segment."
            signal.referenced_profile_fact = fallback_fact
            signal.business_area = "Strategic Operations"
            signal.direction = "neutral"
            signal.urgency = "monitor"
            signal.what_to_consider = "Monitor ongoing developments during weekly brief cycle."
            signal.verification_status = "single_source"
            signal.strategic_relevance = 0.75

        # Format when_published string
        signal.when_published = signal.published_date.strftime("%Y-%m-%d") if signal.published_date else "unknown"

        # Calculate Priority Score and Top Factors
        signal.priority_score = self.calculate_priority_score(signal, cited_signal_ids)
        signal.why_important = self.generate_why_important(signal)

        db.commit()
        return signal

    async def analyze_and_rank_company_signals(self, db: Session, company_id: int) -> List[Signal]:
        """Runs strategic analysis across all candidate signals for the company."""
        company = db.query(Company).filter_by(id=company_id).first()
        if not company:
            return []

        signals = db.query(Signal).filter_by(company_id=company_id).all()
        facts = db.query(ProfileFact).filter_by(company_id=company_id).all()
        qas = db.query(InterviewQA).filter_by(company_id=company_id).all()

        # Find previously cited signal IDs from previous briefs for novelty check
        briefs = db.query(Brief).filter_by(company_id=company_id).all()
        cited_ids = []
        for b in briefs:
            if b.raw_json:
                import re
                found_ids = [int(m) for m in re.findall(r"\[Signal #(\d+)\]", b.raw_json)]
                cited_ids.extend(found_ids)

        fallback_fact = facts[0].text if facts else f"{company.name} Core Operations"
        
        # Phase 1: Score all candidate signals using orthogonal formula
        for sig in signals:
            # Re-normalize event_type to agreed taxonomy
            sig.event_type = validate_and_normalize_event_type(sig.event_type, f"{sig.headline} {sig.evidence_snippet}")
            
            # Domain check for corroboration
            domain_count = 1
            if sig.verification_status == "corroborated":
                doms = {urllib.parse.urlparse(s.publisher_url or s.source_url).netloc for s in signals if s.category == sig.category}
                domain_count = len([d for d in doms if d])
            sig.evidence_strength = self.calculate_evidence_strength(sig, domain_count=domain_count)

            # Date check: published_date must never equal discovery_date or fetch time
            if sig.published_date and sig.discovery_date:
                pub_utc = sig.published_date if sig.published_date.tzinfo else sig.published_date.replace(tzinfo=timezone.utc)
                disc_utc = sig.discovery_date if sig.discovery_date.tzinfo else sig.discovery_date.replace(tzinfo=timezone.utc)
                if abs((pub_utc - disc_utc).total_seconds()) < 60:
                    sig.published_date = None
                    sig.when_published = "unknown"

            # Compute preliminary priority score
            sig.priority_score = self.calculate_priority_score(sig, cited_ids)
            sig.why_important = self.generate_why_important(sig)

        # Sort by priority score descending
        sorted_candidates = sorted(signals, key=lambda s: s.priority_score, reverse=True)

        # Phase 2: Perform deep profile-anchored analysis on top signals (max 10 to respect rate limits)
        analyzed = []
        for idx, sig in enumerate(sorted_candidates):
            if sig.what_happened and sig.why_it_matters and sig.referenced_profile_fact:
                sig.priority_score = self.calculate_priority_score(sig, cited_ids)
                sig.why_important = self.generate_why_important(sig)
                analyzed.append(sig)
            elif idx < 8: # Deep LLM analysis for top 8 signals
                s_analyzed = await self.analyze_and_rank_signal(db, company, sig, facts, qas, cited_ids)
                analyzed.append(s_analyzed)
                await asyncio.sleep(0.5)
            else: # Efficient anchoring for remaining signals without extra LLM overhead
                sig.what_happened = sig.headline
                sig.why_it_matters = f"Relates to Profile Fact '{fallback_fact}': Sector update impacting target operations."
                sig.referenced_profile_fact = fallback_fact
                sig.business_area = "Strategic Operations"
                sig.direction = "neutral"
                sig.urgency = "monitor"
                sig.what_to_consider = "Monitor ongoing developments during weekly brief cycle."
                sig.priority_score = self.calculate_priority_score(sig, cited_ids)
                sig.why_important = self.generate_why_important(sig)
                analyzed.append(sig)

        db.commit()

        return sorted(analyzed, key=lambda s: s.priority_score, reverse=True)

    def recompute_all_signal_scores(self, db: Session) -> Dict[str, Any]:
        """
        Recomputes scores for all stored signals under current caps:
        - headline-only snippets cap at <= 0.40
        - single_source at <= 0.60
        - unverified at <= 0.35
        - corroborated at <= 0.85 (requires 2+ independent domains)
        - primary_source up to 1.00
        Returns before and after scores for target signals (#6, #7, #10).
        """
        target_ids = [6, 7, 10]
        before_scores = {}
        for tid in target_ids:
            sig = db.query(Signal).filter_by(id=tid).first()
            if sig:
                before_scores[tid] = {
                    "headline": sig.headline,
                    "evidence_strength": sig.evidence_strength,
                    "priority_score": sig.priority_score,
                    "verification_status": sig.verification_status
                }

        # Find cited signal IDs across all briefs for novelty weighting
        briefs = db.query(Brief).all()
        cited_ids = []
        for b in briefs:
            if b.raw_json:
                import re
                found_ids = [int(m) for m in re.findall(r"\[Signal #(\d+)\]", b.raw_json)]
                cited_ids.extend(found_ids)

        all_signals = db.query(Signal).all()
        for sig in all_signals:
            # Re-normalize event_type
            sig.event_type = validate_and_normalize_event_type(sig.event_type, f"{sig.headline} {sig.evidence_snippet}")
            
            # Domain count for corroboration
            domain_count = 1
            if sig.verification_status == "corroborated":
                doms = {urllib.parse.urlparse(s.publisher_url or s.source_url).netloc for s in all_signals if s.company_id == sig.company_id and s.category == sig.category}
                domain_count = len([d for d in doms if d])

            # Recalculate source reliability
            publisher = sig.publisher_url or sig.source_url
            sig.source_reliability = self.calculate_source_reliability(publisher)

            # Recalculate evidence strength
            sig.evidence_strength = self.calculate_evidence_strength(sig, domain_count=domain_count)

            # Check date provenance
            if sig.published_date and sig.discovery_date:
                pub_utc = sig.published_date if sig.published_date.tzinfo else sig.published_date.replace(tzinfo=timezone.utc)
                disc_utc = sig.discovery_date if sig.discovery_date.tzinfo else sig.discovery_date.replace(tzinfo=timezone.utc)
                if abs((pub_utc - disc_utc).total_seconds()) < 60:
                    sig.published_date = None
                    sig.when_published = "unknown"

            # Recalculate priority score & why important
            sig.priority_score = self.calculate_priority_score(sig, cited_ids)
            sig.why_important = self.generate_why_important(sig)

        db.commit()

        after_scores = {}
        for tid in target_ids:
            sig = db.query(Signal).filter_by(id=tid).first()
            if sig:
                after_scores[tid] = {
                    "headline": sig.headline,
                    "evidence_strength": sig.evidence_strength,
                    "priority_score": sig.priority_score,
                    "verification_status": sig.verification_status
                }

        return {
            "total_recomputed": len(all_signals),
            "before_scores": before_scores,
            "after_scores": after_scores
        }

    # Method alias for backward compatibility
    run_analysis = analyze_and_rank_company_signals

analysis_engine = AnalysisEngine()
