#!/usr/bin/env python3
"""
MCP Server with Tavily Search Integration for Autonomous Coding Agent
Provides web search, code analysis, and development tools via Model Context Protocol
"""

import os
import sys
import asyncio
import json
import re
import subprocess
from typing import Any, Dict, List, Optional, Sequence
from pathlib import Path

from fastmcp import FastMCP
from tavily import TavilyClient
import aiofiles
import aiohttp

# Initialize FastMCP server
mcp = FastMCP("autonomous-coding-agent")

# Initialize Tavily client (requires TAVILY_API_KEY)
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "").strip()
tavily_client = TavilyClient(api_key=TAVILY_API_KEY) if TAVILY_API_KEY else None

@mcp.tool()
def web_search(query: str, max_results: int = 5) -> Dict[str, Any]:
    """
    Search the web for information using Tavily API.
    
    Args:
        query: Search query string
        max_results: Maximum number of results to return (default: 5)
    
    Returns:
        Dictionary containing search results with titles, URLs, and snippets
    """
    try:
        if not tavily_client:
            return {
                "error": "TAVILY_API_KEY not configured",
                "query": query,
                "results": [],
            }
        # Perform search with Tavily
        response = tavily_client.search(
            query=query,
            max_results=max_results,
            search_depth="basic",
            include_answer=True,
            include_raw_content=False,
            include_domains=None,
            exclude_domains=None
        )
        
        # Format results
        formatted_results = {
            "query": query,
            "answer": response.get("answer", ""),
            "results": []
        }
        
        for result in response.get("results", []):
            formatted_results["results"].append({
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "snippet": result.get("content", ""),
                "score": result.get("score", 0)
            })
        
        return formatted_results
        
    except Exception as e:
        return {
            "error": f"Search failed: {str(e)}",
            "query": query,
            "results": []
        }

@mcp.tool()
def search_documentation(query: str, domain: str = "docs.python.org") -> Dict[str, Any]:
    """
    Search technical documentation for specific programming topics.
    
    Args:
        query: Search query for documentation
        domain: Specific documentation domain (default: docs.python.org)
    
    Returns:
        Dictionary containing relevant documentation results
    """
    try:
        if not tavily_client:
            return {
                "error": "TAVILY_API_KEY not configured",
                "query": query,
                "domain": domain,
                "results": [],
            }
        # Create domain-specific search query
        domain_query = f"{query} site:{domain}"
        
        response = tavily_client.search(
            query=domain_query,
            max_results=3,
            search_depth="advanced",
            include_answer=True,
            include_domains=[domain]
        )
        
        formatted_results = {
            "query": query,
            "domain": domain,
            "answer": response.get("answer", ""),
            "results": []
        }
        
        for result in response.get("results", []):
            formatted_results["results"].append({
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "snippet": result.get("content", ""),
                "relevance": result.get("score", 0)
            })
        
        return formatted_results
        
    except Exception as e:
        return {
            "error": f"Documentation search failed: {str(e)}",
            "query": query,
            "domain": domain,
            "results": []
        }

@mcp.tool()
def analyze_code(file_path: str) -> Dict[str, Any]:
    """
    Analyze code file structure, dependencies, and potential issues.
    
    Args:
        file_path: Path to the code file to analyze
    
    Returns:
        Dictionary containing code analysis results
    """
    try:
        if not os.path.exists(file_path):
            return {"error": f"File not found: {file_path}"}
        
        # Read file content
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        analysis = {
            "file_path": file_path,
            "lines_count": len(content.split('\n')),
            "characters_count": len(content),
            "language": Path(file_path).suffix[1:] if Path(file_path).suffix else "unknown",
            "imports": [],
            "functions": [],
            "classes": [],
            "potential_issues": []
        }
        
        # Language-specific analysis
        if file_path.endswith('.py'):
            # Extract imports
            import_patterns = [
                r'^import\s+([^\s]+)',
                r'^from\s+([^\s]+)\s+import'
            ]
            for pattern in import_patterns:
                matches = re.findall(pattern, content, re.MULTILINE)
                analysis["imports"].extend(matches)
            
            # Extract functions
            func_matches = re.findall(r'def\s+(\w+)\s*\(', content)
            analysis["functions"] = func_matches
            
            # Extract classes
            class_matches = re.findall(r'class\s+(\w+)', content)
            analysis["classes"] = class_matches
            
            # Check for common issues
            if re.search(r'print\([^)]*\)', content):
                analysis["potential_issues"].append("Contains print statements (consider using logging)")
            
            if content.count('except:') > 0:
                analysis["potential_issues"].append("Contains bare except clauses")
        
        elif file_path.endswith(('.js', '.ts')):
            # JavaScript/TypeScript analysis
            import_matches = re.findall(r'import.*from\s+[\'"]([^\'"]+)[\'"]', content)
            analysis["imports"] = import_matches
            
            func_matches = re.findall(r'(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:function|\([^)]*\)\s*=>))', content)
            analysis["functions"] = [f[0] or f[1] for f in func_matches if f[0] or f[1]]
        
        return analysis
        
    except Exception as e:
        return {"error": f"Code analysis failed: {str(e)}"}

