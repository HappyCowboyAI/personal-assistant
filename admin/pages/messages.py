import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta, timezone
from admin.data.supabase_client import fetch_users, fetch_messages, fetch_conversations

MESSAGE_TYPES = ["digest", "meeting_prep", "alert", "conversation", "slash_command", "follow_up_draft"]

def render():
    st.header("Message Activity")

    try:
        users = fetch_users()
    except Exception as e:
        st.error(f"Failed to load users: {e}")
        return

    users_df = pd.DataFrame(users) if users else pd.DataFrame(columns=["id", "email"])
    user_map = dict(zip(users_df["id"], users_df["email"])) if not users_df.empty else {}

    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        now = datetime.now(timezone.utc)
        date_range = st.date_input("Date range", value=(now - timedelta(days=7), now), max_value=now)
        if len(date_range) == 2:
            start_date, end_date = date_range
            start = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc).isoformat()
            end = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc).isoformat()
        else:
            start = (now - timedelta(days=7)).isoformat()
            end = now.isoformat()
    with col2:
        type_filter = st.multiselect("Message type", MESSAGE_TYPES, default=MESSAGE_TYPES)
    with col3:
        user_options = {"All Users": None}
        for _, row in users_df.iterrows():
            name = row["email"].split("@")[0].replace(".", " ").title() if pd.notna(row.get("email")) else row["id"]
            user_options[name] = row["id"]
        selected_user_label = st.selectbox("User", list(user_options.keys()))
        selected_user_id = user_options[selected_user_label]

    # Fetch messages
    try:
        with st.spinner("Loading messages..."):
            msgs = fetch_messages(start=start, end=end, user_id=selected_user_id)
    except Exception as e:
        st.error(f"Failed to load messages: {e}")
        return

    if not msgs:
        st.info("No messages found for this filter.")
        return

    msg_df = pd.DataFrame(msgs)
    msg_df = msg_df[msg_df["message_type"].isin(type_filter)] if "message_type" in msg_df.columns else msg_df

    if msg_df.empty:
        st.info("No messages match the selected filters.")
        return

    # KPI row
    total = len(msg_df)
    msg_df["date"] = pd.to_datetime(msg_df["sent_at"]).dt.date
    num_days = max((msg_df["date"].max() - msg_df["date"].min()).days, 1)
    avg_day = round(total / num_days, 1)
    active_users = msg_df["user_id"].nunique()

    try:
        convos = fetch_conversations()
        convo_df = pd.DataFrame(convos) if convos else pd.DataFrame(columns=["turn_count"])
        avg_turns = round(convo_df["turn_count"].mean(), 1) if not convo_df.empty and "turn_count" in convo_df.columns else 0
    except Exception:
        avg_turns = 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Messages", total)
    c2.metric("Avg/Day", avg_day)
    c3.metric("Active Users", active_users)
    c4.metric("Avg Turns/Convo", avg_turns)

    # Daily volume chart
    st.subheader("Daily Volume")
    daily = msg_df.groupby(["date", "message_type"]).size().reset_index(name="count")
    fig = px.bar(daily, x="date", y="count", color="message_type", barmode="stack",
                 labels={"date": "Date", "count": "Messages", "message_type": "Type"})
    fig.update_layout(height=350, margin=dict(t=10, b=40))
    st.plotly_chart(fig, use_container_width=True)

    # Type breakdown
    col_pie, col_table = st.columns(2)
    with col_pie:
        type_counts = msg_df["message_type"].value_counts()
        fig2 = px.pie(values=type_counts.values, names=type_counts.index, title="Distribution by Type")
        fig2.update_layout(height=300, margin=dict(t=40, b=10))
        st.plotly_chart(fig2, use_container_width=True)
    with col_table:
        type_summary = type_counts.reset_index()
        type_summary.columns = ["Type", "Count"]
        type_summary["% of Total"] = (type_summary["Count"] / total * 100).round(1)
        st.dataframe(type_summary, use_container_width=True, hide_index=True)

    # Message Inspector (when user is selected)
    if selected_user_id:
        st.markdown("---")
        st.subheader(f"Message Inspector — {selected_user_label}")
        _render_inspector(msg_df, selected_user_id)


def _render_inspector(msg_df, user_id):
    """Render message inspector for a specific user."""
    user_msgs = msg_df[msg_df["user_id"] == user_id].sort_values("sent_at", ascending=False)

    if user_msgs.empty:
        st.info("No messages for this user in the selected range.")
        return

    # Pagination
    page_size = 20
    total_msgs = len(user_msgs)
    total_pages = max(1, (total_msgs + page_size - 1) // page_size)
    page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1)
    start_idx = (page - 1) * page_size
    page_msgs = user_msgs.iloc[start_idx:start_idx + page_size]

    st.caption(f"Showing {start_idx + 1}–{min(start_idx + page_size, total_msgs)} of {total_msgs} messages")

    for _, msg in page_msgs.iterrows():
        direction = msg.get("direction", "outbound")
        is_inbound = direction == "inbound"
        icon = "🗣️" if is_inbound else "🤖"
        label = "User Prompt" if is_inbound else "Assistant Response"
        msg_type = msg.get("message_type", "unknown")
        timestamp = str(msg.get("sent_at", ""))[:19].replace("T", " ")
        content = msg.get("content", "") or ""

        with st.container():
            col_icon, col_body = st.columns([1, 20])
            with col_icon:
                st.write(icon)
            with col_body:
                st.markdown(f"**{label}** · `{msg_type}` · {timestamp}")
                with st.expander(content[:200] + ("..." if len(content) > 200 else ""), expanded=False):
                    st.text(content)
                    metadata = msg.get("metadata")
                    if metadata:
                        st.json(metadata)
        st.markdown("<hr style='margin: 4px 0; border-color: #333;'>", unsafe_allow_html=True)
