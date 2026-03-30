"""
Fix: Wrap Pass 1/2/3 command matching in a route === 'unknown' guard
so that pending action routes (confirm_announce, cancel_announce, expire_pending)
aren't overwritten by the command matching chain.

The bug: The pending action check correctly sets route='confirm_announce' when
user types 'send', but the Pass 1/2/3 if/else chain runs unconditionally after.
Pass 3 sets route='cmd_other' + subRoute='unrecognized', overwriting the pending
action route.

Fix: Add `if (route === 'unknown') {` before Pass 1 and `}` after Pass 3's
closing brace, so command matching only runs when no route has been set yet.

Usage:
    N8N_API_KEY=... python scripts/fix_route_guard.py
"""

from n8n_helpers import find_node, modify_workflow, WF_EVENTS_HANDLER


def modifier(nodes, connections):
    route_node = find_node(nodes, "Route by State")
    if not route_node:
        print("ERROR: Could not find 'Route by State' node")
        return 0

    code = route_node["parameters"]["jsCode"]

    # Find the start of Pass 1 — the first `if` after the pending action block
    old_pass1_start = "  // --- Pass 1: Exact command matching (keyword at start of text) ---\n  if (lower.startsWith('announce:')"
    new_pass1_start = "  // --- Pass 1/2/3 only run if no route set by pending action check ---\n  if (route === 'unknown') {\n  // --- Pass 1: Exact command matching (keyword at start of text) ---\n  if (lower.startsWith('announce:')"

    if old_pass1_start not in code:
        print("  ERROR: Could not find Pass 1 start marker")
        return 0

    code = code.replace(old_pass1_start, new_pass1_start, 1)
    print("  Added route === 'unknown' guard before Pass 1")

    # Find the end of Pass 3 — the closing braces of the else chain
    # The Pass 3 block ends with "    }\n  }\n}" — we need to add one more closing brace
    # The structure is: else { Pass 2 ... else { Pass 3 ... } }
    # After the last } of the Pass 1/2/3 chain, we need to close the guard
    old_pass3_end = """      else subRoute = 'unrecognized';
    }
  }
}"""
    new_pass3_end = """      else subRoute = 'unrecognized';
    }
  }
  } // end route === 'unknown' guard
}"""

    if old_pass3_end not in code:
        print("  ERROR: Could not find Pass 3 end marker")
        return 0

    code = code.replace(old_pass3_end, new_pass3_end, 1)
    print("  Closed route === 'unknown' guard after Pass 3")

    route_node["parameters"]["jsCode"] = code
    return 1


if __name__ == "__main__":
    result = modify_workflow(
        WF_EVENTS_HANDLER,
        "Slack Events Handler.json",
        modifier,
    )
    print(f"\nDone! {len(result['nodes'])} total nodes")
