import os
import json
import pytest
from backend.models import Company, Document, ProfileFact, InterviewQA
from backend.services.research_service import company_research_service
from backend.services.interview_service import interview_service, INTERVIEW_TOPICS
from backend.services.llm_client import llm_client

EVIDENCE_DIR = "/Users/anandvardhanchauhan/Downloads/Signal Stack/tests/evidence"

@pytest.fixture(autouse=True)
def ensure_evidence_dir():
    os.makedirs(EVIDENCE_DIR, exist_ok=True)

@pytest.mark.asyncio
async def test_meetuniversity_vs_unrelated_adaptive_interview(db_session):
    """
    Test Phase 1 requirement:
    1. Run research and adaptive interview generation on MeetUniversity (https://www.meetuniversity.com).
    2. Run research and adaptive interview generation on an unrelated company (PostHog - https://posthog.com).
    3. Programmatically validate snippets against crawled text (downgrade ungrounded claims).
    4. Verify that generated questions differ and specifically reference each company's domain.
    5. Save outputs under /tests/evidence/.
    """
    # 1. Onboard MeetUniversity
    comp_meetuni = Company(
        name="MeetUniversity",
        domain="meetuniversity.com",
        website_url="https://www.meetuniversity.com",
        industry="EdTech & Overseas Higher Education Admissions"
    )
    db_session.add(comp_meetuni)
    db_session.commit()
    db_session.refresh(comp_meetuni)

    meetuni_res = await company_research_service.run_research(
        db=db_session,
        company_id=comp_meetuni.id,
        company_name="MeetUniversity",
        url="https://www.meetuniversity.com"
    )
    assert meetuni_res["status"] == "success"
    assert "profile" in meetuni_res

    # Save MeetUniversity Research Evidence
    meetuni_research_path = os.path.join(EVIDENCE_DIR, "meetuniversity_research.json")
    with open(meetuni_research_path, "w") as f:
        json.dump(meetuni_res["profile"], f, indent=2)

    # Generate next question for MeetUniversity
    meetuni_q = await interview_service.get_or_generate_next_question(db_session, comp_meetuni.id)
    assert not meetuni_q.get("is_completed")
    assert "meetuniversity" in meetuni_q["question"].lower()

    # Save MeetUniversity Interview Question
    meetuni_interview_path = os.path.join(EVIDENCE_DIR, "meetuniversity_interview.json")
    with open(meetuni_interview_path, "w") as f:
        json.dump(meetuni_q, f, indent=2)

    # 2. Onboard Unrelated Company (PostHog)
    comp_unrelated = Company(
        name="PostHog",
        domain="posthog.com",
        website_url="https://posthog.com",
        industry="Developer Product Analytics & Session Replay"
    )
    db_session.add(comp_unrelated)
    db_session.commit()
    db_session.refresh(comp_unrelated)

    unrelated_res = await company_research_service.run_research(
        db=db_session,
        company_id=comp_unrelated.id,
        company_name="PostHog",
        url="https://posthog.com"
    )
    assert unrelated_res["status"] == "success"

    # Save Unrelated Research Evidence
    unrelated_research_path = os.path.join(EVIDENCE_DIR, "unrelated_research.json")
    with open(unrelated_research_path, "w") as f:
        json.dump(unrelated_res["profile"], f, indent=2)

    # Generate next question for Unrelated Company
    unrelated_q = await interview_service.get_or_generate_next_question(db_session, comp_unrelated.id)
    assert not unrelated_q.get("is_completed")

    # Save Unrelated Interview Question
    unrelated_interview_path = os.path.join(EVIDENCE_DIR, "unrelated_interview.json")
    with open(unrelated_interview_path, "w") as f:
        json.dump(unrelated_q, f, indent=2)

    # 3. Assert that the questions strictly differ and are not generic
    assert meetuni_q["question"] != unrelated_q["question"], "Questions for different companies must not be identical!"
    assert ("meetuniversity" in meetuni_q["question"].lower() or "student" in meetuni_q["question"].lower() or "admissions" in meetuni_q["question"].lower()), "MeetUniversity question must be grounded in its domain"
    assert ("enterprise" in unrelated_q["question"].lower() or "developer" in unrelated_q["question"].lower() or "infrastructure" in unrelated_q["question"].lower() or "revenue" in unrelated_q["question"].lower()), "Unrelated company question must reflect its domain"

    # Save Comparison Diff Evidence
    comparison_diff = {
        "company_a": {
            "name": comp_meetuni.name,
            "domain": comp_meetuni.domain,
            "question_1": meetuni_q["question"],
            "topic": meetuni_q["topic"]
        },
        "company_b": {
            "name": comp_unrelated.name,
            "domain": comp_unrelated.domain,
            "question_1": unrelated_q["question"],
            "topic": unrelated_q["topic"]
        },
        "questions_are_different": meetuni_q["question"] != unrelated_q["question"],
        "validation": "Passed: Dynamic, non-generic, company-specific questions verified."
    }
    with open(os.path.join(EVIDENCE_DIR, "comparison_diff.json"), "w") as f:
        json.dump(comparison_diff, f, indent=2)

