"""Local function tools the LLM can call. Kept deliberately simple for the
initial conversational-only build — dice, time, weather, and the GitHub
bridge. New tools get added here + registered in TOOL_SCHEMAS/TOOL_FUNCTIONS
as the assistant grows.
"""

import random
from datetime import datetime

import requests

from . import github_bridge


def roll_dice(sides: int = 6, count: int = 1) -> str:
    sides = max(2, min(int(sides), 1000))
    count = max(1, min(int(count), 20))
    rolls = [random.randint(1, sides) for _ in range(count)]
    if count == 1:
        return f"Rolled a {rolls[0]} (d{sides})."
    return f"Rolled {rolls} (d{sides}), total {sum(rolls)}."


def draw_cards(count: int = 1) -> str:
    """Draws from a standard 52-card deck, no replacement (like a real
    hand — won't repeat a card within the same draw)."""
    count = max(1, min(int(count), 10))
    ranks = ["Ace", "2", "3", "4", "5", "6", "7", "8", "9", "10", "Jack", "Queen", "King"]
    suits = ["Hearts", "Diamonds", "Clubs", "Spades"]
    deck = [f"{rank} of {suit}" for rank in ranks for suit in suits]
    cards = random.sample(deck, count)
    if count == 1:
        return f"Drew the {cards[0]}."
    return "Drew: " + ", ".join(cards) + "."


def get_current_time() -> str:
    return datetime.now().strftime("It's %I:%M %p on %A, %B %d.")


def get_weather(location: str) -> str:
    """Free, keyless weather via Open-Meteo (geocode the place name, then
    pull current conditions)."""
    try:
        geo = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": location, "count": 1},
            timeout=10,
        ).json()
        results = geo.get("results")
        if not results:
            return f"I couldn't find a place called '{location}'."

        place = results[0]
        lat, lon = place["latitude"], place["longitude"]
        name = place.get("name", location)

        weather = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={"latitude": lat, "longitude": lon, "current": "temperature_2m,weather_code"},
            timeout=10,
        ).json()
        current = weather.get("current", {})
        temp = current.get("temperature_2m")
        if temp is None:
            return f"Couldn't get current weather for {name} right now."
        return f"It's currently {temp}°C in {name}."
    except Exception as e:
        return f"Couldn't check the weather right now ({e})."


def trigger_alani_bot_workflow(workflow_name: str) -> str:
    return github_bridge.trigger_workflow(workflow_name)


# OpenAI-style tool schemas — Ollama's chat() `tools` param expects this shape.
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "roll_dice",
            "description": "Roll one or more dice and return the result.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sides": {"type": "integer", "description": "Number of sides per die (default 6)"},
                    "count": {"type": "integer", "description": "Number of dice to roll (default 1)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "draw_cards",
            "description": "Draw one or more random playing cards from a standard 52-card deck (no repeats within the draw).",
            "parameters": {
                "type": "object",
                "properties": {
                    "count": {"type": "integer", "description": "Number of cards to draw (default 1)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Get the current local date and time.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a named place.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City or place name"},
                },
                "required": ["location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trigger_alani_bot_workflow",
            "description": (
                "Manually trigger a GitHub Actions workflow in the Alani-Bot "
                "Discord bot repo right now, instead of waiting for its schedule."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "workflow_name": {
                        "type": "string",
                        "description": "Exact workflow file name, e.g. 'fortnite-jam-tracks-tracker-shop-post.yml'",
                    },
                },
                "required": ["workflow_name"],
            },
        },
    },
]

TOOL_FUNCTIONS = {
    "roll_dice": roll_dice,
    "draw_cards": draw_cards,
    "get_current_time": get_current_time,
    "get_weather": get_weather,
    "trigger_alani_bot_workflow": trigger_alani_bot_workflow,
}
