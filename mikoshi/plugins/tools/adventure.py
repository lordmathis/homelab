"""Stateless dice tools for the single-player text adventure DM.

All randomness uses `secrets` so the model cannot fake or predict
rolls. Chance checks return only whether the effect triggered —
never the raw roll. Game state is the conversation itself.
"""

import logging
import secrets
from typing import Union

from mikoshi.tools.toolset_handler import ToolSetHandler, tool

logger = logging.getLogger(__name__)


def describe_roll(value: int) -> str:
    if value < 11:
        return "catastrophic failure"
    if value < 25:
        return "failure with a serious consequence"
    if value < 35:
        return "failure or costly partial success"
    if value < 50:
        return "mediocre success"
    if value < 65:
        return "adequate success"
    if value < 75:
        return "qualified success"
    if value < 90:
        return "resounding success"
    return "perfect success, extra benefits"


class AdventureTool(ToolSetHandler):
    server_name = "adventure"

    @tool(
        description=(
            "Roll the authoritative d100 (0-100) for an uncertain action. "
            "Returns the value plus its fixed interpretation band. The "
            "narration must honor the result. Never invent dice results."
        ),
        parameters={
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Short description of what is being rolled for, e.g. 'pick the lock'",
                }
            },
            "required": ["reason"],
        },
    )
    async def roll_dice(self, reason: str) -> Union[str, dict]:
        value = secrets.randbelow(101)
        result = describe_roll(value)
        entry = {"reason": reason, "value": value, "result": result}
        logger.info(f"Dice roll for '{reason}': {value} ({result})")
        return entry

    @tool(
        description=(
            "Roll the game's single private percentage rule. Pass the rule's "
            "exact chance_percent. At most once per round, never reroll. For "
            "'condition' cadence rules, first judge conservatively whether "
            "the player's action itself attempted or performed the trigger, "
            "and pass trigger_occurred accordingly. Returns whether the "
            "effect triggered — never a raw roll."
        ),
        parameters={
            "type": "object",
            "properties": {
                "chance_percent": {
                    "type": "integer",
                    "description": "The chance rule's whole percent, exactly as the player defined it",
                },
                "trigger_occurred": {
                    "type": "boolean",
                    "description": (
                        "For 'condition' rules: did the player's action "
                        "attempt or perform the trigger this round? Leave "
                        "unset for 'per_round' rules."
                    ),
                },
            },
            "required": ["chance_percent"],
        },
    )
    async def check_chance(
        self, chance_percent: int, trigger_occurred: bool = None
    ) -> Union[str, dict]:
        if (
            not isinstance(chance_percent, int)
            or isinstance(chance_percent, bool)
            or chance_percent < 0
            or chance_percent > 100
        ):
            return (
                f"Invalid chance_percent {chance_percent!r}: must be a whole "
                "number from 0 to 100."
            )

        if trigger_occurred is False:
            return {
                "triggered": False,
                "note": "The trigger did not occur this round. Do not apply the effect.",
            }

        roll = secrets.randbelow(100) + 1
        triggered = roll <= chance_percent
        logger.info(
            f"Chance check: roll {roll} vs {chance_percent}% -> triggered={triggered}"
        )
        return {"triggered": triggered}
