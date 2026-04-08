#!/usr/bin/env python3
"""Add Fetch User Tasks + Filter Urgent Tasks nodes to Sales Digest workflow."""

import json
import os
import subprocess
import sys
import uuid

API_KEY = os.environ.get("N8N_API_KEY", "")
BASE = "https://scottai.trackslife.com/api/v1"
WF_ID = "7sinwSgjkEA40zDj"


def curl_get(url):
    r = subprocess.run(
        ["curl", "-s", "-H", f"X-N8N-API-KEY: {API_KEY}", url],
        capture_output=True, text=True
    )
    return json.loads(r.stdout)


def curl_put(url, data):
    r = subprocess.run(
        ["curl", "-s", "-X", "PUT", "-H", f"X-N8N-API-KEY: {API_KEY}",
         "-H", "Content-Type: application/json",
         "-d", json.dumps(data), url],
        capture_output=True, text=True
    )
    return json.loads(r.stdout)


def main():
    if not API_KEY:
        print("ERROR: N8N_API_KEY not set")
        sys.exit(1)

    # Step 1: Fetch live workflow
    print("Fetching workflow...")
    wf = curl_get(f"{BASE}/workflows/{WF_ID}")
    if "nodes" not in wf:
        print("ERROR: Could not fetch workflow:", json.dumps(wf, indent=2)[:500])
        sys.exit(1)

    nodes = wf["nodes"]
    connections = wf["connections"]

    # Find key nodes
    filter_opps = None
    resolve_identity = None
    for n in nodes:
        if n["name"] == "Filter User Opps":
            filter_opps = n
        elif n["name"] == "Resolve Identity":
            resolve_identity = n

    if not filter_opps or not resolve_identity:
        print("ERROR: Could not find Filter User Opps or Resolve Identity")
        print("Available nodes:", [n["name"] for n in nodes])
        sys.exit(1)

    print(f"Found Filter User Opps at {filter_opps['position']}")
    print(f"Found Resolve Identity at {resolve_identity['position']}")

    # Calculate positions (midpoints)
    fo_x, fo_y = filter_opps["position"]
    ri_x, ri_y = resolve_identity["position"]
    span_x = ri_x - fo_x
    fetch_pos = [fo_x + span_x // 3, (fo_y + ri_y) // 2]
    filter_pos = [fo_x + 2 * span_x // 3, (fo_y + ri_y) // 2]

    # Node 1: Fetch User Tasks
    fetch_node = {
        "id": str(uuid.uuid4()),
        "name": "Fetch User Tasks",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": fetch_pos,
        "parameters": {
            "method": "POST",
            "url": "https://webhooks.workato.com/webhooks/rest/cfff4d3a-6f27-4ba4-9754-ac22c759ecaa/assistant_sf_read",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ action: \"get_tasks_digest\", user_email: $json.email || \"\" }) }}",
            "options": {
                "timeout": 15000
            }
        },
        "onError": "continueRegularOutput",
        "alwaysOutputData": True
    }

    # Node 2: Filter Urgent Tasks (Code)
    filter_code = r'''// Filter tasks to overdue + due-this-week for digest
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

  taskContext = lines.join("\n");
}

// Pass through all user data + task context
return [{ json: { ...userData, taskContext, taskOverdueCount: overdue.length, taskDueThisWeekCount: dueThisWeek.length } }];'''

    filter_node = {
        "id": str(uuid.uuid4()),
        "name": "Filter Urgent Tasks",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": filter_pos,
        "parameters": {
            "jsCode": filter_code
        }
    }

    # Add new nodes
    nodes.append(fetch_node)
    nodes.append(filter_node)

    # Rewire connections
    # Remove Filter User Opps → Resolve Identity
    if "Filter User Opps" in connections:
        main_outputs = connections["Filter User Opps"].get("main", [[]])
        for output_conns in main_outputs:
            original_len = len(output_conns)
            output_conns[:] = [c for c in output_conns if c.get("node") != "Resolve Identity"]
            if len(output_conns) < original_len:
                print("Removed Filter User Opps → Resolve Identity connection")
        # Add Filter User Opps → Fetch User Tasks
        main_outputs[0].append({"node": "Fetch User Tasks", "type": "main", "index": 0})
        print("Added Filter User Opps → Fetch User Tasks")

    # Add Fetch User Tasks → Filter Urgent Tasks
    connections["Fetch User Tasks"] = {
        "main": [[{"node": "Filter Urgent Tasks", "type": "main", "index": 0}]]
    }
    print("Added Fetch User Tasks → Filter Urgent Tasks")

    # Add Filter Urgent Tasks → Resolve Identity
    connections["Filter Urgent Tasks"] = {
        "main": [[{"node": "Resolve Identity", "type": "main", "index": 0}]]
    }
    print("Added Filter Urgent Tasks → Resolve Identity")

    # Step 3: Update Resolve Identity code
    ri_code = resolve_identity["parameters"].get("jsCode", "")

    # Change 1: Update data source
    old_ref = "$('Filter User Opps').first().json"
    new_ref = "$('Filter Urgent Tasks').first().json"
    if old_ref in ri_code:
        ri_code = ri_code.replace(old_ref, new_ref, 1)
        print("Updated Resolve Identity data source reference")
    else:
        print(f"WARNING: Could not find '{old_ref}' in Resolve Identity code")
        # Print first 200 chars for debugging
        print(f"Code starts with: {ri_code[:200]}")

    # Change 2: Add task prompt section before systemPrompt assembly
    # Find the systemPrompt assembly line
    old_assembly = "const systemPrompt = roleContext + '\\n\\n' + focusContext + '\\n\\n' + briefingStructure + '\\n\\n' + blockKitRules;"

    task_section = r"""
// === Task context (overdue + due this week) ===
const taskContext = user.taskContext || '';
const taskPromptSection = taskContext ? `
TASK CONTEXT:
${taskContext}

TASK SECTION INSTRUCTIONS:
If the task context above contains overdue or due-this-week tasks, you MUST include a *Tasks* section IMMEDIATELY after the header block (before The Lead). Format:

*Tasks \u2014 N overdue, M due this week*
Use :red_circle: for overdue items and :warning: for due-this-week items. Show up to 5 items, each on its own line with account name in parentheses if available.
After the task items, add this line:
<https://glass.people.ai/sheet/514ff6d1-7e51-4bab-872e-b1f35ce13f5b|My Open Tasks> \u00b7 <https://glass.people.ai/sheet/3be9132b-cf08-4f94-9164-651bb5804e51|My Completed> \u00b7 <https://glass.people.ai/sheet/40ce97c4-0237-4afb-8d47-b10cf4792253|Last 30 Days>
Then add a divider block before continuing with The Lead.

If there are NO tasks in the context above, do NOT include a Tasks section at all. Start with The Lead as normal.` : '';
"""

    new_assembly = "const systemPrompt = roleContext + '\\n\\n' + focusContext + (taskPromptSection ? '\\n\\n' + taskPromptSection : '') + '\\n\\n' + briefingStructure + '\\n\\n' + blockKitRules;"

    if old_assembly in ri_code:
        ri_code = ri_code.replace(old_assembly, task_section + "\n" + new_assembly)
        print("Added task prompt section and updated systemPrompt assembly")
    else:
        print("WARNING: Could not find exact systemPrompt assembly line")
        # Try to find it with different quote styles
        for variant in [
            "const systemPrompt = roleContext + '\\n\\n' + focusContext + '\\n\\n' + briefingStructure + '\\n\\n' + blockKitRules",
            'const systemPrompt = roleContext + "\\n\\n" + focusContext + "\\n\\n" + briefingStructure + "\\n\\n" + blockKitRules',
        ]:
            if variant in ri_code:
                print(f"Found variant: {variant[:80]}...")
                break
        # Search for partial match
        if "const systemPrompt" in ri_code:
            idx = ri_code.index("const systemPrompt")
            print(f"Found 'const systemPrompt' at offset {idx}")
            print(f"Context: ...{ri_code[idx:idx+200]}...")

    resolve_identity["parameters"]["jsCode"] = ri_code

    # Push updated workflow
    payload = {
        "name": wf["name"],
        "nodes": nodes,
        "connections": connections,
        "settings": wf.get("settings", {}),
        "staticData": wf.get("staticData", None)
    }

    print("\nPushing updated workflow...")
    result = curl_put(f"{BASE}/workflows/{WF_ID}", payload)

    if "id" in result:
        print(f"SUCCESS: Workflow updated (ID: {result['id']})")
    else:
        print("ERROR pushing workflow:")
        print(json.dumps(result, indent=2)[:1000])
        sys.exit(1)

    # Verification
    print("\n=== VERIFICATION ===")
    wf2 = curl_get(f"{BASE}/workflows/{WF_ID}")
    node_names = [n["name"] for n in wf2["nodes"]]

    # Check nodes exist
    for name in ["Fetch User Tasks", "Filter Urgent Tasks"]:
        if name in node_names:
            print(f"  [OK] Node '{name}' exists")
        else:
            print(f"  [FAIL] Node '{name}' NOT found")

    # Check connections
    conns = wf2["connections"]

    def check_conn(src, dst):
        if src in conns:
            for output in conns[src].get("main", []):
                for c in output:
                    if c.get("node") == dst:
                        print(f"  [OK] {src} → {dst}")
                        return
        print(f"  [FAIL] {src} → {dst} NOT found")

    check_conn("Filter User Opps", "Fetch User Tasks")
    check_conn("Fetch User Tasks", "Filter Urgent Tasks")
    check_conn("Filter Urgent Tasks", "Resolve Identity")

    # Check old connection removed
    old_exists = False
    if "Filter User Opps" in conns:
        for output in conns["Filter User Opps"].get("main", []):
            for c in output:
                if c.get("node") == "Resolve Identity":
                    old_exists = True
    if old_exists:
        print("  [FAIL] Filter User Opps → Resolve Identity still exists (should be removed)")
    else:
        print("  [OK] Filter User Opps → Resolve Identity removed")

    # Check Resolve Identity code
    for n in wf2["nodes"]:
        if n["name"] == "Resolve Identity":
            code = n["parameters"].get("jsCode", "")
            if "taskContext" in code:
                print("  [OK] Resolve Identity code contains 'taskContext'")
            else:
                print("  [FAIL] Resolve Identity code missing 'taskContext'")
            if "Filter Urgent Tasks" in code:
                print("  [OK] Resolve Identity code references 'Filter Urgent Tasks'")
            else:
                print("  [FAIL] Resolve Identity code missing 'Filter Urgent Tasks' reference")
            break

    print("\nDone.")


if __name__ == "__main__":
    main()
