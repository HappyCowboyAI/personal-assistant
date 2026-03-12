#!/usr/bin/env python3
"""
Create App Home page for People.ai Personal Assistant.
- Modifies Slack Events Handler (QuQbIaWetunUOFUW): adds app_home_opened route
- Creates new Interactive Events Handler workflow (~27 nodes)
- Activates the Interactive Events Handler
"""

import json
import os
import uuid
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

SLACK_EVENTS_ID = "QuQbIaWetunUOFUW"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

SLACK_CRED = {"id": "LluVuiMJ8NUbAiG7", "name": "Slackbot Auth Token"}
SUPABASE_CRED = {"id": "ASRWWkQ0RSMOpNF1", "name": "Supabase account"}


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
    resp = requests.put(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}", headers=HEADERS, json=payload)
    resp.raise_for_status()
    return resp.json()


def sync_local(wf, filename):
    path = os.path.join(REPO_ROOT, "n8n", "workflows", filename)
    with open(path, "w") as f:
        json.dump(wf, f, indent=4)
    print(f"  Synced {path}")


def activate_workflow(wf_id):
    resp = requests.post(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}/activate", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


# ── JavaScript code constants ─────────────────────────────────────────────────

EXTRACT_EVENT_DATA_CODE = r"""const body = $('Slack Events Webhook').first().json.body;
const headers = $('Slack Events Webhook').first().json.headers || {};

// Drop Slack retry deliveries — they cause duplicate executions
if (headers['x-slack-retry-num'] && parseInt(headers['x-slack-retry-num']) > 0) {
  return [];
}

const event = body.event || {};

return [{
  json: {
    eventType: event.type,
    channelType: event.channel_type || null,
    userId: event.user,
    channelId: event.channel || null,
    text: (event.text || '').trim(),
    ts: event.ts,
    eventId: body.event_id,
    teamId: body.team_id,
    isBot: !!(event.bot_id || event.subtype),
    tab: event.tab || null
  }
}];"""

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
  if (lower.startsWith('rename ')) route = 'cmd_rename';
  else if (lower.startsWith('emoji ')) route = 'cmd_emoji';
  else if (lower.startsWith('persona ')) route = 'cmd_persona';
  else if (lower === 'scope' || lower.startsWith('scope ')) route = 'cmd_scope';
  else if (lower === 'brief' || lower.startsWith('brief ')) route = 'cmd_brief';
  else if (lower === 'insights' || lower.startsWith('insights ')) route = 'cmd_insights';
  else if (lower === 'presentation' || lower.startsWith('presentation ')) route = 'cmd_presentation';
  else {
    route = 'cmd_other';
    if (lower === 'stop digest' || lower === 'pause digest') subRoute = 'stop_digest';
    else if (lower === 'resume digest' || lower === 'start digest') subRoute = 'resume_digest';
    else if (lower === 'help') subRoute = 'help';
    else subRoute = 'unrecognized';
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
}];"""


def home_view_code(user_node, user_id_expr):
    """Generate Build Home View JavaScript for any context.

    user_node: n8n node name that returns the user record
    user_id_expr: JS expression string for the userId (no surrounding quotes)
    """
    return (
        "const user = $('" + user_node + "').first().json;\n"
        "const userId = " + user_id_expr + ";\n"
        "const onboardingState = user && user.onboarding_state ? user.onboarding_state : null;\n"
        "const isComplete = (onboardingState === 'complete');\n"
        "const assistantName = (user && user.assistant_name) ? user.assistant_name : 'Aria';\n"
        "const assistantEmoji = (user && user.assistant_emoji) ? user.assistant_emoji : ':robot_face:';\n"
        "\n"
        "let blocks = [];\n"
        "\n"
        "if (!isComplete) {\n"
        "  blocks = [\n"
        "    { type: 'header', text: { type: 'plain_text', text: 'Welcome to Your Personal Sales Assistant', emoji: true } },\n"
        "    { type: 'section', text: { type: 'mrkdwn', text: \"I'm an AI assistant that monitors your pipeline and delivers insights without being prompted. Here's what I do:\" } },\n"
        "    { type: 'section', text: { type: 'mrkdwn', text: '*Morning briefings* \\u2014 6am daily digest on your pipeline, prioritized by risk and momentum\\n*Meeting prep* \\u2014 briefing before each customer call with account intel and talking points\\n*Re-engagement drafts* \\u2014 one-click email approval when deals go quiet' } },\n"
        "    { type: 'divider' },\n"
        "    { type: 'section', text: { type: 'mrkdwn', text: '*Complete your setup* \\u2014 Send me a DM to get started. I\\'ll ask you for a name, then your first briefing arrives the next morning.' } }\n"
        "  ];\n"
        "} else {\n"
        "  const persona = (user && user.assistant_persona) ? user.assistant_persona : 'direct, action-oriented, conversational';\n"
        "  const digestEnabled = (user && user.digest_enabled !== undefined) ? user.digest_enabled : true;\n"
        "  const digestTime = (user && user.digest_time) ? user.digest_time : '06:00:00';\n"
        "  const timezone = (user && user.timezone) ? user.timezone : 'America/Los_Angeles';\n"
        "  const digestScope = (user && user.digest_scope) ? user.digest_scope : 'my_deals';\n"
        "\n"
        "  function formatTime(t) {\n"
        "    const parts = t.split(':');\n"
        "    let h = parseInt(parts[0]);\n"
        "    const m = parts[1] || '00';\n"
        "    const ampm = h >= 12 ? 'PM' : 'AM';\n"
        "    h = h % 12 || 12;\n"
        "    return h + ':' + m + ' ' + ampm;\n"
        "  }\n"
        "\n"
        "  const scopeLabels = { 'my_deals': 'My deals (IC)', 'team_deals': 'Team deals (Manager)', 'top_pipeline': 'Full pipeline (Exec)' };\n"
        "  const scopeLabel = scopeLabels[digestScope] || digestScope;\n"
        "  const statusText = digestEnabled ? 'Active' : 'Paused';\n"
        "  const digestStatusText = '*Status:* ' + statusText + '  |  *Time:* ' + formatTime(digestTime) + '  |  *Scope:* ' + scopeLabel;\n"
        "  const toggleLabel = digestEnabled ? 'Pause Digest' : 'Resume Digest';\n"
        "  const toggleStyle = digestEnabled ? 'danger' : 'primary';\n"
        "\n"
        "  blocks = [\n"
        "    { type: 'header', text: { type: 'plain_text', text: assistantName + ' Settings', emoji: true } },\n"
        "    { type: 'divider' },\n"
        "    { type: 'section', text: { type: 'mrkdwn', text: '*Identity*\\nName: *' + assistantName + '*   |   Emoji: ' + assistantEmoji } },\n"
        "    { type: 'actions', elements: [\n"
        "      { type: 'button', text: { type: 'plain_text', text: 'Edit Name', emoji: true }, action_id: 'edit_name' },\n"
        "      { type: 'button', text: { type: 'plain_text', text: 'Edit Emoji', emoji: true }, action_id: 'edit_emoji' }\n"
        "    ]},\n"
        "    { type: 'section', text: { type: 'mrkdwn', text: '*Persona*\\n' + persona } },\n"
        "    { type: 'actions', elements: [\n"
        "      { type: 'button', text: { type: 'plain_text', text: 'Edit Persona', emoji: true }, action_id: 'edit_persona' }\n"
        "    ]},\n"
        "    { type: 'divider' },\n"
        "    { type: 'section', text: { type: 'mrkdwn', text: '*Morning Digest*\\n' + digestStatusText } },\n"
        "    { type: 'actions', elements: [\n"
        "      { type: 'button', text: { type: 'plain_text', text: 'Edit Time', emoji: true }, action_id: 'edit_digest_time' },\n"
        "      { type: 'button', text: { type: 'plain_text', text: 'Change Scope', emoji: true }, action_id: 'edit_scope' },\n"
        "      { type: 'button', text: { type: 'plain_text', text: toggleLabel, emoji: true }, action_id: 'toggle_digest', style: toggleStyle }\n"
        "    ]},\n"
        "    { type: 'divider' },\n"
        "    { type: 'context', elements: [{ type: 'mrkdwn', text: 'Timezone: ' + timezone + '   \\u2022   Send me a DM to manage your assistant' }] }\n"
        "  ];\n"
        "}\n"
        "\n"
        "return [{ json: { userId, homeView: JSON.stringify({ type: 'home', blocks: blocks }) } }];"
    )


BUILD_HOME_VIEW_CODE = home_view_code(
    "Route by State",
    "$('Route by State').first().json.userId"
)

BUILD_TOGGLE_HOME_VIEW_CODE = home_view_code(
    "Refresh User After Toggle",
    "$('Parse Interactive Payload').first().json.userId"
)

BUILD_SUBMISSION_HOME_VIEW_CODE = home_view_code(
    "Refresh User (Submission)",
    "$('Parse Interactive Payload').first().json.userId"
)

PARSE_PAYLOAD_CODE = r"""const body = $('Interactive Webhook').first().json.body;

