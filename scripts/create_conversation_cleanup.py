#!/usr/bin/env python3
"""
Create: Conversation Cleanup cron workflow.

Runs weekly (Sunday 11pm PT) to expire stale conversations.
Sets status='expired' on conversations where expires_at < now() and status is
still 'active' or 'processing'.

This is a safety net — the query-time filter in the Events Handler already
ignores expired conversations, but this keeps the table clean.
"""

import json
import os
import uuid
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

SUPABASE_CRED = {"id": "ASRWWkQ0RSMOpNF1", "name": "Supabase account"}
SUPABASE_REST_URL = "https://rhrlnkbphxntxxxcrgvv.supabase.co/rest/v1"


def uid():
    return str(uuid.uuid4())


def sync_local(wf, filename):
    path = os.path.join(REPO_ROOT, "n8n", "workflows", filename)
    with open(path, "w") as f:
        json.dump(wf, f, indent=4)
    print(f"  Synced {path}")


def build_workflow():
    nodes = [
        # 1. Schedule Trigger — Sunday 11pm PT (Mon 7am UTC in summer, 6am in winter)
        {
            "parameters": {
                "rule": {
                    "interval": [{"field": "cronExpression", "expression": "0 7 * * 1"}]
                }
            },
            "id": uid(),
            "name": "Weekly Cleanup Trigger",
            "type": "n8n-nodes-base.scheduleTrigger",
            "typeVersion": 1.2,
            "position": [0, 400],
        },
        # 2. Expire Stale Conversations — HTTP PATCH
        # Sets status='expired' where expires_at < now() and status in (active, processing)
        {
            "parameters": {
                "method": "PATCH",
                "url": f"{SUPABASE_REST_URL}/conversations?expires_at=lt.now()&status=in.(active,processing)",
                "authentication": "predefinedCredentialType",
                "nodeCredentialType": "supabaseApi",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "Content-Type", "value": "application/json"},
                        {"name": "Prefer", "value": "return=representation"},
                    ]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": '={{ JSON.stringify({ status: "expired" }) }}',
                "options": {},
            },
            "id": uid(),
            "name": "Expire Stale Conversations",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [280, 400],
            "credentials": {"supabaseApi": SUPABASE_CRED},
            "continueOnFail": True,
        },
        # 3. Log Result — Code node
        {
            "parameters": {
                "jsCode": """// Count how many conversations were expired
const items = $input.all();
// Supabase PATCH with return=representation returns the updated rows
const count = items.length;
const firstItem = items[0]?.json;

// If the response is an array (multiple items), count them
let expiredCount = 0;
if (Array.isArray(firstItem)) {
  expiredCount = firstItem.length;
} else if (firstItem && firstItem.id) {
  expiredCount = count;
} else {
  expiredCount = 0;
}

const now = new Date().toISOString();
console.log(`[${now}] Conversation cleanup: ${expiredCount} expired`);

return [{ json: { expiredCount, timestamp: now } }];
"""
            },
            "id": uid(),
            "name": "Log Result",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [560, 400],
        },
    ]

    connections = {
        "Weekly Cleanup Trigger": {
            "main": [[{"node": "Expire Stale Conversations", "type": "main", "index": 0}]]
        },
        "Expire Stale Conversations": {
            "main": [[{"node": "Log Result", "type": "main", "index": 0}]]
        },
    }

    return {
        "name": "Conversation Cleanup",
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1"},
        "staticData": None,
    }


def main():
    workflow = build_workflow()

    print("Creating Conversation Cleanup workflow...")
    resp = requests.post(
        f"{N8N_BASE_URL}/api/v1/workflows", headers=HEADERS, json=workflow
    )
    resp.raise_for_status()
    result = resp.json()
    wf_id = result["id"]
    print(f"  Created: ID={wf_id}, {len(result['nodes'])} nodes")

    print("  Activating workflow...")
    resp2 = requests.post(
        f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}/activate", headers=HEADERS
    )
    resp2.raise_for_status()
    print(f"  Activated: {resp2.json().get('active')}")

    # Sync local file
    resp3 = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}", headers=HEADERS)
    resp3.raise_for_status()
    sync_local(resp3.json(), "Conversation Cleanup.json")

    print(f"\nDone! Workflow ID: {wf_id}")
    print("Runs weekly (Monday 7am UTC / Sunday 11pm PT) to expire stale conversations.")


if __name__ == "__main__":
    main()
