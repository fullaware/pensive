# __skill_name__ = "get_weather"
# __skill_description__ = "Get current weather for a location"
# __skill_active__ = False

import httpx
import json


async def execute(location: str) -> str:
    """
    Get current weather for a location using Open-Meteo API.
    
    Args:
        location: City name or coordinates
        
    Returns:
        Weather information as a string
    """
    try:
        # First get coordinates for the location
        geocoding_url = "https://geocoding-api.open-meteo.com/v1/search"
        params = {"name": location, "count": 1}
        
        async with httpx.AsyncClient() as client:
            response = await client.get(geocoding_url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if not data.get("results"):
                return f"Could not find location: {location}"
            
            result = data["results"][0]
            latitude = result["latitude"]
            longitude = result["longitude"]
            location_name = result.get("name", location)
            
            # Get weather data
            weather_url = "https://api.open-meteo.com/v1/forecast"
            weather_params = {
                "latitude": latitude,
                "longitude": longitude,
                "current": "temperature_2m,weather_code,windspeed_10m"
            }
            
            weather_response = await client.get(weather_url, params=weather_params)
            weather_response.raise_for_status()
            weather_data = weather_response.json()
            
            current = weather_data["current"]
            
            # Weather code to description mapping
            wmo_codes = {
                0: "Clear sky",
                1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
                45: "Fog", 48: "Depositing rime fog",
                51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
                61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
                71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
                95: "Thunderstorm", 96: "Thunderstorm with hail"
            }
            
            weather_code = current.get("weather_code", 0)
            weather_desc = wmo_codes.get(weather_code, "Unknown")
            
            return f"Weather in {location_name}: {current.get('temperature_2m', 'N/A')}°C, {weather_desc}, Wind: {current.get('windspeed_10m', 'N/A')} km/h"
            
    except Exception as e:
        return f"Error getting weather: {str(e)}"