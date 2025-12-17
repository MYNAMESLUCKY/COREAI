import os
import re
import json
import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aiohttp import web

from langchain.tools import BaseTool
from pydantic import BaseModel, Field


def _split_allow_dirs(v: str) -> List[str]:
    parts = re.split(r"[;,\s]+", v.strip()) if v else []
    out: List[str] = []
    for p in parts:
        p = p.strip()
        if p:
            out.append(p)
    return out


def _env_bool(key: str, default: bool) -> bool:
    v = os.getenv(key, "").strip().lower()
    if not v:
        return default
    return v in {"1", "true", "yes", "on"}


def _has_path_prefix(p: Path, base: Path) -> bool:
    try:
        p = p.resolve()
        base = base.resolve()
    except Exception:
        return False
    if p == base:
        return True
    try:
        p.relative_to(base)
        return True
    except Exception:
        return False


def _is_allowed(path: str, allow_dirs: List[str]) -> Tuple[Optional[Path], bool]:
    if not path:
        return None, False
    try:
        abs_path = Path(path).expanduser().resolve()
    except Exception:
        return None, False

    for d in allow_dirs:
        try:
            base = Path(d).expanduser().resolve()
        except Exception:
            continue
        if _has_path_prefix(abs_path, base):
            return abs_path, True
    return abs_path, False


@dataclass
class ServerConfig:
    host: str
    port: int
    enable_fs: bool
    allow_dirs: List[str]
    max_read_bytes: int
    max_grep_bytes: int
    max_grep_matches: int


