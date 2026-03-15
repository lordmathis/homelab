import logging

from agentkit.tools.toolset_handler import ToolSetHandler, tool

logger = logging.getLogger(__name__)

NOTES_REPO = "Notes"
NOTES_PATH = "🧑‍🍳 Recipes"
BASE_NOTES_TOOL = "base_notes"


class RecipesNotesTool(ToolSetHandler):
    server_name = "recipes_notes"

    def __init__(self):
        super().__init__()

    @tool(
        description="List all recipes notes as a file tree",
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
        full_path = f"{NOTES_PATH}/{path}".strip("/") if path else NOTES_PATH
        return await self.call_other_tool(
            "base_notes__list_notes", {"repo": NOTES_REPO, "path": full_path}
        )

    @tool(
        description="Get the content of a specific recipe note",
        parameters={
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "Path to the note file (relative to Recipes folder)"
                }
            },
            "required": ["filepath"]
        }
    )
    async def get_note(self, filepath: str) -> str:
        full_path = f"{NOTES_PATH}/{filepath}"
        return await self.call_other_tool(
            "base_notes__get_note", {"repo": NOTES_REPO, "filepath": full_path}
        )

    @tool(
        description="Create a new recipe note with specified content",
        parameters={
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "Path where the note should be created (relative to Recipes folder)"
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
        full_path = f"{NOTES_PATH}/{filepath}"
        return await self.call_other_tool(
            "base_notes__create_note",
            {"repo": NOTES_REPO, "filepath": full_path, "content": content, "commit_message": commit_message}
        )

    @tool(
        description="Update an existing recipe note with new content",
        parameters={
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "Path to the note file to update (relative to Recipes folder)"
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
        full_path = f"{NOTES_PATH}/{filepath}"
        return await self.call_other_tool(
            "base_notes__update_note",
            {"repo": NOTES_REPO, "filepath": full_path, "content": content, "commit_message": commit_message}
        )
