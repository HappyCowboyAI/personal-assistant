#!/usr/bin/env python3
"""
Update help system to be conversation-first with detailed shortcut help.

Changes:
1. Route by State: Add `more <keyword>` and `help <keyword>` detection → subRoute: 'more_help'
2. Build Help Response:
   - `help` → conversation-first overview with compact shortcuts
   - `more <shortcut>` / `help <shortcut>` → detailed explanation with examples
   - Updated "unrecognized" fallback to mention conversational ability
"""

import json
import os
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

EVENTS_HANDLER_ID = "QuQbIaWetunUOFUW"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}


def fetch_workflow(wf_id):
    resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def push_workflow(wf_id, wf):
    payload = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": wf.get("settings", {}),
        "staticData": wf.get("staticData"),
    }
    resp = requests.put(
        f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}", headers=HEADERS, json=payload
    )
    resp.raise_for_status()
    return resp.json()


def sync_local(wf, filename):
    path = os.path.join(REPO_ROOT, "n8n", "workflows", filename)
    with open(path, "w") as f:
        json.dump(wf, f, indent=4)
    print(f"  Synced {path}")


def find_node(nodes, name):
    for n in nodes:
        if n["name"] == name:
            return n
    raise ValueError(f"Node '{name}' not found")


# --- Updated Route by State: adds 'more <keyword>' and 'help <keyword>' detection ---
ROUTE_BY_STATE_CODE = r"""const event = $('Extract Event Data').first().json;
const user = $('Lookup User').first().json;
const text = event.text;
const userId = event.userId;

// app_home_opened — always publish the home view regardless of onboarding state
if (event.eventType === 'app_home_opened') {
  const assistantName = (user && user.assistant_name) ? user.assistant_name : 'Aria';
  const assistantEmoji = (user && user.assistant_emoji) ? user.assistant_emoji : ':robot_face:';
  return [{
    json: {
      route: 'app_home_opened',
      subRoute: null,
      userId,
      channelId: null,
      teamId: event.teamId,
      userRecord: (user && user.id) ? user : null,
      dbUserId: (user && user.id) ? user.id : null,
      organizationId: (user && user.organization_id) ? user.organization_id : null,
      assistantName,
      assistantEmoji,
      state: (user && user.onboarding_state) ? user.onboarding_state : null
    }
  }];
}

let userExists = !!(user && user.id);
let state = userExists ? (user.onboarding_state || 'new') : null;
let route = 'unknown';
let subRoute = 'help';

if (!userExists) {
  route = 'new_user';
} else if (state === 'new') {
  route = 'send_greeting';
} else if (state === 'awaiting_name') {
  route = 'capture_name';
} else if (state === 'awaiting_emoji') {
  route = 'capture_emoji';
} else if (state === 'complete') {
  const lower = text.toLowerCase();

  // --- Pass 1: Exact command matching (keyword at start of text) ---
  if (lower.startsWith('rename ')) route = 'cmd_rename';
  else if (lower.startsWith('emoji ')) route = 'cmd_emoji';
  else if (lower.startsWith('persona ')) route = 'cmd_persona';
  else if (lower === 'scope' || lower.startsWith('scope ')) route = 'cmd_scope';
  else if (lower === 'focus' || lower.startsWith('focus ')) route = 'cmd_focus';
  else if (lower === 'brief' || lower.startsWith('brief ')) route = 'cmd_brief';
  else if (lower === 'insights' || lower.startsWith('insights ')) route = 'cmd_insights';
  else if (/\b(bbr|pbr)\b/i.test(lower)) route = 'cmd_bbr';
  else if (lower === 'presentation' || lower.startsWith('presentation ')) route = 'cmd_presentation';
  else {
    // --- Pass 2: Fuzzy keyword matching (keyword anywhere in text) ---
    if (/\b(presentation|slide|slides|deck)\b/.test(lower)) route = 'cmd_presentation';
    else if (/\b(business\s+review)\b/.test(lower)) route = 'cmd_bbr';
    else if (/\b(brief|briefing|digest)\b/.test(lower)) route = 'cmd_brief';
    else if (/\binsights?\b/.test(lower)) route = 'cmd_insights';
    else {
      // --- Pass 3: Meta commands and fallback ---
      route = 'cmd_other';
      if (lower === 'stop digest' || lower === 'pause digest') subRoute = 'stop_digest';
      else if (lower === 'resume digest' || lower === 'start digest') subRoute = 'resume_digest';
      else if (lower === 'help') subRoute = 'help';
      else if (lower.startsWith('more ') || lower.startsWith('help ')) subRoute = 'more_help';
      else subRoute = 'unrecognized';
    }
  }
}

let assistantName = (userExists && user.assistant_name) ? user.assistant_name : 'Your Assistant';
let assistantEmoji = (userExists && user.assistant_emoji) ? user.assistant_emoji : ':robot_face:';

return [{
  json: {
    route, subRoute, userId, text,
    channelId: event.channelId,
    teamId: event.teamId,
    userRecord: userExists ? user : null,
    dbUserId: userExists ? user.id : null,
    organizationId: userExists ? user.organization_id : null,
    assistantName, assistantEmoji, state
  }
}];
"""

