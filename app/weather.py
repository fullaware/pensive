"""Weather lookup utilities using Open-Meteo."""

from __future__ import annotations

import re
from typing import Optional

import openmeteo_requests
import requests_cache
from retry_requests import retry

from config import logger

US_STATE_MAP = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
}


def _parse_city_state(city_input: str) -> tuple[str, Optional[str], Optional[str]]:
    state_code = None
    state_name = None
    city_only = city_input.strip()

    if "," in city_input:
        city_part, remainder = [part.strip() for part in city_input.split(",", 1)]
        if remainder:
            possible_state = remainder.split()[0].upper()
            if possible_state in US_STATE_MAP:
                state_code = possible_state
                state_name = US_STATE_MAP[state_code]
                city_only = city_part
            else:
                for abbr, full in US_STATE_MAP.items():
                    if remainder.lower().startswith(full.lower()):
                        state_code = abbr
                        state_name = full
                        city_only = city_part
                        break
    else:
        match_state = re.match(r"^(.*?)[\s,]+([A-Za-z]{2})$", city_input)
        if match_state:
            possible_state = match_state.group(2).upper()
            if possible_state in US_STATE_MAP:
                state_code = possible_state
                state_name = US_STATE_MAP[state_code]
                city_only = match_state.group(1).strip()

    return city_only, state_code, state_name


def get_weather_report(city: str) -> str:
    """Fetch a weather report string for the provided city."""
    city_input = city.strip()
    if not city_input:
        return "Error: City name is required. Please provide a city name."

    city_only, state_code, state_name = _parse_city_state(city_input)

    geocode_queries = []
    if state_code:
        geocode_queries.append(f"{city_only}, {state_code}")
    geocode_queries.append(city_input)
    if city_only not in geocode_queries:
        geocode_queries.append(city_only)

    try:
        cache_session = requests_cache.CachedSession(".cache", expire_after=3600)
        retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
        openmeteo = openmeteo_requests.Client(session=retry_session)

        geocode_url = "https://geocoding-api.open-meteo.com/v1/search"
        location = None

        for query in geocode_queries:
            geocode_params = {
                "name": query,
                "count": 5,
                "language": "en",
                "format": "json",
            }
            geocode_response = retry_session.get(geocode_url, params=geocode_params)
            geocode_response.raise_for_status()
            geocode_data = geocode_response.json()
            results = geocode_data.get("results") or []

            if not results:
                continue

            if state_name:
                for candidate in results:
                    if (
                        candidate.get("country_code") == "US"
                        and candidate.get("admin1", "").lower() == state_name.lower()
                    ):
                        location = candidate
                        break

            if not location:
                location = results[0]

            if location:
                break

        if not location:
            return f"Error: Could not find coordinates for city '{city}'. Please check the city name and try again."

        latitude = location["latitude"]
        longitude = location["longitude"]
        timezone_name = location.get("timezone", "UTC")
        city_name = location.get("name", city)
        country = location.get("country", "")

        weather_url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": [
                "temperature_2m",
                "relative_humidity_2m",
                "precipitation",
                "weather_code",
                "wind_speed_10m",
            ],
            "daily": ["temperature_2m_max", "temperature_2m_min", "precipitation_probability_max", "weather_code"],
            "timezone": timezone_name,
            "forecast_days": 1,
            "wind_speed_unit": "mph",
            "temperature_unit": "fahrenheit",
            "precipitation_unit": "inch",
        }

        responses = openmeteo.weather_api(weather_url, params=params)
        response = responses[0]

        current = response.Current()
        temperature = float(current.Variables(0).Value())
        humidity = float(current.Variables(1).Value())
        precipitation = float(current.Variables(2).Value())
        weather_code = int(current.Variables(3).Value())
        wind_speed = float(current.Variables(4).Value())

        daily = response.Daily()
        daily_high = float(daily.Variables(0).ValuesAsNumpy()[0])
        daily_low = float(daily.Variables(1).ValuesAsNumpy()[0])
        precip_prob = float(daily.Variables(2).ValuesAsNumpy()[0])

        weather_descriptions = {
            0: "Clear sky",
            1: "Mainly clear",
            2: "Partly cloudy",
            3: "Overcast",
            45: "Foggy",
            48: "Depositing rime fog",
            51: "Light drizzle",
            53: "Moderate drizzle",
            55: "Dense drizzle",
            56: "Light freezing drizzle",
            57: "Dense freezing drizzle",
            61: "Slight rain",
            63: "Moderate rain",
            65: "Heavy rain",
            66: "Light freezing rain",
            67: "Heavy freezing rain",
            71: "Slight snow fall",
            73: "Moderate snow fall",
            75: "Heavy snow fall",
            77: "Snow grains",
            80: "Slight rain showers",
            81: "Moderate rain showers",
            82: "Violent rain showers",
            85: "Slight snow showers",
            86: "Heavy snow showers",
            95: "Thunderstorm",
            96: "Thunderstorm with slight hail",
            99: "Thunderstorm with heavy hail",
        }

        current_desc = weather_descriptions.get(weather_code, f"Weather code {weather_code}")

        return (
            f"Current weather in {city_name}{f', {country}' if country else ''}:\n"
            f"- Temperature: {temperature:.1f}°F\n"
            f"- Conditions: {current_desc}\n"
            f"- Humidity: {humidity:.0f}%\n"
            f"- Wind Speed: {wind_speed:.1f} mph\n"
            f"- Precipitation: {precipitation:.2f} inches\n\n"
            "Today's forecast:\n"
            f"- High: {daily_high:.1f}°F\n"
            f"- Low: {daily_low:.1f}°F\n"
            f"- Precipitation Probability: {precip_prob:.0f}%"
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error(f"Weather lookup failed for city '{city}': {exc}")
        return f"Error getting weather for '{city}': {exc}. Please check the city name and try again."













