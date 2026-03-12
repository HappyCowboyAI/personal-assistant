#!/usr/bin/env python3
"""
Fix Meeting Prep Cron — multiple issues preventing any output:

1. Fetch Today Meetings: no responseFormat="text", CSV data not captured properly
2. Get Prep Users: Supabase boolean filter unreliable (string "true" vs boolean)
   → Remove filters, add Filter Prep Users Code node to filter in JS
3. SplitInBatches: already fixed (output 0→1)
"""

import json
import os
import uuid
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


def find_node(nodes, name):
    for n in nodes:
        if n["name"] == name:
            return n
    raise ValueError(f"Node '{name}' not found")


def main():
    print("Fetching live Meeting Prep Cron workflow...")
    wf = fetch_workflow(WORKFLOW_ID)
    nodes = wf["nodes"]
    conns = wf["connections"]

    # ── Fix 1: Force Fetch Today Meetings to return text ──
    print("\n1. Fixing Fetch Today Meetings response format...")
    fetch_node = find_node(nodes, "Fetch Today Meetings")
    fetch_node["parameters"]["options"] = {
        "response": {
            "response": {
                "responseFormat": "text"
            }
        }
    }
    print("   Set responseFormat=text")

    # ── Fix 2: Remove Supabase filters, add Code node filter ──
    print("\n2. Fixing Get Prep Users filter...")
    prep_node = find_node(nodes, "Get Prep Users")
    # Remove the unreliable filters — fetch all users
    prep_node["parameters"]["filters"] = {}
    print("   Removed Supabase filters from Get Prep Users")

    # Add a Filter Prep Users code node between Get Prep Users and Check Sent Briefs
    filter_node_id = str(uuid.uuid4())
    # Position between Get Prep Users and Check Sent Briefs
    prep_pos = prep_node["position"]
    filter_node = {
        "parameters": {
            "jsCode": (
                "// Filter to prep-enabled users with complete onboarding\n"
                "const users = $input.all().map(item => item.json);\n"
                "const filtered = users.filter(u => \n"
                "  u.onboarding_state === 'complete' && \n"
                "  u.meeting_prep_enabled !== false\n"  # DEFAULT TRUE, so only exclude explicit false
                ");\n"
                "if (filtered.length === 0) {\n"
                "  return [{ json: { noUsers: true } }];\n"
                "}\n"
                "return filtered.map(u => ({ json: u }));\n"
            )
        },
        "id": filter_node_id,
        "name": "Filter Prep Users",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [prep_pos[0] + 200, prep_pos[1]],
    }
    nodes.append(filter_node)
    print("   Added Filter Prep Users code node")

    # Rewire: Get Prep Users → Filter Prep Users → Check Sent Briefs
    # Currently: Get Prep Users → Check Sent Briefs
    conns["Get Prep Users"] = {
        "main": [[{"node": "Filter Prep Users", "type": "main", "index": 0}]]
    }
    conns["Filter Prep Users"] = {
        "main": [[{"node": "Check Sent Briefs", "type": "main", "index": 0}]]
    }
    print("   Rewired: Get Prep Users → Filter Prep Users → Check Sent Briefs")

    # Update Match Users to Meetings to reference Filter Prep Users instead of Get Prep Users
    match_node = find_node(nodes, "Match Users to Meetings")
    old_code = match_node["parameters"]["jsCode"]
    new_code = old_code.replace(
        "$('Get Prep Users')",
        "$('Filter Prep Users')"
    )
    match_node["parameters"]["jsCode"] = new_code
    print("   Updated Match Users to Meetings to reference Filter Prep Users")

    # Also shift downstream node positions to make room
    for n in nodes:
        if n["name"] in ["Check Sent Briefs", "Match Users to Meetings", "Has Matches?",
                         "Split In Batches", "Execute Meeting Brief", "Log Meeting Brief",
                         "Save to Messages"]:
            n["position"] = [n["position"][0] + 200, n["position"][1]]

    # ── Fix 3: Verify SplitInBatches wiring (already fixed) ──
    print("\n3. Verifying SplitInBatches wiring...")
    sib_conns = conns.get("Split In Batches", {}).get("main", [])
    if len(sib_conns) < 2 or not sib_conns[1]:
        conns["Split In Batches"]["main"] = [
            [],  # Output 0: done
            [{"node": "Execute Meeting Brief", "type": "main", "index": 0}],  # Output 1: loop
        ]
        print("   Fixed SplitInBatches output 1 → Execute Meeting Brief")
    else:
        print("   SplitInBatches already correct")

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

    print("\nDone! Three fixes applied:")
    print("  1. Fetch Today Meetings now returns text (CSV captured correctly)")
    print("  2. Get Prep Users filter moved to reliable Code node")
    print("  3. SplitInBatches output verified")


if __name__ == "__main__":
    main()
