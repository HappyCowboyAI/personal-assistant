"""
Fix: Extract multiple CC emails from the CC line.

The CC line can have multiple participants like:
  *CC:* Alice (alice@co.com), Bob (bob@co.com), Charlie <charlie@co.com>

Current code only extracts the first email. This adds extractAllEmails()
that returns a comma-separated list for the Gmail compose CC param.

Updates all three formatters:
1. Format DM Draft Mailto (Events Handler)
2. Format Draft with Mailto (Interactive Handler)
3. Format Re-engagement with Mailto (Interactive Handler)

Usage:
    N8N_API_KEY=... python scripts/fix_draft_cc_parse.py
"""

from n8n_helpers import (
    find_node, fetch_workflow, push_workflow, sync_local,
    WF_EVENTS_HANDLER, WF_INTERACTIVE_HANDLER,
)

# Old: single email extraction for CC
OLD_CC_EXTRACT = "const ccEmail = ccMatch ? extractEmail(ccMatch[1]) : '';"

# New: extract all emails from CC line
NEW_CC_EXTRACT = """// Extract all emails from a line (for CC with multiple recipients)
function extractAllEmails(line) {
  const emails = [];
  const regex = /[\\w.+-]+@[\\w.-]+\\.\\w+/g;
  let m;
  while ((m = regex.exec(line)) !== null) {
    emails.push(m[0].trim());
  }
  return emails.join(',');
}
const ccEmail = ccMatch ? extractAllEmails(ccMatch[1]) : '';"""


def fix_formatter(wf, node_name):
    node = find_node(wf["nodes"], node_name)
    if not node:
        print(f"  WARNING: '{node_name}' not found")
        return 0

    code = node["parameters"]["jsCode"]

    if OLD_CC_EXTRACT in code:
        code = code.replace(OLD_CC_EXTRACT, NEW_CC_EXTRACT)
        node["parameters"]["jsCode"] = code
        print(f"  Updated CC extraction in '{node_name}'")
        return 1
    elif "extractAllEmails" in code:
        print(f"  '{node_name}' already has extractAllEmails")
        return 0
    else:
        print(f"  WARNING: Could not find CC extract pattern in '{node_name}'")
        return 0


def main():
    # ── Events Handler ──
    print(f"Fetching Events Handler {WF_EVENTS_HANDLER}...")
    wf = fetch_workflow(WF_EVENTS_HANDLER)
    print(f"  {len(wf['nodes'])} nodes")

    changes = fix_formatter(wf, "Format DM Draft Mailto")
    if changes:
        print(f"\n=== Pushing Events Handler ({changes} changes) ===")
        result = push_workflow(WF_EVENTS_HANDLER, wf)
        print(f"  HTTP 200, {len(result['nodes'])} nodes")
        sync_local(result, "Slack Events Handler.json")

    # ── Interactive Handler ──
    print(f"\nFetching Interactive Handler {WF_INTERACTIVE_HANDLER}...")
    wf2 = fetch_workflow(WF_INTERACTIVE_HANDLER)
    print(f"  {len(wf2['nodes'])} nodes")

    changes2 = 0
    changes2 += fix_formatter(wf2, "Format Draft with Mailto")
    changes2 += fix_formatter(wf2, "Format Re-engagement with Mailto")

    if changes2:
        print(f"\n=== Pushing Interactive Handler ({changes2} changes) ===")
        result2 = push_workflow(WF_INTERACTIVE_HANDLER, wf2)
        print(f"  HTTP 200, {len(result2['nodes'])} nodes")
        sync_local(result2, "Interactive Events Handler.json")

    print("\nDone!")


if __name__ == "__main__":
    main()
