---
name: stop-server
description: Stop the local Flask CSV report server started by the sandbox scripts. Use when you need to terminate the running server using the stored PID in .sandbox/server.pid.
---

# Stop Server

## Overview

Stop the running Flask report server using the PID file created by the start script.

## Quick Start

```powershell
powershell -ExecutionPolicy Bypass -File skills\stop-server\scripts\stop_server.ps1
```

## Resources

- `scripts/stop_server.ps1`: Reads `.sandbox\server.pid`, stops the process, and removes the PID file.