// Slack sends payload as URL-encoded form: payload=<json string>
// n8n auto-parses URL-encoded bodies, so body.payload is already decoded
let rawPayload = body.payload;
if (typeof rawPayload !== 'string') {
  rawPayload = JSON.stringify(rawPayload);
}

const payload = JSON.parse(rawPayload);

const type = payload.type;
const userId = (payload.user && payload.user.id) ? payload.user.id : null;
const triggerId = payload.trigger_id || null;

// For block_actions
const actions = payload.actions || [];
const actionId = (actions[0] && actions[0].action_id) ? actions[0].action_id : null;

// For view_submission
const callbackId = (payload.view && payload.view.callback_id) ? payload.view.callback_id : null;
const viewStateValues = (payload.view && payload.view.state && payload.view.state.values)
  ? payload.view.state.values : {};

// Flatten state.values: { block_id: { action_id: { type, value } } } → { action_id: value }
const submittedValues = {};
for (const blockId of Object.keys(viewStateValues)) {
  const actions = viewStateValues[blockId];
  for (const aId of Object.keys(actions)) {
    const el = actions[aId];
    if (el.type === 'plain_text_input') {
      submittedValues[aId] = el.value || '';
    } else if (el.type === 'radio_buttons') {
      submittedValues[aId] = el.selected_option ? el.selected_option.value : null;
    }
  }
}

