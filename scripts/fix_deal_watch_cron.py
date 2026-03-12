#!/usr/bin/env python3
"""
Fix Deal Watch Cron: "Match Alerts to Users" fails when "Detect Transitions" hasn't executed.

Root cause: When "Get Yesterday Snapshots" returns no data (first run, weekend gap),
"Detect Transitions" never executes. But "Match Alerts to Users" still fires from
the "Parse Hierarchy" branch and crashes trying to reference $('Detect Transitions').

Fixes:
1. Set alwaysOutputData: true on "Get Yesterday Snapshots" so Detect Transitions always runs
2. Add try-catch guard in "Match Alerts to Users" for robustness
"""

import json
import os
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = os.environ.get("N8N_API_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA")
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

WF_ID = "kZr1QKPiE7zxcn2n"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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


DETECT_TRANSITIONS_CODE = r"""// Compare today's classifications against yesterday's snapshots
const todayData = $('Parse and Classify').first().json;

let yesterdaySnapshots = [];
try {
  yesterdaySnapshots = $('Get Yesterday Snapshots').all().map(item => item.json);
} catch (e) {
  // No yesterday data (first run, table missing, etc.) — treat all as new
  yesterdaySnapshots = [];
}

const todayOpps = todayData.classifiedOpps || [];

// Build lookup by CRM ID from yesterday's snapshots
const yesterdayMap = {};
for (const snap of yesterdaySnapshots) {
  if (snap.opportunity_crm_id) {
    yesterdayMap[snap.opportunity_crm_id] = snap;
  }
}

const transitions = [];
const snapshotsToSave = [];

// Severity ranking for transition direction
const severityRank = { 'stalled': 0, 'risk': 1, 'healthy': 2, 'accelerating': 3 };
const classLabels = {
  'stalled': '\ud83d\udd34 Stalled',
  'risk': '\u26a0\ufe0f At Risk',
  'healthy': '\u2705 Healthy',
  'accelerating': '\ud83d\ude80 Accelerating'
};

for (const opp of todayOpps) {
  const crmId = opp.crmId;
  if (!crmId) continue;

  // Build snapshot for saving
  snapshotsToSave.push({
    opportunity_crm_id: crmId,
    opportunity_name: opp.name || '',
    account_name: opp.account || '',
    owner_name: opp.owners || '',
    classification: opp.classification,
    engagement_level: opp.metrics?.engagement || 0,
    days_in_stage: opp.metrics?.daysInStage || 0,
    metrics: JSON.stringify(opp.metrics || {})
  });

  const yesterday = yesterdayMap[crmId];

  if (!yesterday) {
    // New deal — only flag if it's stalled or risk
    if (opp.classification === 'stalled' || opp.classification === 'risk') {
      transitions.push({
        crmId,
        name: opp.name,
        account: opp.account,
        owner: opp.owners,
        previousClass: null,
        newClass: opp.classification,
        previousLabel: 'New',
        newLabel: classLabels[opp.classification],
        direction: 'worsening',
        flags: opp.flags || [],
        engagement: opp.metrics?.engagement || 0
      });
    }
    continue;
  }

  // Compare classifications
  const prevClass = yesterday.classification;
  const newClass = opp.classification;

  if (prevClass === newClass) continue; // No change

  const prevRank = severityRank[prevClass] ?? 2;
  const newRank = severityRank[newClass] ?? 2;
  const direction = newRank < prevRank ? 'worsening' : 'improving';

  transitions.push({
    crmId,
    name: opp.name,
    account: opp.account,
    owner: opp.owners,
    previousClass: prevClass,
    newClass: newClass,
    previousLabel: classLabels[prevClass] || prevClass,
    newLabel: classLabels[newClass] || newClass,
    direction,
    flags: opp.flags || [],
    engagement: opp.metrics?.engagement || 0
  });
}

return [{ json: {
  transitions,
  transitionCount: transitions.length,
  worseningCount: transitions.filter(t => t.direction === 'worsening').length,
  improvingCount: transitions.filter(t => t.direction === 'improving').length,
  snapshotsToSave,
  snapshotCount: snapshotsToSave.length,
  hasTransitions: transitions.length > 0
}}];"""

