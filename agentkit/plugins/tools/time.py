import logging
from datetime import datetime, timezone
from typing import Optional, Union
from zoneinfo import ZoneInfo

from agentkit.tools.toolset_handler import ToolSetHandler, tool

logger = logging.getLogger(__name__)


class TimeTools(ToolSetHandler):

    def __init__(self, name: str = "time"):
        super().__init__(name)

    @tool(
        description=(
            "Get the current date and time. "
            "Returns the current date and time in ISO format, optionally in a specific timezone."
        ),
        parameters={
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "description": "Optional timezone (e.g., 'US/Eastern', 'Europe/London', 'Asia/Tokyo'). Defaults to local timezone if not specified."
                },
                "include_offset": {
                    "type": "boolean",
                    "description": "Whether to include UTC offset in the output",
                    "default": False
                }
            },
            "required": []
        }
    )
    async def get_current_datetime(
        self,
        timezone: Optional[str] = None,
        include_offset: bool = False
    ) -> Union[str, dict]:
        try:
            if timezone:
                try:
                    tz = ZoneInfo(timezone)
                except KeyError:
                    return f"Error: Unknown timezone '{timezone}'. Use IANA timezone names like 'US/Eastern', 'Europe/London', or 'Asia/Tokyo'."
            else:
                tz = None

            now = datetime.now(tz)
            
            result = {
                "iso": now.isoformat(),
                "unix_timestamp": now.timestamp(),
                "timezone": str(now.tzinfo) if now.tzinfo else "local"
            }
            
            if include_offset:
                result["utc_offset"] = now.strftime("%z")
            
            logger.info(f"Retrieved current datetime: {now.isoformat()} in timezone {timezone or 'local'}")
            return result
            
        except Exception as e:
            logger.error(f"Error getting current datetime: {e}", exc_info=True)
            return f"Error: {e}"
