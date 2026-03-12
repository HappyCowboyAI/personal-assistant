#!/usr/bin/env python3
"""Inspect all Execute Workflow nodes in Events Handler to see working patterns."""

import json
import requests

N8N_BASE_URL = "https://scottai.trackslife.com"
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/QuQbIaWetunUOFUW", headers=HEADERS)
resp.raise_for_status()
wf = resp.json()

for node in wf["nodes"]:
    if node["type"] == "n8n-nodes-base.executeWorkflow":
        print(f"=== {node['name']} (v{node.get('typeVersion')}) ===")
        print(json.dumps(node["parameters"], indent=2))
        print()
