-- Broker instrument dumps, mapped to ISINs where possible.
CREATE TABLE broker_instruments (
    broker           text    NOT NULL,
    exchange         text    NOT NULL,
    instrument_token bigint  NOT NULL,
    exchange_token   text,
    tradingsymbol    text    NOT NULL,
    name             text,
    instrument_type  text,
    segment          text,
    isin             text REFERENCES securities (isin),
    as_of            date    NOT NULL,
    PRIMARY KEY (broker, exchange, instrument_token)
);

CREATE INDEX broker_instruments_isin_idx ON broker_instruments (isin);

-- Daily candles. Prices are integer paise (CLAUDE.md conventions).
CREATE TABLE daily_prices (
    isin               text    NOT NULL REFERENCES securities (isin),
    exchange           text    NOT NULL CHECK (exchange IN ('NSE', 'BSE')),
    trade_date         date    NOT NULL,
    open_paise         bigint  NOT NULL CHECK (open_paise > 0),
    high_paise         bigint  NOT NULL CHECK (high_paise > 0),
    low_paise          bigint  NOT NULL CHECK (low_paise > 0),
    close_paise        bigint  NOT NULL CHECK (close_paise > 0),
    volume             bigint  NOT NULL CHECK (volume >= 0),
    traded_value_paise bigint  CHECK (traded_value_paise >= 0),
    value_is_estimate  boolean NOT NULL DEFAULT true,
    source             text    NOT NULL,
    ingested_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (isin, exchange, trade_date),
    CHECK (low_paise <= high_paise),
    CHECK (open_paise BETWEEN low_paise AND high_paise),
    CHECK (close_paise BETWEEN low_paise AND high_paise)
);

CREATE INDEX daily_prices_trade_date_idx ON daily_prices (trade_date);

-- Index levels are not money, so they stay numeric.
CREATE TABLE index_prices (
    index_code  text          NOT NULL,
    trade_date  date          NOT NULL,
    open        numeric(14, 4) NOT NULL,
    high        numeric(14, 4) NOT NULL,
    low         numeric(14, 4) NOT NULL,
    close       numeric(14, 4) NOT NULL,
    source      text          NOT NULL,
    ingested_at timestamptz   NOT NULL DEFAULT now(),
    PRIMARY KEY (index_code, trade_date)
);
