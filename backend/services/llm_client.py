import json
import time
import re
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Type, TypeVar
import httpx
from pydantic import BaseModel
from backend.config import settings

T = TypeVar("T", bound=BaseModel)

class LLMResponseError(Exception):
    """Raised when LLM fails to return valid output after retries."""
    pass

class LLMRateLimitError(Exception):
    """Raised when LLM provider encounters rate limiting (429)."""
    pass

class BaseLLMProvider:
    async def generate_json(self, system_prompt: str, user_prompt: str, schema_class: Optional[Type[T]] = None) -> Dict[str, Any]:
        raise NotImplementedError

class MockProvider(BaseLLMProvider):
    """
    Deterministic mock provider for testing, smoke tests, and offline development.
    GUARD ENFORCED: All output produced in mock mode is explicitly labeled "[TEST MODE]"
    so it is never stored or presented as real verified production data.
    """
    async def generate_json(self, system_prompt: str, user_prompt: str, schema_class: Optional[Type[T]] = None) -> Dict[str, Any]:
        await asyncio.sleep(0.01) # Simulated network latency
        
        prompt_lower = (system_prompt + " " + user_prompt).lower()

        # Handle Structured Research Profile Extraction
        if "structured intelligence profile" in prompt_lower or "business_lines" in prompt_lower:
            is_meetuni = "meetuniversity" in prompt_lower
            if is_meetuni:
                data = {
                    "is_test_mode": True,
                    "business_lines": [
                        {"text": "[TEST MODE] International Higher Education Admissions & Guidance", "status": "verified", "source_url": "https://www.meetuniversity.com", "evidence_snippet": "Find universities, colleges and courses abroad"},
                        {"text": "[TEST MODE] University Lead Generation & Student Recruitment", "status": "verified", "source_url": "https://www.meetuniversity.com", "evidence_snippet": "MeetUniversity connects students with overseas institutions"}
                    ],
                    "products_services": [
                        {"text": "[TEST MODE] University Search & Course Discovery Engine", "status": "verified", "source_url": "https://www.meetuniversity.com", "evidence_snippet": "Find universities, colleges and courses abroad"},
                        {"text": "[TEST MODE] Student Counseling & Visa Guidance", "status": "assumption", "source_url": "https://www.meetuniversity.com", "evidence_snippet": ""}
                    ],
                    "customer_segments": [
                        {"text": "[TEST MODE] Prospective Undergraduate and Postgraduate Study Abroad Applicants", "status": "verified", "source_url": "https://www.meetuniversity.com", "evidence_snippet": "Find universities, colleges and courses abroad"},
                        {"text": "[TEST MODE] Global Universities Seeking Indian and South Asian Applicants", "status": "assumption", "source_url": "https://www.meetuniversity.com", "evidence_snippet": ""}
                    ],
                    "positioning": {"text": "[TEST MODE] AI-enabled discovery and admissions platform linking international universities with aspiring overseas students.", "status": "verified", "source_url": "https://www.meetuniversity.com", "evidence_snippet": "Find universities, colleges and courses abroad"},
                    "geography": {"text": "[TEST MODE] Primary applicant base in India/South Asia; target institutions in US, UK, Canada, Australia, and Europe.", "status": "assumption", "source_url": "https://www.meetuniversity.com", "evidence_snippet": ""},
                    "revenue_model": {"text": "[TEST MODE] University recruitment commissions, student premium counseling, and institutional marketing subscriptions.", "status": "assumption", "source_url": "https://www.meetuniversity.com", "evidence_snippet": ""},
                    "likely_competitors": [
                        {"name": "[TEST MODE] Leverage Edu", "rationale": "High-growth Indian study abroad counseling and admissions platform", "status": "assumption"},
                        {"name": "[TEST MODE] Leap Scholar", "rationale": "End-to-end global education test prep and admissions provider", "status": "assumption"},
                        {"name": "[TEST MODE] Yocket", "rationale": "Community-driven study abroad admission guidance platform", "status": "assumption"},
                        {"name": "[TEST MODE] Shiksha Study Abroad", "rationale": "Legacy college search and university aggregation portal", "status": "assumption"}
                    ]
                }
            else:
                data = {
                    "is_test_mode": True,
                    "business_lines": [
                        {"text": "[TEST MODE] Enterprise Developer Tools & Backend Cloud Infrastructure", "status": "verified", "source_url": "https://example.com", "evidence_snippet": "Cloud infrastructure for modern engineering teams"},
                        {"text": "[TEST MODE] Managed Database & Storage Services", "status": "assumption", "source_url": "https://example.com", "evidence_snippet": ""}
                    ],
                    "products_services": [
                        {"text": "[TEST MODE] High-throughput API gateway & realtime database engine", "status": "verified", "source_url": "https://example.com", "evidence_snippet": "Cloud infrastructure for modern engineering teams"}
                    ],
                    "customer_segments": [
                        {"text": "[TEST MODE] Mid-market SaaS CTOs and Staff Platform Engineers", "status": "assumption", "source_url": "https://example.com", "evidence_snippet": ""}
                    ],
                    "positioning": {"text": "[TEST MODE] Zero-ops backend infrastructure platform for cloud-native engineering organizations.", "status": "verified", "source_url": "https://example.com", "evidence_snippet": "Cloud infrastructure for modern engineering teams"},
                    "geography": {"text": "[TEST MODE] Global, predominantly North America and EMEA.", "status": "assumption", "source_url": "https://example.com", "evidence_snippet": ""},
                    "revenue_model": {"text": "[TEST MODE] Usage-based monthly compute and enterprise team seat tiers.", "status": "assumption", "source_url": "https://example.com", "evidence_snippet": ""},
                    "likely_competitors": [
                        {"name": "[TEST MODE] PlanetScale", "rationale": "Managed database platform", "status": "assumption"},
                        {"name": "[TEST MODE] Neon", "rationale": "Serverless Postgres platform", "status": "assumption"}
                    ]
                }
        # Handle Vagueness Judge
        elif "assess if the answer is vague" in prompt_lower or "vagueness" in prompt_lower or "user answer" in prompt_lower:
            data = {
                "is_vague": True,
                "reason": "[TEST MODE] User response is brief and lacks concrete figures or milestones.",
                "followup_question": "[TEST MODE] You mentioned your answer—could you elaborate with a specific metric or breakdown regarding that?"
            }
        # Handle Batch Discovery Questions (plural)
        elif "questions" in prompt_lower or "probing discovery interview" in prompt_lower:
            data = {
                "questions": [
                    {
                        "category": "customers",
                        "question": "[TEST MODE] What is the primary operational friction or bottleneck your customers complain about most often?",
                        "rationale": "Identifies customer churn risks and unmet feature demands."
                    },
                    {
                        "category": "competitors",
                        "question": "[TEST MODE] Which emerging competitor or indirect alternative are you hearing about most in lost sales deals?",
                        "rationale": "Surfaces competitive positioning and market displacement threats."
                    },
                    {
                        "category": "market",
                        "question": "[TEST MODE] What regulatory or platform changes in your industry over the next 6 months concern you most?",
                        "rationale": "Flags macroeconomic and compliance head winds."
                    },
                    {
                        "category": "internal",
                        "question": "[TEST MODE] What is the single most critical strategic milestone your team must hit this quarter?",
                        "rationale": "Anchors internal alignment against real external developments."
                    }
                ]
            }
        # Handle Adaptive Interview Question (single)
        elif "elite management consultant" in prompt_lower or "interview question" in prompt_lower:

            topic = "revenue_lines"
            for t in ["revenue_lines", "top_customer_segments", "customer_problems", "why_customers_choose_us", "competitors_substitutes", "market_shifts", "material_developments", "priorities_6_12_months", "internal_data", "decisions_to_support"]:
                if t in prompt_lower:
                    topic = t
                    break

            is_meetuni = "meetuniversity" in prompt_lower
            if is_meetuni:
                topic_questions = {
                    "revenue_lines": "[TEST MODE] Beyond university admissions commissions, how does MeetUniversity monetize student counseling and institutional partnerships?",
                    "top_customer_segments": "[TEST MODE] Between postgraduate STEM applicants and undergraduate applicants, which student segment generates your highest gross margin at MeetUniversity?",
                    "customer_problems": "[TEST MODE] What is the biggest friction point prospective study-abroad applicants encounter when navigating foreign university applications on MeetUniversity?",
                    "why_customers_choose_us": "[TEST MODE] When students compare MeetUniversity with counselors like Leverage Edu or IDP, what unique advantage secures their trust?",
                    "competitors_substitutes": "[TEST MODE] Which emerging digital platforms or local offline study-abroad agents are taking the most applicant share from MeetUniversity?",
                    "market_shifts": "[TEST MODE] How severely have recent student visa restrictions in the UK, Canada, and Australia impacted MeetUniversity's lead pipeline?",
                    "material_developments": "[TEST MODE] What was the most significant institutional partnership or product milestone MeetUniversity closed in the past 6 months?",
                    "priorities_6_12_months": "[TEST MODE] What are your top 2 expansion bets over the next 12 months—destination market expansion or test-prep integration?",
                    "internal_data": "[TEST MODE] What internal metric best indicates application conversion health at MeetUniversity (e.g., offer letter issuance rate or visa clearance)?",
                    "decisions_to_support": "[TEST MODE] What high-stakes commercial or university partnership decisions must this intelligence system inform for MeetUniversity's leadership?"
                }
            else:
                topic_questions = {
                    "revenue_lines": "[TEST MODE] What proportion of your revenue is driven by recurring enterprise contracts versus usage-based infrastructure consumption?",
                    "top_customer_segments": "[TEST MODE] What is the typical team size and stack maturity of the engineering organizations that adopt your platform fastest?",
                    "customer_problems": "[TEST MODE] What architectural bottleneck or cost overrun pushes engineering teams to replace their existing setup with your product?",
                    "why_customers_choose_us": "[TEST MODE] When engineering leads evaluate your solution against major cloud hyperscalers, what specific capability wins the contract?",
                    "competitors_substitutes": "[TEST MODE] Which open-source alternatives or commercial database providers are mentioned most frequently in your lost sales deals?",
                    "market_shifts": "[TEST MODE] How are recent cloud egress fee changes and data residency mandates impacting customer migration timelines?",
                    "material_developments": "[TEST MODE] What was the most critical architecture release or enterprise feature shipped by your team in the last two quarters?",
                    "priorities_6_12_months": "[TEST MODE] Over the next 6-12 months, is your primary focus multi-region replication or SOC2/FedRAMP enterprise compliance?",
                    "internal_data": "[TEST MODE] What telemetry or churn indicator gives you the earliest signal that an engineering team is disengaging?",
                    "decisions_to_support": "[TEST MODE] Which executive decisions—such as pricing tier redesign or channel partnerships—should this intelligence feed support?"
                }

            q_text = topic_questions.get(topic, f"[TEST MODE] How do you evaluate your strategic execution in {topic.replace('_', ' ')}?")
            data = {
                "question": q_text,
                "topic": topic,
                "category": "customers" if "customer" in topic else ("competitors" if "competitor" in topic else "internal"),
                "rationale": f"Probing {topic.replace('_', ' ')} based on company profile."
            }
        # Handle Follow-Up Question
        elif "follow-up question" in prompt_lower or "evasive answer" in prompt_lower:
            data = {
                "question": "[TEST MODE] Could you provide a concrete metric, estimated dollar amount, or recent customer example to clarify that point?",
                "rationale": "User's prior response was brief; requesting verifiable grounding."
            }
        # Handle Brief Generation
        elif "chief strategy officer" in prompt_lower or "monday morning executive brief" in prompt_lower or "brief" in prompt_lower:
            if "nothing" in prompt_lower or "no signals" in prompt_lower or "zero" in prompt_lower:
                data = {
                    "is_test_mode": True,
                    "week_label": "Week 47, 2026",
                    "nothing_happened_flag": True,
                    "executive_summary": "[TEST MODE] Zero material strategic signals or competitive developments were detected during this monitoring cycle. Core operations, competitor postures, and customer streams remained steady.",
                    "customer_signals": "No meaningful development detected this cycle.",
                    "competitor_intelligence": "No meaningful development detected this cycle.",
                    "market_intelligence": "No meaningful development detected this cycle.",
                    "internal_intelligence": "No internal data uploaded.",
                    "opportunities": [],
                    "risks_threats": "No material risks detected this cycle.",
                    "recommended_actions": [
                        {
                            "title": "[TEST MODE] Maintain routine baseline monitoring",
                            "priority": "low",
                            "reason": "Continue standard crawl cadence; no immediate strategic counter-measures required.",
                            "suggested_owner_role": "Leadership",
                            "due_date": "This Friday"
                        }
                    ],
                    "what_we_should_watch": "Maintain routine baseline monitoring.",
                    "source_appendix": []
                }
            else:
                data = {
                    "is_test_mode": True,
                    "week_label": "Week 47, 2026",
                    "nothing_happened_flag": False,
                    "executive_summary": "[TEST MODE] Evidence shows competitor pricing reductions [Signal #1]. Our interpretation indicates direct margin pressure.",
                    "customer_signals": "[TEST MODE] Applicant inquiries steady; slight delay in winter intake visa clearances [Signal #1].",
                    "competitor_intelligence": "[TEST MODE] Rival provider announced subscription price adjustments [Signal #1].",
                    "market_intelligence": "[TEST MODE] Overseas education regulatory updates published regarding post-study work permits [Signal #1].",
                    "internal_intelligence": "No internal data uploaded.",
                    "opportunities": [
                        {
                            "title": "[TEST MODE] Deploy subsidized university application pilot",
                            "evidence": "[Signal #1] Rival fee shifts. Relates to Founder input: \"Admissions commissions drive 70% of gross margin.\"",
                            "impact": "Mitigates applicant diversion to rival platforms.",
                            "next_step": "Deploy pilot for top 20 destination universities.",
                            "priority": "high"
                        }
                    ],
                    "risks_threats": "[TEST MODE] Rival subscription price reductions threaten margin [Signal #1]. Relates to Profile Fact: \"Core Revenue Line - Overseas Admissions Consulting\".",
                    "recommended_actions": [
                        {
                            "title": "[TEST MODE] Benchmark counseling fees against rival offering",
                            "priority": "high",
                            "reason": "[Signal #1] Competitor price reduction. Relates to Founder input: \"Commission-driven revenue model requires competitive pricing.\"",
                            "suggested_owner_role": "Head of Strategy",
                            "due_date": "This Friday"
                        }
                    ],
                    "what_we_should_watch": "[TEST MODE] Emerging alternative platforms and upcoming visa policy review dates.",
                    "source_appendix": [
                        {
                            "signal_id": 1,
                            "headline": "[TEST MODE] Competitor announces enterprise price reduction",
                            "publisher_url": "https://example.com/competitors/news.rss",
                            "published_date": "2026-11-20",
                            "snippet": "Effective today, subscription pricing is adjusted by 20 percent.",
                            "verification_status": "single_source",
                            "reliability_score": 0.85,
                            "evidence_score": 0.60
                        }
                    ]
                }
        elif "claim verification" in prompt_lower or "semantic claim" in prompt_lower or "supported: yes|partial|no" in prompt_lower:
            data = {
                "supported": "yes",
                "reason": "[TEST MODE] Claim is verified and supported by the source evidence snippet."
            }
        elif "strategic intelligence auditor" in prompt_lower or "reassessments" in prompt_lower or "contextreassessment" in prompt_lower:
            data = {
                "is_test_mode": True,
                "reassessments": [
                    {
                        "is_aligned": False,
                        "relevance_score": 0.45,
                        "reason": "[TEST MODE] Source targets domestic undergraduate admissions, misaligned with new international STEM graduate focus."
                    },
                    {
                        "is_aligned": True,
                        "relevance_score": 0.88,
                        "reason": "[TEST MODE] Source delivers active signals on international STEM graduate university partnerships."
                    },
                    {
                        "is_aligned": False,
                        "relevance_score": 0.35,
                        "reason": "[TEST MODE] Source covers legacy non-STEM programs, low utility under updated strategy."
                    },
                    {
                        "is_aligned": True,
                        "relevance_score": 0.92,
                        "reason": "[TEST MODE] Core regulatory tracking on international STEM student visas in US/Europe."
                    }
                ]
            }
        elif "senior competitive intelligence researcher" in prompt_lower or "search queries to discover" in prompt_lower:
            data = {
                "queries": [
                    "[TEST MODE] study abroad competitors alternatives",
                    "[TEST MODE] overseas education admissions platforms",
                    "[TEST MODE] student recruitment competitors",
                    "[TEST MODE] international student visa platforms"
                ]
            }
        elif "autonomous competitive intelligence specialist" in prompt_lower or "competitors or substitutes" in prompt_lower:
            data = {
                "competitors": [
                    {
                        "name": "[TEST MODE] Leverage Edu",
                        "url": "https://leverageedu.com",
                        "type": "direct",
                        "why_relevant": "[TEST MODE] Direct study abroad admissions and student counseling competitor.",
                        "evidence_url": "https://news.google.com",
                        "evidence_snippet": "[TEST MODE] Leverage Edu operates study abroad counseling."
                    },
                    {
                        "name": "[TEST MODE] Leap Scholar",
                        "url": "https://leapscholar.com",
                        "type": "direct",
                        "why_relevant": "[TEST MODE] Full-stack global education test prep and admissions provider.",
                        "evidence_url": "https://news.google.com",
                        "evidence_snippet": "[TEST MODE] Leap Scholar provides overseas study guidance."
                    },
                    {
                        "name": "[TEST MODE] Yocket",
                        "url": "https://yocket.com",
                        "type": "substitute",
                        "why_relevant": "[TEST MODE] Community-driven overseas student admission guidance platform.",
                        "evidence_url": "https://news.google.com",
                        "evidence_snippet": "[TEST MODE] Yocket community connects students applying abroad."
                    },
                    {
                        "name": "[TEST MODE] IDP Education",
                        "url": "https://idp.com",
                        "type": "direct",
                        "why_relevant": "[TEST MODE] Global international student placement service and IELTS co-owner.",
                        "evidence_url": "https://news.google.com",
                        "evidence_snippet": "[TEST MODE] IDP Education places students in overseas universities."
                    },
                    {
                        "name": "[TEST MODE] Edvoy",
                        "url": "https://edvoy.com",
                        "type": "direct",
                        "why_relevant": "[TEST MODE] Digital platform for university applications and counseling.",
                        "evidence_url": "https://news.google.com",
                        "evidence_snippet": "[TEST MODE] Edvoy simplifies university applications for international students."
                    }
                ]
            }
        elif "autonomous intelligence architect" in prompt_lower or "category_source_queries" in prompt_lower or "customers, competitors, market, and internal" in prompt_lower:
            data = {
                "customer_queries": ["student visa delays refusal complaints", "study abroad admission friction IELTS GRE"],
                "competitor_queries": ["study abroad counseling platforms funding launches", "international admissions platform pricing"],
                "market_queries": ["international student visa caps policy Australia Canada UK", "overseas education regulatory updates 2026"],
                "internal_queries": ["official platform updates", "strategic initiative announcements"]
            }
        elif "internal business data corpus" in prompt_lower or "recurring patterns across four distinct categories" in prompt_lower:
            data = {
                "objections": [
                    {
                        "pattern": "High upfront onboarding fee in emerging markets",
                        "count": 3,
                        "verbatim_quotes": [
                            "Prospect stated $5000 upfront fee exceeds institutional budget",
                            "Lost to local consultancy due to price sensitivity on onboarding fees",
                            "Customer declined subscription due to high per-student license cost"
                        ]
                    }
                ],
                "lost_deal_reasons": [
                    {
                        "pattern": "Lack of direct overseas university placement agreements",
                        "count": 2,
                        "verbatim_quotes": [
                            "Client chose competitor offering direct German university placement guarantee",
                            "Lost to local consultancy due to price sensitivity on onboarding fees"
                        ]
                    }
                ],
                "product_requests": [
                    {
                        "pattern": "Automated applicant document verification portal",
                        "count": 2,
                        "verbatim_quotes": [
                            "Applicant requested step-by-step document verification portal"
                        ]
                    }
                ],
                "sales_patterns": [
                    {
                        "pattern": "Rapid same-day response increases lead conversion",
                        "count": 2,
                        "verbatim_quotes": [
                            "Same-day outreach lead conversion rate reached 65% vs 25% delayed"
                        ]
                    }
                ]
            }
        elif "autonomous intelligence researcher" in prompt_lower or "external data sources to monitor" in prompt_lower:
            data = {
                "is_test_mode": True,
                "sources": [
                    {
                        "category": "customers",
                        "url": "https://example.com/customers/reviews.rss",
                        "reason": "[TEST MODE] Direct customer feedback stream for satisfaction tracking."
                    },
                    {
                        "category": "competitors",
                        "url": "https://example.com/competitors/news.rss",
                        "reason": "[TEST MODE] Monitors competitor pricing and feature press releases."
                    },
                    {
                        "category": "market",
                        "url": "https://example.com/industry/regulations.rss",
                        "reason": "[TEST MODE] Tracks compliance and industry standards."
                    }
                ]
            }
        elif "intelligence verification officer" in prompt_lower or "extract discrete strategic signals" in prompt_lower:
            data = {
                "is_test_mode": True,
                "signals": [
                    {
                        "category": "competitors",
                        "headline": "[TEST MODE] Competitor announces enterprise price reduction",
                        "summary": "[TEST MODE] Competitor reduced subscription pricing effective immediately.",
                        "evidence_snippet": "Effective today, subscription pricing is adjusted by 20 percent.",
                        "source_url": "https://example.com/competitors/news.rss",
                        "verified_flag": True,
                        "interpretation": "[TEST MODE] May increase pressure on sales negotiations.",
                        "source_reliability": 0.9,
                        "evidence_strength": 0.95,
                        "strategic_relevance": 0.85,
                        "impact": "high",
                        "urgency": "high"
                    }
                ]
            }
        elif "evaluating crawled content items" in prompt_lower or "classified_signals" in prompt_lower:
            data = {
                "is_test_mode": True,
                "classified_signals": [
                    {
                        "item_index": 0,
                        "is_relevant": True,
                        "is_discrete_event": True,
                        "event_reason": "[TEST MODE] Discrete service expansion event",
                        "category": "competitors",
                        "linked_competitor": "IDP Education",
                        "event_type": "product_launch",
                        "headline": "[TEST MODE] IDP Education expands advisory programs for international students",
                        "evidence_snippet": "counselling for students & parents",
                        "customer_quote": None,
                        "unmet_need": None
                    }
                ]
            }
        else:
            data = {"is_test_mode": True, "status": "ok", "message": "[TEST MODE] Mock response generated"}

        if schema_class:
            return schema_class.model_validate(data).model_dump()
        return data

