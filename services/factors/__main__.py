"""`make screen [ARGS="--as-of 2026-11-18"]`: compute today's factors and print the ranking."""

import argparse
import logging
from collections.abc import Sequence
from datetime import UTC, date, datetime

from services.db import connect
from services.factors.compute import run_screen
from services.factors.definitions import load_definitions, load_presets
from services.factors.engine import score_universe
from services.money import ist_date


def main(argv: Sequence[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    p = argparse.ArgumentParser(prog="make screen", description=__doc__)
    p.add_argument("--as-of", type=date.fromisoformat, default=ist_date(datetime.now(UTC)))
    p.add_argument("--preset", default=None, help="preset for the printed ranking")
    a = p.parse_args(argv)
    defs, presets = load_definitions(), load_presets()
    weights = presets.presets[a.preset or presets.default]
    with connect() as conn:
        conn.autocommit = True
        run = run_screen(conn, a.as_of, defs)
        from services.factors.compute import load_run

        stocks, values = load_run(conn, run.id)
    res = score_universe(
        stocks,
        values,
        defs,
        weights,
        presets.gates,
        coverage_min=presets.coverage_min,
        min_group_size=presets.min_group_size,
    )
    passed = sum(s.passed for s in res.stocks)
    thin = sum(s.passed and s.thin_data for s in res.stocks)
    print(f"screen run {run.id} as of {run.as_of}: {run.stocks} securities")
    print(f"  pass gates {passed}; thin data {thin}; ranked {len(res.ranked)}")
    if res.unavailable_factors:
        print(f"  factors with no data yet: {', '.join(res.unavailable_factors)}")
    print(f"  top 10 ({a.preset or presets.default}):")
    for s in res.ranked[:10]:
        print(f"    {s.rank:>3}  {s.nse_symbol or s.isin:<14} {s.composite:6.1f}  {s.name}")


if __name__ == "__main__":
    main()
