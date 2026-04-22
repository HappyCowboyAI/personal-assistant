"""
Fix: Email drafts should be signed by the requesting rep, not the account AE.

The agent defaults to signing as whoever it finds as the account owner in
Backstory, but the email should always be signed by the person who asked
for the draft.

Updates three prompts:
1. Build DM System Prompt (Events Handler) — followup subRoute
2. Build Followup Context (Interactive Handler) — button-triggered drafts
3. Build Re-engagement Prompt (Interactive Handler) — silence drafts

Usage:
    N8N_API_KEY=... python scripts/fix_draft_signature.py
"""

from n8n_helpers import (
    find_node, fetch_workflow, push_workflow, sync_local,
    WF_EVENTS_HANDLER, WF_INTERACTIVE_HANDLER,
)


def fix_events_handler():
    """Fix the DM followup prompt signature."""
    print(f"Fetching Events Handler {WF_EVENTS_HANDLER}...")
    wf = fetch_workflow(WF_EVENTS_HANDLER)
    print(f"  {len(wf['nodes'])} nodes")

    node = find_node(wf["nodes"], "Build DM System Prompt")
    if not node:
        print("  ERROR: Could not find 'Build DM System Prompt'")
        return None

    code = node["parameters"]["jsCode"]

    # Add signature rule to the followup RULES section
    old_rules = "'- Do NOT use ### headers — use *bold* for labels',"
    new_rules = "'- Do NOT use ### headers — use *bold* for labels',\n    '- ALWAYS sign the email as ' + repName + '. Do NOT sign as the account owner or AE — the person requesting the draft is ' + repName + '.',"

    # This string appears in both followup and general sections - only replace in followup
    # Find the followup section specifically by looking for a unique nearby marker
    followup_marker = "**FOLLOW-UP EMAIL DRAFT MODE**"
    if followup_marker in code:
        # Find the position of the followup section
        followup_start = code.index(followup_marker)
        # Find the first occurrence of old_rules AFTER the followup section
        rules_pos = code.index(old_rules, followup_start)
        # Replace just that occurrence
        code = code[:rules_pos] + old_rules.replace(
            "'- Do NOT use ### headers — use *bold* for labels',",
            new_rules
        ) + code[rules_pos + len(old_rules):]
        print("  Added signature rule to DM followup prompt")
    else:
        print("  WARNING: Could not find FOLLOW-UP EMAIL DRAFT MODE section")
        return None

    node["parameters"]["jsCode"] = code

    print("\n=== Pushing Events Handler ===")
    result = push_workflow(WF_EVENTS_HANDLER, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")
    sync_local(result, "Slack Events Handler.json")
    return result


def fix_interactive_handler():
    """Fix both followup and re-engagement prompt signatures."""
    print(f"\nFetching Interactive Handler {WF_INTERACTIVE_HANDLER}...")
    wf = fetch_workflow(WF_INTERACTIVE_HANDLER)
    print(f"  {len(wf['nodes'])} nodes")

    changes = 0

    # ── Fix Build Followup Context ──
    node = find_node(wf["nodes"], "Build Followup Context")
    if node:
        code = node["parameters"]["jsCode"]

        old = "- Do NOT use ### headers"
        new = "- ALWAYS sign the email as ${repName}. Do NOT sign as the account owner or AE — the person requesting the draft is ${repName}.\n- Do NOT use ### headers"

        if old in code:
            code = code.replace(old, new, 1)
            node["parameters"]["jsCode"] = code
            print("  Added signature rule to Build Followup Context")
            changes += 1
        else:
            print("  WARNING: Could not find rules marker in Build Followup Context")
    else:
        print("  WARNING: Could not find 'Build Followup Context'")

    # ── Fix Build Re-engagement Prompt ──
    node2 = find_node(wf["nodes"], "Build Re-engagement Prompt")
    if node2:
        code = node2["parameters"]["jsCode"]

        old = "- Do NOT use ### headers"
        new = "- ALWAYS sign the email as ${repName}. Do NOT sign as the account owner or AE — the person requesting the draft is ${repName}.\n- Do NOT use ### headers"

        if old in code:
            code = code.replace(old, new, 1)
            node2["parameters"]["jsCode"] = code
            print("  Added signature rule to Build Re-engagement Prompt")
            changes += 1
        else:
            print("  WARNING: Could not find rules marker in Build Re-engagement Prompt")
    else:
        print("  WARNING: Could not find 'Build Re-engagement Prompt'")

    if changes == 0:
        print("  No changes made")
        return None

    print(f"\n=== Pushing Interactive Handler ({changes} changes) ===")
    result = push_workflow(WF_INTERACTIVE_HANDLER, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")
    sync_local(result, "Interactive Events Handler.json")
    return result


if __name__ == "__main__":
    fix_events_handler()
    fix_interactive_handler()
    print("\nDone!")
