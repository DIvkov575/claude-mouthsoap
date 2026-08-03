# swear-filter

A Claude Code plugin that intercepts submitted prompts containing profanity and **blocks them outright** before Claude ever ingests them — so the model never sees language aimed at its work, and never drifts out-of-distribution or burns tokens reacting to it.

## How it works

Claude Code exposes a `UserPromptSubmit` hook that runs the moment you press enter, *before* the prompt reaches the model. This plugin registers a Python hook there that:

1. Reads the submitted prompt from the hook payload (stdin JSON).
2. Scans it against a configurable wordlist (`config/wordlist.txt`) using a
   regex that also catches repeated letters (`fuuuck`) and common inflections
   (`fucking`, `shitty`, `bastards`).
3. If any match is found, it returns `decision:"block"` — Claude Code erases
   the prompt and never forwards it to the model. The `reason` field carries a
   suggested clean rewrite so you can resubmit quickly.
4. If nothing matches, the prompt passes through untouched (zero overhead).

> **Why block instead of rewrite-in-place:** `UserPromptSubmit` has no field
> that substitutes the text the model receives — a hook can only *add*
> `additionalContext` alongside the original prompt, or block it outright.
> Since the goal is to guarantee the model never sees the raw wording,
> blocking (and asking you to resubmit) is the only mechanism that achieves
> that; injecting a "cleaned" version alongside the original does not — the
> model still receives the raw text either way.
>
> **Note on scope:** the raw text you typed still appears in your own
> terminal scrollback — this plugin only controls what reaches the model.

Word boundaries are enforced so innocent words are safe: `class`, `assess`,
and `passing` are never touched.

## Install

```
/plugin install swear-filter
```

Or point Claude Code at this directory as a local plugin. Requires `python3`
on `PATH` (standard library only — no dependencies).

## Configuration

Edit `config/wordlist.txt`. One stem or phrase per line; `#` starts a
comment. Matching is case-insensitive and handles repeated letters and
inflections automatically, so list base words only (e.g. `shit` also catches
`shitty`/`shits`).

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
