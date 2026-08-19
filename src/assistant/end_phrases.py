"""Detects the user signaling they're done talking ("that will be all",
"never mind", "goodbye", ...) so a session can wrap up naturally instead
of sitting there listening for another utterance that isn't coming.

Deliberately plain string matching rather than routing this through the
LLM — it needs to be fast and 100% predictable. Multi-word phrases
("that will be all") are matched as a substring anywhere in what was
said, since they're distinctive enough that false positives are very
unlikely. Short, common words ("stop", "exit", "cancel", "enough") are
NOT substring-matched — "don't stop the timer" would wrongly end the
session if they were — instead they only trigger when they're
(essentially) the *whole* utterance, i.e. how someone actually says a
bare command word to interrupt Alani.
"""

END_PHRASES = [
    "that will be all",
    "that'll be all",
    "that is all",
    "that's all",
    "thats all",
    "never mind",
    "nevermind",
    "go back to sleep",
    "goodbye",
    "good bye",
    "bye alani",
    "that's it",
    "thats it",
    "nothing else",
    "no more questions",
    "i'm done",
    "im done",
    "we're done",
    "shut up",
    "be quiet",
    "quiet down",
    "forget it",
    "that's enough",
    "thats enough",
]

# Only matched as the (near-)entire utterance — see module docstring.
SHORT_TRIGGER_WORDS = [
    "exit",
    "stop",
    "cancel",
    "enough",
    "quiet",
]


def is_end_phrase(text: str) -> bool:
    normalized = text.lower().strip().strip(".!?")
    if any(phrase in normalized for phrase in END_PHRASES):
        return True

    # A handful of filler/politeness words are allowed alongside a short
    # trigger word without it counting as "part of a longer sentence".
    words = [w for w in normalized.split() if w not in ("alani", "please", "ok", "okay", "now")]
    return len(words) <= 2 and any(w in SHORT_TRIGGER_WORDS for w in words)
