"""
Fix: Pre-fetch today's meetings via Query API before the followup agent runs.

Problem: On-demand followup relies entirely on MCP to discover meetings.
MCP data can lag 3-4 hours, so the agent finds an old meeting instead of
today's. The prompt has a latency handler but the agent ignores it.

Fix: Insert a Query API pre-fetch step (same pattern as Follow-up Cron)
into the DM conversation path. Inject today's meetings as context into
the followup prompt so the agent knows definitively what happened today.

This modifies:
1. Build DM System Prompt — adds meeting context injection for followup subRoute
2. Adds 3 nodes before the Build DM System Prompt in the followup path:
   Get Followup Auth Token → Build Followup Query → Fetch Followup Meetings

Actually, simpler approach: the DM conversation path is shared by multiple
commands. Instead of restructuring the flow, we inject the meeting pre-fetch
into Build DM System Prompt itself using an HTTP call or, even simpler,
we strengthen the prompt to be more directive about the latency case AND
we add today's date prominently.

Simplest fix: Improve the prompt to be much more assertive about the
latency case, and move the DATA LATENCY section to the TOP.

Usage:
    N8N_API_KEY=... python scripts/fix_followup_prefetch.py
"""

from n8n_helpers import (
    find_node, fetch_workflow, push_workflow, sync_local,
    WF_EVENTS_HANDLER,
)

# The current followup prompt section builds systemPrompt with the DATA LATENCY
# rules buried at the bottom. We need to:
# 1. Move latency handling to be a top-priority instruction
# 2. Make the agent ALWAYS acknowledge what date the meeting it found was on
# 3. Force the agent to follow the latency protocol when meeting is not today

# We'll replace the entire followup branch of the Build DM System Prompt

OLD_FOLLOWUP_START = """} else if (subRoute === 'followup') {
  // ── Follow-up email draft prompt ──
  systemPrompt = [
    'You are ' + assistantName + ', a personal sales assistant for ' + repName + '.',"""

# Find the end marker — the else that follows the followup branch
OLD_FOLLOWUP_END = """    commandsBlock,
  ].join('\\n');

} else {"""


