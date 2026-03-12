#!/usr/bin/env python3
"""
Update App Home visual design:
- Fixes bug: Build Home View was reading Route by State output directly as user
  instead of data.userRecord, causing onboarding_state to always be null
- Redesigns both views to be more compelling with images, fields, and richer layout
- Updates Slack Events Handler + Interactive Events Handler
"""

import json
import os
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

SLACK_EVENTS_ID  = "QuQbIaWetunUOFUW"
INTERACTIVE_ID   = "JgVjCqoT6ZwGuDL1"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}


def fetch_workflow(wf_id):
    resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def push_workflow(wf_id, wf):
    payload = {
        "name": wf["name"], "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": wf.get("settings", {}),
        "staticData": wf.get("staticData"),
    }
    resp = requests.put(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}", headers=HEADERS, json=payload)
    resp.raise_for_status()
    return resp.json()


def sync_local(wf, filename):
    path = os.path.join(REPO_ROOT, "n8n", "workflows", filename)
    with open(path, "w") as f:
        json.dump(wf, f, indent=4)
    print(f"  Synced {path}")


# ── New home view JavaScript (parameterised by which node holds the user record)
# user_node:   name of the Supabase getAll node that returned the user record
# user_id_src: JS expression to get the userId string
# ─────────────────────────────────────────────────────────────────────────────

def home_view_code(user_node, user_id_src):
    return r"""// ── Resolve user and state ────────────────────────────────────────────────────
const data  = $('""" + user_node + r"""').first().json;

// FIX: Route by State returns { userRecord: {...}, state, userId, ... }
// Pull userRecord out; fall back to using data directly if it has 'id' (interactive paths)
const user = (data.userRecord !== undefined) ? data.userRecord
           : (data.id         !== undefined) ? data
           : null;

const userId          = """ + user_id_src + r""";
const onboardingState = (user && user.onboarding_state) ? user.onboarding_state
                      : (data.state || null);
const isComplete      = (onboardingState === 'complete');

const assistantName  = (user && user.assistant_name)  || 'Aria';
const assistantEmoji = (user && user.assistant_emoji) || ':robot_face:';
const avatarUrl      = (user && user.assistant_avatar_url) || null;

// ── Build blocks ──────────────────────────────────────────────────────────────
let blocks = [];

if (!isComplete) {
  // ══ ONBOARDING VIEW ════════════════════════════════════════════════════════

  // Hero image — People.ai logo via Clearbit (change to your own CDN URL if desired)
  blocks.push({
    type: 'image',
    image_url: 'https://logo.clearbit.com/people.ai',
    alt_text: 'People.ai'
  });

  blocks.push({
    type: 'section',
    text: {
      type: 'mrkdwn',
      text: '*Your personal AI sales assistant.*\nI run in the background, watch your deals, and show up with the right intel at exactly the right moment — without you ever having to ask.'
    }
  });

  blocks.push({ type: 'divider' });

  blocks.push({
    type: 'section',
    fields: [
      { type: 'mrkdwn', text: ':sun_small_cloud: *Morning briefings*\nPrioritized 6am digest: what moved, what\'s at risk, what needs your attention today.' },
      { type: 'mrkdwn', text: ':calendar: *Pre-meeting prep*\nFull account brief before every call — stakeholders, activity history, talking points.' },
      { type: 'mrkdwn', text: ':pencil: *Re-engagement drafts*\nWhen deals go quiet, I write the outreach email. You review and send with one click.' },
      { type: 'mrkdwn', text: ':bar_chart: *Pipeline coaching*\nRisk signals, momentum shifts, and deal health — surfaced before they become problems.' }
    ]
  });

  blocks.push({ type: 'divider' });

  blocks.push({
    type: 'section',
    text: {
      type: 'mrkdwn',
      text: '*Ready to set up your assistant?*\nSend me a DM — I\'ll walk you through two quick questions, and your first briefing arrives the next morning at 6am.'
    }
  });

  blocks.push({
    type: 'context',
    elements: [{ type: 'mrkdwn', text: 'Takes about 30 seconds to set up  •  Works with your existing Salesforce + People.ai data' }]
  });

} else {
  // ══ SETTINGS VIEW ══════════════════════════════════════════════════════════

  const persona      = (user && user.assistant_persona) || 'direct, action-oriented, conversational';
  const digestOn     = (user && user.digest_enabled !== undefined) ? user.digest_enabled : true;
  const digestTime   = (user && user.digest_time)    || '06:00:00';
  const timezone     = (user && user.timezone)       || 'America/Los_Angeles';
  const digestScope  = (user && user.digest_scope)   || 'my_deals';

  function formatTime(t) {
    const parts = (t || '06:00:00').split(':');
    let h = parseInt(parts[0] || 0);
    const m = parts[1] || '00';
    const ampm = h >= 12 ? 'PM' : 'AM';
    h = h % 12 || 12;
    return h + ':' + m + ' ' + ampm;
  }

  const scopeLabel = { my_deals: 'My deals (IC)', team_deals: 'Team deals (Manager)', top_pipeline: 'Full pipeline (Exec)' }[digestScope] || digestScope;
  const statusEmoji = digestOn ? ':white_check_mark:' : ':pause_button:';
  const statusText  = digestOn ? 'Active' : 'Paused';
  const toggleLabel = digestOn ? 'Pause Digest' : 'Resume Digest';
  const toggleStyle = digestOn ? 'danger' : 'primary';

  // ── Identity header ──────────────────────────────────────────────────────
  if (avatarUrl) {
    blocks.push({
      type: 'section',
      text: { type: 'mrkdwn', text: '*' + assistantName + '* ' + assistantEmoji + '\n_Your personal AI sales assistant_' },
      accessory: { type: 'image', image_url: avatarUrl, alt_text: assistantName }
    });
  } else {
    blocks.push({
      type: 'section',
      text: { type: 'mrkdwn', text: '*' + assistantName + '* ' + assistantEmoji + '\n_Your personal AI sales assistant_' }
    });
  }

  blocks.push({ type: 'divider' });

  // ── Identity fields ──────────────────────────────────────────────────────
  blocks.push({
    type: 'section',
    fields: [
      { type: 'mrkdwn', text: '*Name*\n' + assistantName },
      { type: 'mrkdwn', text: '*Emoji*\n' + assistantEmoji }
    ]
  });
  blocks.push({
    type: 'actions',
    elements: [
      { type: 'button', text: { type: 'plain_text', text: 'Rename', emoji: true }, action_id: 'edit_name' },
      { type: 'button', text: { type: 'plain_text', text: 'Change Emoji', emoji: true }, action_id: 'edit_emoji' }
    ]
  });

  // ── Persona ──────────────────────────────────────────────────────────────
  blocks.push({
    type: 'section',
    fields: [
      { type: 'mrkdwn', text: '*Persona*\n' + persona }
    ]
  });
  blocks.push({
    type: 'actions',
    elements: [
      { type: 'button', text: { type: 'plain_text', text: 'Edit Persona', emoji: true }, action_id: 'edit_persona' }
    ]
  });

  blocks.push({ type: 'divider' });

  // ── Digest settings ──────────────────────────────────────────────────────
  blocks.push({
    type: 'section',
    text: { type: 'mrkdwn', text: ':newspaper: *Morning Digest*' }
  });
  blocks.push({
    type: 'section',
    fields: [
      { type: 'mrkdwn', text: '*Status*\n' + statusEmoji + ' ' + statusText },
      { type: 'mrkdwn', text: '*Scope*\n' + scopeLabel },
      { type: 'mrkdwn', text: '*Delivery*\n' + formatTime(digestTime) },
      { type: 'mrkdwn', text: '*Timezone*\n' + timezone }
    ]
  });
  blocks.push({
    type: 'actions',
    elements: [
      { type: 'button', text: { type: 'plain_text', text: 'Edit Time', emoji: true }, action_id: 'edit_digest_time' },
      { type: 'button', text: { type: 'plain_text', text: 'Change Scope', emoji: true }, action_id: 'edit_scope' },
      { type: 'button', text: { type: 'plain_text', text: toggleLabel, emoji: true }, action_id: 'toggle_digest', style: toggleStyle }
    ]
  });

  blocks.push({ type: 'divider' });

  blocks.push({
    type: 'context',
    elements: [{ type: 'mrkdwn', text: 'You can also manage settings by typing commands in a DM  •  e.g. _rename Luna_, _persona witty and casual_, _scope team_deals_' }]
  });
}

return [{ json: { userId, homeView: JSON.stringify({ type: 'home', blocks }) } }];"""


