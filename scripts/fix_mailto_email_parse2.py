"""
Fix: Interactive Handler mailto nodes — add parenthesized email parsing.

Usage:
    N8N_API_KEY=... python scripts/fix_mailto_email_parse2.py
"""

from n8n_helpers import (
    find_node, fetch_workflow, push_workflow, sync_local,
    WF_INTERACTIVE_HANDLER,
)


def modifier_fn(nodes, connections):
    changes = 0
    for name in ["Format Draft with Mailto", "Format Re-engagement with Mailto"]:
        node = find_node(nodes, name)
        if not node:
            print(f"  WARNING: '{name}' not found")
            continue

        code = node["parameters"]["jsCode"]

        old = "if (angleMatch) return angleMatch[1].trim();\n  const plainMatch"
        new = "if (angleMatch) return angleMatch[1].trim();\n  const parenMatch = line.match(/\\(([^)]+@[^)]+)\\)/);\n  if (parenMatch) return parenMatch[1].trim();\n  const plainMatch"

        if old in code:
            code = code.replace(old, new)
            node["parameters"]["jsCode"] = code
            print(f"  Added paren parsing to '{name}'")
            changes += 1
        else:
            print(f"  WARNING: pattern not found in '{name}'")

    return changes


if __name__ == "__main__":
    from n8n_helpers import modify_workflow
    result = modify_workflow(
        WF_INTERACTIVE_HANDLER,
        "Interactive Events Handler.json",
        modifier_fn,
    )
    print(f"\nDone! {len(result['nodes'])} total nodes")