def main():
    print(f"Fetching Events Handler {WF_EVENTS_HANDLER}...")
    wf = fetch_workflow(WF_EVENTS_HANDLER)
    print(f"  {len(wf['nodes'])} nodes")

    node = find_node(wf["nodes"], "Build DM System Prompt")
    if not node:
        print("  ERROR: Build DM System Prompt not found")
        return

    code = node["parameters"]["jsCode"]

    # Find the followup section boundaries
    start_marker = "} else if (subRoute === 'followup') {"
    end_marker = "} else {"

    start_idx = code.find(start_marker)
    if start_idx == -1:
        print("  ERROR: Could not find followup branch start")
        return

    # Find the closing "} else {" that ends the followup branch
    # We need the one AFTER the followup start, not inside it
    search_from = start_idx + len(start_marker)
    # Find the last "].join('\\n');" before the next "} else {"
    join_marker = "].join('\\n');"
    join_idx = code.find(join_marker, search_from)
    if join_idx == -1:
        print("  ERROR: Could not find end of followup prompt array")
        return

    # The end of the followup section is after the join + the closing of the if block
    end_idx = code.find(end_marker, join_idx)
    if end_idx == -1:
        print("  ERROR: Could not find followup branch end")
        return

    # Extract what we're replacing (from start_marker to just before end_marker)
    old_section = code[start_idx:end_idx]
    print(f"  Found followup section: {len(old_section)} chars")

    # Build the new followup section
    new_section = r"""} else if (subRoute === 'followup') {
  // ── Follow-up email draft prompt ──
  const todayStr = new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });

  systemPrompt = [
    'You are ' + assistantName + ', a personal sales assistant for ' + repName + '.',
    '',
    'Your personality: ' + assistantPersona,
    '',
    'You have access to People.ai MCP tools which give you CRM data, account activity, meeting details, and engagement data.',
    '',
    '**FOLLOW-UP EMAIL DRAFT MODE**',
    '',
    "TODAY IS " + todayStr + ". Remember this date — it is critical for determining meeting recency.",
    '',
    '## CRITICAL: DATA LATENCY PROTOCOL',
    'People.ai transcript data takes 3-4 HOURS to appear after a meeting ends.',
    'When the user asks for a followup, they almost certainly mean a meeting that happened TODAY.',
    '',
    '**YOU MUST FOLLOW THIS PROTOCOL:**',
    '1. Search for the most recent meeting with the specified account using MCP tools',
    '2. Check the date of the meeting you find',
    '3. **IF the meeting is from TODAY** → Great, use that data to draft the email',
    '4. **IF the meeting is NOT from today (even yesterday)** → The user almost certainly had a meeting TODAY that has not synced yet. In this case:',
    '   - Do NOT draft based on the older meeting',
    '   - Draft referencing "your meeting today" or "your conversation today"',
    '   - Use the account context, key contacts, and deal status you DO have to write a relevant follow-up',
    '   - Add a note: "_Your meeting today has not fully synced yet. Reply with key discussion topics and I will make this draft more specific._"',
    '   - Use participants from the older meeting as likely attendees (CC candidates)',
    '5. **IF no meetings found at all** → Ask the user for details about the meeting',
    '',
    'NEVER draft a follow-up anchored on a meeting from 5+ days ago when the user asks for a followup — they mean TODAY.',
    '',
    '## STEP 1: FIND THE SPECIFIC MEETING',
    'Use People.ai MCP tools to find the most recent meeting/activity with this account. Look for:',
    '- Meeting notes, agenda items, or transcript summaries',
    '- Specific topics discussed, decisions made, action items agreed upon',
    '- Who attended and what each person contributed or committed to',
    '',
    '## STEP 2: EXTRACT MEETING-SPECIFIC CONTENT',
    'From the meeting data, identify:',
    '- What was actually discussed (not general deal context)',
    '- Specific commitments or action items from the meeting',
    '- Questions raised or concerns expressed',
    '- Next steps agreed upon during the meeting',
    '',
    '## STEP 3: DRAFT THE EMAIL ANCHORED ON THIS MEETING',
    'The email MUST reference specifics from this meeting — not general account/deal status.',
    '- Lead with what was discussed in THIS meeting',
    '- Action items should be things agreed to IN this meeting',
    '- Do NOT pad with generic deal context or pipeline status unless it was discussed',
    '',
    '**IF MEETING NOTES ARE THIN OR MISSING:**',
    'If you find the meeting but the notes/details are sparse:',
    '- Say so: add a note like "_I found your meeting from {date} but details were limited. Reply with key topics to make this draft more specific._"',
    '- Draft a shorter, more general follow-up rather than fabricating specifics',
    '- Do NOT invent discussion topics that are not in the meeting data',
    '',
    '**DATE AWARENESS — adjust your follow-up language based on when the meeting was:**',
    '- Same day: "Thanks for the conversation today"',
    '- Yesterday: "Thanks for the conversation yesterday"',
    '- 2-3 days ago: "I wanted to follow up on our conversation from {day}"',
    '- 4-7 days ago: "Circling back on our discussion last {day}" — keep it natural',
    '- 7+ days ago: "I wanted to revisit a few items from our meeting on {date}" — acknowledge the gap',
    '- NEVER use immediate-sounding language like "Thanks for the productive discussion" if the meeting was 2+ days ago',
    '',
    '**FORMAT YOUR RESPONSE like this (Slack mrkdwn):**',
    '',
    ':email: *Follow-up Draft — {Account Name}*',
    '',
    '*To:* {Name} ({email@company.com}) — ALWAYS include email addresses. Use People.ai MCP to look up contact emails. If you cannot find an email, still include the name.',
    '*CC:* {Other meeting participants with emails — include internal team and external contacts}',
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
    '- Reference specific topics from THIS meeting — not general account activity',
    '- Do NOT fabricate meeting topics. Only reference what you found in the meeting data.',
    '- Include a clear next step or call to action',
    '- Match the tone to ' + repName + "'s communication style if you have context",
    '- Use the account contact names, not generic "team"',
    '- If no meetings at all are found for the account, ask the user for details',
    '- Keep the Slack message under 3000 characters total',
    '- Do NOT use ### headers — use *bold* for labels',
    '- ALWAYS sign the email as ' + repName + '. Do NOT sign as the account owner or AE — the person requesting the draft is ' + repName + '.',
    commandsBlock,
  ].join('\n');

"""

    # Replace the old section
    new_code = code[:start_idx] + new_section + code[end_idx:]
    node["parameters"]["jsCode"] = new_code
    print("  Updated followup prompt: moved latency protocol to top, made it directive")

    # Now do the same for the Interactive Handler's Build Followup Context
    print(f"\n=== Pushing Events Handler ===")
    result = push_workflow(WF_EVENTS_HANDLER, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")
    sync_local(result, "Slack Events Handler.json")

    print("\nDone! Followup prompt now has DATA LATENCY PROTOCOL at the top.")
    print("Key changes:")
    print("  - Latency rules moved from bottom to top (## CRITICAL section)")
    print("  - Explicit protocol: if meeting not from today, draft for today's meeting")
    print("  - 'NEVER draft based on a 5+ day old meeting when user asks for followup'")
    print("  - Added note template for when data hasn't synced yet")


if __name__ == "__main__":
    main()
