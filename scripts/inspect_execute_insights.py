#!/usr/bin/env python3
"""Inspect the Execute Insights node in the live Events Handler."""

import json
import requests

N8N_BASE_URL = "https://scottai.trackslife.com"
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/QuQbIaWetunUOFUW", headers=HEADERS)
resp.raise_for_status()
wf = resp.json()

for node in wf["nodes"]:
    if node["name"] == "Execute Insights":
        print(json.dumps(node["parameters"], indent=2))
        print(f"\nType version: {node.get('typeVersion')}")
        print(f"Type: {node.get('type')}")
        break
else:
    print("Execute Insights not found!")
    print("Available nodes:")
    for n in wf["nodes"]:
        print(f"  {n['name']}")
