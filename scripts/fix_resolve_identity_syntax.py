#!/usr/bin/env python3
"""
Fix: Missing comma in Resolve Assistant Identity code node.

The systemPrompt array has a missing comma after:
  '- End with a brief actionable recommendation when relevant.'
which causes "Unexpected string" SyntaxError.
"""

import json
import os
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

BACKSTORY_WORKFLOW_ID = "Yg5GB1byqB0qD-5wVDOAn"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}


def fetch_workflow(wf_id):
    resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def push_workflow(wf_id, wf):
    payload = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": wf.get("settings", {}),
        "staticData": wf.get("staticData"),
    }
    resp = requests.put(
        f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}", headers=HEADERS, json=payload
    )
    resp.raise_for_status()
    return resp.json()


def sync_local(wf, filename):
    path = os.path.join(REPO_ROOT, "n8n", "workflows", filename)
    with open(path, "w") as f:
        json.dump(wf, f, indent=4)
    print(f"  Synced {path}")


def main():
    print("Fetching Backstory SlackBot workflow (live)...")
    wf = fetch_workflow(BACKSTORY_WORKFLOW_ID)
    print(f"  {len(wf['nodes'])} nodes")

    # Find the Resolve Assistant Identity node
    target_node = None
    for node in wf["nodes"]:
        if node["name"] == "Resolve Assistant Identity":
            target_node = node
            break

    if not target_node:
        print("ERROR: 'Resolve Assistant Identity' node not found!")
        return

    code = target_node["parameters"]["jsCode"]

    # The bug: missing comma after the line ending with "when relevant.'"
    # Before: '- End with a brief actionable recommendation when relevant.'\n\n  '',
    # After:  '- End with a brief actionable recommendation when relevant.',\n\n  '',
    bad = "'- End with a brief actionable recommendation when relevant.'\n\n  '',"
    good = "'- End with a brief actionable recommendation when relevant.',\n\n  '',"

    if bad not in code:
        print("  Pattern not found — checking if already fixed...")
        if good in code:
            print("  Already fixed!")
        else:
            print("  ERROR: Could not locate the missing comma pattern.")
            # Print context around "actionable recommendation"
            idx = code.find("actionable recommendation")
            if idx >= 0:
                print(f"  Context: ...{repr(code[idx-20:idx+80])}...")
        return

    code = code.replace(bad, good)
    target_node["parameters"]["jsCode"] = code
    print("  Fixed: added missing comma after 'End with a brief actionable recommendation when relevant.'")

    print("\n=== Pushing workflow ===")
    result = push_workflow(BACKSTORY_WORKFLOW_ID, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")

    print("\n=== Re-fetching and syncing local file ===")
    final = fetch_workflow(BACKSTORY_WORKFLOW_ID)
    sync_local(final, "Backstory SlackBot.json")

    print("\nDone! Syntax error fixed.")


if __name__ == "__main__":
    main()
