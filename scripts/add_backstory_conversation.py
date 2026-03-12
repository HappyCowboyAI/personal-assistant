#!/usr/bin/env python3
"""
Add conversation bookend to Backstory SlackBot workflow.

After the agent responds (on both Channel and DM paths), this adds nodes to:
1. Prepare Conversation Data (Code node) — assembles fields from upstream nodes
2. Create Conversation (HTTP POST to Supabase) — creates the conversation record
3. Log User Message (HTTP POST to Supabase) — logs user input (role='user')
4. Log Assistant Message (HTTP POST to Supabase) — logs agent output (role='assistant')

Both paths converge at one shared set of bookend nodes:
  Channel: Update Original Message → Prepare Conversation Data → Create Conversation → Log User Message → Log Assistant Message
  DM:      DM Post Answer1         → Prepare Conversation Data → Create Conversation → Log User Message → Log Assistant Message
"""

import json
import os
import uuid
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

BACKSTORY_WORKFLOW_ID = "Yg5GB1byqB0qD-5wVDOAn"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

SUPABASE_CRED = {"id": "ASRWWkQ0RSMOpNF1", "name": "Supabase account"}
SUPABASE_REST_URL = "https://rhrlnkbphxntxxxcrgvv.supabase.co/rest/v1"


def uid():
    return str(uuid.uuid4())


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
    resp = requests.put(
        f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}", headers=HEADERS, json=payload
    )
    resp.raise_for_status()
    return resp.json()


def sync_local(wf, filename):
    path = os.path.join(REPO_ROOT, "n8n", "workflows", filename)
    with open(path, "w") as f:
        json.dump(wf, f, indent=4)
    print(f"  Synced {path}")


def find_node(nodes, name):
    """Find a node by name, raise if not found."""
    for n in nodes:
        if n["name"] == name:
            return n
    raise ValueError(f"Node '{name}' not found in workflow")


