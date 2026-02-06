import json
import os
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


def session_file_exists(session):
    """Check if the session file still exists on disk."""
    project = session.get("project", "")
    sid = session.get("session_id", "")
    dashed = "-" + project.strip("/").replace("/", "-")
    return os.path.exists(os.path.join(PROJECTS_DIR, dashed, f"{sid}.jsonl"))


def load_all_sessions():
    """Load all sessions and tag each with a resumable flag."""
    try:
        result = subprocess.run(
            ["jq", "-s", "-f", JQ_FILTER, HISTORY_FILE],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            sessions = json.loads(result.stdout)
            for s in sessions:
                s["resumable"] = session_file_exists(s)
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
        for s in matches[:8]:
            sid = s["session_id"]
            folder = s["folder"]
            project = s.get("project", "~")
            items.append(ExtensionResultItem(
                icon="images/icon.png",
                name=f"{s['topic']}",
                description=f"{sid[:8]} \u00b7 {folder} \u00b7 {s['date']} \u00b7 {s['messages']} msgs",
                on_enter=RunScriptAction(
                    f'gnome-terminal -- zsh -ic "cd \'{project}\'; claude --resume {sid}; exec zsh"',
                    [],
                ),
            ))

        return RenderResultListAction(items)


if __name__ == "__main__":
    ClaudeSessionsExtension().run()
