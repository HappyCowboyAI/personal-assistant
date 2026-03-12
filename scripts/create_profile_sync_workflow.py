#!/usr/bin/env python3
"""
Create: Weekly Slack Profile Sync workflow
- Runs every Sunday at 10pm PT
- Fetches all active users from Supabase
- For each user, calls Slack users.info to get current profile
- Updates department, division, and re-derives digest_scope
- Pushes new workflow to n8n
"""

import json
import os
import uuid
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

# Credential IDs from live n8n
SUPABASE_CRED = {"id": "ASRWWkQ0RSMOpNF1", "name": "Supabase account"}
SLACK_CRED = {"id": "LluVuiMJ8NUbAiG7", "name": "Slackbot Auth Token"}


def uid():
    return str(uuid.uuid4())


FILTER_ACTIVE_CODE = """// Only users who completed onboarding and have a real Slack ID
return $input.all().filter(item =>
  item.json.onboarding_state === 'complete' &&
  item.json.slack_user_id &&
  !item.json.slack_user_id.startsWith('U_YOUR')
);
"""

EXTRACT_AND_COMPARE_CODE = """// Extract Slack profile fields and compare with Supabase record
const slackProfile = $('Get Slack Profile').first().json;
const user = $('Split In Batches').first().json;

const profile = (slackProfile.user && slackProfile.user.profile) || {};

const newDepartment = profile.department || '';
const newDivision = profile.title || '';

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


def build_workflow():
    nodes = [
        # 1. Weekly trigger - Sunday 10pm PT (6am Mon UTC)
        {
            "parameters": {
                "rule": {
                    "interval": [
                        {
                            "field": "cronExpression",
                            "expression": "0 6 * * 1"
                        }
                    ]
                }
            },
            "id": uid(),
            "name": "Weekly Sunday 10pm PT",
            "type": "n8n-nodes-base.scheduleTrigger",
            "typeVersion": 1.2,
            "position": [200, 400]
        },
        # 2. Get all users from Supabase
        {
            "parameters": {
                "operation": "getAll",
                "tableId": "users",
                "returnAll": True,
                "filters": {"conditions": []}
            },
            "id": uid(),
            "name": "Get All Users",
            "type": "n8n-nodes-base.supabase",
            "typeVersion": 1,
            "position": [420, 400],
            "credentials": {"supabaseApi": SUPABASE_CRED}
        },
        # 3. Filter to active users only
        {
            "parameters": {
                "jsCode": FILTER_ACTIVE_CODE
            },
            "id": uid(),
            "name": "Filter Active Users",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [640, 400]
        },
        # 4. Split In Batches
        {
            "parameters": {
                "batchSize": 1,
                "options": {}
            },
            "id": uid(),
            "name": "Split In Batches",
            "type": "n8n-nodes-base.splitInBatches",
            "typeVersion": 3,
            "position": [860, 400]
        },
        # 5. Get Slack Profile
        {
            "parameters": {
                "method": "GET",
                "url": "=https://slack.com/api/users.info?user={{ $json.slack_user_id }}",
                "authentication": "genericCredentialType",
                "genericAuthType": "httpHeaderAuth",
                "options": {}
            },
            "id": uid(),
            "name": "Get Slack Profile",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [1080, 300],
            "credentials": {"httpHeaderAuth": SLACK_CRED}
        },
        # 6. Extract and Compare
        {
            "parameters": {
                "jsCode": EXTRACT_AND_COMPARE_CODE
            },
            "id": uid(),
            "name": "Extract and Compare",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1300, 300]
        },
        # 7. Has Changed?
        {
            "parameters": {
                "conditions": {
                    "options": {
                        "version": 2,
                        "leftValue": "",
                        "caseSensitive": True,
                        "typeValidation": "strict"
                    },
                    "conditions": [
                        {
                            "id": uid(),
                            "leftValue": "={{ $json.changed }}",
                            "rightValue": True,
                            "operator": {
                                "type": "boolean",
                                "operation": "true"
                            }
                        }
                    ],
                    "combinator": "and"
                },
                "options": {}
            },
            "id": uid(),
            "name": "Has Changed?",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2.2,
            "position": [1520, 300]
        },
        # 8. Update User Record
        {
            "parameters": {
                "operation": "update",
                "tableId": "users",
                "dataToSend": "defineBelow",
                "fieldsUi": {
                    "fieldValues": [
                        {"fieldId": "department", "fieldValue": "={{ $json.newDepartment }}"},
                        {"fieldId": "division", "fieldValue": "={{ $json.newDivision }}"},
                        {"fieldId": "digest_scope", "fieldValue": "={{ $json.newDigestScope }}"}
                    ]
                },
                "filters": {
                    "conditions": [
                        {
                            "keyName": "id",
                            "condition": "eq",
                            "keyValue": "={{ $json.userId }}"
                        }
                    ]
                }
            },
            "id": uid(),
            "name": "Update User Record",
            "type": "n8n-nodes-base.supabase",
            "typeVersion": 1,
            "position": [1740, 200],
            "credentials": {"supabaseApi": SUPABASE_CRED}
        }
    ]

    connections = {
        "Weekly Sunday 10pm PT": {
            "main": [[{"node": "Get All Users", "type": "main", "index": 0}]]
        },
        "Get All Users": {
            "main": [[{"node": "Filter Active Users", "type": "main", "index": 0}]]
        },
        "Filter Active Users": {
            "main": [[{"node": "Split In Batches", "type": "main", "index": 0}]]
        },
        "Split In Batches": {
            "main": [
                [],  # output 0 = done
                [{"node": "Get Slack Profile", "type": "main", "index": 0}]  # output 1 = loop
            ]
        },
        "Get Slack Profile": {
            "main": [[{"node": "Extract and Compare", "type": "main", "index": 0}]]
        },
        "Extract and Compare": {
            "main": [[{"node": "Has Changed?", "type": "main", "index": 0}]]
        },
        "Has Changed?": {
            "main": [
                [{"node": "Update User Record", "type": "main", "index": 0}],  # true
                [{"node": "Split In Batches", "type": "main", "index": 0}]    # false → loop back
            ]
        },
        "Update User Record": {
            "main": [[{"node": "Split In Batches", "type": "main", "index": 0}]]
        }
    }

    return {
        "name": "Weekly Profile Sync",
        "nodes": nodes,
        "connections": connections,
        "settings": {
            "executionOrder": "v1"
        },
        "staticData": None
    }


def main():
    workflow = build_workflow()

    print("Creating Weekly Profile Sync workflow...")
    resp = requests.post(
        f"{N8N_BASE_URL}/api/v1/workflows",
        headers=HEADERS,
        json=workflow
    )
    resp.raise_for_status()
    result = resp.json()
    wf_id = result["id"]
    print(f"  Created: ID={wf_id}, {len(result['nodes'])} nodes")

    # Activate the workflow
    resp2 = requests.post(
        f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}/activate",
        headers=HEADERS
    )
    resp2.raise_for_status()
    print(f"  Activated: {resp2.json().get('active')}")

    # Sync local file
    path = os.path.join(REPO_ROOT, "n8n", "workflows", "Weekly Profile Sync.json")
    # Fetch the canonical version from n8n
    resp3 = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}", headers=HEADERS)
    resp3.raise_for_status()
    with open(path, "w") as f:
        json.dump(resp3.json(), f, indent=4)
    print(f"  Synced: {path}")

    print(f"\nDone! Workflow ID: {wf_id}")
    print("Runs every Sunday 10pm PT (Monday 6am UTC)")


if __name__ == "__main__":
    main()
