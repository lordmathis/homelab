import logging
from typing import List

from mikoshi.tools.context import ToolCallContext
from mikoshi.tools.toolset_handler import ToolSetHandler, tool

logger = logging.getLogger(__name__)

WORKER_AGENT = "batch_worker"

MAP_DESCRIPTION = (
    "Run a worker sub-agent over a list of inputs, one input at a time. "
    "Each input is processed independently by a fresh worker agent that has "
    "web and workspace tools.\n"
    "- `instructions` must be complete and self-contained for ONE input; "
    "they are applied identically to every input in the list.\n"
    "- The worker knows nothing about this conversation: include file "
    "paths, formats, and the exact expected output in the instructions.\n"
    "- Instruct workers to report briefly (e.g. one line per input); their "
    "replies are returned verbatim, one per input.\n"
    "- Workers see the current workspace state, so instruct them to skip "
    "inputs that are already done if the batch may be re-run.\n"
    "Use for repetitive per-item work that the chat model handles poorly: "
    "extracting info from many URLs, tagging or renaming many files, etc."
)

MAP_PARAMETERS = {
    "type": "object",
    "properties": {
        "inputs": {
            "type": "array",
            "items": {"type": "string"},
            "description": "One entry per item to process (URL, file path, name, ...).",
        },
        "instructions": {
            "type": "string",
            "description": "Complete instructions for processing a single input.",
        },
    },
    "required": ["inputs", "instructions"],
}


class BatchTool(ToolSetHandler):
    server_name = "batch"

    @tool(
        description=MAP_DESCRIPTION,
        parameters=MAP_PARAMETERS,
        require_approval=True,
    )
    async def map(
        self, inputs: List[str], instructions: str, context: ToolCallContext
    ) -> str:
        if not inputs:
            return "Error: 'inputs' must be a non-empty list."

        logger.info(
            "chat_id=%s batch starting: %d inputs", context.chat_id, len(inputs)
        )

        lines = []
        failures = 0
        for i, item in enumerate(inputs, 1):
            task = f"{instructions}\n\nInput: {item}"
            result = str(
                await self.call_other_tool(
                    "subagents__delegate",
                    {"agent": WORKER_AGENT, "task": task},
                    context,
                )
            )
            # delegate returns "Error: ..." strings instead of raising
            if result.startswith("Error"):
                failures += 1
            lines.append(f"{i}. {item}\n   {result}")
            logger.info("chat_id=%s batch item %d/%d done", context.chat_id, i, len(inputs))

        logger.info(
            "chat_id=%s batch finished: %d inputs, %d failed",
            context.chat_id,
            len(inputs),
            failures,
        )
        summary = f"Processed {len(inputs)} inputs, {failures} failed."
        return summary + "\n\n" + "\n".join(lines)
