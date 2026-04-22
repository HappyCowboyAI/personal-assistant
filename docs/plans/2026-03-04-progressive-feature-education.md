# Progressive Feature Education Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a proactive education system where the assistant teaches users about features over time — onboarding drip, re-engagement nudges, and new feature announcements — all delivered with the assistant's personality.

**Architecture:** Daily cron (1pm) checks each user's feature adoption state and education history. Claude generates a personality-driven tip message when warranted. Three trigger types: onboarding drip (first 2 weeks), re-engagement (feature dormant 14+ days with contextual event), new feature announcement (one-time push to all users). Feature usage tracked via `feature_usage` table updated by existing workflows.

**Tech Stack:** Supabase (PostgreSQL), n8n workflows, Claude Sonnet 4.5, Slack API, Python deployment scripts, `n8n_helpers.py` shared module.

---

### Task 1: Database Migration — `008_feature_education.sql`

**Files:**
- Create: `supabase/migrations/008_feature_education.sql`

**Step 1: Write the migration SQL**

```sql
-- Migration 008: Progressive Feature Education
-- Tracks feature adoption and education delivery history

-- ============================================================
-- Feature Catalog
-- ============================================================
-- Registry of features the assistant can teach users about.

CREATE TABLE feature_catalog (
    id TEXT PRIMARY KEY,                -- e.g. 'dm_conversation', 'meeting_brief', 'backstory'
    display_name TEXT NOT NULL,         -- e.g. 'Ask Me Anything'
    description TEXT NOT NULL,          -- What it does (for Claude to rephrase)
    how_to_use TEXT NOT NULL,           -- Command or trigger (e.g. "Just DM me a question")
    category TEXT NOT NULL              -- 'core', 'productivity', 'customization'
        CHECK (category IN ('core', 'productivity', 'customization')),
    drip_order INTEGER,                 -- NULL = not part of onboarding drip; 1-5 = drip sequence
    drip_day INTEGER,                   -- Day after onboarding to send (e.g. 1, 2, 3, 5, 10)
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- Feature Usage Tracking
-- ============================================================
-- One row per user per feature. Updated on first/subsequent use.

CREATE TABLE feature_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    feature_id TEXT NOT NULL REFERENCES feature_catalog(id),
    first_used_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    use_count INTEGER NOT NULL DEFAULT 1,
    UNIQUE(user_id, feature_id)
);

CREATE INDEX idx_feature_usage_user ON feature_usage(user_id);

-- ============================================================
-- Education Log
-- ============================================================
-- Every tip/announcement sent. Used for dedup + pacing.

CREATE TABLE education_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    feature_id TEXT NOT NULL REFERENCES feature_catalog(id),
    trigger_type TEXT NOT NULL           -- 'onboarding_drip', 're_engagement', 'announcement'
        CHECK (trigger_type IN ('onboarding_drip', 're_engagement', 'announcement')),
    message_text TEXT,                   -- What was actually sent
    slack_message_ts TEXT,
    slack_channel_id TEXT,
    delivered_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_education_log_user ON education_log(user_id, delivered_at DESC);
CREATE INDEX idx_education_log_dedup ON education_log(user_id, feature_id, trigger_type);

-- ============================================================
-- User preferences columns
-- ============================================================

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS tips_enabled BOOLEAN DEFAULT TRUE;

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS announcements_enabled BOOLEAN DEFAULT TRUE;

COMMENT ON COLUMN users.tips_enabled IS 'Whether onboarding drip and re-engagement tips are enabled (stop tips)';
COMMENT ON COLUMN users.announcements_enabled IS 'Whether new feature announcements are enabled (stop announcements)';

-- ============================================================
-- Seed: Feature Catalog
-- ============================================================

INSERT INTO feature_catalog (id, display_name, description, how_to_use, category, drip_order, drip_day) VALUES
('dm_conversation', 'Ask Me Anything',
 'Ask questions about any account, deal, or contact directly in DM — I''ll pull live data from Backstory.',
 'Just DM me a question like "what''s happening with AMD?"',
 'core', 1, 1),

('meeting_brief', 'Meeting Briefs',
 'Get a contextual briefing before customer meetings — engagement history, open deals, key contacts.',
 'Type "brief" or I''ll auto-send one 2 hours before your meetings.',
 'core', 2, 2),

('backstory', 'Backstory (/bs)',
 'Ask me about any account from any Slack channel using the /bs slash command.',
 'Type "/bs what''s the latest with Nvidia?" in any channel.',
 'core', 3, 3),

('persona', 'Personality Customization',
 'Customize how I communicate — casual, formal, witty, data-driven, whatever suits you.',
 'Type "persona casual and witty" or "persona formal and data-driven".',
 'customization', 4, 5),

('followup_draft', 'Follow-up Drafts',
 'After customer meetings, I''ll offer to draft a follow-up email based on the meeting context.',
 'I''ll prompt you after meetings — just click "Draft Follow-up" when you see it.',
 'productivity', 5, 7);

-- Non-drip features (for re-engagement only)
INSERT INTO feature_catalog (id, display_name, description, how_to_use, category) VALUES
('rename', 'Rename Me',
 'Change my display name to whatever you want.',
 'Type "rename Luna" or whatever name you prefer.',
 'customization'),

('emoji', 'Change My Emoji',
 'Change the emoji that appears with my messages.',
 'Type "emoji :star:" or any emoji you like.',
 'customization'),

('digest', 'Morning Digest',
 'Your daily pipeline briefing delivered every morning at 6am.',
 'It''s automatic! Type "stop digest" to pause or "resume digest" to restart.',
 'core'),

('silence_alerts', 'Silence Alerts',
 'I''ll warn you when key accounts go quiet — no emails, meetings, or calls for extended periods.',
 'Automatic — I''ll DM you when I detect engagement gaps.',
 'productivity'),

('stakeholders', 'Stakeholder Map',
 'See who''s engaged on a deal and who you need to reach.',
 'Type "stakeholders" followed by a deal or account name.',
 'productivity'),

('insights', 'Pipeline Insights',
 'Deep analysis of your pipeline health, deal velocity, and risk areas.',
 'Type "insights" for a full pipeline analysis.',
 'productivity'),

('focus', 'Digest Focus',
 'Focus your morning digest on specific accounts or themes.',
 'Type "focus AMD, Nvidia" to prioritize those accounts.',
 'customization');
```

