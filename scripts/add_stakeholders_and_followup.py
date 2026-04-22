#!/usr/bin/env python3
"""
Add `stakeholders` and `followup` keyword commands to the Events Handler.

Both commands route through the existing DM conversation agent flow
with specialized system prompts. No new nodes needed — just code
changes to 4 existing nodes:

1. Route by State — add keywords (exact + fuzzy matching)
2. Is Conversational? — expand condition to pass new subRoutes to agent
3. Build DM System Prompt — add stakeholder/followup prompt variants
4. Build Help Response — add help text + more_help details

Also creates migration 007_followup_config.sql for the followup_delay_minutes column.
"""

import json
import os
import uuid
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

EVENTS_HANDLER_ID = "QuQbIaWetunUOFUW"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}


def uid():
    return str(uuid.uuid4())


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
    return None


# ═══════════════════════════════════════════════════════════════════
# 1. Route by State — add stakeholders + followup keywords
# ═══════════════════════════════════════════════════════════════════

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
  else if (lower === 'stakeholders' || lower.startsWith('stakeholders ')) {
    route = 'cmd_other'; subRoute = 'stakeholders';
  }
  else if (lower === 'followup' || lower.startsWith('followup ') || lower.startsWith('follow-up ') || lower.startsWith('follow up ')) {
    route = 'cmd_other'; subRoute = 'followup';
  }
  else if (lower.startsWith('more ') || (lower.startsWith('help ') && lower !== 'help')) {
    route = 'cmd_other'; subRoute = 'more_help';
  } else {
    // --- Pass 2: Fuzzy keyword matching (keyword anywhere in text) ---
    if (/\b(presentation|slide|slides|deck)\b/.test(lower)) route = 'cmd_presentation';
    else if (/\b(business\s+review)\b/.test(lower)) route = 'cmd_bbr';
    else if (/\b(brief|briefing|digest)\b/.test(lower)) route = 'cmd_brief';
    else if (/\binsights?\b/.test(lower)) route = 'cmd_insights';
    else if (/\b(stakeholder|stakeholders|who\s+(should|am|are)\s+I?\s*(be\s+)?talk)/i.test(lower)) {
      route = 'cmd_other'; subRoute = 'stakeholders';
    }
    else if (/\b(follow[\s-]?up|draft\s+(a\s+)?(email|message|note))\b/i.test(lower)) {
      route = 'cmd_other'; subRoute = 'followup';
    }
    else {
      // --- Pass 3: Meta commands and fallback ---
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


# ═══════════════════════════════════════════════════════════════════
# 3. Build DM System Prompt — add stakeholder/followup variants
# ═══════════════════════════════════════════════════════════════════

BUILD_DM_SYSTEM_PROMPT_CODE = r"""const routeData = $('Route by State').first().json;
const user = routeData.userRecord || {};

const assistantName = routeData.assistantName || 'Aria';
const assistantEmoji = routeData.assistantEmoji || ':robot_face:';
const assistantPersona = (user.assistant_persona) || 'direct, action-oriented, conversational';
const repName = user.name || 'there';
const subRoute = routeData.subRoute || 'unrecognized';

// ── Common footer: available commands (only mentioned when relevant) ──
const commandsBlock = [
  '',
  '**AVAILABLE COMMANDS:**',
  'If the user seems to be asking about any of the following, let them know they can use these commands by typing them directly in this DM:',
  '',
  '_Workflow triggers:_',
  '- `presentation <topic> for <account>` — create a presentation',
  '- `bbr <account>` or `pbr <account>` — generate a Business Review presentation',
  '- `brief` — get an on-demand sales digest (also: `brief risk`, `brief momentum`)',
  '- `insights` — pipeline intelligence analysis (also: `insights stalled`, `insights risk`)',
  '- `stakeholders <account>` — stakeholder map and engagement analysis',
  '- `followup <account>` — draft a follow-up email after a meeting',
  '',
  '_Settings:_',
  '- `rename <name>` — change assistant name',
  '- `emoji <emoji>` — change assistant emoji',
  '- `persona <description>` — change assistant personality',
  '- `scope my_deals|team_deals|top_pipeline` — change briefing scope',
  '- `focus retention|revenue|technical|executive` — change digest focus area',
  '- `stop digest` / `resume digest` — toggle morning briefings',
  '- `help` — see the full command list',
  '',
  'Only mention these commands if they are relevant to what the user is asking about. Do not list all commands unprompted.',
].join('\n');

let systemPrompt;

if (subRoute === 'stakeholders') {
  // ── Stakeholder-focused prompt ──
  systemPrompt = [
    'You are ' + assistantName + ', a personal sales assistant for ' + repName + '.',
    '',
    'Your personality: ' + assistantPersona,
    '',
    'You have access to Backstory MCP tools which give you CRM data, account activity, engagement scores, and contact information.',
    '',
    '**STAKEHOLDER ANALYSIS MODE**',
    '',
    'The user wants a stakeholder analysis. Use Backstory MCP tools to:',
    '1. Find the account and its key contacts/people engaged',
    '2. Check engagement history for each contact (last activity date, type, frequency)',
    '3. Identify engagement trends (rising, steady, declining, silent)',
    '4. Spot coverage gaps (missing roles like exec sponsor, procurement, technical lead)',
    '',
    '**FORMAT YOUR RESPONSE like this (Slack mrkdwn):**',
    '',
    ':mag: *Stakeholder Map — {Account Name}*',
    '',
    '*Active Contacts:*',
    '• *Name* — Role — Last: {type} on {date} — :chart_with_upwards_trend: Rising',
    '',
    '*Gone Quiet:*',
    '• *Name* — Role — Last: {type} on {date} — :warning: {N} days silent',
    '',
    '*Coverage Gaps:*',
    '• Any notable missing roles or under-engaged titles',
    '',
    '*Recommendation:*',
    'One specific, actionable suggestion for who to re-engage and why.',
    '',
    '**RULES:**',
    '- Use Slack formatting: *bold*, _italic_, `code`',
    '- Use emoji indicators: :chart_with_upwards_trend: (rising), :arrow_right: (steady), :chart_with_downwards_trend: (declining), :warning: (quiet 10+ days), :red_circle: (silent 21+ days)',
    '- Keep total response under 3000 characters',
    '- Do NOT use ### headers — use *bold* for section titles',
    '- If the account is not found, say so clearly',
    '- If no specific account is mentioned, ask the user which account they want to analyze',
    commandsBlock,
  ].join('\n');

} else if (subRoute === 'followup') {
  // ── Follow-up email draft prompt ──
  systemPrompt = [
    'You are ' + assistantName + ', a personal sales assistant for ' + repName + '.',
    '',
    'Your personality: ' + assistantPersona,
    '',
    'You have access to Backstory MCP tools which give you CRM data, account activity, meeting details, and engagement data.',
    '',
    '**FOLLOW-UP EMAIL DRAFT MODE**',
    '',
    'The user wants to draft a follow-up email. Use Backstory MCP tools to:',
    '1. Find the most recent meeting with the mentioned account',
    '2. Get meeting participants and their roles',
    '3. Check current deal status, stage, and next steps',
    '4. Review recent engagement context',
    '',
    '**FORMAT YOUR RESPONSE like this (Slack mrkdwn):**',
    '',
    ':email: *Follow-up Draft — {Account Name}*',
    '',
    '*To:* {primary recipient(s)}',
    '*Subject:* {concise subject line}',
    '',
    '---',
    '{email body — professional, concise, references specific discussion points}',
    '---',
    '',
    '_Reply in this thread to adjust the tone, add details, or ask me to revise._',
    '',
    '**RULES:**',
    '- Draft should be 150-250 words — concise and professional',
    '- Reference specific topics from the meeting if available',
    '- Include a clear next step or call to action',
    '- Match the tone to ' + repName + "'s communication style if you have context",
    '- Use the account contact names, not generic "team"',
    '- If no specific account/meeting is found, ask the user for details',
    '- Keep the Slack message under 3000 characters total',
    '- Do NOT use ### headers — use *bold* for labels',
    commandsBlock,
  ].join('\n');

} else {
  // ── General DM conversation prompt (existing behavior) ──
  systemPrompt = [
    'You are ' + assistantName + ', a personal sales assistant for ' + repName + '. You work exclusively for them.',
    '',
    'Your personality: ' + assistantPersona,
    '',
    'You have access to Backstory MCP tools which give you CRM data, account activity, opportunity details, engagement scores, and communication summaries.',
    '',
    '**INSTRUCTIONS:**',
    '- Use the Backstory MCP tools to answer the user\'s question with real data.',
    '- Be concise and actionable — this response will be posted in Slack.',
    '- Format your response using Slack markdown: *bold*, _italic_, `code`.',
    '- Use bullet points sparingly and keep them short.',
    '- If the question is about a specific account or opportunity, include key metrics (engagement level, amount, stage, etc.).',
    '- If you can\'t find the requested data, say so clearly rather than guessing.',
    '- Keep your total response under 3000 characters so it displays well in Slack.',
    '- Do NOT use headers with ### or ** section headers ** — just use *bold* for emphasis.',
    '- End with a brief actionable recommendation when relevant.',
    commandsBlock,
  ].join('\n');
}

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


# ═══════════════════════════════════════════════════════════════════
# 4. Build Help Response — add help text for new commands
# ═══════════════════════════════════════════════════════════════════

BUILD_HELP_CODE = r"""const data = $('Route by State').first().json;
let text = '';
const r = data.subRoute;
const name = data.assistantName || 'Your Assistant';
const emoji = data.assistantEmoji || ':robot_face:';

if (r === 'help') {
  // --- Conversation-first help ---
  text = "*Just ask me anything* \u2014 I have access to your Backstory CRM data and can answer questions about accounts, deals, engagement, and pipeline.\n\n" +
    "Try things like:\n" +
    "\u2022 _\"What's happening with AMD?\"_\n" +
    "\u2022 _\"Who should I be talking to at Cisco?\"_\n" +
    "\u2022 _\"Draft a follow-up for my Intel meeting\"_\n" +
    "\u2022 _\"I need a presentation on Q1 results\"_\n\n" +
    ":thread: Reply in a thread to keep the conversation going.\n\n" +
    "*Shortcuts:*\n" +
    "`brief` \u00b7 `insights` \u00b7 `presentation` \u00b7 `bbr` \u00b7 `stakeholders` \u00b7 `followup`\n" +
    "`rename` \u00b7 `emoji` \u00b7 `persona` \u00b7 `scope` \u00b7 `focus`\n\n" +
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
      "I'll pull data from Backstory and build the slides. Takes about 2 minutes.\n\n" +
      "_Or just ask naturally: \"I need a presentation on MCP for AMD\"_",

    'bbr': "*`bbr` \u2014 Business Review Presentation*\n\n" +
      "Generate a complete Backstory Business Review (BBR) deck for a customer account.\n\n" +
      "*Usage:*\n" +
      "\u2022 `bbr AMD`\n" +
      "\u2022 `pbr Cisco` (same thing)\n\n" +
      "Includes: engagement scores, open opps, key contacts, activity trends, adoption signals, and a roadmap placeholder.\n\n" +
      "_Or just ask naturally: \"create a business review for AMD\"_",

    'stakeholders': "*`stakeholders` \u2014 Stakeholder Map*\n\n" +
      "See who you're engaging at an account, who's gone quiet, and where you have coverage gaps.\n\n" +
      "*Usage:*\n" +
      "\u2022 `stakeholders AMD`\n" +
      "\u2022 `stakeholders Cisco`\n\n" +
      "Shows: active contacts with engagement trends, silent contacts, missing roles, and a recommendation for who to re-engage.\n\n" +
      "_Or just ask naturally: \"who should I be talking to at AMD?\"_",

    'followup': "*`followup` \u2014 Draft Follow-up Email*\n\n" +
      "Draft a follow-up email after a customer meeting.\n\n" +
      "*Usage:*\n" +
      "\u2022 `followup AMD`\n" +
      "\u2022 `followup Cisco`\n" +
      "\u2022 `follow-up Intel`\n\n" +
      "I'll find your most recent meeting with the account, check the deal context, and draft a professional follow-up with next steps.\n\n" +
      "_Or just ask naturally: \"draft a follow-up for my AMD meeting\"_",

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
  const aliases = { 'pbr': 'bbr', 'digest': 'brief', 'briefing': 'brief', 'slide': 'presentation', 'slides': 'presentation', 'deck': 'presentation', 'name': 'rename', 'icon': 'emoji', 'follow-up': 'followup', 'contacts': 'stakeholders', 'people': 'stakeholders' };
  const resolved = aliases[target] || target;

  if (details[resolved]) {
    text = details[resolved];
  } else {
    text = "I don't have detailed help for `" + target + "`.\n\n" +
      "Available shortcuts: `brief` \u00b7 `insights` \u00b7 `presentation` \u00b7 `bbr` \u00b7 `stakeholders` \u00b7 `followup` \u00b7 `rename` \u00b7 `emoji` \u00b7 `persona` \u00b7 `scope` \u00b7 `focus`\n\n" +
      "Type `more <shortcut>` for details on any of these.";
  }

} else if (r === 'stop_digest') {
  text = "Understood. I\u2019ve paused your morning briefings.\n\nI\u2019ll still prep you before meetings and flag urgent risks. Just type `resume digest` whenever you want them back.";
} else if (r === 'resume_digest') {
  text = "Morning briefings are back on. You\u2019ll get the next one tomorrow at 6am.";
} else {
  text = "I didn\u2019t catch that. You can ask me anything about your accounts and deals, or try:\n\n" +
    "`brief` \u00b7 `insights` \u00b7 `presentation` \u00b7 `stakeholders` \u00b7 `followup` \u00b7 `help`";
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

    # ── 1. Update Route by State ──────────────────────────────────────
    route_node = find_node(nodes, "Route by State")
    if not route_node:
        print("ERROR: 'Route by State' not found!")
        return
    if "stakeholders" in route_node["parameters"]["jsCode"]:
        print("  Route by State: stakeholders already present — skipping")
    else:
        route_node["parameters"]["jsCode"] = ROUTE_BY_STATE_CODE
        print("  Updated 'Route by State' with stakeholders + followup keywords")
        changes += 1

    # ── 2. Update Is Conversational? IF node ──────────────────────────
    conv_node = find_node(nodes, "Is Conversational?")
    if not conv_node:
        print("ERROR: 'Is Conversational?' not found!")
        return

    # Change from: subRoute === "unrecognized" → agent
    # To: subRoute NOT IN (help, more_help, stop_digest, resume_digest) → agent
    # Using 4 conditions with AND combinator (all must be true to pass to agent)
    current_conditions = conv_node["parameters"]["conditions"]["conditions"]
    if len(current_conditions) > 1:
        print("  Is Conversational?: already has multiple conditions — skipping")
    else:
        conv_node["parameters"]["conditions"] = {
            "options": {
                "version": 2,
                "leftValue": "",
                "caseSensitive": True,
                "typeValidation": "strict",
            },
            "conditions": [
                {
                    "id": uid(),
                    "leftValue": "={{ $json.subRoute }}",
                    "rightValue": "help",
                    "operator": {"type": "string", "operation": "notEquals"},
                },
                {
                    "id": uid(),
                    "leftValue": "={{ $json.subRoute }}",
                    "rightValue": "more_help",
                    "operator": {"type": "string", "operation": "notEquals"},
                },
                {
                    "id": uid(),
                    "leftValue": "={{ $json.subRoute }}",
                    "rightValue": "stop_digest",
                    "operator": {"type": "string", "operation": "notEquals"},
                },
                {
                    "id": uid(),
                    "leftValue": "={{ $json.subRoute }}",
                    "rightValue": "resume_digest",
                    "operator": {"type": "string", "operation": "notEquals"},
                },
            ],
            "combinator": "and",
        }
        print("  Updated 'Is Conversational?' — now passes stakeholders/followup/unrecognized to agent")
        changes += 1

    # ── 3. Update Build DM System Prompt ──────────────────────────────
    prompt_node = find_node(nodes, "Build DM System Prompt")
    if not prompt_node:
        print("ERROR: 'Build DM System Prompt' not found!")
        return
    if "STAKEHOLDER ANALYSIS MODE" in prompt_node["parameters"]["jsCode"]:
        print("  Build DM System Prompt: already has stakeholder prompt — skipping")
    else:
        prompt_node["parameters"]["jsCode"] = BUILD_DM_SYSTEM_PROMPT_CODE
        print("  Updated 'Build DM System Prompt' with stakeholder + followup prompt variants")
        changes += 1

    # ── 4. Update Build Help Response ─────────────────────────────────
    help_node = find_node(nodes, "Build Help Response")
    if not help_node:
        print("ERROR: 'Build Help Response' not found!")
        return
    if "'stakeholders'" in help_node["parameters"]["jsCode"]:
        print("  Build Help Response: already has stakeholders help — skipping")
    else:
        help_node["parameters"]["jsCode"] = BUILD_HELP_CODE
        print("  Updated 'Build Help Response' with stakeholders + followup help text")
        changes += 1

    if changes == 0:
        print("\n  No changes needed")
        return

    # ── Push ──────────────────────────────────────────────────────────
    print(f"\n=== Pushing workflow ({changes} nodes updated) ===")
    result = push_workflow(EVENTS_HANDLER_ID, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")

    # ── Sync ──────────────────────────────────────────────────────────
    print("\n=== Re-fetching and syncing local file ===")
    final = fetch_workflow(EVENTS_HANDLER_ID)
    sync_local(final, "Slack Events Handler.json")

    print(f"\nDone! Stakeholders + Follow-up commands added:")
    print("  - `stakeholders <account>` → stakeholder engagement analysis")
    print("  - `followup <account>` → draft follow-up email")
    print("  - Fuzzy: 'who should I talk to at AMD', 'draft a follow-up for Cisco'")
    print("  - `more stakeholders` / `more followup` → detailed help")
    print("  - `help` updated with new commands")


if __name__ == "__main__":
    main()
