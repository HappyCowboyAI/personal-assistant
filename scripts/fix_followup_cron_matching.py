"""
Fix: Follow-up Cron sends ALL meetings to ALL users instead of only meetings
where the user is a participant.

The Match Users to Ended Meetings code has no participant filtering — it gives
every user every meeting that's 4+ hours old.

Fix: Check if user.email is in meeting.participantEmails before including it.

Usage:
    N8N_API_KEY=... python3 scripts/fix_followup_cron_matching.py
"""

from n8n_helpers import (
    find_node, fetch_workflow, push_workflow, sync_local,
    WF_FOLLOWUP_CRON,
)


NEW_MATCH_USERS = r"""// Match users to meetings that ended 4+ hours ago (transcript available)
// CRITICAL: Only include meetings where the user is a PARTICIPANT
// Group by user: output ONE item per user with all their ready meetings
const meetings = $('Parse Meetings').first().json.meetings || [];
const usersAll = $('Get Followup Users').all().map(i => i.json);
const sentAll = $('Check Sent Followups').all().map(i => i.json);

// Filter valid users
const users = usersAll.filter(u => u && u.id && u.onboarding_state === 'complete');

// Build dedup set: userId:activityUid
const sentSet = new Set();
for (const msg of sentAll) {
  if (msg && msg.metadata) {
    try {
      const meta = typeof msg.metadata === 'string' ? JSON.parse(msg.metadata) : msg.metadata;
      if (meta.activity_uid && msg.user_id) {
        sentSet.add(msg.user_id + ':' + meta.activity_uid);
      }
    } catch(e) {}
  }
}

const now = Date.now();
const MEETING_DURATION_MS = 60 * 60 * 1000; // assume 60 min meetings
const MIN_ELAPSED_MS = 4 * 60 * 60 * 1000;  // 4 hours after meeting end

const output = [];

for (const user of users) {
  const followupEnabled = user.followup_enabled !== false;
  if (!followupEnabled) continue;

  const userEmail = (user.email || '').toLowerCase();
  if (!userEmail) continue;

  // Derive rep name from email
  const repName = userEmail
    .split('@')[0].split('.').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');

  const readyMeetings = [];

  for (const meeting of meetings) {
    // ── PARTICIPANT CHECK: only include meetings this user attended ──
    const participantEmails = (meeting.participantEmails || []).map(e => e.toLowerCase());
    if (!participantEmails.includes(userEmail)) continue;

    const estimatedEnd = meeting.timestamp + MEETING_DURATION_MS;
    const timeSinceEnd = now - estimatedEnd;

    // Must have ended 4+ hours ago (transcript available by now)
    if (timeSinceEnd < MIN_ELAPSED_MS) continue;

    // Skip if already prompted for this meeting
    const dedupKey = user.id + ':' + meeting.activityUid;
    if (sentSet.has(dedupKey)) continue;

    // Skip meetings without account context
    if (!meeting.accountName) continue;

    const tz = 'America/Los_Angeles';
    const meetingDate = new Date(meeting.timestamp);
    const timeStr = meetingDate.toLocaleTimeString('en-US', { timeZone: tz, hour: 'numeric', minute: '2-digit' });
    const dayStr = meetingDate.toLocaleDateString('en-US', { timeZone: tz, weekday: 'short' });

    const hoursAgo = Math.round(timeSinceEnd / 3600000);

    readyMeetings.push({
      activityUid: meeting.activityUid,
      subject: meeting.subject || '[no subject]',
      accountName: meeting.accountName,
      accountId: meeting.accountId,
      opportunityName: meeting.opportunityName,
      participants: meeting.participants,
      timestamp: meeting.timestamp,
      timeStr,
      dayStr,
      hoursAgo,
    });
  }

  if (readyMeetings.length === 0) continue;

  // Sort by time (most recent first)
  readyMeetings.sort((a, b) => b.timestamp - a.timestamp);

  output.push({
    json: {
      userId: user.id,
      slackUserId: user.slack_user_id,
      email: user.email,
      repName,
      assistantName: user.assistant_name || 'Aria',
      assistantEmoji: user.assistant_emoji || ':robot_face:',
      organizationId: user.organization_id,
      meetings: readyMeetings,
      meetingCount: readyMeetings.length,
    }
  });
}

if (output.length === 0) {
  return [{ json: { noMatches: true } }];
}

return output;
"""


def main():
    print(f"Fetching Follow-up Cron {WF_FOLLOWUP_CRON}...")
    wf = fetch_workflow(WF_FOLLOWUP_CRON)
    nodes = wf["nodes"]
    print(f"  {len(nodes)} nodes")

    node = find_node(nodes, "Match Users to Ended Meetings")
    if not node:
        print("  ERROR: Match Users to Ended Meetings not found")
        return

    node["parameters"]["jsCode"] = NEW_MATCH_USERS
    print("  Match Users: added participant email filtering")

    print(f"\n=== Pushing Follow-up Cron ===")
    result = push_workflow(WF_FOLLOWUP_CRON, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")
    sync_local(result, "Follow-up Cron.json")

    print("\nDone! Users now only see meetings they participated in.")
    print("  Added: participantEmails.includes(userEmail) check")
    print("  Before: every user got every meeting (21 meetings to everyone)")
    print("  After: each user only gets their own meetings")


if __name__ == "__main__":
    main()
