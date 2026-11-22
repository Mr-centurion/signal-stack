from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from backend.models import Company, ProfileFact, InterviewQA, Source
from backend.services.llm_client import llm_client
from backend.prompts.templates import INTERVIEW_GENERATION_SYSTEM, SOURCE_DISCOVERY_SYSTEM

class ProfileService:
    """
    Orchestrates LLM-driven company profiling, dynamic interview generation,
    and zero-hardcoding source discovery.
    """
    def retire_non_anchored_facts(self, db: Session, company_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Retires non-anchored, unverified, assumption, or superseded profile facts.
        Eligible facts for strategic brief generation must:
        - Be a verified fact: fact_type == 'fact'
        - Carry a verbatim evidence snippet from the company's own domain (>= 8 characters)
        - Have a source_url anchored to the company's verified domain
        - Not contain test fixture / test mode flags
        Any fact not meeting these criteria is retired (is_current=False, is_anchored=False).
        Returns the list of retired fact records.
        """
        query = db.query(ProfileFact)
        if company_id is not None:
            query = query.filter_by(company_id=company_id)
        
        all_facts = query.all()
        retired_facts = []

        for fact in all_facts:
            company = fact.company or db.query(Company).filter_by(id=fact.company_id).first()
            comp_domain = (company.domain or "").lower().replace("www.", "") if company else ""

            # Check anchoring and validity criteria
            reasons = []
            if fact.fact_type != "fact":
                reasons.append(f"fact_type is '{fact.fact_type}' (must be 'fact')")
            if not fact.evidence_snippet or len(fact.evidence_snippet.strip()) < 8:
                reasons.append("lacks required evidence snippet (minimum 8 characters)")
            if not fact.source_url:
                reasons.append("source_url is missing")
            elif comp_domain and comp_domain not in fact.source_url.lower():
                reasons.append(f"source_url '{fact.source_url}' does not match company domain '{comp_domain}'")
            if "[test fixture]" in fact.text.lower() or "[test mode]" in fact.text.lower():
                reasons.append("contains test fixture / test mode flag")

            if reasons:
                fact.is_current = False
                fact.is_anchored = False
                retired_facts.append({
                    "id": fact.id,
                    "company_id": fact.company_id,
                    "company_name": company.name if company else f"Company #{fact.company_id}",
                    "text": fact.text,
                    "field_name": fact.field_name,
                    "reasons": reasons
                })
            else:
                fact.is_current = True
                fact.is_anchored = True

        db.commit()
        return retired_facts
    async def generate_interview_questions(self, company: Company) -> List[Dict[str, Any]]:
        """Dynamically generates company-tailored discovery interview questions."""
        user_prompt = (
            f"Company Name: {company.name}\n"
            f"Domain: {company.domain}\n"
            f"Industry: {company.industry or 'Technology'}\n"
            f"Description: {company.description or 'A high-growth business.'}\n\n"
            f"Generate tailored interview questions across 'customers', 'competitors', 'market', and 'internal'."
        )
        res = await llm_client.generate_json(INTERVIEW_GENERATION_SYSTEM, user_prompt)
        return res.get("questions", [])

    async def record_interview_qa(self, db: Session, company_id: int, question: str, answer: str, category: str = "internal") -> InterviewQA:
        """Records an answer and extracts a profile fact."""
        qa = InterviewQA(
            company_id=company_id,
            question=question,
            answer=answer,
            category=category,
            created_at=datetime.now(timezone.utc)
        )
        db.add(qa)

        # Also store as an internal ProfileFact
        fact = ProfileFact(
            company_id=company_id,
            category=category,
            fact_type="fact",
            text=f"Q: {question} | A: {answer}",
            source="Founder Interview",
            confidence_score=1.0
        )
        db.add(fact)
        db.commit()
        db.refresh(qa)
        return qa

    async def discover_sources_for_company(self, db: Session, company: Company) -> List[Source]:
        """
        Dynamically derives sources to monitor based on company profile & QAs.
        Strictly zero hardcoding.
        """
        qas = db.query(InterviewQA).filter_by(company_id=company.id).all()
        qa_summary = "\n".join([f"Q: {q.question} A: {q.answer}" for q in qas])

        user_prompt = (
            f"Company: {company.name} ({company.domain})\n"
            f"Industry: {company.industry}\n"
            f"Description: {company.description}\n"
            f"Interview Context:\n{qa_summary}\n\n"
            f"Discover external RSS feeds, news releases, and competitor feeds to crawl."
        )

        res = await llm_client.generate_json(SOURCE_DISCOVERY_SYSTEM, user_prompt)
        sources_created = []
        for s in res.get("sources", []):
            url = s.get("url")
            if not url:
                continue
            # Deduplicate by url & company_id
            existing = db.query(Source).filter_by(company_id=company.id, url=url).first()
            if not existing:
                src = Source(
                    company_id=company.id,
                    url=url,
                    category=s.get("category", "competitors"),
                    reason=s.get("reason", "Discovered through LLM profile analysis"),
                    status="active",
                    health="healthy"
                )
                db.add(src)
                sources_created.append(src)
        
        db.commit()
        for src in sources_created:
            db.refresh(src)
        return sources_created

profile_service = ProfileService()