return [{ json: { type, userId, triggerId, actionId, callbackId, submittedValues } }];"""

BUILD_NAME_MODAL_CODE = r"""const user = $('Lookup User (Action)').first().json;
const currentName = (user && user.assistant_name) ? user.assistant_name : 'Aria';
const triggerId = $('Parse Interactive Payload').first().json.triggerId;

const modal = {
  type: 'modal',
  callback_id: 'save_name',
  title: { type: 'plain_text', text: 'Edit Assistant Name' },
  submit: { type: 'plain_text', text: 'Save' },
  close: { type: 'plain_text', text: 'Cancel' },
  blocks: [
    {
      type: 'input',
      block_id: 'name_block',
      label: { type: 'plain_text', text: 'Assistant Name' },
      element: {
        type: 'plain_text_input',
        action_id: 'name_value',
        initial_value: currentName,
        placeholder: { type: 'plain_text', text: 'e.g. ScottAI, Luna, Aria' },
        max_length: 50
      }
    }
  ]
};

return [{ json: { triggerId, modal: JSON.stringify(modal) } }];"""

BUILD_EMOJI_MODAL_CODE = r"""const user = $('Lookup User (Action)').first().json;
const currentEmoji = (user && user.assistant_emoji) ? user.assistant_emoji : ':robot_face:';
const triggerId = $('Parse Interactive Payload').first().json.triggerId;

const modal = {
  type: 'modal',
  callback_id: 'save_emoji',
  title: { type: 'plain_text', text: 'Edit Assistant Emoji' },
  submit: { type: 'plain_text', text: 'Save' },
  close: { type: 'plain_text', text: 'Cancel' },
  blocks: [
    {
      type: 'input',
      block_id: 'emoji_block',
      label: { type: 'plain_text', text: 'Emoji' },
      hint: { type: 'plain_text', text: 'Use :emoji_name: format. Custom workspace emojis work too.' },
      element: {
        type: 'plain_text_input',
        action_id: 'emoji_value',
        initial_value: currentEmoji,
        placeholder: { type: 'plain_text', text: ':rocket: or :crystal_ball:' }
      }
    }
  ]
};

return [{ json: { triggerId, modal: JSON.stringify(modal) } }];"""

BUILD_PERSONA_MODAL_CODE = r"""const user = $('Lookup User (Action)').first().json;
const currentPersona = (user && user.assistant_persona) ? user.assistant_persona : 'direct, action-oriented, conversational';
const triggerId = $('Parse Interactive Payload').first().json.triggerId;

const modal = {
  type: 'modal',
  callback_id: 'save_persona',
  title: { type: 'plain_text', text: 'Edit Persona' },
  submit: { type: 'plain_text', text: 'Save' },
  close: { type: 'plain_text', text: 'Cancel' },
  blocks: [
    {
      type: 'section',
      text: { type: 'mrkdwn', text: 'Describe how your assistant should sound. This affects the tone of all briefings and responses.' }
    },
    {
      type: 'input',
      block_id: 'persona_block',
      label: { type: 'plain_text', text: 'Personality' },
      hint: { type: 'plain_text', text: "Examples: 'direct and data-driven', 'witty and casual', 'formal and structured'" },
      element: {
        type: 'plain_text_input',
        action_id: 'persona_value',
        multiline: true,
        initial_value: currentPersona,
        placeholder: { type: 'plain_text', text: 'direct, action-oriented, conversational' }
      }
    }
  ]
};

return [{ json: { triggerId, modal: JSON.stringify(modal) } }];"""

BUILD_SCOPE_MODAL_CODE = r"""const user = $('Lookup User (Action)').first().json;
const currentScope = (user && user.digest_scope) ? user.digest_scope : 'my_deals';
const triggerId = $('Parse Interactive Payload').first().json.triggerId;

const options = [
  { text: { type: 'plain_text', text: 'My deals \u2014 personal pipeline' }, value: 'my_deals' },
  { text: { type: 'plain_text', text: 'Team deals \u2014 my team\u2019s pipeline' }, value: 'team_deals' },
  { text: { type: 'plain_text', text: 'Full pipeline \u2014 org-wide top deals' }, value: 'top_pipeline' }
];

