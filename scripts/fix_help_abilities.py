"""
Fix: Update help text wording for "more <skill>" line.

Usage:
    N8N_API_KEY=... python scripts/fix_help_abilities.py
"""

from n8n_helpers import find_node, modify_workflow, WF_EVENTS_HANDLER


def modifier(nodes, connections):
    node = find_node(nodes, "Build Help Response")
    if not node:
        print("ERROR: Could not find 'Build Help Response' node")
        return 0

    code = node["parameters"]["jsCode"]

    old = "for details on any command (e.g."
    new = "for details on any of my abilities (e.g."

    if old in code:
        code = code.replace(old, new)
        node["parameters"]["jsCode"] = code
        print("  Updated: 'any command' → 'any of my abilities'")
        return 1

    print("  WARNING: Could not find target text")
    return 0


if __name__ == "__main__":
    result = modify_workflow(
        WF_EVENTS_HANDLER,
        "Slack Events Handler.json",
        modifier,
    )
    print(f"\nDone! {len(result['nodes'])} total nodes")
