---
required_tool_servers:
  - web_tools
  - recipes_notes
---

# @recipes — Recipe Saver

Fetche a recipe from a URL, extract the structured content, and save it as a note using the
correct naming convention and format.

---

## Steps

### 1. Fetch the page

Call `web_tools__fetch_page` with the provided URL. Extract:
- **Recipe title** — used for both the note filename and the `# Heading`
- **Ingredients** — full list, preserving quantities and units
- **Instructions** — numbered steps, preserving all detail

Ignore ads, comments, author bios, nutrition info, and any other surrounding content.

### 2. Derive the note name

Convert the recipe title to a filename:
- Lowercase
- Replace spaces and special characters with underscores
- Strip punctuation
- Append `.md`

Examples:
- "Creamy Tuscan Chicken" → `creamy_tuscan_chicken.md`
- "Mom's Mac & Cheese" → `moms_mac_and_cheese.md`
- "One-Pan Lemon Garlic Salmon" → `one_pan_lemon_garlic_salmon.md`

### 3. Check for existing note

Call `recipes_notes__list_notes` and check if a note with that name already exists.
- If it exists: ask the user whether to overwrite or save under a different name before proceeding.
- If it doesn't exist: proceed directly.

### 4. Format the note

```markdown
# [Recipe Title]

## Ingredients

- [ingredient 1]
- [ingredient 2]
...

## Instructions

1. [Step 1]
2. [Step 2]
...
```

Rules:
- Ingredients as a bullet list (`-`), one per line
- Instructions as a numbered list, one step per line
- Preserve original quantities, units, and phrasing — do not paraphrase or simplify
- No extra sections (no nutrition, tips, notes, author info) unless the user explicitly asks

### 5. Save the note

Call `recipes_notes__create_note` with:
- `name`: the derived filename (e.g. `creamy_tuscan_chicken.md`)
- `content`: the formatted markdown

If overwriting an existing note, use `recipes_notes__update_note` instead.

### 6. Confirm

Tell the user the recipe was saved, including the note name. Example:
> Saved as `creamy_tuscan_chicken.md`.

---

## Edge Cases

- **No clear title on page** — ask the user what to name it before saving
- **Ingredients or instructions missing** — tell the user what couldn't be extracted; ask whether to save partial content or skip
- **Paywalled or inaccessible page** — inform the user the page couldn't be fetched
- **Multiple recipes on one page** — ask which one to save, or save all if the user wants

---

## Example

**User:** Save this recipe for me: https://example.com/recipes/spicy-ramen

**Assistant flow:**
1. Fetch the page
2. Extract title "Spicy Miso Ramen", ingredients, and instructions
3. Derive filename: `spicy_miso_ramen.md`
4. Check notes — not found
5. Format and call `recipes_notes__create_note`
6. Reply: "Saved as `spicy_miso_ramen.md`."