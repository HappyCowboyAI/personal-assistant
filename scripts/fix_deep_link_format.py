#!/usr/bin/env python3
"""
Hot-fix: Change deep link format from separate "View in People.ai" line
to making the deal/account name itself the clickable link.
"""

import json
import os
import requests

N8N_BASE_URL = "https://scottai.trackslife.com"
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

INSIGHTS_WF_ID = "cV5GDdW5MiukdJdN"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}


def main():
    print("Fetching Opportunity Insights workflow...")
    resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{INSIGHTS_WF_ID}", headers=HEADERS)
    resp.raise_for_status()
    wf = resp.json()

    fixed = False
    for node in wf["nodes"]:
        if node["name"] == "Resolve Insights Identity":
            code = node["parameters"]["jsCode"]

            # Fix the deep links instruction
            old = """DEEP LINKS \u2014 when mentioning a deal or account, include a People.ai link:
- For opportunities: <https://app.people.ai/opportunities/CRMID|View in People.ai> (replace CRMID with the CRM ID from the data table)
- For accounts: <https://app.people.ai/accounts/CRMID|View in People.ai>"""

            new = """DEEP LINKS \u2014 make the deal or account NAME itself a clickable link. Do NOT add a separate "View in People.ai" line.
- For opportunities: <https://app.people.ai/opportunities/CRMID|Deal Name Here> (replace CRMID with the CRM ID from the data table, and "Deal Name Here" with the actual opportunity name)
- For accounts: <https://app.people.ai/accounts/CRMID|Account Name Here>
- Example: *<https://app.people.ai/opportunities/006abc123|PwC - ClosePlan Pilot>* | Closes May 31"""

            if old in code:
                code = code.replace(old, new)
                fixed = True
                print("  Updated deep link format instructions")
            else:
                print("  Deep link pattern not found (may already be updated)")

            # Also update per-type prompts
            code = code.replace("Include People.ai deep link.", "Make the deal name a clickable People.ai link.")
            code = code.replace("Include People.ai deep links.", "Make deal names clickable People.ai links.")
            code = code.replace("Include deep links.", "Make deal names clickable People.ai links.")

            if code != node["parameters"]["jsCode"]:
                node["parameters"]["jsCode"] = code
                fixed = True

            break

    if not fixed:
        print("  No changes needed")
        return

    payload = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
               "settings": wf.get("settings", {}), "staticData": wf.get("staticData")}
    resp = requests.put(f"{N8N_BASE_URL}/api/v1/workflows/{INSIGHTS_WF_ID}", headers=HEADERS, json=payload)
    resp.raise_for_status()
    result = resp.json()
    print(f"  Pushed: {len(result['nodes'])} nodes")

    path = os.path.join(REPO_ROOT, "n8n", "workflows", "Opportunity Insights.json")
    with open(path, "w") as f:
        json.dump(result, f, indent=4)
    print(f"  Synced {path}")
    print("\nDone! Deal names will now be clickable links instead of separate 'View in People.ai' lines.")


if __name__ == "__main__":
    main()
