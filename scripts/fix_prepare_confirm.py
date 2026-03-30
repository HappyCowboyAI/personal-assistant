"""
Fix: Prepare Confirm node — pending.context is already an object, not a JSON string.

JSON.parse(pending.context || '{}') fails with "[object Object] is not valid JSON"
because Supabase JSONB columns are returned as parsed objects by n8n.

Usage:
    N8N_API_KEY=... python scripts/fix_prepare_confirm.py
"""

from n8n_helpers import find_node, modify_workflow, WF_EVENTS_HANDLER


def modifier(nodes, connections):
    node = find_node(nodes, "Prepare Confirm")
    if not node:
        print("ERROR: Could not find 'Prepare Confirm' node")
        return 0

    code = node["parameters"]["jsCode"]

    old = "JSON.parse(pending.context || '{}').user_count || 0"
    new = "(typeof pending.context === 'string' ? JSON.parse(pending.context) : (pending.context || {})).user_count || 0"

    if old not in code:
        print(f"  WARNING: Could not find exact match. Current code:")
        print(code)
        return 0

    code = code.replace(old, new)
    node["parameters"]["jsCode"] = code
    print("  Fixed JSON.parse on pending.context (handle object or string)")
    return 1


if __name__ == "__main__":
    result = modify_workflow(
        WF_EVENTS_HANDLER,
        "Slack Events Handler.json",
        modifier,
    )
    print(f"\nDone! {len(result['nodes'])} total nodes")
