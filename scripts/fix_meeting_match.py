#!/usr/bin/env python3
"""
Fix Meeting Prep Cron matching logic:
- Remove Fetch Open Opps and Parse Opps CSV (export API doesn't return owners)
- Simplified matching: all external meetings → all prep-enabled users
- Correct for exec-level visibility (user wants all customer meeting briefs)
"""

import json
import os
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

CRON_ID = "Of1U4T6x07aVqBYD"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

SIMPLE_MATCH_CODE = r"""// Match meetings to prep-enabled users
// The People.ai export API doesn't return participant/owner data,
// so we send briefs to all prep-enabled users for all external meetings
// within their prep window. Correct for exec-level visibility.
const meetingsData = $('Parse Meetings').first().json;
const meetings = meetingsData.meetings || [];
const users = $('Get Prep Users').all().map(item => item.json);
const sentBriefs = $('Check Sent Briefs').all().map(item => item.json);

// Build dedup set: "userId:activityUid"
const sentKeys = new Set();
for (const brief of sentBriefs) {
  let meta = brief.metadata || {};
  if (typeof meta === 'string') {
    try { meta = JSON.parse(meta); } catch(e) { meta = {}; }
  }
  if (meta.activity_uid && brief.user_id) {
    sentKeys.add(brief.user_id + ':' + meta.activity_uid);
  }
}

const now = Date.now();
const results = [];

for (const user of users) {
  const prepMinutes = user.meeting_prep_minutes_before || 120;
  const prepWindowMs = prepMinutes * 60 * 1000;
  const tooLateMs = 15 * 60 * 1000;

  const userEmail = (user.email || '').toLowerCase();
  const repName = userEmail.split('@')[0]
    .replace(/\./g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase());

  for (const meeting of meetings) {
    if (!meeting.accountName) continue;

    const timeUntil = meeting.timestampMs - now;
    if (timeUntil < tooLateMs || timeUntil > prepWindowMs) continue;

    const dedupKey = user.id + ':' + meeting.activityUid;
    if (sentKeys.has(dedupKey)) continue;

    results.push({
      userId: user.id,
      slackUserId: user.slack_user_id,
      email: user.email,
      assistant_name: user.assistant_name,
      assistant_emoji: user.assistant_emoji,
      assistant_persona: user.assistant_persona,
      timezone: user.timezone || 'America/Los_Angeles',
      repName,
      accountName: meeting.accountName,
      meetingSubject: meeting.subject,
      meetingTime: String(meeting.timestampMs),
      participants: '',
      opportunityName: meeting.oppName || '',
      opportunityStage: '',
      opportunityAmount: '',
      opportunityCloseDate: '',
      opportunityEngagement: '',
      activityUid: meeting.activityUid
    });
  }
}

if (results.length === 0) {
  return [{ json: { matches: [], matchCount: 0, noMatches: true } }];
}

return results.map(r => ({ json: r }));
"""


def main():
    print("Fetching Meeting Prep Cron...")
    resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{CRON_ID}", headers=HEADERS)
    resp.raise_for_status()
    wf = resp.json()
    print(f"  {len(wf['nodes'])} nodes")

    # Remove unused opp-related nodes
    removed = []
    wf["nodes"] = [n for n in wf["nodes"] if n["name"] not in ("Fetch Open Opps", "Parse Opps CSV")]
    if len(wf["nodes"]) < 15:
        removed = ["Fetch Open Opps", "Parse Opps CSV"]
        print(f"  Removed {removed}")

    # Clean connections
    for name in removed:
        wf["connections"].pop(name, None)

    # Remove Fetch Open Opps from Get Auth Token targets
    auth_targets = wf["connections"].get("Get Auth Token", {}).get("main", [[]])[0]
    wf["connections"]["Get Auth Token"]["main"][0] = [
        t for t in auth_targets if t["node"] not in ("Fetch Open Opps", "Parse Opps CSV")
    ]

    # Update matching code
    for node in wf["nodes"]:
        if node["name"] == "Match Users to Meetings":
            node["parameters"]["jsCode"] = SIMPLE_MATCH_CODE
            print("  Updated Match Users to Meetings (simplified)")
            break

    print(f"  Final nodes: {len(wf['nodes'])}")

    # Push
    payload = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
               "settings": wf.get("settings", {}), "staticData": wf.get("staticData")}
    resp = requests.put(f"{N8N_BASE_URL}/api/v1/workflows/{CRON_ID}", headers=HEADERS, json=payload)
    resp.raise_for_status()
    result = resp.json()
    print(f"\n=== Pushed: {len(result['nodes'])} nodes ===")

    # Sync local
    resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{CRON_ID}", headers=HEADERS)
    resp.raise_for_status()
    path = os.path.join(REPO_ROOT, "n8n", "workflows", "Meeting Prep Cron.json")
    with open(path, "w") as f:
        json.dump(resp.json(), f, indent=4)
    print(f"  Synced {path}")
    print("\nDone!")


if __name__ == "__main__":
    main()