const initialOption = options.find(o => o.value === currentScope) || options[0];

const modal = {
  type: 'modal',
  callback_id: 'save_scope',
  title: { type: 'plain_text', text: 'Digest Scope' },
  submit: { type: 'plain_text', text: 'Save' },
  close: { type: 'plain_text', text: 'Cancel' },
  blocks: [
    {
      type: 'section',
      text: { type: 'mrkdwn', text: 'What pipeline view do you want in your morning digest?' }
    },
    {
      type: 'input',
      block_id: 'scope_block',
      label: { type: 'plain_text', text: 'Scope' },
      element: {
        type: 'radio_buttons',
        action_id: 'scope_value',
        initial_option: initialOption,
        options: options
      }
    }
  ]
};

return [{ json: { triggerId, modal: JSON.stringify(modal) } }];"""

BUILD_TIME_MODAL_CODE = r"""const user = $('Lookup User (Action)').first().json;
const rawTime = (user && user.digest_time) ? user.digest_time : '06:00:00';
const currentTime = rawTime.substring(0, 5);  // strip seconds
const triggerId = $('Parse Interactive Payload').first().json.triggerId;

const modal = {
  type: 'modal',
  callback_id: 'save_digest_time',
  title: { type: 'plain_text', text: 'Digest Delivery Time' },
  submit: { type: 'plain_text', text: 'Save' },
  close: { type: 'plain_text', text: 'Cancel' },
  blocks: [
    {
      type: 'input',
      block_id: 'time_block',
      label: { type: 'plain_text', text: 'Delivery time (24-hour format)' },
      hint: { type: 'plain_text', text: 'Format: HH:MM \u2014 e.g. 06:00 for 6am, 07:30 for 7:30am' },
      element: {
        type: 'plain_text_input',
        action_id: 'time_value',
        initial_value: currentTime,
        placeholder: { type: 'plain_text', text: '06:00' }
      }
    }
  ]
};

return [{ json: { triggerId, modal: JSON.stringify(modal) } }];"""

PREPARE_UPDATE_CODE = r"""const p = $('Parse Interactive Payload').first().json;
const user = $('Lookup User (Submission)').first().json;
const cb = p.callbackId;
const vals = p.submittedValues || {};

const fieldMap = {
  'save_name':        { fieldId: 'assistant_name',  fieldValue: (vals.name_value || '').trim() },
  'save_emoji':       { fieldId: 'assistant_emoji', fieldValue: (vals.emoji_value || '').trim() },
  'save_persona':     { fieldId: 'assistant_persona', fieldValue: (vals.persona_value || '').trim() },
  'save_scope':       { fieldId: 'digest_scope',    fieldValue: vals.scope_value || 'my_deals' },
  'save_digest_time': { fieldId: 'digest_time',     fieldValue: (() => {
    const t = (vals.time_value || '06:00').trim();
    const m = t.match(/^(\d{1,2}):(\d{2})$/);
    if (m) return m[1].padStart(2, '0') + ':' + m[2] + ':00';
    return '06:00:00';
  })() }
};

const update = fieldMap[cb];
if (!update || !user || !user.id) return [];

