import json
import logging
import random
from datetime import date
from typing import Any, Dict, List, Optional, Union

from mikoshi.tools.context import ToolCallContext
from mikoshi.tools.toolset_handler import ToolSetHandler, tool

logger = logging.getLogger(__name__)

REPO_OWNER = "Mathis"
NOTES_REPO = "Notes"
DEFAULT_BRANCH = "main"

NOTES_PATH = "🥨 German"
INDEX_FILEPATH = "🥨 German/_review_index.json"
MAX_GRADE = 3
NEVER_PRACTICED_WEIGHT = 10000
GRADE_DECAY_DAYS = 7  # one grade level ≈ a week of recency


def _parse_index(raw: Any) -> Dict[str, dict]:
    """Parse the review index JSON. Returns {} on any failure (empty,
    missing, malformed, non-dict, or the notes tool's error strings)."""
    if not isinstance(raw, str):
        return {}
    raw = raw.strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Review index is malformed JSON, treating as empty")
        return {}
    if not isinstance(parsed, dict):
        logger.warning("Review index is not a JSON object, treating as empty")
        return {}
    return parsed


def _compute_weight(entry: Optional[dict], today: date) -> float:
    """Neglect/weakness weight for a note. Never-practiced notes get the
    large constant; otherwise recency plus a penalty inversely proportional to
    the last grade. Weights are always >= 1."""
    if not entry:
        return float(NEVER_PRACTICED_WEIGHT)
    days = (today - date.fromisoformat(entry["last_practiced"])).days
    return days + (MAX_GRADE - entry["last_grade"]) * GRADE_DECAY_DAYS + 1


def _weighted_sample(
    items: List[str], weights: List[float], k: int
) -> List[str]:
    """Weighted random sample without replacement (Efraimidis-Spirakis key).
    Returns at most min(k, len(items)) distinct items; k >= len returns all."""
    items = list(items)
    n = len(items)
    if n == 0 or k <= 0:
        return []
    k = min(k, n)
    keyed = [
        (random.random() ** (1 / w), item)
        for w, item in zip(weights, items)
    ]
    keyed.sort(key=lambda t: t[0], reverse=True)
    return [item for _, item in keyed[:k]]


class QuizTool(ToolSetHandler):
    server_name = "quiz"

    def __init__(self):
        super().__init__()

    @tool(
        description=(
            "Select a weighted-random set of German concept notes for active "
            "recall review. Notes that were never practiced, practiced long "
            "ago, or scored poorly are favored. Returns each note's full "
            "content plus its last practice date and grade, so the tutor can "
            "ask questions without extra lookups."
        ),
        parameters={
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "description": "Number of notes to select (default 3)",
                    "default": 3,
                }
            },
        },
    )
    async def get_notes(
        self, count: int = 3, context: ToolCallContext = None
    ) -> Union[str, Dict[str, Any]]:
        try:
            entries = await self.call_other_tool(
                "gitea__get_dir_contents",
                {
                    "owner": REPO_OWNER,
                    "repo": NOTES_REPO,
                    "path": NOTES_PATH,
                    "ref": DEFAULT_BRANCH,
                },
                context,
            )

            names = [
                e["name"]
                for e in (entries or [])
                if e.get("type") == "file"
                and e.get("name", "").endswith(".md")
                and not e.get("name", "").startswith("_")
            ]
            total_notes = len(names)
            if total_notes == 0:
                return {"status": "success", "notes": [], "total_notes": 0}

            raw_index = await self.call_other_tool(
                "notes__get_note",
                {"filepath": INDEX_FILEPATH},
                context,
            )
            index = _parse_index(raw_index)

            today = date.today()
            weights = [
                _compute_weight(index.get(name), today) for name in names
            ]

            selected = _weighted_sample(names, weights, count)

            notes_out: List[Dict[str, Any]] = []
            for name in selected:
                content = await self.call_other_tool(
                    "notes__get_note",
                    {"filepath": f"{NOTES_PATH}/{name}"},
                    context,
                )
                entry = index.get(name)
                notes_out.append(
                    {
                        "filepath": name,
                        "content": content,
                        "last_practiced": (
                            entry.get("last_practiced")
                            if entry is not None
                            else None
                        ),
                        "last_grade": (
                            entry.get("last_grade")
                            if entry is not None
                            else None
                        ),
                    }
                )

            return {
                "status": "success",
                "notes": notes_out,
                "total_notes": total_notes,
            }

        except Exception as e:
            logger.error(f"Error selecting quiz notes: {e}", exc_info=True)
            return f"Error selecting quiz notes: {e}"

    @tool(
        description=(
            "Record a quiz grade (0-3) for a note, stamping today's date. "
            "Persists to the git-tracked review index so future selections "
            "prioritize weakly-recalled and long-unseen notes. `filepath` is "
            "the bare filename as returned by quiz__get_notes."
        ),
        parameters={
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": (
                        "Bare filename of the note (e.g. "
                        "'adjektivendungen.md'), as returned by "
                        "quiz__get_notes"
                    ),
                },
                "grade": {
                    "type": "integer",
                    "description": (
                        "0 = forgot/wrong, 1 = hard, 2 = good, 3 = easy"
                    ),
                },
            },
            "required": ["filepath", "grade"],
        },
    )
    async def record_result(
        self,
        filepath: str,
        grade: int,
        context: ToolCallContext = None,
    ) -> Union[str, Dict[str, Any]]:
        try:
            if not isinstance(filepath, str) or not filepath.strip():
                return "Invalid filepath: must be a non-empty string"
            if (
                not isinstance(grade, int)
                or isinstance(grade, bool)
                or grade < 0
                or grade > MAX_GRADE
            ):
                return (
                    f"Invalid grade {grade!r}: must be an integer between 0 "
                    f"and {MAX_GRADE}"
                )

            raw_index = await self.call_other_tool(
                "notes__get_note",
                {"filepath": INDEX_FILEPATH},
                context,
            )
            index = _parse_index(raw_index)

            today_iso = date.today().isoformat()
            index[filepath] = {"last_practiced": today_iso, "last_grade": grade}

            serialized = json.dumps(index, indent=2, ensure_ascii=False)
            update_result = await self.call_other_tool(
                "notes__update_note",
                {
                    "filepath": INDEX_FILEPATH,
                    "content": serialized,
                    "commit_message": f"Quiz: record {filepath} grade {grade}",
                },
                context,
            )

            if isinstance(update_result, str) and update_result.startswith("Error"):
                return f"Failed to write review index: {update_result}"

            return {
                "status": "success",
                "filepath": filepath,
                "last_practiced": today_iso,
                "last_grade": grade,
            }

        except Exception as e:
            logger.error(
                f"Error recording quiz result for '{filepath}': {e}",
                exc_info=True,
            )
            return f"Error recording quiz result: {e}"
