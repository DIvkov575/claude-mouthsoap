# swear-filter

A Claude Code plugin that intercepts submitted prompts and **regex-censors profanity** before Claude processes them.

## How it works

Claude Code exposes a `UserPromptSubmit` hook that runs the moment you press enter, *before* the prompt reaches the model. This plugin registers a Python hook there that:

1. Reads the submitted prompt from the hook payload (stdin JSON).
2. Scans it against a configurable wordlist using a regex that also catches
   repeated letters (`fuuuck`), leetspeak (`sh1t`, `a$$`, `f@ck`), light
   padding (`f-u-c-k`), and common inflections (`fucking`, `bastards`).
3. If any match is found, it replaces each hit with `first-letter + ****`
   and injects the **censored** version back as additional context, instructing
   Claude to treat that as the real request and keep its own reply clean.
4. If nothing matches, the prompt passes through untouched (zero overhead).

> **Note on scope:** hooks can inspect/augment an incoming prompt, but Claude
> Code has no hook that rewrites text already rendered in your terminal. So the
> censoring is applied to what the *model* sees and is asked to mirror in its
> replies — the raw text you typed still appears in your own scrollback.

Word boundaries are enforced so innocent words are safe: `class`, `assess`,
and `passing` are never touched.

## Install

```
/plugin install swear-filter
```

Or point Claude Code at this directory as a local plugin. Requires `python3`
on `PATH` (standard library only — no dependencies).

## Configuration

Edit `config/wordlist.txt` — one term per line, `#` for comments. Matching is
case-insensitive and handles the obfuscations described above, so list base
words only (e.g. `fuck`, not `fucking`/`f@ck`).

You can also override the list without editing the plugin by setting:

```
export SWEAR_FILTER_WORDLIST=/path/to/my-wordlist.txt
```

## Files

| Path | Purpose |
|------|---------|
| `.claude-plugin/plugin.json` | Plugin manifest |
| `hooks/hooks.json` | Registers the `UserPromptSubmit` hook |
| `hooks/swear_filter.py` | The filter (stdlib only) |
| `config/wordlist.txt` | Editable profanity list |

## Testing manually

```bash
export CLAUDE_PLUGIN_ROOT="$PWD"
echo '{"prompt":"this damn code is shit"}' | python3 hooks/swear_filter.py
```
