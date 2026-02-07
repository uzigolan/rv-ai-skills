from __future__ import annotations

from typing import Any

import pandas as pd


def analyze_queues_statistics(df: pd.DataFrame) -> dict[str, Any]:
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
        .head(5)
        .to_dict(orient="records")
    )
    top_dropped_frames = (
        grouped.sort_values("Dropped (Frames)", ascending=False)
        .head(5)
        .to_dict(orient="records")
    )

    abnormal = grouped[
        (grouped["drop_rate_bytes"] >= 0.05) | (grouped["drop_rate_frames"] >= 0.05)
    ].sort_values(["drop_rate_bytes", "drop_rate_frames"], ascending=False)
    abnormal_queues = abnormal.head(10).to_dict(orient="records")

    trend = _build_trend(df)

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
        "unique": {
            "ne_name": int(df["NE Name"].nunique(dropna=False)),
            "resource_name": int(df["Resource Name"].nunique(dropna=False)),
            "queue_block": int(df["Queue Block"].nunique(dropna=False)),
            "queue_number": int(df["Queue Number"].nunique(dropna=False)),
        },
    }


def _build_trend(df: pd.DataFrame) -> dict[str, Any]:
    trend_df = df.dropna(subset=["Time"]).copy()
    if trend_df.empty:
        return {
            "points": "",
            "labels": [],
            "peak": {"rate_pct": 0, "time_label": ""},
            "total_dropped_frames": 0,
        }

    grouped = (
        trend_df.groupby("Time")[["Dequeued (Frames)", "Dropped (Frames)"]].sum().reset_index()
    )
    grouped["total_frames"] = grouped["Dequeued (Frames)"] + grouped["Dropped (Frames)"]
    grouped["rate"] = grouped["Dropped (Frames)"] / grouped["total_frames"].replace(0, pd.NA)
    grouped["rate"] = grouped["rate"].fillna(0)
    grouped["rate_pct"] = (grouped["rate"] * 100).round(2)
    grouped["time_label"] = grouped["Time"].dt.strftime("%H:%M")

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
