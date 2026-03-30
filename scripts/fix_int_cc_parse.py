"""
Fix: Extract multiple CC emails in Interactive Handler formatters.

These use a different pattern: ccRaw → extractEmail(ccRaw) → single email.
Replace with extractAllEmails for multiple CC recipients.

Usage:
    N8N_API_KEY=... python scripts/fix_int_cc_parse.py
"""

from n8n_helpers import (
    find_node, fetch_workflow, push_workflow, sync_local,
    WF_INTERACTIVE_HANDLER,
)

OLD_CC = "const ccEmail = ccRaw ? extractEmail(ccRaw) : '';"

NEW_CC = """// Extract all emails from a line (for CC with multiple recipients)
function extractAllEmails(line) {
  const emails = [];
  const regex = /[\\w.+-]+@[\\w.-]+\\.\\w+/g;
  let m;
  while ((m = regex.exec(line)) !== null) {
    emails.push(m[0].trim());
  }
  return emails.join(',');
}
const ccEmail = ccRaw ? extractAllEmails(ccRaw) : '';"""


def fix_formatter(wf, node_name):
    node = find_node(wf["nodes"], node_name)
    if not node:
        print(f"  WARNING: '{node_name}' not found")
        return 0

    code = node["parameters"]["jsCode"]

    if OLD_CC in code:
        code = code.replace(OLD_CC, NEW_CC)
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
    print(f"Fetching Interactive Handler {WF_INTERACTIVE_HANDLER}...")
    wf = fetch_workflow(WF_INTERACTIVE_HANDLER)
    print(f"  {len(wf['nodes'])} nodes")

    changes = 0
    changes += fix_formatter(wf, "Format Draft with Mailto")
    changes += fix_formatter(wf, "Format Re-engagement with Mailto")

    if changes:
        print(f"\n=== Pushing Interactive Handler ({changes} changes) ===")
        result = push_workflow(WF_INTERACTIVE_HANDLER, wf)
        print(f"  HTTP 200, {len(result['nodes'])} nodes")
        sync_local(result, "Interactive Events Handler.json")

    print("\nDone!")


if __name__ == "__main__":
    main()
