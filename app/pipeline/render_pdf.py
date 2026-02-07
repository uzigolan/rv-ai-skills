from __future__ import annotations

from __future__ import annotations

from io import BytesIO
import html as html_lib
import re


def html_to_pdf(html: str, engine: str = "weasyprint") -> bytes:
    engine = (engine or "weasyprint").lower()
    if engine == "weasyprint":
        try:
            from weasyprint import HTML
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "PDF engine not available. Install system dependencies for WeasyPrint or "
                "switch PDF engine in config."
            ) from exc

        return HTML(string=html).write_pdf()

    if engine == "reportlab":
        return _html_to_reportlab_pdf(html)

    raise RuntimeError(f"Unsupported PDF engine: {engine}")


def _html_to_reportlab_pdf(html: str) -> bytes:
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("ReportLab not installed. Add reportlab to requirements.") from exc

    text = _html_to_text(html)
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    text_obj = c.beginText(40, height - 40)
    text_obj.setFont("Helvetica", 10)
    for line in text.splitlines():
        if text_obj.getY() < 40:
            c.drawText(text_obj)
            c.showPage()
            text_obj = c.beginText(40, height - 40)
            text_obj.setFont("Helvetica", 10)
        text_obj.textLine(line)

    c.drawText(text_obj)
    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.read()


def _html_to_text(html: str) -> str:
    # Basic cleanup for readable PDF text output.
    text = re.sub(r"(?is)<(script|style).*?>.*?</\\1>", "", html)
    text = re.sub(r"(?i)<br\\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p>|</div>|</h[1-6]>", "\n", text)
    text = re.sub(r"(?is)<.*?>", "", text)
    text = html_lib.unescape(text)
    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text
