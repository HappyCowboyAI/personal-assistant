#!/usr/bin/env python3
"""
Add meeting briefs opt-out:
1. Meeting Brief sub-workflow: append footer to Parse Blocks output
2. Slack Events Handler: add stop/start briefs commands (Route by State + Build Help Response)
   - Reuse Toggle Digest Supabase node pattern for meeting_prep_enabled
"""

import json
import os
import requests

N8N_BASE_URL = "https://scottai.trackslife.com"
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

MEETING_BRIEF_ID = "Cj4HcHfbzy9OZhwE"
SLACK_EVENTS_ID = "QuQbIaWetunUOFUW"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}


def fetch_workflow(wid):
    resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{wid}", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def push_workflow(wid, wf):
    payload = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": wf.get("settings", {}),
        "staticData": wf.get("staticData"),
    }
    resp = requests.put(f"{N8N_BASE_URL}/api/v1/workflows/{wid}", headers=HEADERS, json=payload)
    resp.raise_for_status()
    return resp.json()


def sync_local(wid, filename):
    resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{wid}", headers=HEADERS)
    resp.raise_for_status()
    path = os.path.join(REPO_ROOT, "n8n", "workflows", filename)
    with open(path, "w") as f:
        json.dump(resp.json(), f, indent=2)
    print(f"   Synced {filename}")


def find_node(nodes, name):
    for n in nodes:
        if n["name"] == name:
            return n
    raise ValueError(f"Node '{name}' not found")


