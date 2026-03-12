#!/usr/bin/env python3
"""
Add conversation bookend nodes to three remaining workflows:
1. Sales Digest (7sinwSgjkEA40zDj) — workflow_type: 'digest'
2. On-Demand Digest (vxGajBdXFBaOCdkG) — workflow_type: 'on_demand_digest'
3. Meeting Brief (Cj4HcHfbzy9OZhwE) — workflow_type: 'meeting_prep'

Each workflow gets 4 bookend nodes appended after its final Slack posting node:
  Prepare *Workflow* Conversation Data (Code) → Create *Workflow* Conversation (HTTP POST)
    → Log *Workflow* User Message (HTTP POST) → Log *Workflow* Assistant Message (HTTP POST)

Pattern mirrors add_backstory_conversation.py (Task 4).
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

# Workflow IDs
SALES_DIGEST_ID = "7sinwSgjkEA40zDj"
ON_DEMAND_DIGEST_ID = "vxGajBdXFBaOCdkG"
MEETING_BRIEF_ID = "Cj4HcHfbzy9OZhwE"

# Local filenames for syncing
LOCAL_FILES = {
    SALES_DIGEST_ID: "Sales Digest.json",
    ON_DEMAND_DIGEST_ID: "On-Demand Digest.json",
    MEETING_BRIEF_ID: "Meeting Brief.json",
}


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


def make_http_post_node(node_id, name, position, url, json_body):
    """Create a standard HTTP POST node for Supabase REST inserts."""
    return {
        "parameters": {
            "method": "POST",
            "url": url,
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
            "jsonBody": json_body,
            "options": {},
        },
        "id": node_id,
        "name": name,
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": position,
        "credentials": {"supabaseApi": SUPABASE_CRED},
        "continueOnFail": True,
    }


def wire_chain(connections, node_names):
    """Wire a list of node names in sequence: A → B → C → D."""
    for i in range(len(node_names) - 1):
        src = node_names[i]
        dst = node_names[i + 1]
        connections[src] = {
            "main": [[{"node": dst, "type": "main", "index": 0}]]
        }


# ---------------------------------------------------------------------------
# 1. SALES DIGEST
# ---------------------------------------------------------------------------
def upgrade_sales_digest(wf):
    """
    Sales Digest loop body:
      Split In Batches [1] → Filter User Opps → Resolve Identity → Open Bot DM
        → Digest Agent → Parse Blocks → Send Digest → Prepare Message Log
        → Log to Messages → [back to Split In Batches]

    Insert bookend between "Log to Messages" and the loop-back to
    "Split In Batches":
      Log to Messages → Prepare Digest Conversation Data
        → Create Digest Conversation → Log Digest User Message
        → Log Digest Assistant Message → Split In Batches

    Key data sources:
      - Resolve Identity: userId, slackUserId, assistantName, assistantEmoji,
                          systemPrompt, repName, digestScope, theme
      - Open Bot DM:      channel.id (DM channel)
      - Send Digest:      ts (Slack message timestamp), channel
      - Digest Agent:     output (agent response text)
      - Filter User Opps: userEmail (for fallback identification)
      - Workflow Input Trigger / Split In Batches input: full user record

    NOTE: In Sales Digest, Filter User Opps does NOT spread the original user
    object, so user.id and user.organization_id are missing from its output.
    Resolve Identity derives userId from that (so it may be undefined).
    We use $('Resolve Identity') for what it has and fall back to
    $('Prepare Message Log') / $input for user_id from the Log to Messages
    Supabase insert response.
    """
    print("\n=== Adding conversation bookend to Sales Digest ===")
    nodes = wf["nodes"]
    connections = wf["connections"]

    # --- Guard ---
    node_names = [n["name"] for n in nodes]
    if "Prepare Digest Conversation Data" in node_names:
        print("  'Prepare Digest Conversation Data' already exists — skipping")
        return wf

    # --- Identify anchor nodes ---
    log_to_messages = find_node(nodes, "Log to Messages")
    log_pos = log_to_messages["position"]
    split_in_batches = find_node(nodes, "Split In Batches")

    print(f"  Log to Messages position: {log_pos}")
    print(f"  Current loop-back: Log to Messages → Split In Batches")

    # --- Positions: extend rightward from Log to Messages ---
    # Log to Messages is at [3920, 524].  New nodes go to the right.
    x_start = log_pos[0] + 280  # 4200
    y = log_pos[1]  # 524

    pos_prepare = [x_start, y]
    pos_create = [x_start + 280, y]
    pos_log_user = [x_start + 560, y]
    pos_log_asst = [x_start + 840, y]

    print(f"  Positions: Prepare={pos_prepare}, Create={pos_create}, "
          f"LogUser={pos_log_user}, LogAsst={pos_log_asst}")

    # --- Node 1: Prepare Digest Conversation Data ---
    prepare_code = r"""// Gather data for conversation bookend (Sales Digest).
