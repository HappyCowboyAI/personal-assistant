"""
Fix: Rename "Shortcuts" to "Skills" in help text.

Usage:
    N8N_API_KEY=... python scripts/fix_help_skills.py
"""

from n8n_helpers import find_node, modify_workflow, WF_EVENTS_HANDLER


def modifier(nodes, connections):
    node = find_node(nodes, "Build Help Response")
    if not node:
        print("ERROR: Could not find 'Build Help Response' node")
        return 0

    code = node["parameters"]["jsCode"]
    changes = 0

    # Rename header
    if '"*Shortcuts:*\\n"' in code:
        code = code.replace('"*Shortcuts:*\\n"', '"*Skills:*\\n"')
        print("  Renamed *Shortcuts:* → *Skills:*")
        changes += 1

    # Rename "more <shortcut>" reference
    if 'more <shortcut>' in code:
        code = code.replace('more <shortcut>', 'more <skill>')
        print("  Renamed more <shortcut> → more <skill>")
        changes += 1

    if changes:
        node["parameters"]["jsCode"] = code
    return changes


if __name__ == "__main__":
    result = modify_workflow(
        WF_EVENTS_HANDLER,
        "Slack Events Handler.json",
        modifier,
    )
    print(f"\nDone! {len(result['nodes'])} total nodes")
