#!/usr/bin/env python3
"""
Add 'brief' command to Slack Events Handler + create On-Demand Digest sub-workflow.
- Users type: brief, brief risk, brief momentum, brief monday, etc.
- On-Demand Digest mirrors Sales Digest per-user pipeline but for a single user.
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
ANTHROPIC_CRED = {"id": "rlAz7ZSl4y6AwRUq", "name": "Anthropic account 2"}
MCP_CRED = {"id": "wvV5pwBeIL7f2vLG", "name": "Backstory MCP Multi-Header"}
PAI_CLIENT_BODY = "client_id=YOUR_CLIENT_ID&client_secret=YOUR_CLIENT_SECRET&grant_type=client_credentials"


def uid():
    return str(uuid.uuid4())


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


# ============================================================
# Read the theme-aware code from the Sales Digest we just pushed
# ============================================================
def get_sales_digest_code():
    """Fetch the Sales Digest to extract Filter User Opps and Resolve Identity code."""
    wf = fetch_workflow("7sinwSgjkEA40zDj")
    filter_code = None
    resolve_code = None
    parse_opps_code = None
    parse_hierarchy_code = None
    parse_blocks_code = None

    for node in wf["nodes"]:
        if node["name"] == "Filter User Opps":
            filter_code = node["parameters"]["jsCode"]
        elif node["name"] == "Resolve Identity":
            resolve_code = node["parameters"]["jsCode"]
        elif node["name"] == "Parse Opps CSV":
            parse_opps_code = node["parameters"]["jsCode"]
        elif node["name"] == "Parse Hierarchy":
            parse_hierarchy_code = node["parameters"]["jsCode"]
        elif node["name"] == "Parse Blocks":
            parse_blocks_code = node["parameters"]["jsCode"]

    return filter_code, resolve_code, parse_opps_code, parse_hierarchy_code, parse_blocks_code


# ============================================================
# CREATE ON-DEMAND DIGEST WORKFLOW
# ============================================================
def create_on_demand_digest():
    print("\n=== Creating On-Demand Digest workflow ===")

    filter_code, resolve_code, parse_opps_code, parse_hierarchy_code, parse_blocks_code = get_sales_digest_code()

    # Adapt Filter User Opps: read from 'Workflow Input Trigger' instead of 'Split In Batches'
    od_filter_code = filter_code.replace(
        "const user = $('Split In Batches').first().json;",
        "const user = $('Workflow Input Trigger').first().json;"
    )

    # Adapt Send Digest: read channelId from input trigger, not Open Bot DM
    od_send_body = """={{ JSON.stringify({ channel: $('Workflow Input Trigger').first().json.channelId, text: $('Parse Blocks').first().json.notificationText, username: $('Resolve Identity').first().json.assistantName, icon_emoji: $('Resolve Identity').first().json.assistantEmoji, blocks: JSON.parse($('Parse Blocks').first().json.blocks), unfurl_links: false, unfurl_media: false }) }}"""

    nodes = [
        # 1. Workflow Input Trigger
        {
            "parameters": {"inputSource": "passthrough"},
            "id": uid(),
            "name": "Workflow Input Trigger",
            "type": "n8n-nodes-base.executeWorkflowTrigger",
            "typeVersion": 1.1,
            "position": [200, 400]
        },
        # 2. Get Auth Token
        {
            "parameters": {
                "method": "POST",
                "url": "https://api.people.ai/v3/auth/tokens",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [{"name": "Content-Type", "value": "application/x-www-form-urlencoded"}]
                },
                "sendBody": True,
                "specifyBody": "string",
                "body": PAI_CLIENT_BODY,
                "options": {}
            },
            "id": uid(),
            "name": "Get Auth Token",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [420, 400]
        },
        # 3. Fetch User Hierarchy
        {
            "parameters": {
                "method": "POST",
                "url": "https://api.people.ai/v3/beta/insights/export",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "Content-Type", "value": "application/json"},
                        {"name": "Authorization", "value": "=Bearer {{ $('Get Auth Token').first().json.access_token }}"}
                    ]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": '{"object": "user", "columns": [{"slug": "ootb_user_name"}, {"slug": "ootb_user_email"}, {"slug": "ootb_user_manager"}]}',
                "options": {}
            },
            "id": uid(),
            "name": "Fetch User Hierarchy",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [640, 400]
        },
        # 4. Parse Hierarchy
        {
            "parameters": {"jsCode": parse_hierarchy_code},
            "id": uid(),
            "name": "Parse Hierarchy",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [860, 400]
        },
        # 5. Fetch Open Opps
        {
            "parameters": {
                "method": "POST",
                "url": "https://api.people.ai/v3/beta/insights/export",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "Content-Type", "value": "application/json"},
                        {"name": "Authorization", "value": "=Bearer {{ $('Get Auth Token').first().json.access_token }}"}
                    ]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": '{"object": "opportunity", "filter": {"$and": [{"attribute": {"slug": "ootb_opportunity_is_closed"}, "clause": {"$eq": false}}, {"attribute": {"slug": "ootb_opportunity_close_date", "variation_id": "ootb_opportunity_close_date_0"}, "clause": {"$within": {"$ref": "time_ranges.this_fyear"}}}]}, "columns": [{"slug": "ootb_opportunity_owners"}, {"slug": "ootb_opportunity_name"}, {"slug": "ootb_opportunity_account_name"}, {"slug": "ootb_opportunity_close_date"}, {"slug": "ootb_opportunity_current_stage"}, {"slug": "ootb_opportunity_converted_amount"}, {"slug": "ootb_opportunity_crm_id"}, {"slug": "ootb_opportunity_engagement_level"}], "sort": [{"attribute": {"slug": "ootb_opportunity_owners"}, "direction": "asc"}, {"attribute": {"slug": "ootb_opportunity_close_date"}, "direction": "desc"}]}',
                "options": {}
            },
            "id": uid(),
            "name": "Fetch Open Opps",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [1080, 400]
        },
        # 6. Parse Opps CSV
        {
            "parameters": {"jsCode": parse_opps_code},
            "id": uid(),
            "name": "Parse Opps CSV",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1300, 400]
        },
        # 7. Filter User Opps (adapted for single user)
        {
            "parameters": {"jsCode": od_filter_code},
            "id": uid(),
            "name": "Filter User Opps",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1520, 400]
        },
        # 8. Resolve Identity
        {
            "parameters": {"jsCode": resolve_code},
            "id": uid(),
            "name": "Resolve Identity",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1740, 400]
        },
        # 9. Digest Agent
        {
            "parameters": {
                "promptType": "define",
                "text": "={{ $('Resolve Identity').first().json.agentPrompt }}",
                "options": {
                    "systemMessage": "={{ $('Resolve Identity').first().json.systemPrompt }}"
                }
            },
            "id": uid(),
            "name": "Digest Agent",
            "type": "@n8n/n8n-nodes-langchain.agent",
            "typeVersion": 1.7,
            "position": [1960, 400],
            "continueOnFail": True
        },
        # 10. Anthropic Chat Model (sub-node of Digest Agent)
        {
            "parameters": {
                "model": {
                    "__rl": True,
                    "mode": "list",
                    "value": "claude-sonnet-4-5-20250929",
                    "cachedResultName": "Claude Sonnet 4.5"
                },
                "options": {}
            },
            "id": uid(),
            "name": "Anthropic Chat Model",
            "type": "@n8n/n8n-nodes-langchain.lmChatAnthropic",
            "typeVersion": 1.3,
            "position": [1968, 624],
            "credentials": {"anthropicApi": ANTHROPIC_CRED}
        },
        # 11. Backstory MCP (sub-node of Digest Agent)
        {
            "parameters": {
                "endpointUrl": "https://mcp-canary.people.ai/mcp",
                "authentication": "multipleHeadersAuth",
                "options": {}
            },
            "id": uid(),
            "name": "Backstory MCP",
            "type": "@n8n/n8n-nodes-langchain.mcpClientTool",
            "typeVersion": 1.2,
            "position": [2096, 624],
            "credentials": {"httpMultipleHeadersAuth": MCP_CRED}
        },
        # 12. Parse Blocks
        {
            "parameters": {"jsCode": parse_blocks_code},
            "id": uid(),
            "name": "Parse Blocks",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [2180, 400]
        },
        # 13. Send Digest
        {
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
                "jsonBody": od_send_body,
                "options": {}
            },
            "id": uid(),
            "name": "Send Digest",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [2400, 400],
            "credentials": {"httpHeaderAuth": SLACK_CRED},
            "continueOnFail": True
        }
    ]

    connections = {
        "Workflow Input Trigger": {"main": [[{"node": "Get Auth Token", "type": "main", "index": 0}]]},
        "Get Auth Token": {"main": [[{"node": "Fetch User Hierarchy", "type": "main", "index": 0}]]},
        "Fetch User Hierarchy": {"main": [[{"node": "Parse Hierarchy", "type": "main", "index": 0}]]},
        "Parse Hierarchy": {"main": [[{"node": "Fetch Open Opps", "type": "main", "index": 0}]]},
        "Fetch Open Opps": {"main": [[{"node": "Parse Opps CSV", "type": "main", "index": 0}]]},
        "Parse Opps CSV": {"main": [[{"node": "Filter User Opps", "type": "main", "index": 0}]]},
        "Filter User Opps": {"main": [[{"node": "Resolve Identity", "type": "main", "index": 0}]]},
        "Resolve Identity": {"main": [[{"node": "Digest Agent", "type": "main", "index": 0}]]},
        "Digest Agent": {"main": [[{"node": "Parse Blocks", "type": "main", "index": 0}]]},
        "Anthropic Chat Model": {"ai_languageModel": [[{"node": "Digest Agent", "type": "ai_languageModel", "index": 0}]]},
        "Backstory MCP": {"ai_tool": [[{"node": "Digest Agent", "type": "ai_tool", "index": 0}]]},
        "Parse Blocks": {"main": [[{"node": "Send Digest", "type": "main", "index": 0}]]}
    }

    workflow = {
        "name": "On-Demand Digest",
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1"}
    }

    resp = requests.post(f"{N8N_BASE_URL}/api/v1/workflows", headers=HEADERS, json=workflow)
    resp.raise_for_status()
    result = resp.json()
    wf_id = result["id"]
    print(f"  Created: ID={wf_id}, {len(result['nodes'])} nodes")

    # Sub-workflows called via Execute Workflow don't need activation
    print("  (Sub-workflow — no activation needed, called via Execute Workflow)")

    # Sync local
    resp3 = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}", headers=HEADERS)
    resp3.raise_for_status()
    sync_local(resp3.json(), "On-Demand Digest.json")

    return wf_id


# ============================================================
# PARSE BRIEF CODE — for Slack Events Handler
# ============================================================
PARSE_BRIEF_CODE = r"""const data = $('Route by State').first().json;
const text = (data.text || '').toLowerCase().trim();
const briefArg = text.replace(/^brief\s*/, '').trim();

