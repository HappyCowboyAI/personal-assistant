#!/usr/bin/env python3
"""
Fix: Slack profile field mapping for department/division
- Slack admin "Department" and "Division" are custom profile fields
- They live in profile.fields.{ID}.value, NOT profile.department or profile.title
- This script:
  1. Updates Weekly Profile Sync to call team.profile.get for field discovery
  2. Updates Slack Events Handler Create User Record with a Code node for extraction
  3. Pushes both workflows
"""

import json
import os
import uuid
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

WEEKLY_SYNC_ID = "EDLS1vIbb4gNebIv"
SLACK_EVENTS_ID = "QuQbIaWetunUOFUW"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

SLACK_CRED = {"id": "LluVuiMJ8NUbAiG7", "name": "Slackbot Auth Token"}


def fetch_workflow(workflow_id):
    resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{workflow_id}", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def push_workflow(workflow_id, workflow):
    payload = {
        "name": workflow["name"],
        "nodes": workflow["nodes"],
        "connections": workflow["connections"],
        "settings": workflow.get("settings", {}),
        "staticData": workflow.get("staticData"),
    }
    resp = requests.put(f"{N8N_BASE_URL}/api/v1/workflows/{workflow_id}", headers=HEADERS, json=payload)
    resp.raise_for_status()
    return resp.json()


def sync_local(workflow, filename):
    path = os.path.join(REPO_ROOT, "n8n", "workflows", filename)
    with open(path, "w") as f:
        json.dump(workflow, f, indent=4)
    print(f"  Synced {path}")


# ---------------------------------------------------------------------------
# WEEKLY PROFILE SYNC — Add team.profile.get and fix field extraction
# ---------------------------------------------------------------------------

EXTRACT_AND_COMPARE_CODE_V2 = r"""// Extract Slack profile fields using custom field metadata
const slackProfile = $('Get Slack Profile').first().json;
const fieldMeta = $('Get Profile Fields').first().json;
const user = $('Split In Batches').first().json;

const profile = (slackProfile.user && slackProfile.user.profile) || {};
const fields = profile.fields || {};

// Build label→value map from custom profile fields
const profileFields = fieldMeta.profile && fieldMeta.profile.fields || [];
const labelToId = {};
for (const f of profileFields) {
  if (f.label) {
    labelToId[f.label.toLowerCase()] = f.id;
  }
}

// Extract by label
function getCustomField(label) {
  const fieldId = labelToId[label.toLowerCase()];
  if (fieldId && fields[fieldId]) {
    return fields[fieldId].value || '';
  }
  return '';
}

// Try custom fields first, fall back to standard fields
const newDepartment = getCustomField('Department') || profile.department || '';
const newDivision = getCustomField('Division') || profile.title || '';

// Derive digest_scope from division
function deriveDigestScope(div) {
  if (!div) return 'my_deals';
  const lower = div.toLowerCase();
  if (/^(vp|svp|evp|cro|chief|head of)/.test(lower)) return 'top_pipeline';
  if (/(manager|director)/.test(lower)) return 'team_deals';
  return 'my_deals';
}

const newDigestScope = deriveDigestScope(newDivision);

// Check if anything changed
const changed = (
  (user.department || '') !== newDepartment ||
  (user.division || '') !== newDivision ||
  (user.digest_scope || 'my_deals') !== newDigestScope
);

return [{
  json: {
    userId: user.id,
    slackUserId: user.slack_user_id,
    email: user.email,
    oldDepartment: user.department || '',
    oldDivision: user.division || '',
    oldDigestScope: user.digest_scope || 'my_deals',
    newDepartment,
    newDivision,
    newDigestScope,
    changed
  }
}];
"""


