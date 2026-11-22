import pytest
from backend.models import Company, Source
from backend.database import SessionLocal

@pytest.mark.needs_data
def test_stored_meetuniversity_source_counts(db_session):
    """
    Non-live test asserting that stored MeetUniversity approved sources in the database
    meet or exceed the strict 20+ requirement.
    """
    # Query stored approved sources for MeetUniversity
    db = SessionLocal()
    mu = db.query(Company).filter_by(name="MeetUniversity").first()
    approved = db.query(Source).filter_by(company_id=mu.id, status="approved").all() if mu else []
    db.close()

    if not mu or len(approved) == 0:
        pytest.skip("requires pre-populated database: copy data/demo/signal_stack_demo.db over signal_stack.db")

    assert len(approved) >= 20, (
        f"Expected >= 20 stored approved sources for MeetUniversity, found {len(approved)}"
    )