# --- Updated Build Help Response ---
BUILD_HELP_CODE = r"""const data = $('Route by State').first().json;
let text = '';
const r = data.subRoute;
const name = data.assistantName || 'Your Assistant';
const emoji = data.assistantEmoji || ':robot_face:';

if (r === 'help') {
  // --- Conversation-first help ---
  text = "*Just ask me anything* \u2014 I have access to your People.ai CRM data and can answer questions about accounts, deals, engagement, and pipeline.\n\n" +
    "Try things like:\n" +
    "\u2022 _\"What's happening with AMD?\"_\n" +
    "\u2022 _\"Which deals are at risk?\"_\n" +
    "\u2022 _\"I need a presentation on Q1 results for Cisco\"_\n\n" +
    ":thread: Reply in a thread to keep the conversation going.\n\n" +
    "*Shortcuts:*\n" +
    "`brief` \u00b7 `insights` \u00b7 `presentation` \u00b7 `bbr` \u00b7 `rename` \u00b7 `emoji` \u00b7 `persona` \u00b7 `scope` \u00b7 `focus`\n\n" +
    "Type `more <shortcut>` for details on any command (e.g. `more brief`).";

} else if (r === 'more_help') {
  // --- Detailed help for a specific shortcut ---
  const target = (data.text || '').toLowerCase().replace(/^(more|help)\s+/, '').trim();

  const details = {
    'brief': "*`brief` \u2014 On-Demand Sales Digest*\n\n" +
      "Get an instant sales briefing, just like your morning digest.\n\n" +
      "*Usage:*\n" +
      "\u2022 `brief` \u2014 today's themed digest\n" +
      "\u2022 `brief risk` \u2014 deals that need attention\n" +
      "\u2022 `brief momentum` \u2014 deals picking up speed\n" +
      "\u2022 `brief engagement` \u2014 engagement shifts\n" +
      "\u2022 `brief full` \u2014 full pipeline review\n" +
      "\u2022 `brief review` \u2014 weekly recap\n\n" +
      "You can also use day names: `brief monday`, `brief friday`\n\n" +
      "_Or just ask naturally: \"give me a briefing on at-risk deals\"_",

    'insights': "*`insights` \u2014 Pipeline Intelligence*\n\n" +
      "Deep analysis of your pipeline with actionable recommendations.\n\n" +
      "*Usage:*\n" +
      "\u2022 `insights` \u2014 full pipeline analysis\n" +
      "\u2022 `insights stalled` \u2014 deals that have gone quiet\n" +
      "\u2022 `insights risk` \u2014 deals showing warning signs\n" +
      "\u2022 `insights hidden` \u2014 ghost opportunities\n" +
      "\u2022 `insights accelerating` \u2014 fast-moving deals\n\n" +
      "_Or just ask naturally: \"show me insights on stalled deals\"_",

    'presentation': "*`presentation` \u2014 Create a Presentation*\n\n" +
      "Generate a Backstory-branded Google Slides deck on any topic.\n\n" +
      "*Usage:*\n" +
      "\u2022 `presentation Q1 engineering review for Cisco`\n" +
      "\u2022 `presentation competitive landscape for AMD`\n" +
      "\u2022 `presentation onboarding progress for Acme`\n\n" +
      "I'll pull data from People.ai and build the slides. Takes about 2 minutes.\n\n" +
      "_Or just ask naturally: \"I need a presentation on MCP for AMD\"_",

    'bbr': "*`bbr` \u2014 Business Review Presentation*\n\n" +
      "Generate a complete Backstory Business Review (BBR) deck for a customer account.\n\n" +
      "*Usage:*\n" +
      "\u2022 `bbr AMD`\n" +
      "\u2022 `pbr Cisco` (same thing)\n\n" +
      "Includes: engagement scores, open opps, key contacts, activity trends, adoption signals, and a roadmap placeholder.\n\n" +
      "_Or just ask naturally: \"create a business review for AMD\"_",

    'rename': "*`rename` \u2014 Change My Name*\n\n" +
      "Give me a new name that appears on all my messages.\n\n" +
      "*Usage:*\n" +
      "\u2022 `rename Luna`\n" +
      "\u2022 `rename ScottAI`\n" +
      "\u2022 `rename Jarvis`",

    'emoji': "*`emoji` \u2014 Change My Icon*\n\n" +
      "Pick a Slack emoji that appears next to my name.\n\n" +
      "*Usage:*\n" +
      "\u2022 `emoji :rocket:`\n" +
      "\u2022 `emoji :star:`\n" +
      "\u2022 `emoji :brain:`",

    'persona': "*`persona` \u2014 Change My Personality*\n\n" +
      "Adjust how I communicate with you.\n\n" +
      "*Usage:*\n" +
      "\u2022 `persona friendly and uses sports metaphors`\n" +
      "\u2022 `persona formal and data-driven`\n" +
      "\u2022 `persona witty and casual`\n" +
      "\u2022 `persona short responses for busy professionals`",

    'scope': "*`scope` \u2014 Change Briefing Scope*\n\n" +
      "Control whose deals appear in your morning digest.\n\n" +
      "*Usage:*\n" +
      "\u2022 `scope my_deals` \u2014 just your own opportunities (IC mode)\n" +
      "\u2022 `scope team_deals` \u2014 your direct reports' deals (Manager mode)\n" +
      "\u2022 `scope top_pipeline` \u2014 top pipeline deals across the org (Exec mode)",

    'focus': "*`focus` \u2014 Set Digest Focus Area*\n\n" +
      "Prioritize a specific area in your morning briefings.\n\n" +
      "*Usage:*\n" +
      "\u2022 `focus retention` \u2014 renewals and churn risk\n" +
      "\u2022 `focus revenue` \u2014 pipeline and revenue targets\n" +
      "\u2022 `focus technical` \u2014 technical adoption signals\n" +
      "\u2022 `focus executive` \u2014 strategic overview",
  };

  // Also accept aliases
  const aliases = { 'pbr': 'bbr', 'digest': 'brief', 'briefing': 'brief', 'slide': 'presentation', 'slides': 'presentation', 'deck': 'presentation', 'name': 'rename', 'icon': 'emoji' };
  const resolved = aliases[target] || target;

  if (details[resolved]) {
    text = details[resolved];
  } else {
    text = "I don't have detailed help for `" + target + "`.\n\n" +
      "Available shortcuts: `brief` \u00b7 `insights` \u00b7 `presentation` \u00b7 `bbr` \u00b7 `rename` \u00b7 `emoji` \u00b7 `persona` \u00b7 `scope` \u00b7 `focus`\n\n" +
      "Type `more <shortcut>` for details on any of these.";
  }

} else if (r === 'stop_digest') {
  text = "Understood. I\u2019ve paused your morning briefings.\n\nI\u2019ll still prep you before meetings and flag urgent risks. Just type `resume digest` whenever you want them back.";
} else if (r === 'resume_digest') {
  text = "Morning briefings are back on. You\u2019ll get the next one tomorrow at 6am.";
} else {
  // Unrecognized — shouldn't normally reach here since unrecognized goes to agent,
  // but keep as safety net
  text = "I didn\u2019t catch that. You can ask me anything about your accounts and deals, or try:\n\n" +
    "`brief` \u00b7 `insights` \u00b7 `presentation` \u00b7 `help`";
}

const needsUpdate = (r === 'stop_digest' || r === 'resume_digest');
const digestEnabled = (r === 'resume_digest');

return [{ json: { ...data, responseText: text, needsUpdate, digestEnabled } }];
"""


