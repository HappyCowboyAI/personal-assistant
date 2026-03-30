"""
Fix: Move announce command detection into the Pass 1 if/else chain
so that Pass 2 fuzzy matching doesn't overwrite it.

The bug: "announce: ... presentation ..." was being routed to cmd_presentation
because the standalone announce check before Pass 1 set route='cmd_announce',
but Pass 1 didn't match, falling into the else block where Pass 2 fuzzy
matching found "presentation" and overwrote the route.

Fix: Remove the standalone announce check and add it as an else-if in Pass 1.

Usage:
    N8N_API_KEY=... python scripts/fix_announce_route.py
"""

from n8n_helpers import find_node, modify_workflow, WF_EVENTS_HANDLER


def modifier(nodes, connections):
    route_node = find_node(nodes, "Route by State")
    if not route_node:
        print("ERROR: Could not find 'Route by State' node")
        return 0

    code = route_node["parameters"]["jsCode"]

    # Remove the standalone announce check that was before Pass 1
    old_announce = """  // Announce command
  if (route === 'unknown' && (lower.startsWith('announce:') || lower.startsWith('announce '))) {
    route = 'cmd_announce';
  }

"""
    if old_announce in code:
        code = code.replace(old_announce, "")
        print("  Removed standalone announce check")
    else:
        print("  WARNING: Could not find standalone announce check to remove")

    # Add announce as the FIRST check in Pass 1 (before rename)
    # This ensures it's part of the if/else chain so Pass 2 won't run
    old_pass1_start = "  if (lower.startsWith('rename '))"
    new_pass1_start = "  if (lower.startsWith('announce:') || lower.startsWith('announce ')) route = 'cmd_announce';\n  else if (lower.startsWith('rename '))"

    if old_pass1_start in code:
        code = code.replace(old_pass1_start, new_pass1_start, 1)
        print("  Added announce to Pass 1 if/else chain")
    else:
        print("  WARNING: Could not find Pass 1 start")
        return 0

    route_node["parameters"]["jsCode"] = code
    return 1


if __name__ == "__main__":
    result = modify_workflow(
        WF_EVENTS_HANDLER,
        "Slack Events Handler.json",
        modifier,
    )
    print(f"\nDone! {len(result['nodes'])} total nodes")
