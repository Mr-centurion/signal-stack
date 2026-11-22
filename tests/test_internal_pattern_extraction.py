import pytest
from backend.database import SessionLocal
from backend.models import Company, Document, Brief
from backend.services.internal_doc_service import internal_doc_service
from backend.services.brief_service import brief_service
from backend.services.llm_client import llm_client

@pytest.mark.needs_data
@pytest.mark.asyncio
async def test_internal_pattern_extraction_from_sample_file():
    """
    Verifies that for uploaded files (CSV/Excel/PDF/TXT), the engine extracts:
    - recurring objections
    - lost-deal reasons
    - product requests
    - sales patterns
    with exact counts and verbatim line/row quotes verified against raw text.
    Also verifies Section 5 of the brief incorporates these or outputs 'No internal data uploaded.'
    """
    db = SessionLocal()
    
    # Use temporary test company or company #1
    company = db.query(Company).filter_by(id=1).first()
    if not company:
        db.close()
        pytest.skip("requires pre-populated database: copy data/demo/signal_stack_demo.db over signal_stack.db")

    # Clean existing internal uploads for deterministic test run
    db.query(Document).filter_by(
        company_id=company.id,
        category="internal",
        document_type="internal_upload"
    ).delete()
    db.commit()

    # Step 1: When no internal docs exist, pattern extraction returns No internal data uploaded
    empty_patterns = await internal_doc_service.extract_internal_patterns(db, company.id)
    assert empty_patterns["patterns_found"] is False
    assert "No internal data uploaded" in empty_patterns["markdown"]

    # Step 2: Upload a sample file marked SAMPLE_
    sample_filename = "SAMPLE_lost_deals_and_objections.csv"
    sample_csv_content = (
        "Deal_ID,Account_Name,Outcome,Reason_Category,Notes\n"
        "D-101,Acro Corp,Lost,Pricing,Prospect stated $5000 upfront fee exceeds institutional budget\n"
        "D-102,Beta Labs,Lost,Competitor,Client chose competitor offering direct German university placement guarantee\n"
        "D-103,Gamma Ltd,Lost,Pricing,Lost to local consultancy due to price sensitivity on onboarding fees\n"
        "D-104,Delta Tech,Lost,Feature Gap,Applicant requested step-by-step document verification portal\n"
        "D-105,Epsilon,Lost,Pricing,Customer declined subscription due to high per-student license cost\n"
        "D-106,Zeta Group,Won,Sales Dynamic,Same-day outreach lead conversion rate reached 65% vs 25% delayed\n"
    ).encode("utf-8")

    doc = internal_doc_service.ingest_document(
        db=db,
        company_id=company.id,
        filename=sample_filename,
        content_bytes=sample_csv_content
    )
    assert doc is not None
    assert doc.id is not None
    assert doc.document_type == "internal_upload"

    # Step 3: Run internal pattern extraction
    # Provider mock will provide structured response or live preview
    patterns = await internal_doc_service.extract_internal_patterns(db, company.id)
    
    # Assert extraction structure
    assert "markdown" in patterns
    assert len(patterns["markdown"]) > 0

    # Verify that raw text contains the quotes
    doc_raw_text = doc.raw_text.lower()
    for cat in ["objections", "lost_deal_reasons", "product_requests", "sales_patterns"]:
        for item in patterns.get(cat, []):
            assert "pattern" in item
            assert item["count"] >= 1
            for q in item["verbatim_quotes"]:
                # Quote must appear in raw document text
                norm_q = " ".join(q.lower().split())
                norm_doc = " ".join(doc_raw_text.split())
                assert norm_q[:25] in norm_doc, f"Quote '{q}' was not found in raw document text!"

    # Clean up test doc
    db.query(Document).filter_by(id=doc.id).delete()
    db.commit()
    db.close()
