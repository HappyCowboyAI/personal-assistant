#!/usr/bin/env python3
"""
Create: "Continue Conversation" sub-workflow.

Centralized engine for multi-turn conversation follow-ups.
Called by the Slack Events Handler when a user replies in a thread with an
active conversation. Loads history from Supabase, re-invokes the correct
agent with full context, and posts the response back to the same thread.

Nodes:
 1. Execute Workflow Trigger  — receives channelId, threadTs, userId, messageText, conversationId, slackUserName
 2. Load Conversation         — HTTP GET Supabase REST: conversations?id=eq.{conversationId}
 3. Check Limits              — Code: validates status, turn_count < max_turns, not expired
 4. Set Processing            — HTTP PATCH Supabase REST: status='processing'
 5. Load History              — HTTP GET Supabase REST: messages?conversation_id=eq.{conversationId}&order=sent_at.asc
 6. Log Inbound               — HTTP POST Supabase REST: insert message role='user'
 7. Build Agent Context       — Code: reconstructs message array, token budget, system prompt
 8. Conversation Agent        — Anthropic Tools Agent with dynamic system prompt
 9. Backstory MCP Tool        — MCP tool sub-node connected to the agent
10. Post Response             — HTTP POST Slack chat.postMessage with thread_ts
11. Log Outbound              — HTTP POST Supabase REST: insert message role='assistant'
12. Update Conversation       — HTTP PATCH Supabase REST: increment turn_count, slide expires_at

Error path: Check Limits → Post Error to Slack (if expired / max turns / processing)
"""

import json
import os
import uuid
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

# Credential IDs from live n8n
SUPABASE_CRED = {"id": "ASRWWkQ0RSMOpNF1", "name": "Supabase account"}
SLACK_CRED = {"id": "LluVuiMJ8NUbAiG7", "name": "Slackbot Auth Token"}
ANTHROPIC_CRED = {"id": "rlAz7ZSl4y6AwRUq", "name": "Anthropic account 2"}
MCP_CRED = {"id": "wvV5pwBeIL7f2vLG", "name": "Backstory MCP Multi-Header"}

SUPABASE_REST_URL = "https://rhrlnkbphxntxxxcrgvv.supabase.co/rest/v1"


def uid():
    return str(uuid.uuid4())


# ============================================================
# Code node: Check Limits
# ============================================================
CHECK_LIMITS_CODE = r"""const conversation = $('Load Conversation').first().json;
const now = new Date();
const expiresAt = new Date(conversation.expires_at);

if (expiresAt < now) {
  return [{ json: { error: true, errorMessage: 'This conversation has expired. Please start a new request.' } }];
}
if (conversation.turn_count >= conversation.max_turns) {
  return [{ json: { error: true, errorMessage: 'This thread has reached its limit. Please start a new request for further help.' } }];
}
if (conversation.status === 'processing') {
  return [{ json: { error: true, errorMessage: "I'm still working on your last message \u2014 one moment!" } }];
}
return [{ json: { error: false, conversationId: conversation.id } }];
"""

