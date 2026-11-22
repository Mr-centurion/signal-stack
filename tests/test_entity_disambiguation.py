import pytest
from unittest.mock import AsyncMock, patch
from backend.models import Document
from backend.services.research_service import company_research_service

@pytest.mark.asyncio
async def test_entity_disambiguation_rejects_unrelated_news():
    """
    Verifies that Google News RSS items are accepted ONLY if:
    (a) They mention the company's domain or base domain, OR
    (b) They match a strict name + industry check against the site profile text.
    Unrelated entities with overlapping generic words (e.g., Nigerian universities) are rejected.
    """
    mock_rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>Google News</title>
        <item>
          <title>Meet University of Ibadan 14th VC, Peter Olapegba</title>
          <link>https://theguardian.ng/news/nigeria/meet-university-of-ibadan-vc/</link>
          <description>The governing council announces the appointment of Professor Peter Olapegba.</description>
        </item>
        <item>
          <title>Meet University Professor John Doe in Cambridge</title>
          <link>https://example.com/meet-professor</link>
          <description>Cambridge department hosts public lecture series.</description>
        </item>
        <item>
          <title>MeetUniversity expands higher education counseling portal for international admissions</title>
          <link>https://edtechtimes.com/meetuniversity-admissions-portal</link>
          <description>MeetUniversity has introduced an upgraded counseling platform assisting students with university admissions.</description>
        </item>
        <item>
          <title>EdTech platform updates features on meetuniv.com domain</title>
          <link>https://technews.com/meetuniv-updates</link>
          <description>Overseas education startup introduces new tools at meetuniv.com for study abroad applicants.</description>
        </item>
      </channel>
    </rss>
    """

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = mock_rss_xml
        mock_get.return_value = mock_response

        # Test with company MeetUniversity, domain meetuniv.com, and site text
        site_profile = (
            "MeetUniversity operates an overseas higher education admissions counseling platform. "
            "We help students secure university admissions and international study abroad scholarships."
        )

        filtered_news = await company_research_service.fetch_public_news(
            company_name="MeetUniversity",
            domain="meetuniv.com",
            site_profile_text=site_profile
        )

        # Must reject:
        # 1. "Meet University of Ibadan 14th VC..." (unrelated Nigerian academic institution)
        # 2. "Meet University Professor John Doe..." (unrelated Cambridge lecture)
        # Must accept:
        # 3. "MeetUniversity expands higher education counseling portal..." (name + industry match)
        # 4. "EdTech platform updates features on meetuniv.com domain" (domain match)
        assert len(filtered_news) == 2, f"Expected exactly 2 disambiguated news items, got {len(filtered_news)}"
        
        titles = [n["title"] for n in filtered_news]
        assert any("higher education counseling portal" in t for t in titles)
        assert any("meetuniv.com domain" in t for t in titles)
        assert not any("Ibadan" in t for t in titles), "Failed disambiguation: Ibadan university news was not rejected!"
        assert not any("Professor John Doe" in t for t in titles), "Failed disambiguation: Cambridge professor news was not rejected!"

def test_validate_snippets_anchored_strictly_to_site_docs():
    """
    Verifies that claims marked 'verified' MUST have quote snippets present
    in the company's own site documents. If a snippet only appeared in an external news article,
    it must be downgraded to 'assumption' with snippet cleared.
    """
    site_doc = Document(
        id=101,
        url="https://meetuniv.com/about",
        raw_text="MeetUniversity is India's leading international education admissions and student visa counseling marketplace."
    )
    news_doc = Document(
        id=102,
        url="https://news.com/random",
        raw_text="External speculative claim: Company is raising $50M from Silicon Valley venture funds."
    )

    profile_claim = {
        "business_lines": [
            {
                "text": "Overseas education and student visa counseling",
                "status": "verified",
                "evidence_snippet": "international education admissions and student visa counseling"
            },
            {
                "text": "Speculative $50M venture financing round",
                "status": "verified",
                "evidence_snippet": "raising $50M from Silicon Valley venture funds"
            }
        ]
    }

    # Pass site_documents=[site_doc] to validate_snippets_and_ground
    validated = company_research_service.validate_snippets_and_ground(
        profile_claim,
        documents=[site_doc, news_doc],
        site_documents=[site_doc]
    )

    bls = validated["business_lines"]
    # First claim exists verbatim in site_doc -> stays verified
    assert bls[0]["status"] == "verified"
    assert bls[0]["evidence_snippet"] is not None

    # Second claim was only in news_doc -> must be downgraded to assumption
    assert bls[1]["status"] == "assumption"
    assert bls[1]["evidence_snippet"] is None
    assert "Downgraded" in bls[1]["validation_note"]