// Runs inside the SplitInBatches loop after Log to Messages.

const identity = $('Resolve Identity').first().json;
const sendResult = $('Send Digest').first().json;
const agentOutput = $('Digest Agent').first().json.output || '';
const filterData = $('Filter User Opps').first().json;

// userId / organizationId: Resolve Identity outputs these but they may be
// undefined because Filter User Opps doesn't spread the original user record.
// Fall back to the Log to Messages Supabase response which echoes user_id.
let userId = identity.userId || null;
let organizationId = null;
try {
  // Log to Messages inserts into messages table — its response has user_id
  const logResp = $('Log to Messages').first().json;
  if (!userId && logResp.user_id) userId = logResp.user_id;
} catch(e) {}

// Channel and thread_ts from the Send Digest Slack response
const channelId = sendResult.channel || '';
const threadTs = sendResult.ts || '';

const agentConfig = {
  model: 'claude-sonnet-4-5-20250929',
  mcpEndpoint: 'https://mcp-canary.people.ai/mcp',
  assistantName: identity.assistantName || 'Aria',
  assistantEmoji: identity.assistantEmoji || ':robot_face:',
  digestScope: identity.digestScope || 'my_deals',
  theme: identity.theme || 'full_pipeline'
};

// Digest conversations expire after 4 hours (not continuable, but recorded)
const expiresAt = new Date(Date.now() + 4 * 60 * 60 * 1000).toISOString();

