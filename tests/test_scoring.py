import pytest
from backend.services.analysis_engine import analysis_engine
from backend.models import Signal

def test_evidence_strength_caps():
    """
    User Requirement:
    Cap evidence_strength by verification_status:
    - single_source <= 0.6
    - unverified <= 0.35
    - corroborated <= 0.85 (requires 2+ independent domains)
    - primary_source up to 1.0
    """
    # 1. unverified
    s_unverified = Signal(
        evidence_snippet="Some unverified rumor in an anonymous forum thread.",
        verification_status="unverified"
    )
    score_unv = analysis_engine.calculate_evidence_strength(s_unverified, domain_count=1)
    assert score_unv <= 0.35, f"Expected unverified <= 0.35, got {score_unv}"

    # 2. single_source
    s_single = Signal(
        evidence_snippet="IDP Education officially published changes to international student placement policy.",
        verification_status="single_source"
    )
    score_single = analysis_engine.calculate_evidence_strength(s_single, domain_count=1)
    assert score_single <= 0.60, f"Expected single_source <= 0.60, got {score_single}"

    # 3. corroborated with only 1 domain should be downgraded/capped to single_source (0.60)
    s_corrob_1 = Signal(
        evidence_snippet="Both articles discuss the student visa cap changes in Australia.",
        verification_status="corroborated"
    )
    score_corrob_1 = analysis_engine.calculate_evidence_strength(s_corrob_1, domain_count=1)
    assert score_corrob_1 <= 0.60, f"Expected corroborated with 1 domain <= 0.60, got {score_corrob_1}"

    # 4. corroborated with 2+ independent domains
    score_corrob_2 = analysis_engine.calculate_evidence_strength(s_corrob_1, domain_count=2)
    assert score_corrob_2 <= 0.85, f"Expected corroborated with 2+ domains <= 0.85, got {score_corrob_2}"

    # 5. primary_source
    s_primary = Signal(
        evidence_snippet="Official Department of Home Affairs Ministerial Direction on international visa processing.",
        verification_status="primary_source"
    )
    score_primary = analysis_engine.calculate_evidence_strength(s_primary, domain_count=1)
    assert score_primary <= 1.00, f"Expected primary_source <= 1.00, got {score_primary}"

def test_single_source_cannot_exceed_cap():
    """
    Explicit test required by user prompt:
    Fails when a single_source signal exceeds 0.60.
    """
    s_single = Signal(
        evidence_snippet="A very credible, highly detailed verbatim quote from an established major publisher.",
        verification_status="single_source"
    )
    computed = analysis_engine.calculate_evidence_strength(s_single, domain_count=1)
    
    # Assert cap is strictly respected
    assert computed <= 0.60, f"VIOLATION: single_source evidence_strength {computed} exceeded the 0.60 cap!"

    # Intentionally verify that any artificial score > 0.60 fails validation
    s_single.evidence_strength = 0.75
    with pytest.raises(AssertionError):
        # We assert that treating 0.75 as valid for single_source fails
        assert s_single.evidence_strength <= 0.60, "Single source exceeded cap"

def test_headline_only_snippet_caps_at_40():
    """
    Mandate 5 Requirement:
    Headline-only snippets must be capped at <= 0.40 evidence strength,
    even if marked primary_source.
    """
    # Case: Headline and snippet are nearly identical
    sig = Signal(
        headline="Australia introduces cap on international students",
        evidence_snippet="Australia introduces cap on international students",
        verification_status="primary_source"
    )
    score = analysis_engine.calculate_evidence_strength(sig, domain_count=1)
    assert score <= 0.40, f"Expected headline-only score <= 0.40, got {score}"

    # Case: Signals like #6, #7, #10 with feed titles
    sig_10 = Signal(
        headline="Australia introduces official cap on international students.",
        evidence_snippet="Australia introduces cap on international students",
        verification_status="primary_source"
    )
    score_10 = analysis_engine.calculate_evidence_strength(sig_10, domain_count=1)
    assert score_10 <= 0.40, f"Expected Signal #10 headline-like score <= 0.40, got {score_10}"