class GroqProvider(BaseLLMProvider):
    """Groq Free-Tier API client with JSON Mode and backoff."""
    BASE_URL = "https://api.groq.com/openai/v1/chat/completions"
    FALLBACK_MODELS = [
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "qwen/qwen3.8-27b",
        "llama-3.3-70b-versatile"
    ]

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model or "openai/gpt-oss-120b"

    async def generate_json(self, system_prompt: str, user_prompt: str, schema_class: Optional[Type[T]] = None) -> Dict[str, Any]:
        if not self.api_key:
            raise ValueError("Groq API key is not configured.")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # Rotate models in case of model retirement (e.g. 404) or rate limit
        models_to_try = [self.model] + [m for m in self.FALLBACK_MODELS if m != self.model]

        async with httpx.AsyncClient(timeout=45.0) as client:
            last_err = None
            for model_name in models_to_try:
                payload = {
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": f"{system_prompt}\nCRITICAL: Respond ONLY with valid, raw json. Do not wrap in markdown quotes."},
                        {"role": "user", "content": user_prompt}
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.2
                }

                try:
                    response = await client.post(self.BASE_URL, headers=headers, json=payload)
                    if response.status_code == 429:
                        try:
                            retry_after = float(response.headers.get("retry-after", "8.0"))
                        except Exception:
                            retry_after = 8.0
                        sleep_s = max(8.0, retry_after)
                        print(f"[GROQ RATE LIMIT 429] Pacing {sleep_s:.1f}s backoff on model {model_name}...")
                        await asyncio.sleep(sleep_s)
                        last_err = LLMRateLimitError(f"Groq Rate limit hit on {model_name}. Retry-After: {retry_after}")
                        continue
                    if response.status_code == 404:
                        # Model not available in this tier/account, try next model
                        continue
                    response.raise_for_status()
                    
                    result = response.json()
                    raw_content = result["choices"][0]["message"]["content"]
                    match = re.search(r"(\{.*\}|\[.*\])", raw_content, re.DOTALL)
                    clean_text = match.group(1) if match else raw_content.strip()
                    clean_text = re.sub(r"^```(?:json)?\s*|\s*```$", "", clean_text.strip(), flags=re.MULTILINE)
                    clean_text = re.sub(r",\s*([\}\]])", r"\1", clean_text)
                    parsed = json.loads(clean_text)
                    self.last_model_used = model_name
                    if schema_class:
                        if isinstance(parsed, list):
                            field_names = list(schema_class.model_fields.keys())
                            first_field = field_names[0] if field_names else "items"
                            parsed = {first_field: parsed}
                        return schema_class.model_validate(parsed).model_dump()
                    return parsed
                except Exception as e:
                    last_err = e
                    continue

            if last_err:
                raise last_err
            raise LLMResponseError(f"Groq failed across all candidate models: {models_to_try}")

