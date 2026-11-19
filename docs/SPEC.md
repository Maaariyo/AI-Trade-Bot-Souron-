# NiveshCouncil: 7-Agent Indian Equity Advisor — Build Spec v2

18 Nov 2026 · @FMS Delhi · Supersedes v1 (same date)

Claude Code: read this whole file and `/CLAUDE.md` before every phase. Build only what this file specifies.

## 0. Changes from v1

v1's maths and cost arithmetic were correct. Its success test, three data sources and several API details were not. Every change below is already written into the sections that follow.

| # | Area | v1 | v2 decision | Why |
| --- | --- | --- | --- | --- |
| 1 | Success test | BUY and ACCUMULATE beat the Nifty 500 TRI after 200 verdicts | The council must beat the factor screen on the same stocks and dates (incremental IC), over at least 24 monthly evaluation dates | v1 could not tell the council apart from the free factor screen, and 200 verdicts are only 3–4 dates |
| 2 | Who votes | C, D and K over all 7 agents | Over the 5 analysts only. The 2 advocates debate and are shown and logged, but do not vote | The advocates' mandates force them to the extremes, which inflates D by design |
| 3 | Verifier penalty | v = w·c·(1 − 0.5f); Q uses w·c | v = w·c·(1 − f); an agent with f > 0.5 is dropped; Q uses v | An agent with every claim false kept half its vote, and a penalty could raise Q |
| 4 | Validator | Every number must match a pack field | Dates, fiscal periods and durations are exempt; derived numbers must come from a `calc` tool; each agent gets its own stance bands | v1 would reject valid claims such as "4 of 7 since FY22" |
| 5 | Prices | Kite Connect only | Kite, with a daily login step, plus a vendor bake-off in Phase 1 for delisted history, dividends and the TRI | Kite needs a 2FA login every day, has no delisted history and no dividends |
| 6 | Benchmark | Nifty 500 TRI, with no source named | The TRI comes from a licensed source; stock returns are total returns | v1 compared price returns against a total-return index |
| 7 | Fundamentals | The whole universe, weekly | Price-based gates run first; fundamentals are pulled only for stocks that pass | The ₹399 fallback plan covers about a fifth of the calls needed |
| 8 | Management scorecard | No data source | New Phase 1b: transcript ingest and guidance extraction, with a verbatim-quote check and human review | The guidance data did not exist anywhere in v1 |
| 9 | Cost | $131–181 a month | Plan for $250 a month with a hard cap of $300; a search budget and effort level per agent | v1's search assumptions contradicted its agent table, and it ignored thinking tokens |
| 10 | Stack | TimescaleDB, Celery, Redis, pgvector | Postgres, plus an APScheduler worker; pgvector deferred | One user and about 6.8M price rows |
| 11 | Claude API | `web_search_20260318`; "JSON output" | `web_search_20260209` (check Haiku), structured outputs, no forced `tool_choice`, no `temperature` | Current API documentation |
| 12 | Universe count | 5,466 | About 5,470 (the cited parts sum to 5,468) | Arithmetic |

### Open decisions for the owner

Defaults are taken so the build can proceed. Change one before the phase that needs it.

| # | Decision | Default | Needed by |
| --- | --- | --- | --- |
| D1 | Price vendor | Kite Connect with a daily login, unless the Phase 1 bake-off finds a vendor that also covers delisted names, dividends and the TRI | End of Phase 1 |
| D2 | Advocates in C | Excluded. Phase 7 tests including them | Phase 5 |
| D3 | Evaluation date | First trading day of each month | Phase 7 |
| D4 | Budget caps | $300 a month, $25 a day | Phase 4 |
| D5 | Source for delisted price history | None chosen. This is a licence question: Claude Code must stop and ask | Phase 1 |

## 1. Red flags: read before you build

Build v1 as a personal, advice-only research tool. Once it shows stock calls to anyone else, you need SEBI registration, and nothing in this spec gets around that. Each flag below is already handled somewhere in the design.

