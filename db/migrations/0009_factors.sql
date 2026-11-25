-- Phase 2: factor engine (SPEC section 5).

-- Classification. Percentiles rank within `industry`; when an industry has fewer
-- than 10 stocks after the gates, within its broader `sector`, then the universe.
-- financial_type picks the bank/NBFC factor set.
ALTER TABLE securities
    ADD COLUMN industry       text,
    ADD COLUMN sector         text,
    ADD COLUMN financial_type text NOT NULL DEFAULT 'NONE'
        CHECK (financial_type IN ('NONE', 'BANK', 'NBFC'));

-- Governance flags (auditor resignation, qualified opinion, SEBI order, rating
-- downgrade). governance_checks records that a stock was checked at all, so an
-- unchecked stock counts as missing data, never as clean.
CREATE TABLE governance_events (
    id             bigserial PRIMARY KEY,
    isin           text        NOT NULL REFERENCES securities (isin),
    event_type     text        NOT NULL CHECK (event_type IN (
                       'AUDITOR_RESIGNATION', 'QUALIFIED_OPINION', 'SEBI_ORDER', 'RATING_DOWNGRADE')),
    event_date     date        NOT NULL,
    available_from timestamptz NOT NULL,
    source         text        NOT NULL,
    note           text,
    UNIQUE (isin, event_type, event_date, source)
);

CREATE TABLE governance_checks (
    isin       text        NOT NULL REFERENCES securities (isin),
    checked_at timestamptz NOT NULL,
    source     text        NOT NULL,
    PRIMARY KEY (isin, checked_at, source)
);

-- One screen run per as_of date: the raw inputs the scoring engine needs, so a
-- weight or gate change re-ranks in memory without recomputing factors.
CREATE TABLE screen_runs (
    id               bigserial PRIMARY KEY,
    as_of            date        NOT NULL,
    definitions_sha  text        NOT NULL,
    stocks           integer     NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX screen_runs_as_of_idx ON screen_runs (as_of DESC, id DESC);

CREATE TABLE screen_inputs (
    run_id             bigint  NOT NULL REFERENCES screen_runs (id) ON DELETE CASCADE,
    isin               text    NOT NULL REFERENCES securities (isin),
    name               text    NOT NULL,
    nse_symbol         text,
    industry           text,
    sector             text,
    financial_type     text    NOT NULL,
    status             text    NOT NULL,
    surveillance       text    NOT NULL,
    median_value_paise bigint,
    price_observations integer NOT NULL,
    mcap_paise         bigint,
    quarters           integer NOT NULL,
    PRIMARY KEY (run_id, isin)
);

CREATE TABLE factor_values (
    run_id bigint           NOT NULL REFERENCES screen_runs (id) ON DELETE CASCADE,
    isin   text             NOT NULL,
    factor text             NOT NULL,
    value  double precision NOT NULL CHECK (value = value),  -- rejects NaN
    PRIMARY KEY (run_id, isin, factor)
);

-- Saved Weights Studio profiles.
CREATE TABLE weight_profiles (
    name           text PRIMARY KEY,
    family_weights jsonb       NOT NULL,
    gates          jsonb       NOT NULL,
    agent_weights  jsonb       NOT NULL,
    updated_at     timestamptz NOT NULL DEFAULT now()
);
