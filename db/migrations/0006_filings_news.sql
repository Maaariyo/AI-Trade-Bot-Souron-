-- Filings: one row per filing page or PDF. Agents web-fetch these URLs one at a time.
CREATE TABLE filings (
    id          bigserial PRIMARY KEY,
    isin        text        NOT NULL REFERENCES securities (isin),
    filed_at    timestamptz NOT NULL,
    category    text        NOT NULL,
    title       text        NOT NULL,
    url         text        NOT NULL,
    summary     text,
    source      text        NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source, url)
);

CREATE INDEX filings_isin_filed_at_idx ON filings (isin, filed_at DESC);

-- News: headlines and links only, never full articles (SPEC section 14).
CREATE TABLE news_items (
    id           bigserial PRIMARY KEY,
    url          text        NOT NULL UNIQUE,
    title        text        NOT NULL,
    publisher    text,
    feed         text        NOT NULL,
    published_at timestamptz,
    isin         text REFERENCES securities (isin),
    matched_by   text,
    ingested_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX news_items_isin_published_idx ON news_items (isin, published_at DESC);

-- One digest per stock per day. method 'headlines' is built in code from
-- news_items; 'llm' digests arrive with the council phases.
CREATE TABLE news_digests (
    isin        text        NOT NULL REFERENCES securities (isin),
    digest_date date        NOT NULL,
    summary     text        NOT NULL,
    item_urls   text[]      NOT NULL,
    method      text        NOT NULL CHECK (method IN ('headlines', 'llm')),
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (isin, digest_date)
);
