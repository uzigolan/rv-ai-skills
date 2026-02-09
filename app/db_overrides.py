from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
import sqlite3
from typing import Any

from app.config import ReportConfig


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        _migrate_overrides_table(conn)
        _migrate_providers_table(conn)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS report_types (
                report_type_key TEXT PRIMARY KEY,
                report_type TEXT NOT NULL UNIQUE,
                version TEXT,
                pdf_engine TEXT,
                report_mode TEXT,
                overview_text TEXT,
                name TEXT,
                description TEXT,
                prompt TEXT,
                sample_rows INTEGER,
                delimiter TEXT,
                preview_rows INTEGER,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS providers (
                provider_key TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL,
                api_key TEXT,
                api_key_enc TEXT,
                base_url TEXT,
                model TEXT,
                input_per_1m REAL,
                output_per_1m REAL,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS report_overrides (
                override_key TEXT PRIMARY KEY,
                report_type_key TEXT NOT NULL,
                override_name TEXT NOT NULL,
                version TEXT,
                pdf_engine TEXT,
                report_mode TEXT,
                overview_text TEXT,
                name TEXT,
                description TEXT,
                prompt TEXT,
                sample_rows INTEGER,
                delimiter TEXT,
                preview_rows INTEGER,
                updated_at TEXT,
                UNIQUE(report_type_key, override_name),
                FOREIGN KEY(report_type_key) REFERENCES report_types(report_type_key)
            )
            """
        )
        conn.commit()


def _migrate_overrides_table(conn: sqlite3.Connection) -> None:
    columns = _table_columns(conn, "report_overrides")
    if not columns:
        return
    if "report_type_key" in columns:
        return
    if "report_type" in columns:
        conn.execute("ALTER TABLE report_overrides RENAME TO report_overrides_legacy")
        conn.commit()
        conn.execute("DROP TABLE IF EXISTS report_overrides_legacy")
        conn.commit()


def _migrate_providers_table(conn: sqlite3.Connection) -> None:
    columns = _table_columns(conn, "providers")
    if not columns:
        return
    if "name" in columns:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS providers_new (
                provider_key TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL,
                api_key TEXT,
                api_key_enc TEXT,
                base_url TEXT,
                model TEXT,
                input_per_1m REAL,
                output_per_1m REAL,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO providers_new (
                provider_key, enabled, api_key, api_key_enc, base_url, model,
                input_per_1m, output_per_1m, updated_at
            )
            SELECT provider_key, enabled, api_key, api_key_enc, base_url, model,
                   input_per_1m, output_per_1m, updated_at
            FROM providers
            """
        )
        conn.execute("DROP TABLE providers")
        conn.execute("ALTER TABLE providers_new RENAME TO providers")
        conn.commit()
    if "api_key_enc" not in columns:
        conn.execute("ALTER TABLE providers ADD COLUMN api_key_enc TEXT")
        conn.commit()


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def seed_report_types(db_path: Path, reports: list[ReportConfig]) -> None:
    if not reports:
        return
    with sqlite3.connect(db_path) as conn:
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        for report in reports:
            conn.execute(
                """
                INSERT INTO report_types (
                    report_type_key, report_type, version, pdf_engine, report_mode,
                    overview_text, name, description, prompt, sample_rows,
                    delimiter, preview_rows, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(report_type_key) DO UPDATE SET
                    report_type=excluded.report_type,
                    version=excluded.version,
                    pdf_engine=excluded.pdf_engine,
                    report_mode=excluded.report_mode,
                    overview_text=excluded.overview_text,
                    name=excluded.name,
                    description=excluded.description,
                    prompt=excluded.prompt,
                    sample_rows=excluded.sample_rows,
                    delimiter=excluded.delimiter,
                    preview_rows=excluded.preview_rows,
                    updated_at=excluded.updated_at
                """,
                (
                    report.report_type_key,
                    report.report_type,
                    report.version,
                    report.pdf_engine,
                    report.report_mode,
                    report.overview_text,
                    report.name,
                    report.description,
                    report.prompt,
                    report.sample_rows,
                    report.delimiter,
                    report.preview_rows,
                    now,
                ),
            )
        conn.commit()


def list_report_types(db_path: Path) -> list[dict[str, Any]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT * FROM report_types
            ORDER BY report_type
            """
        ).fetchall()
        return [dict(row) for row in rows]


def load_report_type(db_path: Path, report_type_key: str) -> dict[str, Any] | None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM report_types WHERE report_type_key = ?",
            (report_type_key,),
        ).fetchone()
        if not row:
            return None
        return dict(row)


def load_override(db_path: Path, report_type_key: str, override_name: str) -> dict[str, Any] | None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT * FROM report_overrides
            WHERE report_type_key = ? AND override_name = ?
            """,
            (report_type_key, override_name),
        ).fetchone()
        if not row:
            return None
        return dict(row)


def list_overrides(db_path: Path, report_type_key: str) -> list[dict[str, Any]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT override_name, updated_at
            FROM report_overrides
            WHERE report_type_key = ?
            ORDER BY updated_at DESC
            """,
            (report_type_key,),
        ).fetchall()
        return [dict(row) for row in rows]


def list_overrides_details(db_path: Path, report_type_key: str) -> list[dict[str, Any]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT override_name, version, pdf_engine, report_mode, overview_text, name,
                   description, prompt, sample_rows, delimiter, preview_rows, updated_at
            FROM report_overrides
            WHERE report_type_key = ?
            ORDER BY updated_at DESC
            """,
            (report_type_key,),
        ).fetchall()
        return [dict(row) for row in rows]


def load_override_details(db_path: Path, report_type_key: str, override_name: str) -> dict[str, Any] | None:
    return load_override(db_path, report_type_key, override_name)


def apply_override(report: ReportConfig, override: dict[str, Any]) -> ReportConfig:
    data = asdict(report)
    for key in [
        "version",
        "pdf_engine",
        "report_mode",
        "overview_text",
        "name",
        "description",
        "prompt",
        "sample_rows",
        "delimiter",
        "preview_rows",
    ]:
        if key in override and override[key] not in (None, ""):
            data[key] = override[key]
    return ReportConfig(**data)


def save_override(db_path: Path, report: ReportConfig, override_name: str) -> None:
    payload = asdict(report)
    payload["override_name"] = override_name
    payload["updated_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    override_key = f"{report.report_type_key}:{override_name}"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO report_overrides (
                override_key, report_type_key, override_name, version, pdf_engine, report_mode,
                overview_text, name, description, prompt, sample_rows,
                delimiter, preview_rows, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(report_type_key, override_name) DO UPDATE SET
                version=excluded.version,
                pdf_engine=excluded.pdf_engine,
                report_mode=excluded.report_mode,
                overview_text=excluded.overview_text,
                name=excluded.name,
                description=excluded.description,
                prompt=excluded.prompt,
                sample_rows=excluded.sample_rows,
                delimiter=excluded.delimiter,
                preview_rows=excluded.preview_rows,
                updated_at=excluded.updated_at
            """,
            (
                override_key,
                report.report_type_key,
                override_name,
                payload.get("version"),
                payload.get("pdf_engine"),
                payload.get("report_mode"),
                payload.get("overview_text"),
                payload.get("name"),
                payload.get("description"),
                payload.get("prompt"),
                payload.get("sample_rows"),
                payload.get("delimiter"),
                payload.get("preview_rows"),
                payload.get("updated_at"),
            ),
        )
        conn.commit()


def delete_override(db_path: Path, report_type_key: str, override_name: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "DELETE FROM report_overrides WHERE report_type_key = ? AND override_name = ?",
            (report_type_key, override_name),
        )
        conn.commit()


def seed_providers(db_path: Path, providers: list[dict[str, Any]]) -> None:
    if not providers:
        return
    with sqlite3.connect(db_path) as conn:
        existing_rows = conn.execute("SELECT provider_key FROM providers").fetchall()
        existing_keys = {row[0] for row in existing_rows}
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        for provider in providers:
            key = provider["provider_key"]
            api_key_enc = provider.get("api_key_enc")
            api_key_plain = provider.get("api_key") or ""
            if key in existing_keys:
                conn.execute(
                    """
                    UPDATE providers SET
                        enabled = ?,
                        api_key = '',
                        api_key_enc = COALESCE(?, api_key_enc),
                        base_url = ?,
                        model = ?,
                        input_per_1m = ?,
                        output_per_1m = ?,
                        updated_at = ?
                    WHERE provider_key = ?
                    """,
                    (
                        int(provider["enabled"]),
                        api_key_enc,
                        provider["base_url"],
                        provider["model"],
                        provider["input_per_1m"],
                        provider["output_per_1m"],
                        now,
                        key,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO providers (
                        provider_key, enabled, api_key, api_key_enc, base_url, model,
                        input_per_1m, output_per_1m, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        key,
                        int(provider["enabled"]),
                        "",
                        api_key_enc,
                        provider["base_url"],
                        provider["model"],
                        provider["input_per_1m"],
                        provider["output_per_1m"],
                        now,
                    ),
                )
        conn.commit()


def _provider_key_path(db_path: Path) -> Path:
    return db_path.parent / "provider_keys.key"


def set_provider_api_key(db_path: Path, provider_key: str, api_key: str) -> None:
    from app.security.crypto import protect

    encrypted = protect(api_key, _provider_key_path(db_path))
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE providers
            SET api_key = '', api_key_enc = ?, updated_at = ?
            WHERE provider_key = ?
            """,
            (encrypted, datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), provider_key),
        )
        conn.commit()


