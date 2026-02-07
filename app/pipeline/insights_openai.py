from __future__ import annotations

from typing import Any

from openai import OpenAI

from app.config import OpenAIConfig


def get_openai_insights(
    config: OpenAIConfig,
    summary: dict[str, Any],
    sample_rows: list[dict[str, Any]],
    queue_stats: dict[str, Any] | None = None,
) -> str:
    if not config.api_key:
        return "OpenAI API key not configured."

    client = OpenAI(api_key=config.api_key)

    prompt = (
        "You are a data analyst. Provide concise insights based on the CSV summary, queue statistics, "
        "and sample rows. Focus on abnormal or unique behavior, outliers, missing data, time patterns, "
        "and potential operational implications. "
        "Return plain text with short paragraphs.\n\n"
        f"Summary: {summary}\n\n"
        f"Queue Statistics: {queue_stats}\n\n"
        f"Sample rows: {sample_rows}\n"
    )

    try:
        response = client.responses.create(
            model=config.model,
            input=prompt,
        )
        text = response.output_text
        return text.strip() if text else "No insights returned by OpenAI."
    except Exception as exc:  # noqa: BLE001
        return f"OpenAI call failed: {exc}"
