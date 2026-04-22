#!/usr/bin/env python3
"""
Two changes in one script:

1. Executive Inbox (Wgjmfu82wyuwipVN):
   - Add "Assess if Needs Reply" LLM chain (+ Assessment Model + Assessment Parser sub-nodes)
   - Add "If Needs Reply" IF gate
   - Rewire: Is Forwarded? [1] (direct emails) → Assess → If Needs Reply → yes: Is Customer Email? / no: Mark Direct Read
   - Add Confluence MCP as a tool to AI Draft Agent

2. Sales Digest (7sinwSgjkEA40zDj):
   - Update Resolve Identity footer() function to include scopeLabel and theme
"""

import json
import uuid
import requests
import os

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

EXEC_INBOX_ID   = "Wgjmfu82wyuwipVN"
SALES_DIGEST_ID = "7sinwSgjkEA40zDj"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}


def fetch_workflow(wid):
    r = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{wid}", headers=HEADERS)
    r.raise_for_status()
    return r.json()


def push_workflow(wid, wf):
    payload = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": wf.get("settings", {}),
        "staticData": wf.get("staticData"),
    }
    r = requests.put(f"{N8N_BASE_URL}/api/v1/workflows/{wid}", headers=HEADERS, json=payload)
    if not r.ok:
        print(f"  ERROR {r.status_code}: {r.text[:500]}")
        r.raise_for_status()
    return r.json()


def find_node(nodes, name):
    for n in nodes:
        if n["name"] == name:
            return n
    return None


def uid():
    return str(uuid.uuid4())


# ─────────────────────────────────────────────────────────────────────────────
# 1. EXECUTIVE INBOX
# ─────────────────────────────────────────────────────────────────────────────