return [{
  json: {
    organizationId: organizationId,
    userId: userId,
    channelId: channelId,
    threadTs: threadTs,
    workflowType: 'digest',
    agentConfig: agentConfig,
    expiresAt: expiresAt,
    userMessage: 'Daily digest',
    assistantMessage: agentOutput
  }
}];
"""

    prepare_id = uid()
    prepare_node = {
        "parameters": {"jsCode": prepare_code},
        "id": prepare_id,
        "name": "Prepare Digest Conversation Data",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": pos_prepare,
        "continueOnFail": True,
    }
    nodes.append(prepare_node)
    print(f"  Added 'Prepare Digest Conversation Data' (id={prepare_id})")

    # --- Node 2: Create Digest Conversation ---
    create_id = uid()
    create_body = (
        '={{ JSON.stringify({\n'
        '  organization_id: $json.organizationId,\n'
        '  user_id: $json.userId,\n'
        '  slack_channel_id: $json.channelId,\n'
        '  slack_thread_ts: $json.threadTs,\n'
        '  workflow_type: $json.workflowType,\n'
        '  agent_config: $json.agentConfig,\n'
        '  status: "completed",\n'
        '  expires_at: $json.expiresAt\n'
        '}) }}'
    )
    create_node = make_http_post_node(
        create_id, "Create Digest Conversation", pos_create,
        f"{SUPABASE_REST_URL}/conversations", create_body
    )
    nodes.append(create_node)
    print(f"  Added 'Create Digest Conversation' (id={create_id})")

    # --- Node 3: Log Digest User Message ---
    log_user_id = uid()
    log_user_body = (
        '={{ JSON.stringify({\n'
        '  user_id: $("Prepare Digest Conversation Data").first().json.userId,\n'
        '  message_type: "conversation",\n'
        '  channel: "slack",\n'
        '  direction: "inbound",\n'
        '  content: $("Prepare Digest Conversation Data").first().json.userMessage,\n'
        '  conversation_id: $json.id,\n'
        '  slack_thread_ts: $("Prepare Digest Conversation Data").first().json.threadTs,\n'
        '  role: "user"\n'
        '}) }}'
    )
    log_user_node = make_http_post_node(
        log_user_id, "Log Digest User Message", pos_log_user,
        f"{SUPABASE_REST_URL}/messages", log_user_body
    )
    nodes.append(log_user_node)
    print(f"  Added 'Log Digest User Message' (id={log_user_id})")

    # --- Node 4: Log Digest Assistant Message ---
    log_asst_id = uid()
    log_asst_body = (
        '={{ JSON.stringify({\n'
        '  user_id: $("Prepare Digest Conversation Data").first().json.userId,\n'
        '  message_type: "conversation",\n'
        '  channel: "slack",\n'
        '  direction: "outbound",\n'
        '  content: $("Prepare Digest Conversation Data").first().json.assistantMessage,\n'
        '  conversation_id: $("Create Digest Conversation").first().json.id,\n'
        '  slack_thread_ts: $("Prepare Digest Conversation Data").first().json.threadTs,\n'
        '  role: "assistant"\n'
        '}) }}'
    )
    log_asst_node = make_http_post_node(
        log_asst_id, "Log Digest Assistant Message", pos_log_asst,
        f"{SUPABASE_REST_URL}/messages", log_asst_body
    )
    nodes.append(log_asst_node)
    print(f"  Added 'Log Digest Assistant Message' (id={log_asst_id})")

    # --- Wiring ---
    # Current: Log to Messages → Split In Batches (loop back)
    # New:     Log to Messages → Prepare Digest Conversation Data
    #            → Create Digest Conversation → Log Digest User Message
    #            → Log Digest Assistant Message → Split In Batches (loop back)

    # Rewire Log to Messages to point to our new chain instead of Split In Batches
    connections["Log to Messages"] = {
        "main": [
            [{"node": "Prepare Digest Conversation Data", "type": "main", "index": 0}]
        ]
    }
    print("  Wired: Log to Messages → Prepare Digest Conversation Data")

    wire_chain(connections, [
        "Prepare Digest Conversation Data",
        "Create Digest Conversation",
        "Log Digest User Message",
        "Log Digest Assistant Message",
    ])
    print("  Wired: Prepare → Create → LogUser → LogAssistant")

    # Log Digest Assistant Message loops back to Split In Batches
    connections["Log Digest Assistant Message"] = {
        "main": [
            [{"node": "Split In Batches", "type": "main", "index": 0}]
        ]
    }
    print("  Wired: Log Digest Assistant Message → Split In Batches (loop back)")

    print(f"\n  Total nodes: {len(nodes)} (was {len(nodes) - 4})")
    return wf


# ---------------------------------------------------------------------------
# 2. ON-DEMAND DIGEST
# ---------------------------------------------------------------------------
def upgrade_on_demand_digest(wf):
    """
    On-Demand Digest flow (sub-workflow, no loop):
      Workflow Input Trigger → Get Auth Token → Fetch User Hierarchy
        → Parse Hierarchy → Build Opp Query → Fetch Open Opps → Parse Opps CSV
        → Filter User Opps → Resolve Identity → Digest Agent → Parse Blocks
        → Send Digest  (terminal — no outgoing connections)

    Insert bookend after Send Digest:
      Send Digest → Prepare On-Demand Conversation Data
        → Create On-Demand Conversation → Log On-Demand User Message
        → Log On-Demand Assistant Message

    Key data sources:
      - Workflow Input Trigger: full user record (id, organization_id, email,
                                slack_user_id, channelId, etc.)
      - Filter User Opps:      ...user spread + oppTable, repName, etc.
      - Resolve Identity:      userId, slackUserId, assistantName, assistantEmoji,
                               systemPrompt, repName, digestScope, theme
      - Send Digest:           ts, channel (Slack response)
      - Digest Agent:          output

    The On-Demand Digest's Filter User Opps DOES spread the Workflow Input
    Trigger user record (...user), so Resolve Identity has valid userId.
    """
    print("\n=== Adding conversation bookend to On-Demand Digest ===")
    nodes = wf["nodes"]
    connections = wf["connections"]

    # --- Guard ---
    node_names = [n["name"] for n in nodes]
    if "Prepare On-Demand Conversation Data" in node_names:
        print("  'Prepare On-Demand Conversation Data' already exists — skipping")
        return wf

    # --- Identify terminal node ---
    send_digest = find_node(nodes, "Send Digest")
    send_pos = send_digest["position"]  # [2800, 400]

    print(f"  Terminal node: 'Send Digest' at {send_pos}")

    # --- Positions ---
    x_start = send_pos[0] + 280  # 3080
    y = send_pos[1]  # 400

    pos_prepare = [x_start, y]
    pos_create = [x_start + 280, y]
    pos_log_user = [x_start + 560, y]
    pos_log_asst = [x_start + 840, y]

    print(f"  Positions: Prepare={pos_prepare}, Create={pos_create}, "
          f"LogUser={pos_log_user}, LogAsst={pos_log_asst}")

    # --- Node 1: Prepare On-Demand Conversation Data ---
    prepare_code = r"""// Gather data for conversation bookend (On-Demand Digest).

