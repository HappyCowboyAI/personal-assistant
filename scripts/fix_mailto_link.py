"""
Fix: Replace Block Kit button (Slack doesn't support mailto: URLs in buttons)
with a mrkdwn mailto link that Slack renders natively.

Changes the actions block to a section block with a clickable mrkdwn link:
<mailto:email@co.com?subject=...&body=...|:email: Open in Email>

Fixes all four mailto formatter nodes across both workflows.

Usage:
    N8N_API_KEY=... python scripts/fix_mailto_link.py
"""

from n8n_helpers import (
    find_node, fetch_workflow, push_workflow, sync_local,
    WF_EVENTS_HANDLER, WF_INTERACTIVE_HANDLER,
)

# Old: Block Kit actions button
OLD_BLOCK = """if (mailtoUrl) {
  blocks.push({
    type: "actions",
    elements: [{
      type: "button",
      text: { type: "plain_text", text: ":email: Open in Email", emoji: true },
      url: mailtoUrl,
      style: "primary"
    }]
  });
}"""

# New: mrkdwn link in a context block
NEW_BLOCK = """if (mailtoUrl) {
  blocks.push({
    type: "section",
    text: { type: "mrkdwn", text: "<" + mailtoUrl + "|:email: Open in Email>" }
  });
}"""


def fix_nodes(wf_id, node_names, local_filename):
    print(f"\nFetching workflow {wf_id}...")
    wf = fetch_workflow(wf_id)
    print(f"  {len(wf['nodes'])} nodes")
    changes = 0

    for name in node_names:
        node = find_node(wf["nodes"], name)
        if not node:
            print(f"  WARNING: '{name}' not found")
            continue

        code = node["parameters"]["jsCode"]
        if OLD_BLOCK in code:
            code = code.replace(OLD_BLOCK, NEW_BLOCK)
            node["parameters"]["jsCode"] = code
            print(f"  Switched to mrkdwn link in '{name}'")
            changes += 1
        else:
            print(f"  WARNING: button block not found in '{name}'")

    if changes == 0:
        print("  No changes")
        return

    print(f"\n=== Pushing ({changes} changes) ===")
    result = push_workflow(wf_id, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")
    sync_local(result, local_filename)


if __name__ == "__main__":
    fix_nodes(
        WF_EVENTS_HANDLER,
        ["Format DM Draft Mailto"],
        "Slack Events Handler.json",
    )
    fix_nodes(
        WF_INTERACTIVE_HANDLER,
        ["Format Draft with Mailto", "Format Re-engagement with Mailto"],
        "Interactive Events Handler.json",
    )
    print("\nDone!")
