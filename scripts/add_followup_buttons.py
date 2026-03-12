#!/usr/bin/env python3
"""
Add followup_draft and followup_skip button handling to the Interactive Events Handler.

When a user clicks [Draft Follow-up] in the proactive follow-up prompt:
1. Update message → "Drafting follow-up..."
2. Claude agent + People.ai MCP drafts the email
3. Post draft as a thread reply
4. Update original message → "Draft posted in thread"

When [Skip] is clicked:
1. Update message → "Skipped"

Modifies:
- Parse Interactive Payload — extract actionValue, messageTs, channelId
- Route Action Switch — add 2 new outputs (followup_draft, followup_skip)
- Add 9 new nodes for the followup draft flow
"""

import json
import os
import uuid
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

INTERACTIVE_HANDLER_ID = "JgVjCqoT6ZwGuDL1"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

# Credentials
ANTHROPIC_CRED = {"id": "rlAz7ZSl4y6AwRUq", "name": "Anthropic account 2"}
MCP_CRED = {"id": "wvV5pwBeIL7f2vLG", "name": "People.ai MCP Multi-Header"}
SLACK_CRED = {"id": "LluVuiMJ8NUbAiG7", "name": "Slackbot Auth Token"}


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


def find_node(nodes, name):
    for n in nodes:
        if n["name"] == name:
            return n
    return None


# ── Build followup context code ────────────────────────────────────

BUILD_CONTEXT_CODE = r"""// Extract context from button value and build agent prompt
const payload = $('Parse Interactive Payload').first().json;
let context = {};
try {
  context = JSON.parse(payload.actionValue || '{}');
} catch(e) {
  context = {};
}

const accountName = context.accountName || 'the account';
const meetingSubject = context.meetingSubject || '';
const participants = context.participants || '';
const repName = context.repName || 'there';
const assistantName = context.assistantName || 'Aria';
const assistantEmoji = context.assistantEmoji || ':robot_face:';

const meetingSubjectNote = meetingSubject
  ? ` (${meetingSubject})`
  : '';

let systemPrompt = `You are ${assistantName}, a personal sales assistant for ${repName}.

You have access to People.ai MCP tools for CRM data, account activity, meeting details, and engagement data.

**FOLLOW-UP EMAIL DRAFT MODE**

The user just had a meeting with ${accountName}${meetingSubjectNote}. Use People.ai MCP tools to:
1. Check the account's current deal status and stage
2. Review recent engagement and activity
3. Look up the participants to personalize the email

Draft a professional follow-up email.

**FORMAT** (Slack mrkdwn):

:email: *Follow-up Draft — ${accountName}*

*To:* primary recipients
*Subject:* concise subject line

---
email body — 150-250 words, professional, references meeting topics, includes clear next step
---

_Reply in this thread to adjust the tone, add details, or ask me to revise._

**RULES:**
- Keep the email 150-250 words
- Reference specific discussion topics if available
- Include a clear call to action / next step
- Use contact names, not generic "team"
- Tone: professional but warm
- Do NOT use ### headers
- Keep under 3000 characters`;

const agentPrompt = `Draft a follow-up email for my meeting with ${accountName}` +
  (meetingSubject ? `. The meeting was about: ${meetingSubject}` : '') +
  (participants ? `. Participants included: ${participants}` : '') +
  `. Today is ${new Date().toISOString().split('T')[0]}.`;

return [{
  json: {
    ...payload,
    ...context,
    systemPrompt,
    agentPrompt,
    assistantName,
    assistantEmoji,
    accountName,
  }
}];
"""