def load_config() -> ServerConfig:
    host = os.getenv("PYTOOLS_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = int(os.getenv("PYTOOLS_PORT", "8787"))
    enable_fs = _env_bool("PYTOOLS_ENABLE_FS", False)
    allow_dirs = _split_allow_dirs(os.getenv("PYTOOLS_ALLOW_DIRS", ""))
    if not allow_dirs:
        allow_dirs = ["."]

    max_read_bytes = int(os.getenv("PYTOOLS_MAX_READ_BYTES", str(256 * 1024)))
    max_grep_bytes = int(os.getenv("PYTOOLS_MAX_GREP_FILE_BYTES", str(512 * 1024)))
    max_grep_matches = int(os.getenv("PYTOOLS_MAX_GREP_MATCHES", "200"))

    return ServerConfig(
        host=host,
        port=port,
        enable_fs=enable_fs,
        allow_dirs=allow_dirs,
        max_read_bytes=max_read_bytes,
        max_grep_bytes=max_grep_bytes,
        max_grep_matches=max_grep_matches,
    )


async def handle_status(request: web.Request) -> web.Response:
    cfg: ServerConfig = request.app["cfg"]
    return web.json_response(
        {
            "status": "ok",
            "enable_fs": cfg.enable_fs,
            "allow_dirs": cfg.allow_dirs,
            "max_read_bytes": cfg.max_read_bytes,
            "max_grep_file_bytes": cfg.max_grep_bytes,
            "max_grep_matches": cfg.max_grep_matches,
        }
    )


async def handle_tools_list(request: web.Request) -> web.Response:
    tools: Dict[str, BaseTool] = request.app["tools"]
    return web.json_response({"tools": sorted(list(tools.keys()))})


class LSToolArgs(BaseModel):
    path: str = Field(default=".")


class ReadFileToolArgs(BaseModel):
    path: str = Field(...)


class GrepToolArgs(BaseModel):
    root: str = Field(default=".")
    pattern: str = Field(...)
    includes: Optional[List[str]] = Field(default=None)


class LSTool(BaseTool):
    name: str = "ls"
    description: str = "List directory contents within an allowlisted root."
    args_schema = LSToolArgs

    cfg: ServerConfig

    def _run(self, path: str = ".") -> Dict[str, Any]:
        if not self.cfg.enable_fs:
            return {"error": {"kind": "fs_disabled", "message": "filesystem disabled"}}

        abs_path, ok = _is_allowed(path or ".", self.cfg.allow_dirs)
        if not abs_path or not ok:
            return {"error": {"kind": "path_not_allowed", "message": "path not allowed"}}

        if not abs_path.exists() or not abs_path.is_dir():
            return {"error": {"kind": "not_a_directory", "message": "not a directory"}}

        items: List[Dict[str, Any]] = []
        for child in sorted(abs_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            it: Dict[str, Any] = {"name": child.name, "type": "dir" if child.is_dir() else "file"}
            if child.is_file():
                try:
                    it["size_bytes"] = child.stat().st_size
                except Exception:
                    it["size_bytes"] = None
            items.append(it)

        return {"path": str(abs_path), "items": items}

    async def _arun(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        return await asyncio.to_thread(self._run, *args, **kwargs)


class ReadFileTool(BaseTool):
    name: str = "read_file"
    description: str = "Read a file within an allowlisted root (size limited)."
    args_schema = ReadFileToolArgs

    cfg: ServerConfig

    def _run(self, path: str) -> Dict[str, Any]:
        if not self.cfg.enable_fs:
            return {"error": {"kind": "fs_disabled", "message": "filesystem disabled"}}

        abs_path, ok = _is_allowed(path, self.cfg.allow_dirs)
        if not abs_path or not ok:
            return {"error": {"kind": "path_not_allowed", "message": "path not allowed"}}

        if not abs_path.exists() or not abs_path.is_file():
            return {"error": {"kind": "not_a_file", "message": "not a file"}}

        try:
            st = abs_path.stat()
            if st.st_size > self.cfg.max_read_bytes:
                return {"error": {"kind": "file_too_large", "message": "file too large"}}
        except Exception:
            pass

        try:
            content = abs_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return {"error": {"kind": "read_failed", "message": str(e)}}

        return {"path": str(abs_path), "content": content}

    async def _arun(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        return await asyncio.to_thread(self._run, *args, **kwargs)


class GrepTool(BaseTool):
    name: str = "grep"
    description: str = "Search for a regex pattern under an allowlisted directory (limits file size and match count)."
    args_schema = GrepToolArgs

    cfg: ServerConfig

    def _run(self, root: str = ".", pattern: str = "", includes: Optional[List[str]] = None) -> Dict[str, Any]:
        if not self.cfg.enable_fs:
            return {"error": {"kind": "fs_disabled", "message": "filesystem disabled"}}

        abs_root, ok = _is_allowed(root or ".", self.cfg.allow_dirs)
        if not abs_root or not ok:
            return {"error": {"kind": "path_not_allowed", "message": "path not allowed"}}

        if not abs_root.exists() or not abs_root.is_dir():
            return {"error": {"kind": "not_a_directory", "message": "not a directory"}}

        if not pattern:
            return {"error": {"kind": "missing_pattern", "message": "missing pattern"}}

        try:
            rx = re.compile(pattern, re.IGNORECASE)
        except Exception as e:
            return {"error": {"kind": "invalid_pattern", "message": str(e)}}

        inc = set()
        if includes:
            for x in includes:
                x = (x or "").strip().lower()
                if x:
                    inc.add(x if x.startswith(".") else f".{x}")

        matches: List[Dict[str, Any]] = []

        for p in abs_root.rglob("*"):
            if len(matches) >= self.cfg.max_grep_matches:
                break
            if not p.is_file():
                continue
            if inc and p.suffix.lower() not in inc:
                continue
            try:
                st = p.stat()
                if st.st_size > self.cfg.max_grep_bytes:
                    continue
            except Exception:
                continue

            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            for i, line in enumerate(text.splitlines(), start=1):
                if rx.search(line):
                    matches.append({"file": str(p), "line": i, "text": line.strip()})
                    if len(matches) >= self.cfg.max_grep_matches:
                        break

        return {"root": str(abs_root), "pattern": pattern, "matches": matches}

    async def _arun(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        return await asyncio.to_thread(self._run, *args, **kwargs)


def build_tools(cfg: ServerConfig) -> Dict[str, BaseTool]:
    tools: Dict[str, BaseTool] = {}
    tools["ls"] = LSTool(cfg=cfg)
    tools["read_file"] = ReadFileTool(cfg=cfg)
    tools["grep"] = GrepTool(cfg=cfg)
    return tools


async def handle_tools_run(request: web.Request) -> web.Response:
    cfg: ServerConfig = request.app["cfg"]
    tools: Dict[str, BaseTool] = request.app["tools"]
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": {"kind": "invalid_json", "message": "invalid json"}}, status=400)

    name = (body.get("name") or "").strip()
    args = body.get("args")

    if not isinstance(args, dict):
        args = {}

    tool = tools.get(name)
    if tool is None:
        return web.json_response({"error": {"kind": "unknown_tool", "message": "unknown tool"}}, status=400)

    try:
        out = await tool.ainvoke(args)
    except Exception as e:
        return web.json_response({"error": {"kind": "tool_failed", "message": str(e)}}, status=400)

    status = 200
    if isinstance(out, dict) and "error" in out:
        status = 400
    return web.json_response(out, status=status)


def create_app(cfg: ServerConfig) -> web.Application:
    app = web.Application()
    app["cfg"] = cfg
    app["tools"] = build_tools(cfg)
    app.add_routes(
        [
            web.get("/status", handle_status),
            web.get("/tools/list", handle_tools_list),
            web.post("/tools/run", handle_tools_run),
        ]
    )
    return app


async def main() -> None:
    cfg = load_config()
    app = create_app(cfg)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, cfg.host, cfg.port)
    await site.start()

    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
