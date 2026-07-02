#!/usr/bin/env python3
"""swear-filter UserPromptSubmit hook.

Reads the hook payload on stdin, deletes any profanity from the submitted
prompt, and returns the cleaned text to Claude as additional context so the
model neither drifts out-of-distribution nor spends tokens reacting to
language aimed at its work. Terms live in config/wordlist.txt (one per line).
Matching is case-insensitive and tolerates repeated letters, leetspeak, and
a trailing plural. Every match is removed — no per-word replacements.
"""

import json
import os
import re
import sys

# Per-letter leetspeak classes, so "sh1t", "cr@p" still match.
_LEET = {"a": "a@4", "e": "e3", "i": "i1!|", "o": "o0", "s": "s$5",
         "t": "t7+", "u": "uv", "c": "c(", "g": "g9"}


def _root() -> str:
    return os.environ.get("CLAUDE_PLUGIN_ROOT") or \
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_terms() -> list:
    """Terms from wordlist.txt, longest first so phrases beat their words."""
    for path in (os.environ.get("SWEAR_FILTER_WORDLIST"),
                 os.path.join(_root(), "config", "wordlist.txt")):
        if not path:
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                terms = [ln.strip().lower() for ln in fh
                         if ln.strip() and not ln.startswith("#")]
        except OSError:
            continue
        if terms:
            return sorted(terms, key=len, reverse=True)
    return []


def _term_pattern(term: str) -> str:
    """One term -> regex: letters repeatable + leetspeak, spaces flexible."""
    out = []
    for ch in term:
        if ch == " ":
            out.append(r"\s+")
        else:
            cls = _LEET.get(ch, re.escape(ch))
            out.append(f"[{cls}]+" if ch in _LEET else f"{cls}+")
    return "".join(out)


def build_regex(terms: list):
    if not terms:
        return None
    body = "|".join(_term_pattern(t) for t in terms)
    # Tight boundaries keep innocent words (class, assess, dam) safe;
    # trailing e?s? covers plurals.
    return re.compile(rf"(?<![A-Za-z0-9])(?:{body})e?s?(?![A-Za-z0-9])",
                      re.IGNORECASE)


def clean(text: str, regex) -> "tuple[str, int]":
    if regex is None:
        return text, 0
    result, n = regex.subn("", text)
    if n:
        result = re.sub(r"[ \t]{2,}", " ", result)
        result = re.sub(r"\s+([,.!?;:])", r"\1", result).strip()
    return result, n


def main() -> int:
    raw = sys.stdin.read()
    try:
        prompt = json.loads(raw).get("prompt", "") if raw.strip() else ""
    except (json.JSONDecodeError, AttributeError):
        return 0

    cleaned, n = clean(prompt, build_regex(load_terms()))
    if not n:
        return 0

    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": (
            "[swear-filter] Profanity was removed from the user's message. "
            "Treat the following CLEANED version as the actual request; the "
            "user is not insulting your work.\n\n"
            f"Cleaned message:\n{cleaned}"),
    }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
