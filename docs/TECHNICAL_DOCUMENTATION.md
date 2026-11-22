# Signal Stack: Technical Documentation

EDXSO AI Engineer Intern, Assignment 1. Covers architecture, source discovery, crawling, ranking, AI analysis, scheduling and reliability.

## 1. Architecture

```
Streamlit dashboard  ->  FastAPI backend  ->  SQLite (SQLAlchemy)
                              |
     +------------+-----------+-------------+--------------+
     | Research & | Discovery | Crawler &   | Analysis &   |
     | interview  | (competit-| monitoring  | brief        |
     |            | ors, srcs)|             | generation   |
     +------------+-----------+-------------+--------------+
                              |
              APScheduler (persistent job store)
              LLM client: Gemini (model rotation) -> Groq fallback
```

| Layer | Choice | Why |
|---|---|---|
| API | FastAPI | Typed endpoints, automatic docs |
| Storage | SQLite + SQLAlchemy | Zero setup, runs anywhere; schema in `backend/models` |
| Crawling | httpx, trafilatura, feedparser | Free, polite, good text extraction |
| Scheduling | APScheduler with SQLAlchemy job store | Jobs persist across restarts |
| UI | Streamlit | Fast to build a working dashboard |
| LLM | Gemini free tier, Groq free tier | No paid services; provider abstraction with fallback |

The schema has 15 tables, including `companies`, `profile_facts`, `interview_qas`, `competitors`, `sources`, `crawl_runs`, `crawl_results`, `documents`, `signals`, `briefs`, `action_items`, `scheduler_logs`, `source_health_reports`, `context_change_reports` and `settings`.

**Principle:** the LLM proposes, code verifies. Every LLM output that makes a factual claim is checked against fetched text before it is stored.

## 2. Company understanding and the adaptive interview

**Research.** The service fetches the homepage and key internal pages (about, products, pricing, blog, careers, contact), honouring robots.txt and per-domain rate limits, and cleans them with trafilatura. An LLM extracts a profile (business lines, products, segments, positioning, revenue model, geography). Each field is a *verified fact* only if its quoted snippet exists verbatim in the company's own fetched pages; otherwise it is downgraded to an *assumption*. Facts must be anchored to the company's own domain, which prevents name collisions (an early run mixed MeetUniversity with an unrelated university; research now anchors to the domain and a retirement step removes non-anchored facts).

**Interview.** Ten topics (revenue lines, segments, customer problems, win factors, competitors, market shifts, material developments, priorities, internal data, decisions to support) are used as coverage targets, never shown as the question. The LLM writes each question from the profile and prior answers. Validators reject a question if it has no company-specific term, is more than 50% similar to an earlier question in the same interview, or is more than 70% similar to the same topic's question for another company. An LLM vagueness judge returns `{is_vague, reason, followup}` and may trigger up to three follow-ups that quote the user's words. Questions can be skipped, and answers can be edited, which re-merges the profile. Answers tagged as test fixtures are never used as founder input.

## 3. Source discovery

**Competitors (two steps).** (a) The LLM proposes 10 to 15 candidates from the profile and interview, labelled "hypothesis". (b) Each candidate's own website is fetched, and an LLM judges whether it offers an overlapping service to the same segment, quoting a snippet that is programmatically checked against the fetched text. Universities, partners, media, regulators and the company itself are excluded by generic classifiers. At most 10 are kept, ranked by verified overlap and role (direct, substitute).

**Sources.** For each of the four categories the LLM proposes candidate sources tailored to the company (forums, review pages, trade feeds, regulator pages, competitor blogs and pricing pages). Generic infrastructure is allowed: Google News RSS queries (capped at 25% of approved sources), the iTunes Search API and customer-review RSS for competitor apps, and RSS autodiscovery. Every candidate gets:
- a company-specific `reason_for_inclusion` (generic reasons are rejected);
- a liveness check (HTTP status, redirects, feed parse);
- a robots.txt check (blocked sources are recorded as `blocked_by_robots`, never bypassed);
- specificity, recency and credibility scores.

Sources that pass are approved; others stay `discovered` for manual approval or are rejected with a stored reason. Duplicates are detected by canonical URL and path similarity.

**Customer voice.** Customer sources target where customers discuss the problem, not company mentions: competitor app reviews, third-party review pages and public forums. An app's reviews are used only if the app's seller domain matches the competitor's domain (or the name matches exactly in the right category). A classifier rejects non-customer content such as ex-employee disputes. Testimonials hosted on a vendor's own site are excluded.

**Internal.** CSV, Excel, PDF and text uploads are parsed into documents. An extractor finds recurring objections, lost-deal reasons, product requests and sales patterns, each with a count and verbatim row quotes. The company's own website and blog are not treated as internal intelligence; without uploads or interview answers, Section 5 of the brief reads "No internal data uploaded."

## 4. Crawling and monitoring

- **Politeness:** custom User-Agent, robots.txt cached per host, 2.0 s minimum delay per host, concurrency 3, 15 s timeout. ETag and If-Modified-Since are used where supported.
- **Types:** RSS/Atom via feedparser; HTML via httpx and trafilatura.
- **Change detection:** the first fetch of a page stores a *baseline snapshot* and creates no signal. Later fetches create a candidate only if the text diff adds at least 50 non-noise characters. Dated news, blog and feed items are candidates directly.
- **Deduplication:** SHA-256 content hash, canonical URL, normalised title, and near-duplicate detection by 3-word shingle Jaccard similarity of 0.80 or higher. An immediate second crawl produced zero new items on stable sources.
- **Links and dates:** Google News redirect links are decoded to the publisher URL, and search-feed URLs are never stored as evidence. Publication dates come from RSS fields, JSON-LD, OpenGraph, `<time>` tags or the URL; if none exists, the date is stored as null ("date unknown"). Crawl time is never used as a publication date.
- **Records:** every run writes a `crawl_run` and per-source `crawl_results` (status, HTTP code, items found, new, changed, duration, error). Failures are shown in the UI.

