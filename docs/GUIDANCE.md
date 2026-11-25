# Management guidance (Phase 1b)

Agent 7 scores management on guidance versus delivery. This pipeline turns earnings-call transcripts into guidance rows that code has checked against the source. Only rows that are **QUOTE_VERIFIED** (code found the quote word for word, with the target number inside it) or **HUMAN_REVIEWED** (you approved or typed them) can be used (CLAUDE.md rule 10).

## 1. Load transcripts (free)

Download each transcript or investor-presentation PDF yourself, from the company's investor-relations page or an exchange's announcements page, then:

```bash
make ingest ARGS="transcript --isin INE002A01018 --file ~/Downloads/q2fy27-call.pdf --date 2026-11-10 --period Q2FY27"
```

- `--url https://ir.example.com/call.pdf` fetches a single PDF from a company site instead. Exchange and aggregator sites (nseindia.com, bseindia.com, screener.in, moneycontrol.com) are refused: download those by hand.
- `--type PRESENTATION` or `--type ANNUAL_REPORT` for other documents.
- Loading the same file twice does nothing. Scanned image-only pages have no text and are reported. There is no OCR.
- The security master must already contain the ISIN (`docs/DATA.md` step 1).

## 2a. Extract with Claude (the only paid step)

```bash
make guidance ARGS="extract --dry-run"   # worst-case cost, nothing sent
make guidance ARGS="extract"             # sends one Batches request per document
make guidance ARGS="collect --wait"      # reads results when the batch ends
```

- **Model:** Claude Haiku 5.5 on the Message Batches API, at effort `low`, with structured outputs. Model and effort come from `services/config.py`.
- **Cost:** a 20,000-token transcript costs about $0.002 (under ₹0.25). The worst-case estimate assumes the full 16,000-token output budget.
- **Limits:** the daily and monthly caps and the kill switch are checked before anything is sent. A document is split only if it would pass 80,000 prompt tokens.
- **Audit:** every request's raw output, the served model and its cost are stored in `extraction_runs` and `llm_usage`.
- **What happens after collect:** each row is checked against the stored PDF text. Rows that fail stay **EXTRACTED** with a flag, for example "quote not found in document" or "target 2000 not in quote".
- **Retries:** a failed or truncated document is picked up again by the next `extract`. A refused one is not.

`make guidance ARGS="check"` re-runs the quote check on flagged rows.

## 2b. Enter rows by hand (free, no API key)

```bash
make guidance ARGS="documents"                 # document ids
make guidance ARGS="pages --document 1"        # print the text to copy quotes from
make guidance ARGS="add --document 1 --metric CAPEX --period FY27 --low 1500 --unit inr_crore --quote 'capex will be about Rs 1,500 crore in FY27'"
```

The quote must be found in the stored text and must contain the target number, or the row is refused. Hand-entered rows are stored as HUMAN_REVIEWED.

## 3. Review at http://localhost:3000/guidance

- **Approve** or **Reject** each extracted row. Approving a flagged row requires a note saying why.
- The page shows the agreement rate: the share of reviewed QUOTE_VERIFIED rows you approved.

`make guidance ARGS="stats"` prints status counts, agreement and the extraction cost so far.

## Units

Targets are stored twice: as stated, for the quote check (`15`–`18` `percent`, `1500` `inr_crore`), and in canonical units for code (percent, paise or ratio). One crore = 10,000,000 rupees = 1,000,000,000 paise.

## Phase 1b done-when: status

| Item | Status |
| --- | --- |
| `mgmt_guidance` filled for 20 test companies | Needs your transcripts (step 1), then step 2a or 2b |
| Every row passes the quote check or is flagged | Enforced in code; tested with planted mismatches |
| You review 50 rows with at least 90% agreement | Review at `/guidance`; `stats` prints the rate |
| Extraction cost recorded in SPEC "Cost and latency budget" | Run `stats` after the first real batch and write the figure in |

The actual results that guidance is compared with are computed in code from fundamentals when Agent 7 is built (Phase 3), never by an LLM.
