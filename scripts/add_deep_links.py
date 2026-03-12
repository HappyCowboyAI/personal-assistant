#!/usr/bin/env python3
"""
Add People.ai deep links to Sales Digest and Meeting Brief workflows.
- Sales Digest: Include CRM ID in opp table + instruct Claude to add links
- Meeting Brief: Add opportunity link to deal context if CRM ID available
- URL format: https://app.people.ai/opportunities/{crmId}
"""

import json
import os
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

SALES_DIGEST_ID = "7sinwSgjkEA40zDj"
ON_DEMAND_DIGEST_ID = "vxGajBdXFBaOCdkG"
MEETING_BRIEF_ID = "Cj4HcHfbzy9OZhwE"

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


# ============================================================
# SALES DIGEST — add CRM ID to opp table + deep link instructions
# ============================================================
def upgrade_sales_digest(wf):
    print("\n=== Upgrading Sales Digest with deep links ===")
    updated_count = 0

    for node in wf["nodes"]:
        # 1. Filter User Opps — add crmId to opp table markdown
        if node["name"] == "Filter User Opps":
            code = node["parameters"]["jsCode"]

            # Add CRM ID column to my_deals table
            old_my = "oppTable = '| Opportunity | Account | Stage | Close Date | Amount | Engagement |\\n';"
            new_my = "oppTable = '| Opportunity | Account | Stage | Close Date | Amount | Engagement | CRM ID |\\n';"
            code = code.replace(old_my, new_my)

            old_my_sep = "oppTable += '|---|---|---|---|---|---|\\n';"
            new_my_sep = "oppTable += '|---|---|---|---|---|---|---|\\n';"
            code = code.replace(old_my_sep, new_my_sep)

            old_my_row = "oppTable += '| ' + opp.name + ' | ' + opp.account + ' | ' + opp.stage + ' | ' + opp.closeDate + ' | ' + opp.amount + ' | ' + opp.engagement + ' |\\n';"
            new_my_row = "oppTable += '| ' + opp.name + ' | ' + opp.account + ' | ' + opp.stage + ' | ' + opp.closeDate + ' | ' + opp.amount + ' | ' + opp.engagement + ' | ' + (opp.crmId || '') + ' |\\n';"
            code = code.replace(old_my_row, new_my_row)

            # Add CRM ID column to team/pipeline table
            old_team = "oppTable = '| Opportunity | Account | Owner | Stage | Close Date | Amount | Engagement |\\n';"
            new_team = "oppTable = '| Opportunity | Account | Owner | Stage | Close Date | Amount | Engagement | CRM ID |\\n';"
            code = code.replace(old_team, new_team)

            old_team_sep = "oppTable += '|---|---|---|---|---|---|---|\\n';"
            new_team_sep = "oppTable += '|---|---|---|---|---|---|---|---|\\n';"
            code = code.replace(old_team_sep, new_team_sep)

            old_team_row = "oppTable += '| ' + opp.name + ' | ' + opp.account + ' | ' + opp.owners + ' | ' + opp.stage + ' | ' + opp.closeDate + ' | ' + opp.amount + ' | ' + opp.engagement + ' |\\n';"
            new_team_row = "oppTable += '| ' + opp.name + ' | ' + opp.account + ' | ' + opp.owners + ' | ' + opp.stage + ' | ' + opp.closeDate + ' | ' + opp.amount + ' | ' + opp.engagement + ' | ' + (opp.crmId || '') + ' |\\n';"
            code = code.replace(old_team_row, new_team_row)

            if code != node["parameters"]["jsCode"]:
                node["parameters"]["jsCode"] = code
                print("  Filter User Opps: added CRM ID column to opp tables")
                updated_count += 1
            else:
                print("  Filter User Opps: CRM ID column may already be present or format differs")

        # 2. Resolve Identity — add deep link instruction to system prompt
        elif node["name"] == "Resolve Identity":
            code = node["parameters"]["jsCode"]

            # Add deep link instruction to the MCP rules section
            old_mcp = "Do NOT use MCP to search for or list opportunities"
            new_mcp = """DEEP LINKS — when mentioning a deal, include a People.ai link using the CRM ID from the data table:
<https://app.people.ai/opportunities/CRMID|View in People.ai> (replace CRMID with the actual CRM ID)

Do NOT use MCP to search for or list opportunities"""

            if old_mcp in code and "DEEP LINKS" not in code:
                code = code.replace(old_mcp, new_mcp)
                node["parameters"]["jsCode"] = code
                print("  Resolve Identity: added deep link instruction to system prompt")
                updated_count += 1
            else:
                print("  Resolve Identity: deep link instruction may already exist or MCP rules not found")

    return wf, updated_count


