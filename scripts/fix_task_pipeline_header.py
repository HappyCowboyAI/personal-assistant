#!/usr/bin/env python3
"""Add pipeline brief re-anchor after task section divider."""

import json
import os
import subprocess

N8N_URL = "https://scottai.trackslife.com"
API_KEY = os.environ["N8N_API_KEY"]

WORKFLOW_IDS = [
    "vxGajBdXFBaOCdkG",  # On-Demand Digest
    "7sinwSgjkEA40zDj",  # Sales Digest
]

OLD = "4. Add a divider block after the task items, before continuing with The Lead."

NEW = """4. Add a divider block after the task items.
5. Add a section block with ":zap: *Pipeline Brief*" to re-anchor the reader into pipeline content.
6. Then continue with The Lead."""


def api_get(path):
    result = subprocess.run(
        ["curl", "-s", "-H", f"X-N8N-API-KEY: {API_KEY}", f"{N8N_URL}/api/v1{path}"],
        capture_output=True, text=True
    )
    return json.loads(result.stdout)


def api_put(path, data):
    result = subprocess.run(
        ["curl", "-s", "-X", "PUT", "-H", f"X-N8N-API-KEY: {API_KEY}",
         "-H", "Content-Type: application/json",
         f"{N8N_URL}/api/v1{path}", "-d", json.dumps(data)],
        capture_output=True, text=True
    )
    return json.loads(result.stdout)


def main():
    for wf_id in WORKFLOW_IDS:
        wf = api_get(f"/workflows/{wf_id}")
        print(f"Updating {wf['name']} ({wf_id})...")

        for node in wf["nodes"]:
            if node["name"] == "Resolve Identity":
                code = node["parameters"]["jsCode"]
                if OLD in code:
                    code = code.replace(OLD, NEW)
                    node["parameters"]["jsCode"] = code
                    print("  Added pipeline re-anchor instruction")
                else:
                    print("  WARNING: pattern not found")

        payload = {
            "name": wf["name"],
            "nodes": wf["nodes"],
            "connections": wf["connections"],
            "settings": wf["settings"],
            "staticData": wf.get("staticData"),
        }
        result = api_put(f"/workflows/{wf_id}", payload)

        for n in result.get("nodes", []):
            if n["name"] == "Resolve Identity":
                code = n["parameters"]["jsCode"]
                print(f"  Verified: {'Pipeline Brief' in code}")


if __name__ == "__main__":
    main()
