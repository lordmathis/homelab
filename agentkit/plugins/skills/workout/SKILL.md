---
required_tool_servers:
  - workout
---

# @workout - Workout Logging Skill

## Purpose
This skill enables logging and tracking of workouts, including workout templates. When the user mentions exercises, sets, reps, or workout-related activities, treat it as workout logging.

## Available Tools
- `search_exercises` - Search the exercise registry by name or category
- `create_exercise` - Register a new exercise (name + optional category)
- `start_workout` - Start a new workout session
- `log_exercise` - Log sets for an exercise (requires exercise_id)
- `infer_template` - Infer which template is being followed
- `get_template_progress` - Check progress against a template
- `get_exercise_history` - View past performance for an exercise
- `get_workout_summary` - Summarize a workout
- `get_history` - List recent workouts
- `end_workout` - End the current session
- `create_template` - Create a workout template
- `list_templates` - List available templates

## Core Workflow

### Exercise Resolution (always do this first)
When the user mentions an exercise:
1. Call `search_exercises` with the exercise name to find it in the registry
2. If found, use the returned `id` for all subsequent calls
3. If not found, call `create_exercise` to register it, then use the new `id`

### Logging a Workout
1. If no active workout, call `start_workout`
2. Resolve the exercise ID (see above)
3. Call `log_exercise` with the `exercise_id` and `sets_data`
   - Sets can be logged all at once or one at a time (set numbers auto-increment)
   - Use `include_guidance: true` to get template progress and last performance
4. Call `infer_template` to determine which template the user is following
5. Show progress: sets remaining, next exercise, comparison to last performance

### Example Flow
User says: "Bench press 3x8 at 80kg"

1. `search_exercises(query="bench press")` → finds exercise with id `abc-123`
2. `log_exercise(exercise_id="abc-123", sets_data=[{reps: 8, weight: 80}, {reps: 8, weight: 80}, {reps: 8, weight: 80}], include_guidance=true)`
3. Report results and guidance to user

### Set-by-Set Logging
User says: "Bench press 8 reps at 80kg" (then later "another set, 7 reps")

Each call to `log_exercise` auto-increments the set number, so calling it multiple times for the same exercise in the same workout works correctly.

## Behavior

1. **Acknowledge the workout** in an encouraging, supportive tone
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
