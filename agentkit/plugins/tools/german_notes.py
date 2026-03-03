import logging

from agentkit.tools.toolset_handler import ToolSetHandler, tool

logger = logging.getLogger(__name__)

GERMAN_REPO = "German"


class GermanNotesTool(ToolSetHandler):

    def __init__(self, name: str = "german_notes"):
        super().__init__(name)

    @tool(
        description="List all German learning notes as a file tree",
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
        return await self.call_other_tool(
            "gitea_notes", "list_notes", {"repo": GERMAN_REPO, "path": path}
        )

    @tool(
        description="Get the content of a specific German learning note",
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
        return await self.call_other_tool(
            "gitea_notes", "get_note", {"repo": GERMAN_REPO, "filepath": filepath}
        )

    @tool(
        description="Create a new German learning note with specified content",
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
        return await self.call_other_tool(
            "gitea_notes", "create_note",
            {"repo": GERMAN_REPO, "filepath": filepath, "content": content, "commit_message": commit_message}
        )

    @tool(
        description="Update an existing German learning note with new content",
        parameters={
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "Path to the note file to update"
                },
                "content": {
                    "type": "string",
                    "description": "New content for the note"
                },
                "commit_message": {
                    "type": "string",
                    "description": "Optional commit message",
                    "default": "Update note"
                }
            },
            "required": ["filepath", "content"]
        }
    )
    async def update_note(self, filepath: str, content: str, commit_message: str = "Update note") -> str:
        return await self.call_other_tool(
            "gitea_notes", "update_note",
            {"repo": GERMAN_REPO, "filepath": filepath, "content": content, "commit_message": commit_message}
        )
