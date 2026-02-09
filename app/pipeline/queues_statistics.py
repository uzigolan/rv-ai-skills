from __future__ import annotations

from typing import Any

import pandas as pd


def analyze_queues_statistics(
    df: pd.DataFrame,
    abnormal_drop_rate_threshold: float = 0.05,
    top_n_queues: int = 5,
    time_bucket_minutes: int = 15,
    include_trend_chart: bool = True,
    enable_outliers: bool = True,
    enable_percentiles: bool = True,
    enable_correlations: bool = True,
    enable_conclusion: bool = True,
    enable_recommendations: bool = True,
    outlier_method: str = "iqr",
    per_queue_timeseries: bool = False,
    severity_thresholds: str = "0.05,0.2,0.5",
) -> dict[str, Any]:
    df = df.copy()
    df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
    numeric_cols = [
        "Dequeued (Bytes)",
        "Dequeued (Frames)",
        "Dropped (Bytes)",
        "Dropped (Frames)",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    time_min = df["Time"].min()
    time_max = df["Time"].max()

    totals = {
        "dequeued_bytes": int(df["Dequeued (Bytes)"].sum()),
        "dequeued_frames": int(df["Dequeued (Frames)"].sum()),
        "dropped_bytes": int(df["Dropped (Bytes)"].sum()),
        "dropped_frames": int(df["Dropped (Frames)"].sum()),
    }
    total_bytes = totals["dequeued_bytes"] + totals["dropped_bytes"]
    total_frames = totals["dequeued_frames"] + totals["dropped_frames"]

    drop_rate_bytes = totals["dropped_bytes"] / total_bytes if total_bytes else 0
    drop_rate_frames = totals["dropped_frames"] / total_frames if total_frames else 0

    group_cols = ["NE Name", "Resource Name", "Queue Block", "Queue Number"]
    grouped = df.groupby(group_cols, dropna=False)[numeric_cols].sum().reset_index()
    grouped["drop_rate_bytes"] = grouped["Dropped (Bytes)"] / (
        grouped["Dequeued (Bytes)"] + grouped["Dropped (Bytes)"]
    ).replace(0, pd.NA)
    grouped["drop_rate_frames"] = grouped["Dropped (Frames)"] / (
        grouped["Dequeued (Frames)"] + grouped["Dropped (Frames)"]
    ).replace(0, pd.NA)
    grouped["drop_rate_bytes"] = grouped["drop_rate_bytes"].fillna(0)
    grouped["drop_rate_frames"] = grouped["drop_rate_frames"].fillna(0)

    top_dropped_bytes = (
        grouped.sort_values("Dropped (Bytes)", ascending=False)
        .head(top_n_queues)
        .to_dict(orient="records")
    )
    top_dropped_frames = (
        grouped.sort_values("Dropped (Frames)", ascending=False)
        .head(top_n_queues)
        .to_dict(orient="records")
    )

    abnormal = grouped[
        (grouped["drop_rate_bytes"] >= abnormal_drop_rate_threshold)
        | (grouped["drop_rate_frames"] >= abnormal_drop_rate_threshold)
    ].sort_values(["drop_rate_bytes", "drop_rate_frames"], ascending=False)
    abnormal_queues = abnormal.head(max(10, top_n_queues)).to_dict(orient="records")

    trend = _build_trend(df, time_bucket_minutes) if include_trend_chart else {
        "points": "",
        "labels": [],
        "peak": {"rate_pct": 0, "time_label": ""},
        "total_dropped_frames": 0,
    }

    percentiles = _compute_percentiles(df) if enable_percentiles else {}
    outliers = _compute_outliers(df, outlier_method) if enable_outliers else {}
    correlations = _compute_correlations(df) if enable_correlations else {}
    conclusion = _build_conclusion(
        totals=totals,
        drop_rates={"bytes": drop_rate_bytes, "frames": drop_rate_frames},
        abnormal_count=len(abnormal_queues),
        enable=enable_conclusion,
    )
    recommendations = _build_recommendations(
        drop_rates={"bytes": drop_rate_bytes, "frames": drop_rate_frames},
        abnormal_count=len(abnormal_queues),
        enable=enable_recommendations,
    )
    anomalies = _build_anomaly_flags(
        grouped,
        thresholds=severity_thresholds,
    )
    per_queue_trends = (
        _build_per_queue_trends(df, time_bucket_minutes) if per_queue_timeseries else {}
    )

    return {
        "time_range": {
            "start": time_min.isoformat() if pd.notna(time_min) else "",
            "end": time_max.isoformat() if pd.notna(time_max) else "",
        },
        "totals": totals,
        "drop_rates": {
            "bytes": drop_rate_bytes,
            "frames": drop_rate_frames,
        },
        "top_dropped_bytes": top_dropped_bytes,
        "top_dropped_frames": top_dropped_frames,
        "abnormal_queues": abnormal_queues,
        "trend": trend,
        "percentiles": percentiles,
        "outliers": outliers,
        "correlations": correlations,
        "conclusion": conclusion,
        "recommendations": recommendations,
        "anomalies": anomalies,
        "per_queue_trends": per_queue_trends,
        "unique": {
            "ne_name": int(df["NE Name"].nunique(dropna=False)),
            "resource_name": int(df["Resource Name"].nunique(dropna=False)),
            "queue_block": int(df["Queue Block"].nunique(dropna=False)),
            "queue_number": int(df["Queue Number"].nunique(dropna=False)),
        },
    }


def _build_trend(df: pd.DataFrame, time_bucket_minutes: int) -> dict[str, Any]:
    trend_df = df.dropna(subset=["Time"]).copy()
    if trend_df.empty:
        return {
            "points": "",
            "labels": [],
            "peak": {"rate_pct": 0, "time_label": ""},
            "total_dropped_frames": 0,
        }

    bucket = max(1, int(time_bucket_minutes))
    trend_df["TimeBucket"] = trend_df["Time"].dt.floor(f"{bucket}min")
    grouped = (
        trend_df.groupby("TimeBucket")[["Dequeued (Frames)", "Dropped (Frames)"]].sum().reset_index()
    )
    grouped["total_frames"] = grouped["Dequeued (Frames)"] + grouped["Dropped (Frames)"]
    grouped["rate"] = grouped["Dropped (Frames)"] / grouped["total_frames"].replace(0, pd.NA)
    grouped["rate"] = grouped["rate"].fillna(0)
    grouped["rate_pct"] = (grouped["rate"] * 100).round(2)
    grouped["time_label"] = grouped["TimeBucket"].dt.strftime("%H:%M")

    labels = grouped[["time_label", "rate_pct"]].to_dict(orient="records")
    peak_row = grouped.loc[grouped["rate_pct"].idxmax()] if not grouped.empty else None
    peak = {
        "rate_pct": float(peak_row["rate_pct"]) if peak_row is not None else 0,
        "time_label": str(peak_row["time_label"]) if peak_row is not None else "",
    }

    points = _build_svg_points(grouped["rate_pct"].tolist())
    total_dropped_frames = int(grouped["Dropped (Frames)"].sum())

    return {
        "points": points,
        "labels": labels,
        "peak": peak,
        "total_dropped_frames": total_dropped_frames,
    }


def _build_svg_points(rates: list[float]) -> str:
    if not rates:
        return ""
    width = 560
    height = 200
    pad_left = 30
    pad_top = 10
    pad_bottom = 20
    chart_width = width - pad_left
    chart_height = height - pad_top - pad_bottom

    max_rate = max(max(rates), 1)
    count = len(rates)
    points = []
    for idx, rate in enumerate(rates):
        if count == 1:
            x = pad_left + chart_width / 2
        else:
            x = pad_left + (chart_width * idx / (count - 1))
        y = pad_top + (chart_height * (1 - rate / max_rate))
        points.append(f"{x:.1f},{y:.1f}")
    return " ".join(points)


def _compute_percentiles(df: pd.DataFrame) -> dict[str, dict[str, float]]:
    percentiles = {}
    for col in ["Dequeued (Bytes)", "Dropped (Bytes)", "Dequeued (Frames)", "Dropped (Frames)"]:
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if series.empty:
            continue
        percentiles[col] = {
            "p50": float(series.quantile(0.50)),
            "p90": float(series.quantile(0.90)),
            "p95": float(series.quantile(0.95)),
            "p99": float(series.quantile(0.99)),
        }
    return percentiles


def _compute_outliers(df: pd.DataFrame, method: str) -> dict[str, list[dict[str, Any]]]:
    outliers: dict[str, list[dict[str, Any]]] = {}
    for col in ["Dropped (Bytes)", "Dropped (Frames)", "Dequeued (Bytes)", "Dequeued (Frames)"]:
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if series.empty:
            continue
        method_lc = (method or "iqr").lower()
        if method_lc == "zscore":
            mean = series.mean()
            std = series.std() or 1
            z = (pd.to_numeric(df[col], errors="coerce") - mean) / std
            mask = z.abs() > 3
        else:
            q1 = series.quantile(0.25)
            q3 = series.quantile(0.75)
            iqr = q3 - q1
            threshold = q3 + 1.5 * iqr
            mask = pd.to_numeric(df[col], errors="coerce") > threshold
        rows = df.loc[mask, ["NE Name", "Resource Name", "Queue Block", "Queue Number", "Time", col]]
        outliers[col] = rows.head(10).to_dict(orient="records")
    return outliers


def _compute_correlations(df: pd.DataFrame) -> dict[str, float]:
    cols = ["Dequeued (Bytes)", "Dropped (Bytes)", "Dequeued (Frames)", "Dropped (Frames)"]
    numeric = df[cols].apply(pd.to_numeric, errors="coerce")
    corr = numeric.corr()
    return {
        "bytes": float(corr.loc["Dequeued (Bytes)", "Dropped (Bytes)"]),
        "frames": float(corr.loc["Dequeued (Frames)", "Dropped (Frames)"]),
    }


def _build_anomaly_flags(grouped: pd.DataFrame, thresholds: str) -> list[dict[str, Any]]:
    levels = [0.05, 0.2, 0.5]
    try:
        parts = [float(x.strip()) for x in thresholds.split(",") if x.strip()]
        if len(parts) >= 3:
            levels = parts[:3]
    except Exception:  # noqa: BLE001
        pass
    low, medium, high = sorted(levels)

    flags = []
    for _, row in grouped.iterrows():
        rate = max(float(row["drop_rate_bytes"]), float(row["drop_rate_frames"]))
        if rate >= high:
            severity = "high"
        elif rate >= medium:
            severity = "medium"
        elif rate >= low:
            severity = "low"
        else:
            continue
        flags.append(
            {
                "NE Name": row["NE Name"],
                "Resource Name": row["Resource Name"],
                "Queue Block": row["Queue Block"],
                "Queue Number": row["Queue Number"],
                "drop_rate": rate,
                "severity": severity,
            }
        )
    return flags[:50]


def _build_conclusion(
    totals: dict[str, int],
    drop_rates: dict[str, float],
    abnormal_count: int,
    enable: bool,
) -> str:
    if not enable:
        return ""
    parts = []
    if drop_rates["bytes"] >= 0.1 or drop_rates["frames"] >= 0.1:
        parts.append("High drop rates indicate potential congestion or capacity issues.")
    if abnormal_count > 0:
        parts.append(f"Detected {abnormal_count} abnormal queue(s) requiring review.")
    if totals["dropped_bytes"] > totals["dequeued_bytes"]:
        parts.append("Dropped bytes exceed dequeued bytes, suggesting severe loss.")
    if not parts:
        parts.append("No critical anomalies detected based on current thresholds.")
    return " ".join(parts)


def _build_recommendations(
    drop_rates: dict[str, float],
    abnormal_count: int,
    enable: bool,
) -> list[str]:
    if not enable:
        return []
    recs = []
    if drop_rates["bytes"] >= 0.1 or drop_rates["frames"] >= 0.1:
        recs.append("Investigate congestion hotspots and increase capacity where needed.")
    if abnormal_count > 0:
        recs.append("Review abnormal queues for misconfiguration or overload.")
    recs.append("Add targeted monitoring during peak time windows.")
    return recs


def _build_per_queue_trends(df: pd.DataFrame, time_bucket_minutes: int) -> dict[str, str]:
    bucket = max(1, int(time_bucket_minutes))
    df = df.copy()
    df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
    df["TimeBucket"] = df["Time"].dt.floor(f"{bucket}min")
    df["Dropped (Frames)"] = pd.to_numeric(df["Dropped (Frames)"], errors="coerce").fillna(0)
    df["Dequeued (Frames)"] = pd.to_numeric(df["Dequeued (Frames)"], errors="coerce").fillna(0)
    df["rate"] = df["Dropped (Frames)"] / (
        df["Dropped (Frames)"] + df["Dequeued (Frames)"]
    ).replace(0, pd.NA)
    df["rate"] = df["rate"].fillna(0)

    trends: dict[str, str] = {}
    group_cols = ["NE Name", "Resource Name", "Queue Block", "Queue Number"]
    for key, group in df.groupby(group_cols):
        grouped = group.groupby("TimeBucket")["rate"].mean().reset_index()
        points = _build_svg_points((grouped["rate"] * 100).tolist())
        label = " | ".join(str(part) for part in key)
        trends[label] = points
    return trends
