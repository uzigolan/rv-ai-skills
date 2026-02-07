from __future__ import annotations

import argparse
from io import BytesIO
from pathlib import Path

from flask import Flask, Response, render_template, request, send_file

from app.config import AppConfig, load_config
from app.pipeline.csv_parser import CsvParseError, parse_csv
from app.pipeline.insights_openai import get_openai_insights
from app.pipeline.queues_statistics import analyze_queues_statistics
from app.pipeline.report_assembly import build_report_context, render_report_html
from app.pipeline.sections_secondary_ai import get_secondary_sections


def create_app(config: AppConfig) -> Flask:
    base_dir = Path(__file__).resolve().parents[1]
    template_dir = base_dir / "app" / "templates"

    app = Flask(__name__, template_folder=str(template_dir))
    app.config["APP_CONFIG"] = config

    @app.get("/")
    def index() -> str:
        return render_template("upload.html")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/report")
    def report_html() -> Response:
        config = app.config["APP_CONFIG"]
        if config.report.report_mode.lower() != "local":
            return Response("Report mode not implemented. Set report_mode=local.", status=400)
        file = request.files.get("csv_file")
        if not file:
            return Response("Missing csv_file.", status=400)

        try:
            df, summary, sample_rows, preview_html = parse_csv(file.read())
        except CsvParseError as exc:
            return Response(str(exc), status=400)

        title = f"Report: {file.filename or 'CSV'}"
        queue_stats = analyze_queues_statistics(df)
        openai_insights = get_openai_insights(config.openai, summary, sample_rows, queue_stats)
        secondary_sections = get_secondary_sections(config.secondary_ai, summary)

        context = build_report_context(
            title=title,
            summary=summary,
            openai_insights=openai_insights,
            secondary_sections=secondary_sections,
            preview_html=preview_html,
            report_type=config.report.report_type,
            queue_stats=queue_stats,
        )

        template_path = template_dir / "report.html"
        html = render_report_html(template_path, context)
        return Response(html, mimetype="text/html")

    @app.post("/report/html")
    def report_html_download() -> Response:
        config = app.config["APP_CONFIG"]
        if config.report.report_mode.lower() != "local":
            return Response("Report mode not implemented. Set report_mode=local.", status=400)
        file = request.files.get("csv_file")
        if not file:
            return Response("Missing csv_file.", status=400)

        try:
            df, summary, sample_rows, preview_html = parse_csv(file.read())
        except CsvParseError as exc:
            return Response(str(exc), status=400)

        title = f"Report: {file.filename or 'CSV'}"
        queue_stats = analyze_queues_statistics(df)
        openai_insights = get_openai_insights(config.openai, summary, sample_rows, queue_stats)
        secondary_sections = get_secondary_sections(config.secondary_ai, summary)

        context = build_report_context(
            title=title,
            summary=summary,
            openai_insights=openai_insights,
            secondary_sections=secondary_sections,
            preview_html=preview_html,
            report_type=config.report.report_type,
            queue_stats=queue_stats,
        )

        template_path = template_dir / "report.html"
        html = render_report_html(template_path, context)

        return Response(
            html,
            mimetype="text/html",
            headers={"Content-Disposition": "attachment; filename=report.html"},
        )

    @app.post("/report/pdf")
    def report_pdf() -> Response:
        config = app.config["APP_CONFIG"]
        if config.report.report_mode.lower() != "local":
            return Response("Report mode not implemented. Set report_mode=local.", status=400)
        file = request.files.get("csv_file")
        if not file:
            return Response("Missing csv_file.", status=400)

        try:
            df, summary, sample_rows, preview_html = parse_csv(file.read())
        except CsvParseError as exc:
            return Response(str(exc), status=400)

        title = f"Report: {file.filename or 'CSV'}"
        queue_stats = analyze_queues_statistics(df)
        openai_insights = get_openai_insights(config.openai, summary, sample_rows, queue_stats)
        secondary_sections = get_secondary_sections(config.secondary_ai, summary)

        context = build_report_context(
            title=title,
            summary=summary,
            openai_insights=openai_insights,
            secondary_sections=secondary_sections,
            preview_html=preview_html,
            report_type=config.report.report_type,
            queue_stats=queue_stats,
        )

        template_path = template_dir / "report.html"
        html = render_report_html(template_path, context)
        try:
            from app.pipeline.render_pdf import html_to_pdf
            pdf_bytes = html_to_pdf(html, engine=config.report.pdf_engine)
        except RuntimeError as exc:
            return Response(str(exc), status=500)
        except Exception as exc:  # noqa: BLE001
            return Response(f"PDF generation failed: {exc}", status=500)
        pdf_stream = BytesIO(pdf_bytes)
        pdf_stream.seek(0)

        return send_file(
            pdf_stream,
            mimetype="application/pdf",
            as_attachment=True,
            download_name="report.pdf",
        )

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
    )


if __name__ == "__main__":
    main()
