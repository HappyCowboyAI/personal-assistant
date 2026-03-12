#!/usr/bin/env python3
"""
Add fuzzy keyword matching for workflow-trigger commands in the Events Handler.

Currently, Route by State only matches commands at the start of the text
(e.g., "presentation mcp for amd" works but "I need a presentation on mcp for amd" doesn't).

Changes:
1. Route by State: Add fuzzy regex fallback for presentation, bbr/pbr, brief, insights
   - Exact startsWith checks still run first (fast path)
   - Fuzzy matching only fires for text that didn't match any exact command
2. Parse nodes: Update to strip keywords from anywhere, not just the start
3. DM agent system prompt: Add presentation/bbr commands and stronger guidance
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


# --- Updated Route by State code ---
# Adds fuzzy keyword fallback after exact command matching
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
    // Order matters: check most specific first to avoid conflicts
    // (e.g., "brief presentation" should match presentation, not brief)
    if (/\b(presentation|slide|slides|deck)\b/.test(lower)) route = 'cmd_presentation';
    else if (/\b(business\s+review)\b/.test(lower)) route = 'cmd_bbr';
    else if (/\b(brief|briefing|digest)\b/.test(lower)) route = 'cmd_brief';
    else if (/\binsights?\b/.test(lower)) route = 'cmd_insights';
    else {
      route = 'cmd_other';
      if (lower === 'stop digest' || lower === 'pause digest') subRoute = 'stop_digest';
      else if (lower === 'resume digest' || lower === 'start digest') subRoute = 'resume_digest';
      else if (lower === 'help') subRoute = 'help';
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

# --- Updated Parse Presentation code ---
# Strips presentation keywords from anywhere, not just start
PARSE_PRESENTATION_CODE = r"""const data = $('Route by State').first().json;
const text = (data.text || '').trim();

// Strip presentation-related keywords from anywhere in the text
// to extract the actual prompt/topic
const prompt = text
  .replace(/\b(presentation|slide|slides|deck|create|make|generate|build|give\s+me|i\s+need|can\s+you|please|a|the)\b/gi, ' ')
  .replace(/\s+/g, ' ')
  .trim();

return [{
  json: {
    ...data,
    presentationPrompt: prompt.length > 0 ? text : '',
    isValid: prompt.length > 0,
    responseText: prompt.length > 0 ? '' : data.assistantEmoji + ' Please include a description. Example:\n`presentation Build a Q1 engineering review`'
  }
}];
"""

# --- Updated Parse Brief code ---
# Strips brief keywords from anywhere, not just start
PARSE_BRIEF_CODE = r"""const data = $('Route by State').first().json;
const text = (data.text || '').toLowerCase().trim();

// Strip brief-related keywords from anywhere to find the theme argument
const briefArg = text
  .replace(/\b(brief|briefing|digest|give\s+me|i\s+need|i\s+want|can\s+you|run|get|my|a|the|please)\b/gi, ' ')
  .replace(/\s+/g, ' ')
  .trim();

const themeAliases = {
  'monday': 'full_pipeline', 'mon': 'full_pipeline',
  'tuesday': 'engagement_shifts', 'tue': 'engagement_shifts', 'tues': 'engagement_shifts',
  'wednesday': 'at_risk', 'wed': 'at_risk',
  'thursday': 'momentum', 'thu': 'momentum', 'thurs': 'momentum',
  'friday': 'week_review', 'fri': 'week_review',
  'full': 'full_pipeline', 'pipeline': 'full_pipeline', 'full_pipeline': 'full_pipeline',
  'engagement': 'engagement_shifts', 'engagement_shifts': 'engagement_shifts', 'shifts': 'engagement_shifts',
  'risk': 'at_risk', 'at_risk': 'at_risk', 'atrisk': 'at_risk', 'at-risk': 'at_risk',
  'momentum': 'momentum', 'hot': 'momentum', 'accelerating': 'momentum',
  'review': 'week_review', 'week': 'week_review', 'week_review': 'week_review', 'weekly': 'week_review',
};

