import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta, timezone
from admin.data.supabase_client import fetch_feature_usage, fetch_feature_catalog, fetch_education_log, fetch_users

def render():
    st.header("Feature Usage")

    now = datetime.now(timezone.utc)
    week_ago = (now - timedelta(days=7)).isoformat()

    try:
        with st.spinner("Loading feature data..."):
            usage = fetch_feature_usage()
            catalog = fetch_feature_catalog()
            edu_log = fetch_education_log(start=week_ago)
            users = fetch_users()
    except Exception as e:
        st.error(f"Failed to load feature data: {e}")
        return

    catalog_map = {f["id"]: f["display_name"] for f in catalog} if catalog else {}
    onboarded = [u for u in (users or []) if u.get("onboarding_state") == "complete"]
    num_onboarded = max(len(onboarded), 1)

    usage_df = pd.DataFrame(usage) if usage else pd.DataFrame(columns=["user_id", "feature_id", "use_count"])
    edu_df = pd.DataFrame(edu_log) if edu_log else pd.DataFrame(columns=["feature_id"])

    # KPI row
    features_adopted = usage_df[usage_df["use_count"] > 0]["feature_id"].nunique() if not usage_df.empty else 0
    user_feature_counts = usage_df[usage_df["use_count"] > 0].groupby("user_id")["feature_id"].nunique() if not usage_df.empty else pd.Series(dtype=int)
    avg_per_user = round(user_feature_counts.mean(), 1) if not user_feature_counts.empty else 0
    tips_sent = len(edu_df)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Features Adopted", features_adopted)
    c2.metric("Avg Features/User", avg_per_user)
    c3.metric("Tips Sent (7d)", tips_sent)
    c4.metric("Tip→Use Conversion", "—")  # Complex calc, placeholder

    # Feature adoption bar chart
    st.subheader("Feature Adoption Rate")
    if not usage_df.empty and catalog:
        adoption_data = []
        for feat_id, display in catalog_map.items():
            users_using = usage_df[(usage_df["feature_id"] == feat_id) & (usage_df["use_count"] > 0)]["user_id"].nunique()
            rate = round(users_using / num_onboarded * 100, 1)
            adoption_data.append({"Feature": display, "Adoption %": rate, "Users": users_using})
        adoption_df = pd.DataFrame(adoption_data).sort_values("Adoption %", ascending=True)
        fig = px.bar(adoption_df, x="Adoption %", y="Feature", orientation="h",
                     text="Users", color="Adoption %",
                     color_continuous_scale=["#1e293b", "#3b82f6"])
        fig.update_layout(height=max(250, len(adoption_data) * 30), margin=dict(t=10, b=10, l=150))
        fig.update_coloraxes(showscale=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No feature usage data yet.")

    # Education effectiveness table
    st.subheader("Education Effectiveness")
    if not edu_df.empty:
        edu_summary = edu_df.groupby("feature_id").size().reset_index(name="Tips Sent")
        edu_summary["Feature"] = edu_summary["feature_id"].map(catalog_map).fillna("Unknown")
        st.dataframe(edu_summary[["Feature", "Tips Sent"]].sort_values("Tips Sent", ascending=False),
                     use_container_width=True, hide_index=True)
    else:
        st.info("No education tips sent in the last 7 days.")

    # Raw usage table
    st.subheader("Usage Details")
    if not usage_df.empty:
        usage_df["Feature"] = usage_df["feature_id"].map(catalog_map).fillna(usage_df["feature_id"])
        user_email_map = {u["id"]: u.get("email", "—") for u in (users or [])}
        usage_df["User"] = usage_df["user_id"].map(user_email_map).fillna("Unknown")
        display = usage_df[usage_df["use_count"] > 0][["User", "Feature", "use_count", "first_used_at", "last_used_at"]].copy()
        display.columns = ["User", "Feature", "Uses", "First Used", "Last Used"]
        st.dataframe(display.sort_values("Uses", ascending=False), use_container_width=True, hide_index=True)
    else:
        st.info("No feature usage recorded yet.")
