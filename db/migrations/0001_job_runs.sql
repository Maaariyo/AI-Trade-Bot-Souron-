-- Job state for the APScheduler worker (SPEC section 9: "job state in Postgres").
CREATE TABLE job_runs (
    id          bigserial PRIMARY KEY,
    job_name    text        NOT NULL,
    started_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    status      text        NOT NULL
                CHECK (status IN ('running', 'succeeded', 'failed', 'skipped')),
    detail      text
);

CREATE INDEX job_runs_job_name_started_at_idx ON job_runs (job_name, started_at DESC);
