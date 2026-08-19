"""The conversational 'brain' — Ollama chat with tool calling. Keeps a
short rolling history so follow-up turns have context, and always speaks
through the same voice/tone regardless of whether a tool was used.
"""

import ollama

from .config import OLLAMA_MODEL
from .tools import TOOL_SCHEMAS, TOOL_FUNCTIONS

SYSTEM_PROMPT = """You are Alani, a helpful voice assistant running locally \
on the user's PC. You are speaking out loud, so keep replies short and \
natural — a sentence or two, not a written essay, no markdown or lists.

You have a small set of tools right now: rolling dice, telling the current \
time, checking the weather, and triggering workflows in the user's \
Alani-Bot GitHub repo. Use a tool whenever the request matches one.

If the user asks for something you don't have a tool or knowledge for \
(e.g. controlling smart devices, browsing the web, managing a calendar), \
say clearly and briefly that you can't do that yet and it may be added \
later. Don't pretend to do it, don't make up an answer, don't apologize \
excessively — one short sentence is enough."""


class Conversation:
    def __init__(self):
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    def send(self, user_text: str) -> str:
        self.messages.append({"role": "user", "content": user_text})

        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=self.messages,
            tools=TOOL_SCHEMAS,
        )
        message = response["message"]

        tool_calls = message.get("tool_calls")
        if tool_calls:
            self.messages.append(message)
            for call in tool_calls:
                name = call["function"]["name"]
                args = call["function"].get("arguments", {})
                func = TOOL_FUNCTIONS.get(name)
                result = func(**args) if func else f"Unknown tool: {name}"
                self.messages.append({"role": "tool", "content": str(result)})

            # Second pass: let the model turn the tool result into a spoken reply.
            response = ollama.chat(model=OLLAMA_MODEL, messages=self.messages)
            message = response["message"]

        self.messages.append(message)
        # Keep history bounded so context doesn't grow unbounded over a long session.
        if len(self.messages) > 21:
            self.messages = [self.messages[0]] + self.messages[-20:]

        return message.get("content", "").strip()
