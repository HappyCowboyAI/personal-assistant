import streamlit as st
import requests
from datetime import datetime, timedelta, timezone
from admin.config import N8N_URL, N8N_API_KEY

HEADERS = {"X-N8N-API-KEY": N8N_API_KEY}

@st.cache_data(ttl=30)
def fetch_workflows():
    """Fetch all workflows with active status."""
    resp = requests.get(f"{N8N_URL}/api/v1/workflows", headers=HEADERS, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return data.get("data", data) if isinstance(data, dict) else data

@st.cache_data(ttl=30)
def fetch_executions(status=None, limit=250, hours_back=24):
    """Fetch recent executions with optional status filter and time range."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours_back))
    params = {"limit": limit}
    if status:
        params["status"] = status

    all_executions = []
    resp = requests.get(f"{N8N_URL}/api/v1/executions", headers=HEADERS, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    all_executions.extend(data.get("data", []))

    # Paginate if needed — stop if we've gone past the cutoff
    while data.get("nextCursor"):
        # Check if oldest item in batch is before cutoff
        batch = data.get("data", [])
        if batch:
            oldest = batch[-1].get("startedAt", "")
            if oldest and oldest < cutoff.isoformat():
                break
        params["cursor"] = data["nextCursor"]
        resp = requests.get(f"{N8N_URL}/api/v1/executions", headers=HEADERS, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        all_executions.extend(data.get("data", []))

    # Filter to time range client-side
    cutoff_str = cutoff.isoformat()
    all_executions = [e for e in all_executions if e.get("startedAt", "") >= cutoff_str]

    return all_executions

def get_workflow_name_map():
    """Returns {workflow_id: workflow_name} dict."""
    workflows = fetch_workflows()
    return {w["id"]: w["name"] for w in workflows}
