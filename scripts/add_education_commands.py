#!/usr/bin/env python3
"""
Add stop/resume tips and stop/resume announcements commands to the Events Handler.

Modifies 3 existing nodes and adds 2 new nodes to support:
  - `stop tips` / `pause tips` -> set tips_enabled = false
  - `resume tips` / `start tips` -> set tips_enabled = true
  - `stop announcements` -> set announcements_enabled = false
  - `resume announcements` / `start announcements` -> set announcements_enabled = true

Changes:
1. Route by State — add new command patterns in cmd_other section
2. Is Conversational? — add 4 new subRoutes to the NOT-IN list
3. Build Help Response — add handlers for the 4 subRoutes + output dbUpdate field
4. Help text — add stop/resume tips and announcements to help shortcuts
5. New: "Needs Education Update?" IF node — checks $json.needsEducationUpdate
6. New: "Toggle Education Pref" HTTP node — PATCH Supabase users table

The existing chain is:
  Build Help Response -> Needs Digest Update? -> [true] Toggle Digest -> Send Help Response
                                               -> [false] Send Help Direct

After this script:
  Build Help Response -> Needs Digest Update? -> [true] Toggle Digest -> Send Help Response
                                               -> [false] Needs Education Update?
                                                           -> [true] Toggle Education Pref -> Send Help Direct
                                                           -> [false] Send Help Direct
"""

from n8n_helpers import (
    uid,
    find_node,
    modify_workflow,
    WF_EVENTS_HANDLER,
    SUPABASE_URL,
    SUPABASE_CRED,
    NODE_HTTP_REQUEST,
    NODE_IF,
)