# ============================================================
# MEETING BRIEF — add opportunity deep link to deal context
# ============================================================
def upgrade_meeting_brief(wf):
    print("\n=== Upgrading Meeting Brief with deep links ===")
    updated_count = 0

    for node in wf["nodes"]:
        if node["name"] == "Resolve Meeting Identity":
            code = node["parameters"]["jsCode"]

            # Add deep link to deal context section
            old_deal_context = "dealContext = `\\n\\u2501\\u2501\\u2501 DEAL CONTEXT \\u2501\\u2501\\u2501"
            new_deal_context = "dealContext = `\\n\\u2501\\u2501\\u2501 DEAL CONTEXT \\u2501\\u2501\\u2501"

            # Add CRM ID variable extraction + link to deal context
            old_has_opp = "const hasOpportunity = !!(opportunityName && opportunityName !== 'N/A' && opportunityName.trim());"
            new_has_opp = """const opportunityCrmId = input.opportunityCrmId || '';
const hasOpportunity = !!(opportunityName && opportunityName !== 'N/A' && opportunityName.trim());"""

            if old_has_opp in code and "opportunityCrmId" not in code:
                code = code.replace(old_has_opp, new_has_opp)

                # Add People.ai link to deal context block
                old_context_block = "Engagement: ${opportunityEngagement}\n`;"
                new_context_block = """Engagement: ${opportunityEngagement}
${opportunityCrmId ? 'People.ai: https://app.people.ai/opportunities/' + opportunityCrmId : ''}
`;"""
                code = code.replace(old_context_block, new_context_block)

                # Add deep link instruction to system prompt
                old_prepare = "Prepare a 90-second meeting prep briefing"
                new_prepare = """When mentioning a deal, include a People.ai link: <https://app.people.ai/opportunities/CRMID|View in People.ai>

Prepare a 90-second meeting prep briefing"""
                if "DEEP LINKS" not in code and "people.ai/opportunities" not in code.split("Prepare a 90")[0]:
                    code = code.replace(old_prepare, new_prepare)

                node["parameters"]["jsCode"] = code
                print("  Resolve Meeting Identity: added CRM ID + deep link")
                updated_count += 1
            else:
                print("  Resolve Meeting Identity: deep links may already exist or format differs")

    return wf, updated_count


# ============================================================
# MAIN
# ============================================================
def main():
    # Step 1: Upgrade Sales Digest
    print("Fetching Sales Digest...")
    sd_wf = fetch_workflow(SALES_DIGEST_ID)
    print(f"  {len(sd_wf['nodes'])} nodes")

    sd_wf, sd_count = upgrade_sales_digest(sd_wf)

    if sd_count > 0:
        print("\n=== Pushing Sales Digest ===")
        result = push_workflow(SALES_DIGEST_ID, sd_wf)
        print(f"  HTTP 200, {len(result['nodes'])} nodes")
        sync_local(result, "Sales Digest.json")
    else:
        print("  No changes to Sales Digest")

    # Step 2: Also update On-Demand Digest (shares same code pattern)
    print("\nFetching On-Demand Digest...")
    try:
        od_wf = fetch_workflow(ON_DEMAND_DIGEST_ID)
        print(f"  {len(od_wf['nodes'])} nodes")

        # On-Demand Digest has the same Filter User Opps and Resolve Identity nodes
        od_wf, od_count = upgrade_sales_digest(od_wf)

        if od_count > 0:
            print("\n=== Pushing On-Demand Digest ===")
            result = push_workflow(ON_DEMAND_DIGEST_ID, od_wf)
            print(f"  HTTP 200, {len(result['nodes'])} nodes")
            sync_local(result, "On-Demand Digest.json")
        else:
            print("  No changes to On-Demand Digest")
    except Exception as e:
        print(f"  Could not update On-Demand Digest: {e}")

    # Step 3: Upgrade Meeting Brief
    print("\nFetching Meeting Brief...")
    try:
        mb_wf = fetch_workflow(MEETING_BRIEF_ID)
        print(f"  {len(mb_wf['nodes'])} nodes")

        mb_wf, mb_count = upgrade_meeting_brief(mb_wf)

        if mb_count > 0:
            print("\n=== Pushing Meeting Brief ===")
            result = push_workflow(MEETING_BRIEF_ID, mb_wf)
            print(f"  HTTP 200, {len(result['nodes'])} nodes")
            sync_local(result, "Meeting Brief.json")
        else:
            print("  No changes to Meeting Brief")
    except Exception as e:
        print(f"  Could not update Meeting Brief: {e}")

    print("\nDone! Deep links added to:")
    print("  - Sales Digest: CRM ID in opp table + deep link instruction in prompts")
    print("  - On-Demand Digest: same updates (shares code pattern)")
    print("  - Meeting Brief: CRM ID + People.ai link in deal context")
    print("\n  Link format: https://app.people.ai/opportunities/{crmId}")
    print("  Note: Insights and Deal Watch workflows already include deep links from creation.")


if __name__ == "__main__":
    main()
