-- Dividends, splits and bonuses, needed for total returns (SPEC section 4).
-- shares_before:shares_after is the holding change on the ex-date:
-- a 10-to-2 face-value split is 1:5, a 1:1 bonus is 1:2.
CREATE TABLE corporate_actions (
    id                   bigserial PRIMARY KEY,
    isin                 text   NOT NULL REFERENCES securities (isin),
    action_type          text   NOT NULL
                         CHECK (action_type IN ('DIVIDEND', 'SPLIT', 'BONUS', 'RIGHTS', 'OTHER')),
    ex_date              date   NOT NULL,
    record_date          date,
    cash_paise_per_share bigint CHECK (cash_paise_per_share >= 0),
    shares_before        integer CHECK (shares_before > 0),
    shares_after         integer CHECK (shares_after > 0),
    description          text,
    source               text   NOT NULL,
    available_from       timestamptz NOT NULL,
    ingested_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (isin, action_type, ex_date, source),
    CHECK (action_type <> 'DIVIDEND' OR cash_paise_per_share IS NOT NULL),
    CHECK (action_type NOT IN ('SPLIT', 'BONUS')
           OR (shares_before IS NOT NULL AND shares_after IS NOT NULL))
);

CREATE INDEX corporate_actions_isin_ex_date_idx ON corporate_actions (isin, ex_date);

-- Benchmark series. is_approximate marks the fallback built from the price
-- index plus the published dividend yield; the UI labels it "approx. TRI".
CREATE TABLE benchmark_values (
    code           text           NOT NULL,
    trade_date     date           NOT NULL,
    value          numeric(16, 4) NOT NULL CHECK (value > 0),
    is_approximate boolean        NOT NULL,
    method         text           NOT NULL,
    source         text           NOT NULL,
    ingested_at    timestamptz    NOT NULL DEFAULT now(),
    PRIMARY KEY (code, trade_date)
);
