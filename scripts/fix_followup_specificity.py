"""
Fix: Make followup drafts specific to the actual meeting, not general account context.

Problem: The agent pulls broad account activity and writes a generic follow-up.
Fix: Instruct the agent to anchor on the single most recent meeting's notes/topics
and clearly distinguish meeting-specific content from general account context.

Updates both:
1. Build DM System Prompt (Events Handler — `followup <account>`)
2. Build Followup Context (Interactive Handler — button-triggered followup)

Usage:
    N8N_API_KEY=... python scripts/fix_followup_specificity.py
"""

from n8n_helpers import (
    find_node, fetch_workflow, push_workflow, sync_local,
    WF_EVENTS_HANDLER, WF_INTERACTIVE_HANDLER,
)


# ── Events Handler: Build DM System Prompt ──

OLD_DM_STEPS = """'The user wants to draft a follow-up email. Use Backstory MCP tools to:',
    '1. Find the most recent meeting with the mentioned account',
    '2. Get meeting participants and their roles',
    '3. Check current deal status, stage, and next steps',
    '4. Review recent engagement context',"""

NEW_DM_STEPS = """'The user wants to draft a follow-up email for their MOST RECENT meeting with this account.',
    '',
    '**STEP 1: FIND THE SPECIFIC MEETING**',
    'Use Backstory MCP tools to find the most recent meeting/activity with this account. Look for:',
    '- Meeting notes, agenda items, or transcript summaries',
    '- Specific topics discussed, decisions made, action items agreed upon',
    '- Who attended and what each person contributed or committed to',
    '',
    '**STEP 2: EXTRACT MEETING-SPECIFIC CONTENT**',
    'From the meeting data, identify:',
    '- What was actually discussed (not general deal context)',
    '- Specific commitments or action items from the meeting',
    '- Questions raised or concerns expressed',
    '- Next steps agreed upon during the meeting',
    '',
    '**STEP 3: DRAFT THE EMAIL ANCHORED ON THIS MEETING**',
    'The email MUST reference specifics from this meeting — not general account/deal status.',
    '- Lead with what was discussed in THIS meeting',
    '- Action items should be things agreed to IN this meeting',
    '- Do NOT pad with generic deal context or pipeline status unless it was discussed',
    '',
    '**IF MEETING NOTES ARE THIN OR MISSING:**',
    'If you find the meeting but the notes/details are sparse:',
    '- Say so: add a note like "_I found your meeting from {date} but details were limited. Reply with key topics to make this draft more specific._"',
    '- Draft a shorter, more general follow-up rather than fabricating specifics',
    '- Do NOT invent discussion topics that are not in the meeting data',"""

OLD_DM_RULES_PREFIX = """'**RULES:**',
    '- Draft should be 150-250 words — concise and professional',
    '- Reference specific topics from the meeting if available, but prefer recent context over stale meeting data',"""

NEW_DM_RULES_PREFIX = """'**RULES:**',
    '- Draft should be 150-250 words — concise and professional',
    '- Reference specific topics from THIS meeting — not general account activity',
    '- Do NOT fabricate meeting topics. Only reference what you found in the meeting data.',"""


# ── Interactive Handler: Build Followup Context ──

OLD_INT_STEPS = """Use Backstory MCP tools to:
1. Check the account's current deal status and stage
2. Review recent engagement and activity
3. Look up the participants to personalize the email

Draft a professional follow-up email."""

NEW_INT_STEPS = """Use Backstory MCP tools to:
1. Find the SPECIFIC most recent meeting with this account — look for meeting notes, topics discussed, and action items
2. Extract what was actually discussed in that meeting (not general deal context)
3. Look up participant emails to personalize the email

**CRITICAL:** Anchor the email on what was discussed in THIS specific meeting.
- Lead with topics, decisions, and action items from the meeting
- Do NOT pad with generic deal/pipeline context unless it was discussed in the meeting
- If meeting notes are thin, draft a shorter email and note that details were limited

Draft a professional follow-up email."""

OLD_INT_RULES_PREFIX = """**RULES:**
- Keep the email 150-250 words
- Reference specific discussion topics if available"""

NEW_INT_RULES_PREFIX = """**RULES:**
- Keep the email 150-250 words
- Reference specific discussion topics from THIS meeting — do NOT fabricate topics"""


def main():
    # ── Events Handler ──
    print(f"Fetching Events Handler {WF_EVENTS_HANDLER}...")
    wf = fetch_workflow(WF_EVENTS_HANDLER)
    print(f"  {len(wf['nodes'])} nodes")

    node = find_node(wf["nodes"], "Build DM System Prompt")
    changes = 0

    if node:
        code = node["parameters"]["jsCode"]

        if OLD_DM_STEPS in code:
            code = code.replace(OLD_DM_STEPS, NEW_DM_STEPS)
            print("  Updated DM followup steps (anchor on specific meeting)")
            changes += 1

        if OLD_DM_RULES_PREFIX in code:
            code = code.replace(OLD_DM_RULES_PREFIX, NEW_DM_RULES_PREFIX)
            print("  Updated DM followup rules (no fabrication)")
            changes += 1

        node["parameters"]["jsCode"] = code

    if changes:
        print(f"\n=== Pushing Events Handler ({changes} changes) ===")
        result = push_workflow(WF_EVENTS_HANDLER, wf)
        print(f"  HTTP 200, {len(result['nodes'])} nodes")
        sync_local(result, "Slack Events Handler.json")

    # ── Interactive Handler ──
    print(f"\nFetching Interactive Handler {WF_INTERACTIVE_HANDLER}...")
    wf2 = fetch_workflow(WF_INTERACTIVE_HANDLER)
    print(f"  {len(wf2['nodes'])} nodes")

    node2 = find_node(wf2["nodes"], "Build Followup Context")
    changes2 = 0

    if node2:
        code2 = node2["parameters"]["jsCode"]

        if OLD_INT_STEPS in code2:
            code2 = code2.replace(OLD_INT_STEPS, NEW_INT_STEPS)
            print("  Updated Interactive followup steps (anchor on specific meeting)")
            changes2 += 1

        if OLD_INT_RULES_PREFIX in code2:
            code2 = code2.replace(OLD_INT_RULES_PREFIX, NEW_INT_RULES_PREFIX)
            print("  Updated Interactive followup rules (no fabrication)")
            changes2 += 1

        node2["parameters"]["jsCode"] = code2

    if changes2:
        print(f"\n=== Pushing Interactive Handler ({changes2} changes) ===")
        result2 = push_workflow(WF_INTERACTIVE_HANDLER, wf2)
        print(f"  HTTP 200, {len(result2['nodes'])} nodes")
        sync_local(result2, "Interactive Events Handler.json")

    if changes + changes2 == 0:
        print("\n  No changes made")
    else:
        print("\nDone!")


if __name__ == "__main__":
    main()
