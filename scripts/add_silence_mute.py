#!/usr/bin/env python3
"""
Add dead account detection + interactive mute buttons to silence alerts.

Changes three workflows:
1. Silence Contract Monitor (cron) — Parse & Dedup, Build Alert Message, Send Alert DM
2. On-Demand Silence Check — Parse Silence Results, Build Alert Message
3. Interactive Events Handler — Route Action + new mute handler nodes

Design spec: docs/superpowers/specs/2026-03-10-dead-account-detection-design.md
"""

import json
from n8n_helpers import (
    find_node, fetch_workflow, push_workflow, sync_local,
    uid, make_code_node, make_supabase_http_node, make_slack_http_node,
    WF_SILENCE_MONITOR, WF_INTERACTIVE_HANDLER,
    SLACK_CHAT_UPDATE,
)


# ── JavaScript code constants ──────────────────────────────────────────

PARSE_DEDUP_CODE = r"""const agentOutput = $('Silence Monitor Agent').first().json.output || '';
const userData = $('Build Monitor Prompt').first().json;
const recentAlerts = userData.recentAlerts || [];

// Get all muted accounts (fetched before the loop)
let allMutedAccounts = [];
try {
  allMutedAccounts = $('Fetch Muted Accounts').all().map(i => i.json);
} catch (e) { /* node didn't run */ }

// Build per-user muted set (check muted_until expiry)
const now = new Date();
const mutedSet = new Set();
for (const m of allMutedAccounts) {
  if (m.user_id !== userData.userId) continue;
  if (m.muted_until && new Date(m.muted_until) < now) continue; // snooze expired
  mutedSet.add((m.entity_name || '').toLowerCase());
}

// Extract JSON from agent response
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

// Build set of recently alerted entities for cooldown check
const alertedSet = new Set();
for (const alert of recentAlerts) {
  alertedSet.add(alert.entity_name.toLowerCase());
}

// Reclassify 60+ day accounts as 'dead'
for (const a of silentAccounts) {
  if ((a.days_silent || 0) >= 60) {
    a.severity = 'dead';
  }
}

// Filter out muted and recently alerted accounts
const newAlerts = silentAccounts.filter(a => {
  const name = (a.account_name || '').toLowerCase();
  if (mutedSet.has(name)) return false;
  if (alertedSet.has(name)) return false;
  return true;
});

// Identify dead accounts to auto-mute after this alert
const autoMuteAccounts = newAlerts
  .filter(a => a.severity === 'dead')
  .map(a => ({
    user_id: userData.userId,
    organization_id: userData.organizationId,
    alert_type_id: 'silence_contract',
    entity_name: a.account_name,
    mute_reason: 'auto_dead',
    muted_at: now.toISOString()
  }));

return [{
  json: {
    ...userData,
    allDetected: silentAccounts,
    newAlerts,
    autoMuteAccounts,
    detectedCount: silentAccounts.length,
    newAlertCount: newAlerts.length
  }
}];"""


