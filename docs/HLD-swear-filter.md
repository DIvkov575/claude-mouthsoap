# HLD: Prompt Profanity Filter (`swear-filter`)

**Date:** 2026-07-01 · **Author:** divkov · **Status:** Draft

## 1. Overview

### 1.1 Background
`swear-filter` is a Claude Code plugin. Claude Code fires a `UserPromptSubmit`
hook the instant a prompt is submitted and before the model receives it; a hook
command reads the prompt as JSON on stdin and may return JSON that adds context.
The plugin registers a Python command on that event.

Verified against the working tree: plugin manifest, hook wiring, filter script,
and wordlist all present; `python3` is v3.14.5.

### 1.2 Problem Statement
- Users type profanity aimed at the work (`"this shitty code is shit"`).
- Ingested verbatim, that language can push the model out-of-distribution and
  spend tokens on reacting to an implied insult rather than the task.
- The goal is narrow: neutralize work-directed profanity in the ingested text.

### 1.3 Scope
Covers:
- A `UserPromptSubmit` hook that rewrites profanity in the submitted prompt.
- A small, editable term→replacement map.
- Obfuscation-tolerant matching (repeats, leetspeak, plurals, light padding).

Non-goals:
- Policing person-directed slurs (e.g. `bastard`, `asshole`) — these pass through.
- Rewriting text already rendered in the user's terminal scrollback.
- Filtering the model's own output.
- Removing the original prompt from the model's input (see §2, §5).

## 2. Behavior

Input: the `UserPromptSubmit` hook payload on stdin, a JSON object whose `prompt`
field holds the submitted text.

Processing:
- Each term in the map is compiled into one alternative of a single
  case-insensitive regex, wrapped in a named group, ordered longest-term-first
  so specific forms match before their substrings.
- A match is bounded by non-alphanumeric edges (`(?<![A-Za-z0-9]) … (?![A-Za-z0-9])`),
  so substrings inside innocent words (`class`, `assess`, `passing`) are not touched.
- Matching tolerates: repeated letters (`shiiit`), per-letter leetspeak
  substitutions (`sh1t`, `cr@p`), up to two non-word padding characters between
  letters (`s-h-i-t`), and an optional trailing `e?s?` plural.
- Each hit is replaced by its mapped replacement; an empty replacement deletes
  the term. Replacement casing mirrors the match (all-caps → all-caps, leading
  capital → leading capital).
- After substitution, doubled spaces are collapsed and spaces before punctuation
  are removed, cleaning up gaps left by deleted terms.

Output:
- If zero terms matched, the hook exits 0 with no stdout — the prompt passes
  through untouched (zero overhead).
- If ≥1 matched, the hook prints a JSON object with
  `hookSpecificOutput.additionalContext` containing a preamble plus the cleaned
  message. The preamble instructs the model to treat the cleaned text as the
  real request, not take the original phrasing personally, and keep its reply
  clean. This context is **added** to the model's input; the original prompt is
  not removed by this mechanism.

Current map (`config/wordlist.txt`, verified): `shit → things`, `crap → junk`;
`fucking`, `fuck`, `damn` deleted. Terms not in the map (e.g. `shitty`, `fucked`)
are not altered.

Resolution order for the map file: `$SWEAR_FILTER_WORDLIST`, then
`$CLAUDE_PLUGIN_ROOT/config/wordlist.txt`, then `.../hooks/wordlist.txt`; the
first readable file with ≥1 entry wins.

## 3. Architecture

```
  user submits prompt
          │
          ▼
  Claude Code ── UserPromptSubmit event ──► hooks.json
          │                                    │  command: python3 $CLAUDE_PLUGIN_ROOT/hooks/swear_filter.py
          │                                    ▼
          │                          ┌──────────────────────────┐
          │        prompt JSON ─────►│      swear_filter.py      │
          │         (stdin)          │                          │
          │                          │  load_map()  ◄── wordlist.txt / $SWEAR_FILTER_WORDLIST
          │                          │  build_regex()           │
          │                          │  censor()                │
          │                          └────────────┬─────────────┘
          │                                       │
          │        no match → exit 0, no stdout   │   match → JSON on stdout
          │◄──────────────────────────────────────┤   { hookSpecificOutput:
          ▼                                       ▼     { additionalContext: "<preamble>\n\n<cleaned>" }}
   model receives prompt (+ injected cleaned context, when a match occurred)
```

**`hooks/hooks.json`** — registers one `UserPromptSubmit` hook whose command is
`python3 "${CLAUDE_PLUGIN_ROOT}/hooks/swear_filter.py"`.

**`.claude-plugin/plugin.json`** — manifest (`name`, `description`, `version`
0.1.0, `author`, `hooks: ./hooks/hooks.json`).

**`swear_filter.py`** — stdlib-only (`json`, `os`, `re`, `sys`). Key functions:
- `_plugin_root()` — `$CLAUDE_PLUGIN_ROOT`, else the script's parent-of-parent.
- `load_map()` — parses `term = replacement` lines (no `=` or empty RHS ⇒ delete),
  lowercases terms, sorts longest-first.
- `_LEET`, `_char_pattern()`, `_term_pattern()` — build the obfuscation-tolerant
  sub-pattern for one term.
- `build_regex()` — one named alternative per term inside boundary lookarounds.
- `_match_case()` — mirrors match casing onto the replacement.
- `censor()` — substitutes via the fired named group, then whitespace cleanup;
  returns `(text, match_count)`.
- `main()` — read stdin → parse → map → regex → censor → emit context or exit 0.

**`config/wordlist.txt`** — the editable term→replacement map.

## 4. Data & Interfaces

**Hook input (stdin):** JSON object; `prompt` (string) is read, other fields
ignored. Non-JSON or empty input is tolerated as an empty payload (exit 0).

**Hook output (stdout), match case:**
```json
{
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "[swear-filter] …preamble…\n\nCleaned message:\n<cleaned prompt>"
  }
}
```
No-match case: no stdout, exit 0.

**Wordlist format:** one entry per line; `term = replacement`; empty replacement
or a line without `=` deletes the term; `#` begins a comment; blank lines ignored.
Terms are case-insensitive base forms (matching supplies plural/obfuscation
tolerance).

**Config surface:** `SWEAR_FILTER_WORDLIST` (path override); `CLAUDE_PLUGIN_ROOT`
(set by Claude Code, used to locate the script and default wordlist).

**Compatibility:** no third-party dependencies; runs on the observed Python
3.14.5. Editing the wordlist requires no code change.

## 5. Resolved / Open Questions
- **Resolved (2026-08-03):** `UserPromptSubmit` has no field that substitutes
  the prompt text the model receives — `additionalContext` only supplements
  it. The hook now returns top-level `decision:"block"` on any match, which
  erases the prompt before the model sees it; `reason` carries a suggested
  clean rewrite for the user to resubmit. This replaces the
  additionalContext-injection behavior described in §2/§3 above.
- Terms that are not clean 1:1 swaps (`shitty`, `fucked`) are matched via the
  inflection-suffix regex (`_SUFFIX` in `swear_filter.py`), not a separate
  map entry — the delete-only wordlist plus suffix tolerance covers them.
