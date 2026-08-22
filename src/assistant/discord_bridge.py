"""Bridge to the Alani-Bot Discord bot's small HTTP API — lets voice tools
trigger things on the always-on bot that need its own database (reminders
and calendar events for now), which lives only on the bot's host disk and
isn't reachable from this PC directly. Not routed through Discord itself:
the bot ignores its own messages (and a second bot identity or webhook
wouldn't pass its owner check either), so a small authenticated HTTP
endpoint on the bot host is the actually-correct way to bridge two
independent services — see Alani-Bot's src/features/db/voiceApi.js for
the server side.

Calendar events added here also sync to Google Calendar automatically —
that happens entirely on Alani-Bot's side (src/features/orkus-info/
actions.js), nothing extra needed from this file or the tool functions
below.
"""

import requests

from .config import ALANI_BOT_API_SECRET, ALANI_BOT_API_URL

NOT_CONFIGURED = "The Discord reminder bridge isn't configured yet — missing ALANI_BOT_API_URL or ALANI_BOT_API_SECRET in .env."


def _request(method: str, path: str, json: dict | None = None) -> str:
    """Shared call/error-handling for every voiceApi.js endpoint. Never
    raises — tool calls should always produce something speakable back to
    the user, an error included."""
    if not ALANI_BOT_API_URL or not ALANI_BOT_API_SECRET:
        return NOT_CONFIGURED
    try:
        response = requests.request(
            method,
            f"{ALANI_BOT_API_URL.rstrip('/')}{path}",
            json=json,
            headers={"Authorization": f"Bearer {ALANI_BOT_API_SECRET}"},
            timeout=10,
        )
        data = response.json()
        if response.status_code == 200:
            return data.get("message", "Done.")
        return f"That didn't work: {data.get('error', response.text)}"
    except Exception as e:
        return f"Couldn't reach the Discord bot ({e})."


def _request_raw(method: str, path: str, json: dict | None = None) -> dict:
    """Same call as _request(), but for endpoints that return real data
    (not just a `message` string) — e.g. list_databases(). Always returns
    a dict; on any failure it's `{"error": "<speakable reason>"}` rather
    than raising, same never-raise contract as _request()."""
    if not ALANI_BOT_API_URL or not ALANI_BOT_API_SECRET:
        return {"error": NOT_CONFIGURED}
    try:
        response = requests.request(
            method,
            f"{ALANI_BOT_API_URL.rstrip('/')}{path}",
            json=json,
            headers={"Authorization": f"Bearer {ALANI_BOT_API_SECRET}"},
            timeout=10,
        )
        data = response.json()
        if response.status_code == 200:
            return data
        return {"error": data.get("error", response.text)}
    except Exception as e:
        return {"error": f"Couldn't reach the Discord bot ({e})."}


def _reminder_payload(text: str, remind_at: str, database: str, channel_id: str | None) -> dict:
    payload = {"text": text, "remindAt": remind_at, "database": database}
    if channel_id:
        payload["channelId"] = channel_id
    return payload


def set_reminder(text: str, remind_at: str, database: str = "main", channel_id: str | None = None) -> str:
    """remind_at: 24-hour "YYYY-MM-DDTHH:MM", Indochina Time (UTC+7) —
    matches Alani-Bot's own `.a db add reminder` parsing convention.
    database/channel_id are for the "console add" manual-entry UI only —
    the spoken tool-calling path (tools.py) never passes them, so a
    voice-triggered reminder always still means database="main",
    channel_id=None (DMs DISCORD_OWNER_0), exactly as before this
    existed."""
    return _request("POST", "/voice/reminder", _reminder_payload(text, remind_at, database, channel_id))


def console_set_reminder(text: str, remind_at: str, database: str = "main", channel_id: str | None = None) -> tuple[bool, str]:
    """Same call as set_reminder(), but for the "console add" UI, which
    needs a real success/failure signal — not a string it'd have to guess
    at by pattern-matching (set_reminder()'s return is meant to be spoken,
    not parsed)."""
    data = _request_raw("POST", "/voice/reminder", _reminder_payload(text, remind_at, database, channel_id))
    if "error" in data:
        return False, data["error"]
    return True, data.get("message", "Done.")


def list_databases() -> list[dict]:
    """Every database voice-Alani (and the "console add" UI) can target —
    always includes {"name": "main", "kind": "main"} plus any Tier
    Personal/Server database, since the bridge authenticates as
    DISCORD_OWNER_0 and can see everything a bot owner can. Returns an
    empty list (not an exception) if the bridge isn't configured/
    reachable — callers should treat that the same as "nothing to pick
    from yet"."""
    data = _request_raw("GET", "/voice/databases")
    return data.get("databases", [])


def list_reminders() -> str:
    return _request("GET", "/voice/reminders")


def delete_reminder(reminder_id: int) -> str:
    return _request("POST", "/voice/reminder/delete", {"id": reminder_id})


def _event_payload(title: str, start: str, end: str | None, all_day: bool, database: str) -> dict:
    payload = {"title": title, "start": start, "database": database}
    if all_day:
        payload["allDay"] = True
    elif end:
        payload["end"] = end
    return payload


def add_event(title: str, start: str, end: str | None = None, all_day: bool = False, database: str = "main") -> str:
    """start/end: 24-hour "YYYY-MM-DDTHH:MM" (year/month optional, assumes
    current), Indochina Time (UTC+7) — matches Alani-Bot's own
    `.a db add event` parsing convention. end omitted defaults to a 1-hour
    event; all_day=True makes it an all-day event instead (end is ignored
    in that case). Also syncs to Google Calendar automatically
    (Alani-Bot's side) when database="main" — other databases never sync
    there (a server-kind one mirrors to a real Discord Scheduled Event
    instead). database is for the "console add" manual-entry UI only —
    the spoken tool-calling path never passes it, so a voice-triggered
    event always still means database="main", exactly as before this
    existed."""
    return _request("POST", "/voice/event", _event_payload(title, start, end, all_day, database))


def console_add_event(title: str, start: str, end: str | None = None, all_day: bool = False, database: str = "main") -> tuple[bool, str]:
    """Same call as add_event(), but for the "console add" UI — see
    console_set_reminder()'s own note on why this returns a real
    success/failure signal instead of a string meant to be spoken."""
    data = _request_raw("POST", "/voice/event", _event_payload(title, start, end, all_day, database))
    if "error" in data:
        return False, data["error"]
    return True, data.get("message", "Done.")


def list_events() -> str:
    return _request("GET", "/voice/events")


def delete_event(event_id: int) -> str:
    return _request("POST", "/voice/event/delete", {"id": event_id})
