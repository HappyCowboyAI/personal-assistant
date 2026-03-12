#!/usr/bin/env python3
"""
Create the On-Demand Silence Check sub-workflow + wire it into the Slack Events Handler.

Sub-workflow flow:
  Workflow Input Trigger
    → Get Auth Token (People.ai)
    → Fetch Opp Ownership (Query API: owner + CSM columns)
    → Parse Opp Teams (CSV → per-person account lists)
    → Filter User Accounts (scope-aware: my_deals=own accounts, team=wider, exec=all)
    → Build Silence Prompt (account list → agent prompt)
    → Silence Agent (Claude Sonnet 4.5 + People.ai MCP)
    → Parse Silence Results (extract JSON from agent)
    → Build Alert Message (format for Slack)
    → Send Silence Check (chat.postMessage)

Events Handler changes:
  - Route by State: add 'silence' / 'silent' command → cmd_silence
  - Switch: add output 14 for cmd_silence
  - New nodes: Send Checking Msg → Prepare Silence Input → Execute Silence Check → Track Usage
  - Build Help Response: add 'silence' to shortcuts + details dict
"""

import json
import sys
from n8n_helpers import (
    find_node, fetch_workflow, push_workflow, sync_local, activate_workflow,
    uid, WF_EVENTS_HANDLER, WF_SILENCE_MONITOR,
    N8N_BASE_URL, HEADERS,
)
import requests


# ── Credential IDs (from MEMORY.md) ──
CRED_ANTHROPIC = "rlAz7ZSl4y6AwRUq"
CRED_PAI_MCP = "wvV5pwBeIL7f2vLG"
CRED_SLACK = "LluVuiMJ8NUbAiG7"
CRED_SUPABASE = "ASRWWkQ0RSMOpNF1"


