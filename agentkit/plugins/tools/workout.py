"""
Workout Toolset Plugin - Simplified workout logging with template-driven flow
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
    """Template-driven workout logging toolset"""
    server_name = "workout"

    def __init__(self):
        super().__init__()
        self.db_path: Optional[str] = None
        self.current_workout_id: Optional[str] = None
        self.current_template_id: Optional[str] = None

    async def initialize(self) -> None:
        await super().initialize()
        workspace = self._tool_manager.get_persistent_storage(self.server_name)
        self.db_path = os.path.join(workspace, "workouts.db")
        self._init_db()
        logger.info(f"Workout database initialized at {self.db_path}")

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS exercises (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                category TEXT,
                created_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS templates (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                last_used_at TEXT,
                created_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS template_exercises (
                id TEXT PRIMARY KEY,
                template_id TEXT NOT NULL,
                exercise_id TEXT NOT NULL,
                order_index INTEGER NOT NULL,
                target_sets INTEGER NOT NULL DEFAULT 3,
                target_reps_min INTEGER,
                target_reps_max INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY (template_id) REFERENCES templates(id) ON DELETE CASCADE,
                FOREIGN KEY (exercise_id) REFERENCES exercises(id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS workouts (
                id TEXT PRIMARY KEY,
                template_id TEXT,
                date TEXT NOT NULL,
                notes TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (template_id) REFERENCES templates(id)
            )
        """)

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

        conn.commit()
        conn.close()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _normalize(self, name: str) -> str:
        return " ".join(name.strip().lower().split())

    def _get_next_template(self, conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
        """Round-robin: return the active template that was least recently used."""
        return conn.execute(
            """
            SELECT * FROM templates
            WHERE active = 1
            ORDER BY last_used_at ASC NULLS FIRST, created_at ASC
            LIMIT 1
            """
        ).fetchone()

    def _get_template_exercises(self, template_id: str, conn: sqlite3.Connection) -> List[Dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT te.exercise_id, e.display_name AS name, e.category,
                   te.order_index, te.target_sets, te.target_reps_min, te.target_reps_max
            FROM template_exercises te
            JOIN exercises e ON e.id = te.exercise_id
            WHERE te.template_id = ?
            ORDER BY te.order_index
            """,
            (template_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def _get_last_session_for_template(self, template_id: str, conn: sqlite3.Connection) -> Optional[Dict[str, Any]]:
        """Get the most recent completed workout for this template."""
        workout = conn.execute(
            """
            SELECT id, date FROM workouts
            WHERE template_id = ?
            ORDER BY date DESC
            LIMIT 1
            """,
            (template_id,)
        ).fetchone()
        if not workout:
            return None

        rows = conn.execute(
            """
            SELECT e.display_name AS exercise_name, ws.set_number, ws.reps, ws.weight
            FROM workout_sets ws
            JOIN exercises e ON e.id = ws.exercise_id
            WHERE ws.workout_id = ?
            ORDER BY ws.created_at, ws.set_number
            """,
            (workout["id"],)
        ).fetchall()

        # Group sets by exercise
        exercises: Dict[str, Any] = {}
        for r in rows:
            n = r["exercise_name"]
            if n not in exercises:
                exercises[n] = []
            exercises[n].append({"set": r["set_number"], "reps": r["reps"], "weight": r["weight"]})

        return {
            "date": workout["date"],
            "exercises": [{"name": k, "sets": v} for k, v in exercises.items()]
        }

    def _get_workout_progress(self, workout_id: str, template_id: str, conn: sqlite3.Connection) -> Dict[str, Any]:
        """Return per-exercise progress vs template targets."""
        template_exercises = self._get_template_exercises(template_id, conn)

        sets_done = conn.execute(
            """
            SELECT exercise_id, COUNT(*) AS count
            FROM workout_sets WHERE workout_id = ?
            GROUP BY exercise_id
            """,
            (workout_id,)
        ).fetchall()
        done_map = {r["exercise_id"]: r["count"] for r in sets_done}

        result = []
        for ex in template_exercises:
            eid = ex["exercise_id"]
            done = done_map.get(eid, 0)
            remaining = max(ex["target_sets"] - done, 0)
            result.append({
                "name": ex["name"],
                "exercise_id": eid,
                "target_sets": ex["target_sets"],
                "sets_done": done,
                "sets_remaining": remaining,
                "target_reps_min": ex["target_reps_min"],
                "target_reps_max": ex["target_reps_max"],
                "done": remaining == 0
            })

        return {
            "exercises": result,
            "next": next((e for e in result if not e["done"]), None)
        }

    def _get_next_set_number(self, workout_id: str, exercise_id: str, conn: sqlite3.Connection) -> int:
        row = conn.execute(
            "SELECT MAX(set_number) AS m FROM workout_sets WHERE workout_id = ? AND exercise_id = ?",
            (workout_id, exercise_id)
        ).fetchone()
        return (row["m"] or 0) + 1

    # -------------------------------------------------------------------------
    # Tools
    # -------------------------------------------------------------------------

    @tool(
        description=(
            "Start a new workout session. Automatically selects the next template via round-robin "
            "(least recently used active template), loads the last session for that template so the "
            "agent can show the user what they did before, returns template exercises with targets, "
            "and returns workout progress (first exercise to do). "
            "Call this at the beginning of every workout."
        ),
        parameters={
            "type": "object",
            "properties": {
                "notes": {"type": "string", "description": "Optional notes about the workout"}
            },
            "required": []
        }
    )
    async def start_workout(self, notes: Optional[str] = None) -> Dict[str, Any]:
        conn = self._get_conn()

        template = self._get_next_template(conn)
        if not template:
            conn.close()
            return {"status": "error", "message": "No active templates found. Create a template first with create_template."}

        self.current_workout_id = str(uuid.uuid4())
        self.current_template_id = template["id"]
        now = datetime.now(UTC).isoformat()

        conn.execute(
            "INSERT INTO workouts (id, template_id, date, notes, created_at) VALUES (?, ?, ?, ?, ?)",
            (self.current_workout_id, template["id"], now, notes, now)
        )
        conn.execute(
            "UPDATE templates SET last_used_at = ? WHERE id = ?",
            (now, template["id"])
        )
        conn.commit()

        exercises = self._get_template_exercises(template["id"], conn)
        last_session = self._get_last_session_for_template(template["id"], conn)
        progress = self._get_workout_progress(self.current_workout_id, self.current_template_id, conn)
        conn.close()

        return {
            "status": "success",
            "workout_id": self.current_workout_id,
            "template": {
                "id": template["id"],
                "name": template["name"],
                "exercises": exercises
            },
            "last_session": last_session,
            "progress": progress
        }

    @tool(
        description=(
            "Log a set (or multiple sets) for an exercise. "
            "Use the exercise_id from the template returned by start_workout. "
            "Returns updated workout progress so you can tell the user what's next."
        ),
        parameters={
            "type": "object",
            "properties": {
                "exercise_id": {
                    "type": "string",
                    "description": "Exercise ID from the current template (returned by start_workout)"
                },
                "sets": {
                    "type": "array",
                    "description": "One or more sets to log",
                    "items": {
                        "type": "object",
                        "properties": {
                            "reps": {"type": "integer", "description": "Number of reps"},
                            "weight": {"type": "number", "description": "Weight in kg (optional)"},
                            "notes": {"type": "string", "description": "Optional notes for this set"}
                        },
                        "required": ["reps"]
                    }
                }
            },
            "required": ["exercise_id", "sets"]
        }
    )
    async def log_set(self, exercise_id: str, sets: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not self.current_workout_id:
            return {"status": "error", "message": "No active workout. Call start_workout first."}

        conn = self._get_conn()

        exercise = conn.execute(
            "SELECT display_name FROM exercises WHERE id = ?", (exercise_id,)
        ).fetchone()
        if not exercise:
            conn.close()
            return {"status": "error", "message": f"Exercise ID '{exercise_id}' not found. Use an ID from the current template."}

        start_set = self._get_next_set_number(self.current_workout_id, exercise_id, conn)
        now = datetime.now(UTC).isoformat()

        for idx, s in enumerate(sets):
            reps = s.get("reps")
            if not isinstance(reps, int) or reps <= 0:
                conn.close()
                return {"status": "error", "message": f"Invalid reps value: {reps}"}
            conn.execute(
                "INSERT INTO workout_sets (id, workout_id, exercise_id, set_number, reps, weight, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), self.current_workout_id, exercise_id, start_set + idx,
                 reps, s.get("weight"), s.get("notes"), now)
            )

        conn.commit()
        progress = self._get_workout_progress(self.current_workout_id, self.current_template_id, conn)
        conn.close()

        return {
            "status": "success",
            "logged": {
                "exercise": exercise["display_name"],
                "sets_logged": len(sets),
                "sets": sets
            },
            "progress": progress
        }

    @tool(
        description="Get current workout progress: sets done vs targets for each exercise, and what's next.",
        parameters={
            "type": "object",
            "properties": {},
            "required": []
        }
    )
    async def get_progress(self) -> Dict[str, Any]:
        if not self.current_workout_id:
            return {"status": "error", "message": "No active workout."}

        conn = self._get_conn()
        progress = self._get_workout_progress(self.current_workout_id, self.current_template_id, conn)
        conn.close()
        return {"status": "success", "progress": progress}

    @tool(
        description="End the current workout session and return a full summary.",
        parameters={
            "type": "object",
            "properties": {
                "notes": {"type": "string", "description": "Optional final notes"}
            },
            "required": []
        }
    )
    async def end_workout(self, notes: Optional[str] = None) -> Dict[str, Any]:
        if not self.current_workout_id:
            return {"status": "error", "message": "No active workout session."}

        conn = self._get_conn()

        if notes:
            conn.execute("UPDATE workouts SET notes = ? WHERE id = ?", (notes, self.current_workout_id))

        # Build summary
        rows = conn.execute(
            """
            SELECT e.display_name AS exercise_name, ws.set_number, ws.reps, ws.weight, ws.notes
            FROM workout_sets ws
            JOIN exercises e ON e.id = ws.exercise_id
            WHERE ws.workout_id = ?
            ORDER BY ws.created_at, ws.set_number
            """,
            (self.current_workout_id,)
        ).fetchall()

        exercises: Dict[str, Any] = {}
        for r in rows:
            n = r["exercise_name"]
            if n not in exercises:
                exercises[n] = []
            exercises[n].append({"set": r["set_number"], "reps": r["reps"], "weight": r["weight"]})

        conn.commit()
        conn.close()

        summary = {
            "workout_id": self.current_workout_id,
            "exercises": [{"name": k, "sets": v} for k, v in exercises.items()]
        }

        self.current_workout_id = None
        self.current_template_id = None

        return {"status": "success", "summary": summary}

    @tool(
        description=(
            "Create a new workout template. Each exercise will be registered in the exercise registry "
            "if it doesn't exist yet."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Template name (e.g. 'Push A', 'Legs')"},
                "exercises": {
                    "type": "array",
                    "description": "Exercises in order",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Exercise name"},
                            "category": {"type": "string", "description": "Category (chest, legs, back, etc.)"},
                            "target_sets": {"type": "integer", "description": "Target number of sets"},
                            "target_reps_min": {"type": "integer", "description": "Minimum target reps"},
                            "target_reps_max": {"type": "integer", "description": "Maximum target reps"}
                        },
                        "required": ["name", "target_sets"]
                    }
                }
            },
            "required": ["name", "exercises"]
        }
    )
    async def create_template(self, name: str, exercises: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not exercises:
            return {"status": "error", "message": "Template must include at least one exercise."}

        template_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()

        conn = self._get_conn()
        conn.execute(
            "INSERT INTO templates (id, name, active, created_at) VALUES (?, ?, 1, ?)",
            (template_id, name, now)
        )

        registered = []
        for idx, ex in enumerate(exercises, 1):
            ex_name = ex.get("name", "").strip()
            if not ex_name:
                conn.close()
                return {"status": "error", "message": "Each exercise must have a name."}

            normalized = self._normalize(ex_name)
            row = conn.execute("SELECT id FROM exercises WHERE name = ?", (normalized,)).fetchone()
            if row:
                exercise_id = row["id"]
            else:
                exercise_id = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO exercises (id, name, display_name, category, created_at) VALUES (?, ?, ?, ?, ?)",
                    (exercise_id, normalized, ex_name, ex.get("category"), now)
                )

            conn.execute(
                """
                INSERT INTO template_exercises
                    (id, template_id, exercise_id, order_index, target_sets, target_reps_min, target_reps_max, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), template_id, exercise_id, idx,
                 ex.get("target_sets", 3), ex.get("target_reps_min"), ex.get("target_reps_max"), now)
            )
            registered.append(ex_name)

        conn.commit()
        conn.close()

        return {
            "status": "success",
            "template_id": template_id,
            "name": name,
            "exercises": registered
        }

    @tool(
        description="List all workout templates with their exercises and active status.",
        parameters={
            "type": "object",
            "properties": {
                "active_only": {"type": "boolean", "description": "Only show active templates (default true)"}
            },
            "required": []
        }
    )
    async def list_templates(self, active_only: bool = True) -> Dict[str, Any]:
        conn = self._get_conn()
        where = "WHERE active = 1" if active_only else ""
        templates = conn.execute(
            f"SELECT * FROM templates {where} ORDER BY last_used_at ASC NULLS FIRST, created_at ASC"
        ).fetchall()

        result = []
        for t in templates:
            result.append({
                "id": t["id"],
                "name": t["name"],
                "active": bool(t["active"]),
                "last_used_at": t["last_used_at"],
                "exercises": self._get_template_exercises(t["id"], conn)
            })

        conn.close()
        return {"status": "success", "templates": result}

    @tool(
        description=(
            "Get recent workout history, optionally filtered by template. "
            "Use this to look up past performance or answer questions like 'what did I do last week'."
        ),
        parameters={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Number of recent workouts to return (default 5)"},
                "template_id": {"type": "string", "description": "Filter by template ID (optional)"}
            },
            "required": []
        }
    )
    async def get_history(self, limit: int = 5, template_id: Optional[str] = None) -> Dict[str, Any]:
        conn = self._get_conn()

        where = "WHERE w.template_id = ?" if template_id else ""
        params = [template_id] if template_id else []
        params.append(limit)

        workouts = conn.execute(
            f"""
            SELECT w.id, w.date, w.notes, t.name AS template_name
            FROM workouts w
            LEFT JOIN templates t ON t.id = w.template_id
            {where}
            ORDER BY w.date DESC
            LIMIT ?
            """,
            params
        ).fetchall()

        result = []
        for w in workouts:
            rows = conn.execute(
                """
                SELECT e.display_name AS exercise_name, ws.set_number, ws.reps, ws.weight
                FROM workout_sets ws
                JOIN exercises e ON e.id = ws.exercise_id
                WHERE ws.workout_id = ?
                ORDER BY ws.created_at, ws.set_number
                """,
                (w["id"],)
            ).fetchall()

            exercises: Dict[str, Any] = {}
            for r in rows:
                n = r["exercise_name"]
                if n not in exercises:
                    exercises[n] = []
                exercises[n].append({"set": r["set_number"], "reps": r["reps"], "weight": r["weight"]})

            result.append({
                "date": w["date"],
                "template": w["template_name"],
                "notes": w["notes"],
                "exercises": [{"name": k, "sets": v} for k, v in exercises.items()]
            })

        conn.close()
        return {"status": "success", "count": len(result), "workouts": result}

    async def cleanup(self) -> None:
        pass