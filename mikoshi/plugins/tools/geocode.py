import logging
from typing import Any, Dict

from mikoshi.tools.toolset_handler import ToolSetHandler, tool

from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

logger = logging.getLogger(__name__)


class GeocodingTool(ToolSetHandler):
    """Tool for converting location names to coordinates using geopy"""
    server_name = "geocode"

    def __init__(self):
        super().__init__()

    @tool(
        description="Convert a location name or address to geographic coordinates (latitude, longitude)",
        parameters={
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "Location name or address (e.g., 'Heidelberg, Germany', '10115 Berlin')"
                }
            },
            "required": ["location"]
        }
    )
    async def geocode_location(self, location: str) -> Dict[str, Any]:
        """Convert a location name to coordinates using geopy"""
        try:
            # Initialize geocoder with proper user agent (required by Nominatim)
            geolocator = Nominatim(user_agent="mikoshi_geocoding_tool")
            
            # Perform geocoding
            location_obj = geolocator.geocode(location, language='en', addressdetails=True)
            
            if not location_obj:
                return {
                    "status": "error",
                    "error": f"Could not find location: '{location}'",
                    "location": location
                }

            return {
                "status": "success",
                "location": location,
                "coordinates": {
                    "latitude": location_obj.latitude,
                    "longitude": location_obj.longitude
                },
                "display_name": location_obj.display_name,
                "address": location_obj.address
            }

        except (GeocoderTimedOut, GeocoderServiceError) as e:
            logger.error(f"Geocoding service error: {e}", exc_info=True)
            return {
                "status": "error",
                "error": f"Geocoding service error: {str(e)}",
                "location": location
            }
        except Exception as e:
            logger.error(f"Error geocoding location: {e}", exc_info=True)
            return {
                "status": "error",
                "error": f"Error geocoding location: {str(e)}",
                "location": location
            }
