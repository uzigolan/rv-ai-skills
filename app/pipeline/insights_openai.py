from __future__ import annotations

from typing import Any

from openai import OpenAI

from app.config import ReportConfig, AISectionsProviderConfig


def get_openai_insights(
    report: ReportConfig,
    provider: AISectionsProviderConfig,
    summary: dict[str, Any],
    sample_rows: list[dict[str, Any]],
    queue_stats: dict[str, Any] | None = None,
) -> str:
    if not provider.api_key:
        return "OpenAI API key not configured."

    client = OpenAI(api_key=provider.api_key)

    prompt = build_openai_prompt(report, summary, sample_rows, queue_stats)

    try:
        response = client.responses.create(
            model=provider.model,
            input=prompt,
        )
        _log_openai_response(response)
        text = response.output_text
        return text.strip() if text else "No insights returned by OpenAI."
    except Exception as exc:  # noqa: BLE001
        _log_openai_error(exc)
        return f"OpenAI call failed: {exc}"


def build_openai_prompt(
    report: ReportConfig,
    summary: dict[str, Any],
    sample_rows: list[dict[str, Any]],
    queue_stats: dict[str, Any] | None = None,
) -> str:
    delimiter = report.delimiter.strip() or "###"
    default_prompt = (
        "You are a data analyst. Provide concise insights based on the CSV summary, queue statistics, "
        "and sample rows. Focus on abnormal or unique behavior, outliers, missing data, time patterns, "
        "and potential operational implications.\n\n"
        f"Format output as sections. Start each section with '{delimiter} ' followed by the section title "
        "on the same line, then the section content on following lines.\n\n"
        "Summary: {summary}\n\n"
        "Queue Statistics: {queue_stats}\n\n"
        "Sample rows: {sample_rows}\n"
    )
    prompt_template = report.prompt.strip() if report.prompt.strip() else default_prompt
    return prompt_template.format(
        summary=summary,
        queue_stats=queue_stats,
        sample_rows=sample_rows,
    )


def _log_openai_response(response: Any) -> None:
    import json
    from datetime import datetime
    from pathlib import Path

    log_paths = [
        Path("logs") / "server.log",
        Path(".sandbox") / "server.log",
    ]
    for path in log_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        payload = response.model_dump()
    except Exception:  # noqa: BLE001
        try:
            payload = json.loads(response.model_dump_json())
        except Exception:  # noqa: BLE001
            payload = {"response": str(response)}
    for path in log_paths:
        with path.open("a", encoding="utf-8") as f:
            f.write(f"\n[{timestamp}] OpenAI response:\n")
            f.write(json.dumps(payload, ensure_ascii=False, indent=2))
            f.write("\n")


def _log_openai_error(exc: Exception) -> None:
    from datetime import datetime
    from pathlib import Path

    log_paths = [
        Path("logs") / "server.log",
        Path(".sandbox") / "server.log",
    ]
    for path in log_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for path in log_paths:
        with path.open("a", encoding="utf-8") as f:
            f.write(f"\n[{timestamp}] OpenAI error: {exc}\n")
