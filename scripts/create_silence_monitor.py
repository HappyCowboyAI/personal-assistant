#!/usr/bin/env python3
"""
Create the Silence Contract Monitor workflow.

Daily cron (6:30am PT weekdays) that:
1. Fetches active users from Supabase
2. Fetches recent alerts for deduplication (72h cooldown)
3. For each user, calls a Claude agent + People.ai MCP to detect silent accounts
4. Parses the agent response for engagement gaps
5. Filters out already-alerted accounts (cooldown)
6. Sends a consolidated Slack DM per user with all new alerts
7. Logs each alert to alert_history in Supabase
"""

import json
import os
import uuid
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

SUPABASE_URL = "https://rhrlnkbphxntxxxcrgvv.supabase.co"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

# Credential references (live n8n)
SUPABASE_CRED = {"id": "ASRWWkQ0RSMOpNF1", "name": "Supabase account"}
ANTHROPIC_CRED = {"id": "rlAz7ZSl4y6AwRUq", "name": "Anthropic account 2"}
MCP_CRED = {"id": "wvV5pwBeIL7f2vLG", "name": "People.ai MCP Multi-Header"}
SLACK_CRED = {"id": "LluVuiMJ8NUbAiG7", "name": "Slackbot Auth Token"}


def uid():
    return str(uuid.uuid4())


# ── System prompt for the silence detection agent ──────────────────────

SILENCE_SYSTEM_PROMPT = r"""You are a sales engagement monitor. Your job is to detect "silence contracts" — accounts where customer engagement has gone quiet.

Using the People.ai tools available to you, check the user's accounts for engagement gaps:
1. Find the user's accounts that have open opportunities
2. For each account, check the most recent customer-facing activity (emails, meetings, calls)
3. Identify accounts where the last activity was more than 5 days ago

Classify each silent account by severity:
- "info" (5-9 days silent): Getting quiet
- "warning" (10-20 days silent): Gone silent
- "critical" (21+ days silent): Relationship at risk

CRITICAL: You MUST end your response with a JSON code block containing your findings in this exact format:
```json
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
```
If no accounts are silent (all had activity within the past 5 days), return:
```json
{"silent_accounts": []}
```

Do NOT include any text after the JSON code block."""


# ── Build alert message code ──────────────────────────────────────────

BUILD_ALERT_CODE = r"""const data = $input.first().json;
const alerts = data.newAlerts || [];

if (alerts.length === 0) {
  return [{ json: { ...data, hasAlerts: false, alertText: '' } }];
}

const severityEmoji = {
  critical: ':red_circle:',
  warning: ':large_orange_circle:',
  info: ':large_blue_circle:'
};

const severityLabel = {
  critical: 'Relationship at risk',
  warning: 'Gone silent',
  info: 'Getting quiet'
};

// Sort: critical first, then warning, then info
const order = { critical: 0, warning: 1, info: 2 };
alerts.sort((a, b) => (order[a.severity] || 9) - (order[b.severity] || 9));

let text = ':mag: *Silence Contract Alert*\n\n';
text += alerts.length === 1
  ? '1 account needs attention:\n\n'
  : `${alerts.length} accounts need attention:\n\n`;

for (const a of alerts) {
  const emoji = severityEmoji[a.severity] || ':white_circle:';
  const label = severityLabel[a.severity] || a.severity;
  const lastType = a.last_activity_type || 'activity';
  const lastDate = a.last_activity_date || 'unknown';
  text += `${emoji} *${a.account_name}* — ${a.days_silent} days silent`;
  if (lastDate !== 'unknown') {
    text += ` (last: ${lastType} on ${lastDate})`;
  }
  text += `\n_${label}_\n\n`;
}

text += '_Reply to discuss any of these accounts, or type `silence off` to pause these alerts._';

return [{ json: { ...data, hasAlerts: true, alertText: text } }];
"""


# ── Parse & dedup agent response ──────────────────────────────────────