# ── Three variants needed ──────────────────────────────────────────────────────
#   1. Events Handler:     data from Route by State, userId from data.userId
#   2. Interactive toggle: data from Refresh User After Toggle, userId from Parse node
#   3. Interactive submit: data from Refresh User (Submission), userId from Parse node

EVENTS_HANDLER_CODE   = home_view_code("Route by State",            "$('Route by State').first().json.userId")
TOGGLE_HOME_CODE       = home_view_code("Refresh User After Toggle", "$('Parse Interactive Payload').first().json.userId")
SUBMISSION_HOME_CODE   = home_view_code("Refresh User (Submission)", "$('Parse Interactive Payload').first().json.userId")


def patch_nodes(wf, patches):
    """patches: {node_name: new_jsCode}"""
    found = set()
    for node in wf["nodes"]:
        if node["name"] in patches:
            node["parameters"]["jsCode"] = patches[node["name"]]
            found.add(node["name"])
            print(f"  Patched: {node['name']}")
    for name in patches:
        if name not in found:
            print(f"  WARNING: node '{name}' not found")
    return wf


def main():
    # ── Update Slack Events Handler ──────────────────────────────────────────
    print("Fetching Slack Events Handler...")
    events_wf = fetch_workflow(SLACK_EVENTS_ID)
    print(f"  {len(events_wf['nodes'])} nodes")

    events_wf = patch_nodes(events_wf, {"Build Home View": EVENTS_HANDLER_CODE})
    result = push_workflow(SLACK_EVENTS_ID, events_wf)
    print(f"  Pushed: {len(result['nodes'])} nodes")
    sync_local(fetch_workflow(SLACK_EVENTS_ID), "Slack Events Handler.json")

    # ── Update Interactive Events Handler ────────────────────────────────────
    print("\nFetching Interactive Events Handler...")
    interactive_wf = fetch_workflow(INTERACTIVE_ID)
    print(f"  {len(interactive_wf['nodes'])} nodes")

    interactive_wf = patch_nodes(interactive_wf, {
        "Build Toggle Home View":     TOGGLE_HOME_CODE,
        "Build Submission Home View": SUBMISSION_HOME_CODE,
    })
    result = push_workflow(INTERACTIVE_ID, interactive_wf)
    print(f"  Pushed: {len(result['nodes'])} nodes")
    sync_local(fetch_workflow(INTERACTIVE_ID), "Interactive Events Handler.json")

    print("\nDone — re-open the App Home tab in Slack to see the updated view.")


if __name__ == "__main__":
    main()