@pytest.mark.asyncio
async def test_adaptive_interview_flow_with_followup_and_skip(db_session):
    """
    Tests:
    - 10-question adaptive loop
    - Follow-up question triggered on vague answer
    - Skip option for confidential questions
    - Answer editing re-triggers profile update
    """
    company = Company(
        name="Nexus BioTech",
        domain="nexusbio.example.com",
        industry="Genomics Therapeutics"
    )
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)

    # Step 1: Initial Question (Topic 1: revenue_lines)
    q1 = await interview_service.get_or_generate_next_question(db_session, company.id)
    assert q1["topic"] == "revenue_lines"
    assert not q1["is_follow_up"]

    # Step 2: User gives a vague/brief answer -> triggers follow-up
    qa1 = await interview_service.submit_answer(
        db=db_session,
        company_id=company.id,
        question=q1["question"],
        answer="sales", # intentionally brief (<25 chars)
        topic=q1["topic"],
        category=q1["category"],
        question_index=q1["question_index"]
    )
    assert qa1.id is not None

    # Step 3: Next call should return a follow-up probe
    q_followup = await interview_service.get_or_generate_next_question(db_session, company.id)
    assert q_followup["is_follow_up"] is True
    assert q_followup["parent_qa_id"] == qa1.id

    # Step 4: Answer the follow-up with concrete details
    await interview_service.submit_answer(
        db=db_session,
        company_id=company.id,
        question=q_followup["question"],
        answer="We generate $12M annually from enterprise pharma screening licenses and clinical pipeline milestones.",
        topic=q_followup["topic"],
        category=q_followup["category"],
        question_index=q_followup["question_index"],
        is_follow_up=True,
        parent_qa_id=qa1.id
    )

    # Step 5: Next question should advance to Topic 2 (top_customer_segments)
    q2 = await interview_service.get_or_generate_next_question(db_session, company.id)
    assert q2["topic"] == "top_customer_segments"
    assert not q2["is_follow_up"]

    # Step 6: User skips Topic 2 (Confidential)
    await interview_service.submit_answer(
        db=db_session,
        company_id=company.id,
        question=q2["question"],
        answer="skip",
        topic=q2["topic"],
        category=q2["category"],
        question_index=q2["question_index"],
        is_skipped=True
    )

    # Step 7: Next question should advance to Topic 3 (customer_problems)
    q3 = await interview_service.get_or_generate_next_question(db_session, company.id)
    assert q3["topic"] == "customer_problems"

    # Step 8: Edit previous answer (qa1) and assert re-triggered profile update
    updated_qa = await interview_service.update_answer(
        db=db_session,
        qa_id=qa1.id,
        new_answer="Commercial licensing agreements with Tier-1 oncology pharmaceutical enterprises."
    )
    assert "Commercial licensing agreements" in updated_qa.answer
    
    # Verify ProfileFact was updated with edited origin
    fact = db_session.query(ProfileFact).filter_by(
        company_id=company.id,
        field_name="revenue_lines",
        source_origin="edited"
    ).first()
    assert fact is not None
    assert "Commercial licensing agreements" in fact.text

def test_programmatic_snippet_validation():
    """
    Tests programmatic validation:
    Verified claims with fake/missing snippets must be downgraded to 'assumption'.
    Verified claims with verbatim snippets must remain 'verified'.
    """
    doc = Document(
        company_id=1,
        url="https://example.com/about",
        content_hash="test_hash",
        title="About Us",
        raw_text="Acme Corp specializes in enterprise supply chain logistics across North America.",
        first_seen=None
    )

    profile = {
        "business_lines": [
            {
                "text": "Enterprise Supply Chain Logistics",
                "status": "verified",
                "evidence_snippet": "enterprise supply chain logistics",
                "source_url": "https://example.com/about"
            },
            {
                "text": "Quantum Cryptography Banking",
                "status": "verified",
                "evidence_snippet": "this snippet is completely made up and not in text",
                "source_url": "https://example.com/about"
            }
        ],
        "positioning": {
            "text": "Leader in freight deadhead reduction",
            "status": "verified",
            "evidence_snippet": "completely ungrounded hallucination",
            "source_url": "https://example.com/about"
        }
    }

    validated = company_research_service.validate_snippets_and_ground(profile, [doc])
    
    # 1. Grounded claim must remain verified
    assert validated["business_lines"][0]["status"] == "verified"
    
    # 2. Ungrounded claims must be programmatically downgraded to assumption
    assert validated["business_lines"][1]["status"] == "assumption"
    assert validated["business_lines"][1]["evidence_snippet"] is None
    assert "Downgraded" in validated["business_lines"][1]["validation_note"]

    assert validated["positioning"]["status"] == "assumption"
    assert validated["positioning"]["evidence_snippet"] is None
