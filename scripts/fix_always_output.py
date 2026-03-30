"""
Fix: Set alwaysOutputData on Check Pending Action and Check Existing Announce
nodes so they pass through even when Supabase returns empty arrays.

Usage:
    N8N_API_KEY=... python scripts/fix_always_output.py
"""

from n8n_helpers import find_node, modify_workflow, WF_EVENTS_HANDLER


def modifier(nodes, connections):
    changes = 0
    for name in ["Check Pending Action", "Check Existing Announce"]:
        node = find_node(nodes, name)
        if node:
            node["alwaysOutputData"] = True
            print(f"  Set alwaysOutputData on '{name}'")
            changes += 1
    return changes


if __name__ == "__main__":
    result = modify_workflow(
        WF_EVENTS_HANDLER,
        "Slack Events Handler.json",
        modifier,
    )
    print(f"\nDone! {len(result['nodes'])} total nodes")
