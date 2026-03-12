#!/usr/bin/env python3
"""
Add 'scope' command to Slack Events Handler
- Users can type: scope, scope my deals, scope team, scope pipeline
- Adds cmd_scope route, Switch output, Parse/Update/Confirm nodes
"""

import json
import os
import uuid
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

SLACK_EVENTS_ID = "QuQbIaWetunUOFUW"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}
SLACK_CRED = {"id": "LluVuiMJ8NUbAiG7", "name": "Slackbot Auth Token"}
SUPABASE_CRED = {"id": "ASRWWkQ0RSMOpNF1", "name": "Supabase account"}


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


# Parse Scope node code
PARSE_SCOPE_CODE = r"""const input = $('Route by State').first().json;
const text = (input.text || '').toLowerCase().trim();
const assistantName = input.assistantName;
const assistantEmoji = input.assistantEmoji;
const currentScope = (input.userRecord && input.userRecord.digest_scope) || 'my_deals';

// Parse the scope argument
const scopeArg = text.replace(/^scope\s*/, '').trim();

const scopeMap = {
  'my deals': 'my_deals',
  'my_deals': 'my_deals',
  'deals': 'my_deals',
  'personal': 'my_deals',
  'me': 'my_deals',
  'team': 'team_deals',
  'team_deals': 'team_deals',
  'my team': 'team_deals',
  'team deals': 'team_deals',
  'pipeline': 'top_pipeline',
  'top_pipeline': 'top_pipeline',
  'top pipeline': 'top_pipeline',
  'full pipeline': 'top_pipeline',
  'exec': 'top_pipeline',
  'executive': 'top_pipeline',
  'all': 'top_pipeline'
};

const scopeLabels = {
  'my_deals': 'My Deals — your personal pipeline',
  'team_deals': 'Team — your team\'s pipeline',
  'top_pipeline': 'Full Pipeline — org-wide top deals'
};

let newScope = null;
let responseText = '';

if (!scopeArg) {
  // Just "scope" — show current and options
  responseText = `${assistantEmoji} Your briefing scope is currently set to: *${scopeLabels[currentScope]}*\n\nTo change it, reply with one of:\n• \`scope my deals\` — personal pipeline (for reps)\n• \`scope team\` — team pipeline (for managers)\n• \`scope pipeline\` — full org pipeline (for executives)`;
} else if (scopeMap[scopeArg]) {
  newScope = scopeMap[scopeArg];
  if (newScope === currentScope) {
    responseText = `${assistantEmoji} Your briefing scope is already set to *${scopeLabels[currentScope]}*. No changes needed!`;
    newScope = null; // No update needed
  } else {
    responseText = `${assistantEmoji} Got it! Your briefing scope is now set to *${scopeLabels[newScope]}*.\n\nYour next morning digest will use this view.`;
  }
} else {
  responseText = `${assistantEmoji} I didn't recognize that scope. Try one of:\n• \`scope my deals\`\n• \`scope team\`\n• \`scope pipeline\``;
}

return [{
  json: {
    userId: input.dbUserId,
    channelId: input.channelId,
    newScope,
    needsUpdate: !!newScope,
    responseText,
    assistantName,
    assistantEmoji
  }
}];
"""


