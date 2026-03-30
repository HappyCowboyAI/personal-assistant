"""
Fix: Complete the Gmail compose migration for Format DM Draft Mailto.

The previous fix_gmail_compose.py only updated the render block (composeUrl button)
but left the URL builder still creating mailtoUrl. This fixes the mismatch.

Usage:
    N8N_API_KEY=... python scripts/fix_dm_gmail_compose.py
"""

from n8n_helpers import (
    find_node, fetch_workflow, push_workflow, sync_local,
    WF_EVENTS_HANDLER,
)


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

    # Check current state
    has_mailto_builder = "let mailtoUrl = '';" in code
    has_compose_render = "composeUrl" in code and "Open in Gmail" in code

    if has_mailto_builder and has_compose_render:
        print("  Confirmed: URL builder has mailtoUrl, render has composeUrl (mismatch)")
    elif not has_mailto_builder:
        print("  URL builder already uses composeUrl — nothing to fix")
        return
    else:
        print("  Unexpected state — checking anyway")

    # Replace the entire mailto URL builder with Gmail compose builder
    old_builder = """// Build mailto URL
let mailtoUrl = '';
if (toEmail || subject) {
  const params = [];
  if (subject) params.push('subject=' + encodeURIComponent(subject));
  if (ccEmail) params.push('cc=' + encodeURIComponent(ccEmail));
  if (plainBody) params.push('body=' + encodeURIComponent(plainBody));
  mailtoUrl = 'mailto:' + (toEmail ? encodeURIComponent(toEmail) : '');
  if (params.length) mailtoUrl += '?' + params.join('&');
}

// Truncate mailto URL if too long (browser limit ~2000 chars)
const MAX_URL = 2000;
if (mailtoUrl.length > MAX_URL) {
  // Rebuild with truncated body
  const truncBody = plainBody.substring(0, 800) + '\\n\\n[... see draft in Slack thread for full text]';
  const params2 = [];
  if (subject) params2.push('subject=' + encodeURIComponent(subject));
  if (ccEmail) params2.push('cc=' + encodeURIComponent(ccEmail));
  params2.push('body=' + encodeURIComponent(truncBody));
  mailtoUrl = 'mailto:' + (toEmail ? encodeURIComponent(toEmail) : '') + '?' + params2.join('&');
}"""

    new_builder = """// Build Gmail compose deep link
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

    if old_builder in code:
        code = code.replace(old_builder, new_builder)
        print("  Replaced mailto URL builder with Gmail compose builder")
    else:
        # Fallback: just do a blanket variable rename
        print("  WARNING: Exact mailto builder block not found, doing variable rename")
        code = code.replace("let mailtoUrl = '';", "let composeUrl = '';")
        code = code.replace("mailtoUrl = 'mailto:", "composeUrl = 'https://mail.google.com/mail/?view=cm&fs=1&to=")
        code = code.replace("mailtoUrl", "composeUrl")

    # Also replace any remaining mailtoUrl references
    if "mailtoUrl" in code:
        code = code.replace("mailtoUrl", "composeUrl")
        print("  Renamed remaining mailtoUrl → composeUrl references")

    node["parameters"]["jsCode"] = code

    print(f"\n=== Pushing Events Handler ===")
    result = push_workflow(WF_EVENTS_HANDLER, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")
    sync_local(result, "Slack Events Handler.json")
    print("\nDone!")


if __name__ == "__main__":
    main()
