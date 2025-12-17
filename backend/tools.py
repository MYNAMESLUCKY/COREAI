import os
import re
import json
import subprocess
from typing import List, Dict, Any, Optional
from langchain.tools import BaseTool
from pydantic import BaseModel, Field
import shutil

class FileReadTool(BaseTool):
    name = "file_read"
    description = "Read the contents of a file. Use this when you need to examine existing code or files."
    
    def _run(self, file_path: str) -> str:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            return f"Error reading file: {str(e)}"

class FileWriteTool(BaseTool):
    name = "file_write"
    description = "Write content to a file. Creates the file if it doesn't exist. Overwrites existing content."
    
    def _run(self, file_path: str, content: str) -> str:
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return f"Successfully wrote to {file_path}"
        except Exception as e:
            return f"Error writing file: {str(e)}"

class FileAppendTool(BaseTool):
    name = "file_append"
    description = "Append content to an existing file."
    
    def _run(self, file_path: str, content: str) -> str:
        try:
            with open(file_path, 'a', encoding='utf-8') as f:
                f.write(content)
            return f"Successfully appended to {file_path}"
        except Exception as e:
            return f"Error appending to file: {str(e)}"

class FileDeleteTool(BaseTool):
    name = "file_delete"
    description = "Delete a file or directory."
    
    def _run(self, file_path: str) -> str:
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)
                return f"Successfully deleted file: {file_path}"
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
                return f"Successfully deleted directory: {file_path}"
            else:
                return f"Path does not exist: {file_path}"
        except Exception as e:
            return f"Error deleting: {str(e)}"

class ListDirectoryTool(BaseTool):
    name = "list_directory"
    description = "List contents of a directory."
    
    def _run(self, directory_path: str) -> str:
        try:
            if not os.path.exists(directory_path):
                return f"Directory does not exist: {directory_path}"
            
            items = []
            for item in os.listdir(directory_path):
                item_path = os.path.join(directory_path, item)
                if os.path.isfile(item_path):
                    size = os.path.getsize(item_path)
                    items.append(f"FILE: {item} ({size} bytes)")
                else:
                    items.append(f"DIR:  {item}")
            
            return "\n".join(items) if items else "Directory is empty"
        except Exception as e:
            return f"Error listing directory: {str(e)}"

class CreateDirectoryTool(BaseTool):
    name = "create_directory"
    description = "Create a new directory and any necessary parent directories."
    
    def _run(self, directory_path: str) -> str:
        try:
            os.makedirs(directory_path, exist_ok=True)
            return f"Successfully created directory: {directory_path}"
        except Exception as e:
            return f"Error creating directory: {str(e)}"

class SearchFilesTool(BaseTool):
    name = "search_files"
    description = "Search for files by name pattern or content within files."
    
    def _run(self, search_term: str, search_type: str = "name", directory: str = ".") -> str:
        try:
            results = []
            
            if search_type == "name":
                for root, dirs, files in os.walk(directory):
                    for file in files:
                        if re.search(search_term, file, re.IGNORECASE):
                            results.append(os.path.join(root, file))
            
            elif search_type == "content":
                for root, dirs, files in os.walk(directory):
                    for file in files:
                        if file.endswith(('.py', '.js', '.ts', '.html', '.css', '.md', '.txt')):
                            try:
                                file_path = os.path.join(root, file)
                                with open(file_path, 'r', encoding='utf-8') as f:
                                    content = f.read()
                                    if re.search(search_term, content, re.IGNORECASE):
                                        results.append(file_path)
                            except:
                                continue
            
            return "\n".join(results) if results else f"No matches found for '{search_term}'"
        except Exception as e:
            return f"Error searching: {str(e)}"

class RunCommandTool(BaseTool):
    name = "run_command"
    description = "Execute a terminal command. Use with caution for potentially dangerous operations."
    
    def _run(self, command: str, working_directory: str = ".") -> str:
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=working_directory,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            output = f"Exit code: {result.returncode}\n"
            if result.stdout:
                output += f"STDOUT:\n{result.stdout}"
            if result.stderr:
                output += f"STDERR:\n{result.stderr}"
            
            return output
        except subprocess.TimeoutExpired:
            return "Command timed out after 30 seconds"
        except Exception as e:
            return f"Error running command: {str(e)}"

