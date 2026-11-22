import pytest
from backend.models import Company, Signal, Brief
from backend.services.brief_service import generate_monday_brief
from backend.crawler.fetcher import crawler_fetcher

def test_api_health_check(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["active_llm_provider"] == "mock"

def test_company_creation_and_interview_flow(client):
    # 1. Register company
    resp = client.post("/api/companies", json={
        "name": "Apex Cloud Systems",
        "domain": "apexcloud.example.com",
        "industry": "FinTech Cloud Infrastructure",
        "description": "Zero-latency transaction clearing platform for regional banks."
    })
    assert resp.status_code == 201
    company_id = resp.json()["id"]

    # 2. Generate dynamic interview questions (Rule 1: No hardcoded questions)
    q_resp = client.post(f"/api/companies/{company_id}/interview/generate")
    assert q_resp.status_code == 200
    questions = q_resp.json()["questions"]
    assert len(questions) >= 4
    categories = [q["category"] for q in questions]
    assert "customers" in categories
    assert "competitors" in categories

    # 3. Answer an interview question
    ans_resp = client.post(f"/api/companies/{company_id}/interview/answer", json={
        "question": questions[0]["question"],
        "answer": "Our customers are migrating from legacy on-prem core banking servers.",
        "category": questions[0]["category"]
    })
    assert ans_resp.status_code == 200
    assert ans_resp.json()["company_id"] == company_id

    # 4. Discover sources dynamically (Rule 1: No hardcoded sources)
    src_resp = client.post(f"/api/companies/{company_id}/sources/discover")
    assert src_resp.status_code == 200
    discovered = src_resp.json()["discovered_sources"]
    assert len(discovered) > 0

@pytest.mark.asyncio
async def test_monday_brief_nothing_happened_rule(db_session):
    """
    Test Rule 2: If nothing happened, the brief explicitly says so
    and nothing_happened_flag is True.
    """
    company = Company(
        name="Quiet Horizon Inc",
        domain="quiethorizon.example.com",
        industry="B2B Quiet Monitoring"
    )
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)

    # Generate brief with ZERO signals in DB
    brief = await generate_monday_brief(db_session, company.id)
    assert brief.nothing_happened_flag is True
    assert "zero material strategic signals" in brief.executive_summary.lower()
    assert brief.week_label is not None

def test_provider_switch_endpoint(client):
    res = client.post("/api/llm/provider", json={"provider": "mock"})
    assert res.status_code == 200
    assert res.json()["active_provider"] == "mock"

    res_invalid = client.post("/api/llm/provider", json={"provider": "nonexistent_ai"})
    assert res_invalid.status_code == 400
