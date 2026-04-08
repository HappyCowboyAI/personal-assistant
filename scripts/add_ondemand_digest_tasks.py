#!/usr/bin/env python3
"""
Add Fetch User Tasks + Filter Urgent Tasks nodes to On-Demand Digest workflow,
mirroring the same pattern from Sales Digest.
"""

import json
import os
import subprocess
import sys
import uuid

N8N_URL = "https://scottai.trackslife.com"
API_KEY = os.environ["N8N_API_KEY"]
WORKFLOW_ID = "vxGajBdXFBaOCdkG"


def api(method, path, data=None):
    """Call n8n REST API via curl."""
    cmd = [
        "curl", "-s", "-X", method,
        f"{N8N_URL}{path}",
        "-H", f"X-N8N-API-KEY: {API_KEY}",
        "-H", "Content-Type: application/json",
    ]
    if data:
        cmd += ["-d", json.dumps(data)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        print(f"curl error: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)


def main():
    # 1. Fetch live workflow
    print("Fetching On-Demand Digest workflow...")
    wf = api("GET", f"/api/v1/workflows/{WORKFLOW_ID}")
    nodes = wf["nodes"]
    connections = wf["connections"]

    # Check if already applied
    node_names = [n["name"] for n in nodes]
    if "Fetch User Tasks" in node_names:
        print("SKIP: Fetch User Tasks already exists. Aborting.")
        sys.exit(0)

    # 2. Find positions of Filter User Opps and Resolve Identity
    filter_opps_pos = None
    resolve_pos = None
    for n in nodes:
        if n["name"] == "Filter User Opps":
            filter_opps_pos = n["position"]
        elif n["name"] == "Resolve Identity":
            resolve_pos = n["position"]

    if not filter_opps_pos or not resolve_pos:
        print("ERROR: Could not find Filter User Opps or Resolve Identity nodes")
        sys.exit(1)

    # Place new nodes between Filter User Opps and Resolve Identity
    # Shift Resolve Identity right to make room
    mid_x = (filter_opps_pos[0] + resolve_pos[0]) // 2
    fetch_tasks_pos = [filter_opps_pos[0] + 150, filter_opps_pos[1]]
    filter_tasks_pos = [filter_opps_pos[0] + 300, filter_opps_pos[1]]
    new_resolve_pos = [filter_opps_pos[0] + 450, filter_opps_pos[1]]

    # Update Resolve Identity position
    for n in nodes:
        if n["name"] == "Resolve Identity":
            n["position"] = new_resolve_pos

    # 3. Add Fetch User Tasks node (copied from Sales Digest)
    fetch_user_tasks_node = {
        "id": str(uuid.uuid4()),
        "name": "Fetch User Tasks",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": fetch_tasks_pos,
        "parameters": {
            "method": "POST",
            "url": "https://webhooks.workato.com/webhooks/rest/cfff4d3a-6f27-4ba4-9754-ac22c759ecaa/assistant_sf_read",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": '={{ JSON.stringify({ action: "get_tasks_digest", user_email: $json.email || "" }) }}',
            "options": {
                "timeout": 15000
            }
        },
        "onError": "continueRegularOutput",
        "alwaysOutputData": True
    }

    # 4. Add Filter Urgent Tasks node (copied from Sales Digest)
    filter_urgent_tasks_code = """// Filter tasks to overdue + due-this-week for digest
const taskResponse = $input.first().json;
const userData = $('Filter User Opps').first().json;
const rawTasks = (taskResponse.tasks || []);

const now = new Date();
const ptNow = new Date(now.toLocaleString("en-US", { timeZone: "America/Los_Angeles" }));
const todayStr = ptNow.toISOString().split("T")[0];

function daysUntil(dateStr) {
  if (!dateStr) return null;
  const due = new Date(dateStr + "T00:00:00");
  const today = new Date(todayStr + "T00:00:00");
  return Math.round((due - today) / 86400000);
}

function formatDate(dateStr) {
  if (!dateStr) return "";
  const d = new Date(dateStr + "T12:00:00");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

const overdue = [];
const dueThisWeek = [];

for (const t of rawTasks) {
  const days = daysUntil(t.ActivityDate);
  if (days === null) continue;
  const acct = (t.Account && t.Account.Name) || "";
  const entry = { subject: t.Subject || "Task", account: acct, days: Math.abs(days), daysRaw: days, date: formatDate(t.ActivityDate) };
  if (days < 0) overdue.push(entry);
  else if (days <= 7) dueThisWeek.push(entry);
}

// Build task context string for the prompt
let taskContext = "";

if (overdue.length > 0 || dueThisWeek.length > 0) {
  const lines = [];
  lines.push("TASK SUMMARY: " + overdue.length + " overdue, " + dueThisWeek.length + " due this week");
  lines.push("");

  overdue.sort((a, b) => b.days - a.days);
  for (const t of overdue.slice(0, 5)) {
    const acctTag = t.account ? " (" + t.account + ")" : "";
    lines.push("- OVERDUE (" + t.days + " days): " + t.subject + acctTag);
  }

  dueThisWeek.sort((a, b) => a.daysRaw - b.daysRaw);
  for (const t of dueThisWeek.slice(0, 5)) {
    const acctTag = t.account ? " (" + t.account + ")" : "";
    const dueLabel = t.daysRaw === 0 ? "TODAY" : t.daysRaw === 1 ? "TOMORROW" : "in " + t.daysRaw + " days";
    lines.push("- DUE " + dueLabel + ": " + t.subject + acctTag);
  }

  const remaining = Math.max(0, overdue.length - 5) + Math.max(0, dueThisWeek.length - 5);
  if (remaining > 0) lines.push("- ... and " + remaining + " more");

  taskContext = lines.join("\\n");
}

// Pass through all user data + task context
return [{ json: { ...userData, taskContext, taskOverdueCount: overdue.length, taskDueThisWeekCount: dueThisWeek.length } }];"""

    filter_urgent_tasks_node = {
        "id": str(uuid.uuid4()),
        "name": "Filter Urgent Tasks",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": filter_tasks_pos,
        "parameters": {
            "jsCode": filter_urgent_tasks_code
        }
    }

    nodes.append(fetch_user_tasks_node)
    nodes.append(filter_urgent_tasks_node)

    # 5. Rewire connections:
    # REMOVE: Filter User Opps → Resolve Identity
    # ADD: Filter User Opps → Fetch User Tasks → Filter Urgent Tasks → Resolve Identity
    if "Filter User Opps" in connections:
        old_targets = connections["Filter User Opps"]["main"][0]
        connections["Filter User Opps"]["main"][0] = [
            t for t in old_targets if t["node"] != "Resolve Identity"
        ]
        # Add connection to Fetch User Tasks
        connections["Filter User Opps"]["main"][0].append({
            "node": "Fetch User Tasks",
            "type": "main",
            "index": 0
        })

    connections["Fetch User Tasks"] = {
        "main": [[{
            "node": "Filter Urgent Tasks",
            "type": "main",
            "index": 0
        }]]
    }

    connections["Filter Urgent Tasks"] = {
        "main": [[{
            "node": "Resolve Identity",
            "type": "main",
            "index": 0
        }]]
    }

    # 6. Update Resolve Identity code
    for n in nodes:
        if n["name"] == "Resolve Identity":
            code = n["parameters"]["jsCode"]

            # a) Change data source reference
            code = code.replace(
                "$('Filter User Opps').first().json",
                "$('Filter Urgent Tasks').first().json",
                1  # only the first occurrence (the user data line)
            )

            # b) Add task context variable and prompt section before systemPrompt assembly
            # Find the line that builds systemPrompt and insert task section before it
            task_section = """
// === Task context (overdue + due this week) ===
const taskContext = user.taskContext || '';
const taskPromptSection = taskContext ? `
TASK CONTEXT:
${taskContext}

TASK SECTION INSTRUCTIONS:
If the task context above contains overdue or due-this-week tasks, you MUST include a *Tasks* section IMMEDIATELY after the header block (before The Lead). Format:

*Tasks \\u2014 N overdue, M due this week*
Use :red_circle: for overdue items and :warning: for due-this-week items. Show up to 5 items, each on its own line with account name in parentheses if available.
After the task items, add this line:
<https://glass.people.ai/sheet/514ff6d1-7e51-4bab-872e-b1f35ce13f5b|My Open Tasks> \\u00b7 <https://glass.people.ai/sheet/3be9132b-cf08-4f94-9164-651bb5804e51|My Completed> \\u00b7 <https://glass.people.ai/sheet/40ce97c4-0237-4afb-8d47-b10cf4792253|Last 30 Days>
Then add a divider block before continuing with The Lead.

If there are NO tasks in the context above, do NOT include a Tasks section at all. Start with The Lead as normal.` : '';

"""

            # Insert before the systemPrompt line
            old_system_prompt_line = "const systemPrompt = roleContext + '\\n\\n' + focusContext + '\\n\\n' + briefingStructure + '\\n\\n' + blockKitRules;"
            new_system_prompt_line = "const systemPrompt = roleContext + '\\n\\n' + focusContext + (taskPromptSection ? '\\n\\n' + taskPromptSection : '') + '\\n\\n' + briefingStructure + '\\n\\n' + blockKitRules;"

            if old_system_prompt_line in code:
                code = code.replace(old_system_prompt_line, task_section + new_system_prompt_line)
            else:
                print("WARNING: Could not find systemPrompt assembly line, trying alternate pattern...")
                # Try without escaped newlines
                alt_old = "const systemPrompt = roleContext + '\\n\\n' + focusContext + '\\n\\n' + briefingStructure + '\\n\\n' + blockKitRules;"
                if alt_old in code:
                    code = code.replace(alt_old, task_section + new_system_prompt_line)
                else:
                    print("ERROR: Could not find systemPrompt assembly line in Resolve Identity")
                    print("Looking for:", repr(old_system_prompt_line))
                    # Print context around 'systemPrompt' for debugging
                    for i, line in enumerate(code.split('\n')):
                        if 'systemPrompt' in line and 'roleContext' in line:
                            print(f"  Found at line {i}: {line}")
                    sys.exit(1)

            n["parameters"]["jsCode"] = code
            print("Updated Resolve Identity code.")
            break

    # 7. Push updated workflow
    print("Pushing updated workflow...")
    payload = {
        "name": wf["name"],
        "nodes": nodes,
        "connections": connections,
        "settings": wf.get("settings", {}),
        "staticData": wf.get("staticData", None),
    }
    result = api("PUT", f"/api/v1/workflows/{WORKFLOW_ID}", payload)

    if "id" in result:
        print(f"SUCCESS: Workflow updated (ID: {result['id']})")
    else:
        print(f"ERROR: {json.dumps(result, indent=2)}")
        sys.exit(1)

    # 8. Verify
    print("\n=== VERIFICATION ===")
    verify = api("GET", f"/api/v1/workflows/{WORKFLOW_ID}")
    v_nodes = {n["name"]: n for n in verify["nodes"]}
    v_conn = verify["connections"]

    # Check nodes exist
    for name in ["Fetch User Tasks", "Filter Urgent Tasks"]:
        if name in v_nodes:
            print(f"  [OK] Node '{name}' exists")
        else:
            print(f"  [FAIL] Node '{name}' NOT found")

    # Check connection chain
    chain_ok = True
    expected_chain = [
        ("Filter User Opps", "Fetch User Tasks"),
        ("Fetch User Tasks", "Filter Urgent Tasks"),
        ("Filter Urgent Tasks", "Resolve Identity"),
    ]
    for src, dst in expected_chain:
        targets = []
        if src in v_conn and "main" in v_conn[src]:
            for t in v_conn[src]["main"][0]:
                targets.append(t["node"])
        if dst in targets:
            print(f"  [OK] {src} -> {dst}")
        else:
            print(f"  [FAIL] {src} -> {dst} (found targets: {targets})")
            chain_ok = False

    # Verify old direct connection is removed
    if "Filter User Opps" in v_conn:
        direct_targets = [t["node"] for t in v_conn["Filter User Opps"]["main"][0]]
        if "Resolve Identity" in direct_targets:
            print("  [FAIL] Filter User Opps still directly connects to Resolve Identity")
            chain_ok = False
        else:
            print("  [OK] No direct Filter User Opps -> Resolve Identity connection")

    # Check Resolve Identity code
    ri_code = v_nodes.get("Resolve Identity", {}).get("parameters", {}).get("jsCode", "")
    if "taskContext" in ri_code:
        print("  [OK] Resolve Identity code contains 'taskContext'")
    else:
        print("  [FAIL] Resolve Identity code missing 'taskContext'")

    if "Filter Urgent Tasks" in ri_code:
        print("  [OK] Resolve Identity code references 'Filter Urgent Tasks'")
    else:
        print("  [FAIL] Resolve Identity code missing 'Filter Urgent Tasks' reference")

    if "taskPromptSection" in ri_code:
        print("  [OK] Resolve Identity systemPrompt includes taskPromptSection")
    else:
        print("  [FAIL] Resolve Identity systemPrompt missing taskPromptSection")

    print("\nDone.")


if __name__ == "__main__":
    main()
