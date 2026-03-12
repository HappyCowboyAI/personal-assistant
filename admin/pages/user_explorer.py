import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta, timezone
from admin.data.supabase_client import (
    fetch_users, fetch_messages, fetch_alert_history,
    fetch_pending_actions, fetch_feature_usage, fetch_feature_catalog, fetch_conversations
)

def render():
    st.header("User Explorer")

    try:
        users = fetch_users()
    except Exception as e:
        st.error(f"Failed to load users: {e}")
        return

    if not users:
        st.info("No users found.")
        return

    # User selector
    user_options = {}
    for u in users:
        email = u.get("email", "")
        name = email.split("@")[0].replace(".", " ").title() if email else u["id"]
        user_options[f"{name} ({email})"] = u["id"]

    # Check for pre-selected user from session state
    default_idx = 0
    if "explorer_user_id" in st.session_state:
        for i, (label, uid) in enumerate(user_options.items()):
            if uid == st.session_state["explorer_user_id"]:
                default_idx = i
                break

    selected_label = st.selectbox("Select user", list(user_options.keys()), index=default_idx)
    user_id = user_options[selected_label]

    # Find user record
    user = next((u for u in users if u["id"] == user_id), {})

    # Profile card
    st.subheader("Profile")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"**Email:** {user.get('email', '—')}")
        st.markdown(f"**Slack ID:** `{user.get('slack_user_id', '—')}`")
        st.markdown(f"**Assistant:** {user.get('assistant_emoji', '')} {user.get('assistant_name', '—')}")
        st.markdown(f"**Persona:** {user.get('assistant_persona', '—') or '—'}")
    with col2:
        st.markdown(f"**State:** {user.get('onboarding_state', '—')}")
        st.markdown(f"**Scope:** {user.get('digest_scope', '—') or '—'}")
        st.markdown(f"**Focus:** {user.get('focus', '—') or '—'}")
        st.markdown(f"**Timezone:** {user.get('timezone', '—')}")
    with col3:
        st.markdown(f"**Digest:** {'Enabled' if user.get('digest_enabled', True) else 'Disabled'}")
        st.markdown(f"**Meeting Prep:** {'Enabled' if user.get('meeting_prep_enabled', True) else 'Disabled'}")
        st.markdown(f"**Follow-ups:** {'Enabled' if user.get('followup_enabled', True) else 'Disabled'}")
        st.markdown(f"**Tips:** {'Enabled' if user.get('tips_enabled', True) else 'Disabled'}")
        st.markdown(f"**Created:** {str(user.get('created_at', ''))[:10]}")

    st.markdown("---")

    # Activity summary
    now = datetime.now(timezone.utc)
    week_ago = (now - timedelta(days=7)).isoformat()
    month_ago = (now - timedelta(days=30)).isoformat()

    try:
        with st.spinner("Loading activity..."):
            msgs_7d = fetch_messages(start=week_ago, user_id=user_id)
            msgs_30d = fetch_messages(start=month_ago, user_id=user_id)
            alerts_7d = fetch_alert_history(start=week_ago)
            actions = fetch_pending_actions(user_id=user_id)
            f_usage = fetch_feature_usage()
            f_catalog = fetch_feature_catalog()
    except Exception as e:
        st.error(f"Failed to load activity: {e}")
        return

    user_alerts = [a for a in (alerts_7d or []) if a.get("user_id") == user_id]
    approved = len([a for a in (actions or []) if a.get("status") == "approved"])
    rejected = len([a for a in (actions or []) if a.get("status") == "rejected"])
    user_features = [f for f in (f_usage or []) if f.get("user_id") == user_id and f.get("use_count", 0) > 0]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Messages (7d)", len(msgs_7d or []))
    c2.metric("Alerts (7d)", len(user_alerts))
    c3.metric("Drafts", f"{approved} approved / {rejected} rejected")
    c4.metric("Features Used", len(user_features))

    # Message sparkline (30 days)
    if msgs_30d:
        msg_df = pd.DataFrame(msgs_30d)
        msg_df["date"] = pd.to_datetime(msg_df["sent_at"]).dt.date
        daily = msg_df.groupby("date").size().reset_index(name="count")
        fig = px.area(daily, x="date", y="count", labels={"date": "", "count": "Messages"})
        fig.update_layout(height=150, margin=dict(t=10, b=10, l=40, r=10))
        fig.update_xaxes(showgrid=False)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # Activity timeline
    st.subheader("Activity Timeline")
    type_filter = st.multiselect("Filter", ["Messages", "Alerts", "Drafts"], default=["Messages", "Alerts", "Drafts"])

    timeline = []
    if "Messages" in type_filter and msgs_7d:
        for m in msgs_7d:
            direction = m.get("direction", "outbound")
            icon = "🗣️" if direction == "inbound" else "🤖"
            timeline.append({
                "time": m.get("sent_at", ""),
                "icon": icon,
                "type": m.get("message_type", "message"),
                "preview": (m.get("content", "") or "")[:150],
                "full": m.get("content", ""),
            })
    if "Alerts" in type_filter:
        for a in user_alerts:
            timeline.append({
                "time": a.get("created_at", ""),
                "icon": "🔔",
                "type": f"alert ({a.get('severity', 'info')})",
                "preview": a.get("title", "Alert"),
                "full": a.get("body", ""),
            })
    if "Drafts" in type_filter and actions:
        for a in actions:
            icon = "✅" if a.get("status") == "approved" else "❌" if a.get("status") == "rejected" else "⏳"
            timeline.append({
                "time": a.get("created_at", ""),
                "icon": icon,
                "type": f"draft ({a.get('status', 'pending')})",
                "preview": (a.get("draft_content", "") or "")[:150],
                "full": a.get("draft_content", ""),
            })

    timeline.sort(key=lambda x: x["time"], reverse=True)

    if not timeline:
        st.info("No activity in the last 7 days.")
    else:
        for item in timeline[:50]:
            ts = str(item["time"])[:19].replace("T", " ")
            st.markdown(f"{item['icon']} **{item['type']}** · {ts}")
            with st.expander(item["preview"] or "(empty)", expanded=False):
                st.text(item["full"])

    st.markdown("---")

    # Feature usage
    st.subheader("Feature Usage")
    catalog_map = {f["id"]: f["display_name"] for f in (f_catalog or [])}
    if user_features:
        feat_rows = []
        for f in user_features:
            feat_rows.append({
                "Feature": catalog_map.get(f["feature_id"], f["feature_id"]),
                "First Used": str(f.get("first_used_at", ""))[:10],
                "Last Used": str(f.get("last_used_at", ""))[:10],
                "Uses": f.get("use_count", 0),
            })
        st.dataframe(pd.DataFrame(feat_rows).sort_values("Uses", ascending=False),
                     use_container_width=True, hide_index=True)
    else:
        st.info("No features used yet.")
