#!/usr/bin/env python3
"""Fix Silence Monitor: update Build Monitor Prompt to check account/opp team, not just owner."""

from n8n_helpers import find_node, fetch_workflow, push_workflow, sync_local, WF_SILENCE_MONITOR

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


def main():
    print("=== Update Build Monitor Prompt (team-aware) ===\n")
    wf = fetch_workflow(WF_SILENCE_MONITOR)
    nodes = wf["nodes"]

    node = find_node(nodes, "Build Monitor Prompt")
    if not node:
        print("ERROR: node not found")
        return

    node["parameters"]["jsCode"] = BUILD_MONITOR_PROMPT_CODE
    print("  Updated 'Build Monitor Prompt' — checks account team + opp team, not just owner")

    result = push_workflow(WF_SILENCE_MONITOR, wf)
    print(f"  Pushed, {len(result['nodes'])} nodes")

    final = fetch_workflow(WF_SILENCE_MONITOR)
    sync_local(final, "Silence Contract Monitor.json")


if __name__ == "__main__":
    main()
