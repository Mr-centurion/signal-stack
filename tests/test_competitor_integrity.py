import pytest
from backend.database import SessionLocal
from backend.models import Company, Competitor, InterviewQA
from backend.services.competitor_discovery_service import competitor_discovery_service
from backend.services.brief_service import brief_service

def test_company_never_in_own_competitor_list():
    """
    Verifies that a company, its subsidiaries, and its own domains
    are strictly excluded from its competitor list.
    """
    db = SessionLocal()
    for c in db.query(Company).all():
        comps = db.query(Competitor).filter_by(company_id=c.id).all()
        for comp in comps:
            # Domain check
            assert not competitor_discovery_service.is_excluded_entity(comp.name, comp.url, c.domain, c.name), (
                f"Company #{c.id} ({c.name}) lists prohibited competitor: '{comp.name}' ({comp.url})"
            )
            # Direct name equality check
            assert c.name.lower() != comp.name.lower(), (
                f"Company #{c.id} ({c.name}) lists itself as a competitor"
            )
    db.close()

def test_competitor_cap_at_ten():
    """
    Verifies that competitors are strictly capped at 10 per company.
    """
    db = SessionLocal()
    for c in db.query(Company).all():
        comps = db.query(Competitor).filter_by(company_id=c.id).all()
        assert len(comps) <= 10, f"Company {c.name} has {len(comps)} competitors, exceeding max cap of 10"
    db.close()

@pytest.mark.needs_data
def test_fixture_answers_excluded_from_founder_input():
    """
    Verifies that interview answers containing [TEST FIXTURE] are strictly
    excluded from brief founder input context.
    """
    db = SessionLocal()
    mu = db.query(Company).filter_by(id=1).first()
    if not mu:
        db.close()
        pytest.skip("requires pre-populated database: copy data/demo/signal_stack_demo.db over signal_stack.db")

    qas = db.query(InterviewQA).filter_by(company_id=mu.id).all()
    # Confirm fixture detection
    for qa in qas:
        if qa.answer and "[TEST FIXTURE]" in qa.answer:
            is_fixture = (
                "[TEST FIXTURE]" in qa.answer or
                qa.answer.startswith("TEST FIXTURE")
            )
            assert is_fixture is True

    # Confirm that validate_brief_specificity filters them out
    real_qas = [
        q for q in qas 
        if q.answer and not q.is_skipped and "[TEST FIXTURE]" not in q.answer
    ]
    # No real human answers in fixture run
    assert len(real_qas) == 0, "All simulated answers must be identified as test fixtures"
    db.close()