# ============================================================
# Code node: Build Agent Context
# ============================================================
BUILD_AGENT_CONTEXT_CODE = r"""const conversation = $('Load Conversation').first().json;
const historyItems = $('Load History').all();
const newMessage = $('Execute Workflow Trigger').first().json.messageText;
const config = conversation.agent_config || {};

const messages = historyItems.map(item => ({
  role: item.json.role,
  content: item.json.content
}));
messages.push({ role: 'user', content: newMessage });

const MAX_HISTORY_CHARS = 16000;
let totalChars = messages.reduce((sum, m) => sum + m.content.length, 0);
let finalMessages = messages;
if (totalChars > MAX_HISTORY_CHARS) {
  const recent = messages.slice(-8);
  const older = messages.slice(0, -8);
  const summary = older.map(m => `${m.role}: ${m.content.substring(0, 200)}`).join('\n');
  finalMessages = [
    { role: 'user', content: `[Previous conversation summary]\n${summary}` },
    ...recent
  ];
}

let systemPrompt = config.systemPrompt || 'You are a helpful sales assistant.';
systemPrompt += '\n\nYou are continuing an existing conversation. The message history is provided. Build on what was discussed \u2014 do not repeat introductions or re-ask questions that were already answered.';

const turnCount = conversation.turn_count || 1;
const maxTurns = conversation.max_turns || 10;
if (turnCount >= maxTurns - 1) {
  systemPrompt += '\n\nIMPORTANT: This is the final exchange in this thread. Provide your best complete answer. If more work is needed, tell the user to start a new conversation.';
}

const chatHistory = finalMessages.slice(0, -1).map(m =>
  `${m.role === 'user' ? 'Human' : 'Assistant'}: ${m.content}`
).join('\n\n');
const userMessage = finalMessages[finalMessages.length - 1].content;
const agentPrompt = chatHistory
  ? `[Conversation history]\n${chatHistory}\n\n[Current message]\n${userMessage}`
  : userMessage;

return [{
  json: {
    systemPrompt,
    agentPrompt,
    assistantName: config.assistantName || 'Aria',
    assistantEmoji: config.assistantEmoji || ':robot_face:',
    channelId: $('Execute Workflow Trigger').first().json.channelId,
    threadTs: $('Execute Workflow Trigger').first().json.threadTs,
    conversationId: conversation.id,
    turnCount,
    maxTurns,
    isFinalTurn: turnCount >= maxTurns - 1,
    workflowType: conversation.workflow_type
  }
}];
"""