**Step 2: Verify syntax**

User runs the SQL in Supabase SQL editor. Verify tables created:
- `feature_catalog` (12 rows)
- `feature_usage` (empty)
- `education_log` (empty)
- `users` has `tips_enabled` and `announcements_enabled` columns

---

### Task 2: Feature Education Cron Workflow

**Files:**
- Create: `scripts/create_feature_education_cron.py`
- Output: `n8n/workflows/Feature Education Cron.json`

**Pattern:** Follow `create_silence_monitor.py` — new cron workflow using `n8n_helpers.py`.

**Workflow: 16 nodes**

```
Daily 1pm PT → Get Active Users → Get Education History → Get Feature Usage
→ Prepare Education Batch → Split In Batches → [loop]
→ Pick Feature & Build Prompt → Has Tip? (IF)
→ [true] Education Agent (Claude + system prompt) → Open Bot DM → Send Tip DM → Log Education
→ [loop back to Split]
→ [false] → [loop back to Split]
```

**Step 1: Write the script**

The script should use `from n8n_helpers import *` and follow these patterns:

**Node 1 — Schedule Trigger:** Daily at 1pm PT (13:00), weekdays only.

```python
{
    "parameters": {
        "rule": {
            "interval": [{
                "triggerAtHour": 13,
                "triggerAtMinute": 0,
                "triggerAtDay": [1, 2, 3, 4, 5],
            }]
        },
    },
    "name": "Daily 1pm PT",
    "type": NODE_SCHEDULE_TRIGGER,
    "typeVersion": 1.2,
}
```

**Node 2 — Get Active Users:** Supabase HTTP GET for complete users with tips/announcements prefs.
```
GET /rest/v1/users?onboarding_state=eq.complete&select=id,slack_user_id,email,assistant_name,assistant_emoji,assistant_persona,organization_id,onboarding_state,tips_enabled,announcements_enabled,created_at
```

**Node 3 — Get Education History:** Supabase HTTP GET for recent education log (last 30 days).
```
GET /rest/v1/education_log?delivered_at=gte.={{ new Date(Date.now() - 30*24*60*60*1000).toISOString() }}&select=user_id,feature_id,trigger_type,delivered_at
```

