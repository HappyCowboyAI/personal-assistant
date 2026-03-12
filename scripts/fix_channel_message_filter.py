#!/usr/bin/env python3
"""
Fix: Filter out non-thread channel messages in Events Handler.

After adding message.channels event subscription, the Events Handler receives
ALL channel messages — not just DMs. Non-thread channel messages (like someone
chatting in #ai-innovations-team) were falling through to the onboarding/settings
router, triggering unwanted greetings.

Fix: Insert an "Is DM?" check between "Is Thread Reply?" (false) and "Lookup User".
Only DMs proceed to the onboarding/settings router. Channel messages that aren't
thread replies are dropped with a NoOp.
"""

import json
import os
import uuid
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

EVENTS_HANDLER_ID = "QuQbIaWetunUOFUW"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}


def uid():
    return str(uuid.uuid4())


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
    print("Fetching Slack Events Handler workflow (live)...")
    wf = fetch_workflow(EVENTS_HANDLER_ID)
    nodes = wf["nodes"]
    connections = wf["connections"]
    print(f"  {len(nodes)} nodes")

    # Guard: check if already applied
    node_names = [n["name"] for n in nodes]
    if "Is DM?" in node_names:
        print("  'Is DM?' already exists — skipping")
        return

    # Find position of Is Thread Reply? and Lookup User for placement
    thread_reply_node = None
    lookup_user_node = None
    for n in nodes:
        if n["name"] == "Is Thread Reply?":
            thread_reply_node = n
        elif n["name"] == "Lookup User":
            lookup_user_node = n

    if not thread_reply_node:
        print("ERROR: 'Is Thread Reply?' node not found!")
        return
    if not lookup_user_node:
        print("ERROR: 'Lookup User' node not found!")
        return

    tr_pos = thread_reply_node["position"]
    lu_pos = lookup_user_node["position"]
    print(f"  Is Thread Reply? at {tr_pos}")
    print(f"  Lookup User at {lu_pos}")

    # Position the new nodes between Is Thread Reply? and Lookup User
    # Is Thread Reply? is at [1200, 1400], Lookup User is at [1328, 1200]
    # Place Is DM? at midpoint x, same y as the false output path
    is_dm_pos = [tr_pos[0] + 280, lu_pos[1]]  # [1480, 1200]
    stop_pos = [is_dm_pos[0], is_dm_pos[1] + 200]  # [1480, 1400] below for false branch

    print(f"  New positions: Is DM? at {is_dm_pos}, Stop at {stop_pos}")

    # Also need to shift Lookup User right to make room
    new_lu_pos = [is_dm_pos[0] + 280, lu_pos[1]]  # [1760, 1200]
    print(f"  Moving Lookup User from {lu_pos} to {new_lu_pos}")
    lookup_user_node["position"] = new_lu_pos

    # --- Add "Is DM?" IF node ---
    is_dm_id = uid()
    is_dm_node = {
        "parameters": {
            "conditions": {
                "options": {
                    "version": 2,
                    "leftValue": "",
                    "caseSensitive": True,
                    "typeValidation": "strict",
                },
                "conditions": [
                    {
                        "id": uid(),
                        "leftValue": "={{ $json.channelType }}",
                        "rightValue": "im",
                        "operator": {
                            "type": "string",
                            "operation": "equals",
                        },
                    }
                ],
                "combinator": "and",
            },
            "options": {},
        },
        "id": is_dm_id,
        "name": "Is DM?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": is_dm_pos,
    }
    nodes.append(is_dm_node)
    print(f"  Added 'Is DM?' (id={is_dm_id})")

    # --- Add "Stop - Channel Message" NoOp node ---
    stop_id = uid()
    stop_node = {
        "parameters": {},
        "id": stop_id,
        "name": "Stop - Channel Message",
        "type": "n8n-nodes-base.noOp",
        "typeVersion": 1,
        "position": stop_pos,
    }
    nodes.append(stop_node)
    print(f"  Added 'Stop - Channel Message' (id={stop_id})")

    # --- Rewire ---

    # Currently: Is Thread Reply? → false (index 1) → Lookup User
    # Change to: Is Thread Reply? → false (index 1) → Is DM?
    is_thread_conns = connections.get("Is Thread Reply?", {}).get("main", [[], []])
    # Index 0 = true (thread reply → Check Active Conversation) — keep as-is
    # Index 1 = false (not thread reply) — change from Lookup User to Is DM?
    is_thread_conns[1] = [{"node": "Is DM?", "type": "main", "index": 0}]
    connections["Is Thread Reply?"]["main"] = is_thread_conns
    print("  Rewired: Is Thread Reply? → false → Is DM?")

    # Is DM? → true (index 0) → Lookup User
    # Is DM? → false (index 1) → Stop - Channel Message
    connections["Is DM?"] = {
        "main": [
            [{"node": "Lookup User", "type": "main", "index": 0}],
            [{"node": "Stop - Channel Message", "type": "main", "index": 0}],
        ]
    }
    print("  Wired: Is DM? → true → Lookup User")
    print("  Wired: Is DM? → false → Stop - Channel Message")

    print(f"\n  Total nodes: {len(nodes)} (was {len(nodes) - 2})")

    print("\n=== Pushing workflow ===")
    result = push_workflow(EVENTS_HANDLER_ID, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")

    print("\n=== Re-fetching and syncing local file ===")
    final = fetch_workflow(EVENTS_HANDLER_ID)
    sync_local(final, "Slack Events Handler.json")

    print("\nDone! Channel messages that aren't thread replies are now ignored.")


if __name__ == "__main__":
    main()