def create_sub_workflow():
    """Create and push the On-Demand Silence Check sub-workflow."""
    print("=== Creating On-Demand Silence Check sub-workflow ===\n")

    trigger_id = uid()
    auth_id = uid()
    fetch_id = uid()
    parse_teams_id = uid()
    filter_accounts_id = uid()
    build_prompt_id = uid()
    agent_id = uid()
    model_id = uid()
    mcp_id = uid()
    parse_results_id = uid()
    build_msg_id = uid()
    send_id = uid()

    export_body = json.dumps({
        "object": "opportunity",
        "filter": {"$and": [
            {"attribute": {"slug": "ootb_opportunity_is_closed"}, "clause": {"$eq": False}}
        ]},
        "columns": [
            {"slug": "ootb_opportunity_name"},
            {"slug": "ootb_opportunity_account_name"},
            {"slug": "ootb_opportunity_original_owner"},
            {"slug": "opportunity_csm_owner__c_user"},
            {"slug": "ootb_opportunity_crm_id"}
        ],
        "sort": [{"attribute": {"slug": "ootb_opportunity_account_name"}, "direction": "asc"}]
    })

    nodes = [
        # 1. Trigger
        {
            "parameters": {"inputSource": "passthrough"},
            "id": trigger_id,
            "name": "Workflow Input Trigger",
            "type": "n8n-nodes-base.executeWorkflowTrigger",
            "typeVersion": 1.1,
            "position": [0, 300]
        },
        # 2. Get Auth Token
        {
            "parameters": {
                "method": "POST",
                "url": "https://api.people.ai/v3/auth/tokens",
                "sendHeaders": True,
                "headerParameters": {"parameters": [
                    {"name": "Content-Type", "value": "application/x-www-form-urlencoded"}
                ]},
                "sendBody": True,
                "specifyBody": "string",
                "body": "client_id=YOUR_CLIENT_ID&client_secret=YOUR_CLIENT_SECRET&grant_type=client_credentials",
                "options": {}
            },
            "id": auth_id,
            "name": "Get Auth Token",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [224, 300]
        },
        # 3. Fetch Opp Ownership
        {
            "parameters": {
                "method": "POST",
                "url": "https://api.people.ai/v3/beta/insights/export",
                "sendHeaders": True,
                "headerParameters": {"parameters": [
                    {"name": "Authorization", "value": "=Bearer {{ $json.access_token }}"},
                    {"name": "Content-Type", "value": "application/json"}
                ]},
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": export_body,
                "options": {}
            },
            "id": fetch_id,
            "name": "Fetch Opp Ownership",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [448, 300]
        },
        # 4. Parse Opp Teams
        {
            "parameters": {
                "mode": "runOnceForAllItems",
                "jsCode": r"""// Parse opp ownership CSV into per-person account lists
const csvData = $('Fetch Opp Ownership').first().json.data;
const userData = $('Workflow Input Trigger').first().json;

if (!csvData) {
  return [{ json: { ...userData, userAccounts: [], error: 'No ownership data' } }];
}

const lines = csvData.split('\n').filter(l => l.trim());
if (lines.length < 2) {
  return [{ json: { ...userData, userAccounts: [] } }];
}

function parseCsvLine(line) {
  const result = [];
  let current = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (inQuotes && i + 1 < line.length && line[i + 1] === '"') { current += '"'; i++; }
      else { inQuotes = !inQuotes; }
    } else if (ch === ',' && !inQuotes) {
      result.push(current.trim());
      current = '';
    } else {
      current += ch;
    }
  }
  result.push(current.trim());
  return result;
}

const headers = parseCsvLine(lines[0]);
const headerMap = {};
headers.forEach((h, i) => { headerMap[h.toLowerCase()] = i; });

function get(row, ...names) {
  for (const name of names) {
    const idx = headerMap[name.toLowerCase()];
    if (idx !== undefined && row[idx] !== undefined && row[idx] !== '') return row[idx];
  }
  return '';
}

// Build per-person account sets
const accountsByPerson = {};
function addAccount(personName, accountName) {
  if (!personName || !accountName) return;
  const key = personName.toLowerCase().trim();
  if (!accountsByPerson[key]) accountsByPerson[key] = new Set();
  accountsByPerson[key].add(accountName);
}

for (let i = 1; i < lines.length; i++) {
  const row = parseCsvLine(lines[i]);
  if (row.length < 2) continue;
  const accountName = get(row, 'Account Name');
  const ownerName = get(row, 'Opportunity Owner (name)', 'Opportunity Owner');
  const csmName = get(row, 'CSM Owner (name)', 'CSM Owner');
  addAccount(ownerName, accountName);
  addAccount(csmName, accountName);
}

// Find this user's accounts
const repName = userData.repName || '';
const repLower = repName.toLowerCase();
const userAccounts = accountsByPerson[repLower] ? Array.from(accountsByPerson[repLower]).sort() : [];

return [{ json: { ...userData, userAccounts, userAccountCount: userAccounts.length, accountsByPerson: Object.fromEntries(Object.entries(accountsByPerson).map(([k, v]) => [k, Array.from(v)])) } }];"""
            },
            "id": parse_teams_id,
            "name": "Parse Opp Teams",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [672, 300]
        },
        # 5. Build Silence Prompt
        {
            "parameters": {
                "mode": "runOnceForAllItems",
                "jsCode": r"""const data = $input.first().json;
const today = new Date().toISOString().split('T')[0];
const scope = data.digestScope || data.digest_scope || 'my_deals';
const repName = data.repName || '';
const userAccounts = data.userAccounts || [];
const assistantName = data.assistantName || data.assistant_name || 'Aria';
const assistantEmoji = data.assistantEmoji || data.assistant_emoji || ':robot_face:';
const assistantPersona = data.assistantPersona || data.assistant_persona || '';

let prompt;

if (scope === 'my_deals' && userAccounts.length > 0) {
  const accountList = userAccounts.map(a => `• ${a}`).join('\n');
  prompt = `Check these specific accounts for engagement gaps. For each account below, check if there has been any customer-facing activity (emails, meetings, or calls) in the past 5 or more days. Only check these accounts — they are the accounts where ${repName} is the owner or CSM:\n\n${accountList}\n\nToday's date is ${today}. Report any that have gone silent (5+ days with no activity).`;
} else if (scope === 'my_deals') {
  prompt = `Check accounts associated with ${repName} for engagement gaps. Which accounts with open opportunities have had no customer-facing activity in the past 5 or more days? Only include accounts where ${repName} is the owner, CSM, or team member. Today's date is ${today}.`;
} else if (scope === 'team_deals') {
  if (userAccounts.length > 0) {
    const accountList = userAccounts.map(a => `• ${a}`).join('\n');
    prompt = `Check these accounts for engagement gaps:\n\n${accountList}\n\nToday's date is ${today}. Report any with 5+ days of no activity.`;
  } else {
    prompt = `Check accounts for engagement gaps across my team. Which accounts with open opportunities have had no customer-facing activity in the past 5 or more days? Today's date is ${today}.`;
  }
} else {
  prompt = `Check all accounts for engagement gaps. Which accounts with open opportunities have had no customer-facing activity in the past 5 or more days? Today's date is ${today}.`;
}

const systemPrompt = `You are ${assistantName}, a proactive sales assistant.${assistantPersona ? ' Your personality: ' + assistantPersona + '.' : ''} You detect "silence contracts" — accounts where customer engagement has gone quiet.

Using the People.ai tools, check accounts for engagement gaps:
1. For each account, check the most recent customer-facing activity (emails, meetings, calls)
2. Identify accounts where the last activity was more than 5 days ago

Classify each silent account by severity:
- "info" (5-9 days): Getting quiet
- "warning" (10-20 days): Gone silent
- "critical" (21+ days): Relationship at risk

CRITICAL: End your response with a JSON code block:
\`\`\`json
{
  "silent_accounts": [
    {
      "account_name": "Account Name",
      "days_silent": 14,
      "last_activity_date": "2026-02-17",
      "last_activity_type": "email",
      "severity": "warning"
    }
  ]
}
\`\`\`
If no accounts are silent, return: \`\`\`json\n{"silent_accounts": []}\n\`\`\`
Do NOT include text after the JSON block.`;

return [{ json: { ...data, silencePrompt: prompt, systemPrompt, assistantName, assistantEmoji } }];"""
            },
            "id": build_prompt_id,
            "name": "Build Silence Prompt",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [896, 300]
        },
        # 6. Silence Agent
        {
            "parameters": {
                "promptType": "define",
                "text": "={{ $json.silencePrompt }}",
                "options": {
                    "systemMessage": "={{ $json.systemPrompt }}",
                    "maxIterations": 15
                }
            },
            "id": agent_id,
            "name": "Silence Agent",
            "type": "@n8n/n8n-nodes-langchain.agent",
            "typeVersion": 1.7,
            "position": [1120, 300]
        },
        # 6a. Anthropic Chat Model
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
            "id": model_id,
            "name": "Anthropic Chat Model",
            "type": "@n8n/n8n-nodes-langchain.lmChatAnthropic",
            "typeVersion": 1.3,
            "position": [1020, 520],
            "credentials": {
                "anthropicApi": {"id": CRED_ANTHROPIC, "name": "Anthropic account 2"}
            }
        },
        # 6b. People.ai MCP
        {
            "parameters": {
                "url": "https://mcp.people.ai/mcp",
                "authentication": "genericCredentialType",
                "genericAuthType": "httpHeaderAuth",
                "options": {}
            },
            "id": mcp_id,
            "name": "People.ai MCP",
            "type": "@n8n/n8n-nodes-langchain.mcpClientTool",
            "typeVersion": 1,
            "position": [1220, 520],
            "credentials": {
                "httpHeaderAuth": {"id": CRED_PAI_MCP, "name": "People.ai MCP Multi-Header"}
            }
        },
        # 7. Parse Silence Results
        {
            "parameters": {
                "mode": "runOnceForAllItems",
                "jsCode": r"""const agentOutput = $('Silence Agent').first().json.output || '';
const userData = $('Build Silence Prompt').first().json;

let silentAccounts = [];
const jsonMatch = agentOutput.match(/```json\s*([\s\S]*?)\s*```/);
if (jsonMatch) {
  try {
    const parsed = JSON.parse(jsonMatch[1]);
    silentAccounts = parsed.silent_accounts || [];
  } catch (e) {
    try {
      silentAccounts = JSON.parse(agentOutput).silent_accounts || [];
    } catch (e2) {}
  }
}

// Sort by severity (critical first) then days silent
const severityOrder = { critical: 0, warning: 1, info: 2 };
silentAccounts.sort((a, b) => {
  const sA = severityOrder[a.severity] ?? 3;
  const sB = severityOrder[b.severity] ?? 3;
  if (sA !== sB) return sA - sB;
  return (b.days_silent || 0) - (a.days_silent || 0);
});

return [{ json: { ...userData, silentAccounts, alertCount: silentAccounts.length } }];"""
            },
            "id": parse_results_id,
            "name": "Parse Silence Results",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1344, 300]
        },
        # 8. Build Alert Message
        {
            "parameters": {
                "mode": "runOnceForAllItems",
                "jsCode": r"""const data = $input.first().json;
const accounts = data.silentAccounts || [];
const assistantName = data.assistantName || 'Aria';

if (accounts.length === 0) {
  return [{ json: { ...data, blocks: JSON.stringify([
    { type: "section", text: { type: "mrkdwn", text: ":white_check_mark: *All clear!* None of your accounts have gone silent. Everything looks active." } }
  ]), notificationText: "All accounts active" } }];
}

const severityEmoji = { info: ':large_blue_circle:', warning: ':warning:', critical: ':red_circle:' };
const severityLabel = { info: 'Getting quiet', warning: 'Gone silent', critical: 'Relationship at risk' };

const blocks = [
  { type: "section", text: { type: "mrkdwn", text: `:mag: *Silence Contract Check*\n${accounts.length} account${accounts.length === 1 ? '' : 's'} need${accounts.length === 1 ? 's' : ''} attention:` } }
];

for (const acct of accounts) {
  const emoji = severityEmoji[acct.severity] || ':grey_question:';
  const label = severityLabel[acct.severity] || acct.severity;
  const lastDate = acct.last_activity_date ? ` (last: ${acct.last_activity_type || 'activity'} on ${acct.last_activity_date})` : '';
  blocks.push({
    type: "section",
    text: { type: "mrkdwn", text: `${emoji} *${acct.account_name}* \u2014 ${acct.days_silent} days silent${lastDate}\n${label}` }
  });
}

blocks.push({ type: "section", text: { type: "mrkdwn", text: "_Reply to discuss any of these accounts._" } });

// Enforce Slack limits
if (blocks.length > 50) blocks.length = 50;
for (const b of blocks) {
  if (b.text && b.text.text && b.text.text.length > 3000) {
    b.text.text = b.text.text.slice(0, 2997) + '...';
  }
}

return [{ json: { ...data, blocks: JSON.stringify(blocks), notificationText: `${accounts.length} silent account${accounts.length === 1 ? '' : 's'} found` } }];"""
            },
            "id": build_msg_id,
            "name": "Build Alert Message",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1568, 300]
        },
        # 9. Send Silence Check
        {
            "parameters": {
                "method": "POST",
                "url": "https://slack.com/api/chat.postMessage",
                "authentication": "genericCredentialType",
                "genericAuthType": "httpHeaderAuth",
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": '={\n  "channel": "{{ $json.channelId }}",\n  "text": "{{ $json.notificationText }}",\n  "blocks": {{ $json.blocks }},\n  "username": "{{ $json.assistantName }}",\n  "icon_emoji": "{{ $json.assistantEmoji }}"\n}',
                "options": {}
            },
            "id": send_id,
            "name": "Send Silence Check",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [1792, 300],
            "credentials": {
                "httpHeaderAuth": {"id": CRED_SLACK, "name": "Slackbot Auth Token"}
            }
        },
    ]

    connections = {
        "Workflow Input Trigger": {"main": [[{"node": "Get Auth Token", "type": "main", "index": 0}]]},
        "Get Auth Token": {"main": [[{"node": "Fetch Opp Ownership", "type": "main", "index": 0}]]},
        "Fetch Opp Ownership": {"main": [[{"node": "Parse Opp Teams", "type": "main", "index": 0}]]},
        "Parse Opp Teams": {"main": [[{"node": "Build Silence Prompt", "type": "main", "index": 0}]]},
        "Build Silence Prompt": {"main": [[{"node": "Silence Agent", "type": "main", "index": 0}]]},
        "Silence Agent": {"main": [[{"node": "Parse Silence Results", "type": "main", "index": 0}]]},
        "Anthropic Chat Model": {"ai_languageModel": [[{"node": "Silence Agent", "type": "ai_languageModel", "index": 0}]]},
        "People.ai MCP": {"ai_tool": [[{"node": "Silence Agent", "type": "ai_tool", "index": 0}]]},
        "Parse Silence Results": {"main": [[{"node": "Build Alert Message", "type": "main", "index": 0}]]},
        "Build Alert Message": {"main": [[{"node": "Send Silence Check", "type": "main", "index": 0}]]},
    }

    workflow = {
        "name": "On-Demand Silence Check",
        "nodes": nodes,
        "connections": connections,
        "settings": {
            "executionOrder": "v1",
            "saveManualExecutions": True,
            "callerPolicy": "workflowsFromSameOwner"
        },
    }

    # Create workflow
    resp = requests.post(
        f"{N8N_BASE_URL}/api/v1/workflows",
        headers=HEADERS,
        json=workflow,
    )
    resp.raise_for_status()
    result = resp.json()
    wf_id = result["id"]
    print(f"  Created workflow: {result['name']} (ID: {wf_id}, {len(result['nodes'])} nodes)")

    # Sub-workflows don't need activation — they're called via executeWorkflow
    print(f"  (Sub-workflow — no activation needed)")

    # Sync local
    final = fetch_workflow(wf_id)
    sync_local(final, "On-Demand Silence Check.json")

    return wf_id


