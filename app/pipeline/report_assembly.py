from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape


def render_report_html(template_path: Path, context: dict[str, Any]) -> str:
    env = Environment(
        loader=FileSystemLoader(template_path.parent),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template(template_path.name)
    return template.render(**context)


def build_report_context(
    title: str,
    summary: dict[str, Any],
    openai_insights: str,
    secondary_sections: list[dict[str, str]],
    preview_html: str,
    report_type: str,
    queue_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    parsed_insights = _parse_insights(openai_insights)
    return {
        "title": title,
        "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "summary": summary,
        "openai_insights": openai_insights,
        "openai_insights_sections": parsed_insights,
        "secondary_sections": secondary_sections,
        "preview_html": preview_html,
        "report_type": report_type,
        "queue_stats": queue_stats or {},
    }


def _parse_insights(text: str) -> list[dict[str, str]]:
    if not text or not text.strip():
        return [
            {
                "title": "AI Insights",
                "content": "No insights available. Verify the OpenAI API key and connectivity.",
            }
        ]
    normalized = text.replace("\r\n", "\n")
    if "1." in normalized and "\n" not in normalized:
        normalized = normalized.replace(" 1. ", "\n1. ")
    normalized = normalized.replace(" Insights:", "\nInsights:")

    sections: list[dict[str, str]] = []

    numbered = _split_numbered_items(normalized)
    if len(numbered) > 1:
        for title, content in numbered:
            sections.append({"title": title, "content": content})
        return sections

    bold_sections = _split_bold_sections(normalized)
    if len(bold_sections) > 1:
        for title, content in bold_sections:
            sections.append({"title": title, "content": content})
        return sections

    current_title = "Overview"
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_lines, current_title
        if current_lines:
            sections.append({"title": current_title, "content": "\n".join(current_lines).strip()})
            current_lines = []

    for line in normalized.splitlines():
        stripped = line.strip()
        if stripped.startswith("#### "):
            flush()
            current_title = stripped.replace("#### ", "", 1).strip() or "Insight"
        elif stripped.startswith("### "):
            flush()
            current_title = stripped.replace("### ", "", 1).strip() or "Insight"
        elif stripped.startswith("## "):
            flush()
            current_title = stripped.replace("## ", "", 1).strip() or "Insight"
        else:
            current_lines.append(line)

    flush()

    if not sections:
        return [{"title": "Overview", "content": normalized.strip()}]

    return sections


def _split_numbered_items(text: str) -> list[tuple[str, str]]:
    import re

    items: list[tuple[str, str]] = []
    pattern = re.compile(r"(^|\n)\s*(\d+)\.\s+")
    parts = pattern.split(text)
    if len(parts) < 4:
        return items

    it = iter(parts[1:])
    for _sep in it:
        num = next(it, "").strip()
        rest = next(it, "").strip()
        if not rest:
            continue
        title = f"Insight {num}"
        title_match = re.match(r"\*\*(.+?)\*\*[:\-]?\s*(.*)", rest)
        if title_match:
            title = title_match.group(1).strip()
            content = title_match.group(2).strip()
        else:
            colon_idx = rest.find(":")
            if 0 < colon_idx < 80:
                title = rest[:colon_idx].strip()
                content = rest[colon_idx + 1 :].strip()
            else:
                content = rest
        items.append((title or f"Insight {num}", content))
    return items


def _split_bold_sections(text: str) -> list[tuple[str, str]]:
    import re

    items: list[tuple[str, str]] = []
    pattern = re.compile(r"\*\*(.+?)\*\*")
    matches = list(pattern.finditer(text))
    if len(matches) < 2:
        return items

    for idx, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        content = text[start:end].strip(" \n:-")
        if content:
            items.append((title, content.strip()))
    return items
