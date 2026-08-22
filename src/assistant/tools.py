"""Local function tools the LLM can call. Kept deliberately simple for the
initial conversational-only build — dice, time, weather, and the GitHub
bridge. New tools get added here + registered in TOOL_SCHEMAS/TOOL_FUNCTIONS
as the assistant grows.
"""

import random
from datetime import datetime

import requests

from . import discord_bridge, github_bridge, web_search


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


def set_reminder(text: str, remind_at: str) -> str:
    return discord_bridge.set_reminder(text, remind_at)


def list_reminders() -> str:
    return discord_bridge.list_reminders()


def delete_reminder(reminder_id: int) -> str:
    return discord_bridge.delete_reminder(reminder_id)


def add_calendar_event(title: str, start: str, end: str | None = None, all_day: bool = False) -> str:
    return discord_bridge.add_event(title, start, end, all_day)


def list_calendar_events() -> str:
    return discord_bridge.list_events()


def delete_calendar_event(event_id: int) -> str:
    return discord_bridge.delete_event(event_id)


def search_web(query: str) -> str:
    return web_search.search_web(query)


def end_conversation() -> str:
    """Doesn't actually do anything itself — llm.py's Conversation.send()
    special-cases this tool's name (same way it special-cases search_web
    for the UI state) to set self.should_end, which pipeline.py checks
    after the reply is spoken to decide whether to keep listening."""
    return "Ending the conversation now."


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
    {
        "type": "function",
        "function": {
            "name": "set_reminder",
            "description": (
                "Set a reminder that will be delivered later by DM on Discord. "
                "Use this whenever the user asks to be reminded of something."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "What to be reminded about"},
                    "remind_at": {
                        "type": "string",
                        "description": (
                            "When to deliver it, 24-hour format YYYY-MM-DDTHH:MM, "
                            "Indochina Time (UTC+7) — resolve relative times ('tomorrow', "
                            "'in an hour') against the current date/time given above"
                        ),
                    },
                },
                "required": ["text", "remind_at"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_reminders",
            "description": "List all currently pending reminders, with their IDs, times, and text.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_reminder",
            "description": (
                "Delete/cancel a pending reminder by its ID. Use list_reminders first if you "
                "don't already know the ID from earlier in the conversation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reminder_id": {"type": "integer", "description": "The reminder's ID, from list_reminders"},
                },
                "required": ["reminder_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_calendar_event",
            "description": (
                "Add a calendar event with a start time — for things that happen "
                "at a specific time, as opposed to a one-off reminder. "
                "Also shows up on the user's actual Google Calendar automatically."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "The event's title"},
                    "start": {
                        "type": "string",
                        "description": (
                            "24-hour format YYYY-MM-DDTHH:MM, Indochina Time (UTC+7) — year "
                            "and/or month may be omitted, assumed to be the current year/month "
                            "— resolve relative times against the current date/time given above"
                        ),
                    },
                    "end": {
                        "type": "string",
                        "description": (
                            "24-hour format YYYY-MM-DDTHH:MM, Indochina Time (UTC+7), must be "
                            "after start. Optional — if omitted, the event defaults to a "
                            "1-hour duration. Ignored if all_day is true."
                        ),
                    },
                    "all_day": {
                        "type": "boolean",
                        "description": "True to make this an all-day event instead of a timed one (end is ignored)",
                    },
                },
                "required": ["title", "start"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_calendar_events",
            "description": "List all upcoming calendar events, with their IDs, times, and titles.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_calendar_event",
            "description": (
                "Delete/cancel a calendar event by its ID. Use list_calendar_events first if you "
                "don't already know the ID from earlier in the conversation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "integer", "description": "The event's ID, from list_calendar_events"},
                },
                "required": ["event_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": (
                "Search the web for current information — news, facts, "
                "prices, anything beyond your own knowledge or the other "
                "tools here. Use whenever the user asks something you "
                "don't already know or that could have changed recently."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "end_conversation",
            "description": (
                "Call this whenever the user signals the conversation is "
                "wrapping up — not just literal goodbyes, but also things "
                "like 'that covers everything', 'I'm all set', 'appreciate "
                "it', 'that answers my question', or any closing remark "
                "that means they're satisfied and about to stop talking. "
                "If you're about to reply with something like 'let me know "
                "if you need anything else' or 'have a great day', that's "
                "usually a strong sign you should be calling this tool "
                "right now instead of just saying it. This ends the "
                "session; you'll stop listening after your reply."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

TOOL_FUNCTIONS = {
    "roll_dice": roll_dice,
    "draw_cards": draw_cards,
    "get_current_time": get_current_time,
    "get_weather": get_weather,
    "trigger_alani_bot_workflow": trigger_alani_bot_workflow,
    "set_reminder": set_reminder,
    "list_reminders": list_reminders,
    "delete_reminder": delete_reminder,
    "add_calendar_event": add_calendar_event,
    "list_calendar_events": list_calendar_events,
    "delete_calendar_event": delete_calendar_event,
    "search_web": search_web,
    "end_conversation": end_conversation,
}
