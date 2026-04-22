"""
Fix: Apply two-layer Query API + MCP pattern to the Follow-up Cron draft path.

The Follow-up Cron already uses Query API for meeting discovery and passes
meeting context (accountName, meetingSubject, participants) through the
button payload. But the Interactive Handler's Build Followup Context prompt
doesn't have the DATA LATENCY PROTOCOL — if MCP returns no transcript data,
the agent should still draft using the Query API context rather than failing.

This updates Build Followup Context in the Interactive Events Handler to:
1. Add DATA LATENCY PROTOCOL (same as on-demand followup)
2. Instruct agent to use the Query API context (title, participants, account)
   as primary meeting identity — MCP is for enrichment only
3. Draft a meaningful email even when MCP has no transcript data yet

Usage:
    N8N_API_KEY=... python scripts/fix_followup_twolayer.py
"""

from n8n_helpers import (
    find_node, fetch_workflow, push_workflow, sync_local,
    WF_INTERACTIVE_HANDLER,
)


NEW_BUILD_FOLLOWUP_CONTEXT = r"""// Extract context from button value and build agent prompt
// Two-layer pattern: Query API context (in button payload) + MCP enrichment
const payload = $('Parse Interactive Payload').first().json;
let context = {};
try {
  context = JSON.parse(payload.actionValue || '{}');
} catch(e) {
  context = {};
}

const accountName = context.accountName || 'the account';
const meetingSubject = context.meetingSubject || '';
const participants = context.participants || '';
const repName = context.repName || 'there';
const assistantName = context.assistantName || 'Aria';
const assistantEmoji = context.assistantEmoji || ':robot_face:';

const meetingSubjectNote = meetingSubject
  ? ` (${meetingSubject})`
  : '';

const todayStr = new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });

let systemPrompt = `You are ${assistantName}, a personal sales assistant for ${repName}.

You have access to Backstory MCP tools for CRM data, account activity, meeting details, and engagement data.

**FOLLOW-UP EMAIL DRAFT MODE**

TODAY IS ${todayStr}. Remember this date — it is critical for determining meeting recency.

## KNOWN MEETING CONTEXT (from Backstory Query API — confirmed data):
- **Account:** ${accountName}
- **Meeting Subject:** ${meetingSubject || '[not available]'}
- **Participants:** ${participants || '[not available]'}

This meeting data comes from the Backstory Query API and is CONFIRMED — the meeting definitely happened. Use this as your primary anchor.

## CRITICAL: DATA LATENCY PROTOCOL
Backstory transcript data takes 3-4 HOURS to appear after a meeting ends.
The meeting above may not have full transcript/notes available via MCP yet.

**YOU MUST FOLLOW THIS PROTOCOL:**
1. Use Backstory MCP tools to search for this meeting and try to get detailed notes, topics, and action items
2. **IF MCP has rich data** (transcript, topics, action items) → Great, use it all to draft a detailed email
3. **IF MCP has limited/no data for this meeting** → This is normal for recent meetings. You still KNOW the meeting happened because of the Query API data above. Draft a meaningful email using:
   - The meeting subject as the anchor topic
   - The account context and relationship history from MCP
   - The participant list for To/CC fields
   - A professional, forward-looking tone referencing "our conversation"
   - Add a note: "_Details from this meeting are still syncing. Reply with key discussion points and I\\'ll make this draft more specific._"
4. **NEVER say you cannot find the meeting** — you have confirmed data above that it happened
5. **NEVER draft based on an older meeting** — the user clicked the button for THIS specific meeting

## DRAFTING INSTRUCTIONS
Use Backstory MCP tools to:
1. Find the specific meeting with ${accountName} — look for notes, topics, action items
2. Extract what was actually discussed (not general deal context)
3. Look up participant emails to personalize the To/CC fields

**CRITICAL:** Anchor the email on THIS specific meeting${meetingSubjectNote}.
- Lead with topics, decisions, and action items from the meeting
- Do NOT pad with generic deal/pipeline context unless it was discussed
- If meeting notes are thin, use the meeting subject and account context to draft a relevant follow-up

**DATE AWARENESS — adjust your follow-up language based on when the meeting was:**
- Same day: "Thanks for the conversation today"
- Yesterday: "Thanks for the conversation yesterday"
- 2-3 days ago: "I wanted to follow up on our conversation from {day}"
- 4-7 days ago: "Circling back on our discussion last {day}"

**FORMAT** (Slack mrkdwn):

:email: *Follow-up Draft — ${accountName}*

*To:* primary recipient ({email@company.com}) — ALWAYS include email address. Use Backstory MCP to look up emails.
*CC:* other meeting participants with emails — internal team and external contacts
*Subject:* concise subject line

---
email body — 150-250 words, professional, references meeting topics, includes clear next step
---

_Reply in this thread to adjust the tone, add details, or ask me to revise._

**RULES:**
- Keep the email 150-250 words
- Reference specific discussion topics from THIS meeting — do NOT fabricate topics
- If MCP data is limited, draft based on the meeting subject and note that details are still syncing
- Include a clear call to action / next step
- Use contact names, not generic "team"
- Tone: professional but warm
- ALWAYS sign the email as ${repName}. Do NOT sign as the account owner or AE — the person requesting the draft is ${repName}.
- Do NOT use ### headers
- Keep under 3000 characters`;

const agentPrompt = `Draft a follow-up email for my meeting with ${accountName}` +
  (meetingSubject ? `. The meeting was about: ${meetingSubject}` : '') +
  (participants ? `. Participants included: ${participants}` : '') +
  `. Today is ${todayStr}.` +
  `\n\nIMPORTANT: Even if MCP tools don't return detailed transcript data for this meeting, you KNOW it happened. Draft based on the meeting subject and account context.`;

return [{
  json: {
    ...payload,
    ...context,
    systemPrompt,
    agentPrompt,
    assistantName,
    assistantEmoji,
    accountName,
  }
}];
"""


def main():
    print(f"Fetching Interactive Handler {WF_INTERACTIVE_HANDLER}...")
    wf = fetch_workflow(WF_INTERACTIVE_HANDLER)
    nodes = wf["nodes"]
    print(f"  {len(nodes)} nodes")

    node = find_node(nodes, "Build Followup Context")
    if not node:
        print("  ERROR: Build Followup Context not found")
        return

    old_code = node["parameters"]["jsCode"]
    print(f"  Found Build Followup Context ({len(old_code)} chars)")

    node["parameters"]["jsCode"] = NEW_BUILD_FOLLOWUP_CONTEXT
    print("  Updated: Added two-layer Query API + MCP pattern with DATA LATENCY PROTOCOL")

    print(f"\n=== Pushing Interactive Handler ===")
    result = push_workflow(WF_INTERACTIVE_HANDLER, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")
    sync_local(result, "Interactive Events Handler.json")

    print("\nDone! Follow-up Cron draft path now uses two-layer pattern:")
    print("  - Query API meeting data (title, participants, account) is the primary anchor")
    print("  - MCP is used for enrichment (transcripts, topics, action items)")
    print("  - DATA LATENCY PROTOCOL: agent drafts even without transcript data")
    print("  - Agent NEVER says 'meeting not found' — it has confirmed Query API data")
    print("  - Date-aware language (today/yesterday/last week)")


if __name__ == "__main__":
    main()