def build_workflow():
    nodes = [
        # -------------------------------------------------------
        # 1. Execute Workflow Trigger
        # -------------------------------------------------------
        {
            "parameters": {"inputSource": "passthrough"},
            "id": uid(),
            "name": "Execute Workflow Trigger",
            "type": "n8n-nodes-base.executeWorkflowTrigger",
            "typeVersion": 1.1,
            "position": [0, 400]
        },
        # -------------------------------------------------------
        # 2. Load Conversation — HTTP GET from Supabase REST
        # -------------------------------------------------------
        {
            "parameters": {
                "method": "GET",
                "url": f"={SUPABASE_REST_URL}/conversations?id=eq.{{{{ $json.conversationId }}}}&select=*",
                "authentication": "predefinedCredentialType",
                "nodeCredentialType": "supabaseApi",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "Accept", "value": "application/json"},
                        {"name": "Prefer", "value": "return=representation"}
                    ]
                },
                "options": {}
            },
            "id": uid(),
            "name": "Load Conversation",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [250, 400],
            "credentials": {"supabaseApi": SUPABASE_CRED}
        },
        # -------------------------------------------------------
        # 3. Check Limits — Code node
        # -------------------------------------------------------
        {
            "parameters": {"jsCode": CHECK_LIMITS_CODE},
            "id": uid(),
            "name": "Check Limits",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [500, 400]
        },
        # -------------------------------------------------------
        # 4. Has Error? — If node (routes to error path or happy path)
        # -------------------------------------------------------
        {
            "parameters": {
                "conditions": {
                    "options": {
                        "version": 2,
                        "leftValue": "",
                        "caseSensitive": True,
                        "typeValidation": "strict"
                    },
                    "conditions": [
                        {
                            "id": uid(),
                            "leftValue": "={{ $json.error }}",
                            "rightValue": True,
                            "operator": {
                                "type": "boolean",
                                "operation": "true"
                            }
                        }
                    ],
                    "combinator": "and"
                },
                "options": {}
            },
            "id": uid(),
            "name": "Has Error?",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2.2,
            "position": [750, 400]
        },
        # -------------------------------------------------------
        # 5. Post Error — HTTP POST to Slack (error path)
        # -------------------------------------------------------
        {
            "parameters": {
                "method": "POST",
                "url": "https://slack.com/api/chat.postMessage",
                "authentication": "genericCredentialType",
                "genericAuthType": "httpHeaderAuth",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "Content-Type", "value": "application/json"}
                    ]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify({ channel: $('Execute Workflow Trigger').first().json.channelId, thread_ts: $('Execute Workflow Trigger').first().json.threadTs, text: $json.errorMessage, username: ($('Load Conversation').first().json.agent_config || {}).assistantName || 'Aria', icon_emoji: ($('Load Conversation').first().json.agent_config || {}).assistantEmoji || ':robot_face:', unfurl_links: false, unfurl_media: false }) }}",
                "options": {}
            },
            "id": uid(),
            "name": "Post Error",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [1000, 250],
            "credentials": {"httpHeaderAuth": SLACK_CRED}
        },
        # -------------------------------------------------------
        # 6. Set Processing — HTTP PATCH Supabase REST (happy path)
        # -------------------------------------------------------
        {
            "parameters": {
                "method": "PATCH",
                "url": f"={SUPABASE_REST_URL}/conversations?id=eq.{{{{ $json.conversationId }}}}",
                "authentication": "predefinedCredentialType",
                "nodeCredentialType": "supabaseApi",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "Content-Type", "value": "application/json"},
                        {"name": "Prefer", "value": "return=representation"}
                    ]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify({ status: 'processing' }) }}",
                "options": {}
            },
            "id": uid(),
            "name": "Set Processing",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [1000, 550],
            "credentials": {"supabaseApi": SUPABASE_CRED}
        },
        # -------------------------------------------------------
        # 7. Load History — HTTP GET from Supabase REST
        # -------------------------------------------------------
        {
            "parameters": {
                "method": "GET",
                "url": f"={SUPABASE_REST_URL}/messages?conversation_id=eq.{{{{ $('Check Limits').first().json.conversationId }}}}&order=sent_at.asc&select=role,content",
                "authentication": "predefinedCredentialType",
                "nodeCredentialType": "supabaseApi",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "Accept", "value": "application/json"}
                    ]
                },
                "options": {}
            },
            "id": uid(),
            "name": "Load History",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [1250, 550],
            "credentials": {"supabaseApi": SUPABASE_CRED}
        },
        # -------------------------------------------------------
        # 8. Log Inbound — HTTP POST to Supabase REST (insert user message)
        # -------------------------------------------------------
        {
            "parameters": {
                "method": "POST",
                "url": f"{SUPABASE_REST_URL}/messages",
                "authentication": "predefinedCredentialType",
                "nodeCredentialType": "supabaseApi",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "Content-Type", "value": "application/json"},
                        {"name": "Prefer", "value": "return=representation"}
                    ]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify({ user_id: $('Load Conversation').first().json.user_id, message_type: 'conversation', conversation_id: $('Check Limits').first().json.conversationId, slack_thread_ts: $('Execute Workflow Trigger').first().json.threadTs, role: 'user', content: $('Execute Workflow Trigger').first().json.messageText, channel: 'slack', direction: 'inbound' }) }}",
                "options": {}
            },
            "id": uid(),
            "name": "Log Inbound",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [1500, 550],
            "credentials": {"supabaseApi": SUPABASE_CRED}
        },
        # -------------------------------------------------------
        # 9. Build Agent Context — Code node
        # -------------------------------------------------------
        {
            "parameters": {"jsCode": BUILD_AGENT_CONTEXT_CODE},
            "id": uid(),
            "name": "Build Agent Context",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1750, 550]
        },
        # -------------------------------------------------------
        # 10. Conversation Agent — Anthropic Tools Agent
        # -------------------------------------------------------
        {
            "parameters": {
                "promptType": "define",
                "text": "={{ $('Build Agent Context').first().json.agentPrompt }}",
                "options": {
                    "systemMessage": "={{ $('Build Agent Context').first().json.systemPrompt }}",
                    "maxIterations": 10
                }
            },
            "id": uid(),
            "name": "Conversation Agent",
            "type": "@n8n/n8n-nodes-langchain.agent",
            "typeVersion": 1.7,
            "position": [2000, 550],
            "continueOnFail": True
        },
        # -------------------------------------------------------
        # 11. Anthropic Chat Model — sub-node of Conversation Agent
        # -------------------------------------------------------
        {
            "parameters": {
                "model": {
                    "__rl": True,
                    "mode": "list",
                    "value": "claude-sonnet-4-5-20250929",
                    "cachedResultName": "Claude Sonnet 4.5"
                },
                "options": {}
            },
            "id": uid(),
            "name": "Anthropic Chat Model",
            "type": "@n8n/n8n-nodes-langchain.lmChatAnthropic",
            "typeVersion": 1.3,
            "position": [2008, 774],
            "credentials": {"anthropicApi": ANTHROPIC_CRED}
        },
        # -------------------------------------------------------
        # 12. Backstory MCP Tool — sub-node of Conversation Agent
        # -------------------------------------------------------
        {
            "parameters": {
                "endpointUrl": "https://mcp.people.ai/mcp",
                "authentication": "multipleHeadersAuth",
                "options": {}
            },
            "id": uid(),
            "name": "Backstory MCP",
            "type": "@n8n/n8n-nodes-langchain.mcpClientTool",
            "typeVersion": 1.2,
            "position": [2136, 774],
            "credentials": {"httpMultipleHeadersAuth": MCP_CRED}
        },
        # -------------------------------------------------------
        # 13. Post Response — HTTP POST to Slack chat.postMessage
        # -------------------------------------------------------
        {
            "parameters": {
                "method": "POST",
                "url": "https://slack.com/api/chat.postMessage",
                "authentication": "genericCredentialType",
                "genericAuthType": "httpHeaderAuth",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "Content-Type", "value": "application/json"}
                    ]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify({ channel: $('Build Agent Context').first().json.channelId, thread_ts: $('Build Agent Context').first().json.threadTs, text: $json.output || $json.text || 'I encountered an issue processing your request. Please try again.', username: $('Build Agent Context').first().json.assistantName, icon_emoji: $('Build Agent Context').first().json.assistantEmoji, unfurl_links: false, unfurl_media: false }) }}",
                "options": {}
            },
            "id": uid(),
            "name": "Post Response",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [2250, 550],
            "credentials": {"httpHeaderAuth": SLACK_CRED}
        },
        # -------------------------------------------------------
        # 14. Log Outbound — HTTP POST to Supabase REST (insert assistant message)
        # -------------------------------------------------------
        {
            "parameters": {
                "method": "POST",
                "url": f"{SUPABASE_REST_URL}/messages",
                "authentication": "predefinedCredentialType",
                "nodeCredentialType": "supabaseApi",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "Content-Type", "value": "application/json"},
                        {"name": "Prefer", "value": "return=representation"}
                    ]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify({ user_id: $('Load Conversation').first().json.user_id, message_type: 'conversation', conversation_id: $('Build Agent Context').first().json.conversationId, slack_thread_ts: $('Build Agent Context').first().json.threadTs, role: 'assistant', content: $('Conversation Agent').first().json.output || $('Conversation Agent').first().json.text || '', channel: 'slack', direction: 'outbound' }) }}",
                "options": {}
            },
            "id": uid(),
            "name": "Log Outbound",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [2500, 550],
            "credentials": {"supabaseApi": SUPABASE_CRED}
        },
        # -------------------------------------------------------
        # 15. Update Conversation — HTTP PATCH Supabase REST
        #     Increments turn_count, slides expires_at, sets status
        # -------------------------------------------------------
        {
            "parameters": {
                "method": "PATCH",
                "url": f"={SUPABASE_REST_URL}/conversations?id=eq.{{{{ $('Build Agent Context').first().json.conversationId }}}}",
                "authentication": "predefinedCredentialType",
                "nodeCredentialType": "supabaseApi",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "Content-Type", "value": "application/json"},
                        {"name": "Prefer", "value": "return=representation"}
                    ]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify({ turn_count: ($('Build Agent Context').first().json.turnCount || 1) + 1, expires_at: new Date(Date.now() + 4 * 60 * 60 * 1000).toISOString(), status: $('Build Agent Context').first().json.isFinalTurn ? 'completed' : 'active' }) }}",
                "options": {}
            },
            "id": uid(),
            "name": "Update Conversation",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [2750, 550],
            "credentials": {"supabaseApi": SUPABASE_CRED}
        },
    ]

    connections = {
        # Main flow: Trigger → Load Conversation → Check Limits → Has Error?
        "Execute Workflow Trigger": {
            "main": [[{"node": "Load Conversation", "type": "main", "index": 0}]]
        },
        "Load Conversation": {
            "main": [[{"node": "Check Limits", "type": "main", "index": 0}]]
        },
        "Check Limits": {
            "main": [[{"node": "Has Error?", "type": "main", "index": 0}]]
        },
        # Has Error? — true (output 0) → Post Error, false (output 1) → Set Processing
        "Has Error?": {
            "main": [
                [{"node": "Post Error", "type": "main", "index": 0}],    # true → error path
                [{"node": "Set Processing", "type": "main", "index": 0}]  # false → happy path
            ]
        },
        # Happy path continues
        "Set Processing": {
            "main": [[{"node": "Load History", "type": "main", "index": 0}]]
        },
        "Load History": {
            "main": [[{"node": "Log Inbound", "type": "main", "index": 0}]]
        },
        "Log Inbound": {
            "main": [[{"node": "Build Agent Context", "type": "main", "index": 0}]]
        },
        "Build Agent Context": {
            "main": [[{"node": "Conversation Agent", "type": "main", "index": 0}]]
        },
        "Conversation Agent": {
            "main": [[{"node": "Post Response", "type": "main", "index": 0}]]
        },
        "Post Response": {
            "main": [[{"node": "Log Outbound", "type": "main", "index": 0}]]
        },
        "Log Outbound": {
            "main": [[{"node": "Update Conversation", "type": "main", "index": 0}]]
        },
        # Sub-node connections (agent sub-nodes)
        "Anthropic Chat Model": {
            "ai_languageModel": [[{"node": "Conversation Agent", "type": "ai_languageModel", "index": 0}]]
        },
        "Backstory MCP": {
            "ai_tool": [[{"node": "Conversation Agent", "type": "ai_tool", "index": 0}]]
        }
    }

    return {
        "name": "Continue Conversation",
        "nodes": nodes,
        "connections": connections,
        "settings": {
            "executionOrder": "v1"
        },
        "staticData": None
    }


