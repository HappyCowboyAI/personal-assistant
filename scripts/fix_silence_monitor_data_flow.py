#!/usr/bin/env python3
"""
Fix Silence Contract Monitor data flow issues:

1. Get Recent Alerts returns [] on first run → stops workflow.
   Fix: Set alwaysOutputData=true so branch continues with empty data.

2. Get Active Users returns 9 individual items (n8n splits arrays).
   Prepare User Batch uses $('...').first().json which only gets user #1.
   Fix: Use $('...').all() to get all users and all alerts.
"""

import json
import os
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

WORKFLOW_ID = "6FsYIe3tYj0HfRY2"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}


# Fixed Prepare User Batch code — uses .all() instead of .first()
PREPARE_BATCH_CODE = r"""// Combine users with their recent alerts
// n8n splits array responses into individual items, so use .all()
const usersAll = $('Get Active Users').all().map(i => i.json);
const alertsAll = $('Get Recent Alerts').all().map(i => i.json);

// Filter out empty items (from alwaysOutputData on empty response)
const users = usersAll.filter(u => u && u.id);
const alerts = alertsAll.filter(a => a && a.id);

// Group recent alerts by user_id
const alertsByUser = {};
for (const a of alerts) {
  if (!alertsByUser[a.user_id]) alertsByUser[a.user_id] = [];
  alertsByUser[a.user_id].push(a);
}

// Output one item per active user
const output = [];
for (const user of users) {
  if (user.onboarding_state !== 'complete') continue;
  output.push({
    json: {
      userId: user.id,
      slackUserId: user.slack_user_id,
      email: user.email,
      assistantName: user.assistant_name || 'Aria',
      assistantEmoji: user.assistant_emoji || ':robot_face:',
      organizationId: user.organization_id,
      recentAlerts: alertsByUser[user.id] || []
    }
  });
}

if (output.length === 0) {
  return [{ json: { skip: true, reason: 'No active users found' } }];
}

return output;
"""


def find_node(nodes, name):
    for n in nodes:
        if n["name"] == name:
            return n
    return None


def main():
    print("Fetching Silence Contract Monitor workflow (live)...")
    resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{WORKFLOW_ID}", headers=HEADERS)
    resp.raise_for_status()
    wf = resp.json()
    nodes = wf["nodes"]
    print(f"  {len(nodes)} nodes")

    changes = 0

    # --- Fix 1: alwaysOutputData on Get Recent Alerts ---
    alerts_node = find_node(nodes, "Get Recent Alerts")
    if alerts_node:
        if alerts_node.get("alwaysOutputData"):
            print("  Get Recent Alerts: alwaysOutputData already set")
        else:
            alerts_node["alwaysOutputData"] = True
            print("  Set Get Recent Alerts: alwaysOutputData=true")
            changes += 1
    else:
        print("  WARNING: Get Recent Alerts not found!")

    # --- Fix 2: Update Prepare User Batch code ---
    batch_node = find_node(nodes, "Prepare User Batch")
    if batch_node:
        if ".all()" in batch_node["parameters"]["jsCode"]:
            print("  Prepare User Batch: already uses .all()")
        else:
            batch_node["parameters"]["jsCode"] = PREPARE_BATCH_CODE
            print("  Updated Prepare User Batch: .first() → .all()")
            changes += 1
    else:
        print("  WARNING: Prepare User Batch not found!")

    if changes == 0:
        print("\n  No changes needed")
        return

    # Push
    print(f"\n=== Pushing workflow ({changes} fixes) ===")
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
    print("\n=== Re-fetching and syncing ===")
    final = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{WORKFLOW_ID}", headers=HEADERS).json()
    path = os.path.join(REPO_ROOT, "n8n", "workflows", "Silence Contract Monitor.json")
    with open(path, "w") as f:
        json.dump(final, f, indent=4)
    print(f"  Synced {path}")

    print("\nDone! Fixed:")
    print("  1. Get Recent Alerts now continues on empty results")
    print("  2. Prepare User Batch now processes ALL users (not just first)")


if __name__ == "__main__":
    main()
