"""
Shared helpers for n8n workflow modification scripts.

Centralizes: API config, credentials, common helpers, and node factories.
"""

import json
import os
import uuid

import requests

# ── API Configuration ──────────────────────────────────────────────────
N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = os.getenv("N8N_API_KEY")
if not N8N_API_KEY:
    raise RuntimeError(
        "N8N_API_KEY environment variable is required. "
        "Set it before running any workflow script."
    )

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

# ── Credential IDs (live n8n instance) ─────────────────────────────────
SUPABASE_CRED = {"id": "ASRWWkQ0RSMOpNF1", "name": "Supabase account"}
ANTHROPIC_CRED = {"id": "rlAz7ZSl4y6AwRUq", "name": "Anthropic account 2"}
MCP_CRED = {"id": "wvV5pwBeIL7f2vLG", "name": "People.ai MCP Multi-Header"}
SLACK_CRED = {"id": "LluVuiMJ8NUbAiG7", "name": "Slackbot Auth Token"}

# ── URLs ───────────────────────────────────────────────────────────────
SUPABASE_URL = "https://rhrlnkbphxntxxxcrgvv.supabase.co"
PEOPLEAI_MCP_URL = "https://mcp.people.ai/mcp"
SLACK_CHAT_POST = "https://slack.com/api/chat.postMessage"
SLACK_CHAT_UPDATE = "https://slack.com/api/chat.update"
SLACK_CONVERSATIONS_OPEN = "https://slack.com/api/conversations.open"

# ── n8n Node Types ─────────────────────────────────────────────────────
NODE_HTTP_REQUEST = "n8n-nodes-base.httpRequest"
NODE_CODE = "n8n-nodes-base.code"
NODE_IF = "n8n-nodes-base.if"
NODE_SWITCH = "n8n-nodes-base.switch"
NODE_SPLIT_IN_BATCHES = "n8n-nodes-base.splitInBatches"
NODE_SCHEDULE_TRIGGER = "n8n-nodes-base.scheduleTrigger"
NODE_AGENT = "@n8n/n8n-nodes-langchain.agent"
NODE_ANTHROPIC_CHAT = "@n8n/n8n-nodes-langchain.lmChatAnthropic"
NODE_MCP_CLIENT = "@n8n/n8n-nodes-langchain.mcpClientTool"

MODEL_SONNET = "claude-sonnet-4-5-20250929"

# ── Workflow IDs ───────────────────────────────────────────────────────
WF_EVENTS_HANDLER = "QuQbIaWetunUOFUW"
WF_INTERACTIVE_HANDLER = "JgVjCqoT6ZwGuDL1"
WF_BACKSTORY = "Yg5GB1byqB0qD-5wVDOAn"
WF_SALES_DIGEST = "7sinwSgjkEA40zDj"
WF_SILENCE_MONITOR = "6FsYIe3tYj0HfRY2"
WF_FOLLOWUP_CRON = "JhDuCvZdFN4PFTOW"
WF_MEETING_PREP_CRON = "Of1U4T6x07aVqBYD"
WF_ON_DEMAND_DIGEST = "vxGajBdXFBaOCdkG"
WF_MEETING_BRIEF = "Cj4HcHfbzy9OZhwE"
WF_PROFILE_SYNC = "EDLS1vIbb4gNebIv"
WF_DEAL_WATCH_CRON = "kZr1QKPiE7zxcn2n"


# ── Core Helpers ───────────────────────────────────────────────────────

def uid():
    """Generate a random UUID for n8n node IDs."""
    return str(uuid.uuid4())


def find_node(nodes, name):
    """Find a node by name in a list of n8n nodes."""
    for n in nodes:
        if n["name"] == name:
            return n
    return None


def fetch_workflow(wf_id):
    """GET a workflow from n8n by ID."""
    resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def push_workflow(wf_id, wf):
    """PUT a workflow back to n8n. Returns the response JSON (the updated workflow)."""
    payload = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": wf.get("settings", {}),
        "staticData": wf.get("staticData"),
    }
    resp = requests.put(
        f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}",
        headers=HEADERS,
        json=payload,
    )
    resp.raise_for_status()
    return resp.json()


def sync_local(wf_json, filename):
    """Write workflow JSON to the local n8n/workflows/ directory."""
    path = os.path.join(REPO_ROOT, "n8n", "workflows", filename)
    with open(path, "w") as f:
        json.dump(wf_json, f, indent=4)
    print(f"  Synced {path}")


def activate_workflow(wf_id):
    """POST to activate a workflow."""
    resp = requests.post(
        f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}/activate",
        headers=HEADERS,
    )
    resp.raise_for_status()
    return resp.json()


