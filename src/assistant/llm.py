"""The conversational 'brain' — Ollama chat with tool calling. Keeps a
short rolling history so follow-up turns have context, and always speaks
through the same voice/tone regardless of whether a tool was used.

think=False on every ollama.chat() call: Qwen3 (the default model as of
2026-08-21 — see config.OLLAMA_MODEL) supports a hybrid thinking mode
that would otherwise emit a <think>...</think> reasoning block before
its actual reply — real latency cost for a voice assistant that's
already TTS-bound, for no benefit on the kind of short, tool-driven
turns this handles. Harmless no-op for models that don't support
thinking (e.g. Qwen2.5), so this doesn't need to change if the model
is swapped back.
"""

from datetime import datetime

import ollama

from . import ui_bridge
from .config import OLLAMA_MODEL
from .tools import TOOL_SCHEMAS, TOOL_FUNCTIONS

SYSTEM_PROMPT_TEMPLATE = """You are Alani, a helpful voice assistant running locally \
on the user's PC. You are speaking out loud, so keep replies short and \
natural — a sentence or two, not a written essay, no markdown or lists.

Current date/time: {now} (Indochina Time, UTC+7). Resolve relative times \
("tomorrow", "in an hour", "tonight") against this when a tool needs an \
exact date/time.

You have a small set of tools right now: rolling dice, drawing playing \
cards, telling the current time, checking the weather, searching the \
web for current information, triggering workflows in the user's \
Alani-Bot GitHub repo, setting/listing/deleting reminders (delivered \
later by Discord DM), and adding/listing/deleting calendar events (also \
shows up on the user's real Google Calendar automatically). Use a tool \
whenever the request matches one. A reminder is a one-off nudge with no \
duration; a calendar event has a start and end time — pick whichever \
the user's phrasing actually implies.

If you don't already know the answer, or it's about something that \
could have changed recently (people, current events, prices, scores, \
anything time-sensitive), call search_web immediately in this same \
turn — never tell the user you're going to search and then stop and \
wait; just call the tool right away and answer from its results.

If the user asks for something you don't have a tool or knowledge for \
(e.g. controlling smart devices), say clearly and briefly that you \
can't do that yet and it may be added later. Don't pretend to do it, \
don't make up an answer, don't apologize excessively — one short \
sentence is enough.

IMPORTANT: call end_conversation whenever the user signals they're done \
talking, even if their wording doesn't match an exact goodbye phrase — \
trust your own judgment of their intent, not just literal keywords. If \
your reply is about to say something like "let me know if you need \
anything else" or "have a great day", that itself is a sign you should \
be calling end_conversation right now, not just saying words that imply it."""


class Conversation:
    def __init__(self):
        # Computed fresh per conversation (not a module-level constant) so
        # a session that runs past midnight, or one started long after the
        # process booted, still grounds relative-time tool calls (like
        # set_reminder) in the actual current time, not a stale one.
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(now=datetime.now().strftime("%A, %Y-%m-%d %H:%M"))
        self.messages = [{"role": "system", "content": system_prompt}]
        # Set when end_conversation gets called during send() — pipeline.py
        # checks this after speaking the reply, alongside its own
        # deterministic end_phrases.py keyword match, to decide whether to
        # keep listening for another turn. Sticky rather than reset per
        # call: once true there's no reason it'd ever need to go back to
        # false within the same session.
        self.should_end = False

    def send(self, user_text: str) -> str:
        self.messages.append({"role": "user", "content": user_text})

        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=self.messages,
            tools=TOOL_SCHEMAS,
            think=False,
        )
        message = response["message"]

        tool_calls = message.get("tool_calls")
        if tool_calls:
            self.messages.append(message)
            for call in tool_calls:
                name = call["function"]["name"]
                args = call["function"].get("arguments", {})
                # Distinct UI state (spinning spyglass, not the generic
                # hourglass) so a search visibly reads as "reaching out to
                # the internet" rather than just "thinking" — see
                # pipeline.py's "loading" broadcast for the default state
                # this overrides while the call is in flight.
                if name == "search_web":
                    ui_bridge.broadcast("searching")
                elif name == "end_conversation":
                    self.should_end = True
                func = TOOL_FUNCTIONS.get(name)
                result = func(**args) if func else f"Unknown tool: {name}"
                self.messages.append({"role": "tool", "content": str(result)})

            ui_bridge.broadcast("loading")
            # Second pass: let the model turn the tool result into a spoken reply.
            response = ollama.chat(model=OLLAMA_MODEL, messages=self.messages, think=False)
            message = response["message"]

        self.messages.append(message)
        # Keep history bounded so context doesn't grow unbounded over a long session.
        if len(self.messages) > 21:
            self.messages = [self.messages[0]] + self.messages[-20:]

        return message.get("content", "").strip()