PARSE_AND_DEDUP_CODE = r"""const agentOutput = $('Silence Monitor Agent').first().json.output || '';
const userData = $('Build Monitor Prompt').first().json;
const recentAlerts = userData.recentAlerts || [];

// Extract JSON from agent response
let silentAccounts = [];
const jsonMatch = agentOutput.match(/```json\s*([\s\S]*?)\s*```/);
if (jsonMatch) {
  try {
    const parsed = JSON.parse(jsonMatch[1]);
    silentAccounts = parsed.silent_accounts || [];
  } catch (e) {
    // If JSON parsing fails, try to extract from the full output
    try {
      const directParse = JSON.parse(agentOutput);
      silentAccounts = directParse.silent_accounts || [];
    } catch (e2) {
      // Give up parsing
    }
  }
}

// Build set of recently alerted entities for cooldown check
const alertedSet = new Set();
for (const alert of recentAlerts) {
  alertedSet.add(alert.entity_name.toLowerCase());
}

// Filter out already-alerted accounts
const newAlerts = silentAccounts.filter(a => {
  return !alertedSet.has((a.account_name || '').toLowerCase());
});

return [{
  json: {
    ...userData,
    allDetected: silentAccounts,
    newAlerts: newAlerts,
    detectedCount: silentAccounts.length,
    newAlertCount: newAlerts.length
  }
}];
"""


# ── Prepare user batch code ───────────────────────────────────────────

PREPARE_BATCH_CODE = r"""// Combine users with their recent alerts
// Get Active Users returns array, Get Recent Alerts returns array
const usersRaw = $('Get Active Users').first().json;
const alertsRaw = $('Get Recent Alerts').first().json;

// Handle both array responses and split-item responses
const users = Array.isArray(usersRaw) ? usersRaw : [usersRaw];
const alerts = Array.isArray(alertsRaw) ? alertsRaw : (alertsRaw.id ? [alertsRaw] : []);

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
  return [{ json: { skip: true } }];
}

return output;
"""


# ── Build monitor prompt code ─────────────────────────────────────────

BUILD_PROMPT_CODE = r"""const user = $input.first().json;

if (user.skip) {
  return [{ json: { ...user, monitorPrompt: '', skip: true } }];
}

const prompt = `Check my accounts for engagement gaps. Which accounts with open opportunities have had no customer-facing activity (emails, meetings, or calls) in the past 5 or more days? Today's date is ${new Date().toISOString().split('T')[0]}.`;

return [{
  json: {
    ...user,
    monitorPrompt: prompt
  }
}];
"""


# ── Log alerts code ───────────────────────────────────────────────────

LOG_ALERTS_CODE = r"""const data = $('Build Alert Message').first().json;
const sendResult = $('Send Alert DM').first().json;
const alerts = data.newAlerts || [];

// Build array of alert_history rows to insert
const rows = alerts.map(a => ({
  alert_type_id: 'silence_contract',
  user_id: data.userId,
  organization_id: data.organizationId,
  entity_type: 'account',
  entity_id: a.account_name.toLowerCase().replace(/\s+/g, '_'),
  entity_name: a.account_name,
  severity: a.severity,
  title: `${a.account_name} — ${a.days_silent} days silent`,
  body: data.alertText,
  detection_data: {
    days_silent: a.days_silent,
    last_activity_date: a.last_activity_date,
    last_activity_type: a.last_activity_type
  },
  delivered_at: new Date().toISOString(),
  delivery_channel: 'slack',
  slack_message_ts: sendResult.ts || null,
  slack_channel_id: sendResult.channel || null,
  status: 'delivered'
}));

return [{ json: { alertRows: rows } }];
"""


