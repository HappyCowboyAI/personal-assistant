# Slack Formatting Guide for n8n Workflows
## Reference for Claude Code — Backstory Personal Assistant

> This document defines all formatting rules, Block Kit patterns, best practices, and image handling for building visually compelling Slack messages in n8n. Always follow these guidelines when generating or modifying n8n workflow JSON or Slack message payloads.

---

## The Core Problem This Document Solves

The n8n Langchain agent outputs a plain text string via `$json.output`. If that string is passed directly into the `text` field of `chat.postMessage`, it renders as a flat wall of text with no visual hierarchy — regardless of how well Claude formatted it internally.

**The solution:** instruct the agent to output a JSON Block Kit payload as a string, then parse it in a Code node before sending. This is the pattern all workflows in this project should follow.

---

## Architecture: Text vs Block Kit

### What the current workflow does (flat, uncompelling)

```json
{
  "channel": "{{ channelId }}",
  "text": "{{ $json.output }}",
  "username": "ScottAI",
  "icon_emoji": ":robot_face:"
}
```

The agent's text output — even with `*bold*` and bullets — renders with almost no visual structure in Slack.

### What it should do (structured, visual, compelling)

```json
{
  "channel": "{{ channelId }}",
  "text": "Your morning pipeline briefing",
  "username": "ScottAI",
  "icon_emoji": ":robot_face:",
  "blocks": [ ...parsed from agent JSON output... ]
}
```

The `text` field becomes a notification fallback only. All visual content lives in `blocks`.

---

## n8n Workflow Pattern for Block Kit

### Step 1 — Update the agent system prompt

Tell the agent to output valid Block Kit JSON, not prose. Add this to the system prompt in the **Resolve Identity** code node:

```
CRITICAL OUTPUT FORMAT:
You must respond with ONLY a valid JSON object — no prose, no explanation, no markdown code fences.
The JSON must have this exact shape:
{
  "notification_text": "One-line preview for mobile notifications",
  "blocks": [ ...array of valid Slack Block Kit blocks... ]
}

Do not wrap in backticks. Do not add any text before or after the JSON object.
```

### Step 2 — Add a Parse Blocks code node

Insert a Code node between Digest Agent and Send Digest:

```javascript
// Parse Blocks node
const agentOutput = $('Digest Agent').first().json.output;

let parsed;
try {
  // Strip any accidental markdown fences if the model adds them
  const cleaned = agentOutput
    .replace(/^```json\s*/i, '')
    .replace(/^```\s*/i, '')
    .replace(/```\s*$/i, '')
    .trim();
  parsed = JSON.parse(cleaned);
} catch (e) {
  // Fallback: wrap raw text in a single section block
  parsed = {
    notification_text: "Your morning briefing is ready",
    blocks: [
      {
        type: "section",
        text: { type: "mrkdwn", text: agentOutput }
      }
    ]
  };
}

return [{
  json: {
    notificationText: parsed.notification_text || "Your morning briefing",
    blocks: JSON.stringify(parsed.blocks)
  }
}];
```

### Step 3 — Update the Send Digest HTTP Request node

```json
{
  "channel": "{{ $('Open Bot DM').first().json.channel.id }}",
  "text": "{{ $('Parse Blocks').first().json.notificationText }}",
  "username": "{{ $('Resolve Identity').first().json.assistantName }}",
  "icon_emoji": "{{ $('Resolve Identity').first().json.assistantEmoji }}",
  "blocks": "={{ $('Parse Blocks').first().json.blocks }}",
  "unfurl_links": false,
  "unfurl_media": false
}
```

---

## HTTP Request Node Configuration

### Base Setup (applies to all Slack API calls)

```
Method: POST
URL: https://slack.com/api/chat.postMessage
Authentication: Header Auth
  Header Name: Authorization
  Header Value: Bearer xoxb-your-bot-token
