# Architecture & Technical Decisions

This document logs key architectural choices made during the development of **Signal Stack**, explaining the rationale and trade-offs.

---

## 1. Provider-Agnostic LLM Layer with Structured Outputs

- **Decision:** Implement a unified `LLMClient` with a provider switch supporting Groq (`llama-3.3-70b-versatile`), Google Gemini (`gemini-1.5-flash`), and a local `MockProvider`.
- **Why:** 
  - Meets the hard constraint of using free tiers without locking the platform into a single vendor's API quirks or quotas.
  - Groq provides rapid response times and high rate limits on open-weight models.
  - Gemini provides generous context windows.
  - `MockProvider` enables 100% deterministic unit and smoke testing without consuming live API quotas or requiring network access during CI.
- **Trade-offs:** Custom JSON schema enforcement and response sanitization must be maintained uniformly across distinct provider APIs.

## 2. Multi-Dimensional Signal Scoring vs. Single Composite Score

- **Decision:** Separate signal evaluation into three distinct floating-point metrics (`source_reliability`, `evidence_strength`, `strategic_relevance`) alongside impact and urgency ratings.
- **Why:** 
  - A single "relevance" score obscures why a signal matters. A blog post from an unverified source might have immense theoretical relevance but low reliability. Conversely, a SEC filing has high reliability but might have negligible strategic impact.
  - Protects against AI hallucination: users can filter by evidence strength to inspect only hard-grounded items.

## 3. Strict Relational Schema for Intelligence Provenance

- **Decision:** Model the ingestion pipeline as an auditable chain: `Source` -> `CrawlRun` -> `Document` (with SHA-256 hash) -> `Signal` (with `source_url` and `evidence_snippet`) -> `Brief`.
- **Why:** 
  - Zero-fabrication guarantee requires full cryptographic traceability from the final executive brief back to the exact crawled document text and HTTP response.
  - Deduplication is achieved naturally via document content hashes (`content_hash`), preventing redundant processing of unchanged pages.

## 4. SQLite with SQLAlchemy 2.0

- **Decision:** Use SQLite as the primary database with modern SQLAlchemy 2.0 declarative models and type annotations.
- **Why:** 
  - Zero operational overhead: requires no external database container or daemon, making deployment trivial.
  - Perfectly matches the local-first, lightweight architecture while supporting full relational queries, foreign keys, and indexes.
  - Easily migratable to PostgreSQL if scaled up in the future.

## 5. Polite Crawler Architecture

- **Decision:** Enforce `urllib.robotparser` inspection for all URLs, explicit request rate limiting (default 2s delay), and strict timeout handling.
- **Why:** 
  - Respects web standards, prevents IP bans, avoids hammering target company infrastructure, and abides by the hard requirement to never bypass auth or violate crawler etiquette.

## 6. Anti-Slop Frontend Aesthetics

- **Decision:** Adopt an editorial, high-contrast, information-dense layout in Streamlit using custom typography, slate-zinc color palette, clean badges for verified facts, and distinct treatment for LLM interpretation.
- **Why:** 
  - Default Streamlit dashboards look generic and uninspired. Executive briefs require clear hierarchy, fast scanning, zero visual noise, and no gratuitous AI gradient tropes.

## 7. Programmatic Evidence Snippet Verification Guard

- **Decision:** Programmatically validate that any claim tagged "verified" contains a verbatim quote snippet present inside the fetched document corpus.
- **Why:** 
  - Prevents LLM sycophancy or hallucinated grounding. If an extracted claim cites a quote that cannot be found in the actual crawled HTML or RSS text, it is immediately downgraded to "assumption" with an audit note.

## 8. 10-Topic Adaptive Interview with Stateful Memory

- **Decision:** Structure executive discovery across 10 canonical strategic topics (revenue lines, customer segments, customer pain, win factors, competitors, market shifts, developments, priorities, metrics, decisions) generated sequentially with context memory.
- **Why:** 
  - One-at-a-time generation allows questions to reference the specific company profile and prior answers, avoiding repetitive or boilerplate questions.
  - Vague answers trigger targeted follow-up probes (max 3 across session), while confidential topics can be skipped cleanly.

## 9. Mock Output Quarantine ("TEST MODE")

