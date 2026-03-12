#!/usr/bin/env python3
"""
Hot-fix: Fix Opportunity Insights sub-workflow field name mismatches + timing issue.

Issues:
1. Sub-workflow expects snake_case fields (assistant_name, email, digest_scope)
   but passthrough gives camelCase/nested (assistantName, userRecord.email, etc.)
2. "Generating" message appears after results due to parallel connection

Fixes:
1. Update Filter by Scope + Resolve Insights Identity in sub-workflow to handle both formats
2. Add Prepare Insights Input node between Send Generating and Execute Insights
   that reads from $('Is Valid Insight?') — restores sequential flow with correct data
"""

import json
import os
import uuid
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

INSIGHTS_WF_ID = "cV5GDdW5MiukdJdN"
SLACK_EVENTS_ID = "QuQbIaWetunUOFUW"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}


def uid():
    return str(uuid.uuid4())


# ============================================================
# FIX 1: Update Opportunity Insights sub-workflow field refs
# ============================================================
def fix_sub_workflow():
    print("=== Fix 1: Updating Opportunity Insights sub-workflow ===")
    resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{INSIGHTS_WF_ID}", headers=HEADERS)
    resp.raise_for_status()
    wf = resp.json()
    print(f"  {len(wf['nodes'])} nodes")

    fixed_count = 0

    for node in wf["nodes"]:
        if node["name"] == "Filter by Scope":
            code = node["parameters"]["jsCode"]

            # Fix email reference
            old = """const repName = (input.email || '').split('@')[0]
  .replace(/\\./g, ' ')
  .replace(/\\b\\w/g, c => c.toUpperCase());
const repLower = repName.toLowerCase();
const digestScope = input.digest_scope || 'my_deals';
const userEmail = (input.email || '').toLowerCase();"""

            new = """// Support both passthrough (camelCase/nested) and explicit inputData (snake_case/flat)
const ur = input.userRecord || {};
const userEmail = (ur.email || input.email || '').toLowerCase();
const repName = userEmail.split('@')[0]
  .replace(/\\./g, ' ')
  .replace(/\\b\\w/g, c => c.toUpperCase());
const repLower = repName.toLowerCase();
const digestScope = ur.digest_scope || input.digest_scope || 'my_deals';"""

            if old in code:
                code = code.replace(old, new)
                node["parameters"]["jsCode"] = code
                print("  Filter by Scope: fixed email/scope field references")
                fixed_count += 1
            else:
                print("  Filter by Scope: pattern not found (may already be fixed)")

        elif node["name"] == "Resolve Insights Identity":
            code = node["parameters"]["jsCode"]

            # Fix assistant name/emoji/persona/timezone
            old = """const assistantName = input.assistant_name || 'Aria';
const assistantEmoji = input.assistant_emoji || ':robot_face:';
const assistantPersona = input.assistant_persona || 'direct, action-oriented, and conversational';
const repName = data.repName || 'Rep';
const timezone = input.timezone || 'America/Los_Angeles';"""

            new = """// Support both passthrough (camelCase/nested) and explicit inputData (snake_case/flat)
const ur = input.userRecord || {};
const assistantName = input.assistantName || ur.assistant_name || input.assistant_name || 'Aria';
const assistantEmoji = input.assistantEmoji || ur.assistant_emoji || input.assistant_emoji || ':robot_face:';
const assistantPersona = ur.assistant_persona || input.assistant_persona || 'direct, action-oriented, and conversational';
const repName = data.repName || 'Rep';
const timezone = ur.timezone || input.timezone || 'America/Los_Angeles';"""

            if old in code:
                code = code.replace(old, new)
            else:
                print("  Resolve Insights Identity: assistant pattern not found (may already be fixed)")

            # Fix userId/slackUserId
            old2 = """userId: input.id,
  slackUserId: input.slack_user_id,"""
            new2 = """userId: input.dbUserId || input.id,
  slackUserId: input.userId || input.slack_user_id,"""

            if old2 in code:
                code = code.replace(old2, new2)

            if code != node["parameters"]["jsCode"]:
                node["parameters"]["jsCode"] = code
                print("  Resolve Insights Identity: fixed field references")
                fixed_count += 1

    if fixed_count > 0:
        payload = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
                   "settings": wf.get("settings", {}), "staticData": wf.get("staticData")}
        resp = requests.put(f"{N8N_BASE_URL}/api/v1/workflows/{INSIGHTS_WF_ID}", headers=HEADERS, json=payload)
        resp.raise_for_status()
        result = resp.json()
        print(f"  Pushed: {len(result['nodes'])} nodes")

        path = os.path.join(REPO_ROOT, "n8n", "workflows", "Opportunity Insights.json")
        with open(path, "w") as f:
            json.dump(result, f, indent=4)
        print(f"  Synced {path}")
    else:
        print("  No changes needed")

    return fixed_count