return [{ json: { fieldId: update.fieldId, fieldValue: update.fieldValue, dbUserId: user.id } }];"""


# ── Slack Events Handler upgrade ──────────────────────────────────────────────

def upgrade_events_handler(wf):
    print("\n=== Upgrading Slack Events Handler ===")
    nodes = wf["nodes"]
    connections = wf["connections"]

    # Guard: skip if already upgraded
    if any(n["name"] == "Build Home View" for n in nodes):
        print("  'Build Home View' already exists — skipping")
        return wf

    # 1. Patch Extract Event Data
    patched = False
    for node in nodes:
        if node["name"] == "Extract Event Data":
            node["parameters"]["jsCode"] = EXTRACT_EVENT_DATA_CODE
            patched = True
            print("  Patched: Extract Event Data")
            break
    if not patched:
        print("  WARNING: 'Extract Event Data' node not found")

    # 2. Patch Route by State
    patched = False
    for node in nodes:
        if node["name"] == "Route by State":
            node["parameters"]["jsCode"] = ROUTE_BY_STATE_CODE
            patched = True
            print("  Patched: Route by State")
            break
    if not patched:
        print("  WARNING: 'Route by State' node not found")

    # 3. Add 'App Home' output (index 12) to Switch Route
    patched = False
    for node in nodes:
        if node["name"] == "Switch Route":
            node["parameters"]["rules"]["values"].append({
                "outputKey": "App Home",
                "renameOutput": True,
                "conditions": {
                    "options": {
                        "version": 2,
                        "leftValue": "",
                        "caseSensitive": True,
                        "typeValidation": "strict"
                    },
                    "combinator": "and",
                    "conditions": [{
                        "id": uid(),
                        "operator": {
                            "name": "filter.operator.equals",
                            "type": "string",
                            "operation": "equals"
                        },
                        "leftValue": "={{ $json.route }}",
                        "rightValue": "app_home_opened"
                    }]
                }
            })
            patched = True
            print("  Added output 12 'App Home' to Switch Route")
            break
    if not patched:
        print("  WARNING: 'Switch Route' node not found")

    # 4. Add 'Build Home View' Code node
    build_id = uid()
    nodes.append({
        "parameters": {"jsCode": BUILD_HOME_VIEW_CODE},
        "id": build_id,
        "name": "Build Home View",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [2000, 3300]
    })
    print(f"  Added: Build Home View (id={build_id})")

    # 5. Add 'Publish Home View' HTTP node
    publish_id = uid()
    nodes.append({
        "parameters": {
            "method": "POST",
            "url": "https://slack.com/api/views.publish",
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Content-Type", "value": "application/json"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ user_id: $json.userId, view: JSON.parse($json.homeView) }) }}",
            "options": {}
        },
        "id": publish_id,
        "name": "Publish Home View",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [2224, 3300],
        "continueOnFail": True,
        "credentials": {"httpHeaderAuth": SLACK_CRED}
    })
    print(f"  Added: Publish Home View (id={publish_id})")

    # 6. Wire connections
    # Switch Route output[12] → Build Home View
    switch_main = connections["Switch Route"]["main"]
    while len(switch_main) < 13:
        switch_main.append([])
    switch_main[12] = [{"node": "Build Home View", "type": "main", "index": 0}]

    connections["Build Home View"] = {
        "main": [[{"node": "Publish Home View", "type": "main", "index": 0}]]
    }

    print(f"  Total nodes after upgrade: {len(nodes)}")
    return wf


# ── Interactive Events Handler workflow builder ───────────────────────────────

def make_supabase_getall_by_slack_id(name, slack_id_expr, position):
    return {
        "parameters": {
            "operation": "getAll",
            "tableId": "users",
            "limit": 1,
            "filters": {
                "conditions": [{
                    "keyName": "slack_user_id",
                    "condition": "eq",
                    "keyValue": slack_id_expr
                }]
            }
        },
        "id": uid(),
        "name": name,
        "type": "n8n-nodes-base.supabase",
        "typeVersion": 1,
        "position": position,
        "alwaysOutputData": True,
        "credentials": {"supabaseApi": SUPABASE_CRED}
    }


def make_supabase_getall_by_id(name, id_expr, position):
    return {
        "parameters": {
            "operation": "getAll",
            "tableId": "users",
            "limit": 1,
            "filters": {
                "conditions": [{
                    "keyName": "id",
                    "condition": "eq",
                    "keyValue": id_expr
                }]
            }
        },
        "id": uid(),
        "name": name,
        "type": "n8n-nodes-base.supabase",
        "typeVersion": 1,
        "position": position,
        "alwaysOutputData": True,
        "credentials": {"supabaseApi": SUPABASE_CRED}
    }


def make_views_open_node(name, position):
    return {
        "parameters": {
            "method": "POST",
            "url": "https://slack.com/api/views.open",
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Content-Type", "value": "application/json"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ trigger_id: $json.triggerId, view: JSON.parse($json.modal) }) }}",
            "options": {}
        },
        "id": uid(),
        "name": name,
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": position,
        "continueOnFail": True,
        "credentials": {"httpHeaderAuth": SLACK_CRED}
    }


def make_views_publish_node(name, position):
    return {
        "parameters": {
            "method": "POST",
            "url": "https://slack.com/api/views.publish",
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Content-Type", "value": "application/json"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ user_id: $json.userId, view: JSON.parse($json.homeView) }) }}",
            "options": {}
        },
        "id": uid(),
        "name": name,
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": position,
        "continueOnFail": True,
        "credentials": {"httpHeaderAuth": SLACK_CRED}
    }


def make_switch_condition(output_key, left_expr, right_value):
    return {
        "outputKey": output_key,
        "renameOutput": True,
        "conditions": {
            "options": {"version": 2, "leftValue": "", "caseSensitive": True, "typeValidation": "strict"},
            "combinator": "and",
            "conditions": [{
                "id": uid(),
                "operator": {
                    "name": "filter.operator.equals",
                    "type": "string",
                    "operation": "equals"
                },
                "leftValue": left_expr,
                "rightValue": right_value
            }]
        }
    }


def build_interactive_workflow():
    """Build the complete Interactive Events Handler workflow JSON."""

    nodes = []
    connections = {}

    # ── Node 1: Interactive Webhook ────────────────────────────────────────
    webhook_node = {
        "parameters": {
            "httpMethod": "POST",
            "path": "slack-interactive",
            "responseMode": "responseNode",
            "options": {}
        },
        "id": uid(),
        "name": "Interactive Webhook",
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 2,
        "position": [200, 600],
        "webhookId": uid()
    }
    nodes.append(webhook_node)

    # ── Node 2: Parse Interactive Payload ──────────────────────────────────
    parse_node = {
        "parameters": {"jsCode": PARSE_PAYLOAD_CODE},
        "id": uid(),
        "name": "Parse Interactive Payload",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [424, 600]
    }
    nodes.append(parse_node)

    # ── Node 3: Is View Submission? ────────────────────────────────────────
    is_submission_node = {
        "parameters": {
            "conditions": {
                "options": {"version": 2, "caseSensitive": True, "typeValidation": "strict"},
                "combinator": "and",
                "conditions": [{
                    "id": uid(),
                    "leftValue": "={{ $json.type }}",
                    "rightValue": "view_submission",
                    "operator": {"type": "string", "operation": "equals", "name": "filter.operator.equals"}
                }]
            },
            "options": {}
        },
        "id": uid(),
        "name": "Is View Submission?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [648, 600]
    }
    nodes.append(is_submission_node)

    # ── BLOCK ACTIONS BRANCH (output 1 / false) ────────────────────────────

    # Node 4: Acknowledge Action
    ack_node = {
        "parameters": {
            "respondWith": "json",
            "responseBody": "{}",
            "options": {"responseCode": 200}
        },
        "id": uid(),
        "name": "Acknowledge Action",
        "type": "n8n-nodes-base.respondToWebhook",
        "typeVersion": 1.1,
        "position": [648, 800]
    }
    nodes.append(ack_node)

    # Node 5: Lookup User (Action)
    lookup_action_node = make_supabase_getall_by_slack_id(
        "Lookup User (Action)",
        "={{ $('Parse Interactive Payload').first().json.userId }}",
        [872, 800]
    )
    nodes.append(lookup_action_node)

    # Node 6: Route Action (Switch, 6 outputs)
    route_action_node = {
        "parameters": {
            "rules": {
                "values": [
                    make_switch_condition("Edit Name", "={{ $('Parse Interactive Payload').first().json.actionId }}", "edit_name"),
                    make_switch_condition("Edit Emoji", "={{ $('Parse Interactive Payload').first().json.actionId }}", "edit_emoji"),
                    make_switch_condition("Edit Persona", "={{ $('Parse Interactive Payload').first().json.actionId }}", "edit_persona"),
                    make_switch_condition("Edit Scope", "={{ $('Parse Interactive Payload').first().json.actionId }}", "edit_scope"),
                    make_switch_condition("Edit Time", "={{ $('Parse Interactive Payload').first().json.actionId }}", "edit_digest_time"),
                    make_switch_condition("Toggle Digest", "={{ $('Parse Interactive Payload').first().json.actionId }}", "toggle_digest"),
                ]
            },
            "options": {}
        },
        "id": uid(),
        "name": "Route Action",
        "type": "n8n-nodes-base.switch",
        "typeVersion": 3.2,
        "position": [1096, 800]
    }
    nodes.append(route_action_node)

    # Modal builder nodes — fan out vertically from Switch outputs
    # Output 0: Edit Name (y=400)
    build_name_node = {
        "parameters": {"jsCode": BUILD_NAME_MODAL_CODE},
        "id": uid(), "name": "Build Name Modal",
        "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [1320, 400]
    }
    open_name_node = make_views_open_node("Open Name Modal", [1544, 400])
    nodes += [build_name_node, open_name_node]

    # Output 1: Edit Emoji (y=600)
    build_emoji_node = {
        "parameters": {"jsCode": BUILD_EMOJI_MODAL_CODE},
        "id": uid(), "name": "Build Emoji Modal",
        "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [1320, 600]
    }
    open_emoji_node = make_views_open_node("Open Emoji Modal", [1544, 600])
    nodes += [build_emoji_node, open_emoji_node]

    # Output 2: Edit Persona (y=800)
    build_persona_node = {
        "parameters": {"jsCode": BUILD_PERSONA_MODAL_CODE},
        "id": uid(), "name": "Build Persona Modal",
        "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [1320, 800]
    }
    open_persona_node = make_views_open_node("Open Persona Modal", [1544, 800])
    nodes += [build_persona_node, open_persona_node]

    # Output 3: Edit Scope (y=1000)
    build_scope_node = {
        "parameters": {"jsCode": BUILD_SCOPE_MODAL_CODE},
        "id": uid(), "name": "Build Scope Modal",
        "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [1320, 1000]
    }
    open_scope_node = make_views_open_node("Open Scope Modal", [1544, 1000])
    nodes += [build_scope_node, open_scope_node]

    # Output 4: Edit Time (y=1200)
    build_time_node = {
        "parameters": {"jsCode": BUILD_TIME_MODAL_CODE},
        "id": uid(), "name": "Build Time Modal",
        "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [1320, 1200]
    }
    open_time_node = make_views_open_node("Open Time Modal", [1544, 1200])
    nodes += [build_time_node, open_time_node]

    # Output 5: Toggle Digest (y=1400) — no modal, direct DB toggle
    toggle_db_node = {
        "parameters": {
            "operation": "update",
            "tableId": "users",
            "dataToSend": "defineBelow",
            "fieldsUi": {
                "fieldValues": [{
                    "fieldId": "digest_enabled",
                    "fieldValue": "={{ !$('Lookup User (Action)').first().json.digest_enabled }}"
                }]
            },
            "filters": {
                "conditions": [{
                    "keyName": "id",
                    "condition": "eq",
                    "keyValue": "={{ $('Lookup User (Action)').first().json.id }}"
                }]
            }
        },
        "id": uid(),
        "name": "Toggle Digest DB",
        "type": "n8n-nodes-base.supabase",
        "typeVersion": 1,
        "position": [1320, 1400],
        "credentials": {"supabaseApi": SUPABASE_CRED}
    }
    nodes.append(toggle_db_node)

    refresh_toggle_node = make_supabase_getall_by_id(
        "Refresh User After Toggle",
        "={{ $('Lookup User (Action)').first().json.id }}",
        [1544, 1400]
    )
    nodes.append(refresh_toggle_node)

    build_toggle_home_node = {
        "parameters": {"jsCode": BUILD_TOGGLE_HOME_VIEW_CODE},
        "id": uid(), "name": "Build Toggle Home View",
        "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [1768, 1400]
    }
    nodes.append(build_toggle_home_node)

    publish_toggle_home_node = make_views_publish_node("Publish Toggle Home View", [1992, 1400])
    nodes.append(publish_toggle_home_node)

    # ── VIEW SUBMISSION BRANCH (output 0 / true) ───────────────────────────

    # Node: Respond Modal Close (FIRST — closes modal immediately)
    respond_close_node = {
        "parameters": {
            "respondWith": "json",
            "responseBody": "{}",
            "options": {"responseCode": 200}
        },
        "id": uid(),
        "name": "Respond Modal Close",
        "type": "n8n-nodes-base.respondToWebhook",
        "typeVersion": 1.1,
        "position": [648, 200]
    }
    nodes.append(respond_close_node)

    # Node: Lookup User (Submission)
    lookup_submission_node = make_supabase_getall_by_slack_id(
        "Lookup User (Submission)",
        "={{ $('Parse Interactive Payload').first().json.userId }}",
        [872, 200]
    )
    nodes.append(lookup_submission_node)

    # Node: Prepare Update (maps callback_id to field/value)
    prepare_update_node = {
        "parameters": {"jsCode": PREPARE_UPDATE_CODE},
        "id": uid(),
        "name": "Prepare Update",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1096, 200]
    }
    nodes.append(prepare_update_node)

    # Node: Update User Field (single dynamic Supabase update)
    update_field_node = {
        "parameters": {
            "operation": "update",
            "tableId": "users",
            "dataToSend": "defineBelow",
            "fieldsUi": {
                "fieldValues": [{
                    "fieldId": "={{ $json.fieldId }}",
                    "fieldValue": "={{ $json.fieldValue }}"
                }]
            },
            "filters": {
                "conditions": [{
                    "keyName": "id",
                    "condition": "eq",
                    "keyValue": "={{ $json.dbUserId }}"
                }]
            }
        },
        "id": uid(),
        "name": "Update User Field",
        "type": "n8n-nodes-base.supabase",
        "typeVersion": 1,
        "position": [1320, 200],
        "credentials": {"supabaseApi": SUPABASE_CRED}
    }
    nodes.append(update_field_node)

    # Node: Refresh User (Submission)
    refresh_submission_node = make_supabase_getall_by_id(
        "Refresh User (Submission)",
        "={{ $('Lookup User (Submission)').first().json.id }}",
        [1544, 200]
    )
    nodes.append(refresh_submission_node)

    # Node: Build Submission Home View
    build_submission_home_node = {
        "parameters": {"jsCode": BUILD_SUBMISSION_HOME_VIEW_CODE},
        "id": uid(), "name": "Build Submission Home View",
        "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [1768, 200]
    }
    nodes.append(build_submission_home_node)

    # Node: Publish Submission Home View
    publish_submission_home_node = make_views_publish_node("Publish Submission Home View", [1992, 200])
    nodes.append(publish_submission_home_node)

    # ── Connections ────────────────────────────────────────────────────────
    connections = {
        "Interactive Webhook": {
            "main": [[{"node": "Parse Interactive Payload", "type": "main", "index": 0}]]
        },
        "Parse Interactive Payload": {
            "main": [[{"node": "Is View Submission?", "type": "main", "index": 0}]]
        },
        "Is View Submission?": {
            "main": [
                # output 0 (true): view_submission branch
                [{"node": "Respond Modal Close", "type": "main", "index": 0}],
                # output 1 (false): block_actions branch
                [{"node": "Acknowledge Action", "type": "main", "index": 0}]
            ]
        },
        # Block actions branch
        "Acknowledge Action": {
            "main": [[{"node": "Lookup User (Action)", "type": "main", "index": 0}]]
        },
        "Lookup User (Action)": {
            "main": [[{"node": "Route Action", "type": "main", "index": 0}]]
        },
        "Route Action": {
            "main": [
                [{"node": "Build Name Modal", "type": "main", "index": 0}],    # 0: edit_name
                [{"node": "Build Emoji Modal", "type": "main", "index": 0}],   # 1: edit_emoji
                [{"node": "Build Persona Modal", "type": "main", "index": 0}], # 2: edit_persona
                [{"node": "Build Scope Modal", "type": "main", "index": 0}],   # 3: edit_scope
                [{"node": "Build Time Modal", "type": "main", "index": 0}],    # 4: edit_digest_time
                [{"node": "Toggle Digest DB", "type": "main", "index": 0}]     # 5: toggle_digest
            ]
        },
        "Build Name Modal":    {"main": [[{"node": "Open Name Modal",    "type": "main", "index": 0}]]},
        "Build Emoji Modal":   {"main": [[{"node": "Open Emoji Modal",   "type": "main", "index": 0}]]},
        "Build Persona Modal": {"main": [[{"node": "Open Persona Modal", "type": "main", "index": 0}]]},
        "Build Scope Modal":   {"main": [[{"node": "Open Scope Modal",   "type": "main", "index": 0}]]},
        "Build Time Modal":    {"main": [[{"node": "Open Time Modal",    "type": "main", "index": 0}]]},
        "Toggle Digest DB": {
            "main": [[{"node": "Refresh User After Toggle", "type": "main", "index": 0}]]
        },
        "Refresh User After Toggle": {
            "main": [[{"node": "Build Toggle Home View", "type": "main", "index": 0}]]
        },
        "Build Toggle Home View": {
            "main": [[{"node": "Publish Toggle Home View", "type": "main", "index": 0}]]
        },
        # View submission branch
        "Respond Modal Close": {
            "main": [[{"node": "Lookup User (Submission)", "type": "main", "index": 0}]]
        },
        "Lookup User (Submission)": {
            "main": [[{"node": "Prepare Update", "type": "main", "index": 0}]]
        },
        "Prepare Update": {
            "main": [[{"node": "Update User Field", "type": "main", "index": 0}]]
        },
        "Update User Field": {
            "main": [[{"node": "Refresh User (Submission)", "type": "main", "index": 0}]]
        },
        "Refresh User (Submission)": {
            "main": [[{"node": "Build Submission Home View", "type": "main", "index": 0}]]
        },
        "Build Submission Home View": {
            "main": [[{"node": "Publish Submission Home View", "type": "main", "index": 0}]]
        }
    }

    return {
        "name": "Interactive Events Handler",
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1"},
        "staticData": None
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # ── Step 1: Upgrade Slack Events Handler ──────────────────────────────
    print("Fetching Slack Events Handler...")
    events_wf = fetch_workflow(SLACK_EVENTS_ID)
    print(f"  {len(events_wf['nodes'])} nodes, {len(events_wf['connections'])} connection keys")

    events_wf = upgrade_events_handler(events_wf)
    result = push_workflow(SLACK_EVENTS_ID, events_wf)
    print(f"  Pushed: {len(result['nodes'])} nodes")

    # Sync local file
    live_events = fetch_workflow(SLACK_EVENTS_ID)
    sync_local(live_events, "Slack Events Handler.json")

    # ── Step 2: Create Interactive Events Handler ──────────────────────────
    print("\n=== Creating Interactive Events Handler ===")
    interactive_wf = build_interactive_workflow()
    print(f"  Workflow has {len(interactive_wf['nodes'])} nodes")

    resp = requests.post(
        f"{N8N_BASE_URL}/api/v1/workflows",
        headers=HEADERS,
        json=interactive_wf
    )
    resp.raise_for_status()
    created = resp.json()
    interactive_id = created["id"]
    print(f"  Created: ID={interactive_id}, {len(created['nodes'])} nodes")

    # Activate
    activate_workflow(interactive_id)
    print(f"  Activated: {interactive_id}")

    # Sync local file
    live_interactive = fetch_workflow(interactive_id)
    sync_local(live_interactive, "Interactive Events Handler.json")

    # ── Summary ────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("Done!")
    print(f"  Slack Events Handler: {SLACK_EVENTS_ID} (updated)")
    print(f"  Interactive Events Handler: {interactive_id} (created + activated)")
    print()
    print("Next steps:")
    print("  1. In Slack app → Event Subscriptions → add 'app_home_opened'")
    print("  2. In Slack app → Interactivity & Shortcuts → confirm Request URL:")
    print(f"     https://scottai.trackslife.com/webhook/slack-interactive")
    print("  3. Click the App Home tab in Slack to test")


if __name__ == "__main__":
    main()
