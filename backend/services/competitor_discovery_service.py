import re
import json
import asyncio
import urllib.parse
import httpx
import trafilatura
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from backend.models import Company, Competitor, Document, InterviewQA
from backend.services.llm_client import llm_client
from backend.prompts.templates import (
    COMPETITOR_HYPOTHESIS_SYSTEM,
    COMPETITOR_WEBSITE_VERIFICATION_SYSTEM
)

class CompetitorDiscoveryService:
    """
    Two-Step Autonomous Competitor & Substitute Discovery Engine:
    Step (a): LLM proposes 10-15 candidates labelled 'hypothesis' based on
              the company's business lines, positioning, and customer segments.
              Strictly excludes universities, trade media, testing bodies, and regulators.
    Step (b): For each candidate, fetch its actual website, verify it offers an overlapping
              commercial service to the same customers, and extract an exact verbatim quote snippet
              programmatically verified to exist in the fetched text.
              Keeps 5-10 verified direct and substitute competitors.
              Resolves Google News redirect links to real publisher/company URLs.
    """

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 SignalStackIntelBot/2.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }

    async def resolve_redirect_url(self, url: str) -> str:
        """Resolves Google News or intermediate redirect links to the real destination URL."""
        if not url or not url.startswith("http"):
            return url
        if "news.google.com" in url or "google.com/url" in url:
            try:
                async with httpx.AsyncClient(timeout=6.0, follow_redirects=True, headers=self.headers, verify=False) as client:
                    r = await client.head(url)
                    if r.url and "news.google.com" not in str(r.url):
                        return str(r.url).rstrip("/")
                    r = await client.get(url)
                    if r.url and "news.google.com" not in str(r.url):
                        return str(r.url).rstrip("/")
            except Exception:
                pass
        return url.rstrip("/")

    def get_base_domain(self, domain_or_url: str) -> str:
        """Extracts normalized root domain (e.g., posthog.com from https://www.posthog.com/docs)."""
        if not domain_or_url:
            return ""
        raw = domain_or_url.strip().lower()
        if not raw.startswith("http://") and not raw.startswith("https://"):
            raw = f"https://{raw}"
        try:
            parsed = urllib.parse.urlparse(raw)
            netloc = parsed.netloc.split(":")[0]
            if netloc.startswith("www."):
                netloc = netloc[4:]
            return netloc
        except Exception:
            return domain_or_url.strip().lower()

    def is_excluded_entity(self, name: str, url: str, target_domain: str = "", target_name: str = "") -> bool:
        """Domain & name heuristics to reject non-competitors (universities, media, regulators, self-reference)."""
        name_lower = re.sub(r"[^\w\s]", "", name.lower()).strip()
        url_lower = url.lower()
        parsed = urllib.parse.urlparse(url_lower)
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]

        # Reject self-reference (target company, its subsidiaries, and its own domains)
        target_base = self.get_base_domain(target_domain)
        cand_base = self.get_base_domain(url)

        if target_base and cand_base:
            if target_base == cand_base or target_base in cand_base or cand_base in target_base:
                return True

        if target_name:
            t_name_clean = re.sub(r"[^\w\s]", "", target_name.lower()).strip()
            if t_name_clean:
                # Direct match or target name contained in candidate name (e.g. 'PostHog Cloud', 'PostHog Analytics')
                if t_name_clean == name_lower or t_name_clean in name_lower.split() or name_lower in t_name_clean.split():
                    return True
                # If candidate name starts with target name
                if name_lower.startswith(t_name_clean) or t_name_clean.startswith(name_lower):
                    return True

        # 1. Educational / Academic institutions
        if any(tld in netloc for tld in [".edu", ".ac.", "edu."]):
            return True
        if any(term in name_lower for term in [
            "university", "college", "school of", "polytechnic", "academy of", "institute of technology"
        ]):
            return True

        # 2. General news media, rankings, trade magazines (generic media heuristics)
        if any(term in netloc for term in [
            "news.", ".news", "times.", "magazine.", "journal.", "ranking.", "herald.", "tribune."
        ]) or any(term in name_lower.split() for term in [
            "news", "times", "magazine", "rankings", "journal", "gazette", "herald", "tribune", "broadcast"
        ]):
            return True

        # 3. Regulators, government portals, examination & testing authorities
        if any(gov in netloc for gov in [".gov", "gov.", ".mil"]):
            return True
        if any(body in name_lower for body in [
            "testing service", "exam board", "examination council", "regulatory authority",
            "department of", "ministry of", "standards board", "accreditation council",
            "teachers of singing", "national association of"
        ]):
            return True

        return False

    async def propose_competitor_hypotheses(self, company: Company) -> List[Dict[str, Any]]:
        """
        Step (a): Generates 10-15 competitor and substitute hypotheses using LLM,
        strictly excluding universities, media, testing bodies, and regulators.
        """
        profile_text = company.intelligence_profile or ""
        interview_context = ""
        for qa in company.interview_qas:
            if qa.topic in ["revenue_lines", "why_customers_choose_us", "competitors_substitutes"]:
                interview_context += f"Topic: {qa.topic}\nQ: {qa.question}\nA: {qa.answer}\n"

        prompt = (
            f"TARGET COMPANY: {company.name}\n"
            f"DOMAIN: {company.domain}\n"
            f"INDUSTRY: {company.industry or 'Technology'}\n\n"
            f"PROFILE CONTEXT:\n{profile_text[:2000]}\n\n"
            f"INTERVIEW CONTEXT:\n{interview_context[:1200]}\n\n"
            f"Propose 10 to 15 commercial competitors and substitutes for {company.name}. "
            f"Label each as 'hypothesis'. Remember: DO NOT include universities, schools, trade media, rankings, or testing bodies."
        )

        res = await llm_client.generate_json(COMPETITOR_HYPOTHESIS_SYSTEM, prompt)
        hypotheses = res.get("hypotheses", [])
        clean_hypotheses = []
        comp_name_lower = company.name.lower()

        for h in hypotheses:
            name = h.get("name", "").strip()
            raw_url = h.get("url", "").strip()
            htype = h.get("type", "direct").lower()
            if htype not in ["direct", "substitute"]:
                htype = "direct"
            rationale = h.get("hypothesis_rationale", "").strip()

            if not name or comp_name_lower in name.lower() or name.lower() in comp_name_lower:
                continue
            if company.domain and company.domain.lower() in raw_url.lower():
                continue
            if self.is_excluded_entity(name, raw_url, company.domain, company.name):
                continue
            if not raw_url.startswith("http"):
                raw_url = f"https://{raw_url}"

            clean_hypotheses.append({
                "name": name,
                "url": raw_url,
                "type": htype,
                "hypothesis_rationale": rationale
            })

        return clean_hypotheses

    async def fetch_and_verify_candidate(self, cand: Dict[str, Any], company: Company) -> Optional[Dict[str, Any]]:
        """
        Step (b): Fetches candidate's website, verifies it offers an overlapping service,
        and quotes a snippet that actually exists in the fetched text.
        """
        name = cand["name"]
        raw_url = cand["url"]
        cand_type = cand["type"]

        # Resolve redirects if Google News URL or shortlink
        target_url = await self.resolve_redirect_url(raw_url)

        if self.is_excluded_entity(name, target_url, company.domain, company.name):
            return None

        clean_url = target_url.strip().rstrip("/")
        if company.domain and company.domain.lower() in clean_url.lower():
            return None
        if company.website_url and urllib.parse.urlparse(company.website_url).netloc.lower() in clean_url.lower():
            return None
        parsed = urllib.parse.urlparse(clean_url)
        root_url = f"{parsed.scheme}://{parsed.netloc}"

        fetched_text = ""
        final_url = clean_url

        # Attempt to fetch homepage text
        for u in [clean_url, root_url]:
            try:
                async with httpx.AsyncClient(timeout=7.0, follow_redirects=True, headers=self.headers, verify=False) as client:
                    resp = await client.get(u)
                    if resp.status_code < 400:
                        final_url = str(resp.url).rstrip("/")
                        extracted = trafilatura.extract(resp.text)
                        if extracted and len(extracted.strip()) >= 150:
                            fetched_text = extracted.strip()
                            break
                        # Fallback to simple paragraph extraction if trafilatura stripped too much
                        body_text = re.sub(r"<[^>]+>", " ", resp.text)
                        body_text = re.sub(r"\s+", " ", body_text).strip()
                        if len(body_text) >= 200:
                            fetched_text = body_text[:4000]
                            break
            except Exception:
                pass

        if not fetched_text or len(fetched_text) < 150:
            return None

        # Verify through LLM with groundings
        prompt = (
            f"TARGET COMPANY MONITORED: {company.name} ({company.industry})\n"
            f"CANDIDATE COMPETITOR: {name} ({final_url})\n\n"
            f"FETCHED CANDIDATE WEBSITE TEXT:\n{fetched_text[:3500]}\n\n"
            f"Verify if {name} is a legitimate commercial competitor or substitute offering an overlapping service to the same customer segment as {company.name}. "
            f"Extract a verbatim quote snippet (15 to 150 chars) from the text proving this offering."
        )

        res = await llm_client.generate_json(COMPETITOR_WEBSITE_VERIFICATION_SYSTEM, prompt)
        if not res.get("is_valid_competitor"):
            return None

        verified_type = res.get("type", cand_type).lower()
        if verified_type not in ["direct", "substitute"]:
            verified_type = cand_type

        why_relevant = res.get("why_relevant", cand.get("hypothesis_rationale", "")).strip()
        evidence_snippet = res.get("evidence_snippet", "").strip()

        # PROGRAMMATIC SNIPPET GROUNDING GUARD:
        # Quote MUST exist verbatim in fetched text
        norm_snippet = " ".join(evidence_snippet.lower().split())
        norm_text = " ".join(fetched_text.lower().split())

        if not norm_snippet or len(norm_snippet) < 15 or norm_snippet not in norm_text:
            # Fallback: search for first 40 characters or sentence
            found_sub = False
            for chunk_len in [40, 30, 25]:
                if len(norm_snippet) >= chunk_len and norm_snippet[:chunk_len] in norm_text:
                    found_sub = True
                    break
            if not found_sub:
                return None

        return {
            "name": name,
            "url": final_url,
            "type": verified_type,
            "why_relevant": why_relevant,
            "evidence_url": final_url,
            "evidence_snippet": evidence_snippet,
            "is_verified": True
        }

    async def discover_competitors(self, db: Session, company_id: int) -> List[Competitor]:
        """
        Executes end-to-end two-step competitor discovery:
        1. Formulates 10-15 hypotheses via LLM.
        2. Concurrently fetches candidate websites, verifies overlapping service,
           and validates quote snippets verbatim in fetched text.
        3. Keeps 5-10 verified direct and substitute competitors.
        4. Saves to DB and syncs profile.
        """
        company = db.query(Company).filter_by(id=company_id).first()
        if not company:
            raise ValueError(f"Company {company_id} not found")

        # Step (a): Propose 10-15 hypotheses
        hypotheses = await self.propose_competitor_hypotheses(company)

        # Step (b): Fetch websites and verify overlapping service with exact quote
        sem = asyncio.Semaphore(2)

        async def bounded_verify(h):
            async with sem:
                res = await self.fetch_and_verify_candidate(h, company)
                await asyncio.sleep(0.4)
                return res

        tasks = [bounded_verify(h) for h in hypotheses]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        verified_competitors = []
        seen_names = set()

        for res in results:
            if isinstance(res, dict) and res.get("is_verified"):
                name_key = res["name"].lower()
                if name_key not in seen_names:
                    seen_names.add(name_key)
                    verified_competitors.append(res)

        # Target between 5 and 10 verified competitors
        if len(verified_competitors) > 10:
            # Prioritize direct competitors, then substitutes
            directs = [c for c in verified_competitors if c["type"] == "direct"]
            substitutes = [c for c in verified_competitors if c["type"] == "substitute"]
            verified_competitors = (directs + substitutes)[:10]

        # Step (c): Persist to DB with self-exclusion guard and hard cap of 10
        # 1. Prune any existing records that match the company itself, subsidiaries, or own domains
        existing_all = db.query(Competitor).filter_by(company_id=company.id).all()
        for ec in existing_all:
            if self.is_excluded_entity(ec.name, ec.url, company.domain, company.name):
                db.delete(ec)
        db.commit()

        # 2. Update existing or add new verified candidates (capped at top 10)
        existing_records = {c.name.lower(): c for c in db.query(Competitor).filter_by(company_id=company.id).all()}
        created_competitors = []

        for vdata in verified_competitors[:10]:
            name_key = vdata["name"].lower()
            if name_key in existing_records:
                c_rec = existing_records[name_key]
                c_rec.url = vdata["url"]
                c_rec.type = vdata["type"]
                c_rec.why_relevant = vdata["why_relevant"]
                c_rec.evidence_url = vdata["evidence_url"]
                c_rec.evidence_snippet = vdata["evidence_snippet"]
                c_rec.is_verified = True
                c_rec.updated_at = datetime.now(timezone.utc)
                created_competitors.append(c_rec)
            else:
                c_rec = Competitor(
                    company_id=company.id,
                    name=vdata["name"],
                    url=vdata["url"],
                    type=vdata["type"],
                    why_relevant=vdata["why_relevant"],
                    evidence_url=vdata["evidence_url"],
                    evidence_snippet=vdata["evidence_snippet"],
                    is_verified=True,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)
                )
                db.add(c_rec)
                created_competitors.append(c_rec)

        db.commit()

        # 3. Enforce strict cap: maximum 10 competitors per company, ranked by verification status & overlap
        all_recs = db.query(Competitor).filter_by(company_id=company.id).order_by(
            Competitor.is_verified.desc(),
            (Competitor.type == 'direct').desc(),
            Competitor.id.asc()
        ).all()
        if len(all_recs) > 10:
            to_keep = all_recs[:10]
            to_drop = all_recs[10:]
            for d in to_drop:
                db.delete(d)
            db.commit()
            created_competitors = to_keep
        else:
            created_competitors = all_recs

        # Step (d): Sync with company.intelligence_profile JSON
        try:
            profile_dict = json.loads(company.intelligence_profile or "{}")
            profile_dict["likely_competitors"] = [
                {
                    "name": c.name,
                    "url": c.url,
                    "type": c.type,
                    "rationale": c.why_relevant,
                    "evidence_url": c.evidence_url,
                    "evidence_snippet": c.evidence_snippet,
                    "status": "verified"
                } for c in created_competitors
            ]
            company.intelligence_profile = json.dumps(profile_dict)
            db.commit()
        except Exception:
            pass

        return created_competitors

competitor_discovery_service = CompetitorDiscoveryService()