@mcp.tool()
def search_codebase(directory: str, pattern: str, file_type: str = "py") -> Dict[str, Any]:
    """
    Search for patterns within a codebase directory.
    
    Args:
        directory: Directory to search in
        pattern: Regex pattern to search for
        file_type: File extension to filter (default: py)
    
    Returns:
        Dictionary containing search results with file paths and matches
    """
    try:
        results = {
            "directory": directory,
            "pattern": pattern,
            "file_type": file_type,
            "matches": []
        }
        
        directory_path = Path(directory)
        if not directory_path.exists():
            return {"error": f"Directory not found: {directory}"}
        
        # Compile regex pattern
        regex_pattern = re.compile(pattern, re.IGNORECASE)
        
        # Search through files
        for file_path in directory_path.rglob(f"*.{file_type}"):
            if file_path.is_file():
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    matches = regex_pattern.finditer(content)
                    for match in matches:
                        line_number = content[:match.start()].count('\n') + 1
                        line_content = content.split('\n')[line_number - 1].strip()
                        
                        results["matches"].append({
                            "file": str(file_path),
                            "line": line_number,
                            "content": line_content,
                            "match": match.group()
                        })
                
                except (UnicodeDecodeError, PermissionError):
                    continue
        
        return results
        
    except Exception as e:
        return {"error": f"Codebase search failed: {str(e)}"}

@mcp.tool()
def get_file_info(file_path: str) -> Dict[str, Any]:
    """
    Get detailed information about a file.
    
    Args:
        file_path: Path to the file
    
    Returns:
        Dictionary containing file information
    """
    try:
        path = Path(file_path)
        
        if not path.exists():
            return {"error": f"File not found: {file_path}"}
        
        stat = path.stat()
        
        info = {
            "file_path": str(path.absolute()),
            "name": path.name,
            "size": stat.st_size,
            "created": stat.st_ctime,
            "modified": stat.st_mtime,
            "is_file": path.is_file(),
            "is_directory": path.is_dir(),
            "extension": path.suffix,
            "parent": str(path.parent)
        }
        
        if path.is_file():
            # Add file content analysis
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                info.update({
                    "lines": len(content.split('\n')),
                    "characters": len(content),
                    "encoding": 'utf-8'
                })
            except UnicodeDecodeError:
                info["encoding"] = 'binary'
        
        return info
        
    except Exception as e:
        return {"error": f"Failed to get file info: {str(e)}"}

@mcp.tool()
def run_terminal_command(command: str, working_directory: str = ".") -> Dict[str, Any]:
    """
    Execute a terminal command and return the output.
    
    Args:
        command: Command to execute
        working_directory: Directory to run the command in (default: current directory)
    
    Returns:
        Dictionary containing command execution results
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=working_directory,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        return {
            "command": command,
            "working_directory": working_directory,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "success": result.returncode == 0
        }
        
    except subprocess.TimeoutExpired:
        return {
            "command": command,
            "working_directory": working_directory,
            "error": "Command timed out after 30 seconds",
            "success": False
        }
    except Exception as e:
        return {
            "command": command,
            "working_directory": working_directory,
            "error": str(e),
            "success": False
        }

if __name__ == "__main__":
    # Run the MCP server
    mcp.run(transport="stdio")
