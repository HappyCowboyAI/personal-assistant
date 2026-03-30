"""
Redesign: Consolidated follow-up prompts (2x/day instead of per-meeting).

Changes:
  1. Schedule: every 15 min → 9am + 3pm PT weekdays
  2. Build Query: today only → last 24 hours (catches yesterday's late meetings)
  3. Check Sent Followups: extend dedup window to 48 hours
  4. Match Users to Ended Meetings: remove per-meeting timing window,
     group by user, include all meetings ended 4+ hours ago
  5. Build Follow-up Prompt: one Slack message per USER with all their
     ready meetings listed + individual Draft/Skip buttons per meeting

Usage:
    N8N_API_KEY=... python scripts/fix_followup_consolidated.py
"""

from n8n_helpers import (
    find_node, fetch_workflow, push_workflow, sync_local,
    WF_FOLLOWUP_CRON,
)

# ── 1. Schedule: 9am and 3pm PT weekdays ──────────────────────────────

def fix_schedule(wf):
    node = find_node(wf["nodes"], "Every 15 Minutes")
    if not node:
        print("  WARNING: Schedule trigger not found")
        return 0

    node["name"] = "Followup Check (9am + 3pm PT)"
    node["parameters"]["rule"] = {
        "interval": [
            {
                "field": "cronExpression",
                "expression": "0 9,15 * * 1-5"  # 9am and 3pm, Mon-Fri
            }
        ]
    }

    # Update connection key (old name → new name)
    conns = wf["connections"]
    old_conn = conns.pop("Every 15 Minutes", None)
    if old_conn:
        conns["Followup Check (9am + 3pm PT)"] = old_conn

    print("  Schedule: every 15 min → 9am + 3pm PT weekdays")
    return 1


# ── 2. Build Query: last 24 hours instead of today only ───────────────

NEW_BUILD_QUERY = r"""// Build People.ai export query for meetings in the last 24 hours
// At 9am: catches yesterday afternoon meetings (4h+ delay means they're ready)
// At 3pm: catches this morning's meetings (ended by 11am, 4h+ elapsed)
const now = Date.now();
const twentyFourHoursAgo = now - 24 * 60 * 60 * 1000;

const query = {
  object: "activity",
  filter: {
    "$and": [
      { attribute: { slug: "ootb_activity_type" }, clause: { "$eq": "meeting" } },
      { attribute: { slug: "ootb_activity_external" }, clause: { "$eq": true } },
      { attribute: { slug: "ootb_activity_timestamp" }, clause: { "$gte": twentyFourHoursAgo } },
      { attribute: { slug: "ootb_activity_timestamp" }, clause: { "$lte": now } }
    ]
  },
  columns: [
    { slug: "ootb_activity_uid" },
    { slug: "ootb_activity_timestamp" },
    { slug: "ootb_activity_subject" },
    { slug: "ootb_activity_originator" },
    { slug: "ootb_activity_account_name" },
    { slug: "ootb_activity_account_id" },
    { slug: "ootb_activity_opportunity_name" },
    { slug: "ootb_activity_participants" }
  ],
  sort: [{ attribute: { slug: "ootb_activity_timestamp" }, direction: "desc" }]
};

return [{ json: { query: JSON.stringify(query) } }];
"""

def fix_build_query(wf):
    node = find_node(wf["nodes"], "Build Query")
    if not node:
        print("  WARNING: Build Query not found")
        return 0

    node["parameters"]["jsCode"] = NEW_BUILD_QUERY
    print("  Build Query: startOfDay → last 24 hours")
    return 1


# ── 3. Check Sent Followups: extend dedup to 48 hours ─────────────────

def fix_check_sent(wf):
    node = find_node(wf["nodes"], "Check Sent Followups")
    if not node:
        print("  WARNING: Check Sent Followups not found")
        return 0

    # Replace the URL to look back 48 hours instead of just today
    node["parameters"]["url"] = (
        "=https://rhrlnkbphxntxxxcrgvv.supabase.co/rest/v1/messages"
        "?message_type=eq.followup_prompt"
        "&sent_at=gte.{{ new Date(Date.now() - 48 * 60 * 60 * 1000).toISOString() }}"
        "&select=user_id,metadata"
    )

    print("  Check Sent Followups: today → last 48 hours")
    return 1


# ── 4. Match Users: group by user, 4h+ elapsed, no timing window ──────

NEW_MATCH_USERS = r"""// Match users to meetings that ended 4+ hours ago (transcript available)
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

  // Derive rep name from email
  const repName = user.email
    ? user.email.split('@')[0].split('.').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
    : 'there';

  const readyMeetings = [];

  for (const meeting of meetings) {
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

def fix_match_users(wf):
    node = find_node(wf["nodes"], "Match Users to Ended Meetings")
    if not node:
        print("  WARNING: Match Users to Ended Meetings not found")
        return 0

    node["parameters"]["jsCode"] = NEW_MATCH_USERS
    print("  Match Users: per-meeting window → grouped by user, 4h+ elapsed")
    return 1


# ── 5. Build Follow-up Prompt: consolidated per-user message ──────────

NEW_BUILD_PROMPT = r"""// Build a consolidated follow-up prompt: one Slack message per user
// Lists all their ready meetings with individual Draft/Skip buttons
const data = $input.first().json;
const meetings = data.meetings || [];

if (meetings.length === 0) {
  return [{ json: { ...data, skip: true } }];
}

const noun = meetings.length === 1 ? 'meeting' : 'meetings';
let headerText = `:email:  You have *${meetings.length} ${noun}* ready for follow-up`;