def main():
    print("Fetching Slack Events Handler workflow (live)...")
    wf = fetch_workflow(EVENTS_HANDLER_ID)
    nodes = wf["nodes"]
    print(f"  {len(nodes)} nodes")

    changes = 0

    # --- 1. Update Route by State ---
    route_node = find_node(nodes, "Route by State")
    if "more_help" in route_node["parameters"]["jsCode"]:
        print("  Route by State: 'more_help' already present — skipping")
    else:
        route_node["parameters"]["jsCode"] = ROUTE_BY_STATE_CODE
        print("  Updated 'Route by State' with 'more <keyword>' detection")
        changes += 1

    # --- 2. Update Build Help Response ---
    help_node = find_node(nodes, "Build Help Response")
    if "more_help" in help_node["parameters"]["jsCode"]:
        print("  Build Help Response: already updated — skipping")
    else:
        help_node["parameters"]["jsCode"] = BUILD_HELP_CODE
        print("  Updated 'Build Help Response' with conversation-first help + detailed shortcuts")
        changes += 1

    if changes == 0:
        print("\n  No changes needed")
        return

    # --- Push ---
    print(f"\n=== Pushing workflow ({changes} nodes updated) ===")
    result = push_workflow(EVENTS_HANDLER_ID, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")

    # --- Sync ---
    print("\n=== Re-fetching and syncing local file ===")
    final = fetch_workflow(EVENTS_HANDLER_ID)
    sync_local(final, "Slack Events Handler.json")

    print("\nDone! Help system updated:")
    print("  - `help` → conversation-first overview")
    print("  - `more <shortcut>` → detailed help (e.g. `more brief`, `more presentation`)")
    print("  - `help <shortcut>` → same as `more <shortcut>`")


if __name__ == "__main__":
    main()