# ============================================================
# FIX 2: Fix Events Handler flow — sequential with data restore
# ============================================================
def fix_events_handler():
    print("\n=== Fix 2: Fixing Events Handler flow (sequential + data restore) ===")
    resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{SLACK_EVENTS_ID}", headers=HEADERS)
    resp.raise_for_status()
    wf = resp.json()
    print(f"  {len(wf['nodes'])} nodes")

    nodes = wf["nodes"]
    connections = wf["connections"]

    # Check if Prepare Insights Input already exists
    node_names = [n["name"] for n in nodes]
    if "Prepare Insights Input" in node_names:
        print("  Prepare Insights Input already exists — skipping")
        return

    # Add "Prepare Insights Input" Code node that restores data from Is Valid Insight?
    prepare_id = uid()
    nodes.append({
        "parameters": {
            "jsCode": "// Restore original data from Is Valid Insight? (Send Generating outputs Slack API response)\nreturn [{ json: $('Is Valid Insight?').first().json }];"
        },
        "id": prepare_id,
        "name": "Prepare Insights Input",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [2900, 2120]
    })
    print(f"  Added Prepare Insights Input (id={prepare_id})")

    # Move Execute Insights position to make room
    for node in nodes:
        if node["name"] == "Execute Insights":
            node["position"] = [3140, 2220]
            print("  Moved Execute Insights to [3140, 2220]")
            break

    # Rewire connections:
    # Before: Is Valid Insight? → [parallel] Send Generating + Execute Insights
    # After:  Is Valid Insight? → Send Generating → Prepare Insights Input → Execute Insights
    #         Is Valid Insight? (false) → Send Error

    connections["Is Valid Insight?"] = {
        "main": [
            [{"node": "Send Insights Generating", "type": "main", "index": 0}],  # true
            [{"node": "Send Insights Error", "type": "main", "index": 0}]         # false
        ]
    }
    connections["Send Insights Generating"] = {
        "main": [[{"node": "Prepare Insights Input", "type": "main", "index": 0}]]
    }
    connections["Prepare Insights Input"] = {
        "main": [[{"node": "Execute Insights", "type": "main", "index": 0}]]
    }

    print("  Rewired: Is Valid? → Send Generating → Prepare Input → Execute Insights")

    # Push
    payload = {"name": wf["name"], "nodes": nodes, "connections": connections,
               "settings": wf.get("settings", {}), "staticData": wf.get("staticData")}
    resp = requests.put(f"{N8N_BASE_URL}/api/v1/workflows/{SLACK_EVENTS_ID}", headers=HEADERS, json=payload)
    resp.raise_for_status()
    result = resp.json()
    print(f"  Pushed: {len(result['nodes'])} nodes")

    path = os.path.join(REPO_ROOT, "n8n", "workflows", "Slack Events Handler.json")
    with open(path, "w") as f:
        json.dump(result, f, indent=4)
    print(f"  Synced {path}")


def main():
    fix_sub_workflow()
    fix_events_handler()
    print("\nDone! Fixed:")
    print("  1. Sub-workflow field refs: email, digest_scope, assistant_name/emoji, timezone")
    print("  2. Sequential flow: Send Generating → Prepare Input → Execute Insights")
    print("     (Generating message will now appear before results)")
    print("\nTry 'insights' in Slack again.")


if __name__ == "__main__":
    main()