class CodeAnalysisTool(BaseTool):
    name = "code_analysis"
    description = "Analyze code structure, dependencies, and potential issues."
    
    def _run(self, file_path: str) -> str:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            analysis = []
            
            # Basic file info
            lines = content.split('\n')
            analysis.append(f"File: {file_path}")
            analysis.append(f"Lines: {len(lines)}")
            analysis.append(f"Size: {len(content)} characters")
            
            # Language detection
            if file_path.endswith('.py'):
                analysis.append("\nPython Analysis:")
                imports = re.findall(r'^(?:from|import)\s+.+$', content, re.MULTILINE)
                if imports:
                    analysis.append("Imports:")
                    for imp in imports:
                        analysis.append(f"  - {imp}")
                
                functions = re.findall(r'def\s+(\w+)\s*\(', content)
                if functions:
                    analysis.append(f"Functions found: {', '.join(functions)}")
                
                classes = re.findall(r'class\s+(\w+)', content)
                if classes:
                    analysis.append(f"Classes found: {', '.join(classes)}")
            
            elif file_path.endswith(('.js', '.ts')):
                analysis.append("\nJavaScript/TypeScript Analysis:")
                imports = re.findall(r'^(?:import|const)\s+.+from\s+.+$', content, re.MULTILINE)
                if imports:
                    analysis.append("Imports:")
                    for imp in imports:
                        analysis.append(f"  - {imp}")
                
                functions = re.findall(r'(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:function|\([^)]*\)\s*=>))', content)
                funcs = [f[0] or f[1] for f in functions if f[0] or f[1]]
                if funcs:
                    analysis.append(f"Functions found: {', '.join(funcs)}")
            
            return "\n".join(analysis)
        except Exception as e:
            return f"Error analyzing code: {str(e)}"

class TaskClassifier(BaseModel):
    """Classifies user requests to determine if they need coding tools or just a normal response."""
    
    @staticmethod
    def is_coding_task(user_input: str) -> bool:
        """Determine if the user request requires coding tools."""
        coding_keywords = [
            'create', 'write', 'delete', 'modify', 'edit', 'update', 'build',
            'file', 'code', 'program', 'script', 'function', 'class', 'api',
            'directory', 'folder', 'run', 'execute', 'compile', 'test', 'debug',
            'install', 'setup', 'configure', 'deploy', 'search', 'find',
            'list', 'show', 'read', 'append', 'copy', 'move', 'rename'
        ]
        
        file_patterns = [
            r'\.py$', r'\.js$', r'\.ts$', r'\.html$', r'\.css$', r'\.md$',
            r'\.json$', r'\.txt$', r'\.csv$', r'\.xml$', r'\.yaml$', r'\.yml$'
        ]
        
        user_input_lower = user_input.lower()
        
        # Check for coding keywords
        for keyword in coding_keywords:
            if keyword in user_input_lower:
                return True
        
        # Check for file patterns
        for pattern in file_patterns:
            if re.search(pattern, user_input):
                return True
        
        # Check for path-like patterns
        if re.search(r'[\\/]', user_input):
            return True
        
        return False

# Tool collection for the autonomous coding agent
AUTONOMOUS_CODING_TOOLS = [
    FileReadTool(),
    FileWriteTool(),
    FileAppendTool(),
    FileDeleteTool(),
    ListDirectoryTool(),
    CreateDirectoryTool(),
    SearchFilesTool(),
    RunCommandTool(),
    CodeAnalysisTool()
]

def get_available_tools() -> List[BaseTool]:
    """Return all available tools for the autonomous coding agent."""
    return AUTONOMOUS_CODING_TOOLS

def should_use_tools(user_input: str) -> bool:
    """Determine if tools should be used for this request."""
    return TaskClassifier.is_coding_task(user_input)
