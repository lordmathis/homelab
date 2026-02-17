"""
Workout Toolset Plugin - Self-contained workout logging and tracking
"""

import logging
import os
import sqlite3
import uuid
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from agentkit.tools.toolset_handler import ToolSetHandler, tool

logger = logging.getLogger(__name__)


class WorkoutToolset(ToolSetHandler):
    """Standalone workout logging toolset plugin"""

    def __init__(self):
        super().__init__("workout")
        self.db_path: Optional[str] = None
        self.current_workout_id: Optional[str] = None

    async def initialize(self) -> None:
        """Initialize the toolset and database"""
        await super().initialize()

        # Get persistent storage directory
        workspace = self._tool_manager.get_persistent_storage(self.server_name)
        self.db_path = os.path.join(workspace, "workouts.db")

        # Initialize database schema
        self._init_db()
        logger.info(f"Workout database initialized at {self.db_path}")

    def _init_db(self) -> None:
        """Create database tables if they don't exist"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")

        # Create exercises registry table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS exercises (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                category TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_exercise_name ON exercises(name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_exercise_category ON exercises(category)")

        # Create workouts table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS workouts (
                id TEXT PRIMARY KEY,
                date TEXT NOT NULL,
                notes TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_workout_date ON workouts(date)")

        # Create workout_sets table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS workout_sets (
                id TEXT PRIMARY KEY,
                workout_id TEXT NOT NULL,
                exercise_id TEXT NOT NULL,
                set_number INTEGER NOT NULL,
                reps INTEGER NOT NULL,
                weight REAL,
                notes TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (workout_id) REFERENCES workouts(id) ON DELETE CASCADE,
                FOREIGN KEY (exercise_id) REFERENCES exercises(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_set_workout ON workout_sets(workout_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_set_exercise ON workout_sets(exercise_id)")

        # Create templates table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS templates (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_templates_active ON templates(active)")

        # Create template_exercises table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS template_exercises (
                id TEXT PRIMARY KEY,
                template_id TEXT NOT NULL,
                exercise_id TEXT NOT NULL,
                order_index INTEGER NOT NULL,
                target_sets INTEGER NOT NULL,
                target_reps_min INTEGER,
                target_reps_max INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY (template_id) REFERENCES templates(id) ON DELETE CASCADE,
                FOREIGN KEY (exercise_id) REFERENCES exercises(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_template_exercises_template ON template_exercises(template_id)")

        conn.commit()
        conn.close()

    def _get_conn(self) -> sqlite3.Connection:
        """Get a database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _normalize_name(self, name: str) -> str:
        return " ".join(name.strip().lower().split())

    def _find_or_create_exercise(self, name: str, category: Optional[str], conn: sqlite3.Connection) -> str:
        """Find an exercise by normalized name or create it. Returns exercise ID."""
        normalized = self._normalize_name(name)
        row = conn.execute(
            "SELECT id FROM exercises WHERE name = ?",
            (normalized,)
        ).fetchone()
        if row:
            return row["id"]

        exercise_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        conn.execute(
            "INSERT INTO exercises (id, name, display_name, category, created_at) VALUES (?, ?, ?, ?, ?)",
            (exercise_id, normalized, name.strip(), category, now)
        )
        return exercise_id

    def _get_logged_exercise_ids(self, workout_id: str, conn: sqlite3.Connection) -> List[str]:
        rows = conn.execute(
            "SELECT DISTINCT exercise_id FROM workout_sets WHERE workout_id = ?",
            (workout_id,)
        ).fetchall()
        return [r["exercise_id"] for r in rows]

    def _get_last_exercise_sets(self, exercise_id: str, exclude_workout_id: Optional[str], conn: sqlite3.Connection) -> Dict[str, Any]:
        last_workout = conn.execute(
            """
            SELECT w.id, w.date
            FROM workouts w
            JOIN workout_sets ws ON ws.workout_id = w.id
            WHERE ws.exercise_id = ?
              AND (? IS NULL OR w.id != ?)
            ORDER BY w.date DESC
            LIMIT 1
            """,
            (exercise_id, exclude_workout_id, exclude_workout_id)
        ).fetchone()

        if not last_workout:
            return {"workout_id": None, "date": None, "sets": []}

        sets = conn.execute(
            """
            SELECT set_number, reps, weight, notes
            FROM workout_sets
            WHERE workout_id = ? AND exercise_id = ?
            ORDER BY set_number
            """,
            (last_workout["id"], exercise_id)
        ).fetchall()

        return {
            "workout_id": last_workout["id"],
            "date": last_workout["date"],
            "sets": [
                {"set": s["set_number"], "reps": s["reps"], "weight": s["weight"], "notes": s["notes"]}
                for s in sets
            ]
        }

    def _get_template_exercises(self, template_id: str, conn: sqlite3.Connection) -> List[Dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT te.exercise_id, e.display_name, te.order_index, te.target_sets, te.target_reps_min, te.target_reps_max
            FROM template_exercises te
            JOIN exercises e ON e.id = te.exercise_id
            WHERE te.template_id = ?
            ORDER BY te.order_index
            """,
            (template_id,)
        ).fetchall()

        return [
            {
                "exercise_id": r["exercise_id"],
                "name": r["display_name"],
                "order": r["order_index"],
                "target_sets": r["target_sets"],
                "target_reps_min": r["target_reps_min"],
                "target_reps_max": r["target_reps_max"]
            }
            for r in rows
        ]

    def _compute_template_progress(self, template_id: str, workout_id: str, conn: sqlite3.Connection) -> Dict[str, Any]:
        template_exercises = self._get_template_exercises(template_id, conn)
        if not template_exercises:
            return {"completed": [], "remaining": [], "next": None}

        sets_done_by_exercise = conn.execute(
            """
            SELECT exercise_id, COUNT(id) AS sets_done
            FROM workout_sets
            WHERE workout_id = ?
            GROUP BY exercise_id
            """,
            (workout_id,)
        ).fetchall()

        sets_done_map = {r["exercise_id"]: r["sets_done"] for r in sets_done_by_exercise}

        completed = []
        remaining = []
        for ex in template_exercises:
            sets_done = sets_done_map.get(ex["exercise_id"], 0)
            sets_remaining = max(ex["target_sets"] - sets_done, 0)

            entry = {
                "exercise_id": ex["exercise_id"],
                "name": ex["name"],
                "order": ex["order"],
                "target_sets": ex["target_sets"],
                "target_reps_min": ex["target_reps_min"],
                "target_reps_max": ex["target_reps_max"],
                "sets_done": sets_done,
                "sets_remaining": sets_remaining
            }

            if sets_remaining == 0:
                completed.append(entry)
            else:
                remaining.append(entry)

        remaining_sorted = sorted(remaining, key=lambda x: x["order"])
        next_exercise = remaining_sorted[0] if remaining_sorted else None

        return {
            "completed": completed,
            "remaining": remaining_sorted,
            "next": next_exercise
        }

    def _get_next_set_number(self, workout_id: str, exercise_id: str, conn: sqlite3.Connection) -> int:
        row = conn.execute(
            "SELECT MAX(set_number) AS max_set FROM workout_sets WHERE workout_id = ? AND exercise_id = ?",
            (workout_id, exercise_id)
        ).fetchone()
        return (row["max_set"] or 0) + 1

    @tool(
        description="Search the exercise registry by name or category",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query to match against exercise names"
                },
                "category": {
                    "type": "string",
                    "description": "Filter by category (e.g. back, chest, legs, shoulders, arms, core)"
                }
            },
            "required": []
        }
    )
    async def search_exercises(self, query: Optional[str] = None, category: Optional[str] = None) -> Dict[str, Any]:
        """Search the exercise registry"""
        conn = self._get_conn()

        conditions = []
        params = []
        if query:
            conditions.append("name LIKE ?")
            params.append(f"%{self._normalize_name(query)}%")
        if category:
            conditions.append("lower(category) = ?")
            params.append(category.strip().lower())

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = conn.execute(
            f"SELECT id, display_name, category FROM exercises {where} ORDER BY display_name",
            params
        ).fetchall()

        conn.close()
        return {
            "status": "success",
            "count": len(rows),
            "exercises": [
                {"id": r["id"], "name": r["display_name"], "category": r["category"]}
                for r in rows
            ]
        }

    @tool(
        description="Register a new exercise in the exercise registry",
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Exercise name"
                },
                "category": {
                    "type": "string",
                    "description": "Category (e.g. back, chest, legs, shoulders, arms, core)"
                }
            },
            "required": ["name"]
        }
    )
    async def create_exercise(self, name: str, category: Optional[str] = None) -> Dict[str, Any]:
        """Register a new exercise"""
        normalized = self._normalize_name(name)
        if not normalized:
            raise ValueError("Exercise name cannot be empty")

        conn = self._get_conn()

        existing = conn.execute(
            "SELECT id, display_name, category FROM exercises WHERE name = ?",
            (normalized,)
        ).fetchone()
        if existing:
            conn.close()
            return {
                "status": "already_exists",
                "id": existing["id"],
                "name": existing["display_name"],
                "category": existing["category"]
            }

        exercise_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        conn.execute(
            "INSERT INTO exercises (id, name, display_name, category, created_at) VALUES (?, ?, ?, ?, ?)",
            (exercise_id, normalized, name.strip(), category, now)
        )
        conn.commit()
        conn.close()

        return {
            "status": "success",
            "id": exercise_id,
            "name": name.strip(),
            "category": category
        }

    @tool(
        description="Start a new workout session",
        parameters={
            "type": "object",
            "properties": {
                "notes": {
                    "type": "string",
                    "description": "Optional notes about the workout"
                }
            },
            "required": []
        }
    )
    async def start_workout(self, notes: Optional[str] = None) -> Dict[str, str]:
        """Start a new workout session"""
        self.current_workout_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()

        conn = self._get_conn()
        conn.execute(
            "INSERT INTO workouts (id, date, notes, created_at) VALUES (?, ?, ?, ?)",
            (self.current_workout_id, now, notes, now)
        )
        conn.commit()
        conn.close()

        return {
            "status": "success",
            "workout_id": self.current_workout_id,
            "message": "Started new workout session"
        }

    @tool(
        description="Create a workout template with exercises and target rep ranges",
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Template name"
                },
                "exercises": {
                    "type": "array",
                    "description": "Exercises in order with targets",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Exercise name (will be registered if new)"},
                            "category": {"type": "string", "description": "Exercise category"},
                            "order": {"type": "integer"},
                            "target_sets": {"type": "integer"},
                            "target_reps_min": {"type": "integer"},
                            "target_reps_max": {"type": "integer"}
                        },
                        "required": ["name"]
                    }
                }
            },
            "required": ["name", "exercises"]
        }
    )
    async def create_template(self, name: str, exercises: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create a workout template"""
        if not exercises:
            raise ValueError("Template exercises cannot be empty")

        template_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()

        conn = self._get_conn()
        conn.execute(
            "INSERT INTO templates (id, name, active, created_at) VALUES (?, ?, ?, ?)",
            (template_id, name, 1, now)
        )

        registered = []
        for idx, exercise in enumerate(exercises, 1):
            ex_name = exercise.get("name")
            if not ex_name:
                raise ValueError("Each template exercise must include a name")

            ex_category = exercise.get("category")
            exercise_id = self._find_or_create_exercise(ex_name, ex_category, conn)

            order_index = exercise.get("order", idx)
            target_sets = exercise.get("target_sets", 3)
            target_reps_min = exercise.get("target_reps_min")
            target_reps_max = exercise.get("target_reps_max")

            conn.execute(
                """
                INSERT INTO template_exercises
                    (id, template_id, exercise_id, order_index, target_sets, target_reps_min, target_reps_max, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), template_id, exercise_id, order_index, target_sets, target_reps_min, target_reps_max, now)
            )
            registered.append({"name": ex_name, "exercise_id": exercise_id})

        conn.commit()
        conn.close()

        return {
            "status": "success",
            "template_id": template_id,
            "name": name,
            "exercises": registered
        }

    @tool(
        description="List workout templates",
        parameters={
            "type": "object",
            "properties": {
                "include_exercises": {"type": "boolean", "description": "Include exercises list"},
                "active_only": {"type": "boolean", "description": "Only active templates"}
            },
            "required": []
        }
    )
    async def list_templates(self, include_exercises: bool = False, active_only: bool = True) -> Dict[str, Any]:
        """List workout templates"""
        conn = self._get_conn()

        if active_only:
            templates = conn.execute(
                "SELECT * FROM templates WHERE active = 1 ORDER BY created_at DESC"
            ).fetchall()
        else:
            templates = conn.execute(
                "SELECT * FROM templates ORDER BY created_at DESC"
            ).fetchall()

        result = []
        for t in templates:
            item = {
                "id": t["id"],
                "name": t["name"],
                "active": bool(t["active"]),
                "created_at": t["created_at"]
            }

            if include_exercises:
                item["exercises"] = self._get_template_exercises(t["id"], conn)

            result.append(item)

        conn.close()
        return {
            "status": "success",
            "count": len(result),
            "templates": result
        }

    @tool(
        description="Infer the most likely workout template from an exercise",
        parameters={
            "type": "object",
            "properties": {
                "exercise_id": {"type": "string", "description": "Exercise ID"},
                "workout_id": {"type": "string", "description": "Workout ID (uses current if not provided)"}
            },
            "required": ["exercise_id"]
        }
    )
    async def infer_template(self, exercise_id: str, workout_id: Optional[str] = None) -> Dict[str, Any]:
        """Infer the template based on exercise and current workout progress"""
        target_workout_id = workout_id or self.current_workout_id

        conn = self._get_conn()

        candidates = conn.execute(
            """
            SELECT DISTINCT t.id, t.name
            FROM templates t
            JOIN template_exercises te ON te.template_id = t.id
            WHERE t.active = 1 AND te.exercise_id = ?
            """,
            (exercise_id,)
        ).fetchall()

        if not candidates:
            conn.close()
            return {
                "status": "not_found",
                "message": "No active template contains this exercise"
            }

        if len(candidates) == 1:
            chosen = candidates[0]
            reason = "single_match"
        else:
            reason = "best_overlap"
            if target_workout_id:
                logged = set(self._get_logged_exercise_ids(target_workout_id, conn))
            else:
                logged = set()

            best_score = -1
            chosen = candidates[0]
            for cand in candidates:
                templ_ex = self._get_template_exercises(cand["id"], conn)
                templ_ids = {e["exercise_id"] for e in templ_ex}
                score = len(templ_ids.intersection(logged))
                if score > best_score:
                    best_score = score
                    chosen = cand

        progress = None
        if target_workout_id:
            progress = self._compute_template_progress(chosen["id"], target_workout_id, conn)

        last_perf = self._get_last_exercise_sets(exercise_id, target_workout_id, conn)

        conn.close()
        return {
            "status": "success",
            "template": {
                "id": chosen["id"],
                "name": chosen["name"]
            },
            "reason": reason,
            "progress": progress,
            "last_performance": last_perf
        }

    @tool(
        description="Get template progress for a workout",
        parameters={
            "type": "object",
            "properties": {
                "template_id": {"type": "string", "description": "Template ID"},
                "workout_id": {"type": "string", "description": "Workout ID (uses current if not provided)"}
            },
            "required": ["template_id"]
        }
    )
    async def get_template_progress(self, template_id: str, workout_id: Optional[str] = None) -> Dict[str, Any]:
        """Get template progress for a workout"""
        target_workout_id = workout_id or self.current_workout_id
        if not target_workout_id:
            raise ValueError("No workout specified.")

        conn = self._get_conn()
        progress = self._compute_template_progress(template_id, target_workout_id, conn)
        conn.close()

        return {
            "status": "success",
            "workout_id": target_workout_id,
            "template_id": template_id,
            "progress": progress
        }

    @tool(
        description="Get recent history for a specific exercise",
        parameters={
            "type": "object",
            "properties": {
                "exercise_id": {"type": "string", "description": "Exercise ID"},
                "limit": {"type": "integer", "description": "Number of recent workouts to include"}
            },
            "required": ["exercise_id"]
        }
    )
    async def get_exercise_history(self, exercise_id: str, limit: int = 3) -> Dict[str, Any]:
        """Get recent history for a specific exercise"""
        if limit <= 0:
            raise ValueError("Limit must be greater than 0")

        conn = self._get_conn()

        exercise = conn.execute(
            "SELECT display_name FROM exercises WHERE id = ?",
            (exercise_id,)
        ).fetchone()
        if not exercise:
            conn.close()
            raise ValueError(f"Exercise {exercise_id} not found")

        workouts = conn.execute(
            """
            SELECT DISTINCT w.id, w.date
            FROM workouts w
            JOIN workout_sets ws ON ws.workout_id = w.id
            WHERE ws.exercise_id = ?
            ORDER BY w.date DESC
            LIMIT ?
            """,
            (exercise_id, limit)
        ).fetchall()

        history = []
        for w in workouts:
            sets = conn.execute(
                """
                SELECT set_number, reps, weight, notes
                FROM workout_sets
                WHERE workout_id = ? AND exercise_id = ?
                ORDER BY set_number
                """,
                (w["id"], exercise_id)
            ).fetchall()

            history.append({
                "workout_id": w["id"],
                "date": w["date"],
                "sets": [
                    {"set": s["set_number"], "reps": s["reps"], "weight": s["weight"], "notes": s["notes"]}
                    for s in sets
                ]
            })

        conn.close()
        return {
            "status": "success",
            "exercise_id": exercise_id,
            "exercise_name": exercise["display_name"],
            "count": len(history),
            "history": history
        }

    @tool(
        description="Log an exercise with sets, reps, and optional weight",
        parameters={
            "type": "object",
            "properties": {
                "exercise_id": {
                    "type": "string",
                    "description": "Exercise ID from the exercise registry"
                },
                "sets_data": {
                    "type": "array",
                    "description": "Array of sets with reps and optional weight",
                    "items": {
                        "type": "object",
                        "properties": {
                            "reps": {"type": "integer"},
                            "weight": {"type": "number"},
                            "notes": {"type": "string"}
                        },
                        "required": ["reps"]
                    }
                },
                "workout_id": {
                    "type": "string",
                    "description": "Workout ID (uses current if not provided)"
                },
                "template_id": {
                    "type": "string",
                    "description": "Template ID (optional, used for guidance)"
                },
                "include_guidance": {
                    "type": "boolean",
                    "description": "Include template progress and last performance guidance"
                }
            },
            "required": ["exercise_id", "sets_data"]
        }
    )
    async def log_exercise(self, exercise_id: str, sets_data: List[Dict[str, Any]],
                          workout_id: Optional[str] = None, template_id: Optional[str] = None,
                          include_guidance: bool = False) -> Dict[str, Any]:
        """Log an exercise with multiple sets"""
        target_workout_id = workout_id or self.current_workout_id
        if not target_workout_id:
            raise ValueError("No active workout. Start a workout first with start_workout.")

        conn = self._get_conn()

        # Verify exercise exists
        exercise = conn.execute(
            "SELECT display_name FROM exercises WHERE id = ?",
            (exercise_id,)
        ).fetchone()
        if not exercise:
            conn.close()
            raise ValueError(f"Exercise {exercise_id} not found. Use search_exercises or create_exercise first.")

        # Get next set number for incremental logging
        start_set = self._get_next_set_number(target_workout_id, exercise_id, conn)

        for idx, set_data in enumerate(sets_data):
            reps = set_data.get("reps")
            weight = set_data.get("weight")
            notes = set_data.get("notes")

            if not isinstance(reps, int) or reps <= 0:
                raise ValueError(f"Invalid reps: {reps}")

            set_id = str(uuid.uuid4())
            now = datetime.now(UTC).isoformat()
            conn.execute(
                "INSERT INTO workout_sets (id, workout_id, exercise_id, set_number, reps, weight, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (set_id, target_workout_id, exercise_id, start_set + idx, reps, weight, notes, now)
            )

        conn.commit()

        exercise_name = exercise["display_name"]
        response = {
            "status": "success",
            "exercise_id": exercise_id,
            "exercise_name": exercise_name,
            "sets_logged": len(sets_data),
            "message": f"Logged {exercise_name} - {len(sets_data)} set(s)"
        }

        if include_guidance:
            inferred = None
            progress = None
            if template_id:
                progress = self._compute_template_progress(template_id, target_workout_id, conn)
            else:
                conn.close()
                inferred = await self.infer_template(exercise_id, target_workout_id)
                conn = self._get_conn()
                if inferred.get("status") == "success":
                    template_id = inferred["template"]["id"]
                    progress = inferred.get("progress")

            last_perf = self._get_last_exercise_sets(exercise_id, target_workout_id, conn)
            response["guidance"] = {
                "template_inference": inferred,
                "template_id": template_id,
                "progress": progress,
                "last_performance": last_perf
            }

        conn.close()
        return response

    @tool(
        description="Get summary of a workout",
        parameters={
            "type": "object",
            "properties": {
                "workout_id": {
                    "type": "string",
                    "description": "Workout ID (uses current if not provided)"
                }
            },
            "required": []
        }
    )
    async def get_workout_summary(self, workout_id: Optional[str] = None) -> Dict[str, Any]:
        """Get a summary of a workout"""
        target_workout_id = workout_id or self.current_workout_id
        if not target_workout_id:
            raise ValueError("No workout specified.")

        conn = self._get_conn()
        summary = self._get_workout_summary_sync(target_workout_id, conn)
        if not summary:
            conn.close()
            raise ValueError(f"Workout {target_workout_id} not found")

        conn.close()
        return summary

    def _get_workout_summary_sync(self, workout_id: str, conn: sqlite3.Connection) -> Dict[str, Any]:
        """Synchronous version of get_workout_summary for internal use"""
        workout = conn.execute(
            "SELECT * FROM workouts WHERE id = ?",
            (workout_id,)
        ).fetchone()

        if not workout:
            return {}

        # Get all sets grouped by exercise
        rows = conn.execute(
            """
            SELECT e.id AS exercise_id, e.display_name, ws.set_number, ws.reps, ws.weight, ws.notes
            FROM workout_sets ws
            JOIN exercises e ON e.id = ws.exercise_id
            WHERE ws.workout_id = ?
            ORDER BY ws.created_at, ws.set_number
            """,
            (workout_id,)
        ).fetchall()

        # Group by exercise
        exercises_map: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            eid = r["exercise_id"]
            if eid not in exercises_map:
                exercises_map[eid] = {
                    "exercise_id": eid,
                    "name": r["display_name"],
                    "sets": []
                }
            exercises_map[eid]["sets"].append({
                "set": r["set_number"],
                "reps": r["reps"],
                "weight": r["weight"],
                "notes": r["notes"]
            })

        return {
            "id": workout["id"],
            "date": workout["date"],
            "notes": workout["notes"],
            "exercises": list(exercises_map.values())
        }

    @tool(
        description="Get recent workouts",
        parameters={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of workouts to retrieve"
                }
            },
            "required": []
        }
    )
    async def get_history(self, limit: int = 10) -> Dict[str, Any]:
        """Get recent workouts"""
        if limit <= 0:
            raise ValueError("Limit must be greater than 0")

        conn = self._get_conn()
        workouts = conn.execute(
            "SELECT id FROM workouts ORDER BY date DESC LIMIT ?",
            (limit,)
        ).fetchall()

        result = {
            "status": "success",
            "count": len(workouts),
            "workouts": []
        }

        for workout_row in workouts:
            summary = self._get_workout_summary_sync(workout_row["id"], conn)
            result["workouts"].append(summary)

        conn.close()
        return result

    @tool(
        description="End current workout session",
        parameters={
            "type": "object",
            "properties": {
                "final_notes": {
                    "type": "string",
                    "description": "Optional final notes"
                }
            },
            "required": []
        }
    )
    async def end_workout(self, final_notes: Optional[str] = None) -> Dict[str, Any]:
        """End current workout session"""
        if not self.current_workout_id:
            raise ValueError("No active workout session")

        conn = self._get_conn()
        summary = self._get_workout_summary_sync(self.current_workout_id, conn)

        if final_notes:
            conn.execute(
                "UPDATE workouts SET notes = ? WHERE id = ?",
                (final_notes, self.current_workout_id)
            )
            conn.commit()

        conn.close()
        self.current_workout_id = None

        return {
            "status": "success",
            "message": "Workout session ended",
            "summary": summary
        }

    async def cleanup(self) -> None:
        """Clean up resources"""
        pass
