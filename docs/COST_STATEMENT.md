# Cost Statement

**Total spend to build and run the demonstration: USD 0.** No paid APIs, paid scraping platforms or paid AI services were used.

## Components

| Component | Used for | Cost |
|---|---|---|
| Google Gemini API (free tier) | Research extraction, interview, classification, analysis, brief writing, claim checking | Free tier |
| Groq API (free tier, Llama 3.3 70B) | Automatic fallback when Gemini quota is exhausted | Free tier |
| Python, FastAPI, SQLAlchemy, SQLite, APScheduler, Streamlit | Application and storage | Open source |
| httpx, trafilatura, feedparser, googlenewsdecoder, pypdf, openpyxl | Crawling, text extraction, feed parsing, file parsing | Open source |
| Google News RSS | News discovery and monitoring | Public, no key |
| Apple iTunes Search API and customer-review RSS | Public competitor app reviews | Public, no key |
| Public websites and feeds | Monitored sources (robots.txt respected) | Public |
| Hosting | Runs locally on the developer machine | None |
| Reddit API | Optional; not used in the demonstration | Skipped without credentials |

## LLM configuration

- Primary provider: Gemini. Primary model: `gemini-3.5-flash-lite`. Rotation list is defined in `backend/config.py`.
- Fallback provider: Groq, model `llama-3.3-70b-versatile`.
- A `mock` provider exists for offline unit tests only. It is not selectable in the UI and its output is never stored as real data.

## Free-tier limitations (observed)

- **Quotas are low and vary by model and time.** During development some Gemini models returned HTTP 429 after roughly 20 requests per day, so the client rotates models and falls back to Groq. Quotas change, so check the provider's current limits.
- **One full run is expensive for a free quota.** A complete pipeline for one company (research, interview, discovery, crawl classification, analysis, brief with validation) makes many LLM calls. Re-running several companies in one day can exhaust free quotas; the app batches requests, backs off, and falls back automatically.
- **Output varies by model.** Because the model can rotate, wording of briefs can differ between runs. The validators apply to every model.
- **Crawling limits.** The crawler waits 2.0 seconds between requests to the same host and runs 3 requests in parallel. Sources that disallow crawlers are not fetched.
- **Reddit** requires OAuth credentials and is skipped when they are absent.
- **No deployment.** The project runs locally, so there are no hosting limits to disclose. `[UPDATE if you deploy: provider, free-tier limits, sleep behaviour]`

## Cost at scale (informational)

The system is free only within provider free tiers. Monitoring many companies on a weekly schedule would exceed free LLM quotas, at which point a paid LLM plan or a self-hosted open model would be needed. This is not required for the assignment and was not tested.
