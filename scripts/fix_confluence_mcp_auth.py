#!/usr/bin/env python3
"""
Switch the Confluence MCP node from OAuth2 to Multi-Header Auth with API token.

Problem: Atlassian's MCP gateway uses OAuth 2.1, which n8n's mcpOAuth2Api doesn't
fully support — resulting in `accessibleResources.filter is not a function` errors.

Fix: Create a Multi-Header Auth credential with the Atlassian API token as a Bearer
header, then update the Confluence MCP node to use it.
"""

import json
import os
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = os.getenv("N8N_API_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA")

PRESENTATION_WF_ID = "lJypxYaw0BmUsTV8"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

# Atlassian API token
ATLASSIAN_API_TOKEN = "REDACTED_ATLASSIAN_TOKEN_2"
ATLASSIAN_MCP_ENDPOINT = "https://mcp.atlassian.com/v1/sse"


def fetch_workflow(wf_id):
    resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def push_workflow(wf_id, wf):
    payload = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": wf.get("settings", {}),
        "staticData": wf.get("staticData"),
    }
    resp = requests.put(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}", headers=HEADERS, json=payload)
    resp.raise_for_status()
    return resp.json()


def create_credential():
    """Create a Multi-Header Auth credential for Atlassian MCP."""
    payload = {
        "name": "Atlassian MCP API Token",
        "type": "httpMultipleHeadersAuth",
        "data": {
            "headers": [
                {"name": "Authorization", "value": f"Bearer {ATLASSIAN_API_TOKEN}"}
            ]
        }
    }
    print("   Attempting to create credential via API...")
    resp = requests.post(f"{N8N_BASE_URL}/api/v1/credentials", headers=HEADERS, json=payload)

    if resp.status_code in (200, 201):
        cred = resp.json()
        print(f"   Created credential: id={cred['id']}, name={cred['name']}")
        return cred["id"], cred["name"]
    else:
        print(f"   API returned {resp.status_code}: {resp.text}")
        print("   Credential creation via API may not be supported.")
        print("   Falling back: you'll need to create it in the n8n UI.")
        return None, None


def sync_local(wf, filename):
    path = os.path.join(REPO_ROOT, "n8n", "workflows", filename)
    with open(path, "w") as f:
        json.dump(wf, f, indent=4)
    print(f"  Synced {path}")


def main():
    print("=== Fix Confluence MCP Auth ===\n")

    # 1. Try to create credential
    print("1. Creating Multi-Header Auth credential for Atlassian MCP...")
    cred_id, cred_name = create_credential()

    if not cred_id:
        # If API creation failed, check if we can use existing credentials
        print("\n   Checking for existing usable credentials...")
        resp = requests.get(f"{N8N_BASE_URL}/api/v1/credentials", headers=HEADERS)
        resp.raise_for_status()
        creds = resp.json().get("data", [])

        # Look for any existing Atlassian multi-header credential
        for c in creds:
            if c["type"] == "httpMultipleHeadersAuth" and "atlassian" in c["name"].lower():
                cred_id = c["id"]
                cred_name = c["name"]
                print(f"   Found existing: id={cred_id}, name={cred_name}")
                break

        if not cred_id:
            print("\n   ERROR: No suitable credential found.")
            print("   Please create a 'Multi-Header Auth' credential in n8n UI with:")
            print(f"     Header Name: Authorization")
            print(f"     Header Value: Bearer {ATLASSIAN_API_TOKEN[:20]}...")
            print("   Then update the Confluence MCP node manually.")
            return

    # 2. Fetch the Backstory Presentation workflow
    print(f"\n2. Fetching Backstory Presentation workflow ({PRESENTATION_WF_ID})...")
    wf = fetch_workflow(PRESENTATION_WF_ID)

    # 3. Find and update the Confluence MCP node
    print("\n3. Updating Confluence MCP node...")
    updated = False
    for node in wf["nodes"]:
        if node["name"] == "Confluence MCP":
            print(f"   Found: id={node['id']}")
            print(f"   Current auth: {node['parameters'].get('authentication', 'N/A')}")
            print(f"   Current cred: {json.dumps(node.get('credentials', {}))}")

            # Update parameters: switch from mcpOAuth2Api to multipleHeadersAuth
            node["parameters"]["authentication"] = "multipleHeadersAuth"
            # Remove serverTransport if present (default is fine for SSE)
            # Keep endpointUrl and options as-is

            # Update credential reference
            node["credentials"] = {
                "httpMultipleHeadersAuth": {
                    "id": cred_id,
                    "name": cred_name
                }
            }

            print(f"   Updated auth: multipleHeadersAuth")
            print(f"   Updated cred: id={cred_id}, name={cred_name}")
            updated = True
            break

    if not updated:
        print("   ERROR: Confluence MCP node not found!")
        return

    # 4. Push updated workflow
    print("\n4. Pushing updated workflow...")
    result = push_workflow(PRESENTATION_WF_ID, wf)
    print("   Done!")

    # 5. Activate workflow
    print("\n5. Activating workflow...")
    resp = requests.patch(
        f"{N8N_BASE_URL}/api/v1/workflows/{PRESENTATION_WF_ID}",
        headers=HEADERS,
        json={"active": True}
    )
    resp.raise_for_status()
    print("   Activated!")

    # 6. Sync local copy
    print("\n6. Syncing local JSON...")
    sync_local(result, "Backstory Presentation.json")

    print("\n=== Fix applied! ===")
    print(f"Confluence MCP now uses Multi-Header Auth (credential: {cred_name})")
    print("The agent should now be able to search Confluence when generating presentations.")


if __name__ == "__main__":
    main()
