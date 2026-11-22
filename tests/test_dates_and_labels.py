from datetime import datetime, timezone, timedelta
from backend.crawler.date_extractor import sanitize_publication_date
from backend.services.analysis_engine import validate_and_normalize_event_type, VALID_EVENT_TYPES

def test_publication_date_provenance():
    """
    User Requirement:
    Verify published_at is never equal to discovered_at or the fetch time.
    If the only date available is the fetch time (or within 60s of crawl time), store NULL.
    """
    now = datetime.now(timezone.utc)

    # 1. If publication date equals fetch time exactly, it MUST return None (NULL)
    sanitized_exact = sanitize_publication_date(now, fetch_time=now)
    assert sanitized_exact is None, "Expected None when pub_date == fetch_time"

    # 2. If publication date is within 60 seconds of fetch time (leaked HTTP Date header), return None
    near_time = now - timedelta(seconds=25)
    sanitized_near = sanitize_publication_date(near_time, fetch_time=now)
    assert sanitized_near is None, "Expected None when pub_date is within 60s of crawl time"

    # 3. If publication date is an authentic past date (e.g. 5 days ago), preserve it
    past_date = now - timedelta(days=5)
    sanitized_past = sanitize_publication_date(past_date, fetch_time=now)
    assert sanitized_past is not None
    assert sanitized_past == past_date

    # 4. If publication date is in the future (> 24 hours), return None
    future_date = now + timedelta(days=3)
    sanitized_future = sanitize_publication_date(future_date, fetch_time=now)
    assert sanitized_future is None, "Expected None for future publication date"

def test_event_type_taxonomy():
    """
    User Requirement:
    Restrict event_type to the agreed taxonomy:
    (regulatory_change, market_data, product_launch, pricing_change, partnership,
     hiring, funding_or_ma, customer_complaint, other)
    and require the source text to support the label.
    """
    expected_taxonomy = {
        "regulatory_change",
        "market_data",
        "product_launch",
        "pricing_change",
        "partnership",
        "hiring",
        "funding_or_ma",
        "customer_complaint",
        "other"
    }
    assert set(VALID_EVENT_TYPES) == expected_taxonomy

    # 1. product_launch: MUST NOT be applied unless text mentions launch/release/unveil
    assert validate_and_normalize_event_type("product_launch", "ApplyBoard launched a new counselor AI tool") == "product_launch"
    # Fallback to other if no launch keywords present in text
    assert validate_and_normalize_event_type("product_launch", "Students find universities and courses abroad") == "other"

    # 2. pricing_change: requires price/fee/tuition keywords
    assert validate_and_normalize_event_type("pricing_change", "Tuition fee increased by 10 percent") == "pricing_change"
    assert validate_and_normalize_event_type("pricing_change", "Our students love our platform") == "other"

    # 3. regulatory_change: requires visa/policy/ministry keywords
    assert validate_and_normalize_event_type("regulatory_change", "New student visa caps announced by minister") == "regulatory_change"

    # 4. invalid taxonomy labels are normalized to 'other'
    assert validate_and_normalize_event_type("unknown_label", "Some random text") == "other"
    assert validate_and_normalize_event_type("marketing_tagline", "Best university portal") == "other"
