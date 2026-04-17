import logging

from mikoshi.tools.toolset_handler import ToolSetHandler, tool

logger = logging.getLogger(__name__)

DWDS_BASE_URL = "https://www.dwds.de/wb"


class DictionaryTool(ToolSetHandler):
    server_name = "dictionary"

    def __init__(self):
        super().__init__()

    @tool(
        description=(
            "Look up a German word in the DWDS (Digitales Wörterbuch der deutschen Sprache) dictionary. "
            "Returns the dictionary entry including definitions, examples, and usage notes."
        ),
        parameters={
            "type": "object",
            "properties": {
                "word": {
                    "type": "string",
                    "description": "The German word to look up"
                }
            },
            "required": ["word"]
        }
    )
    async def lookup_word(self, word: str) -> str:
        url = f"{DWDS_BASE_URL}/{word}"
        logger.info(f"Looking up German word '{word}' at {url}")
        return await self.call_other_tool("web_tools__fetch_page", {"url": url, "include_links": False})