const identity = $('Resolve Identity').first().json;
const sendResult = $('Send Digest').first().json;
const agentOutput = $('Digest Agent').first().json.output || '';
const inputData = $('Workflow Input Trigger').first().json;

// userId and organizationId — Resolve Identity has userId (from Filter User
// Opps which spreads the full user record). Organization ID from the input.
const userId = identity.userId || inputData.id || null;
const organizationId = inputData.organization_id || null;

// Channel and thread_ts from the Send Digest Slack response
const channelId = sendResult.channel || inputData.channelId || '';
const threadTs = sendResult.ts || '';

const agentConfig = {
  model: 'claude-sonnet-4-5-20250929',
  mcpEndpoint: 'https://mcp-canary.people.ai/mcp',
  assistantName: identity.assistantName || 'Aria',
  assistantEmoji: identity.assistantEmoji || ':robot_face:',
  digestScope: identity.digestScope || 'my_deals',
  theme: identity.theme || 'full_pipeline'
};

// On-demand digests expire after 4 hours
const expiresAt = new Date(Date.now() + 4 * 60 * 60 * 1000).toISOString();

// The "user message" is the on-demand trigger — capture any theme override
const themeOverride = inputData.themeOverride || '';
const userMessage = themeOverride
  ? 'On-demand digest (theme: ' + themeOverride + ')'
  : 'On-demand digest';