def get_provider_api_key(db_path: Path, provider_key: str) -> str:
    from app.security.crypto import unprotect

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT api_key_enc FROM providers WHERE provider_key = ?",
            (provider_key,),
        ).fetchone()
        if not row or not row[0]:
            return ""
        return unprotect(row[0], _provider_key_path(db_path))


def list_providers(db_path: Path) -> list[dict[str, Any]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT provider_key, enabled, base_url, model,
                   input_per_1m, output_per_1m, updated_at
            FROM providers
            ORDER BY provider_key
            """
        ).fetchall()
        return [dict(row) for row in rows]


def get_provider(db_path: Path, provider_key: str) -> dict[str, Any] | None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT provider_key, enabled, base_url, model,
                   input_per_1m, output_per_1m, updated_at
            FROM providers
            WHERE provider_key = ?
            """,
            (provider_key,),
        ).fetchone()
        if not row:
            return None
        return dict(row)


def get_report_type(db_path: Path, report_type_key: str) -> dict[str, Any] | None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT * FROM report_types WHERE report_type_key = ?
            """,
            (report_type_key,),
        ).fetchone()
        if not row:
            return None
        return dict(row)


def save_report_type(db_path: Path, report: dict[str, Any]) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO report_types (
                report_type_key, report_type, version, pdf_engine, report_mode,
                overview_text, name, description, prompt, sample_rows,
                delimiter, preview_rows, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(report_type_key) DO UPDATE SET
                report_type=excluded.report_type,
                version=excluded.version,
                pdf_engine=excluded.pdf_engine,
                report_mode=excluded.report_mode,
                overview_text=excluded.overview_text,
                name=excluded.name,
                description=excluded.description,
                prompt=excluded.prompt,
                sample_rows=excluded.sample_rows,
                delimiter=excluded.delimiter,
                preview_rows=excluded.preview_rows,
                updated_at=excluded.updated_at
            """,
            (
                report["report_type_key"],
                report["report_type"],
                report["version"],
                report["pdf_engine"],
                report["report_mode"],
                report["overview_text"],
                report["name"],
                report["description"],
                report["prompt"],
                report["sample_rows"],
                report["delimiter"],
                report["preview_rows"],
                report["updated_at"],
            ),
        )
        conn.commit()


def delete_report_type(db_path: Path, report_type_key: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM report_types WHERE report_type_key = ?", (report_type_key,))
        conn.commit()


def save_provider(db_path: Path, provider: dict[str, Any]) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO providers (
                provider_key, enabled, api_key, api_key_enc, base_url, model,
                input_per_1m, output_per_1m, updated_at
            ) VALUES (?, ?, '', NULL, ?, ?, ?, ?, ?)
            ON CONFLICT(provider_key) DO UPDATE SET
                enabled=excluded.enabled,
                base_url=excluded.base_url,
                model=excluded.model,
                input_per_1m=excluded.input_per_1m,
                output_per_1m=excluded.output_per_1m,
                updated_at=excluded.updated_at
            """,
            (
                provider["provider_key"],
                int(provider["enabled"]),
                provider["base_url"],
                provider["model"],
                provider["input_per_1m"],
                provider["output_per_1m"],
                provider["updated_at"],
            ),
        )
        conn.commit()


def delete_provider(db_path: Path, provider_key: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM providers WHERE provider_key = ?", (provider_key,))
        conn.commit()
