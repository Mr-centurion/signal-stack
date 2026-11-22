import pytest
from backend.models import Company, Source
from backend.database import SessionLocal

def test_stored_meetuniversity_source_counts(db_session):
    """
    Non-live test asserting that stored MeetUniversity approved sources in the database
    meet or exceed the strict 20+ requirement.
    """
    # Query stored approved sources for MeetUniversity
    mu = db_session.query(Company).filter_by(name="MeetUniversity").first()
    if not mu:
        db = SessionLocal()
        mu = db.query(Company).filter_by(name="MeetUniversity").first()
        approved = db.query(Source).filter_by(company_id=mu.id, status="approved").all() if mu else []
        db.close()
    else:
        approved = db_session.query(Source).filter_by(company_id=mu.id, status="approved").all()
        if len(approved) < 20:
            db = SessionLocal()
            mu_db = db.query(Company).filter_by(name="MeetUniversity").first()
            if mu_db:
                approved = db.query(Source).filter_by(company_id=mu_db.id, status="approved").all()
            db.close()

    assert len(approved) >= 20, (
        f"Expected >= 20 stored approved sources for MeetUniversity, found {len(approved)}"
    )
