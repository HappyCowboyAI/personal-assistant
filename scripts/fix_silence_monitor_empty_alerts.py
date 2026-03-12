#!/usr/bin/env python3
"""
Fix: Get Recent Alerts node stops workflow when alert_history is empty.

On first run (or when no recent alerts exist), Supabase returns [].
n8n treats empty array as 0 output items and stops the branch.

Fix: Set alwaysOutputData=true on "Get Recent Alerts" node so the
workflow continues even when there are no recent alerts.
"""

import json
import os
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

WORKFLOW_ID = "6FsYIe3tYj0HfRY2"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}


def main():
    print("Fetching Silence Contract Monitor workflow (live)...")
    resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{WORKFLOW_ID}", headers=HEADERS)
    resp.raise_for_status()
    wf = resp.json()
    nodes = wf["nodes"]
    print(f"  {len(nodes)} nodes")

    changes = 0

    for node in nodes:
        if node["name"] == "Get Recent Alerts":
            if node.get("onError") == "continueRegularOutput" or node.get("alwaysOutputData"):
                print("  Get Recent Alerts: already has alwaysOutputData — skipping")
            else:
                node["onError"] = "continueRegularOutput"
                # Also set in options to ensure empty arrays still produce output
                if "options" not in node["parameters"]:
                    node["parameters"]["options"] = {}
                node["parameters"]["options"]["response"] = {
                    "response": {"neverError": True}
                }
                print("  Set Get Recent Alerts: onError=continueRegularOutput")
                changes += 1

        # Also fix Get Active Users — same issue if no users
        if node["name"] == "Get Active Users":
            if node.get("onError") == "continueRegularOutput":
                print("  Get Active Users: already fixed — skipping")
            else:
                node["onError"] = "continueRegularOutput"
                if "options" not in node["parameters"]:
                    node["parameters"]["options"] = {}
                node["parameters"]["options"]["response"] = {
                    "response": {"neverError": True}
                }
                print("  Set Get Active Users: onError=continueRegularOutput")
                changes += 1

    if changes == 0:
        print("\n  No changes needed")
        return

    # Push
    print(f"\n=== Pushing workflow ({changes} nodes updated) ===")
    payload = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": wf.get("settings", {}),
        "staticData": wf.get("staticData"),
    }
    resp = requests.put(
        f"{N8N_BASE_URL}/api/v1/workflows/{WORKFLOW_ID}",
        headers=HEADERS,
        json=payload,
    )
    resp.raise_for_status()
    print(f"  HTTP 200, {len(resp.json()['nodes'])} nodes")

    # Sync
    print("\n=== Re-fetching and syncing local file ===")
    final_resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{WORKFLOW_ID}", headers=HEADERS)
    final_resp.raise_for_status()
    final = final_resp.json()
    path = os.path.join(REPO_ROOT, "n8n", "workflows", "Silence Contract Monitor.json")
    with open(path, "w") as f:
        json.dump(final, f, indent=4)
    print(f"  Synced {path}")

    print("\nDone! Empty response handling fixed for Get Recent Alerts and Get Active Users.")


if __name__ == "__main__":
    main()
