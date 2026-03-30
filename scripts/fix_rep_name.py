"""
Fix: repName fallback in Build DM System Prompt.

user.name is null in the DB, so repName falls back to 'there'.
Fix: derive from email (scott.metcalf@people.ai → Scott Metcalf),
matching the pattern used in other workflows (Match Users to Meetings, etc.)

Usage:
    N8N_API_KEY=... python scripts/fix_rep_name.py
"""

from n8n_helpers import find_node, modify_workflow, WF_EVENTS_HANDLER


def modifier(nodes, connections):
    node = find_node(nodes, "Build DM System Prompt")
    if not node:
        print("ERROR: Could not find 'Build DM System Prompt'")
        return 0

    code = node["parameters"]["jsCode"]

    old = "const repName = user.name || 'there';"
    new = "const repName = user.name || (user.email || '').split('@')[0].replace(/\\./g, ' ').replace(/\\b\\w/g, c => c.toUpperCase()) || 'there';"

    if old in code:
        code = code.replace(old, new)
        node["parameters"]["jsCode"] = code
        print("  Fixed repName fallback: derives from email when name is null")
        return 1

    print("  WARNING: Could not find repName line")
    return 0


if __name__ == "__main__":
    result = modify_workflow(
        WF_EVENTS_HANDLER,
        "Slack Events Handler.json",
        modifier,
    )
    print(f"\nDone! {len(result['nodes'])} total nodes")
