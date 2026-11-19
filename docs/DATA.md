# Loading real data (Phase 1)

The Phase 1 code is tested against hand-written sample files only. These steps load real data. Run them in order, with the stack up (`make up`). Every command is `make ingest ARGS="..."`; `make ingest` alone lists them.

Nothing here fetches from nseindia.com or bseindia.com automatically (CLAUDE.md non-negotiable 5). Where a step uses an exchange file, you download it yourself, for personal research use.

## 1. Security master (weekly)

Download three files by hand:

| File | Where | Notes |
| --- | --- | --- |
| NSE main-board equity list | NSE website, "Securities available for trading" (`EQUITY_L.csv`) | Every row is an active listing |
| NSE SME equity list | NSE website, Emerge (SME) securities list | Same layout family as the main list |
| BSE list of scrips | BSE website, "List of Scrips", segment Equity, status All | Keeps Suspended and Delisted rows |

```bash
make ingest ARGS="security-master --nse ~/Downloads/EQUITY_L.csv --nse-sme ~/Downloads/SME_EQUITY_L.csv --bse ~/Downloads/List_of_Scrips.csv"
```

- The import is a full snapshot: an ISIN missing from all three files is marked DELISTED. Its row and price history are kept.
- If a file's header row doesn't match, the command stops and prints the headers it found. Add the new spelling to the aliases in `services/ingest/security_master.py`.
- BSE SME stocks are detected by group code, defaulting to `M,MT,MS`. Check that against the real file and override it with `--bse-sme-groups` if needed.
- Expect about 5,470 active equities. The command prints the counts.

## 2. Surveillance lists (weekly)

Download the current GSM and ASM lists from the exchanges, then:

```bash
make ingest ARGS="surveillance --gsm ~/Downloads/gsm.csv --asm ~/Downloads/asm.csv"
```

Each file replaces the previous list of that kind. GSM is applied first, so a stock on both lists stays GSM.

## 3. Prices from Kite Connect (every weekday)

1. Create a Kite Connect app (₹500 a month). Set its redirect URL to `http://localhost:8000/kite/callback`.
2. Put `KITE_API_KEY` and `KITE_API_SECRET` in `.env`, then run `make up` again.
3. **Each day**, open http://localhost:8000/kite/login and sign in on Zerodha's page with 2FA. The session lasts until 06:00 IST the next morning. Never script this login.
4. The worker runs the price update at 18:30 IST on weekdays. It retries hourly, and records the run as skipped at 23:00 if you haven't logged in. To run it now:

```bash
make ingest ARGS="prices"
```

The first run backfills 5 years: one request per stock at 3 requests a second, about 30 minutes for the full universe. Later runs fetch only the new days. Index candles (Nifty 50, Nifty 500 and sector indices) come in the same run; any index symbol Kite doesn't recognise is listed in the job's detail.

Kite day candles carry no traded value, so traded value is estimated as typical price × volume and flagged `value_is_estimate`.

Kite adjusts past candles for splits and bonuses after the fact. Each run therefore re-reads the last stored day; if its close has moved by more than 0.2%, that stock's full history is fetched again and overwritten (the run's detail counts these as `rebased`). Because Kite prices are already split-adjusted, total returns use `prices_split_adjusted=True`. Whether Kite also adjusts for dividends above 2% is disputed (see `docs/VENDORS.md`); settle it before Phase 7.

## 4. Measure the price gates

```bash
make ingest ARGS="gates"
```

This prints how many stocks pass the price gates and the fundamentals vendor calls a month that number implies. **Write the pass count into SPEC section 5.** It is a Phase 1 done-when item, and it sizes the fundamentals plan.

## 5. Benchmark

If you have a licensed Nifty 500 TRI file (for example from NSE Indices):

```bash
make ingest ARGS="benchmark --file ~/Downloads/nifty500_tri.csv --source nse-indices"
```

Otherwise, build the labelled fallback from the Nifty 500 price index (loaded in step 3) and a CSV of published monthly dividend yields (`year,month,dividend_yield_pct`):

```bash
make ingest ARGS="benchmark-approx --yields ~/Downloads/nifty500_yields.csv"
```

A licensed value is never overwritten by an approximate one.

## 6. Corporate actions and fundamentals

These need the vendor decision (D1 in `docs/VENDORS.md`). Until an adapter exists, any vendor export can be converted to the project's CSV layouts:

```text
corporate actions: isin,action_type,ex_date,cash_per_share,shares_before,shares_after,record_date,available_from,description
fundamentals:      isin,period_end,period_type,statement,field,value,unit,available_from
```

```bash
make ingest ARGS="actions --file actions.csv --source <vendor>"
make ingest ARGS="fundamentals --file fundamentals.csv --source <vendor>"
```

- `available_from` is required and needs a time zone, for example `2026-07-18T16:00:00+05:30`. It is when the figure became public; backtests never see a row before then.
- Money in the fundamentals file is in rupees (`unit` = `rupees`) and is stored as paise.

## 7. Watchlist and news

Until the Weights Studio lands (Phase 2), add watchlist stocks with SQL:

```bash
docker compose exec db psql -U nivesh -d nivesh -c "INSERT INTO watchlist (isin) VALUES ('INE002A01018')"
```

Put publisher RSS URLs in `NEWS_FEEDS` in `.env` (a JSON list), checking each publisher's terms first, then:

```bash
make ingest ARGS="news"
```

Only headlines and links are stored.

## Phase 1 done-when: status

| Item | Status |
| --- | --- |
| `docs/VENDORS.md` with the bake-off and the D1 decision | Bake-off written, with a recommendation; D1 is your call |
| About 5,470 active ISINs in the security master | Needs step 1 |
| 5 years of daily prices, corporate actions and dividends | Prices need step 3; actions need D1 |
| Benchmark loaded and labelled | Needs step 5 |
| Price-gate pass count in SPEC section 5 | Needs steps 1 and 3, then step 4 |
| `available_from` on every fundamental row | Enforced by the code and a database CHECK |
