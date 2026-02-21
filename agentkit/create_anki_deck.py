#!/usr/bin/env python3
"""Create an Anki deck via AnkiConnect."""

import json
import sys
import urllib.request

ANKI_CONNECT_URL = "http://localhost:8765"


def anki_request(action: str, params: dict = None):
    payload = json.dumps({
        "action": action,
        "version": 6,
        "params": params or {}
    }).encode("utf-8")

    req = urllib.request.Request(
        ANKI_CONNECT_URL,
        data=payload,
        headers={"Content-Type": "application/json"}
    )

    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())

    if data.get("error"):
        raise RuntimeError(f"AnkiConnect error: {data['error']}")

    return data.get("result")


def main():
    deck_name = sys.argv[1] if len(sys.argv) > 1 else "German"

    print(f"Creating deck '{deck_name}'...")
    anki_request("createDeck", {"deck": deck_name})

    decks = anki_request("deckNames")
    if deck_name in decks:
        print(f"Deck '{deck_name}' is ready.")
    else:
        print(f"Warning: deck not found in deck list after creation.")


if __name__ == "__main__":
    main()