MATCH_ALERTS_CODE = r"""// Match transitions to users based on their scope
let transData;
try {
  transData = $('Detect Transitions').first().json;
} catch (e) {
  // Detect Transitions didn't execute — no transitions to alert on
  return [{ json: { noAlerts: true } }];
}

const users = $('Get Alert Users').all().map(item => item.json);
const hierarchyData = $('Parse Hierarchy').first().json;

const transitions = transData.transitions || [];
if (transitions.length === 0 || users.length === 0) {
  return [{ json: { noAlerts: true } }];
}

const managerToReports = hierarchyData.managerToReports || {};
const results = [];

for (const user of users) {
  const userEmail = (user.email || '').toLowerCase();
  const repName = userEmail.split('@')[0].replace(/\./g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  const repLower = repName.toLowerCase();
  const digestScope = user.digest_scope || 'my_deals';

  let userTransitions = [];

  if (digestScope === 'my_deals') {
    userTransitions = transitions.filter(t => {
      const owner = (t.owner || '').toLowerCase();
      return owner.includes(repLower);
    });
  } else if (digestScope === 'team_deals') {
    let reportNames = [repLower];
    for (const [mgrKey, reports] of Object.entries(managerToReports)) {
      if (mgrKey.includes(repLower) || repLower.includes(mgrKey)) {
        for (const report of reports) {
          const rName = (report.name || '').toLowerCase();
          if (rName && !reportNames.includes(rName)) reportNames.push(rName);
        }
      }
    }
    if (managerToReports[userEmail]) {
      for (const report of managerToReports[userEmail]) {
        const rName = (report.name || '').toLowerCase();
        if (rName && !reportNames.includes(rName)) reportNames.push(rName);
      }
    }
    userTransitions = transitions.filter(t => {
      const owner = (t.owner || '').toLowerCase();
      return reportNames.some(name => owner.includes(name));
    });
  } else {
    // pipeline scope — see all transitions
    userTransitions = transitions;
  }

  if (userTransitions.length === 0) continue;

  results.push({
    userId: user.id,
    slackUserId: user.slack_user_id,
    email: user.email,
    assistantName: user.assistant_name || 'Aria',
    assistantEmoji: user.assistant_emoji || ':robot_face:',
    repName,
    transitions: userTransitions,
    worseningCount: userTransitions.filter(t => t.direction === 'worsening').length,
    improvingCount: userTransitions.filter(t => t.direction === 'improving').length
  });
}

if (results.length === 0) {
  return [{ json: { noAlerts: true } }];
}

return results.map(r => ({ json: r }));"""


def main():
    print("=== Fix Deal Watch Cron ===\n")
    print("Fetching workflow...")
    wf = fetch_workflow(WF_ID)
    nodes = wf["nodes"]
    print(f"  {len(nodes)} nodes")

    changes = 0

    # Fix 1: alwaysOutputData on Get Yesterday Snapshots
    snap_node = find_node(nodes, "Get Yesterday Snapshots")
    if not snap_node:
        print("ERROR: 'Get Yesterday Snapshots' not found!")
        return
    if snap_node.get("alwaysOutputData"):
        print("  Get Yesterday Snapshots: alwaysOutputData already set — skipping")
    else:
        snap_node["alwaysOutputData"] = True
        print("  Set alwaysOutputData: true on 'Get Yesterday Snapshots'")
        changes += 1

    # Fix 2: Add try-catch guard in Detect Transitions
    detect_node = find_node(nodes, "Detect Transitions")
    if not detect_node:
        print("ERROR: 'Detect Transitions' not found!")
        return
    detect_code = detect_node["parameters"]["jsCode"]
    if "try {" in detect_code:
        print("  Detect Transitions: try-catch already present — skipping")
    else:
        detect_node["parameters"]["jsCode"] = DETECT_TRANSITIONS_CODE
        print("  Added try-catch guard to 'Detect Transitions'")
        changes += 1

    # Fix 3: Add try-catch guard in Match Alerts to Users
    match_node = find_node(nodes, "Match Alerts to Users")
    if not match_node:
        print("ERROR: 'Match Alerts to Users' not found!")
        return
    current_code = match_node["parameters"]["jsCode"]
    if "try {" in current_code:
        print("  Match Alerts to Users: try-catch already present — skipping")
    else:
        match_node["parameters"]["jsCode"] = MATCH_ALERTS_CODE
        print("  Added try-catch guard to 'Match Alerts to Users'")
        changes += 1

    if changes == 0:
        print("\n  No changes needed")
        return

    print(f"\n=== Pushing workflow ({changes} changes) ===")
    result = push_workflow(WF_ID, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")

    print("\n=== Re-fetching and syncing local file ===")
    final = fetch_workflow(WF_ID)
    sync_local(final, "Deal Watch Cron.json")

    print("\nDone! Fixes applied:")
    print("  1. Get Yesterday Snapshots: alwaysOutputData=true (ensures Detect Transitions always runs)")
    print("  2. Match Alerts to Users: try-catch guard (graceful fallback if Detect Transitions skipped)")


if __name__ == "__main__":
    main()
