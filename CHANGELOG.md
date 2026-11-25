# Changelog

## 2026-11-25 — Phase 2: factor engine, Screener, Weights Studio

- `services/factors/definitions.yaml`: 27 factors in 7 families, each with a formula, a direction and which stock types it applies to; the canonical fundamentals fields every vendor adapter must map to. `presets.yaml`: the SPEC's Safe, Balanced and Risky weights, default gates and agent weights.
- Scoring engine (`engine.py`, pure functions):
  - Gates run in two steps.
  - Percentiles rank within industry; with fewer than 10 stocks, within sector; then across the whole universe.
  - Values are winsorised at the 1st and 99th percentiles; ties share the average rank; lower-is-better factors are flipped.
  - Governance scores 0 or 100 directly.
  - The composite skips missing factors. Below 70% coverage a stock is marked thin data and left unranked.
  - Ranking is split from weighting, so a slider move costs about 70 ms on 5,500 stocks and a gate change about 400 ms.
- Factor computation (`compute.py`):
  - Prices, the Nifty 500 index and point-in-time fundamentals (`available_from` before the end of the as-of day; historical P/E uses each month-end's public figures).
  - Bank and NBFC ratios, and governance flags (missing until checked).
  - Results stored as screen runs.
- `make screen`; worker job at 23:30 IST; `make ingest ARGS="classification ..."`; securities gain industry, sector and financial type.
- API: `GET /scores`, `POST /scores/preview` (with move against a baseline), `/presets`, `/profiles`, `POST /screen/run`.
- Web:
  - `/screener`: TanStack Table v9 with sorting, search, paging and a passed-gates filter; family heat cells carry ▲ and ▼ as well as colour.
  - `/weights`: preset buttons, sliders, gates, agent weights, live top 20 with moves and timing, saved profiles, and a run-screen button.
- Deviation from SPEC, for review: lenders also skip FCF yield, ROCE and interest cover.
- New dependencies: `numpy`, `pyyaml`, `@tanstack/react-table`.

## 2026-11-25 — Phase 1b: management guidance; D1 and D5 decided (free options)

- Decisions recorded in `docs/VENDORS.md` and SPEC section 0:
  - D1: Upstox for prices, corporate actions and fundamentals (free); Kite kept as the fallback. The Upstox adapter is not built yet.
  - D5: no delisted-history source.
  - Benchmark: the approximate TRI.
  - Transcripts: PDFs the owner downloads.
- Migration 0008: documents, per-page text, `llm_usage` (cost ledger), `extraction_runs` (raw outputs kept) and `mgmt_guidance`.
- `make ingest ARGS="transcript ..."` stores a PDF's text page by page (pypdf). A single owner-supplied URL can be fetched, but never from nseindia.com, bseindia.com, screener.in or moneycontrol.com.
- Extraction: Claude Haiku 5.5 on the Batches API, with structured outputs, effort set from config, and no forced tool use or sampling parameters. It checks `stop_reason` and records the served model. The budget caps and kill switch are checked before anything is sent (`services/llm/costs.py`).
- Quote check: a row is QUOTE_VERIFIED only if its quote is found word for word in the stored text and contains the stated target. Otherwise it stays EXTRACTED with a flag. Tested with planted paraphrases and wrong numbers.
- Review:
  - API: `/guidance` and `/guidance/stats`, plus approve, reject and manual entry.
  - Screen: `/guidance` in the web app.
  - `usable_guidance()` returns only QUOTE_VERIFIED and HUMAN_REVIEWED rows.
  - Free manual path: `make guidance ARGS="pages ..."` then `add`.
- `docs/GUIDANCE.md` runbook. New dependencies: `anthropic`, `pypdf`.

## 2026-11-19 — Phase 1: data layer (code; real data not loaded yet)

- Migrations 0002–0007: securities and status history, watchlist, broker instruments, daily and index prices (integer paise), corporate actions, benchmark, point-in-time fundamentals (a CHECK enforces `available_from` >= period end), filings, news, broker sessions and alerts.
- Security master: imports the NSE main, NSE SME and BSE files the owner downloads, merges them by ISIN, marks delistings without deleting rows, and replaces the ASM/GSM lists with GSM taking precedence.
- Kite Connect: the manual daily login (`/kite/login`, `/kite/callback`, `/kite/status`), tokens kept on the server, rate-limited day candles for stocks and indices, idempotent upserts, and a full re-fetch when Kite re-adjusts past candles.
- Worker: price update at 18:30 IST on weekdays, retried hourly. It raises an alert when there is no Kite session and records the run as skipped at 23:00. `/alerts` lists open alerts.
- Corporate actions and total-return maths (unadjusted or split-adjusted prices), the Nifty 500 TRI import with a labelled approximate fallback, the fundamentals store with point-in-time reads and a call-budget calculator, filings storage, and RSS news (defusedxml, headlines and links only) with daily headline digests.
- Price gates (median traded value >= ₹5 crore over about 3 months, active, not GSM) in `services/factors/gates.py`.
- `make ingest ARGS="..."` CLI; `docs/DATA.md` (steps to load real data); `docs/VENDORS.md` (bake-off and the D1 recommendation).
- New dependencies: `kiteconnect`, `defusedxml`.

## 2026-11-19 — Phase 0: scaffold

- Docker Compose stack with four services: web (Next.js 16, :3000), api (FastAPI, :8000), worker (APScheduler) and db (Postgres 16). Ports bind to localhost only.
- `services/config.py`: settings from `.env`, including model IDs, per-agent effort levels and budget caps ($25/day, $300/month).
- Plain-SQL migrations in `db/migrations/`, applied in order by `services/migrate.py` under an advisory lock. First table: `job_runs`.
- API `GET /health` reports database status, the worker's last heartbeat, the mode and the kill switch. The worker writes a heartbeat every 60 s.
- Web: dark theme, navigation, disclaimer footer, the dashboard's live system status, and placeholders for every SPEC screen. `lib/format.ts` gives Indian digit grouping, lakh/crore labels and IST timestamps; `lib/isin.ts` validates ISIN check digits.
- Makefile: `dev`, `up`, `down`, `test`, `lint`, `fmt` and `migrate`. `ingest`, `screen`, `council` and `nightly` are stubs that exit with an error.
- Tooling: ruff, mypy (strict), pytest with Postgres integration tests in throwaway schemas, ESLint, tsc and vitest. GitHub Actions runs all of them.
- Optional `EXTRA_CA_CERT_FILE` for image builds behind a TLS-intercepting proxy.

## 2026-11-18 — Spec v2

- docs/SPEC.md v2 supersedes v1. Section 0 lists every change and the five open decisions (D1–D5).
- CLAUDE.md added at the repo root. New rules: analysts-only verdict maths, never automate the Kite login, guidance data must be quote-verified, and the Claude API rules.
- No code yet. Phase 0 (scaffold) is next.
