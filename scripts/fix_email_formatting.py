"""
Fix: Improve email body formatting for Gmail compose.

Problems:
- **double bold** asterisks show as literal * in Gmail
- :emoji: codes show as text in Gmail
- Bullet formatting could be cleaner

Updates all three formatters.

Usage:
    N8N_API_KEY=... python scripts/fix_email_formatting.py
"""

from n8n_helpers import (
    find_node, fetch_workflow, push_workflow, sync_local,
    WF_EVENTS_HANDLER, WF_INTERACTIVE_HANDLER,
)

# Current stripping (same in all three formatters)
OLD_STRIP = """// Strip Slack mrkdwn for plain-text email
const plainBody = body
  .replace(/\\*([^*]+)\\*/g, '$1')
  .replace(/_([^_]+)_/g, '$1')
  .replace(/•/g, '-')
  .replace(/\\n{3,}/g, '\\n\\n');"""

# Also match the variant with comments
OLD_STRIP_COMMENTED = """// Strip Slack mrkdwn for plain-text email body
const plainBody = body
  .replace(/\\*([^*]+)\\*/g, '$1')   // bold
  .replace(/_([^_]+)_/g, '$1')     // italic
  .replace(/•/g, '-')               // bullets
  .replace(/\\n{3,}/g, '\\n\\n');      // excess newlines"""

# Better stripping for Gmail plain text
NEW_STRIP = """// Strip Slack mrkdwn for plain-text email
const plainBody = body
  .replace(/\\*\\*([^*]+)\\*\\*/g, '$1')  // **double bold** (Markdown)
  .replace(/\\*([^*]+)\\*/g, '$1')       // *single bold* (Slack mrkdwn)
  .replace(/_([^_]+)_/g, '$1')          // _italic_
  .replace(/~([^~]+)~/g, '$1')          // ~strikethrough~
  .replace(/:[a-z0-9_+-]+:/g, '')       // :emoji: codes
  .replace(/•/g, '-')                    // bullet chars
  .replace(/- \\*\\*/g, '- ')             // leftover bold after bullets
  .replace(/\\*\\*$/gm, '')               // trailing bold markers
  .replace(/\\n{3,}/g, '\\n\\n')           // excess newlines
  .trim();"""


def fix_formatter(wf, node_name):
    node = find_node(wf["nodes"], node_name)
    if not node:
        print(f"  WARNING: '{node_name}' not found")
        return 0

    code = node["parameters"]["jsCode"]
    changed = False

    if OLD_STRIP_COMMENTED in code:
        code = code.replace(OLD_STRIP_COMMENTED, NEW_STRIP)
        changed = True
    elif OLD_STRIP in code:
        code = code.replace(OLD_STRIP, NEW_STRIP)
        changed = True

    if changed:
        node["parameters"]["jsCode"] = code
        print(f"  Updated mrkdwn stripping in '{node_name}'")
        return 1
    elif "double bold" in code:
        print(f"  '{node_name}' already has updated stripping")
        return 0
    else:
        print(f"  WARNING: Could not find strip block in '{node_name}'")
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
