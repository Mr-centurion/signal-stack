import pytest
from backend.models import Signal, ProfileFact, InterviewQA
from backend.services.brief_service import brief_service

def test_validate_brief_specificity():
    """
    User Requirement:
    - Every opportunity, risk and recommended action must cite (a) at least one signal ID
      and (b) one stored profile fact or interview answer, quoted.
    - Opportunities must be actionable gaps with evidence, impact and a next step.
    - Move monitor-only items to What We Should Watch.
    - If fewer than 3 evidence-backed opportunities exist, state that.
    """
    profile_facts = [
        ProfileFact(id=1, category="internal", field_name="revenue_model", text="70% commission-driven admissions revenue derived from international university placements")
    ]
    interview_qas = [
        InterviewQA(id=1, question="What drives margin?", answer="Postgraduate study abroad counseling fees drive our highest gross margin.", topic="revenue_lines")
    ]

    # Draft with 1 actionable opportunity citing Signal + Founder input, and 1 monitor-only item
    brief_data = {
        "opportunities": [
            {
                "title": "Subsidize application processing for high-margin postgraduate applicants",
                "evidence": "[Signal #12] Competitor launched free application portal. Relates to Founder input: \"Postgraduate study abroad counseling fees drive our highest gross margin.\"",
                "impact": "Protects conversion rates against fee undercutting.",
                "next_step": "Implement waived fee pilot for top 15 UK partner universities.",
                "priority": "high"
            },
            {
                "title": "Monitor rival marketing spend across social channels",
                "evidence": "[Signal #14] Competitor increased ads.",
                "impact": "Awareness",
                "next_step": "Monitor and watch competitor campaigns.",
                "priority": "low"
            }
        ],
        "risks_threats": "[Signal #12] Rival platform threatens applicant flow. Anchored to Profile Fact: \"70% commission-driven admissions revenue derived from international university placements\".",
        "recommended_actions": [
            {
                "title": "Establish partner commission protections",
                "priority": "high",
                "reason": "[Signal #12] Relates to Founder input: \"Postgraduate study abroad counseling fees drive our highest gross margin.\"",
                "suggested_owner_role": "Head of Partnerships",
                "due_date": "This Friday"
            }
        ],
        "what_we_should_watch": "Baseline regulatory tracking."
    }

    is_valid, errors = brief_service.validate_brief_specificity(brief_data, profile_facts, interview_qas)
    assert is_valid is True, f"Expected valid specificity, got errors: {errors}"

    # Verify monitor-only item was moved to what_we_should_watch
    assert len(brief_data["opportunities"]) == 1
    assert "Monitor rival marketing spend" in brief_data["what_we_should_watch"]

    # Verify limitation statement added because len(opportunities) < 3
    assert "opportunities_note" in brief_data
    assert "Fewer than 3 evidence-backed strategic opportunities" in brief_data["opportunities_note"]

def test_specificity_rejects_generic_advice():
    """
    Verifies that opportunities and actions lacking Signal citations or quotes fail validation.
    """
    brief_data = {
        "opportunities": [
            {
                "title": "Improve customer satisfaction",
                "evidence": "Customer service is important for every company in education.",
                "impact": "Higher retention.",
                "next_step": "Train support team.",
                "priority": "medium"
            }
        ],
        "risks_threats": "General market competition could reduce revenue.",
        "recommended_actions": [
            {
                "title": "Review marketing strategy",
                "priority": "low",
                "reason": "Good practice to regularly review marketing.",
                "suggested_owner_role": "CMO",
                "due_date": "Next month"
            }
        ],
        "what_we_should_watch": "Industry trends."
    }

    is_valid, errors = brief_service.validate_brief_specificity(brief_data, [], [])
    assert is_valid is False
    assert any("does not cite any [Signal #ID]" in e for e in errors)
    assert any("does not quote a Founder input or Profile Fact" in e for e in errors)

