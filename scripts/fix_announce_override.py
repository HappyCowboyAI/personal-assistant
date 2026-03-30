"""
Fix: Allow 'announce:' command to override an existing pending action.

The bug: If a pending action exists in the DB, ANY message that isn't 'send'
or 'cancel' routes to 'expire_pending'. This means a new 'announce:' command
gets swallowed instead of starting a fresh announcement flow.

Fix: Add 'announce:' as a special case in the pending action block so it
routes to 'cmd_announce' (the announce flow's Check Existing Announce node
already handles replacing the old pending action).

Usage:
    N8N_API_KEY=... python scripts/fix_announce_override.py
"""

from n8n_helpers import find_node, modify_workflow, WF_EVENTS_HANDLER


def modifier(nodes, connections):
    route_node = find_node(nodes, "Route by State")
    if not route_node:
        print("ERROR: Could not find 'Route by State' node")
        return 0

    code = route_node["parameters"]["jsCode"]

    # In the pending action block, add announce: override before expire_pending
    old_pending = "    else route = 'expire_pending';"
    new_pending = "    else if (lower.startsWith('announce:') || lower.startsWith('announce ')) route = 'cmd_announce';\n    else route = 'expire_pending';"

    if old_pending not in code:
        print("  ERROR: Could not find expire_pending fallback in pending action block")
        return 0

    code = code.replace(old_pending, new_pending, 1)
    print("  Added announce: override in pending action block")

    route_node["parameters"]["jsCode"] = code
    return 1


if __name__ == "__main__":
    result = modify_workflow(
        WF_EVENTS_HANDLER,
        "Slack Events Handler.json",
        modifier,
    )
    print(f"\nDone! {len(result['nodes'])} total nodes")
