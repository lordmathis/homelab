import threading
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from reachy_mini.utils import create_head_pose


@dataclass
class Step:
    head: np.ndarray | None = None
    antennas: list[float] | None = None
    duration: float = 0.5


@dataclass
class Expression:
    name: str
    steps: list[Step]
    blocking: bool = False


EXPRESSIONS: dict[str, Expression] = {
    "greet": Expression(
        name="greet",
        steps=[
            Step(head=create_head_pose(pitch=-10), antennas=[0.3, -0.3], duration=0.3),
            Step(head=create_head_pose(pitch=-10), antennas=[-0.5, 0.5], duration=0.2),
            Step(head=create_head_pose(pitch=-10), antennas=[0.5, -0.5], duration=0.2),
            Step(head=create_head_pose(pitch=-5), antennas=[0.0, 0.0], duration=0.3),
        ],
    ),
    "listen": Expression(
        name="listen",
        steps=[
            Step(head=create_head_pose(pitch=-5, yaw=-5), antennas=[0.2, -0.2], duration=0.3),
            Step(head=create_head_pose(pitch=-8, yaw=5), antennas=[0.3, -0.3], duration=0.4),
            Step(head=create_head_pose(pitch=-5), antennas=[0.15, -0.15], duration=0.3),
        ],
    ),
    "happy": Expression(
        name="happy",
        steps=[
            Step(head=create_head_pose(pitch=-12), antennas=[0.5, -0.5], duration=0.3),
            Step(head=create_head_pose(pitch=-8), antennas=[-0.5, 0.5], duration=0.2),
            Step(head=create_head_pose(pitch=-12), antennas=[0.5, -0.5], duration=0.2),
            Step(head=create_head_pose(), antennas=[0.0, 0.0], duration=0.4),
        ],
    ),
    "thinking": Expression(
        name="thinking",
        steps=[
            Step(head=create_head_pose(pitch=-8, yaw=8), antennas=[0.1, 0.1], duration=0.5),
            Step(head=create_head_pose(pitch=-10, yaw=-5), antennas=[-0.1, -0.1], duration=0.6),
            Step(head=create_head_pose(pitch=-5, yaw=0), antennas=[0.0, 0.0], duration=0.4),
        ],
    ),
    "nod": Expression(
        name="nod",
        steps=[
            Step(head=create_head_pose(pitch=8), duration=0.2),
            Step(head=create_head_pose(pitch=-5), duration=0.2),
            Step(head=create_head_pose(pitch=5), duration=0.15),
            Step(head=create_head_pose(), duration=0.2),
        ],
    ),
    "confused": Expression(
        name="confused",
        steps=[
            Step(head=create_head_pose(roll=10, pitch=-5), antennas=[0.0, 0.4], duration=0.3),
            Step(head=create_head_pose(roll=-5, pitch=-8), antennas=[0.3, 0.0], duration=0.3),
            Step(head=create_head_pose(roll=5), antennas=[0.0, 0.2], duration=0.2),
            Step(head=create_head_pose(), antennas=[0.0, 0.0], duration=0.3),
        ],
    ),
    "surprised": Expression(
        name="surprised",
        steps=[
            Step(head=create_head_pose(pitch=-15), antennas=[0.6, -0.6], duration=0.25),
            Step(head=create_head_pose(pitch=-12), antennas=[-0.3, 0.3], duration=0.3),
            Step(head=create_head_pose(), antennas=[0.0, 0.0], duration=0.4),
        ],
    ),
    "reset": Expression(
        name="reset",
        steps=[
            Step(head=create_head_pose(), antennas=[0.0, 0.0], duration=0.5),
        ],
    ),
}


class ExpressionRunner:
    def __init__(self, reachy_mini):
        self._reachy = reachy_mini
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def play(self, name: str, on_done: Callable | None = None):
        expr = EXPRESSIONS.get(name)
        if expr is None:
            return f"Unknown expression: {name}"

        with self._lock:
            if self._thread and self._thread.is_alive():
                self._reachy.cancel_move()

            self._thread = threading.Thread(
                target=self._run_expression,
                args=(expr, on_done),
                daemon=True,
            )
            self._thread.start()

        return None

    def _run_expression(self, expr: Expression, on_done: Callable | None = None):
        try:
            for i, step in enumerate(expr.steps):
                print(f"[expression] {expr.name} step {i+1}/{len(expr.steps)}")
                self._reachy.goto_target(
                    head=step.head,
                    antennas=step.antennas,
                    duration=step.duration,
                )
            print(f"[expression] {expr.name} done")
            if on_done:
                on_done()
        except Exception as e:
            print(f"[expression] ERROR in {expr.name}: {e}")