def sync_local(wf, filename):
    path = os.path.join(REPO_ROOT, "n8n", "workflows", filename)
    with open(path, "w") as f:
        json.dump(wf, f, indent=4)
    print(f"  Synced {path}")


def main():
    workflow = build_workflow()

    print("Creating Continue Conversation workflow...")
    resp = requests.post(
        f"{N8N_BASE_URL}/api/v1/workflows",
        headers=HEADERS,
        json=workflow
    )
    resp.raise_for_status()
    result = resp.json()
    wf_id = result["id"]
    print(f"  Created: ID={wf_id}, {len(result['nodes'])} nodes")

    # Sub-workflows called via Execute Workflow don't need activation,
    # but the executeWorkflowTrigger with inputSource=passthrough must be
    # in an active workflow to receive calls.
    print("  Activating workflow...")
    resp2 = requests.post(
        f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}/activate",
        headers=HEADERS
    )
    resp2.raise_for_status()
    print(f"  Activated: {resp2.json().get('active')}")

    # Sync local file
    resp3 = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}", headers=HEADERS)
    resp3.raise_for_status()
    sync_local(resp3.json(), "Continue Conversation.json")

    print(f"\nDone! Workflow ID: {wf_id}")
    print("This sub-workflow is called via Execute Workflow from the Slack Events Handler.")
    print("It handles all multi-turn conversation follow-ups across all agent types.")


if __name__ == "__main__":
    main()
