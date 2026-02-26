from typing import Dict, List
import logging
import base64

from agentkit.tools.toolset_handler import ToolSetHandler, tool

logger = logging.getLogger(__name__)

GITEA_SERVER = "gitea"
REPO_OWNER = "Mathis"
DEFAULT_BRANCH = "main"


class GiteaNotes(ToolSetHandler):

    def __init__(self, name: str = "gitea_notes"):
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
        description="List notes in a Gitea repository as a file tree",
        parameters={
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Name of the Gitea repository"
                },
                "path": {
                    "type": "string",
                    "description": "Optional subdirectory path to list",
                    "default": ""
                }
            },
            "required": ["repo"]
        }
    )
    async def list_notes(self, repo: str, path: str = "") -> str:
        try:
            logger.debug(f"Listing notes for repo='{repo}' path='{path}'")

            result = await self.call_other_tool(
                GITEA_SERVER,
                "get_dir_content",
                {
                    "owner": REPO_OWNER,
                    "repo": repo,
                    "filePath": path,
                    "ref": DEFAULT_BRANCH
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
        description="Get the content of a specific note from a Gitea repository",
        parameters={
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Name of the Gitea repository"
                },
                "filepath": {
                    "type": "string",
                    "description": "Path to the note file"
                }
            },
            "required": ["repo", "filepath"]
        }
    )
    async def get_note(self, repo: str, filepath: str) -> str:
        try:
            logger.debug(f"Getting note: repo='{repo}' filepath='{filepath}'")

            result = await self.call_other_tool(
                GITEA_SERVER,
                "get_file_content",
                {
                    "owner": REPO_OWNER,
                    "repo": repo,
                    "filePath": filepath,
                    "ref": DEFAULT_BRANCH
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
        description="Create a new note with specified content in a Gitea repository",
        parameters={
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Name of the Gitea repository"
                },
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
            "required": ["repo", "filepath", "content"]
        }
    )
    async def create_note(self, repo: str, filepath: str, content: str, commit_message: str = "Create note") -> str:
        try:
            await self.call_other_tool(
                GITEA_SERVER,
                "create_file",
                {
                    "owner": REPO_OWNER,
                    "repo": repo,
                    "filePath": filepath,
                    "content": content,
                    "message": commit_message,
                    "branch_name": DEFAULT_BRANCH
                }
            )

            return f"Successfully created note: {filepath}"

        except Exception as e:
            logger.error(f"Error creating note '{filepath}': {e}", exc_info=True)
            return f"Error creating note: {str(e)}"
