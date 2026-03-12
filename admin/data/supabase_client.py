import streamlit as st
from supabase import create_client
from admin.config import SUPABASE_URL, SUPABASE_SERVICE_KEY

@st.cache_resource
def get_client():
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

@st.cache_data(ttl=60)
def fetch_table(table_name, select="*", filters=None, order=None, limit=None):
    """Generic fetch with optional filters.

    filters: list of (column, operator, value) tuples
        operators: eq, neq, gt, gte, lt, lte
    """
    client = get_client()
    query = client.table(table_name).select(select)
    if filters:
        for col, op, val in filters:
            query = getattr(query, op)(col, val)
    if order:
        col, asc = order
        query = query.order(col, desc=not asc)
    if limit:
        query = query.limit(limit)
    result = query.execute()
    return result.data

def fetch_users():
    return fetch_table("users")

def fetch_messages(start=None, end=None, user_id=None, message_type=None):
    filters = []
    if start:
        filters.append(("sent_at", "gte", start))
    if end:
        filters.append(("sent_at", "lte", end))
    if user_id:
        filters.append(("user_id", "eq", user_id))
    if message_type:
        filters.append(("message_type", "eq", message_type))
    return fetch_table("messages", filters=filters, order=("sent_at", False))

def fetch_alert_history(start=None, end=None):
    filters = []
    if start:
        filters.append(("created_at", "gte", start))
    if end:
        filters.append(("created_at", "lte", end))
    return fetch_table("alert_history", filters=filters)

def fetch_alert_types():
    return fetch_table("alert_types")

def fetch_muted_alerts():
    return fetch_table("muted_alerts")

def fetch_feature_usage():
    return fetch_table("feature_usage")

def fetch_feature_catalog():
    return fetch_table("feature_catalog")

def fetch_education_log(start=None, end=None):
    filters = []
    if start:
        filters.append(("created_at", "gte", start))
    if end:
        filters.append(("created_at", "lte", end))
    return fetch_table("education_log", filters=filters)

def fetch_pending_actions(user_id=None):
    filters = []
    if user_id:
        filters.append(("user_id", "eq", user_id))
    return fetch_table("pending_actions", filters=filters)

def fetch_conversations(user_id=None):
    filters = []
    if user_id:
        filters.append(("user_id", "eq", user_id))
    return fetch_table("conversations", filters=filters)
