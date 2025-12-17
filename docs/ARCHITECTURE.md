# Architecture (Windows)

This document describes the current Yogz architecture and the intended production distribution model.

## High-level design

Yogz is built as a **hybrid local agent**:

- **Go process**: primary entrypoint (`agent.exe`)
  - provides CLI and HTTP API modes
  - owns configuration, limits/auth, and tool registry
  - runs a **supervisor** that ensures the Python service is running

- **Python process**: local agent service (FastAPI)
  - exposes `POST /ask` and `GET /status`
  - wraps `simple_agent.py` which contains the primary agent/planner/executor logic

Communication is local-only over `127.0.0.1`.

## Processes

### Go agent (`backend/go_agent`)

Entry point:

- `backend/go_agent/cmd/agent/main.go`

Modes:

- `--mode cli`
  - reads user input
  - routes explicit commands (`/ls`, `/run`, `/py`)
  - routes natural language to Python service
  - executes JSON plans returned by Python (shell commands, etc.)

- `--mode api`
  - HTTP server exposing `/v1/*`
  - forwards `/v1/ask` to Python
  - executes JSON plans returned by Python (server-side)

### Python agent service (`backend/python_agent_server.py`)

Endpoints:

- `GET /status`
  - returns health and model info
- `POST /ask`
  - body: `{ "question": string, "user_id": string, "model": string|null }`
  - `model` overrides the active model for the request (via `SimpleAgent.set_model()`)

## Supervisor

Location:

- `backend/go_agent/internal/supervisor/supervisor.go`

Responsibilities:

- pick a free localhost port
- start the Python server with:
  - `PYTHON_AGENT_HOST=127.0.0.1`
  - `PYTHON_AGENT_PORT=<free_port>`
- poll `GET /status` until the service is ready
- write logs to `%APPDATA%\Yogz\logs\python_agent.log`

Production target:

- replace `python python_agent_server.py` with a packaged exe: `python_agent_server.exe`
- add restart/backoff so the service is resilient

## Tooling

Go tools registry:

- `/help`, `/status`, `/model`, `/ls`, `/run`, `/py`, `/exit`

Key behaviors:

- JSON plan execution: the agent can return a JSON object that describes an action to run. The Go side executes it.
- Windows normalization: heredoc and `python3` are normalized to Windows-compatible commands.

## Security model

- Local-only binding for Python server (`127.0.0.1`)
- API mode supports:
  - API key auth middleware
  - rate limiting middleware
- Filesystem access is gated behind `AGENT_ENABLE_FS` and allowlisted directories.

## Known production hardening items

- Add a shared local token for Go↔Python to prevent other local processes calling the Python service.
- Add structured logging and log rotation.
- Add a release pipeline (signed binaries + checksums).
