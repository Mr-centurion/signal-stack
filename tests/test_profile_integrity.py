import pytest
from backend.models import Company, ProfileFact
from backend.services.brief_service import brief_service
from backend.services.profile_service import profile_service

@pytest.mark.asyncio
async def test_brief_consistency_rejects_ibadan_contradiction():
    """
    Mandate 1 Requirement:
    Add a brief-level consistency check: before saving, an LLM compares the brief
    against the current profile description and industry and rejects contradictions
    (a university vs a counselling platform). Add a test using the Ibadan text.
    """
    company = Company(
        id=1,
        name="MeetUniversity",
        domain="www.meetuniversity.com",
        industry="EdTech & Study Abroad Admissions Portal",
        description="A technology-driven, personalized consultancy providing unbiased guidance for Indian students seeking international education."
    )

    # Draft containing the corrupted Ibadan university hallucination
    corrupted_brief_data = {
        "executive_summary": (
            "Meet University operates as a public research university and academic institution located in Ibadan, Nigeria, "
            "focusing on higher education degree programs, undergraduate and postgraduate students, and academic administration "
            "funded by government allocations and student tuition fees."
        ),
        "internal_intelligence": "Campus faculties reported administrative restructuring.",
        "customer_signals": "No meaningful development detected this cycle.",
        "competitor_intelligence": "No meaningful development detected this cycle."
    }

    is_consistent, contradictions = await brief_service.verify_brief_consistency(corrupted_brief_data, company)
    
    assert is_consistent is False, "Expected brief-level consistency check to reject Ibadan university contradiction!"
    assert len(contradictions) > 0
    assert any("ibadan" in c.lower() or "university" in c.lower() for c in contradictions)

def test_retire_non_anchored_facts(db_session):
    """
    Mandate 1 Requirement:
    Brief generation must use only facts that are verified, carry a snippet from the
    company's own domain, and are current; superseded or non-anchored facts must never be eligible.
    """
    company = Company(
        name="MeetUniversity",
        domain="www.meetuniversity.com",
        industry="EdTech"
    )
    db_session.add(company)
    db_session.commit()

    # 1. Valid anchored fact
    f_valid = ProfileFact(
        company_id=company.id,
        category="internal",
        field_name="business_lines",
        fact_type="fact",
        text="Study Abroad Counseling",
        source_url="https://www.meetuniversity.com/about",
        evidence_snippet="Empower students to achieve their dreams of studying abroad by offering counseling",
        is_current=True,
        is_anchored=True
    )
    # 2. Assumption without snippet
    f_assumption = ProfileFact(
        company_id=company.id,
        category="internal",
        field_name="revenue_model",
        fact_type="assumption",
        text="Likely a combination of service fees",
        source_url="https://www.meetuniversity.com/about",
        evidence_snippet=None,
        is_current=True,
        is_anchored=True
    )
    # 3. Fact from external non-anchored domain
    f_unanchored = ProfileFact(
        company_id=company.id,
        category="internal",
        field_name="positioning",
        fact_type="fact",
        text="Nigerian university administration",
        source_url="https://en.wikipedia.org/wiki/University_of_Ibadan",
        evidence_snippet="The University of Ibadan is a public research university in Ibadan, Nigeria.",
        is_current=True,
        is_anchored=True
    )

    db_session.add_all([f_valid, f_assumption, f_unanchored])
    db_session.commit()

    retired = profile_service.retire_non_anchored_facts(db_session, company_id=company.id)
    retired_ids = [r["id"] for r in retired]

    assert f_assumption.id in retired_ids
    assert f_unanchored.id in retired_ids
    assert f_valid.id not in retired_ids

    # Check DB state
    db_session.refresh(f_valid)
    db_session.refresh(f_assumption)
    db_session.refresh(f_unanchored)

    assert f_valid.is_current is True and f_valid.is_anchored is True
    assert f_assumption.is_current is False and f_assumption.is_anchored is False
    assert f_unanchored.is_current is False and f_unanchored.is_anchored is False
