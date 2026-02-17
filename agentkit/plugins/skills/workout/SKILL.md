---
required_tool_servers:
  - workout
---

# @workout - Workout Logging Skill

## Purpose
This skill enables logging and tracking of workouts, including workout templates. When the user mentions exercises, sets, reps, or workout-related activities, treat it as workout logging.

## CRITICAL: Always Call the Tools
NEVER pretend you logged something. When the user reports an exercise, you MUST call `workout__log_exercise` before responding. Do not generate a summary of what was logged without actually calling the tool. If you are unsure about any details (weight, reps), ask the user first, but ALWAYS call the tool to persist the data.

## Available Tools
- `workout__search_exercises` - Search the exercise registry by name or category
- `workout__create_exercise` - Register a new exercise (name + optional category)
- `workout__start_workout` - Start a new workout session
- `workout__log_exercise` - Log sets for an exercise (requires exercise_id)
- `workout__infer_template` - Infer which template is being followed
- `workout__get_template_progress` - Check progress against a template
- `workout__get_exercise_history` - View past performance for an exercise
- `workout__get_workout_summary` - Summarize a workout
- `workout__get_history` - List recent workouts
- `workout__end_workout` - End the current session
- `workout__create_template` - Create a workout template
- `workout__list_templates` - List available templates

## Core Workflow

### Exercise Resolution (always do this first)
When the user mentions an exercise:
1. Call `workout__search_exercises` with the exercise name to find it in the registry
2. If found, use the returned `id` for all subsequent calls
3. If not found, call `workout__create_exercise` to register it, then use the new `id`

### Logging a Workout
1. If no active workout, call `workout__start_workout`
2. Resolve the exercise ID (see above)
3. Call `workout__log_exercise` with the `exercise_id` and `sets_data`
   - Sets can be logged all at once or one at a time (set numbers auto-increment)
   - Use `include_guidance: true` to get template progress and last performance
4. Call `workout__infer_template` to determine which template the user is following
5. Show progress: sets remaining, next exercise, comparison to last performance

### Example Flow
User says: "Bench press 3x8 at 80kg"

1. `workout__search_exercises(query="bench press")` -> finds exercise with id `abc-123`
2. `workout__log_exercise(exercise_id="abc-123", sets_data=[{reps: 8, weight: 80}, {reps: 8, weight: 80}, {reps: 8, weight: 80}], include_guidance=true)`
3. Report results and guidance to user

### Set-by-Set Logging
User says: "Bench press 8 reps at 80kg" (then later "another set, 7 reps")

Each call to `workout__log_exercise` auto-increments the set number, so calling it multiple times for the same exercise in the same workout works correctly.

## Behavior

1. **Always call the tools first**, then respond based on the tool results
2. **Summarize what was logged** clearly (exercise, sets, reps, weight if mentioned)
3. **Provide guidance** when possible:
   - Show last performance for the exercise (reps/weight)
   - Show how many sets remain for the current exercise
   - Show which exercises are left in the template and the next exercise
4. **Ask relevant follow-up questions** if details are missing:
   - How did it feel?
   - What weight did you use?
   - Any notes about form or difficulty?

## Exercise Categories
When creating exercises, assign a category: back, chest, legs, shoulders, arms, core, cardio, or other appropriate category. This helps with organization and search.

## Tone
- Encouraging and supportive
- Casual but respectful
- Focus on progress and consistency
- Never judgmental about performance
