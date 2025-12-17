# Yogz — Local AI Terminal Agent (Windows)

Yogz is a Windows-first AI terminal agent designed to operate like a production developer tool:

- A single Go binary (`agent.exe`) is the primary entrypoint.
- A local Python agent service is launched automatically by a Go **supervisor** (no manual `python ...` server startup).
- The agent can answer questions and (when enabled) execute real filesystem and shell commands.

This repository currently contains:

- **Go agent**: `backend/go_agent` (CLI + API mode)
- **Python agent service**: `backend/python_agent_server.py` (FastAPI wrapper around `backend/simple_agent.py`)
- **Frontend**: `backend/frontend` (static)

---

## Quick start (Windows)

### Prerequisites (current dev setup)

- **Go** (1.21+ recommended)
- **Python** (3.10+)
- Optional: **Ollama** running on `http://localhost:11434`

### 1) Install Python deps

```powershell
pip install -r backend\requirements.txt
```

### 2) Build the Go agent

```powershell
cd backend\go_agent
go build -o agent.exe .\cmd\agent
```

### 3) Run CLI mode

```powershell
$env:AGENT_ENABLE_FS="true"   # optional
.\agent.exe --mode cli
```

The Go agent will auto-start the Python service via the supervisor and connect to it over localhost.

---

## Modes

- **CLI**: `agent.exe --mode cli`
- **API**: `agent.exe --mode api --host 127.0.0.1 --port 8080`

API endpoints live under `/v1/*` (see `docs/ARCHITECTURE.md`).

---

## Configuration

Environment variables are supported for development. In production, the supervisor will own runtime configuration.

Common vars:

- `AGENT_ENABLE_FS=true` — enable filesystem tools
- `AGENT_ALLOW_DIRS=.` — allowlisted dirs
- `PYTOOLS_URL=http://127.0.0.1:8787` — python service URL (dev override)
- `PYTHON_AGENT_ENTRY=<path-to-python_agent_server.py>` — python entry script (dev override)
- `OLLAMA_HOST=http://localhost:11434`
- `OLLAMA_MODEL=deepseek-v3.1:671b-cloud`

---

## Download / Releases

This repo is prepared for a GitHub Releases-based download flow.

- **How users download**: GitHub → Releases → download `Yogz-win-x64-vX.Y.Z.zip`
- **How you publish**: see `docs/RELEASING.md`

---

## Security notes

- The Python service binds to `127.0.0.1` only.
- Command execution is powerful. Treat `AGENT_ENABLE_FS` (and any future "run" tools) as privileged.
- For production, you should code-sign Windows binaries.

---

## Docs

- `docs/ARCHITECTURE.md`
- `docs/RELEASING.md`
