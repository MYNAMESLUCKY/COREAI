# Go Terminal AI Agent

Windows-first terminal AI agent + REST API.

## Features

- CLI mode and API mode (same core)
- Token limiting (by character clamp)
- Rate limiting (per API key / per IP) using in-memory token bucket
- API key auth (Bearer token)
- RAG-like memory using Ollama embeddings + local vector store file (`agent_memory_vectors.json`)
- Docker example for DevOps

## Requirements

- Go 1.22+
- Ollama running locally
- Models present:
  - `deepseek-v3.1:671b-cloud` (or any)
  - `nomic-embed-text:latest`

## Build (Windows)

From `backend/go_agent`:

```powershell
go build -o agent.exe .\cmd\agent
```

## Run CLI

```powershell
.\agent.exe --mode cli
```

## Run API

```powershell
.\agent.exe --mode api --host 127.0.0.1 --port 8080
```

### Endpoints

- `GET /v1/status`
- `POST /v1/ask`  body: `{ "question": "..." }`

### Auth

If you set `AGENT_API_KEYS`, requests must include:

`Authorization: Bearer <key>`

## Environment Variables

- `OLLAMA_HOST` (default `http://localhost:11434`)
- `OLLAMA_MODEL` (default `deepseek-v3.1:671b-cloud`)
- `OLLAMA_EMBED_MODEL` (default `nomic-embed-text:latest`)
- `AGENT_RATE_LIMIT_PER_MIN` (default `60`)
- `AGENT_MAX_INPUT_CHARS` (default `12000`)
- `AGENT_MAX_OUTPUT_CHARS` (default `12000`)
- `AGENT_API_KEYS` (comma-separated)

## Docker

From `backend/go_agent`:

```bash
docker build -t go-agent .
docker run --rm -p 8080:8080 -e OLLAMA_HOST=http://host.docker.internal:11434 go-agent
```

## Security note ("hide code")

- If you ship source code, it can be inspected.
- To *reduce* exposure, ship a compiled binary (`agent.exe`) or host the API server yourself.
- Docker images still contain the binary, but not your Go source.