return [{
  json: {
    organizationId: organizationId,
    userId: userId,
    channelId: channelId,
    threadTs: threadTs,
    workflowType: 'on_demand_digest',
    agentConfig: agentConfig,
    expiresAt: expiresAt,
    userMessage: userMessage,
    assistantMessage: agentOutput
  }
}];
"""

    prepare_id = uid()
    prepare_node = {
        "parameters": {"jsCode": prepare_code},
        "id": prepare_id,
        "name": "Prepare On-Demand Conversation Data",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": pos_prepare,
        "continueOnFail": True,
    }
    nodes.append(prepare_node)
    print(f"  Added 'Prepare On-Demand Conversation Data' (id={prepare_id})")

    # --- Node 2: Create On-Demand Conversation ---
    create_id = uid()
    create_body = (
        '={{ JSON.stringify({\n'
        '  organization_id: $json.organizationId,\n'
        '  user_id: $json.userId,\n'
        '  slack_channel_id: $json.channelId,\n'
        '  slack_thread_ts: $json.threadTs,\n'
        '  workflow_type: $json.workflowType,\n'
        '  agent_config: $json.agentConfig,\n'
        '  status: "completed",\n'
        '  expires_at: $json.expiresAt\n'
        '}) }}'
    )
    create_node = make_http_post_node(
        create_id, "Create On-Demand Conversation", pos_create,
        f"{SUPABASE_REST_URL}/conversations", create_body
    )
    nodes.append(create_node)
    print(f"  Added 'Create On-Demand Conversation' (id={create_id})")

    # --- Node 3: Log On-Demand User Message ---
    log_user_id = uid()
    log_user_body = (
        '={{ JSON.stringify({\n'
        '  user_id: $("Prepare On-Demand Conversation Data").first().json.userId,\n'
        '  message_type: "conversation",\n'
        '  channel: "slack",\n'
        '  direction: "inbound",\n'
        '  content: $("Prepare On-Demand Conversation Data").first().json.userMessage,\n'
        '  conversation_id: $json.id,\n'
        '  slack_thread_ts: $("Prepare On-Demand Conversation Data").first().json.threadTs,\n'
        '  role: "user"\n'
        '}) }}'
    )
    log_user_node = make_http_post_node(
        log_user_id, "Log On-Demand User Message", pos_log_user,
        f"{SUPABASE_REST_URL}/messages", log_user_body
    )
    nodes.append(log_user_node)
    print(f"  Added 'Log On-Demand User Message' (id={log_user_id})")

    # --- Node 4: Log On-Demand Assistant Message ---
    log_asst_id = uid()
    log_asst_body = (
        '={{ JSON.stringify({\n'
        '  user_id: $("Prepare On-Demand Conversation Data").first().json.userId,\n'
        '  message_type: "conversation",\n'
        '  channel: "slack",\n'
        '  direction: "outbound",\n'
        '  content: $("Prepare On-Demand Conversation Data").first().json.assistantMessage,\n'
        '  conversation_id: $("Create On-Demand Conversation").first().json.id,\n'
        '  slack_thread_ts: $("Prepare On-Demand Conversation Data").first().json.threadTs,\n'
        '  role: "assistant"\n'
        '}) }}'
    )
    log_asst_node = make_http_post_node(
        log_asst_id, "Log On-Demand Assistant Message", pos_log_asst,
        f"{SUPABASE_REST_URL}/messages", log_asst_body
    )
    nodes.append(log_asst_node)
    print(f"  Added 'Log On-Demand Assistant Message' (id={log_asst_id})")

    # --- Wiring ---
    # Send Digest (terminal) → new chain
    connections["Send Digest"] = {
        "main": [
            [{"node": "Prepare On-Demand Conversation Data", "type": "main", "index": 0}]
        ]
    }
    print("  Wired: Send Digest → Prepare On-Demand Conversation Data")

    wire_chain(connections, [
        "Prepare On-Demand Conversation Data",
        "Create On-Demand Conversation",
        "Log On-Demand User Message",
        "Log On-Demand Assistant Message",
    ])
    print("  Wired: Prepare → Create → LogUser → LogAssistant")

    print(f"\n  Total nodes: {len(nodes)} (was {len(nodes) - 4})")
    return wf


# ---------------------------------------------------------------------------
# 3. MEETING BRIEF
# ---------------------------------------------------------------------------
def upgrade_meeting_brief(wf):
    """
    Meeting Brief flow (sub-workflow, no loop):
      Workflow Input Trigger → Open Bot DM → Set Channel ID
        → Resolve Meeting Identity → Meeting Brief Agent → Parse Blocks
        → Send Meeting Brief  (terminal — no outgoing connections)

    Insert bookend after Send Meeting Brief:
      Send Meeting Brief → Prepare Meeting Brief Conversation Data
        → Create Meeting Brief Conversation → Log Meeting Brief User Message
        → Log Meeting Brief Assistant Message

    Key data sources:
      - Workflow Input Trigger:    full user record (userId, slackUserId,
                                   organization_id, email, accountName,
                                   meetingSubject, participants, etc.)
      - Resolve Meeting Identity:  userId, slackUserId, channelId,
                                   assistantName, assistantEmoji, repName,
                                   accountName, systemPrompt, agentPrompt
      - Send Meeting Brief:        ts, channel (Slack response)
      - Meeting Brief Agent:       output
    """
    print("\n=== Adding conversation bookend to Meeting Brief ===")
    nodes = wf["nodes"]
    connections = wf["connections"]

    # --- Guard ---
    node_names = [n["name"] for n in nodes]
    if "Prepare Meeting Brief Conversation Data" in node_names:
        print("  'Prepare Meeting Brief Conversation Data' already exists — skipping")
        return wf

    # --- Identify terminal node ---
    send_brief = find_node(nodes, "Send Meeting Brief")
    send_pos = send_brief["position"]  # [1520, 400]

    print(f"  Terminal node: 'Send Meeting Brief' at {send_pos}")

    # --- Positions ---
    x_start = send_pos[0] + 280  # 1800
    y = send_pos[1]  # 400

    pos_prepare = [x_start, y]
    pos_create = [x_start + 280, y]
    pos_log_user = [x_start + 560, y]
    pos_log_asst = [x_start + 840, y]

    print(f"  Positions: Prepare={pos_prepare}, Create={pos_create}, "
          f"LogUser={pos_log_user}, LogAsst={pos_log_asst}")

    # --- Node 1: Prepare Meeting Brief Conversation Data ---
    prepare_code = r"""// Gather data for conversation bookend (Meeting Brief).