def fix_executive_inbox():
    print("\n── Executive Inbox ──────────────────────────────────────────────────")
    # Always re-fetch fresh — a prior failed PUT may have saved a draft with partial changes
    wf = fetch_workflow(EXEC_INBOX_ID)
    print(f"  Fetched: {len(wf['nodes'])} nodes")
    nodes = wf["nodes"]
    conns = wf["connections"]

    # ── New node IDs
    assess_id  = uid()
    model_id   = uid()
    parser_id  = uid()
    if_id      = uid()
    conf_id    = uid()

    # ── Positions: slot Assess between Is Forwarded? (208,-144) and Is Customer Email? (432,-144)
    # Place Assess at (208, 80), If Needs Reply at (432, 80), sub-nodes below
    assess_pos  = [208,  80]
    model_pos   = [96,  304]
    parser_pos  = [368, 304]
    if_pos      = [640,  80]
    conf_pos    = [1856, 304]   # below Backstory MCP: Agent

    # ── New nodes ─────────────────────────────────────────────────────────────

    assess_node = {
        "id": assess_id,
        "name": "Assess if Needs Reply",
        "type": "@n8n/n8n-nodes-langchain.chainLlm",
        "typeVersion": 1.4,
        "position": assess_pos,
        "parameters": {
            "prompt": "=Subject: {{ $json.subject }}\n\nFrom: {{ $json.senderEmail || $json.fromEmail || '' }}\n\nMessage:\n{{ $json.bodyText || $json.body || $json.rawBody || $json.textPlain || '' }}",
            "messages": {
                "messageValues": [{
                    "message": (
                        "You are a professional email assistant. Decide whether this email "
                        "genuinely requires a written reply.\n\n"
                        "Return JSON: { \"needsReply\": true } or { \"needsReply\": false }.\n\n"
                        "Do NOT reply for:\n"
                        "- Automated notifications, alerts, or system emails\n"
                        "- Marketing, newsletter, or promotional emails\n"
                        "- Calendar invites, confirmations, or automated scheduling messages\n"
                        "- Out-of-office or bounce/delivery messages\n"
                        "- CC-only threads where no response is expected\n"
                        "- Receipts or invoices already acknowledged\n\n"
                        "DO reply for:\n"
                        "- Direct questions or requests needing an answer\n"
                        "- Customer or partner emails requesting information or action\n"
                        "- Escalations or complaints needing follow-up\n"
                        "- Emails asking for a meeting, decision, or next step\n"
                        "- Business correspondence that clearly expects a reply"
                    )
                }]
            }
        }
    }

    assessment_model = {
        "id": model_id,
        "name": "Assessment Model",
        "type": "@n8n/n8n-nodes-langchain.lmChatAnthropic",
        "typeVersion": 1.3,
        "position": model_pos,
        "parameters": {
            "model": {
                "__rl": True,
                "value": "claude-haiku-4-5-20251001",
                "mode": "list",
                "cachedResultName": "Claude Haiku 4.5"
            },
            "options": {}
        },
        "credentials": {
            "anthropicApi": {"id": "rlAz7ZSl4y6AwRUq", "name": "Anthropic account 2"}
        }
    }

    assessment_parser = {
        "id": parser_id,
        "name": "Assessment Parser",
        "type": "@n8n/n8n-nodes-langchain.outputParserStructured",
        "typeVersion": 1.2,
        "position": parser_pos,
        "parameters": {
            "jsonSchema": json.dumps({
                "type": "object",
                "properties": {
                    "needsReply": {"type": "boolean"}
                },
                "required": ["needsReply"]
            }, indent=2)
        }
    }

    if_needs_reply = {
        "id": if_id,
        "name": "If Needs Reply",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2,
        "position": if_pos,
        "parameters": {
            "conditions": {
                "options": {
                    "caseSensitive": True,
                    "leftValue": "",
                    "typeValidation": "strict",
                    "version": 2
                },
                "conditions": [{
                    "id": uid(),
                    "leftValue": "={{ $json.needsReply }}",
                    "operator": {"type": "boolean", "operation": "true", "singleValue": True}
                }],
                "combinator": "and"
            },
            "options": {}
        }
    }

    confluence_mcp = {
        "id": conf_id,
        "name": "Confluence MCP",
        "type": "@n8n/n8n-nodes-langchain.mcpClientTool",
        "typeVersion": 1.2,
        "position": conf_pos,
        "parameters": {
            "endpointUrl": "https://mcp.atlassian.com/v1/sse",
            "authentication": "mcpOAuth2Api",
            "options": {"timeout": 30000}
        },
        "credentials": {
            "mcpOAuth2Api": {"id": "mL7GmjUrxj1FpYxZ", "name": "Atlassian MCP"}
        }
    }

    nodes += [assess_node, assessment_model, assessment_parser, if_needs_reply, confluence_mcp]
    print("  ✓ Added 5 new nodes: Assess chain, Assessment Model, Assessment Parser, If Needs Reply, Confluence MCP")

    # ── Rewire connections ────────────────────────────────────────────────────

    # Currently:  Is Forwarded? [1] → Is Customer Email? (idx 0)
    # Change to:  Is Forwarded? [1] → Assess if Needs Reply (idx 0)
    fwd_conns = conns.get("Is Forwarded?", {}).get("main", [])
    if len(fwd_conns) >= 2:
        # Output 1 (false = direct email) → point to Assess instead of Is Customer Email?
        fwd_conns[1] = [{"node": "Assess if Needs Reply", "type": "main", "index": 0}]
        print("  ✓ Rewired Is Forwarded? [1] → Assess if Needs Reply")
    else:
        print("  ✗ Unexpected Is Forwarded? connection structure — manual check needed")

    # Assess if Needs Reply → If Needs Reply (main)
    conns["Assess if Needs Reply"] = {
        "main": [[{"node": "If Needs Reply", "type": "main", "index": 0}]]
    }

    # Assessment Model → Assess if Needs Reply (ai_languageModel)
    conns["Assessment Model"] = {
        "ai_languageModel": [[{"node": "Assess if Needs Reply", "type": "ai_languageModel", "index": 0}]]
    }

    # Assessment Parser → Assess if Needs Reply (ai_outputParser)
    conns["Assessment Parser"] = {
        "ai_outputParser": [[{"node": "Assess if Needs Reply", "type": "ai_outputParser", "index": 0}]]
    }

    # If Needs Reply:
    #   [0] true  → Is Customer Email? (existing destination for direct emails)
    #   [1] false → Mark Direct Read
    conns["If Needs Reply"] = {
        "main": [
            [{"node": "Is Customer Email?", "type": "main", "index": 0}],  # true
            [{"node": "Mark Direct Read",   "type": "main", "index": 0}],  # false
        ]
    }
    print("  ✓ If Needs Reply [0]=yes→Is Customer Email?, [1]=no→Mark Direct Read")

    # Confluence MCP → AI Draft Agent (ai_tool)
    conf_conn = conns.get("Confluence MCP", {"ai_tool": [[]]})
    if "ai_tool" not in conf_conn:
        conf_conn["ai_tool"] = [[]]
    conf_conn["ai_tool"] = [[{"node": "AI Draft Agent", "type": "ai_tool", "index": 0}]]
    conns["Confluence MCP"] = conf_conn
    print("  ✓ Confluence MCP → AI Draft Agent (ai_tool)")

    # Push
    print("  Pushing to n8n...")
    result = push_workflow(EXEC_INBOX_ID, wf)
    print(f"  ✓ Pushed: '{result.get('name')}' ({len(result.get('nodes',[]))} nodes)")

    # Sync local
    fresh = fetch_workflow(EXEC_INBOX_ID)
    local_path = os.path.join(REPO_ROOT, "n8n/workflows/Executive Inbox.json")
    with open(local_path, "w") as f:
        json.dump(fresh, f, indent=2)
    print(f"  ✓ Synced local: {local_path}")


