import json
import logging
from typing import Callable, Optional

import httpx

logger = logging.getLogger(__name__)


class MikoshiClient:
    """Client for the mikoshi chat API."""

    def __init__(
        self,
        base_url: str = "http://localhost:9002",
        agent_name: str = "Reachy",
        title: str = "Reachy Voice Session",
    ):
        self._base_url = base_url.rstrip("/")
        self._agent_name = agent_name
        self._title = title
        self._chat_id: Optional[str] = None

    @property
    def chat_id(self) -> Optional[str]:
        return self._chat_id

    def new_session(self) -> str:
        """Create a new chat session for this voice conversation."""
        resp = httpx.post(
            f"{self._base_url}/api/chats",
            json={
                "title": self._title,
                "config": {"model": self._agent_name},
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        self._chat_id = resp.json()["id"]
        logger.info("Created mikoshi chat %s (agent=%s)", self._chat_id, self._agent_name)
        return self._chat_id

    def send_message(
        self,
        message: str,
        on_message: Optional[Callable[[str], None]] = None,
        timeout: float = 300.0,
    ) -> None:
        """Send a user message, invoking ``on_message(text)`` for each assistant
        text reply as it streams in.

        A single agent turn may emit several assistant messages (e.g. an answer
        that also triggers a reachy expression, then a follow-up). Each one with
        non-empty content is delivered to ``on_message`` immediately, so the
        caller can TTS it right away — no message is skipped.
        """
        if not self._chat_id:
            raise RuntimeError("No active chat session — call new_session() first")

        with httpx.stream(
            "POST",
            f"{self._base_url}/api/chats/{self._chat_id}/messages",
            json={"message": message},
            timeout=timeout,
        ) as response:
            response.raise_for_status()
            event_type: Optional[str] = None
            for line in response.iter_lines():
                if not line:
                    continue
                if line.startswith("event:"):
                    event_type = line.split(":", 1)[1].strip()
                    continue
                if not line.startswith("data:"):
                    continue

                try:
                    event = json.loads(line[len("data:"):].strip())
                except json.JSONDecodeError:
                    continue

                etype = event.get("type") or event_type
                data = event.get("data", {}) or {}
                event_type = None

                if etype == "message" and data.get("role") == "assistant":
                    content = (data.get("content") or "").strip()
                    if content and on_message:
                        on_message(content)
                elif etype == "error":
                    err = data.get("message", "unknown error")
                    logger.error("Agent error: %s", err)
                elif etype == "done":
                    break

