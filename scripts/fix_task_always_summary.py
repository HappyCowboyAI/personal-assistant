#!/usr/bin/env python3
"""Show task summary whenever open tasks exist, but only list overdue/due-today items."""

import json
import os
import subprocess

N8N_URL = "https://scottai.trackslife.com"
API_KEY = os.environ["N8N_API_KEY"]

WORKFLOW_IDS = [
    "vxGajBdXFBaOCdkG",  # On-Demand Digest
    "7sinwSgjkEA40zDj",  # Sales Digest
]

NEW_FILTER_CODE = r"""// Filter tasks for digest: summary always shown if open tasks exist,
// but only list overdue + due today items individually.
const supabaseResult = $input.first().json;
const userData = $('Filter User Opps').first().json;

// Parse tasks from Supabase pending_actions draft_content
let rawTasks = [];
try {
  if (supabaseResult.draft_content) {
    rawTasks = JSON.parse(supabaseResult.draft_content);
  } else if (Array.isArray(supabaseResult)) {
    const row = supabaseResult[0];
    if (row && row.draft_content) {
      rawTasks = JSON.parse(row.draft_content);
    }
  }
} catch(e) {
  rawTasks = [];
}

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

const totalOpen = rawTasks.length;
const overdue = [];
const dueToday = [];

for (const t of rawTasks) {
  const days = daysUntil(t.ActivityDate);
  if (days === null) continue;
  const acct = (t.Account && t.Account.Name) || "";
  const entry = { subject: t.Subject || "Task", account: acct, days: Math.abs(days), daysRaw: days, date: formatDate(t.ActivityDate) };
  if (days < 0) overdue.push(entry);
  else if (days === 0) dueToday.push(entry);
}

// Build task context string for the prompt
let taskContext = "";

if (totalOpen > 0) {
  const lines = [];
  lines.push("TOTAL OPEN TASKS: " + totalOpen);
  lines.push("OVERDUE: " + overdue.length);
  lines.push("DUE TODAY: " + dueToday.length);
  lines.push("");

  if (overdue.length > 0 || dueToday.length > 0) {
    lines.push("URGENT TASK DETAILS:");
    overdue.sort((a, b) => b.days - a.days);
    for (const t of overdue.slice(0, 5)) {
      const acctTag = t.account ? " (" + t.account + ")" : "";
      lines.push("- OVERDUE (" + t.days + " days): " + t.subject + acctTag);
    }
    for (const t of dueToday.slice(0, 5)) {
      const acctTag = t.account ? " (" + t.account + ")" : "";
      lines.push("- DUE TODAY: " + t.subject + acctTag);
    }
  }

  taskContext = lines.join("\n");
}

// Pass through all user data + task context
return [{ json: { ...userData, taskContext, taskTotalOpen: totalOpen, taskOverdueCount: overdue.length, taskDueTodayCount: dueToday.length } }];
"""

# Update the prompt instructions
OLD_PROMPT_INSTRUCTIONS = """TASK SECTION INSTRUCTIONS:
If the task context above contains overdue or due-this-week tasks, you MUST include a Tasks section IMMEDIATELY after the header block (before The Lead). Use this exact structure:

1. Add a divider block
2. Add a section block with this format for the header line (all on ONE line):
   - If overdue > 0 and due today > 0: ":clipboard: *Open Tasks \u2014 N overdue, M due today*"""

# We need to find and replace the entire TASK SECTION INSTRUCTIONS block
# Let's search for it and replace up to the closing marker

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


NEW_PROMPT_INSTRUCTIONS = """TASK SECTION INSTRUCTIONS:
The task context above tells you the total open tasks, how many are overdue, and how many are due today.

If total open tasks > 0, you MUST include a Tasks section IMMEDIATELY after the header block (before The Lead). Use this exact structure:

1. Add a divider block
2. Add a section block with the header line (all on ONE line). Build it based on counts:
   - Base: ":clipboard: *Open Tasks \u2014 N open*"
   - If overdue > 0, append: ", X overdue"
   - If due today > 0, append: ", Y due today"
   - Always append links: " \u00b7 <https://glass.people.ai/sheet/514ff6d1-7e51-4bab-872e-b1f35ce13f5b|My Open Tasks> \u00b7 <https://glass.people.ai/sheet/3be9132b-cf08-4f94-9164-651bb5804e51|My Completed> \u00b7 <https://glass.people.ai/sheet/40ce97c4-0237-4afb-8d47-b10cf4792253|Last 30 Days>"
   - Examples: ":clipboard: *Open Tasks \u2014 3 open, 2 overdue* \u00b7 links", ":clipboard: *Open Tasks \u2014 1 open* \u00b7 links"
3. ONLY if there are overdue or due-today tasks in URGENT TASK DETAILS, add a section block listing each:
   - Use :red_circle: for overdue: ":red_circle: Task subject (Account) \u2014 N days overdue"
   - Use :warning: for due today: ":warning: Task subject (Account) \u2014 due today"
   - Show up to 5 items. If no urgent tasks, skip this block entirely.
4. Add a divider block after the task section.
5. Add a section block with ":zap: *Pipeline Brief*" to re-anchor the reader into pipeline content.
6. Then continue with The Lead.

If total open tasks = 0, do NOT include a Tasks section at all. Start directly with The Lead as normal."""


def main():
    for wf_id in WORKFLOW_IDS:
        wf = api_get(f"/workflows/{wf_id}")
        print(f"Updating {wf['name']} ({wf_id})...")

        for node in wf["nodes"]:
            if node["name"] == "Filter Urgent Tasks":
                node["parameters"]["jsCode"] = NEW_FILTER_CODE.strip()
                print("  Updated Filter Urgent Tasks code")

            if node["name"] == "Resolve Identity":
                code = node["parameters"]["jsCode"]

                # Find and replace the TASK SECTION INSTRUCTIONS block
                start_marker = "TASK SECTION INSTRUCTIONS:"
                end_marker = "If there are NO tasks in the context above, do NOT include a Tasks section at all. Start directly with The Lead as normal."

                start_idx = code.find(start_marker)
                end_idx = code.find(end_marker)

                if start_idx >= 0 and end_idx >= 0:
                    end_idx += len(end_marker)
                    code = code[:start_idx] + NEW_PROMPT_INSTRUCTIONS + code[end_idx:]
                    print("  Replaced TASK SECTION INSTRUCTIONS block")
                else:
                    print(f"  WARNING: Could not find instruction block (start={start_idx}, end={end_idx})")

                node["parameters"]["jsCode"] = code

        payload = {
            "name": wf["name"],
            "nodes": wf["nodes"],
            "connections": wf["connections"],
            "settings": wf["settings"],
            "staticData": wf.get("staticData"),
        }
        result = api_put(f"/workflows/{wf_id}", payload)

        for n in result.get("nodes", []):
            if n["name"] == "Filter Urgent Tasks":
                code = n["parameters"]["jsCode"]
                print(f"  Filter: totalOpen={('taskTotalOpen' in code)}, overdue={('overdue' in code)}, dueToday={('dueToday' in code)}")
            if n["name"] == "Resolve Identity":
                code = n["parameters"]["jsCode"]
                print(f"  Prompt: 'N open'={'N open' in code}, 'total open tasks'={'total open tasks' in code}")


if __name__ == "__main__":
    main()
