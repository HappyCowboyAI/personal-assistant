#!/usr/bin/env python3
"""
Add conversational DM support to Slack Events Handler.

When an onboarded user DMs the bot with unrecognized text (not a keyword command),
instead of showing help text, spin up a Claude agent with Backstory MCP tools.

Changes:
1. Insert "Is Conversational?" IF node between Switch Route output 7 and Build Help Response
   - subRoute === "unrecognized" → DM agent flow
   - other subRoutes (help, stop_digest, resume_digest) → Build Help Response (unchanged)
2. Add DM agent flow: Build Prompt → Post Thinking → Agent → Post Answer → Conversation Bookend
"""

import json
import os
import uuid
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

EVENTS_HANDLER_ID = "QuQbIaWetunUOFUW"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

SUPABASE_CRED = {"id": "ASRWWkQ0RSMOpNF1", "name": "Supabase account"}
ANTHROPIC_CRED = {"id": "rlAz7ZSl4y6AwRUq", "name": "Anthropic account 2"}
MCP_CRED = {"id": "wvV5pwBeIL7f2vLG", "name": "Backstory MCP Multi-Header"}
SLACK_CRED = {"id": "LluVuiMJ8NUbAiG7", "name": "Slackbot Auth Token"}
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


def main():
    print("Fetching Slack Events Handler workflow (live)...")
    wf = fetch_workflow(EVENTS_HANDLER_ID)
    nodes = wf["nodes"]
    connections = wf["connections"]
    print(f"  {len(nodes)} nodes")

    # --- Guard: check if already applied ---
    node_names = [n["name"] for n in nodes]
    if "Is Conversational?" in node_names:
        print("  'Is Conversational?' already exists — skipping")
        return

    print("\n=== Adding conversational DM support ===")

    # --- Node 1: Is Conversational? (IF) ---
    is_conv_id = uid()
    is_conv_node = {
        "parameters": {
            "conditions": {
                "options": {
                    "version": 2,
                    "leftValue": "",
                    "caseSensitive": True,
                    "typeValidation": "strict",
                },
                "conditions": [
                    {
                        "id": uid(),
                        "leftValue": "={{ $json.subRoute }}",
                        "rightValue": "unrecognized",
                        "operator": {
                            "type": "string",
                            "operation": "equals",
                        },
                    }
                ],
                "combinator": "and",
            },
            "options": {},
        },
        "id": is_conv_id,
        "name": "Is Conversational?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [2448, 2496],
    }
    nodes.append(is_conv_node)
    print(f"  Added 'Is Conversational?' (id={is_conv_id})")

    # --- Node 2: Build DM System Prompt (Code) ---
    build_prompt_code = r"""const routeData = $('Route by State').first().json;
const user = routeData.userRecord || {};

const assistantName = routeData.assistantName || 'Aria';
const assistantEmoji = routeData.assistantEmoji || ':robot_face:';
const assistantPersona = (user.assistant_persona) || 'direct, action-oriented, conversational';
const repName = user.name || 'there';

const systemPrompt = [
  'You are ' + assistantName + ', a personal sales assistant for ' + repName + '. You work exclusively for them.',
  '',
  'Your personality: ' + assistantPersona,
  '',
  'You have access to Backstory MCP tools which give you CRM data, account activity, opportunity details, engagement scores, and communication summaries.',
  '',
  '**INSTRUCTIONS:**',
  '- Use the Backstory MCP tools to answer the user\'s question with real data.',
  '- Be concise and actionable — this response will be posted in Slack.',
  '- Format your response using Slack markdown: *bold*, _italic_, `code`.',
  '- Use bullet points sparingly and keep them short.',
  '- If the question is about a specific account or opportunity, include key metrics (engagement level, amount, stage, etc.).',
  '- If you can\'t find the requested data, say so clearly rather than guessing.',
  '- Keep your total response under 3000 characters so it displays well in Slack.',
  '- Do NOT use headers with ### or ** section headers ** — just use *bold* for emphasis.',
  '- End with a brief actionable recommendation when relevant.',
  '',
  '**AVAILABLE COMMANDS:**',
  'If the user seems to be asking about settings or configuration rather than a sales question, let them know they can use these commands by typing them directly in this DM:',
  '- `rename <name>` — change assistant name',
  '- `emoji <emoji>` — change assistant emoji (e.g. emoji :star:)',
  '- `persona <description>` — change assistant personality',
  '- `scope my_deals|team_deals|top_pipeline` — change briefing scope',
  '- `focus retention|revenue|technical|executive` — change digest focus area',
  '- `brief` — get an on-demand digest (also: `brief risk`, `brief momentum`)',
  '- `insights` — pipeline analysis (also: `insights stalled`, `insights risk`)',
  '- `stop digest` / `resume digest` — toggle morning briefings',
  '- `help` — see the full command list',
  '',
  'Only mention these commands if they are relevant to what the user is asking about. Do not list all commands unprompted.',
].join('\n');

const thinkingText = assistantEmoji + ' ' + assistantName + '\n\n:hourglass_flowing_sand: Thinking...';

return [{
  json: {
    systemPrompt,
    userMessage: routeData.text,
    channelId: routeData.channelId,
    userId: routeData.userId,
    assistantName,
    assistantEmoji,
    thinkingText,
    dbUserId: routeData.dbUserId,
    organizationId: routeData.organizationId,
  }
}];
"""
    build_prompt_id = uid()
    build_prompt_node = {
        "parameters": {"jsCode": build_prompt_code},
        "id": build_prompt_id,
        "name": "Build DM System Prompt",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [2672, 4400],
    }
    nodes.append(build_prompt_node)
    print(f"  Added 'Build DM System Prompt' (id={build_prompt_id})")

    # --- Node 3: DM Post Thinking (HTTP Request → chat.postMessage) ---
    dm_thinking_id = uid()
    dm_thinking_node = {
        "parameters": {
            "method": "POST",
            "url": "https://slack.com/api/chat.postMessage",
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Content-Type", "value": "application/json"},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": '={{ JSON.stringify({ channel: $json.channelId, text: $json.thinkingText, username: $json.assistantName, icon_emoji: $json.assistantEmoji, unfurl_links: false, unfurl_media: false }) }}',
            "options": {},
        },
        "id": dm_thinking_id,
        "name": "DM Post Thinking",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [2896, 4400],
        "credentials": {"httpHeaderAuth": SLACK_CRED},
    }
    nodes.append(dm_thinking_node)
    print(f"  Added 'DM Post Thinking' (id={dm_thinking_id})")

    # --- Node 4: DM Conversation Agent ---
    dm_agent_id = uid()
    dm_agent_node = {
        "parameters": {
            "promptType": "define",
            "text": '={{ $("Build DM System Prompt").first().json.userMessage }}',
            "options": {
                "systemMessage": '={{ $("Build DM System Prompt").first().json.systemPrompt }}',
                "maxIterations": 10,
            },
        },
        "id": dm_agent_id,
        "name": "DM Conversation Agent",
        "type": "@n8n/n8n-nodes-langchain.agent",
        "typeVersion": 1.7,
        "position": [3120, 4400],
        "continueOnFail": True,
    }
    nodes.append(dm_agent_node)
    print(f"  Added 'DM Conversation Agent' (id={dm_agent_id})")

    # --- Node 5: Anthropic Chat Model (DM Conv) — sub-node ---
    dm_model_id = uid()
    dm_model_node = {
        "parameters": {
            "model": {
                "__rl": True,
                "mode": "list",
                "value": "claude-sonnet-4-5-20250929",
                "cachedResultName": "Claude Sonnet 4.5",
            },
            "options": {},
        },
        "id": dm_model_id,
        "name": "Anthropic Chat Model (DM Conv)",
        "type": "@n8n/n8n-nodes-langchain.lmChatAnthropic",
        "typeVersion": 1.3,
        "position": [3120, 4624],
        "credentials": {"anthropicApi": ANTHROPIC_CRED},
    }
    nodes.append(dm_model_node)
    print(f"  Added 'Anthropic Chat Model (DM Conv)' (id={dm_model_id})")

    # --- Node 6: Backstory MCP (DM Conv) — sub-node ---
    dm_mcp_id = uid()
    dm_mcp_node = {
        "parameters": {
            "endpointUrl": "https://mcp.people.ai/mcp",
            "authentication": "multipleHeadersAuth",
            "options": {},
        },
        "id": dm_mcp_id,
        "name": "Backstory MCP (DM Conv)",
        "type": "@n8n/n8n-nodes-langchain.mcpClientTool",
        "typeVersion": 1.2,
        "position": [3344, 4624],
        "credentials": {"httpMultipleHeadersAuth": MCP_CRED},
    }
    nodes.append(dm_mcp_node)
    print(f"  Added 'Backstory MCP (DM Conv)' (id={dm_mcp_id})")

    # --- Node 7: DM Post Answer (HTTP Request → chat.update) ---
    dm_answer_id = uid()
    dm_answer_body = (
        '={{ JSON.stringify({'
        ' channel: $("Build DM System Prompt").first().json.channelId,'
        ' ts: $("DM Post Thinking").first().json.ts,'
        ' text: $("Build DM System Prompt").first().json.assistantEmoji'
        ' + " " + $("Build DM System Prompt").first().json.assistantName'
        ' + "\\n\\n" + ($json.output || $json.text || "Sorry, I was unable to generate a response. Please try again.")'
        ' }) }}'
    )
    dm_answer_node = {
        "parameters": {
            "method": "POST",
            "url": "https://slack.com/api/chat.update",
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Content-Type", "value": "application/json"},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": dm_answer_body,
            "options": {},
        },
        "id": dm_answer_id,
        "name": "DM Post Answer",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [3568, 4400],
        "credentials": {"httpHeaderAuth": SLACK_CRED},
    }
    nodes.append(dm_answer_node)
    print(f"  Added 'DM Post Answer' (id={dm_answer_id})")

    # --- Node 8: Prepare DM Conv Data (Code) ---
    prepare_code = r"""const buildData = $('Build DM System Prompt').first().json;
const agentOutput = $('DM Conversation Agent').first().json.output || $('DM Conversation Agent').first().json.text || '';
const thinkingTs = $('DM Post Thinking').first().json.ts || '';

const agentConfig = {
  systemPrompt: buildData.systemPrompt,
  model: 'claude-sonnet-4-5-20250929',
  mcpEndpoint: 'https://mcp.people.ai/mcp',
  assistantName: buildData.assistantName,
  assistantEmoji: buildData.assistantEmoji,
};

const expiresAt = new Date(Date.now() + 4 * 60 * 60 * 1000).toISOString();

return [{
  json: {
    organizationId: buildData.organizationId,
    userId: buildData.dbUserId,
    channelId: buildData.channelId,
    threadTs: thinkingTs,
    workflowType: 'dm_conversation',
    agentConfig: agentConfig,
    expiresAt: expiresAt,
    userMessage: buildData.userMessage,
    assistantMessage: agentOutput,
  }
}];
"""
    prepare_id = uid()
    prepare_node = {
        "parameters": {"jsCode": prepare_code},
        "id": prepare_id,
        "name": "Prepare DM Conv Data",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [3792, 4400],
        "continueOnFail": True,
    }
    nodes.append(prepare_node)
    print(f"  Added 'Prepare DM Conv Data' (id={prepare_id})")

    # --- Node 9: Create DM Conversation (HTTP POST to Supabase) ---
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
        "name": "Create DM Conversation",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [4016, 4400],
        "credentials": {"supabaseApi": SUPABASE_CRED},
        "continueOnFail": True,
    }
    nodes.append(create_conv_node)
    print(f"  Added 'Create DM Conversation' (id={create_conv_id})")

    # --- Node 10: Log DM User Msg (HTTP POST to Supabase) ---
    log_user_id = uid()
    log_user_body = (
        '={{ JSON.stringify({\n'
        '  user_id: $("Prepare DM Conv Data").first().json.userId,\n'
        '  message_type: "conversation",\n'
        '  channel: "slack",\n'
        '  direction: "inbound",\n'
        '  content: $("Prepare DM Conv Data").first().json.userMessage,\n'
        '  conversation_id: $json.id,\n'
        '  slack_thread_ts: $("Prepare DM Conv Data").first().json.threadTs,\n'
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
        "name": "Log DM User Msg",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [4240, 4400],
        "credentials": {"supabaseApi": SUPABASE_CRED},
        "continueOnFail": True,
    }
    nodes.append(log_user_node)
    print(f"  Added 'Log DM User Msg' (id={log_user_id})")

    # --- Node 11: Log DM Assistant Msg (HTTP POST to Supabase) ---
    log_asst_id = uid()
    log_asst_body = (
        '={{ JSON.stringify({\n'
        '  user_id: $("Prepare DM Conv Data").first().json.userId,\n'
        '  message_type: "conversation",\n'
        '  channel: "slack",\n'
        '  direction: "outbound",\n'
        '  content: $("Prepare DM Conv Data").first().json.assistantMessage,\n'
        '  conversation_id: $("Create DM Conversation").first().json.id,\n'
        '  slack_thread_ts: $("Prepare DM Conv Data").first().json.threadTs,\n'
        '  role: "assistant"\n'
        '}) }}'
    )
    log_asst_node = {
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
            "jsonBody": log_asst_body,
            "options": {},
        },
        "id": log_asst_id,
        "name": "Log DM Assistant Msg",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [4464, 4400],
        "credentials": {"supabaseApi": SUPABASE_CRED},
        "continueOnFail": True,
    }
    nodes.append(log_asst_node)
    print(f"  Added 'Log DM Assistant Msg' (id={log_asst_id})")

    # --- Wiring ---
    print("\n=== Wiring connections ===")

    # 1. Rewire Switch Route output 7: Build Help Response → Is Conversational?
    switch_conns = connections["Switch Route"]["main"]
    switch_conns[7] = [{"node": "Is Conversational?", "type": "main", "index": 0}]
    print("  Rewired: Switch Route output 7 → Is Conversational?")

    # 2. Is Conversational? true → Build DM System Prompt, false → Build Help Response
    connections["Is Conversational?"] = {
        "main": [
            [{"node": "Build DM System Prompt", "type": "main", "index": 0}],
            [{"node": "Build Help Response", "type": "main", "index": 0}],
        ]
    }
    print("  Wired: Is Conversational? → true → Build DM System Prompt")
    print("  Wired: Is Conversational? → false → Build Help Response")

    # 3. Main chain: Build Prompt → Thinking → Agent → Answer → Bookend
    connections["Build DM System Prompt"] = {
        "main": [[{"node": "DM Post Thinking", "type": "main", "index": 0}]]
    }
    connections["DM Post Thinking"] = {
        "main": [[{"node": "DM Conversation Agent", "type": "main", "index": 0}]]
    }
    connections["DM Conversation Agent"] = {
        "main": [[{"node": "DM Post Answer", "type": "main", "index": 0}]]
    }
    connections["DM Post Answer"] = {
        "main": [[{"node": "Prepare DM Conv Data", "type": "main", "index": 0}]]
    }
    connections["Prepare DM Conv Data"] = {
        "main": [[{"node": "Create DM Conversation", "type": "main", "index": 0}]]
    }
    connections["Create DM Conversation"] = {
        "main": [[{"node": "Log DM User Msg", "type": "main", "index": 0}]]
    }
    connections["Log DM User Msg"] = {
        "main": [[{"node": "Log DM Assistant Msg", "type": "main", "index": 0}]]
    }
    print("  Wired: Build DM System Prompt → DM Post Thinking → DM Conversation Agent → DM Post Answer → Prepare DM Conv Data → Create DM Conversation → Log DM User Msg → Log DM Assistant Msg")

    # 4. Sub-node connections: Anthropic + MCP → Agent
    connections["Anthropic Chat Model (DM Conv)"] = {
        "ai_languageModel": [
            [{"node": "DM Conversation Agent", "type": "ai_languageModel", "index": 0}]
        ]
    }
    connections["Backstory MCP (DM Conv)"] = {
        "ai_tool": [
            [{"node": "DM Conversation Agent", "type": "ai_tool", "index": 0}]
        ]
    }
    print("  Wired: Anthropic Chat Model (DM Conv) → DM Conversation Agent (ai_languageModel)")
    print("  Wired: Backstory MCP (DM Conv) → DM Conversation Agent (ai_tool)")

    print(f"\n  Total nodes: {len(nodes)} (was {len(nodes) - 11})")

    # --- Push ---
    print("\n=== Pushing workflow ===")
    result = push_workflow(EVENTS_HANDLER_ID, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")

    # --- Sync ---
    print("\n=== Re-fetching and syncing local file ===")
    final = fetch_workflow(EVENTS_HANDLER_ID)
    sync_local(final, "Slack Events Handler.json")

    print("\nDone! DMs with unrecognized text now trigger the conversational agent.")
    print("Existing commands (rename, emoji, brief, help, etc.) still route to their handlers.")


if __name__ == "__main__":
    main()