def upgrade_weekly_sync(wf):
    print("\n=== Upgrading Weekly Profile Sync ===")
    nodes = wf["nodes"]
    connections = wf["connections"]

    # Check if already has Get Profile Fields
    node_names = [n["name"] for n in nodes]
    if "Get Profile Fields" in node_names:
        print("  Already has Get Profile Fields — updating Extract and Compare only")
        for node in nodes:
            if node["name"] == "Extract and Compare":
                node["parameters"]["jsCode"] = EXTRACT_AND_COMPARE_CODE_V2
                print("  Updated Extract and Compare jsCode")
        return wf

    # Add "Get Profile Fields" node — calls team.profile.get (runs once before the loop)
    get_fields_id = str(uuid.uuid4())
    get_fields_node = {
        "parameters": {
            "method": "GET",
            "url": "https://slack.com/api/team.profile.get",
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "options": {}
        },
        "id": get_fields_id,
        "name": "Get Profile Fields",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [310, 400],
        "credentials": {"httpHeaderAuth": SLACK_CRED}
    }
    nodes.append(get_fields_node)
    print(f"  Added Get Profile Fields (id={get_fields_id})")

    # Shift existing nodes right
    for node in nodes:
        if node["name"] == "Get Profile Fields":
            continue
        x, y = node["position"]
        if x >= 420:  # Everything from "Get All Users" onward
            node["position"] = [x + 220, y]

    # Update Extract and Compare code
    for node in nodes:
        if node["name"] == "Extract and Compare":
            node["parameters"]["jsCode"] = EXTRACT_AND_COMPARE_CODE_V2
            print("  Updated Extract and Compare jsCode")
            break

    # Fix connections: insert Get Profile Fields between trigger and Get All Users
    connections["Weekly Sunday 10pm PT"] = {
        "main": [[{"node": "Get Profile Fields", "type": "main", "index": 0}]]
    }
    connections["Get Profile Fields"] = {
        "main": [[{"node": "Get All Users", "type": "main", "index": 0}]]
    }
    print("  Updated connections: Trigger → Get Profile Fields → Get All Users")

    print(f"  Total nodes: {len(nodes)}")
    return wf


# ---------------------------------------------------------------------------
# SLACK EVENTS HANDLER — Fix Create User Record field expressions
# ---------------------------------------------------------------------------

EXTRACT_PROFILE_CODE = r"""// Extract department and division from Slack custom profile fields
// Called after Get Slack User Info, passes data to Create User Record
const slackResponse = $('Get Slack User Info').first().json;
const fieldMeta = $('Get Onboarding Profile Fields').first().json;

const user = slackResponse.user || {};
const profile = user.profile || {};
const fields = profile.fields || {};

// Build label→ID map from workspace field metadata
const profileFields = (fieldMeta.profile && fieldMeta.profile.fields) || [];
const labelToId = {};
for (const f of profileFields) {
  if (f.label) {
    labelToId[f.label.toLowerCase()] = f.id;
  }
}

function getCustomField(label) {
  const fieldId = labelToId[label.toLowerCase()];
  if (fieldId && fields[fieldId]) {
    return fields[fieldId].value || '';
  }
  return '';
}

// Try custom fields first, fall back to standard fields
const department = getCustomField('Department') || profile.department || '';
const division = getCustomField('Division') || profile.title || '';

// Derive digest_scope
function deriveDigestScope(div) {
  if (!div) return 'my_deals';
  const lower = div.toLowerCase();
  if (/^(vp|svp|evp|cro|chief|head of)/.test(lower)) return 'top_pipeline';
  if (/(manager|director)/.test(lower)) return 'team_deals';
  return 'my_deals';
}

const digestScope = deriveDigestScope(division);

return [{
  json: {
    ...slackResponse,
    extractedDepartment: department,
    extractedDivision: division,
    derivedDigestScope: digestScope
  }
}];
"""


