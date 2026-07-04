"""OpenCode bridge tool server.

Delegates coding work to a remote ``opencode serve`` instance.
Each mikoshi workspace is mounted into the opencode container and targeted
per-session, so one opencode server serves every workspace. A mikoshi chat
maps 1:1 to an opencode session, persisted on disk at
``<data_dir>/tool_storage/opencode/sessions.json``.

- ``OPENCODE_WORKSPACES_ROOT``  container path workspaces are mounted at
                                (default ``/home/coder/workspaces``)
- ``OPENCODE_PROVIDER_ID``      opencode provider to pin for delegated tasks
                                (e.g. ``zai-coding-plan``); requires ``OPENCODE_MODEL_ID``
- ``OPENCODE_MODEL_ID``         model id to pin (e.g. ``glm-5.2``); requires
                                ``OPENCODE_PROVIDER_ID``. If both are unset, opencode's
                                server default is used.
"""

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, Optional

import httpx

from mikoshi.tools.context import ToolCallContext
from mikoshi.tools.toolset_handler import ToolSetHandler, tool

logger = logging.getLogger(__name__)

# Assistant message finish reasons that mean the model emitted tool calls and
# the agent loop will continue with another step (i.e. the turn is NOT done).
# Anything else that is set ("stop", "length", "error", "stopped",
# "content_filter", ...) means the turn is complete.
_LOOP_FINISH = {"tool", "tool-calls"}


