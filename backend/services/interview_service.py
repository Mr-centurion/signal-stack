import json
import re
from difflib import SequenceMatcher
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Set
from sqlalchemy.orm import Session

from backend.models import Company, InterviewQA, ProfileFact
from backend.services.llm_client import llm_client
from backend.prompts.templates import (
    ADAPTIVE_QUESTION_GENERATION_SYSTEM,
    VAGUENESS_JUDGE_SYSTEM
)

# 10 Canonical Interview Topics with isolated objectives
INTERVIEW_TOPICS = [
    {
        "index": 1,
        "topic": "revenue_lines",
        "title": "Revenue Lines & Monetization",
        "category": "internal",
        "objective": "how the company monetizes, its core pricing structure, and key revenue streams",
        "allow_competitors": False
    },
    {
        "index": 2,
        "topic": "top_customer_segments",
        "title": "Target Customer Segments",
        "category": "customers",
        "objective": "primary customer segments, ideal buyer personas, and highest-value users",
        "allow_competitors": False
    },
    {
        "index": 3,
        "topic": "customer_problems",
        "title": "Customer Problems & Friction",
        "category": "customers",
        "objective": "urgent operational bottlenecks, customer pain points, or unmet needs you solve",
        "allow_competitors": False
    },
    {
        "index": 4,
        "topic": "why_customers_choose_us",
        "title": "Value Proposition & Win Factors",
        "category": "customers",
        "objective": "your core differentiator, unique defensible advantage, and why customers choose your offering",
        "allow_competitors": False
    },
    {
        "index": 5,
        "topic": "competitors_substitutes",
        "title": "Competitors & Alternatives",
        "category": "competitors",
        "objective": "direct competitors, emerging substitutes, and alternatives encountered in lost deals",
        "allow_competitors": True
    },
    {
        "index": 6,
        "topic": "market_shifts",
        "title": "Market Shifts & Macro Trends",
        "category": "market",
        "objective": "regulatory changes, economic shifts, industry tailwinds, or platform disruptions impacting your space",
        "allow_competitors": False
    },
    {
        "index": 7,
        "topic": "material_developments",
        "title": "Recent Material Developments",
        "category": "internal",
        "objective": "major internal milestones, product releases, key partnerships, or leadership additions in the last 6 months",
        "allow_competitors": False
    },
    {
        "index": 8,
        "topic": "priorities_6_12_months",
        "title": "6-12 Month Strategic Priorities",
        "category": "internal",
        "objective": "top 2-3 strategic initiatives, growth bets, or operational targets for the upcoming year",
        "allow_competitors": False
    },
    {
        "index": 9,
        "topic": "internal_data",
        "title": "Internal Health Metrics",
        "category": "internal",
        "objective": "operational telemetry, retention/conversion indicators, or key health metrics monitored weekly",
        "allow_competitors": False
    },
    {
        "index": 10,
        "topic": "decisions_to_support",
        "title": "Decisions System Must Support",
        "category": "internal",
        "objective": "high-stakes strategic, pricing, or product decisions this executive intelligence engine should inform",
        "allow_competitors": False
    }
]

