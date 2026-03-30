"""
Fix: Correct the Gmail compose URL structure in Format DM Draft Mailto.

Previous fix renamed variables but kept mailto-style URL params.
This replaces the entire URL builder with proper Gmail compose format.

Usage:
    N8N_API_KEY=... python scripts/fix_dm_gmail_compose2.py
"""

from n8n_helpers import (
    find_node, fetch_workflow, push_workflow, sync_local,
    WF_EVENTS_HANDLER,
)

# What the code looks like now (broken hybrid)
OLD_BUILDER = """// Build mailto URL
let composeUrl = '';
if (toEmail || subject) {
  const params = [];
  if (subject) params.push('subject=' + encodeURIComponent(subject));
  if (ccEmail) params.push('cc=' + encodeURIComponent(ccEmail));
  if (plainBody) params.push('body=' + encodeURIComponent(plainBody));
  composeUrl = 'https://mail.google.com/mail/?view=cm&fs=1&to=' + (toEmail ? encodeURIComponent(toEmail) : '');
  if (params.length) composeUrl += '?' + params.join('&');
}

// Truncate if too long
if (composeUrl.length > 2000) {
  const truncBody = plainBody.substring(0, 800) + '\\n\\n[... see full draft in Slack]';
  const params2 = [];
  if (subject) params2.push('subject=' + encodeURIComponent(subject));
  if (ccEmail) params2.push('cc=' + encodeURIComponent(ccEmail));
  params2.push('body=' + encodeURIComponent(truncBody));
  composeUrl = 'https://mail.google.com/mail/?view=cm&fs=1&to=' + (toEmail ? encodeURIComponent(toEmail) : '') + '?' + params2.join('&');
}"""

# Correct Gmail compose format
NEW_BUILDER = """// Build Gmail compose deep link
let composeUrl = '';
if (toEmail || subject) {
  const params = ['view=cm', 'fs=1'];
  if (toEmail) params.push('to=' + encodeURIComponent(toEmail));
  if (ccEmail) params.push('cc=' + encodeURIComponent(ccEmail));
  if (subject) params.push('su=' + encodeURIComponent(subject));
  if (plainBody) params.push('body=' + encodeURIComponent(plainBody));
  composeUrl = 'https://mail.google.com/mail/?' + params.join('&');
}

// Truncate if too long (browser URL limit ~8000 chars for Chrome)
const MAX_URL = 7500;
if (composeUrl.length > MAX_URL) {
  const truncBody = plainBody.substring(0, 2000) + '\\n\\n[... see full draft in Slack thread]';
  const params2 = ['view=cm', 'fs=1'];
  if (toEmail) params2.push('to=' + encodeURIComponent(toEmail));
  if (ccEmail) params2.push('cc=' + encodeURIComponent(ccEmail));
  if (subject) params2.push('su=' + encodeURIComponent(subject));
  params2.push('body=' + encodeURIComponent(truncBody));
  composeUrl = 'https://mail.google.com/mail/?' + params2.join('&');
}"""


def main():
    print(f"Fetching Events Handler {WF_EVENTS_HANDLER}...")
    wf = fetch_workflow(WF_EVENTS_HANDLER)
    nodes = wf["nodes"]
    print(f"  {len(nodes)} nodes")

    node = find_node(nodes, "Format DM Draft Mailto")
    if not node:
        print("  ERROR: 'Format DM Draft Mailto' not found")
        return

    code = node["parameters"]["jsCode"]

    if OLD_BUILDER in code:
        code = code.replace(OLD_BUILDER, NEW_BUILDER)
        node["parameters"]["jsCode"] = code
        print("  Replaced URL builder with correct Gmail compose format")
    else:
        print("  ERROR: Could not find expected URL builder block")
        # Debug: show what's there
        idx = code.find("let composeUrl")
        if idx >= 0:
            print("  Found 'let composeUrl' at position", idx)
            print("  Context:", repr(code[idx-50:idx+200]))
        return

    print(f"\n=== Pushing Events Handler ===")
    result = push_workflow(WF_EVENTS_HANDLER, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")
    sync_local(result, "Slack Events Handler.json")
    print("\nDone!")


if __name__ == "__main__":
    main()
