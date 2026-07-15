"""
Workout Toolset Plugin - Thin file operations over a Gitea markdown repo
"""

import base64
import logging
from typing import Optional

from mikoshi.tools.context import ToolCallContext
from mikoshi.tools.toolset_handler import ToolSetHandler, tool

logger = logging.getLogger(__name__)

REPO_OWNER = "Mathis"
REPO = "workouts"
BRANCH = "main"


class WorkoutToolset(ToolSetHandler):
    server_name = "workout"

    @tool(
        description="List files in a directory in the workouts repo.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path (e.g. 'workouts')"}
            },
            "required": ["path"],
        },
    )
    async def list_files(self, path: str, context: ToolCallContext = None) -> str:
        try:
            result = await self.call_other_tool(
                "gitea__get_dir_contents",
                {"owner": REPO_OWNER, "repo": REPO, "path": path, "ref": BRANCH},
                context,
            )
            if not result:
                return f"Empty directory: {path}"
            lines = []
            for e in result:
                name = e.get("name", "")
                if e.get("type") == "dir":
                    lines.append(f"{name}/")
                else:
                    lines.append(name)
            return "\n".join(lines)
        except Exception as e:
            return f"Error listing {path}: {str(e)}"

    @tool(
        description="Read a file from the workouts repo. Returns raw markdown text.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path (e.g. 'workouts/2026-05-19.md')"}
            },
            "required": ["path"],
        },
    )
    async def read_file(self, path: str, context: ToolCallContext = None) -> str:
        try:
            result = await self.call_other_tool(
                "gitea__get_file_contents",
                {"owner": REPO_OWNER, "repo": REPO, "path": path, "ref": BRANCH},
                context,
            )
            if not result:
                return f"File not found: {path}"
            content_b64 = result.get("content", "") if isinstance(result, dict) else ""
            if not content_b64:
                return f"File is empty: {path}"
            return base64.b64decode(content_b64).decode("utf-8")
        except Exception as e:
            return f"Error reading {path}: {str(e)}"

    @tool(
        description="Write a file to the workouts repo. Creates a new file or updates an existing one.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
                "content": {"type": "string", "description": "File content (markdown)"},
                "message": {"type": "string", "description": "Commit message"},
            },
            "required": ["path", "content", "message"],
        },
    )
    async def write_file(self, path: str, content: str, message: str, context: ToolCallContext = None) -> str:
        try:
            params = {
                "owner": REPO_OWNER, "repo": REPO, "path": path,
                "content": content, "message": message, "branch_name": BRANCH,
            }
            try:
                existing = await self.call_other_tool(
                    "gitea__get_file_contents",
                    {"owner": REPO_OWNER, "repo": REPO, "path": path, "ref": BRANCH},
                    context,
                )
                if isinstance(existing, dict) and existing.get("sha"):
                    params["sha"] = existing["sha"]
            except Exception as e:
                logger.debug(f"No existing file at {path}, will create: {e}")
            await self.call_other_tool("gitea__create_or_update_file", params, context)
            return f"Saved: {path}"
        except Exception as e:
            return f"Error writing {path}: {str(e)}"
