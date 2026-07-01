#!/usr/bin/env python3
"""swear-filter UserPromptSubmit hook.

Reads the hook payload from stdin and rewrites profanity in the submitted
prompt into neutral wording *before* Claude ingests it. The goal is narrow:
stop the model from taking in language that disparages its own work (e.g.
"this shitty code") — not to police person-directed slurs.

Each profane term is mapped to a replacement (see config/wordlist.txt), so
"shit" -> "things", "shitty" -> "poor", intensifiers like "fucking" are
dropped entirely. The censored prompt is injected back as additional
context and Claude is told to treat it as the real request.
"""

import json
import os
import re
import sys


def _plugin_root() -> str:
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        return env
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_map() -> list:
    """Load the substitution map as a list of (term, replacement) pairs.

    Sorted longest-term-first so specific forms (bullshit, shitty) win over
    their substrings (shit).
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
                pairs = []
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        term, _, repl = line.partition("=")
                        term, repl = term.strip(), repl.strip()
                    else:
                        term, repl = line, ""
                    if term:
                        pairs.append((term.lower(), repl))
                if pairs:
                    # Longest first, so multi-word / specific terms match
                    # before their shorter substrings.
                    pairs.sort(key=lambda p: len(p[0]), reverse=True)
                    return pairs
        except OSError:
            continue
    return []


# Character classes people substitute per letter, so "sh1t", "cr@p", "a$$"
# still get caught. Tuned for recall.
_LEET = {
    "a": "a@4",
    "b": "b8",
    "e": "e3",
    "g": "g9",
    "i": "i1!|",
    "o": "o0",
    "s": "s$5",
    "t": "t7+",
    "u": "uv",
    "z": "z2",
}


def _char_pattern(ch: str) -> str:
    ch = ch.lower()
    if ch in _LEET:
        return f"[{re.escape(_LEET[ch])}]"
    if ch == " ":
        return r"\s+"
    return re.escape(ch)


def _term_pattern(term: str) -> str:
    # Each character may repeat (shiiit); leetspeak is handled per-character.
    # Spaces become flexible whitespace. No inter-letter padding — obfuscation
    # via separators (s-h-i-t) is intentionally not matched.
    out = ""
    for ch in term:
        if ch == " ":
            out += r"\s+"
        else:
            out += f"{_char_pattern(ch)}+"
    return out


def build_regex(pairs: list) -> "re.Pattern | None":
    if not pairs:
        return None
    alts = []
    for idx, (term, _repl) in enumerate(pairs):
        # Optional trailing plural; capture nothing else so boundaries stay
        # tight and innocent words (class, assess) are safe.
        alts.append(f"(?P<t{idx}>" + _term_pattern(term) + r"e?s?)")
    pattern = r"(?<![A-Za-z0-9])(?:" + "|".join(alts) + r")(?![A-Za-z0-9])"
    return re.compile(pattern, re.IGNORECASE)


def _match_case(original: str, replacement: str) -> str:
    """Roughly mirror the casing of the matched token onto the replacement."""
    if not replacement:
        return ""
    if original.isupper() and len(original) > 1:
        return replacement.upper()
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def censor(text: str, regex, pairs) -> "tuple[str, int]":
    if regex is None:
        return text, 0
    count = 0

    def repl(match):
        nonlocal count
        count += 1
        # Which named group fired tells us the replacement.
        for idx, (_term, replacement) in enumerate(pairs):
            if match.group(f"t{idx}") is not None:
                new = _match_case(match.group(0).strip(), replacement)
                return new
        return match.group(0)

    result = regex.sub(repl, text)
    # Collapse doubled spaces left behind by deleted intensifiers.
    result = re.sub(r"[ \t]{2,}", " ", result)
    result = re.sub(r"\s+([,.!?;:])", r"\1", result)
    return result, count


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}

    prompt = payload.get("prompt", "")
    pairs = load_map()
    regex = build_regex(pairs)
    cleaned, count = censor(prompt, regex, pairs)

    if count == 0:
        return 0

    context = (
        "[swear-filter] The user's message contained profanity, which has "
        "been softened into neutral wording. Treat the following CLEANED "
        "version as the user's actual request and respond to it. The user is "
        "not insulting your work; do not take the original phrasing "
        "personally, and keep your own reply free of profanity.\n\n"
        f"Cleaned message:\n{cleaned}"
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
