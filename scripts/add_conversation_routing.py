#!/usr/bin/env python3
"""
Add conversation thread-reply routing to Slack Events Handler.

Intercepts thread replies to active conversations and routes them to the
"Continue Conversation" sub-workflow (dutUnWP73mjpkaIL).

Changes:
1. Update "Extract Event Data" — add thread_ts extraction
2. Add "Is Thread Reply?" IF node after "Is Bot Message?" false output
3. Add "Check Active Conversation" HTTP Request (Supabase GET on conversations table)
4. Add "Has Active Conversation?" IF node
5. Add "Continue Conversation" Execute Workflow node
6. Reconnect: Bot false → Is Thread Reply? → (yes) Check → Has? → (yes) Execute / (no) Lookup User
                                            → (no) Lookup User
"""

import json
import os
import uuid
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

SLACK_EVENTS_ID = "QuQbIaWetunUOFUW"
CONTINUE_CONVERSATION_ID = "dutUnWP73mjpkaIL"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}
SUPABASE_CRED = {"id": "ASRWWkQ0RSMOpNF1", "name": "Supabase account"}
SUPABASE_REST_URL = "https://rhrlnkbphxntxxxcrgvv.supabase.co/rest/v1"


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
    print("\n=== Adding conversation thread-reply routing ===")
    nodes = wf["nodes"]
    connections = wf["connections"]

    # --- Guard: check if already applied ---
    node_names = [n["name"] for n in nodes]
    if "Is Thread Reply?" in node_names:
        print("  'Is Thread Reply?' already exists — skipping")
        return wf

    # --- Step 1: Update Extract Event Data to include thread_ts ---
    extract_node = find_node(nodes, "Extract Event Data")
    old_code = extract_node["parameters"]["jsCode"]

    # Add thread_ts and isThreadReply to the return object
    # Find the return object and add the new fields before the closing braces
    old_return_fragment = (
        "    isBot: !!(event.bot_id || event.subtype),\n"
        "    tab: event.tab || null\n"
        "  }\n"
        "}];"
    )
    new_return_fragment = (
        "    isBot: !!(event.bot_id || event.subtype),\n"
        "    tab: event.tab || null,\n"
        "    threadTs: event.thread_ts || null,\n"
        "    isThreadReply: !!event.thread_ts\n"
        "  }\n"
        "}];"
    )

    if "threadTs" in old_code:
        print("  Extract Event Data already has threadTs — skipping code update")
    elif old_return_fragment in old_code:
        extract_node["parameters"]["jsCode"] = old_code.replace(
            old_return_fragment, new_return_fragment
        )
        print("  Updated Extract Event Data with threadTs and isThreadReply fields")
    else:
        # Fallback: try to inject before the final }]; using a more flexible approach
        # Look for the closing pattern
        if "tab: event.tab || null" in old_code and "threadTs" not in old_code:
            extract_node["parameters"]["jsCode"] = old_code.replace(
                "tab: event.tab || null",
                "tab: event.tab || null,\n    threadTs: event.thread_ts || null,\n    isThreadReply: !!event.thread_ts",
            )
            print(
                "  Updated Extract Event Data with threadTs and isThreadReply (fallback pattern)"
            )
        else:
            print(
                "  WARNING: Could not find expected pattern in Extract Event Data. Manual update needed."
            )

    # --- Step 2: Determine positions for new nodes ---
    # Current layout:
    #   Is Bot Message? at [1104, 1104]
    #     true  → Stop - Bot Message at [1328, 1008]
    #     false → Lookup User at [1328, 1200]
    #   Lookup User → Route by State at [1552, 1200]
    #
    # We need to insert 4 nodes between Bot false output and Lookup User.
    # We'll shift Lookup User and Route by State (and everything downstream) to the right,
    # OR we can place new nodes in the vertical space below the main path.
    #
    # Better approach: place new nodes in a branch below, keeping existing positions.
    # New layout:
    #   Is Bot Message? [1104, 1104]
    #     true  → Stop - Bot Message [1328, 1008]
    #     false → Is Thread Reply? [1328, 1200] (takes Lookup User's position)
    #       false → Lookup User (shifted right to [1552, 1200], Route by State to [1776, 1200])
    #       true  → Check Active Conversation [1552, 1400]
    #               → Has Active Conversation? [1776, 1400]
    #                   true  → Continue Conversation [2000, 1400] (END)
    #                   false → connects to Lookup User [1552, 1200]
    #
    # But shifting Lookup User and Route by State would break all downstream connections
    # from Switch Route. That's too risky.
    #
    # Safer approach: place "Is Thread Reply?" at a new position between Bot and Lookup User,
    # and route the branch downward for the conversation check path.
    #
    # The space between Is Bot Message? [1104] and Lookup User [1328] is only 224px.
    # We can't easily fit a node there. Instead, let's insert the "Is Thread Reply?" node
    # between the Bot check and Lookup User by placing it at [1216, 1200] — midway.
    # Actually with n8n canvas, ~200px is enough. Let's place it at:
    #   Is Thread Reply?          [1216, 1200]  — between Bot and Lookup User
    #   Check Active Conversation [1216, 1460]  — below Is Thread Reply (true branch goes down)
    #   Has Active Conversation?  [1456, 1460]  — to the right
    #   Continue Conversation     [1696, 1460]  — to the right (end)
    #
    # Wait — there's only 224px horizontal gap between Bot [1104] and Lookup [1328].
    # Inserting a node at x=1216 would be very tight with Lookup at x=1328.
    #
    # Best approach: Keep Lookup User where it is. Place new nodes below the main path.
    # Re-wire: Bot false → Is Thread Reply? (new, placed at [1104, 1400])
    #   Is Thread Reply? false → Lookup User [1328, 1200] (existing, no position change)
    #   Is Thread Reply? true  → Check Active Conversation [1328, 1500]
    #     → Has Active Conversation? [1600, 1500]
    #       true → Continue Conversation [1872, 1500]
    #       false → Lookup User [1328, 1200]

    # Position calculations — place thread reply check below and slightly right of Bot check
    pos_is_thread_reply = [1200, 1400]
    pos_check_active_conv = [1440, 1560]
    pos_has_active_conv = [1680, 1560]
    pos_continue_conv = [1920, 1560]

    # --- Step 3: Create new nodes ---

    # 3a. "Is Thread Reply?" — IF node
    is_thread_reply_id = str(uuid.uuid4())
    is_thread_reply_node = {
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
                        "id": str(uuid.uuid4()),
                        "leftValue": "={{ $json.isThreadReply }}",
                        "rightValue": True,
                        "operator": {
                            "type": "boolean",
                            "operation": "true",
                        },
                    }
                ],
                "combinator": "and",
            },
            "options": {},
        },
        "id": is_thread_reply_id,
        "name": "Is Thread Reply?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": pos_is_thread_reply,
    }
    nodes.append(is_thread_reply_node)
    print(f"  Added 'Is Thread Reply?' node (id={is_thread_reply_id})")

    # 3b. "Check Active Conversation" — HTTP Request GET to Supabase conversations table
    check_active_conv_id = str(uuid.uuid4())
    # Query: conversations where slack_channel_id matches, slack_thread_ts matches,
    # status is active or processing, and not expired
    check_active_conv_node = {
        "parameters": {
            "method": "GET",
            "url": (
                f"={SUPABASE_REST_URL}/conversations"
                "?slack_channel_id=eq.{{ $json.channelId }}"
                "&slack_thread_ts=eq.{{ $json.threadTs }}"
                "&status=in.(active,processing)"
                "&expires_at=gt.now()"
                "&select=id,status"
                "&limit=1"
            ),
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "supabaseApi",
            "options": {},
        },
        "id": check_active_conv_id,
        "name": "Check Active Conversation",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": pos_check_active_conv,
        "credentials": {"supabaseApi": SUPABASE_CRED},
        "alwaysOutputData": True,
        "continueOnFail": True,
    }
    nodes.append(check_active_conv_node)
    print(f"  Added 'Check Active Conversation' node (id={check_active_conv_id})")

    # 3c. "Has Active Conversation?" — IF node
    # The Supabase REST API returns an array. If a match was found, the first item
    # will have an 'id' field. n8n auto-unwraps arrays from HTTP requests, so if
    # the array is empty, $json will be empty / have no 'id'. If there's a match,
    # $json.id will be the conversation UUID.
    # We check: $json.id is not empty (exists and has a value)
    has_active_conv_id = str(uuid.uuid4())
    has_active_conv_node = {
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
                        "id": str(uuid.uuid4()),
                        "leftValue": "={{ $json.id }}",
                        "rightValue": "",
                        "operator": {
                            "type": "string",
                            "operation": "notEmpty",
                        },
                    }
                ],
                "combinator": "and",
            },
            "options": {},
        },
        "id": has_active_conv_id,
        "name": "Has Active Conversation?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": pos_has_active_conv,
    }
    nodes.append(has_active_conv_node)
    print(f"  Added 'Has Active Conversation?' node (id={has_active_conv_id})")

    # 3d. "Continue Conversation" — Execute Workflow node
    # Pass through: channelId, threadTs, userId, messageText, conversationId, slackUserName
    # The sub-workflow (Continue Conversation) expects these as input data.
    # We need a Code node to prepare the input, or we can use the Execute Workflow's
    # "each" mode which passes the current item's JSON.
    #
    # Actually, let's add a small "Prepare Conversation Input" Code node to assemble
    # the fields the sub-workflow needs from both Extract Event Data and Check Active Conversation.
    prepare_conv_input_id = str(uuid.uuid4())
    prepare_conv_input_code = r"""// Gather data from Extract Event Data and Check Active Conversation
const event = $('Extract Event Data').first().json;
const conversation = $('Check Active Conversation').first().json;

return [{
  json: {
    channelId: event.channelId,
    threadTs: event.threadTs,
    userId: event.userId,
    messageText: event.text,
    conversationId: conversation.id,
    conversationStatus: conversation.status,
    slackUserName: event.userId
  }
}];
"""
    prepare_conv_input_node = {
        "parameters": {"jsCode": prepare_conv_input_code},
        "id": prepare_conv_input_id,
        "name": "Prepare Conversation Input",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [pos_continue_conv[0], pos_continue_conv[1]],
    }
    nodes.append(prepare_conv_input_node)
    print(f"  Added 'Prepare Conversation Input' node (id={prepare_conv_input_id})")

    # Now the actual Execute Workflow node — placed after Prepare Conversation Input
    continue_conv_id = str(uuid.uuid4())
    continue_conv_node = {
        "parameters": {
            "workflowId": {
                "__rl": True,
                "mode": "id",
                "value": CONTINUE_CONVERSATION_ID,
            },
            "options": {},
        },
        "id": continue_conv_id,
        "name": "Continue Conversation",
        "type": "n8n-nodes-base.executeWorkflow",
        "typeVersion": 1.2,
        "position": [pos_continue_conv[0] + 240, pos_continue_conv[1]],
    }
    nodes.append(continue_conv_node)
    print(f"  Added 'Continue Conversation' node (id={continue_conv_id})")

    # --- Step 4: Rewire connections ---

    # 4a. Disconnect Bot false output from Lookup User, connect to Is Thread Reply?
    # Current: Is Bot Message? output 1 (false) → Lookup User
    bot_outputs = connections.get("Is Bot Message?", {}).get("main", [])
    if len(bot_outputs) > 1:
        # Output 0 = true (Stop - Bot Message), Output 1 = false (was: Lookup User)
        bot_outputs[1] = [{"node": "Is Thread Reply?", "type": "main", "index": 0}]
        print("  Rewired: Is Bot Message? false → Is Thread Reply?")
    else:
        print("  WARNING: Is Bot Message? doesn't have expected output structure")

    # 4b. Is Thread Reply? connections
    # Output 0 = true → Check Active Conversation
    # Output 1 = false → Lookup User (existing)
    connections["Is Thread Reply?"] = {
        "main": [
            [{"node": "Check Active Conversation", "type": "main", "index": 0}],  # true
            [{"node": "Lookup User", "type": "main", "index": 0}],  # false
        ]
    }
    print("  Wired: Is Thread Reply? true → Check Active Conversation")
    print("  Wired: Is Thread Reply? false → Lookup User (existing)")

    # 4c. Check Active Conversation → Has Active Conversation?
    connections["Check Active Conversation"] = {
        "main": [
            [{"node": "Has Active Conversation?", "type": "main", "index": 0}]
        ]
    }
    print("  Wired: Check Active Conversation → Has Active Conversation?")

    # 4d. Has Active Conversation?
    # Output 0 = true → Prepare Conversation Input → Continue Conversation
    # Output 1 = false → Lookup User (fall through to existing routing)
    connections["Has Active Conversation?"] = {
        "main": [
            [{"node": "Prepare Conversation Input", "type": "main", "index": 0}],  # true
            [{"node": "Lookup User", "type": "main", "index": 0}],  # false
        ]
    }
    print("  Wired: Has Active Conversation? true → Prepare Conversation Input")
    print("  Wired: Has Active Conversation? false → Lookup User (existing)")

    # 4e. Prepare Conversation Input → Continue Conversation
    connections["Prepare Conversation Input"] = {
        "main": [
            [{"node": "Continue Conversation", "type": "main", "index": 0}]
        ]
    }
    print("  Wired: Prepare Conversation Input → Continue Conversation")

    # Continue Conversation is the terminal node (sub-workflow handles everything)
    # No output connection needed.

    print(f"\n  Total nodes: {len(nodes)}")
    return wf


def main():
    print("Fetching Slack Events Handler (live)...")
    wf = fetch_workflow(SLACK_EVENTS_ID)
    print(f"  {len(wf['nodes'])} nodes, {len(wf['connections'])} connection groups")

    wf = upgrade(wf)

    print("\n=== Pushing workflow ===")
    result = push_workflow(SLACK_EVENTS_ID, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")

    print("\n=== Re-fetching and syncing local file ===")
    final = fetch_workflow(SLACK_EVENTS_ID)
    sync_local(final, "Slack Events Handler.json")

    print("\nDone! Thread replies to active conversations will now route to Continue Conversation.")


if __name__ == "__main__":
    main()
