"""Reachy robot control tool server.

Calls the reachy_app REST API (default http://host.docker.internal:8050) to
drive the robot's body — expressions, gaze, sounds, pose.
"""

import logging
import os
from typing import Any, Dict

import httpx

from mikoshi.tools.toolset_handler import ToolSetHandler, tool

logger = logging.getLogger(__name__)


class ReachyTools(ToolSetHandler):
    """Control the Reachy Mini robot via the reachy_app REST API."""

    server_name = "reachy"

    def __init__(self):
        super().__init__()
        self._base_url = os.getenv(
            "REACHY_API_URL", "http://localhost:8050"
        ).rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def initialize(self):
        await super().initialize()
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=15.0)
        logger.info("ReachyTools pointing at %s", self._base_url)

    async def cleanup(self):
        if self._client:
            await self._client.aclose()

    async def _post(self, path: str, payload: dict | None = None) -> Dict[str, Any]:
        if not self._client:
            return {"success": False, "error": "Reachy client not initialized"}
        try:
            resp = await self._client.post(path, json=payload or {})
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error("Reachy API POST %s failed: %s", path, e)
            return {"success": False, "error": f"Reachy API unreachable: {e}"}

    async def _get(self, path: str) -> Any:
        if not self._client:
            return {"success": False, "error": "Reachy client not initialized"}
        try:
            resp = await self._client.get(path)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error("Reachy API GET %s failed: %s", path, e)
            return {"success": False, "error": f"Reachy API unreachable: {e}"}

    @tool(
        description=(
            "Play a predefined expression on the Reachy robot to react physically during "
            "conversation — match your words with body language. Call reachy__list_expressions "
            "first if unsure which names are available. Common: happy, sad, confused, thinking, "
            "nod, surprised, greet, listen, reset."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Expression name (e.g. happy, confused, nod, greet).",
                }
            },
            "required": ["name"],
        },
    )
    async def express(self, name: str) -> Dict[str, Any]:
        return await self._post("/api/expression", {"name": name})

    @tool(
        description=(
            "Point the Reachy robot's head in a direction to gaze around naturally while "
            "talking or thinking. yaw and pitch are in degrees."
        ),
        parameters={
            "type": "object",
            "properties": {
                "yaw": {
                    "type": "number",
                    "description": "Left/right head turn in degrees.",
                },
                "pitch": {
                    "type": "number",
                    "description": "Up/down head tilt in degrees (negative looks up).",
                },
                "duration": {
                    "type": "number",
                    "description": "Movement duration in seconds.",
                    "default": 1.0,
                },
            },
            "required": ["yaw", "pitch"],
        },
    )
    async def look_at(
        self, yaw: float, pitch: float, duration: float = 1.0
    ) -> Dict[str, Any]:
        return await self._post(
            "/api/look_at", {"yaw": yaw, "pitch": pitch, "duration": duration}
        )

    @tool(
        description="Return the Reachy robot to its neutral pose (head centered, antennas flat).",
        parameters={
            "type": "object",
            "properties": {
                "duration": {
                    "type": "number",
                    "description": "Movement duration in seconds.",
                    "default": 1.0,
                }
            },
            "required": [],
        },
    )
    async def reset_pose(self, duration: float = 1.0) -> Dict[str, Any]:
        return await self._post("/api/reset_pose", {"duration": duration})

    @tool(
        description=(
            "Play a built-in sound on the Reachy robot. Available: wake_up, go_sleep, "
            "confused1, impatient1, dance1, count."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Built-in sound name."}
            },
            "required": ["name"],
        },
    )
    async def play_sound(self, name: str) -> Dict[str, Any]:
        return await self._post("/api/play_sound", {"name": name})

    @tool(
        description="Wake the Reachy robot up — it goes to its initial pose and plays its wake-up emote.",
        parameters={"type": "object", "properties": {}, "required": []},
    )
    async def wake_up(self) -> Dict[str, Any]:
        return await self._post("/api/wake_up")

    @tool(
        description="Put the Reachy robot to sleep — it moves to its sleep pose.",
        parameters={"type": "object", "properties": {}, "required": []},
    )
    async def go_to_sleep(self) -> Dict[str, Any]:
        return await self._post("/api/go_to_sleep")

    @tool(
        description=(
            "List the expressions and sounds available on the Reachy robot. Call this if "
            "unsure what to pass to reachy__express or reachy__play_sound."
        ),
        parameters={"type": "object", "properties": {}, "required": []},
    )
    async def list_expressions(self) -> Any:
        return await self._get("/api/available_expressions")

    @tool(
        description=(
            "Get the Reachy robot's current state (idle/listening/processing/responding) "
            "and whether it is connected."
        ),
        parameters={"type": "object", "properties": {}, "required": []},
    )
    async def get_status(self) -> Any:
        return await self._get("/api/status")
