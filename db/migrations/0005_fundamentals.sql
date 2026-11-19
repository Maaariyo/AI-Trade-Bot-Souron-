-- Point-in-time fundamentals (SPEC section 5). Long format so any vendor fits.
-- A restatement is a new row with a later available_from; nothing is overwritten.
-- Money values are in paise (unit 'paise'); ratios and percentages keep their unit.
CREATE TABLE fundamentals (
    isin           text        NOT NULL REFERENCES securities (isin),
    period_end     date        NOT NULL,
    period_type    text        NOT NULL CHECK (period_type IN ('Q', 'H', 'FY', 'TTM')),
    statement      text        NOT NULL
                   CHECK (statement IN ('PL', 'BS', 'CF', 'RATIO', 'SHAREHOLDING')),
    field          text        NOT NULL,
    value          numeric     NOT NULL,
    unit           text        NOT NULL
                   CHECK (unit IN ('paise', 'ratio', 'percent', 'count', 'shares', 'days')),
    available_from timestamptz NOT NULL,
    source         text        NOT NULL,
    ingested_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (isin, period_end, period_type, statement, field, source, available_from),
    CHECK (available_from::date >= period_end)
);

CREATE INDEX fundamentals_isin_available_idx ON fundamentals (isin, available_from);