- **Decision:** Explicitly prefix mock LLM responses with `[TEST MODE]` and remove mock selection from the user-facing UI.
- **Why:** 
  - Protects data integrity: ensures synthetic mock data can never be mistaken for real production intelligence.
  - The UI permits only real free-tier providers (Groq and Gemini) with direct API key management.

## 10. Entity-Grounded Question Generation & Similarity Threshold (< 70%)

- **Decision:** Validate all LLM-generated interview questions against the company's research profile, requiring explicit entity/term grounding and rejecting questions with >70% similarity to other companies on the same topic.
- **Why:** 
  - Ensures the engine never produces generic, interchangeable questions or mere regurgitations of internal topic labels.
  - Verifiable across diverse sectors (e.g., EdTech admissions vs. Developer analytics vs. Restaurant hospitality).

## 11. LLM Vagueness Judge with User-Quote Attribution

- **Decision:** Replace arbitrary string-length heuristics with an LLM judge evaluating whether an executive answer possesses substance, automatically formulating a follow-up probe that directly quotes and questions the user's specific words.
- **Why:** 
  - Probes vague answers like "sales" or "commissions" with tailored, contextual questions while respecting comprehensive answers. Capped at 3 follow-ups to maintain interview pacing.

## 12. Ephemeral Secret Isolation

- **Decision:** Prohibit persistence of API keys in database tables, log files, or evidence output files. Enforce `.gitignore` exclusion for `.env` and SQLite database files.
- **Why:** 
  - Zero credential leakage guarantee across local testing, version control, and multi-tenant persistence layers.

## 13. Within-Session Question Similarity and Phrasing Validator (<= 50%)

- **Decision:** Reject any newly generated canonical interview question if its similarity to any prior question in the same interview session exceeds 50%, or if it attempts to re-cover an already-answered topic.
- **Why:**
  - Prevents the interview from looping or echoing prior questions with slightly altered synonyms, guaranteeing that each of the 10 questions explores distinct strategic territory.

## 14. Strict Topic Isolation and Entity Economy

- **Decision:** Prohibit mentioning competitor names on non-competitor topics (competitors are restricted strictly to topic 5: `competitors_substitutes`). Restrict entity usage to at most one natural company-specific term, and forbid quoting previous answers on canonical questions (reserving user quotes strictly for follow-up probes).
- **Why:**
  - Eliminates prompt pollution where competitor names or financial metrics from earlier answers leaked into unrelated questions like customer friction or material milestones.

## 15. Autonomous Competitor Discovery via Evidence Grounding & URL Liveness Verification

- **Decision:** Formulate 4-6 search queries from the company's intelligence profile, search Google News RSS and news aggregators for live market context, extract 5-10 competitors strictly grounded in retrieved snippets/titles, and verify that candidate URLs resolve via parallel HTTP GET checks with SSL-fallback. Drop unresolvable candidates.
- **Why:**
  - Completely satisfies the zero hardcoding mandate while ensuring that only actual, reachable organizations and substitutes with cited source evidence are stored in the competitive graph.
  - Zero overlap verified across different companies (e.g. EdTech vs. Fast-Casual restaurants).

## 16. Problem-Centric Customer Source Formulation

- **Decision:** In the `customers` source category, formulate discovery search queries targeting user friction, grievances, objections, and problems the company solves (e.g. visa rejections, admission delays, meal customization), rather than simple vanity brand mentions.
- **Why:**
  - True strategic intelligence requires tracking where buyers complain about the bottlenecks the business exists to resolve, surfacing actionable demand signals and emerging customer pain points.

## 17. Multi-Dimensional Source Scoring, Provenance Rationale & Auto-Approval Gate

- **Decision:** Evaluate each candidate source across `specificity_score` (0.85-0.88), `credibility_score` (heuristics on educational/governmental/authoritative domains), and `recency_score` (HTTP `Last-Modified` and feed entry parse). Compute composite `overall_score`, conduct HTTP liveness checks, and auto-approve only sources with `health in ['healthy', 'degraded']` and `overall_score >= 0.70`.
- **Why:**
  - Guarantees high-signal monitoring feeds while screening out dead endpoints, 404s, or junk links. Meets the mandate of 20+ approved sources for MeetUniversity.

## 18. Multi-Format Internal Document Ingestion with SHA-256 Deduplication