def upgrade(wf):
    print("\n=== Adding scope command ===")
    nodes = wf["nodes"]
    connections = wf["connections"]

    # Check if already exists
    node_names = [n["name"] for n in nodes]
    if "Parse Scope" in node_names:
        print("  Parse Scope already exists — skipping")
        return wf

    # --- 1. Update Route by State to recognize "scope" command ---
    for node in nodes:
        if node["name"] == "Route by State":
            old_code = node["parameters"]["jsCode"]
            # Add scope command before the cmd_other fallback
            new_code = old_code.replace(
                "else if (lower.startsWith('persona ')) route = 'cmd_persona';",
                "else if (lower.startsWith('persona ')) route = 'cmd_persona';\n  else if (lower === 'scope' || lower.startsWith('scope ')) route = 'cmd_scope';"
            )
            node["parameters"]["jsCode"] = new_code
            print("  Updated Route by State with 'scope' command")
            break

    # --- 2. Add "Scope" output to Switch Route ---
    for node in nodes:
        if node["name"] == "Switch Route":
            node["parameters"]["rules"]["values"].append({
                "outputKey": "Scope",
                "conditions": {
                    "options": {
                        "version": 2,
                        "leftValue": "",
                        "caseSensitive": True,
                        "typeValidation": "strict"
                    },
                    "combinator": "and",
                    "conditions": [
                        {
                            "id": str(uuid.uuid4()),
                            "operator": {
                                "name": "filter.operator.equals",
                                "type": "string",
                                "operation": "equals"
                            },
                            "leftValue": "={{ $json.route }}",
                            "rightValue": "cmd_scope"
                        }
                    ]
                },
                "renameOutput": True
            })
            print("  Added 'Scope' output to Switch Route (output 8)")
            break

    # --- 3. Add Parse Scope node ---
    parse_scope_id = str(uuid.uuid4())
    nodes.append({
        "parameters": {"jsCode": PARSE_SCOPE_CODE},
        "id": parse_scope_id,
        "name": "Parse Scope",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [2180, 1360]
    })
    print(f"  Added Parse Scope (id={parse_scope_id})")

    # --- 4. Add Needs Scope Update? (If node) ---
    needs_update_id = str(uuid.uuid4())
    nodes.append({
        "parameters": {
            "conditions": {
                "options": {
                    "version": 2,
                    "leftValue": "",
                    "caseSensitive": True,
                    "typeValidation": "strict"
                },
                "conditions": [
                    {
                        "id": str(uuid.uuid4()),
                        "leftValue": "={{ $json.needsUpdate }}",
                        "rightValue": True,
                        "operator": {
                            "type": "boolean",
                            "operation": "true"
                        }
                    }
                ],
                "combinator": "and"
            },
            "options": {}
        },
        "id": needs_update_id,
        "name": "Needs Scope Update?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [2420, 1360]
    })
    print(f"  Added Needs Scope Update? (id={needs_update_id})")

    # --- 5. Add Update Scope (Supabase update) ---
    update_scope_id = str(uuid.uuid4())
    nodes.append({
        "parameters": {
            "operation": "update",
            "tableId": "users",
            "dataToSend": "defineBelow",
            "fieldsUi": {
                "fieldValues": [
                    {"fieldId": "digest_scope", "fieldValue": "={{ $json.newScope }}"}
                ]
            },
            "filters": {
                "conditions": [
                    {"keyName": "id", "condition": "eq", "keyValue": "={{ $json.userId }}"}
                ]
            }
        },
        "id": update_scope_id,
        "name": "Update Scope",
        "type": "n8n-nodes-base.supabase",
        "typeVersion": 1,
        "position": [2660, 1260],
        "credentials": {"supabaseApi": SUPABASE_CRED}
    })
    print(f"  Added Update Scope (id={update_scope_id})")

    # --- 6. Add Send Scope Response (Slack message) ---
    send_response_id = str(uuid.uuid4())
    nodes.append({
        "parameters": {
            "method": "POST",
            "url": "https://slack.com/api/chat.postMessage",
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Content-Type", "value": "application/json"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ channel: $json.channelId, text: $json.responseText, username: $json.assistantName, icon_emoji: $json.assistantEmoji, unfurl_links: false, unfurl_media: false }) }}",
            "options": {}
        },
        "id": send_response_id,
        "name": "Send Scope Response",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [2900, 1360],
        "credentials": {"httpHeaderAuth": SLACK_CRED}
    })
    print(f"  Added Send Scope Response (id={send_response_id})")

    # --- 7. Wire connections ---
    # Switch Route output 8 → Parse Scope
    if "Switch Route" not in connections:
        connections["Switch Route"] = {"main": []}
    switch_outputs = connections["Switch Route"]["main"]
    # Ensure we have enough output slots (0-7 already exist, add 8)
    while len(switch_outputs) < 9:
        switch_outputs.append([])
    switch_outputs[8] = [{"node": "Parse Scope", "type": "main", "index": 0}]

    connections["Parse Scope"] = {
        "main": [[{"node": "Needs Scope Update?", "type": "main", "index": 0}]]
    }
    connections["Needs Scope Update?"] = {
        "main": [
            [{"node": "Update Scope", "type": "main", "index": 0}],  # true
            [{"node": "Send Scope Response", "type": "main", "index": 0}]  # false (no update, just info)
        ]
    }
    connections["Update Scope"] = {
        "main": [[{"node": "Send Scope Response", "type": "main", "index": 0}]]
    }

    print("  Wired connections: Switch[8] → Parse Scope → Needs Update? → Update Scope → Send Response")
    print(f"  Total nodes: {len(nodes)}")
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

    print("\nDone! Users can now type 'scope', 'scope my deals', 'scope team', or 'scope pipeline'")


if __name__ == "__main__":
    main()