const identity = $('Resolve Meeting Identity').first().json;
const sendResult = $('Send Meeting Brief').first().json;
const agentOutput = $('Meeting Brief Agent').first().json.output || '';
const inputData = $('Workflow Input Trigger').first().json;

// userId and organizationId from input and Resolve Meeting Identity
const userId = identity.userId || inputData.userId || null;
const organizationId = inputData.organization_id || null;

// Channel and thread_ts from the Slack response
const channelId = sendResult.channel || identity.channelId || '';
const threadTs = sendResult.ts || '';

const agentConfig = {
  model: 'claude-sonnet-4-5-20250929',
  mcpEndpoint: 'https://mcp.people.ai/mcp',
  assistantName: identity.assistantName || 'Aria',
  assistantEmoji: identity.assistantEmoji || ':robot_face:',
  accountName: identity.accountName || ''
};

// Meeting brief conversations expire after 4 hours
const expiresAt = new Date(Date.now() + 4 * 60 * 60 * 1000).toISOString();

// User message = meeting context (what triggered the brief)
const meetingSubject = inputData.meetingSubject || 'Customer Meeting';
const accountName = inputData.accountName || identity.accountName || 'Unknown';
const participants = inputData.participants || '';
const userMessage = 'Meeting prep: ' + meetingSubject + ' with ' + accountName
  + (participants ? ' (' + participants + ')' : '');

