import base64
import logging
import uuid
from typing import Any, Dict, Union

import aiohttp

from agentkit.tools.toolset_handler import ToolSetHandler, tool

logger = logging.getLogger(__name__)


class AnkiTool(ToolSetHandler):
    server_name = "anki"

    ANKI_CONNECT_URL = "http://host.docker.internal:8765"
    AUDIO_SERVICE_URL = "http://host.docker.internal:9100"
    ANKI_CONNECT_VERSION = 6
    DECK_NAME = "German::Sentences"

    def __init__(self):
        super().__init__()

    async def _anki_request(self, action: str, params: Dict = None) -> Any:
        payload = {
            "action": action,
            "version": self.ANKI_CONNECT_VERSION,
            "params": params or {}
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(self.ANKI_CONNECT_URL, json=payload) as resp:
                data = await resp.json()
                if data.get("error"):
                    return f"AnkiConnect error: {data['error']}"
                return data.get("result")

    async def _generate_audio(self, text: str, language: str = "en") -> bytes:
        payload = {
            "model": "tts-1",
            "input": text,
            "voice": "alloy",
            "language": language
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.AUDIO_SERVICE_URL}/v1/audio/speech",
                json=payload
            ) as resp:
                resp.raise_for_status()
                return await resp.read()

    async def _store_audio(self, audio_data: bytes, filename: str) -> None:
        audio_b64 = base64.b64encode(audio_data).decode("utf-8")
        await self._anki_request("storeMediaFile", {
            "filename": filename,
            "data": audio_b64
        })

    @tool(
        description=f"List cards in the Anki deck, showing the front and back of each card",
        parameters={
            "type": "object",
            "properties": {}
        }
    )
    async def list_cards(self) -> Union[str, Dict[str, Any]]:
        note_ids = await self._anki_request("findNotes", {"query": f"deck:{self.DECK_NAME}"})
        if isinstance(note_ids, str):
            return note_ids
        if not note_ids:
            return {"status": "success", "deck": self.DECK_NAME, "cards": []}
        notes_info = await self._anki_request("notesInfo", {"notes": note_ids})
        if isinstance(notes_info, str):
            return notes_info
        cards = [
            {
                "note_id": note["noteId"],
                "front": note["fields"]["Front"]["value"],
                "back": note["fields"]["Back"]["value"],
                "tags": note.get("tags", []),
            }
            for note in notes_info
        ]
        return {"status": "success", "deck": self.DECK_NAME, "cards": cards}

    @tool(
        description=(
            "Add an English-German flashcard to Anki. "
            "The front side contains the English sentence and its audio. "
            "The back side contains the German sentence, its audio, and optional notes. "
            "Audio is generated via TTS for both sentences. "
            "The collection is synced to AnkiWeb automatically after adding."
        ),
        parameters={
            "type": "object",
            "properties": {
                "english_sentence": {
                    "type": "string",
                    "description": "English sentence shown on the front of the card"
                },
                "german_sentence": {
                    "type": "string",
                    "description": "German sentence shown on the back of the card"
                },
                "notes": {
                    "type": "string",
                    "description": "Optional notes for the back of the card (grammar, context, etc.)"
                }
            },
            "required": ["english_sentence", "german_sentence"]
        }
    )
    async def add_card(
        self,
        english_sentence: str,
        german_sentence: str,
        notes: str = ""
    ) -> Union[str, Dict[str, Any]]:
        deck_name = self.DECK_NAME
        result = await self._anki_request("createDeck", {"deck": deck_name})
        if isinstance(result, str):
            return result

        card_id = uuid.uuid4().hex[:10]
        en_filename = f"anki_en_{card_id}.wav"
        de_filename = f"anki_de_{card_id}.wav"

        try:
            en_audio = await self._generate_audio(english_sentence, language="en")
        except Exception as e:
            return f"Error generating English audio: {e}"

        try:
            de_audio = await self._generate_audio(german_sentence, language="de")
        except Exception as e:
            return f"Error generating German audio: {e}"

        await self._store_audio(en_audio, en_filename)
        await self._store_audio(de_audio, de_filename)

        front = f"{english_sentence}<br><br>[sound:{en_filename}]"
        back = f"{german_sentence}<br><br>[sound:{de_filename}]"
        if notes:
            back += f"<br><br><i>{notes}</i>"

        note_id = await self._anki_request("addNote", {
            "note": {
                "deckName": deck_name,
                "modelName": "Basic",
                "fields": {
                    "Front": front,
                    "Back": back
                },
                "options": {
                    "allowDuplicate": False
                },
                "tags": ["language", "en-de"]
            }
        })

        if isinstance(note_id, str):
            return note_id

        await self._anki_request("sync")

        return {
            "status": "success",
            "note_id": note_id,
            "deck": deck_name,
            "english": english_sentence,
            "german": german_sentence,
            "has_notes": bool(notes)
        }
