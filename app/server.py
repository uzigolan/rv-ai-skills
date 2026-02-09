from __future__ import annotations

import argparse
from io import BytesIO
from pathlib import Path

from flask import Flask, Response, render_template, request, send_file

from app.config import AppConfig, load_config
from app.db_overrides import (
    apply_override,
    list_overrides_details,
    list_overrides,
    load_override,
    load_override_details,
    save_override,
    list_providers,
    get_provider,
    save_provider,
    delete_provider,
    set_provider_api_key,
    list_report_types,
    get_report_type,
    save_report_type,
    delete_report_type,
)
from app.pipeline.csv_parser import CsvParseError, parse_csv
from app.pipeline.cost_estimator import estimate_report_costs
from app.pipeline.insights_openai import get_openai_insights
from app.pipeline.queues_statistics import analyze_queues_statistics
from app.pipeline.report_assembly import build_report_context, render_report_html
from app.pipeline.sections_ai import get_ai_sections


def create_app(config: AppConfig) -> Flask:
    base_dir = Path(__file__).resolve().parents[1]
    template_dir = base_dir / "app" / "templates"

    app = Flask(__name__, template_folder=str(template_dir))
    app.config["APP_CONFIG"] = config

    @app.get("/")
    def index() -> str:
        report_types = [
            {"key": key, "name": report.name} for key, report in sorted(config.report_map.items())
        ]
        if not report_types:
            report_types = [{"key": config.report.report_type_key, "name": config.report.name}]
        report_config = config.report_map.get(config.report.report_type_key, config.report)
        return render_template(
            "upload.html",
            report_types=report_types,
            selected_report=config.report.report_type_key,
            report_config=report_config,
        )

    @app.get("/customize")
    def customize() -> str:
        report_types = [
            {"key": key, "name": report.name} for key, report in sorted(config.report_map.items())
        ]
        if not report_types:
            report_types = [{"key": config.report.report_type_key, "name": config.report.name}]
        return render_template(
            "customize.html",
            report_types=report_types,
            selected_report=config.report.report_type_key,
        )

    @app.get("/providers")
    def providers() -> str:
        providers_list = list_providers(config.database.path)
        return render_template("providers.html", providers=providers_list)

    @app.get("/report-types")
    def report_types_page() -> str:
        report_types = list_report_types(config.database.path)
        return render_template("report_types.html", report_types=report_types)

    @app.get("/report-types/edit")
    def report_types_edit() -> Response:
        report_type_key = request.args.get("report_type") or ""
        if report_type_key:
            report_type = get_report_type(config.database.path, report_type_key)
            if not report_type:
                return Response("Report type not found.", status=404)
        else:
            report_type = {
                "report_type_key": "",
                "report_type": "",
                "version": "1.0",
                "pdf_engine": "reportlab",
                "report_mode": "local",
                "overview_text": "",
                "name": "",
                "description": "",
                "prompt": "",
                "sample_rows": 5,
                "delimiter": "###",
                "preview_rows": 15,
            }
        return Response(
            render_template("report_types_edit.html", report_type=report_type),
            mimetype="text/html",
        )

    @app.post("/report-types/save")
    def report_types_save() -> Response:
        report_type_key = (request.form.get("report_type_key") or "").strip()
        if not report_type_key:
            return Response("Missing report_type_key.", status=400)
        data = {
            "report_type_key": report_type_key,
            "report_type": (request.form.get("report_type") or "").strip() or report_type_key,
            "version": (request.form.get("version") or "").strip(),
            "pdf_engine": (request.form.get("pdf_engine") or "").strip(),
            "report_mode": (request.form.get("report_mode") or "").strip(),
            "overview_text": (request.form.get("overview_text") or "").strip(),
            "name": (request.form.get("name") or "").strip(),
            "description": (request.form.get("description") or "").strip(),
            "prompt": (request.form.get("prompt") or "").strip(),
            "sample_rows": int(request.form.get("sample_rows") or 5),
            "delimiter": (request.form.get("delimiter") or "").strip(),
            "preview_rows": int(request.form.get("preview_rows") or 15),
            "updated_at": __import__("datetime").datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        }
        save_report_type(config.database.path, data)
        return Response("Saved report type.", status=200)

    @app.post("/report-types/delete")
    def report_types_delete() -> Response:
        report_type_key = (request.form.get("report_type_key") or "").strip()
        if not report_type_key:
            return Response("Missing report_type_key.", status=400)
        delete_report_type(config.database.path, report_type_key)
        return Response("Deleted report type.", status=200)

    @app.get("/providers/edit")
    def providers_edit() -> Response:
        provider_key = request.args.get("provider") or ""
        if provider_key:
            provider = get_provider(config.database.path, provider_key)
            if not provider:
                return Response("Provider not found.", status=404)
        else:
            provider = {
                "provider_key": "",
                "enabled": 0,
                "base_url": "",
                "model": "",
                "input_per_1m": 0.0,
                "output_per_1m": 0.0,
            }
        return Response(
            render_template("providers_edit.html", provider=provider),
            mimetype="text/html",
        )

    @app.post("/providers/save")
    def providers_save() -> Response:
        provider_key = (request.form.get("provider_key") or "").strip()
        if not provider_key:
            return Response("Missing provider_key.", status=400)
        provider = {
            "provider_key": provider_key,
            "enabled": 1 if (request.form.get("enabled") or "").lower() in {"true", "1", "yes", "on"} else 0,
            "base_url": (request.form.get("base_url") or "").strip(),
            "model": (request.form.get("model") or "").strip(),
            "input_per_1m": float(request.form.get("input_per_1m") or 0),
            "output_per_1m": float(request.form.get("output_per_1m") or 0),
            "updated_at": __import__("datetime").datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        }
        save_provider(config.database.path, provider)
        return Response("Saved provider.", status=200)

    @app.post("/providers/delete")
    def providers_delete() -> Response:
        provider_key = (request.form.get("provider_key") or "").strip()
        if not provider_key:
            return Response("Missing provider_key.", status=400)
        delete_provider(config.database.path, provider_key)
        return Response("Deleted provider.", status=200)

    @app.post("/providers/key")
    def providers_key() -> Response:
        provider_key = (request.form.get("provider_key") or "").strip()
        api_key = (request.form.get("api_key") or "").strip()
        if not provider_key or not api_key:
            return Response("Missing provider_key or api_key.", status=400)
        set_provider_api_key(config.database.path, provider_key, api_key)
        return Response("Updated provider key.", status=200)

    @app.get("/customize/view")
    def customize_view() -> Response:
        report_type_key = request.args.get("report_type") or config.report.report_type_key
        override_name = request.args.get("override_name") or ""
        if not override_name:
            return Response("Missing override_name.", status=400)
        data = load_override_details(config.database.path, report_type_key, override_name)
        if not data:
            return Response("Override not found.", status=404)
        return Response(
            render_template(
                "override_view.html",
                report_type=report_type_key,
                override_name=override_name,
                data=data,
            ),
            mimetype="text/html",
        )

    @app.get("/customize/edit")
    def customize_edit() -> Response:
        report_type_key = request.args.get("report_type") or config.report.report_type_key
        override_name = request.args.get("override_name") or ""
        if override_name:
            data = load_override_details(config.database.path, report_type_key, override_name)
            if not data:
                return Response("Override not found.", status=404)
        else:
            base_report = config.report_map.get(report_type_key, config.report)
            data = {
                "name": base_report.name,
                "version": base_report.version,
                "pdf_engine": base_report.pdf_engine,
                "report_mode": base_report.report_mode,
                "sample_rows": base_report.sample_rows,
                "preview_rows": base_report.preview_rows,
                "delimiter": base_report.delimiter,
                "overview_text": base_report.overview_text,
                "description": base_report.description,
                "prompt": base_report.prompt,
            }
        return Response(
            render_template(
                "override_edit.html",
                report_types=[
                    {"key": key, "name": report.name} for key, report in sorted(config.report_map.items())
                ],
                selected_report=report_type_key,
                override_name=override_name or "",
                data=data,
            ),
            mimetype="text/html",
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/report/config")
    def report_config() -> dict[str, str | int]:
        report_type_key = request.args.get("report_type")
        report_cfg = _get_report_config(config, report_type_key)
        return {
            "report_type": report_cfg.report_type_key,
            "name": report_cfg.name,
            "version": report_cfg.version,
            "pdf_engine": report_cfg.pdf_engine,
            "report_mode": report_cfg.report_mode,
            "sample_rows": report_cfg.sample_rows,
            "preview_rows": report_cfg.preview_rows,
            "delimiter": report_cfg.delimiter,
            "overview_text": report_cfg.overview_text,
            "description": report_cfg.description,
            "prompt": report_cfg.prompt,
        }

    @app.get("/report/overrides")
    def report_overrides() -> dict[str, list[dict[str, str]]]:
        report_type_key = request.args.get("report_type") or config.report.report_type_key
        overrides = list_overrides(config.database.path, report_type_key)
        return {"overrides": overrides}

    @app.get("/report/overrides/details")
    def report_overrides_details() -> dict[str, list[dict[str, str | int]]]:
        report_type_key = request.args.get("report_type") or config.report.report_type_key
        overrides = list_overrides_details(config.database.path, report_type_key)
        return {"overrides": overrides}

    @app.get("/report/override")
    def report_override() -> dict[str, str | int] | Response:
        report_type_key = request.args.get("report_type") or config.report.report_type_key
        override_name = request.args.get("override_name") or ""
        if not override_name:
            return Response("Missing override_name.", status=400)
        data = load_override_details(config.database.path, report_type_key, override_name)
        if not data:
            return Response("Override not found.", status=404)
        return {
            "report_type": report_type_key,
            "name": data.get("name") or "",
            "version": data.get("version") or "",
            "pdf_engine": data.get("pdf_engine") or "",
            "report_mode": data.get("report_mode") or "",
            "sample_rows": int(data.get("sample_rows") or 0),
            "preview_rows": int(data.get("preview_rows") or 0),
            "delimiter": data.get("delimiter") or "",
            "overview_text": data.get("overview_text") or "",
            "description": data.get("description") or "",
            "prompt": data.get("prompt") or "",
            "override_name": override_name,
        }

    @app.post("/report")
    def report_html() -> Response:
        config = app.config["APP_CONFIG"]
        report_config = _get_report_config(
            config,
            request.form.get("report_type"),
            request.form.get("override_name"),
        )
        missing = _missing_provider_keys(config)
        if missing:
            return Response(
                f"Missing API keys for enabled providers: {', '.join(missing)}.",
                status=400,
            )
        if report_config.report_mode.lower() != "local":
            return Response("Report mode not implemented. Set report_mode=local.", status=400)
        file = request.files.get("csv_file")
        if not file:
            return Response("Missing csv_file.", status=400)

        try:
            df, summary, sample_rows, preview_html = parse_csv(
                file.read(),
                sample_rows=report_config.sample_rows,
                preview_rows=report_config.preview_rows,
            )
        except CsvParseError as exc:
            return Response(str(exc), status=400)

        report_name = report_config.name
        file_name = file.filename or "CSV"
        title = f"{report_name} Report - {file_name}"
        queue_stats = analyze_queues_statistics(
            df,
            abnormal_drop_rate_threshold=config.analysis.abnormal_drop_rate_threshold,
            top_n_queues=config.analysis.top_n_queues,
            time_bucket_minutes=config.analysis.time_bucket_minutes,
            include_trend_chart=config.analysis.include_trend_chart,
            enable_outliers=config.analysis.enable_outliers,
            enable_percentiles=config.analysis.enable_percentiles,
            enable_correlations=config.analysis.enable_correlations,
            enable_conclusion=config.analysis.enable_conclusion,
            enable_recommendations=config.analysis.enable_recommendations,
            outlier_method=config.analysis.outlier_method,
            per_queue_timeseries=config.analysis.per_queue_timeseries,
            severity_thresholds=config.analysis.severity_thresholds,
        )
        openai_insights = get_openai_insights(
            report_config,
            config.ai_sections.openai,
            summary,
            sample_rows,
            queue_stats,
        )
        secondary_sections = get_ai_sections(config.ai_sections, summary)
        cost_estimates = estimate_report_costs(
            config,
            report_config,
            summary,
            sample_rows,
            queue_stats,
        )

        context = build_report_context(
            title=title,
            summary=summary,
            openai_insights=openai_insights,
            secondary_sections=secondary_sections,
            preview_html=preview_html,
            report_type=report_config.report_type,
            queue_stats=queue_stats,
            provider_status=_provider_status(config),
            overview_text=report_config.overview_text,
            report_title=report_name,
            report_description=report_config.description,
            data_file_name=file_name,
            report_version=report_config.version,
            cost_estimates=cost_estimates,
        )

        template_path = template_dir / "report.html"
        html = render_report_html(template_path, context)
        return Response(html, mimetype="text/html")

    @app.post("/report/html")
    def report_html_download() -> Response:
        config = app.config["APP_CONFIG"]
        report_config = _get_report_config(
            config,
            request.form.get("report_type"),
            request.form.get("override_name"),
        )
        missing = _missing_provider_keys(config)
        if missing:
            return Response(
                f"Missing API keys for enabled providers: {', '.join(missing)}.",
                status=400,
            )
        if report_config.report_mode.lower() != "local":
            return Response("Report mode not implemented. Set report_mode=local.", status=400)
        file = request.files.get("csv_file")
        if not file:
            return Response("Missing csv_file.", status=400)

        try:
            df, summary, sample_rows, preview_html = parse_csv(
                file.read(),
                sample_rows=report_config.sample_rows,
                preview_rows=report_config.preview_rows,
            )
        except CsvParseError as exc:
            return Response(str(exc), status=400)

        report_name = report_config.name
        file_name = file.filename or "CSV"
        title = f"{report_name} Report - {file_name}"
        queue_stats = analyze_queues_statistics(
            df,
            abnormal_drop_rate_threshold=config.analysis.abnormal_drop_rate_threshold,
            top_n_queues=config.analysis.top_n_queues,
            time_bucket_minutes=config.analysis.time_bucket_minutes,
            include_trend_chart=config.analysis.include_trend_chart,
            enable_outliers=config.analysis.enable_outliers,
            enable_percentiles=config.analysis.enable_percentiles,
            enable_correlations=config.analysis.enable_correlations,
            enable_conclusion=config.analysis.enable_conclusion,
            enable_recommendations=config.analysis.enable_recommendations,
            outlier_method=config.analysis.outlier_method,
            per_queue_timeseries=config.analysis.per_queue_timeseries,
            severity_thresholds=config.analysis.severity_thresholds,
        )
        openai_insights = get_openai_insights(
            report_config,
            config.ai_sections.openai,
            summary,
            sample_rows,
            queue_stats,
        )
        secondary_sections = get_ai_sections(config.ai_sections, summary)
        cost_estimates = estimate_report_costs(
            config,
            report_config,
            summary,
            sample_rows,
            queue_stats,
        )

        context = build_report_context(
            title=title,
            summary=summary,
            openai_insights=openai_insights,
            secondary_sections=secondary_sections,
            preview_html=preview_html,
            report_type=report_config.report_type,
            queue_stats=queue_stats,
            provider_status=_provider_status(config),
            overview_text=report_config.overview_text,
            report_title=report_name,
            report_description=report_config.description,
            data_file_name=file_name,
            report_version=report_config.version,
            cost_estimates=cost_estimates,
        )

        template_path = template_dir / "report.html"
        html = render_report_html(template_path, context)

        timestamp = _report_timestamp()
        filename = f"report_{timestamp}.html"
        return Response(
            html,
            mimetype="text/html",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    @app.post("/report/pdf")
    def report_pdf() -> Response:
        config = app.config["APP_CONFIG"]
        report_config = _get_report_config(
            config,
            request.form.get("report_type"),
            request.form.get("override_name"),
        )
        missing = _missing_provider_keys(config)
        if missing:
            return Response(
                f"Missing API keys for enabled providers: {', '.join(missing)}.",
                status=400,
            )
        if report_config.report_mode.lower() != "local":
            return Response("Report mode not implemented. Set report_mode=local.", status=400)
        file = request.files.get("csv_file")
        if not file:
            return Response("Missing csv_file.", status=400)

        try:
            df, summary, sample_rows, preview_html = parse_csv(
                file.read(),
                sample_rows=report_config.sample_rows,
                preview_rows=report_config.preview_rows,
            )
        except CsvParseError as exc:
            return Response(str(exc), status=400)

        report_name = report_config.name
        file_name = file.filename or "CSV"
        title = f"{report_name} Report - {file_name}"
        queue_stats = analyze_queues_statistics(
            df,
            abnormal_drop_rate_threshold=config.analysis.abnormal_drop_rate_threshold,
            top_n_queues=config.analysis.top_n_queues,
            time_bucket_minutes=config.analysis.time_bucket_minutes,
            include_trend_chart=config.analysis.include_trend_chart,
            enable_outliers=config.analysis.enable_outliers,
            enable_percentiles=config.analysis.enable_percentiles,
            enable_correlations=config.analysis.enable_correlations,
            enable_conclusion=config.analysis.enable_conclusion,
            enable_recommendations=config.analysis.enable_recommendations,
            outlier_method=config.analysis.outlier_method,
            per_queue_timeseries=config.analysis.per_queue_timeseries,
            severity_thresholds=config.analysis.severity_thresholds,
        )
        openai_insights = get_openai_insights(
            report_config,
            config.ai_sections.openai,
            summary,
            sample_rows,
            queue_stats,
        )
        secondary_sections = get_ai_sections(config.ai_sections, summary)
        cost_estimates = estimate_report_costs(
            config,
            report_config,
            summary,
            sample_rows,
            queue_stats,
        )

        context = build_report_context(
            title=title,
            summary=summary,
            openai_insights=openai_insights,
            secondary_sections=secondary_sections,
            preview_html=preview_html,
            report_type=report_config.report_type,
            queue_stats=queue_stats,
            provider_status=_provider_status(config),
            overview_text=report_config.overview_text,
            report_title=report_name,
            report_description=report_config.description,
            data_file_name=file_name,
            report_version=report_config.version,
            cost_estimates=cost_estimates,
        )

        template_path = template_dir / "report.html"
        html = render_report_html(template_path, context)
        try:
            from app.pipeline.render_pdf import html_to_pdf
            pdf_bytes = html_to_pdf(html, engine=report_config.pdf_engine)
        except RuntimeError as exc:
            return Response(str(exc), status=500)
        except Exception as exc:  # noqa: BLE001
            return Response(f"PDF generation failed: {exc}", status=500)
        pdf_stream = BytesIO(pdf_bytes)
        pdf_stream.seek(0)

        timestamp = _report_timestamp()
        filename = f"report_{timestamp}.pdf"
        return send_file(
            pdf_stream,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename,
        )

    @app.post("/report/costs")
    def report_costs() -> Response:
        config = app.config["APP_CONFIG"]
        report_config = _get_report_config(
            config,
            request.form.get("report_type"),
            request.form.get("override_name"),
        )
        file = request.files.get("csv_file")
        if not file:
            return Response("Missing csv_file.", status=400)

        try:
            df, summary, sample_rows, _preview_html = parse_csv(
                file.read(),
                sample_rows=report_config.sample_rows,
                preview_rows=report_config.preview_rows,
            )
        except CsvParseError as exc:
            return Response(str(exc), status=400)

        queue_stats = analyze_queues_statistics(
            df,
            abnormal_drop_rate_threshold=config.analysis.abnormal_drop_rate_threshold,
            top_n_queues=config.analysis.top_n_queues,
            time_bucket_minutes=config.analysis.time_bucket_minutes,
            include_trend_chart=config.analysis.include_trend_chart,
            enable_outliers=config.analysis.enable_outliers,
            enable_percentiles=config.analysis.enable_percentiles,
            enable_correlations=config.analysis.enable_correlations,
            enable_conclusion=config.analysis.enable_conclusion,
            enable_recommendations=config.analysis.enable_recommendations,
            outlier_method=config.analysis.outlier_method,
            per_queue_timeseries=config.analysis.per_queue_timeseries,
            severity_thresholds=config.analysis.severity_thresholds,
        )

        cost_estimates = estimate_report_costs(
            config,
            report_config,
            summary,
            sample_rows,
            queue_stats,
        )

        return Response(
            render_template(
                "costs.html",
                report_title=report_config.name,
                report_type=report_config.report_type,
                cost_estimates=cost_estimates,
            ),
            mimetype="text/html",
        )

    @app.post("/report/customize")
    def report_customize() -> Response:
        config = app.config["APP_CONFIG"]
        report_type = request.form.get("report_type")
        override_name = (request.form.get("override_name") or "").strip()
        if not override_name:
            return Response("Missing override_name.", status=400)

        base_config = _get_report_config(config, report_type)
        data = base_config.__dict__.copy()

        def _take_str(key: str) -> None:
            value = (request.form.get(key) or "").strip()
            if value:
                data[key] = value

        def _take_int(key: str) -> None:
            raw = (request.form.get(key) or "").strip()
            if raw:
                data[key] = int(raw)

        _take_str("name")
        _take_str("description")
        _take_str("overview_text")
        _take_str("prompt")
        _take_str("delimiter")
        _take_str("pdf_engine")
        _take_str("report_mode")
        _take_str("version")
        _take_int("sample_rows")
        _take_int("preview_rows")

        updated = base_config.__class__(**data)
        save_override(config.database.path, updated, override_name)
        return Response("Saved override.", status=200)

    @app.post("/report/override/delete")
    def report_override_delete() -> Response:
        config = app.config["APP_CONFIG"]
        report_type = request.form.get("report_type") or config.report.report_type_key
        override_name = (request.form.get("override_name") or "").strip()
        if not override_name:
            return Response("Missing override_name.", status=400)
        from app.db_overrides import delete_override

        delete_override(config.database.path, report_type, override_name)
        return Response("Deleted override.", status=200)

    return app


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CSV Report Generator")
    parser.add_argument("--config", default="config.ini", help="Path to config.ini")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    config = load_config(args.config)
    app = create_app(config)

    ssl_context = None
    if config.server.use_https:
        if not config.server.cert_path or not config.server.key_path:
            raise RuntimeError("HTTPS enabled but cert_path or key_path is missing.")
        ssl_context = (str(config.server.cert_path), str(config.server.key_path))

    app.run(
        host=config.server.host,
        port=config.server.port,
        ssl_context=ssl_context,
        debug=config.server.debug,
    )


def _report_timestamp() -> str:
    from datetime import datetime

    return datetime.now().strftime("%y%m%d_%H%M")


def _provider_status(config: AppConfig) -> dict[str, str]:
    return {
        "OpenAI Insights": "enabled" if config.ai_sections.openai.enabled else "disabled",
        "Grok Insights": "enabled" if config.ai_sections.grok.enabled else "disabled",
        "Claude Insights": "enabled" if config.ai_sections.claude.enabled else "disabled",
        "Gemini Insights": "enabled" if config.ai_sections.gemini.enabled else "disabled",
    }


def _get_report_config(
    config: AppConfig,
    requested: str | None,
    override_name: str | None = None,
) -> ReportConfig:
    report_config = config.report
    if requested and requested in config.report_map:
        report_config = config.report_map[requested]
    override = (override_name or "").strip()
    if override:
        override_data = load_override(config.database.path, report_config.report_type_key, override)
        if override_data:
            report_config = apply_override(report_config, override_data)
    return report_config


def _missing_provider_keys(config: AppConfig) -> list[str]:
    missing: list[str] = []
    if config.ai_sections.openai.enabled and not config.ai_sections.openai.api_key:
        missing.append("OpenAI")
    if config.ai_sections.grok.enabled and not config.ai_sections.grok.api_key:
        missing.append("Grok")
    if config.ai_sections.claude.enabled and not config.ai_sections.claude.api_key:
        missing.append("Claude")
    if config.ai_sections.gemini.enabled and not config.ai_sections.gemini.api_key:
        missing.append("Gemini")
    return missing


if __name__ == "__main__":
    main()
