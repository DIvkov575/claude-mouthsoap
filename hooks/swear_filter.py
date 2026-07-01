#!/usr/bin/env python3
"""swear-filter UserPromptSubmit hook.

Reads the hook payload from stdin, censors profanity in the submitted
prompt using regex, and returns the censored text to Claude as additional
context along with an instruction to work from the cleaned version.

Claude Code cannot rewrite the prompt already shown in the user's
terminal, so this hook injects the censored prompt and tells Claude to
treat *that* as the real message and to keep its own replies clean.
"""

import json
import os
import re
import sys


def _plugin_root() -> str:
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        return env
    # hooks/ -> plugin root
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_words() -> list:
    """Load the profanity list from wordlist.txt (one word per line).

    A user override can live at $CLAUDE_PLUGIN_ROOT/config/wordlist.txt or
    be pointed to via SWEAR_FILTER_WORDLIST.
    """
    candidates = []
    override = os.environ.get("SWEAR_FILTER_WORDLIST")
    if override:
        candidates.append(override)
    root = _plugin_root()
    candidates.append(os.path.join(root, "config", "wordlist.txt"))
    candidates.append(os.path.join(root, "hooks", "wordlist.txt"))

    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                words = []
                for line in fh:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        words.append(line.lower())
                if words:
                    return words
        except OSError:
            continue
    return []


# Map letters to the character classes people substitute for them, so
# "sh1t", "f@ck", "a$$" and friends still get caught.
_LEET = {
    "a": "a@4",
    "b": "b8",
    "e": "e3",
    "g": "g9",
    "i": "i1!|",
    "l": "l1|",
    "o": "o0",
    "s": "s$5",
    "t": "t7+",
    "u": "uv",
    "z": "z2",
}


def _char_pattern(ch: str) -> str:
    ch = ch.lower()
    if ch in _LEET:
        cls = re.escape(_LEET[ch])
        return f"[{cls}]"
    return re.escape(ch)


def build_regex(words: list) -> "re.Pattern | None":
    if not words:
        return None
    # Common inflections so "fucking", "shitty", "bastards" are caught too,
    # without dropping the trailing boundary (which protects words like
    # "class" or "assess").
    suffix = r"(?:in|ing|ed|er|ers|ain|a|s|es|y|ish|ing|head|hole)?"
    alts = []
    for word in words:
        # Allow each character to be repeated (fuuuck) and separated by
        # non-word padding (f-u-c-k). Keep it bounded to avoid catastrophic
        # backtracking on very long inputs.
        parts = [f"{_char_pattern(c)}+" for c in word]
        alts.append(r"[\W_]{0,2}".join(parts) + suffix)
    # \b-ish boundaries: not preceded/followed by a word char so we don't
    # nuke substrings inside innocent words (e.g. "assess", "class").
    pattern = r"(?<![A-Za-z0-9])(?:" + "|".join(alts) + r")(?![A-Za-z0-9])"
    return re.compile(pattern, re.IGNORECASE)


def censor(text: str, regex) -> "tuple[str, int]":
    if regex is None:
        return text, 0
    count = 0

    def repl(match):
        nonlocal count
        count += 1
        word = match.group(0)
        # Preserve length-ish feel: keep first char, star the rest.
        stripped = word.strip()
        if len(stripped) <= 1:
            return "*"
        return stripped[0] + "*" * (len(stripped) - 1)

    return regex.sub(repl, text), count


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}

    prompt = payload.get("prompt", "")
    words = load_words()
    regex = build_regex(words)
    cleaned, count = censor(prompt, regex)

    if count == 0:
        # Nothing to do; let the prompt through untouched.
        return 0

    context = (
        "[swear-filter] Profanity was detected in the user's message and has "
        "been censored. Treat the following CENSORED version as the user's "
        "actual request and respond to it. Do not repeat or reconstruct the "
        "original profanity, and keep your own reply free of profanity.\n\n"
        f"Censored message:\n{cleaned}"
    )

    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": context,
        }
    }
    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
