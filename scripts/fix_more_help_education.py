#!/usr/bin/env python3
"""
Add education commands to the `more <keyword>` help system.

Currently `more tips`, `more announcements` etc. return
"I don't have detailed help for ..." because the details dictionary in
Build Help Response doesn't have entries for them.

Changes:
1. Build Help Response — add `tips` and `announcements` detail entries
2. Build Help Response — add aliases (stop tips -> tips, etc.)
3. Build Help Response — update fallback "Available shortcuts" list
"""

from n8n_helpers import (
    find_node,
    modify_workflow,
    WF_EVENTS_HANDLER,
)


def modify_events_handler(nodes, connections):
    help_node = find_node(nodes, "Build Help Response")
    if not help_node:
        print("ERROR: 'Build Help Response' node not found!")
        return 0

    code = help_node["parameters"]["jsCode"]

    # Guard: already applied?
    if "Feature Education Tips" in code:
        print("  Guard: education 'more' help already present — skipping")
        return 0

    # 1. Add new detail entries to the details dict.
    # Find the closing of the details object.
    details_close = "  };\n\n  // Also accept aliases"
    if details_close not in code:
        print("ERROR: Could not find details dict closing")
        return 0

    new_entries = r"""
    'tips': "*Feature Tips*\n\n" +
      "I\u2019ll share helpful tips about features you haven\u2019t tried yet \u2014 delivered at most twice a week.\n\n" +
      "*Commands:*\n" +
      "\u2022 `stop tips` \u2014 pause feature tips\n" +
      "\u2022 `resume tips` \u2014 resume feature tips",

    'announcements': "*Feature Announcements*\n\n" +
      "I\u2019ll let you know when I learn new capabilities.\n\n" +
      "*Commands:*\n" +
      "\u2022 `stop announcements` \u2014 pause announcements\n" +
      "\u2022 `resume announcements` \u2014 resume announcements",

"""

    code = code.replace(
        details_close,
        new_entries + details_close,
    )

    # 2. Add aliases so all variations resolve to the parent entry
    old_aliases = "const aliases = { 'pbr': 'bbr', 'digest': 'brief', 'briefing': 'brief', 'slide': 'presentation', 'slides': 'presentation', 'deck': 'presentation', 'name': 'rename', 'icon': 'emoji'"
    if old_aliases not in code:
        print("ERROR: Could not find aliases dict")
        return 0

    new_aliases = (
        old_aliases
        + ", 'stop tips': 'tips', 'pause tips': 'tips', 'resume tips': 'tips', 'start tips': 'tips'"
        + ", 'stop announcements': 'announcements', 'resume announcements': 'announcements', 'start announcements': 'announcements'"
        + ", 'follow-up': 'followup', 'contacts': 'stakeholders', 'people': 'stakeholders'"
    )
    code = code.replace(old_aliases, new_aliases)

    # 3. Update the fallback "Available shortcuts" list
    old_fallback = (
        '"Available shortcuts: `brief` \\u00b7 `insights` \\u00b7 `presentation` '
        '\\u00b7 `bbr` \\u00b7 `rename` \\u00b7 `emoji` \\u00b7 `persona` '
        '\\u00b7 `scope` \\u00b7 `focus`\\n\\n"'
    )
    if old_fallback in code:
        new_fallback = (
            '"Available shortcuts: `brief` \\u00b7 `insights` \\u00b7 `presentation` '
            '\\u00b7 `bbr` \\u00b7 `stakeholders` \\u00b7 `followup`\\n" +\n'
            '      "`rename` \\u00b7 `emoji` \\u00b7 `persona` \\u00b7 `scope` '
            '\\u00b7 `focus` \\u00b7 `tips` \\u00b7 `announcements`\\n\\n"'
        )
        code = code.replace(old_fallback, new_fallback)
        print("  Updated fallback 'Available shortcuts' list")
    else:
        print("  WARN: Could not update fallback shortcuts list (non-fatal)")

    help_node["parameters"]["jsCode"] = code
    print("  Added 'tips' and 'announcements' to 'more' help details")
    return 1


def main():
    print("=== Fix 'more' Help for Education Commands ===\n")

    modify_workflow(
        WF_EVENTS_HANDLER,
        "Slack Events Handler.json",
        modify_events_handler,
    )

    print("\nDone! These now work:")
    print("  - `more tips` (also: `more stop tips`, `more resume tips`)")
    print("  - `more announcements` (also: `more stop announcements`, `more resume announcements`)")


if __name__ == "__main__":
    main()