class GeminiProvider(BaseLLMProvider):
    """Google Gemini Free-Tier API client with JSON Mode and model rotation on quota."""
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
    FALLBACK_MODELS = [
        "gemini-flash-lite-latest",
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash",
        "gemini-3.6-flash",
        "gemini-3-flash-preview",
        "gemini-flash-latest"
    ]

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model.replace("models/", "") if model else "gemini-3.5-flash-lite"

    async def generate_json(self, system_prompt: str, user_prompt: str, schema_class: Optional[Type[T]] = None) -> Dict[str, Any]:
        if not self.api_key:
            raise ValueError("Gemini API key is not configured.")

        # Candidate models to try in case of single-model quota exhaustion
        models_to_try = [self.model] + [m for m in self.FALLBACK_MODELS if m != self.model]

        async with httpx.AsyncClient(timeout=35.0) as client:
            last_err = None
            for model_name in models_to_try:
                url = f"{self.BASE_URL}/{model_name}:generateContent?key={self.api_key}"
                payload = {
                    "contents": [
                        {
                            "parts": [
                                {"text": f"SYSTEM INSTRUCTION: {system_prompt}\nReturn strict JSON."},
                                {"text": user_prompt}
                            ]
                        }
                    ],
                    "generationConfig": {
                        "response_mime_type": "application/json",
                        "temperature": 0.2
                    }
                }

                for attempt in range(2):
                    try:
                        response = await client.post(url, json=payload)
                        if response.status_code in (429, 503):
                            resp_text = response.text.lower()
                            if "requests per day" in resp_text or "resource_exhausted" in resp_text or "limit: 20" in resp_text:
                                last_err = LLMRateLimitError(f"Gemini model {model_name} daily quota exhausted.")
                                break
                            await asyncio.sleep(2.0)
                            if attempt == 0:
                                continue
                            last_err = LLMRateLimitError(f"Gemini model {model_name} status {response.status_code}.")
                            break
                        
                        response.raise_for_status()
                        res_json = response.json()
                        candidates = res_json.get("candidates", [])
                        if not candidates:
                            continue
                        
                        raw_text = candidates[0]["content"]["parts"][0]["text"]
                        match = re.search(r"(\{.*\}|\[.*\])", raw_text, re.DOTALL)
                        clean_text = match.group(1) if match else raw_text.strip()
                        clean_text = re.sub(r"^```(?:json)?\s*|\s*```$", "", clean_text.strip(), flags=re.MULTILINE)
                        clean_text = re.sub(r",\s*([\}\]])", r"\1", clean_text)
                        parsed = json.loads(clean_text)
                        self.last_model_used = model_name
                        if schema_class:
                            if isinstance(parsed, list):
                                field_names = list(schema_class.model_fields.keys())
                                first_field = field_names[0] if field_names else "items"
                                parsed = {first_field: parsed}
                            return schema_class.model_validate(parsed).model_dump()
                        return parsed
                    except Exception as e:
                        print(f"[GEMINI CALL ERROR] {model_name}: {e}")
                        last_err = e
                        if attempt == 0:
                            await asyncio.sleep(1.0)
                            continue
                        break

            if last_err:
                raise last_err
            raise LLMResponseError("Gemini failed across all candidate models.")



