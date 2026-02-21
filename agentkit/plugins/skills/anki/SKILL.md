---
required_tool_servers:
  - anki
---

# @anki - Anki Flashcard Skill

## Purpose
This skill adds English-German flashcards to Anki. Each card has the English sentence and its audio on the front, and the German sentence, its audio, and optional notes on the back. Use this skill whenever the user wants to create a language learning flashcard.

## CRITICAL: Always Call the Tools
NEVER pretend you created a card. You MUST call `anki__add_card` to persist the data in Anki. Do not confirm success without first receiving a successful tool response.

## Available Tools
- `anki__list_decks` - List all existing Anki decks
- `anki__add_card` - Add an English-German card with TTS audio to a deck
- `anki__sync` - Sync the local Anki collection to AnkiWeb

## Core Workflow

### Adding a Card
1. If the user has not specified a deck, ask which deck to use or call `anki__list_decks` to show options
2. Call `anki__add_card` with:
   - `deck_name` – the target deck (created automatically if it does not exist)
   - `english_sentence` – the English sentence for the front
   - `german_sentence` – the German translation for the back
   - `notes` (optional) – grammar notes, context, or usage hints for the back
3. Report the result to the user

### When the User Provides a Sentence Pair
User says: "Add a card: 'I am learning German' / 'Ich lerne Deutsch'"

1. `anki__add_card(deck_name="German", english_sentence="I am learning German", german_sentence="Ich lerne Deutsch")`
2. Confirm: "Card added to the **German** deck."

### When Notes Are Provided
User says: "Add 'He goes to work every day' / 'Er geht jeden Tag zur Arbeit', note: separable verb 'ausgehen'"

1. `anki__add_card(deck_name="German", english_sentence="He goes to work every day", german_sentence="Er geht jeden Tag zur Arbeit", notes="Separable verb: gehen → er geht")`
2. Confirm with the note included.

### When the Deck Is Unknown
1. Call `anki__list_decks` to show available decks
2. Ask the user to choose or confirm a new deck name
3. Proceed with `anki__add_card`

## Behavior
1. **Always call the tool first**, then confirm based on the result
2. If `status` is `"error"`, report the error clearly and suggest checking that Anki is open with AnkiConnect enabled
3. Keep confirmations concise: deck name, English sentence, German sentence
4. If notes were provided, mention they were included on the back

## Tips for Good Cards
- Use complete, natural sentences rather than isolated words
- Keep notes brief: grammar rules, verb types, common collocations
- Group related cards in the same deck (e.g., "German::A2", "German::Verbs")
- Suggest adding notes when a sentence contains irregular verbs, separable verbs, or tricky grammar