def modify_workflow(wf_id, local_filename, modifier_fn):
    """
    Fetch-modify-push-sync lifecycle for workflow modifications.

    modifier_fn(nodes, connections) -> int (number of changes made).
    If 0 changes, skips push/sync.
    Uses the PUT response for local sync (no redundant re-fetch).
    """
    print(f"Fetching workflow {wf_id} (live)...")
    wf = fetch_workflow(wf_id)
    print(f"  {len(wf['nodes'])} nodes")

    changes = modifier_fn(wf["nodes"], wf.get("connections", {}))

    if changes == 0:
        print("\n  No changes needed")
        return wf

    print(f"\n=== Pushing workflow ({changes} changes) ===")
    result = push_workflow(wf_id, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")

    print("\n=== Syncing ===")
    sync_local(result, local_filename)

    return result


def create_or_update_workflow(workflow_dict, local_filename):
    """
    Create a new workflow or update an existing one by name.
    Activates it and syncs locally. Returns the final workflow JSON.
    """
    name = workflow_dict["name"]
    print(f"Looking for existing '{name}' workflow...")

    # Check if exists
    resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows", headers=HEADERS)
    resp.raise_for_status()
    existing = None
    for w in resp.json().get("data", []):
        if w["name"] == name:
            existing = w
            break

    if existing:
        wf_id = existing["id"]
        print(f"  Found existing: {wf_id} — updating")
        result = push_workflow(wf_id, workflow_dict)
    else:
        print("  Not found — creating new workflow")
        resp = requests.post(
            f"{N8N_BASE_URL}/api/v1/workflows",
            headers=HEADERS,
            json=workflow_dict,
        )
        resp.raise_for_status()
        result = resp.json()
        wf_id = result["id"]
        print(f"  Created: {wf_id}")

    print(f"\n=== Activating workflow {wf_id} ===")
    activate_workflow(wf_id)
    print("  Activated")

    # Re-fetch to get canonical version with activation state
    final = fetch_workflow(wf_id)
    print("\n=== Syncing ===")
    sync_local(final, local_filename)

    return final


# ── Node Factory Helpers ───────────────────────────────────────────────

def make_code_node(name, js_code, position):
    """Create an n8n Code node."""
    return {
        "parameters": {"jsCode": js_code},
        "id": uid(),
        "name": name,
        "type": NODE_CODE,
        "typeVersion": 2,
        "position": position,
    }


def make_slack_http_node(name, api_url, json_body, position):
    """Create an HTTP Request node for Slack API calls."""
    return {
        "parameters": {
            "method": "POST",
            "url": api_url,
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Content-Type", "value": "application/json"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": json_body,
            "options": {},
        },
        "id": uid(),
        "name": name,
        "type": NODE_HTTP_REQUEST,
        "typeVersion": 4.2,
        "position": position,
        "credentials": {"httpHeaderAuth": SLACK_CRED},
    }


def make_supabase_http_node(name, method, url_path, position, json_body=None,
                            extra_headers=None):
    """Create an HTTP Request node for Supabase REST API calls."""
    params = {
        "method": method,
        "url": f"{SUPABASE_URL}/rest/v1/{url_path}",
        "authentication": "predefinedCredentialType",
        "nodeCredentialType": "supabaseApi",
        "sendHeaders": True,
        "headerParameters": {
            "parameters": extra_headers or [
                {"name": "Prefer", "value": "return=representation"}
            ]
        },
        "options": {},
    }
    if json_body:
        params["sendBody"] = True
        params["specifyBody"] = "json"
        params["jsonBody"] = json_body

    return {
        "parameters": params,
        "id": uid(),
        "name": name,
        "type": NODE_HTTP_REQUEST,
        "typeVersion": 4.2,
        "position": position,
        "credentials": {"supabaseApi": SUPABASE_CRED},
    }


def make_switch_condition(left_expr, right_value):
    """Create an n8n Switch v2 condition entry."""
    return {
        "id": uid(),
        "operator": {
            "name": "filter.operator.equals",
            "type": "string",
            "operation": "equals",
        },
        "leftValue": left_expr,
        "rightValue": right_value,
    }


def make_switch_rule(output_key, left_expr, right_value):
    """Create a complete Switch v2 rule (output with condition)."""
    return {
        "outputKey": output_key,
        "renameOutput": True,
        "conditions": {
            "options": {
                "version": 2,
                "leftValue": "",
                "caseSensitive": True,
                "typeValidation": "strict",
            },
            "combinator": "and",
            "conditions": [make_switch_condition(left_expr, right_value)],
        },
    }


def make_agent_trio(agent_name, suffix, system_prompt_expr, user_prompt_expr,
                    position, connections):
    """
    Create a Claude Agent + Anthropic Chat Model + People.ai MCP trio.
    Adds all three nodes and wires sub-node connections.
    Returns the list of 3 nodes.
    """
    model_name = f"Anthropic Chat Model ({suffix})"
    mcp_name = f"People.ai MCP ({suffix})"

    agent_node = {
        "parameters": {
            "promptType": "define",
            "text": user_prompt_expr,
            "options": {
                "systemMessage": system_prompt_expr,
                "maxIterations": 5,
            },
        },
        "id": uid(),
        "name": agent_name,
        "type": NODE_AGENT,
        "typeVersion": 1.7,
        "position": position,
        "continueOnFail": True,
    }

    model_node = {
        "parameters": {"model": {"__rl": True, "mode": "list", "value": MODEL_SONNET, "cachedResultName": "Claude Sonnet 4.5"}, "options": {}},
        "id": uid(),
        "name": model_name,
        "type": NODE_ANTHROPIC_CHAT,
        "typeVersion": 1.3,
        "position": [position[0] - 50, position[1] + 200],
        "credentials": {"anthropicApi": ANTHROPIC_CRED},
    }

    mcp_node = {
        "parameters": {
            "endpointUrl": PEOPLEAI_MCP_URL,
            "authentication": "multipleHeadersAuth",
            "options": {},
        },
        "id": uid(),
        "name": mcp_name,
        "type": NODE_MCP_CLIENT,
        "typeVersion": 1.2,
        "position": [position[0] + 150, position[1] + 200],
        "credentials": {"httpMultipleHeadersAuth": MCP_CRED},
    }

    # Wire sub-node connections
    connections[model_name] = {
        "ai_languageModel": [[{"node": agent_name, "type": "ai_languageModel", "index": 0}]]
    }
    connections[mcp_name] = {
        "ai_tool": [[{"node": agent_name, "type": "ai_tool", "index": 0}]]
    }

    return [agent_node, model_node, mcp_node]
