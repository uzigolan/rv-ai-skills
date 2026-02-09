from __future__ import annotations

from io import BytesIO
from typing import Any

import pandas as pd


class CsvParseError(Exception):
    pass


def parse_csv(
    file_bytes: bytes,
    sample_rows: int = 5,
    preview_rows: int = 20,
) -> tuple[pd.DataFrame, dict[str, Any], list[dict[str, Any]], str]:
    try:
        buffer = BytesIO(file_bytes)
        df = pd.read_csv(buffer)
    except Exception as exc:  # noqa: BLE001
        raise CsvParseError(f"Failed to parse CSV: {exc}") from exc

    if df.empty:
        raise CsvParseError("CSV is empty.")

    summary = {
        "row_count": int(df.shape[0]),
        "column_count": int(df.shape[1]),
        "columns": [
            {
                "name": str(col),
                "dtype": str(df[col].dtype),
                "missing": int(df[col].isna().sum()),
            }
            for col in df.columns
        ],
    }

    describe = df.describe(include="all").fillna("")
    summary["describe"] = describe.to_dict()

    sample_rows_data = df.head(sample_rows).to_dict(orient="records")
    preview_html = df.head(preview_rows).to_html(index=False, classes="dataframe", border=0)

    return df, summary, sample_rows_data, preview_html
