# Installation (Linux)

## Prerequisites

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

## Setup

```bash
git clone https://github.com/uzigolan/rv-ai-skills.git
cd rv-ai-skills
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

`config.ini` is ignored in git. Create it locally:

```bash
cp config.ini.example config.ini
```

If there is no example file yet, copy from a working machine and remove any secrets.

### HTTPS

If you want HTTPS, place certs in `https-certs/` and set:

```
use_https = true
cert_path = https-certs/tls.cert.pem
key_path = https-certs/tls.key.pem
```

Or disable HTTPS:

```
use_https = false
```

## API Keys (Encrypted in DB)

Keys are stored encrypted in the database, not in `config.ini` or `.env`.

Set a key:

```bash
python scripts/set_provider_key.py --provider openai --api-key YOUR_KEY
```

Supported providers: `openai`, `grok`, `claude`, `gemini`.

### If you cloned from Git (Linux/macOS)

The DB may contain keys encrypted on another machine. If startup fails or keys don’t work:

```bash
rm -f db/provider_keys.key

python - <<'PY'
import sqlite3
conn = sqlite3.connect('db/report_overrides.db')
conn.execute("UPDATE providers SET api_key_enc = NULL")
conn.commit()
conn.close()
PY
```

Then set your local key again:

```bash
python scripts/set_provider_key.py --provider openai --api-key YOUR_KEY
```

## Run

```bash
python app/server.py --config config.ini
```

Open in browser:

- HTTP: `http://localhost:444/`
- HTTPS: `https://localhost:444/`

## Useful Pages

- `/` Report generator
- `/customize` Overrides
- `/providers` Providers
- `/report-types` Report types
- `/report/costs` Cost estimate
