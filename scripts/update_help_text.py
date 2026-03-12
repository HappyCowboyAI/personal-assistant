#!/usr/bin/env python3
"""
Update the help command text in Slack Events Handler
- Example-driven style with real commands users can copy
- Order: Personalize → Ask → Briefings → Pause/Resume
"""

import json
import os
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

SLACK_EVENTS_ID = "QuQbIaWetunUOFUW"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}


def fetch_workflow(wf_id):
    resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def push_workflow(wf_id, wf):
    payload = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
               "settings": wf.get("settings", {}), "staticData": wf.get("staticData")}
    resp = requests.put(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}", headers=HEADERS, json=payload)
    resp.raise_for_status()
    return resp.json()


def sync_local(wf, filename):
    path = os.path.join(REPO_ROOT, "n8n", "workflows", filename)
    with open(path, "w") as f:
        json.dump(wf, f, indent=4)
    print(f"  Synced {path}")


# Example-driven help text — real commands users can copy
NEW_HELP_CODE = r"""const data = $('Route by State').first().json;
let text = '';
const r = data.subRoute;

if (r === 'help') {
  text = "Here are things you can type to me:\n\n" +
    "*Change how I look and sound:*\n" +
    "`rename Jarvis` \u2014 now I\u2019m Jarvis\n" +
    "`emoji :rocket:` \u2014 now I\u2019m a rocket\n" +
    "`persona friendly and uses sports metaphors` \u2014 now I talk like a coach\n" +
    "`scope team` \u2014 now I brief you on your whole team (also: `my deals`, `pipeline`)\n\n" +
    "*Ask a question (works in any channel):*\n" +
    "`/bs how is the Acme deal going?`\n" +
    "`/bs what meetings does Sarah have this week?`\n\n" +
    "*Get a briefing:*\n" +
    "`brief` \u2014 today\u2019s themed digest\n" +
    "`brief risk` \u2014 which deals need attention\n" +
    "`brief momentum` \u2014 what\u2019s going well\n" +
    "`brief engagement` \u2014 who went hot or cold\n" +
    "`brief review` \u2014 the week in review\n" +
    "`brief full` \u2014 everything\n\n" +
    "*Pause or restart:*\n" +
    "`stop digest` \u2014 no more morning briefings\n" +
    "`resume digest` \u2014 bring them back";
} else if (r === 'stop_digest') {
  text = "Understood. I\u2019ve paused your morning briefings.\n\nI\u2019ll still prep you before meetings and flag urgent risks. Just type `resume digest` whenever you want them back.";
} else if (r === 'resume_digest') {
  text = "Morning briefings are back on. You\u2019ll get the next one tomorrow at 6am.";
} else {
  text = "I didn\u2019t catch that. Try one of these:\n\n" +
    "`brief` \u2014 today\u2019s themed digest\n" +
    "`brief risk` \u2014 deals that need attention\n" +
    "`/bs how is the Acme deal going?` \u2014 ask me anything\n" +
    "`rename Jarvis` \u2014 change my name\n" +
    "`help` \u2014 see everything I can do";
}

const needsUpdate = (r === 'stop_digest' || r === 'resume_digest');
const digestEnabled = (r === 'resume_digest');

return [{ json: { ...data, responseText: text, needsUpdate, digestEnabled } }];"""


def upgrade(wf):
    print("\n=== Updating help text ===")
    updated = False
    for node in wf["nodes"]:
        if node["name"] == "Build Help Response":
            node["parameters"]["jsCode"] = NEW_HELP_CODE
            updated = True
            print("  Updated Build Help Response node")

    if not updated:
        print("  WARNING: Build Help Response node not found!")
    return wf


def main():
    print("Fetching Slack Events Handler...")
    wf = fetch_workflow(SLACK_EVENTS_ID)
    print(f"  {len(wf['nodes'])} nodes")

    wf = upgrade(wf)

    print("\n=== Pushing workflow ===")
    result = push_workflow(SLACK_EVENTS_ID, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")

    print("\n=== Syncing local file ===")
    sync_local(result, "Slack Events Handler.json")

    print("\nDone! Help text updated to example-driven style.")


if __name__ == "__main__":
    main()
