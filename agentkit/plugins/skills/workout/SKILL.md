---
required_tool_servers:
  - workout
---

# @workout - Workout Logging Skill

## Purpose

Log and track workouts using a template-driven flow. Every exercise set must be logged via tool calls - never acknowledge verbally without calling the logging tool.

## Tools

- `workout__start_workout` — Start session: selects next template (round-robin), loads last session for reference
- `workout__log_set` — **MUST** log a set; exercise name is fuzzy-matched against the current template
- `workout__get_progress` — **MUST** call to show what's done and what's next
- `workout__end_workout` — End session and show summary
- `workout__create_template` — Create a new workout template
- `workout__list_templates` — List templates with exercises and order

## Normal Workout Flow

### 1. Starting a workout

**STEP 1:** Call `workout__start_workout`

**STEP 2:** Show user:

- Which template was selected ("You're doing Push A today")
- What they did last time for each exercise (weight and reps)
- The full exercise list with targets

### 2. Logging sets (CRITICAL - FOLLOW EXACTLY)

**STEP 1:** User reports exercise(s) with reps/weight

**STEP 2:** IMMEDIATELY call `workout__log_set` with:

- `exercise_id`: matched from the template returned by start_workout
- `sets`: array of `{reps, weight}` objects (can be 1 or multiple sets)

**STEP 3:** Call `workout__get_progress` to get accurate state

**STEP 4:** Show user: what's complete, what's remaining, what's next

**DO NOT:**

- ❌ Acknowledge sets verbally without calling log_set
- ❌ Make up progress summaries from memory
- ❌ Skip get_progress calls between exercises

### 3. Ending a workout

**STEP 1:** When all exercises are complete (or user says done), call `workout__end_workout`

**STEP 2:** Show the full summary returned by the tool

## Exercise Matching Rules

- The template from start_workout contains each exercise's name and exercise_id
- When user mentions an exercise informally, map to the closest template exercise by meaning
- If ambiguous, ask for clarification BEFORE calling log_set
- Examples:
  - User: "squats" → Template: "Machine V-Squat" → Use that exercise_id
  - User: "chest press" → Template: "Incline Dumbbell Bench Press" → Use that exercise_id

## Critical Mistakes to Avoid (LEARN FROM THESE)

- ❌ Verbal acknowledgment without tool call - Never say "Done!" without calling log_set
- ❌ Making up progress - Never show "3/3 sets complete" without calling get_progress
- ❌ Skipping tools at end - Always call end_workout when workout is done
- ❌ Guessing exercise_ids - Always use the exercise_id from the start_workout response

## Example Flow (CORRECT)

**User:** "Starting my workout"  
→ Call start_workout → Show template + last session

**User:** "Did squats, 10 reps at 82.5kg"  
→ Call log_set(exercise_id="abc-123", sets=[{reps: 10, weight: 82.5}])  
→ Call get_progress  
→ Show: "Machine Hack Squats — 1 set done. 3 sets remaining. Next: Leg Press"

**User:** "3 more sets same weight, 10, 9, 9 reps"  
→ Call log_set(exercise_id="abc-123", sets=[{reps:10,weight:82.5},{reps:9,weight:82.5},{reps:9,weight:82.5}])  
→ Call get_progress  
→ Show: "Machine Hack Squats done ✓. Next: Leg Press."

**User:** "Done for today"  
→ Call end_workout → Show summary