Content-Type: application/json
```

### Always Include These Fields

| Field | Purpose |
|-------|---------|
| `channel` | Channel ID or DM channel ID from `conversations.open` |
| `text` | Notification fallback — shown in push notifications, lock screen, and message previews. Never leave blank. |
| `username` | Overrides the bot display name per message — this is how each rep sees their named assistant |
| `icon_emoji` | Overrides the bot avatar per message — use the emoji the rep chose during onboarding |
| `unfurl_links: false` | Prevents Slack from expanding URLs into link previews — keeps messages clean |
| `blocks` | The actual visual content — always use this for structured output |

---

## Slack mrkdwn Reference

Slack uses its own markdown dialect called mrkdwn. Standard markdown does NOT work.

### What Works in mrkdwn

```
*bold text*              → bold (single asterisks only)
_italic text_            → italic
~strikethrough~          → strikethrough
`inline code`            → monospace
> blockquote             → indented quote block
• bullet item            → bullet point (paste the • character directly)
<https://url|link text>  → hyperlink with custom display text
<@U0123456789>           → mention a specific user by Slack ID
<!here>                  → @here mention
<!channel>               → @channel mention
:emoji_name:             → Slack emoji
\n                       → line break (use \n in JSON strings)
```

### What Does NOT Work

```
**bold**                 → use *bold* instead
# Heading                → use a header block instead
## Subheading            → use bold text on its own line instead
[text](url)              → use <url|text> instead
- bullet                 → use the • character instead
1. numbered list         → use rich_text block instead
---                      → use a divider block instead
```

### Line Breaks and Spacing

In JSON strings, use `\n` for line breaks and `\n\n` for a blank line between paragraphs. Never use `<br>`.

```json
{
  "type": "mrkdwn",
  "text": "*Salesforce — Negotiation*\n$142,000 • Close: Mar 31\n\nEngagement dropped 12 points this week."
}
```

---

## Block Kit Blocks Reference

### header — Large Bold Title

Use at the top of each message. Limited to plain text only — no mrkdwn formatting inside header blocks.

```json
{
  "type": "header",
  "text": {
    "type": "plain_text",
    "text": "☀️ Monday Morning Brief — ScottAI",
    "emoji": true
  }
}
```

### section — Main Content Block

The workhorse block. Supports mrkdwn. Optional right-aligned accessory element.

```json
{
  "type": "section",
  "text": {
    "type": "mrkdwn",
    "text": "*The Lead*\nSalesforce procurement is moving faster than expected — legal review self-initiated. Push for March close."
  }
}
```

### section with fields — Two-Column Layout

Use for deal metrics, key-value pairs, and quick stats. Renders as a two-column grid left to right. Maximum 10 fields per block — always use an even number for clean alignment.

```json
{
  "type": "section",
  "fields": [
    { "type": "mrkdwn", "text": "*Amount*\n$142,000" },
    { "type": "mrkdwn", "text": "*Close Date*\nMarch 31, 2026" },
    { "type": "mrkdwn", "text": "*Stage*\nNegotiation" },
    { "type": "mrkdwn", "text": "*Engagement*\n🔥 82 / 100" }
  ]
}
```

### section with accessory — Right-Aligned Image or Button

```json
{
  "type": "section",
  "text": {
    "type": "mrkdwn",
    "text": "*Salesforce*\nEngagement rising — up 14 points this week"
  },
  "accessory": {
    "type": "image",
    "image_url": "https://yourdomain.com/icons/rising.png",
    "alt_text": "Rising engagement"
  }
}
```

### divider — Visual Separator

```json
{
  "type": "divider"
}
```

Use between major sections. Maximum 2 dividers per message — overuse makes messages feel choppy.

### context — Small Secondary Text

Use for timestamps, metadata, and source attribution. Renders in small gray text. Supports both text and image elements side by side.

```json
{
  "type": "context",
  "elements": [
    {
      "type": "mrkdwn",
      "text": "Backstory intelligence • Generated at 6:02 AM PT • Monday, Feb 23, 2026"
    }
  ]
}
```

With an inline icon:

```json
{
  "type": "context",
  "elements": [
    {
      "type": "image",
      "image_url": "https://yourdomain.com/icons/peopleai-16.png",
      "alt_text": "Backstory"
    },
    {
      "type": "mrkdwn",
      "text": "Powered by Backstory intelligence"
    }
  ]
}
```

### actions — Buttons

Use for approve/reject flows and quick actions. Each element is a button inside the actions block.

```json
{
  "type": "actions",
  "elements": [
    {
      "type": "button",
      "text": { "type": "plain_text", "text": "✅ Send Follow-Up", "emoji": true },
      "style": "primary",
      "value": "approve_followup_opp_123",
      "action_id": "approve_followup"
    },
    {
      "type": "button",
      "text": { "type": "plain_text", "text": "✏️ Edit Draft", "emoji": true },
      "value": "edit_followup_opp_123",
      "action_id": "edit_followup"
    },
    {
      "type": "button",
      "text": { "type": "plain_text", "text": "View in CRM", "emoji": true },
      "url": "https://yourcrm.com/opportunity/123",
      "action_id": "view_crm"
    }
  ]
}
```

Button styles: `primary` (green), `danger` (red), or omit for default gray.

### image — Standalone Full-Width Image

Use for charts, pipeline snapshots, or visual summaries. The image must be a publicly accessible HTTPS URL.

```json
{
  "type": "image",
  "image_url": "https://yourdomain.com/charts/pipeline-snapshot.png",
  "alt_text": "Pipeline engagement chart",
  "title": {
    "type": "plain_text",
    "text": "Engagement Trend — Last 30 Days"
  }
}
```

---

## Image Handling

### How Images Work in Slack Block Kit

Slack does not accept uploaded image files via the Blocks API. All images must be publicly accessible HTTPS URLs — Slack's servers fetch the image at render time.

There are three image contexts in Block Kit:

| Context | Block Type | Rendered Size | Use For |
|---------|------------|---------------|---------|
| Standalone image | `image` block | Full message width | Charts, snapshots, visual summaries |
| Right-aligned thumbnail | `section` accessory | ~75×75px | Deal status icons, avatars |
| Inline icon | `context` element | ~16×16px | Logos, source attribution |

### Option 1 — Static Hosted Icons (Recommended for v1)

Host a small set of status icons on a public URL (S3, GitHub raw content, or your own domain). Reference by URL in blocks. Suggested icon set for the digest:

```
/icons/rising.png     → green upward arrow (engagement rising)
/icons/falling.png    → red downward arrow (engagement falling)
/icons/stable.png     → gray horizontal arrow (no change)
/icons/alert.png      → orange warning triangle (risk flagged)
/icons/star.png       → blue star (hidden upside)
/icons/rocket.png     → navy rocket (acceleration)
/icons/clock.png      → gray clock (stalled)
```

### Option 2 — Dynamically Generated Charts via QuickChart.io

QuickChart.io is a free charting API that returns a public image URL — perfect for pipeline snapshots. Use in a Code node before building your blocks:

```javascript
const chartConfig = {
  type: 'bar',
  data: {
    labels: ['Salesforce', 'Google', 'Adobe', 'Workday'],
    datasets: [{
      label: 'Engagement Score',
      data: [82, 61, 45, 78],
      backgroundColor: ['#012C48', '#6296AD', '#D04911', '#012C48']
    }]
  },
  options: {
    plugins: { legend: { display: false } },
    scales: { y: { min: 0, max: 100 } }
  }
};

