#!/usr/bin/env python3
"""
Fix: Has Matches? sends all 168 items to False branch.

Root cause: strict typeValidation + checking $json.noMatches (undefined on real matches).
Strict mode treats undefined as not-a-boolean → False branch.

Fix: Check $json.userId exists (string, exists) with loose validation.
Matched items have userId; the no-matches sentinel doesn't.
"""

import json
import os
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

WORKFLOW_ID = "Of1U4T6x07aVqBYD"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}


def main():
    print("Fetching live Meeting Prep Cron workflow...")
    resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{WORKFLOW_ID}", headers=HEADERS)
    resp.raise_for_status()
    wf = resp.json()

    # Fix Has Matches? node
    for n in wf["nodes"]:
        if n["name"] == "Has Matches?":
            n["parameters"]["conditions"] = {
                "options": {
                    "caseSensitive": True,
                    "leftValue": "",
                    "typeValidation": "loose",
                    "version": 2,
                },
                "conditions": [
                    {
                        "id": "dbccfc98-fde5-4090-8f70-12ebbcfe354a",
                        "leftValue": "={{ $json.userId }}",
                        "rightValue": "",
                        "operator": {
                            "type": "string",
                            "operation": "exists",
                            "singleValue": True,
                        },
                    }
                ],
                "combinator": "and",
            }
            print("  Updated condition: $json.userId exists (loose validation)")
            break

    # Push
    payload = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": wf.get("settings", {}),
        "staticData": wf.get("staticData"),
    }
    resp = requests.put(f"{N8N_BASE_URL}/api/v1/workflows/{WORKFLOW_ID}", headers=HEADERS, json=payload)
    resp.raise_for_status()
    print(f"  ✓ Pushed (updatedAt: {resp.json().get('updatedAt', '?')})")

    # Sync local
    resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{WORKFLOW_ID}", headers=HEADERS)
    resp.raise_for_status()
    local_path = os.path.join(REPO_ROOT, "n8n", "workflows", "Meeting Prep Cron.json")
    with open(local_path, "w") as f:
        json.dump(resp.json(), f, indent=2)
    print(f"  ✓ Synced local file")

    print("\nDone! Has Matches? now checks $json.userId exists → True branch → Split In Batches")


if __name__ == "__main__":
    main()
