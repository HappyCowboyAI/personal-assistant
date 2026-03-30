"""
Fix: DM Build Meeting Query returns ALL org meetings (34+) but the CSV parser
in Build DM System Prompt only processes the first 19 rows. TransUnion's meeting
at row 24 gets cut off.

Fix: Increase the CSV parser limit from 20 to 100 to capture all meetings.
The meeting list is injected as prompt context, so showing all is fine.

Usage:
    N8N_API_KEY=... python3 scripts/fix_dm_meeting_limit.py
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

    node = find_node(nodes, "Build DM System Prompt")
    if not node:
        print("  ERROR: Build DM System Prompt not found")
        return

    code = node["parameters"]["jsCode"]

    # Fix 1: Increase row limit from 20 to 100
    old_limit = "Math.min(lines.length, 20)"
    new_limit = "Math.min(lines.length, 100)"
    if old_limit in code:
        code = code.replace(old_limit, new_limit)
        print("  Fixed: CSV parser row limit 20 → 100")
    else:
        print(f"  WARNING: Could not find '{old_limit}' in code")

    node["parameters"]["jsCode"] = code

    print(f"\n=== Pushing Events Handler ===")
    result = push_workflow(WF_EVENTS_HANDLER, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")
    sync_local(result, "Slack Events Handler.json")

    print("\nDone! CSV parser now processes up to 99 meetings instead of 19.")
    print("TransUnion at row 24 will now be included in the meeting list.")


if __name__ == "__main__":
    main()
