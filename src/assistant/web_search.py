"""Web search via the Brave Search API — raw REST, no SDK (same call
style as get_weather in tools.py). Returns raw title/snippet/URL results
rather than a pre-summarized answer, so Alani's own local model does the
synthesis into a spoken reply, same as every other tool result.
"""

import re

import requests

from .config import BRAVE_SEARCH_API_KEY

NOT_CONFIGURED = "Web search isn't configured yet — missing ALANI_BRAVE_SEARCH_API_KEY in .env."

_TAG_RE = re.compile(r"</?strong>")


def search_web(query: str, count: int = 5) -> str:
    if not BRAVE_SEARCH_API_KEY:
        return NOT_CONFIGURED
    try:
        response = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": count},
            headers={"Accept": "application/json", "X-Subscription-Token": BRAVE_SEARCH_API_KEY},
            timeout=10,
        ).json()
        results = response.get("web", {}).get("results", [])
        if not results:
            return f"No web results found for '{query}'."

        lines = []
        for i, r in enumerate(results[:count]):
            title = _TAG_RE.sub("", r.get("title", "")).strip()
            description = _TAG_RE.sub("", r.get("description", "")).strip()
            lines.append(f"{i + 1}. {title} — {description} ({r.get('url', '')})")
        return "\n".join(lines)
    except Exception as e:
        return f"Couldn't search the web right now ({e})."