def wire_events_handler(silence_wf_id):
    """Add silence command route to the Slack Events Handler."""
    print("\n=== Wiring silence command into Events Handler ===\n")

    wf = fetch_workflow(WF_EVENTS_HANDLER)
    nodes = wf["nodes"]
    connections = wf["connections"]
    print(f"  {len(nodes)} nodes")

    # ── 1. Update Route by State — add silence/silent command routing ──
    route_node = find_node(nodes, "Route by State")
    if not route_node:
        print("ERROR: 'Route by State' not found!")
        return
    code = route_node["parameters"]["jsCode"]

    if "cmd_silence" in code:
        print("  Route by State: cmd_silence already present — skipping")
    else:
        # Add silence command before the brief/digest matching
        # Find the brief matching line and add silence before it
        old_pattern = "if (lower.startsWith('brief')"
        if old_pattern not in code:
            # Try alternative patterns
            for pat in ["if (lower === 'brief'", "lower.startsWith('brief')", "startsWith('brief"]:
                if pat in code:
                    old_pattern = pat
                    break

        if old_pattern in code:
            new_code = code.replace(
                old_pattern,
                "if (lower === 'silence' || lower === 'silent' || lower === 'silent accounts' || lower.startsWith('silence check')) {\n      route = 'cmd_silence';\n    } else " + old_pattern
            )
            route_node["parameters"]["jsCode"] = new_code
            print("  Updated Route by State — added cmd_silence route")
        else:
            print("  WARNING: Could not find brief pattern in Route by State — manual edit needed")

    # ── 2. Update Switch node — add output 14 for cmd_silence ──
    switch_node = find_node(nodes, "Switch Route")
    if not switch_node:
        print("ERROR: 'Switch Route' not found!")
        return

    switch_rules = switch_node["parameters"]["conditions"]["conditions"]
    has_silence = any("cmd_silence" in json.dumps(r) for r in switch_rules)

    if has_silence:
        print("  Switch Route: cmd_silence output already present — skipping")
    else:
        new_rule = {
            "id": uid(),
            "operator": {
                "name": "filter.operator.equals",
                "type": "string",
                "operation": "equals"
            },
            "leftValue": "={{ $json.route }}",
            "rightValue": "cmd_silence"
        }
        # The rules are inside conditions which has a specific structure
        # Each rule in the Switch v3.2 has the nested format
        new_condition = {
            "id": uid(),
            "options": {
                "version": 2,
                "caseSensitive": True,
                "typeValidation": "strict"
            },
            "combinator": "and",
            "conditions": [{
                "id": uid(),
                "operator": {
                    "name": "filter.operator.equals",
                    "type": "string",
                    "operation": "equals"
                },
                "leftValue": "={{ $json.route }}",
                "rightValue": "cmd_silence"
            }]
        }

        # The switch conditions are stored as an array of rule objects
        # Each element maps to an output index
        rules = switch_node["parameters"]["conditions"]["conditions"]
        rules.append(new_condition)
        print(f"  Added Switch output {len(rules) - 1} for cmd_silence")

    # ── 3. Add silence handling nodes ──
    # Find a good position (below the brief flow)
    switch_pos = switch_node["position"]
    base_x = switch_pos[0] + 300
    base_y = switch_pos[1] + 1200  # Below existing routes

    # 3a. Send Checking Message
    send_checking_name = "Send Checking Silence"
    if not find_node(nodes, send_checking_name):
        nodes.append({
            "parameters": {
                "method": "POST",
                "url": "https://slack.com/api/chat.postMessage",
                "authentication": "genericCredentialType",
                "genericAuthType": "httpHeaderAuth",
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": '={\n  "channel": "{{ $json.channelId }}",\n  "text": ":mag: Checking your accounts for engagement gaps... give me about 30 seconds.",\n  "username": "{{ $json.assistantName }}",\n  "icon_emoji": "{{ $json.assistantEmoji }}"\n}',
                "options": {}
            },
            "id": uid(),
            "name": send_checking_name,
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [base_x, base_y],
            "credentials": {
                "httpHeaderAuth": {"id": CRED_SLACK, "name": "Slackbot Auth Token"}
            }
        })
        print(f"  Added '{send_checking_name}'")

    # 3b. Prepare Silence Input
    prepare_name = "Prepare Silence Input"
    if not find_node(nodes, prepare_name):
        nodes.append({
            "parameters": {
                "mode": "runOnceForAllItems",
                "jsCode": f"""const data = $('Route by State').first().json;
const user = data.userRecord || {{}};

return [{{ json: {{
  id: data.dbUserId,
  slack_user_id: data.userId,
  email: user.email || '',
  channelId: data.channelId,
  repName: (user.email || '').split('@')[0].replace(/\\./g, ' ').replace(/\\b\\w/g, c => c.toUpperCase()),
  assistantName: data.assistantName || 'Aria',
  assistantEmoji: data.assistantEmoji || ':robot_face:',
  assistantPersona: user.assistant_persona || '',
  digestScope: user.digest_scope || 'my_deals',
  organizationId: data.organizationId
}} }}];"""
            },
            "id": uid(),
            "name": prepare_name,
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [base_x + 250, base_y]
        })
        print(f"  Added '{prepare_name}'")

    # 3c. Execute On-Demand Silence Check
    execute_name = "Execute Silence Check"
    if not find_node(nodes, execute_name):
        nodes.append({
            "parameters": {
                "source": "database",
                "workflowId": silence_wf_id,
                "mode": "each"
            },
            "id": uid(),
            "name": execute_name,
            "type": "n8n-nodes-base.executeWorkflow",
            "typeVersion": 1.2,
            "position": [base_x + 500, base_y]
        })
        print(f"  Added '{execute_name}'")

    # 3d. Track Usage
    track_name = "Track Silence Usage"
    if not find_node(nodes, track_name):
        nodes.append({
            "parameters": {
                "method": "POST",
                "url": f"https://rhrlnkbphxntxxxcrgvv.supabase.co/rest/v1/rpc/track_feature_usage",
                "authentication": "predefinedCredentialType",
                "nodeCredentialType": "supabaseApi",
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": '={\n  "p_user_id": "{{ $("Route by State").first().json.dbUserId }}",\n  "p_feature_id": "silence_check"\n}',
                "options": {}
            },
            "id": uid(),
            "name": track_name,
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [base_x + 750, base_y],
            "credentials": {
                "supabaseApi": {"id": CRED_SUPABASE, "name": "Supabase account"}
            }
        })
        print(f"  Added '{track_name}'")

    # ── 4. Wire connections ──
    # Switch Route → Send Checking Silence (from the new output index)
    switch_name = "Switch Route"
    if switch_name not in connections:
        connections[switch_name] = {"main": []}

    # Ensure enough output arrays
    output_idx = len(switch_node["parameters"]["conditions"]["conditions"]) - 1
    while len(connections[switch_name]["main"]) <= output_idx:
        connections[switch_name]["main"].append([])

    # Check if already wired
    existing = [t["node"] for t in connections[switch_name]["main"][output_idx]]
    if send_checking_name not in existing:
        connections[switch_name]["main"][output_idx].append(
            {"node": send_checking_name, "type": "main", "index": 0}
        )
        print(f"  Connected Switch Route [{output_idx}] → {send_checking_name}")

    # Send Checking → Prepare Input
    if send_checking_name not in connections:
        connections[send_checking_name] = {"main": [[]]}
    existing = [t["node"] for t in connections[send_checking_name]["main"][0]]
    if prepare_name not in existing:
        connections[send_checking_name]["main"][0].append(
            {"node": prepare_name, "type": "main", "index": 0}
        )

    # Prepare Input → Execute Silence Check
    if prepare_name not in connections:
        connections[prepare_name] = {"main": [[]]}
    existing = [t["node"] for t in connections[prepare_name]["main"][0]]
    if execute_name not in existing:
        connections[prepare_name]["main"][0].append(
            {"node": execute_name, "type": "main", "index": 0}
        )

    # Execute → Track Usage
    if execute_name not in connections:
        connections[execute_name] = {"main": [[]]}
    existing = [t["node"] for t in connections[execute_name]["main"][0]]
    if track_name not in existing:
        connections[execute_name]["main"][0].append(
            {"node": track_name, "type": "main", "index": 0}
        )

    # ── 5. Update Build Help Response — add silence shortcut ──
    help_node = find_node(nodes, "Build Help Response")
    if help_node:
        help_code = help_node["parameters"]["jsCode"]

        if "'silence'" in help_code or '"silence"' in help_code:
            print("  Build Help Response: silence already present — skipping")
        else:
            # Add to details dict
            silence_detail = """
  silence: `*silence* — Check your accounts for engagement gaps right now.\\n\\nI'll scan your accounts (based on your ownership and CSM assignments) and report any that have gone quiet — no emails, meetings, or calls in 5+ days.\\n\\nSeverity levels:\\n• :large_blue_circle: Getting quiet (5-9 days)\\n• :warning: Gone silent (10-20 days)\\n• :red_circle: Relationship at risk (21+ days)\\n\\nThe daily cron also runs this automatically at 6:30am PT.`,"""

            # Find the details dict and add silence entry
            if "brief:" in help_code:
                # Add after the opening of details dict
                old = "  brief:"
                new = silence_detail + "\n  brief:"
                help_code = help_code.replace(old, new, 1)

            # Add alias
            if "aliases" in help_code and "'silent'" not in help_code:
                old = "'digest': 'brief'"
                new = "'digest': 'brief',\n    'silent': 'silence', 'silent accounts': 'silence', 'silence check': 'silence'"
                help_code = help_code.replace(old, new, 1)

            # Add to shortcuts list
            if "stakeholders" in help_code:
                # Find the shortcuts line and add silence
                old = "stakeholders"
                # Add silence before stakeholders in the shortcuts listing
                if "silence" not in help_code:
                    help_code = help_code.replace(
                        "brief · insights",
                        "brief · insights · silence",
                        1
                    )

            help_node["parameters"]["jsCode"] = help_code
            print("  Updated Build Help Response — added 'silence' to shortcuts + details")

    # ── Push ──
    print(f"\n=== Pushing Events Handler ===")
    result = push_workflow(WF_EVENTS_HANDLER, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")

    final = fetch_workflow(WF_EVENTS_HANDLER)
    sync_local(final, "Slack Events Handler.json")


def main():
    # Step 1: Create sub-workflow
    silence_wf_id = create_sub_workflow()

    # Step 2: Wire into Events Handler
    wire_events_handler(silence_wf_id)

    print("\n=== Done! ===")
    print(f"  On-Demand Silence Check workflow ID: {silence_wf_id}")
    print("  Commands: silence, silent, silent accounts, silence check")
    print("  Help text + details updated")


if __name__ == "__main__":
    main()
