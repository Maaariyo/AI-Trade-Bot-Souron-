# NiveshCouncil — CLAUDE.md

A personal research app for Indian equities. A factor screen ranks about 5,470 NSE/BSE
stocks using the owner's weights. A 7-agent Claude council (5 analysts who vote, 2
advocates who only debate) reviews the top 50 plus the watchlist, and code computes
one verdict per stock. Full spec: docs/SPEC.md. Read it before every phase and build
only what it specifies.

## Non-negotiables
1. ADVICE ONLY. Write no order-placement code and don't call broker order endpoints.
   Only the owner may change this rule (Phase 8). Never edit it yourself.
2. NO INVENTED NUMBERS. Agents may only use numbers from the data pack, a logged
   calc result, or a web search or web fetch result in the same response.
   services/council/validator.py enforces this. Never weaken it to pass a test.
3. CODE DECIDES. Verdict maths lives only in services/council/aggregate.py: pure,
   deterministic, fully unit-tested, over the 5 analysts only. No LLM call may set
   C, D, K, Q, A, G or the action.
4. POINT IN TIME. Every fundamental row has available_from. Factor code filters
   available_from <= as_of, and tests must cover this. Returns are total returns.
5. LICENSED DATA ONLY. Use the clients in services/ingest/. Never write scrapers for
   nseindia.com, bseindia.com, screener.in or moneycontrol.com. Agents may only
   web_fetch single pages. Never automate the Kite login.
6. AUDIT EVERYTHING. Every council run writes an append-only audit row: data-pack
   hash, prompt-file hashes, requested and served model IDs, raw outputs, verifier
   labels, calc calls and cost. Never update or delete audit rows.
7. BUDGET CAPS. Check the per-run, per-day and per-month $ caps before every LLM
   call; abort the run if a call would exceed them.
8. SECRETS. Keys live in .env (gitignored) and stay on the server. Never ship keys
   to the frontend.
9. DISCLAIMER. Every verdict view shows: "Personal research output. Not investment
   advice. Not from a SEBI-registered Research Analyst or Investment Adviser."
10. GUIDANCE DATA. Management targets come only from mgmt_guidance rows with status
    QUOTE_VERIFIED or HUMAN_REVIEWED. Actuals are computed by code, never by an LLM.

## Claude API rules
- Model IDs and effort levels come from config (claude-opus-5-5,
  claude-sonnet-5-5, claude-haiku-5-5). Never hard-code them in agent code.
- Set output_config.effort on every call.
- Agent JSON goes through structured outputs (output_config.format). Never use a
  forced tool_choice ("any" or "tool"), and never send temperature, top_p or top_k.
- Check stop_reason before reading content. Log the model that actually served
  each call.
- Web search and web fetch versions come from config; docs/VENDORS.md records what
  each model accepts.
- Keep every Haiku prompt under 100K tokens.

## Commands
- make dev       docker compose up (web :3000, api :8000, worker, db)
- make test      pytest + vitest
- make ingest    security master, prices, corporate actions, benchmark,
                 fundamentals, filings, transcripts, news cache
- make screen    recompute factor scores for today
- make council ISIN=INE000X01010   one council run on the standard API
- make nightly   full nightly pipeline on the Batches API

## Layout
- apps/web                Next.js UI
- services/api            FastAPI routers
- services/ingest         data clients (prices, corporate actions, benchmark,
                          fundamentals, filings, transcripts, news cache)
- services/mgmt_guidance  guidance extraction, quote check, review
- services/factors        definitions.yaml, presets.yaml, gates, normalise, compute
- services/council        agents/*.md prompts, schemas, datapack, orchestrator,
                          debate, verifier, validator, aggregate, costs,
                          tools/dcf.py, tools/calc.py
- services/worker         APScheduler jobs
- services/backtest       factor backtests and forward evaluation only (no LLM
                          backtests: the models know events up to Jun 2026)

## Conventions
- Python: type hints, Pydantic v2, ruff + mypy clean. TypeScript: strict.
- Money is stored as integer paise. Display Indian grouping (Rs 1,23,45,678) with
  lakh/crore labels. Store UTC, display IST.
- Validate every agent output against AgentOpinion before storing it.
- Unsure about a SEBI or data-licence question? Stop and ask. Do not guess.

## Definition of done (every task)
Tests pass, types clean, new behaviour has tests, no secrets in the diff,
CHANGELOG.md updated.
