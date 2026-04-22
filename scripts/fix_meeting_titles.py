"""
Fix: Pre-fetch participant titles from Backstory activity export
and include them in the participant string passed to Meeting Brief agent.

The bug: Meeting Brief agent guesses/hallucinates participant titles because
no title data is provided — only names and internal/external flags.

Fix:
1. Meeting Prep Cron: Add title column to activity export query
2. Meeting Prep Cron: Parse titles in Parse Meetings node
3. Meeting Prep Cron: Include titles in Match Users to Meetings participant string
4. Meeting Brief: Update prompt to trust provided titles

Usage:
    N8N_API_KEY=... python scripts/fix_meeting_titles.py
"""

from n8n_helpers import (
    find_node, modify_workflow, fetch_workflow, push_workflow, sync_local,
    WF_MEETING_PREP_CRON,
)

WF_MEETING_BRIEF = "Cj4HcHfbzy9OZhwE"


def fix_prep_cron(nodes, connections):
    changes = 0

    # ── 1. Build Query: add title column to activity export ──────────
    build_query = find_node(nodes, "Build Query")
    if not build_query:
        print("  ERROR: Could not find 'Build Query' node")
        return 0

    code = build_query["parameters"]["jsCode"]
    old_cols = '{ slug: "ootb_activity_participants", variation_id: "ootb_activity_participants_external" },\n    { slug: "ootb_activity_account" }'
    new_cols = '{ slug: "ootb_activity_participants", variation_id: "ootb_activity_participants_external" },\n    { slug: "ootb_activity_participants", variation_id: "ootb_activity_participants_title" },\n    { slug: "ootb_activity_account" }'

    if old_cols in code:
        code = code.replace(old_cols, new_cols)
        build_query["parameters"]["jsCode"] = code
        print("  Added title column to Build Query")
        changes += 1
    else:
        print("  WARNING: Could not find column insertion point in Build Query")

    # ── 2. Parse Meetings: extract titles alongside names/emails ─────
    parse_meetings = find_node(nodes, "Parse Meetings")
    if not parse_meetings:
        print("  ERROR: Could not find 'Parse Meetings' node")
        return changes

    code = parse_meetings["parameters"]["jsCode"]

    # Add title parsing after externals
    old_externals = "  const externals = parseList(getField(row, 'Activity Participants (External)'));"
    new_externals = """  const externals = parseList(getField(row, 'Activity Participants (External)'));
  const titles = parseList(getField(row, 'Activity Participants (Title)', 'ootb_activity_participants_title'));"""

    if old_externals in code:
        code = code.replace(old_externals, new_externals)
        print("  Added title parsing to Parse Meetings")
        changes += 1
    else:
        print("  WARNING: Could not find externals line in Parse Meetings")

    # Add participantTitles to meeting object
    old_field = "    participantExternals: externals,"
    new_field = "    participantTitles: titles,\n    participantExternals: externals,"

    if old_field in code:
        code = code.replace(old_field, new_field)
        print("  Added participantTitles field to meeting object")
        changes += 1
    else:
        print("  WARNING: Could not find participantExternals field in Parse Meetings")

    parse_meetings["parameters"]["jsCode"] = code

    # ── 3. Match Users to Meetings: include titles in participant string
    match_node = find_node(nodes, "Match Users to Meetings")
    if not match_node:
        print("  ERROR: Could not find 'Match Users to Meetings' node")
        return changes

    code = match_node["parameters"]["jsCode"]

    # Add pTitles declaration
    old_decl = "        const pExternals = meeting.participantExternals || [];"
    new_decl = """        const pExternals = meeting.participantExternals || [];
        const pTitles = meeting.participantTitles || [];"""

    if old_decl in code:
        code = code.replace(old_decl, new_decl)
        print("  Added pTitles declaration")
        changes += 1
    else:
        print("  WARNING: Could not find pExternals declaration")

    # Add title variable in loop
    old_name = "          const pName = pNames[p] || pEmails[p];"
    new_name = """          const pName = pNames[p] || pEmails[p];
          const pTitle = pTitles[p] || '';
          const titleSuffix = pTitle ? ' — ' + pTitle : '';"""

    if old_name in code:
        code = code.replace(old_name, new_name)
        print("  Added title variable in loop")
        changes += 1
    else:
        print("  WARNING: Could not find pName line in loop")

    # Update external participant string
    old_ext = "            parts.push(pName + ' (external)');"
    new_ext = "            parts.push(pName + titleSuffix + ' (external)');"

    if old_ext in code:
        code = code.replace(old_ext, new_ext)
        print("  Updated external participant format with title")
        changes += 1
    else:
        print("  WARNING: Could not find external parts.push")

    # Update internal participant with Slack ID
    old_int_slack = "              parts.push('<@' + pUser.slack_user_id + '> :backstory:');"
    new_int_slack = "              parts.push('<@' + pUser.slack_user_id + '>' + titleSuffix + ' :backstory:');"

    if old_int_slack in code:
        code = code.replace(old_int_slack, new_int_slack)
        print("  Updated internal (Slack) participant format with title")
        changes += 1
    else:
        print("  WARNING: Could not find internal Slack parts.push")

    # Update internal participant without Slack ID
    old_int_name = "              parts.push(pName + ' :backstory:');"
    new_int_name = "              parts.push(pName + titleSuffix + ' :backstory:');"

    if old_int_name in code:
        code = code.replace(old_int_name, new_int_name)
        print("  Updated internal (name) participant format with title")
        changes += 1
    else:
        print("  WARNING: Could not find internal name parts.push")

    match_node["parameters"]["jsCode"] = code

    return changes


def fix_meeting_brief():
    """Update Meeting Brief prompt to trust provided titles."""
    print(f"\nFetching Meeting Brief workflow {WF_MEETING_BRIEF} (live)...")
    wf = fetch_workflow(WF_MEETING_BRIEF)
    print(f"  {len(wf['nodes'])} nodes")

    node = find_node(wf["nodes"], "Resolve Meeting Identity")
    if not node:
        print("  ERROR: Could not find 'Resolve Meeting Identity' node")
        return None

    code = node["parameters"]["jsCode"]

    # Update the research instructions to trust provided titles
    old_research = "- Each participant's role, title, and recent touchpoints"
    new_research = "- Each participant's role, title, and recent touchpoints. IMPORTANT: If titles are provided in the Participants field above (after the — dash), use them exactly as listed. Do not guess or override provided titles."

    if old_research in code:
        code = code.replace(old_research, new_research)
        print("  Updated prompt to trust provided titles")
    else:
        print("  WARNING: Could not find research instruction line")
        return None

    node["parameters"]["jsCode"] = code

    print("\n=== Pushing Meeting Brief workflow ===")
    result = push_workflow(WF_MEETING_BRIEF, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")

    print("\n=== Syncing ===")
    sync_local(result, "Meeting Brief.json")

    return result


if __name__ == "__main__":
    # Fix Meeting Prep Cron
    result = modify_workflow(
        WF_MEETING_PREP_CRON,
        "Meeting Prep Cron.json",
        fix_prep_cron,
    )
    print(f"\nMeeting Prep Cron: {len(result['nodes'])} total nodes")

    # Fix Meeting Brief prompt
    brief_result = fix_meeting_brief()
    if brief_result:
        print(f"Meeting Brief: {len(brief_result['nodes'])} total nodes")

    print("\nDone!")
