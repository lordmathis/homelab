"""OpenCode bridge tool server.

Delegates coding work to a remote ``opencode serve`` instance (v2 HTTP API).
Each mikoshi workspace is mounted into the opencode container and targeted
per-session, so one opencode server serves every workspace. A mikoshi chat
maps 1:1 to an opencode session, persisted on disk at
``<data_dir>/tool_storage/opencode/sessions.json``.

Requires opencode with the v2 (``/api/...``) HTTP API and per-request location
targeting. Configure via environment variables:

- ``OPENCODE_SERVE_URL``        default ``http://localhost:4096``
- ``OPENCODE_SERVER_PASSWORD``  basic-auth password (username defaults to ``opencode``)
- ``OPENCODE_WORKSPACES_ROOT``  container path workspaces are mounted at
                                (default ``/home/coder/workspaces``)
"""

import json
import logging
import os
from typing import Any, Dict, Optional

import httpx

from mikoshi.tools.context import ToolCallContext
from mikoshi.tools.toolset_handler import ToolSetHandler, tool

logger = logging.getLogger(__name__)


class OpencodeTools(ToolSetHandler):
    """Bridge to a remote ``opencode serve`` instance (v2 API)."""

    server_name = "opencode"

    def __init__(self):
        super().__init__()
        self._base_url = os.getenv("OPENCODE_SERVE_URL", "http://localhost:4096").rstrip("/")
        self._username = os.getenv("OPENCODE_SERVER_USERNAME", "opencode")
        self._password = os.getenv("OPENCODE_SERVER_PASSWORD", "")
        self._workspaces_root = os.getenv(
            "OPENCODE_WORKSPACES_ROOT", "/home/coder/workspaces"
        ).rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    async def initialize(self) -> None:
        await super().initialize()
        auth = (self._username, self._password) if self._password else None
        # No read timeout: `wait` blocks legitimately until the session is idle.
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

        try:
            resp = await self._client.post(
                f"/api/session/{session_id}/prompt", json={"prompt": {"text": prompt}}
            )
            resp.raise_for_status()
            await self._client.post(f"/api/session/{session_id}/wait")
        except httpx.HTTPError as e:
            logger.error("opencode prompt/wait failed: %s", e, exc_info=True)
            return f"Error: opencode task failed (session {session_id}): {e}."

        try:
            resp = await self._client.get(
                f"/api/session/{session_id}/message",
                params={"order": "desc", "limit": 20},
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            return f"Error: opencode finished but reading the response failed: {e}"

        return (
            _extract_assistant_text(resp.json())
            or "opencode completed but returned no text output."
        )


def _extract_assistant_text(payload: Any) -> str:
    """Pull the text of the latest assistant message from a v2 message list."""
    messages = (payload or {}).get("data") or []
    for msg in messages:
        if not isinstance(msg, dict) or msg.get("type") != "assistant":
            continue
        if msg.get("error"):
            err = msg["error"]
            detail = err.get("message") if isinstance(err, dict) else str(err)
            return f"opencode error: {detail}"
        chunks = [
            c.get("text", "")
            for c in (msg.get("content") or [])
            if isinstance(c, dict) and c.get("type") == "text" and c.get("text")
        ]
        text = "\n".join(chunks).strip()
        if text:
            return text
    return ""