const encoded = encodeURIComponent(JSON.stringify(chartConfig));
const chartUrl = `https://quickchart.io/chart?c=${encoded}&w=600&h=200&bkg=white`;

return [{ json: { chartUrl } }];
```

Then reference in a blocks image block:

```json
{
  "type": "image",
  "image_url": "{{ $('Generate Chart').first().json.chartUrl }}",
  "alt_text": "Engagement scores by account"
}
```

### Option 3 — Emoji as Lightweight Visual Indicators

For simple status signals, emoji in mrkdwn text is the most reliable approach and requires no hosting. Use these consistently so reps learn the visual language quickly:

```
🔴  Stalled / critical risk
⚠️  Risk pattern detected
💎  Hidden upside opportunity
🚀  Acceleration / strong momentum
✅  Healthy / on track
📈  Engagement rising
📉  Engagement falling
➡️  Engagement stable
🔥  High engagement (80+)
💀  No activity in 30+ days
```

---

## Complete Message Templates

### Morning Digest — Full Block Kit Structure

This is the target output the agent should produce. Instruct Claude to output JSON in this exact shape:

```json
{
  "notification_text": "Your Monday morning brief — 3 deals need attention today",
  "blocks": [
    {
      "type": "header",
      "text": {
        "type": "plain_text",
        "text": "☀️ Monday Brief — ScottAI",
        "emoji": true
      }
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*The Lead*\nSalesforce procurement moved faster than expected — legal self-initiated review overnight. This is your best shot at a March close. Get in front of it today."
      }
    },
    {
      "type": "divider"
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*Today's Priorities*\n\n🚀 *Salesforce* — Follow up with Sarah Chen on legal timeline. She self-initiated the review; strike while momentum is high.\n\n⚠️ *Google Cloud* — Marcus Webb hasn't responded in 11 days. Champion risk. Draft a re-engagement before end of day.\n\n💎 *Adobe* — POC ended strong. Ask about the EMEA team — expansion is the move."
      }
    },
    {
      "type": "divider"
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*Pipeline Pulse*"
      }
    },
    {
      "type": "section",
      "fields": [
        { "type": "mrkdwn", "text": "📈 *Salesforce*\n82 → 94 (+12)" },
        { "type": "mrkdwn", "text": "📉 *Google Cloud*\n71 → 59 (−12)" },
        { "type": "mrkdwn", "text": "➡️ *Adobe*\n78 → 79 (flat)" },
        { "type": "mrkdwn", "text": "🔴 *Workday*\n34 → 31 (stalling)" }
      ]
    },
    {
      "type": "divider"
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*One Thing I'm Watching*\nWorkday has been in Proposal stage for 47 days with a 31 engagement score and no meetings in 5 weeks. Worth a direct call to the sponsor — or a hard conversation about whether this belongs in the forecast."
      }
    },
    {
      "type": "context",
      "elements": [
        {
          "type": "mrkdwn",
          "text": "Backstory intelligence • Monday, Feb 23, 2026 • 6:02 AM PT"
        }
      ]
    }
  ]
}
```

### Deal Alert — Single Opportunity Risk Flag

```json
{
  "notification_text": "⚠️ Risk detected on Google Cloud deal",
  "blocks": [
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "⚠️ *Risk Detected — Google Cloud*\nMarcus Webb (your champion) hasn't engaged in 11 days. Engagement dropped from 71 to 59."
      }
    },
    {
      "type": "section",
      "fields": [
        { "type": "mrkdwn", "text": "*Amount*\n$218,000" },
        { "type": "mrkdwn", "text": "*Close Date*\nApril 15, 2026" },
        { "type": "mrkdwn", "text": "*Stage*\nProposal" },
        { "type": "mrkdwn", "text": "*Last Activity*\n11 days ago" }
      ]
    },
    {
      "type": "actions",
      "elements": [
        {
          "type": "button",
          "text": { "type": "plain_text", "text": "✉️ Draft Re-Engagement", "emoji": true },
          "style": "primary",
          "value": "draft_reengagement_google_cloud",
          "action_id": "draft_reengagement"
        },
        {
          "type": "button",
          "text": { "type": "plain_text", "text": "View in CRM", "emoji": true },
          "url": "https://yourcrm.com/opportunity/456",
          "action_id": "view_crm"
        }
      ]
    }
  ]
}
```

---

## Agent Prompt Instructions for Block Kit Output

Include this block in every agent system prompt (in the Resolve Identity code node) to ensure clean Block Kit JSON output:

```
OUTPUT FORMAT — CRITICAL:
Respond with ONLY a valid JSON object. No prose. No explanation. No markdown code fences (no backticks).