def build_workflow():
    nodes = []
    connections = {}

    # ── 1. Schedule Trigger ───────────────────────────────────────────
    trigger_id = uid()
    nodes.append({
        "parameters": {
            "rule": {
                "interval": [
                    {
                        "triggerAtHour": 6,
                        "triggerAtMinute": 30,
                        "triggerAtDay": [1, 2, 3, 4, 5],  # Mon-Fri
                    }
                ]
            },
        },
        "id": trigger_id,
        "name": "Daily 6:30am PT",
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.2,
        "position": [250, 300],
    })

    # ── 2. Get Active Users ───────────────────────────────────────────
    get_users_id = uid()
    nodes.append({
        "parameters": {
            "method": "GET",
            "url": f"{SUPABASE_URL}/rest/v1/users?onboarding_state=eq.complete&select=id,slack_user_id,email,assistant_name,assistant_emoji,organization_id,onboarding_state",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "supabaseApi",
            "options": {},
        },
        "id": get_users_id,
        "name": "Get Active Users",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [550, 300],
        "credentials": {"supabaseApi": SUPABASE_CRED},
    })
    connections["Daily 6:30am PT"] = {
        "main": [[{"node": "Get Active Users", "type": "main", "index": 0}]]
    }

    # ── 3. Get Recent Alerts ──────────────────────────────────────────
    get_alerts_id = uid()
    nodes.append({
        "parameters": {
            "method": "GET",
            "url": f"={SUPABASE_URL}/rest/v1/alert_history?alert_type_id=eq.silence_contract&created_at=gte.{{{{ new Date(Date.now() - 72*60*60*1000).toISOString() }}}}&select=user_id,entity_id,entity_name,severity,created_at",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "supabaseApi",
            "options": {},
        },
        "id": get_alerts_id,
        "name": "Get Recent Alerts",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [850, 300],
        "credentials": {"supabaseApi": SUPABASE_CRED},
    })
    connections["Get Active Users"] = {
        "main": [[{"node": "Get Recent Alerts", "type": "main", "index": 0}]]
    }

    # ── 4. Prepare User Batch ─────────────────────────────────────────
    prepare_id = uid()
    nodes.append({
        "parameters": {"jsCode": PREPARE_BATCH_CODE},
        "id": prepare_id,
        "name": "Prepare User Batch",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1150, 300],
    })
    connections["Get Recent Alerts"] = {
        "main": [[{"node": "Prepare User Batch", "type": "main", "index": 0}]]
    }

    # ── 5. Split In Batches ───────────────────────────────────────────
    split_id = uid()
    nodes.append({
        "parameters": {"options": {}},
        "id": split_id,
        "name": "Split In Batches",
        "type": "n8n-nodes-base.splitInBatches",
        "typeVersion": 3,
        "position": [1450, 300],
    })
    connections["Prepare User Batch"] = {
        "main": [[{"node": "Split In Batches", "type": "main", "index": 0}]]
    }

    # ── 6. Build Monitor Prompt ───────────────────────────────────────
    build_prompt_id = uid()
    nodes.append({
        "parameters": {"jsCode": BUILD_PROMPT_CODE},
        "id": build_prompt_id,
        "name": "Build Monitor Prompt",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1750, 300],
    })
    # SplitInBatches output 1 = loop items
    connections["Split In Batches"] = {
        "main": [
            [],  # output 0 = done (nothing connected)
            [{"node": "Build Monitor Prompt", "type": "main", "index": 0}],  # output 1 = loop
        ]
    }

    # ── 7. Silence Monitor Agent ──────────────────────────────────────
    agent_id = uid()
    nodes.append({
        "parameters": {
            "promptType": "define",
            "text": '={{ $json.monitorPrompt }}',
            "options": {
                "systemMessage": SILENCE_SYSTEM_PROMPT,
                "maxIterations": 15,
            },
        },
        "id": agent_id,
        "name": "Silence Monitor Agent",
        "type": "@n8n/n8n-nodes-langchain.agent",
        "typeVersion": 1.7,
        "position": [2050, 300],
        "continueOnFail": True,
    })
    connections["Build Monitor Prompt"] = {
        "main": [[{"node": "Silence Monitor Agent", "type": "main", "index": 0}]]
    }

    # ── 8. Anthropic Chat Model (sub-node) ────────────────────────────
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
        "name": "Anthropic Chat Model (Silence)",
        "type": "@n8n/n8n-nodes-langchain.lmChatAnthropic",
        "typeVersion": 1.3,
        "position": [1950, 520],
        "credentials": {"anthropicApi": ANTHROPIC_CRED},
    })
    connections["Anthropic Chat Model (Silence)"] = {
        "ai_languageModel": [
            [{"node": "Silence Monitor Agent", "type": "ai_languageModel", "index": 0}]
        ]
    }

    # ── 9. People.ai MCP (sub-node) ───────────────────────────────────
    mcp_id = uid()
    nodes.append({
        "parameters": {
            "endpointUrl": "https://mcp.people.ai/mcp",
            "authentication": "multipleHeadersAuth",
            "options": {},
        },
        "id": mcp_id,
        "name": "People.ai MCP (Silence)",
        "type": "@n8n/n8n-nodes-langchain.mcpClientTool",
        "typeVersion": 1.2,
        "position": [2150, 520],
        "credentials": {"httpMultipleHeadersAuth": MCP_CRED},
    })
    connections["People.ai MCP (Silence)"] = {
        "ai_tool": [
            [{"node": "Silence Monitor Agent", "type": "ai_tool", "index": 0}]
        ]
    }

    # ── 10. Parse & Dedup ─────────────────────────────────────────────
    parse_id = uid()
    nodes.append({
        "parameters": {"jsCode": PARSE_AND_DEDUP_CODE},
        "id": parse_id,
        "name": "Parse & Dedup",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [2350, 300],
    })
    connections["Silence Monitor Agent"] = {
        "main": [[{"node": "Parse & Dedup", "type": "main", "index": 0}]]
    }

    # ── 11. Build Alert Message ───────────────────────────────────────
    build_msg_id = uid()
    nodes.append({
        "parameters": {"jsCode": BUILD_ALERT_CODE},
        "id": build_msg_id,
        "name": "Build Alert Message",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [2650, 300],
    })
    connections["Parse & Dedup"] = {
        "main": [[{"node": "Build Alert Message", "type": "main", "index": 0}]]
    }

    # ── 12. Has New Alerts? ───────────────────────────────────────────
    has_alerts_id = uid()
    nodes.append({
        "parameters": {
            "conditions": {
                "options": {"version": 2, "leftValue": "", "caseSensitive": True, "typeValidation": "strict"},
                "conditions": [
                    {
                        "id": uid(),
                        "leftValue": "={{ $json.hasAlerts }}",
                        "rightValue": True,
                        "operator": {"type": "boolean", "operation": "equals"},
                    }
                ],
                "combinator": "and",
            },
            "options": {},
        },
        "id": has_alerts_id,
        "name": "Has New Alerts?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [2950, 300],
    })
    connections["Build Alert Message"] = {
        "main": [[{"node": "Has New Alerts?", "type": "main", "index": 0}]]
    }

    # ── 13. Open Bot DM ──────────────────────────────────────────────
    open_dm_id = uid()
    nodes.append({
        "parameters": {
            "method": "POST",
            "url": "https://slack.com/api/conversations.open",
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Content-Type", "value": "application/json"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": '={{ JSON.stringify({ users: $json.slackUserId }) }}',
            "options": {},
        },
        "id": open_dm_id,
        "name": "Open Bot DM",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [3250, 300],
        "credentials": {"httpHeaderAuth": SLACK_CRED},
    })

    # ── 14. Send Alert DM ────────────────────────────────────────────
    send_dm_id = uid()
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
            "jsonBody": '={{ JSON.stringify({ channel: $json.channel.id, text: $("Build Alert Message").first().json.alertText, username: $("Build Alert Message").first().json.assistantName, icon_emoji: $("Build Alert Message").first().json.assistantEmoji }) }}',
            "options": {},
        },
        "id": send_dm_id,
        "name": "Send Alert DM",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [3550, 300],
        "credentials": {"httpHeaderAuth": SLACK_CRED},
    })

    # ── 15. Prepare Alert Logs ────────────────────────────────────────
    log_prep_id = uid()
    nodes.append({
        "parameters": {"jsCode": LOG_ALERTS_CODE},
        "id": log_prep_id,
        "name": "Prepare Alert Logs",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [3850, 300],
    })

    # ── 16. Log Alerts to DB ──────────────────────────────────────────
    log_id = uid()
    nodes.append({
        "parameters": {
            "method": "POST",
            "url": f"{SUPABASE_URL}/rest/v1/alert_history",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "supabaseApi",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Prefer", "value": "return=representation"},
                    {"name": "Content-Type", "value": "application/json"},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": '={{ JSON.stringify($json.alertRows) }}',
            "options": {},
        },
        "id": log_id,
        "name": "Log Alerts to DB",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [4150, 300],
        "credentials": {"supabaseApi": SUPABASE_CRED},
    })

    # ── Wire the alert delivery chain ─────────────────────────────────

    # Has New Alerts? → true (output 0) → Open Bot DM
    # Has New Alerts? → false (output 1) → loop back to Split
    connections["Has New Alerts?"] = {
        "main": [
            [{"node": "Open Bot DM", "type": "main", "index": 0}],
            [{"node": "Split In Batches", "type": "main", "index": 0}],
        ]
    }

    connections["Open Bot DM"] = {
        "main": [[{"node": "Send Alert DM", "type": "main", "index": 0}]]
    }
    connections["Send Alert DM"] = {
        "main": [[{"node": "Prepare Alert Logs", "type": "main", "index": 0}]]
    }
    connections["Prepare Alert Logs"] = {
        "main": [[{"node": "Log Alerts to DB", "type": "main", "index": 0}]]
    }
    connections["Log Alerts to DB"] = {
        "main": [[{"node": "Split In Batches", "type": "main", "index": 0}]]
    }

    return {
        "name": "Silence Contract Monitor",
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1"},
        "staticData": None,
    }


