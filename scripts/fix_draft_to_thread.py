"""
Fix: Post email drafts as threaded replies instead of inline.

Currently the DM followup draft replaces the "Thinking..." message with
the full email body, taking up a lot of space in the DM channel.

New behavior for drafts:
1. DM Post Answer: updates "Thinking..." → short summary like
   ":email: Follow-up draft for *Iron Mountain* posted in thread"
2. New "Post Draft Thread" node: posts full draft + mailto button as thread reply

Non-draft responses (general DM) keep the current inline behavior.

Usage:
    N8N_API_KEY=... python scripts/fix_draft_to_thread.py
"""

from n8n_helpers import (
    uid, find_node, fetch_workflow, push_workflow, sync_local,
    WF_EVENTS_HANDLER, NODE_HTTP_REQUEST,
)

SLACK_CRED = {"id": "LluVuiMJ8NUbAiG7", "name": "Slackbot Auth Token"}


def main():
    print(f"Fetching Events Handler {WF_EVENTS_HANDLER}...")
    wf = fetch_workflow(WF_EVENTS_HANDLER)
    nodes = wf["nodes"]
    connections = wf["connections"]
    print(f"  {len(nodes)} nodes")

    post_answer = find_node(nodes, "DM Post Answer")
    if not post_answer:
        print("  ERROR: Could not find 'DM Post Answer'")
        return

    # ── 1. Update DM Post Answer ──
    # For drafts: show short summary. For non-drafts: show full response.
    # The Format DM Draft Mailto node passes isDraft, blocks, fallbackText.
    new_body = (
        '={{ JSON.stringify(Object.assign('
        '{ channel: $("Build DM System Prompt").first().json.channelId,'
        ' ts: $("DM Post Thinking").first().json.ts },'
        ' $json.isDraft'
        ' ? { text: ":email: Draft posted in thread — check below." }'
        ' : { text: $json.fallbackText || "Sorry, I was unable to generate a response." }'
        ')) }}'
    )
    post_answer["parameters"]["jsonBody"] = new_body
    print("  Updated DM Post Answer: drafts show short summary")

    # ── 2. Create Post Draft Thread node ──
    post_answer_pos = post_answer["position"]
    thread_node = {
        "parameters": {
            "method": "POST",
            "url": "https://slack.com/api/chat.postMessage",
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Content-Type", "value": "application/json"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": (
                '={{ JSON.stringify(Object.assign('
                '{ channel: $("Build DM System Prompt").first().json.channelId,'
                ' thread_ts: $("DM Post Thinking").first().json.ts,'
                ' text: $("Format DM Draft Mailto").first().json.fallbackText || "Draft",'
                ' username: $("Build DM System Prompt").first().json.assistantName,'
                ' icon_emoji: $("Build DM System Prompt").first().json.assistantEmoji },'
                ' $("Format DM Draft Mailto").first().json.blocks'
                ' ? { blocks: JSON.parse($("Format DM Draft Mailto").first().json.blocks) }'
                ' : {}'
                ')) }}'
            ),
            "options": {},
        },
        "id": uid(),
        "name": "Post Draft Thread",
        "type": NODE_HTTP_REQUEST,
        "typeVersion": 4.2,
        "position": [post_answer_pos[0] + 220, post_answer_pos[1] + 150],
        "credentials": {"httpHeaderAuth": SLACK_CRED},
    }
    nodes.append(thread_node)
    print("  Added 'Post Draft Thread' node")

    # ── 3. Create a router node (Code) to split draft vs non-draft ──
    # Actually, simpler: Post Draft Thread has continueOnFail, and we use
    # an If node to only post thread for drafts.
    router_node = {
        "parameters": {
            "conditions": {
                "options": {
                    "version": 2,
                    "caseSensitive": True,
                    "typeValidation": "strict",
                    "leftValue": "",
                },
                "combinator": "and",
                "conditions": [{
                    "id": uid(),
                    "operator": {
                        "name": "filter.operator.equals",
                        "type": "boolean",
                        "operation": "equals",
                    },
                    "leftValue": "={{ $('Format DM Draft Mailto').first().json.isDraft }}",
                    "rightValue": True,
                }],
            },
        },
        "id": uid(),
        "name": "Is Email Draft?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [post_answer_pos[0] + 220, post_answer_pos[1]],
    }
    nodes.append(router_node)
    print("  Added 'Is Email Draft?' router node")

    # ── 4. Rewire connections ──
    # Current: DM Post Answer → Track DM Conv Usage
    # New: DM Post Answer → Is Email Draft?
    #      Is Email Draft? (true, output 0) → Post Draft Thread → Track DM Conv Usage
    #      Is Email Draft? (false, output 1) → Track DM Conv Usage

    # Find what DM Post Answer currently connects to
    old_targets = connections.get("DM Post Answer", {}).get("main", [[]])[0]
    next_node_name = old_targets[0]["node"] if old_targets else "Track DM Conv Usage"

    # DM Post Answer → Is Email Draft?
    connections["DM Post Answer"] = {
        "main": [[{
            "node": "Is Email Draft?",
            "type": "main",
            "index": 0,
        }]]
    }

    # Is Email Draft? → true (output 0): Post Draft Thread, false (output 1): Track DM Conv Usage
    connections["Is Email Draft?"] = {
        "main": [
            [{  # Output 0 (true) → Post Draft Thread
                "node": "Post Draft Thread",
                "type": "main",
                "index": 0,
            }],
            [{  # Output 1 (false) → next node (Track DM Conv Usage)
                "node": next_node_name,
                "type": "main",
                "index": 0,
            }],
        ]
    }

    # Post Draft Thread → Track DM Conv Usage
    connections["Post Draft Thread"] = {
        "main": [[{
            "node": next_node_name,
            "type": "main",
            "index": 0,
        }]]
    }

    print(f"  Rewired: DM Post Answer → Is Email Draft? → Post Draft Thread / {next_node_name}")

    print(f"\n=== Pushing workflow ===")
    result = push_workflow(WF_EVENTS_HANDLER, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")

    print("\n=== Syncing ===")
    sync_local(result, "Slack Events Handler.json")
    print(f"\nDone! {len(result['nodes'])} total nodes")


if __name__ == "__main__":
    main()
