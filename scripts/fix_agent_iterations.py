#!/usr/bin/env python3
"""Hot-fix: Increase Insights Agent maxIterations from default (10) to 20."""

import json
import os
import requests

N8N_BASE_URL = "https://scottai.trackslife.com"
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

INSIGHTS_WF_ID = "cV5GDdW5MiukdJdN"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{INSIGHTS_WF_ID}", headers=HEADERS)
resp.raise_for_status()
wf = resp.json()

for node in wf["nodes"]:
    if node["name"] == "Insights Agent":
        node["parameters"]["options"]["maxIterations"] = 20
        print(f"  Insights Agent: set maxIterations = 20")
        print(f"  Options: {json.dumps(node['parameters']['options'])}")
        break

payload = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
           "settings": wf.get("settings", {}), "staticData": wf.get("staticData")}
resp = requests.put(f"{N8N_BASE_URL}/api/v1/workflows/{INSIGHTS_WF_ID}", headers=HEADERS, json=payload)
resp.raise_for_status()
result = resp.json()
print(f"  Pushed: {len(result['nodes'])} nodes")

path = os.path.join(REPO_ROOT, "n8n", "workflows", "Opportunity Insights.json")
with open(path, "w") as f:
    json.dump(result, f, indent=4)
print(f"  Synced {path}")
print("\nDone! Agent can now use up to 20 iterations (was default 10).")
