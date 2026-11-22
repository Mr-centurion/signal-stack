# Signal Stack: Company Intelligence & Monday Morning Brief Engine

EDXSO AI Engineer Intern, Assignment 1.

Signal Stack turns a company name and website into a continuously monitored intelligence system. It researches the company, interviews the founder, discovers competitors and sources, crawls them, analyses what matters, and writes an executive Monday Morning Brief in which every claim links to evidence.

**Design rule:** nothing is hard-coded per company or industry. Competitors, sources, interview questions and briefs are all generated per company, and every reported development carries a source link, a discovery date and a verbatim snippet. If nothing happened in a category, the brief says so.

- Live URL: not deployed. This is a documented local setup, which the assignment allows.
- Repository: https://github.com/Mr-centurion/signal-stack
- Demo URL: https://youtu.be/CsA18lSOBZM


## Contents

1. [Quick start](#quick-start)
2. [What it does](#what-it-does)
3. [Dashboard pages](#dashboard-pages)
4. [Demonstration companies](#demonstration-companies)
5. [Automation](#automation)
6. [Tests](#tests)
7. [Known limitations](#known-limitations)
8. [Project structure](#project-structure)
9. [Documentation](#documentation)

## Quick start

Requirements: Python 3.11 or newer (developed and tested on Python 3.13) and at least one free LLM key (Gemini or Groq).

```bash
git clone https://github.com/Mr-centurion/signal-stack.git
cd signal-stack

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # then edit .env and add your keys
```

Get free keys:
- Gemini: https://aistudio.google.com
- Groq: https://console.groq.com

Start the backend (terminal 1):

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Start the dashboard (terminal 2):

```bash
streamlit run frontend/app.py
```

- Dashboard: http://localhost:8501
- API docs: http://localhost:8000/docs

The SQLite database (`signal_stack.db`) is created on first start. No other services are needed.

To explore pre-built data, stop the app, copy data/demo/signal_stack_demo.db over signal_stack.db, then start.

### Environment variables

See `.env.example`. The important ones:

| Variable | Purpose |
|---|---|
| `DEFAULT_LLM_PROVIDER` | `gemini` (default) or `groq` |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Gemini free tier |
| `GROQ_API_KEY`, `GROQ_MODEL` | Groq free tier, used as automatic fallback |
| `USER_AGENT`, `CRAWL_DELAY_SECONDS`, `CRAWL_CONCURRENCY` | Crawler politeness |
| `RESPECT_ROBOTS_TXT` | Keep `true` |
| `SMTP_HOST`, `SMTP_USER`, ... | Optional. If absent, delivery is logged as "skipped: SMTP not configured" |
| `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` | Optional. If absent, Reddit sources are skipped and logged |

Free-tier quotas are low and vary by model and time. The client rotates through several Gemini models and falls back to Groq on quota errors (HTTP 429). Details are in [docs/COST_STATEMENT.md](docs/COST_STATEMENT.md).

## What it does

1. **Company setup.** Enter a name and URL.
2. **Initial research.** Crawls the company's own site (robots.txt respected), extracts a structured profile, and tags each field as a *verified fact* (with a verbatim snippet from the company's own domain) or an *assumption*.
3. **Adaptive interview.** Ten LLM-generated questions built from the profile and previous answers, asked one at a time. Vague answers trigger follow-ups (max 3). Questions can be skipped. Answers can be edited later and the profile updates.
4. **Competitors.** Candidates are proposed as hypotheses, then verified by fetching each competitor's own site and checking for a quoted snippet that shows overlapping service. At most 10 are kept.
5. **Signal Stack.** Sources are discovered in four categories (Customers, Competitors, Market, Internal), each with a stated reason and liveness, robots and relevance checks.
6. **Monitoring.** Approved sources are crawled with ETag support, deduplication and snapshot diffs. Failures are logged and visible.
7. **Analysis and ranking.** Each signal is stored with evidence separate from interpretation, three separate scores (source reliability, evidence strength, strategic relevance) and a weighted priority with a written explanation.
8. **Monday Morning Brief.** Ten sections, validated before saving: citations must exist, claims must be supported by the cited snippet, and generic advice is rejected.
9. **Automation.** A weekly brief job and a monthly source audit, each with failure logging and manual triggers.
10. **Context change.** Editing the business context re-scores sources, recommends removals and additions, and stores a "what changed" report.

## Dashboard pages

| Group | Page | Purpose |
|---|---|---|
| Setup | Register Company | Name and URL; runs research. Also a one-click "Onboard and run". |
| Setup | Company Profile | View and edit the profile; facts vs assumptions; "What changed" panel |
| Setup | Adaptive Interview | One question at a time, progress, skip, edit |
| Intelligence | Signal Stack | Four categories, each source with its reason |
| Intelligence | Source Manager | Approve, reject, add, remove; health, history, duplicates |
| Intelligence | Grounded Feed | Chronological signals with filters (category, competitor, date, relevance, impact, verification) |
| Output | Monday Brief | Report, history, evidence links, action tracking, Markdown and email-ready HTML export |
| Output | Settings & Schedules | Brief time, timezone, monitoring and refresh frequency, monthly audit, run history and failures |

## Demonstration companies

| Company | Industry | Role |
|---|---|---|
| MeetUniversity | EdTech / study-abroad counselling | Primary demo |
| Sweetgreen | Fast-casual restaurants | Stress test (different industry) |
| PostHog | Developer analytics | Stress test |
| Linear | Project management software | Run through "Onboard and run" with no company-specific changes |

Competitor sets between industries do not overlap, and interview questions, sources and briefs differ for each company. Evidence is in `tests/evidence/` (see [docs/TEST_EVIDENCE.md](docs/TEST_EVIDENCE.md)). Source and signal counts change with each crawl, so check the dashboard for current numbers.

Generated briefs are in `reports/` as Markdown and email-ready HTML.

## Automation

- **Weekly Intelligence Brief:** runs source checks, collects, detects changes, analyses, generates and saves the brief, and makes it available for delivery. Default: Monday 06:00 UTC, configurable per company in Settings.
- **Monthly Signal Stack Audit:** checks dead URLs, robots-blocked sources, duplicates, inactive sources and declining relevance, re-runs discovery for new candidates, and produces recommendations (add / remove / keep). Nothing is ever auto-deleted; the user accepts or dismisses each recommendation.
- **Reliability:** jobs are stored in a persistent APScheduler job store and survive restarts. Every run is written to `scheduler_logs`. Failures are caught, logged, and shown in a dashboard banner and the run history table. A failed job does not stop the scheduler.
- **Manual triggers:** buttons in the dashboard and API endpoints for both jobs.

## Tests

```bash
pytest -m "not live"        # fast offline suite (no network or LLM needed)
pytest -m live              # live-site and live-LLM tests (need keys and network)
```

Live tests depend on third-party sites that may return 403/404 or block robots, so they are marked tolerant. The offline suite covers scoring caps, date provenance, event taxonomy, claim and citation validators, profile integrity, competitor integrity, scheduler behaviour (including forced failure and restart persistence), the monthly audit, and stored-source counts.

- **Clean clone (empty DB):** `40 passed, 7 skipped, 5 deselected, 2 warnings in 29.20s` (tests requiring pre-populated data auto-skip with `needs_data`).
- **With demonstration DB (`data/demo/signal_stack_demo.db`):** `47 passed, 5 deselected, 2 warnings in 248.53s` (0 failed, 0 skipped).

## Known limitations

- **Free-tier LLM quotas** are low and forced model rotation. Heavy re-runs may hit limits.
- **Some sources block crawlers.** Those are recorded as `blocked_by_robots` and never bypassed. Reddit needs OAuth credentials; without them it is skipped.
- **Headline-only evidence.** Several news items expose only a headline through free feeds. These are labelled "Headline-only" and capped at lower evidence strength.
- **Small customer-voice samples.** Customer signals come mainly from public App Store reviews of verified competitors and are counted explicitly ("N negative of M total").
- **Trends need history.** Inactivity and declining-relevance checks need several weeks of crawl history; early reports say so.
- **Founder interview & Internal data.** Founder interview completed in UI with dynamic branching; internal data integration demonstrated using sample export (`samples/SAMPLE_crm_export.csv`).
- **Not deployed.** Local setup only.

## Project structure

```
backend/
  api/         REST endpoints
  crawler/     robots-aware crawler, feed ingestion, redirect resolver, diff detector
  models/      SQLAlchemy models
  prompts/     LLM prompt templates
  scheduler/   APScheduler jobs and persistent job store
  services/    research, interview, competitor and source discovery,
               analysis and ranking, brief generation, audit, context change
frontend/      Streamlit dashboard
scripts/       stress test and batch utilities
tests/         pytest suite and tests/evidence/ outputs
reports/       generated briefs (Markdown and HTML)
docs/          technical documentation, cost statement, demo script, test evidence
```

## Documentation

- [Technical documentation](docs/TECHNICAL_DOCUMENTATION.md)
- [Cost statement](docs/COST_STATEMENT.md)
- [Test evidence index](docs/TEST_EVIDENCE.md)
- [Architecture decisions](docs/DECISIONS.md) and [requirements tracker](docs/REQUIREMENTS_TRACKER.md)
