"""
Fix: DM Fetch Today Meetings uses responseFormat: "text" but the CSV parser reads .json.data.

The Follow-up Cron's Fetch node does NOT use responseFormat: "text" and works correctly
(CSV response goes into .json.data). The DM Fetch node has responseFormat: "text" which
may store the response in a different field, causing the CSV parser to see empty data.

Fix: Remove the responseFormat: "text" option to match the working Follow-up Cron pattern.

Usage:
    N8N_API_KEY=... python3 scripts/fix_dm_fetch_response_format.py
"""

from n8n_helpers import (
    find_node, fetch_workflow, push_workflow, sync_local,
    WF_EVENTS_HANDLER,
)


def main():
    print(f"Fetching Events Handler {WF_EVENTS_HANDLER}...")
    wf = fetch_workflow(WF_EVENTS_HANDLER)
    nodes = wf["nodes"]
    print(f"  {len(nodes)} nodes")

    node = find_node(nodes, "DM Fetch Today Meetings")
    if not node:
        print("  ERROR: DM Fetch Today Meetings not found")
        return

    old_options = node["parameters"].get("options", {})
    print(f"  Current options: {old_options}")

    # Remove responseFormat: "text" — match the working Follow-up Cron pattern
    node["parameters"]["options"] = {}
    print("  Fixed: Removed responseFormat: 'text' — response will go into .json.data like Cron")

    print(f"\n=== Pushing Events Handler ===")
    result = push_workflow(WF_EVENTS_HANDLER, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")
    sync_local(result, "Slack Events Handler.json")

    print("\nDone! DM Fetch Today Meetings now matches Follow-up Cron's working pattern.")


if __name__ == "__main__":
    main()