BUILD_ALERT_MSG_CODE = r"""const data = $input.first().json;
const alerts = data.newAlerts || [];

if (alerts.length === 0) {
  return [{ json: { ...data, hasAlerts: false, alertBlocks: '[]', alertText: '' } }];
}

const severityEmoji = {
  dead: ':skull:',
  critical: ':red_circle:',
  warning: ':large_orange_circle:',
  info: ':large_blue_circle:'
};

// Sort: dead first, then critical, warning, info
const order = { dead: 0, critical: 1, warning: 2, info: 3 };
alerts.sort((a, b) => (order[a.severity] || 9) - (order[b.severity] || 9));

const blocks = [
  {
    type: "section",
    text: {
      type: "mrkdwn",
      text: `:mag: *Silence Contract Alert*\n${alerts.length} account${alerts.length === 1 ? '' : 's'} need${alerts.length === 1 ? 's' : ''} attention:`
    }
  }
];

for (const a of alerts) {
  const emoji = severityEmoji[a.severity] || ':white_circle:';
  const lastType = a.last_activity_type || 'activity';
  const lastDate = a.last_activity_date || 'unknown';
  let line = `${emoji} *${a.account_name}* — ${a.days_silent} days silent`;
  if (lastDate !== 'unknown') {
    line += ` (last: ${lastType} on ${lastDate})`;
  }

  // Slack overflow value has 75-char max. Use compact format: "action|accountName"
  const acctName = a.account_name;

  blocks.push({
    type: "section",
    text: { type: "mrkdwn", text: line },
    accessory: {
      type: "overflow",
      action_id: "silence_overflow_" + blocks.length,
      options: [
        {
          text: { type: "plain_text", text: "Snooze 7d" },
          value: ("s7|" + acctName).slice(0, 75)
        },
        {
          text: { type: "plain_text", text: "Snooze 30d" },
          value: ("s30|" + acctName).slice(0, 75)
        },
        {
          text: { type: "plain_text", text: "Mark as Lost" },
          value: ("ml|" + acctName).slice(0, 75)
        }
      ]
    }
  });
}

blocks.push({
  type: "context",
  elements: [{ type: "mrkdwn", text: "Use the menu on each account to snooze or mute alerts." }]
});

// Enforce Slack limits
if (blocks.length > 50) blocks.length = 50;
for (const b of blocks) {
  if (b.text && b.text.text && b.text.text.length > 3000) {
    b.text.text = b.text.text.slice(0, 2997) + '...';
  }
}

let plainText = alerts.length + ' account' + (alerts.length === 1 ? '' : 's') + ' need attention in silence check';

return [{ json: { ...data, hasAlerts: true, alertBlocks: JSON.stringify(blocks), alertText: plainText } }];"""


AUTO_MUTE_PREP_CODE = r"""// Prepare auto-mute payload for dead accounts
const data = $input.first().json;
const autoMute = data.autoMuteAccounts || [];

if (autoMute.length === 0) {
  return [{ json: { ...data, autoMuted: 0 } }];
}

return [{ json: { ...data, autoMutePayload: autoMute, autoMuted: autoMute.length } }];"""


PARSE_RESULTS_OD_CODE = r"""const agentOutput = $('Silence Agent').first().json.output || '';
const inputData = $('Build Silence Prompt').first().json;

// Get muted accounts
let allMuted = [];
try {
  allMuted = $('Fetch Muted Accounts').all().map(i => i.json);
} catch (e) {}

const now = new Date();
const userId = inputData.userId;
const mutedSet = new Set();
for (const m of allMuted) {
  if (m.user_id !== userId) continue;
  if (m.muted_until && new Date(m.muted_until) < now) continue;
  mutedSet.add((m.entity_name || '').toLowerCase());
}

// Extract JSON from agent response
let silentAccounts = [];
const jsonMatch = agentOutput.match(/```json\s*([\s\S]*?)\s*```/);
if (jsonMatch) {
  try {
    silentAccounts = JSON.parse(jsonMatch[1]).silent_accounts || [];
  } catch (e) {}
}

// Reclassify 60+ day accounts as 'dead'
for (const a of silentAccounts) {
  if ((a.days_silent || 0) >= 60) a.severity = 'dead';
}

// Filter out muted
const filtered = silentAccounts.filter(a => !mutedSet.has((a.account_name || '').toLowerCase()));

// Sort by severity then days
const order = { dead: 0, critical: 1, warning: 2, info: 3 };
filtered.sort((a, b) => (order[a.severity] || 9) - (order[b.severity] || 9) || (b.days_silent || 0) - (a.days_silent || 0));

// Dead accounts to auto-mute
const autoMuteAccounts = filtered
  .filter(a => a.severity === 'dead')
  .map(a => ({
    user_id: userId,
    organization_id: inputData.organizationId,
    alert_type_id: 'silence_contract',
    entity_name: a.account_name,
    mute_reason: 'auto_dead',
    muted_at: now.toISOString()
  }));

return [{ json: {
  ...inputData,
  silentAccounts: filtered,
  autoMuteAccounts,
  silentCount: filtered.length
} }];"""


