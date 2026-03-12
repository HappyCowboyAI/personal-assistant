import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
from admin.data.n8n_client import fetch_workflows, fetch_executions, get_workflow_name_map
from admin.data.supabase_client import fetch_messages

def render():
    st.header("System Health")

    try:
        workflows = fetch_workflows()
        all_execs = fetch_executions(hours_back=24)
        error_execs = [e for e in all_execs if e.get("status") == "error"]
    except Exception as e:
        st.error(f"Failed to connect to n8n: {e}")
        return

    try:
        now = datetime.now(timezone.utc)
        yesterday = (now - timedelta(hours=24)).isoformat()
        messages_24h = fetch_messages(start=yesterday)
    except Exception as e:
        st.error(f"Failed to connect to Supabase: {e}")
        messages_24h = []

    # KPI row
    active_count = sum(1 for w in workflows if w.get("active"))
    total_count = len(workflows)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Active Workflows", f"{active_count}/{total_count}")
    c2.metric("Executions (24h)", len(all_execs))
    c3.metric("Errors (24h)", len(error_execs), delta=None if len(error_execs) == 0 else f"{len(error_execs)} errors", delta_color="inverse")
    c4.metric("Messages Delivered (24h)", len(messages_24h))

    # Workflow Status table
    st.subheader("Workflow Status")
    wf_name_map = get_workflow_name_map()

    # Build last execution per workflow
    last_exec = {}
    for e in all_execs:
        wf_id = e.get("workflowId")
        if wf_id and (wf_id not in last_exec or e.get("startedAt", "") > last_exec[wf_id].get("startedAt", "")):
            last_exec[wf_id] = e

    rows = []
    for w in workflows:
        wid = w["id"]
        le = last_exec.get(wid)
        rows.append({
            "Workflow": w["name"],
            "Status": "Active" if w.get("active") else "Inactive",
            "Last Run": le.get("startedAt", "—")[:19].replace("T", " ") if le else "—",
            "Last Status": le.get("status", "—").title() if le else "—",
        })
    rows.sort(key=lambda r: r["Last Run"], reverse=True)

    df_wf = pd.DataFrame(rows)
    st.dataframe(df_wf, use_container_width=True, hide_index=True)

    # Recent Errors
    st.subheader("Recent Errors")
    if not error_execs:
        st.info("No errors in the last 24 hours.")
    else:
        error_rows = []
        for e in sorted(error_execs, key=lambda x: x.get("startedAt", ""), reverse=True)[:20]:
            wf_name = wf_name_map.get(e.get("workflowId"), "Unknown")
            error_msg = ""
            if e.get("data", {}).get("resultData", {}).get("error", {}).get("message"):
                error_msg = e["data"]["resultData"]["error"]["message"][:100]
            error_rows.append({
                "Workflow": wf_name,
                "Error": error_msg or "See execution details",
                "Execution": e.get("id", ""),
                "Time": e.get("startedAt", "")[:19].replace("T", " "),
            })
        st.dataframe(pd.DataFrame(error_rows), use_container_width=True, hide_index=True)

    # Execution volume chart
    st.subheader("Execution Volume (24h)")
    if all_execs:
        import plotly.express as px
        exec_df = pd.DataFrame(all_execs)
        exec_df["hour"] = pd.to_datetime(exec_df["startedAt"]).dt.floor("h")
        exec_df["workflow"] = exec_df["workflowId"].map(wf_name_map).fillna("Unknown")
        hourly = exec_df.groupby(["hour", "workflow"]).size().reset_index(name="count")
        fig = px.bar(hourly, x="hour", y="count", color="workflow", barmode="stack",
                     labels={"hour": "Hour", "count": "Executions", "workflow": "Workflow"})
        fig.update_layout(height=350, margin=dict(t=10, b=40))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No executions in the last 24 hours.")
