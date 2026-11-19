-- Security master (SPEC section 4): one row per ISIN, NSE and BSE merged.
-- Rows are never deleted; a delisted company keeps its row and price history.
CREATE TABLE securities (
    isin                 text PRIMARY KEY CHECK (isin ~ '^[A-Z]{2}[A-Z0-9]{9}[0-9]$'),
    name                 text        NOT NULL,
    nse_symbol           text,
    nse_series           text,
    bse_code             text,
    bse_symbol           text,
    is_sme               boolean     NOT NULL DEFAULT false,
    status               text        NOT NULL CHECK (status IN ('ACTIVE', 'SUSPENDED', 'DELISTED')),
    surveillance         text        NOT NULL DEFAULT 'NONE'
                         CHECK (surveillance IN ('NONE', 'ASM', 'GSM')),
    surveillance_stage   text,
    listed_on            date,
    first_seen           date        NOT NULL,
    last_seen            date        NOT NULL,
    delisted_detected_on date,
    updated_at           timestamptz NOT NULL DEFAULT now(),
    CHECK (nse_symbol IS NOT NULL OR bse_code IS NOT NULL)
);

CREATE INDEX securities_nse_symbol_idx ON securities (nse_symbol);
CREATE INDEX securities_bse_code_idx ON securities (bse_code);
CREATE INDEX securities_status_idx ON securities (status);

-- Append-only record of status and surveillance changes, for point-in-time gates.
CREATE TABLE security_status_history (
    isin               text NOT NULL REFERENCES securities (isin),
    as_of              date NOT NULL,
    status             text NOT NULL,
    surveillance       text NOT NULL,
    surveillance_stage text,
    source             text NOT NULL,
    PRIMARY KEY (isin, as_of, source)
);

-- Watchlist (the council list adds it to the top 50; news is polled for it).
CREATE TABLE watchlist (
    isin     text PRIMARY KEY REFERENCES securities (isin),
    added_at timestamptz NOT NULL DEFAULT now(),
    note     text
);
