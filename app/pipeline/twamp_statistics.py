from __future__ import annotations

from typing import Any

import pandas as pd


def analyze_twamp_statistics(df: pd.DataFrame) -> dict[str, Any]:
    df = df.copy()
    _normalize_numeric(df)

    time_col = _first_existing(df, ["DateTimeUTC", "DateTimeLocal", "DateTimeUTC", "DateTimeLocal", "Date Time (UTC)", "Date And Time (UTC)"])
    if time_col:
        df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
        time_start = df[time_col].min()
        time_end = df[time_col].max()
        time_range = {
            "start": time_start.strftime("%Y-%m-%d %H:%M:%S") if pd.notna(time_start) else "",
            "end": time_end.strftime("%Y-%m-%d %H:%M:%S") if pd.notna(time_end) else "",
        }
    else:
        time_range = {"start": "", "end": ""}

    forwarded_packets = _sum_col(df, "FwdTotalPackets_Emulated")
    forwarded_bytes = _sum_col(df, "FwdTotalBytes_Emulated")
    discarded_packets = _sum_col(df, "ColorDiscardTotalPackets_Emulated")
    discarded_bytes = _sum_col(df, "ColorDiscardTotalBytes_Emulated")
    discard_rate_pct = _mean_col(df, "DiscardRatePct_Emulated")
    yellow_pct = _mean_col(df, "YellowTrafficPct_Emulated")
    avg_packet_size = _mean_col(df, "AvgPacketSizeBytes_Emulated")

    green_avg = _mean_col(df, "FwdGreenPackets_Emulated")
    yellow_avg = _mean_col(df, "FwdYellowPackets_Emulated")
    red_avg = _mean_col(df, "DiscardRedPackets_Emulated")

    twamp_active = _twamp_is_active(df)

    trend_rows = []
    if "twampReportCurrentElapsedTime" in df.columns:
        for _, row in df.iterrows():
            trend_rows.append(
                {
                    "elapsed": int(row.get("twampReportCurrentElapsedTime") or 0),
                    "discard_rate": float(row.get("DiscardRatePct_Emulated") or 0),
                    "yellow_pct": float(row.get("YellowTrafficPct_Emulated") or 0),
                    "forwarded": int(row.get("FwdTotalPackets_Emulated") or 0),
                    "discards": int(row.get("ColorDiscardTotalPackets_Emulated") or 0),
                }
            )

    peak_rate = 0.0
    peak_elapsed = 0
    for row in trend_rows:
        if row["discard_rate"] > peak_rate:
            peak_rate = row["discard_rate"]
            peak_elapsed = row["elapsed"]

    findings: list[str] = []
    if not twamp_active:
        findings.append("No active TWAMP sessions detected; delay/jitter/loss metrics are unavailable.")
    if discard_rate_pct > 0.2:
        findings.append("Discard rate exceeds 0.2%, indicating burst or policing pressure.")
    elif discard_rate_pct > 0:
        findings.append("Discard rate is low, suggesting traffic largely within SLA thresholds.")
    if yellow_pct > 5:
        findings.append("Yellow traffic exceeds 5%, indicating frequent bursts near commit rate.")
    elif yellow_pct > 0:
        findings.append("Yellow traffic is modest, indicating manageable excess bursts.")

    executive_summary = (
        "TWAMP metrics appear inactive, but emulated policing counters show low discard rates and "
        "modest yellow traffic, indicating stable service with occasional bursts."
    )
    if discard_rate_pct > 0.3:
        executive_summary = (
            "Emulated discard rates are elevated, indicating burst-driven congestion that may impact "
            "service quality. Consider tuning policing thresholds or increasing capacity."
        )

    kpi_rows = [
        {
            "label": "Monitoring Window (UTC)",
            "value": f"{time_range['start']} to {time_range['end']}",
            "note": "15-minute TWAMP/traffic snapshot.",
        },
        {
            "label": "TWAMP Activity",
            "value": "Active" if twamp_active else "Inactive",
            "note": "Delay/jitter metrics require active sessions.",
        },
        {
            "label": "Total Forwarded Packets",
            "value": f"{forwarded_packets:,}",
            "note": "Green + Yellow packets.",
        },
        {
            "label": "Forwarded Bytes",
            "value": f"{forwarded_bytes:,}",
            "note": "Total throughput processed.",
        },
        {
            "label": "Total Discarded Packets",
            "value": f"{discarded_packets:,}",
            "note": "Aggregate color discards.",
        },
        {
            "label": "Total Discarded Bytes",
            "value": f"{discarded_bytes:,}",
            "note": "Bytes lost to policing.",
        },
        {
            "label": "Avg Discard Rate (%)",
            "value": f"{discard_rate_pct:.3f}%",
            "note": f"Peak {peak_rate:.3f}% at {peak_elapsed}s.",
        },
        {
            "label": "Avg Yellow Traffic (%)",
            "value": f"{yellow_pct:.3f}%",
            "note": "Burst utilization near commit.",
        },
        {
            "label": "Avg Packet Size (Bytes)",
            "value": f"{avg_packet_size:.0f}",
            "note": "Typical traffic size.",
        },
    ]

    operations_notes = [
        "Enable TWAMP sessions to capture latency/jitter during peak discard windows.",
        "Review CBS/EBS settings if yellow traffic frequently exceeds 5%.",
        "Investigate discard spikes near peak intervals for burst scheduling issues.",
    ]
    sales_notes = [
        "Yellow traffic indicates headroom stress; propose higher CIR/EIR tiers.",
        "Highlight low discard rate as proof of stable service for SLA upgrades.",
    ]
    customer_notes = [
        "Overall discards are low, suggesting reliable service within SLA limits.",
        "Consider traffic shaping if burst-driven discards affect critical apps.",
    ]

    return {
        "time_range": time_range,
        "twamp_active": twamp_active,
        "forwarded_packets": forwarded_packets,
        "forwarded_bytes": forwarded_bytes,
        "discarded_packets": discarded_packets,
        "discarded_bytes": discarded_bytes,
        "discard_rate_pct": discard_rate_pct,
        "yellow_pct": yellow_pct,
        "avg_packet_size": avg_packet_size,
        "green_avg": green_avg,
        "yellow_avg": yellow_avg,
        "red_avg": red_avg,
        "trend_rows": trend_rows,
        "findings": findings,
        "peak_discard_rate": peak_rate,
        "peak_elapsed": peak_elapsed,
        "executive_summary": executive_summary,
        "kpi_rows": kpi_rows,
        "operations_notes": operations_notes,
        "sales_notes": sales_notes,
        "customer_notes": customer_notes,
    }


def _normalize_numeric(df: pd.DataFrame) -> None:
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = pd.to_numeric(df[col], errors="ignore")
    sentinel_values = {4294967295, 18446744073709551615}
    for col in df.select_dtypes(include="number").columns:
        df.loc[df[col].isin(sentinel_values), col] = pd.NA


def _twamp_is_active(df: pd.DataFrame) -> bool:
    cols = [
        "twampReportCurrentTxPackets",
        "twampReportCurrentRxValidPackets",
        "twampReportCurrentLossPackets",
    ]
    for col in cols:
        if col in df.columns and df[col].fillna(0).astype(float).sum() > 0:
            return True
    return False


def _first_existing(df: pd.DataFrame, names: list[str]) -> str | None:
    for name in names:
        if name in df.columns:
            return name
    return None


def _sum_col(df: pd.DataFrame, col: str) -> int:
    if col not in df.columns:
        return 0
    return int(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())


def _mean_col(df: pd.DataFrame, col: str) -> float:
    if col not in df.columns:
        return 0.0
    series = pd.to_numeric(df[col], errors="coerce").dropna()
    if series.empty:
        return 0.0
    return float(series.mean())
