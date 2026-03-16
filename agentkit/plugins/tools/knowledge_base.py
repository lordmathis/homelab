import logging

from agentkit.tools.toolset_handler import ToolSetHandler, tool

logger = logging.getLogger(__name__)

NOTES_REPO = "Notes"
BASE_NOTES_TOOL = "base_notes"

EXCLUDED_FOLDERS = ["🥨 German", "🧑‍🍳 Recipes", "💻 CompSci"]


class KnowledgeBaseTool(ToolSetHandler):
    server_name = "knowledge_base"

    def __init__(self):
        super().__init__()

    @tool(
        description="List all knowledge base notes as a file tree (excludes German, Recipes, and CompSci folders)",
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
            "base_notes__list_notes", 
            {"repo": NOTES_REPO, "path": path, "excluded_folders": EXCLUDED_FOLDERS}
        )

    @tool(
        description="Get the content of a specific knowledge base note (cannot access German, Recipes, or CompSci folders)",
        parameters={
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "Path to the note file (cannot be in German, Recipes, or CompSci folders)"
                }
            },
            "required": ["filepath"]
        }
    )
    async def get_note(self, filepath: str) -> str:
        first_folder = filepath.split("/")[0] if "/" in filepath else filepath
        if first_folder in EXCLUDED_FOLDERS:
            return "Access denied: Cannot access notes in specialized folders. Use german_notes, recipes_notes, or computer_science_notes tools instead."
        
        return await self.call_other_tool(
            "base_notes__get_note", {"repo": NOTES_REPO, "filepath": filepath}
        )

    @tool(
        description="Create a new knowledge base note with specified content (cannot create in German, Recipes, or CompSci folders)",
        parameters={
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "Path where the note should be created (cannot be in German, Recipes, or CompSci folders)"
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
        first_folder = filepath.split("/")[0] if "/" in filepath else filepath
        if first_folder in EXCLUDED_FOLDERS:
            return "Access denied: Cannot create notes in specialized folders. Use german_notes, recipes_notes, or computer_science_notes tools instead."
        
        return await self.call_other_tool(
            "base_notes__create_note",
            {"repo": NOTES_REPO, "filepath": filepath, "content": content, "commit_message": commit_message}
        )

    @tool(
        description="Update an existing knowledge base note with new content (cannot update notes in German, Recipes, or CompSci folders)",
        parameters={
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "Path to the note file to update (cannot be in German, Recipes, or CompSci folders)"
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
        first_folder = filepath.split("/")[0] if "/" in filepath else filepath
        if first_folder in EXCLUDED_FOLDERS:
            return "Access denied: Cannot update notes in specialized folders. Use german_notes, recipes_notes, or computer_science_notes tools instead."
        
        return await self.call_other_tool(
            "base_notes__update_note",
            {"repo": NOTES_REPO, "filepath": filepath, "content": content, "commit_message": commit_message}
        )