| # | Flag | Fact | What this spec does |
| --- | --- | --- | --- |
| 1 | Giving stock calls to others needs SEBI Research Analyst (INH) registration | You cannot recommend securities or publish research on them unless registered as an RA ([ComplianceCalendar](https://www.compliancecalendar.in/learn/sebi-latest-amendments-for-research-analysts)). An AI cannot hold the licence, and the regulated entity stays accountable for AI output. Since January 2025, RAs have had to tell clients how they use AI ([TaxGuru](https://taxguru.in/?p=1045785)). Screenshots in WhatsApp groups, LinkedIn or YouTube count as showing others. | v1 has one user. A "publish" mode sits behind a compliance gate that needs a named human RA to sign off. |
| 2 | Sizing positions for other people is Investment Adviser (INA) territory | Personalised advice is a separate SEBI licence from research calls. | The allocation suggestion only appears in personal mode. |
| 3 | Auto-trading falls under the retail algo framework | The framework has been mandatory since 1 Apr 2026. It requires a static IP, OAuth with 2FA each session, and an exchange algo ID on every order. Strategies above 10 orders/second must be registered, and black-box algos can only be offered by RAs ([Tradejini](https://www.tradejini.com/blogs/what-sebis-new-algo-trading-rules-mean-for-you)). | v1 places no orders. Phase 8 (optional) is for personal use only. |
| 4 | Showing exchange data requires a licence | NSE has sent cease-and-desist notices to apps that used unlicensed data. Licensed feeds come from 30+ authorised vendors ([YourStory](https://yourstory.com/2022/10/exclusive-nse-issues-cease-desist-notices-to-stock-gaming-apps)). yfinance limits itself to research and educational use ([Tapetide](https://tapetide.com/compare/best-api-indian-stock-market-data)). | Licensed APIs only. No bulk scraping of nseindia.com or bseindia.com. |
| 5 | "All Indian stocks" means about 5,470 unique equities | As of 18 Sep 2026: NSE main board 2,578, NSE SME 572, BSE active 4,768, with 2,450 listed on both. Those parts sum to 5,468; the source states 5,466. BSE also has 1,228 suspended securities ([Multibagg](https://www.multibagg.ai/feeds/screener-all-nse-bse-stocks-cmudzc8ty000009gm1mk1h3en)). Running all 7 agents on every stock costs $1,651–7,868 per sweep (see Cost). | Two stages: a quant screen scores every stock, then the agents debate only the top 50 plus your watchlist. |
| 6 | Your 7 thinkers mix two different things | #1 and #2 are risk appetites. #3 to #7 are ways of analysing a company. "Advanced on thought" (#3) has no definition, and #4 and #5 both cover news. | 5 analysts who vote, plus 2 advocates who argue over the analysts' evidence but do not vote. #3 becomes the Deep Reasoner. #4 owns all news and #5 owns the business and its peers. |
| 7 | Seven agents on one base model are not seven independent opinions | They share training data and blind spots, so when they agree, they look more certain than they are. | Round 1 is blind. Dissent is forced. A verifier checks claims. A measured consensus score can return "No consensus". |
| 8 | LLMs make up numbers | Hallucinated financial figures are the most common way these tools fail. | Agents may only use numbers from the data pack, a `calc` result or a fetched source, and a validator rejects anything else. Code computes the final verdict, not an LLM. |
| 9 | You can't honestly backtest the LLMs before mid-2026 | The current Claude models' training data runs to June 2026 ([Claude models](https://platform.claude.com/docs/en/models/overview)), so they already "know" those outcomes. | Backtest only the factor engine. Judge the agents on forward paper trading. |
| 10 | A score is not a probability, and a few months prove nothing | "+29 conviction" only ranks stocks until it is checked against actual returns. With about 50 stocks per date, detecting a realistic IC of 0.05 needs about 33 independent dates. | The track record tests the council against the factor screen over at least 24 monthly dates. Thresholds are re-tuned only after that. |
| 11 | SEBI's AI rules are still coming | On 14 Nov 2026 the SEBI chair said detailed AI guidelines are coming, covering disclosure, accountability and human-in-the-loop ([Angel One](https://www.angelone.in/news/market-updates/sebi-to-issue-ai-usage-guidelines-for-capital-markets-sebi-chairman-tuhin-kanta-pandey)). The 2025 draft proposed keeping model inputs and outputs for at least 5 years ([Telangana Today/PTI](https://telanganatoday.com/sebi-proposes-ai-ml-usage-norms-to-protect-investors)). | An audit log that can't be edited, kept for 5 years. A kill switch. A human approval step before anything is shared. |
| 12 | The council may add nothing over the screen | The council only sees the factor engine's top 50, so a good track record could come entirely from the free screen. | Every council metric is reported next to the factor-only baseline on the same stocks and dates. |

## 2. What it does and v1 scope

Every night, NiveshCouncil scores every listed Indian equity using your weights. The top 50, plus your watchlist, go to a 7-agent council. The agents debate, and code turns the five analysts' final scores into one quantified verdict per stock.

**User:** just you. Treat it as a research cockpit, not a signal service.

**In v1**

- A security master of NSE and BSE equities, keyed by ISIN
- End-of-day prices nightly, corporate actions and dividends, a total-return benchmark, fundamentals weekly, and filings and news during the day for the watchlist
- Management guidance extracted from earnings-call transcripts, with every quote checked against its source
- A factor engine with your weights, presets and hard gates
- The 7-agent council: a blind round, cross-examination, a verifier, and a final number computed by code
- A verdict page with all 7 assessments, the debate, the evidence and the final number
- A track record (paper trading) that compares the council with the factor screen, an audit log and cost caps

**Not in v1:** placing orders, F&O, more than one user, native mobile apps (the web app works on phones), intraday signals.

### Success test

The unit of evaluation is one (ISIN, evaluation date) pair. On each evaluation date (default: the first trading day of the month), take each stock's latest valid verdict as of the previous close. Re-running a stock within the same month does not create a new observation.

- **Entry and exit.** Enter at the next trading day's open, plus 0.2% slippage and full costs (brokerage and STT). Exit at the close at the end of the horizon. Dividends are reinvested on the ex-date, so every stock return is a total return.
- **Primary test (council versus screen).** Over at least 24 monthly evaluation dates, the mean per-date Spearman IC of conviction C against 1-month forward excess total return beats the IC of the factor composite S on the same stocks and dates. The paired t-statistic on the per-date difference must be at least 2.
- **Secondary test (does it make money).** An equal-weight monthly basket of BUY and ACCUMULATE calls beats both the Nifty 500 TRI and an equal-weight basket of the same month's top-50 factor names, after costs.
- **Interim read at 12 dates.** Directional only; make no "it works" claim. If incremental IC is at or below 0 with t ≤ −1, move the council to the Lean setup or stop it.

Statistical power, so expectations are set before launch: one date's IC across about 50 stocks has a standard error of about 0.14. Reaching t = 2 needs about 13 dates for a true IC of 0.08, 33 for 0.05 and 91 for 0.03. Monthly dates therefore detect only a large edge within two years.

## 3. System architecture

```
Licensed APIs ──> services/ingest ──> Postgres
  (prices, corporate actions,            │
   benchmark, fundamentals,              ▼
   filings, transcripts, news)   Stage 1: factor engine (code, every stock)
                                   gates ─> sector percentiles ─> composite S
                                         │
                                         ▼
                         council list: top 50 + watchlist + event-triggered
                                         │
                                         ▼
                      data pack per stock (JSON, hashed)
                                         │
                                         ▼
                  Stage 2: council (LLM). Round 1 blind ─> verifier ─>
                  Round 2 cross-examination ─> Round 3 if D > 35
                                         │
                                         ▼
                  aggregate.py (code): C, D, K, Q, action, allocation
                                         │
                     ┌───────────────────┼───────────────────┐
                     ▼                   ▼                   ▼
                 web UI           append-only audit      track record
```

Only Stage 2 calls an LLM, and only for the shortlist. The number on the verdict card comes from `aggregate.py`, which is plain code.

## 4. Data layer and internet access

The app gets to the internet in two ways: scheduled pulls from licensed data APIs, and Claude's server-side web search and web fetch inside agent calls. Web search costs $10 per 1,000 searches plus tokens. Web fetch costs only the tokens of the fetched page ([Claude pricing](https://platform.claude.com/docs/en/about-claude/pricing)).

| Data | v1 source, then fallback | Cost | Refresh | Note |
| --- | --- | --- | --- | --- |
| Prices: daily candles, live ticks, indices | Zerodha Kite Connect, unless the Phase 1 bake-off picks another vendor (D1) | ₹500/month per app. The free Personal plan has no market data ([Zerodha](https://support.zerodha.com/category/trading-and-markets/kite-api/articles/what-are-the-charges-for-kite-apis)) | Daily candles at 18:30 IST; live ticks for the watchlist | The access token expires every morning and needs your login with 2FA. Never automate that login. See "Kite daily login" below. |
| Corporate actions and dividends | Fundamentals vendor if it has them; otherwise chosen in the bake-off | Vendor plan | Daily | Needed for total returns. Price candles leave out dividends. |
| Benchmark | Nifty 500 TRI from NSE Indices or a licensed vendor | Check the licence | Daily | Fallback only if no licensed TRI exists: Nifty 500 price index plus the published index dividend yield ÷ 12 each month. The UI must label that fallback as approximate. |
| Delisted price history | Not chosen (D5) | Unknown | One-time backfill | Needed for a backtest without survivorship bias. This is a licence question: stop and ask. |
| Fundamentals: P&L, balance sheet, cash flow, ratios, shareholding | Tapetide Pro+, then EODHD | ₹1,499/month, then $59.99/month ([Tapetide comparison](https://tapetide.com/compare/best-api-indian-stock-market-data), prices checked 24 Oct 2026) | Weekly, and when results are filed | Only for stocks that pass the price gates. Tapetide's `available_from` dates keep backtests honest. Tapetide wrote that comparison, so check its claims yourself. IndianAPI.in's ₹399 plan (5,000 requests/month) is dropped as a full-universe option. |
| Filings: results, board meetings, pledges, auditor changes, rating actions | The fundamentals vendor's feed. Agents web-fetch single filing pages. | Tokens only | Every 30 min in market hours | Read one page at a time. Never crawl. |
| Earnings-call transcripts and investor presentations | Exchange filings (PDF links from the filings feed) | Tokens for extraction (see Cost) | Each quarter, plus a one-time backfill | Phase 1b turns them into the `mgmt_guidance` table. |
| News | Publisher RSS for the 30-minute watchlist polling; Claude web search once per stock per day | RSS is free; $0.01 per search | One digest per stock per day for the council list and watchlist | Store summaries and links, not full articles. |
| Management records: annual reports, director profiles, pay, SEBI orders | Annual-report PDFs from filings; web search of sebi.gov.in and rating agencies | Tokens and searches | Each annual report, plus quarterly checks | Agent 7 gets relevant sections, never a whole report. |
| Industry and macro | Web search of rbi.org.in, mospi.gov.in, ministry sites and industry bodies | About 3 searches per sector per week | Weekly per sector | One sector pack, shared by every stock in the sector. |

**Phase 1 vendor bake-off.** Score each candidate vendor on six criteria and record the result in `docs/VENDORS.md`: adjusted daily prices for all active equities; dividends and corporate actions; delisted history; an API that runs unattended without a daily login; a licence that covers personal research; and `available_from` dates on fundamentals. Do not sign up for anything or pay; list the facts and let the owner decide.

**Kite daily login.** The nightly job runs only with a valid access token. The UI shows a "Connect Kite" banner until you log in that day. If no token exists by 23:00 IST, the run is skipped and the dashboard raises an alert. Check Zerodha's current rules in Phase 1 and record them in `docs/VENDORS.md`.

**Security master.** One row per ISIN, merging the NSE and BSE listings. Flag SME, suspended and surveillance (ASM/GSM) status. Expect about 5,470 active equities, and keep delisted names in history so backtests aren't skewed by survivorship.

**Search budget per agent.** Each agent's web search tool sets `max_uses`: News 8, Management 4, Company & Peer 2, Deep Reasoner 1, Industry 0 (it reads the weekly sector pack), advocates 0. That is 15 at most per stock, against 25 in v1.

**Shared news cache.** Pull each council-list or watchlist stock's news once a day into a cache that every agent reads. The News agent can still search live within its budget.

**Domain allowlist for agent search.** Pass it as the web search tool's `allowed_domains`: sebi.gov.in, rbi.org.in, bseindia.com, nseindia.com, mospi.gov.in, pib.gov.in, economictimes.indiatimes.com, livemint.com, business-standard.com, thehindubusinessline.com, moneycontrol.com, crisil.com, icra.in, careratings.com, plus the company's investor-relations domain. One request can't carry both `allowed_domains` and `blocked_domains`; the API returns an error ([web search docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool)).

**Web fetch rules.** Web fetch only opens URLs that already appear in the conversation ([web fetch docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-fetch-tool)), so the data pack must list every filing and investor-relations URL an agent may need. nseindia.com pages build their content with JavaScript and block automated clients, so expect fetches there to fail. Prefer BSE's filing PDF links.

## 5. Stage 1: the user-weighted factor engine

Every stock gets a composite score from 0 to 100, built from factors you weight. Hard gates remove untradeable stocks first, and no weighting can bring a stock back past a gate.

**Hard gates** (pass or fail; you can edit them), run in this order:

1. **Price gates**, from prices and the security master, before any fundamentals call: active and not suspended; not under GSM (ASM exclusion is optional); median daily traded value over 3 months of at least ₹5 crore.
2. **Fundamental gates**, only for stocks that pass the price gates: market cap of at least ₹500 crore; at least 8 quarters of financials.

Phase 1 records the number of stocks that pass the price gates here, along with the fundamentals vendor calls that number implies (stocks × endpoints × 4.3 refreshes a month).

**Measured:** not yet. It needs the first real security-master import and price backfill (`docs/DATA.md` steps 1, 3 and 4).

**Factor families and preset weights (0–10)**

| Family | Factors | Better when | Safe | Balanced | Risky |
| --- | --- | --- | --- | --- | --- |
| Value | P/E vs own 5-yr median, EV/EBITDA, FCF yield | Cheaper | 8 | 6 | 3 |
| Quality | ROCE, ROE, debt/equity, interest cover, CFO/PAT | Higher (leverage lower) | 9 | 7 | 5 |
| Growth | 3-yr revenue CAGR, 3-yr EPS CAGR, last 4 quarters YoY | Higher | 4 | 6 | 9 |
| Momentum | 12-1 month return, price vs 200 DMA, strength vs Nifty 500 | Higher | 2 | 5 | 9 |
| Risk | 1-yr volatility, beta, max drawdown, promoter pledge % | Lower | 9 | 5 | 2 |
| Ownership | Promoter holding change QoQ, FII + DII change QoQ | Rising | 4 | 4 | 5 |
| Governance | Auditor resignation, qualified opinion, SEBI order, rating downgrade | None present | 10 | 8 | 6 |

Banks and NBFCs swap in different factors: P/B, GNPA and NNPA, CASA ratio, capital adequacy and credit cost replace EV/EBITDA, debt/equity and CFO/PAT. Governance flags score 0 if present and 100 if clean.

**Normalisation.** Rank each factor within its sector. If a sector has fewer than 10 stocks after the gates, rank within its parent industry group instead. Winsorise at the 1st and 99th percentiles, convert to a percentile from 0 to 100, and flip the sign wherever lower is better.

```latex
S_i = \frac{\sum_{k \in A_i} w_k \, p_{i,k}}{\sum_{k \in A_i} w_k}
```

Here p is stock i's sector percentile on factor k, w is your weight, and A\_i is the set of factors that have data for stock i. A missing factor drops out of both sums. If the stock's available weight falls below 70% of the total, it gets a "thin data" badge and can't join the council list.

**Point in time.** Every fundamental row carries an `available_from` date, and the engine only uses rows where `available_from <= as_of`. A backtest can never see results before they were filed.

**Council list.** The top 50 by composite after gates, plus your watchlist, plus any stock in the top 200 with a material event in the last 24 hours: results, a rating action, a large order, or a management exit.

**Agent weights.** You also weight the seven agents, from 0 to 3 (default 1). Stage 2 uses the five analysts' weights in the verdict; the advocates' weights apply only if Phase 7 shows they should vote (D2).

## 6. Stage 2: the 7-agent council

Five analysts each own one way of looking at the company and vote on the verdict. Two advocates represent the risk appetites: they rate the stock, cross-examine the analysts and are shown on the page, but they do not vote. Your #1 and #2 become the advocates; #3 to #7 become the analysts.

| Your # | Agent | Role | Mandate | Reads | Search `max_uses` | Effort (start) | Model: Premium / Standard |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Risk-On Advocate ("slightly risky") | Advocate, no vote | Makes the strongest case for the upside. Accepts volatility and drawdowns up to 30%. Horizon of 6–12 months. | Data pack, plus all analyst outputs in Round 2 | 0 | low | Sonnet 5.5 / Haiku 5.5 |
| 2 | Capital Preserver ("slightly safe") | Advocate, no vote | Makes the strongest case for the downside: balance sheet, valuation cushion, liquidity, governance. Asks how you lose 25%. | Data pack, plus all analyst outputs in Round 2 | 0 | low | Sonnet 5.5 / Haiku 5.5 |
| 3 | Deep Reasoner ("advanced on thought") | Analyst | Values the company from first principles. A reverse DCF shows the growth the price assumes. Base rates show how often companies achieve that growth. Bull, base and bear scenarios carry probabilities that sum to 1. | Data pack, plus the `dcf` and `calc` client tools | 1 | high | Opus 5.5 / Sonnet 5.5 |
| 4 | News & Catalyst Analyst | Analyst | Covers the last 90 days of news and filings. Separates events that change earnings from noise. Builds a catalyst calendar: results date, AGM, ex-dates, policy decisions. | News cache, plus live search | 8 | medium | Sonnet 5.5 / Haiku 5.5 |
| 5 | Company & Peer Analyst | Analyst | Covers the business model, segment mix, market-share trend and moat. Compares 3–5 rivals on growth, margins, ROCE and valuation. | Data pack and peer packs | 2 | medium | Sonnet 5.5 / Haiku 5.5 |
| 6 | Industry & Macro Analyst | Analyst | Covers market size and growth, where the sector is in its cycle, regulation, input costs, rate sensitivity and the sector index trend. | Weekly sector pack | 0 | medium | Sonnet 5.5 / Haiku 5.5 |
| 7 | Management & Governance Analyst | Analyst | Compares guidance with delivery over 3–5 years. Checks the return on new capital, the M&A record, pledges, related-party deals, auditor history, pay against profit, legal and SEBI matters, and insider trades. | `mgmt_guidance` rows, relevant annual-report sections, filings, plus search | 4 | medium | Sonnet 5.5 / Haiku 5.5 |
| — | Verifier | Checker | Labels each key claim verified, unverified or false against the pack, `calc` results and fetched sources. | All Round 1 outputs and their sources | 0 | low | Haiku 5.5 / Haiku 5.5 |
| — | Chair | Writer | Writes the summary and the dissent note. Cannot change any number. | Final outputs and the computed verdict | 0 | low | Sonnet 5.5 / Sonnet 5.5 |

Effort levels are starting values; Phase 4 tunes them. Every call sets effort explicitly, because the defaults differ by model.

**Management scorecard (Agent 7).** Built from the `mgmt_guidance` table (Phase 1b), never from the agent's own reading of a transcript. Each row holds the date, the metric (revenue, margin, capex, debt), the target, the verbatim quote, the source URL and page, the actual result (computed by code from fundamentals), the gap and a status:

- `EXTRACTED`: an LLM pulled the row from a transcript or presentation.
- `QUOTE_VERIFIED`: code confirmed the quote appears verbatim in the source text, and the target number appears in the quote.
- `HUMAN_REVIEWED`: you checked it.

The delivery ratio (targets met ÷ targets given) uses only `QUOTE_VERIFIED` and `HUMAN_REVIEWED` rows, and the card shows how many are human-reviewed. That ratio drives the score, not the tone of management commentary.

**Output schema** (every agent, every round)

```json
{
  "agent_id": "management_governance",
  "isin": "INE000X01010",
  "as_of": "2026-11-18",
  "round": 1,
  "score": 10,
  "rating_0_10": 5.5,
  "stance": "HOLD",
  "confidence": 0.8,
  "horizon_months": 12,
  "thesis": "Max 120 words",
  "key_points": [
    {
      "claim": "Met 4 of 7 margin targets since FY22",
      "direction": "-",
      "evidence": [
        {"type": "data", "field": "mgmt.guidance.margin_hits"},
        {"type": "data", "field": "mgmt.guidance.margin_targets"},
        {"type": "calc", "id": "calc_2"},
        {"type": "url", "url": "https://..."}
      ]
    }
  ],
  "risks": ["..."],
  "would_change_my_mind": ["..."],
  "data_gaps": ["..."]
}
```

`score` is an integer from −100 (strong sell) to +100 (strong buy). `rating_0_10 = (score + 100) / 20`, for display only. The ISIN above is a placeholder. The schema is enforced with structured outputs (`output_config.format`), never with a forced tool call.

**Per-agent stance bands** (on the agent's own integer score)

| Score | Stance |
| --- | --- |
| +40 to +100 | BUY |
| +15 to +39 | ACCUMULATE |
| −14 to +14 | HOLD |
| −39 to −15 | REDUCE |
| −100 to −40 | AVOID |

**`calc` client tool.** A deterministic expression evaluator over data-pack field paths. Allowed operations: + − × ÷, `pct_change`, `ratio`, `cagr`, `mean` and `median`. It returns a value and an id such as `calc_2`, and every call is logged. It cannot run arbitrary code.

**Validator rules** (enforced in code, not in the prompt)

1. Every number in `claim` or `thesis` must match, within 0.5%, a pack field cited in that point's evidence, a cited `calc` result, or text from a web search or web fetch result in the same response. If not, the output is rejected and retried once, then marked invalid.
2. Exempt from rule 1: calendar years (1990–2035), fiscal-period labels (FY24, Q2FY26, H1FY25), durations with a unit (12 months, 3–5 years), and the output's own `score`, `confidence` and `horizon_months`.
3. `stance` must match the per-agent stance band.
4. At most 6 key points, with at least 1 risk and 1 "would change my mind".
5. The Deep Reasoner's scenario probabilities must sum to 1 (±0.001), and its DCF numbers must come from the `dcf` tool.

**Prompt rules**

- Each agent sticks to its own lens. The Management analyst doesn't comment on valuation.
- Round 1 is blind: each agent scores before it sees anyone else's output.
- System prompts live in `services/council/agents/*.md` under version control, and every run logs their hashes.

## 7. Debate and the final quantified verdict

The council argues for up to three rounds, then code turns the five analysts' post-debate scores into one number. No LLM sets the final number, so a single hallucination can't decide a verdict.

```
data pack ─> Round 1 (7 agents, blind, parallel) ─> verifier labels claims
          ─> Round 2 (cross-examination, all 7)
          ─> D over analysts > 35 ? ── yes ─> Round 3 (3 most contested claims)
                                   └─ no ──┐                │
                                           ▼                ▼
                                   aggregate.py (5 analysts) ─> K < 0.5 ? NO CONSENSUS : action band
                                           ─> Chair writes summary and dissent note
```

**Steps**

1. **Data pack (code).** Build one JSON pack per stock and hash it. It holds factor percentiles, 5 years of financials, the peer table, a filings digest with URLs, a news digest, and the management scorecard. Keep it under 60K tokens so no Haiku prompt passes 100K.
2. **Round 1, blind, in parallel.** All 7 agents score the stock independently.
3. **Verifier (Haiku 5.5).** Checks every key claim against the pack, `calc` results and fetched sources, and labels each one verified, unverified or false.
4. **Round 2, cross-examination.** Each agent sees the other six outputs, anonymised as A to F, with the verifier labels. It rebuts up to 2 specific claims, then keeps or revises its score with a reason. An advocate who disagrees with the analysts' majority must attack the majority's two strongest claims.
5. **Round 3, only when D > 35** (D over the 5 analysts). Debate only the three most contested claims, then take final scores.
6. **Aggregation (code)** produces the verdict. The **Chair (Sonnet 5.5)** writes the summary and the dissent note, and can't change any number.

**The maths** (over the 5 analysts; the advocates never enter these sums)

```latex
v_a = \begin{cases} w_a \, c_a \, (1 - f_a) & \text{if the output is valid and } f_a \le 0.5 \\ 0 & \text{otherwise} \end{cases}
```

```latex
C = \frac{\sum_a v_a s_a}{\sum_a v_a} \qquad D = \sqrt{\frac{\sum_a v_a (s_a - C)^2}{\sum_a v_a}} \qquad K = 1 - \frac{D}{100} \qquad Q = K \cdot \frac{\sum_a v_a}{\sum_a w_a}
```

Here s is the post-debate score, f is the share of an agent's key claims the verifier marked false, C is conviction (−100 to +100), D is dispersion, K is consensus (0 to 1), and Q is verdict confidence. Q uses v, so a verifier penalty always lowers it. Confidence c starts as each agent's own estimate. Calibration replaces it only once Phase 7 has at least 300 outcomes per agent: a two-parameter logistic fit of hit rate on stated confidence, pooled across agents until then. With fewer than 3 analysts at v > 0, the verdict is INSUFFICIENT EVIDENCE.

**Advocate gap.** G = Risk-On score − Capital Preserver score, shown on the verdict card as a measure of how far apart the bull and bear cases are. It never sets the action.

**Action bands** (starting values; re-tune only after 24 monthly evaluation dates)

| Condition | Action |
| --- | --- |
| Fewer than 3 analysts with v > 0 | INSUFFICIENT EVIDENCE |
| K < 0.5 (D > 50) | NO CONSENSUS: research further, whatever C says |
| C ≥ +40 and K ≥ 0.6 | BUY |
| +15 ≤ C < +40, or C ≥ +40 with K < 0.6 | ACCUMULATE |
| −15 < C < +15 | HOLD |
| −40 < C ≤ −15, or C ≤ −40 with K < 0.6 | REDUCE |
| C ≤ −40 and K ≥ 0.6 | AVOID |

**Suggested maximum allocation** (personal mode only; 0 for HOLD and below, NO CONSENSUS and INSUFFICIENT EVIDENCE)

```latex
A = \min\left(\text{cap},\; b \cdot \frac{C}{100} \cdot \frac{\sigma^{*}}{\sigma_{\text{stock}}}\right)
```

Defaults: b = 5% base allocation, σ\* = 25% annualised target volatility, cap = 8%.

**Historical analog (code, not LLM).** The card shows how stocks in the same composite-score decile did over the next 3 and 6 months, as excess total return over the Nifty 500 TRI, taken from the factor backtest. It is the only return figure on the page, and it comes from data.

**Worked example 1** (made-up numbers, no verifier penalties; σ_stock = 32%)

| Agent | Role | Score s | Confidence c | Weight w | v = w × c | v × s |
| --- | --- | --- | --- | --- | --- | --- |
| Risk-On Advocate | Advocate | +70 | 0.60 | 1.0 | — | — |
| Capital Preserver | Advocate | −20 | 0.70 | 1.0 | — | — |
| Deep Reasoner | Analyst | +35 | 0.65 | 1.5 | 0.975 | 34.125 |
| News & Catalyst | Analyst | +50 | 0.50 | 1.0 | 0.500 | 25.0 |
| Company & Peers | Analyst | +40 | 0.70 | 1.0 | 0.700 | 28.0 |
| Industry & Macro | Analyst | +25 | 0.60 | 1.0 | 0.600 | 15.0 |
| Management & Governance | Analyst | +10 | 0.80 | 1.5 | 1.200 | 12.0 |
| **Analyst total** |  |  |  | **6.0** | **3.975** | **114.125** |

C = 114.125 ÷ 3.975 = +28.71. D = 14.03, so K = 0.860. Q = 0.860 × (3.975 ÷ 6.0) = 0.570. Advocate gap G = +90. **Verdict: ACCUMULATE, conviction +29, consensus 0.86, confidence 0.57.** A = 5% × 0.2871 × 25/32 = 1.12%.

**Worked example 2** (the same, but the verifier marks 25% of the News agent's claims false): v_news = 0.375. C = +28.02, D = 13.72, K = 0.863, Q = 0.554, ACCUMULATE, A = 1.09%.

**Worked example 3** (the same as example 1, but 60% of the Management agent's claims are false, so it is dropped): Σv = 2.775. C = +36.80, D = 8.08, K = 0.919, Q = 0.425, ACCUMULATE, A = 1.44%.

## 8. Screens and layout

The app has eight screens. The Stock Council page is the product: one stock, seven assessments, the debate and the verdict.

| Route | Screen | Contents |
| --- | --- | --- |
| `/` | Dashboard | Nifty 50 and Nifty 500, a sector heatmap, today's verdicts sorted by conviction, watchlist changes, and alerts (rating flips, NO CONSENSUS, cost cap hit, Kite not connected) |
| `/screener` | Universe | Every stock with its composite score, factor percentiles and gates passed; filters; a "Send to council" button |
| `/weights` | Weights Studio | Factor sliders, presets (Slightly Safe, Balanced, Slightly Risky, Custom), gates and agent weights; a live preview of how the top 20 shifts; saved profiles |
| `/stock/[isin]` | Stock Council | See the wireframe below |
| `/runs` | Council runs | The queue, status per round, tokens, searches and $ per run, served model per call, errors, re-run |
| `/track-record` | Track record | Every verdict and what happened next; council IC beside factor-only IC on the same dates, with the paired t-statistic; hit rate and excess return by action band; per-agent calibration; ablations |
| `/audit` | Audit log | Read-only: data-pack hash, prompt hashes, requested and served model IDs, raw outputs, verifier labels, `calc` calls; export |
| `/settings` | Settings | API keys (kept on the server), Connect Kite, schedules, budget caps, the kill switch, and the mode (personal, or publish behind the compliance gate) |

**Stock Council page** (desktop, two columns over full-width tabs)

```
+----------------------------------------------------------------------------+
| < Screener   COMPANY NAME  (NSE: SYMBOL | BSE: CODE)   Sector | Mcap Rs cr |
| Price Rs   1D %   1Y %   Composite 78/100   As of 18-Nov-2026 21:00 IST    |
+-------------------------------+--------------------------------------------+
| VERDICT CARD                  | ANALYSTS (vote)  click to expand           |
|   ACCUMULATE                  |   Deep        +35  ####                    |
|   Conviction   +29 / 100      |   News        +50  #####                   |
|   Consensus K  0.86           |   Company     +40  ####                    |
|   Confidence Q 0.57           |   Industry    +25  ###                     |
|   Max alloc    1.12%          |   Mgmt        +10  #                       |
|   Advocate gap +90            | ADVOCATES (debate only, no vote)           |
|   Analog: decile 9, 6M excess |   Risk-On     +70  #######                 |
|   median / IQR (from backtest)|   Preserver   -20  ##                      |
|   [Re-run] [Watchlist]        |   each: score, stance, thesis, R1->R2 move |
+-------------------------------+--------------------------------------------+
| TABS:  Debate | Evidence | Peers | Management | News | Financials          |
| Debate tab: Round 1 -> Verifier -> Round 2 -> (Round 3) as a timeline;     |
|   each rebuttal: who -> which claim -> verifier label -> score change      |
| Management tab: guidance rows with status (quote-verified / reviewed)      |
+----------------------------------------------------------------------------+
| TOP 3 BULL POINTS    |    TOP 3 BEAR POINTS    |    WHAT WOULD FLIP IT     |
+----------------------------------------------------------------------------+
| Chair dissent note | Disclaimer | Audit ID | model + prompt versions       |
+----------------------------------------------------------------------------+
```

**Weights Studio** (Balanced preset shown)

```
+----------------------------------------------------------------------------+
| PRESET [Safe|Balanced|Risky|Custom]     | LIVE PREVIEW: top 20             |
|                                         |   rank  stock      score  move   |
| FACTOR WEIGHTS (0-10)                   |   1     ........   84     +3     |
|   Value       --o-------  6             |   2     ........   82     -1     |
|   Quality     ----o-----  7             |   ...                            |
|   Growth      ---o------  6             |                                  |
|   Momentum    --o-------  5             | GATES                            |
|   Risk        --o-------  5             |   Liquidity >= Rs 5 cr/day       |
|   Ownership   -o--------  4             |   Mcap >= Rs 500 cr              |
|   Governance  ---o------  8             |   Exclude GSM [x]  ASM [ ]       |
|                                         |   Min quarters of data: 8        |
| ANALYST WEIGHTS (0-3)                   |                                  |
|   Deep 1.5  News 1  Company 1           |                                  |
|   Industry 1  Mgmt 1.5                  |                                  |
| ADVOCATE WEIGHTS (used only if D2 flips)|                                  |
|   Risk-On 1  Preserver 1                | [Save profile]  [Run screen]     |
+----------------------------------------------------------------------------+
```

**UI rules**

- Dark theme by default. Green and red always come with ▲ and ▼, so the direction is still clear to colour-blind users.
- Indian number formatting (₹1,23,45,678) and lakh/crore labels. Timestamps in IST.
- Every verdict view carries the disclaimer, the data timestamp and the audit ID.
- Any figure built on the approximate benchmark fallback is labelled "approx. TRI".
- On phones, the agent strip collapses to a horizontal scroller under the verdict card.

## 9. Tech stack and repo structure

Use one Python backend for data, factors and agents, and a Next.js frontend. Everything runs in Docker Compose on one VPS: four services (web, api, worker, db).

| Layer | Choice | Why |
| --- | --- | --- |
| Frontend | Next.js (App Router) + TypeScript, Tailwind, shadcn/ui, TanStack Table, ECharts | Handles large tables and charts, and Claude Code knows this stack well |
| API | Python 3.12, FastAPI, Pydantic v2 | Same language as the factor and agent code |
| Factor maths | Polars (or pandas), NumPy, SciPy | Fast enough to rank about 5,470 stocks in seconds |
| Jobs | APScheduler in a `worker` container; job state in Postgres | One user and one nightly pipeline need no message broker |
| Database | PostgreSQL 16, plain | 5 years of daily prices for about 5,470 stocks is about 6.8M rows, which plain Postgres handles easily. Add pgvector only if Phase 3 shows Agent 7 needs search across annual reports |
| LLM | Anthropic Python SDK; Message Batches for nightly runs; prompt caching per agent | Batches cost 50% less per token |
| Agent JSON | Structured outputs (`output_config.format`) validated against `AgentOpinion` | Forced `tool_choice` (`any` or `tool`) returns a 400 on Opus 5.5 and Sonnet 5.5, including in batches |
| Web access | Server tools `web_search_20260209` and `web_fetch_20260209` on Opus 5.5 and Sonnet 5.5 | Current documented versions. The docs don't list Haiku 5.5 for them, so Phase 3 checks which version Haiku accepts, falling back to `web_search_20250305` and `web_fetch_20250910` |
| Deep Reasoner maths | Our own `dcf` and `calc` client tools in Python | Deterministic, testable; no arithmetic done by the LLM |
| Broker | Kite Connect via the `kiteconnect` Python client | Data now; orders later, if ever |
| Deploy | Docker Compose on one VPS with a static IP | API orders require a static IP, if you ever place them |

**Claude API rules** (current API behaviour)

- Set `output_config.effort` on every call. Defaults differ by model: Opus 5.5 and Haiku 5.5 default to `medium`, Sonnet 5.5 to `high`.
- Don't send `temperature`, `top_p` or `top_k`; the current API version rejects them. The stability test therefore measures real run-to-run noise.
- Thinking cannot be switched off on Opus 5.5; lower effort instead. Thinking tokens are billed as output.
- Check `stop_reason` before reading content. Opus 5.5 and Sonnet 5.5 calls use server-side fallbacks (`fallbacks: "default"`, beta `server-side-fallback-2026-07-01`); Haiku 5.5 has no server-side fallback, so treat a refusal as an invalid output. Log the model that actually served each call.
- Document citations and `output_config.format` in one request return a 400. If web search plus structured outputs in one call fails in Phase 3, split each agent turn into a research call and a formatting call.
- Prompt caching matches prefixes in the order tools, system, messages, so agents with different system prompts or tools can't share a cached data pack. Caching pays off within one agent from Round 1 to Round 2. For batch rounds, use the 1-hour cache lifetime and confirm hits with `usage.cache_read_input_tokens`; if hits stay at zero, remove caching from the cost model.
- Keep every Haiku prompt under 100K tokens; above that Haiku 5.5 costs $0.50/$2.50 per million instead of $0.10/$0.50.
- Model IDs and effort levels come from config, never from agent code.

```
niveshcouncil/
  CLAUDE.md
  CHANGELOG.md
  docs/SPEC.md                 # this file
  docs/VENDORS.md              # Phase 1 bake-off result
  docker-compose.yml           # web, api, worker, db
  Makefile
  .env.example
  apps/web/                    # Next.js
    app/page.tsx               # Dashboard
    app/screener/page.tsx
    app/weights/page.tsx
    app/stock/[isin]/page.tsx  # Stock Council
    app/runs/page.tsx
    app/track-record/page.tsx
    app/audit/page.tsx
    app/settings/page.tsx
    components/                # verdict-card, agent-card, debate-timeline,
                               # weight-slider, factor-table, analog-chart
  services/
    api/                       # FastAPI routers: universe, scores, council,
                               # runs, audit, settings
    ingest/                    # security_master, prices (kite adapter),
                               # corporate_actions, benchmark, fundamentals,
                               # filings, transcripts, news_cache
    mgmt_guidance/             # extract.py, quote_check.py, review.py
    factors/                   # definitions.yaml, presets.yaml, gates.py,
                               # normalise.py, compute.py
    council/
      agents/                  # risk_on.md, capital_preserver.md,
                               # deep_reasoner.md, news_catalyst.md,
                               # company_peers.md, industry_macro.md,
                               # management_governance.md, verifier.md, chair.md
      tools/dcf.py             # reverse DCF + scenario maths
      tools/calc.py            # whitelisted expression evaluator
      schemas.py  datapack.py  orchestrator.py  debate.py
      verifier.py validator.py aggregate.py     costs.py
    worker/                    # APScheduler jobs
    backtest/                  # factor backtests, analog distributions,
                               # forward tracking and evaluation
  db/migrations/
  tests/
```

## 10. CLAUDE.md

`/CLAUDE.md` at the repo root holds the rules Claude Code follows in every session. It is the source of truth for those rules; this spec does not repeat them.

## 11. Build plan: Phases 0–7, plus 1b and an optional Phase 8

Run the phases in order, each in a fresh Claude Code session. Paste the prompt, review the plan Claude Code proposes, then let it build. Start the next phase only once the current phase's "done when" check passes.

### Phase 0: Scaffold

**Done when** `make dev` starts web, api, worker and db, and `make test` passes.

```
Read CLAUDE.md and docs/SPEC.md. Scaffold the monorepo exactly as in "Tech stack and repo structure": Next.js in apps/web, FastAPI in services/api, an APScheduler worker in services/worker, and Postgres 16, all in docker-compose.yml (four services, no Redis). Add a Makefile with dev/test/ingest/screen/council/nightly targets (stub the last four), ruff, mypy, pytest, vitest, .env.example, CHANGELOG.md, and a GitHub Actions workflow for lint + tests. Propose the plan first, then build. Done when make dev and make test both succeed.
```

### Phase 1: Data layer and vendor bake-off

**Done when** `docs/VENDORS.md` records the bake-off and the D1 decision; the security master holds about 5,470 active ISINs; 5 years of daily prices, corporate actions and dividends are loaded for them; a benchmark series is loaded and labelled licensed or approximate; the number of stocks passing the price gates is written into SPEC section 5; and every fundamental row has `available_from`.

```
Read CLAUDE.md and docs/SPEC.md. Implement services/ingest per SPEC "Data layer and internet access". 0) Write docs/VENDORS.md: score each candidate vendor on the six bake-off criteria, and record Zerodha's current login rules; do not sign up or pay for anything. 1) security_master.py: merge NSE + BSE equity lists by ISIN with flags for SME, suspended and ASM/GSM; keep delisted history. 2) prices.py with a Kite adapter: daily candles plus index candles (Nifty 50, Nifty 500, sector indices), rate-limited, idempotent upserts; the nightly job checks for a valid access token and alerts if there is none; never automate the login. 3) corporate_actions.py and benchmark.py: dividends, splits and bonuses; the Nifty 500 TRI, or the labelled fallback. 4) fundamentals.py: a vendor-agnostic interface with one adapter for <VENDOR>, called only for stocks that pass the price gates; every row stores available_from. 5) filings.py and news_cache.py: one digest per stock per day, storing summary + URL only; RSS for watchlist polling. Test with recorded fixtures, no live calls. Do not write scrapers for exchange websites. For any delisted-history source, stop and ask: it is a licence question.
```

### Phase 1b: Management guidance

**Done when** the `mgmt_guidance` table is filled for 20 test companies; every row either passes the quote check or is flagged; you hand-review 50 rows and agree with at least 90% of them; and the extraction cost is recorded in the Cost section.

```
Read CLAUDE.md and docs/SPEC.md. Implement services/mgmt_guidance and services/ingest/transcripts.py per SPEC "Management scorecard". Ingest earnings-call transcripts and investor presentations from the filings feed's PDF links. extract.py: one LLM call per document on the Batches API, structured output of guidance rows (date, metric, target, verbatim quote, source URL, page). quote_check.py: confirm in code that each quote appears verbatim in the extracted PDF text and that the target number appears in the quote; set status QUOTE_VERIFIED or leave EXTRACTED and flag it. Actuals are computed in code from fundamentals, never by the LLM. review.py plus a small review screen: approve or reject rows, setting HUMAN_REVIEWED. Test the quote check with planted mismatched quotes.
```

### Phase 2: Factor engine, Weights Studio, Screener

**Done when** moving a slider re-ranks the top 20 in under 1 second, and the point-in-time tests pass.

```
Read CLAUDE.md and docs/SPEC.md. Implement services/factors per SPEC "Stage 1". Put factor definitions in definitions.yaml (family, formula, direction, bank/NBFC overrides) and the Safe/Balanced/Risky weights from the SPEC table in presets.yaml. Implement the two-step hard gates, sector-wise winsorised percentile ranks with the parent-industry fallback for sectors under 10 stocks, and the composite S_i with missing-data handling and the 70% coverage rule. Expose GET /scores and POST /scores/preview (weights in the body). Build /screener and /weights per the wireframes. Test normalisation, direction flips, the small-sector fallback, the coverage rule and available_from <= as_of.
```

### Phase 3: One agent end to end

**Done when** the Management agent returns a valid `AgentOpinion` for 5 test stocks; the validator rejects a planted fake number and accepts a valid "Met 4 of 7 margin targets since FY22" claim; and `docs/VENDORS.md` records which web search and web fetch versions Haiku 5.5 accepts.

```
Read CLAUDE.md and docs/SPEC.md. Implement services/council: schemas.py (AgentOpinion, Rebuttal, Verdict per SPEC), datapack.py (build and hash the per-stock pack, under 60K tokens, listing every filing URL), tools/calc.py (whitelisted expression evaluator with logged ids), validator.py (rules 1-5 in SPEC, including the exemptions; retry once, then mark invalid), costs.py (tokens, searches and $ per call, requested and served model), and agents/management_governance.md. Call the model and effort set in config, with structured outputs for the JSON, the current web search tool restricted to the SPEC allowlist with the agent's max_uses, and prompt caching on the pack. Never use forced tool_choice or temperature. Check which web search and web fetch versions Haiku 5.5 accepts and record the result. Add tests: a planted unsupported number is rejected; a valid claim with a fiscal year and pack-backed counts passes; a derived percentage passes only with a calc reference.
```

### Phase 4: All seven agents, Round 1

**Done when** 7 valid opinions come back for each of 10 stocks; a spot-check of 20 outputs finds every agent staying in its lens; and the Cost and latency section holds measured numbers per agent.

```
Read CLAUDE.md and docs/SPEC.md. Add the other six agent prompts, plus verifier.md and chair.md, in services/council/agents/ following the SPEC table (role, mandate, inputs, search max_uses, effort). Implement tools/dcf.py (reverse DCF and bull/base/bear scenarios) and expose it with calc to the Deep Reasoner as client tools; validate that scenario probabilities sum to 1. Run Round 1 in parallel and blind. Add an eval script that runs 10 fixed stocks and reports scores, invalid rate, input, output and thinking tokens, searches, cost, time and served model per agent. Write the measured numbers into SPEC "Cost and latency budget".
```

### Phase 5: Debate, verifier, aggregation, verdict page

**Done when** `aggregate.py` reproduces all three worked examples exactly (example 1: C = +28.71, D = 14.03, K = 0.860, Q = 0.570, ACCUMULATE, A = 1.12%) plus the edge-case tests in the Testing section, and the Stock Council page renders every tab.

```
Read CLAUDE.md and docs/SPEC.md. Implement verifier.py (labels each key claim verified/unverified/false against the pack, calc results and fetched sources), debate.py (Round 2 cross-examination with anonymised peers and forced advocate dissent; Round 3 only when D over the analysts > 35, limited to the 3 most contested claims), aggregate.py (pure functions over the 5 analysts for v_a, C, D, K, Q, INSUFFICIENT EVIDENCE, the action bands, allocation A and the advocate gap G; no I/O), and the Chair summary. Put the three SPEC worked examples and the edge cases in unit tests. Build /stock/[isin] per the wireframe, with analysts and advocates shown separately and a debate timeline that shows each rebuttal, its verifier label and the score change.
```

### Phase 6: Nightly pipeline, cost caps, audit

**Done when** a nightly run on 70 stocks finishes inside the budget cap, every verdict has a complete audit row, and a run without a valid Kite token is skipped with an alert.

```
Read CLAUDE.md and docs/SPEC.md. Implement make nightly as APScheduler jobs: token check -> ingest -> screen -> council list (top 50 + watchlist + event-triggered) -> Round 1 batch -> verifier -> Round 2 batch -> conditional Round 3 -> aggregate -> store. Use the Message Batches API with the 1-hour cache lifetime; if a batch is not back by 06:00 IST, finish on the standard API. Enforce per-run, per-day and per-month $ caps before every call. Make audit rows append-only at the database level (revoke UPDATE and DELETE). Build /runs, /audit, Connect Kite and the kill switch in /settings.
```

### Phase 7: Track record and calibration

**Done when** /track-record shows, per evaluation date and pooled: council IC beside factor-only IC on the same stocks with the paired t-statistic; hit rate and excess total return by action band; the council-off, drop-one-agent and advocates-vote ablations; and the date count against the 24-date bar.

```
Read CLAUDE.md and docs/SPEC.md. Implement services/backtest for the factor engine: point in time, delisted stocks included where a licensed source exists (otherwise label the survivorship bias), total returns, costs included (brokerage + STT + 0.2% slippage per side), decile forward returns against the Nifty 500 TRI, and the historical-analog distribution for the verdict card. Implement forward evaluation per SPEC "Success test": monthly evaluation dates, one observation per (ISIN, date), next-open entry, 1-month primary and 3-month secondary horizons (Newey-West for overlapping windows). Report Spearman IC of C and of S on the same names, the paired t-statistic on their difference, the equal-weight basket comparisons, a Brier score for Q, pooled logistic calibration (per agent only after 300 outcomes), and ablations: council off, drop one agent, advocates voting. Build /track-record.
```

### Phase 8 (optional, gated): Order placement for personal use

Start this only after 24 monthly evaluation dates with a positive incremental IC. It needs a static IP, OAuth with 2FA each session, the broker's algo-ID tagging, a kill switch, and a hard order rate far below 10 per second. It also needs the owner, not Claude Code, to edit Non-negotiable #1 in CLAUDE.md. Write this prompt when you get there, against the broker's rules at that time.

## 12. Cost and latency budget

**v1 assumptions per stock** (kept as the floor). Round 1: 25k input and 2k output tokens per agent (8k output for the Deep Reasoner, thinking included). Round 2: 14k new input plus 15k cached. Round 3 runs on 30% of stocks. Add the verifier, the Chair and 25 web searches. Prices per million tokens: Opus 5.5 $4/$20, Sonnet 5.5 $2/$10, Haiku 5.5 $0.10/$0.50 (prompts up to 100K tokens). Batch cuts token prices by 50%, and searches cost $0.01 each ([Claude pricing](https://platform.claude.com/docs/en/about-claude/pricing)).

| Setup | Per stock, standard | Per stock, batch | 70 stocks/day × 22 days (standard / batch) | Weekly top 50 + 5/day on demand, 327 runs/month (standard / batch) | One sweep of all ~5,470 (standard) |
| --- | --- | --- | --- | --- | --- |
| Premium: Opus Deep Reasoner + Sonnet × 6 | $1.44 | $0.84 | $2,217 / $1,301 | $470 / $276 | $7,868 |
| Standard: Sonnet Deep Reasoner + Haiku × 6 | $0.55 | $0.40 | $852 / $619 | $181 / $131 | $3,024 |
| Lean: Haiku × 7 | $0.30 | $0.28 | $465 / $425 | $99 / $90 | $1,651 |

**v2 corrections to the floor**

- **On-demand runs can't wait for a batch.** The realistic Standard mix is 218 weekly runs on batch ($0.40) plus 110 on-demand runs on the standard API ($0.55): about $148 a month.
- **Searches** fall from 25 to at most 15 per stock (see the search budget), saving up to $0.10 a run.
- **News cache:** one search a day for about 70 stocks (council list plus watchlist), about $21 a month. Watchlist polling uses RSS and costs nothing.
- **Sector packs:** about 3 searches × 20 sectors a week, about $3 a month.
- **Thinking tokens** are billed as output and were left out of v1's 2k per agent. Effort is set per agent; Phase 4 measures the real figure.
- **Phase 1b backfill:** about 6,000 transcripts (300 companies × 20 quarters) × 20k tokens is about 120M input tokens: about $6 on Haiku batch or $120 on Sonnet batch, plus output, one-time. Ongoing extraction is a few dollars a month.
- **Caching** may save less than v1 assumed (see the Claude API rules).

**Plan.** Budget $250 a month for Standard with the weekly top 50 plus on-demand runs, with hard caps of $300 a month and $25 a day. Add the price vendor (Kite at ₹500 a month) and fundamentals (₹1,499 a month on Tapetide); hosting isn't priced here. Replace these estimates with Phase 4's measured numbers. Only move the Deep Reasoner to Opus if the ablation shows it improves rank IC.

**Batch caveat.** The Batches API throttles web search per organisation, so big batches with lots of searching can run slowly ([web search docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool)).

**Latency.** There are no measurements yet, only targets: an on-demand single-stock run in under 5 minutes, and the nightly run done by 06:00 IST. Measure both in Phase 4 and record them here.

## 13. Testing, backtesting and evaluation

Backtest the factor engine on history, and judge the council only on verdicts it makes from launch onwards. Everything else is unit and schema testing. The pass bars below are starting defaults, not industry standards.

| What | Test | Pass bar |
| --- | --- | --- |
| `aggregate.py` | The three worked examples; all 5 analysts at +60 (C = 60, K = 1, BUY); all at −60 (AVOID); 3 at +100 and 2 at −100 (C = 20, D = 97.98, NO CONSENSUS); only 2 valid analysts (INSUFFICIENT EVIDENCE); advocates' scores change nothing | 100% line coverage; exact match to 2 decimals |
| Factor engine | Point-in-time test, direction flips, bank/NBFC overrides, small-sector fallback | No future rows used |
| Validator | 30 hand-written valid claims and 30 planted fakes | At least 28 of the valid claims pass; all 30 fakes are rejected |
| Agent outputs | Schema check, validator, planted-number test | Under 5% invalid per agent |
| Guidance extraction | Quote check on planted mismatches; 50 rows you label by hand | Every planted mismatch caught; at least 90% agreement |
| Verifier | 50 claims you label by hand | At least 90% agreement with your labels |
| Stability | Run 20 stocks twice (no `temperature`, so this is real noise) | Median change in C of 10 or less; above 15, treat scores as noise |
| Factor backtest | Point in time, delisted stocks included where licensed, total returns, costs included, against the Nifty 500 TRI | Top decile beats bottom decile in at least 60% of rolling 12-month windows |
| Council, forward | Paper trading from launch, per "Success test" | At least 24 monthly dates; incremental IC over the factor screen with paired t ≥ 2; BUY + ACCUMULATE beat both the TRI and the top-50 factor basket after costs |
| Ablations | Council off (factor only); drop one agent at a time; advocates voting; Round 1 average against post-debate C | Cut any agent or round that adds no IC |

The council-off ablation matters most. If the council doesn't beat the factor screen on the same stocks, you're paying tokens for theatre, so cut it.

## 14. Compliance checklist before anyone else sees a verdict

Personal use needs only the first two items. The rest apply from the day another person sees a verdict, including a screenshot in a group chat or a social post.

- [ ] Disclaimer on every verdict view, and a working kill switch in Settings
- [ ] Data licences that cover your use (personal versus shown to others), with no exchange-site scraping
- [ ] Showing calls to anyone else: SEBI RA registration (INH), a named RA signing off each call, and AI use disclosed to clients
- [ ] Allocation advice to anyone else: SEBI IA registration (INA), or remove the allocation field
- [ ] Placing orders: the broker's algo setup (static IP, OAuth + 2FA, algo ID), registration above 10 orders/second, and no black-box strategy offered to others without RA registration
- [ ] An append-only audit log kept for 5 years
- [ ] A human approval step before any verdict leaves the app
- [ ] News stored as summaries and links only
- [ ] User data handled under the DPDP Act, if you add users
- [ ] SEBI's final AI/ML guidelines read when they are issued, and this list updated to match

## 15. Sources

- [Research Analyst registration and AI disclosure](https://www.compliancecalendar.in/learn/sebi-latest-amendments-for-research-analysts) (ComplianceCalendar)
- [RA disclosure of AI use, January 2025](https://taxguru.in/?p=1045785) (TaxGuru)
- [Retail algo rules, effective 1 Apr 2026](https://www.tradejini.com/blogs/what-sebis-new-algo-trading-rules-mean-for-you) (Tradejini)
- [SEBI chair on coming AI guidelines, 14 Nov 2026](https://www.angelone.in/news/market-updates/sebi-to-issue-ai-usage-guidelines-for-capital-markets-sebi-chairman-tuhin-kanta-pandey) (Angel One)
- [SEBI AI/ML draft, 20 Jun 2025: 5-year data retention](https://telanganatoday.com/sebi-proposes-ai-ml-usage-norms-to-protect-investors) (Telangana Today / PTI)
- [NSE and BSE listed equity counts, 18 Sep 2026](https://www.multibagg.ai/feeds/screener-all-nse-bse-stocks-cmudzc8ty000009gm1mk1h3en) (Multibagg)
- [NSE Data cease-and-desist notices](https://yourstory.com/2022/10/exclusive-nse-issues-cease-desist-notices-to-stock-gaming-apps) (YourStory)
- [Indian market data API comparison, 24 Oct 2026](https://tapetide.com/compare/best-api-indian-stock-market-data) (Tapetide, vendor-published)
- [Kite Connect API charges](https://support.zerodha.com/category/trading-and-markets/kite-api/articles/what-are-the-charges-for-kite-apis) (Zerodha)
- [Claude API pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- [Claude web search tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool)
- [Claude web fetch tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-fetch-tool)
- [Claude models overview](https://platform.claude.com/docs/en/models/overview)

v2's SEBI, vendor-price and stock-count figures are carried over from v1 and have not been re-checked. The Claude API rules were checked against the current API documentation on 18 Nov 2026.
