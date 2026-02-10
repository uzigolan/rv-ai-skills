from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Any

from app.config import AppConfig, ReportConfig, AISectionsProviderConfig
from app.pipeline.insights_openai import build_openai_prompt


@dataclass
class CostEstimate:
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    input_per_1m: float
    output_per_1m: float
    estimated_cost: float
    note: str | None = None


def estimate_report_costs(
    config: AppConfig,
    report: ReportConfig,
    summary: dict[str, Any],
    sample_rows: list[dict[str, Any]],
    queue_stats: dict[str, Any] | None = None,
    analysis_data: dict[str, Any] | None = None,
) -> list[CostEstimate]:
    estimates: list[CostEstimate] = []
    chars_per_token = 4

    # OpenAI insights
    if config.ai_sections.openai.enabled:
        prompt = build_openai_prompt(report, summary, sample_rows, queue_stats, analysis_data)
        input_tokens = _estimate_tokens(prompt, chars_per_token)
        output_tokens = 800
        estimates.append(
            _estimate_provider_cost(
                "OpenAI",
                config.ai_sections.openai.model,
                input_tokens,
                output_tokens,
                config.ai_sections.openai,
            )
        )

    # AI sections providers (summary-only payload)
    summary_payload = json.dumps(
        {
            "summary": summary,
            "requested_sections": ["Executive Summary", "Key Risks", "Recommendations"],
        },
        ensure_ascii=False,
    )
    input_tokens_sections = _estimate_tokens(summary_payload, chars_per_token)
    output_tokens_sections = 400

    if config.ai_sections.grok.enabled:
        estimates.append(
            _estimate_provider_cost(
                "Grok",
                config.ai_sections.grok.model,
                input_tokens_sections,
                output_tokens_sections,
                config.ai_sections.grok,
            )
        )
    if config.ai_sections.claude.enabled:
        estimates.append(
            _estimate_provider_cost(
                "Claude",
                config.ai_sections.claude.model,
                input_tokens_sections,
                output_tokens_sections,
                config.ai_sections.claude,
            )
        )
    if config.ai_sections.gemini.enabled:
        estimates.append(
            _estimate_provider_cost(
                "Gemini",
                config.ai_sections.gemini.model,
                input_tokens_sections,
                output_tokens_sections,
                config.ai_sections.gemini,
            )
        )

    return estimates


def _estimate_tokens(text: str, chars_per_token: int) -> int:
    if not text:
        return 0
    return max(1, math.ceil(len(text) / max(chars_per_token, 1)))


def _estimate_provider_cost(
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    pricing: AISectionsProviderConfig,
) -> CostEstimate:
    if pricing.input_per_1m <= 0 or pricing.output_per_1m <= 0:
        return CostEstimate(
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            input_per_1m=pricing.input_per_1m,
            output_per_1m=pricing.output_per_1m,
            estimated_cost=0.0,
            note="Pricing not configured for this provider/model.",
        )
    cost = (input_tokens / 1_000_000) * pricing.input_per_1m + (output_tokens / 1_000_000) * pricing.output_per_1m
    return CostEstimate(
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        input_per_1m=pricing.input_per_1m,
        output_per_1m=pricing.output_per_1m,
        estimated_cost=round(cost, 6),
    )
