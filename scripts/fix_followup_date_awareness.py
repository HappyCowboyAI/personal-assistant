#!/usr/bin/env python3
"""Fix follow-up email draft prompt to be date-aware and adjust language for stale meetings."""

import json
import os
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

WORKFLOW_ID = "QuQbIaWetunUOFUW"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

def main():
    print("Fetching Slack Events Handler workflow (live)...")
    resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{WORKFLOW_ID}", headers=HEADERS)
    resp.raise_for_status()
    wf = resp.json()
    nodes = wf["nodes"]
    print(f"  {len(nodes)} nodes")

    target = None
    for n in nodes:
        if n["name"] == "Build DM System Prompt":
            target = n
            break

    if not target:
        print("ERROR: Build DM System Prompt not found!")
        return

    code = target["parameters"]["jsCode"]

    if "DATE AWARENESS" in code:
        print("  Already has date awareness — skipping")
        return

    # Find and replace the followup header section
    old_marker = "**FOLLOW-UP EMAIL DRAFT MODE**"
    if old_marker not in code:
        print("  ERROR: Could not find FOLLOW-UP EMAIL DRAFT MODE marker")
        return

    # Replace the specific section
    old_block = (
        "'**FOLLOW-UP EMAIL DRAFT MODE**',\n"
        "    '',\n"
        "    'The user wants to draft a follow-up email. Use People.ai MCP tools to:',\n"
        "    '1. Find the most recent meeting with the mentioned account',\n"
        "    '2. Get meeting participants and their roles',\n"
        "    '3. Check current deal status, stage, and next steps',\n"
        "    '4. Review recent engagement context',"
    )

    new_block = (
        "'**FOLLOW-UP EMAIL DRAFT MODE**',\n"
        "    '',\n"
        "    \"Today\\'s date is \" + new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' }) + \".\",\n"
        "    '',\n"
        "    'The user wants to draft a follow-up email. Use People.ai MCP tools to:',\n"
        "    '1. Find the most recent meeting with the mentioned account',\n"
        "    '2. Get meeting participants and their roles',\n"
        "    '3. Check current deal status, stage, and next steps',\n"
        "    '4. Review recent engagement context',\n"
        "    '',\n"
        "    '**DATE AWARENESS — adjust your follow-up language based on when the meeting was:**',\n"
        "    '- Same day: \"Thanks for the conversation today\"',\n"
        "    '- Yesterday: \"Thanks for the conversation yesterday\"',\n"
        "    '- 2-3 days ago: \"I wanted to follow up on our conversation from {day}\"',\n"
        "    '- 4-7 days ago: \"Circling back on our discussion last {day}\" — keep it natural',\n"
        "    '- 7+ days ago: \"I wanted to revisit a few items from our meeting on {date}\" — acknowledge the gap',\n"
        "    '- NEVER use immediate-sounding language like \"Thanks for the productive discussion\" if the meeting was 2+ days ago',"
    )

    if old_block in code:
        code = code.replace(old_block, new_block)
        target["parameters"]["jsCode"] = code
        print("  Updated followup prompt with date awareness + language adjustment rules")
    else:
        print("  ERROR: Could not find exact old block — code may have changed")
        print("  Attempting line-by-line approach...")
        # Fallback: inject after the FOLLOW-UP EMAIL DRAFT MODE line
        lines = code.split('\n')
        new_lines = []
        for i, line in enumerate(lines):
            new_lines.append(line)
            if "'**FOLLOW-UP EMAIL DRAFT MODE**'," in line:
                # Find the next empty string line and inject after the 4 numbered items
                pass  # We'll use a different approach
        print("  Fallback not implemented — please check code manually")
        return

    # Push
    print("\n=== Pushing workflow ===")
    payload = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": wf.get("settings", {}),
        "staticData": wf.get("staticData"),
    }
    resp = requests.put(
        f"{N8N_BASE_URL}/api/v1/workflows/{WORKFLOW_ID}",
        headers=HEADERS,
        json=payload,
    )
    resp.raise_for_status()
    print(f"  HTTP 200, {len(resp.json()['nodes'])} nodes")

    # Sync
    print("\n=== Re-fetching and syncing ===")
    final = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{WORKFLOW_ID}", headers=HEADERS).json()
    path = os.path.join(REPO_ROOT, "n8n", "workflows", "Slack Events Handler.json")
    with open(path, "w") as f:
        json.dump(final, f, indent=4)
    print(f"  Synced {path}")
    print("\nDone! Follow-up prompt now adjusts language based on meeting recency.")

if __name__ == "__main__":
    main()
