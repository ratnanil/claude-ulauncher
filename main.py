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
JQ_FILTER = os.path.join(os.path.dirname(__file__), "sessions.jq")


def load_sessions():
    """Load sessions using the same jq filter the user already has."""
    try:
        result = subprocess.run(
            ["jq", "-s", "-f", JQ_FILTER, HISTORY_FILE],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception:
        pass
    return []


def generate_html_table(sessions):
    """Generate an HTML table and return the file path."""
    rows = ""
    for s in sessions:
        rows += (
            f"<tr><td>{s['session_id']}</td><td>{s['topic']}</td>"
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
    ]


class ClaudeSessionsExtension(Extension):
    def __init__(self):
        super().__init__()
        self.subscribe(KeywordQueryEvent, QueryHandler())


class QueryHandler(EventListener):
    def on_event(self, event, extension):
        sessions = load_sessions()
        arg = event.get_argument()

        if not arg:
            html_path = generate_html_table(sessions)
            return RenderResultListAction([
                ExtensionResultItem(
                    icon="images/icon.png",
                    name=f"View all sessions ({len(sessions)})",
                    description="Open HTML table in browser",
                    on_enter=OpenUrlAction(f"file://{html_path}"),
                ),
            ])

        matches = search_sessions(sessions, arg)

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
            items.append(ExtensionResultItem(
                icon="images/icon.png",
                name=f"{s['topic']}",
                description=f"{folder} \u00b7 {s['date']} \u00b7 {s['messages']} msgs",
                on_enter=RunScriptAction(
                    f'gnome-terminal -- bash -c "cd ~/**/\'{folder}\' 2>/dev/null; claude --resume {sid}"',
                    [],
                ),
            ))

        return RenderResultListAction(items)


if __name__ == "__main__":
    ClaudeSessionsExtension().run()
