from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any
import csv
import datetime as dt

import pandas as pd


@dataclass
class SnmpParseResult:
    service_df: pd.DataFrame
    twamp_df: pd.DataFrame
    summary: dict[str, Any]
    sample_rows: list[dict[str, Any]]
    preview_html: str


def parse_snmp_performance_csv(
    file_bytes: bytes,
    sample_rows: int = 5,
    preview_rows: int = 20,
) -> SnmpParseResult:
    text = file_bytes.decode("utf-8", errors="ignore")
    lines = text.splitlines()

    service_rows: list[dict[str, Any]] = []
    twamp_rows: list[dict[str, Any]] = []

    current_interval: int | None = None
    current_table: str | None = None
    current_time_utc: str = ""
    current_time_local: str = ""

    idx = 0
    while idx < len(lines):
        raw = lines[idx]
        line = raw.strip()
        if not line:
            idx += 1
            continue

        if "Interval Length (Seconds):" in line:
            current_interval = _parse_interval_seconds(line)

        if line.startswith("Table Name,Entry OID"):
            current_table, current_time_local, current_time_utc = _parse_table_meta(lines, idx + 1)
            idx += 1
            continue

        if current_table == "serviceStatTable" and "srvForwardGreenPackets" in line:
            header = _split_csv_line(raw)
            idx = _consume_rows(
                lines,
                idx + 1,
                header,
                service_rows,
                current_time_local,
                current_time_utc,
                current_interval,
            )
            continue

        if current_table == "twampReportCurrentTable" and line.startswith("twampControllerId"):
            header = _split_csv_line(raw)
            idx = _consume_rows(
                lines,
                idx + 1,
                header,
                twamp_rows,
                current_time_local,
                current_time_utc,
                current_interval,
            )
            continue

        idx += 1

    service_df = pd.DataFrame(service_rows)
    twamp_df = pd.DataFrame(twamp_rows)

    if not service_df.empty:
        _normalize_numeric(service_df)
    if not twamp_df.empty:
        _normalize_numeric(twamp_df)

    summary_df = service_df if not service_df.empty else twamp_df
    if summary_df.empty:
        summary = {"row_count": 0, "column_count": 0, "columns": []}
        sample_rows_data: list[dict[str, Any]] = []
        preview_html = "<p>No SNMP service stats found.</p>"
    else:
        summary = {
            "row_count": int(summary_df.shape[0]),
            "column_count": int(summary_df.shape[1]),
            "columns": [
                {
                    "name": str(col),
                    "dtype": str(summary_df[col].dtype),
                    "missing": int(summary_df[col].isna().sum()),
                }
                for col in summary_df.columns
            ],
        }
        describe = summary_df.describe(include="all").fillna("")
        summary["describe"] = describe.to_dict()
        sample_rows_data = summary_df.head(sample_rows).to_dict(orient="records")
        preview_html = summary_df.head(preview_rows).to_html(index=False, classes="dataframe", border=0)

    return SnmpParseResult(
        service_df=service_df,
        twamp_df=twamp_df,
        summary=summary,
        sample_rows=sample_rows_data,
        preview_html=preview_html,
    )