def main():
    print("Fetching Interactive Events Handler workflow (live)...")
    wf = fetch_workflow(INTERACTIVE_HANDLER_ID)
    nodes = wf["nodes"]
    connections = wf["connections"]
    print(f"  {len(nodes)} nodes")

    # Guard
    if find_node(nodes, "Build Followup Context"):
        print("  followup_draft handling already exists — skipping")
        return

    changes = 0

    # ── 1. Update Parse Interactive Payload ───────────────────────────
    parse_node = find_node(nodes, "Parse Interactive Payload")
    if not parse_node:
        print("ERROR: 'Parse Interactive Payload' not found!")
        return

    old_code = parse_node["parameters"]["jsCode"]
    # Add actionValue, messageTs, channelId extraction
    if "actionValue" not in old_code:
        # Find the return statement and add new fields before it
        new_code = old_code.rstrip()
        # Add extraction lines before the return
        insertion = """
// Follow-up button context
const actionValue = (payload.actions && payload.actions[0]) ? (payload.actions[0].value || '') : '';
const messageTs = (payload.message && payload.message.ts) ? payload.message.ts : '';
const channelId = (payload.channel && payload.channel.id) ? payload.channel.id : '';
"""
        # Find the return statement
        return_idx = new_code.rfind("return")
        if return_idx > 0:
            # Get the return line and add actionValue, messageTs, channelId
            before_return = new_code[:return_idx]
            return_part = new_code[return_idx:]
            # Add the new fields to the returned JSON
            return_part = return_part.replace(
                "actionId,",
                "actionId, actionValue, messageTs, channelId,",
            )
            # If that didn't match, try another pattern
            if "actionValue" not in return_part:
                return_part = return_part.replace(
                    "actionId",
                    "actionId, actionValue, messageTs, channelId",
                    1,
                )
            new_code = before_return + insertion + "\n" + return_part
            parse_node["parameters"]["jsCode"] = new_code
            print("  Updated 'Parse Interactive Payload' with actionValue/messageTs/channelId")
            changes += 1
        else:
            print("  WARNING: Could not find return statement in Parse Interactive Payload")
    else:
        print("  Parse Interactive Payload: already has actionValue")

    # ── 2. Add new Switch outputs to Route Action ─────────────────────
    route_node = find_node(nodes, "Route Action")
    if not route_node:
        print("ERROR: 'Route Action' not found!")
        return

    existing_conditions = route_node["parameters"]["rules"]["values"]
    # n8n v2 Switch: conditions is an object with nested conditions array using leftValue/rightValue
    action_ids = []
    for c in existing_conditions:
        conds_obj = c.get("conditions", {})
        inner = conds_obj.get("conditions", [])
        for inner_c in inner:
            action_ids.append(inner_c.get("rightValue", ""))

    if "followup_draft" in action_ids:
        print("  Route Action: followup_draft already exists — skipping")
    else:
        def make_switch_condition(action_id, output_key):
            return {
                "outputKey": output_key,
                "renameOutput": True,
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
                            "id": uid(),
                            "operator": {
                                "name": "filter.operator.equals",
                                "type": "string",
                                "operation": "equals",
                            },
                            "leftValue": "={{ $('Parse Interactive Payload').first().json.actionId }}",
                            "rightValue": action_id,
                        }
                    ],
                },
            }

        existing_conditions.append(make_switch_condition("followup_draft", "Draft Followup"))
        existing_conditions.append(make_switch_condition("followup_skip", "Skip Followup"))
        print("  Added 'followup_draft' (output 6) and 'followup_skip' (output 7) to Route Action")
        changes += 1

    # ── 3. Position reference — find Route Action position ────────────
    route_pos = route_node.get("position", [800, 800])
    # New nodes will be placed to the right and below
    base_x = route_pos[0] + 400
    base_y = route_pos[1] + 600  # Below existing routes

    # ── 4. Add followup_skip handler (simple: update message) ─────────
    skip_id = uid()
    nodes.append({
        "parameters": {
            "method": "POST",
            "url": "https://slack.com/api/chat.update",
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Content-Type", "value": "application/json"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": '={{ JSON.stringify({ channel: $("Parse Interactive Payload").first().json.channelId, ts: $("Parse Interactive Payload").first().json.messageTs, text: "_Skipped — no follow-up needed_", blocks: [] }) }}',
            "options": {},
        },
        "id": skip_id,
        "name": "Update Msg - Skipped",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [base_x, base_y + 200],
        "credentials": {"httpHeaderAuth": SLACK_CRED},
    })
    print(f"  Added 'Update Msg - Skipped'")
    changes += 1

    # ── 5. Add followup_draft handler nodes ───────────────────────────

    # 5a. Update original message → "Drafting..."
    drafting_id = uid()
    nodes.append({
        "parameters": {
            "method": "POST",
            "url": "https://slack.com/api/chat.update",
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Content-Type", "value": "application/json"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": '={{ JSON.stringify({ channel: $("Parse Interactive Payload").first().json.channelId, ts: $("Parse Interactive Payload").first().json.messageTs, text: ":hourglass_flowing_sand: Drafting follow-up...", blocks: [{ type: "section", text: { type: "mrkdwn", text: ":hourglass_flowing_sand: Drafting follow-up..." } }] }) }}',
            "options": {},
        },
        "id": drafting_id,
        "name": "Update Msg - Drafting",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [base_x, base_y],
        "credentials": {"httpHeaderAuth": SLACK_CRED},
    })
    print(f"  Added 'Update Msg - Drafting'")

    # 5b. Build followup context (extract button value, build prompt)
    context_id = uid()
    nodes.append({
        "parameters": {"jsCode": BUILD_CONTEXT_CODE},
        "id": context_id,
        "name": "Build Followup Context",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [base_x + 300, base_y],
    })
    print(f"  Added 'Build Followup Context'")

    # 5c. Followup Draft Agent
    agent_id = uid()
    nodes.append({
        "parameters": {
            "promptType": "define",
            "text": "={{ $json.agentPrompt }}",
            "options": {
                "systemMessage": "={{ $json.systemPrompt }}",
                "maxIterations": 10,
            },
        },
        "id": agent_id,
        "name": "Followup Draft Agent",
        "type": "@n8n/n8n-nodes-langchain.agent",
        "typeVersion": 1.7,
        "position": [base_x + 600, base_y],
        "continueOnFail": True,
    })
    print(f"  Added 'Followup Draft Agent'")

    # 5d. Anthropic Chat Model (Followup)
    model_id = uid()
    nodes.append({
        "parameters": {
            "model": {
                "__rl": True,
                "mode": "list",
                "value": "claude-sonnet-4-5-20250929",
                "cachedResultName": "Claude Sonnet 4.5",
            },
            "options": {},
        },
        "id": model_id,
        "name": "Anthropic Chat Model (Followup)",
        "type": "@n8n/n8n-nodes-langchain.lmChatAnthropic",
        "typeVersion": 1.3,
        "position": [base_x + 500, base_y + 200],
        "credentials": {"anthropicApi": ANTHROPIC_CRED},
    })
    print(f"  Added 'Anthropic Chat Model (Followup)'")

    # 5e. People.ai MCP (Followup)
    mcp_id = uid()
    nodes.append({
        "parameters": {
            "endpointUrl": "https://mcp.people.ai/mcp",
            "authentication": "multipleHeadersAuth",
            "options": {},
        },
        "id": mcp_id,
        "name": "People.ai MCP (Followup)",
        "type": "@n8n/n8n-nodes-langchain.mcpClientTool",
        "typeVersion": 1.2,
        "position": [base_x + 700, base_y + 200],
        "credentials": {"httpMultipleHeadersAuth": MCP_CRED},
    })
    print(f"  Added 'People.ai MCP (Followup)'")

    # 5f. Post Draft Reply (thread reply to original message)
    reply_id = uid()
    reply_body = (
        '={{ JSON.stringify({ '
        'channel: $("Build Followup Context").first().json.channelId, '
        'thread_ts: $("Build Followup Context").first().json.messageTs, '
        'text: $json.output || "I could not generate a draft. Try the followup command in a DM.", '
        'username: $("Build Followup Context").first().json.assistantName, '
        'icon_emoji: $("Build Followup Context").first().json.assistantEmoji '
        '}) }}'
    )
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
            "jsonBody": reply_body,
            "options": {},
        },
        "id": reply_id,
        "name": "Post Draft Reply",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [base_x + 900, base_y],
        "credentials": {"httpHeaderAuth": SLACK_CRED},
    })
    print(f"  Added 'Post Draft Reply'")

    # 5g. Update original message → "Draft posted ✓"
    done_id = uid()
    nodes.append({
        "parameters": {
            "method": "POST",
            "url": "https://slack.com/api/chat.update",
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Content-Type", "value": "application/json"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": '={{ JSON.stringify({ channel: $("Build Followup Context").first().json.channelId, ts: $("Build Followup Context").first().json.messageTs, text: ":white_check_mark: Follow-up draft posted in thread — " + $("Build Followup Context").first().json.accountName, blocks: [{ type: "section", text: { type: "mrkdwn", text: ":white_check_mark: Follow-up draft posted in thread — *" + $("Build Followup Context").first().json.accountName + "*" } }] }) }}',
            "options": {},
        },
        "id": done_id,
        "name": "Update Msg - Done",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [base_x + 1200, base_y],
        "credentials": {"httpHeaderAuth": SLACK_CRED},
    })
    print(f"  Added 'Update Msg - Done'")
    changes += 1

    # ── 6. Wire connections ───────────────────────────────────────────

    # Route Action needs new outputs
    route_conns = connections.get("Route Action", {}).get("main", [])
    # Extend to add outputs 6 and 7
    while len(route_conns) < 6:
        route_conns.append([])
    # Output 6 → Update Msg - Drafting (followup_draft)
    route_conns.append([{"node": "Update Msg - Drafting", "type": "main", "index": 0}])
    # Output 7 → Update Msg - Skipped (followup_skip)
    route_conns.append([{"node": "Update Msg - Skipped", "type": "main", "index": 0}])
    connections["Route Action"]["main"] = route_conns

    # Drafting chain
    connections["Update Msg - Drafting"] = {
        "main": [[{"node": "Build Followup Context", "type": "main", "index": 0}]]
    }
    connections["Build Followup Context"] = {
        "main": [[{"node": "Followup Draft Agent", "type": "main", "index": 0}]]
    }
    connections["Followup Draft Agent"] = {
        "main": [[{"node": "Post Draft Reply", "type": "main", "index": 0}]]
    }
    connections["Post Draft Reply"] = {
        "main": [[{"node": "Update Msg - Done", "type": "main", "index": 0}]]
    }

    # Sub-node connections
    connections["Anthropic Chat Model (Followup)"] = {
        "ai_languageModel": [
            [{"node": "Followup Draft Agent", "type": "ai_languageModel", "index": 0}]
        ]
    }
    connections["People.ai MCP (Followup)"] = {
        "ai_tool": [
            [{"node": "Followup Draft Agent", "type": "ai_tool", "index": 0}]
        ]
    }

    print(f"\n  Total nodes: {len(nodes)} (was {len(nodes) - 9})")

    # ── Push ──────────────────────────────────────────────────────────
    print(f"\n=== Pushing workflow ({changes} changes) ===")
    result = push_workflow(INTERACTIVE_HANDLER_ID, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")

    # ── Sync ──────────────────────────────────────────────────────────
    print("\n=== Re-fetching and syncing ===")
    final = fetch_workflow(INTERACTIVE_HANDLER_ID)
    sync_local(final, "Interactive Events Handler.json")

    print("\nDone! Follow-up button handling added:")
    print("  - [Draft Follow-up] → agent drafts email → posts in thread")
    print("  - [Skip] → updates message to 'Skipped'")


if __name__ == "__main__":
    main()
