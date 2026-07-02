#!/usr/bin/env python3
"""swear-filter UserPromptSubmit hook.

Deletes swearing from the submitted prompt before Claude sees it, so
deliberate venting doesn't reach the model. Stems live in config/wordlist.txt
(one per line). Each stem matches its whole word family — inflections
(shit -> shitty, shits; fuck -> fucking, fucker) — and tolerates stretched
letters (fuuuck, shiiit). Case-insensitive. No leetspeak/obfuscation handling:
the user isn't trying to evade their own filter.
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
            terms = [ln.strip().lower() for ln in fh
                     if ln.strip() and not ln.startswith("#")]
    except OSError:
        return []
    # Longest first so phrases match before their component words.
    return sorted(terms, key=len, reverse=True)


# Real English inflection/derivation suffixes, so a stem matches its word
# family (shit -> shitty/shits/shithead) but NOT unrelated words that merely
# start with it (shiitake, crapshoot, crappie).
_SUFFIX = (r"(?:s|es|ed|ing|in|er|ers|y|ty|ies|ier|iest|"
           r"head|heads|hole|holes|face|bag|bags)?")


def _word(stem: str) -> str:
    # Each letter repeatable (fuuuck) + a bounded inflection suffix.
    return "".join(re.escape(c) + "+" for c in stem) + _SUFFIX


def build_regex(terms):
    if not terms:
        return None
    body = "|".join(r"\s+".join(_word(w) for w in t.split()) for t in terms)
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