const themeAliases = {
  'monday': 'full_pipeline', 'mon': 'full_pipeline',
  'tuesday': 'engagement_shifts', 'tue': 'engagement_shifts', 'tues': 'engagement_shifts',
  'wednesday': 'at_risk', 'wed': 'at_risk',
  'thursday': 'momentum', 'thu': 'momentum', 'thurs': 'momentum',
  'friday': 'week_review', 'fri': 'week_review',
  'full': 'full_pipeline', 'pipeline': 'full_pipeline', 'full pipeline': 'full_pipeline',
  'engagement': 'engagement_shifts', 'shifts': 'engagement_shifts',
  'risk': 'at_risk', 'at-risk': 'at_risk', 'at risk': 'at_risk', 'stalled': 'at_risk',
  'momentum': 'momentum', 'wins': 'momentum', 'positive': 'momentum',
  'review': 'week_review', 'week': 'week_review', 'recap': 'week_review', 'preview': 'week_review'
};

const themeLabels = {
  'full_pipeline': 'Full Pipeline Brief',
  'engagement_shifts': 'Engagement Shifts',
  'at_risk': 'At-Risk Deals',
  'momentum': 'Momentum & Wins',
  'week_review': 'Week in Review'
};

let theme = null;
let responseText = '';

if (!briefArg) {
  // Just "brief" — use today's theme
  const dayMap = {
    'monday': 'full_pipeline', 'tuesday': 'engagement_shifts',
    'wednesday': 'at_risk', 'thursday': 'momentum', 'friday': 'week_review'
  };
  const today = new Date().toLocaleDateString('en-US', { weekday: 'long', timeZone: 'America/Los_Angeles' }).toLowerCase();
  theme = dayMap[today] || 'full_pipeline';
} else if (themeAliases[briefArg]) {
  theme = themeAliases[briefArg];
} else {
  responseText = `${data.assistantEmoji} I didn't recognize that theme. Try one of:\n• \`brief\` — today's theme\n• \`brief risk\` — at-risk deals\n• \`brief momentum\` — wins & momentum\n• \`brief engagement\` — engagement shifts\n• \`brief review\` — week in review\n• \`brief full\` — full pipeline\n\nOr use a day name: \`brief monday\`, \`brief wednesday\`, etc.`;
}

