# NiveshCouncil

A personal research app for Indian equities. A factor screen ranks every NSE/BSE stock using your weights. A 7-agent Claude council (5 analysts who vote, 2 advocates who only debate) reviews the top 50 plus your watchlist, and code computes one verdict per stock.

**Personal research output. Not investment advice. Not from a SEBI-registered Research Analyst or Investment Adviser.** The app places no orders.

- Spec: [docs/SPEC.md](docs/SPEC.md). Read section 0 first: changes from v1 and the open decisions.
- Rules for Claude Code: [CLAUDE.md](CLAUDE.md)
- Build status: Phase 1 (data layer) code is in; real data is not loaded yet (see [docs/DATA.md](docs/DATA.md)). Phases 1b–7 follow SPEC section 11.
- Vendors: [docs/VENDORS.md](docs/VENDORS.md)

## Requirements

- Docker with Compose v2
- [uv](https://docs.astral.sh/uv/) and Node.js 22, for tests and linting on the host

## Quick start

```bash
make dev
```

This creates `.env` from `.env.example` if it is missing, then starts four services:

| Service | Address | What it is |
| --- | --- | --- |
| web | http://localhost:3000 | Next.js UI. The dashboard shows API, database and worker status |
| api | http://localhost:8000/health | FastAPI |
| worker | — | APScheduler; writes a heartbeat to Postgres every 60 s |
| db | localhost:5432 | Postgres 16 |

Other commands (`make help` lists them all):

```bash
make test    # pytest against Postgres in Docker, plus vitest
make lint    # ruff, mypy, eslint, tsc
make up      # the stack in the background, waiting until healthy
make down    # stop the stack; the database volume is kept
```

`make ingest ARGS="<command> ..."` loads data; [docs/DATA.md](docs/DATA.md) lists the steps. `make screen`, `make council` and `make nightly` are stubs until their phases land; they exit with an error.

## Behind a TLS-intercepting proxy

If image builds fail with certificate errors, set `EXTRA_CA_CERT_FILE` in `.env` to your proxy's CA certificate. Both Dockerfiles add it to the system trust store during the build; when it is unset they use an empty placeholder and change nothing.

## Layout

```
apps/web/           Next.js UI (8 screens, placeholders until their phase)
services/api/       FastAPI
services/worker/    APScheduler jobs
services/ingest/    data clients (Phase 1)
services/mgmt_guidance/  guidance extraction (Phase 1b)
services/factors/   factor engine (Phase 2)
services/council/   agent council (Phases 3–5)
services/backtest/  backtests and forward evaluation (Phase 7)
db/migrations/      plain SQL, applied in order by services/migrate.py
tests/              pytest
```
