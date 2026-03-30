"""
Fix: Meeting Prep Cron's Query API call aborts because the response is too large.

The heavy columns (ootb_activity_account, ootb_activity_opportunity) return full
objects with (id) and (name) sub-columns, bloating the CSV. Combined with 48h of
org-wide meetings + participant arrays, the API aborts the stream.

Fix: Use lightweight _name columns instead of full objects. Drop title (not needed
for user-to-meeting matching). Keep external (needed to identify internal participants).

Also update Parse Meetings to handle the new "Account Name" header (vs "Account (name)").

Usage:
    N8N_API_KEY=... python3 scripts/fix_meeting_prep_query.py
"""

from n8n_helpers import (
    find_node, fetch_workflow, push_workflow, sync_local,
    WF_MEETING_PREP_CRON,
)


NEW_BUILD_QUERY = r"""// Build People.ai activity export query for upcoming external meetings
// NOTE: Do NOT include ootb_activity_participants_title — it causes the API
// to abort the stream when combined with 48h of org-wide meetings.
const tz = 'America/Los_Angeles';
const now = new Date();

const windowStart = now.getTime();

// End of tomorrow (48h buffer)
const todayStr = now.toLocaleDateString('en-US', { timeZone: tz });
const parts = todayStr.split('/');
const todayMidnight = new Date(parts[2] + '-' + parts[0].padStart(2, '0') + '-' + parts[1].padStart(2, '0') + 'T00:00:00-08:00');
const tomorrowEnd = new Date(todayMidnight.getTime() + 48 * 3600000);

const query = {
  object: "activity",
  filter: {
    "$and": [
      { attribute: { slug: "ootb_activity_type" }, clause: { "$eq": "meeting" } },
      { attribute: { slug: "ootb_activity_external" }, clause: { "$eq": true } },
      { attribute: { slug: "ootb_activity_timestamp" }, clause: { "$gte": windowStart } },
      { attribute: { slug: "ootb_activity_timestamp" }, clause: { "$lte": tomorrowEnd.getTime() } }
    ]
  },
  columns: [
    { slug: "ootb_activity_uid" },
    { slug: "ootb_activity_timestamp" },
    { slug: "ootb_activity_subject" },
    { slug: "ootb_activity_participants", variation_id: "ootb_activity_participants_email" },
    { slug: "ootb_activity_participants", variation_id: "ootb_activity_participants_name" },
    { slug: "ootb_activity_participants", variation_id: "ootb_activity_participants_external" },
    { slug: "ootb_activity_account" },
    { slug: "ootb_activity_opportunity" }
  ],
  sort: [
    { attribute: { slug: "ootb_activity_timestamp" }, direction: "asc" }
  ]
};

return [{ json: { query: JSON.stringify(query) } }];
"""


def main():
    print(f"Fetching Meeting Prep Cron {WF_MEETING_PREP_CRON}...")
    wf = fetch_workflow(WF_MEETING_PREP_CRON)
    nodes = wf["nodes"]
    print(f"  {len(nodes)} nodes")

    # Fix Build Query columns
    bq = find_node(nodes, "Build Query")
    if not bq:
        print("  ERROR: Build Query not found")
        return
    bq["parameters"]["jsCode"] = NEW_BUILD_QUERY
    print("  Build Query: swapped heavy object columns for lightweight _name variants")

    # Parse Meetings doesn't need changes — account/opportunity object columns
    # still return "Account (name)" / "Opportunity (name)" headers as before

    print(f"\n=== Pushing Meeting Prep Cron ===")
    result = push_workflow(WF_MEETING_PREP_CRON, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")
    sync_local(result, "Meeting Prep Cron.json")

    print("\nDone! Meeting Prep Cron query fixed.")
    print("  Dropped: ootb_activity_participants_title (causes API stream abort)")
    print("  Kept: account + opportunity objects (needed for id + name)")
    print("  Kept: participant email/name/external (needed for user matching)")


if __name__ == "__main__":
    main()
