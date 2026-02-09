from __future__ import annotations

from typing import Any

import requests

from app.config import AISectionsConfig, AISectionsProviderConfig


def get_ai_sections(config: AISectionsConfig, summary: dict[str, Any]) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    for provider_name, provider in (
        ("OpenAI", config.openai),
        ("Grok", config.grok),
        ("Claude", config.claude),
        ("Gemini", config.gemini),
    ):
        if not provider.enabled:
            continue
        provider_sections = _call_provider(provider_name, provider, summary)
        sections.extend(provider_sections)

    if sections:
        return sections

    return _fallback_sections(summary, "No AI sections enabled.")


def _call_provider(
    provider_name: str,
    config: AISectionsProviderConfig,
    summary: dict[str, Any],
) -> list[dict[str, str]]:
    if not config.base_url:
        return _fallback_sections(summary, f"{provider_name} base_url not configured.")

    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"

    payload = {
        "model": config.model,
        "input": {
            "summary": summary,
            "requested_sections": [
                "Executive Summary",
                "Key Risks",
                "Recommendations",
            ],
        },
        "provider": provider_name,
    }

    try:
        response = requests.post(config.base_url, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        data: Any = response.json()
        sections = data.get("sections")
        if isinstance(sections, list) and sections:
            return [
                {
                    "title": str(item.get("title", "Section")),
                    "content": str(item.get("content", "")),
                }
                for item in sections
            ]
    except Exception as exc:  # noqa: BLE001
        return _fallback_sections(summary, f"{provider_name} call failed: {exc}")

    return _fallback_sections(summary, f"{provider_name} response missing sections.")


def _fallback_sections(summary: dict[str, Any], reason: str) -> list[dict[str, str]]:
    return [
        {
            "title": "Executive Summary",
            "content": (
                "AI sections unavailable. This report includes a basic summary only. "
                f"Reason: {reason}"
            ),
        },
        {
            "title": "Key Metrics",
            "content": (
                f"Rows: {summary.get('row_count')}, Columns: {summary.get('column_count')}."
            ),
        },
    ]
