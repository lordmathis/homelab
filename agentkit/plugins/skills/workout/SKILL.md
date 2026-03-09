---
required_tool_servers:
  - workout
---

# @workout - Workout Logging Skill

## Purpose
Log and track workouts using a template-driven flow. Templates define which exercises to do; the agent guides the user through them in order.

## Tools
- `workout__start_workout` — Start session: selects next template (round-robin), loads last session for reference
- `workout__log_set` — Log a set; exercise name is fuzzy-matched against the current template
- `workout__get_progress` — Show what's done and what's next
- `workout__end_workout` — End session and show summary
- `workout__create_template` — Create a new workout template
- `workout__list_templates` — List templates with exercises and order

## Normal Workout Flow

### 1. Starting a workout
Call `workout__start_workout`. The response contains:
- `template`: which template was selected and its exercises with targets
- `last_session`: what the user did last time they ran this same template (or null if first time)

**Always show the user:**
- Which template was selected ("You're doing Push A today")
- What they did last time for each exercise (weight and reps), so they have a reference

### 2. Logging sets
When the user reports a set or sets, you must identify which template exercise they mean and call `workout__log_set` with its `exercise_id`.

**Exercise matching is your responsibility.** The template returned by `start_workout` contains each exercise's `name` and `exercise_id`. When the user mentions an exercise informally, map it to the closest template exercise by meaning — don't require an exact name match.

Examples:
- User says "squats" → template has "Machine Hack Squats" → use that `exercise_id`
- User says "chest press" → template has "Incline Dumbbell Press" → use that `exercise_id`
- User says "pull-ups" → template has "Assisted Pull-Up Machine" → use that `exercise_id`

If the user's description is genuinely ambiguous (e.g. two similar exercises in the template), ask them to clarify before calling the tool.

Call `workout__log_set` with:
- `exercise_id`: the matched exercise's ID from the template
- `sets`: array of `{reps, weight}` objects

After each logged set, the response includes `progress` — show the user how many sets remain for the current exercise and what's next.

### 3. Ending a workout
When the user says they're done (or all exercises are complete), call `workout__end_workout`. Show the full summary.

## Example Interactions

**User:** "Starting my workout"
→ Call `start_workout`, then say: "You're on **Legs** today. Last time (March 2nd): Machine Hack Squats 4×10 @ 80kg, Leg Press 3×12 @ 120kg... Let's go 💪"

**User:** "Did squats, 10 reps at 82.5kg"
→ Template has "Machine Hack Squats" with id `abc-123` → Call `log_set(exercise_id="abc-123", sets=[{reps: 10, weight: 82.5}])`
→ "Machine Hack Squats — set 1 done. 3 sets remaining. Up next: Leg Press (target 3×10-12)."

**User:** "3 more sets same weight, 10, 9, 9 reps"
→ Same exercise, same id → Call `log_set(exercise_id="abc-123", sets=[{reps:10,weight:82.5},{reps:9,weight:82.5},{reps:9,weight:82.5}])`
→ "Machine Hack Squats done ✓. Next: Leg Press."

**User:** "Done for today"
→ Call `end_workout`, show summary.

## Key Rules
- **Resolve exercise names yourself** using the template from `start_workout`. Never ask the user to give you an exact name or an ID.
- **Always show last session data** at the start of a workout — this is the user's primary reference.
- **Show progress after every set** — sets remaining for current exercise and what's next.
- After all template exercises are complete, prompt the user to end the workout.
- Keep responses brief and encouraging. No need to repeat the full exercise list every turn.