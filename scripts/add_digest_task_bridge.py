#!/usr/bin/env python3
"""
Add async task bridge for digest workflows.

Workato returns {"status":"ok"} immediately and POSTs task data asynchronously
to /webhook/digest-tasks. This script:

1. Activates the Digest Tasks Receiver workflow (stores tasks in Supabase)
2. Updates Digest Tasks Receiver to store in Supabase pending_actions
3. Updates Sales Digest with Wait → Read → updated Filter → Cleanup nodes
4. Updates On-Demand Digest with the same changes

Uses curl for all n8n API calls (urllib has SSL issues).
"""

import json
import os
import subprocess
import sys
import uuid

API_KEY = os.environ.get("N8N_API_KEY", "")
BASE = "https://scottai.trackslife.com/api/v1"

WF_RECEIVER = "k28HzSxYjwzwNS2m"
WF_SALES_DIGEST = "7sinwSgjkEA40zDj"
WF_ON_DEMAND_DIGEST = "vxGajBdXFBaOCdkG"

SUPABASE_URL = "https://rhrlnkbphxntxxxcrgvv.supabase.co"
SUPABASE_CRED = {"supabaseApi": {"id": "ASRWWkQ0RSMOpNF1", "name": "Supabase account"}}


def uid():
    return str(uuid.uuid4())