return [{
  json: {
    ...data,
    theme,
    themeLabel: theme ? themeLabels[theme] : null,
    isValid: !!theme,
    responseText
  }
}];
"""


# ============================================================
# ADD BRIEF COMMAND TO SLACK EVENTS HANDLER
# ============================================================
def upgrade_events_handler(wf, on_demand_wf_id):
    print(f"\n=== Adding brief command (On-Demand WF ID: {on_demand_wf_id}) ===")
    nodes = wf["nodes"]
    connections = wf["connections"]

    node_names = [n["name"] for n in nodes]
    if "Parse Brief" in node_names:
        print("  Parse Brief already exists — skipping")
        return wf

    # --- 1. Update Route by State to recognize "brief" command ---
    for node in nodes:
        if node["name"] == "Route by State":
            old_code = node["parameters"]["jsCode"]
            new_code = old_code.replace(
                "else if (lower === 'scope' || lower.startsWith('scope ')) route = 'cmd_scope';",
                "else if (lower === 'scope' || lower.startsWith('scope ')) route = 'cmd_scope';\n  else if (lower === 'brief' || lower.startsWith('brief ')) route = 'cmd_brief';"
            )
            node["parameters"]["jsCode"] = new_code
            print("  Updated Route by State with 'brief' command")
            break

    # --- 2. Add "Brief" output to Switch Route ---
    for node in nodes:
        if node["name"] == "Switch Route":
            node["parameters"]["rules"]["values"].append({
                "outputKey": "Brief",
                "conditions": {
                    "options": {"version": 2, "leftValue": "", "caseSensitive": True, "typeValidation": "strict"},
                    "combinator": "and",
                    "conditions": [{
                        "id": uid(),
                        "operator": {"name": "filter.operator.equals", "type": "string", "operation": "equals"},
                        "leftValue": "={{ $json.route }}",
                        "rightValue": "cmd_brief"
                    }]
                },
                "renameOutput": True
            })
            print("  Added 'Brief' output to Switch Route (output 9)")
            break

    # --- 3. Add Parse Brief node ---
    parse_brief_id = uid()
    nodes.append({
        "parameters": {"jsCode": PARSE_BRIEF_CODE},
        "id": parse_brief_id,
        "name": "Parse Brief",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [2180, 1920]
    })
    print(f"  Added Parse Brief (id={parse_brief_id})")

    # --- 4. Add Is Valid Theme? (If node) ---
    is_valid_id = uid()
    nodes.append({
        "parameters": {
            "conditions": {
                "options": {"version": 2, "leftValue": "", "caseSensitive": True, "typeValidation": "strict"},
                "conditions": [{
                    "id": uid(),
                    "leftValue": "={{ $json.isValid }}",
                    "rightValue": True,
                    "operator": {"type": "boolean", "operation": "true"}
                }],
                "combinator": "and"
            },
            "options": {}
        },
        "id": is_valid_id,
        "name": "Is Valid Theme?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [2420, 1920]
    })
    print(f"  Added Is Valid Theme? (id={is_valid_id})")

    # --- 5. Add Send Generating Msg ---
    send_gen_id = uid()
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
            "jsonBody": "={{ JSON.stringify({ channel: $json.channelId, text: $json.assistantEmoji + ' Generating your *' + $json.themeLabel + '*... give me about 30 seconds.', username: $json.assistantName, icon_emoji: $json.assistantEmoji, unfurl_links: false, unfurl_media: false }) }}",
            "options": {}
        },
        "id": send_gen_id,
        "name": "Send Generating Msg",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [2660, 1820],
        "credentials": {"httpHeaderAuth": SLACK_CRED}
    })
    print(f"  Added Send Generating Msg (id={send_gen_id})")

    # --- 6. Add Execute On-Demand Digest ---
    exec_digest_id = uid()
    nodes.append({
        "parameters": {
            "workflowId": {"__rl": True, "mode": "id", "value": on_demand_wf_id},
            "options": {},
            "inputData": {
                "values": [
                    {"name": "id", "value": "={{ $json.dbUserId }}"},
                    {"name": "slack_user_id", "value": "={{ $json.userId }}"},
                    {"name": "email", "value": "={{ $json.userRecord.email }}"},
                    {"name": "channelId", "value": "={{ $json.channelId }}"},
                    {"name": "themeOverride", "value": "={{ $json.theme }}"},
                    {"name": "assistant_name", "value": "={{ $json.assistantName }}"},
                    {"name": "assistant_emoji", "value": "={{ $json.assistantEmoji }}"},
                    {"name": "assistant_persona", "value": "={{ $json.userRecord.assistant_persona || 'direct, action-oriented, and conversational' }}"},
                    {"name": "digest_scope", "value": "={{ $json.userRecord.digest_scope || 'my_deals' }}"},
                    {"name": "timezone", "value": "={{ $json.userRecord.timezone || 'America/Los_Angeles' }}"}
                ]
            }
        },
        "id": exec_digest_id,
        "name": "Execute On-Demand Digest",
        "type": "n8n-nodes-base.executeWorkflow",
        "typeVersion": 1.2,
        "position": [2900, 1820]
    })
    print(f"  Added Execute On-Demand Digest (id={exec_digest_id})")

    # --- 7. Add Send Brief Error ---
    send_error_id = uid()
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
        "id": send_error_id,
        "name": "Send Brief Error",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [2660, 2020],
        "credentials": {"httpHeaderAuth": SLACK_CRED}
    })
    print(f"  Added Send Brief Error (id={send_error_id})")

    # --- 8. Wire connections ---
    # Switch Route output 9 → Parse Brief
    if "Switch Route" not in connections:
        connections["Switch Route"] = {"main": []}
    switch_outputs = connections["Switch Route"]["main"]
    while len(switch_outputs) < 10:
        switch_outputs.append([])
    switch_outputs[9] = [{"node": "Parse Brief", "type": "main", "index": 0}]

    connections["Parse Brief"] = {
        "main": [[{"node": "Is Valid Theme?", "type": "main", "index": 0}]]
    }
    connections["Is Valid Theme?"] = {
        "main": [
            [{"node": "Send Generating Msg", "type": "main", "index": 0}],  # true
            [{"node": "Send Brief Error", "type": "main", "index": 0}]     # false
        ]
    }
    connections["Send Generating Msg"] = {
        "main": [[{"node": "Execute On-Demand Digest", "type": "main", "index": 0}]]
    }

    print("  Wired: Switch[9] → Parse Brief → Is Valid? → [yes: Send Generating → Execute Digest] [no: Send Error]")

    # --- 9. Update Build Help Response ---
    for node in nodes:
        if node["name"] == "Build Help Response":
            old_code = node["parameters"]["jsCode"]
            # Add brief command to the help text
            new_code = old_code.replace(
                r'\u2022 *scope* \u2014 set your briefing view (my deals, team, or pipeline)',
                r'\u2022 *brief [theme]* \u2014 get any briefing on demand (risk, momentum, review, full)\n\u2022 *scope* \u2014 set your briefing view (my deals, team, or pipeline)'
            )
            # Add to fallback text too
            new_code = new_code.replace(
                r'\u2022 *scope* \u2014 set your briefing view',
                r'\u2022 *brief [theme]* \u2014 on-demand briefing\n\u2022 *scope* \u2014 set your briefing view'
            )
            node["parameters"]["jsCode"] = new_code
            print("  Updated Build Help Response with 'brief' command")
            break

    print(f"  Total nodes: {len(nodes)}")
    return wf


# ============================================================
# MAIN
# ============================================================
def main():
    # Step 1: Create On-Demand Digest sub-workflow
    on_demand_wf_id = create_on_demand_digest()

    # Step 2: Update Slack Events Handler
    print("\nFetching Slack Events Handler...")
    events_wf = fetch_workflow(SLACK_EVENTS_ID)
    print(f"  {len(events_wf['nodes'])} nodes")

    events_wf = upgrade_events_handler(events_wf, on_demand_wf_id)

    print("\n=== Pushing Slack Events Handler ===")
    result = push_workflow(SLACK_EVENTS_ID, events_wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")

    print("\n=== Syncing local file ===")
    sync_local(result, "Slack Events Handler.json")

    print(f"\nDone! On-Demand Digest workflow ID: {on_demand_wf_id}")
    print("Users can now type 'brief', 'brief risk', 'brief momentum', 'brief monday', etc.")


if __name__ == "__main__":
    main()
