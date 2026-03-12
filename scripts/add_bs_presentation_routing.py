#!/usr/bin/env python3
"""
Add presentation routing to Backstory SlackBot (/bs command).

Currently `/bs presentation <prompt>` goes through the generic agent path,
which generates pptxgenjs code inline. This script routes it to the
Backstory Presentation sub-workflow (Google Slides API) instead.

Changes:
1. Adds `isPresentation` + `presentationPrompt` detection in Resolve Assistant Identity
2. Adds "Is Presentation?" IF node between "Is BBR?" (no) and "Has Question?"
3. Routes yes → Post Thinking → Prepare Input → Execute Backstory Presentation workflow
4. Removes the pptxgenjs code generation instructions from the system prompt
"""

import json
import os
import uuid
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

BACKSTORY_SLACKBOT_ID = "Yg5GB1byqB0qD-5wVDOAn"
PRESENTATION_WF_ID = "lJypxYaw0BmUsTV8"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

SLACK_CRED = {"id": "LluVuiMJ8NUbAiG7", "name": "Slackbot Auth Token"}


def uid():
    return str(uuid.uuid4())


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


def upgrade_slackbot(wf):
    print(f"\n=== Adding presentation routing to Backstory SlackBot ===")
    nodes = wf["nodes"]
    connections = wf["connections"]

    # Check if already applied
    node_names = [n["name"] for n in nodes]
    if "Is Presentation?" in node_names:
        print("  Is Presentation? already exists -- skipping")
        return wf

    # --- 1. Update Resolve Assistant Identity: add isPresentation detection ---
    for node in nodes:
        if node["name"] == "Resolve Assistant Identity":
            old_code = node["parameters"]["jsCode"]

            # Add presentation detection after BBR detection block
            # Find the BBR account extraction block end and add presentation detection after it
            old_marker = "// Build system prompt"
            presentation_detection = (
                "// Presentation detection\n"
                "const presPatterns = [/^presentation\\b/i, /^pres\\b/i, /^slides?\\b/i, /^deck\\b/i];\n"
                "const isPresentation = presPatterns.some(p => p.test(commandLower));\n"
                "let presentationPrompt = null;\n"
                "if (isPresentation) {\n"
                "  presentationPrompt = commandText\n"
                "    .replace(/^(presentation|pres|slides?|deck)\\s*/i, '')\n"
                "    .trim();\n"
                "}\n\n"
                "// Build system prompt"
            )
            new_code = old_code.replace(old_marker, presentation_detection, 1)

            if new_code == old_code:
                print("  WARNING: Could not find 'Build system prompt' marker in Resolve Assistant Identity")
                return wf

            # Remove the PRESENTATIONS / BBR pptxgenjs code generation section from system prompt.
            # Replace it with a brief note that presentations are handled via a separate workflow.
            old_pres_section = "'',\n  '## PRESENTATIONS"
            # Find the full presentations section and replace it
            # The section starts with '## PRESENTATIONS' and ends before the closing ].join
            lines = new_code.split('\n')
            in_pres_section = False
            pres_start = None
            pres_end = None
            for i, line in enumerate(lines):
                if '## PRESENTATIONS' in line and 'BBR' in line:
                    # Go back one line to capture the empty string before it
                    pres_start = i - 1 if i > 0 and "''" in lines[i-1] else i
                    in_pres_section = True
                elif in_pres_section and "].join(" in line:
                    pres_end = i
                    break

            if pres_start is not None and pres_end is not None:
                # Replace the entire presentations section with a simple note
                replacement_lines = [
                    "  '',",
                    "  '## PRESENTATIONS',",
                    "  'If the user asks you to create a presentation, slides, or deck, respond:',",
                    "  '\"I\\'ll create that presentation for you now! Building your Backstory deck...\"',",
                    "  'Do NOT generate pptxgenjs code or any code. The presentation system handles this automatically.',",
                ]
                lines[pres_start:pres_end] = replacement_lines
                new_code = '\n'.join(lines)
                print("  Replaced pptxgenjs code generation instructions with redirect note")
            else:
                print("  WARNING: Could not find PRESENTATIONS section boundaries in system prompt")

            # Add isPresentation and presentationPrompt to the return object
            old_return_marker = "    isBBR,\n    bbrAccount,"
            new_return_marker = "    isBBR,\n    bbrAccount,\n    isPresentation,\n    presentationPrompt,"
            new_code = new_code.replace(old_return_marker, new_return_marker)

            node["parameters"]["jsCode"] = new_code
            print("  Updated Resolve Assistant Identity with presentation detection")
            break

    # --- 2. Add "Is Presentation?" IF node ---
    # Position it between Is BBR? and Has Question?
    is_pres_id = uid()
    nodes.append({
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
                    "leftValue": "={{ $json.isPresentation }}",
                    "rightValue": True,
                    "operator": {
                        "type": "boolean",
                        "operation": "true"
                    }
                }],
                "combinator": "and"
            },
            "options": {}
        },
        "id": is_pres_id,
        "name": "Is Presentation?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [3344, 2544]
    })
    print("  Added 'Is Presentation?' IF node")

    # --- 3. Add "Pres Post Thinking" — Slack message saying "building presentation" ---
    pres_thinking_id = uid()
    nodes.append({
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
            "jsonBody": "={{ JSON.stringify({ channel: $('Resolve Assistant Identity').first().json.channelId, text: $('Resolve Assistant Identity').first().json.assistantEmoji + ' Building your Backstory presentation... this takes about 2 minutes.', username: $('Resolve Assistant Identity').first().json.assistantName, icon_emoji: $('Resolve Assistant Identity').first().json.assistantEmoji, unfurl_links: false, unfurl_media: false }) }}",
            "options": {}
        },
        "id": pres_thinking_id,
        "name": "Pres Post Thinking",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [3568, 2544],
        "credentials": {"httpHeaderAuth": SLACK_CRED}
    })
    print("  Added 'Pres Post Thinking' node")

    # --- 4. Add "Prepare Pres Input" — pass data to sub-workflow ---
    prepare_pres_id = uid()
    nodes.append({
        "parameters": {
            "jsCode": (
                "const identity = $('Resolve Assistant Identity').first().json;\n"
                "return [{ json: {\n"
                "  channelId: identity.channelId,\n"
                "  presentationPrompt: identity.presentationPrompt || identity.commandText,\n"
                "  assistantName: identity.assistantName,\n"
                "  assistantEmoji: identity.assistantEmoji\n"
                "}}];"
            )
        },
        "id": prepare_pres_id,
        "name": "Prepare Pres Input",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [3792, 2544]
    })
    print("  Added 'Prepare Pres Input' node")

    # --- 5. Add "Execute Presentation" — calls Backstory Presentation sub-workflow ---
    exec_pres_id = uid()
    nodes.append({
        "parameters": {
            "workflowId": {"__rl": True, "mode": "id", "value": PRESENTATION_WF_ID},
            "options": {"waitForSubWorkflow": True}
        },
        "id": exec_pres_id,
        "name": "Execute Presentation",
        "type": "n8n-nodes-base.executeWorkflow",
        "typeVersion": 1.1,
        "position": [4016, 2544]
    })
    print("  Added 'Execute Presentation' node")

    # --- 6. Rewire connections ---
    # Currently: Is BBR? [no/output 1] → Has Question?
    # New:       Is BBR? [no/output 1] → Is Presentation? [yes/0] → Pres Post Thinking → Prepare → Execute
    #                                    Is Presentation? [no/1]  → Has Question?

    # Update Is BBR? no-branch (output index 1) to point to Is Presentation?
    if "Is BBR?" in connections:
        bbr_outputs = connections["Is BBR?"]["main"]
        if len(bbr_outputs) > 1:
            bbr_outputs[1] = [{"node": "Is Presentation?", "type": "main", "index": 0}]
            print("  Rewired: Is BBR? [no] → Is Presentation?")

    # Is Presentation? [yes] → Pres Post Thinking, [no] → Has Question?
    connections["Is Presentation?"] = {
        "main": [
            [{"node": "Pres Post Thinking", "type": "main", "index": 0}],
            [{"node": "Has Question?", "type": "main", "index": 0}]
        ]
    }
    print("  Wired: Is Presentation? [yes] → Pres Post Thinking, [no] → Has Question?")

    connections["Pres Post Thinking"] = {
        "main": [[{"node": "Prepare Pres Input", "type": "main", "index": 0}]]
    }
    connections["Prepare Pres Input"] = {
        "main": [[{"node": "Execute Presentation", "type": "main", "index": 0}]]
    }
    print("  Wired: Pres Post Thinking → Prepare Pres Input → Execute Presentation")

    print(f"  Total nodes: {len(nodes)}")
    return wf


def main():
    print("Fetching Backstory SlackBot workflow...")
    wf = fetch_workflow(BACKSTORY_SLACKBOT_ID)
    print(f"  {len(wf['nodes'])} nodes")

    wf = upgrade_slackbot(wf)

    print("\n=== Pushing updated workflow ===")
    result = push_workflow(BACKSTORY_SLACKBOT_ID, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")

    print("\n=== Syncing local file ===")
    sync_local(result, "Backstory SlackBot.json")

    print("\nDone! /bs presentation <prompt> now routes to Backstory Presentation workflow.")
    print("Supported trigger words: presentation, pres, slide, slides, deck")


if __name__ == "__main__":
    main()
