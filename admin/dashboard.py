import streamlit as st

st.set_page_config(
    page_title="OppAssistant Admin",
    page_icon="📊",
    layout="wide",
)

from admin.pages import health, adoption, messages, alerts, features, user_explorer

PAGES = {
    "System Health": health,
    "User Adoption": adoption,
    "Message Activity": messages,
    "Alert Performance": alerts,
    "Feature Usage": features,
    "User Explorer": user_explorer,
}

st.sidebar.title("OppAssistant Admin")
st.sidebar.markdown("---")
selection = st.sidebar.radio("Navigate", list(PAGES.keys()), label_visibility="collapsed")

# Manual refresh button
if st.sidebar.button("Refresh Data"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.caption("Local admin dashboard")

PAGES[selection].render()
