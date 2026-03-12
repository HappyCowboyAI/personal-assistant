#!/usr/bin/env python3
"""
Create the Feature Education Cron workflow.

Daily cron (1pm PT weekdays) that delivers personalized feature tips
to users based on their onboarding age, feature usage history, and
education history. Supports two trigger types:

- onboarding_drip: New users (first 14 days) get features introduced
  in drip_order sequence based on drip_day thresholds.
- re_engagement: Existing users who stopped using a feature (14+ days)
  get a nudge to re-engage.

Pacing: max 2 tips per week, min 3 days between tips.

Workflow (15 nodes):
  Daily 1pm PT → Get Active Users → Get Education History → Get Feature Usage
  → Get Feature Catalog → Prepare Education Batch → Split In Batches → [loop]
  → Pick Feature & Build Prompt → Has Tip? (IF)
  → [true] Education Agent → Open Bot DM → Send Tip DM → Prepare Education Log
  → Log Education → [loop back]
  → [false] → [loop back]

Sub-nodes: Anthropic Chat Model (Education) → Education Agent
"""

from n8n_helpers import (
    uid,
    create_or_update_workflow,
    make_code_node,
    make_slack_http_node,
    make_supabase_http_node,
    SUPABASE_URL,
    SUPABASE_CRED,
    ANTHROPIC_CRED,
    SLACK_CONVERSATIONS_OPEN,
    SLACK_CHAT_POST,
    NODE_SCHEDULE_TRIGGER,
    NODE_HTTP_REQUEST,
    NODE_IF,
    NODE_SPLIT_IN_BATCHES,
    NODE_AGENT,
    NODE_ANTHROPIC_CHAT,
    MODEL_SONNET,
)


# ── Code: Prepare Education Batch ────────────────────────────────────

PREPARE_EDUCATION_BATCH_CODE = r"""const usersRaw = $('Get Active Users').first().json;
const historyRaw = $('Get Education History').first().json;
const usageRaw = $('Get Feature Usage').first().json;
const catalogRaw = $('Get Feature Catalog').first().json;

const users = Array.isArray(usersRaw) ? usersRaw : [usersRaw];
const history = Array.isArray(historyRaw) ? historyRaw : (historyRaw?.id ? [historyRaw] : []);
const usage = Array.isArray(usageRaw) ? usageRaw : (usageRaw?.id ? [usageRaw] : []);
const catalog = Array.isArray(catalogRaw) ? catalogRaw : (catalogRaw?.id ? [catalogRaw] : []);

// Group history by user
const historyByUser = {};
for (const h of history) {
  if (!historyByUser[h.user_id]) historyByUser[h.user_id] = [];
  historyByUser[h.user_id].push(h);
}

// Group usage by user
const usageByUser = {};
for (const u of usage) {
  if (!usageByUser[u.user_id]) usageByUser[u.user_id] = {};
  usageByUser[u.user_id][u.feature_id] = u;
}

const output = [];
for (const user of users) {
  if (user.onboarding_state !== 'complete') continue;
  if (!user.tips_enabled && !user.announcements_enabled) continue;

  output.push({
    json: {
      userId: user.id,
      slackUserId: user.slack_user_id,
      email: user.email,
      assistantName: user.assistant_name || 'Aria',
      assistantEmoji: user.assistant_emoji || ':robot_face:',
      assistantPersona: user.assistant_persona || 'friendly and helpful',
      organizationId: user.organization_id,
      tipsEnabled: user.tips_enabled !== false,
      announcementsEnabled: user.announcements_enabled !== false,
      userCreatedAt: user.created_at,
      educationHistory: historyByUser[user.id] || [],
      featureUsage: usageByUser[user.id] || {},
      featureCatalog: catalog,
    }
  });
}

if (output.length === 0) {
  return [{ json: { skip: true } }];
}

return output;
"""


# ── Code: Pick Feature & Build Prompt ────────────────────────────────

