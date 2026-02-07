---
name: start-server
description: Start the local Flask CSV report server in a self-contained sandbox. Use when you need to launch the HTTPS server from this repo using config.ini/.env, install dependencies into the sandbox venv, and write PID/log files for later stop.
---

# Start Server

## Overview

Start the Flask report server in a local sandbox venv and record its PID/log so it can be stopped later.

## Quick Start

1. Ensure `config.ini` and `.env` have the desired values.
2. Run the start script:

```powershell
powershell -ExecutionPolicy Bypass -File skills\start-server\scripts\start_server.ps1
```

3. Check the log at `.sandbox\server.log` if the server does not start.

## Resources

- `scripts/start_server.ps1`: Creates `.sandbox\venv`, installs dependencies, starts the server, writes `.sandbox\server.pid` and `.sandbox\server.log`.
