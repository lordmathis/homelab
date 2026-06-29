import logging
import threading

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

from reachy_mini.utils import create_head_pose

from voice_assistant.expressions import EXPRESSIONS

logger = logging.getLogger(__name__)

BUILTIN_SOUNDS = ["wake_up", "go_sleep", "confused1", "impatient1", "dance1", "count"]


class ConversationState:
    """Shared, thread-safe-ish holder for the current conversation phase."""

    def __init__(self) -> None:
        self.current = "idle"
        self.robot_connected = False


class ExpressionRequest(BaseModel):
    name: str


class LookAtRequest(BaseModel):
    yaw: float = 0.0
    pitch: float = 0.0
    duration: float = 1.0


class DurationRequest(BaseModel):
    duration: float = 1.0


class SoundRequest(BaseModel):
    name: str


def create_robot_app(reachy_mini, expression_runner, state: ConversationState) -> FastAPI:
    app = FastAPI(title="Reachy Robot Control API")

    @app.post("/api/expression")
    def expression(req: ExpressionRequest):
        err = expression_runner.play(req.name)
        if err:
            return {"success": False, "error": err}
        return {"success": True}

    @app.post("/api/look_at")
    def look_at(req: LookAtRequest):
        try:
            reachy_mini.goto_target(
                head=create_head_pose(yaw=req.yaw, pitch=req.pitch),
                duration=req.duration,
            )
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.post("/api/reset_pose")
    def reset_pose(req: DurationRequest):
        try:
            reachy_mini.goto_target(
                head=create_head_pose(),
                antennas=[0.0, 0.0],
                duration=req.duration,
            )
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.post("/api/play_sound")
    def play_sound(req: SoundRequest):
        try:
            reachy_mini.media.play_sound(req.name)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.post("/api/wake_up")
    def wake_up():
        try:
            reachy_mini.wake_up()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.post("/api/go_to_sleep")
    def go_to_sleep():
        try:
            reachy_mini.goto_sleep()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.get("/api/status")
    def status():
        return {"state": state.current, "robot_connected": state.robot_connected}

    @app.get("/api/available_expressions")
    def available():
        return {
            "expressions": sorted(EXPRESSIONS.keys()),
            "sounds": BUILTIN_SOUNDS,
        }

    return app


def start_robot_api(
    reachy_mini,
    expression_runner,
    state: ConversationState,
    host: str = "0.0.0.0",
    port: int = 8050,
) -> threading.Thread:
    app = create_robot_app(reachy_mini, expression_runner, state)
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    logger.info("Robot control API on http://%s:%s", host, port)
    return t
