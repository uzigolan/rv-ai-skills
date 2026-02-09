# CSV Report Generator

A Flask app that uploads a CSV, runs local analysis, optionally calls AI providers for insights and sections, then assembles a single HTML report and a PDF version.

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
- AI Sections support multiple providers (OpenAI, Grok, Claude, Gemini) via `[ai_sections.*]` config.
- Report types are stored in the database and are seeded/updated from `[reports.*]` sections in `config.ini` on server start.
- `.env` overrides are supported (see `.env` for available keys).

## Download Report

- HTML download: use the **Download HTML** button (POST `/report/html`).
- PDF download: use the **Download PDF** button (POST `/report/pdf`).

## Customize Overrides

- Manage overrides at `https://localhost:444/customize`.
- Create a new override or edit existing ones per report type.
- Overrides are stored in `db/report_overrides.db` and applied by name during report generation.
- View and edit pages:
  - `/customize/view?report_type=<key>&override_name=<name>`
  - `/customize/edit?report_type=<key>&override_name=<name>`

## Configuration Overview

### Server

- `[server] host, port, use_https, cert_path, key_path, debug`

### Database

- `[database] path` points to the SQLite file for report types and overrides.

### Report Types (Seed)

Report types are seeded/updated from `config.ini` on startup. Each `reports.<type>` section supports:

- `version`
- `pdf_engine`
- `report_mode`
- `overview_text`
- `name`
- `description`
- `prompt`
- `sample_rows`
- `delimiter`
- `preview_rows`
- `override_name` (optional default override name)

### OpenAI Insights

OpenAI insights now use `[ai_sections.openai]` settings (prompt, delimiter, sample rows).

### AI Sections Providers

Enable providers with `enabled = true` under:
- `[ai_sections.openai]`
- `[ai_sections.grok]`
- `[ai_sections.claude]`
- `[ai_sections.gemini]`

Only enabled providers are called and shown in the report.

Each provider section supports:
- `enabled`
- `base_url`
- `model`
- `input_per_1m`
- `output_per_1m`

API keys are stored securely in the DB (encrypted) and are **not** stored in `config.ini`.

### Secure API Keys (DB)

API keys are stored **encrypted** in the database using a local Fernet key stored at `db/provider_keys.key` (not checked into git). This encryption method is used on all platforms (Windows, Linux, macOS).

Set a provider key:

```powershell
.\.sandbox\venv\Scripts\python.exe scripts\set_provider_key.py --provider openai --api-key YOUR_KEY
```

Supported provider keys: `openai`, `grok`, `claude`, `gemini`.

### Pricing (Cost Estimates)

Cost estimates are based on approximate token counts and the rates configured under each provider:

- `[ai_sections.openai]` → `input_per_1m`, `output_per_1m`
- `[ai_sections.grok]` → `input_per_1m`, `output_per_1m`
- `[ai_sections.claude]` → `input_per_1m`, `output_per_1m`
- `[ai_sections.gemini]` → `input_per_1m`, `output_per_1m`

Update rates if you change models. Estimates appear in the report as “Estimated AI Cost”.

### Local Analysis

Local analysis is configured under `[analysis]` (or `[local-analysis]` if you choose to add it).  
Options include:
- `abnormal_drop_rate_threshold`
- `top_n_queues`
- `time_bucket_minutes`
- `include_trend_chart`
- `enable_outliers` (iqr or zscore via `outlier_method`)
- `enable_percentiles`
- `enable_correlations`
- `enable_conclusion`
- `enable_recommendations`
- `per_queue_timeseries`
- `severity_thresholds`

## Outputs and Logs

- HTML reports: `output/html/`
- PDF reports: `output/pdf/`
- Logs: `logs/server.log` and `.sandbox/server.log`

## Web Pages

- `/` Report generator + upload
- `/customize` Overrides list
- `/customize/edit` Override editor
- `/customize/view` Override view
- `/providers` Provider list
- `/providers/edit` Provider editor
- `/report-types` Report type list
- `/report-types/edit` Report type editor
- `/report/costs` Estimate report costs
