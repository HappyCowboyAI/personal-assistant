#!/usr/bin/env python3
"""Fix the Digest Tasks Receiver test workflow Parse Tasks node."""

import json
import os
import urllib.request
import ssl

N8N_URL = "https://scottai.trackslife.com"
API_KEY = os.environ["N8N_API_KEY"]
WORKFLOW_ID = "k28HzSxYjwzwNS2m"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def api(method, path, data=None):
    url = f"{N8N_URL}/api/v1{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method,
                                headers={"X-N8N-API-KEY": API_KEY,
                                         "Content-Type": "application/json"})
    with urllib.request.urlopen(req, context=ctx) as resp:
        return json.load(resp)

PARSE_TASKS_CODE = r"""
const body = $input.first().json.body || $input.first().json;
const userEmail = body.user_email || "";
const tasks = body.tasks || [];

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

for (const t of tasks) {
  const days = daysUntil(t.ActivityDate);
  if (days === null) continue;
  const acct = (t.Account && t.Account.Name) || "";
  const entry = { subject: t.Subject || "Task", account: acct, days: Math.abs(days), daysRaw: days, date: formatDate(t.ActivityDate) };
  if (days < 0) overdue.push(entry);
  else if (days <= 7) dueThisWeek.push(entry);
}

const blocks = [];

if (overdue.length === 0 && dueThisWeek.length === 0) {
  // Nothing urgent — send a test message anyway so we can see it worked
  blocks.push({ type: "section", text: { type: "mrkdwn", text: "*Tasks*\nAll caught up! No overdue or due-this-week tasks." } });
  return [{ json: { blocks: JSON.stringify(blocks), text: "Tasks: all caught up" } }];
}

blocks.push({ type: "section", text: { type: "mrkdwn", text: "*Tasks*" } });

const lines = [];
overdue.sort((a, b) => b.days - a.days);
for (const t of overdue.slice(0, 3)) {
  const acctTag = t.account ? " (" + t.account + ")" : "";
  lines.push(":red_circle: " + t.subject.substring(0, 80) + acctTag + " \u2014 *" + t.days + " days overdue*");
}

dueThisWeek.sort((a, b) => a.daysRaw - b.daysRaw);
for (const t of dueThisWeek.slice(0, 3)) {
  const acctTag = t.account ? " (" + t.account + ")" : "";
  const label = t.daysRaw === 0 ? "*due today*" : t.daysRaw === 1 ? "*due tomorrow*" : "due " + t.date;
  lines.push(":warning: " + t.subject.substring(0, 80) + acctTag + " \u2014 " + label);
}

const remaining = Math.max(0, overdue.length - 3) + Math.max(0, dueThisWeek.length - 3);
if (remaining > 0) lines.push("_and " + remaining + " more..._");
lines.push("\nType `tasks` for the full list.");

blocks.push({ type: "section", text: { type: "mrkdwn", text: lines.join("\n") } });

return [{ json: { blocks: JSON.stringify(blocks), text: overdue.length + " overdue, " + dueThisWeek.length + " due this week" } }];
""".strip()

def main():
    wf = api("GET", f"/workflows/{WORKFLOW_ID}")

    for node in wf["nodes"]:
        if node["name"] == "Parse Tasks":
            node["parameters"]["jsCode"] = PARSE_TASKS_CODE

    payload = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": wf["settings"],
        "staticData": wf.get("staticData"),
    }
    result = api("PUT", f"/workflows/{WORKFLOW_ID}", payload)
    print(f"Updated: {result['name']} — {len(result['nodes'])} nodes")

if __name__ == "__main__":
    main()
