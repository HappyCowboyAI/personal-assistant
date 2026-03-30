"""
Fix: Add CC line to follow-up email draft prompts.

Tells Claude to include *CC:* with other meeting participants
so the Gmail compose button pre-fills CC recipients.

Updates:
1. Build DM System Prompt (Events Handler — DM followup)
2. Build Followup Context (Interactive Handler — button-triggered followup)
(Re-engagement already has CC)

Usage:
    N8N_API_KEY=... python scripts/fix_draft_cc.py
"""

from n8n_helpers import (
    find_node, fetch_workflow, push_workflow, sync_local,
    WF_EVENTS_HANDLER, WF_INTERACTIVE_HANDLER,
)


def fix_dm_prompt(wf):
    """Add CC line to DM followup prompt in Events Handler."""
    node = find_node(wf["nodes"], "Build DM System Prompt")
    if not node:
        print("  WARNING: 'Build DM System Prompt' not found")
        return 0

    code = node["parameters"]["jsCode"]

    OLD = (
        "'*To:* {Name} ({email@company.com}) — ALWAYS include email addresses. "
        "Use People.ai MCP to look up contact emails. If you cannot find an email, still include the name.',\n"
        "    '*Subject:* {concise subject line}',"
    )

    NEW = (
        "'*To:* {Name} ({email@company.com}) — ALWAYS include email addresses. "
        "Use People.ai MCP to look up contact emails. If you cannot find an email, still include the name.',\n"
        "    '*CC:* {Other meeting participants with emails — include internal team and external contacts}',\n"
        "    '*Subject:* {concise subject line}',"
    )

    if OLD in code:
        code = code.replace(OLD, NEW)
        node["parameters"]["jsCode"] = code
        print("  Added CC line to DM followup prompt")
        return 1
    elif "*CC:*" in code:
        print("  DM prompt already has CC line")
        return 0
    else:
        print("  WARNING: Could not find To/Subject format block in DM prompt")
        return 0


def fix_followup_context(wf):
    """Add CC line to Build Followup Context in Interactive Handler."""
    node = find_node(wf["nodes"], "Build Followup Context")
    if not node:
        print("  WARNING: 'Build Followup Context' not found")
        return 0

    code = node["parameters"]["jsCode"]

    OLD = "*To:* primary recipients\n*Subject:* concise subject line"
    NEW = (
        "*To:* primary recipient ({email@company.com}) — ALWAYS include email address\n"
        "*CC:* other meeting participants with emails — internal team and external contacts\n"
        "*Subject:* concise subject line"
    )

    if OLD in code:
        code = code.replace(OLD, NEW)
        node["parameters"]["jsCode"] = code
        print("  Added CC line to Build Followup Context")
        return 1
    elif "*CC:*" in code:
        print("  Build Followup Context already has CC line")
        return 0
    else:
        print("  WARNING: Could not find To/Subject in Build Followup Context")
        return 0


def main():
    # ── Events Handler ──
    print(f"Fetching Events Handler {WF_EVENTS_HANDLER}...")
    wf = fetch_workflow(WF_EVENTS_HANDLER)
    print(f"  {len(wf['nodes'])} nodes")

    changes = fix_dm_prompt(wf)
    if changes:
        print(f"\n=== Pushing Events Handler ({changes} changes) ===")
        result = push_workflow(WF_EVENTS_HANDLER, wf)
        print(f"  HTTP 200, {len(result['nodes'])} nodes")
        sync_local(result, "Slack Events Handler.json")

    # ── Interactive Handler ──
    print(f"\nFetching Interactive Handler {WF_INTERACTIVE_HANDLER}...")
    wf2 = fetch_workflow(WF_INTERACTIVE_HANDLER)
    print(f"  {len(wf2['nodes'])} nodes")

    changes2 = fix_followup_context(wf2)

    if changes2:
        print(f"\n=== Pushing Interactive Handler ({changes2} changes) ===")
        result2 = push_workflow(WF_INTERACTIVE_HANDLER, wf2)
        print(f"  HTTP 200, {len(result2['nodes'])} nodes")
        sync_local(result2, "Interactive Events Handler.json")

    print("\nDone!")


if __name__ == "__main__":
    main()
