import argparse
import json
import sqlite3
from datetime import datetime


def _update_provider(conn, provider_key, input_rate, output_rate):
    conn.execute(
        """
        UPDATE providers
        SET input_per_1m = ?, output_per_1m = ?, updated_at = ?
        WHERE provider_key = ?
        """,
        (input_rate, output_rate, datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), provider_key),
    )


def main():
    parser = argparse.ArgumentParser(description="Update provider pricing in DB")
    parser.add_argument("--db", default="db/report_overrides.db")
    parser.add_argument("--provider")
    parser.add_argument("--input", type=float)
    parser.add_argument("--output", type=float)
    parser.add_argument("--json")
    args = parser.parse_args()

    if not args.json and not args.provider:
        raise SystemExit("Provide --provider or --json")

    conn = sqlite3.connect(args.db)
    try:
        if args.json:
            data = json.loads(args.json)
            for key, rates in data.items():
                _update_provider(conn, key, float(rates["input"]), float(rates["output"]))
        else:
            if args.input is None or args.output is None:
                raise SystemExit("Provide --input and --output")
            _update_provider(conn, args.provider, args.input, args.output)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
