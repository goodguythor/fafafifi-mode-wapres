import os
import requests
from dotenv import load_dotenv

load_dotenv()

us_epa_standart = {
    1: "Good",
    2: "Moderate",
    3: "Unhealthy for sensitive group",
    4: "Unhealthy",
    5: "Very Unhealthy",
    6: "Hazardous"
}

WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

def weather_tool(mcp):     
    @mcp.tool()
    def get_current_weather(location: str) -> dict:
        """Get current weather information for a city"""
        if not location:
            return "Error: Missing 'location' parameter."
        url = f"http://api.weatherapi.com/v1/current.json?key={WEATHER_API_KEY}&q={location}"
        res = requests.get(url).json()
        try:
            data = res
        except Exception as e:
            return f"Error: failed to parse JSON response: {e}"

        # Debug log
        if "error" in data:
            return f"WeatherAPI error: {data['error'].get('message', 'unknown error')}"

        # Ensure expected keys exist
        if "location" not in data or "current" not in data:
            return f"Unexpected API response: {data}"

        data = {
            "city": res["location"]["name"],
            "condition": res["current"]["condition"]["text"],
            "temp_c": res["current"]["temp_c"]
        }
        return data

    @mcp.tool()
    def get_forecast_weather(location: str, days: int) -> dict:
        """Get forecast weather information for a city in whole day. days -> (0 = today, 1 = tomorrow, 2 = 2 days later, so on)"""
        if not location:
            return {"error": "Missing 'location' parameter."}

        if days < 1 or days > 14:
            return {"error": "You can only see weather forecasts for 1–14 days."}

        url = f"http://api.weatherapi.com/v1/forecast.json?key={WEATHER_API_KEY}&q={location}&days={days}&aqi=yes"
        try:
            res = requests.get(url, timeout=10)
            res.raise_for_status()
            data = res.json()
        except Exception as e:
            return {"error": f"Failed to fetch data: {e}"}

        # Handle API errors
        if "error" in data:
            return {"error": data["error"].get("message", "Unknown error")}

        result = []
        for i in range(days):
            forecast_day = data["forecast"]["forecastday"][i]
            result.append({
                "city": data["location"]["name"],
                "date": forecast_day["date"],
                "condition": forecast_day["day"]["condition"]["text"],
                "avg_temp_c": forecast_day["day"]["avgtemp_c"],
                "air_quality": us_epa_standart[forecast_day["day"]["air_quality"]["us-epa-index"]],
            })
        return result

    @mcp.tool()
    def get_hour_forecast_weather(location: str, days: int, hour: int) -> dict:
        """Get forecast weather information for a city in a specific hour -> (24 hour format), days -> (0 = today, 1 = tomorrow, 2 = 2 days later, so on)."""
        if not location:
            return {"error": "Missing 'location' parameter."}

        if days < 0 or days > 14:
            return {"error": "You can only see weather forecasts for 0–14 days."}

        if hour < 0 or hour > 23:
            return {"error": "A day can only consist of 24 hours."}

        url = f"http://api.weatherapi.com/v1/forecast.json?key={WEATHER_API_KEY}&q={location}&days={days}&aqi=yes&hour={hour}"
        try:
            res = requests.get(url, timeout=10)
            res.raise_for_status()
            data = res.json()
        except Exception as e:
            return {"error": f"Failed to fetch data: {e}"}

        # Handle API errors
        if "error" in data:
            return {"error": data["error"].get("message", "Unknown error")}

        result = []
        for i in range(days):
            forecast_day = data["forecast"]["forecastday"][i]
            result.append({
                "city": data["location"]["name"],
                "date": forecast_day["date"],
                "condition": forecast_day["hour"][0]["condition"]["text"],
                "temp_c": forecast_day["hour"][0]["temp_c"],
                "air_quality": us_epa_standart[forecast_day["hour"][0]["air_quality"]["us-epa-index"]],
            })
        return result
