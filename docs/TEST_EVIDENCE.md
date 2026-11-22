# Test Evidence Index

Maps each assignment requirement to the file or screenshot that demonstrates it. Counts change with every crawl, so the dashboard is the source of truth; the numbers below are from the last recorded runs and should be refreshed before submission. `[FILL]` marks values to confirm.

## Test results

| Suite | Command | Result at last run |
|---|---|---|
| Offline | `pytest -m "not live"` | `3 failed, 44 passed, 5 deselected, 2 warnings in 83.83s` |
| Live (network and LLM) | `pytest -m live` | Depends on third-party sites; failures from HTTP 403/404 or robots blocks are marked tolerant (`xfail`) and listed in the README |

## Requirement to evidence

| Requirement | Evidence |
|---|---|
| Company research with facts vs assumptions | `tests/evidence/meetuniversity_research.json`, `unrelated_research.json`; screenshot `screenshots/01_profile_facts.png` |
| Adaptive 10-question interview, different per company | `meetuniversity_questions.json`, `posthog_questions.json`, `sweetgreen_questions.json`, `comparison_diff.json`; screenshot `02_interview.png` |
| Skip, edit, follow-up | `tests/test_phase1.py`; screenshot `03_interview_skip_edit.png` |
| 5 to 10 competitors, verified, no hard-coding | `phase2_meetuniversity_competitors.json`, `phase2_sweetgreen_competitors.json`, `phase2_comparison.json`; `tests/test_competitor_integrity.py` |
| 20+ approved sources for MeetUniversity, with reasons | `phase2_meetuniversity_sources.json`; `tests/test_stored_sources.py` (offline check of stored sources); screenshot `04_signal_stack.png` |
| Four Signal Stack categories | Screenshot `04_signal_stack.png`; per-category counts in `phase6_comparison_table.json` |
| Source Manager (add, remove, approve, health, duplicates) | Screenshot `05_source_manager.png` |
| Crawling, change detection, dedup | `phase3_crawl_run_1.json`, `phase3_crawl_run_2.json`, `phase3_dedup_comparison.json`, `phase3_gate_evidence.json` |
| Real collected records with links and dates | `phase3_sample_signals.json`, `phase6_signals_summary.json`; Grounded Feed screenshot `06_feed.png` |
| Ranking with three separate scores and explanation | `phase4_sample_ranked_signal.json`; `tests/test_scoring.py`; screenshot `07_signal_scores.png` |
| Monday Brief, ten sections, evidence appendix | `reports/*_brief.md` and `.html`; screenshot `08_brief.png` |
| Brief validation (citations, semantic claim check, numbers, mechanism) | `tests/test_specificity_and_semantic_validator.py`, `tests/test_profile_integrity.py`; validator line in each brief |
| Weekly scheduler fires and logs | `tests/test_scheduler.py`; screenshot `09_scheduler_jobs.png` |
| Failed runs logged and visible | `tests/test_scheduler.py::test_scheduler_forced_failure_shielding`; screenshot `10_failure_banner.png` |
| Persistence across restart | `tests/test_scheduler.py::test_persistent_reload_jobs` |
| Monthly source-health audit | `tests/test_monthly_audit.py`; screenshot `11_audit_report.png` |
| Context-change reassessment | `phase6_context_change.json`, `phase8_context_change.json`; screenshot `12_what_changed.png` |
| Two additional companies from other industries | `reports/sweetgreen_brief.md`, `reports/posthog_brief.md`, `phase6_stress_test_report.md` |
| Unseen company, no manual configuration | `reports/linear_brief.md` |
| Internal upload and pattern extraction | `tests/test_internal_pattern_extraction.py` (uses a `SAMPLE_` file); screenshot `13_internal_patterns.png` |
| Evidence caps, date provenance, taxonomy | `tests/test_scoring.py`, `tests/test_dates_and_labels.py` |
| Free tools only | [COST_STATEMENT.md](COST_STATEMENT.md) |

## Evidence files in `tests/evidence/`

Phase 1: `meetuniversity_research.json`, `meetuniversity_interview.json`, `meetuniversity_questions.json`, `posthog_questions.json`, `sweetgreen_questions.json`, `unrelated_research.json`, `unrelated_interview.json`, `comparison_diff.json`
Phase 2: `phase2_meetuniversity_competitors.json`, `phase2_meetuniversity_sources.json`, `phase2_sweetgreen_competitors.json`, `phase2_sweetgreen_sources.json`, `phase2_comparison.json`
Phase 3: `phase3_crawl_run_1.json`, `phase3_crawl_run_2.json`, `phase3_dedup_comparison.json`, `phase3_gate_evidence.json`, `phase3_sample_signals.json`
Phase 4: `phase4_brief_v2.md`, `phase4_brief_export.md`, `phase4_brief_export.html`, `phase4_meetuniversity_brief.json`, `phase4_sample_ranked_signal.json`
Phase 6 and 8: `phase6_comparison_table.json`, `phase6_context_change.json`, `phase6_signals_summary.json`, `phase6_stress_test_report.md`, `phase8_context_change.json`

Some early evidence files were produced before later quality fixes (for example, test-fixture interview answers and earlier brief versions). The current briefs in `reports/` are the authoritative output.

## Known gaps in the evidence

- **Founder interview:** Completed directly in the UI dashboard (with one question skipped to verify adaptive branching). Real answers are recorded into the verified profile and incorporated into executive intelligence synthesis.
- **Internal data:** Completed via dashboard upload of `samples/SAMPLE_crm_export.csv`, parsing customer retention and account status into the signal engine.
- **Early evidence versions** of briefs and sources were generated before later fixes; use the files under `reports/` for the final output.

## Screenshots to capture

Save in `screenshots/` using the names above (13 images). Take them from a fresh app start and check that no API keys or personal data are visible.
