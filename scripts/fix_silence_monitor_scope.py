#!/usr/bin/env python3
"""
Fix Silence Contract Monitor: Add scope-aware filtering.

Problem: All users get the same alerts regardless of digest_scope.
AJ has my_deals scope but sees alerts for accounts she doesn't own.

Fix:
1. Prepare User Batch: pass digest_scope through
2. Build Monitor Prompt: scope-aware prompt (my_deals = only my accounts)
"""

from n8n_helpers import find_node, modify_workflow, WF_SILENCE_MONITOR


PREPARE_USER_BATCH_CODE = r"""// Combine users with their recent alerts
// n8n splits array responses into individual items, so use .all()
const usersAll = $('Get Active Users').all().map(i => i.json);
const alertsAll = $('Get Recent Alerts').all().map(i => i.json);

// Filter out empty items (from alwaysOutputData on empty response)
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
      recentAlerts: alertsByUser[user.id] || []
    }
  });
}

if (output.length === 0) {
  return [{ json: { skip: true, reason: 'No active users found' } }];
}

return output;"""


BUILD_MONITOR_PROMPT_CODE = r"""const user = $input.first().json;

if (user.skip) {
  return [{ json: { ...user, monitorPrompt: '', skip: true } }];
}

const today = new Date().toISOString().split('T')[0];
const scope = user.digestScope || 'my_deals';
const repName = user.repName || '';

let prompt;

if (scope === 'my_deals') {
  // IC/CSM scope — accounts where this person is involved (owner, account team, or opp team)
  prompt = `Check accounts associated with ${repName} for engagement gaps. Look up opportunities and accounts where ${repName} is involved — as the opportunity owner, a member of the account team, or a member of the opportunity team. Which of those accounts have had no customer-facing activity (emails, meetings, or calls) in the past 5 or more days? Only include accounts where ${repName} is on the account team, opportunity team, or is the owner. Today's date is ${today}.`;
} else if (scope === 'team_deals') {
  // Manager scope — their team's accounts
  prompt = `Check accounts for engagement gaps across my team. Which accounts with open opportunities have had no customer-facing activity (emails, meetings, or calls) in the past 5 or more days? Include accounts associated with ${repName} and their direct reports (as owners or team members). Today's date is ${today}.`;
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


def modify_silence_monitor(nodes, connections):
    changes = 0

    # Fix 1: Prepare User Batch — add digest_scope and repName
    batch_node = find_node(nodes, "Prepare User Batch")
    if not batch_node:
        print("ERROR: 'Prepare User Batch' not found!")
        return 0
    code = batch_node["parameters"]["jsCode"]
    if "digestScope" in code:
        print("  Prepare User Batch: digestScope already present — skipping")
    else:
        batch_node["parameters"]["jsCode"] = PREPARE_USER_BATCH_CODE
        print("  Updated 'Prepare User Batch' — passes digestScope + repName")
        changes += 1

    # Fix 2: Build Monitor Prompt — scope-aware prompts
    prompt_node = find_node(nodes, "Build Monitor Prompt")
    if not prompt_node:
        print("ERROR: 'Build Monitor Prompt' not found!")
        return 0
    code = prompt_node["parameters"]["jsCode"]
    if "digestScope" in code or "scope" in code:
        print("  Build Monitor Prompt: scope-aware already — skipping")
    else:
        prompt_node["parameters"]["jsCode"] = BUILD_MONITOR_PROMPT_CODE
        print("  Updated 'Build Monitor Prompt' — scope-aware prompts")
        print("    - my_deals: only accounts owned by the rep")
        print("    - team_deals: rep + direct reports")
        print("    - top_pipeline: all accounts")
        changes += 1

    return changes


def main():
    print("=== Fix Silence Contract Monitor: Scope Filtering ===\n")

    modify_workflow(
        WF_SILENCE_MONITOR,
        "Silence Contract Monitor.json",
        modify_silence_monitor,
    )


if __name__ == "__main__":
    main()