Your response must have exactly this shape:
{
  "notification_text": "string — one sentence, shown in push notifications",
  "blocks": [ array of valid Slack Block Kit blocks ]
}

BLOCK KIT STRUCTURE RULES:
- Use a "header" block for the message title
- Use "section" blocks for all body content
- Use "divider" blocks between major sections (maximum 2 per message)
- Use "section" with "fields" for two-column data (metrics, scores, dates)
- Use "context" block at the bottom for timestamp and data source
- Use "actions" block only when the rep needs to take a specific action

MRKDWN RULES (inside all text fields):
- Bold: *text* — single asterisks only
- Italic: _text_
- Line break: \n
- Blank line: \n\n
- Bullet points: use the • character on its own line
- Links: <https://url|display text>
- NO ##headers — use *bold text* on its own line instead
- NO **double asterisks**
- NO standard markdown links [text](url)
- NO dash bullets

EMOJI STATUS INDICATORS — use these consistently:
🚀 Acceleration / strong momentum
⚠️ Risk pattern detected
💎 Hidden upside opportunity
🔴 Stalled / critical risk
✅ Healthy / on track
📈 Engagement rising
📉 Engagement falling
➡️ Engagement stable
🔥 High engagement (80+)
```

---

## Common Mistakes to Avoid

**Sending agent output directly to the `text` field**
Always parse the agent's JSON output and pass the `blocks` array to the blocks field. The `text` field is for notification previews only.

**Using standard markdown in mrkdwn**
`**bold**`, `# heading`, `[text](url)`, and `- bullets` do not render in Slack. Use `*bold*`, header blocks, `<url|text>`, and `•` character bullets.