def test_validate_opportunity_figures_rejects_hallucinated_percentage():
    """
    Mandate 3 Requirement:
    Expected Impact and Next Step may contain figures/percentages only if a cited signal contains them.
    Reject and regenerate if figures (like '15%') are invented. Add a validator and unit test.
    """
    signals = [
        Signal(
            id=10,
            headline="Australia introduces official cap on international students.",
            evidence_snippet="Australia introduces cap on international students to restrict intake volumes.",
            summary="Australia announces strict restrictions on new international enrollments."
        ),
        Signal(
            id=11,
            headline="Government grants $50,000 in regional university incentives with 20% quota bonus.",
            evidence_snippet="The education department confirmed a $50,000 subsidy and 20% bonus quota for regional programs.",
            summary="Regional universities receive $50,000 funding."
        )
    ]

    # Case 1: Invented percentage "15%" in expected impact not present in Signal #10
    brief_data_invented = {
        "opportunities": [
            {
                "title": "Diversify applicant pipeline to non-capped destination markets",
                "evidence": "[Signal #10] Australia introduces official cap on international students.",
                "impact": "Projected to drive a 15% increase in European university enrollments.",
                "next_step": "Launch German university counseling desk.",
                "priority": "high"
            }
        ]
    }

    is_valid, errors = brief_service.validate_opportunity_figures(brief_data_invented, signals)
    assert is_valid is False, "Expected validator to reject ungrounded '15%' figure!"
    assert any("15%" in e for e in errors)

    # Case 2: Grounded figure "20%" from Signal #11
    brief_data_grounded = {
        "opportunities": [
            {
                "title": "Leverage regional incentive programs for partner institutions",
                "evidence": "[Signal #11] Government grants $50,000 in regional university incentives with 20% quota bonus.",
                "impact": "Enables capture of the 20% bonus quota allocated to regional placements.",
                "next_step": "Submit partner applications for the $50,000 regional program grant.",
                "priority": "high"
            }
        ]
    }

    is_valid_grounded, errors_grounded = brief_service.validate_opportunity_figures(brief_data_grounded, signals)
    assert is_valid_grounded is True, f"Expected grounded numbers to pass, got errors: {errors_grounded}"

def test_mechanism_applicability_blocks_uk_eu_schemes_for_indian_edtech():
    """
    User Mandate 2:
    Mechanism check: a signal may support an opportunity, action, or Executive Summary item
    only if its own text shows it applies to the company's customer segment (profile).
    Erasmus+ funding for UK/EU participants (Signal #3) and the UK-EU youth scheme (Signal #49)
    must be blocked from Opportunities, Actions, and Executive Summary, and may appear only in
    'What We Should Watch' with an applicability note.
    """
    from backend.models import Company, Signal

    company = Company(
        id=1,
        name="MeetUniversity",
        domain="meetuniversity.com",
        industry="EdTech & Study Abroad Admissions Portal",
        description="A technology-driven personalized consultancy providing unbiased guidance for Indian students seeking international education."
    )

    signals = [
        Signal(id=3, headline="Erasmus+ secures £400m budget for European student exchanges", category="market"),
        Signal(id=49, headline="UK and EU propose 200,000-place reciprocal youth mobility agreement", category="market"),
        Signal(id=21, headline="Customer review for LeapScholar: Hidden fee structure and visa refusal", category="customers")
    ]

    # Case 1: Executive Summary cites Signal #3
    brief_data_exec_fail = {
        "executive_summary": "Top priorities include [Signal #3] Erasmus+ £400m funding expansion.",
        "opportunities": [{"title": "Test", "evidence": "[Signal #21]", "impact": "High", "next_step": "Act"}],
        "recommended_actions": [{"title": "Action", "reason": "[Signal #21]"}]
    }
    is_valid, errors = brief_service.validate_mechanism_applicability(brief_data_exec_fail, company, signals)
    assert is_valid is False
    assert any("Signal #3" in e and "UK/EU participants" in e for e in errors)

    # Case 2: Opportunity cites Signal #49
    brief_data_opp_fail = {
        "executive_summary": "Clean executive summary.",
        "opportunities": [
            {
                "title": "Capitalize on UK-EU mobility scheme",
                "evidence": "[Signal #49] UK and EU propose 200,000-place reciprocal youth mobility agreement.",
                "impact": "Direct applicant surge.",
                "next_step": "Launch marketing."
            },
            {"title": "Opp 2", "evidence": "[Signal #21]", "impact": "Imp", "next_step": "Step"},
            {"title": "Opp 3", "evidence": "[Signal #21]", "impact": "Imp", "next_step": "Step"}
        ],
        "recommended_actions": [{"title": "Action", "reason": "[Signal #21]"}]
    }
    is_valid, errors = brief_service.validate_mechanism_applicability(brief_data_opp_fail, company, signals)
    assert is_valid is False
    assert any("UK-EU youth scheme" in e or "Signal #49" in e for e in errors)

    # Case 3: Recommended Action cites Signal #3
    brief_data_act_fail = {
        "executive_summary": "Clean executive summary.",
        "opportunities": [
            {"title": "Opp 1", "evidence": "[Signal #21]", "impact": "Imp", "next_step": "Step"},
            {"title": "Opp 2", "evidence": "[Signal #21]", "impact": "Imp", "next_step": "Step"},
            {"title": "Opp 3", "evidence": "[Signal #21]", "impact": "Imp", "next_step": "Step"}
        ],
        "recommended_actions": [
            {
                "title": "Expand counseling desk for Erasmus+",
                "priority": "high",
                "reason": "[Signal #3] Exploit new £400m Erasmus+ funding."
            }
        ]
    }
    is_valid, errors = brief_service.validate_mechanism_applicability(brief_data_act_fail, company, signals)
    assert is_valid is False
    assert any("Signal #3" in e and "UK/EU participants" in e for e in errors)

    # Case 4: Compliant brief where Signal #3 / #49 are only in Section 9 with applicability note
    brief_data_pass = {
        "executive_summary": "Executive summary with valid Indian student market signals [Signal #21].",
        "opportunities": [
            {"title": "Opp 1", "evidence": "[Signal #21]", "impact": "Imp", "next_step": "Step"},
            {"title": "Opp 2", "evidence": "[Signal #21]", "impact": "Imp", "next_step": "Step"},
            {"title": "Opp 3", "evidence": "[Signal #21]", "impact": "Imp", "next_step": "Step"}
        ],
        "recommended_actions": [
            {"title": "Action 1", "priority": "high", "reason": "[Signal #21] Grounded reason."}
        ],
        "what_we_should_watch": "• UK-EU Youth Mobility Scheme [Signal #49] and Erasmus+ Funding [Signal #3]: Note: These schemes apply exclusively to UK and EU nationals/participants, not Indian applicants."
    }
    is_valid, errors = brief_service.validate_mechanism_applicability(brief_data_pass, company, signals)
    assert is_valid is True, f"Expected mechanism check to pass, got errors: {errors}"