def main():
    # ═══════════════════════════════════════════════════════
    # Part 1: Add footer to Meeting Brief sub-workflow
    # ═══════════════════════════════════════════════════════
    print("=== Part 1: Meeting Brief footer ===")
    wf = fetch_workflow(MEETING_BRIEF_ID)

    parse_node = find_node(wf["nodes"], "Parse Blocks")
    old_code = parse_node["parameters"]["jsCode"]

    # Add footer block before the return statement
    # Find the return statement and inject footer append before it
    footer_injection = """
  // Append opt-out footer
  if (parsed.blocks) {
    parsed.blocks.push(
      { type: "divider" },
      {
        type: "context",
        elements: [{
          type: "mrkdwn",
          text: "_Type `stop briefs` to pause meeting briefs · `start briefs` to resume_"
        }]
      }
    );
  }
"""

    # Insert before "// Enforce Slack limits"
    marker = "// Enforce Slack limits"
    if marker in old_code:
        new_code = old_code.replace(marker, footer_injection + "\n  " + marker)
        parse_node["parameters"]["jsCode"] = new_code
        print("   Added footer block before Slack limits enforcement")
    else:
        print("   WARNING: Could not find insertion point")
        return

    result = push_workflow(MEETING_BRIEF_ID, wf)
    print(f"   Pushed Meeting Brief (updatedAt: {result.get('updatedAt', '?')})")
    sync_local(MEETING_BRIEF_ID, "Meeting Brief.json")

    # ═══════════════════════════════════════════════════════
    # Part 2: Add stop/start briefs commands to Slack Events Handler
    # ═══════════════════════════════════════════════════════
    print("\n=== Part 2: Slack Events Handler commands ===")
    wf = fetch_workflow(SLACK_EVENTS_ID)

    # 2a. Route by State: add stop/start briefs routing
    route_node = find_node(wf["nodes"], "Route by State")
    route_code = route_node["parameters"]["jsCode"]

    # Add briefs commands alongside digest commands in Pass 3
    old_pass3 = """if (lower === 'stop digest' || lower === 'pause digest') subRoute = 'stop_digest';
      else if (lower === 'resume digest' || lower === 'start digest') subRoute = 'resume_digest';"""

    new_pass3 = """if (lower === 'stop digest' || lower === 'pause digest') subRoute = 'stop_digest';
      else if (lower === 'resume digest' || lower === 'start digest') subRoute = 'resume_digest';
      else if (lower === 'stop briefs' || lower === 'pause briefs' || lower === 'stop meeting briefs') subRoute = 'stop_briefs';
      else if (lower === 'start briefs' || lower === 'resume briefs' || lower === 'start meeting briefs') subRoute = 'resume_briefs';"""

    if old_pass3 in route_code:
        route_code = route_code.replace(old_pass3, new_pass3)
        route_node["parameters"]["jsCode"] = route_code
        print("   Added stop/start briefs routes")
    else:
        print("   WARNING: Could not find routing insertion point")
        return

    # 2b. Build Help Response: add response text + update logic for briefs
    help_node = find_node(wf["nodes"], "Build Help Response")
    help_code = help_node["parameters"]["jsCode"]

    # Add response text for stop/start briefs
    old_resume_announcements = """} else if (r === 'resume_announcements') {
  text = "Announcements resumed! I\\u2019ll let you know when I learn new tricks.";
} else {"""

    new_resume_announcements = """} else if (r === 'resume_announcements') {
  text = "Announcements resumed! I\\u2019ll let you know when I learn new tricks.";
} else if (r === 'stop_briefs') {
  text = "Meeting briefs paused \\u2014 I won\\u2019t send pre-meeting prep anymore. Type `start briefs` anytime to resume.";
} else if (r === 'resume_briefs') {
  text = "Meeting briefs are back on! I\\u2019ll prep you before upcoming customer meetings.";
} else {"""

    if old_resume_announcements in help_code:
        help_code = help_code.replace(old_resume_announcements, new_resume_announcements)
        print("   Added stop/start briefs response text")
    else:
        print("   WARNING: Could not find help text insertion point")
        return

    # Add meeting_prep_enabled update logic alongside education prefs
    old_education_check = "const needsEducationUpdate = ['stop_tips', 'resume_tips', 'stop_announcements', 'resume_announcements'].includes(r);"
    new_education_check = """const needsBriefsUpdate = (r === 'stop_briefs' || r === 'resume_briefs');
const meetingPrepEnabled = (r === 'resume_briefs');
const needsEducationUpdate = ['stop_tips', 'resume_tips', 'stop_announcements', 'resume_announcements'].includes(r);"""

    if old_education_check in help_code:
        help_code = help_code.replace(old_education_check, new_education_check)
        print("   Added needsBriefsUpdate logic")
    else:
        print("   WARNING: Could not find education check insertion point")
        return

    # Update the return to include briefs fields
    old_return = "return [{ json: { ...data, responseText: text, needsUpdate, digestEnabled, needsEducationUpdate, educationField, educationValue } }];"
    new_return = "return [{ json: { ...data, responseText: text, needsUpdate, digestEnabled, needsBriefsUpdate, meetingPrepEnabled, needsEducationUpdate, educationField, educationValue } }];"

    if old_return in help_code:
        help_code = help_code.replace(old_return, new_return)
        print("   Updated return to include briefs fields")
    else:
        print("   WARNING: Could not find return statement")
        return

    help_node["parameters"]["jsCode"] = help_code

    # 2c. Find the connection path from Build Help Response to understand
    # how Toggle Digest works, then add a Toggle Briefs node alongside it
    conns = wf["connections"]

    # The existing pattern: Build Help Response → Is Conversational? →
    # (false) → Needs Digest Update? → Toggle Digest → Send Response
    # We need a similar path for briefs. But since it uses the same Supabase update
    # pattern, we can add a Toggle Briefs node that fires when needsBriefsUpdate=true.

    # Find the node that checks needsUpdate for digest toggle
    # Look for a node that checks needsUpdate
    needs_update_node = None
    toggle_digest_node = None
    for n in wf["nodes"]:
        name = n["name"]
        params = json.dumps(n.get("parameters", {}))
        if "needsUpdate" in params and "If" in n["type"]:
            needs_update_node = n
        if name == "Toggle Digest":
            toggle_digest_node = n

    if needs_update_node:
        print(f"   Found digest update check: {needs_update_node['name']}")
    if toggle_digest_node:
        print(f"   Found Toggle Digest node")

    # Add a "Toggle Briefs" HTTP Request node (using PATCH pattern like Toggle Education Pref)
    # Position it near Toggle Digest
    toggle_digest_pos = toggle_digest_node["position"] if toggle_digest_node else [1000, 800]
    import uuid

    toggle_briefs_node = {
        "parameters": {
            "method": "PATCH",
            "url": "=https://rhrlnkbphxntxxxcrgvv.supabase.co/rest/v1/users?id=eq.{{ $json.dbUserId }}",
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
            "jsonBody": "={{ JSON.stringify({ meeting_prep_enabled: $json.meetingPrepEnabled }) }}",
            "options": {},
        },
        "id": str(uuid.uuid4()),
        "name": "Toggle Briefs",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [toggle_digest_pos[0], toggle_digest_pos[1] + 200],
        "credentials": {
            "supabaseApi": {
                "id": "ASRWWkQ0RSMOpNF1",
                "name": "Supabase account",
            }
        },
    }
    wf["nodes"].append(toggle_briefs_node)
    print("   Added Toggle Briefs node")

    # Add a "Needs Briefs Update?" If node
    needs_briefs_node = {
        "parameters": {
            "conditions": {
                "options": {
                    "version": 2,
                    "leftValue": "",
                    "caseSensitive": True,
                    "typeValidation": "loose",
                },
                "conditions": [
                    {
                        "id": str(uuid.uuid4()),
                        "leftValue": "={{ $json.needsBriefsUpdate }}",
                        "rightValue": True,
                        "operator": {
                            "type": "boolean",
                            "operation": "true",
                        },
                    }
                ],
                "combinator": "and",
            },
            "options": {},
        },
        "id": str(uuid.uuid4()),
        "name": "Needs Briefs Update?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [toggle_digest_pos[0] - 200, toggle_digest_pos[1] + 200],
    }
    wf["nodes"].append(needs_briefs_node)
    print("   Added Needs Briefs Update? node")

    # Now wire it up. We need to find where the response sending happens
    # after Toggle Digest. The pattern is:
    # Needs Digest Update? → [true] Toggle Digest → Send Response
    # Needs Digest Update? → [false] → (continues to response)
    #
    # We'll tap into the same flow: after the digest check, also check briefs.
    # Find what connects after Toggle Digest or the false branch of Needs Digest Update

    # Actually, let's find the exact connection chain
    if needs_update_node:
        nu_name = needs_update_node["name"]
        nu_conns = conns.get(nu_name, {}).get("main", [])
        print(f"   {nu_name} connections:")
        for i, targets in enumerate(nu_conns):
            for t in targets:
                print(f"     Output {i} → {t['node']}")

    # Find what Toggle Digest connects to
    td_conns = conns.get("Toggle Digest", {}).get("main", [])
    if td_conns:
        print(f"   Toggle Digest connections:")
        for i, targets in enumerate(td_conns):
            for t in targets:
                print(f"     Output {i} → {t['node']}")

    # Wire:
    # After the digest update check's false branch (or after Toggle Digest),
    # chain → Needs Briefs Update? → [true] Toggle Briefs → (continue)
    #                                → [false] (continue)
    #
    # The simplest approach: Insert Needs Briefs Update? between the false branch
    # of Needs Digest Update? and wherever it goes.

    if needs_update_node:
        nu_name = needs_update_node["name"]
        nu_conns = conns.get(nu_name, {}).get("main", [])

        # False branch (output 1) of Needs Digest Update?
        if len(nu_conns) > 1 and nu_conns[1]:
            false_target = nu_conns[1][0]["node"]  # Where false goes
            print(f"   Inserting Needs Briefs Update? between {nu_name}[false] and {false_target}")

            # Needs Digest Update? false → Needs Briefs Update?
            nu_conns[1] = [{"node": "Needs Briefs Update?", "type": "main", "index": 0}]

            # Also: Toggle Digest → Needs Briefs Update?
            conns["Toggle Digest"] = {
                "main": [[{"node": "Needs Briefs Update?", "type": "main", "index": 0}]]
            }

            # Needs Briefs Update? true → Toggle Briefs
            # Needs Briefs Update? false → original target
            conns["Needs Briefs Update?"] = {
                "main": [
                    [{"node": "Toggle Briefs", "type": "main", "index": 0}],  # true
                    [{"node": false_target, "type": "main", "index": 0}],  # false
                ]
            }

            # Toggle Briefs → original target
            conns["Toggle Briefs"] = {
                "main": [[{"node": false_target, "type": "main", "index": 0}]]
            }

            print(f"   Wired: {nu_name}[false] → Needs Briefs Update? → Toggle Briefs → {false_target}")
            print(f"   Wired: Toggle Digest → Needs Briefs Update?")
        else:
            print("   WARNING: Needs Digest Update? has no false branch")

    result = push_workflow(SLACK_EVENTS_ID, wf)
    print(f"   Pushed Slack Events Handler (updatedAt: {result.get('updatedAt', '?')})")
    sync_local(SLACK_EVENTS_ID, "Slack Events Handler.json")

    print("\nDone! Changes:")
    print("  1. Meeting Brief messages now include footer: 'Type stop briefs to pause...'")
    print("  2. 'stop briefs' / 'start briefs' commands added to Slack Events Handler")
    print("  3. Toggle Briefs updates meeting_prep_enabled in Supabase")


if __name__ == "__main__":
    main()
