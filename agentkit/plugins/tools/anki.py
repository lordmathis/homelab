import base64
import logging
import uuid
from typing import Any, Dict, Optional

import aiohttp

from agentkit.tools.toolset_handler import ToolSetHandler, tool

logger = logging.getLogger(__name__)


class AnkiTool(ToolSetHandler):

    ANKI_CONNECT_URL = "http://host.docker.internal:8765"
    AUDIO_SERVICE_URL = "http://host.docker.internal:9100"
    ANKI_CONNECT_VERSION = 6

    def __init__(self, name: str = "anki"):
        super().__init__(name)

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
                    raise Exception(f"AnkiConnect error: {data['error']}")
                return data.get("result")

    async def _generate_audio(self, text: str) -> bytes:
        payload = {
            "model": "tts-1",
            "input": text,
            "voice": "alloy"
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
        description="List all available Anki decks",
        parameters={
            "type": "object",
            "properties": {}
        }
    )
    async def list_decks(self) -> Dict[str, Any]:
        try:
            decks = await self._anki_request("deckNames")
            return {"status": "success", "decks": decks}
        except Exception as e:
            logger.error(f"Error listing decks: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    @tool(
        description=(
            "Add an English-German flashcard to an Anki deck. "
            "The front side contains the English sentence and its audio. "
            "The back side contains the German sentence, its audio, and optional notes. "
            "The deck is created automatically if it does not exist. "
            "Audio is generated via TTS for both sentences."
        ),
        parameters={
            "type": "object",
            "properties": {
                "deck_name": {
                    "type": "string",
                    "description": "Name of the Anki deck to add the card to"
                },
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
            "required": ["deck_name", "english_sentence", "german_sentence"]
        }
    )
    async def add_card(
        self,
        deck_name: str,
        english_sentence: str,
        german_sentence: str,
        notes: str = ""
    ) -> Dict[str, Any]:
        try:
            # Ensure deck exists
            await self._anki_request("createDeck", {"deck": deck_name})

            card_id = uuid.uuid4().hex[:10]
            en_filename = f"anki_en_{card_id}.wav"
            de_filename = f"anki_de_{card_id}.wav"

            # Generate and store audio for both sentences
            en_audio = await self._generate_audio(english_sentence)
            de_audio = await self._generate_audio(german_sentence)

            await self._store_audio(en_audio, en_filename)
            await self._store_audio(de_audio, de_filename)

            # Build card HTML
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

            return {
                "status": "success",
                "note_id": note_id,
                "deck": deck_name,
                "english": english_sentence,
                "german": german_sentence,
                "has_notes": bool(notes)
            }

        except Exception as e:
            logger.error(f"Error adding Anki card: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    @tool(
        description="Trigger a sync of the local Anki collection to AnkiWeb",
        parameters={
            "type": "object",
            "properties": {}
        }
    )
    async def sync(self) -> Dict[str, Any]:
        try:
            await self._anki_request("sync")
            return {"status": "success"}
        except Exception as e:
            logger.error(f"Error syncing Anki: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}
