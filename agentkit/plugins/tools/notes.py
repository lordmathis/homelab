from typing import Any, Dict, List
import logging
import base64

from agentkit.tools.toolset_handler import ToolSetHandler, tool

logger = logging.getLogger(__name__)


class NotesTool(ToolSetHandler):
    
    gitea_server = "gitea"
    repo_owner = "Mathis"
    repo_name = "Notes"
    default_branch = "main"
    
    def __init__(self, name: str = "notes"):
        super().__init__(name)
    
    def _format_tree(self, entries: List[Dict]) -> List[str]:
        lines = []
        
        dirs = [e for e in entries if e.get("type") == "dir"]
        files = [e for e in entries if e.get("type") == "file"]
        sorted_entries = dirs + files
        
        for i, entry in enumerate(sorted_entries):
            is_last = (i == len(sorted_entries) - 1)
            connector = "└── " if is_last else "├── "
            name = entry.get("name", "")
            entry_type = entry.get("type", "")
            display_name = f"{name}/" if entry_type == "dir" else name
            lines.append(f"{connector}{display_name}")
        
        return lines
    
    @tool(
        description="List all notes in the repository as a file tree",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Optional subdirectory path to list",
                    "default": ""
                }
            }
        }
    )
    async def list_notes(self, path: str = "") -> str:
        try:
            logger.debug(f"Listing notes for path='{path}'")

            result = await self.call_other_tool(
                self.gitea_server,
                "get_dir_content",
                {
                    "owner": self.repo_owner,
                    "repo": self.repo_name,
                    "filePath": path,
                    "ref": self.default_branch
                }
            )

            if not result:
                return f"No notes found in '{path or 'root'}'"

            tree_lines = [f"Notes in '{path or 'root'}':"]
            tree_lines.extend(self._format_tree(result))

            return "\n".join(tree_lines)

        except Exception as e:
            logger.error(f"Error listing notes: {e}", exc_info=True)
            return f"Error listing notes: {str(e)}"
    
    @tool(
        description="Get the content of a specific note",
        parameters={
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "Path to the note file"
                }
            },
            "required": ["filepath"]
        }
    )
    async def get_note(self, filepath: str) -> str:
        try:
            logger.debug(f"Getting note: {filepath}")

            result = await self.call_other_tool(
                self.gitea_server,
                "get_file_content",
                {
                    "owner": self.repo_owner,
                    "repo": self.repo_name,
                    "filePath": filepath,
                    "ref": self.default_branch
                }
            )

            if not result:
                return f"Note not found: {filepath}"

            content_base64 = result.get("content", "")
            if not content_base64:
                return f"Note is empty: {filepath}"

            content = base64.b64decode(content_base64).decode('utf-8')
            return content

        except Exception as e:
            logger.error(f"Error getting note '{filepath}': {e}", exc_info=True)
            return f"Error getting note: {str(e)}"
    
    @tool(
        description="Create a new note with specified content",
        parameters={
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "Path where the note should be created"
                },
                "content": {
                    "type": "string",
                    "description": "Content of the note"
                },
                "commit_message": {
                    "type": "string",
                    "description": "Optional commit message",
                    "default": "Create note"
                }
            },
            "required": ["filepath", "content"]
        }
    )
    async def create_note(self, filepath: str, content: str, commit_message: str = "Create note") -> str:
        try:
            await self.call_other_tool(
                self.gitea_server,
                "create_file",
                {
                    "owner": self.repo_owner,
                    "repo": self.repo_name,
                    "filePath": filepath,
                    "content": content,
                    "message": commit_message,
                    "branch_name": self.default_branch
                }
            )
            
            return f"Successfully created note: {filepath}"
            
        except Exception as e:
            logger.error(f"Error creating note '{filepath}': {e}", exc_info=True)
            return f"Error creating note: {str(e)}"