**Node 4 — Get Feature Usage:** Supabase HTTP GET all feature usage.
```
GET /rest/v1/feature_usage?select=user_id,feature_id,first_used_at,last_used_at,use_count
```

**Node 5 — Get Feature Catalog:** Supabase HTTP GET all features.
```
GET /rest/v1/feature_catalog?select=*&order=drip_order.asc.nullslast
```

**Node 6 — Prepare Education Batch (Code node):**

```javascript
const usersRaw = $('Get Active Users').first().json;
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
```

**Node 7 — Split In Batches:** Standard v3, output 1 = loop.

**Node 8 — Pick Feature & Build Prompt (Code node):**

This is the core logic that decides WHAT to educate about:

```javascript
const data = $input.first().json;
if (data.skip) {
  return [{ json: { ...data, hasTip: false } }];
}

const now = new Date();
const userAge = Math.floor((now - new Date(data.userCreatedAt)) / (24*60*60*1000)); // days
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

const lastTip = history.length > 0
  ? Math.min(...history.map(h => (now - new Date(h.delivered_at)) / (24*60*60*1000)))
  : Infinity;
if (lastTip < 3) {
  return [{ json: { ...data, hasTip: false } }];
}

// Set of features already educated about (by trigger type)
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
    if (!featureUsage) continue; // Never used = not re-engagement
    const daysSinceUse = (now - new Date(featureUsage.last_used_at)) / (24*60*60*1000);
    if (daysSinceUse >= 14 && !educatedReengagement.has(feature.id)) {
      // Don't re-engage on features that were only used once long ago
      // (they may have tried it and decided it's not for them)
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

// Build Claude prompt
const persona = data.assistantPersona || 'friendly and helpful';
const systemPrompt = `You are ${data.assistantName}, a sales assistant with the following personality: ${persona}.

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

Trigger type: ${triggerType === 're_engagement' ? 'Re-engagement — they used this before but haven\'t recently' : 'Onboarding — they haven\'t tried this yet'}

Write ONLY the message text. No subject line, no preamble.`;

return [{
  json: {
    ...data,
    hasTip: true,
    selectedFeatureId: selectedFeature.id,
    selectedFeatureName: selectedFeature.display_name,
    triggerType: triggerType,
    tipSystemPrompt: systemPrompt,
    tipUserPrompt: `Write a tip about ${selectedFeature.display_name} for this user.`,
  }
}];
```

**Node 9 — Has Tip? (IF node):** `$json.hasTip === true`

