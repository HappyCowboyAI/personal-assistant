#!/usr/bin/env python3
"""Check Insights Agent node settings (max iterations, model, etc.)"""

import json
import requests

N8N_BASE_URL = "https://scottai.trackslife.com"
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

# Check Insights Agent
resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/cV5GDdW5MiukdJdN", headers=HEADERS)
resp.raise_for_status()
wf = resp.json()

for node in wf["nodes"]:
    if node["name"] == "Insights Agent":
        print("=== Insights Agent ===")
        print(json.dumps(node["parameters"], indent=2))
        print(f"Type: {node['type']}, Version: {node.get('typeVersion')}")
        break

# Check Digest Agent for comparison
resp2 = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/7sinwSgjkEA40zDj", headers=HEADERS)
resp2.raise_for_status()
wf2 = resp2.json()

for node in wf2["nodes"]:
    if node["name"] == "Digest Agent":
        print("\n=== Digest Agent (Sales Digest — for comparison) ===")
        print(json.dumps(node["parameters"], indent=2))
        print(f"Type: {node['type']}, Version: {node.get('typeVersion')}")
        break
