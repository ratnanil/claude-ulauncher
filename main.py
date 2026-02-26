import html
import json
import os
import re
import subprocess
import tempfile

from ulauncher.api.client.Extension import Extension
from ulauncher.api.client.EventListener import EventListener
from ulauncher.api.shared.event import KeywordQueryEvent
from ulauncher.api.shared.item.ExtensionResultItem import ExtensionResultItem
from ulauncher.api.shared.action.RenderResultListAction import RenderResultListAction
from ulauncher.api.shared.action.OpenUrlAction import OpenUrlAction
from ulauncher.api.shared.action.RunScriptAction import RunScriptAction

HISTORY_FILE = os.path.expanduser("~/.claude/history.jsonl")
PROJECTS_DIR = os.path.expanduser("~/.claude/projects")
JQ_FILTER = os.path.join(os.path.dirname(__file__), "sessions.jq")
TMPDIR = tempfile.gettempdir()


def project_slug(project):
    """Convert a project path to the directory name Claude Code uses.

    Claude Code replaces any non-alphanumeric character (slashes, underscores,
    dots, spaces, …) with a hyphen when deriving the project directory name.
    """
    return "-" + re.sub(r"[^a-zA-Z0-9-]", "-", project.strip("/"))


def session_file_exists(session):
    """Check if the session file still exists on disk."""
    project = session.get("project", "")
    sid = session.get("session_id", "")
    return os.path.exists(os.path.join(PROJECTS_DIR, project_slug(project), f"{sid}.jsonl"))


def load_summaries():
    """Build a session_id → summary map from all sessions-index.json files."""
    summaries = {}
    try:
        for proj_dir in os.listdir(PROJECTS_DIR):
            idx_path = os.path.join(PROJECTS_DIR, proj_dir, "sessions-index.json")
            if not os.path.isfile(idx_path):
                continue
            with open(idx_path) as f:
                data = json.load(f)
            for entry in data.get("entries", []):
                sid = entry.get("sessionId")
                summary = (entry.get("summary") or "").strip()
                if sid and summary and not summary.startswith("API Error"):
                    summaries[sid] = summary
    except Exception:
        pass
    return summaries


