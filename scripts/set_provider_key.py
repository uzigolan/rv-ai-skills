from __future__ import annotations

import argparse
from pathlib import Path

from app.config import load_config
from app.db_overrides import set_provider_api_key


def main() -> None:
    parser = argparse.ArgumentParser(description="Store provider API key securely in the DB")
    parser.add_argument("--provider", required=True, help="Provider key (openai, grok, claude, gemini)")
    parser.add_argument("--api-key", required=True, help="API key to store securely")
    parser.add_argument("--config", default="config.ini", help="Path to config.ini")
    args = parser.parse_args()

    config = load_config(args.config)
    set_provider_api_key(config.database.path, args.provider, args.api_key)
    print(f"Stored API key for {args.provider} in DB.")


if __name__ == "__main__":
    main()
