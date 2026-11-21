def weather_fetch(city: str) -> str:
    """Get the current weather for a city.

    In production this would call the weather API through the session tunnel.
    This example returns mock data for demonstration.
    """
    mock_data = {
        "London": "14°C, overcast, humidity 78%",
        "Tokyo": "22°C, sunny, humidity 45%",
        "New York": "18°C, partly cloudy, humidity 62%",
        "Sydney": "26°C, clear, humidity 38%",
        "Paris": "16°C, light rain, humidity 85%",
    }
    weather = mock_data.get(city, f"20°C, fair, humidity 55%")
    return f"Weather in {city}: {weather}"
