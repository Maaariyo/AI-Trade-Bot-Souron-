# Changelog

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
