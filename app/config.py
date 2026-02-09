from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import configparser
import os

from dotenv import load_dotenv


@dataclass
class ServerConfig:
    host: str
    port: int
    use_https: bool
    cert_path: Path | None
    key_path: Path | None
    debug: bool


@dataclass
class ReportConfig:
    report_type_key: str
    pdf_engine: str
    report_type: str
    report_mode: str
    overview_text: str
    description: str
    prompt: str
    sample_rows: int
    delimiter: str
    name: str
    version: str
    preview_rows: int
    override_name: str


@dataclass
class DatabaseConfig:
    path: Path


@dataclass
class AnalysisConfig:
    abnormal_drop_rate_threshold: float
    top_n_queues: int
    time_bucket_minutes: int
    include_trend_chart: bool
    enable_outliers: bool
    enable_percentiles: bool
    enable_correlations: bool
    enable_conclusion: bool
    enable_recommendations: bool
    outlier_method: str
    per_queue_timeseries: bool
    severity_thresholds: str


@dataclass
class AISectionsProviderConfig:
    enabled: bool
    api_key: str
    base_url: str
    model: str
    input_per_1m: float
    output_per_1m: float


@dataclass
class AISectionsConfig:
    openai: AISectionsProviderConfig
    grok: AISectionsProviderConfig
    claude: AISectionsProviderConfig
    gemini: AISectionsProviderConfig



@dataclass
class AppConfig:
    server: ServerConfig
    report: ReportConfig
    analysis: AnalysisConfig
    ai_sections: AISectionsConfig
    report_map: dict[str, ReportConfig]
    database: DatabaseConfig


def _resolve_path(value: str | None, base_dir: Path) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def _env_or(env: dict[str, str], key: str, fallback: str) -> str:
    value = env.get(key)
    if value is None or value.strip() == "":
        return fallback
    return value