BUILD_ALERT_OD_CODE = r"""const data = $input.first().json;
const accounts = data.silentAccounts || [];

if (accounts.length === 0) {
  return [{ json: { ...data, blocks: JSON.stringify([
    { type: "section", text: { type: "mrkdwn", text: ":white_check_mark: *All clear!* None of your accounts have gone silent. Everything looks active." } }
  ]), notificationText: "All accounts active" } }];
}

const severityEmoji = { dead: ':skull:', critical: ':red_circle:', warning: ':large_orange_circle:', info: ':large_blue_circle:' };

const blocks = [
  { type: "section", text: { type: "mrkdwn", text: `:mag: *Silence Contract Check*\n${accounts.length} account${accounts.length === 1 ? '' : 's'} need${accounts.length === 1 ? 's' : ''} attention:` } }
];

for (const acct of accounts) {
  const emoji = severityEmoji[acct.severity] || ':grey_question:';
  const lastDate = acct.last_activity_date ? ` (last: ${acct.last_activity_type || 'activity'} on ${acct.last_activity_date})` : '';
  const line = `${emoji} *${acct.account_name}* \u2014 ${acct.days_silent} days silent${lastDate}`;

  const acctName = acct.account_name;

  blocks.push({
    type: "section",
    text: { type: "mrkdwn", text: line },
    accessory: {
      type: "overflow",
      action_id: "silence_overflow_" + blocks.length,
      options: [
        { text: { type: "plain_text", text: "Snooze 7d" }, value: ("s7|" + acctName).slice(0, 75) },
        { text: { type: "plain_text", text: "Snooze 30d" }, value: ("s30|" + acctName).slice(0, 75) },
        { text: { type: "plain_text", text: "Mark as Lost" }, value: ("ml|" + acctName).slice(0, 75) }
      ]
    }
  });
}

blocks.push({ type: "context", elements: [{ type: "mrkdwn", text: "Use the menu on each account to snooze or mute alerts." }] });

if (blocks.length > 50) blocks.length = 50;
for (const b of blocks) {
  if (b.text && b.text.text && b.text.text.length > 3000) {
    b.text.text = b.text.text.slice(0, 2997) + '...';
  }
}

return [{ json: { ...data, blocks: JSON.stringify(blocks), notificationText: accounts.length + ' silent account' + (accounts.length === 1 ? '' : 's') + ' found' } }];"""


PARSE_MUTE_CODE = r"""// Parse overflow menu selection and build mute payload + updated message
const payload = $('Parse Interactive Payload').first().json;
const selectedValue = payload.selectedOptionValue || '';
const messageBlocks = payload.messageBlocks || [];

// Parse compact "action|accountName" format (e.g. "s7|Elastic", "ml|Cyberhaven")
const pipeIdx = selectedValue.indexOf('|');
if (pipeIdx === -1) {
  return [{ json: { error: 'Invalid selection value', selectedValue } }];
}

const actionCode = selectedValue.substring(0, pipeIdx);
const accountName = selectedValue.substring(pipeIdx + 1);

// Get userId and organizationId from Lookup User (Action) — already fetched by the handler
const userRecord = $('Lookup User (Action)').first().json;
const userId = userRecord.id || '';
const organizationId = userRecord.organization_id || '';

// Determine mute parameters
let muteReason, mutedUntil, confirmText;
const now = new Date();

if (actionCode === 's7') {
  muteReason = 'snoozed';
  const until = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000);
  mutedUntil = until.toISOString();
  confirmText = `:white_check_mark: *${accountName}* snoozed for 7 days.`;
} else if (actionCode === 's30') {
  muteReason = 'snoozed';
  const until = new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000);
  mutedUntil = until.toISOString();
  confirmText = `:white_check_mark: *${accountName}* snoozed for 30 days.`;
} else if (actionCode === 'ml') {
  muteReason = 'marked_lost';
  mutedUntil = null;
  confirmText = `:white_check_mark: *${accountName}* muted — consider closing the open opps in Salesforce.`;
} else {
  return [{ json: { error: 'Unknown action: ' + actionCode } }];
}

// Build mute row for upsert
const mutePayload = {
  user_id: userId,
  organization_id: organizationId,
  alert_type_id: 'silence_contract',
  entity_name: accountName,
  mute_reason: muteReason,
  muted_at: now.toISOString(),
  muted_until: mutedUntil,
  unmuted_at: null
};

// Rebuild message blocks — replace the actioned account's section with confirmation
const updatedBlocks = [];
for (const block of messageBlocks) {
  if (block.type === 'section' && block.text && block.text.text &&
      block.text.text.includes('*' + accountName + '*') && block.accessory) {
    // Replace this section with confirmation (no accessory)
    updatedBlocks.push({
      type: 'section',
      text: { type: 'mrkdwn', text: confirmText }
    });
  } else {
    updatedBlocks.push(block);
  }
}

return [{ json: {
  mutePayload,
  updatedBlocks: JSON.stringify(updatedBlocks),
  channelId: payload.channelId,
  messageTs: payload.messageTs,
  accountName,
  confirmText
} }];"""


