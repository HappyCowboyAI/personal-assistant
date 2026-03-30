"""
Fix: Switch from mailto: links to Gmail compose deep links.

Gmail compose URL format:
https://mail.google.com/mail/?view=cm&fs=1&to=email&subject=...&body=...

This is a regular https:// URL so Slack Block Kit buttons work properly.

Updates all three mailto formatter nodes.

Usage:
    N8N_API_KEY=... python scripts/fix_gmail_compose.py
"""

from n8n_helpers import (
    find_node, fetch_workflow, push_workflow, sync_local,
    WF_EVENTS_HANDLER, WF_INTERACTIVE_HANDLER,
)

# The old mailto URL builder + context block (in DM formatter)
OLD_DM_URL_BLOCK = """// Build mailto URL
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

NEW_DM_URL_BLOCK = """// Build Gmail compose deep link
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

# Old context block (DM path)
OLD_DM_RENDER = """if (toEmail) {
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

NEW_DM_RENDER = """if (composeUrl) {
  blocks.push({
    type: "actions",
    elements: [{
      type: "button",
      text: { type: "plain_text", text: ":email: Open in Gmail", emoji: true },
      url: composeUrl,
      style: "primary"
    }]
  });
}"""

# Also need to update the variable name in the return statement
OLD_DM_RETURN_DRAFT = "isDraft: true, blocks: JSON.stringify(blocks), fallbackText: output"
NEW_DM_RETURN_DRAFT = "isDraft: true, blocks: JSON.stringify(blocks), fallbackText: output, composeUrl"


def fix_dm_formatter(wf):
    """Fix Format DM Draft Mailto in Events Handler."""
    node = find_node(wf["nodes"], "Format DM Draft Mailto")
    if not node:
        print("  WARNING: 'Format DM Draft Mailto' not found")
        return 0

    code = node["parameters"]["jsCode"]
    changes = 0

    if OLD_DM_URL_BLOCK in code:
        code = code.replace(OLD_DM_URL_BLOCK, NEW_DM_URL_BLOCK)
        print("  Switched URL builder to Gmail compose (DM)")
        changes += 1

    if OLD_DM_RENDER in code:
        code = code.replace(OLD_DM_RENDER, NEW_DM_RENDER)
        print("  Switched render to Gmail button (DM)")
        changes += 1

    if OLD_DM_RETURN_DRAFT in code:
        code = code.replace(OLD_DM_RETURN_DRAFT, NEW_DM_RETURN_DRAFT)
        changes += 1

    node["parameters"]["jsCode"] = code
    return changes


# Interactive handler formatters have slightly different code
# They use the original MAILTO_CODE template from add_mailto_to_drafts.py

OLD_INT_URL = """// Build mailto URL
let mailtoUrl = '';
if (toEmail) {
  const params = [];
  if (subject) params.push('subject=' + encodeURIComponent(subject));
  if (ccEmail) params.push('cc=' + encodeURIComponent(ccEmail));
  if (plainBody) params.push('body=' + encodeURIComponent(plainBody));
  mailtoUrl = 'mailto:' + encodeURIComponent(toEmail);
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
  mailtoUrl = 'mailto:' + encodeURIComponent(toEmail) + '?' + params2.join('&');
}"""

NEW_INT_URL = """// Build Gmail compose deep link
let composeUrl = '';
if (toEmail || subject) {
  const params = ['view=cm', 'fs=1'];
  if (toEmail) params.push('to=' + encodeURIComponent(toEmail));
  if (ccEmail) params.push('cc=' + encodeURIComponent(ccEmail));
  if (subject) params.push('su=' + encodeURIComponent(subject));
  if (plainBody) params.push('body=' + encodeURIComponent(plainBody));
  composeUrl = 'https://mail.google.com/mail/?' + params.join('&');
}

// Truncate if too long
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

OLD_INT_RENDER = """if (toEmail) {
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

NEW_INT_RENDER = """if (composeUrl) {
  blocks.push({
    type: "actions",
    elements: [{
      type: "button",
      text: { type: "plain_text", text: ":email: Open in Gmail", emoji: true },
      url: composeUrl,
      style: "primary"
    }]
  });
}"""


def fix_int_formatter(wf, node_name):
    node = find_node(wf["nodes"], node_name)
    if not node:
        print(f"  WARNING: '{node_name}' not found")
        return 0

    code = node["parameters"]["jsCode"]
    changes = 0

    if OLD_INT_URL in code:
        code = code.replace(OLD_INT_URL, NEW_INT_URL)
        print(f"  Switched URL builder to Gmail compose ({node_name})")
        changes += 1
    elif OLD_DM_URL_BLOCK in code:
        # Might use the DM format
        code = code.replace(OLD_DM_URL_BLOCK, NEW_DM_URL_BLOCK)
        print(f"  Switched URL builder to Gmail compose ({node_name}) [DM format]")
        changes += 1

    if OLD_INT_RENDER in code:
        code = code.replace(OLD_INT_RENDER, NEW_INT_RENDER)
        print(f"  Switched render to Gmail button ({node_name})")
        changes += 1
    elif OLD_DM_RENDER in code:
        code = code.replace(OLD_DM_RENDER, NEW_DM_RENDER)
        print(f"  Switched render to Gmail button ({node_name}) [DM format]")
        changes += 1

    # Update variable references from mailtoUrl to composeUrl
    code = code.replace("mailtoUrl,", "composeUrl,")
    code = code.replace("mailtoUrl", "composeUrl")

    node["parameters"]["jsCode"] = code
    return changes


def main():
    # ── Events Handler ──
    print(f"Fetching Events Handler {WF_EVENTS_HANDLER}...")
    wf = fetch_workflow(WF_EVENTS_HANDLER)
    print(f"  {len(wf['nodes'])} nodes")

    changes = fix_dm_formatter(wf)
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
    changes2 += fix_int_formatter(wf2, "Format Draft with Mailto")
    changes2 += fix_int_formatter(wf2, "Format Re-engagement with Mailto")

    if changes2:
        print(f"\n=== Pushing Interactive Handler ({changes2} changes) ===")
        result2 = push_workflow(WF_INTERACTIVE_HANDLER, wf2)
        print(f"  HTTP 200, {len(result2['nodes'])} nodes")
        sync_local(result2, "Interactive Events Handler.json")

    print("\nDone!")


if __name__ == "__main__":
    main()
