#!/usr/bin/env python3
"""
Fix syntax error in Route by State node.

The jsCode has orphaned '}];' and '}' tokens between the variable
declarations and 'let userExists', causing "Unexpected token ']'" error.

Removes the stray code so the JS is valid again.
"""

from n8n_helpers import (
    find_node,
    modify_workflow,
    WF_EVENTS_HANDLER,
)


def fix_route_by_state(nodes, connections):
    route_node = find_node(nodes, "Route by State")
    if not route_node:
        print("ERROR: 'Route by State' node not found!")
        return 0

    code = route_node["parameters"]["jsCode"]

    # The corrupted section: variable declarations followed by stray }]; and }
    bad = "const userId = event.userId;\n\n  }];\n}\n\nlet userExists"
    good = "const userId = event.userId;\n\nlet userExists"

    if bad not in code:
        print("  Stray '}];' not found — code may already be fixed")
        return 0

    code = code.replace(bad, good)
    route_node["parameters"]["jsCode"] = code
    print("  Removed stray '}];' and '}' from Route by State")
    return 1


def main():
    print("=== Fix Route by State Syntax Error ===\n")
    modify_workflow(
        WF_EVENTS_HANDLER,
        "Slack Events Handler.json",
        fix_route_by_state,
    )
    print("\nDone! Route by State should no longer have 'Unexpected token' error.")


if __name__ == "__main__":
    main()
