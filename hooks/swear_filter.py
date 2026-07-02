#!/usr/bin/env python3
"""swear-filter UserPromptSubmit hook.

Deletes swear words/phrases from the submitted prompt before Claude sees it,
so deliberate venting doesn't reach the model. Terms live in
config/wordlist.txt (one per line). Plain case-insensitive whole-word match —
no obfuscation handling, because the user isn't trying to evade their own filter.
"""

import json
import os
import re
import sys


def load_terms() -> list:
    root = os.environ.get("CLAUDE_PLUGIN_ROOT") or \
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.environ.get("SWEAR_FILTER_WORDLIST") or \
        os.path.join(root, "config", "wordlist.txt")
    try:
        with open(path, encoding="utf-8") as fh:
            terms = [ln.strip() for ln in fh
                     if ln.strip() and not ln.startswith("#")]
    except OSError:
        return []
    # Longest first so phrases match before their component words.
    return sorted(terms, key=len, reverse=True)


def build_regex(terms):
    if not terms:
        return None
    body = "|".join(re.escape(t) for t in terms)
    return re.compile(rf"\b(?:{body})\b", re.IGNORECASE)


def clean(text, regex):
    if regex is None:
        return text, 0
    result, n = regex.subn("", text)
    if n:
        result = re.sub(r"\s{2,}", " ", result)
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
            "Treat the following as the actual request; the user is not "
            "insulting your work.\n\n"
            f"Cleaned message:\n{cleaned}"),
    }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