# ── Workflow modification functions ────────────────────────────────────

def update_silence_monitor():
    """Update Silence Contract Monitor cron with dead detection + Block Kit + mute filtering."""
    print("=== Updating Silence Contract Monitor ===\n")
    wf = fetch_workflow(WF_SILENCE_MONITOR)
    nodes = wf["nodes"]
    connections = wf["connections"]

    # ── 1. Add "Fetch Muted Accounts" node ──
    fetch_mutes_name = "Fetch Muted Accounts"
    if not find_node(nodes, fetch_mutes_name):
        prep_node = find_node(nodes, "Prepare User Batch")
        prep_pos = prep_node["position"]

        fetch_mutes = make_supabase_http_node(
            name=fetch_mutes_name,
            method="GET",
            url_path="muted_alerts?alert_type_id=eq.silence_contract&unmuted_at=is.null&select=user_id,entity_name,muted_until",
            position=[prep_pos[0] + 224, prep_pos[1] + 100],
        )
        nodes.append(fetch_mutes)

        # Connect in PARALLEL — do NOT wire in series through SplitInBatches
        prep_conns = connections.get("Prepare User Batch", {}).get("main", [[]])
        already_connected = any(c["node"] == fetch_mutes_name for c in prep_conns[0])
        if not already_connected:
            prep_conns[0].append({"node": fetch_mutes_name, "type": "main", "index": 0})
            connections["Prepare User Batch"]["main"] = prep_conns
        connections[fetch_mutes_name] = {"main": [[]]}

        print(f"  Added '{fetch_mutes_name}' (parallel)")
    else:
        print(f"  '{fetch_mutes_name}' already exists")

    # ── 2. Update Parse & Dedup ──
    parse_node = find_node(nodes, "Parse & Dedup")
    parse_node["parameters"]["jsCode"] = PARSE_DEDUP_CODE
    print("  Updated 'Parse & Dedup'")

    # ── 3. Add Auto-Mute Dead Accounts + Insert Dead Mutes ──
    auto_mute_name = "Auto-Mute Dead Accounts"
    if not find_node(nodes, auto_mute_name):
        log_node = find_node(nodes, "Log Alerts to DB")
        log_pos = log_node["position"]

        auto_mute_prep = make_code_node(auto_mute_name, AUTO_MUTE_PREP_CODE,
                                         [log_pos[0] + 224, log_pos[1]])
        nodes.append(auto_mute_prep)

        # Get existing Log Alerts → Split In Batches connection
        log_targets = connections.get("Log Alerts to DB", {"main": [[]]})["main"][0]
        loop_back = [t for t in log_targets if t["node"] == "Split In Batches"]

        # Rewire: Log Alerts → Auto-Mute Dead
        connections["Log Alerts to DB"]["main"][0] = [
            {"node": auto_mute_name, "type": "main", "index": 0}
        ]

        # Insert Dead Mutes node
        insert_mutes_name = "Insert Dead Mutes"
        insert_mutes = make_supabase_http_node(
            name=insert_mutes_name,
            method="POST",
            url_path="muted_alerts",
            position=[log_pos[0] + 448, log_pos[1]],
            json_body='={{ JSON.stringify($json.autoMutePayload || []) }}',
            extra_headers=[
                {"name": "Prefer", "value": "resolution=merge-duplicates,return=representation"},
                {"name": "Content-Type", "value": "application/json"}
            ],
        )
        nodes.append(insert_mutes)

        # Wire: Auto-Mute → Insert Dead Mutes → loop back to Split In Batches
        connections[auto_mute_name] = {"main": [[
            {"node": insert_mutes_name, "type": "main", "index": 0}
        ]]}
        connections[insert_mutes_name] = {"main": [
            loop_back if loop_back else [{"node": "Split In Batches", "type": "main", "index": 0}]
        ]}

        print(f"  Added '{auto_mute_name}' + '{insert_mutes_name}'")
    else:
        print(f"  '{auto_mute_name}' already exists")

    # ── 4. Update Build Alert Message ──
    alert_msg_node = find_node(nodes, "Build Alert Message")
    alert_msg_node["parameters"]["jsCode"] = BUILD_ALERT_MSG_CODE
    print("  Updated 'Build Alert Message' — Block Kit with overflow menus")

    # ── 5. Update Send Alert DM to use blocks ──
    send_node = find_node(nodes, "Send Alert DM")
    # Already uses specifyBody: "json" with cross-node refs. Update to include blocks.
    send_node["parameters"]["jsonBody"] = (
        '={{ JSON.stringify({ '
        'channel: $json.channel.id, '
        'blocks: JSON.parse($("Build Alert Message").first().json.alertBlocks), '
        'text: $("Build Alert Message").first().json.alertText, '
        'username: $("Build Alert Message").first().json.assistantName, '
        'icon_emoji: $("Build Alert Message").first().json.assistantEmoji '
        '}) }}'
    )
    print("  Updated 'Send Alert DM' — sends blocks")

    return wf