# ─────────────────────────────────────────────────────────────────────────────
# 2. SALES DIGEST — footer scope + theme
# ─────────────────────────────────────────────────────────────────────────────

OLD_FOOTER_FN = """// === Scope-aware footer ===
function footer(scope) {
  if (scope === 'team_deals') return `Backstory team intelligence • ${currentDate} • ${timeStr} PT`;
  if (scope === 'top_pipeline') return `Backstory executive intelligence • ${currentDate} • ${timeStr} PT`;
  return `Backstory intelligence • ${currentDate} • ${timeStr} PT`;
}"""

NEW_FOOTER_FN = """// === Scope-aware footer (includes scope label and theme for transparency) ===
function footer(scope) {
  const themeNames = {
    full_pipeline:     'Full Pipeline',
    engagement_shifts: 'Engagement Shifts',
    at_risk:           'At-Risk Focus',
    momentum:          'Momentum',
    week_review:       'Week Review'
  };
  const themeDisplay = themeNames[theme] || theme;

  let base;
  if (scope === 'team_deals')    base = 'Backstory team intelligence';
  else if (scope === 'top_pipeline') base = 'Backstory executive intelligence';
  else                           base = 'Backstory intelligence';

  return `${base} • ${currentDate} • ${timeStr} PT • ${scopeLabel} • ${themeDisplay}`;
}"""


def fix_sales_digest_footer():
    print("\n── Sales Digest ─────────────────────────────────────────────────────")
    wf = fetch_workflow(SALES_DIGEST_ID)
    nodes = wf["nodes"]

    ri = find_node(nodes, "Resolve Identity")
    if not ri:
        print("  ✗ Could not find 'Resolve Identity' node")
        return

    code = ri["parameters"]["jsCode"]
    if OLD_FOOTER_FN not in code:
        print("  ✗ Footer function not found in expected form — may have been modified already")
        print("    Searching for partial match...")
        if "function footer(scope)" in code:
            # Try targeted replacement of just the return lines
            import re
            new_code = re.sub(
                r"function footer\(scope\) \{[^}]+\}",
                NEW_FOOTER_FN.strip(),
                code,
                flags=re.DOTALL
            )
            if new_code != code:
                ri["parameters"]["jsCode"] = new_code
                print("  ✓ Footer function replaced via regex")
            else:
                print("  ✗ Regex replacement also failed — check Resolve Identity code manually")
                return
        else:
            print("  ✗ No footer function found at all")
            return
    else:
        ri["parameters"]["jsCode"] = code.replace(OLD_FOOTER_FN, NEW_FOOTER_FN)
        print("  ✓ Footer function updated to include scopeLabel + themeDisplay")

    print("  Pushing to n8n...")
    result = push_workflow(SALES_DIGEST_ID, wf)
    print(f"  ✓ Pushed: '{result.get('name')}' ({len(result.get('nodes',[]))} nodes)")

    fresh = fetch_workflow(SALES_DIGEST_ID)
    local_path = os.path.join(REPO_ROOT, "n8n/workflows/Sales Digest.json")
    with open(local_path, "w") as f:
        json.dump(fresh, f, indent=2)
    print(f"  ✓ Synced local: {local_path}")


if __name__ == "__main__":
    fix_executive_inbox()
    fix_sales_digest_footer()
    print("\nDone.")
