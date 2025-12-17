#!/usr/bin/env python3
"""
Simple Autonomous Coding Agent
Clean terminal interface with proper input handling
"""

import os
import sys
import subprocess
import requests
import json
import uuid
from datetime import datetime
from pathlib import Path
from langchain_ollama import ChatOllama
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class SimpleAgent:
    def __init__(self):
        """Initialize simple coding agent."""

        self.available_models = [
            "gpt-oss:120b-cloud",
            "deepseek-v3.1:671b-cloud",
            "qwen3-coder:480b-cloud",
        ]
        
        # Get Tavily API key
        self.tavily_api_key = os.getenv("TAVILY_API_KEY")
        
        # Contextual memory
        self.memory_file = "agent_memory.json"
        self.memory = self.load_memory()
        self.chat_history = self.memory.get("chat_history", [])

        self.max_history = int(self.memory.get("max_history", 20))

        self.model_name = self.memory.get("model_name") or os.getenv("OLLAMA_MODEL") or "gpt-oss:120b-cloud"
        self.planner_model_name = self.memory.get("planner_model_name") or os.getenv("OLLAMA_PLANNER_MODEL") or "qwen3-coder:480b-cloud"
        self._init_llm()

        self._server_process = None
        self._pending_command = None
        self._pending_command_reason = None

        self.rag_enabled = bool(self.memory.get("rag_enabled", True))
        self.rag_embed_model = self.memory.get("rag_embed_model") or os.getenv("OLLAMA_EMBED_MODEL") or "nomic-embed-text:latest"
        self.rag_k = int(self.memory.get("rag_k", 4))

        self._chroma_client = None
        self._chroma_collection = None
        try:
            import chromadb  # type: ignore

            self._chroma_client = chromadb.PersistentClient(path=self.memory.get("rag_path", ".chroma"))
            self._chroma_collection = self._chroma_client.get_or_create_collection(name="chat_memory")
        except Exception:
            self._chroma_client = None
            self._chroma_collection = None

        self.allowed_command_prefixes = [
            "dir",
            "type",
            "python -m http.server",
            "python -c",
            "py -m http.server",
            "pip show",
            "pip list",
            "ollama list",
        ]
        
        # System prompt
        self.system_prompt = """You are an advanced autonomous coding agent with access to powerful tools for development, research, and problem-solving.

CAPABILITIES:
- Web search and documentation lookup via Tavily
- Code analysis and pattern searching
- File operations and directory management
- Terminal command execution
- Real-time information retrieval
- Contextual memory for remembering user preferences and past actions

GUIDELINES:
1. Always analyze the user's request carefully before taking action
2. Use web search when you need current information or documentation
3. Use code analysis tools to understand existing codebases
4. Execute terminal commands only when necessary and safe
5. Provide clear, actionable feedback about your actions
6. Be efficient and avoid redundant operations
7. Ask for clarification when requests are ambiguous
8. Remember user preferences and project context
9. When asked to create files or projects, ACTUALLY CREATE THEM using file creation tools

OUTPUT FORMAT REQUIREMENTS:
- When you need the program to take actions, you MUST respond with a single JSON object (and nothing else) matching the schema described in the user's message.
- If no actions are needed, you may respond with normal text.

You are thorough, efficient, and focused on delivering high-quality solutions."""

        self.planner_prompt = """You are a planner for a local coding agent.

Return either:
1) A normal assistant response (plain text) if no actions are needed.
OR
2) A SINGLE JSON object (and nothing else) with this schema:

{
  "type": "plan",
  "actions": [
    {
      "tool": "create_file",
      "path": "relative/or/absolute/path",
      "content": "file content as a string"
    },
    {
      "tool": "run_command",
      "command": "command to execute"
    },
    {
      "tool": "web_search",
      "query": "search query"
    },
    {
      "tool": "reply",
      "text": "final user-facing message"
    }
  ]
}

Rules:
- Use web_search ONLY if user explicitly asks for news/current events/web search.
- If user asks to create/build files, you MUST output the JSON plan, not plain text.
- Start your response with { and end with } for JSON plans.
"""

    def _init_llm(self):
        self.llm = ChatOllama(
            model=self.model_name,
            temperature=float(self.memory.get("temperature", 0.1)),
        )
        self.planner_llm = ChatOllama(
            model=self.planner_model_name,
            temperature=float(self.memory.get("planner_temperature", 0.0)),
        )

    def set_model(self, model_name: str) -> str:
        model_name = (model_name or "").strip()
        if not model_name:
            return "❌ Usage: /model <model-name>"

        self.model_name = model_name
        self.memory["model_name"] = model_name
        self.save_memory()
        self._init_llm()
        return f"✅ Model set to: {model_name}"

    def set_planner_model(self, model_name: str) -> str:
        model_name = (model_name or "").strip()
        if not model_name:
            return "❌ Usage: /planner <model-name>"

        self.planner_model_name = model_name
        self.memory["planner_model_name"] = model_name
        self.save_memory()
        self._init_llm()
        return f"✅ Planner model set to: {model_name}"
    
    def load_memory(self):
        """Load contextual memory from file."""
        try:
            if os.path.exists(self.memory_file):
                with open(self.memory_file, 'r') as f:
                    return json.load(f)
            return {}
        except:
            return {}
    
    def save_memory(self):
        """Save contextual memory to file."""
        try:
            self.memory["chat_history"] = self.chat_history[-30:]
            with open(self.memory_file, 'w') as f:
                json.dump(self.memory, f, indent=2)
        except:
            pass
    
    def remember(self, key: str, value: str):
        """Store information in memory."""
        self.memory[key] = value
        self.save_memory()

    def _append_history(self, role: str, content: str):
        self.chat_history.append({"role": role, "content": content})
        self.chat_history = self.chat_history[-self.max_history:]
        self.save_memory()
    
    def web_search(self, query: str) -> str:
        """Perform web search using Tavily API."""
        if not self.tavily_api_key:
            return "❌ Tavily API key not configured. Web search is not available."
        
        try:
            url = "https://api.tavily.com/search"
            # Tavily expects api_key in JSON for most setups.
            headers = {"Content-Type": "application/json"}
            data = {
                "api_key": self.tavily_api_key,
                "query": query,
                "max_results": 5,
                "search_depth": "basic"
            }
            
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            
            results = response.json()
            
            # Format results
            formatted = f"🔍 Web Search Results for: '{query}'\n\n"
            
            if results.get("answer"):
                formatted += f"💡 Quick Answer: {results['answer']}\n\n"
            
            for i, result in enumerate(results.get("results", []), 1):
                formatted += f"{i}. **{result['title']}**\n"
                formatted += f"   {result['url']}\n"
                formatted += f"   {result.get('content', 'No description')[:200]}...\n\n"
            
            return formatted
            
        except Exception as e:
            return f"❌ Web search failed: {str(e)}"
    
    def create_file(self, filepath: str, content: str) -> str:
        """Create a file with content."""
        try:
            parent = os.path.dirname(filepath)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return f"✅ Successfully created: {filepath}"
        except Exception as e:
            return f"❌ Failed to create {filepath}: {str(e)}"
    
    def run_command(self, command: str) -> str:
        """Execute a terminal command."""
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
            output = f"📋 Command: {command}\n"
            output += f"Exit code: {result.returncode}\n"
            if result.stdout:
                output += f"Output:\n{result.stdout}\n"
            if result.stderr:
                output += f"Error:\n{result.stderr}\n"
            return output
        except subprocess.TimeoutExpired:
            return f"❌ Command timed out: {command}"
        except Exception as e:
            return f"❌ Failed to run command: {str(e)}"

    def _is_command_allowed(self, command: str) -> bool:
        cmd = (command or "").strip().lower()
        if not cmd:
            return False
        for p in self.allowed_command_prefixes:
            if cmd.startswith(p.lower()):
                return True
        return False

    def _queue_command(self, command: str, reason: str) -> str:
        self._pending_command = command
        self._pending_command_reason = reason
        return (
            "⚠️ Command requires confirmation.\n"
            f"Reason: {reason}\n"
            f"Pending: {command}\n\n"
            "Use /confirm to run it or /cancel to discard."
        )

    def _confirm_command(self) -> str:
        if not self._pending_command:
            return "ℹ️ No pending command."
        cmd = self._pending_command
        self._pending_command = None
        self._pending_command_reason = None
        return self.run_command(cmd)

    def _cancel_command(self) -> str:
        if not self._pending_command:
            return "ℹ️ No pending command."
        self._pending_command = None
        self._pending_command_reason = None
        return "✅ Pending command canceled."

    def _list_files(self, folder: str | None = None) -> str:
        folder = (folder or ".").strip().strip('"').strip("'")
        p = Path(folder)
        if not p.exists() or not p.is_dir():
            return f"❌ Folder not found: {folder}"
        items = []
        for child in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            kind = "dir" if child.is_dir() else "file"
            items.append(f"- [{kind}] {child.name}")
        if not items:
            return f"(empty) {p.resolve()}"
        return f"{p.resolve()}\n" + "\n".join(items)

    def _read_file_text(self, path: str) -> str:
        path = (path or "").strip().strip('"').strip("'")
        if not path:
            return "❌ Usage: /open <file-path>"
        p = Path(path)
        if not p.exists() or not p.is_file():
            return f"❌ File not found: {path}"
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            if len(text) > 8000:
                text = text[:8000] + "\n\n... (truncated)"
            return text
        except Exception as e:
            return f"❌ Failed to read file: {str(e)}"

    def _ollama_embed(self, text: str) -> list:
        text = (text or "").strip()
        if not text:
            return []
        url = os.getenv("OLLAMA_HOST")
        if url:
            url = url.rstrip("/")
        else:
            url = "http://localhost:11434"
        try:
            resp = requests.post(
                f"{url}/api/embeddings",
                json={"model": self.rag_embed_model, "prompt": text},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("embedding") or []
        except Exception:
            return []

    def rag_add(self, text: str, meta: dict | None = None) -> str:
        if not self.rag_enabled:
            return "ℹ️ RAG memory is disabled."
        if not self._chroma_collection:
            return "❌ ChromaDB is not available. Install dependencies and restart."
        text = (text or "").strip()
        if not text:
            return "❌ Usage: /remember <text>"

        emb = self._ollama_embed(text)
        if not emb:
            return "❌ Could not create embeddings (is Ollama running and is the embed model available?)."

        doc_id = str(uuid.uuid4())
        metadata = {"ts": datetime.utcnow().isoformat()}
        if meta:
            metadata.update(meta)

        try:
            self._chroma_collection.add(
                ids=[doc_id],
                documents=[text],
                embeddings=[emb],
                metadatas=[metadata],
            )
            return "✅ Saved to RAG memory."
        except Exception as e:
            return f"❌ Failed to save to RAG memory: {str(e)}"

    def rag_query(self, query: str, k: int | None = None) -> list[str]:
        if not self.rag_enabled:
            return []
        if not self._chroma_collection:
            return []
        query = (query or "").strip()
        if not query:
            return []

        emb = self._ollama_embed(query)
        if not emb:
            return []

        try:
            res = self._chroma_collection.query(
                query_embeddings=[emb],
                n_results=int(k or self.rag_k),
            )
            docs = (res.get("documents") or [[]])[0]
            return [d for d in docs if d]
        except Exception:
            return []

    def _serve_start(self, folder: str, port: int) -> str:
        folder = (folder or "").strip().strip('"').strip("'")
        if not folder:
            return "❌ Usage: /serve <folder> [port]"
        if not os.path.isdir(folder):
            return f"❌ Folder not found: {folder}"

        if self._server_process and self._server_process.poll() is None:
            return "❌ A server is already running. Use /serve stop first."

        py = sys.executable
        try:
            self._server_process = subprocess.Popen(
                [py, "-m", "http.server", str(port)],
                cwd=folder,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except Exception as e:
            self._server_process = None
            return f"❌ Failed to start server: {str(e)}"

        self.memory["last_served_folder"] = folder
        self.memory["last_served_port"] = port
        self.save_memory()

        return (
            f"✅ Serving '{folder}' on http://localhost:{port}\n"
            f"Stop with: /serve stop"
        )

    def _serve_stop(self) -> str:
        if not self._server_process or self._server_process.poll() is not None:
            self._server_process = None
            return "ℹ️ No server is currently running."

        try:
            self._server_process.terminate()
            self._server_process.wait(timeout=5)
        except Exception:
            try:
                self._server_process.kill()
            except Exception:
                pass
        finally:
            self._server_process = None

        return "✅ Server stopped."

    def _plan(self, user_input: str) -> str:
        """Ask the model for either a plan JSON or a plain text response."""
        history_text = "\n".join(
            [f"{m['role'].upper()}: {m['content']}" for m in self.chat_history[-6:]]
        )
        state = {
            "current_model": self.model_name,
            "planner_model": self.planner_model_name,
            "last_served_folder": self.memory.get("last_served_folder"),
            "last_served_port": self.memory.get("last_served_port"),
            "rag_enabled": self.rag_enabled,
        }

        retrieved = self.rag_query(user_input, k=3)
        if retrieved:
            state["retrieved_memories"] = retrieved
        messages = [
            ("system", self.planner_prompt),
            ("system", f"Agent state (JSON): {json.dumps(state)}"),
            ("system", f"Recent chat history (for context):\n{history_text}"),
            ("human", user_input),
        ]
        resp = self.planner_llm.invoke(messages)
        return resp.content.strip()

    def _execute_plan(self, plan: dict) -> str:
        outputs = []
        for action in plan.get("actions", []):
            tool = action.get("tool")
            if tool == "create_file":
                path = action.get("path")
                content = action.get("content", "")
                if not path:
                    outputs.append("❌ create_file missing 'path'")
                    continue
                outputs.append(self.create_file(path, content))
            elif tool == "run_command":
                cmd = action.get("command")
                if not cmd:
                    outputs.append("❌ run_command missing 'command'")
                    continue
                outputs.append(self.run_command(cmd))
            elif tool == "web_search":
                query = action.get("query")
                if not query:
                    outputs.append("❌ web_search missing 'query'")
                    continue
                outputs.append(self.web_search(query))
            elif tool == "reply":
                text = action.get("text", "")
                if text:
                    outputs.append(text)
            else:
                outputs.append(f"❌ Unknown tool in plan: {tool}")
        return "\n".join([o for o in outputs if o is not None and o != ""])
    
    def process_request(self, user_input: str) -> str:
        """Process user request."""
        try:
            self._append_history("user", user_input)
            self.remember("last_request", user_input)

            # Explicit commands
            if user_input.strip().lower() in ("/models", "/model list"):
                models_text = "\n".join([f"- {m}" for m in self.available_models])
                out = f"Available models:\n{models_text}\n\nCurrent: {self.model_name}\n\nUse: /model <name>"
                self._append_history("assistant", out)
                return out

            if user_input.strip().lower().startswith("/model "):
                arg = user_input.strip()[7:].strip()
                if arg.lower() in ("show", "current"):
                    out = f"Current model: {self.model_name}"
                    self._append_history("assistant", out)
                    return out
                out = self.set_model(arg)
                self._append_history("assistant", out)
                return out

            if user_input.strip().lower() in ("/planner", "/planner show"):
                out = f"Planner model: {self.planner_model_name}"
                self._append_history("assistant", out)
                return out

            if user_input.strip().lower().startswith("/planner "):
                arg = user_input.strip()[9:].strip()
                out = self.set_planner_model(arg)
                self._append_history("assistant", out)
                return out

            if user_input.strip().lower().startswith("/remember "):
                text = user_input.strip()[10:].strip()
                out = self.rag_add(text, meta={"type": "manual"})
                self._append_history("assistant", out)
                return out

            if user_input.strip().lower().startswith("/memories"):
                q = user_input.strip()[9:].strip()
                if not q:
                    out = "❌ Usage: /memories <query>"
                    self._append_history("assistant", out)
                    return out
                items = self.rag_query(q, k=6)
                if not items:
                    out = "ℹ️ No relevant memories found."
                    self._append_history("assistant", out)
                    return out
                out = "\n".join([f"- {m}" for m in items])
                out = f"Retrieved memories:\n{out}"
                self._append_history("assistant", out)
                return out

            if user_input.strip().lower().startswith("/serve"):
                parts = user_input.strip().split()
                if len(parts) == 1:
                    folder = self.memory.get("last_served_folder") or "restaurant-site"
                    port = int(self.memory.get("last_served_port") or 8000)
                    out = self._serve_start(folder, port)
                    self._append_history("assistant", out)
                    return out

                if len(parts) >= 2 and parts[1].lower() == "stop":
                    out = self._serve_stop()
                    self._append_history("assistant", out)
                    return out

                folder = parts[1]
                port = 8000
                if len(parts) >= 3:
                    try:
                        port = int(parts[2])
                    except ValueError:
                        out = "❌ Port must be a number. Example: /serve restaurant-site 8000"
                        self._append_history("assistant", out)
                        return out

                out = self._serve_start(folder, port)
                self._append_history("assistant", out)
                return out

            if user_input.strip().lower() in ("/pwd", "/cwd"):
                out = str(Path.cwd())
                self._append_history("assistant", out)
                return out

            if user_input.strip().lower().startswith("/files"):
                parts = user_input.strip().split(maxsplit=1)
                folder = parts[1] if len(parts) == 2 else "."
                out = self._list_files(folder)
                self._append_history("assistant", out)
                return out

            if user_input.strip().lower().startswith("/open "):
                path = user_input.strip()[6:].strip()
                out = self._read_file_text(path)
                self._append_history("assistant", out)
                return out

            if user_input.strip().lower() == "/confirm":
                out = self._confirm_command()
                self._append_history("assistant", out)
                return out

            if user_input.strip().lower() == "/cancel":
                out = self._cancel_command()
                self._append_history("assistant", out)
                return out

            if user_input.strip().lower().startswith("/run "):
                cmd = user_input.strip()[5:].strip()
                if not cmd:
                    out = "❌ Usage: /run <command>"
                    self._append_history("assistant", out)
                    return out
                if self._is_command_allowed(cmd):
                    out = self.run_command(cmd)
                    self._append_history("assistant", out)
                    return out
                out = self._queue_command(cmd, reason="Not in safe allowlist")
                self._append_history("assistant", out)
                return out

            if user_input.strip().lower().startswith("/search "):
                query = user_input.strip()[8:].strip()
                out = self.web_search(query)
                self._append_history("assistant", out)
                return out

            # Ask model to either reply or output a JSON plan
            planned = self._plan(user_input)
            if planned.startswith("{"):
                try:
                    plan = json.loads(planned)
                    if plan.get("type") == "plan":
                        out = self._execute_plan(plan)
                        self.remember("last_action", "executed_plan")
                        self._append_history("assistant", out)
                        return out
                except Exception:
                    # Fall through to normal response
                    pass

            # Normal response path
            state = {
                "current_model": self.model_name,
                "planner_model": self.planner_model_name,
                "last_served_folder": self.memory.get("last_served_folder"),
                "last_served_port": self.memory.get("last_served_port"),
                "rag_enabled": self.rag_enabled,
            }

            retrieved = self.rag_query(user_input, k=3)
            if retrieved:
                state["retrieved_memories"] = retrieved
            messages = [
                ("system", self.system_prompt),
                ("system", f"Agent state (JSON): {json.dumps(state)}"),
                ("human", user_input),
            ]
            resp = self.llm.invoke(messages)
            self._append_history("assistant", resp.content)

            if self.rag_enabled:
                _ = self.rag_add(
                    f"USER: {user_input}\nASSISTANT: {resp.content}",
                    meta={"type": "chat"},
                )
            return resp.content
                
        except Exception as e:
            return f"❌ Error processing request: {str(e)}"

    def extract_code_content(self, response_text: str, language: str) -> str:
        """Extract code content from LLM response."""
        try:
            start_marker = f"```{language}"
            start_idx = response_text.find(start_marker)
            if start_idx == -1:
                return ""
            start_idx = response_text.find("\n", start_idx)
            if start_idx == -1:
                return ""
            start_idx += 1
            end_idx = response_text.find("```", start_idx)
            if end_idx == -1:
                return ""
            return response_text[start_idx:end_idx].strip()
        except Exception:
            return ""
    
    def print_header(self):
        """Print agent header."""
        os.system('cls' if os.name == 'nt' else 'clear')
        print("🤖 Simple Autonomous Coding Agent")
        print("=" * 50)
        print("Commands: 'help', 'exit'")
        print("=" * 50)
    
    def print_help(self):
        """Print help information."""
        print("\n📋 Available Commands:")
        print("  help     - Show this help message")
        print("  exit     - Exit the agent")
        print("  /models  - List available models")
        print("  /model <name> - Switch the active model")
        print("  /model show   - Show current model")
        print("  /planner <name> - Switch the planner model (for faster routing)")
        print("  /planner show   - Show current planner model")
        print("  /remember <text> - Save a memory into RAG store")
        print("  /memories <query> - Search your saved memories")
        print("  /search <query> - Force a web search (Tavily)")
        print("  /serve [folder] [port] - Serve a folder via http.server")
        print("  /serve stop - Stop the currently running server")
        print("  /pwd - Show current working directory")
        print("  /files [folder] - List files in a folder")
        print("  /open <file> - Print a file (truncated)")
        print("  /run <command> - Run a command (unsafe commands require /confirm)")
        print("  /confirm - Run the pending command")
        print("  /cancel - Cancel the pending command")
        print("\n💡 You can ask me to:")
        print("  🔍 Search web for information")
        print("  📊 Analyze code and files")
        print("  💻 Execute terminal commands")
        print("  📚 Look up documentation")
        print("  📁 Create, read, write, delete files")
        print("  🐛 Debug and troubleshoot code")
        print("  📋 Plan and implement projects")
        print("\n🔧 Example requests:")
        print('  "Search for Python async best practices"')
        print('  "Analyze current directory"')
        print('  "Create a simple Flask app"')
        print('  "Run tests and show results"')
        print()
    
    def get_input(self, prompt: str) -> str:
        """Get user input without duplication."""
        try:
            return input(prompt)
        except (KeyboardInterrupt, EOFError):
            return ""
    
    def chat_loop(self):
        """Simple chat loop - no asyncio."""
        self.print_header()
        
        while True:
            try:
                # Get user input with proper prompt
                user_input = self.get_input("\n>>> ")
                
                # Handle empty input
                if not user_input:
                    continue
                
                # Handle commands
                cmd_lower = user_input.lower().strip()
                
                if cmd_lower in ['exit', 'quit']:
                    print("\n👋 Goodbye!")
                    break
                
                if cmd_lower == 'help':
                    self.print_help()
                    continue
                
                # Process request
                print("🔄 Processing...")
                response = self.process_request(user_input)
                
                # Print response with clean formatting
                print(f"\n🤖 Agent Response:")
                print("-" * 40)
                print(response)
                print("-" * 40)
                
            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except EOFError:
                print("\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"\n❌ Error: {str(e)}")

def main():
    """Main entry point."""
    # Check if Tavily API key is available
    tavily_api_key = os.getenv("TAVILY_API_KEY")
    
    if not tavily_api_key:
        print("⚠️  TAVILY_API_KEY not found in .env file")
        print("Web search functionality will not be available.")
        print("To enable web search, add TAVILY_API_KEY to your .env file")
        print()
    
    # Create and run agent
    agent = SimpleAgent()
    agent.chat_loop()

if __name__ == "__main__":
    main()