def curl(method, path, data=None):
    """Call n8n REST API via curl."""
    cmd = [
        "curl", "-s", "-X", method,
        f"https://scottai.trackslife.com{path}",
        "-H", f"X-N8N-API-KEY: {API_KEY}",
        "-H", "Content-Type: application/json",
    ]
    if data:
        cmd += ["-d", json.dumps(data)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        print(f"curl error: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"JSON decode error. stdout: {result.stdout[:500]}")
        sys.exit(1)


def check_conn(conns, src, dst):
    """Check if a connection exists from src to dst."""
    if src in conns:
        for output in conns[src].get("main", []):
            for c in output:
                if c.get("node") == dst:
                    return True
    return False


def remove_conn(conns, src, dst):
    """Remove connections from src to dst."""
    if src in conns and "main" in conns[src]:
        for output in conns[src]["main"]:
            output[:] = [c for c in output if c.get("node") != dst]


def add_conn(conns, src, dst, src_output=0, dst_input=0):
    """Add a connection from src to dst."""
    if src not in conns:
        conns[src] = {"main": [[]]}
    while len(conns[src]["main"]) <= src_output:
        conns[src]["main"].append([])
    conns[src]["main"][src_output].append({
        "node": dst,
        "type": "main",
        "index": dst_input
    })


def push_workflow(wf_id, wf):
    """PUT a workflow back to n8n."""
    payload = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": wf.get("settings", {}),
        "staticData": wf.get("staticData", None),
    }
    return curl("PUT", f"/api/v1/workflows/{wf_id}", payload)


# ─── Filter Urgent Tasks code that reads from Supabase ───────────────
FILTER_URGENT_TASKS_CODE = r"""// Filter tasks to overdue + due-this-week for digest
// Tasks are read from Supabase pending_actions (stored by Digest Tasks Receiver callback)
const supabaseResult = $input.first().json;
const userData = $('Filter User Opps').first().json;

// Parse tasks from Supabase pending_actions draft_content
let rawTasks = [];
try {
  if (Array.isArray(supabaseResult)) {
    // HTTP Request returns array when response is JSON array
    const row = supabaseResult[0];
    if (row && row.draft_content) {
      rawTasks = JSON.parse(row.draft_content);
    }
  } else if (supabaseResult.draft_content) {
    rawTasks = JSON.parse(supabaseResult.draft_content);
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
return [{ json: { ...userData, taskContext, taskOverdueCount: overdue.length, taskDueThisWeekCount: dueThisWeek.length } }];"""


def update_receiver():
    """Update Digest Tasks Receiver to store tasks in Supabase."""
    print("\n" + "=" * 60)
    print("STEP 1: Update Digest Tasks Receiver")
    print("=" * 60)

    # Activate first
    print("Activating Digest Tasks Receiver...")
    result = curl("POST", f"/api/v1/workflows/{WF_RECEIVER}/activate")
    if "active" in result:
        print(f"  Activation result: active={result.get('active')}")
    else:
        print(f"  Activation response: {json.dumps(result)[:300]}")

    # Fetch live workflow
    print("Fetching Digest Tasks Receiver workflow...")
    wf = curl("GET", f"/api/v1/workflows/{WF_RECEIVER}")
    if "nodes" not in wf:
        print(f"ERROR: Could not fetch workflow: {json.dumps(wf)[:500]}")
        sys.exit(1)

    nodes = wf["nodes"]
    connections = wf["connections"]
    node_names = [n["name"] for n in nodes]
    print(f"  Current nodes: {node_names}")

    # Find the webhook node
    webhook_node = None
    for n in nodes:
        if "webhook" in n["type"].lower() or "Webhook" in n["name"]:
            webhook_node = n
            break

    if not webhook_node:
        print("ERROR: No webhook node found")
        sys.exit(1)

    print(f"  Webhook node: {webhook_node['name']} at {webhook_node['position']}")

    # Find existing Parse Tasks node (or similar)
    parse_node = None
    for n in nodes:
        if "parse" in n["name"].lower() or "task" in n["name"].lower():
            if n["name"] != webhook_node["name"]:
                parse_node = n
                break

    # Remove all nodes except the webhook
    webhook_name = webhook_node["name"]
    wx, wy = webhook_node["position"]

    # Build new Parse Tasks code node
    parse_tasks_node = {
        "id": uid(),
        "name": "Parse Tasks",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [wx + 200, wy],
        "parameters": {
            "jsCode": """const body = $input.first().json.body || $input.first().json;
const userEmail = (body.user_email || "").toLowerCase().trim();
const tasks = body.tasks || [];
const count = tasks.length;

// Return data to pass to Supabase store
return [{ json: { userEmail, tasks, count } }];"""
        }
    }

    # Build Store Tasks HTTP Request node
    store_tasks_node = {
        "id": uid(),
        "name": "Store Tasks",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [wx + 450, wy],
        "parameters": {
            "method": "POST",
            "url": f"{SUPABASE_URL}/rest/v1/pending_actions",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "supabaseApi",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Prefer", "value": "return=representation"},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": '={{ JSON.stringify({ user_id: null, action_type: "digest_tasks", opportunity_id: $json.userEmail, draft_content: JSON.stringify($json.tasks), context: JSON.stringify({ count: $json.count }), status: "pending" }) }}'
        },
        "credentials": SUPABASE_CRED
    }

    # Keep only webhook, add new nodes
    new_nodes = [webhook_node, parse_tasks_node, store_tasks_node]
    wf["nodes"] = new_nodes

    # Rewire: Webhook → Parse Tasks → Store Tasks
    wf["connections"] = {}
    add_conn(wf["connections"], webhook_name, "Parse Tasks")
    add_conn(wf["connections"], "Parse Tasks", "Store Tasks")

    # Push
    print("Pushing updated Digest Tasks Receiver...")
    result = push_workflow(WF_RECEIVER, wf)
    if "id" in result:
        print(f"  SUCCESS: Workflow updated (ID: {result['id']})")
    else:
        print(f"  ERROR: {json.dumps(result)[:500]}")
        sys.exit(1)

    # Re-activate (push may deactivate)
    print("Re-activating Digest Tasks Receiver...")
    result = curl("POST", f"/api/v1/workflows/{WF_RECEIVER}/activate")
    print(f"  active={result.get('active', 'unknown')}")

    # Verify
    print("\n  --- Verification ---")
    wf2 = curl("GET", f"/api/v1/workflows/{WF_RECEIVER}")
    v_names = [n["name"] for n in wf2["nodes"]]
    print(f"  Nodes: {v_names}")
    for expected in ["Parse Tasks", "Store Tasks"]:
        status = "OK" if expected in v_names else "FAIL"
        print(f"  [{status}] {expected}")
    print(f"  Active: {wf2.get('active', False)}")


def update_digest_workflow(wf_id, wf_label):
    """Add Wait, Read, updated Filter, and Cleanup nodes to a digest workflow."""
    print(f"\n{'=' * 60}")
    print(f"Updating {wf_label} ({wf_id})")
    print("=" * 60)

    # Fetch live
    print(f"Fetching {wf_label}...")
    wf = curl("GET", f"/api/v1/workflows/{wf_id}")
    if "nodes" not in wf:
        print(f"ERROR: Could not fetch workflow: {json.dumps(wf)[:500]}")
        sys.exit(1)

    nodes = wf["nodes"]
    connections = wf["connections"]
    node_names = [n["name"] for n in nodes]
    print(f"  Nodes: {node_names}")

    # Check if already applied
    if "Wait for Tasks" in node_names:
        print("  SKIP: Wait for Tasks already exists.")
        return
    if "Read Tasks from Supabase" in node_names:
        print("  SKIP: Read Tasks from Supabase already exists.")
        return

    # Find key nodes
    fetch_tasks = None
    filter_tasks = None
    resolve_identity = None
    filter_opps = None

    for n in nodes:
        if n["name"] == "Fetch User Tasks":
            fetch_tasks = n
        elif n["name"] == "Filter Urgent Tasks":
            filter_tasks = n
        elif n["name"] == "Resolve Identity":
            resolve_identity = n
        elif n["name"] == "Filter User Opps":
            filter_opps = n

    if not fetch_tasks:
        print("  ERROR: Fetch User Tasks not found")
        sys.exit(1)
    if not filter_tasks:
        print("  ERROR: Filter Urgent Tasks not found")
        sys.exit(1)
    if not resolve_identity:
        print("  ERROR: Resolve Identity not found")
        sys.exit(1)

    print(f"  Fetch User Tasks at {fetch_tasks['position']}")
    print(f"  Filter Urgent Tasks at {filter_tasks['position']}")
    print(f"  Resolve Identity at {resolve_identity['position']}")

    # Calculate positions for new nodes
    ft_x, ft_y = fetch_tasks["position"]
    fut_x, fut_y = filter_tasks["position"]
    ri_x, ri_y = resolve_identity["position"]

    # We need to insert: Wait for Tasks, Read Tasks from Supabase between Fetch and Filter
    # And Cleanup Tasks Row between Filter and Resolve Identity
    # Shift existing nodes right to make room

    # Spacing: ~200px between nodes
    wait_pos = [ft_x + 200, ft_y]
    read_pos = [ft_x + 400, ft_y]
    # Move Filter Urgent Tasks right
    new_filter_pos = [ft_x + 600, ft_y]
    cleanup_pos = [ft_x + 800, ft_y]
    # Move Resolve Identity right
    new_resolve_pos = [ft_x + 1000, ri_y]

    filter_tasks["position"] = new_filter_pos
    resolve_identity["position"] = new_resolve_pos

    # Also shift any nodes that were downstream of Resolve Identity
    # (to avoid overlap) — shift anything at or past old resolve x
    old_ri_x = ri_x
    shift_amount = new_resolve_pos[0] - old_ri_x
    if shift_amount > 0:
        for n in nodes:
            if n["name"] in ("Filter Urgent Tasks", "Resolve Identity"):
                continue  # already handled
            if n["position"][0] >= old_ri_x and n["name"] != "Fetch User Tasks":
                n["position"][0] += shift_amount

    # Create Wait for Tasks node
    wait_node = {
        "id": uid(),
        "name": "Wait for Tasks",
        "type": "n8n-nodes-base.wait",
        "typeVersion": 1.1,
        "position": wait_pos,
        "parameters": {
            "resume": "timeInterval",
            "interval": 8,
            "unit": "seconds"
        },
        "webhookId": uid()
    }

    # Create Read Tasks from Supabase node
    read_node = {
        "id": uid(),
        "name": "Read Tasks from Supabase",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": read_pos,
        "alwaysOutputData": True,
        "parameters": {
            "url": f"={SUPABASE_URL}/rest/v1/pending_actions?action_type=eq.digest_tasks&opportunity_id=eq.{{{{ $('Filter User Opps').first().json.email }}}}&select=draft_content&order=created_at.desc&limit=1",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "supabaseApi",
            "options": {}
        },
        "credentials": SUPABASE_CRED
    }

    # Create Cleanup Tasks Row node
    cleanup_node = {
        "id": uid(),
        "name": "Cleanup Tasks Row",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": cleanup_pos,
        "parameters": {
            "method": "DELETE",
            "url": f"={SUPABASE_URL}/rest/v1/pending_actions?action_type=eq.digest_tasks&opportunity_id=eq.{{{{ $('Filter User Opps').first().json.email }}}}",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "supabaseApi",
            "options": {}
        },
        "credentials": SUPABASE_CRED
    }

    # Add new nodes
    nodes.append(wait_node)
    nodes.append(read_node)
    nodes.append(cleanup_node)

    # Update Filter Urgent Tasks code to read from Supabase result
    filter_tasks["parameters"]["jsCode"] = FILTER_URGENT_TASKS_CODE

    # Rewire connections:
    # Old: Fetch User Tasks → Filter Urgent Tasks → Resolve Identity
    # New: Fetch User Tasks → Wait for Tasks → Read Tasks from Supabase → Filter Urgent Tasks → Cleanup Tasks Row → Resolve Identity

    # Remove Fetch User Tasks → Filter Urgent Tasks
    remove_conn(connections, "Fetch User Tasks", "Filter Urgent Tasks")
    # Remove Filter Urgent Tasks → Resolve Identity
    remove_conn(connections, "Filter Urgent Tasks", "Resolve Identity")

    # Add new chain
    add_conn(connections, "Fetch User Tasks", "Wait for Tasks")
    connections["Wait for Tasks"] = {"main": [[{"node": "Read Tasks from Supabase", "type": "main", "index": 0}]]}
    connections["Read Tasks from Supabase"] = {"main": [[{"node": "Filter Urgent Tasks", "type": "main", "index": 0}]]}
    # Filter Urgent Tasks → Cleanup Tasks Row → Resolve Identity
    connections["Filter Urgent Tasks"] = {"main": [[{"node": "Cleanup Tasks Row", "type": "main", "index": 0}]]}
    connections["Cleanup Tasks Row"] = {"main": [[{"node": "Resolve Identity", "type": "main", "index": 0}]]}

    print("  Rewired connections:")
    print("    Fetch User Tasks → Wait for Tasks → Read Tasks from Supabase → Filter Urgent Tasks → Cleanup Tasks Row → Resolve Identity")

    # Push
    print(f"  Pushing updated {wf_label}...")
    result = push_workflow(wf_id, wf)
    if "id" in result:
        print(f"  SUCCESS: Workflow updated (ID: {result['id']})")
    else:
        print(f"  ERROR: {json.dumps(result)[:800]}")
        # If the Wait node params were rejected, try alternate param format
        if "error" in str(result).lower() or "message" in result:
            print("\n  Retrying with alternate Wait node params (amount/unit)...")
            wait_node["parameters"] = {
                "amount": 8,
                "unit": "seconds"
            }
            result = push_workflow(wf_id, wf)
            if "id" in result:
                print(f"  SUCCESS on retry: Workflow updated (ID: {result['id']})")
            else:
                print(f"  ERROR on retry: {json.dumps(result)[:800]}")
                # Try typeVersion 1
                print("\n  Retrying with typeVersion 1 (value/unit)...")
                wait_node["typeVersion"] = 1
                wait_node["parameters"] = {
                    "value": 8,
                    "unit": "seconds"
                }
                result = push_workflow(wf_id, wf)
                if "id" in result:
                    print(f"  SUCCESS on retry 2: Workflow updated (ID: {result['id']})")
                else:
                    print(f"  FINAL ERROR: {json.dumps(result)[:800]}")
                    sys.exit(1)

    # Verify
    print(f"\n  --- Verification for {wf_label} ---")
    wf2 = curl("GET", f"/api/v1/workflows/{wf_id}")
    v_names = [n["name"] for n in wf2["nodes"]]
    v_conns = wf2["connections"]

    for expected in ["Wait for Tasks", "Read Tasks from Supabase", "Cleanup Tasks Row"]:
        status = "OK" if expected in v_names else "FAIL"
        print(f"  [{status}] Node '{expected}' exists")

    chain = [
        ("Fetch User Tasks", "Wait for Tasks"),
        ("Wait for Tasks", "Read Tasks from Supabase"),
        ("Read Tasks from Supabase", "Filter Urgent Tasks"),
        ("Filter Urgent Tasks", "Cleanup Tasks Row"),
        ("Cleanup Tasks Row", "Resolve Identity"),
    ]
    for src, dst in chain:
        status = "OK" if check_conn(v_conns, src, dst) else "FAIL"
        print(f"  [{status}] {src} -> {dst}")

    # Verify old direct connections are gone
    if check_conn(v_conns, "Fetch User Tasks", "Filter Urgent Tasks"):
        print("  [FAIL] Direct Fetch User Tasks -> Filter Urgent Tasks still exists")
    else:
        print("  [OK] No direct Fetch User Tasks -> Filter Urgent Tasks")

    if check_conn(v_conns, "Filter Urgent Tasks", "Resolve Identity"):
        print("  [FAIL] Direct Filter Urgent Tasks -> Resolve Identity still exists")
    else:
        print("  [OK] No direct Filter Urgent Tasks -> Resolve Identity")

    # Check Filter Urgent Tasks code
    for n in wf2["nodes"]:
        if n["name"] == "Filter Urgent Tasks":
            code = n["parameters"].get("jsCode", "")
            if "supabaseResult" in code:
                print("  [OK] Filter Urgent Tasks reads from Supabase")
            else:
                print("  [FAIL] Filter Urgent Tasks code not updated")
            break


def main():
    if not API_KEY:
        print("ERROR: N8N_API_KEY not set")
        sys.exit(1)

    # Step 1: Update Digest Tasks Receiver
    update_receiver()

    # Step 2: Update Sales Digest
    update_digest_workflow(WF_SALES_DIGEST, "Sales Digest")

    # Step 3: Update On-Demand Digest
    update_digest_workflow(WF_ON_DEMAND_DIGEST, "On-Demand Digest")

    print("\n" + "=" * 60)
    print("ALL DONE")
    print("=" * 60)


if __name__ == "__main__":
    main()
