# CSV Report Generator

A Flask app that uploads a CSV, calls OpenAI for insights, optionally calls a secondary AI provider for report sections, then assembles a single HTML report and a PDF version.

## Quick Start

1. Create or update `config.ini` with your API keys and HTTPS cert paths.
2. Optionally set overrides in `.env` (loaded automatically).
3. Install dependencies.
4. Run the server.

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python app\server.py --config config.ini
```

Open `https://localhost:444` in your browser.

## Notes

- HTTPS is enabled via `config.ini` and uses the cert and key in `https-certs/` by default.
- PDF generation uses `reportlab` by default (works without system deps). You can switch to `weasyprint` in `config.ini`.
- The secondary AI integration is a placeholder adapter. Adjust the request/response format in `app/pipeline/sections_secondary_ai.py`.
- Report type defaults to `queues_statistics` and uses local analysis plus OpenAI insights.
- `.env` overrides are supported (see `.env` for available keys).

## Download Report

- HTML download: use the **Download HTML** button (POST `/report/html`).
- PDF download: use the **Download PDF** button (POST `/report/pdf`).
