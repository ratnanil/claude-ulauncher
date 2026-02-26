# ulauncher-claude-sessions

A [Ulauncher](https://ulauncher.io/) extension to browse, search, and resume [Claude Code](https://claude.ai/code) sessions directly from your launcher.

## Features

- Browse all Claude Code sessions with a summary table in your browser
- Search resumable sessions by topic, folder, or session ID
- Resume a session in a new terminal with one keypress
- View a rendered HTML transcript of any conversation

## Requirements

- Ulauncher (API v2)
- `jq` installed and on `$PATH`
- `gnome-terminal` (used to open Claude Code for session resumption)
- Claude Code CLI (`claude`) installed

## Installation

Clone or copy this directory into your Ulauncher extensions folder:

```
~/.local/share/ulauncher/extensions/ulauncher-claude-sessions/
```

Then restart Ulauncher and enable the extension in preferences.

## Usage

### Default keyword: `cc`

| Input | Action |
|-------|--------|
| `cc` (no query) | Opens an HTML table of all sessions in your browser |
| `cc <query>` | Filters resumable sessions by topic, folder, or session ID |

When searching, each match shows two entries:
- **Session entry** — press Enter to resume it in a new `gnome-terminal`
- **View transcript** — press Enter to open the conversation as HTML in your browser

Up to 4 session matches are shown (8 list items total).

### What "resumable" means

A session is considered resumable if its backing `.jsonl` file still exists under `~/.claude/projects/`. Sessions whose files have been deleted show in the overview table but are excluded from search results.

### Session topics

The topic shown for each session comes from one of two sources, in order of preference:

1. **AI-generated summary** from `sessions-index.json` — Claude Code writes this file per project and includes a short descriptive title (e.g. "ZHAW drive mounting with GNOME Keyring"). Coverage grows automatically as you use Claude Code.
2. **First prompt** from `~/.claude/history.jsonl` — used as a fallback when no summary is available yet.

## File overview

```
main.py        — Extension entry point; all logic lives here
sessions.jq    — jq filter that parses ~/.claude/history.jsonl into session metadata
manifest.json  — Ulauncher extension manifest (keyword, API version)
versions.json  — Ulauncher version compatibility declaration
images/        — Extension icon
```

## How it works

1. **Session discovery**: `~/.claude/history.jsonl` is parsed with `jq` using `sessions.jq`. Each entry in the history file represents a message; they are grouped by `sessionId`, then summarised (topic, folder, date, message count).

2. **Resumability check**: For each session, `main.py` checks whether `~/.claude/projects/<project-slug>/<session_id>.jsonl` exists on disk. Only sessions with an existing file are offered for resumption.

   The project slug is derived from the project path by replacing any non-alphanumeric character (slashes, underscores, dots, spaces, …) with a hyphen and prepending one. For example `/home/rata/.local/share/my_project` → `-home-rata--local-share-my-project`. This matches exactly how Claude Code itself names these directories.

3. **Topic resolution**: After loading sessions from history, `main.py` reads all `sessions-index.json` files under `~/.claude/projects/` and builds a `session_id → summary` map. Sessions that appear in this index get the AI-generated summary as their topic; the rest keep the first prompt from `history.jsonl`.

4. **Transcript rendering**: When viewing a transcript, `main.py` reads the session's `.jsonl` file line by line, extracts `user` and `assistant` messages (handling plain strings, text blocks, tool calls, and tool results), and writes a self-contained HTML file to `/tmp/`.

5. **Session resumption**: Runs:
   ```
   gnome-terminal -- zsh -ic "cd '<project>'; claude --resume <session_id>; exec zsh"
   ```

## Data locations

| Path | Purpose |
|------|---------|
| `~/.claude/history.jsonl` | Master list of all Claude Code activity (source of session metadata) |
| `~/.claude/projects/` | Per-project session files; used to check resumability and read transcripts |
| `~/.claude/projects/*/sessions-index.json` | AI-generated session summaries written by Claude Code; used as topic when available |

## Customisation

- **Keyword**: Change the default `cc` keyword in Ulauncher's extension preferences.
- **Terminal**: Replace `gnome-terminal` in `main.py:219` with your preferred terminal emulator.
- **Result count**: The cap of 4 matches is set at `main.py:209` (`matches[:4]`).
- **Session filter**: `sessions.jq` controls which fields are extracted and how sessions are sorted (currently newest-first by date).
