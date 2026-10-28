"""
Workout Toolset Plugin - Session-based workout logging in the workouts workspace.

Operates directly on the workspace clone of the workouts repo: files are
read/written on disk, every write is committed and pushed. The repo is
pulled once per chat before the first tool call.
"""

import asyncio
import datetime
import json
import logging
import os
from typing import Optional

from mikoshi.agents.streaming import StreamEvent
from mikoshi.git import GitService
from mikoshi.tools.context import ToolCallContext
from mikoshi.tools.toolset_handler import ToolSetHandler, tool

logger = logging.getLogger(__name__)


class WorkoutToolset(ToolSetHandler):
    server_name = "workout"

    def __init__(self):
        super().__init__()
        self._pulled_chats: set = set()
        self._pull_lock = asyncio.Lock()

    # --- Workspace helpers ----------------------------------------------

    def _root(self, context) -> Optional[str]:
        if context is None or context.workspace is None:
            return None
        return context.workspace.root

    def _resolve(self, root: str, path: str) -> str:
        full = os.path.realpath(os.path.join(root, path))
        if full != root and not full.startswith(root + os.sep):
            raise ValueError("Path is outside the workspace")
        return full

    def _git(self, context) -> GitService:
        return GitService(context.workspace.root, context.workspace.workspace_id)

    async def _auth_env(self, context) -> dict:
        ws = context.workspace
        token = None
        if ws.connector and self._tool_manager:
            token = self._tool_manager.get_connector_token(ws.connector)
        return await self._git(context).https_auth_env(token)

    async def _ensure_pulled(self, context) -> None:
        if context.chat_id in self._pulled_chats:
            return
        async with self._pull_lock:
            if context.chat_id in self._pulled_chats:
                return
            # Mark pulled even on failure to avoid retrying on every call.
            self._pulled_chats.add(context.chat_id)
            try:
                result = await self._git(context).pull(await self._auth_env(context))
                logger.info(
                    "chat_id=%s initial pull success=%s output=%s",
                    context.chat_id, result.success, result.output,
                )
            except Exception as e:
                logger.warning("chat_id=%s initial pull failed: %s", context.chat_id, e)

    async def _name_chat(self, context, title: str) -> None:
        tm = self._tool_manager
        if tm is None:
            return
        tm.set_chat_title(context.chat_id, title)
        if context.stream_queue is not None:
            await context.stream_queue.put(
                StreamEvent(
                    type="chat_renamed",
                    data={"chat_id": context.chat_id, "title": title},
                )
            )

    async def _commit_and_push(self, context, message: str) -> dict:
        svc = self._git(context)
        result = await svc.commit(
            message, context.workspace.git_user_name, context.workspace.git_user_email
        )
        if not result.success and "nothing to commit" in result.output:
            return {"commit": "nothing to commit"}
        if not result.success:
            return {"error": f"commit failed: {result.output}"}
        push = await svc.push(await self._auth_env(context))
        if not push.success:
            return {"error": f"push failed: {push.output}", "commit": result.output}
        return {"commit": result.output, "push": "pushed"}

    # --- File tools (general) -------------------------------------------

    @tool(
        description=(
            "Read a file from the workouts workspace. Use it on 'exercises.md' to find "
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
        root = self._root(context)
        if root is None:
            return "Error: no workspace linked to this chat."
        try:
            await self._ensure_pulled(context)
            full = self._resolve(root, path)
        except Exception as e:
            return f"Error reading {path}: {str(e)}"
        if not os.path.isfile(full):
            return f"File not found: {path}"
        try:
            with open(full, encoding="utf-8") as f:
                return f.read()
        except OSError as e:
            return f"Error reading {path}: {str(e)}"

    @tool(
        description=(
            "Create or update a file in the workouts workspace. The change is committed "
            "and pushed automatically. Use it to add a new exercise to exercises.md "
            "(read it first, append the name, write it back)."
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
    async def write_file(
        self, path: str, content: str, message: str, context: ToolCallContext = None
    ) -> str:
        root = self._root(context)
        if root is None:
            return "Error: no workspace linked to this chat."
        try:
            await self._ensure_pulled(context)
            full = self._resolve(root, path)
        except Exception as e:
            return f"Error writing {path}: {str(e)}"
        try:
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError as e:
            return f"Error writing {path}: {str(e)}"
        status = await self._commit_and_push(context, message)
        if "error" in status:
            return f"Saved: {path}, but {status['error']}"
        return f"Saved and pushed: {path}"

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
        root = self._root(context)
        if root is None:
            return json.dumps({"error": "No workspace linked to this chat."})
        await self._ensure_pulled(context)
        session = self._load_session(context.chat_id)
        if session is None:
            date = datetime.date.today().isoformat()
            session = {"date": date, "sets": []}
            await self._name_chat(context, f"Workout {date}")

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
            "commit and push, and close the session. Returns the file path and content."
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