def load_config(config_path: str | Path = "config.ini") -> AppConfig:
    config_path = Path(config_path).resolve()
    base_dir = config_path.parent
    load_dotenv(base_dir / ".env")

    parser = configparser.ConfigParser()
    parser.read(config_path, encoding="utf-8")

    env = os.environ

    database = DatabaseConfig(
        path=_resolve_path(
            _env_or(env, "DATABASE_PATH", parser.get("database", "path", fallback="db/report_overrides.db")),
            base_dir,
        )
        or (base_dir / "db" / "report_overrides.db"),
    )

    server = ServerConfig(
        host=_env_or(env, "SERVER_HOST", parser.get("server", "host", fallback="0.0.0.0")),
        port=int(_env_or(env, "SERVER_PORT", str(parser.get("server", "port", fallback=444)))),
        use_https=str(
            _env_or(env, "SERVER_USE_HTTPS", str(parser.get("server", "use_https", fallback=True)))
        ).lower()
        in {"true", "1", "yes"},
        cert_path=_resolve_path(
            _env_or(env, "SERVER_CERT_PATH", parser.get("server", "cert_path", fallback="")),
            base_dir,
        ),
        key_path=_resolve_path(
            _env_or(env, "SERVER_KEY_PATH", parser.get("server", "key_path", fallback="")),
            base_dir,
        ),
        debug=str(
            _env_or(env, "SERVER_DEBUG", parser.get("server", "debug", fallback="false"))
        ).lower()
        in {"true", "1", "yes"},
    )

    # OpenAI insights now read from ai_sections.openai

    report_sections = sorted([name for name in parser.sections() if name.startswith("reports.")])

    def _report_from_section(section: str) -> ReportConfig:
        report_type = section.split("reports.", 1)[1]
        return ReportConfig(
            report_type_key=report_type,
            pdf_engine=parser.get(section, "pdf_engine", fallback="weasyprint"),
            report_type=report_type,
            report_mode=parser.get(section, "report_mode", fallback="local"),
            overview_text=parser.get(
                section,
                "overview_text",
                fallback="Ethernet Layer 2 queue loss analysis summary.",
            ),
            description=parser.get(section, "description", fallback=""),
            prompt=parser.get(section, "prompt", fallback=""),
            sample_rows=int(parser.get(section, "sample_rows", fallback="5")),
            delimiter=parser.get(section, "delimiter", fallback="###"),
            name=parser.get(section, "name", fallback=report_type.replace("_", " ").title()),
            version=parser.get(section, "version", fallback="v1"),
            preview_rows=int(parser.get(section, "preview_rows", fallback="20")),
            override_name=parser.get(section, "override_name", fallback=""),
        )

    report_seed = [_report_from_section(section) for section in report_sections]

    from app.db_overrides import (
        init_db,
        seed_report_types,
        list_report_types,
        load_override,
        apply_override,
        seed_providers,
    )

    init_db(database.path)
    seed_report_types(database.path, report_seed)

    report_rows = list_report_types(database.path)
    report_map: dict[str, ReportConfig] = {}
    for row in report_rows:
        report_type_key = row.get("report_type_key") or row.get("report_type")
        report_type = row.get("report_type") or report_type_key
        report_map[report_type_key] = ReportConfig(
            report_type_key=report_type_key,
            pdf_engine=row.get("pdf_engine") or "weasyprint",
            report_type=report_type,
            report_mode=row.get("report_mode") or "local",
            overview_text=row.get("overview_text") or "",
            description=row.get("description") or "",
            prompt=row.get("prompt") or "",
            sample_rows=int(row.get("sample_rows") or 5),
            delimiter=row.get("delimiter") or "###",
            name=row.get("name") or report_type.replace("_", " ").title(),
            version=row.get("version") or "v1",
            preview_rows=int(row.get("preview_rows") or 20),
            override_name="",
        )

    if report_map:
        default_report_key = next(iter(report_map.keys()))
    else:
        default_report_key = "queues_statistics"
        report_map[default_report_key] = ReportConfig(
            report_type_key=default_report_key,
            pdf_engine="weasyprint",
            report_type=default_report_key,
            report_mode="local",
            overview_text="Ethernet Layer 2 queue loss analysis summary.",
            description="",
            prompt="",
            sample_rows=5,
            delimiter="###",
            name=default_report_key.replace("_", " ").title(),
            version="v1",
            preview_rows=20,
            override_name="",
        )

    selected_report_key = _env_or(env, "REPORT_TYPE_KEY", _env_or(env, "REPORT_TYPE", default_report_key))
    report = report_map.get(selected_report_key, report_map[default_report_key])

    if report.override_name:
        override = load_override(database.path, report.report_type_key, report.override_name)
        if override:
            report = apply_override(report, override)

    analysis_section = "local-analysis" if parser.has_section("local-analysis") else "analysis"
    analysis = AnalysisConfig(
        abnormal_drop_rate_threshold=float(
            _env_or(
                env,
                "ABNORMAL_DROP_RATE_THRESHOLD",
                parser.get(analysis_section, "abnormal_drop_rate_threshold", fallback="0.05"),
            )
        ),
        top_n_queues=int(
            _env_or(env, "TOP_N_QUEUES", parser.get(analysis_section, "top_n_queues", fallback="5"))
        ),
        time_bucket_minutes=int(
            _env_or(
                env,
                "TIME_BUCKET_MINUTES",
                parser.get(analysis_section, "time_bucket_minutes", fallback="15"),
            )
        ),
        include_trend_chart=str(
            _env_or(
                env,
                "INCLUDE_TREND_CHART",
                parser.get(analysis_section, "include_trend_chart", fallback="true"),
            )
        ).lower()
        in {"true", "1", "yes"},
        enable_outliers=str(
            _env_or(
                env,
                "ENABLE_OUTLIERS",
                parser.get(analysis_section, "enable_outliers", fallback="true"),
            )
        ).lower()
        in {"true", "1", "yes"},
        enable_percentiles=str(
            _env_or(
                env,
                "ENABLE_PERCENTILES",
                parser.get(analysis_section, "enable_percentiles", fallback="true"),
            )
        ).lower()
        in {"true", "1", "yes"},
        enable_correlations=str(
            _env_or(
                env,
                "ENABLE_CORRELATIONS",
                parser.get(analysis_section, "enable_correlations", fallback="true"),
            )
        ).lower()
        in {"true", "1", "yes"},
        enable_conclusion=str(
            _env_or(
                env,
                "ENABLE_CONCLUSION",
                parser.get(analysis_section, "enable_conclusion", fallback="true"),
            )
        ).lower()
        in {"true", "1", "yes"},
        enable_recommendations=str(
            _env_or(
                env,
                "ENABLE_RECOMMENDATIONS",
                parser.get(analysis_section, "enable_recommendations", fallback="true"),
            )
        ).lower()
        in {"true", "1", "yes"},
        outlier_method=_env_or(
            env,
            "OUTLIER_METHOD",
            parser.get(analysis_section, "outlier_method", fallback="iqr"),
        ),
        per_queue_timeseries=str(
            _env_or(
                env,
                "PER_QUEUE_TIMESERIES",
                parser.get(analysis_section, "per_queue_timeseries", fallback="false"),
            )
        ).lower()
        in {"true", "1", "yes"},
        severity_thresholds=_env_or(
            env,
            "SEVERITY_THRESHOLDS",
            parser.get(analysis_section, "severity_thresholds", fallback="0.05,0.2,0.5"),
        ),
    )

    def _provider(section: str, prefix: str, default_enabled: bool) -> AISectionsProviderConfig:
        enabled = _env_or(env, f"{prefix}_ENABLED", parser.get(section, "enabled", fallback=str(default_enabled)))
        return AISectionsProviderConfig(
            enabled=str(enabled).lower() in {"true", "1", "yes"},
            api_key="",
            base_url=_env_or(env, f"{prefix}_BASE_URL", parser.get(section, "base_url", fallback="")),
            model=_env_or(env, f"{prefix}_MODEL", parser.get(section, "model", fallback="")),
            input_per_1m=float(parser.get(section, "input_per_1m", fallback="0")),
            output_per_1m=float(parser.get(section, "output_per_1m", fallback="0")),
        )

    ai_sections = AISectionsConfig(
        openai=_provider("ai_sections.openai", "OPENAI_SECTIONS", True),
        grok=_provider("ai_sections.grok", "GROK_SECTIONS", False),
        claude=_provider("ai_sections.claude", "CLAUDE_SECTIONS", False),
        gemini=_provider("ai_sections.gemini", "GEMINI_SECTIONS", False),
    )

    seed_providers(
        database.path,
        [
            {
                "provider_key": "openai",
                "enabled": ai_sections.openai.enabled,
                "api_key": "",
                "api_key_enc": None,
                "base_url": ai_sections.openai.base_url,
                "model": ai_sections.openai.model,
                "input_per_1m": ai_sections.openai.input_per_1m,
                "output_per_1m": ai_sections.openai.output_per_1m,
            },
            {
                "provider_key": "grok",
                "enabled": ai_sections.grok.enabled,
                "api_key": "",
                "api_key_enc": None,
                "base_url": ai_sections.grok.base_url,
                "model": ai_sections.grok.model,
                "input_per_1m": ai_sections.grok.input_per_1m,
                "output_per_1m": ai_sections.grok.output_per_1m,
            },
            {
                "provider_key": "claude",
                "enabled": ai_sections.claude.enabled,
                "api_key": "",
                "api_key_enc": None,
                "base_url": ai_sections.claude.base_url,
                "model": ai_sections.claude.model,
                "input_per_1m": ai_sections.claude.input_per_1m,
                "output_per_1m": ai_sections.claude.output_per_1m,
            },
            {
                "provider_key": "gemini",
                "enabled": ai_sections.gemini.enabled,
                "api_key": "",
                "api_key_enc": None,
                "base_url": ai_sections.gemini.base_url,
                "model": ai_sections.gemini.model,
                "input_per_1m": ai_sections.gemini.input_per_1m,
                "output_per_1m": ai_sections.gemini.output_per_1m,
            },
        ],
    )

    from app.db_overrides import get_provider_api_key, set_provider_api_key

    if ai_sections.openai.api_key:
        set_provider_api_key(database.path, "openai", ai_sections.openai.api_key)
    if ai_sections.grok.api_key:
        set_provider_api_key(database.path, "grok", ai_sections.grok.api_key)
    if ai_sections.claude.api_key:
        set_provider_api_key(database.path, "claude", ai_sections.claude.api_key)
    if ai_sections.gemini.api_key:
        set_provider_api_key(database.path, "gemini", ai_sections.gemini.api_key)

    ai_sections.openai.api_key = get_provider_api_key(database.path, "openai") or ai_sections.openai.api_key
    ai_sections.grok.api_key = get_provider_api_key(database.path, "grok") or ai_sections.grok.api_key
    ai_sections.claude.api_key = get_provider_api_key(database.path, "claude") or ai_sections.claude.api_key
    ai_sections.gemini.api_key = get_provider_api_key(database.path, "gemini") or ai_sections.gemini.api_key

    return AppConfig(
        server=server,
        report=report,
        analysis=analysis,
        ai_sections=ai_sections,
        report_map=report_map,
        database=database,
    )
