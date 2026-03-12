#!/usr/bin/env python3
"""
Fix On-Demand Silence Check: restore per-account section blocks with overflow accessories.

The previous push used detached actions blocks which made menus impossible to match
to their accounts. This restores the section+accessory pattern.
"""

from n8n_helpers import modify_workflow, find_node, sync_local, fetch_workflow

WF_ON_DEMAND = "7QaWpTuTp6oNVFjM"

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


def fix_alert_blocks(nodes, connections):
    node = find_node(nodes, "Build Alert Message")
    if not node:
        print("  ERROR: 'Build Alert Message' not found!")
        return 0

    old_code = node["parameters"]["jsCode"]
    if "accessory" in old_code:
        print("  Already has section+accessory pattern")
        return 0

    node["parameters"]["jsCode"] = BUILD_ALERT_OD_CODE
    print("  Updated Build Alert Message → section blocks with overflow accessories")
    return 1


def main():
    print("=== Fix On-Demand Build Alert Message ===\n")
    modify_workflow(WF_ON_DEMAND, "On-Demand Silence Check.json", fix_alert_blocks)
    print("\nDone!")


if __name__ == "__main__":
    main()
