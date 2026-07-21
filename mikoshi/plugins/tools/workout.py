"""
Workout Toolset Plugin - Session-based workout logging over a Gitea markdown repo.

Agent-facing tools: read_file / write_file (general file ops, used for exercises.md),
log_set (append sets; lazily opens a session), finish_workout (render markdown, write
the workout file, close the session).
"""

import base64
import datetime
import json
import logging
import os
from typing import Optional

from mikoshi.tools.context import ToolCallContext
from mikoshi.tools.toolset_handler import ToolSetHandler, tool

logger = logging.getLogger(__name__)

REPO_OWNER = "Mathis"
REPO = "workouts"
BRANCH = "main"


class WorkoutToolset(ToolSetHandler):
    server_name = "workout"

    # --- File tools (general) -------------------------------------------

    @tool(
        description=(
            "Read a file from the workouts repo. Use it on 'exercises.md' to find "
            "canonical exercise names."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path (e.g. 'exercises.md')"}
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
        description=(
            "Create or update a file in the workouts repo. Use it to add a new exercise "
            "to exercises.md (read it first, append the name, write it back)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
                "content": {"type": "string", "description": "Full file content"},
                "message": {"type": "string", "description": "Commit message"},
            },
            "required": ["path", "content", "message"],
        },
    )
    async def write_file(self, path: str, content: str, message: str, context: ToolCallContext = None) -> str:
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
            logger.debug("No existing file at %s, will create: %s", path, e)

        try:
            await self.call_other_tool("gitea__create_or_update_file", params, context)
            return f"Saved: {path}"
        except Exception as e:
            return f"Error writing {path}: {str(e)}"

    # --- Session helpers -------------------------------------------------

    def _session_path(self, chat_id: str) -> str:
        storage = self.get_persistent_storage()
        return os.path.join(storage, f".session.{chat_id}.json")

    def _load_session(self, chat_id: str) -> Optional[dict]:
        path = self._session_path(chat_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            logger.warning("Corrupt session file at %s; treating as no session", path)
            return None

    def _save_session(self, chat_id: str, session: dict) -> None:
        path = self._session_path(chat_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(session, f, indent=2)

    def _delete_session(self, chat_id: str) -> None:
        path = self._session_path(chat_id)
        if os.path.exists(path):
            os.remove(path)

    def _summary(self, session: dict) -> dict:
        sets = session.get("sets", [])
        if not sets:
            progress = "no sets logged yet"
        else:
            groups = {}
            order = []
            for s in sets:
                name = s["name"]
                if name not in groups:
                    groups[name] = []
                    order.append(name)
                groups[name].append((s["weight"], s["reps"]))
            parts = []
            for name in order:
                entries = groups[name]
                count = len(entries)
                sets_word = "set" if count == 1 else "sets"
                entries_str = ", ".join(f"{w} {r}" for w, r in entries)
                parts.append(f"{name} {entries_str} ({count} {sets_word})")
            progress = "; ".join(parts)
        return {
            "status": "active",
            "date": session["date"],
            "progress": progress,
        }

    def _render_markdown(self, session: dict) -> str:
        lines = [
            f"# {session['date']}",
            "",
            "| Exercise Name | Weight | Reps/Time | Notes |",
            "|---|---|---|---|",
        ]
        for s in session["sets"]:
            lines.append(f'| {s["name"]} | {s["weight"]} | {s["reps"]} | |')
        return "\n".join(lines) + "\n"

    # --- Session tools ---------------------------------------------------

    @tool(
        description=(
            "Log one or more completed sets. Opens a new workout session automatically "
            "on the first call (date captured server-side). Use sets=N for 'NxM' / "
            "'N sets of M' phrasings; use separate calls for varied weight or reps. "
            "weight='—' for bodyweight/timed; reps may be a duration like '45s'. "
            "Pass the exercise name exactly as it appears in exercises.md. Carry the "
            "returned summary into new_state."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Exercise name (canonical form from exercises.md).",
                },
                "weight": {
                    "type": "string",
                    "description": "Weight used, e.g. '60kg'. Use '—' if not applicable.",
                },
                "reps": {
                    "type": "string",
                    "description": "Reps or time, e.g. '10 reps' or '45s'.",
                },
                "sets": {
                    "type": "integer",
                    "description": "Number of identical sets to log (default 1).",
                    "default": 1,
                },
            },
            "required": ["name", "weight", "reps"],
        },
    )
    async def log_set(self, name, weight, reps, sets=1, context=None):
        session = self._load_session(context.chat_id)
        if session is None:
            session = {"date": datetime.date.today().isoformat(), "sets": []}

        try:
            count = max(1, int(sets))
        except (TypeError, ValueError):
            count = 1
        for _ in range(count):
            session["sets"].append({"name": name, "weight": weight, "reps": reps})
        self._save_session(context.chat_id, session)
        logger.info(
            "chat_id=%s logged %s x%d %s %s",
            context.chat_id, name, count, weight, reps,
        )
        return json.dumps(self._summary(session))

    @tool(
        description=(
            "Finish the active workout: render it as markdown, write workouts/<date>.md, "
            "and close the session. Returns the file path and content."
        ),
        parameters={"type": "object", "properties": {}},
    )
    async def finish_workout(self, context=None):
        session = self._load_session(context.chat_id)
        if session is None:
            return json.dumps({"error": "No active workout session to finish."})
        if not session.get("sets"):
            self._delete_session(context.chat_id)
            return json.dumps(
                {"error": "No sets logged; session closed without writing a file."}
            )

        content = self._render_markdown(session)
        path = f"workouts/{session['date']}.md"
        save_result = await self.write_file(
            path, content, f"Workout {session['date']}", context
        )
        self._delete_session(context.chat_id)
        logger.info("chat_id=%s finished workout path=%s", context.chat_id, path)
        return json.dumps({"path": path, "content": content, "save_result": save_result})