def main():
    print("Building Silence Contract Monitor workflow...")
    workflow = build_workflow()
    print(f"  {len(workflow['nodes'])} nodes")

    # Check if workflow already exists
    print("\nChecking for existing workflow...")
    resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows", headers=HEADERS)
    resp.raise_for_status()
    existing = resp.json()
    existing_wf = None
    for wf in existing.get("data", []):
        if wf["name"] == "Silence Contract Monitor":
            existing_wf = wf
            break

    if existing_wf:
        wf_id = existing_wf["id"]
        print(f"  Found existing workflow: {wf_id}")
        print("  Updating...")
        payload = {
            "name": workflow["name"],
            "nodes": workflow["nodes"],
            "connections": workflow["connections"],
            "settings": workflow["settings"],
            "staticData": workflow["staticData"],
        }
        resp = requests.put(
            f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}",
            headers=HEADERS,
            json=payload,
        )
        resp.raise_for_status()
        print(f"  Updated workflow {wf_id}")
    else:
        print("  Creating new workflow...")
        resp = requests.post(
            f"{N8N_BASE_URL}/api/v1/workflows",
            headers=HEADERS,
            json=workflow,
        )
        resp.raise_for_status()
        result = resp.json()
        wf_id = result["id"]
        print(f"  Created workflow: {wf_id}")

    # Activate
    print("\nActivating workflow...")
    resp = requests.post(
        f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}/activate",
        headers=HEADERS,
    )
    resp.raise_for_status()
    print("  Activated")

    # Sync local file
    print("\nSyncing local file...")
    resp = requests.get(
        f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}",
        headers=HEADERS,
    )
    resp.raise_for_status()
    final = resp.json()
    path = os.path.join(REPO_ROOT, "n8n", "workflows", "Silence Contract Monitor.json")
    with open(path, "w") as f:
        json.dump(final, f, indent=4)
    print(f"  Synced to {path}")

    print(f"\nDone! Silence Contract Monitor workflow created.")
    print(f"  Workflow ID: {wf_id}")
    print(f"  Schedule: 6:30am PT, weekdays")
    print(f"  Nodes: {len(final['nodes'])}")
    print(f"\n  IMPORTANT: Run the 006_watchdog_alerts.sql migration in Supabase first!")


if __name__ == "__main__":
    main()