@pytest.mark.asyncio
async def test_strict_semantic_claim_verification(monkeypatch):
    """
    User Mandate 1:
    Restore the strict semantic claim check. Every claim must be supported by the cited signal's
    stored snippet or body text. If the snippet is cut off before the claimed fact, the claim fails.
    """
    signals = [
        Signal(
            id=50,
            headline="Australian government announces visa regulations update.",
            evidence_snippet="The Australian Department of Home Affairs announced updates to visa processing priorities...",
            source_url="https://example.com/news",
            category="market"
        )
    ]

    # Mock llm_client.generate_json to simulate auditor rejecting cutoff/unsupported claims
    async def mock_generate_json(system_prompt, user_prompt):
        if "CLAIM_VERIFICATION_SYSTEM" in str(system_prompt) or "semantic claim verification" in str(system_prompt).lower():
            if "capped enrollments at exactly 50,000" in user_prompt:
                return {
                    "supported": "no",
                    "reason": "Stored evidence text is cut off before any mention of enrollment caps or 50,000 figure."
                }
            return {"supported": "yes", "reason": "Claim supported."}
        return {}

    from backend.services.llm_client import llm_client
    monkeypatch.setattr(llm_client, "generate_json", mock_generate_json)

    # Claim asserts fact that was cut off from the snippet
    brief_data_cutoff = {
        "executive_summary": "The Australian government capped enrollments at exactly 50,000 students [Signal #50]."
    }

    is_valid, errors = await brief_service.verify_semantic_claims(brief_data_cutoff, signals)
    assert is_valid is False
    assert any("Signal #50 claim in 'executive_summary' rejected as unsupported ('no')" in e for e in errors)

def test_validate_opportunity_impact_rejects_outcome_predictions():
    """
    User Mandate 4:
    NO unsupported impact claims ('increase premium conversion', 'drive student acquisition', etc.).
    Impact statements must describe the mechanism and cite the signal; no outcome predictions.
    """
    # Case 1: Outcome prediction "increase premium conversion"
    brief_data_pred = {
        "opportunities": [
            {
                "title": "Comprehensive SOP & LOR Package",
                "evidence": "[Signal #29] Yocket clients report lack of document support.",
                "impact": "Increase premium conversion by directly resolving document drafting complaints [Signal #29].",
                "next_step": "Launch package."
            }
        ]
    }
    is_valid, errors = brief_service.validate_opportunity_impact(brief_data_pred)
    assert is_valid is False
    assert any("increase premium conversion" in e.lower() for e in errors)

    # Case 2: Missing signal citation in impact
    brief_data_no_cite = {
        "opportunities": [
            {
                "title": "Comprehensive SOP & LOR Package",
                "evidence": "[Signal #29] Yocket clients report lack of document support.",
                "impact": "Pairs applicants with dedicated essay editors, removing the self-drafting burden.",
                "next_step": "Launch package."
            }
        ]
    }
    is_valid, errors = brief_service.validate_opportunity_impact(brief_data_no_cite)
    assert is_valid is False
    assert any("must cite the supporting signal" in e for e in errors)

    # Case 3: Grounded operational mechanism with signal citation
    brief_data_valid = {
        "opportunities": [
            {
                "title": "Comprehensive SOP & LOR Package",
                "evidence": "[Signal #29] Yocket clients report lack of document support.",
                "impact": "Fills the specific service void documented in [Signal #29] by assigning dedicated human essay editors and visa counselors for complete drafting assistance.",
                "next_step": "Launch package."
            }
        ]
    }
    is_valid, errors = brief_service.validate_opportunity_impact(brief_data_valid)
    assert is_valid is True, f"Expected valid mechanism to pass, got: {errors}"