PICK_FEATURE_CODE = r"""const data = $input.first().json;
if (data.skip) {
  return [{ json: { ...data, hasTip: false } }];
}

const now = new Date();
const userAge = Math.floor((now - new Date(data.userCreatedAt)) / (24*60*60*1000));
const history = data.educationHistory || [];
const usage = data.featureUsage || {};
const catalog = data.featureCatalog || [];

// Pacing: max 2 tips/week, min 3 days between tips
const recentTips = history.filter(h => {
  const daysAgo = (now - new Date(h.delivered_at)) / (24*60*60*1000);
  return daysAgo <= 7;
});
if (recentTips.length >= 2) {
  return [{ json: { ...data, hasTip: false } }];
}

if (history.length > 0) {
  const lastTipDaysAgo = Math.min(...history.map(h => (now - new Date(h.delivered_at)) / (24*60*60*1000)));
  if (lastTipDaysAgo < 3) {
    return [{ json: { ...data, hasTip: false } }];
  }
}

const educatedDrip = new Set(history.filter(h => h.trigger_type === 'onboarding_drip').map(h => h.feature_id));
const educatedReengagement = new Set(history.filter(h => h.trigger_type === 're_engagement').map(h => h.feature_id));

let selectedFeature = null;
let triggerType = null;

// Priority 1: Onboarding drip (first 14 days, tips_enabled)
if (data.tipsEnabled && userAge <= 14) {
  const dripFeatures = catalog
    .filter(f => f.drip_order !== null && f.drip_day !== null)
    .sort((a, b) => a.drip_order - b.drip_order);

  for (const feature of dripFeatures) {
    if (userAge >= feature.drip_day && !educatedDrip.has(feature.id) && !usage[feature.id]) {
      selectedFeature = feature;
      triggerType = 'onboarding_drip';
      break;
    }
  }
}

// Priority 2: Re-engagement (feature unused 14+ days, tips_enabled)
if (!selectedFeature && data.tipsEnabled && userAge > 7) {
  for (const feature of catalog) {
    const featureUsage = usage[feature.id];
    if (!featureUsage) continue;
    const daysSinceUse = (now - new Date(featureUsage.last_used_at)) / (24*60*60*1000);
    if (daysSinceUse >= 14 && !educatedReengagement.has(feature.id)) {
      if (featureUsage.use_count >= 3) {
        selectedFeature = feature;
        triggerType = 're_engagement';
        break;
      }
    }
  }
}

if (!selectedFeature) {
  return [{ json: { ...data, hasTip: false } }];
}

const persona = data.assistantPersona || 'friendly and helpful';
const tipSystemPrompt = `You are ${data.assistantName}, a sales assistant with the following personality: ${persona}.

Write a SHORT Slack DM (2-3 sentences max) introducing a feature to your user. This should feel like a casual, helpful tip — not a product announcement or documentation.

Rules:
- Use Slack formatting (*bold*, _italic_, bullet points)
- Match the personality described above
- Be conversational and brief
- Include the specific command or action they should try
- Don't start with "Hey!" or "Did you know?" — vary your openings
- Don't use emojis excessively (1-2 max)
- If this is a re-engagement tip, acknowledge they've used it before

Feature to introduce:
- Name: ${selectedFeature.display_name}
- What it does: ${selectedFeature.description}
- How to use: ${selectedFeature.how_to_use}

Trigger type: ${triggerType === 're_engagement' ? "Re-engagement — they used this before but haven't recently" : "Onboarding — they haven't tried this yet"}

Write ONLY the message text. No subject line, no preamble.`;

return [{
  json: {
    ...data,
    hasTip: true,
    selectedFeatureId: selectedFeature.id,
    selectedFeatureName: selectedFeature.display_name,
    triggerType: triggerType,
    tipSystemPrompt: tipSystemPrompt,
    tipUserPrompt: 'Write a tip about ' + selectedFeature.display_name + ' for this user.',
  }
}];
"""


# ── Code: Prepare Education Log ──────────────────────────────────────

PREPARE_EDUCATION_LOG_CODE = r"""const data = $('Pick Feature & Build Prompt').first().json;
const agentOutput = $('Education Agent').first().json.output || '';
const sendResult = $('Send Tip DM').first().json;

return [{
  json: {
    user_id: data.userId,
    feature_id: data.selectedFeatureId,
    trigger_type: data.triggerType,
    message_text: agentOutput,
    slack_message_ts: sendResult.ts || null,
    slack_channel_id: sendResult.channel || null,
  }
}];
"""


