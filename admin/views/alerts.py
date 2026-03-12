import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta, timezone
from admin.data.supabase_client import fetch_alert_history, fetch_alert_types, fetch_muted_alerts, fetch_users

def render():
    st.header("Alert Performance")

    now = datetime.now(timezone.utc)
    week_ago = (now - timedelta(days=7)).isoformat()

    try:
        with st.spinner("Loading alert data..."):
            alerts = fetch_alert_history(start=week_ago)
            alert_types = fetch_alert_types()
            muted = fetch_muted_alerts()
            users = fetch_users()
    except Exception as e:
        st.error(f"Failed to load alert data: {e}")
        return

    type_map = {t["id"]: t["display_name"] for t in alert_types} if alert_types else {}
    user_map = {u["id"]: u.get("email", u["id"]) for u in users} if users else {}

    if not alerts:
        st.info("No alerts recorded in the last 7 days.")
        return

    df = pd.DataFrame(alerts)
    df["alert_name"] = df["alert_type_id"].map(type_map).fillna("Unknown")

    # KPI row
    total = len(df)
    responded = df[df["status"].isin(["acknowledged", "acted"])]
    response_rate = round(len(responded) / total * 100, 1) if total > 0 else 0

    # Avg time to action
    acted = df[df["status"] == "acted"].copy()
    avg_action_time = "—"
    if not acted.empty and "delivered_at" in acted.columns and "resolved_at" in acted.columns:
        acted["delivered_at"] = pd.to_datetime(acted["delivered_at"], errors="coerce")
        acted["resolved_at"] = pd.to_datetime(acted["resolved_at"], errors="coerce")
        valid = acted.dropna(subset=["delivered_at", "resolved_at"])
        if not valid.empty:
            avg_mins = (valid["resolved_at"] - valid["delivered_at"]).dt.total_seconds().mean() / 60
            if avg_mins < 60:
                avg_action_time = f"{avg_mins:.0f}m"
            else:
                avg_action_time = f"{avg_mins / 60:.1f}h"

    active_mutes = len([m for m in (muted or []) if not m.get("unmuted_at")])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Alerts (7d)", total)
    c2.metric("Response Rate", f"{response_rate}%")
    c3.metric("Avg Time to Action", avg_action_time)
    c4.metric("Active Mutes", active_mutes)

    # Alert volume chart by severity
    st.subheader("Alert Volume by Severity")
    df["date"] = pd.to_datetime(df["created_at"]).dt.date
    daily_sev = df.groupby(["date", "severity"]).size().reset_index(name="count")
    color_map = {"info": "#60a5fa", "warning": "#fbbf24", "critical": "#ef4444", "dead": "#6b7280"}
    fig = px.bar(daily_sev, x="date", y="count", color="severity", barmode="stack",
                 color_discrete_map=color_map,
                 labels={"date": "Date", "count": "Alerts", "severity": "Severity"})
    fig.update_layout(height=300, margin=dict(t=10, b=40))
    st.plotly_chart(fig, use_container_width=True)

    # Response funnel
    st.subheader("Response Funnel")
    status_counts = df["status"].value_counts()
    funnel_stages = ["delivered", "acknowledged", "acted", "dismissed", "expired"]
    funnel_data = [{"Stage": s, "Count": int(status_counts.get(s, 0))} for s in funnel_stages if status_counts.get(s, 0) > 0]
    if funnel_data:
        fig2 = px.funnel(pd.DataFrame(funnel_data), x="Count", y="Stage")
        fig2.update_layout(height=250, margin=dict(t=10, b=10))
        st.plotly_chart(fig2, use_container_width=True)

    # Alert type table
    st.subheader("Performance by Alert Type")
    type_groups = df.groupby("alert_name")
    type_rows = []
    for name, group in type_groups:
        count = len(group)
        acted_pct = round(len(group[group["status"] == "acted"]) / count * 100, 1)
        dismissed_pct = round(len(group[group["status"] == "dismissed"]) / count * 100, 1)
        type_rows.append({"Alert Type": name, "Count (7d)": count, "Acted %": acted_pct, "Dismissed %": dismissed_pct})
    st.dataframe(pd.DataFrame(type_rows), use_container_width=True, hide_index=True)

    # Mute patterns
    st.subheader("Active Mutes")
    active_mute_list = [m for m in (muted or []) if not m.get("unmuted_at")]
    if not active_mute_list:
        st.info("No active mutes.")
    else:
        mute_rows = []
        for m in active_mute_list:
            mute_rows.append({
                "User": user_map.get(m.get("user_id"), "Unknown"),
                "Alert Type": type_map.get(m.get("alert_type_id"), "Unknown"),
                "Entity": m.get("entity_name", "—"),
                "Reason": m.get("mute_reason", "—"),
                "Since": str(m.get("muted_at", ""))[:10],
            })
        st.dataframe(pd.DataFrame(mute_rows), use_container_width=True, hide_index=True)
