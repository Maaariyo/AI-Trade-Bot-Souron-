-- Phase 1b: management guidance (SPEC section 6, "Management scorecard").

-- Source documents: earnings-call transcripts, investor presentations, annual reports.
CREATE TABLE documents (
    id           bigserial PRIMARY KEY,
    isin         text        NOT NULL REFERENCES securities (isin),
    doc_type     text        NOT NULL CHECK (doc_type IN ('TRANSCRIPT', 'PRESENTATION', 'ANNUAL_REPORT')),
    doc_date     date        NOT NULL,
    period_label text,
    source_url   text,
    sha256       text        NOT NULL UNIQUE,
    page_count   integer     NOT NULL CHECK (page_count >= 0),
    ingested_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX documents_isin_date_idx ON documents (isin, doc_date DESC);

-- Extracted text per page. The quote check searches this, never the LLM output.
CREATE TABLE document_pages (
    document_id bigint  NOT NULL REFERENCES documents (id),
    page_no     integer NOT NULL CHECK (page_no >= 1),
    text        text    NOT NULL,
    PRIMARY KEY (document_id, page_no)
);

-- Every LLM call's tokens and cost. Budget caps sum this table (CLAUDE.md rule 7).
CREATE TABLE llm_usage (
    id                 bigserial PRIMARY KEY,
    at                 timestamptz NOT NULL DEFAULT now(),
    purpose            text        NOT NULL,
    request_ref        text,
    model_requested    text        NOT NULL,
    model_served       text,
    batch              boolean     NOT NULL,
    input_tokens       integer     NOT NULL DEFAULT 0,
    output_tokens      integer     NOT NULL DEFAULT 0,
    cache_read_tokens  integer     NOT NULL DEFAULT 0,
    cache_write_tokens integer     NOT NULL DEFAULT 0,
    cost_usd           numeric(12, 6) NOT NULL CHECK (cost_usd >= 0)
);

CREATE INDEX llm_usage_at_idx ON llm_usage (at);

-- One row per extraction request, with the raw output kept for audit.
CREATE TABLE extraction_runs (
    id              bigserial PRIMARY KEY,
    document_id     bigint      NOT NULL REFERENCES documents (id),
    custom_id       text        NOT NULL UNIQUE,
    batch_id        text,
    pages           int4range   NOT NULL,
    model_requested text        NOT NULL,
    model_served    text,
    prompt_sha256   text        NOT NULL,
    status          text        NOT NULL
                    CHECK (status IN ('SUBMITTED', 'SUCCEEDED', 'FAILED', 'REFUSED')),
    stop_reason     text,
    raw_output      text,
    error           text,
    submitted_at    timestamptz NOT NULL DEFAULT now(),
    completed_at    timestamptz
);

CREATE INDEX extraction_runs_status_idx ON extraction_runs (status);

-- Guidance rows. Agent 7 may use only QUOTE_VERIFIED and HUMAN_REVIEWED rows
-- (CLAUDE.md rule 10). Targets keep the stated number and unit for the quote
-- check, plus a canonical value (percent, paise or ratio) for code.
CREATE TABLE mgmt_guidance (
    id                 bigserial PRIMARY KEY,
    isin               text    NOT NULL REFERENCES securities (isin),
    document_id        bigint  NOT NULL REFERENCES documents (id),
    extraction_run_id  bigint REFERENCES extraction_runs (id),
    method             text    NOT NULL CHECK (method IN ('llm', 'manual')),
    stated_on          date    NOT NULL,
    metric             text    NOT NULL CHECK (metric IN (
                           'REVENUE', 'REVENUE_GROWTH', 'EBITDA', 'EBITDA_MARGIN',
                           'PAT', 'PAT_GROWTH', 'CAPEX', 'NET_DEBT', 'OTHER')),
    metric_detail      text,
    target_period      text    NOT NULL,
    target_low_stated  numeric NOT NULL,
    target_high_stated numeric NOT NULL,
    unit_stated        text    NOT NULL
                       CHECK (unit_stated IN ('percent', 'inr_crore', 'inr_lakh', 'inr', 'times')),
    target_low         numeric NOT NULL,
    target_high        numeric NOT NULL,
    unit               text    NOT NULL CHECK (unit IN ('percent', 'paise', 'ratio')),
    quote              text    NOT NULL,
    page_no            integer,
    status             text    NOT NULL
                       CHECK (status IN ('EXTRACTED', 'QUOTE_VERIFIED', 'HUMAN_REVIEWED', 'REJECTED')),
    flag               text,
    pre_review_status  text,
    review_note        text,
    reviewed_at        timestamptz,
    created_at         timestamptz NOT NULL DEFAULT now(),
    CHECK (target_high_stated >= target_low_stated),
    CHECK (method = 'llm' OR status IN ('HUMAN_REVIEWED', 'REJECTED'))
);

CREATE INDEX mgmt_guidance_isin_status_idx ON mgmt_guidance (isin, status);