def update_on_demand_silence():
    """Update On-Demand Silence Check with dead detection + overflow menus + mute filtering."""
    print("\n=== Updating On-Demand Silence Check ===\n")
    wf = fetch_workflow("7QaWpTuTp6oNVFjM")
    nodes = wf["nodes"]
    connections = wf["connections"]

    # ── 1. Add Fetch Muted Accounts (parallel, no downstream) ──
    fetch_mutes_name = "Fetch Muted Accounts"
    if not find_node(nodes, fetch_mutes_name):
        agent_node = find_node(nodes, "Silence Agent")
        agent_pos = agent_node["position"]

        fetch_mutes = make_supabase_http_node(
            name=fetch_mutes_name,
            method="GET",
            url_path="muted_alerts?alert_type_id=eq.silence_contract&unmuted_at=is.null&select=user_id,entity_name,muted_until",
            position=[agent_pos[0], agent_pos[1] + 150],
        )
        nodes.append(fetch_mutes)

        # Connect from Build Silence Prompt in parallel — no downstream connection
        if "Build Silence Prompt" not in connections:
            connections["Build Silence Prompt"] = {"main": [[]]}
        connections["Build Silence Prompt"]["main"][0].append(
            {"node": fetch_mutes_name, "type": "main", "index": 0}
        )
        connections[fetch_mutes_name] = {"main": [[]]}
        print(f"  Added '{fetch_mutes_name}' (parallel)")
    else:
        print(f"  '{fetch_mutes_name}' already exists")

    # ── 2. Update Parse Silence Results ──
    parse_node = find_node(nodes, "Parse Silence Results")
    parse_node["parameters"]["jsCode"] = PARSE_RESULTS_OD_CODE
    print("  Updated 'Parse Silence Results'")

    # ── 3. Update Build Alert Message ──
    alert_node = find_node(nodes, "Build Alert Message")
    alert_node["parameters"]["jsCode"] = BUILD_ALERT_OD_CODE
    print("  Updated 'Build Alert Message' — overflow menus")

    # ── 4. Add Auto-Mute Dead (OD) after Send Silence Check ──
    auto_mute_name = "Auto-Mute Dead (OD)"
    if not find_node(nodes, auto_mute_name):
        send_node = find_node(nodes, "Send Silence Check")
        send_pos = send_node["position"]

        auto_mute = make_supabase_http_node(
            name=auto_mute_name,
            method="POST",
            url_path="muted_alerts",
            position=[send_pos[0] + 224, send_pos[1]],
            json_body='={{ JSON.stringify($json.autoMuteAccounts || []) }}',
            extra_headers=[
                {"name": "Prefer", "value": "resolution=merge-duplicates,return=representation"},
                {"name": "Content-Type", "value": "application/json"}
            ],
        )
        nodes.append(auto_mute)

        # Wire: Send Silence Check → Auto-Mute Dead (OD)
        if "Send Silence Check" not in connections:
            connections["Send Silence Check"] = {"main": [[]]}
        existing_targets = connections["Send Silence Check"]["main"][0]
        connections["Send Silence Check"]["main"][0] = [
            {"node": auto_mute_name, "type": "main", "index": 0}
        ]
        connections[auto_mute_name] = {"main": [existing_targets]}

        print(f"  Added '{auto_mute_name}'")
    else:
        print(f"  '{auto_mute_name}' already exists")

    return wf


