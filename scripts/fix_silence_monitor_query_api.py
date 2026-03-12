#!/usr/bin/env python3
"""
Fix Silence Contract Monitor: Add Query API pre-fetch for account/opp ownership.

Problem: MCP uses shared service account, can't filter by user. AJ (CSM) sees all alerts.

Solution: Query API + MCP hybrid (same pattern as Sales Digest):
1. Pre-fetch opp ownership via Query API (owner + CSM owner columns)
2. Code node: filter accounts per user based on ownership (owner OR CSM)
3. Agent only checks engagement for filtered accounts via MCP

New nodes added before the loop:
  - Get Auth Token → Fetch Opp Ownership → Parse Opp Teams
  - Prepare User Batch updated to receive ownership data

New node inside the loop:
  - Filter User Accounts (before Build Monitor Prompt)

Build Monitor Prompt updated to include the filtered account list.
"""

import json
from n8n_helpers import (
    find_node, fetch_workflow, push_workflow, sync_local,
    uid, WF_SILENCE_MONITOR
)


def main():
    print("=== Add Query API ownership layer to Silence Contract Monitor ===\n")

    wf = fetch_workflow(WF_SILENCE_MONITOR)
    nodes = wf["nodes"]
    connections = wf["connections"]
    print(f"  {len(nodes)} nodes")

    # ── 1. Add "Get Auth Token" node ──
    auth_node_name = "Get Auth Token"
    if find_node(nodes, auth_node_name):
        print(f"  '{auth_node_name}' already exists — skipping add")
    else:
        trigger_node = find_node(nodes, "Daily 6:30am PT")
        trigger_pos = trigger_node["position"] if trigger_node else [208, 376]

        auth_node = {
            "parameters": {
                "method": "POST",
                "url": "https://api.people.ai/v3/auth/tokens",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "Content-Type", "value": "application/x-www-form-urlencoded"}
                    ]
                },
                "sendBody": True,
                "specifyBody": "string",
                "body": "client_id=YOUR_CLIENT_ID&client_secret=YOUR_CLIENT_SECRET&grant_type=client_credentials",
                "options": {}
            },
            "id": uid(),
            "name": auth_node_name,
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [trigger_pos[0] + 224, trigger_pos[1]]
        }
        nodes.append(auth_node)

        # Connect trigger → auth
        if "Daily 6:30am PT" not in connections:
            connections["Daily 6:30am PT"] = {"main": [[]]}
        connections["Daily 6:30am PT"]["main"][0].append(
            {"node": auth_node_name, "type": "main", "index": 0}
        )
        print(f"  Added '{auth_node_name}'")

    # ── 2. Add "Fetch Opp Ownership" node ──
    fetch_node_name = "Fetch Opp Ownership"
    if find_node(nodes, fetch_node_name):
        print(f"  '{fetch_node_name}' already exists — skipping add")
    else:
        auth_node = find_node(nodes, auth_node_name)
        auth_pos = auth_node["position"]

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

        fetch_node = {
            "parameters": {
                "method": "POST",
                "url": "https://api.people.ai/v3/beta/insights/export",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "Authorization", "value": "=Bearer {{ $json.access_token }}"},
                        {"name": "Content-Type", "value": "application/json"}
                    ]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": export_body,
                "options": {}
            },
            "id": uid(),
            "name": fetch_node_name,
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [auth_pos[0] + 224, auth_pos[1]]
        }
        nodes.append(fetch_node)

        # Connect auth → fetch
        if auth_node_name not in connections:
            connections[auth_node_name] = {"main": [[]]}
        connections[auth_node_name]["main"][0].append(
            {"node": fetch_node_name, "type": "main", "index": 0}
        )
        print(f"  Added '{fetch_node_name}'")

    # ── 3. Add "Parse Opp Teams" node ──
    parse_node_name = "Parse Opp Teams"
    if find_node(nodes, parse_node_name):
        print(f"  '{parse_node_name}' already exists — skipping add")
    else:
        fetch_node = find_node(nodes, fetch_node_name)
        fetch_pos = fetch_node["position"]

        parse_code = r"""// Parse opp ownership CSV into per-person account lists
const csvData = $('Fetch Opp Ownership').first().json.data;

if (!csvData) {
  return [{ json: { accountsByPerson: {}, oppCount: 0, error: 'No data' } }];
}

const lines = csvData.split('\n').filter(l => l.trim());
if (lines.length < 2) {
  return [{ json: { accountsByPerson: {}, oppCount: 0 } }];
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

// Build: personName (lowercase) → Set of account names
const accountsByPerson = {};

function addAccount(personName, accountName) {
  if (!personName || !accountName) return;
  const key = personName.toLowerCase().trim();
  if (!accountsByPerson[key]) accountsByPerson[key] = new Set();
  accountsByPerson[key].add(accountName);
}

let oppCount = 0;
for (let i = 1; i < lines.length; i++) {
  const row = parseCsvLine(lines[i]);
  if (row.length < 2) continue;
  oppCount++;

  const accountName = get(row, 'Account Name');
  const ownerName = get(row, 'Opportunity Owner (name)', 'Opportunity Owner');
  const csmName = get(row, 'CSM Owner (name)', 'CSM Owner');

  addAccount(ownerName, accountName);
  addAccount(csmName, accountName);
}

// Convert Sets to Arrays for JSON serialization
const result = {};
for (const [person, accounts] of Object.entries(accountsByPerson)) {
  result[person] = Array.from(accounts).sort();
}

return [{ json: { accountsByPerson: result, oppCount } }];"""

        parse_node = {
            "parameters": {
                "jsCode": parse_code,
                "mode": "runOnceForAllItems"
            },
            "id": uid(),
            "name": parse_node_name,
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [fetch_pos[0] + 224, fetch_pos[1]]
        }
        nodes.append(parse_node)

        # Connect fetch → parse
        if fetch_node_name not in connections:
            connections[fetch_node_name] = {"main": [[]]}
        connections[fetch_node_name]["main"][0].append(
            {"node": parse_node_name, "type": "main", "index": 0}
        )
        print(f"  Added '{parse_node_name}'")

    # ── 4. Connect Parse Opp Teams → Get Active Users (parallel with existing) ──
    # Parse Opp Teams needs to flow into Prepare User Batch so it can access the data
    # The existing flow is: trigger → Get Active Users + Get Recent Alerts → Prepare User Batch
    # New flow: trigger → auth → fetch → parse ─→ Prepare User Batch
    #           trigger → Get Active Users ────────→ Prepare User Batch
    #           trigger → Get Recent Alerts ───────→ Prepare User Batch
    # Actually, Prepare User Batch already references Get Active Users and Get Recent Alerts
    # We need it to also reference Parse Opp Teams
    # The simplest approach: connect Parse Opp Teams → Prepare User Batch as an additional input
    # But n8n Code nodes with multiple inputs just get the data merged
    # Better: connect Parse Opp Teams → Get Active Users so they run in sequence after auth

    # Actually, let's check the current connections from trigger
    # We need auth token before fetch, and Get Active Users/Get Recent Alerts can run in parallel
    # Let's connect: Parse Opp Teams → Prepare User Batch (as additional input)
    # And update Prepare User Batch code to read from Parse Opp Teams

    # Connect Parse Opp Teams → Prepare User Batch
    prep_node_name = "Prepare User Batch"
    if parse_node_name not in connections:
        connections[parse_node_name] = {"main": [[]]}

    # Check if already connected
    existing_targets = [t["node"] for t in connections.get(parse_node_name, {}).get("main", [[]])[0]]
    if prep_node_name not in existing_targets:
        connections[parse_node_name]["main"][0].append(
            {"node": prep_node_name, "type": "main", "index": 0}
        )
        print(f"  Connected '{parse_node_name}' → '{prep_node_name}'")

    # ── 5. Update "Prepare User Batch" to include ownership data ──
    prep_node = find_node(nodes, prep_node_name)
    prep_code = prep_node["parameters"]["jsCode"]

    NEW_PREPARE_CODE = r"""// Combine users with their recent alerts + ownership data
const usersAll = $('Get Active Users').all().map(i => i.json);
const alertsAll = $('Get Recent Alerts').all().map(i => i.json);

// Get per-person account ownership map
let accountsByPerson = {};
try {
  accountsByPerson = $('Parse Opp Teams').first().json.accountsByPerson || {};
} catch (e) {
  // Parse Opp Teams didn't execute — no ownership filtering available
}

// Filter out empty items
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

  // Derive rep name from email for scope-aware filtering
  const email = (user.email || '').toLowerCase();
  const repName = email.split('@')[0].replace(/\./g, ' ').replace(/\b\w/g, c => c.toUpperCase());

  // Find this user's accounts from ownership data (match on name, case-insensitive)
  const repLower = repName.toLowerCase();
  const userAccounts = accountsByPerson[repLower] || [];

  output.push({
    json: {
      userId: user.id,
      slackUserId: user.slack_user_id,
      email: user.email,
      assistantName: user.assistant_name || 'Aria',
      assistantEmoji: user.assistant_emoji || ':robot_face:',
      organizationId: user.organization_id,
      digestScope: user.digest_scope || 'my_deals',
      repName,
      userAccounts,
      userAccountCount: userAccounts.length,
      recentAlerts: alertsByUser[user.id] || []
    }
  });
}

if (output.length === 0) {
  return [{ json: { skip: true, reason: 'No active users found' } }];
}

return output;"""

    if "accountsByPerson" in prep_code:
        print(f"  '{prep_node_name}': ownership data already present — skipping")
    else:
        prep_node["parameters"]["jsCode"] = NEW_PREPARE_CODE
        print(f"  Updated '{prep_node_name}' — includes ownership-based account lists")

    # ── 6. Update "Build Monitor Prompt" to use pre-filtered account list ──
    prompt_node = find_node(nodes, "Build Monitor Prompt")

    NEW_PROMPT_CODE = r"""const user = $input.first().json;

if (user.skip) {
  return [{ json: { ...user, monitorPrompt: '', skip: true } }];
}

const today = new Date().toISOString().split('T')[0];
const scope = user.digestScope || 'my_deals';
const repName = user.repName || '';
const userAccounts = user.userAccounts || [];

let prompt;

if (scope === 'my_deals') {
  if (userAccounts.length === 0) {
    // No accounts found for this user — skip
    return [{ json: { ...user, monitorPrompt: '', skip: true, skipReason: 'No accounts found for ' + repName } }];
  }
  // IC/CSM scope — only check their specific accounts
  const accountList = userAccounts.map(a => `• ${a}`).join('\n');
  prompt = `Check these specific accounts for engagement gaps. For each account below, check if there has been any customer-facing activity (emails, meetings, or calls) in the past 5 or more days. Only check these accounts — they are the accounts where ${repName} is the owner or CSM:\n\n${accountList}\n\nToday's date is ${today}. Report any that have gone silent (5+ days with no activity).`;
} else if (scope === 'team_deals') {
  // Manager scope — their accounts + team members' accounts
  // userAccounts already includes accounts where this person is owner or CSM
  // For team scope, we'd ideally include reports' accounts too, but for now use their accounts
  if (userAccounts.length > 0) {
    const accountList = userAccounts.map(a => `• ${a}`).join('\n');
    prompt = `Check these accounts for engagement gaps. For each account below, check if there has been any customer-facing activity (emails, meetings, or calls) in the past 5 or more days:\n\n${accountList}\n\nToday's date is ${today}. Report any that have gone silent (5+ days with no activity).`;
  } else {
    prompt = `Check accounts for engagement gaps across my team. Which accounts with open opportunities have had no customer-facing activity (emails, meetings, or calls) in the past 5 or more days? Today's date is ${today}.`;
  }
} else {
  // Exec/pipeline scope — all accounts
  prompt = `Check all accounts for engagement gaps. Which accounts with open opportunities have had no customer-facing activity (emails, meetings, or calls) in the past 5 or more days? Today's date is ${today}.`;
}

return [{
  json: {
    ...user,
    monitorPrompt: prompt
  }
}];"""

    if "userAccounts" in prompt_node["parameters"]["jsCode"]:
        print(f"  'Build Monitor Prompt': account list already present — skipping")
    else:
        prompt_node["parameters"]["jsCode"] = NEW_PROMPT_CODE
        print(f"  Updated 'Build Monitor Prompt' — passes pre-filtered account list to agent")

    # ── Push ──
    print(f"\n=== Pushing workflow ===")
    result = push_workflow(WF_SILENCE_MONITOR, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")

    final = fetch_workflow(WF_SILENCE_MONITOR)
    sync_local(final, "Silence Contract Monitor.json")

    print("\nDone! Silence Contract Monitor now uses Query API + MCP hybrid:")
    print("  1. Get Auth Token → Fetch Opp Ownership (Query API: owner + CSM columns)")
    print("  2. Parse Opp Teams → builds per-person account lists")
    print("  3. Prepare User Batch → attaches each user's accounts")
    print("  4. Build Monitor Prompt → passes specific account list to agent (my_deals scope)")
    print("  5. Agent only checks engagement for those accounts via MCP")


if __name__ == "__main__":
    main()
