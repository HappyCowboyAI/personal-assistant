#!/usr/bin/env python3
"""
Fix Switch Route connection misalignment in Slack Events Handler.

The "Switch Route" node's main outputs at indices 12-14 are misaligned:
- Index 12 (cmd_focus): currently empty — should connect to "Parse Focus"
- Index 13 (cmd_bbr): currently connects to "Parse Focus" — should connect to "Parse BBR"
- Index 14 (cmd_silence): currently connects to both "Parse BBR" AND "Send Checking Silence"
                          — should connect to ONLY "Send Checking Silence"

This script fetches the live workflow, fixes the three indices, pushes, and syncs.
"""

import json

from n8n_helpers import (
    modify_workflow,
    WF_EVENTS_HANDLER,
)

# Desired wiring for each index
FIXES = {
    12: [{"node": "Parse Focus", "type": "main", "index": 0}],
    13: [{"node": "Parse BBR", "type": "main", "index": 0}],
    14: [{"node": "Send Checking Silence", "type": "main", "index": 0}],
}


def fix_switch_route_wiring(nodes, connections):
    if "Switch Route" not in connections:
        print("ERROR: 'Switch Route' not found in connections dict!")
        return 0

    main_outputs = connections["Switch Route"]["main"]
    changes = 0

    for idx, desired in sorted(FIXES.items()):
        # Ensure the outputs array is long enough
        while len(main_outputs) <= idx:
            main_outputs.append([])

        current = main_outputs[idx]

        print(f"\n  Index {idx}:")
        print(f"    BEFORE: {json.dumps(current)}")
        print(f"    AFTER:  {json.dumps(desired)}")

        if current != desired:
            main_outputs[idx] = desired
            changes += 1
        else:
            print("    (already correct)")

    return changes


def main():
    print("=== Fix Switch Route Connection Misalignment ===\n")
    modify_workflow(
        WF_EVENTS_HANDLER,
        "Slack Events Handler.json",
        fix_switch_route_wiring,
    )
    print("\nDone! Switch Route indices 12-14 are now correctly wired.")


if __name__ == "__main__":
    main()