def analyze_snmp_performance(
    service_df: pd.DataFrame,
    twamp_df: pd.DataFrame,
) -> dict[str, Any]:
    if service_df.empty:
        return {
            "time_range": {"start": "", "end": ""},
            "executive_summary": "No service statistics were detected in this SNMP export.",
            "kpi_rows": [],
            "microburst_rows": [],
            "operations_notes": [
                "Verify serviceStatTable collection for the reporting interval.",
            ],
            "sales_notes": [],
            "customer_notes": [],
            "twamp_summary": "TWAMP data not found.",
        }

    time_series = _parse_time_series(service_df)
    interval_seconds = _mean_interval(service_df)

    totals = _compute_service_totals(service_df)
    avg_packet_size = totals["forwarded_bytes"] / totals["forwarded_packets"] if totals["forwarded_packets"] else 0.0
    discard_rate_avg = _safe_pct(totals["discarded_packets"], totals["forwarded_packets"] + totals["discarded_packets"])
    yellow_pct_avg = _safe_pct(totals["yellow_packets"], totals["forwarded_packets"])

    microburst_rows: list[dict[str, Any]] = []
    max_discard_rate = 0.0
    max_yellow_pct = 0.0
    max_microburst = 0.0
    max_microburst_time = ""

    for _, row in service_df.iterrows():
        forwarded_packets = _to_float(row, "srvForwardGreenPackets") + _to_float(row, "srvForwardYellowPackets")
        discarded_packets = _discard_packets(row)
        discard_rate = _safe_pct(discarded_packets, forwarded_packets + discarded_packets)
        yellow_pct = _safe_pct(_to_float(row, "srvForwardYellowPackets"), forwarded_packets)
        yellow_bytes = _to_float(row, "srvForwardYellowBytes")
        red_bytes = _to_float(row, "srvDiscardRedBytes_fld_num") or _to_float(row, "srvDiscardYellowRedBytes")
        microburst_bps = 0.0
        if interval_seconds:
            microburst_bps = (yellow_bytes + red_bytes) / interval_seconds
        timestamp = row.get("DateTimeUTC") or row.get("DateTimeLocal") or ""

        microburst_rows.append(
            {
                "time": timestamp,
                "discard_rate": discard_rate,
                "yellow_pct": yellow_pct,
                "microburst_bps": microburst_bps,
                "forwarded_packets": int(forwarded_packets),
                "discarded_packets": int(discarded_packets),
            }
        )

        max_discard_rate = max(max_discard_rate, discard_rate)
        max_yellow_pct = max(max_yellow_pct, yellow_pct)
        if microburst_bps > max_microburst:
            max_microburst = microburst_bps
            max_microburst_time = str(timestamp)

    twamp_active = _twamp_is_active(twamp_df)
    twamp_summary = (
        "TWAMP sessions detected; delay/loss metrics available."
        if twamp_active
        else "TWAMP appears inactive; delay/jitter metrics are unavailable."
    )

    executive_summary = (
        "Service performance is stable with low average discard rates and modest yellow traffic. "
        "Microburst stress peaks indicate burst-driven events rather than persistent congestion."
    )
    if discard_rate_avg > 0.3:
        executive_summary = (
            "Service performance shows elevated discard rates with repeated burst-driven stress events. "
            "Consider tuning policing thresholds or increasing capacity."
        )

    kpi_rows = [
        {
            "label": "Monitoring Window (UTC)",
            "value": f"{time_series['start']} to {time_series['end']}",
            "note": "SNMP interval snapshot from the CSV export.",
        },
        {
            "label": "Avg Yellow Traffic (%)",
            "value": f"{yellow_pct_avg:.3f}%",
            "note": f"Peak {max_yellow_pct:.3f}%",
        },
        {
            "label": "Avg Discard Rate (%)",
            "value": f"{discard_rate_avg:.3f}%",
            "note": f"Peak {max_discard_rate:.3f}%",
        },
        {
            "label": "Total Discarded Packets",
            "value": f"{totals['discarded_packets']:,}",
            "note": "Total across intervals.",
        },
        {
            "label": "Total Forwarded Packets",
            "value": f"{totals['forwarded_packets']:,}",
            "note": "Green + Yellow packets.",
        },
        {
            "label": "Forwarded Bytes",
            "value": f"{totals['forwarded_bytes']:,}",
            "note": "Approx. total throughput.",
        },
        {
            "label": "Avg Packet Size (Bytes)",
            "value": f"{avg_packet_size:.0f}",
            "note": "Derived from forwarded bytes/packets.",
        },
        {
            "label": "Peak Microburst Stress (B/s)",
            "value": f"{max_microburst:,.0f}",
            "note": f"Peak at {max_microburst_time or 'N/A'}.",
        },
    ]

    operations_notes = [
        "Validate policer CBS/EBS settings if discard peaks align with burst windows.",
        "Enable TWAMP monitoring to capture latency and jitter during peak stress periods.",
        "Investigate recurring microburst windows for upstream scheduling conflicts.",
    ]
    sales_notes = [
        "Yellow traffic peaks indicate headroom stress; propose higher CIR/EIR tiers.",
        "Microburst-driven discards justify premium SLA or deterministic low-jitter packages.",
    ]
    customer_notes = [
        "Most traffic is forwarded successfully with minimal loss overall.",
        "Burst-heavy workloads may benefit from shaping or additional bandwidth.",
    ]

    return {
        "time_range": time_series,
        "interval_seconds": interval_seconds,
        "totals": totals,
        "avg_packet_size": avg_packet_size,
        "avg_discard_rate": discard_rate_avg,
        "max_discard_rate": max_discard_rate,
        "avg_yellow_pct": yellow_pct_avg,
        "max_yellow_pct": max_yellow_pct,
        "microburst_rows": microburst_rows,
        "microburst_peak_bps": max_microburst,
        "microburst_peak_time": max_microburst_time,
        "executive_summary": executive_summary,
        "kpi_rows": kpi_rows,
        "operations_notes": operations_notes,
        "sales_notes": sales_notes,
        "customer_notes": customer_notes,
        "twamp_summary": twamp_summary,
    }


def _parse_interval_seconds(line: str) -> int | None:
    try:
        part = line.split("Interval Length (Seconds):", 1)[1]
        return int(part.split(",")[0].strip())
    except Exception:
        return None


def _parse_table_meta(lines: list[str], start: int) -> tuple[str | None, str, str]:
    idx = start
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    if idx >= len(lines):
        return None, "", ""
    row = _split_csv_line(lines[idx])
    table_name = row[0].strip() if row else None
    time_local = row[2].strip() if len(row) > 2 else ""
    time_utc = row[3].strip() if len(row) > 3 else ""
    return table_name, time_local, time_utc


