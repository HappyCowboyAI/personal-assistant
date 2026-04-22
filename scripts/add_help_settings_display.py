"""
Add "Your Settings" section to the help command response.

Shows the user's current configuration inline so they can see what they have
set and know which commands to use to change things.

Usage:
    N8N_API_KEY=... python3 scripts/add_help_settings_display.py
"""

from n8n_helpers import fetch_workflow, find_node, push_workflow, sync_local

WF_EVENTS = "QuQbIaWetunUOFUW"


def main():
    print(f"Fetching Slack Events Handler {WF_EVENTS}...")
    wf = fetch_workflow(WF_EVENTS)
    nodes = wf["nodes"]
    print(f"  {len(nodes)} nodes")

    node = find_node(nodes, "Build Help Response")
    if not node:
        print("  ERROR: Build Help Response not found")
        return

    old_code = node["parameters"]["jsCode"]

    # Replace the help section to add a settings display
    # Find the existing help block and replace it
    OLD_HELP_BLOCK = (
        """if (r === 'help') {
  // --- Conversation-first help ---
  text = "*Just ask me anything* \\u2014 I have access to your Backstory CRM data and can answer questions about accounts, deals, engagement, and pipeline.\\n\\n" +
    "Try things like:\\n" +
    "\\u2022 _\\"What's happening with AMD?\\"_\\n" +
    "\\u2022 _\\"Who should I be talking to at Cisco?\\"_\\n" +
    "\\u2022 _\\"Draft a follow-up for my Intel meeting\\"_\\n" +
    "\\u2022 _\\"I need a presentation on Q1 results\\"_\\n\\n" +
    ":thread: Reply in a thread to keep the conversation going.\\n\\n" +
    "*Skills:*\\n" +
    "`brief` \\u00b7 `meet` \\u00b7 `insights` \\u00b7 `presentation` \\u00b7 `bbr` \\u00b7 `stakeholders` \\u00b7 `followup` \\u00b7 `silence`\\n" +
    "`rename` \\u00b7 `emoji` \\u00b7 `persona` \\u00b7 `scope` \\u00b7 `focus`\\n" +
    "`tips` \\u00b7 `announcements`\\n\\n" +
    "Type `more <skill>` for details on any of my abilities (e.g. `more brief`).";"""
    )

    NEW_HELP_BLOCK = r"""if (r === 'help') {
  // --- Conversation-first help ---
  const u = data.userRecord || {};

  // Build settings display
  const scopeLabels = { 'my_deals': 'My Deals (IC)', 'team_deals': 'Team Deals (Manager)', 'top_pipeline': 'Top Pipeline (Exec)' };
  const scopeVal = u.digest_scope || 'my_deals';
  const scopeDisplay = scopeLabels[scopeVal] || scopeVal;

  const digestOn = u.digest_enabled !== false;
  const briefsOn = u.meeting_prep_enabled !== false;
  const tipsOn = u.tips_enabled !== false;
  const announcementsOn = u.announcements_enabled !== false;

  const personaDisplay = u.assistant_persona ? u.assistant_persona : '_default_';
  const focusDisplay = u.digest_focus || '_none_';

  const settingsBlock =
    "\n\n*Your Settings:*\n" +
    "\u2022 *Name:* " + (u.assistant_name || 'Your Assistant') + " \u2014 `rename <name>`\n" +
    "\u2022 *Icon:* " + (u.assistant_emoji || ':robot_face:') + " \u2014 `emoji <emoji>`\n" +
    "\u2022 *Persona:* " + personaDisplay + " \u2014 `persona <style>`\n" +
    "\u2022 *Scope:* " + scopeDisplay + " \u2014 `scope <mode>`\n" +
    "\u2022 *Focus:* " + focusDisplay + " \u2014 `focus <area>`\n" +
    "\u2022 *Morning Digest:* " + (digestOn ? ':white_check_mark: on' : ':no_entry_sign: paused') + " \u2014 `" + (digestOn ? 'stop' : 'resume') + " digest`\n" +
    "\u2022 *Meeting Briefs:* " + (briefsOn ? ':white_check_mark: on' : ':no_entry_sign: paused') + " \u2014 `" + (briefsOn ? 'stop' : 'start') + " briefs`\n" +
    "\u2022 *Tips:* " + (tipsOn ? ':white_check_mark: on' : ':no_entry_sign: paused') + " \u2014 `" + (tipsOn ? 'stop' : 'resume') + " tips`\n" +
    "\u2022 *Announcements:* " + (announcementsOn ? ':white_check_mark: on' : ':no_entry_sign: paused') + " \u2014 `" + (announcementsOn ? 'stop' : 'resume') + " announcements`";

  text = "*Just ask me anything* \u2014 I have access to your Backstory CRM data and can answer questions about accounts, deals, engagement, and pipeline.\n\n" +
    "Try things like:\n" +
    "\u2022 _\"What's happening with AMD?\"_\n" +
    "\u2022 _\"Who should I be talking to at Cisco?\"_\n" +
    "\u2022 _\"Draft a follow-up for my Intel meeting\"_\n" +
    "\u2022 _\"I need a presentation on Q1 results\"_\n\n" +
    ":thread: Reply in a thread to keep the conversation going.\n\n" +
    "*Skills:*\n" +
    "`brief` \u00b7 `meet` \u00b7 `insights` \u00b7 `presentation` \u00b7 `bbr` \u00b7 `stakeholders` \u00b7 `followup` \u00b7 `silence`\n" +
    "`rename` \u00b7 `emoji` \u00b7 `persona` \u00b7 `scope` \u00b7 `focus`\n" +
    "`tips` \u00b7 `announcements`\n\n" +
    "Type `more <skill>` for details on any of my abilities (e.g. `more brief`)." +
    settingsBlock;"""

    if OLD_HELP_BLOCK in old_code:
        new_code = old_code.replace(OLD_HELP_BLOCK, NEW_HELP_BLOCK)
        node["parameters"]["jsCode"] = new_code
        print("  Updated Build Help Response with 'Your Settings' section")
    else:
        # Try matching just the start of the block
        print("  WARNING: Exact match not found, applying code directly...")
        # Replace everything from 'if (r === 'help')' to the semicolon after the help text
        import re
        pattern = r"if \(r === 'help'\) \{[^}]+?Type `more <skill>`[^;]+;"
        match = re.search(pattern, old_code, re.DOTALL)
        if match:
            new_code = old_code[:match.start()] + NEW_HELP_BLOCK + old_code[match.end():]
            node["parameters"]["jsCode"] = new_code
            print("  Updated Build Help Response with 'Your Settings' section (regex match)")
        else:
            print("  ERROR: Could not find help block to replace")
            return

    print(f"\n=== Pushing Slack Events Handler ===")
    result = push_workflow(WF_EVENTS, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")
    sync_local(result, "Slack Events Handler.json")

    print("\nDone! Help command now shows 'Your Settings' section:")
    print("  - Name, Icon, Persona (current value + change command)")
    print("  - Scope, Focus (current value + change command)")
    print("  - Morning Digest, Meeting Briefs, Tips, Announcements (on/off + toggle command)")
    print("  Test: type 'help' in a DM")


if __name__ == "__main__":
    main()