def modify_events_handler(nodes, connections):
    changes = 0

    # ── Guard: already applied? ──────────────────────────────────────
    route_node = find_node(nodes, "Route by State")
    if not route_node:
        print("ERROR: 'Route by State' node not found!")
        return 0

    if "stop_tips" in route_node["parameters"]["jsCode"]:
        print("  Guard: 'stop_tips' already in Route by State — skipping all")
        return 0

    # ═══════════════════════════════════════════════════════════════════
    # 1. Route by State — add education command patterns
    # ═══════════════════════════════════════════════════════════════════
    code = route_node["parameters"]["jsCode"]

    # Find the existing stop/resume digest lines and add new patterns after them
    # The pattern is:
    #   if (lower === 'stop digest' || ...) subRoute = 'stop_digest';
    #   else if (lower === 'resume digest' || ...) subRoute = 'resume_digest';
    # We insert right after the resume_digest line.
    marker = "subRoute = 'resume_digest';"
    if marker not in code:
        print("ERROR: Could not find 'resume_digest' marker in Route by State")
        return 0

    new_commands = """
      else if (lower === 'stop tips' || lower === 'pause tips') subRoute = 'stop_tips';
      else if (lower === 'resume tips' || lower === 'start tips') subRoute = 'resume_tips';
      else if (lower === 'stop announcements') subRoute = 'stop_announcements';
      else if (lower === 'resume announcements' || lower === 'start announcements') subRoute = 'resume_announcements';"""

    code = code.replace(
        marker,
        marker + new_commands,
    )
    route_node["parameters"]["jsCode"] = code
    print("  [1/6] Updated 'Route by State' with education command patterns")
    changes += 1

    # ═══════════════════════════════════════════════════════════════════
    # 2. Is Conversational? — add 4 new subRoutes to NOT-IN list
    # ═══════════════════════════════════════════════════════════════════
    conv_node = find_node(nodes, "Is Conversational?")
    if not conv_node:
        print("ERROR: 'Is Conversational?' node not found!")
        return changes

    current_conditions = conv_node["parameters"]["conditions"]["conditions"]
    existing_values = {c["rightValue"] for c in current_conditions}
    new_values = ["stop_tips", "resume_tips", "stop_announcements", "resume_announcements"]
    added = []

    for val in new_values:
        if val not in existing_values:
            current_conditions.append({
                "id": uid(),
                "leftValue": "={{ $json.subRoute }}",
                "rightValue": val,
                "operator": {"type": "string", "operation": "notEquals"},
            })
            added.append(val)

    if added:
        print(f"  [2/6] Updated 'Is Conversational?' — added {len(added)} conditions: {', '.join(added)}")
        changes += 1
    else:
        print("  [2/6] 'Is Conversational?' already has education conditions — skipping")

    # ═══════════════════════════════════════════════════════════════════
    # 3. Build Help Response — add handlers + help text updates
    # ═══════════════════════════════════════════════════════════════════
    help_node = find_node(nodes, "Build Help Response")
    if not help_node:
        print("ERROR: 'Build Help Response' node not found!")
        return changes

    help_code = help_node["parameters"]["jsCode"]

    # 3a. Add new subRoute handlers before the fallback `else` block.
    # The current code ends with:
    #   } else if (r === 'resume_digest') { ... }
    #   } else { ... }
    #   const needsUpdate = ...
    # We insert the new handlers between resume_digest and the fallback else.
    old_resume_digest_block = "} else if (r === 'resume_digest') {\n  text = \"Morning briefings are back on."
    if old_resume_digest_block not in help_code:
        print("ERROR: Could not find resume_digest handler in Build Help Response")
        return changes

    # Find the closing brace of resume_digest and insert before the final else
    # Strategy: replace the section from resume_digest through the end of the else block
    # to add new handlers in between.

    new_handlers = r"""} else if (r === 'stop_tips') {
  text = "Tips paused \u2014 I won\u2019t send feature tips anymore. Type `resume tips` anytime to restart.";
} else if (r === 'resume_tips') {
  text = "Tips resumed! I\u2019ll share helpful feature tips from time to time.";
} else if (r === 'stop_announcements') {
  text = "Announcements paused \u2014 I won\u2019t send new feature announcements. Type `resume announcements` anytime to restart.";
} else if (r === 'resume_announcements') {
  text = "Announcements resumed! I\u2019ll let you know when I learn new tricks.";
"""

    # Insert after the resume_digest closing brace, before the final else
    # Find: "} else {\n  text = \"I didn" (the fallback)
    fallback_marker = '} else {\n  text = "I didn'
    if fallback_marker not in help_code:
        print("ERROR: Could not find fallback handler in Build Help Response")
        return changes

    help_code = help_code.replace(
        fallback_marker,
        new_handlers + fallback_marker,
    )

    # 3b. Update needsUpdate and add education update fields.
    # Replace the old needsUpdate/digestEnabled lines with expanded logic.
    old_needs = "const needsUpdate = (r === 'stop_digest' || r === 'resume_digest');\nconst digestEnabled = (r === 'resume_digest');"
    if old_needs not in help_code:
        print("ERROR: Could not find needsUpdate/digestEnabled in Build Help Response")
        return changes

    new_needs = """const needsUpdate = (r === 'stop_digest' || r === 'resume_digest');
const digestEnabled = (r === 'resume_digest');

// Education preference updates (tips_enabled, announcements_enabled)
const needsEducationUpdate = ['stop_tips', 'resume_tips', 'stop_announcements', 'resume_announcements'].includes(r);
let educationField = null;
let educationValue = null;
if (r === 'stop_tips') { educationField = 'tips_enabled'; educationValue = false; }
else if (r === 'resume_tips') { educationField = 'tips_enabled'; educationValue = true; }
else if (r === 'stop_announcements') { educationField = 'announcements_enabled'; educationValue = false; }
else if (r === 'resume_announcements') { educationField = 'announcements_enabled'; educationValue = true; }"""

    help_code = help_code.replace(old_needs, new_needs)

    # 3c. Update the return statement to include new fields.
    old_return = "return [{ json: { ...data, responseText: text, needsUpdate, digestEnabled } }];"
    if old_return not in help_code:
        print("ERROR: Could not find return statement in Build Help Response")
        return changes

    new_return = "return [{ json: { ...data, responseText: text, needsUpdate, digestEnabled, needsEducationUpdate, educationField, educationValue } }];"
    help_code = help_code.replace(old_return, new_return)

    # 3d. Update help text to mention new commands.
    # Add stop/resume tips and announcements after the existing settings shortcuts line.
    # The line in the JS code looks like:
    #   "`rename` \u00b7 `emoji` \u00b7 `persona` \u00b7 `scope` \u00b7 `focus`\n\n" +
    old_settings_line = '"`rename` \\u00b7 `emoji` \\u00b7 `persona` \\u00b7 `scope` \\u00b7 `focus`\\n\\n" +'
    if old_settings_line in help_code:
        # Insert a new line of shortcuts between settings and the "Type more" line
        new_settings_line = (
            '"`rename` \\u00b7 `emoji` \\u00b7 `persona` \\u00b7 `scope` \\u00b7 `focus`\\n" +\n'
            '    "`stop tips` \\u00b7 `resume tips` \\u00b7 `stop announcements` \\u00b7 `resume announcements`\\n\\n" +'
        )
        help_code = help_code.replace(old_settings_line, new_settings_line)
    else:
        # If the exact match fails, we'll still continue — help text is nice-to-have
        print("  WARN: Could not update help shortcuts listing (non-fatal)")

    help_node["parameters"]["jsCode"] = help_code
    print("  [3/6] Updated 'Build Help Response' with education handlers + help text")
    changes += 1

    # ═══════════════════════════════════════════════════════════════════
    # 4. New node: "Needs Education Update?" IF node
    # ═══════════════════════════════════════════════════════════════════
    # Position: between "Needs Digest Update?" false output and "Send Help Direct"
    # Current: Needs Digest Update? -> [false] Send Help Direct (position=[2896, 2400])
    # New: Needs Digest Update? -> [false] Needs Education Update? -> [true] Toggle Education Pref -> Send Help Direct
    #                                                               -> [false] Send Help Direct

    needs_edu_node = {
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
                        "leftValue": "={{ $json.needsEducationUpdate }}",
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
        "name": "Needs Education Update?",
        "type": NODE_IF,
        "typeVersion": 2.2,
        "position": [2896, 2400],
    }
    nodes.append(needs_edu_node)
    print(f"  [4/6] Added 'Needs Education Update?' IF node")
    changes += 1

    # ═══════════════════════════════════════════════════════════════════
    # 5. New node: "Toggle Education Pref" HTTP Request node
    # ═══════════════════════════════════════════════════════════════════
    # Uses HTTP Request to PATCH Supabase users table, since Supabase node
    # has issues with dynamic field names.
    # The field to update comes from $json.educationField and value from $json.educationValue.
    # URL uses n8n expression prefix "=" for dynamic user ID filtering.

    toggle_edu_body = (
        '={{ JSON.stringify({ '
        '[$json.educationField]: $json.educationValue '
        '}) }}'
    )
    toggle_edu_node = {
        "parameters": {
            "method": "PATCH",
            "url": f"={SUPABASE_URL}/rest/v1/users?id=eq.{{{{ $json.dbUserId }}}}",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "supabaseApi",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Prefer", "value": "return=representation"},
                    {"name": "Content-Type", "value": "application/json"},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": toggle_edu_body,
            "options": {},
        },
        "id": uid(),
        "name": "Toggle Education Pref",
        "type": NODE_HTTP_REQUEST,
        "typeVersion": 4.2,
        "position": [3120, 2400],
        "credentials": {"supabaseApi": SUPABASE_CRED},
        "continueOnFail": True,
    }
    nodes.append(toggle_edu_node)
    print(f"  [5/6] Added 'Toggle Education Pref' HTTP node")
    changes += 1

    # ═══════════════════════════════════════════════════════════════════
    # 6. Build DM System Prompt — add new commands to available commands list
    # ═══════════════════════════════════════════════════════════════════
    dm_prompt_node = find_node(nodes, "Build DM System Prompt")
    if dm_prompt_node:
        dm_code = dm_prompt_node["parameters"]["jsCode"]
        # Add stop/resume tips/announcements after the existing 'stop digest' line
        dm_marker = "'- `stop digest` / `resume digest` — toggle morning briefings',"
        if dm_marker in dm_code and "'stop tips'" not in dm_code:
            dm_code = dm_code.replace(
                dm_marker,
                dm_marker + "\n"
                "  '- `stop tips` / `resume tips` — toggle feature education tips',\n"
                "  '- `stop announcements` / `resume announcements` — toggle new feature announcements',",
            )
            dm_prompt_node["parameters"]["jsCode"] = dm_code
            print("  [6/6] Updated 'Build DM System Prompt' with education commands")
            changes += 1
        else:
            print("  [6/6] 'Build DM System Prompt' already has education commands or marker not found")
    else:
        print("  WARN: 'Build DM System Prompt' node not found — skipping")

    # ═══════════════════════════════════════════════════════════════════
    # Wiring
    # ═══════════════════════════════════════════════════════════════════

    # Move "Send Help Direct" to make room for the new nodes
    send_help_direct = find_node(nodes, "Send Help Direct")
    if send_help_direct:
        send_help_direct["position"] = [3344, 2400]

    # Current wiring:
    #   "Needs Digest Update?" -> [true, output 0] Toggle Digest -> Send Help Response
    #   "Needs Digest Update?" -> [false, output 1] Send Help Direct
    #
    # New wiring:
    #   "Needs Digest Update?" -> [true, output 0] Toggle Digest -> Send Help Response (unchanged)
    #   "Needs Digest Update?" -> [false, output 1] Needs Education Update?
    #     -> [true, output 0] Toggle Education Pref -> Send Help Direct
    #     -> [false, output 1] Send Help Direct

    # Rewire Needs Digest Update? false output -> Needs Education Update?
    if "Needs Digest Update?" in connections:
        main_outputs = connections["Needs Digest Update?"]["main"]
        # output 1 (false) currently goes to Send Help Direct
        main_outputs[1] = [{"node": "Needs Education Update?", "type": "main", "index": 0}]
        print("  Wired: Needs Digest Update? [false] -> Needs Education Update?")

    # Wire Needs Education Update? outputs
    connections["Needs Education Update?"] = {
        "main": [
            [{"node": "Toggle Education Pref", "type": "main", "index": 0}],  # true
            [{"node": "Send Help Direct", "type": "main", "index": 0}],       # false
        ]
    }
    print("  Wired: Needs Education Update? [true] -> Toggle Education Pref")
    print("  Wired: Needs Education Update? [false] -> Send Help Direct")

    # Wire Toggle Education Pref -> Send Help Direct
    connections["Toggle Education Pref"] = {
        "main": [[{"node": "Send Help Direct", "type": "main", "index": 0}]]
    }
    print("  Wired: Toggle Education Pref -> Send Help Direct")

    return changes


def main():
    print("=== Add Education Commands (stop/resume tips + announcements) ===\n")

    modify_workflow(
        WF_EVENTS_HANDLER,
        "Slack Events Handler.json",
        modify_events_handler,
    )

    print("\nDone! Education commands added:")
    print("  - `stop tips` / `pause tips` -> pauses feature tips")
    print("  - `resume tips` / `start tips` -> resumes feature tips")
    print("  - `stop announcements` -> pauses feature announcements")
    print("  - `resume announcements` / `start announcements` -> resumes announcements")
    print("  - Help text updated with new commands")
    print("  - DB updates via Supabase PATCH (tips_enabled / announcements_enabled)")


if __name__ == "__main__":
    main()