def _consume_rows(
    lines: list[str],
    start: int,
    header: list[str],
    collector: list[dict[str, Any]],
    time_local: str,
    time_utc: str,
    interval_seconds: int | None,
) -> int:
    idx = start
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    while idx < len(lines):
        line = lines[idx].strip()
        if not line or line.startswith("Interval State") or line.startswith("Table Name"):
            break
        values = _split_csv_line(lines[idx])
        row = {header[i]: values[i] if i < len(values) else "" for i in range(len(header))}
        row["DateTimeLocal"] = time_local
        row["DateTimeUTC"] = time_utc
        row["interval_seconds"] = interval_seconds or 0
        collector.append(row)
        idx += 1
    return idx


def _split_csv_line(line: str) -> list[str]:
    return next(csv.reader([line]))


def _normalize_numeric(df: pd.DataFrame) -> None:
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = pd.to_numeric(df[col], errors="ignore")
    sentinel_values = {4294967295, 18446744073709551615}
    for col in df.select_dtypes(include="number").columns:
        df.loc[df[col].isin(sentinel_values), col] = pd.NA


def _parse_time_series(df: pd.DataFrame) -> dict[str, str]:
    time_col = None
    for candidate in ("DateTimeUTC", "DateTimeLocal", "Date And Time (UTC)", "Date And Time (Local)"):
        if candidate in df.columns:
            time_col = candidate
            break
    if not time_col:
        return {"start": "", "end": ""}
    times = pd.to_datetime(df[time_col], errors="coerce")
    start = times.min()
    end = times.max()
    return {
        "start": start.strftime("%Y-%m-%d %H:%M:%S") if pd.notna(start) else "",
        "end": end.strftime("%Y-%m-%d %H:%M:%S") if pd.notna(end) else "",
    }


def _mean_interval(df: pd.DataFrame) -> float:
    if "interval_seconds" not in df.columns:
        return 0.0
    values = pd.to_numeric(df["interval_seconds"], errors="coerce").dropna()
    if values.empty:
        return 0.0
    return float(values.mean())


def _to_float(row: pd.Series, key: str) -> float:
    value = row.get(key)
    try:
        return float(value)
    except Exception:
        return 0.0


def _discard_packets(row: pd.Series) -> float:
    green = _to_float(row, "srvDiscardGreenPackets")
    yellow = _to_float(row, "srvDiscardYellowPackets")
    red = _to_float(row, "srvDiscardRedPackets")
    combined = _to_float(row, "srvDiscardYellowRedPackets")
    total = green + yellow + red
    if total == 0 and combined:
        return green + combined
    return total


def _compute_service_totals(df: pd.DataFrame) -> dict[str, float]:
    totals = {
        "forwarded_packets": 0.0,
        "yellow_packets": 0.0,
        "discarded_packets": 0.0,
        "forwarded_bytes": 0.0,
        "discarded_bytes": 0.0,
    }
    totals["forwarded_packets"] = _sum_col(df, "srvForwardGreenPackets") + _sum_col(df, "srvForwardYellowPackets")
    totals["yellow_packets"] = _sum_col(df, "srvForwardYellowPackets")
    totals["discarded_packets"] = _sum_col(df, "srvDiscardGreenPackets") + _sum_col(df, "srvDiscardYellowPackets") + _sum_col(
        df, "srvDiscardRedPackets"
    )
    if totals["discarded_packets"] == 0:
        totals["discarded_packets"] = _sum_col(df, "srvDiscardYellowRedPackets") + _sum_col(df, "srvDiscardGreenPackets")
    totals["forwarded_bytes"] = _sum_col(df, "srvForwardGreenBytes") + _sum_col(df, "srvForwardYellowBytes")
    totals["discarded_bytes"] = _sum_col(df, "srvDiscardGreenBytes") + _sum_col(df, "srvDiscardYellowBytes") + _sum_col(
        df, "srvDiscardRedBytes_fld_num"
    )
    if totals["discarded_bytes"] == 0:
        totals["discarded_bytes"] = _sum_col(df, "srvDiscardYellowRedBytes") + _sum_col(df, "srvDiscardGreenBytes")
    return totals


def _sum_col(df: pd.DataFrame, col: str) -> float:
    if col not in df.columns:
        return 0.0
    return float(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())


def _safe_pct(numerator: float, denominator: float) -> float:
    if not denominator:
        return 0.0
    return (numerator / denominator) * 100


def _twamp_is_active(df: pd.DataFrame) -> bool:
    if df.empty:
        return False
    cols = [
        "twampReportCurrentTxPackets",
        "twampReportCurrentRxValidPackets",
        "twampReportCurrentLossPackets",
    ]
    for col in cols:
        if col in df.columns and pd.to_numeric(df[col], errors="coerce").fillna(0).sum() > 0:
            return True
    return False
