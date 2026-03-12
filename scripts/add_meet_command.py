#!/usr/bin/env python3
"""
Add `meet <account>` command to Slack Events Handler.
User types: "meet Five9" or "meeting brief Dataiku"
→ Calls Meeting Brief sub-workflow with that account name.
"""

import json
import os
import uuid
import requests

N8N_BASE_URL = "https://scottai.trackslife.com"
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

SLACK_EVENTS_ID = "QuQbIaWetunUOFUW"
MEETING_BRIEF_ID = "Cj4HcHfbzy9OZhwE"
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
    print("Fetching live Slack Events Handler...")
    wf = fetch_workflow(SLACK_EVENTS_ID)
    nodes = wf["nodes"]
    conns = wf["connections"]

    # ── 1. Add cmd_meet route to Route by State ──
    print("\n1. Adding cmd_meet route...")
    route_node = find_node(nodes, "Route by State")
    route_code = route_node["parameters"]["jsCode"]

    # Add meet command in Pass 1 (exact matching), after cmd_brief
    old_brief_route = "else if (lower === 'brief' || lower.startsWith('brief ')) route = 'cmd_brief';"
    new_brief_route = (
        "else if (lower === 'brief' || lower.startsWith('brief ')) route = 'cmd_brief';\n"
        "  else if (lower === 'meet' || lower.startsWith('meet ') || lower.startsWith('meeting brief ') || lower.startsWith('prep ')) route = 'cmd_meet';"
    )
    route_code = route_code.replace(old_brief_route, new_brief_route)

    # Also add fuzzy match in Pass 2
    old_brief_fuzzy = "else if (/\\b(brief|briefing|digest)\\b/.test(lower)) route = 'cmd_brief';"
    new_brief_fuzzy = (
        "else if (/\\b(brief|briefing|digest)\\b/.test(lower)) route = 'cmd_brief';\n"
        "    else if (/\\b(meet(?:ing)?\\s+(?:brief|prep)|prep\\s+(?:me|for))\\b/i.test(lower)) route = 'cmd_meet';"
    )
    route_code = route_code.replace(old_brief_fuzzy, new_brief_fuzzy)

    route_node["parameters"]["jsCode"] = route_code
    print("   Added cmd_meet to Pass 1 and Pass 2")

    # ── 2. Add Switch Route output for cmd_meet ──
    print("\n2. Adding Switch Route output...")
    switch_node = find_node(nodes, "Switch Route")
    rules = switch_node["parameters"]["rules"]["values"]

    # Add new rule for cmd_meet
    new_rule = {
        "conditions": {
            "options": {
                "version": 2,
                "leftValue": "",
                "caseSensitive": True,
                "typeValidation": "strict",
            },
            "combinator": "and",
            "conditions": [
                {
                    "id": str(uuid.uuid4()),
                    "operator": {
                        "name": "filter.operator.equals",
                        "type": "string",
                        "operation": "equals",
                    },
                    "leftValue": "={{ $json.route }}",
                    "rightValue": "cmd_meet",
                }
            ],
        }
    }
    new_output_index = len(rules)
    rules.append(new_rule)
    print(f"   Added Switch Route output {new_output_index} for cmd_meet")

    # ── 3. Create Parse Meet Account node ──
    print("\n3. Creating Parse Meet Account node...")
    # Position near Parse Brief
    parse_brief = find_node(nodes, "Parse Brief")
    pb_pos = parse_brief["position"]

    parse_meet_node = {
        "parameters": {
            "jsCode": """// Parse account name from meet command
const data = $('Route by State').first().json;
const text = (data.text || '').trim();

// Strip command keywords to find the account name
const accountArg = text
  .replace(/\\b(meet|meeting\\s+brief|prep|prep\\s+me\\s+for|for|with|about|on|a|the|my|please)\\b/gi, ' ')
  .replace(/\\s+/g, ' ')
  .trim();

if (!accountArg) {
  return [{ json: { ...data, hasAccount: false, responseText: 'What account should I prep you for? Try: `meet Five9` or `meet Dataiku`' } }];
}

const ur = data.userRecord || {};
const repName = (ur.email || '').split('@')[0].replace(/\\./g, ' ').replace(/\\b\\w/g, c => c.toUpperCase()) || 'Rep';

return [{ json: {
  ...data,
  hasAccount: true,
  accountName: accountArg,
  repName,
  meetInput: {
    userId: data.dbUserId,
    slackUserId: data.userId,
    email: ur.email || '',
    assistant_name: data.assistantName,
    assistant_emoji: data.assistantEmoji,
    assistant_persona: ur.assistant_persona || null,
    timezone: ur.timezone || 'America/Los_Angeles',
    repName,
    accountName: accountArg,
    meetingSubject: 'On-demand meeting prep: ' + accountArg,
    meetingTime: '',
    participants: '',
    opportunityName: '',
    opportunityStage: '',
    opportunityAmount: '',
    opportunityCloseDate: '',
    opportunityEngagement: '',
    activityUid: 'ondemand_' + Date.now()
  }
} }];
"""
        },
        "id": str(uuid.uuid4()),
        "name": "Parse Meet Account",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [pb_pos[0], pb_pos[1] + 300],
    }
    nodes.append(parse_meet_node)

    # ── 4. Create Has Account? If node ──
    has_account_node = {
        "parameters": {
            "conditions": {
                "options": {
                    "version": 2,
                    "leftValue": "",
                    "caseSensitive": True,
                    "typeValidation": "loose",
                },
                "conditions": [
                    {
                        "id": str(uuid.uuid4()),
                        "leftValue": "={{ $json.hasAccount }}",
                        "rightValue": True,
                        "operator": {
                            "type": "boolean",
                            "operation": "true",
                        },
                    }
                ],
                "combinator": "and",
            },
            "options": {},
        },
        "id": str(uuid.uuid4()),
        "name": "Has Account?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [pb_pos[0] + 250, pb_pos[1] + 300],
    }
    nodes.append(has_account_node)

    # ── 5. Create Send Meet Thinking message ──
    send_meet_thinking = {
        "parameters": {
            "method": "POST",
            "url": "https://slack.com/api/chat.postMessage",
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Content-Type", "value": "application/json"}
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": '={{ JSON.stringify({ channel: $json.channelId, text: $json.assistantEmoji + " Prepping you for *" + $json.accountName + "*... give me about 30 seconds.", username: $json.assistantName, icon_emoji: $json.assistantEmoji, unfurl_links: false, unfurl_media: false }) }}',
            "options": {},
        },
        "id": str(uuid.uuid4()),
        "name": "Send Meet Thinking",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [pb_pos[0] + 500, pb_pos[1] + 200],
        "credentials": {
            "httpHeaderAuth": {
                "id": "LluVuiMJ8NUbAiG7",
                "name": "Slackbot Auth Token",
            }
        },
    }
    nodes.append(send_meet_thinking)

    # ── 6. Create Prepare Meet Input node ──
    prepare_meet_input = {
        "parameters": {
            "jsCode": """const data = $('Parse Meet Account').first().json;
return [{ json: data.meetInput }];
"""
        },
        "id": str(uuid.uuid4()),
        "name": "Prepare Meet Input",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [pb_pos[0] + 750, pb_pos[1] + 200],
    }
    nodes.append(prepare_meet_input)

    # ── 7. Create Execute Meeting Brief node ──
    exec_meet_brief = {
        "parameters": {
            "workflowId": {
                "__rl": True,
                "mode": "id",
                "value": MEETING_BRIEF_ID,
            },
            "options": {
                "waitForSubWorkflow": True,
            },
        },
        "id": str(uuid.uuid4()),
        "name": "Execute Meeting Brief1",
        "type": "n8n-nodes-base.executeWorkflow",
        "typeVersion": 1.2,
        "position": [pb_pos[0] + 1000, pb_pos[1] + 200],
    }
    nodes.append(exec_meet_brief)

    # ── 8. Create Send Meet Error (reuse pattern from Send Brief Error) ──
    # Find Send Brief Error to copy its pattern
    send_brief_error = None
    for n in nodes:
        if n["name"] == "Send Brief Error":
            send_brief_error = n
            break

    send_meet_error = {
        "parameters": {
            "method": "POST",
            "url": "https://slack.com/api/chat.postMessage",
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Content-Type", "value": "application/json"}
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": '={{ JSON.stringify({ channel: $json.channelId, text: $json.responseText, username: $json.assistantName, icon_emoji: $json.assistantEmoji, unfurl_links: false, unfurl_media: false }) }}',
            "options": {},
        },
        "id": str(uuid.uuid4()),
        "name": "Send Meet Error",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [pb_pos[0] + 500, pb_pos[1] + 400],
        "credentials": {
            "httpHeaderAuth": {
                "id": "LluVuiMJ8NUbAiG7",
                "name": "Slackbot Auth Token",
            }
        },
    }
    nodes.append(send_meet_error)

    # ── 9. Wire everything ──
    print("\n4. Wiring connections...")

    # Switch Route output N → Parse Meet Account
    sr_conns = conns.get("Switch Route", {}).get("main", [])
    while len(sr_conns) <= new_output_index:
        sr_conns.append([])
    sr_conns[new_output_index] = [{"node": "Parse Meet Account", "type": "main", "index": 0}]
    conns["Switch Route"]["main"] = sr_conns
    print(f"   Switch Route output {new_output_index} → Parse Meet Account")

    # Parse Meet Account → Has Account?
    conns["Parse Meet Account"] = {
        "main": [[{"node": "Has Account?", "type": "main", "index": 0}]]
    }
    print("   Parse Meet Account → Has Account?")

    # Has Account? true → Send Meet Thinking
    # Has Account? false → Send Meet Error
    conns["Has Account?"] = {
        "main": [
            [{"node": "Send Meet Thinking", "type": "main", "index": 0}],
            [{"node": "Send Meet Error", "type": "main", "index": 0}],
        ]
    }
    print("   Has Account? [true] → Send Meet Thinking, [false] → Send Meet Error")

    # Send Meet Thinking → Prepare Meet Input → Execute Meeting Brief1
    conns["Send Meet Thinking"] = {
        "main": [[{"node": "Prepare Meet Input", "type": "main", "index": 0}]]
    }
    conns["Prepare Meet Input"] = {
        "main": [[{"node": "Execute Meeting Brief1", "type": "main", "index": 0}]]
    }
    print("   Send Meet Thinking → Prepare Meet Input → Execute Meeting Brief1")

    # ── Push ──
    print("\nPushing...")
    result = push_workflow(SLACK_EVENTS_ID, wf)
    print(f"   ✓ Pushed (updatedAt: {result.get('updatedAt', '?')})")

    # Sync
    live = fetch_workflow(SLACK_EVENTS_ID)
    local_path = os.path.join(REPO_ROOT, "n8n", "workflows", "Slack Events Handler.json")
    with open(local_path, "w") as f:
        json.dump(live, f, indent=2)
    print("   ✓ Synced local file")

    print("\nDone! New commands:")
    print("  • meet Five9")
    print("  • meeting brief Dataiku")
    print("  • prep CyberArk")
    print("  → Calls Meeting Brief sub-workflow with that account")


if __name__ == "__main__":
    main()
