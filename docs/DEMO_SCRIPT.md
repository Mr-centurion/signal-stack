# Demo Script (target 9 to 10 minutes)

The video must show the end-to-end workflow from company setup to the final brief. Follow the order below. If you run over 10 minutes, trim the Sweetgreen/PostHog/Linear segment first.

## Before recording

- [ ] Fresh terminal: start backend and Streamlit from a clean start (`uvicorn ...`, `streamlit run ...`).
- [ ] Confirm API keys work and quota is available (do a short test call earlier, not during the recording).
- [ ] Back up `reports/`; do not regenerate briefs while recording.
- [ ] MeetUniversity is already researched and crawled so you do not wait on slow steps; recording live research/crawl for 20 to 30 seconds is enough, then cut to the finished data.
- [ ] Have `SAMPLE_crm_export.csv` ready (clearly fictional).
- [ ] Close other tabs, hide notifications, set browser zoom to 100 to 110%.
- [ ] Open the repo README and `tests/evidence/` in tabs for the closing shot.

## Timeline

| Time | Screen | What to say and show |
|---|---|---|
| 0:00 to 0:40 | README / architecture | One sentence: turns a company into a monitored intelligence system. State the rule: nothing hard-coded, every claim has evidence. Mention free tools only. |
| 0:40 to 1:30 | Register Company, Company Profile | Enter MeetUniversity and its URL. Show research. On the profile, show **verified facts with site snippets** vs **assumptions**. |
| 1:30 to 3:00 | Adaptive Interview | Show question 1 (company-specific). Answer 2 or 3 questions as the founder using public information. Give one vague answer to show the follow-up. **Skip one** question. Edit an earlier answer and show the profile update. Say that the rest were completed earlier. |
| 3:00 to 4:15 | Signal Stack, Source Manager | Four categories. Open a source and read its **reason**. Show competitors with their **verified website snippets** (IDP Education, Leap Scholar, Yocket and others). Show approve/reject, add a source by URL, health and duplicate flags. |
| 4:15 to 5:30 | Sources & Crawler, Grounded Feed | Run a crawl (or show the last run). Show per-source status, a `blocked_by_robots` source, and the error list. Show the **second run adding ~0 new items** (dedup). Open the feed and apply filters (category, impact, verification). |
| 5:30 to 6:30 | One signal | Show **evidence vs interpretation** separately, the three scores (source reliability, evidence strength, strategic relevance), the priority and `why_important`. Say that AI confidence is not proof. |
| 6:30 to 8:00 | Monday Brief | Walk through the sections. Point out: Executive Summary; Customer Signals with counts and verbatim quotes; Competitor Intelligence stating when nothing happened; "No internal data uploaded" (before upload); Opportunities with signal IDs and quoted profile facts; "What We Should Watch" holding items that do not apply to the company's customers; the Source Appendix (link, dates, snippet, scores, headline-only vs body). Show the validator line and action tracking; export Markdown or HTML. |
| 8:00 to 8:45 | Settings & Schedules | Show the registered weekly and monthly jobs and their next run. Click a **manual trigger** and show the new `scheduler_logs` row. Show a **failed run** and the dashboard failure banner. Show the monthly audit report and its recommendations. |
| 8:45 to 9:30 | Internal upload, context change | Upload `SAMPLE_crm_export.csv` (say it is a labelled sample) and show extracted patterns with counts. Then edit the business context and show the **"What changed"** panel: sources recommended for removal, new competitors and sources. |
| 9:30 to 10:00 | Reusability | Show the Sweetgreen, PostHog and Linear briefs and the comparison (different questions, competitors, sources). State that Linear was onboarded with no company-specific changes. Close on the repo and test evidence. |

## Points to state honestly

- Free-tier quotas are low, so the model rotates and falls back to Groq.
- Some sources block crawlers; those are respected and logged.
- Several news items expose headlines only; these are labelled and score lower.
- The internal-data upload uses a fictional sample file.
- The project runs locally and is not deployed.

## After recording

- [ ] Watch it once at 1x to confirm audio and that no keys or personal data appear on screen (check `.env`, terminals, browser autofill).
- [ ] Upload (YouTube unlisted, Google Drive or similar) and open the link in a private window to confirm evaluators can view it.
- [ ] Put the link in the README (`[DEMO_URL]`) and the submission message.