def build_workflow():
    nodes = []
    connections = {}

    # ── 1. Schedule Trigger (Daily 1pm PT, weekdays) ─────────────────
    nodes.append({
        "parameters": {
            "rule": {
                "interval": [{
                    "triggerAtHour": 13,
                    "triggerAtMinute": 0,
                    "triggerAtDay": [1, 2, 3, 4, 5],
                }]
            },
        },
        "id": uid(),
        "name": "Daily 1pm PT",
        "type": NODE_SCHEDULE_TRIGGER,
        "typeVersion": 1.2,
        "position": [250, 300],
    })

    # ── 2. Get Active Users ──────────────────────────────────────────
    nodes.append(make_supabase_http_node(
        name="Get Active Users",
        method="GET",
        url_path="users?onboarding_state=eq.complete&select=id,slack_user_id,email,assistant_name,assistant_emoji,assistant_persona,organization_id,onboarding_state,tips_enabled,announcements_enabled,created_at",
        position=[550, 300],
    ))
    connections["Daily 1pm PT"] = {
        "main": [[{"node": "Get Active Users", "type": "main", "index": 0}]]
    }

    # ── 3. Get Education History (last 30 days) ──────────────────────
    # URL contains an n8n expression for the date filter, so must use
    # leading "=" to mark the entire URL as an expression field.
    history_node = {
        "parameters": {
            "method": "GET",
            "url": f"={SUPABASE_URL}/rest/v1/education_log?delivered_at=gte.{{{{ new Date(Date.now() - 30*24*60*60*1000).toISOString() }}}}&select=user_id,feature_id,trigger_type,delivered_at",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "supabaseApi",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Prefer", "value": "return=representation"}
                ]
            },
            "options": {},
        },
        "id": uid(),
        "name": "Get Education History",
        "type": NODE_HTTP_REQUEST,
        "typeVersion": 4.2,
        "position": [850, 300],
        "credentials": {"supabaseApi": SUPABASE_CRED},
        "alwaysOutputData": True,
    }
    nodes.append(history_node)
    connections["Get Active Users"] = {
        "main": [[{"node": "Get Education History", "type": "main", "index": 0}]]
    }

    # ── 4. Get Feature Usage ─────────────────────────────────────────
    usage_node = make_supabase_http_node(
        name="Get Feature Usage",
        method="GET",
        url_path="feature_usage?select=user_id,feature_id,first_used_at,last_used_at,use_count",
        position=[1150, 300],
    )
    usage_node["alwaysOutputData"] = True
    nodes.append(usage_node)
    connections["Get Education History"] = {
        "main": [[{"node": "Get Feature Usage", "type": "main", "index": 0}]]
    }

    # ── 5. Get Feature Catalog ───────────────────────────────────────
    nodes.append(make_supabase_http_node(
        name="Get Feature Catalog",
        method="GET",
        url_path="feature_catalog?select=*&order=drip_order.asc.nullslast",
        position=[1450, 300],
    ))
    connections["Get Feature Usage"] = {
        "main": [[{"node": "Get Feature Catalog", "type": "main", "index": 0}]]
    }

    # ── 6. Prepare Education Batch (Code) ────────────────────────────
    nodes.append(make_code_node(
        name="Prepare Education Batch",
        js_code=PREPARE_EDUCATION_BATCH_CODE,
        position=[1750, 300],
    ))
    connections["Get Feature Catalog"] = {
        "main": [[{"node": "Prepare Education Batch", "type": "main", "index": 0}]]
    }

    # ── 7. Split In Batches ──────────────────────────────────────────
    nodes.append({
        "parameters": {"options": {}},
        "id": uid(),
        "name": "Split In Batches",
        "type": NODE_SPLIT_IN_BATCHES,
        "typeVersion": 3,
        "position": [2050, 300],
    })
    connections["Prepare Education Batch"] = {
        "main": [[{"node": "Split In Batches", "type": "main", "index": 0}]]
    }

    # ── 8. Pick Feature & Build Prompt (Code) ────────────────────────
    nodes.append(make_code_node(
        name="Pick Feature & Build Prompt",
        js_code=PICK_FEATURE_CODE,
        position=[2350, 300],
    ))
    # SplitInBatches v3: output 0 = done, output 1 = loop items
    connections["Split In Batches"] = {
        "main": [
            [],  # output 0 = done (nothing connected)
            [{"node": "Pick Feature & Build Prompt", "type": "main", "index": 0}],
        ]
    }

    # ── 9. Has Tip? (IF node) ────────────────────────────────────────
    nodes.append({
        "parameters": {
            "conditions": {
                "options": {
                    "version": 2,
                    "leftValue": "",
                    "caseSensitive": True,
                    "typeValidation": "strict",
                },
                "conditions": [
                    {
                        "id": uid(),
                        "leftValue": "={{ $json.hasTip }}",
                        "rightValue": True,
                        "operator": {
                            "type": "boolean",
                            "operation": "equals",
                        },
                    }
                ],
                "combinator": "and",
            },
            "options": {},
        },
        "id": uid(),
        "name": "Has Tip?",
        "type": NODE_IF,
        "typeVersion": 2.2,
        "position": [2650, 300],
    })
    connections["Pick Feature & Build Prompt"] = {
        "main": [[{"node": "Has Tip?", "type": "main", "index": 0}]]
    }

    # ── 10. Education Agent ──────────────────────────────────────────
    nodes.append({
        "parameters": {
            "promptType": "define",
            "text": "={{ $json.tipUserPrompt }}",
            "options": {
                "systemMessage": "={{ $json.tipSystemPrompt }}",
                "maxIterations": 3,
            },
        },
        "id": uid(),
        "name": "Education Agent",
        "type": NODE_AGENT,
        "typeVersion": 1.7,
        "position": [2950, 200],
        "continueOnFail": True,
    })

    # ── 11. Anthropic Chat Model (Education) — sub-node ──────────────
    nodes.append({
        "parameters": {
            "model": {
                "__rl": True,
                "mode": "list",
                "value": MODEL_SONNET,
                "cachedResultName": "Claude Sonnet 4.5",
            },
            "options": {},
        },
        "id": uid(),
        "name": "Anthropic Chat Model (Education)",
        "type": NODE_ANTHROPIC_CHAT,
        "typeVersion": 1.3,
        "position": [2900, 420],
        "credentials": {"anthropicApi": ANTHROPIC_CRED},
    })
    # Wire sub-node: model → agent
    connections["Anthropic Chat Model (Education)"] = {
        "ai_languageModel": [
            [{"node": "Education Agent", "type": "ai_languageModel", "index": 0}]
        ]
    }

    # Has Tip? → true (output 0) → Education Agent
    # Has Tip? → false (output 1) → loop back to Split In Batches
    connections["Has Tip?"] = {
        "main": [
            [{"node": "Education Agent", "type": "main", "index": 0}],
            [{"node": "Split In Batches", "type": "main", "index": 0}],
        ]
    }

    # ── 12. Open Bot DM ──────────────────────────────────────────────
    nodes.append(make_slack_http_node(
        name="Open Bot DM",
        api_url=SLACK_CONVERSATIONS_OPEN,
        json_body='={{ JSON.stringify({ users: $("Pick Feature & Build Prompt").first().json.slackUserId }) }}',
        position=[3250, 200],
    ))
    connections["Education Agent"] = {
        "main": [[{"node": "Open Bot DM", "type": "main", "index": 0}]]
    }

    # ── 13. Send Tip DM ──────────────────────────────────────────────
    nodes.append(make_slack_http_node(
        name="Send Tip DM",
        api_url=SLACK_CHAT_POST,
        json_body='={{ JSON.stringify({ channel: $json.channel.id, text: $("Education Agent").first().json.output, username: $("Pick Feature & Build Prompt").first().json.assistantName, icon_emoji: $("Pick Feature & Build Prompt").first().json.assistantEmoji }) }}',
        position=[3550, 200],
    ))
    connections["Open Bot DM"] = {
        "main": [[{"node": "Send Tip DM", "type": "main", "index": 0}]]
    }

    # ── 14. Prepare Education Log (Code) ─────────────────────────────
    nodes.append(make_code_node(
        name="Prepare Education Log",
        js_code=PREPARE_EDUCATION_LOG_CODE,
        position=[3850, 200],
    ))
    connections["Send Tip DM"] = {
        "main": [[{"node": "Prepare Education Log", "type": "main", "index": 0}]]
    }

    # ── 15. Log Education (Supabase HTTP POST) ───────────────────────
    nodes.append(make_supabase_http_node(
        name="Log Education",
        method="POST",
        url_path="education_log",
        position=[4150, 200],
        json_body='={{ JSON.stringify($json) }}',
        extra_headers=[
            {"name": "Prefer", "value": "return=representation"},
            {"name": "Content-Type", "value": "application/json"},
        ],
    ))
    connections["Prepare Education Log"] = {
        "main": [[{"node": "Log Education", "type": "main", "index": 0}]]
    }

    # Log Education → loop back to Split In Batches
    connections["Log Education"] = {
        "main": [[{"node": "Split In Batches", "type": "main", "index": 0}]]
    }

    return {
        "name": "Feature Education Cron",
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1"},
        "staticData": None,
    }


def main():
    print("Building Feature Education Cron workflow...")
    workflow = build_workflow()
    print(f"  {len(workflow['nodes'])} nodes")

    print("\n=== Deploying ===")
    final = create_or_update_workflow(workflow, "Feature Education Cron.json")

    print(f"\nDone! Feature Education Cron workflow deployed.")
    print(f"  Workflow ID: {final['id']}")
    print(f"  Schedule: 1pm PT, weekdays (Mon-Fri)")
    print(f"  Nodes: {len(final['nodes'])}")
    print(f"\n  IMPORTANT: Ensure education_log, feature_catalog, and feature_usage")
    print(f"  tables exist in Supabase before the first run.")


if __name__ == "__main__":
    main()
