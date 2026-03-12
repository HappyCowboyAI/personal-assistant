#!/usr/bin/env python3
"""
Hot-fix: Change connection flow so Execute Insights gets data from Is Valid Insight?
instead of from Send Insights Generating (which outputs a Slack API response).

Before: Is Valid Insight? → Send Insights Generating → Execute Insights
After:  Is Valid Insight? → [parallel] Send Insights Generating + Execute Insights
"""

import json
import os
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

SLACK_EVENTS_ID = "QuQbIaWetunUOFUW"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}


def main():
    # Fetch current Events Handler
    print("Fetching Slack Events Handler...")
    resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{SLACK_EVENTS_ID}", headers=HEADERS)
    resp.raise_for_status()
    wf = resp.json()
    print(f"  {len(wf['nodes'])} nodes")

    connections = wf["connections"]

    # Verify current broken flow: Is Valid Insight? → Send Generating → Execute Insights
    is_valid_conns = connections.get("Is Valid Insight?", {}).get("main", [])
    send_gen_conns = connections.get("Send Insights Generating", {}).get("main", [])

    print("\n  Current connections:")
    print(f"  Is Valid Insight? outputs: {json.dumps(is_valid_conns)}")
    print(f"  Send Insights Generating outputs: {json.dumps(send_gen_conns)}")

    # Fix: Make Is Valid Insight? (true branch) connect to BOTH nodes in parallel
    # True branch = index 0, False branch = index 1
    if len(is_valid_conns) >= 1:
        true_branch = is_valid_conns[0]
        has_generating = any(c["node"] == "Send Insights Generating" for c in true_branch)
        has_execute = any(c["node"] == "Execute Insights" for c in true_branch)

        if has_generating and not has_execute:
            # Add Execute Insights to the true branch (parallel with Send Generating)
            true_branch.append({"node": "Execute Insights", "type": "main", "index": 0})
            print("\n  Added Execute Insights to Is Valid Insight? true branch (parallel)")

            # Remove the connection from Send Insights Generating → Execute Insights
            if "Send Insights Generating" in connections:
                old_gen_conns = connections["Send Insights Generating"].get("main", [[]])
                print(f"  Removing Send Generating → Execute Insights connection")
                connections["Send Insights Generating"]["main"] = [[]]  # no output

            print(f"\n  Updated connections:")
            print(f"  Is Valid Insight? true: {json.dumps(true_branch)}")
        elif has_execute:
            print("\n  Execute Insights already connected to Is Valid Insight? — no fix needed")
            return
        else:
            print("\n  ERROR: Unexpected connection structure")
            return
    else:
        print("\n  ERROR: Is Valid Insight? has no outputs")
        return

    # Push updated workflow
    print("\n=== Pushing Slack Events Handler ===")
    payload = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": connections,
        "settings": wf.get("settings", {}),
        "staticData": wf.get("staticData")
    }
    resp = requests.put(f"{N8N_BASE_URL}/api/v1/workflows/{SLACK_EVENTS_ID}", headers=HEADERS, json=payload)
    resp.raise_for_status()
    result = resp.json()
    print(f"  HTTP 200, {len(result['nodes'])} nodes")

    # Sync local
    path = os.path.join(REPO_ROOT, "n8n", "workflows", "Slack Events Handler.json")
    with open(path, "w") as f:
        json.dump(result, f, indent=4)
    print(f"  Synced {path}")

    print("\nDone! Flow is now:")
    print("  Is Valid Insight? → [parallel] Send Insights Generating + Execute Insights")
    print("  Execute Insights now gets channelId etc. from Is Valid Insight? output")
    print("\nTry running 'insights' in Slack again.")


if __name__ == "__main__":
    main()