def load_all_sessions():
    """Load all sessions and tag each with a resumable flag."""
    try:
        result = subprocess.run(
            ["jq", "-s", "-f", JQ_FILTER, HISTORY_FILE],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            sessions = json.loads(result.stdout)
            summaries = load_summaries()
            for s in sessions:
                s["resumable"] = session_file_exists(s)
                sid = s.get("session_id", "")
                if sid in summaries:
                    s["topic"] = summaries[sid]
            return sessions
    except Exception:
        pass
    return []


def generate_html_table(sessions):
    """Generate an HTML table and return the file path."""
    rows = ""
    for s in sessions:
        cls = "" if s.get("resumable") else ' class="expired"'
        rows += (
            f"<tr{cls}><td>{s['session_id'][:8]}</td><td>{s['topic']}</td>"
            f"<td>{s['folder']}</td><td>{s['date']}</td>"
            f"<td>{s['messages']}</td></tr>\n"
        )

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Claude Sessions</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
  th {{ background: #4A90D9; color: white; position: sticky; top: 0; }}
  tr:nth-child(even) {{ background: #f9f9f9; }}
  tr:hover {{ background: #e9e9e9; }}
  tr.expired {{ color: #888; }}
</style></head>
<body>
<h2>Claude Code Sessions ({len(sessions)})</h2>
<table>
<tr><th>Session</th><th>Topic</th><th>Folder</th><th>Date</th><th>Messages</th></tr>
{rows}
</table></body></html>"""

    path = os.path.join(tempfile.gettempdir(), "claude-sessions.html")
    with open(path, "w") as f:
        f.write(html)
    return path


def session_file_path(session):
    """Return the path to a session's jsonl file."""
    project = session.get("project", "")
    sid = session.get("session_id", "")
    return os.path.join(PROJECTS_DIR, project_slug(project), f"{sid}.jsonl")


def extract_text(content):
    """Extract readable text from a message content field."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    name = block.get("name", "tool")
                    parts.append(f"[Tool: {name}]")
                elif block.get("type") == "tool_result":
                    inner = block.get("content", "")
                    if isinstance(inner, str) and inner:
                        parts.append(f"[Result: {inner[:200]}]")
        return "\n".join(parts)
    return ""


def generate_transcript_html(session):
    """Render a session transcript as a readable HTML page."""
    path = session_file_path(session)
    messages = []
    with open(path) as f:
        for line in f:
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    body = ""
    for msg in messages:
        role = msg.get("type")
        if role not in ("user", "assistant"):
            continue
        content = msg.get("message", {})
        if isinstance(content, dict):
            content = content.get("content", "")
        text = extract_text(content).strip()
        if not text:
            continue
        escaped = html.escape(text)
        cls = "user" if role == "user" else "assistant"
        label = "You" if role == "user" else "Claude"
        body += f'<div class="msg {cls}"><span class="label">{label}</span><pre>{escaped}</pre></div>\n'

    sid = session.get("session_id", "")[:8]
    topic = html.escape(session.get("topic", ""))
    page = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Session {sid}</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem; max-width: 900px; margin: 2rem auto; }}
  .msg {{ margin: 1rem 0; padding: 1rem; border-radius: 8px; }}
  .msg pre {{ white-space: pre-wrap; word-wrap: break-word; margin: 0.5rem 0 0 0; font-size: 0.9rem; }}
  .label {{ font-weight: bold; font-size: 0.85rem; text-transform: uppercase; }}
  .user {{ background: #e8f0fe; }}
  .assistant {{ background: #f0f0f0; }}
  h2 {{ border-bottom: 1px solid #ddd; padding-bottom: 0.5rem; }}
</style></head>
<body>
<h2>{topic} <small style="color:#888">({sid})</small></h2>
{body}
</body></html>"""

    out = os.path.join(TMPDIR, f"claude-transcript-{sid}.html")
    with open(out, "w") as f:
        f.write(page)
    return out


def search_sessions(sessions, query):
    """Filter sessions by topic or folder."""
    query = query.lower()
    return [
        s for s in sessions
        if query in s.get("topic", "").lower()
        or query in s.get("folder", "").lower()
        or query in s.get("session_id", "").lower()
    ]


class ClaudeSessionsExtension(Extension):
    def __init__(self):
        super().__init__()
        self.subscribe(KeywordQueryEvent, QueryHandler())


class QueryHandler(EventListener):
    def on_event(self, event, extension):
        all_sessions = load_all_sessions()
        arg = event.get_argument()

        if not arg:
            html_path = generate_html_table(all_sessions)
            resumable = sum(1 for s in all_sessions if s.get("resumable"))
            return RenderResultListAction([
                ExtensionResultItem(
                    icon="images/icon.png",
                    name=f"View all sessions ({len(all_sessions)}, {resumable} resumable)",
                    description="Open HTML table in browser",
                    on_enter=OpenUrlAction(f"file://{html_path}"),
                ),
            ])

        resumable = [s for s in all_sessions if s.get("resumable")]
        matches = search_sessions(resumable, arg)

        if not matches:
            return RenderResultListAction([
                ExtensionResultItem(
                    icon="images/icon.png",
                    name="No matching sessions",
                    description=f'No sessions matching "{arg}"',
                    on_enter=RenderResultListAction([]),
                ),
            ])

        items = []
        for s in matches[:4]:
            sid = s["session_id"]
            folder = s["folder"]
            project = s.get("project", "~")
            transcript_path = generate_transcript_html(s)
            items.append(ExtensionResultItem(
                icon="images/icon.png",
                name=f"{s['topic']}",
                description=f"{sid[:8]} \u00b7 {folder} \u00b7 {s['date']} \u00b7 {s['messages']} msgs \u00b7 Enter to resume",
                on_enter=RunScriptAction(
                    f'gnome-terminal -- zsh -ic "cd \'{project}\'; claude --resume {sid}; exec zsh"',
                    [],
                ),
            ))
            items.append(ExtensionResultItem(
                icon="images/icon.png",
                name=f"\u2514 View transcript",
                description=f"{sid[:8]} \u00b7 Open conversation in browser",
                on_enter=OpenUrlAction(f"file://{transcript_path}"),
            ))

        return RenderResultListAction(items)


if __name__ == "__main__":
    ClaudeSessionsExtension().run()
