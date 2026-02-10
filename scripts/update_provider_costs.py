from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def _update_provider(db_path: Path, provider: str, input_cost: float, output_cost: float) -> None:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT provider_key FROM providers WHERE provider_key = ?", (provider,)).fetchone()
        if not row:
            return
        conn.execute(
            """
            UPDATE providers
            SET input_per_1m = ?, output_per_1m = ?, updated_at = datetime('now')
            WHERE provider_key = ?
            """,
            (input_cost, output_cost, provider),
        )
        conn.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description="Update provider pricing in the DB.")
    parser.add_argument("--db", default="db/report_overrides.db", help="Path to DB file")
    parser.add_argument("--provider", help="Provider key (e.g., openai)")
    parser.add_argument("--input", type=float, help="Input $ per 1M tokens")
    parser.add_argument("--output", type=float, help="Output $ per 1M tokens")
    parser.add_argument("--json", help="JSON payload for multiple providers")
    args = parser.parse_args()

    db_path = Path(args.db)
    if args.json:
        payload = json.loads(args.json)
        for provider, values in payload.items():
            _update_provider(db_path, provider, float(values["input"]), float(values["output"]))
        return 0

    if not args.provider:
        raise SystemExit("Missing --provider or --json")
    if args.input is None or args.output is None:
        raise SystemExit("Missing --input or --output")

    _update_provider(db_path, args.provider, float(args.input), float(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