const theme = themeAliases[briefArg] || null;
const isValid = true;

return [{
  json: {
    ...data,
    briefTheme: theme,
    briefArg,
    isValid,
    responseText: ''
  }
}];
"""

# --- Updated Parse Insights code ---
# Strips insights keywords from anywhere, not just start
PARSE_INSIGHTS_CODE = r"""const data = $('Route by State').first().json;
const text = (data.text || '').toLowerCase().trim();

// Strip insights-related keywords from anywhere to find the type argument
const insightArg = text
  .replace(/\b(insights?|give\s+me|i\s+need|i\s+want|can\s+you|run|get|show|my|a|the|some|please)\b/gi, ' ')
  .replace(/\s+/g, ' ')
  .trim();

const typeAliases = {
  'stalled': 'stalled', 'stall': 'stalled', 'stuck': 'stalled',
  'risk': 'risk', 'risks': 'risk', 'at-risk': 'risk', 'at risk': 'risk',
  'hidden': 'hidden', 'ghost': 'hidden', 'ghosts': 'hidden',
  'accelerating': 'accelerating', 'accel': 'accelerating', 'fast': 'accelerating', 'hot': 'accelerating',
  'all': 'all', 'everything': 'all', 'full': 'all',
};

const insightType = typeAliases[insightArg] || 'all';

return [{
  json: {
    ...data,
    insightType,
    insightArg,
    isValid: true,
    responseText: ''
  }
}];
"""

# --- Updated DM System Prompt ---
# Adds presentation/bbr commands and stronger guidance
DM_SYSTEM_PROMPT_CODE = r"""const routeData = $('Route by State').first().json;
const user = routeData.userRecord || {};

const assistantName = routeData.assistantName || 'Aria';
const assistantEmoji = routeData.assistantEmoji || ':robot_face:';
const assistantPersona = (user.assistant_persona) || 'direct, action-oriented, conversational';
const repName = user.name || 'there';

const systemPrompt = [
  'You are ' + assistantName + ', a personal sales assistant for ' + repName + '. You work exclusively for them.',
  '',
  'Your personality: ' + assistantPersona,
  '',
  'You have access to People.ai MCP tools which give you CRM data, account activity, opportunity details, engagement scores, and communication summaries.',
  '',
  '**INSTRUCTIONS:**',
  '- Use the People.ai MCP tools to answer the user\'s question with real data.',
  '- Be concise and actionable — this response will be posted in Slack.',
  '- Format your response using Slack markdown: *bold*, _italic_, `code`.',
  '- Use bullet points sparingly and keep them short.',
  '- If the question is about a specific account or opportunity, include key metrics (engagement level, amount, stage, etc.).',
  '- If you can\'t find the requested data, say so clearly rather than guessing.',
  '- Keep your total response under 3000 characters so it displays well in Slack.',
  '- Do NOT use headers with ### or ** section headers ** — just use *bold* for emphasis.',
  '- End with a brief actionable recommendation when relevant.',
  '',
  '**AVAILABLE COMMANDS:**',
  'If the user seems to be asking about any of the following, let them know they can use these commands by typing them directly in this DM:',
  '',
  '_Workflow triggers:_',
  '- `presentation <topic> for <account>` — create a presentation (e.g. `presentation Q1 review for AMD`)',
  '- `bbr <account>` or `pbr <account>` — generate a Business Review presentation',
  '- `brief` — get an on-demand sales digest (also: `brief risk`, `brief momentum`)',
  '- `insights` — pipeline intelligence analysis (also: `insights stalled`, `insights risk`)',
  '',
  '_Settings:_',
  '- `rename <name>` — change assistant name',
  '- `emoji <emoji>` — change assistant emoji (e.g. `emoji :star:`)',
  '- `persona <description>` — change assistant personality',
  '- `scope my_deals|team_deals|top_pipeline` — change briefing scope',
  '- `focus retention|revenue|technical|executive` — change digest focus area',
  '- `stop digest` / `resume digest` — toggle morning briefings',
  '- `help` — see the full command list',
  '',
  'Only mention these commands if they are relevant to what the user is asking about. Do not list all commands unprompted.',
].join('\n');