def upgrade(wf):
    print("\n=== Adding conversation bookend to Backstory SlackBot ===")
    nodes = wf["nodes"]
    connections = wf["connections"]

    # --- Guard: check if already applied ---
    node_names = [n["name"] for n in nodes]
    if "Prepare Conversation Data" in node_names:
        print("  'Prepare Conversation Data' already exists — skipping")
        return wf

    # --- Identify terminal nodes for both paths ---
    # Channel path terminal: "Update Original Message" at [4608, 1960]
    # DM path terminal: "DM Post Answer1" at [4608, 2256]
    channel_terminal = find_node(nodes, "Update Original Message")
    dm_terminal = find_node(nodes, "DM Post Answer1")

    channel_term_pos = channel_terminal["position"]
    dm_term_pos = dm_terminal["position"]

    print(f"  Channel terminal: 'Update Original Message' at {channel_term_pos}")
    print(f"  DM terminal: 'DM Post Answer1' at {dm_term_pos}")

    # --- Position new nodes ---
    # Place the bookend chain to the right of both terminals.
    # Both terminals are at x=4608. New nodes start at x=4880,
    # centered vertically between the two paths (y ~2108, midpoint of 1960 and 2256).
    mid_y = (channel_term_pos[1] + dm_term_pos[1]) // 2  # 2108
    x_start = max(channel_term_pos[0], dm_term_pos[0]) + 280  # 4888

    pos_prepare = [x_start, mid_y]
    pos_create_conv = [x_start + 280, mid_y]
    pos_log_user = [x_start + 560, mid_y]
    pos_log_assistant = [x_start + 840, mid_y]

    print(f"  Positions: Prepare={pos_prepare}, CreateConv={pos_create_conv}, "
          f"LogUser={pos_log_user}, LogAssistant={pos_log_assistant}")

    # --- Node 1: Prepare Conversation Data (Code) ---
    # Uses try/catch to handle data from either Channel or DM path.
    # Key upstream nodes:
    #   - "Resolve Assistant Identity" — always available (shared before split)
    #   - "Extract Slash Command Data" — always available (shared before split)
    #   - "Lookup User" — always available (shared before split)
    #   - "Backstory Agent" — Channel path only
    #   - "Backstory Agent DM1" — DM path only
    #   - "Post Question to Channel" — Channel path only (has thread ts)
    #   - "DM Post Thinking1" — DM path only (has message ts)
    #   - "Open Bot DM" — DM path only (has channel.id for DM)
    prepare_code = r"""// Gather data for conversation record and message logging.
// This node is reached by BOTH Channel and DM paths, so we use
// try/catch to handle whichever upstream nodes are available.

const identity = $('Resolve Assistant Identity').first().json;
const extract = $('Extract Slash Command Data').first().json;
const user = $('Lookup User').first().json;

// Get agent output — try channel agent first, then DM agent
let agentOutput = '';
try { agentOutput = $('Backstory Agent').first().json.output || ''; } catch(e) {}
if (!agentOutput) {
  try { agentOutput = $('Backstory Agent DM1').first().json.output || ''; } catch(e) {}
}

// Get thread_ts — channel path uses Post Question to Channel ts,
// DM path uses DM Post Thinking1 ts
let threadTs = '';
try { threadTs = $('Post Question to Channel').first().json.ts || ''; } catch(e) {}
if (!threadTs) {
  try { threadTs = $('DM Post Thinking1').first().json.ts || ''; } catch(e) {}
}

// Get the channel ID — for DM path it's the opened DM channel, for channel path it's from extract
let channelId = extract.channelId || '';
try {
  const dmChannel = $('Open Bot DM').first().json.channel;
  if (dmChannel && dmChannel.id) channelId = dmChannel.id;
} catch(e) {
  // Channel path — use extract.channelId (already set)
}

// Build agent_config for the conversation record
const agentConfig = {
  systemPrompt: identity.systemPrompt,
  model: 'claude-sonnet-4-5-20250929',
  mcpEndpoint: 'https://mcp.people.ai/mcp',
  assistantName: identity.assistantName || 'Backstory',
  assistantEmoji: identity.assistantEmoji || ':robot_face:'
};

// Expiry: 4 hours from now
const expiresAt = new Date(Date.now() + 4 * 60 * 60 * 1000).toISOString();

return [{
  json: {
    organizationId: user.organization_id || null,
    userId: user.id || null,
    channelId: channelId,
    threadTs: threadTs,
    workflowType: 'backstory',
    agentConfig: agentConfig,
    expiresAt: expiresAt,
    userMessage: extract.commandText || '',
    assistantMessage: agentOutput
  }
}];
"""

    prepare_id = uid()
    prepare_node = {
        "parameters": {"jsCode": prepare_code},
        "id": prepare_id,
        "name": "Prepare Conversation Data",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": pos_prepare,
        "continueOnFail": True,
    }
    nodes.append(prepare_node)
    print(f"  Added 'Prepare Conversation Data' (id={prepare_id})")

    # --- Node 2: Create Conversation (HTTP POST) ---
    # Inserts into conversations table via Supabase REST API.
    # Returns the created row (Prefer: return=representation).
    create_conv_id = uid()
    create_conv_body = (
        '={{ JSON.stringify({\n'
        '  organization_id: $json.organizationId,\n'
        '  user_id: $json.userId,\n'
        '  slack_channel_id: $json.channelId,\n'
        '  slack_thread_ts: $json.threadTs,\n'
        '  workflow_type: $json.workflowType,\n'
        '  agent_config: $json.agentConfig,\n'
        '  status: "active",\n'
        '  expires_at: $json.expiresAt\n'
        '}) }}'
    )
    create_conv_node = {
        "parameters": {
            "method": "POST",
            "url": f"{SUPABASE_REST_URL}/conversations",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "supabaseApi",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Prefer", "value": "return=representation"},
                    {"name": "Content-Type", "value": "application/json"},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": create_conv_body,
            "options": {},
        },
        "id": create_conv_id,
        "name": "Create Conversation",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": pos_create_conv,
        "credentials": {"supabaseApi": SUPABASE_CRED},
        "continueOnFail": True,
    }
    nodes.append(create_conv_node)
    print(f"  Added 'Create Conversation' (id={create_conv_id})")

    # --- Node 3: Log User Message (HTTP POST) ---
    # Inserts user's slash command text as an inbound message.
    # Needs conversation_id from the Create Conversation response.
    log_user_id = uid()
    log_user_body = (
        '={{ JSON.stringify({\n'
        '  user_id: $("Prepare Conversation Data").first().json.userId,\n'
        '  message_type: "conversation",\n'
        '  channel: "slack",\n'
        '  direction: "inbound",\n'
        '  content: $("Prepare Conversation Data").first().json.userMessage,\n'
        '  conversation_id: $json.id,\n'
        '  slack_thread_ts: $("Prepare Conversation Data").first().json.threadTs,\n'
        '  role: "user"\n'
        '}) }}'
    )
    log_user_node = {
        "parameters": {
            "method": "POST",
            "url": f"{SUPABASE_REST_URL}/messages",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "supabaseApi",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Prefer", "value": "return=representation"},
                    {"name": "Content-Type", "value": "application/json"},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": log_user_body,
            "options": {},
        },
        "id": log_user_id,
        "name": "Log User Message",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": pos_log_user,
        "credentials": {"supabaseApi": SUPABASE_CRED},
        "continueOnFail": True,
    }
    nodes.append(log_user_node)
    print(f"  Added 'Log User Message' (id={log_user_id})")

    # --- Node 4: Log Assistant Message (HTTP POST) ---
    # Inserts agent output as an outbound message.
    # Needs conversation_id from the Create Conversation response (via cross-node ref).
    log_assistant_id = uid()
    log_assistant_body = (
        '={{ JSON.stringify({\n'
        '  user_id: $("Prepare Conversation Data").first().json.userId,\n'
        '  message_type: "conversation",\n'
        '  channel: "slack",\n'
        '  direction: "outbound",\n'
        '  content: $("Prepare Conversation Data").first().json.assistantMessage,\n'
        '  conversation_id: $("Create Conversation").first().json.id,\n'
        '  slack_thread_ts: $("Prepare Conversation Data").first().json.threadTs,\n'
        '  role: "assistant"\n'
        '}) }}'
    )
    log_assistant_node = {
        "parameters": {
            "method": "POST",
            "url": f"{SUPABASE_REST_URL}/messages",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "supabaseApi",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Prefer", "value": "return=representation"},
                    {"name": "Content-Type", "value": "application/json"},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": log_assistant_body,
            "options": {},
        },
        "id": log_assistant_id,
        "name": "Log Assistant Message",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": pos_log_assistant,
        "credentials": {"supabaseApi": SUPABASE_CRED},
        "continueOnFail": True,
    }
    nodes.append(log_assistant_node)
    print(f"  Added 'Log Assistant Message' (id={log_assistant_id})")

    # --- Wiring ---

    # Channel path: Update Original Message → Prepare Conversation Data
    # Current: Update Original Message has no outgoing connections (terminal).
    connections["Update Original Message"] = {
        "main": [
            [{"node": "Prepare Conversation Data", "type": "main", "index": 0}]
        ]
    }
    print("  Wired: Update Original Message → Prepare Conversation Data")

    # DM path: DM Post Answer1 → Prepare Conversation Data
    # Current: DM Post Answer1 has no outgoing connections (terminal).
    connections["DM Post Answer1"] = {
        "main": [
            [{"node": "Prepare Conversation Data", "type": "main", "index": 0}]
        ]
    }
    print("  Wired: DM Post Answer1 → Prepare Conversation Data")

    # Prepare Conversation Data → Create Conversation
    connections["Prepare Conversation Data"] = {
        "main": [
            [{"node": "Create Conversation", "type": "main", "index": 0}]
        ]
    }
    print("  Wired: Prepare Conversation Data → Create Conversation")

    # Create Conversation → Log User Message
    connections["Create Conversation"] = {
        "main": [
            [{"node": "Log User Message", "type": "main", "index": 0}]
        ]
    }
    print("  Wired: Create Conversation → Log User Message")

    # Log User Message → Log Assistant Message
    connections["Log User Message"] = {
        "main": [
            [{"node": "Log Assistant Message", "type": "main", "index": 0}]
        ]
    }
    print("  Wired: Log User Message → Log Assistant Message")

    # Log Assistant Message is the new terminal node (no outgoing connections).

    print(f"\n  Total nodes: {len(nodes)} (was {len(nodes) - 4})")
    return wf


def main():
    print("Fetching Backstory SlackBot workflow (live)...")
    wf = fetch_workflow(BACKSTORY_WORKFLOW_ID)
    print(f"  {len(wf['nodes'])} nodes, {len(wf['connections'])} connection groups")

    wf = upgrade(wf)

    print("\n=== Pushing workflow ===")
    result = push_workflow(BACKSTORY_WORKFLOW_ID, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")

    print("\n=== Re-fetching and syncing local file ===")
    final = fetch_workflow(BACKSTORY_WORKFLOW_ID)
    sync_local(final, "Backstory SlackBot.json")

    print("\nDone! Backstory SlackBot now creates conversation records and logs messages.")


if __name__ == "__main__":
    main()
