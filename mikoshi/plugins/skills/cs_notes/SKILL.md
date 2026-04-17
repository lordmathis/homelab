---
required_tool_servers:
  - computer_science_notes
---

# @cs_notes Note Taker Skill

Distill a concept discussed in conversation into a clean, atomic Markdown note and save it using
`computer_science_notes__create_note` (or `computer_science_notes__update_note` for overwrites).

---

## Note Style

Model the note closely on the user's existing notes. Key conventions:

**Structure:**
```markdown
---
tags:
  - tag1
  - tag2
---

# Concept Name
One-sentence definition or core idea. Link related concepts with [[wiki_links]].

## Sub-section (if needed)
Concise prose or bullet list. One idea per section.

## Algorithm (if applicable)
Numbered steps.

## Hyperparameters (if applicable)
List with typical defaults.
```

**Formatting rules:**
- YAML frontmatter with relevant `tags` (e.g. `deep_learning`, `kubernetes`, `nlp`, `cuda`) — always included
- Inline math: `$...$` — never write equations as plain text
- Block/display math: `$$...$$`
- Code: inline with backticks, blocks with triple backticks + language tag
- Wiki links: `[[snake_case_concept_name]]` for any related concept that likely has its own note
- Bullet lists only for genuinely enumerable items; prefer prose otherwise
- Tables for structured comparisons (see cuda_memory_model style)
- Image placeholders: `![[descriptive_name.png]]` — only if the concept has a well-known diagram
- **No fluff.** No "it is worth noting", no motivation paragraphs, no restating equations in prose
- **Definitions first** — open with what the concept *is*, not history or context

**Tags — use these existing categories (add new ones only if clearly needed):**
- `machine_learning`, `deep_learning`, `nlp`, `computer_vision`
- `cuda`, `kubernetes`, `cryptocurrency`

---

## Steps

### 1. Determine scope

If the conversation covered one concept → one note.  
If multiple distinct concepts were discussed → ask the user whether to save all as separate notes or just a specific one.

### 2. Derive the filename

- Lowercase, underscore-separated
- Match the concept name exactly
- Append `.md`

Examples:
- "Attention Mechanism" → `attention_mechanism.md`
- "kube-proxy" → `kube_proxy.md`
- "BLEU Score" → `bleu_score.md`

### 3. Check for existing note

Call `computer_science_notes__list_notes` and check for a name collision.
- If found: ask the user whether to overwrite or save under a different name
- If not found: proceed

### 4. Draft the note

Synthesize from the conversation — do not copy verbatim. Apply all style rules above. Include:
- Everything essential to understand and use the concept
- Wiki links to any related concepts mentioned (algorithms, parent concepts, related techniques)
- LaTeX for any math covered in discussion
- Numbered steps for any algorithm walkthrough

Omit: tangents, motivating examples not core to the concept, anything the user said was out of scope.

### 5. Show the note to the user first

Before saving, display the formatted note in the chat and ask for confirmation or corrections.  
Only call `computer_science_notes__create_note` after the user approves (explicit "looks good", "save it", "yes", etc.).

### 6. Save

Call `computer_science_notes__create_note` with:
- `name`: derived filename
- `content`: approved markdown content

For overwrites, use `computer_science_notes__update_note`.

### 7. Confirm

Single line confirmation: e.g. `Saved as \`attention_mechanism.md\`.`

---

## Edge Cases

- **Concept not fully discussed** — write what was covered, mark gaps with `<!-- TODO: expand -->` comments, tell the user
- **User wants to add to an existing note** — fetch it with `computer_science_notes__get_note`, merge content, use `update_note`
- **Multiple concepts** — produce each note separately, confirm and save one at a time unless user says to save all

---

## Example

**User:** "Ok save this as a note" (after discussing attention mechanisms)

**Assistant flow:**
1. Concept = Attention Mechanism, one note
2. Filename: `attention_mechanism.md`
3. List notes — not found
4. Draft note with frontmatter, definition, math for attention scores, wiki links to `[[transformer_network]]`, `[[self_attention]]`
5. Display draft in chat, ask for confirmation
6. User: "looks good"
7. Call `computer_science_notes__create_note`
8. Reply: `Saved as \`attention_mechanism.md\`.`