#!/usr/bin/env python3
"""
Fix: Meeting Prep Cron SplitInBatches wiring is wrong.

Problem: Execute Meeting Brief is connected to SplitInBatches output 0 ("done"),
but it should be on output 1 ("loop"). This means the sub-workflow never executes.

Also: Save to Messages loops back to SplitInBatches — this is correct but needs
to connect to input 0 (main) for the loop-back.

Fix: Move Execute Meeting Brief from output 0 to output 1 of Split In Batches.
"""

import json
import os
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

WORKFLOW_ID = "Of1U4T6x07aVqBYD"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}


def fetch_workflow(wid):
    resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{wid}", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def push_workflow(wid, wf):
    payload = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": wf.get("settings", {}),
        "staticData": wf.get("staticData"),
    }
    resp = requests.put(f"{N8N_BASE_URL}/api/v1/workflows/{wid}", headers=HEADERS, json=payload)
    resp.raise_for_status()
    return resp.json()


def main():
    print("Fetching live Meeting Prep Cron workflow...")
    wf = fetch_workflow(WORKFLOW_ID)
    conns = wf["connections"]

    # Fix SplitInBatches: move Execute Meeting Brief from output 0 to output 1
    sib = conns.get("Split In Batches", {}).get("main", [])
    print(f"  Current Split In Batches outputs: {len(sib)}")
    for i, targets in enumerate(sib):
        for t in targets:
            print(f"    Output {i} → {t['node']}")

    # Output 0 should be empty (done) or have a "done" handler
    # Output 1 should have Execute Meeting Brief (loop)
    conns["Split In Batches"]["main"] = [
        [],  # Output 0: "done" — nothing to do after all items processed
        [{"node": "Execute Meeting Brief", "type": "main", "index": 0}],  # Output 1: "loop" — process each item
    ]

    print("\n  Fixed Split In Batches outputs:")
    for i, targets in enumerate(conns["Split In Batches"]["main"]):
        for t in targets:
            print(f"    Output {i} → {t['node']}")
        if not targets:
            print(f"    Output {i} → (none)")

    # Push
    print("\nPushing updated workflow...")
    result = push_workflow(WORKFLOW_ID, wf)
    print(f"  ✓ Pushed (updatedAt: {result.get('updatedAt', '?')})")

    # Sync local
    print("\nSyncing local file...")
    live = fetch_workflow(WORKFLOW_ID)
    local_path = os.path.join(REPO_ROOT, "n8n", "workflows", "Meeting Prep Cron.json")
    with open(local_path, "w") as f:
        json.dump(live, f, indent=2)
    print(f"  ✓ Saved to {local_path}")

    print("\nDone! Execute Meeting Brief now connected to SplitInBatches output 1 (loop).")


if __name__ == "__main__":
    main()
