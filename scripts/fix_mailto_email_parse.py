"""
Fix: mailto email extraction doesn't handle parenthesized emails.

Agent outputs "Philip Heineman (philip.heineman@ironmountain.com)" but
extractEmail only checks angle brackets <> and bare emails. Need to also
check parentheses ().

Fixes all three mailto formatter nodes:
1. Format DM Draft Mailto (Events Handler)
2. Format Draft with Mailto (Interactive Handler)
3. Format Re-engagement with Mailto (Interactive Handler)

Usage:
    N8N_API_KEY=... python scripts/fix_mailto_email_parse.py
"""

from n8n_helpers import (
    find_node, fetch_workflow, push_workflow, sync_local,
    WF_EVENTS_HANDLER, WF_INTERACTIVE_HANDLER,
)

OLD_EXTRACT = """function extractEmail(line) {
  const angleMatch = line.match(/<([^>]+@[^>]+)>/);
  if (angleMatch) return angleMatch[1].trim();
  const plainMatch = line.match(/[\\w.+-]+@[\\w.-]+\\.\\w+/);
  if (plainMatch) return plainMatch[0].trim();
  return '';
}"""

NEW_EXTRACT = """function extractEmail(line) {
  const angleMatch = line.match(/<([^>]+@[^>]+)>/);
  if (angleMatch) return angleMatch[1].trim();
  const parenMatch = line.match(/\\(([^)]+@[^)]+)\\)/);
  if (parenMatch) return parenMatch[1].trim();
  const plainMatch = line.match(/[\\w.+-]+@[\\w.-]+\\.\\w+/);
  if (plainMatch) return plainMatch[0].trim();
  return '';
}"""


def fix_workflow(wf_id, node_names, local_filename):
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
        if OLD_EXTRACT in code:
            code = code.replace(OLD_EXTRACT, NEW_EXTRACT)
            node["parameters"]["jsCode"] = code
            print(f"  Fixed extractEmail in '{name}'")
            changes += 1
        else:
            print(f"  WARNING: extractEmail pattern not found in '{name}'")

    if changes == 0:
        print("  No changes")
        return

    print(f"\n=== Pushing ({changes} changes) ===")
    result = push_workflow(wf_id, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")
    sync_local(result, local_filename)


if __name__ == "__main__":
    fix_workflow(
        WF_EVENTS_HANDLER,
        ["Format DM Draft Mailto"],
        "Slack Events Handler.json",
    )
    fix_workflow(
        WF_INTERACTIVE_HANDLER,
        ["Format Draft with Mailto", "Format Re-engagement with Mailto"],
        "Interactive Events Handler.json",
    )
    print("\nDone!")
