#!/usr/bin/env python3
"""
Fix the 'Create User Record' node in Slack Events Handler.

Problem: The node has no tableId and no field mappings, so it silently fails
(continueOnFail=true). New users never get a DB record created, trapping them
in an infinite greeting loop — they can never name their assistant.

Fix: Add proper tableId ('users') and fieldsUi with expressions that pull
data from earlier nodes in the new-user flow, plus set onboarding_state
to 'awaiting_name' immediately so users can name on their second message.
"""

import json
import os
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

SLACK_EVENTS_ID = "QuQbIaWetunUOFUW"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}


def fetch_workflow(wf_id):
    resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def push_workflow(wf_id, wf):
    payload = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
               "settings": wf.get("settings", {}), "staticData": wf.get("staticData")}
    resp = requests.put(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}", headers=HEADERS, json=payload)
    resp.raise_for_status()
    return resp.json()


def sync_local(wf, filename):
    path = os.path.join(REPO_ROOT, "n8n", "workflows", filename)
    with open(path, "w") as f:
        json.dump(wf, f, indent=4)
    print(f"  Synced {path}")


def main():
    print("=== Fix Create User Record ===\n")

    # 1. Fetch current Events Handler
    print("1. Fetching Slack Events Handler...")
    wf = fetch_workflow(SLACK_EVENTS_ID)
    nodes = wf["nodes"]

    # 2. Find the Create User Record node
    target = None
    for node in nodes:
        if node["name"] == "Create User Record":
            target = node
            break

    if not target:
        print("   ERROR: 'Create User Record' node not found!")
        return

    print(f"   Found node: id={target['id']}")
    print(f"   Current parameters: {json.dumps(target['parameters'], indent=2)}")

    # 3. Fix the node — add tableId and proper field mappings
    target["parameters"] = {
        "operation": "insert",
        "tableId": "users",
        "fieldsUi": {
            "fieldValues": [
                {
                    "fieldId": "slack_user_id",
                    "fieldValue": "={{ $('Route by State').first().json.userId }}"
                },
                {
                    "fieldId": "email",
                    "fieldValue": "={{ $('Get Slack User Info').first().json.user.profile.email }}"
                },
                {
                    "fieldId": "organization_id",
                    "fieldValue": "={{ $('Lookup Default Org').first().json.id }}"
                },
                {
                    "fieldId": "department",
                    "fieldValue": "={{ $('Extract Slack Profile').first().json.extractedDepartment }}"
                },
                {
                    "fieldId": "division",
                    "fieldValue": "={{ $('Extract Slack Profile').first().json.extractedDivision }}"
                },
                {
                    "fieldId": "digest_scope",
                    "fieldValue": "={{ $('Extract Slack Profile').first().json.derivedDigestScope }}"
                },
                {
                    "fieldId": "onboarding_state",
                    "fieldValue": "awaiting_name"
                }
            ]
        }
    }

    print("   Updated parameters with tableId='users' and 7 field mappings")

    # 4. Push updated workflow
    print("\n2. Pushing updated workflow...")
    updated = push_workflow(SLACK_EVENTS_ID, wf)
    print("   Done!")

    # 5. Sync local copy
    print("\n3. Syncing local JSON...")
    sync_local(updated, "Slack Events Handler.json")

    print("\n=== Fix applied! ===")
    print("New users will now get a proper DB record with onboarding_state='awaiting_name'.")
    print("Susan Zuzic should be able to name her assistant on her next message.")
    print("\nNote: If Susan already has a broken record in Supabase, you may need to")
    print("either delete her row or manually set her onboarding_state to 'awaiting_name'.")


if __name__ == "__main__":
    main()