**Nodes 10-12 — Education Agent trio:** Claude Sonnet 4.5, NO MCP tools needed (tips don't require live data).

Actually, remove the MCP node — tips are just personality-driven messages, no Backstory data needed. Use a simpler approach:

**Node 10 — Education Agent (Agent node, no MCP):**
- System prompt: `={{ $json.tipSystemPrompt }}`
- User prompt: `={{ $json.tipUserPrompt }}`
- Sub-nodes: Anthropic Chat Model only (no MCP)

**Node 11 — Anthropic Chat Model (Education):** Claude Sonnet 4.5.

**Node 12 — Open Bot DM:** `conversations.open` with user's Slack ID.

**Node 13 — Send Tip DM:**
```json
{
  "channel": "{{ $json.channel.id }}",
  "text": "{{ $('Education Agent').first().json.output }}",
  "username": "{{ $('Pick Feature & Build Prompt').first().json.assistantName }}",
  "icon_emoji": "{{ $('Pick Feature & Build Prompt').first().json.assistantEmoji }}"
}
```

**Node 14 — Prepare Education Log (Code):**
```javascript
const data = $('Pick Feature & Build Prompt').first().json;
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
```

**Node 15 — Log Education (HTTP POST to Supabase):**
```
POST /rest/v1/education_log
Body: {{ JSON.stringify($json) }}
```

**Node 16 — (Loop back):** Log Education → Split In Batches. Has Tip? false → Split In Batches.

**Step 2: Run the script**

```bash
N8N_API_KEY=$N8N_API_KEY python3 scripts/create_feature_education_cron.py
```

Expected: Workflow created, activated, synced locally.

**Step 3: Commit**

```bash
git add supabase/migrations/008_feature_education.sql scripts/create_feature_education_cron.py
git commit -m "feat: add feature education cron with adoption tracking"
```

---

### Task 3: Add `stop tips` / `stop announcements` Commands to Events Handler

**Files:**
- Create: `scripts/add_education_commands.py`
- Modify: `n8n/workflows/Slack Events Handler.json` (synced after push)

**Pattern:** Follow `add_stakeholders_and_followup.py` — modify Route by State code to recognize new commands, then handle them in the existing cmd_other flow.

**Step 1: Write the script**

The script modifies the live Events Handler workflow:

1. **Update Route by State code** — add recognition for:
   - `stop tips` / `pause tips` → `subRoute = 'stop_tips'`
   - `resume tips` / `start tips` → `subRoute = 'resume_tips'`
   - `stop announcements` → `subRoute = 'stop_announcements'`
   - `resume announcements` / `start announcements` → `subRoute = 'resume_announcements'`

2. **Update Build DM System Prompt** — add the new commands to the available commands list in the system prompt (so the DM conversation agent knows about them).

3. **Update Is Conversational? node** — ensure `stop_tips`, `resume_tips`, `stop_announcements`, `resume_announcements` route to Build Help Response (not the DM agent).

4. **Update Build Help Response** — add handling for:
   - `stop_tips` → Update `tips_enabled = false` in Supabase, confirm
   - `resume_tips` → Update `tips_enabled = true`, confirm
   - `stop_announcements` → Update `announcements_enabled = false`, confirm
   - `resume_announcements` → Update `announcements_enabled = true`, confirm

Since Build Help Response already handles `stop_digest` / `resume_digest` via Supabase update nodes, the same pattern applies. We need to add 4 new Supabase update nodes + confirmation message sends.

Actually — looking at the existing pattern more carefully: `stop_digest` and `resume_digest` are handled by the existing Build Help Response Code node which outputs different confirmation text, then a single "Send Confirmation" HTTP node sends it. The Supabase update is done by separate nodes.

**Simpler approach:** Add the new subRoutes to the Is Conversational? false path. The Build Help Response code node already switches on subRoute — extend it to handle the new commands. Add corresponding Supabase update HTTP nodes.

**Actual simplest approach:** Since these are simple DB toggles + confirmation, handle them the same way `stop_digest`/`resume_digest` work in the existing flow. Extend the Build Help Response code to output the right confirmation text AND a `dbUpdate` field, then add an IF node + Supabase HTTP update after it.

Wait — let me look at the existing flow more carefully. The `stop_digest`/`resume_digest` likely already has DB update nodes. Let me plan to just extend the same pattern:

1. Route by State recognizes the commands → sets subRoute
2. Is Conversational? passes them to false path (Build Help Response)
3. Build Help Response outputs confirmation text + DB fields to update
4. Existing update nodes handle the DB write

The Build Help Response code node should handle producing the right output for each subRoute. Any new DB update patterns can reuse the existing Supabase update HTTP nodes if they follow the same field update pattern, or add new ones if needed.

**Step 2: Run the script**

```bash
N8N_API_KEY=$N8N_API_KEY python3 scripts/add_education_commands.py
```

**Step 3: Test**

DM the bot: `stop tips` → should confirm tips are paused
DM the bot: `resume tips` → should confirm tips are resumed
DM the bot: `help` → should still work

**Step 4: Commit**

```bash
git add scripts/add_education_commands.py
git commit -m "feat: add stop/resume tips and announcements commands"
```

---

### Task 4: Add Feature Usage Tracking to Existing Workflows

**Files:**
- Create: `scripts/add_feature_usage_tracking.py`

**Purpose:** When users use features, upsert a row in `feature_usage`. This enables the education cron to know what features each user has tried.

**Features to track and where:**

| Feature ID | Workflow | Trigger Point |
|-----------|----------|---------------|
| `dm_conversation` | Events Handler | After DM Conversation Agent responds |
| `meeting_brief` | Events Handler | After `brief` command is processed |
| `backstory` | Backstory SlackBot | After agent responds |
| `followup_draft` | Interactive Events Handler | After followup_draft button clicked |
| `persona` | Events Handler | After persona command processed |
| `rename` | Events Handler | After rename command processed |
| `emoji` | Events Handler | After emoji command processed |
| `digest` | Sales Digest | After digest sent to user |
| `stakeholders` | Events Handler | After stakeholders subRoute processed |
| `insights` | Events Handler | After insights command processed |
| `focus` | Events Handler | After focus command processed |

**Implementation approach:** For each workflow, add a single HTTP POST node after the feature is used that calls a Supabase RPC function or does an upsert.

**Supabase upsert for feature_usage:**

Add a PostgreSQL function in the migration (Task 1) that handles the upsert:

```sql
CREATE OR REPLACE FUNCTION track_feature_usage(p_user_id UUID, p_feature_id TEXT)
RETURNS void AS $$
BEGIN
  INSERT INTO feature_usage (user_id, feature_id, first_used_at, last_used_at, use_count)
  VALUES (p_user_id, p_feature_id, NOW(), NOW(), 1)
  ON CONFLICT (user_id, feature_id)
  DO UPDATE SET last_used_at = NOW(), use_count = feature_usage.use_count + 1;
END;
$$ LANGUAGE plpgsql;
```

Then each tracking node is a simple HTTP POST:
```
POST /rest/v1/rpc/track_feature_usage
Body: { "p_user_id": "{{ userId }}", "p_feature_id": "feature_id" }
```

**Phase this:** Start by tracking the 3 most impactful features for education:
1. `dm_conversation` (drip tip #1)
2. `meeting_brief` (drip tip #2)
3. `backstory` (drip tip #3)

Add tracking for remaining features in a follow-up.

**Step 1: Add the RPC function to migration 008**

Include `track_feature_usage` function in the migration SQL from Task 1.

**Step 2: Write the tracking script**

The script modifies 3 workflows:
- **Events Handler**: Add tracking node after DM Conversation Agent response and after `brief` command
- **Backstory SlackBot**: Add tracking node after agent response

Each tracking node is a simple HTTP POST with `continueOnFail: true` (tracking should never break the main flow).

**Step 3: Run and commit**

```bash
N8N_API_KEY=$N8N_API_KEY python3 scripts/add_feature_usage_tracking.py
git add scripts/add_feature_usage_tracking.py
git commit -m "feat: track feature usage for education system"
```

---

### Task 5: Verify End-to-End

**Step 1: Run migration 008 in Supabase**

User runs `008_feature_education.sql` in Supabase SQL editor.

**Step 2: Deploy all scripts**

```bash
N8N_API_KEY=$N8N_API_KEY python3 scripts/create_feature_education_cron.py
N8N_API_KEY=$N8N_API_KEY python3 scripts/add_education_commands.py
N8N_API_KEY=$N8N_API_KEY python3 scripts/add_feature_usage_tracking.py
```

**Step 3: Manual test**

1. Check n8n: Feature Education Cron is active, scheduled for 1pm PT
2. DM the bot: `stop tips` → confirms tips paused
3. DM the bot: `resume tips` → confirms tips resumed
4. DM the bot: `help` → still works
5. Use a feature (e.g., DM a question) → check `feature_usage` table has a row
6. Manually trigger the Education Cron in n8n → verify it picks a feature and sends a tip

**Step 4: Final commit**

```bash
git add -A
git commit -m "feat: progressive feature education system — cron, commands, tracking"
```

---

## Summary of Deliverables

| Deliverable | Type | Description |
|-------------|------|-------------|
| `008_feature_education.sql` | Migration | feature_catalog, feature_usage, education_log tables + user prefs columns + track_feature_usage RPC |
| `create_feature_education_cron.py` | Script | New 16-node cron workflow: daily 1pm, personality-driven tips |
| `add_education_commands.py` | Script | Adds stop/resume tips/announcements to Events Handler |
| `add_feature_usage_tracking.py` | Script | Adds usage tracking to Events Handler, Backstory, Interactive Handler |
| `Feature Education Cron.json` | Workflow | Synced n8n workflow JSON |

## Pacing Rules (embedded in Pick Feature logic)

- Max 2 tips per week per user
- Min 3 days between tips
- Onboarding drip: days 1, 2, 3, 5, 7 (only if feature unused)
- Re-engagement: feature unused 14+ days AND use_count >= 3
- `stop tips` disables drip + re-engagement
- `stop announcements` disables announcements (separate control)
- Announcements: not yet implemented (will be a manual trigger script when we ship new features)
