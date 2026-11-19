# Data vendors: Phase 1 bake-off

19 Nov 2026 · Full notes with every source: [vendor-research-2026-11-19.md](vendor-research-2026-11-19.md)

**How far to trust this:** every finding comes from web-search summaries of the cited pages, not from reading the pages. This build session's network blocked kite.trade and support.zerodha.com. Before paying for anything, open the cited pages yourself and check the rows marked ⚠. Nothing was signed up for or paid for.

## Scores against the six SPEC criteria

✓ yes · ◐ partial · ✗ no · ? unknown

| Vendor | 1. Adjusted EOD, all NSE + BSE | 2. Dividends and corporate actions | 3. Delisted history | 4. Runs unattended | 5. Personal-use licence | 6. `available_from` on fundamentals | Price a month |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Zerodha Kite Connect | ◐ splits and bonuses adjusted, no unadjusted series | ✗ | ✗ | ✗ daily manual login | ◐ personal only, no redistribution | ✗ no fundamentals | ₹500 per app |
| Upstox API | ✓ day candles from 2000, adjusted per staff ⚠ | ✓ API keyed by ISIN (since 11 May 2026) | ✗ | ✓ 1-year read-only Analytics Token | ◐ personal OK per staff ⚠ | ✗ no filing dates found | Free |
| Tapetide | ◐ split/bonus factors; not total return | ✓ events endpoint | ◐ per-day status flag only | ✓ static token | ? no terms found ⚠ | ✓ but estimated before about Sep 2024 | ₹1,499 Pro+ ⚠ (vendor's own page) |
| EODHD | ◐ NSE yes, BSE unconfirmed; `adjusted_close` includes dividends | ✓ dividends and splits endpoints | ✓ 940 delisted NSE tickers | ✓ static token | ✓ personal, single user | ✗ no filing dates for India | $19.99 EOD; $79.98 with fundamentals |
| Dhan | ◐ adjusted for splits and bonuses | ✗ (official) | ? | ◐ token via PIN + TOTP | ? | ✗ | ₹499 + GST |
| TrueData | ◐ NSE; BSE unclear | ◐ separate APIs | ? | ◐ password login in code | ✓ personal only | ? | Quote-based |
| IndianAPI.in, Angel One, ICICI Breeze, Global Datafeeds | Mostly unknown or weak; see the full notes | | | | | | |

## Kite facts that change the build

1. **The login really is manual, every day.** The access token expires at 06:00 IST. Zerodha staff say a daily manual login is an exchange requirement and they don't support automating it. The app follows this rule (CLAUDE.md non-negotiable 5).
2. **Kite rewrites past candles.** Day candles are adjusted for splits and bonuses after the fact, and no unadjusted series exists. Stored history would go stale after every split. **The price ingest now handles this:** every fetch overlaps the last stored day, and if that close has moved by more than 0.2%, the stock's whole history is fetched again.
3. **Dividend adjustment is disputed ⚠.** A Sep 2026 forum answer says candles are also adjusted for dividends above 2%; older staff answers say dividends are never adjusted. If the newer answer is right, adding those dividends back for total returns would count them twice. Resolve this before Phase 7.
4. **No ISIN in the instruments dump.** The app maps Kite instruments to ISINs through the security master: NSE by symbol, BSE by scrip code.
5. **The limit is 3 requests a second with no daily cap, and at most 2,000 days per day-candle request.** These match the defaults in `services/config.py`.
6. **SEBI's retail algo framework changes nothing for data-only use.** The static-IP check applies only to order endpoints.

## Benchmark

**No vendor was confirmed to serve the Nifty 500 TRI.** niftyindices.com has a Total Returns Index section, but Nifty 500 TRI couldn't be confirmed there. NSE Indices' disclaimer says use of its index data requires a licence, and no personal-use exception was found. **Action for you:** email indices@nse.co.in asking for Nifty 500 TRI for personal, non-redistributed research, and its cost. Until then, use the labelled approximate fallback (`docs/DATA.md` step 5).

## Recommendation for D1 (your decision)

I recommend splitting by job rather than buying one vendor:

| Job | Recommended | Why | Monthly cost |
| --- | --- | --- | --- |
| Nightly prices and corporate actions | **Upstox**, if its terms check out | No daily login, ISIN in the instruments list, corporate actions by ISIN, free | ₹0 (needs an Upstox account) |
| Delisted history for the backtest (D5) | **EODHD EOD plan** | The only vendor with documented delisted NSE history, plus dividends and splits | $19.99 (about ₹1,700); could be a one-time backfill month |
| Point-in-time fundamentals | **Tapetide** | The only vendor with `available_from` | ₹1,499 (Pro+, unconfirmed) |
| Fallback for prices | **Kite**, already built | Works today if you accept the daily login | ₹500 |

Against Kite-only (₹500 plus Tapetide ₹1,499), this costs roughly ₹1,200 more a month while EODHD runs, and removes the daily login. If you'd rather not open an Upstox account, keep Kite. It works now; the cost is the 2FA login every weekday.

**Check before paying:**
- **Upstox:** the API terms and whether its candles include dividends.
- **Tapetide:**
  - its data licence;
  - whether a bulk endpoint exists. Pro+ allows 2,500 calls a day, and the gated universe times endpoints may exceed that (`make ingest ARGS="gates"` prints the monthly figure);
  - how much of the history before Sep 2024 is estimated.
- **EODHD:** BSE coverage, and how it handles bonuses and rights for Indian stocks.

## What is built against this

- **Kite** adapter for prices and index candles, with the daily-login flow, alerts and the re-adjustment re-fetch.
- **Vendor-neutral CSV imports** for corporate actions, fundamentals and the TRI, so any vendor's export loads today.
- **Upstox, EODHD and Tapetide** adapters come after you decide D1. Each is a new class behind the interfaces in `services/ingest/`; the tables don't change.
