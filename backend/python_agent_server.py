#!/usr/bin/env python3
"""
FastAPI wrapper for simple_agent.py so the Go server can call it via HTTP.
Only exposes /ask (POST) and /status (GET). No auth here—Go handles it.
"""

"""This is an ** IMPORTANT FILE ** Do not delete this file for the program to run"""

import os
import json
import asyncio
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

from simple_agent import SimpleAgent

app = FastAPI(title="Python Agent Service", version="1.0")

# Global agent instance (reuse across requests)
_agent: SimpleAgent | None = None

@app.get("/")
def root() -> Dict[str, str]:
    return {"service": "python_agent_server", "status": "ok"}

@app.get("/favicon.ico")
def favicon() -> int:
    # Return 204 No Content to avoid 404 spam
    return 204

class AskRequest(BaseModel):
    question: str
    user_id: str = "default"
    model: str | None = None

class AskResponse(BaseModel):
    answer: str
    ts: str

def get_agent() -> SimpleAgent:
    global _agent
    if _agent is None:
        _agent = SimpleAgent()
    return _agent

@app.get("/status")
def status() -> Dict[str, Any]:
    ag = get_agent()
    return {
        "status": "ok",
        "model": ag.model_name,
        "planner_model": ag.planner_model_name,
        "rag_enabled": ag.rag_enabled,
        "tavily_configured": bool(ag.tavily_api_key),
        "chroma_available": ag._chroma_collection is not None,
    }

@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest) -> AskResponse:
    ag = get_agent()
    # Override model if provided
    if req.model:
        ag.set_model(req.model)
    try:
        # SimpleAgent.process_request is synchronous; run in threadpool to avoid blocking FastAPI
        loop = asyncio.get_event_loop()
        answer = await loop.run_in_executor(None, ag.process_request, req.question)
        return AskResponse(answer=answer, ts=ag.memory.get("last_request_ts", ""))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    # Default bind to 127.0.0.1:8787 (matching Go's PYTOOLS_URL)
    host = os.getenv("PYTHON_AGENT_HOST", "127.0.0.1")
    port = int(os.getenv("PYTHON_AGENT_PORT", "8787"))
    uvicorn.run(app, host=host, port=port, log_level="info")