- **Decision:** Implement parser for CSV, Excel (.xlsx/.xls via `openpyxl`), PDF (via `pypdf`), and plain text/markdown. Store as `Document` with `category='internal'`, `document_type='internal_upload'`, filename metadata, and cryptographic SHA-256 content deduplication.
- **Why:**
  - Allows founders to ingest internal customer objection logs, lost deal summaries, and sales feedback into the company intelligence corpus without external leaks.

## 19. Test Fixture Tagging Guard (`[TEST FIXTURE]`)

- **Decision:** Tag all simulated interview answers in test suites with `[TEST FIXTURE]`. Updated `InterviewService.submit_answer` to detect this prefix and strictly prevent fixture answers from being committed as real `ProfileFact` records in the database.
- **Why:**
  - Guarantees complete separation between automated CI test runs and genuine enterprise profile facts.

## 20. Anti-Slop UI Typography and Workflow Layout

- **Decision:** Adopt a single sans font (Inter), WCAG AA secondary text contrast (#94a3b8), 8px spacing scale, a single sky accent color (#38bdf8), zero emojis across all buttons/headings/badges, grouped sidebar navigation (Setup, Intelligence, Output), a collapsed bottom Settings expander for credentials, and a persistent workflow stepper (`Research -> Interview -> Signal Stack -> Crawl -> Brief`).
- **Why:**
  - Executive tooling requires clean, restrained, high-density presentation without visual clutter or generic AI templates. Meets Taste Skill 2.5 anti-slop guidelines.

## 21. Two-Step Competitor Discovery & Programmatic Verbatim Quote Grounding

- **Decision:** Split competitor discovery into two explicit stages: (a) LLM proposes 10–15 candidate hypotheses strictly excluding universities, trade media, ranking publishers, testing bodies, and regulators; (b) parallel HTTP fetch of candidate websites, LLM verification of overlapping commercial service to identical customer segments, and programmatic verification that extracted quote snippets exist verbatim in fetched text (`norm_snippet in norm_text`). Resolve Google News redirects to real publisher URLs.
- **Why:**
  - Eliminates non-competitors (e.g. universities, British Council, ETS, Forbes) from competitive monitoring graphs. Guarantees that every competitor is a real, operational commercial enterprise offering direct or substitute solutions with verifiable on-page proof.

## 22. Customer-Voice Source Formulation, Visible Audit Logging & 25% Google News Cap

- **Decision:** In the `customers` category, replace general news queries and Hacker News with direct customer-voice channels: Reddit search/subreddits, review aggregators (Sitejabber, ConsumerAffairs, Trustpilot), and consumer/student forums (College Confidential, Pagalguy, Quora). Visibly log all liveness or robots.txt failures. Restrict Google News queries to $\le 25\%$ of total approved sources ($N_{gnews} \le \lfloor N_{non\_gnews} / 3 \rfloor$) and report approved sources broken down by distinct domain.
- **Why:**
  - Prevents news aggregators from drowning out organic user grievances and raw customer feedback. Enforces source domain diversity while upholding strict robots.txt compliance and transparent failure auditing.

## 23. Strict Verification Status Caps on Evidence Strength

- **Decision:** Cap `evidence_strength` strictly based on provenance and verification status:
  - `unverified` $\le 0.35$
  - `single_source` $\le 0.60$
  - `corroborated` $\le 0.85$ (strictly requiring $2+$ independent domains; otherwise capped at `single_source` $\le 0.60$)
  - `primary_source` up to $1.00$
- **Why:**
  - Prevents overconfidence in single-outlet reports or unverified community chatter. Enforces mathematical boundaries so that no single-source article can ever claim high-confidence evidence without independent multi-domain corroboration.

## 24. Temporal Provenance & Date Isolation Guard

- **Decision:** Mandate that `published_at` is strictly isolated from `discovered_at` or crawl fetch time. If the extracted publication date matches or falls within 60 seconds of the crawl fetch time (a common crawler artifact from HTTP `Date` response headers or dynamic feed rendering), it is purged to `None` (NULL), displaying "date unknown". Discovered timestamp is tracked independently.
- **Why:**
  - Crawl time must never be masqueraded as the original publication date. Prevents false recency scoring and guarantees historical integrity.

## 25. Discrete Event Gate & Taxonomy Validation

- **Decision:** Enforce that a signal must represent a genuine commercial or operational development, not static marketing copy or promotional taglines. Classify events strictly into nine taxonomical buckets: `regulatory_change`, `market_data`, `product_launch`, `pricing_change`, `partnership`, `hiring`, `funding_or_ma`, `customer_complaint`, `other`. Forbid `product_launch` unless the text explicitly states something launched, was announced, or was released.
- **Why:**
  - Eliminates noise and evergreen website marketing copy. Guarantees that the intelligence feed surfaces only discrete, material real-world actions.

## 26. Specificity & Grounding Mandate for Brief Recommendations

- **Decision:** Require that every strategic opportunity, risk/threat, and recommended action cites at least one signal ID (`[Signal #<ID>]`) AND quotes a stored profile fact (`Profile Fact: "<quote>"`) or founder interview answer (`Founder input: "<quote>"`). Reject generic industry advice that could apply to any generic firm. Require opportunities to be actionable gaps with evidence, impact, and a concrete next step; move monitor-only items to Section 9 ("What We Should Watch").
- **Why:**
  - Executive briefs are useless if filled with generic platitudes ("improve marketing", "monitor rivals"). Grounding actions in specific observed signals and founder answers creates high-conviction, custom operational steps.

## 27. Semantic Claim Verification & Autonomous Brief Regeneration

- **Decision:** Implement an automated LLM claim auditor (`CLAIM_VERIFICATION_SYSTEM`) that cross-checks claims made in the draft brief against the verbatim evidence snippet stored for each cited signal. Evaluates support as `yes`, `partial`, or `no`. If any claim receives a `"no"` (unsupported or contradictory), the brief draft is rejected and regenerated with explicit error feedback (up to 2 retries).
- **Why:**
  - Guarantees factual alignment between the final narrative text and the underlying raw crawled evidence. Eliminates LLM narrative drift and subtle hallucinations.

## 28. Zero-Truncation Mandate for Intelligence Explanations

- **Decision:** Strictly prohibit `...` ellipsis truncations across `why_important` breakdowns, strategic implications, and verbatim snippet presentations.
- **Why:**
  - Leadership briefs must deliver complete, unbroken rationale without artificial truncation or ellipses that obscure why an event matters.

## 29. Resilient Multi-Provider Fallback on 429 Quota Exhaustion

- **Decision:** In `LLMClient`, implement instant provider fallback between Google Gemini and Groq whenever a 429 rate limit or quota exhaustion is encountered, recording structured telemetry in `fallback_events` and logging console audit events.
- **Why:**
  - Ensures continuous automated pipeline execution without halting or crashing when free-tier rate limits or transient quota spikes occur.

## 23. ETag & If-Modified-Since HTTP Caching with Fallback

- **Decision:** Capture HTTP `ETag` and `Last-Modified` headers for both RSS feeds (via `feedparser`) and HTML pages (via `httpx`). Pass conditional `If-None-Match` and `If-Modified-Since` headers on subsequent crawl cycles; if the server responds with HTTP 304, immediately return 0 new/changed items without re-parsing content.
- **Why:**
  - Dramatically minimizes unnecessary bandwidth, speeds up repetitive background monitoring runs, and respects origin server resources.

## 24. Exact & Shingle/MinHash Deduplication Engine

- **Decision:** Enforce multi-tier deduplication across all ingested documents. First, exact deduplication matches normalized content SHA-256 hashes, canonical URLs, original URLs, and titles. Second, near-duplicate deduplication extracts 3-word shingles and computes Jaccard similarity against existing corpus documents; any item with similarity $\ge 0.80$ is tagged as duplicate, increments `source.duplicate_count`, and is suppressed from generating duplicate signals.
- **Why:**
  - Guarantees that repetitive syndication across Google News RSS or multiple publisher mirrors does not flood the executive feed. Verified by running an immediate second crawl producing ~0 new items (100% dedup efficiency).

## 25. Noise-Filtered Structural Page Snapshot Diffing

- **Decision:** For monitored page sources (pricing, blog index, careers, press), retain historical HTML text snapshots. When a new fetch arrives, strip volatile noise patterns (dates, timestamps, days of the week, cookie banners, copyright notices) using pre-compiled regular expressions and compute `difflib.Differ` unified line diffs. Only trigger candidate signals if meaningful added content exceeds 50 non-noise characters.
- **Why:**
  - Eliminates false positive change alerts caused by updating copyright years, daily date headers, or transient session IDs.

## 26. Batch Signal Classification & Customer-Voice Extraction

- **Decision:** Pre-filter crawled items for strategic relevance against company business lines, industry, and competitor names before LLM invocation. Batch items (3–4 per call) into `SIGNAL_BATCH_CLASSIFICATION_SYSTEM` extracting category, linked competitor, event type, one-sentence headline, and verbatim evidence snippets. For `customers` sources, extract the customer's own words as a verbatim quote and the core unmet need. All snippets are programmatically verified to exist verbatim in the source text (`norm_snippet in norm_text`); ungrounded items are dropped.
- **Why:**
  - Ensures 100% adherence to Rule 2 (No fabricated data) and Rule 6 (Distinguish verified fact from interpretation) while keeping LLM token usage well within free-tier limits.

## 27. Development Gate: Static Copy Baseline & Discrete Event Verification

- **Decision:** Enforce a strict Development Gate:
  1. For HTML web pages, the first crawl stores an initial snapshot as a baseline with zero signals generated. Signals are created exclusively upon meaningful snapshot diffs ($\ge 50$ added non-noise chars) on subsequent crawls, or from dated news/blog/feed entries.
  2. Filter out promotional marketing taglines (e.g., "Make your application stress-free"), navigation copy, and evergreen descriptions (e.g., "Student loans and comfortable stays"). Add an LLM check `is_discrete_event` with a concrete `event_reason` stored directly on each `Signal`.
  3. Forbid labeling signals as `product_launch` unless the text explicitly contains a launch, announcement, or release verb ("launch", "announc", "unveil", "releas", "roll out", "introduc"). Items without launch verbs are reclassified or dropped by the gate.
- **Why:**
  - Prevents static website slogans or evergreen company descriptions from masquerading as actual weekly business developments.

## 28. Verified Publication Date Provenance

- **Decision:** Extract authentic publication dates (`published_date`) from RSS fields (`published_parsed`, `updated_parsed`, `pubDate`), page metadata (JSON-LD `datePublished`/`dateModified`, OpenGraph `article:published_time`, `<time>` tags), or date-encoded URL paths (`/YYYY/MM/DD/`). If no date is found, store `NULL` in the database and display `"date unknown"` in the UI. Keep `discovery_date` (the crawl timestamp) strictly separate. Never default to crawl time as publication date.
- **Why:**
  - Protects chronological integrity and prevents old articles from being falsely presented as recent developments.

## 29. Two-Stage Google News Opaque Token Resolution & Search Feed Exclusion

- **Decision:** Google News RSS article URLs containing opaque server tokens (`news.google.com/rss/articles/CBMi...`) are decoded directly into destination publisher URLs and human-readable publisher names using Google's `batchexecute` RPC via `googlenewsdecoder`. Search-feed URLs (`news.google.com/rss/search?q=...`) are strictly forbidden as evidence links. Any Google News article that fails resolution is immediately dropped and audited.
- **Why:**
  - Guarantees that every cited evidence link points to the authentic underlying publisher article (e.g. BBC, Time, Times Higher Education) rather than an opaque Google redirect wrapper.

## 30. Customer Voice Isolation & Permanent WAF (403) Removal

- **Decision:** Exclude customer testimonials or case studies hosted on a company's or competitor's own website from the `customers` category. Customer voice must originate strictly from third-party reviews, public forums, or Q&A platforms. Sources permanently blocked by origin Cloudflare/WAF policies (HTTP 403) are automatically removed from approved monitoring and audited. If `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` are present in `.env`, use the official Reddit OAuth API; otherwise log "Reddit unavailable: no credentials" and skip without failure.
- **Why:**
  - Distinguishes authentic, unsolicited customer sentiment from self-serving vendor marketing materials while adhering strictly to robots.txt and credential security boundaries.

## 31. Competitor App Store Customer Voice Discovery & Ingestion

- **Decision:** Discover public mobile app store customer reviews for discovered competitors (e.g. LeapScholar, Yocket, IDP) using the public Apple iTunes Search API (`itunes.apple.com/search?term={comp}&entity=software`) and public iTunes customer reviews RSS endpoint (`itunes.apple.com/{storefront}/rss/customerreviews/id={trackId}/sortBy=mostRecent/json`). Extract low-star ratings ($\le 3$) and customer friction points as genuine customer complaints with verbatim customer quotes and unmet needs.
- **Why:**
  - Bypasses anti-bot/WAF blocking and CAPTCHAs legally and cleanly via public Apple RSS APIs. Delivers authentic student complaints regarding aggressive sales counseling, unfulfilled promises, and refund issues without scraping or auth bypass.

## 32. Multi-Factor Priority Ranking Formula with Orthogonal Scoring

- **Decision:** Implement three strictly orthogonal scoring dimensions:
  1. `source_reliability`: Origin authority hierarchy (Regulator/Government official: 0.95, Established Trade Media: 0.90–0.92, Competitor's own press/site: 0.85, Third-party reviews/forums: 0.75–0.80).
  2. `evidence_strength`: Degree of verifiability (verbatim body snippet: +0.70, primary source: +0.20, published date known: +0.10, paywalled/headline only capped at 0.30).
  3. `strategic_relevance`: Floating score evaluated by LLM assessing degree of impact on target company operations, strictly anchored to stored Profile Facts or Interview Answers.
  Priority Score is computed using a documented weighted formula:
  $$\text{Priority} = 0.30 \cdot \text{relevance} + 0.20 \cdot \text{impact} + 0.15 \cdot \text{urgency} + 0.15 \cdot \text{credibility} + 0.10 \cdot \text{recency} + 0.10 \cdot \text{novelty}$$
  with recency decay ($e^{-\lambda \cdot \text{age}}$) and novelty discount (0.5 for signals already cited in past briefs).
- **Why:**
  - Ensures priority ordering reflects true leadership importance rather than raw crawl order, with explicit mathematical factor explanations (`why_important`).

## 33. 10-Section Monday Brief Structure with Programmatic Citation & Source Appendix Validation

- **Decision:** The Monday Executive Brief generates all 10 standard structural intelligence sections:
  1. Executive Summary (top 5 developments by priority, age $\le 90$d, separating "Our interpretation" from "Evidence")
  2. Customer Signals & Voice (App Store reviews / customer complaints)
  3. Competitor Intelligence
  4. Market & Regulatory Shifts
  5. Internal Business Intelligence (analyzing uploaded internal documents, or explicitly printing "No internal data uploaded")
  6. Actionable Strategic Opportunities (target 3 with evidence, expected impact, concrete next step, priority)
  7. Strategic Risks & Threats
  8. Recommended Actions This Week (action items with suggested owner roles, priorities, reasons, and interactive status tracking)
  9. What We Should Watch
  10. Source Provenance Appendix (table with signal ID, headline, publisher link, published date, verbatim body snippet, reliability/evidence scores)
  Programmatic validation verifies that every factual claim cites an authentic `[Signal #ID]`, that all cited IDs exist, and automatically reconciles Section 10 so every cited signal appears in the Source Appendix. Multi-format exports generate standalone email-ready HTML (inline CSS) and Markdown.
- **Why:**
  - Guarantees complete provenance and eliminates AI hallucination or fabricated claims. Leadership can trace any assertion in the brief directly back to the cited primary source.

## 34. 90-Day Recency Background Filter & Executive Summary Cutoff

- **Decision:** Signals published more than 90 days ago (`MAX_RECENT_SIGNAL_DAYS = 90`) are marked `is_background = True` and barred from the Executive Summary unless explicitly marked as ongoing. Every signal displays its age in days (`age_display`) in the Grounded Feed and Brief provenance views.
- **Why:**
  - Keeps the Monday Brief focused on actionable recent developments while preserving historical context as background intelligence.

## 35. Persistent Job Store Architecture (APScheduler + SQLite SQLAlchemyJobStore)

- **Decision:** Back APScheduler with `SQLAlchemyJobStore(engine=engine)` inside the backend process, storing persistent jobs in the SQLite database (`apscheduler_jobs` table). Module-level standalone functions in `backend.scheduler.jobs` serve as target callables (`weekly_brief_{company_id}`, `monthly_audit_{company_id}`).
- **Why:**
  - Guarantees registered jobs survive backend process restarts and server reboots without loss of schedule state or timing.
  - Maintains a local-first, zero-infrastructure footprint without requiring Redis, Celery, or external daemons.
  - Enables dynamic per-company rescheduling whenever schedule settings change.

## 36. Shielded Exception Handling & Telemetry Logging (`SchedulerLog`)

- **Decision:** Wrap every scheduled job in try/except/finally blocks that intercept all exceptions, record start/finish timestamps, duration, status (`success` | `failed` | `skipped`), records collected, and full error details into `SchedulerLog`. Never allow an uncaught exception to bubble to the scheduler engine.
- **Why:**
  - Guarantees that individual company crawl failures or temporary network glitches never kill the background scheduler process.
  - Provides complete transparency in the UI by surfacing errors in a Failure Alert Banner and a searchable Run History table.

## 37. Monthly Signal Stack Source Health Audit & Actionable Recommendations (Zero Auto-Deletion)

- **Decision:** Implement an autonomous monthly audit engine checking dead URLs (HTTP status codes, connection errors, RSS parse bozo flags), duplicate sources, inactive feeds (no new items over $N$ weeks), and declining relevance (<10% items passing the development gate). Re-runs discovery for fresh candidate sources and persists a `SourceHealthReport` with `add` / `remove` / `keep` recommendations.
- **Why:**
  - Prevents signal rot and degraded intelligence coverage over time.
  - Strict preservation constraint: sources are NEVER automatically deleted from the database. When an audit recommendation to remove a source is accepted, it transitions to `status="rejected"` with an audit note, maintaining database foreign key integrity and audit logs.

## 38. Per-Company Dynamic Settings & SMTP Delivery Fallback

- **Decision:** Store per-company schedule and monitoring settings (`brief_day`, `brief_time`, `timezone`, `monitoring_frequency`, `source_refresh_frequency`, `monthly_audit_day`, `delivery_email`, `inactivity_threshold_weeks`) in a `settings_json` column on `Company`. If SMTP variables are missing in `.env`, the delivery service cleanly logs `"delivery skipped: SMTP not configured"` and marks delivery as skipped without error.
- **Why:**
  - Empowers founders and administrators to customize delivery days, times, and timezones per organization without code changes.
  - Ensures clean offline and CI operation without crashing when email servers are not configured.

## 39. Distinct "blocked_by_robots" Status in Monthly Source Audits

- **Decision:** Separate crawl boundary restrictions (`blocked_by_robots`) from broken or unreachable endpoints (`dead`). In `SourceHealthReport`, report `dead_sources_count`, `blocked_sources_count`, `inactive_sources_count`, and `declining_sources_count` independently.
- **Why:**
  - A 403 Forbidden or robots.txt disallow rule does not mean the target URL is dead or 404; it indicates crawl policy barriers. Disaggregating these counts ensures transparent operational diagnostics.

## 40. Informational KEEP Recommendations with User Action Gate

- **Decision:** Monthly audit recommendations with `action="keep"` are emitted with status `"info"` and can never be marked `"accepted"`. Only genuine changes (`add` or `remove`) accept user confirmation.
- **Why:**
  - "Keep" is the default baseline state for healthy, active sources; it requires no state mutation. Only explicit user actions modify source configurations.

## 41. End-to-End One-Click Autonomous Pipeline ("Onboard and run")

- **Decision:** Implement `OneClickPipelineService` orchestrating the entire lifecycle for any input domain: research -> profile -> founder interview (skipped if human input absent, explicitly noting "No founder input provided" and anchoring strictly to verified profile facts) -> competitor discovery -> source discovery -> polite crawling -> signal extraction & ranking -> brief generation & export (Markdown + email-ready HTML).
- **Why:**
  - Enables zero-touch intelligence generation for new companies while guaranteeing zero data fabrication and strict fallback to verified profile facts when human input is skipped.

## 42. Context-Change Strategic Reassessment Engine & Diff Tracking

- **Decision:** When a founder modifies business priorities (target customer segment, pricing model, core markets), trigger `ContextChangeService.reassess_context`. Re-evaluate all active sources against updated strategic priorities, emit removal recommendations for misaligned feeds, discover fresh aligned candidate sources, and persist a `ContextChangeReport`. Strictly prohibit automatic source deletion; all mutations remain recommendations pending user confirmation.
- **Why:**
  - Business strategy pivots render certain monitoring sources obsolete while requiring new intelligence streams. Proposing explicit diffs with human-in-the-loop approval maintains data safety and foreign key integrity.

## 43. Elimination of Mock Provider from User-Facing UI

- **Decision:** Restrict frontend LLM provider selection strictly to real providers (Google Gemini and Groq). The `mock` provider is quarantined as a test-only fixture and unreachable via the UI.
- **Why:**
  - Prevents accidental generation of synthetic test data in live workspaces. Guarantees that all user-facing intelligence is derived from genuine LLM reasoning.





