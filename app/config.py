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


@dataclass
class OpenAIConfig:
    api_key: str
    model: str


@dataclass
class SecondaryAIConfig:
    api_key: str
    base_url: str
    model: str


@dataclass
class ReportConfig:
    pdf_engine: str
    report_type: str
    report_mode: str


@dataclass
class AppConfig:
    server: ServerConfig
    openai: OpenAIConfig
    secondary_ai: SecondaryAIConfig
    report: ReportConfig


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
    )

    openai = OpenAIConfig(
        api_key=_env_or(env, "OPENAI_API_KEY", parser.get("openai", "api_key", fallback="")),
        model=_env_or(env, "OPENAI_MODEL", parser.get("openai", "model", fallback="gpt-4o-mini")),
    )

    secondary_ai = SecondaryAIConfig(
        api_key=_env_or(env, "SECONDARY_API_KEY", parser.get("secondary_ai", "api_key", fallback="")),
        base_url=_env_or(env, "SECONDARY_BASE_URL", parser.get("secondary_ai", "base_url", fallback="")),
        model=_env_or(env, "SECONDARY_MODEL", parser.get("secondary_ai", "model", fallback="")),
    )

    report = ReportConfig(
        pdf_engine=_env_or(env, "PDF_ENGINE", parser.get("report", "pdf_engine", fallback="weasyprint")),
        report_type=_env_or(env, "REPORT_TYPE", parser.get("report", "report_type", fallback="queues_statistics")),
        report_mode=_env_or(env, "REPORT_MODE", parser.get("report", "report_mode", fallback="local")),
    )

    return AppConfig(server=server, openai=openai, secondary_ai=secondary_ai, report=report)
