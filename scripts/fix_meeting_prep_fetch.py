"""
Fix: Meeting Prep Cron's "Fetch Today Meetings" fails with "stream has been aborted".

Same issue as DM Fetch: responseFormat: "text" causes stream problems with large CSV.
The Follow-up Cron's equivalent node works fine without it.

Fix: Remove responseFormat: "text" and add a timeout.

Usage:
    N8N_API_KEY=... python3 scripts/fix_meeting_prep_fetch.py
"""

from n8n_helpers import (
    find_node, fetch_workflow, push_workflow, sync_local,
    WF_MEETING_PREP_CRON,
)


def main():
    print(f"Fetching Meeting Prep Cron {WF_MEETING_PREP_CRON}...")
    wf = fetch_workflow(WF_MEETING_PREP_CRON)
    nodes = wf["nodes"]
    print(f"  {len(nodes)} nodes")

    node = find_node(nodes, "Fetch Today Meetings")
    if not node:
        print("  ERROR: Fetch Today Meetings not found")
        return

    old_options = node["parameters"].get("options", {})
    print(f"  Current options: {old_options}")

    # Remove responseFormat: "text" and add timeout
    node["parameters"]["options"] = {
        "timeout": 30000,  # 30 second timeout
    }
    print("  Fixed: Removed responseFormat: 'text', added 30s timeout")

    print(f"\n=== Pushing Meeting Prep Cron ===")
    result = push_workflow(WF_MEETING_PREP_CRON, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")
    sync_local(result, "Meeting Prep Cron.json")

    print("\nDone!")


if __name__ == "__main__":
    main()