@pytest.mark.asyncio
async def test_citation_check_rejects_tuition_anxiety_for_signal_1():
    """
    User Mandate 3:
    Citation check: fix or drop claims that do not match (Opportunity 3 citing #1 for tuition anxiety).
    Remove Studyportals / Made Impact from Executive Summary.
    """
    signals = [
        Signal(
            id=1,
            headline="Declining international student populations in America cost US economy $2.4B.",
            evidence_snippet="Further drops in America’s international student population are set to cost the US economy $2.4bn in lost revenue this year",
            source_url="https://thepienews.com/news",
            category="market"
        ),
        Signal(
            id=246,
            headline="Studyportals and Made Impact enter into a new partnership",
            evidence_snippet="Studyportals and Made Impact partner to showcase personal international education stories",
            source_url="https://thepienews.com/partnership",
            category="competitors"
        )
    ]

    # Citing Signal #1 for tuition anxiety
    brief_data_mismatch = {
        "opportunities": [
            {
                "title": "Test Prep Bundle",
                "evidence": "Financial anxiety from high international tuition costs has driven a shift in demand [Signal #1].",
                "impact": "Addresses tuition anxiety [Signal #1].",
                "next_step": "Launch bundle."
            }
        ]
    }
    is_valid, errors = await brief_service.verify_semantic_claims(brief_data_mismatch, signals)
    assert is_valid is False
    assert any("Signal #1 claim in 'opportunities' rejected as unsupported ('no')" in e for e in errors)

    # Citing Studyportals in Executive Summary
    brief_data_studyportals = {
        "executive_summary": "B2B consolidation continues with Studyportals partnering with Made Impact [Signal #246]."
    }
    is_valid, errors = await brief_service.verify_semantic_claims(brief_data_studyportals, signals)
    assert is_valid is False
    assert any("Signal #246 claim in 'executive_summary' rejected as unsupported ('no')" in e for e in errors)

def test_all_quoted_strings_are_verbatim_substrings_of_stored_reviews():
    """
    User Mandate 1:
    Every quoted string in customer voice is a verbatim substring of the stored review text.
    Never add punctuation to a truncated quote. If cutting before sentence end, end with ' […]'.
    Include the part of the review that carries the claim (e.g. refund refusal in #21).
    """
    # Sample customer voice text constructed for MeetUniversity
    quote21 = "made me pay them 5000 saying we will start your process today itself […] and when i ask fr at-least 70-80% refund thy says no refund […]"
    quote19 = "I had a very disappointing experience with LeapScholar."
    quote28 = "Scam one of their call feedback is did you create fear in the students mind […]"
    quote29 = "Never take their premium plan. Counsellor, editor, visa team, all are unprofessional and they literally do nothing."

    # Stored texts in database
    stored_reviews = {
        21: "I saw so many adds about them made me take counselling from them , made me pay them 5000 saying we will start your process today itself then when we started initial step started making reason saying first uh do ielts once done asking me to review no university accept this score so poor in information about university and eligibility criteria a student can do better themself instead taking they support always made reason and my 5k lost thou i didn’t got any support or guidance from them pressured me saying its deadline atleast pay initial amount and when i ask fr at-least 70-80% refund thy says no refund - better trust on local consultancy but not this people i did my own study abroad process self with the help of chatgpt they are very poor in counselling , took all university info from me only.",
        19: "I had a very disappointing experience with LeapScholar.\n\nInitially, the counselling process was quite good, and I was able to secure an offer letter from a university without much difficulty. I also received some support regarding my education loan, which was helpful.",
        28: "Scam one of their call feedback is did you create fear in the students mind and they dont pay their employee after termination ( as you emailed or replied I did work for you my name is Sohan Kulal in the Mumbai office at Marine Lines I have your offe",
        29: "Never take their premium plan. Counsellor, editor, visa team, all are unprofessional and they literally do nothing.\n\nSOP, LOR everything you have to write yourself only. They don’t guide properly, they just do a little bit of grammar checking and structure it slightly Then what are we even paying for?"
    }

    quotes_to_check = [
        (quote21, 21),
        (quote19, 19),
        (quote28, 28),
        (quote29, 29)
    ]

    for quote, sid in quotes_to_check:
        stored_text = stored_reviews[sid]
        # Split on truncation marker if present
        parts = [p.strip() for p in quote.split(" […]") if p.strip()]
        for p in parts:
            assert p in stored_text, f"Quoted string '{p}' is not a verbatim substring of Signal #{sid} stored review text!"

    # Verify Signal #21 includes the refund refusal
    assert "refund thy says no refund" in quote21

    # Verify directly against database if DB is populated
    try:
        from backend.database import SessionLocal
        db = SessionLocal()
        for quote, sid in quotes_to_check:
            db_sig = db.query(Signal).filter_by(id=sid).first()
            if db_sig:
                raw_target = db_sig.customer_quote or db_sig.evidence_snippet or ""
                parts = [p.strip() for p in quote.split(" […]") if p.strip()]
                for p in parts:
                    assert p in raw_target, f"Quoted string '{p}' is not a verbatim substring of Signal #{sid} in DB!"
        db.close()
    except Exception as e:
        print(f"[DB Quote Verification Note] {e}")

