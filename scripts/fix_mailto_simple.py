"""
Fix: Remove the broken mailto link with query params.

Slack mrkdwn can't render mailto: URLs with ?subject=&body= cleanly —
it dumps the raw URL-encoded string.

New approach: Add a clean, simple mailto link (recipient only, no body)
as a context line below the draft. The rep clicks it to open a new email
to the right person, then copies the body from the Slack thread.

Format: ":email:  <mailto:philip@co.com|philip@co.com> — click to start email, copy body above"

Updates all three mailto formatter nodes.

Usage:
    N8N_API_KEY=... python scripts/fix_mailto_simple.py
"""

from n8n_helpers import (
    find_node, fetch_workflow, push_workflow, sync_local,
    WF_EVENTS_HANDLER, WF_INTERACTIVE_HANDLER,
)

# Old: mrkdwn link with full mailto URL (subject + body)
OLD_BLOCK = """if (mailtoUrl) {
  blocks.push({
    type: "section",
    text: { type: "mrkdwn", text: "<" + mailtoUrl + "|:email: Open in Email>" }
  });
}"""

# New: simple mailto link (recipient only) + clean label
NEW_BLOCK = """if (toEmail) {
  blocks.push({
    type: "context",
    elements: [{ type: "mrkdwn", text: ":email:  <mailto:" + toEmail + "|" + toEmail + "> — click to compose, copy body from above" }]
  });
} else if (subject) {
  blocks.push({
    type: "context",
    elements: [{ type: "mrkdwn", text: ":email:  Copy the draft above into your email client" }]
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
            print(f"  Switched to simple mailto in '{name}'")
            changes += 1
        else:
            print(f"  WARNING: mrkdwn link block not found in '{name}'")

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
