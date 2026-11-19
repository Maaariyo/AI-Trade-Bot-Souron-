# Indian equity market-data vendor bake-off: research notes

Researched 19 Nov 2026. Scope: a personal, single-user, non-commercial Indian equity research app. Nothing was signed up for, paid for or logged into, and nothing was crawled from nseindia.com or bseindia.com.

## How this was researched, and how much to trust it

- **Only search results were read, not the pages themselves.** WebFetch could not resolve `kite.trade` or `support.zerodha.com` in this session (the session's network does not allow them). The tool said to stop fetching other sites after that. So every fact below comes from WebSearch result summaries and snippets of the cited URL, not from reading the full page. Treat each cell as "the cited page appears to say", and spot-check the important ones in a browser. To verify directly, `kite.trade` and `support.zerodha.com` (and the other vendor hosts) have to be allowed in the session's network settings.
- **Source tags** used in the tables:
  - **[D]**: the vendor's own docs, support or FAQ page.
  - **[VM]**: the vendor's own marketing or pricing page only.
  - **[VC]**: a comparison page written by a vendor (mostly Tapetide's "best API" page, which is Tapetide's own marketing).
  - **[F-staff]**: a forum reply attributed to vendor staff.
  - **[F-user]**: a forum post by a user.
  - **[3P]**: a third-party blog, reseller page or directory.
- **"unknown"** means no evidence was found. It does not mean "no".

---

## Table 1: Criteria 1–3 (prices, corporate actions, delisted stocks)

| Vendor | 1. Adjusted daily (EOD) prices, all active NSE + BSE equities | 2. Dividends and corporate actions as a feed | 3. Price history for delisted stocks |
|---|---|---|---|
| **Zerodha Kite Connect** | **Partial.** Day candles are served for instruments in the NSE/BSE instruments dump. They are adjusted for splits and bonuses, and per a Sep 2026 forum answer also for rights, spin-offs and "extraordinary" dividends (>2%). Ordinary dividends are not adjusted, and no unadjusted series exists. Users report gaps (demergers, recent actions). [F-staff/F-user] kite.trade/forum/discussion/16280, comment/24111, comment/52478 | **No.** "No dedicated Corporate Actions API" (Sep 2026 forum). No dividend data. [F] kite.trade/forum/discussion/16280 | **No.** Delisted instruments are dropped from the instruments dump, so their history cannot be fetched. A 2025 feature request was closed with no roadmap. Expired futures do have history. [F-staff] kite.trade/forum/discussion/11382, comment/50505 |
| **Tapetide** | **Partial.** Daily/weekly OHLCV, up to 2,000 calendar days per call. An `/stocks/{symbol}/adjustment-factors` route gives per-event and cumulative split/bonus factors, so raw prices can be rebuilt. Rights issues and demergers have "no reliable numeric factor". The series is **not** total return: dividends are not included in the adjustment. Claims about 8,200 NSE/BSE companies. [D/VM] developers.tapetide.com/api/, glama get_adjustment_factors | **Yes (vendor docs).** An `/stocks/{symbol}/events` route covers corporate actions (dividends, splits, bonuses, AGMs, rights, with ex-dates). There is also dividend history. [D] developers.tapetide.com/api/, glama get_corporate_actions | **Partial / unknown.** An `/observation-status` route flags each day as traded, holiday, pre-listing, **delisted**, and so on. No statement says the full history of delisted companies can be retrieved. Point-in-time index membership and symbol/ISIN-at-date lookups are offered. [D] developers.tapetide.com/api/ |
| **EODHD** | **Partial.** NSE is confirmed (`.NSE` tickers). **No BSE exchange code was found** in the searches (unknown). `open/high/low/close` are raw. `adjusted_close` is adjusted for splits **and dividends**, and volume for splits only. [D] eodhd.com/financial-academy/financial-faq/adjusted-close-and-close-whats-the-difference | **Yes.** Separate dividends and splits endpoints, plus per-exchange bulk download. Included in the $19.99 EOD plan. Indian data quality and how bonus/rights issues are handled were not verified. [D] eodhd.com/financial-apis/api-splits-dividends | **Yes.** The delisted coverage table lists **NSE with 940 delisted tickers**. Call `exchange-symbol-list?delisted=1`, then use the normal EOD endpoint. Watch out for reused tickers. The BSE count is unknown. [D] eodhd.com/financial-apis/review-delisted-stock-companies-data |
| **TrueData** | **Partial.** Daily bars "10+ years" [D]. One TrueData page lists BSE Equity; others list NSE only, so this is inconsistent. A FYERS reseller post says the "entire history is adjusted for splits, bonuses, rights & dividends" [3P, dated]. feedback.truedata.in historical-availability article; community.fyers.in TrueData post | **Partial.** A separate "Corporate Data & Fundamentals API" and a "Corporate Announcements API" (corporate actions feed) exist. No price or schema was found. [VM] truedata.in/products/marketdataapi | **Unknown** |
| **IndianAPI.in** | **Partial / unknown.** A `historical_data` endpoint takes `period` (1m…10yr, max) and `filter=price`. Whether prices are adjusted is unknown, and the exchange coverage is not documented. [D] indianapi.in/documentation/indian-stock-market | **Partial.** "Corporate actions" are listed in the stock endpoint's coverage. The format is unknown. [VM] indianapi.in/indian-stock-market | **Unknown** |
| **Upstox API** | **Yes (mostly).** Historical Candle Data V3 returns day candles from **Jan 2000** [D]. Staff say responses are "re-adjusted as per corporate actions" (example: the HDFC Bank bonus, Aug 2025) [F-staff]. Dividend adjustment is unknown. NSE_EQ and BSE_EQ keys exist. upstox.com/developer/api-documentation/backtesting; community thread 13555 | **Yes.** `/v2/fundamentals/{ISIN}/corporate-actions` returns dividends, bonuses, splits and rights, with announcement, ex and record dates and amounts. It is part of the Company Fundamentals API (effective **11 May 2026**). [D] upstox.com/developer/api-documentation/get-corporate-actions | **No.** Staff: "We do not support historical data for delisted stocks" (older thread, nothing newer found). The expired-instrument endpoints are for derivatives and need the Plus plan. [F-staff] community.upstox.com/t/historical-data-for-legacy-stocks/6851 |
| **Dhan (DhanHQ)** | **Yes (NSE/BSE breadth not explicitly verified).** Daily OHLCV "back up to the date of its inception", up to the previous trading day. Adjusted for **bonuses and splits** [D]. Dividend adjustment is unknown. dhanhq.co/docs/v2/historical-data/; dhan.co support FAQ on adjustments | **No (official).** Only undocumented "ScanX" endpoints, reverse-engineered by a third party. [3P] mintlify chartsmaze_clone | **Unknown.** Intraday history is "only for active contracts". [D] dhan.co support FAQ on expired futures |
| **Angel One SmartAPI** | **Partial.** `getCandleData` ONE_DAY is documented at 2,000 days per request, but users report about 500-candle truncation [F]. Adjustment is not documented, and a user reports one stock's split was not adjusted (TALBROAUTO) [F-user]. smartapi forum posts 11697, 4771; topic 3380 | **Unknown** (no evidence of a feed) | **Unknown** |
| **ICICI Direct Breeze** | **Partial.** A `1day` interval exists for cash equity (SDK exchange codes: NSE=4, BSE=1). But the official doc says "securities listed on BSE and MCX are not available" (conflict). History depth is stated as 3 years (F&O). Adjustment is unknown. [D] api.icicidirect.com/breezeapi/documents/index.html; icicidirect.com/faqs/f-and-o/what-is-trading-apis | **Unknown** | **Unknown** |
| **Global Datafeeds** | **Partial.** `GetHistory` (REST/WebSocket) serves day/week/month data. EOD history goes back to 2010 for the main exchanges, and BSE cash has backfill. Adjustment is unknown. [VM/D] globaldatafeeds.in "Type of Data Available" | **Unknown** | **Unknown** |

## Table 2: Criteria 4–6 (unattended API, licence, point-in-time fundamentals)

| Vendor | 4. Runs unattended (nightly job, no daily human login) | 5. Licence allows personal research? Can the data be shown to others? | 6. Point-in-time dates on fundamentals |
|---|---|---|---|
| **Zerodha Kite Connect** | **No.** The access token expires at **6 AM** the next day. Staff say "users must log in manually at least once each day" (an exchange requirement) and "we do not recommend automating the Kite Connect login flow". [F-staff] kite.trade/forum/discussion/comment/51353, comment/52683 | **Partial.** Personal use only. Staff say "it is not for redistribution of the data", so **showing it to others is not allowed**. Users cite a terms clause 4(b) restricting databases and permanent copies, but its wording was **not verified**. [F-staff] kite.trade/forum/discussion/comment/34108, comment/45067; kite.trade/terms | **N/A** (no fundamentals) |
| **Tapetide** | **Yes.** Static API token (the same token and quota as the MCP server). [D] developers.tapetide.com/api/ | **Unknown.** No terms of service or data licence page was found. The MCP client code is MIT-licensed, which covers the code only, not the data. pypi.org/project/tapetide-mcp/ | **Yes (vendor docs).** Each quarterly period has `available_from`: the result-declaration date where known, otherwise a regulatory-lag **estimate**. Values are the *latest* figures, so later restatements may be included. A third-party PR says dates **before about Sep 2024 are estimated** (`tapetide_est`). A results-declared tool has filed-date and revision fields. [D] developers.tapetide.com/api/; [3P] github.com/swapnil-agrim/nivesh/pull/129 |
| **EODHD** | **Yes.** Static `api_token` on each request. No daily login (standard REST). [D] eodhd.com/help/limits | **Yes for personal use, single user.** Showing the data to others (a public website, an app other people use, published charts) is **not** personal use and needs a commercial licence. Account sharing is prohibited. [D] eodhd.com/help/personal-use, eodhd.com/help/commercial | **Unknown / probably no for India.** Non-US statements go back to 2000 for "most essential companies" (Infosys used as the example). Quarterly entries are keyed by period date. **No filing-date field was found for Indian companies** (`filed_at` exists only in the separate US SEC-filings API). [D] eodhd.com/financial-apis-blog/huge-update-for-non-us-fundamentals-data |
| **TrueData** | **Partial (likely yes).** The official Python SDK takes a login ID and password in code (no interactive or 2FA flow seen). Session lifetime is not documented in what was found. [D] pypi.org/project/truedata/ | **Yes for personal use.** "APIs are provided for Personal Use only" [3P FYERS]. "Redistribution, resale, or public sharing of data is not allowed without prior written permission". Exchange fees are separate. [D] truedata.in/market-data-apis | **Unknown.** A fundamentals API exists [VM]. Tapetide's comparison page says TrueData's point-in-time support is "not stated" [VC]. |
| **IndianAPI.in** | **Yes.** `X-API-Key` header. [D] indianapi.in/documentation/indian-stock-market | **Unknown** (terms not found) | **Unknown.** Financials, `historical_stats` and `statement` endpoints exist. No filing dates were found. [D] dev.indianapi.in |
| **Upstox API** | **Yes, via the "Analytics Token".** A **1-year, read-only** token generated once in the developer console with no OAuth flow ("no daily re-authorization needed"). It covers market data, including historical candles, fundamentals and expired instruments. One token per account. Static IP is needed only for account-specific endpoints. The standard token expires at 3:30 AM, and staff say they do not support automating the normal login. [D] upstox.com/developer/api-documentation/analytics-token/ | **Partial.** No formal API data-licence text was found. Staff: personal web-app use is OK, and you should "only [let] Upstox customers consume data via your platform" [F-staff]. `ai.txt` says resale or republishing needs contact with Upstox. community.upstox.com/t/api-usage-clarification/13250; upstox.com/ai.txt | **No evidence.** The income statement, balance sheet and cash-flow endpoints return values labelled by period (for example "Mar 2026"). No filing or result-date field was found. [D] upstox.com/developer/api-documentation/get-income-statement |
| **Dhan (DhanHQ)** | **Partial / yes.** Tokens last 24 h, and API keys last 12 months. The official docs describe `auth.dhan.co/app/generateAccessToken` with client ID + PIN + TOTP, and support says you can generate a token "without logging into the website" using API key + TOTP. A user reports TOTP must be used within about 30 s. [D] dhanhq.co/docs/v2/authentication/; dhan.co support | **Unknown** (Terms of Use not retrieved) | **N/A** (no official fundamentals API) |
| **Angel One SmartAPI** | **Partial.** `loginByPassword` takes client code + PIN + TOTP through the API, so it can be scripted. The token lasts about 24–28 h (Angel announcement). Older posts say it expired at 5 AM, and one post claims midnight. One session per API key. A move to OAuth was announced in 2025, and its current status is unclear. [F-staff] smartapi forum posts 19219, 18262 | **Unknown.** The SmartAPI page says "free of cost", but no data-use terms were found. smartapi.angelone.in | **N/A** |
| **ICICI Direct Breeze** | **No.** ICICI FAQ: "Session key needs to be generated everyday manually according to SEBI guidelines". It is valid for 24 h or until midnight, whichever is earlier. [D] icicidirect.com/faqs/f-and-o/what-is-trading-apis | **Unknown** | **N/A** |
| **Global Datafeeds** | **Unknown** (a vendor feed, so probably key-based, but not verified) | **Unknown.** It is an authorised NSE/BSE data vendor, and terms were not found. globaldatafeeds.in/authorised-data-vendors/ | **N/A / unknown** |

## Table 3: Price, ISIN and rate limits

| Vendor | Monthly price for a plan that covers EOD history (plus fundamentals where offered) | ISIN in the instrument/security list? | API rate limits |
|---|---|---|---|
| **Zerodha Kite Connect** | **₹500/month per app** ("Connect"; includes live and historical data). Whether GST is included is not stated. The "Personal" app is free but has **no** live or historical data. **New since Oct 2026:** a month with ≥₹2,000 brokerage earns ₹500 developer credits for the next month (an active app is required). [F-staff/D] kite.trade/forum/discussion/15015; tradingqna 198623; kite.trade/forum/discussion/comment/53032 | **No.** Forum posts over many years say ISIN is "being worked on". No sign it has been added. [F-staff] kite.trade/forum/discussion/1240, comment/50266 | Historical: **3 req/s**, "no daily or monthly request limits" [F-staff]. Quote: 1 req/s. Other endpoints: 10 req/s. Orders: 10/s and 400/min. kite.trade/forum/discussion/comment/52670, comment/52868 |
| **Tapetide** | Starter ₹499/mo (400 calls/day, 5,000/mo). Pro ₹999/mo (1,200/day, 20,000/mo). **Pro+ ₹1,499/mo (2,500/day, 50,000/mo).** Free: 50 calls/day. 7-day trial on paid plans, and payments are non-refundable. **The figures appear only on Tapetide's own comparison page [VC/VM].** The pricing page snippet showed only "from ₹499". tapetide.com/compare/best-api-indian-stock-market-data; tapetide.com/pricing | **Yes (vendor docs):** "which symbol and ISIN a company traded under at a point in time". [D] | Burst cap of **60 req/min** on every plan, plus the daily/monthly quotas above. Each successful request costs 1 unit, and failed requests are refunded. Note: at about 8,200 companies, one call per stock per night is **over the Pro+ 2,500/day quota** unless a bulk endpoint exists (unknown). [VC/D] |
| **EODHD** | EOD Historical Data (All World) **$19.99/mo** (EOD + splits + dividends). Fundamentals Data Feed **$59.99/mo, which does not include EOD prices**. All-In-One **$99.99/mo**. Annual billing is cheaper ($599.90/yr fundamentals, $999.90/yr All-In-One). [VM/D] eodhd.com/pricing; eodhd.com/help/plans | **Yes.** The exchange symbol list returns `Code, Name, Country, Exchange, Currency, Type, Isin` (`Isin` may be null). [D] eodhd.com/knowledgebase/list-symbols-exchange/ | **100,000 API calls/day** (paid) and **1,000 req/min**. A bulk whole-exchange call costs 100 calls. The counter resets at midnight GMT. [D] eodhd.com/financial-apis/api-limits |
| **TrueData** | **Quote-based** (price depends on exchanges, symbol count and data type; exchange fees extra). FYERS reseller (dated): about ₹1,599 + GST/mo historical, ₹2,599 + GST/mo live + historical, 50–200 symbol caps. [3P] community.fyers.in TrueData post | **Unknown** | REST historical: tick 5/s, 300/min, 18,000/h. Minute bars 10/s, 600/min, 18,000/h. Daily-bar limits not stated. [D] feedback.truedata.in rate-limit article |
| **IndianAPI.in** | Free 500 req/mo. ₹399/mo for 5,000. ₹799/mo for 10,000. ₹1,799/mo for 50,000. ₹3,999/mo for 100,000. **Only from Tapetide's comparison page [VC], "checked 24 Oct 2026"**, and not confirmed on IndianAPI.in itself. | **Unknown** | ₹3,999 tier: 10 req/s [VC]. Other tiers unknown. |
| **Upstox API** | **Free.** Data APIs are free [D]. The "Plus" plan, needed for expired-instrument data, is "free initially" [D]. upstox.com/developer/api-documentation/announcements/update-zero-brokerage; upstox.com/help-center … upstox-plus-264073 | **Yes.** The instruments JSON has an `isin` field, and equity keys follow the pattern `NSE_EQ\|<ISIN>`. [D] upstox.com/developer/api-documentation/instruments/ | The official page shows **25 req/s per API per user** (other rows not seen). A third-party review says 50/s, 500/min and 2,000/30 min for standard APIs. No daily cap. [D/3P] upstox.com/developer/api-documentation/rate-limiting |
| **Dhan (DhanHQ)** | **₹499 + GST/month** Data API (the "free with 25 trades" offer has been discontinued). [D] dhan.co support "how does the DhanHQ Data API subscription work" | **Unknown** (the detailed scrip-master CSV exists, and its header was not verified) | Data APIs: **5 req/s** [D]. Forum: 100,000 requests/day [F-staff]. Users report HTTP 429 after about 400 calls [F-user]. |
| **Angel One SmartAPI** | **Free** [VM] smartapi.angelone.in | **No.** "currently not providing ISIN on json file" [F-staff] (may be dated) | `getCandleData`: 3/s, 180/min, 5,000/h (forum table), or 500/min in another staff post. Users report spurious AB1021 throttling (Aug 2026). [F] |
| **ICICI Direct Breeze** | **Free** (historical included; brokerage applies to trades). [D] icicidirect.com/faqs/f-and-o/what-is-trading-apis | **Unknown** | **100 calls/min, 5,000 calls/day.** Third party: max 1,000 candles per request (unverified). [D/3P] |
| **Global Datafeeds** | **Quote-based.** No monthly figure is published ("no commitment, flexible pricing"). [VM] globaldatafeeds.in API Pricing page | **Unknown** | **Unknown** |

### Other candidates noted but not scored
- **Trendlyne MCP**: Indian fundamentals, shareholding and filings through MCP. The "Pro" tier is ₹299/month [VM]. It is MCP-based, not a documented REST feed, and it was not evaluated against the six criteria. trendlyne.com/subscription/mcp/plans/
- **CMIE Prowess**: Indian financial statements and corporate actions for about 5,300 listed and about 100,000 unlisted companies, with an API option. Institutional pricing, nothing published. Not evaluated.
- **NSE direct (for context)**: NSE's domestic price list (effective 1 Apr 2026) prices EOD Capital Market data at ₹1,00,000/yr and EOD Corporate Data at ₹5,00,000/yr per site. This is institutional-scale and not practical for a personal app. nsearchives.nseindia.com … NSE_Pricing_file_-_Domestic_clients_20260309171343.pdf (one document, found via search, not crawled)

---

## Zerodha Kite Connect: the specific questions

**Access token and login**
- The access token expires at **6 AM the next day**. The forum quotes the docs: "Current access_token expiry is set to 6AM". Older posts mention 8:15 or 8:30 AM, but those pre-date the current rule. kite.trade/forum/discussion/comment/51353; kite.trade/forum/discussion/14312
- **The user has to complete the login (with 2FA/TOTP) personally every day.** Staff: "As per exchange requirements, users must log in manually at least once each day. For this reason, we do not recommend automating the Kite Connect login flow." They also say there is "no workaround to keep the authenticated Kite Connect session running continuously without the daily login". kite.trade/forum/discussion/16226; kite.trade/forum/discussion/comment/52683
- **Automating the login (for example a TOTP script):** Zerodha staff consistently say they "do not recommend or support" it. An older staff reply calls it "against the regulation". A feature request for API-based TOTP login was closed with the same answer. No clause in Zerodha's *terms* explicitly banning it was found; the evidence is staff forum posts. kite.trade/forum/discussion/8976; kite.trade/forum/discussion/9738; kite.trade/forum/discussion/comment/52683
- TOTP is mandatory for Kite Connect, under a SEBI circular. [F-staff]

**SEBI retail algo framework (mandatory from 1 Apr 2026): what changes for data-only use**
- **Nothing material for data-only use (no orders).** The static-IP requirement applies only to order endpoints. Kite team: "Only order endpoints are validated against the static IP. All other API endpoints, WebSocket data, order book, positions, etc., remain accessible from any IP." [F-staff] kite.trade/forum/discussion/15359
- NSE's retail-algo FAQ (3 Nov 2025) ties the client static IP to clients who use the API "to place orders". NSE FAQ_Retail_Algo_03112025_NSE.pdf (one document, found via search). Upstox and FYERS staff give the same reading.
- What still applies: the daily manual login (already in place before the framework) and the need for the paid ₹500 Connect app for any data. Zerodha cut the data price from ₹2,000 to ₹500 citing "new regulatory clarity" around this framework. kite.trade/forum/discussion/15015; nithinkamath.substack.com/p/nses-new-retail-algo-trading-circular
- Background: SEBI circular of 4 Feb 2025 ("Safer participation of retail investors in Algorithmic trading"). Its effective date was pushed back and finally set at 1 Apr 2026 by SEBI's circular of 30 Sep 2025. sebi.gov.in/sebi_data/attachdocs/sep-2025/1759232056254.pdf; taxguru.in

**Historical candle API**
- **Rate limit: 3 requests/second.** Staff: "There are no daily or monthly request limits for the Historical Data API." [F-staff] kite.trade/forum/discussion/comment/52670; kite.trade/forum/discussion/8899
- **Maximum span per request for `day` candles: 2,000 days.** Error text: "Difference between `to` and `from` dates for `day` cannot be more than 2000 days". Longer history takes several requests. Intraday maximums conflict between sources (minute candles: 30 vs 60 days). kite.trade/forum/discussion/3458
- **Delisted equities: not available.** They are missing from the instruments dump, and old tokens return "invalid token". **Expired futures: available.** [F-staff] kite.trade/forum/discussion/11382; kite.trade/forum/discussion/14080; kite.trade/forum/discussion/comment/50505
- **Corporate-action adjustment:** Splits and bonuses are adjusted. A Sep 2026 forum answer also lists rights, spin-offs and extraordinary dividends (>2%). Older staff answers said "only Stock Splits and Bonus, not Dividends", and that adjustment was "done only on day candle". No unadjusted series is offered. Users report errors (a 2016 demerger not adjusted, discontinuous candles, a "a × price − fixed amount" pattern). kite.trade/forum/discussion/16280; comment/24111; comment/52478; comment/53138

**Instruments dump columns (CSV, regenerated once a day)**
`instrument_token, exchange_token, tradingsymbol, name, last_price, expiry, strike, tick_size, lot_size, instrument_type, segment, exchange`. **There is no ISIN column.** `last_price` is not live. The docs recommend `exchange` + `tradingsymbol` as the unique key. kite.trade/docs/connect/v3/market-data-and-instruments (column list taken from a search snippet of this page). ISIN status: staff have said "working on adding ISIN" for years, with no evidence it has shipped. kite.trade/forum/discussion/1240; comment/50266. ISIN does appear in the *holdings* response.

**Price and what it includes**
- **₹500/month per app ("Connect")**: live market data, WebSocket and **historical candle data**, plus everything in Personal. The order and account APIs ("Personal") are free but have **no** live or historical data. The ₹2,000 historical add-on was dropped from 8 Feb 2025, and the overall price fell from ₹2,000 to ₹500 around May 2025. GST treatment is not stated. kite.trade/forum/discussion/14806; kite.trade/forum/discussion/15015; zerodha.com/z-connect/business-updates/whats-new-at-zerodha-june-2025; support.zerodha.com … what-are-the-charges-for-kite-apis
- **New (announced 7 Oct 2026):** a calendar month with ≥₹2,000 brokerage earns ₹500 in developer credits toward the *next* month's fee. You must have an active Connect app when the credit is issued. tradingqna.com/t/free-kite-connect-subscription-for-active-users/198623; kite.trade/forum/discussion/comment/53032
- **Licence:** personal use only, no redistribution. [F-staff] kite.trade/forum/discussion/comment/34108

---

## Benchmark: Nifty 500 TRI

- **Official source:** niftyindices.com has a "Historical Data Reports" page with index-type, index and date-range selectors. Its historical section includes **Total Returns Index** values. niftyindices.com/reports/historical-data; methodology at niftyindices.com/resources/index-concepts/total-return-index. This search could not confirm that Nifty 500 TRI specifically is offered there (the cached page showed "No Data Found"), and a TradingQnA user also "could not find" it. tradingqna.com/t/nifty-500-tri-historical-data/141395
- **Unofficial routes:** BharatFinTrack (Python) downloads NSE equity TRI series from a niftyindices.com endpoint [3P]. Freefincal offers TRI for 52 NSE indices, but its chart export may be **rebased** rather than absolute [3P]. niftyindices.com is reported to be behind Cloudflare, so scripts may be blocked. bharatfintrack.readthedocs.io …/nse_tri.html; freefincal.com/download-historical-total-returns-index-data-52-nse-indices/; github.com/jugaad-py/jugaad-data/issues/76 (open TRI feature request)
- **Through the vendors above:** **None was confirmed to serve Nifty 500 TRI.** Kite: staff note that some indices have no stored history ("only live feed is available"), and no TRI token was found. Upstox's Nifty 500 web page mentions a TRI variant, but no API feed is documented. EODHD, Dhan and Tapetide: no evidence found. **Unknown across the board.**
- **NSE Indices licensing:** The niftyindices.com disclaimer says "Use or distribution of the Company's … index data and the use of their index data to create financial products require a license from NSE Indices Limited and/or its third party licensors." **No personal-use exemption was found.** The site terms grant only a limited right to access the site. Data subscriptions are paid, with charges varying by data type and period; contact indices@nse.co.in. The IOSCO statement says use of NSE Indices data "requires a license or subscription". niftyindices.com/disclaimer; niftyindices.com/terms-of-use; niftyindices.com/offerings/data-subscription; archives.nseindia.com …/Nifty_Indices_IOSCO_Compliance_2020.pdf
- **Practical reading (not legal advice):** viewing or downloading through the website for your own use is ambiguous. Storing it in an app, and especially showing it to others, appears to need a licence. Ask indices@nse.co.in in writing.

---

## Checking the existing assumptions

| Assumption | Finding |
|---|---|
| Kite Connect costs ₹500/month | **Confirmed**, per app. GST is not stated. New since Oct 2026: ₹500 credit in any month with ≥₹2,000 brokerage. The free "Personal" plan has no data at all. |
| Kite needs a daily manual login | **Confirmed.** The token expires at 6 AM. Staff say a manual daily login is an exchange requirement and automating it is not recommended. The SEBI 2026 framework does not change this for data-only use. |
| Kite has no delisted history | **Confirmed** (expired futures do have history). |
| Kite has no dividends | **Confirmed as a feed** (no corporate-actions API). **Nuance:** a Sep 2026 forum answer says candles *are* adjusted for "extraordinary dividends (>2%)" as well as splits, bonuses, rights and spin-offs. Older staff answers said dividends are not adjusted. The sources conflict. |
| Tapetide Pro+ costs ₹1,499/month with `available_from` dates | **Price confirmed only on Tapetide's own comparison page [VC]**, not on the pricing page snippet. **`available_from` confirmed in the vendor's API docs, but it does not appear to be Pro+-only** (a third-party project uses it on the free tier). Caveats: dates before about Sep 2024 are *estimated*, values are latest-restated, Pro+ has a 2,500-calls/day quota, and no data-licence terms were found. |
| EODHD fundamentals plan costs $59.99/month | **The price is confirmed, but that plan has no EOD prices.** Prices plus fundamentals cost $79.98 ($19.99 + $59.99) or $99.99 (All-In-One). Also: no point-in-time filing dates found for India, BSE coverage unconfirmed, and the personal plan bars showing data to others. |

---

## Every URL used

**Zerodha / Kite / regulation**
- https://kite.trade/forum/discussion/14806/historical-data-is-now-free
- https://kite.trade/forum/discussion/15015/revising-kite-connect-fees-from-2000-to-500-per-month
- https://zerodha.com/z-connect/business-updates/whats-new-at-zerodha-june-2025
- https://support.zerodha.com/category/trading-and-markets/kite-api/articles/what-are-the-charges-for-kite-apis
- https://support.zerodha.com/category/trading-and-markets/general-kite/kite-api/articles/historical-data-and-live-market-data-payment-plan
- https://tradingqna.com/t/free-kite-connect-subscription-for-active-users/198623
- https://kite.trade/forum/discussion/comment/53032/
- https://www.marketcalls.in/algo-trading/zerodha-makes-trading-api-free-for-personal-use-bundles-historical-data-with-connect-api.html
- https://kite.trade/forum/discussion/comment/51353
- https://kite.trade/forum/discussion/14312/access-token-timing
- https://kite.trade/forum/discussion/16226/how-to-keep-the-api-running
- https://kite.trade/forum/discussion/comment/52683/
- https://kite.trade/forum/discussion/8976/automate-kiteconnect-login-process
- https://kite.trade/forum/discussion/9738/totp-and-auto-access-token-generation
- https://kite.trade/forum/discussion/3458/inputexception-difference-between-to-and-from-dates-for-day-cannot-be-more-than-2000-days
- https://kite.trade/forum/discussion/8899/rate-limit-of-kite-connect-historical-data-api-and-lookback
- https://kite.trade/forum/discussion/comment/52670/
- https://kite.trade/forum/discussion/comment/52868/
- https://kite.trade/forum/discussion/11382/how-to-get-historical-data-for-stock-that-got-delisted
- https://kite.trade/forum/discussion/comment/50505/
- https://kite.trade/forum/discussion/14080/instruments-tokens-of-delisted-stocks
- https://kite.trade/forum/discussion/16280/historical-5-minute-api-data-corporate-action-price-and-volume-adjustments
- https://kite.trade/forum/discussion/comment/24111/
- https://kite.trade/forum/discussion/comment/52478/
- https://www.kite.trade/forum/discussion/comment/53138/
- https://kite.trade/docs/connect/v3/market-data-and-instruments
- https://kite.trade/docs/connect/v3/historical/ (could not be fetched)
- https://kite.trade/forum/discussion/1240/do-you-have-isin-security-of-master-data
- https://kite.trade/forum/discussion/comment/50266/
- https://kite.trade/terms
- https://kite.trade/forum/discussion/comment/34108/
- https://kite.trade/forum/discussion/comment/45067/
- https://kite.trade/forum/discussion/15359/query-regarding-static-ip-requirement-for-kite-connect-api-data-only-usage
- https://nithinkamath.substack.com/p/nses-new-retail-algo-trading-circular
- https://nsearchives.nseindia.com/web/sites/default/files/inline-files/FAQ_Retail_Algo_03112025_NSE.pdf
- https://www.sebi.gov.in/sebi_data/attachdocs/sep-2025/1759232056254.pdf
- https://taxguru.in/sebi/sebi-circular-safer-participation-retail-investors-algorithmic-trading.html
- https://fyers.in/community/t/is-a-static-ip-required-for-data-only-applications-historical-market-depth-tbt-under-the-new-sebi-guidelines/22865

**Tapetide**
- https://tapetide.com/pricing
- https://tapetide.com/compare/best-api-indian-stock-market-data
- https://developers.tapetide.com/api/
- https://glama.ai/mcp/servers/Tapetide-hq/nse-bse-indian-stock-market-data-mcp/tools/get_adjustment_factors
- https://glama.ai/mcp/servers/Tapetide-hq/nse-bse-indian-stock-market-data-mcp/tools/get_corporate_actions
- https://glama.ai/mcp/connectors/com.tapetide/stock-research-mcp/tools/get_results_declared
- https://github.com/swapnil-agrim/nivesh/pull/129
- https://pypi.org/project/tapetide-mcp/
- https://github.com/akfamily/akhub/issues/30

**EODHD**
- https://eodhd.com/pricing
- https://eodhd.com/help/plans
- https://eodhd.com/financial-academy/financial-faq/adjusted-close-and-close-whats-the-difference
- https://eodhd.com/financial-apis/api-splits-dividends
- https://eodhd.com/financial-apis/review-delisted-stock-companies-data
- https://eodhd.com/financial-academy/financial-faq/historical-stock-prices-for-delisted-companies
- https://eodhd.com/financial-apis/list-supported-exchanges
- https://eodhd.com/knowledgebase/list-symbols-exchange/
- https://eodhd.com/financial-apis-blog/huge-update-for-non-us-fundamentals-data
- https://eodhd.com/financial-apis/stock-etfs-fundamental-data-feeds
- https://eodhd.com/financial-apis/api-limits
- https://eodhd.com/help/limits
- https://eodhd.com/help/personal-use
- https://eodhd.com/help/commercial
- https://eodhd.com/financial-apis/terms-conditions
- https://eodhd.com/financial-summary/BHARATFORG.NSE

**TrueData**
- https://feedback.truedata.in/knowledge-base/article/historical-real-time-data-availability-through-market-data-api
- https://feedback.truedata.in/knowledge-base/article/requestscalls-limit-via-historical-and-real-time-api
- https://www.truedata.in/market-data-apis
- https://www.truedata.in/products/marketdataapi
- https://community.fyers.in/post/fyers-ties-up-with-truedata-5f40dc9ca9f2036c40234384
- https://pypi.org/project/truedata/
- https://www.truedata.co/?p=4991

**IndianAPI.in**
- https://indianapi.in/indian-stock-market
- https://indianapi.in/documentation/indian-stock-market
- https://dev.indianapi.in/

**Upstox**
- https://upstox.com/developer/api-documentation/analytics-token/
- https://upstox.com/developer/api-documentation/announcements/analytics-token
- https://upstox.com/developer/api-documentation/get-token
- https://upstox.com/developer/api-documentation/announcements/extended-tokens-all-apps
- https://upstox.com/developer/api-documentation/access-token-request
- https://community.upstox.com/t/how-to-api-login-process-automate/5368/2
- https://upstox.com/developer/api-documentation/backtesting
- https://upstox.com/developer/api-documentation/v3/get-historical-candle-data
- https://community.upstox.com/t/does-historical-candle-data-api-takes-care-of-corporate-actions/13555
- https://community.upstox.com/t/historical-data-for-legacy-stocks/6851
- https://upstox.com/developer/api-documentation/instruments/
- https://upstox.com/developer/api-documentation/get-corporate-actions
- https://upstox.com/developer/api-documentation/announcements/company-fundamentals-api
- https://upstox.com/developer/api-documentation/get-income-statement
- https://upstox.com/developer/api-documentation/rate-limiting
- https://www.chittorgarh.com/broker/upstox/api-for-algo-trading-review/33/
- https://upstox.com/developer/api-documentation/announcements/update-zero-brokerage
- https://upstox.com/help-center/what-are-the-terms-and-conditions-for-upstox-plus-264073/
- https://community.upstox.com/t/api-usage-clarification/13250
- https://upstox.com/ai.txt
- https://community.upstox.com/t/clarification-on-static-ip-requirement-for-different-api-types/10421

**Dhan**
- https://dhanhq.co/docs/v2/historical-data/
- https://dhan.co/support/platforms/dhanhq-api/is-the-historical-data-from-dhan-s-data-api-adjusted-for-corporate-actions-like-bonuses-and-splits/
- https://dhan.co/support/platforms/dhanhq-api/what-are-the-api-rate-limits-for-dhan/
- https://dhan.co/support/platforms/dhanhq-api/how-does-the-dhanhq-data-api-subscription-work/
- https://dhan.co/support/platforms/dhanhq-api/is-the-dhanhq-data-api-subscription-free-if-i-execute-a-minimum-number-of-trades-every-month/
- https://madefortrade.in/t/enhanced-dhanhq-data-apis-with-more-data-and-higher-rate-limits/50328
- https://madefortrade.in/t/dhan-cloud-charts-historical-returning-429-after-400-calls/91330
- https://dhanhq.co/docs/v2/authentication/
- https://dhan.co/support/platforms/dhanhq-api/do-i-need-to-generate-an-access-token-manually/
- https://dhanhq.co/docs/v2/instruments
- https://dhan.co/support/platforms/dhanhq-api/how-can-i-retrieve-data-for-expired-futures-contracts-using-the-apis/
- https://www.mintlify.com/Anny26022/chartsmaze_clone/api/corporate-actions

**Angel One SmartAPI**
- https://smartapi.angelone.in
- https://smartapi.angelone.in/smartapi/forum/post/11697
- https://smartapi.angelbroking.com/topic/3380/issue-fetching-historical-data/12
- https://smartapi.angelone.in/smartapi/forum/post/4771
- https://smartapi.angelone.in/smartapi/forum/post/16438
- https://smartapi.angelone.in/smartapi/forum/post/19204
- https://smartapi.angelone.in/smartapi/forum/post/19219
- https://smartapi.angelone.in/topic/3392/faqs-on-ab1010-invalid-session-or-session-expired-please-re-login
- https://smartapi.angelone.in/smartapi/forum/post/18262
- https://www.angelone.in/news/market-updates/what-s-changing-in-angel-one-s-smartapi-access-from-april-1-2026
- https://smartapi.angelone.in/smartapi/forum/post/15193

**ICICI Direct Breeze**
- https://icicidirect.com/faqs/f-and-o/what-is-trading-apis
- https://api.icicidirect.com/breezeapi/documents/index.html
- https://www.icicidirect.com/ilearn/stocks/articles/how-to-download-historical-data-using-breeze-api-python-sdk
- https://icicidirect.com/ilearn/stocks/articles/what-is-a-session-key-and-how-to-generate-it-for-using-breezeapi
- https://onetradejournal.com/trading-apis/historical-data-api-india
- https://pypi.org/project/breeze-connect

**Global Datafeeds**
- https://globaldatafeeds.in/global-datafeeds-apis/global-datafeeds-apis/pricing-sales/api-pricing/
- https://globaldatafeeds.in/global-datafeeds-apis/global-datafeeds-apis/introduction/type-of-data-available/
- https://globaldatafeeds.in/global-datafeeds-apis/global-datafeeds-apis/rest-api-documentation/function-gethistory/
- https://globaldatafeeds.in/authorised-data-vendors/

**Benchmark / NSE Indices**
- https://niftyindices.com/reports/historical-data
- https://www.niftyindices.com/resources/index-concepts/total-return-index
- https://niftyindices.com/disclaimer
- https://niftyindices.com/terms-of-use
- https://niftyindices.com/offerings/data-subscription
- https://archives.nseindia.com/supra_global/content/iisl/Nifty_Indices_IOSCO_Compliance_2020.pdf
- https://tradingqna.com/t/nifty-500-tri-historical-data/141395
- https://freefincal.com/download-historical-total-returns-index-data-52-nse-indices/
- https://bharatfintrack.readthedocs.io/en/latest/_modules/BharatFinTrack/nse_tri.html
- https://github.com/jugaad-py/jugaad-data/issues/76
- https://parse.bot/marketplace/cc31af5a-888a-4ecd-b4eb-825a31f9f414/niftyindices-com-api
- https://upstox.com/indices/nifty-500-share-price

**Other / context**
- https://trendlyne.com/subscription/mcp/plans/
- https://nsearchives.nseindia.com//web/mediaattachment/2026-03/NSE_Pricing_file_-_Domestic_clients_20260309171343.pdf