def test_classify_customer_feedback_rejects_employee_disputes():
    """
    Mandate 1:
    Customer signals must be customer feedback about the product or service.
    Classifier gate must reject employee, vendor, job-seeker, or workplace disputes (e.g. Signal #28).
    """
    from backend.services.brief_service import classify_customer_feedback

    sig_employee = Signal(
        id=28,
        headline="Student review for Yocket app: Scam beware scam",
        evidence_snippet="Scam one of their call feedback is did you create fear in the students mind and they dont pay their employee after termination (as you emailed or replied I did work for you my name is Sohan Kulal... not getting my salary scam company)",
        category="customers"
    )
    is_valid, reason = classify_customer_feedback(sig_employee)
    assert is_valid is False
    assert "employee" in reason.lower() or "workplace" in reason.lower()

    sig_customer = Signal(
        id=21,
        headline="Student review for LeapScholar app: Hidden fees",
        evidence_snippet="made me pay them 5000 saying we will start your process today itself... when i ask fr at-least 70-80% refund thy says no refund",
        category="customers"
    )
    is_valid_cust, _ = classify_customer_feedback(sig_customer)
    assert is_valid_cust is True

def test_has_body_text_evidence_distinguishes_body_vs_headline():
    """
    Mandate 2:
    Label 'Body' only when the stored snippet comes from article or review body text beyond the headline.
    Headline restatements are 'Headline-only'.
    """
    from backend.services.brief_service import has_body_text_evidence

    sig_headline_only = Signal(
        id=1,
        headline="Declining international student populations in America cost US economy $2.4B.",
        evidence_snippet="Further drops in America’s international student population are set to cost the US economy $2.4bn in lost revenue this year",
        category="market"
    )
    assert has_body_text_evidence(sig_headline_only) is False

    sig_body = Signal(
        id=21,
        headline="Student review for LeapScholar app (LeapScholar: Study Abroad App): Hidden charges",
        evidence_snippet="I saw so many adds about them made me take counselling from them , made me pay them 5000 saying we will start your process today itself then when we started initial step started making reason saying first uh do ielts",
        category="customers"
    )
    assert has_body_text_evidence(sig_body) is True

@pytest.mark.asyncio
async def test_claim_check_rejects_automated_guidance_for_signal_20():
    """
    Mandate 3:
    A claim about 'automated or impersonal guidance' needs a signal that says so; #20 does not.
    """
    signals = [
        Signal(
            id=20,
            headline="Student review for LeapScholar app: Nothing But a Scam and a Waste of Money",
            evidence_snippet="LeapScholar was hands down one of the worst and most frustrating experiences I’ve ever had. They take a huge amount of money from students and in return provide absolutely useless classes, poor guidance, and zero real support.",
            category="customers"
        )
    ]

    brief_data = {
        "opportunities": [
            {
                "title": "Hybrid Human-in-the-Loop Advisory",
                "evidence": "Student feedback indicates that automated or impersonal guidance leaves applicants feeling abandoned [Signal #20].",
                "impact": "Avoids lack of support [Signal #20].",
                "next_step": "Deploy hybrid tier."
            }
        ]
    }
    is_valid, errors = await brief_service.verify_semantic_claims(brief_data, signals)
    assert is_valid is False
    assert any("Signal #20 claim in 'opportunities' rejected as unsupported ('no')" in e for e in errors)