def upgrade_slack_events(wf):
    print("\n=== Upgrading Slack Events Handler ===")
    nodes = wf["nodes"]
    connections = wf["connections"]

    node_names = [n["name"] for n in nodes]

    # Check if already has the profile fields node
    if "Get Onboarding Profile Fields" in node_names:
        print("  Already has Get Onboarding Profile Fields — skipping")
        return wf

    # --- Add "Get Onboarding Profile Fields" node ---
    # This calls team.profile.get. Position it near the new user branch.
    # Current flow: Switch Route [output 0] → Get Slack User Info → Lookup Default Org → Create User Record → Send Greeting
    # New flow: Switch Route [output 0] → Get Slack User Info → Get Onboarding Profile Fields → Extract Slack Profile → Lookup Default Org → Create User Record → Send Greeting

    # Find Get Slack User Info position for reference
    slack_info_pos = [2180, 240]
    for node in nodes:
        if node["name"] == "Get Slack User Info":
            slack_info_pos = node["position"]
            break

    # Add Get Onboarding Profile Fields (after Get Slack User Info)
    get_fields_id = str(uuid.uuid4())
    get_fields_node = {
        "parameters": {
            "method": "GET",
            "url": "https://slack.com/api/team.profile.get",
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "options": {}
        },
        "id": get_fields_id,
        "name": "Get Onboarding Profile Fields",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [slack_info_pos[0] + 220, slack_info_pos[1]],
        "credentials": {"httpHeaderAuth": SLACK_CRED}
    }
    nodes.append(get_fields_node)
    print(f"  Added Get Onboarding Profile Fields (id={get_fields_id})")

    # Add Extract Slack Profile code node
    extract_id = str(uuid.uuid4())
    extract_node = {
        "parameters": {
            "jsCode": EXTRACT_PROFILE_CODE
        },
        "id": extract_id,
        "name": "Extract Slack Profile",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [slack_info_pos[0] + 440, slack_info_pos[1]]
    }
    nodes.append(extract_node)
    print(f"  Added Extract Slack Profile (id={extract_id})")

    # Shift Lookup Default Org, Create User Record, Send Greeting right
    shift_nodes = ["Lookup Default Org", "Create User Record", "Send Greeting"]
    for node in nodes:
        if node["name"] in shift_nodes:
            node["position"] = [node["position"][0] + 440, node["position"][1]]
            print(f"  Shifted {node['name']} to {node['position']}")

    # Update Create User Record to use Extract Slack Profile outputs
    for node in nodes:
        if node["name"] == "Create User Record":
            values = node["parameters"]["fieldsToSend"]["values"]
            for v in values:
                if v["fieldId"] == "department":
                    v["fieldValue"] = "={{ $('Extract Slack Profile').first().json.extractedDepartment }}"
                elif v["fieldId"] == "division":
                    v["fieldValue"] = "={{ $('Extract Slack Profile').first().json.extractedDivision }}"
                elif v["fieldId"] == "digest_scope":
                    v["fieldValue"] = "={{ $('Extract Slack Profile').first().json.derivedDigestScope }}"
            print("  Updated Create User Record field expressions")
            break

    # Update connections
    # Old: Get Slack User Info → Lookup Default Org
    # New: Get Slack User Info → Get Onboarding Profile Fields → Extract Slack Profile → Lookup Default Org
    connections["Get Slack User Info"] = {
        "main": [[{"node": "Get Onboarding Profile Fields", "type": "main", "index": 0}]]
    }
    connections["Get Onboarding Profile Fields"] = {
        "main": [[{"node": "Extract Slack Profile", "type": "main", "index": 0}]]
    }
    connections["Extract Slack Profile"] = {
        "main": [[{"node": "Lookup Default Org", "type": "main", "index": 0}]]
    }
    print("  Updated connections: Get Slack User Info → Get Onboarding Profile Fields → Extract Slack Profile → Lookup Default Org")

    print(f"  Total nodes: {len(nodes)}")
    return wf


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    print("Fetching live workflows...")
    sync_wf = fetch_workflow(WEEKLY_SYNC_ID)
    events_wf = fetch_workflow(SLACK_EVENTS_ID)
    print(f"  Weekly Profile Sync: {len(sync_wf['nodes'])} nodes")
    print(f"  Slack Events Handler: {len(events_wf['nodes'])} nodes")

    sync_wf = upgrade_weekly_sync(sync_wf)
    events_wf = upgrade_slack_events(events_wf)

    print("\n=== Pushing workflows ===")
    result1 = push_workflow(WEEKLY_SYNC_ID, sync_wf)
    print(f"  Weekly Profile Sync: HTTP 200, {len(result1['nodes'])} nodes")

    result2 = push_workflow(SLACK_EVENTS_ID, events_wf)
    print(f"  Slack Events Handler: HTTP 200, {len(result2['nodes'])} nodes")

    print("\n=== Syncing local files ===")
    sync_local(result1, "Weekly Profile Sync.json")
    sync_local(result2, "Slack Events Handler.json")

    print("\nDone! Both workflows fixed for custom Slack profile fields.")
    print("\nNext step: Test the Weekly Profile Sync workflow manually in n8n.")
    print("The 'Get Profile Fields' node output will show all custom field IDs and labels.")


if __name__ == "__main__":
    main()