def update_interactive_handler():
    """Add silence mute button handlers to Interactive Events Handler."""
    print("\n=== Updating Interactive Events Handler ===\n")
    wf = fetch_workflow(WF_INTERACTIVE_HANDLER)
    nodes = wf["nodes"]
    connections = wf["connections"]

    # ── 1. Update Parse Interactive Payload — add selectedOptionValue + messageBlocks ──
    parse_node = find_node(nodes, "Parse Interactive Payload")
    code = parse_node["parameters"]["jsCode"]

    if "selectedOptionValue" not in code:
        old_line = "const actionValue = (payload.actions && payload.actions[0]) ? (payload.actions[0].value || '') : '';"
        new_line = (
            "const actionValue = (payload.actions && payload.actions[0]) ? (payload.actions[0].value || '') : '';\n"
            "const selectedOptionValue = (payload.actions && payload.actions[0] && payload.actions[0].selected_option) "
            "? payload.actions[0].selected_option.value : '';"
        )
        if old_line in code:
            code = code.replace(old_line, new_line)
            print("  Added selectedOptionValue extraction")
        else:
            print("  WARNING: Could not find actionValue line — adding selectedOptionValue manually")

    if "messageBlocks" not in code:
        old_return = "return [{ json: { type, userId, triggerId, actionId, actionValue, messageTs, channelId, callbackId, submittedValues } }];"
        new_return = (
            "const messageBlocks = payload.message ? (payload.message.blocks || []) : [];\n"
            "\n"
            "return [{ json: { type, userId, triggerId, actionId, actionValue, selectedOptionValue, "
            "messageTs, channelId, messageBlocks, callbackId, submittedValues } }];"
        )
        if old_return in code:
            code = code.replace(old_return, new_return)
            print("  Added messageBlocks + selectedOptionValue to output")
        else:
            print("  WARNING: Could not find return statement — check Parse Interactive Payload manually")

    parse_node["parameters"]["jsCode"] = code

    # ── 2. Add silence_overflow route to Route Action Switch ──
    route_node = find_node(nodes, "Route Action")
    rules = route_node["parameters"]["rules"]["values"]

    silence_route_exists = any(
        "silence" in str(r.get("outputKey", "")).lower()
        for r in rules
    )

    if not silence_route_exists:
        silence_rule = {
            "outputKey": "Silence Mute",
            "renameOutput": True,
            "conditions": {
                "options": {
                    "version": 2,
                    "leftValue": "",
                    "caseSensitive": True,
                    "typeValidation": "strict",
                },
                "combinator": "and",
                "conditions": [{
                    "id": uid(),
                    "operator": {
                        "name": "filter.operator.startsWith",
                        "type": "string",
                        "operation": "startsWith",
                    },
                    "leftValue": "={{ $('Parse Interactive Payload').first().json.actionId }}",
                    "rightValue": "silence_overflow_",
                }],
            },
        }
        rules.append(silence_rule)
        print(f"  Added 'Silence Mute' route (output {len(rules) - 1})")
    else:
        print("  Silence route already exists")

    # ── 3. Add Parse Mute Action node ──
    parse_mute_name = "Parse Mute Action"
    if not find_node(nodes, parse_mute_name):
        route_pos = route_node["position"]
        parse_mute_node = make_code_node(
            parse_mute_name, PARSE_MUTE_CODE,
            [route_pos[0] + 400, route_pos[1] + 400]
        )
        nodes.append(parse_mute_node)
        print(f"  Added '{parse_mute_name}'")
    else:
        print(f"  '{parse_mute_name}' already exists")

    # ── 4. Add Upsert Mute node ──
    upsert_name = "Upsert Mute"
    if not find_node(nodes, upsert_name):
        pm_node = find_node(nodes, parse_mute_name)
        pm_pos = pm_node["position"]

        upsert_node = make_supabase_http_node(
            name=upsert_name,
            method="POST",
            url_path="muted_alerts",
            position=[pm_pos[0] + 250, pm_pos[1]],
            json_body='={{ JSON.stringify($json.mutePayload) }}',
            extra_headers=[
                {"name": "Prefer", "value": "resolution=merge-duplicates,return=representation"},
                {"name": "Content-Type", "value": "application/json"}
            ],
        )
        nodes.append(upsert_node)
        print(f"  Added '{upsert_name}'")
    else:
        print(f"  '{upsert_name}' already exists")

    # ── 5. Add Update Alert Message node ──
    update_msg_name = "Update Alert Message"
    if not find_node(nodes, update_msg_name):
        u_node = find_node(nodes, upsert_name)
        u_pos = u_node["position"]

        # Use cross-node refs — $json after Upsert Mute is the Supabase response
        update_body = (
            '={{ JSON.stringify({ '
            'channel: $("Parse Mute Action").first().json.channelId, '
            'ts: $("Parse Mute Action").first().json.messageTs, '
            'blocks: JSON.parse($("Parse Mute Action").first().json.updatedBlocks) '
            '}) }}'
        )

        update_node = make_slack_http_node(
            name=update_msg_name,
            api_url=SLACK_CHAT_UPDATE,
            json_body=update_body,
            position=[u_pos[0] + 250, u_pos[1]],
        )
        nodes.append(update_node)
        print(f"  Added '{update_msg_name}'")
    else:
        print(f"  '{update_msg_name}' already exists")

    # ── 6. Wire connections ──
    silence_output_idx = len(rules) - 1

    route_conns = connections.get("Route Action", {"main": []})
    while len(route_conns["main"]) <= silence_output_idx:
        route_conns["main"].append([])
    route_conns["main"][silence_output_idx] = [
        {"node": parse_mute_name, "type": "main", "index": 0}
    ]
    connections["Route Action"] = route_conns

    connections[parse_mute_name] = {"main": [[
        {"node": upsert_name, "type": "main", "index": 0}
    ]]}
    connections[upsert_name] = {"main": [[
        {"node": update_msg_name, "type": "main", "index": 0}
    ]]}

    print("  Wired: Route Action → Parse Mute Action → Upsert Mute → Update Alert Message")

    return wf