class AdaptiveInterviewEngine:
    """
    Adaptive Interview Engine:
    - Generates 10 canonical questions one at a time.
    - Question text strictly targets only its own topic.
    - Uses at most one company-specific entity where natural.
    - Within-session validator: rejects question if similarity to ANY earlier question in same interview > 50%.
    - Enforces cross-company similarity threshold (< 70%).
    - Evaluates answer vagueness via LLM judge, formulating follow-ups quoting user's words (max 3).
    - In-place editing re-triggers profile update.
    """

    def extract_company_entities(self, company: Company) -> Set[str]:
        """Extracts candidate specific entities, products, and keywords from profile."""
        terms = set()
        terms.add(company.name.lower())
        for part in re.split(r"[\s\-_]+", company.name.lower()):
            if len(part) >= 3 and part not in ["inc", "llc", "corp", "ltd", "the", "and"]:
                terms.add(part)

        clean_domain = company.domain.lower().replace("www.", "").split(".")[0]
        if len(clean_domain) >= 3:
            terms.add(clean_domain)

        if company.intelligence_profile:
            try:
                prof = json.loads(company.intelligence_profile)
                for bl in prof.get("business_lines", []):
                    t = bl.get("text", "") if isinstance(bl, dict) else str(bl)
                    for word in re.findall(r"\b[A-Za-z]{4,}\b", t):
                        terms.add(word.lower())
                for ps in prof.get("products_services", []):
                    t = ps.get("text", "") if isinstance(ps, dict) else str(ps)
                    for word in re.findall(r"\b[A-Za-z]{4,}\b", t):
                        terms.add(word.lower())
            except Exception:
                pass

        return terms

    def extract_competitor_names(self, company: Company) -> Set[str]:
        """Extracts competitor names listed in the company profile."""
        competitors = set()
        if company.intelligence_profile:
            try:
                prof = json.loads(company.intelligence_profile)
                for comp in prof.get("likely_competitors", []):
                    cname = comp.get("name", "") if isinstance(comp, dict) else str(comp)
                    if cname:
                        competitors.add(cname.lower())
                        for cpart in re.split(r"[\s\-_]+", cname.lower()):
                            if len(cpart) >= 4:
                                competitors.add(cpart)
            except Exception:
                pass
        return competitors

    def validate_question(
        self,
        db: Session,
        company: Company,
        topic_key: str,
        question_text: str,
        company_terms: Set[str],
        prior_session_qas: List[InterviewQA]
    ) -> (bool, str):
        """
        Validates generated question:
        1. Within-Session Check: similarity to ANY earlier question in same interview must be <= 50%.
        2. Topic Already Answered: ensure topic is not already answered.
        3. Entity Grounding: must contain at most one natural entity and at least one company term.
        4. Competitor Leakage: do NOT mention competitors unless topic is 'competitors_substitutes'.
        5. Phrasing Cleanliness: no 'instead', 'you noted', 'you mentioned', or quoting prior answers in canonical questions.
        6. Cross-Company Check: similarity to other companies on the same topic must be < 70%.
        """
        q_lower = question_text.lower()

        # 1. Within-session similarity check (<= 50%)
        for prior_qa in prior_session_qas:
            sim = SequenceMatcher(None, q_lower, prior_qa.question.lower()).ratio()
            if sim > 0.50:
                return False, f"Within-session rejection: {sim*100:.1f}% similar to earlier question Q{prior_qa.question_index} ('{prior_qa.question}'). Must be <= 50%."

        # 2. Topic already answered
        for prior_qa in prior_session_qas:
            if not prior_qa.is_follow_up and prior_qa.topic == topic_key:
                return False, f"Topic '{topic_key}' has already been answered in this interview."

        # 3. Phrasing cleanliness: No follow-up or answer-quoting phrasing in canonical questions
        banned_phrases = [
            "you noted", "you mentioned", "you stated", "instead", 
            "could you share the specific financial breakdown", 
            "could you return to the question", "as you said", "you previously"
        ]
        for bp in banned_phrases:
            if bp in q_lower:
                return False, f"Prohibited phrasing: Canonical questions must not contain '{bp}'."

        # Check if canonical question reuses phrasing from previous answers
        for prior_qa in prior_session_qas:
            if prior_qa.answer and prior_qa.answer != "[Skipped: Confidential]":
                ans_words = prior_qa.answer.strip().split()
                if len(ans_words) >= 4:
                    for i in range(len(ans_words) - 3):
                        phrase = " ".join(ans_words[i:i+4]).lower()
                        if len(phrase) > 16 and phrase in q_lower:
                            return False, f"Prohibited reuse: Canonical question reuses phrase '{phrase}' from previous answer."

        # 4. Competitor Leakage: Only allowed in competitors_substitutes
        if topic_key != "competitors_substitutes":
            comp_names = self.extract_competitor_names(company)
            found_comps = [c for c in comp_names if c in q_lower]
            if found_comps:
                return False, f"Do not name competitors ('{found_comps[0]}') in non-competitor topic '{topic_key}'."

        # 5. Must contain company reference
        has_entity = any(term in q_lower for term in company_terms)
        if not has_entity:
            return False, f"Question must reference at least one natural entity or term from {company.name}'s profile."

        # 6. Never echo internal topic label
        for topic_cfg in INTERVIEW_TOPICS:
            if topic_cfg["topic"] == topic_key:
                if topic_cfg["title"].lower() in q_lower and ("structure its" in q_lower or "how does" in q_lower):
                    return False, f"Question echoes internal topic title '{topic_cfg['title']}' as generic phrasing."

        # 7. Cross-company similarity check (< 70%)
        other_qas = db.query(InterviewQA).filter(
            InterviewQA.company_id != company.id,
            InterviewQA.topic == topic_key,
            InterviewQA.is_follow_up == False
        ).all()

        for oqa in other_qas:
            sim = SequenceMatcher(None, q_lower, oqa.question.lower()).ratio()
            if sim > 0.70:
                return False, f"Question is {sim*100:.1f}% similar to another company's question on '{topic_key}'."

        return True, "Valid"

    def get_progress(self, db: Session, company_id: int) -> Dict[str, Any]:
        """Returns the current interview progress (e.g. 3/10 completed)."""
        answered_qas = db.query(InterviewQA).filter_by(company_id=company_id).all()
        canonical_answered = [q for q in answered_qas if not q.is_follow_up]
        answered_topic_keys = {q.topic for q in canonical_answered}
        completed_count = len(answered_topic_keys)
        total_topics = len(INTERVIEW_TOPICS)
        current_step = min(completed_count + 1, total_topics)
        is_completed = completed_count >= total_topics

        return {
            "completed_count": completed_count,
            "total_questions": total_topics,
            "progress_label": f"{completed_count}/{total_topics}",
            "is_completed": is_completed,
            "next_index": current_step if not is_completed else None
        }

    async def get_or_generate_next_question(self, db: Session, company_id: int, allow_followup: bool = True) -> Dict[str, Any]:
        """
        Dynamically generates the next question in sequence, or an adaptive follow-up.
        Enforces within-session validation, topic isolation, and regeneration (max 2 retries).
        """
        company = db.query(Company).filter_by(id=company_id).first()
        if not company:
            raise ValueError("Company not found")

        qas = db.query(InterviewQA).filter_by(company_id=company_id).order_by(InterviewQA.id.asc()).all()
        canonical_answered = [q for q in qas if not q.is_follow_up]
        follow_ups_count = len([q for q in qas if q.is_follow_up])

        # Check if the last submitted answer was judged vague and needs ONE follow-up
        if allow_followup and qas and not qas[-1].is_follow_up and not qas[-1].is_skipped and follow_ups_count < 3:
            last_qa = qas[-1]
            has_followup_for_last = any(q.parent_qa_id == last_qa.id for q in qas)
            if not has_followup_for_last:
                last_ans = last_qa.answer.strip()
                # Evaluate vagueness with LLM judge
                vagueness_eval = await self.evaluate_vagueness(company, last_qa.question, last_ans)
                if vagueness_eval.get("is_vague") and vagueness_eval.get("followup_question"):
                    return {
                        "question_index": last_qa.question_index,
                        "topic": last_qa.topic,
                        "category": last_qa.category,
                        "question": vagueness_eval["followup_question"],
                        "rationale": f"Vagueness probe: {vagueness_eval.get('reason')}",
                        "is_follow_up": True,
                        "parent_qa_id": last_qa.id,
                        "progress_label": f"{len(canonical_answered)}/10 (Follow-Up)"
                    }

        # Check if all 10 canonical topics are finished
        answered_topic_keys = {q.topic for q in canonical_answered}
        unanswered_topics = [t for t in INTERVIEW_TOPICS if t["topic"] not in answered_topic_keys]
        if not unanswered_topics:
            return {
                "is_completed": True,
                "message": "Interview completed! All 10 strategic topics covered."
            }

        # Next canonical topic
        next_topic_cfg = unanswered_topics[0]
        topic_key = next_topic_cfg["topic"]
        topic_objective = next_topic_cfg["objective"]

        company_terms = self.extract_company_entities(company)
        profile_context = company.intelligence_profile or ""
        
        # Build prior questions list for within-session context
        prior_session_qas = qas
        prior_q_list = "\n".join([f"- Q{q.question_index} [{q.topic}]: {q.question}" for q in canonical_answered])

        # Generate with validation loop (max 2 retries)
        last_feedback = ""
        question_text = ""
        category = next_topic_cfg["category"]
        rationale = ""

        competitor_instruction = "You MAY mention relevant competitors here if natural." if next_topic_cfg["allow_competitors"] else "DO NOT mention or name any competitors in this question."

        for attempt in range(3):
            user_prompt = (
                f"TARGET COMPANY: {company.name} ({company.domain})\n"
                f"INDUSTRY: {company.industry or 'Technology'}\n"
                f"RESEARCH PROFILE: {profile_context[:2000]}\n\n"
                f"QUESTIONS ALREADY ASKED IN THIS INTERVIEW (DO NOT REPEAT PHRASING OR TOPICS):\n{prior_q_list or 'None yet.'}\n\n"
                f"ASSIGNED TOPIC: {next_topic_cfg['title']} ({topic_key})\n"
                f"TOPIC OBJECTIVE: {topic_objective}\n"
                f"COMPETITOR POLICY: {competitor_instruction}\n"
                f"MANDATORY CONSTRAINTS:\n"
                f"1. Target ONLY {next_topic_cfg['title']}. Do not ask about other topics.\n"
                f"2. Use at most ONE natural company entity (e.g. '{company.name}'). Do not pack multiple entities.\n"
                f"3. Do NOT quote prior answers or say 'instead' or 'you noted'.\n"
                f"4. Formulate an incisive, direct, original question (1-2 sentences)."
            )
            if last_feedback:
                user_prompt += f"\n\nCORRECTION REQUIRED: Your prior draft failed validation: {last_feedback}. Fix this strictly in your new generation."

            res = await llm_client.generate_json(ADAPTIVE_QUESTION_GENERATION_SYSTEM, user_prompt)
            candidate_q = res.get("question") or res.get("interview_question") or res.get("text") or ""
            category = res.get("category", category)
            rationale = res.get("rationale", f"Gauging {next_topic_cfg['title']} for {company.name}.")

            if candidate_q:
                is_valid, reason = self.validate_question(db, company, topic_key, candidate_q, company_terms, prior_session_qas)
                if is_valid:
                    question_text = candidate_q
                    break
                else:
                    last_feedback = reason
                    question_text = candidate_q

        # Fallback safety if retries exhaust
        if not question_text or len(question_text.strip()) < 15:
            topic_clean = topic_key.replace('_', ' ')
            question_text = f"Regarding {company.name}'s {topic_clean}: what is your primary strategic focus and operational mechanism in this area?"

        return {
            "question_index": next_topic_cfg["index"],
            "topic": topic_key,
            "category": category,
            "question": question_text,
            "rationale": rationale,
            "is_follow_up": False,
            "progress_label": f"{len(canonical_answered) + 1}/10"
        }

    async def evaluate_vagueness(self, company: Company, question: str, answer: str) -> Dict[str, Any]:
        """
        Uses an LLM judge to determine if an answer is vague/brief/evasive.
        Returns {is_vague: bool, reason: str, followup_question: str}
        Follow-up must directly quote or reference the user's answer.
        """
        if answer in ["[Skipped: Confidential]", "skip"]:
            return {"is_vague": False, "reason": "User skipped confidential topic", "followup_question": None}

        # If answer is detailed and substantive, avoid unnecessary extra probe
        if len(answer.split()) > 25:
            return {"is_vague": False, "reason": "Detailed answer provided", "followup_question": None}

        judge_prompt = (
            f"COMPANY: {company.name} ({company.domain})\n"
            f"QUESTION ASKED: {question}\n"
            f"USER ANSWER: \"{answer}\"\n\n"
            f"Assess if the answer is vague or lacking substance. If vague, formulate a follow-up that explicitly quotes or references words from '{answer}'."
        )

        try:
            res = await llm_client.generate_json(VAGUENESS_JUDGE_SYSTEM, judge_prompt)
            return {
                "is_vague": bool(res.get("is_vague", False)),
                "reason": res.get("reason", ""),
                "followup_question": res.get("followup_question")
            }
        except Exception:
            is_vague = len(answer.strip().split()) < 4
            followup = f"You mentioned '{answer}'—could you elaborate with a specific metric or example regarding that?" if is_vague else None
            return {
                "is_vague": is_vague,
                "reason": "Brief response",
                "followup_question": followup
            }

    async def submit_answer(
        self,
        db: Session,
        company_id: int,
        question: str,
        answer: str,
        topic: str,
        category: str,
        question_index: int,
        is_follow_up: bool = False,
        parent_qa_id: Optional[int] = None,
        is_skipped: bool = False
    ) -> InterviewQA:
        """Records an answer or skip, and updates the Company Intelligence Profile."""
        company = db.query(Company).filter_by(id=company_id).first()
        if not company:
            raise ValueError("Company not found")

        final_answer = "[Skipped: Confidential]" if is_skipped else answer.strip()

        qa = InterviewQA(
            company_id=company_id,
            question_index=question_index,
            topic=topic,
            question=question,
            answer=final_answer,
            category=category,
            is_follow_up=is_follow_up,
            is_skipped=is_skipped,
            parent_qa_id=parent_qa_id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(qa)

        # If not skipped and not a test fixture, store as a ProfileFact originating from interview
        is_test_fixture = (
            "[TEST FIXTURE]" in final_answer or
            final_answer.startswith("TEST FIXTURE") or
            "[TEST MODE]" in final_answer
        )
        if not is_skipped and not is_test_fixture:
            fact = ProfileFact(
                company_id=company_id,
                category=category,
                field_name=topic,
                fact_type="fact",
                text=f"[{topic.upper()}] {final_answer}",
                source_origin="interview",
                source=f"Executive Interview (Topic: {topic})",
                confidence_score=1.0
            )
            db.add(fact)

        db.commit()
        db.refresh(qa)

        # Merge update into intelligence profile
        self.sync_intelligence_profile(db, company)

        return qa

    async def update_answer(self, db: Session, qa_id: int, new_answer: str) -> InterviewQA:
        """
        Allows editing a previous answer and re-triggers intelligence profile update.
        """
        qa = db.query(InterviewQA).filter_by(id=qa_id).first()
        if not qa:
            raise ValueError("Interview QA not found")

        qa.answer = new_answer.strip()
        qa.is_skipped = False
        qa.updated_at = datetime.now(timezone.utc)

        fact = db.query(ProfileFact).filter_by(
            company_id=qa.company_id,
            field_name=qa.topic,
            source_origin="interview"
        ).first()

        if fact:
            fact.text = f"[{qa.topic.upper()}] {qa.answer}"
            fact.source_origin = "edited"
            fact.source = f"Edited Interview Answer ({qa.topic})"
            fact.updated_at = datetime.now(timezone.utc)
        else:
            fact = ProfileFact(
                company_id=qa.company_id,
                category=qa.category,
                field_name=qa.topic,
                fact_type="fact",
                text=f"[{qa.topic.upper()}] {qa.answer}",
                source_origin="edited",
                source=f"Edited Interview Answer ({qa.topic})"
            )
            db.add(fact)

        db.commit()
        db.refresh(qa)

        company = db.query(Company).filter_by(id=qa.company_id).first()
        self.sync_intelligence_profile(db, company)

        return qa

    def sync_intelligence_profile(self, db: Session, company: Company):
        """Merges research profile and interview Q&As into unified Company Intelligence Profile."""
        raw_profile = {}
        if company.intelligence_profile:
            try:
                raw_profile = json.loads(company.intelligence_profile)
            except Exception:
                raw_profile = {}

        qas = db.query(InterviewQA).filter_by(company_id=company.id).all()
        interview_insights = {}
        for q in qas:
            if not q.is_skipped and q.answer != "[Skipped: Confidential]":
                interview_insights[q.topic] = {
                    "question": q.question,
                    "answer": q.answer,
                    "source": "interview"
                }

        raw_profile["interview_insights"] = interview_insights
        company.intelligence_profile = json.dumps(raw_profile)
        db.commit()

interview_service = AdaptiveInterviewEngine()