const thinkingText = assistantEmoji + ' ' + assistantName + '\n\n:hourglass_flowing_sand: Thinking...';

return [{
  json: {
    systemPrompt,
    userMessage: routeData.text,
    channelId: routeData.channelId,
    userId: routeData.userId,
    assistantName,
    assistantEmoji,
    thinkingText,
    dbUserId: routeData.dbUserId,
    organizationId: routeData.organizationId,
  }
}];
"""


def main():
    print("Fetching Slack Events Handler workflow (live)...")
    wf = fetch_workflow(EVENTS_HANDLER_ID)
    nodes = wf["nodes"]
    print(f"  {len(nodes)} nodes")

    changes = 0

    # --- 1. Update Route by State ---
    route_node = find_node(nodes, "Route by State")
    old_code = route_node["parameters"]["jsCode"]
    if "Pass 2: Fuzzy keyword matching" in old_code:
        print("  Route by State: fuzzy matching already present — skipping")
    else:
        route_node["parameters"]["jsCode"] = ROUTE_BY_STATE_CODE
        print("  Updated 'Route by State' with fuzzy keyword matching")
        changes += 1

    # --- 2. Update Parse Presentation ---
    parse_pres = find_node(nodes, "Parse Presentation")
    if "Strip presentation-related keywords from anywhere" in parse_pres["parameters"].get("jsCode", ""):
        print("  Parse Presentation: already updated — skipping")
    else:
        parse_pres["parameters"]["jsCode"] = PARSE_PRESENTATION_CODE
        print("  Updated 'Parse Presentation' for natural language input")
        changes += 1

    # --- 3. Update Parse Brief ---
    parse_brief = find_node(nodes, "Parse Brief")
    if "Strip brief-related keywords from anywhere" in parse_brief["parameters"].get("jsCode", ""):
        print("  Parse Brief: already updated — skipping")
    else:
        parse_brief["parameters"]["jsCode"] = PARSE_BRIEF_CODE
        print("  Updated 'Parse Brief' for natural language input")
        changes += 1

    # --- 4. Update Parse Insights ---
    parse_insights = find_node(nodes, "Parse Insights")
    if "Strip insights-related keywords from anywhere" in parse_insights["parameters"].get("jsCode", ""):
        print("  Parse Insights: already updated — skipping")
    else:
        parse_insights["parameters"]["jsCode"] = PARSE_INSIGHTS_CODE
        print("  Updated 'Parse Insights' for natural language input")
        changes += 1

    # --- 5. Update DM System Prompt ---
    try:
        dm_prompt = find_node(nodes, "Build DM System Prompt")
        if "Workflow triggers:" in dm_prompt["parameters"].get("jsCode", ""):
            print("  Build DM System Prompt: already updated — skipping")
        else:
            dm_prompt["parameters"]["jsCode"] = DM_SYSTEM_PROMPT_CODE
            print("  Updated 'Build DM System Prompt' with presentation/bbr commands")
            changes += 1
    except ValueError:
        print("  Build DM System Prompt: not found (DM conversation not yet added)")

    if changes == 0:
        print("\n  No changes needed — everything already applied")
        return

    # --- Push ---
    print(f"\n=== Pushing workflow ({changes} nodes updated) ===")
    result = push_workflow(EVENTS_HANDLER_ID, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")

    # --- Sync ---
    print("\n=== Re-fetching and syncing local file ===")
    final = fetch_workflow(EVENTS_HANDLER_ID)
    sync_local(final, "Slack Events Handler.json")

    print("\nDone! Fuzzy keyword matching active for: presentation, bbr/pbr, brief, insights")
    print("Natural language like 'I need a presentation on mcp for amd' now routes correctly.")


if __name__ == "__main__":
    main()
