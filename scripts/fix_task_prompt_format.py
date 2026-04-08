#!/usr/bin/env python3
"""Update task section prompt format in both digest workflows."""

import json
import os
import subprocess

N8N_URL = "https://scottai.trackslife.com"
API_KEY = os.environ["N8N_API_KEY"]

WORKFLOW_IDS = [
    "vxGajBdXFBaOCdkG",  # On-Demand Digest
    "7sinwSgjkEA40zDj",  # Sales Digest
]

OLD_SECTION = """TASK SECTION INSTRUCTIONS:
If the task context above contains overdue or due-this-week tasks, you MUST include a *Tasks* section IMMEDIATELY after the header block (before The Lead). Format:

*Tasks \u2014 N overdue, M due this week*
Use :red_circle: for overdue items and :warning: for due-this-week items. Show up to 5 items, each on its own line with account name in parentheses if available.
After the task items, add this line:
<https://glass.people.ai/sheet/514ff6d1-7e51-4bab-872e-b1f35ce13f5b|My Open Tasks> \u00b7 <https://glass.people.ai/sheet/3be9132b-cf08-4f94-9164-651bb5804e51|My Completed> \u00b7 <https://glass.people.ai/sheet/40ce97c4-0237-4afb-8d47-b10cf4792253|Last 30 Days>
Then add a divider block before continuing with The Lead.

If there are NO tasks in the context above, do NOT include a Tasks section at all. Start with The Lead as normal."""

NEW_SECTION = """TASK SECTION INSTRUCTIONS:
If the task context above contains overdue or due-this-week tasks, you MUST include a Tasks section IMMEDIATELY after the header block (before The Lead). Use this exact structure:

1. Add a divider block
2. Add a section block with this format for the header line (all on ONE line):
   - If overdue > 0 and due this week > 0: ":clipboard: *Open Tasks \u2014 N overdue, M due this week* \u00b7 <https://glass.people.ai/sheet/514ff6d1-7e51-4bab-872e-b1f35ce13f5b|My Open Tasks> \u00b7 <https://glass.people.ai/sheet/3be9132b-cf08-4f94-9164-651bb5804e51|My Completed> \u00b7 <https://glass.people.ai/sheet/40ce97c4-0237-4afb-8d47-b10cf4792253|Last 30 Days>"
   - If only overdue > 0: ":clipboard: *Open Tasks \u2014 N overdue* \u00b7 <links as above>"
   - If only due this week > 0: ":clipboard: *Open Tasks \u2014 M due this week* \u00b7 <links as above>"
3. Add a section block listing each task on its own line:
   - Use :red_circle: for overdue: ":red_circle: Task subject (Account) \u2014 N days overdue"
   - Use :warning: for due this week: ":warning: Task subject (Account) \u2014 due Apr 6"
   - Show up to 5 items. Use short friendly dates (due today, due tomorrow, due Thu, due Apr 6).
4. Add a divider block after the task items, before continuing with The Lead.

If there are NO tasks in the context above, do NOT include a Tasks section at all. Start directly with The Lead as normal."""


def api_get(path):
    result = subprocess.run(
        ["curl", "-s", "-H", f"X-N8N-API-KEY: {API_KEY}", f"{N8N_URL}/api/v1{path}"],
        capture_output=True, text=True
    )
    return json.loads(result.stdout)


def api_put(path, data):
    result = subprocess.run(
        ["curl", "-s", "-X", "PUT", "-H", f"X-N8N-API-KEY: {API_KEY}",
         "-H", "Content-Type: application/json",
         f"{N8N_URL}/api/v1{path}", "-d", json.dumps(data)],
        capture_output=True, text=True
    )
    return json.loads(result.stdout)


def main():
    for wf_id in WORKFLOW_IDS:
        wf = api_get(f"/workflows/{wf_id}")
        print(f"Updating {wf['name']} ({wf_id})...")

        for node in wf["nodes"]:
            if node["name"] == "Resolve Identity":
                code = node["parameters"]["jsCode"]
                if OLD_SECTION in code:
                    code = code.replace(OLD_SECTION, NEW_SECTION)
                    node["parameters"]["jsCode"] = code
                    print("  Replaced task section format")
                else:
                    print("  WARNING: Old section not found exactly, searching...")
                    # Try to find any task section instructions
                    if "TASK SECTION INSTRUCTIONS:" in code:
                        # Find start and end
                        start = code.index("TASK SECTION INSTRUCTIONS:")
                        # Find end - look for next section or the closing backtick
                        end_marker = "If there are NO tasks"
                        if end_marker in code:
                            end_pos = code.index(end_marker, start)
                            # Find the end of that line
                            end_line = code.index("\n", end_pos + len(end_marker))
                            # Check for closing backtick
                            remaining = code[end_line:end_line+50]
                            if "` : '';" in remaining or "as normal.`" in remaining:
                                end_line = code.index("`", end_pos)
                            old_text = code[start:end_line]
                            # Don't include the closing backtick
                            code = code[:start] + NEW_SECTION + code[end_line:]
                            node["parameters"]["jsCode"] = code
                            print("  Replaced via fuzzy match")
                        else:
                            print("  ERROR: Could not find task section boundaries")
                    else:
                        print("  ERROR: No TASK SECTION INSTRUCTIONS found")

        payload = {
            "name": wf["name"],
            "nodes": wf["nodes"],
            "connections": wf["connections"],
            "settings": wf["settings"],
            "staticData": wf.get("staticData"),
        }
        result = api_put(f"/workflows/{wf_id}", payload)

        # Verify
        for n in result.get("nodes", []):
            if n["name"] == "Resolve Identity":
                code = n["parameters"]["jsCode"]
                has_clipboard = ":clipboard:" in code
                has_open_tasks = "Open Tasks" in code
                print(f"  Verified: clipboard={has_clipboard}, Open Tasks={has_open_tasks}")


if __name__ == "__main__":
    main()