class LLMClient:
    """
    Resilient provider-abstracted LLM client supporting Groq, Gemini, and Mock.
    Includes exponential backoff retries, rate-limit pauses, and structured output parsing.
    """
    def __init__(self, provider_name: Optional[str] = None):
        self.provider_name = provider_name or settings.DEFAULT_LLM_PROVIDER
        self.providers: Dict[str, BaseLLMProvider] = {
            "mock": MockProvider(),
            "groq": GroqProvider(settings.GROQ_API_KEY, settings.GROQ_MODEL),
            "gemini": GeminiProvider(settings.GEMINI_API_KEY, settings.GEMINI_MODEL),
        }
        self._cache: Dict[str, Any] = {}
        self.fallback_events: list[Dict[str, Any]] = []

    def set_provider(self, provider_name: str, api_key: Optional[str] = None):
        if provider_name not in self.providers:
            raise ValueError(f"Unknown provider '{provider_name}'. Must be one of: {list(self.providers.keys())}")
        self.provider_name = provider_name
        if api_key:
            if provider_name == "groq":
                self.providers["groq"] = GroqProvider(api_key, settings.GROQ_MODEL)
            elif provider_name == "gemini":
                self.providers["gemini"] = GeminiProvider(api_key, settings.GEMINI_MODEL)

    def get_active_provider(self) -> BaseLLMProvider:
        return self.providers.get(self.provider_name, self.providers["mock"])

    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema_class: Optional[Type[T]] = None,
        max_retries: int = 5,
        base_backoff: float = 2.0,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Executes generation with caching, exponential backoff on transient errors and rate limits (429),
        and automatic fallback between Gemini and Groq on 429/quota errors with a logged event.
        """
        import hashlib
        cache_key = hashlib.sha256((system_prompt + "::" + user_prompt).encode("utf-8")).hexdigest()
        if use_cache and cache_key in self._cache:
            cached_val = self._cache[cache_key]
            if schema_class:
                return schema_class.model_validate(cached_val).model_dump()
            return dict(cached_val)

        provider = self.get_active_provider()
        last_error = None

        # Determine alternate provider if configured
        alternate_provider_name = None
        if self.provider_name == "gemini" and getattr(self.providers.get("groq"), "api_key", None):
            alternate_provider_name = "groq"
        elif self.provider_name == "groq" and getattr(self.providers.get("gemini"), "api_key", None):
            alternate_provider_name = "gemini"

        # 1. Try primary provider with exponential backoff and instant fallback on 429
        for attempt in range(max_retries):
            try:
                res = await provider.generate_json(system_prompt, user_prompt, schema_class=schema_class)
                self.last_model_used = getattr(provider, "last_model_used", getattr(provider, "model", self.provider_name))
                if use_cache and not res.get("is_test_mode"):
                    self._cache[cache_key] = res
                return res
            except LLMRateLimitError as rle:
                last_error = rle
                if alternate_provider_name:
                    event = {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "from_provider": self.provider_name,
                        "to_provider": alternate_provider_name,
                        "reason": f"429 rate limit hit: {rle}"
                    }
                    self.fallback_events.append(event)
                    print(f"[LLM FALLBACK EVENT] Rate limit (429) hit on {self.provider_name}. Switching to alternate provider {alternate_provider_name}: {rle}")
                    try:
                        alt_provider = self.providers[alternate_provider_name]
                        res = await alt_provider.generate_json(system_prompt, user_prompt, schema_class=schema_class)
                        if use_cache and not res.get("is_test_mode"):
                            self._cache[cache_key] = res
                        return res
                    except Exception as alt_err:
                        print(f"[LLM FALLBACK FAILED] Alternate {alternate_provider_name} also failed: {alt_err}")
                        # Keep primary provider error so the user knows what actually failed on active provider
                        last_error = LLMResponseError(f"{self.provider_name.upper()} error: {rle} (Fallback {alternate_provider_name} also failed: {alt_err})")
                sleep_time = max(8.0, base_backoff * (2 ** attempt))
                print(f"[LLM RATE LIMIT 429] Pacing {sleep_time:.1f}s backoff on {self.provider_name} (attempt {attempt+1}/{max_retries})...")
                await asyncio.sleep(sleep_time)
            except (json.JSONDecodeError, httpx.HTTPError, Exception) as e:
                last_error = e
                sleep_time = base_backoff * (2 ** attempt)
                await asyncio.sleep(sleep_time)

        # 2. Try alternate live provider if configured and not yet attempted
        if alternate_provider_name:
            alt_provider = self.providers[alternate_provider_name]
            event = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "from_provider": self.provider_name,
                "to_provider": alternate_provider_name,
                "reason": f"Primary provider failed after retries: {last_error}"
            }
            self.fallback_events.append(event)
            print(f"[LLM FALLBACK EVENT] Switching from {self.provider_name} to {alternate_provider_name} after retry exhaustion: {last_error}")
            try:
                res = await alt_provider.generate_json(system_prompt, user_prompt, schema_class=schema_class)
                if use_cache:
                    self._cache[cache_key] = res
                return res
            except Exception as alt_err:
                last_error = alt_err

        # 3. Fail if live provider failed and provider is not mock
        if self.provider_name != "mock":
            raise LLMResponseError(f"Live LLM Provider '{self.provider_name}' failed after {max_retries} attempts: {last_error}")

        # 4. Fallback to mock only if mock is configured as active provider
        try:
            res = await self.providers["mock"].generate_json(system_prompt, user_prompt, schema_class=schema_class)
            return res
        except Exception:
            pass

        raise LLMResponseError(f"LLM Client failed after {max_retries} attempts: {last_error}")

# Global instance
llm_client = LLMClient()