return [{
  json: {
    organizationId: organizationId,
    userId: userId,
    channelId: channelId,
    threadTs: threadTs,
    workflowType: 'meeting_prep',
    agentConfig: agentConfig,
    expiresAt: expiresAt,
    userMessage: userMessage,
    assistantMessage: agentOutput
  }
}];
"""

    prepare_id = uid()
    prepare_node = {
        "parameters": {"jsCode": prepare_code},
        "id": prepare_id,
        "name": "Prepare Meeting Brief Conversation Data",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": pos_prepare,
        "continueOnFail": True,
    }
    nodes.append(prepare_node)
    print(f"  Added 'Prepare Meeting Brief Conversation Data' (id={prepare_id})")

    # --- Node 2: Create Meeting Brief Conversation ---
    create_id = uid()
    create_body = (
        '={{ JSON.stringify({\n'
        '  organization_id: $json.organizationId,\n'
        '  user_id: $json.userId,\n'
        '  slack_channel_id: $json.channelId,\n'
        '  slack_thread_ts: $json.threadTs,\n'
        '  workflow_type: $json.workflowType,\n'
        '  agent_config: $json.agentConfig,\n'
        '  status: "completed",\n'
        '  expires_at: $json.expiresAt\n'
        '}) }}'
    )
    create_node = make_http_post_node(
        create_id, "Create Meeting Brief Conversation", pos_create,
        f"{SUPABASE_REST_URL}/conversations", create_body
    )
    nodes.append(create_node)
    print(f"  Added 'Create Meeting Brief Conversation' (id={create_id})")

    # --- Node 3: Log Meeting Brief User Message ---
    log_user_id = uid()
    log_user_body = (
        '={{ JSON.stringify({\n'
        '  user_id: $("Prepare Meeting Brief Conversation Data").first().json.userId,\n'
        '  message_type: "conversation",\n'
        '  channel: "slack",\n'
        '  direction: "inbound",\n'
        '  content: $("Prepare Meeting Brief Conversation Data").first().json.userMessage,\n'
        '  conversation_id: $json.id,\n'
        '  slack_thread_ts: $("Prepare Meeting Brief Conversation Data").first().json.threadTs,\n'
        '  role: "user"\n'
        '}) }}'
    )
    log_user_node = make_http_post_node(
        log_user_id, "Log Meeting Brief User Message", pos_log_user,
        f"{SUPABASE_REST_URL}/messages", log_user_body
    )
    nodes.append(log_user_node)
    print(f"  Added 'Log Meeting Brief User Message' (id={log_user_id})")

    # --- Node 4: Log Meeting Brief Assistant Message ---
    log_asst_id = uid()
    log_asst_body = (
        '={{ JSON.stringify({\n'
        '  user_id: $("Prepare Meeting Brief Conversation Data").first().json.userId,\n'
        '  message_type: "conversation",\n'
        '  channel: "slack",\n'
        '  direction: "outbound",\n'
        '  content: $("Prepare Meeting Brief Conversation Data").first().json.assistantMessage,\n'
        '  conversation_id: $("Create Meeting Brief Conversation").first().json.id,\n'
        '  slack_thread_ts: $("Prepare Meeting Brief Conversation Data").first().json.threadTs,\n'
        '  role: "assistant"\n'
        '}) }}'
    )
    log_asst_node = make_http_post_node(
        log_asst_id, "Log Meeting Brief Assistant Message", pos_log_asst,
        f"{SUPABASE_REST_URL}/messages", log_asst_body
    )
    nodes.append(log_asst_node)
    print(f"  Added 'Log Meeting Brief Assistant Message' (id={log_asst_id})")

    # --- Wiring ---
    # Send Meeting Brief (terminal) → new chain
    connections["Send Meeting Brief"] = {
        "main": [
            [{"node": "Prepare Meeting Brief Conversation Data", "type": "main", "index": 0}]
        ]
    }
    print("  Wired: Send Meeting Brief → Prepare Meeting Brief Conversation Data")

    wire_chain(connections, [
        "Prepare Meeting Brief Conversation Data",
        "Create Meeting Brief Conversation",
        "Log Meeting Brief User Message",
        "Log Meeting Brief Assistant Message",
    ])
    print("  Wired: Prepare → Create → LogUser → LogAssistant")

    print(f"\n  Total nodes: {len(nodes)} (was {len(nodes) - 4})")
    return wf


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    workflows = [
        (SALES_DIGEST_ID, "Sales Digest", upgrade_sales_digest),
        (ON_DEMAND_DIGEST_ID, "On-Demand Digest", upgrade_on_demand_digest),
        (MEETING_BRIEF_ID, "Meeting Brief", upgrade_meeting_brief),
    ]

    for wf_id, name, upgrade_fn in workflows:
        print(f"\nFetching {name} workflow (live)...")
        wf = fetch_workflow(wf_id)
        print(f"  {len(wf['nodes'])} nodes, {len(wf['connections'])} connection groups")

        wf = upgrade_fn(wf)

        print(f"\n=== Pushing {name} workflow ===")
        result = push_workflow(wf_id, wf)
        print(f"  HTTP 200, {len(result['nodes'])} nodes")

        print(f"\n=== Re-fetching and syncing {name} local file ===")
        final = fetch_workflow(wf_id)
        local_file = LOCAL_FILES.get(wf_id)
        if local_file:
            sync_local(final, local_file)

    print("\nDone! All three workflows now create conversation records and log messages.")


if __name__ == "__main__":
    main()
