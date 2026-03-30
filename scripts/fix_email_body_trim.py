"""
Fix: Stop email body extraction at the signature — don't include Slack UI chrome.

The Gmail compose body currently includes everything after the Subject line,
including the trailing --- divider, warning notes, and "Reply to adjust tone" text.

These are meant for the Slack thread UI, not the email body.

The body should end at:
- A trailing "---" divider (the one AFTER the email body)
- Any line starting with "_Reply" or warning emoji
- Any line starting with ":warning:" or similar

Updates all three formatters.

Usage:
    N8N_API_KEY=... python scripts/fix_email_body_trim.py
"""

from n8n_helpers import (
    find_node, fetch_workflow, push_workflow, sync_local,
    WF_EVENTS_HANDLER, WF_INTERACTIVE_HANDLER,
)

# Current end markers (too limited)
OLD_EXTRACT = """// Extract body between Subject and ending markers
let body = '';
if (subjectMatch) {
  const startIdx = output.indexOf(subjectMatch[0]) + subjectMatch[0].length;
  let endIdx = output.length;
  const endMarkers = ['\\n*Next Steps', '\\n_Reply in this thread', '\\n---\\n_'];
  for (const marker of endMarkers) {
    const idx = output.indexOf(marker, startIdx);
    if (idx > -1 && idx < endIdx) endIdx = idx;
  }
  body = output.substring(startIdx, endIdx).trim();
  body = body.replace(/^---\\s*/, '').replace(/\\s*---$/, '').trim();
}"""

# Better extraction: find body between the two --- dividers, plus more end markers
NEW_EXTRACT = """// Extract email body between the --- dividers (after Subject, before trailing ---)
let body = '';
if (subjectMatch) {
  const startIdx = output.indexOf(subjectMatch[0]) + subjectMatch[0].length;
  let afterSubject = output.substring(startIdx);

  // The email body is typically wrapped in --- dividers
  // Find the opening --- after subject
  const openDivider = afterSubject.indexOf('---');
  if (openDivider > -1) {
    const bodyStart = openDivider + 3;
    // Find the closing --- after the body
    const closeDivider = afterSubject.indexOf('\\n---', bodyStart);
    if (closeDivider > -1) {
      body = afterSubject.substring(bodyStart, closeDivider).trim();
    } else {
      // No closing divider — use end markers as fallback
      body = afterSubject.substring(bodyStart).trim();
    }
  } else {
    // No dividers at all — take everything after subject
    body = afterSubject.trim();
  }

  // Trim at any Slack UI chrome that leaked through
  const uiMarkers = [
    '\\n_Reply in this thread',
    '\\n_Reply to adjust',
    '\\n:warning:',
    '\\n\\u26a0',
    '\\n*Next Steps',
  ];
  for (const marker of uiMarkers) {
    const idx = body.indexOf(marker);
    if (idx > -1) body = body.substring(0, idx).trim();
  }

  // Clean up any remaining --- at start/end
  body = body.replace(/^---\\s*/, '').replace(/\\s*---$/, '').trim();
}"""


def fix_formatter(wf, node_name):
    node = find_node(wf["nodes"], node_name)
    if not node:
        print(f"  WARNING: '{node_name}' not found")
        return 0

    code = node["parameters"]["jsCode"]

    if OLD_EXTRACT in code:
        code = code.replace(OLD_EXTRACT, NEW_EXTRACT)
        node["parameters"]["jsCode"] = code
        print(f"  Updated body extraction in '{node_name}'")
        return 1
    elif "Slack UI chrome" in code:
        print(f"  '{node_name}' already has updated extraction")
        return 0
    else:
        print(f"  WARNING: Could not find extraction block in '{node_name}'")
        return 0


def main():
    # ── Events Handler ──
    print(f"Fetching Events Handler {WF_EVENTS_HANDLER}...")
    wf = fetch_workflow(WF_EVENTS_HANDLER)
    print(f"  {len(wf['nodes'])} nodes")

    changes = fix_formatter(wf, "Format DM Draft Mailto")
    if changes:
        print(f"\n=== Pushing Events Handler ===")
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
        print(f"\n=== Pushing Interactive Handler ===")
        result2 = push_workflow(WF_INTERACTIVE_HANDLER, wf2)
        print(f"  HTTP 200, {len(result2['nodes'])} nodes")
        sync_local(result2, "Interactive Events Handler.json")

    print("\nDone!")


if __name__ == "__main__":
    main()
