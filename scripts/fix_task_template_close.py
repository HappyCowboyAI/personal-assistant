#!/usr/bin/env python3
"""Fix missing closing backtick on taskPromptSection template literal."""

import json
import os
import subprocess

N8N_URL = "https://scottai.trackslife.com"
API_KEY = os.environ["N8N_API_KEY"]

WORKFLOW_IDS = [
    "vxGajBdXFBaOCdkG",  # On-Demand Digest
    "7sinwSgjkEA40zDj",  # Sales Digest
]

# The broken pattern: template literal ends without closing backtick
OLD = """If there are NO tasks in the context above, do NOT include a Tasks section at all. Start directly with The Lead as normal.

const systemPrompt"""

NEW = """If there are NO tasks in the context above, do NOT include a Tasks section at all. Start directly with The Lead as normal.` : '';

const systemPrompt"""


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
        print(f"Fixing {wf['name']} ({wf_id})...")

        for node in wf["nodes"]:
            if node["name"] == "Resolve Identity":
                code = node["parameters"]["jsCode"]
                if OLD in code:
                    code = code.replace(OLD, NEW)
                    node["parameters"]["jsCode"] = code
                    print("  Fixed: added closing backtick + ternary")
                elif "` : '';" in code[code.find("Start directly"):code.find("Start directly")+200] if "Start directly" in code else False:
                    print("  Already fixed")
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

        # Verify by checking for syntax errors
        for n in result.get("nodes", []):
            if n["name"] == "Resolve Identity":
                code = n["parameters"]["jsCode"]
                # Count backticks in the taskPromptSection area
                tps_start = code.find("const taskPromptSection")
                tps_end = code.find("const systemPrompt")
                if tps_start >= 0 and tps_end >= 0:
                    section = code[tps_start:tps_end]
                    backtick_count = section.count("`")
                    has_ternary = "` : '';" in section
                    print(f"  Backticks in section: {backtick_count}, has ternary close: {has_ternary}")


if __name__ == "__main__":
    main()
