# Autonomous Coding Agent (Terminal)

A terminal-based autonomous coding agent that can **plan actions** and then **execute them locally** (create files, run commands, do web search) using a simple JSON-plan executor.

This repo currently uses `simple_agent.py` as the primary entrypoint.

## What it does

- **Action executor**
  - The model can return a JSON plan describing actions.
  - The agent executes the actions and prints results.

- **File creation**
  - Creates folders/files on disk (e.g. project scaffolds).

- **Command execution**
  - Runs shell commands and returns stdout/stderr.

- **Web search (Tavily)**
  - Only used when explicitly requested (via `/search ...`) or when the planner decides it’s necessary for a *news/current events* request.

- **Contextual memory**
  - Stores lightweight memory + recent conversation in `agent_memory.json`.

- **Model switching**
  - Switch between installed Ollama models at runtime using `/model`.

## Setup

1. Install dependencies

```bash
pip install -r requirements.txt
```

2. Add `.env`

```env
TAVILY_API_KEY=YOUR_KEY
# Optional default model:
# OLLAMA_MODEL=deepseek-v3.1:671b-cloud
```

3. Make sure Ollama is running and you have models

```bash
ollama list
```

## Run

```bash
python simple_agent.py
```

## Commands

- `help`
- `exit`
- `/search <query>`
  - Forces Tavily search.
- `/models`
  - Lists available models configured in the agent.
- `/model <name>`
  - Switches the active model (persisted in `agent_memory.json`).
- `/model show`
  - Prints the current model.
- `/planner <name>`
  - Switches the planner model (used for faster routing to actions).
- `/planner show`
  - Prints the current planner model.
- `/remember <text>`
  - Save a long-term memory into the local RAG store (ChromaDB).
- `/memories <query>`
  - Search previously saved memories.
- `/serve [folder] [port]`
  - Serve a folder locally using `python -m http.server` (Windows-safe via the current Python executable).
- `/serve stop`
  - Stop the currently running server started by `/serve`.
- `/pwd`
  - Print the current working directory.
- `/files [folder]`
  - List files in a folder.
- `/open <file>`
  - Print a file to the terminal (truncated for safety).
- `/run <command>`
  - Run a command. If it is not in the safe allowlist, it will require confirmation.
- `/confirm`
  - Confirm and execute the pending command.
- `/cancel`
  - Cancel the pending command.

## Supported models (configured)

These are the models listed in `simple_agent.py` for quick switching:

- `gpt-oss:120b-cloud`
- `deepseek-v3.1:671b-cloud`
- `qwen3-coder:480b-cloud`

You can still set any other Ollama model name with `/model <name>` if it exists locally.

## Latency optimization (planner vs main model)

The agent uses **two LLM instances**:

- **Planner model** (fast): decides whether to reply normally or emit a JSON plan.
- **Main model** (strong): generates normal answers (and can be used by the planner if you choose).

By default, the planner model is `qwen3-coder:480b-cloud` (configurable via `/planner`).

## RAG memory (ChromaDB + Ollama embeddings)

The agent stores and retrieves long-term memories using:

- **ChromaDB**: persistent vector store in `backend/.chroma`
- **Ollama embeddings**: `nomic-embed-text:latest` via `http://localhost:11434/api/embeddings`

Use `/remember` to explicitly save a memory and `/memories` to query it.

## How the executor works

The agent asks the model for either:

- a **normal response** (plain text), or
- a **JSON plan** like:

```json
{
  "type": "plan",
  "actions": [
    {"tool": "create_file", "path": "restaurant-site/index.html", "content": "..."},
    {"tool": "create_file", "path": "restaurant-site/style.css", "content": "..."},
    {"tool": "create_file", "path": "restaurant-site/script.js", "content": "..."},
    {"tool": "reply", "text": "Created restaurant-site/*"}
  ]
}
```

Then `simple_agent.py` executes each action and prints `✅ Successfully created: ...` etc.

## Notes

- `agent_memory.json` is created automatically (needed for contextual memory and model persistence).
- Tavily search requires a valid `TAVILY_API_KEY`.