**Forgetting the `text` notification fallback**
Slack uses `text` for push notifications, mobile previews, and accessibility. Always include it even when blocks are present.

**Nesting blocks inside other blocks**
Blocks cannot be nested. Each block is a flat item in the top-level `blocks` array.

**Using the image block for small icons**
For small status icons, use the `context` block's image element or a section accessory. The standalone `image` block is for full-width visuals only.

**Images behind authentication or on localhost**
Slack fetches images from your URL at render time. Always use public HTTPS URLs. Private network images will not load.

**Exceeding 50 blocks per message**
Slack enforces a maximum of 50 blocks per message. Summarize aggressively or split into multiple messages.

**Empty or malformed JSON from the agent**
Always wrap JSON parsing in a try/catch with a plain text fallback (see Parse Blocks node pattern above). This prevents workflow failures when the model occasionally outputs imperfect JSON.

---

## Quick Reference Card

```
ENDPOINT:   POST https://slack.com/api/chat.postMessage
AUTH:       Authorization: Bearer xoxb-your-bot-token

REQUIRED FIELDS:
  channel         DM channel ID from conversations.open
  text            Notification fallback — never blank
  username        Assistant name (e.g. "ScottAI")
  icon_emoji      Assistant emoji (e.g. ":robot_face:")
  blocks          Block Kit JSON array
  unfurl_links    false
  unfurl_media    false

RECOMMENDED BLOCK ORDER (digest):
  1. header              — message title
  2. section             — lead insight
  3. divider
  4. section             — priorities (bullets)
  5. divider
  6. section             — pipeline pulse label
  7. section + fields    — two-column engagement scores
  8. divider
  9. section             — one thing watching
  10. context            — timestamp + source

MRKDWN CHEATSHEET:
  *bold*    _italic_    ~strike~    `code`
  > quote   • bullet    <url|text>  :emoji:
  \n = line break    \n\n = paragraph break
```

---

*This is a living reference document — update it as new patterns are discovered.*
