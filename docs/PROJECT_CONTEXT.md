# PROJECT CONTEXT: Signal Stack

> **Signal Stack** is an autonomous company intelligence and Monday Morning Brief engine designed to transform fragmented external and internal signals into verified, high-leverage strategic briefings.

---

## HARD RULES (Non-Negotiable)

1. **No hard-coded competitors, sources, interview questions, or categories.**
   - Everything is dynamically generated per target company using LLMs based on its profile, market positioning, and ongoing discoveries.
   - Any list of competitors, monitoring targets, or sources must originate from LLM discovery workflows or validated user inputs.

2. **No fabricated data.**
   - Every single development reported must cite a valid source URL, discovery timestamp, and exact evidence snippet extracted from crawled documents.
   - **If nothing happened during a crawl period, the brief explicitly states so.** Hallucinating progress or synthesizing ungrounded developments is strictly forbidden.

3. **Free tools only.**
   - LLMs are accessed via Groq or Gemini free tiers behind a provider-abstraction layer.
   - The provider layer must handle automatic retries, backoff, and rate limits gracefully, with support for seamless provider switching and offline mock mode for deterministic testing.

4. **Crawler ethics & boundaries:**
   - The crawler must strictly respect `robots.txt`, honor rate limits and crawl delays, and **never attempt to bypass authentication**, paywalls, or anti-bot challenges.

5. **Separate score dimensions (AI confidence is never proof):**
   - Every signal maintains independent scores across three orthogonal axes:
     - `source_reliability` (0.0 - 1.0): Authority and reputation of origin domain.
     - `evidence_strength` (0.0 - 1.0): Directness and verifiability of excerpted snippet.
     - `strategic_relevance` (0.0 - 1.0): Degree of business impact on the monitored entity.
   - Model confidence is logged for telemetry but never treated as factual verification.

6. **Strict separation of "verified fact" vs. "interpretation":**
   - The user interface and data pipeline must always bifurcate what actually occurred (objective facts directly anchored to cited evidence) from what it means strategically (LLM interpretation, risk analysis, second-order effects).

---

## CORE DOMAIN CATEGORIES

All intelligence, sources, signals, and brief sections are structured across four fundamental categories:

- `customers`: Customer feedback, churn indicators, procurement changes, case studies, reviews, hiring in client organizations.
- `competitors`: Product releases, pricing adjustments, leadership turnover, patent filings, competitive wins/losses.
- `market`: Regulatory shifts, macro developments, emerging tech trends, industry standards, ecosystem partnerships.
- `internal`: Internal objectives, key metric updates, product roadmaps, interview responses, self-identified risks.

---

## TECH STACK & ARCHITECTURE

- **Backend Framework:** FastAPI (async REST API, OpenAPI docs).
- **Persistence:** SQLite via SQLAlchemy 2.0 (ORM models, relational schemas).
- **Task Orchestration:** APScheduler 3.x (background cron jobs, weekly Monday triggers, crawling intervals).
- **Network & Parsing:**
  - `httpx` (async HTTP client with timeouts, respectful user-agent).
  - `trafilatura` (DOM boilerplate removal and core content extraction).
  - `feedparser` (RSS/Atom feed parsing).
- **Frontend:** Streamlit with custom anti-slop typography and editorial layout adhering to high-taste design guidelines.
- **Testing:** Pytest & pytest-asyncio with in-memory SQLite fixtures and deterministic mock LLM provider.
