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
    provider_status: dict[str, str] | None = None,
    overview_text: str | None = None,
    report_title: str | None = None,
    report_description: str | None = None,
    data_file_name: str | None = None,
    report_version: str | None = None,
    cost_estimates: list[Any] | None = None,
) -> dict[str, Any]:
    parsed_insights = _parse_insights(openai_insights)
    for section in parsed_insights:
        section["content_html"] = _format_insight_content(section.get("content", ""))
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
        "provider_status": provider_status or {},
        "overview_text": overview_text or "",
        "report_title": report_title or "",
        "report_description": report_description or "",
        "data_file_name": data_file_name or "",
        "report_version": report_version or "",
        "cost_estimates": cost_estimates or [],
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

    delimiter_sections = _split_delimiter_sections(normalized)
    if len(delimiter_sections) > 1:
        for title, content in delimiter_sections:
            sections.append({"title": _strip_markup(title), "content": _strip_markup(content)})
        return sections

    numbered = _split_numbered_items(normalized)
    if len(numbered) > 1:
        for title, content in numbered:
            sections.append({"title": _strip_markup(title), "content": _strip_markup(content)})
        return sections

    bold_sections = _split_bold_sections(normalized)
    if len(bold_sections) > 1:
        for title, content in bold_sections:
            sections.append({"title": _strip_markup(title), "content": _strip_markup(content)})
        return sections

    current_title = "Overview"
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_lines, current_title
        if current_lines:
            sections.append(
                {
                    "title": _strip_markup(current_title),
                    "content": _strip_markup("\n".join(current_lines).strip()),
                }
            )
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
        return [{"title": "Overview", "content": _strip_markup(normalized.strip())}]

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


def _split_delimiter_sections(text: str) -> list[tuple[str, str]]:
    import re

    items: list[tuple[str, str]] = []
    pattern = re.compile(r"^\s*(#{3,}|\*{3,})\s*(.+)$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    if len(matches) < 2:
        return items

    for idx, match in enumerate(matches):
        title = match.group(2).strip()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        if content:
            items.append((title, content))
    return items


def _strip_markup(text: str) -> str:
    return text.replace("**", "").replace("###", "").replace("***", "").strip()


def _format_insight_content(text: str) -> str:
    import html
    import re

    if not text:
        return ""

    escaped = html.escape(text)
    # Basic bold: **text**
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)

    lines = [line.rstrip() for line in escaped.splitlines()]
    html_parts: list[str] = []
    in_list = False
    list_type = "ul"

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            html_parts.append(f"</{list_type}>")
            in_list = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            close_list()
            html_parts.append("<div class=\"insight-spacer\"></div>")
            continue

        bullet_match = re.match(r"^[-•]\s+(.*)$", stripped)
        number_match = re.match(r"^\d+\.\s+(.*)$", stripped)
        if bullet_match or number_match:
            if not in_list:
                list_type = "ol" if number_match else "ul"
                html_parts.append(f"<{list_type}>")
                in_list = True
            item_text = bullet_match.group(1) if bullet_match else number_match.group(1)
            html_parts.append(f"<li>{item_text}</li>")
        else:
            close_list()
            html_parts.append(f"<p>{stripped}</p>")

    close_list()
    return "".join(html_parts)
