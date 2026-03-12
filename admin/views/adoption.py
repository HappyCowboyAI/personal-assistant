import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
from admin.data.supabase_client import fetch_users, fetch_messages

def render():
    st.header("User Adoption")

    try:
        users = fetch_users()
    except Exception as e:
        st.error(f"Failed to load users: {e}")
        return

    if not users:
        st.info("No users found.")
        return

    users_df = pd.DataFrame(users)
    now = datetime.now(timezone.utc)
    week_ago = (now - timedelta(days=7)).isoformat()

    try:
        recent_msgs = fetch_messages(start=week_ago)
    except Exception:
        recent_msgs = []

    # Compute last active per user
    msg_df = pd.DataFrame(recent_msgs) if recent_msgs else pd.DataFrame(columns=["user_id", "sent_at"])
    active_users = set(msg_df["user_id"].unique()) if not msg_df.empty else set()

    # KPI row
    total = len(users_df)
    onboarded = len(users_df[users_df["onboarding_state"] == "complete"])
    active_week = len(active_users)
    stuck = users_df[users_df["onboarding_state"].isin(["awaiting_name", "awaiting_emoji"])]
    stuck_old = 0
    if not stuck.empty and "created_at" in stuck.columns:
        seven_days_ago = (now - timedelta(days=7)).isoformat()
        stuck_old = len(stuck[stuck["created_at"] < seven_days_ago])
    dropoff = round(stuck_old / total * 100, 1) if total > 0 else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Users", total)
    c2.metric("Onboarded", onboarded)
    c3.metric("Active This Week", active_week)
    c4.metric("Drop-off Rate", f"{dropoff}%")

    # Onboarding Funnel
    st.subheader("Onboarding Funnel")
    import plotly.express as px
    states = ["new", "awaiting_name", "awaiting_emoji", "complete"]
    state_counts = users_df["onboarding_state"].value_counts()
    funnel_data = [{"Stage": s, "Count": int(state_counts.get(s, 0))} for s in states]
    fig = px.funnel(pd.DataFrame(funnel_data), x="Count", y="Stage")
    fig.update_layout(height=250, margin=dict(t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)

    # Users table
    st.subheader("Users")
    col_filter1, col_filter2 = st.columns(2)
    with col_filter1:
        state_filter = st.multiselect("Filter by state", states, default=states)
    with col_filter2:
        scope_options = sorted(users_df["digest_scope"].dropna().unique().tolist())
        scope_filter = st.multiselect("Filter by scope", scope_options, default=scope_options)

    filtered = users_df[
        users_df["onboarding_state"].isin(state_filter) &
        (users_df["digest_scope"].isin(scope_filter) | users_df["digest_scope"].isna())
    ].copy()

    # Compute last active
    if not msg_df.empty:
        last_active = msg_df.groupby("user_id")["sent_at"].max().reset_index()
        last_active.columns = ["id", "last_active"]
        filtered = filtered.merge(last_active, on="id", how="left")
    else:
        filtered["last_active"] = None

    # Derive name from email
    filtered["name"] = filtered["email"].apply(
        lambda e: e.split("@")[0].replace(".", " ").title() if pd.notna(e) else "—"
    )

    display_cols = ["name", "email", "onboarding_state", "assistant_name", "digest_scope", "focus", "last_active"]
    available_cols = [c for c in display_cols if c in filtered.columns]
    st.dataframe(filtered[available_cols].sort_values("last_active", ascending=False, na_position="last"),
                 use_container_width=True, hide_index=True)

    # Personalization stats
    st.subheader("Personalization")
    complete = users_df[users_df["onboarding_state"] == "complete"]
    n = len(complete) if len(complete) > 0 else 1  # avoid div by zero

    p1, p2, p3 = st.columns(3)
    p1.metric("Custom Name", f"{len(complete[complete['assistant_name'].notna()]) / n * 100:.0f}%")
    p2.metric("Custom Emoji", f"{len(complete[complete['assistant_emoji'].notna()]) / n * 100:.0f}%")
    p3.metric("Custom Persona", f"{len(complete[complete['assistant_persona'].notna()]) / n * 100:.0f}%")

    if not complete.empty and "digest_scope" in complete.columns:
        scope_dist = complete["digest_scope"].value_counts()
        fig2 = px.pie(values=scope_dist.values, names=scope_dist.index, title="Digest Scope Distribution")
        fig2.update_layout(height=300, margin=dict(t=40, b=10))
        st.plotly_chart(fig2, use_container_width=True)