def main():
    print("=== Dead Account Detection + Mute Buttons ===\n")

    # 1. Silence Contract Monitor
    wf1 = update_silence_monitor()
    result1 = push_workflow(WF_SILENCE_MONITOR, wf1)
    print(f"  Pushed cron: {len(result1['nodes'])} nodes")
    sync_local(fetch_workflow(WF_SILENCE_MONITOR), "Silence Contract Monitor.json")

    # 2. On-Demand Silence Check
    wf2 = update_on_demand_silence()
    result2 = push_workflow("7QaWpTuTp6oNVFjM", wf2)
    print(f"  Pushed on-demand: {len(result2['nodes'])} nodes")
    sync_local(fetch_workflow("7QaWpTuTp6oNVFjM"), "On-Demand Silence Check.json")

    # 3. Interactive Events Handler
    wf3 = update_interactive_handler()
    result3 = push_workflow(WF_INTERACTIVE_HANDLER, wf3)
    print(f"  Pushed interactive: {len(result3['nodes'])} nodes")
    sync_local(fetch_workflow(WF_INTERACTIVE_HANDLER), "Interactive Events Handler.json")

    print("\n=== Done! ===")
    print("  - Dead accounts (60+ days) alert once then auto-mute")
    print("  - Every alert has [...] overflow menu: Snooze 7d / Snooze 30d / Mark as Lost")
    print("  - Muted accounts filtered from future alerts")


if __name__ == "__main__":
    main()