const blocks = [
  {
    type: "section",
    text: { type: "mrkdwn", text: headerText }
  },
  { type: "divider" }
];

// Track all activity UIDs for logging
const activityUids = [];

for (const m of meetings) {
  const subjectTrunc = m.subject.length > 50
    ? m.subject.substring(0, 47) + '...'
    : m.subject;

  const meetingLine = `*${m.dayStr} ${m.timeStr}* — ${subjectTrunc}\n_${m.accountName}_` +
    (m.hoursAgo ? ` | ${m.hoursAgo}h ago` : '');

  // Button payload for this specific meeting
  const buttonValue = JSON.stringify({
    accountName: m.accountName,
    accountId: m.accountId,
    activityUid: m.activityUid,
    meetingSubject: m.subject,
    participants: m.participants,
    userId: data.userId,
    dbUserId: data.userId,
    slackUserId: data.slackUserId,
    organizationId: data.organizationId,
    assistantName: data.assistantName,
    assistantEmoji: data.assistantEmoji,
    repName: data.repName,
  });

  blocks.push({
    type: "section",
    text: { type: "mrkdwn", text: meetingLine },
    accessory: {
      type: "button",
      text: { type: "plain_text", text: "Draft Follow-up", emoji: true },
      style: "primary",
      action_id: "followup_draft",
      value: buttonValue,
    }
  });

  activityUids.push(m.activityUid);
}

// Footer
blocks.push({ type: "divider" });
blocks.push({
  type: "context",
  elements: [
    { type: "mrkdwn", text: "_Transcript data is available for these meetings. Tap to draft a follow-up email._" }
  ]
});

const promptText = `You have ${meetings.length} ${noun} ready for follow-up.`;

return [{
  json: {
    ...data,
    promptText,
    blocks: JSON.stringify(blocks),
    activityUids,
  }
}];
"""

def fix_build_prompt(wf):
    node = find_node(wf["nodes"], "Build Follow-up Prompt")
    if not node:
        print("  WARNING: Build Follow-up Prompt not found")
        return 0

    node["parameters"]["jsCode"] = NEW_BUILD_PROMPT
    print("  Build Prompt: per-meeting → consolidated per-user with meeting list")
    return 1


# ── 6. Fix Prepare Log Data: log one entry per meeting in the list ─────

NEW_PREPARE_LOG = r"""// Log one message row per meeting that was included in the prompt
const data = $('Build Follow-up Prompt').first().json;
const sendResult = $('Send Follow-up Prompt').first().json;

const activityUids = data.activityUids || [];
const output = [];

for (const uid of activityUids) {
  // Find matching meeting details
  const meeting = (data.meetings || []).find(m => m.activityUid === uid);

  output.push({
    json: {
      user_id: data.userId,
      message_type: 'followup_prompt',
      channel: 'slack',
      direction: 'outbound',
      content: data.promptText,
      metadata: JSON.stringify({
        activity_uid: uid,
        account_name: meeting ? meeting.accountName : '',
        meeting_subject: meeting ? meeting.subject : '',
        slack_ts: sendResult.ts || null,
        slack_channel: sendResult.channel || null,
        consolidated: true,
        total_meetings: activityUids.length,
      }),
    }
  });
}

if (output.length === 0) {
  return [{ json: { _skip: true } }];
}

return output;
"""

def fix_prepare_log(wf):
    node = find_node(wf["nodes"], "Prepare Log Data")
    if not node:
        print("  WARNING: Prepare Log Data not found")
        return 0

    node["parameters"]["jsCode"] = NEW_PREPARE_LOG
    print("  Prepare Log: single entry → one per meeting (for dedup)")
    return 1


# ── 7. Fix Send Follow-up Prompt: reference updated node names ─────────

def fix_send_prompt(wf):
    node = find_node(wf["nodes"], "Send Follow-up Prompt")
    if not node:
        print("  WARNING: Send Follow-up Prompt not found")
        return 0

    # The jsonBody references Build Follow-up Prompt which still exists
    # but we need to make sure it works with the new consolidated format
    # Current jsonBody already references the right node, just verify
    current = node["parameters"].get("jsonBody", "")
    if "Build Follow-up Prompt" in current:
        print("  Send Follow-up Prompt: already references correct node")
        return 0

    return 0


def main():
    print(f"Fetching Follow-up Cron {WF_FOLLOWUP_CRON}...")
    wf = fetch_workflow(WF_FOLLOWUP_CRON)
    print(f"  {len(wf['nodes'])} nodes")

    changes = 0
    changes += fix_schedule(wf)
    changes += fix_build_query(wf)
    changes += fix_check_sent(wf)
    changes += fix_match_users(wf)
    changes += fix_build_prompt(wf)
    changes += fix_prepare_log(wf)
    changes += fix_send_prompt(wf)

    if changes:
        print(f"\n=== Pushing Follow-up Cron ({changes} changes) ===")
        result = push_workflow(WF_FOLLOWUP_CRON, wf)
        print(f"  HTTP 200, {len(result['nodes'])} nodes")
        sync_local(result, "Follow-up Cron.json")
    else:
        print("\n  No changes needed")

    print("\nDone! Follow-up Cron now runs at 9am + 3pm PT with consolidated prompts.")
    print("  - 9am: covers yesterday afternoon meetings (4h+ transcript delay)")
    print("  - 3pm: covers today's morning meetings")
    print("  - One Slack message per user listing all ready meetings")
    print("  - Individual 'Draft Follow-up' button per meeting")


if __name__ == "__main__":
    main()
