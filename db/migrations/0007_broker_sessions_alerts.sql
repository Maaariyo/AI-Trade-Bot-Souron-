-- Broker sessions from the manual daily login (CLAUDE.md: never automate it).
-- Tokens stay on the server; the API never returns them.
CREATE TABLE broker_sessions (
    id           bigserial PRIMARY KEY,
    broker       text        NOT NULL,
    access_token text        NOT NULL,
    user_id      text,
    login_time   timestamptz NOT NULL,
    expires_at   timestamptz NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    CHECK (expires_at > login_time)
);

CREATE INDEX broker_sessions_broker_expires_idx ON broker_sessions (broker, expires_at DESC);

-- Dashboard alerts. At most one open alert per kind.
CREATE TABLE alerts (
    id          bigserial PRIMARY KEY,
    kind        text        NOT NULL,
    message     text        NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz
);

CREATE UNIQUE INDEX alerts_one_open_per_kind ON alerts (kind) WHERE resolved_at IS NULL;
