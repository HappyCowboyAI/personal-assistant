#!/usr/bin/env python3
"""Update Filter Urgent Tasks to only show overdue + due today."""

import json
import os
import subprocess

N8N_URL = "https://scottai.trackslife.com"
API_KEY = os.environ["N8N_API_KEY"]

WORKFLOW_IDS = [
    "vxGajBdXFBaOCdkG",  # On-Demand Digest
    "7sinwSgjkEA40zDj",  # Sales Digest
]

NEW_CODE = r"""// Filter tasks to overdue + due today only for digest
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

if (overdue.length > 0 || dueToday.length > 0) {
  const lines = [];
  lines.push("TASK SUMMARY: " + overdue.length + " overdue, " + dueToday.length + " due today");
  lines.push("");

  overdue.sort((a, b) => b.days - a.days);
  for (const t of overdue.slice(0, 5)) {
    const acctTag = t.account ? " (" + t.account + ")" : "";
    lines.push("- OVERDUE (" + t.days + " days): " + t.subject + acctTag);
  }

  for (const t of dueToday.slice(0, 5)) {
    const acctTag = t.account ? " (" + t.account + ")" : "";
    lines.push("- DUE TODAY: " + t.subject + acctTag);
  }

  const remaining = Math.max(0, overdue.length - 5) + Math.max(0, dueToday.length - 5);
  if (remaining > 0) lines.push("- ... and " + remaining + " more");

  taskContext = lines.join("\n");
}

// Pass through all user data + task context
return [{ json: { ...userData, taskContext, taskOverdueCount: overdue.length, taskDueTodayCount: dueToday.length } }];
"""

# Also update the prompt to say "due today" instead of "due this week"
OLD_PROMPT_SUMMARY = """   - If overdue > 0 and due this week > 0: ":clipboard: *Open Tasks \u2014 N overdue, M due this week*"""
NEW_PROMPT_SUMMARY = """   - If overdue > 0 and due today > 0: ":clipboard: *Open Tasks \u2014 N overdue, M due today*"""

OLD_PROMPT_ONLY_WEEK = """   - If only due this week > 0: ":clipboard: *Open Tasks \u2014 M due this week*"""
NEW_PROMPT_ONLY_TODAY = """   - If only due today > 0: ":clipboard: *Open Tasks \u2014 M due today*"""

OLD_PROMPT_WARNING = """   - Use :warning: for due this week: ":warning: Task subject (Account) \u2014 due Apr 6"
   - Show up to 5 items. Use short friendly dates (due today, due tomorrow, due Thu, due Apr 6)."""
NEW_PROMPT_WARNING = """   - Use :warning: for due today: ":warning: Task subject (Account) \u2014 due today"
   - Show up to 5 items."""


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
            if node["name"] == "Filter Urgent Tasks":
                node["parameters"]["jsCode"] = NEW_CODE.strip()
                print("  Updated Filter Urgent Tasks code")

            if node["name"] == "Resolve Identity":
                code = node["parameters"]["jsCode"]
                code = code.replace(OLD_PROMPT_SUMMARY, NEW_PROMPT_SUMMARY)
                code = code.replace(OLD_PROMPT_ONLY_WEEK, NEW_PROMPT_ONLY_TODAY)
                code = code.replace(OLD_PROMPT_WARNING, NEW_PROMPT_WARNING)
                # Also update the taskAgentNote check field name
                code = code.replace("taskDueThisWeekCount", "taskDueTodayCount")
                node["parameters"]["jsCode"] = code
                print("  Updated Resolve Identity prompt (this week -> today)")

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
                has_due_today = "dueToday" in code
                no_due_week = "dueThisWeek" not in code
                print(f"  Filter verified: dueToday={has_due_today}, no dueThisWeek={no_due_week}")
            if n["name"] == "Resolve Identity":
                code = n["parameters"]["jsCode"]
                print(f"  Prompt has 'due today': {'due today' in code}")


if __name__ == "__main__":
    main()