class OpencodeTools(ToolSetHandler):
    """Bridge to a remote ``opencode serve`` instance (v2 API)."""

    server_name = "opencode"

    def __init__(self):
        super().__init__()
        self._base_url = "http://localhost:4096"
        self._username = "opencode"
        self._password = ""
        self._workspaces_root = os.getenv(
            "OPENCODE_WORKSPACES_ROOT", "/home/coder/workspaces"
        ).rstrip("/")
        self._task_timeout = 900.0
        self._poll_interval = 1.0
        self._provider_id = os.getenv("OPENCODE_PROVIDER_ID", "")
        self._model_id = os.getenv("OPENCODE_MODEL_ID", "")
        self._client: Optional[httpx.AsyncClient] = None

    async def initialize(self) -> None:
        await super().initialize()
        auth = (self._username, self._password) if self._password else None
        # No read timeout: a delegated task can run for many minutes.
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            auth=auth,
            timeout=httpx.Timeout(None, connect=10.0),
        )
        logger.info("OpencodeTools pointing at %s", self._base_url)

    async def cleanup(self) -> None:
        if self._client:
            await self._client.aclose()

    def _directory_for(self, context: ToolCallContext) -> Optional[str]:
        ws = context.workspace
        if not ws:
            return None
        return f"{self._workspaces_root}/{ws.workspace_id}"

    def _sessions_path(self) -> str:
        return os.path.join(self.get_persistent_storage(), "sessions.json")

    def _load_sessions(self) -> Dict[str, str]:
        try:
            with open(self._sessions_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_sessions(self, sessions: Dict[str, str]) -> None:
        path = self._sessions_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sessions, f, indent=2)

    async def _ensure_session(self, context: ToolCallContext) -> str:
        sessions = self._load_sessions()
        chat_id = context.chat_id
        if chat_id in sessions:
            return sessions[chat_id]

        directory = self._directory_for(context)
        if not directory:
            raise RuntimeError("no workspace linked to this chat")

        body: Dict[str, Any] = {"location": {"directory": directory}}
        if self._provider_id and self._model_id:
            body["model"] = {"providerID": self._provider_id, "id": self._model_id}
        resp = await self._client.post("/api/session", json=body)
        resp.raise_for_status()
        session_id = resp.json()["data"]["id"]
        sessions[chat_id] = session_id
        self._save_sessions(sessions)
        logger.info(
            "created opencode session %s for chat %s in %s",
            session_id,
            chat_id,
            directory,
        )
        return session_id

    @tool(
        description=(
            "Delegate a coding task to the opencode coding agent running in the code-server "
            "container. opencode works directly in the current workspace's files (the same files "
            "you see via the workspace__ tools). Use this for any code change, refactor, debugging, "
            "or multi-file edit. Pass a clear, self-contained instruction describing what to do. "
            "Blocks until opencode finishes, then returns its final answer. Review the actual "
            "changes with workspace__git_status and workspace__git_diff."
        ),
        parameters={
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The coding task for opencode to perform in the workspace.",
                }
            },
            "required": ["prompt"],
        },
    )
    async def delegate(self, prompt: str, context: ToolCallContext) -> Any:
        if not context.workspace:
            return "Error: no workspace linked to this chat. Open or create a workspace first."
        if not self._client:
            return "Error: opencode client not initialized."

        try:
            session_id = await self._ensure_session(context)
        except Exception as e:
            logger.error("opencode session create failed: %s", e, exc_info=True)
            return f"Error: cannot create opencode session ({self._base_url}): {e}"

        # The v2 `/prompt` endpoint admits the prompt and returns immediately; it
        # does NOT block on the reply, and `/wait` is unavailable on this server
        # version. `timeCreated` marks this turn so the poller can ignore messages
        # produced by earlier turns on the same session.
        try:
            resp = await self._client.post(
                f"/api/session/{session_id}/prompt",
                json={"prompt": {"text": prompt}},
            )
            resp.raise_for_status()
            prompt_data = (resp.json() or {}).get("data") or {}
        except httpx.HTTPError as e:
            logger.error("opencode prompt rejected: %s", e, exc_info=True)
            return f"Error: opencode task rejected (session {session_id}): {e}."

        reply = await self._wait_for_completion(
            session_id, prompt_data.get("timeCreated") or 0
        )
        if reply is None:
            return (
                f"Error: opencode did not finish within {int(self._task_timeout)}s "
                f"(session {session_id}). The task may still be running in the "
                f"background; check workspace__git_status shortly."
            )
        return _message_text(reply) or "opencode completed but returned no text output."

    async def _wait_for_completion(
        self, session_id: str, user_created: int
    ) -> Optional[Dict[str, Any]]:
        """Poll ``GET /api/session/:id/message`` until the assistant turn that
        began at ``user_created`` reaches a terminal finish.

        The v2 API is asynchronous: ``/prompt`` returns as soon as the prompt is
        admitted and there is no blocking wait endpoint, so we poll. A turn may
        span several agent steps (tool calls); each in-flight step's message
        carries a tool-call finish (``"tool-calls"``) while the loop continues, so
        only a non-tool finish (``stop``/``error``/``stopped``/``length``/...) is
        treated as done. Messages are returned newest-first, and only messages
        newer than ``user_created`` (i.e. this turn's) are considered, which
        avoids mistaking a previous turn's reply for the current one.
        """
        deadline = time.monotonic() + self._task_timeout
        while time.monotonic() < deadline:
            try:
                resp = await self._client.get(
                    f"/api/session/{session_id}/message",
                    params={"order": "desc", "limit": 32},
                )
                resp.raise_for_status()
                messages = (resp.json() or {}).get("data") or []
            except httpx.HTTPError as e:
                logger.warning("opencode message poll failed: %s", e)
                await asyncio.sleep(self._poll_interval)
                continue

            for msg in messages:
                created = (msg.get("time") or {}).get("created")
                # Newest-first: once we reach this turn's user message (or
                # anything older), there is no newer assistant reply yet.
                if created is None or created <= user_created:
                    break
                if msg.get("type") == "assistant":
                    finish = msg.get("finish")
                    if finish is not None and finish not in _LOOP_FINISH:
                        return msg
                    # Newest reply of this turn is still generating (or mid
                    # tool-loop); wait and poll again.
                    break

            await asyncio.sleep(self._poll_interval)

        logger.warning(
            "opencode turn timed out after %ss (session %s)",
            int(self._task_timeout),
            session_id,
        )
        return None


def _message_text(msg: Dict[str, Any]) -> str:
    """Pull the text (or error) out of a completed assistant message."""
    err = msg.get("error")
    if err:
        detail = err.get("message") if isinstance(err, dict) else str(err)
        return f"opencode error: {detail}"
    chunks = [
        p.get("text", "")
        for p in (msg.get("content") or [])
        if isinstance(p, dict) and p.get("type") == "text" and p.get("text")
    ]
    return "\n".join(chunks).strip()
