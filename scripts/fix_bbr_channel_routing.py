#!/usr/bin/env python3
"""
Fix: BBR command should post to originating channel, not always force a DM.

Problem: When /bs BBR is used in a channel, BBR Open DM forces the response
to the bot's DM. It should post to the channel where the command was invoked.

Fix:
1. Rewire Is BBR? → BBR Post Thinking (skip BBR Open DM)
2. Update BBR Post Thinking to use originating channelId
3. Update Prepare BBR Input to use originating channelId
"""

import json
import os
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = os.getenv("N8N_API_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA")

BACKSTORY_ID = "Yg5GB1byqB0qD-5wVDOAn"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}


def fetch_workflow(workflow_id):
    resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{workflow_id}", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def push_workflow(workflow_id, workflow):
    payload = {
        "name": workflow["name"],
        "nodes": workflow["nodes"],
        "connections": workflow["connections"],
        "settings": workflow.get("settings", {}),
        "staticData": workflow.get("staticData"),
    }
    resp = requests.put(
        f"{N8N_BASE_URL}/api/v1/workflows/{workflow_id}",
        headers=HEADERS,
        json=payload,
    )
    resp.raise_for_status()
    return resp.json()


def find_node(nodes, name):
    for n in nodes:
        if n["name"] == name:
            return n
    raise ValueError(f"Node '{name}' not found")


def main():
    print("Fetching live Backstory SlackBot workflow...")
    wf = fetch_workflow(BACKSTORY_ID)
    nodes = wf["nodes"]
    conns = wf["connections"]

    # 1. Rewire: Is BBR? output 0 (true) → BBR Post Thinking (skip BBR Open DM)
    bbr_conns = conns.get("Is BBR?", {}).get("main", [])
    if bbr_conns and len(bbr_conns) > 0:
        old_target = bbr_conns[0][0]["node"] if bbr_conns[0] else None
        print(f"  Is BBR? true output currently → {old_target}")
        bbr_conns[0] = [{"node": "BBR Post Thinking", "type": "main", "index": 0}]
        print(f"  Rewired Is BBR? true output → BBR Post Thinking")

    # 2. Update BBR Post Thinking to use originating channelId
    node = find_node(nodes, "BBR Post Thinking")
    old_body = node["parameters"]["jsonBody"]
    new_body = old_body.replace(
        "$('BBR Open DM').first().json.channel.id",
        "$('Resolve Assistant Identity').first().json.channelId"
    )
    if new_body != old_body:
        node["parameters"]["jsonBody"] = new_body
        print("  Updated BBR Post Thinking channel → originating channelId")
    else:
        print("  WARNING: BBR Post Thinking body not changed (pattern not found)")

    # 3. Update Prepare BBR Input to use originating channelId
    node = find_node(nodes, "Prepare BBR Input")
    old_code = node["parameters"]["jsCode"]
    new_code = old_code.replace(
        "$('BBR Open DM').first().json.channel.id",
        "$('Resolve Assistant Identity').first().json.channelId"
    )
    if new_code != old_code:
        node["parameters"]["jsCode"] = new_code
        print("  Updated Prepare BBR Input channelId → originating channelId")
    else:
        print("  WARNING: Prepare BBR Input code not changed (pattern not found)")

    # 4. Remove BBR Open DM connections (it's now orphaned)
    if "BBR Open DM" in conns:
        del conns["BBR Open DM"]
        print("  Removed BBR Open DM connections")

    # Push updated workflow
    print("\nPushing updated workflow...")
    result = push_workflow(BACKSTORY_ID, wf)
    print(f"  ✓ Pushed successfully (updatedAt: {result.get('updatedAt', 'unknown')})")

    # Sync local file
    print("\nSyncing local file...")
    live = fetch_workflow(BACKSTORY_ID)
    local_path = os.path.join(REPO_ROOT, "n8n", "workflows", "Backstory SlackBot.json")
    with open(local_path, "w") as f:
        json.dump(live, f, indent=2)
    print(f"  ✓ Saved to {local_path}")

    print("\nDone! BBR now posts to the originating channel instead of forcing a DM.")


if __name__ == "__main__":
    main()