## 5. Analysis and ranking

**Development gate.** An LLM check decides whether an item is a discrete event or change (not marketing copy or an evergreen description) and must give a reason. Event types come from a fixed taxonomy (regulatory_change, market_data, product_launch, pricing_change, partnership, hiring, funding_or_ma, customer_complaint, other), and the source text must support the label (for example, "product_launch" requires a launch or release verb).

**Evidence vs interpretation.** Each signal stores *evidence* (what happened, when, source, publisher URL, verbatim snippet, verification status) separately from *interpretation* (why it matters, business area, opportunity / threat / neutral, urgency, what to consider). Interpretations must reference a stored profile fact or founder answer.

**Three separate scores.**
- *Source reliability:* domain authority heuristics (.gov/.edu/.europa.eu about 0.98, established media about 0.90, review platforms about 0.72, default 0.65).
- *Evidence strength:* capped by verification status and snippet type: unverified at most 0.35, single_source at most 0.60, corroborated (2 or more independent domains) at most 0.85, primary_source up to 1.00, headline-only snippets at most 0.40, paywalled at most 0.30.
- *Strategic relevance:* LLM rationale tied to the profile.

An AI confidence value is never used as proof of truth.

**Priority formula** (weights in `config.py`):

`Priority = 0.30·Relevance + 0.20·Impact + 0.15·Urgency + 0.15·Credibility + 0.10·Recency + 0.10·Novelty`

Each signal stores a generated `why_important` listing its top contributing factors. Novelty compares against signals in previous briefs. Market and competitor signals older than 90 days are flagged `background`; customer reviews use a 12-month window because they are evergreen, and their age is displayed.

## 6. Brief generation and validation

The brief has the ten required sections. Candidates are selected per category (customer, competitor, market) so one category cannot crowd out the others. Before a brief is saved it must pass:

1. **Citation validator:** every factual claim carries a `[Signal #ID]` that exists and appears in the appendix.
2. **Semantic claim auditor:** an LLM compares each claim with the cited signal's stored snippet or body text and returns yes / partial / no; "no" triggers regeneration. A table of (claim, signal, verdict) is logged.
3. **Specificity:** opportunities, risks and actions must cite a signal and quote a stored profile fact or founder answer of at least 8 words that bears on the recommendation.
4. **Mechanism applicability:** a signal may support an opportunity only if its text shows it applies to the company's customers (for example, a UK-EU youth mobility scheme is routed to "What We Should Watch", not "Opportunities", for an Indian-student counselling company).
5. **Number integrity:** figures in impact and next-step text must appear in a cited signal; outcome predictions are rejected.
6. **Customer sentiment counts:** claims state counts ("N negative of M total"); "widespread" and "massive" are rejected without support.
7. **Consistency check:** the brief is compared with the stored profile to catch entity mix-ups.

Empty sections say "No meaningful development detected this cycle." The appendix lists only cited signals with link, publication date and age, discovery date, snippet, scores, and whether the evidence is body text or headline-only, plus a publisher-diversity summary. Briefs export as Markdown and email-ready HTML, and recommended actions are stored as trackable items (open, in progress, done).

## 7. Scheduling and reliability

- **Weekly brief job** and **monthly audit job** per company, registered with APScheduler using a SQLAlchemy job store (they survive restarts). Schedule settings (day, time, timezone, frequencies, audit day) are stored per company and changing them reschedules the jobs.
- **Monthly audit** checks approved sources for dead URLs, robots blocks, duplicates, inactivity and declining relevance, re-runs discovery for candidates, and writes a `source_health_report` with add / remove / keep recommendations. Removal is a recommendation the user accepts; sources are marked `rejected` with a reason and history is preserved.
- **Failure handling:** every job is wrapped so exceptions are caught and written to `scheduler_logs` (job, company, times, status, error, records collected). The dashboard shows a failure banner and a run history table. A failed run never stops the scheduler.
- **LLM resilience:** the client rotates through Gemini models and falls back to Groq on HTTP 429, logging each fallback event.
- **Tests:** short-interval firing, forced failure shielding, restart persistence and settings-driven rescheduling are covered by automated tests.

## 8. Reusability and context change

No company, industry or competitor names appear in source selection, scoring or prompts. A hard-coding audit removed industry-keyed domain lists and keyword sets; discovery is LLM-proposed and code-verified.

**Context change.** Editing the profile or an interview answer triggers reassessment: each source is re-scored against the new context, irrelevant sources are recommended for removal with reasons, new competitors are found through the same two-step discovery, and new sources are discovered. A `context_change_report` stores before and after counts and the diff. In the MeetUniversity test (a pivot to German public universities), run on a copy of the database, discovery added competitors with verified website snippets and recommended removal of sources that no longer fit. See `tests/evidence/phase8_context_change.json`.

## 9. Known limitations

- Free-tier LLM limits restrict how often full pipelines can run.
- Several sources block crawlers or expose headlines only, so evidence strength is capped and labelled.
- Customer-voice samples are small and come mainly from public app reviews.
- Trend-based audit checks need several weeks of history.
- Validators reduce but cannot eliminate LLM errors; they are the main defence against unsupported claims.
