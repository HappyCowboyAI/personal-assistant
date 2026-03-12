# Admin & Analytics Dashboard Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local Streamlit admin dashboard with 6 pages: System Health, User Adoption, Message Activity, Alert Performance, Feature Usage, and User Explorer.

**Architecture:** Python Streamlit app with sidebar navigation. Data layer uses `supabase-py` for DB queries and `requests` for n8n REST API. All cross-table aggregation done in pandas. Charts via Plotly.

**Tech Stack:** Python 3.11+, Streamlit 1.33+, supabase-py 2.0+, Plotly 5.18+, pandas 2.0+, python-dotenv 1.0+

**Spec:** `docs/superpowers/specs/2026-03-11-admin-dashboard-design.md`

---

## Chunk 1: Foundation — Config, Data Layer, Shell App

### Task 1: Project scaffolding and dependencies

**Files:**
- Create: `admin/requirements.txt`
- Create: `admin/.env.example`
- Create: `admin/.gitignore`

- [ ] **Step 1: Create requirements.txt**

```
streamlit>=1.33
supabase>=2.0
plotly>=5.18
pandas>=2.0
python-dotenv>=1.0
requests>=2.31
```

- [ ] **Step 2: Create .env.example (no real secrets)**

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-role-key
N8N_URL=https://your-n8n-instance.com
N8N_API_KEY=your-n8n-api-key
```

- [ ] **Step 3: Create admin/.gitignore**

```
.env
__pycache__/
```

- [ ] **Step 4: Create the real .env with credentials**

Copy `.env.example` to `.env` and fill in real values. This file is gitignored.

- [ ] **Step 5: Install dependencies**

Run: `pip install -r admin/requirements.txt`

- [ ] **Step 6: Commit**

```bash
git add admin/requirements.txt admin/.env.example admin/.gitignore
git commit -m "feat(admin): scaffold admin dashboard with dependencies"
```

---

### Task 2: Config module

**Files:**
- Create: `admin/config.py`

- [ ] **Step 1: Write config.py**

```python
from dotenv import load_dotenv
import os

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
N8N_URL = os.environ["N8N_URL"]
N8N_API_KEY = os.environ["N8N_API_KEY"]
```

- [ ] **Step 2: Verify config loads**

Run: `python -c "import admin.config; print('OK:', admin.config.SUPABASE_URL[:30])"`
Expected: `OK: https://rhrlnkbphxntxxxcr`

- [ ] **Step 3: Commit**

```bash
git add admin/config.py
git commit -m "feat(admin): add config module loading from .env"
```

---

### Task 3: Supabase data client

**Files:**
- Create: `admin/data/__init__.py`
- Create: `admin/data/supabase_client.py`

- [ ] **Step 1: Create __init__.py**

Empty file.

- [ ] **Step 2: Write supabase_client.py**

```python
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
    order: (column, ascending) tuple
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
```

- [ ] **Step 3: Verify Supabase client connects**

Run: `python -c "from admin.data.supabase_client import fetch_users; print(len(fetch_users()), 'users')"`
Expected: prints user count (e.g., `14 users`)

- [ ] **Step 4: Commit**

```bash
git add admin/data/__init__.py admin/data/supabase_client.py
git commit -m "feat(admin): add Supabase data client with cached queries"
```

---

### Task 4: n8n API client

**Files:**
- Create: `admin/data/n8n_client.py`

- [ ] **Step 1: Write n8n_client.py**

```python
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
    started_after = (datetime.now(timezone.utc) - timedelta(hours=hours_back)).isoformat()
    params = {"limit": limit, "startedAfter": started_after}
    if status:
        params["status"] = status

    all_executions = []
    resp = requests.get(f"{N8N_URL}/api/v1/executions", headers=HEADERS, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    all_executions.extend(data.get("data", []))

    # Paginate if needed
    while data.get("nextCursor"):
        params["cursor"] = data["nextCursor"]
        resp = requests.get(f"{N8N_URL}/api/v1/executions", headers=HEADERS, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        all_executions.extend(data.get("data", []))

    return all_executions

def get_workflow_name_map():
    """Returns {workflow_id: workflow_name} dict."""
    workflows = fetch_workflows()
    return {w["id"]: w["name"] for w in workflows}
```

- [ ] **Step 2: Verify n8n client connects**

Run: `python -c "from admin.data.n8n_client import fetch_workflows; wfs = fetch_workflows(); print(len(wfs), 'workflows')"`
Expected: prints workflow count (e.g., `14 workflows`)

- [ ] **Step 3: Commit**

```bash
git add admin/data/n8n_client.py
git commit -m "feat(admin): add n8n API client with pagination"
```

---

### Task 5: Dashboard shell with sidebar navigation

**Files:**
- Create: `admin/__init__.py`
- Create: `admin/dashboard.py`
- Create: `admin/pages/__init__.py`
- Create: `admin/pages/health.py` (stub)
- Create: `admin/pages/adoption.py` (stub)
- Create: `admin/pages/messages.py` (stub)
- Create: `admin/pages/alerts.py` (stub)
- Create: `admin/pages/features.py` (stub)
- Create: `admin/pages/user_explorer.py` (stub)

- [ ] **Step 1: Create __init__.py files**

Empty files for `admin/__init__.py` and `admin/pages/__init__.py`.

- [ ] **Step 2: Create page stubs**

Each page file follows this pattern (example for health.py):

```python
import streamlit as st

def render():
    st.header("System Health")
    st.info("Coming soon...")
```

Create all 6 page files with the same pattern, updating the header text:
- `health.py`: "System Health"
- `adoption.py`: "User Adoption"
- `messages.py`: "Message Activity"
- `alerts.py`: "Alert Performance"
- `features.py`: "Feature Usage"
- `user_explorer.py`: "User Explorer"

- [ ] **Step 3: Write dashboard.py**

```python
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
```

- [ ] **Step 4: Verify the app launches**

Run: `cd /Users/scottmetcalf/projects/oppassistant && streamlit run admin/dashboard.py`
Expected: Browser opens with sidebar showing 6 pages, each showing "Coming soon..."

- [ ] **Step 5: Commit**

```bash
git add admin/__init__.py admin/dashboard.py admin/pages/
git commit -m "feat(admin): add dashboard shell with sidebar navigation and page stubs"
```

---

## Chunk 2: System Health Page

### Task 6: System Health — KPIs and workflow status

**Files:**
- Modify: `admin/pages/health.py`

- [ ] **Step 1: Implement health.py**

```python
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
```

- [ ] **Step 2: Test the page**

Run: `streamlit run admin/dashboard.py`
Navigate to System Health. Verify KPI cards, workflow table, errors table, and execution chart render with live data.

- [ ] **Step 3: Commit**

```bash
git add admin/pages/health.py
git commit -m "feat(admin): implement System Health page with KPIs, workflow table, errors, volume chart"
```

---

## Chunk 3: User Adoption Page

### Task 7: User Adoption — funnel, table, personalization stats

**Files:**
- Modify: `admin/pages/adoption.py`

- [ ] **Step 1: Implement adoption.py**

```python
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
```

- [ ] **Step 2: Test the page**

Run: `streamlit run admin/dashboard.py`
Navigate to User Adoption. Verify funnel, users table with filters, personalization stats render.

- [ ] **Step 3: Commit**

```bash
git add admin/pages/adoption.py
git commit -m "feat(admin): implement User Adoption page with funnel, table, personalization stats"
```

---

## Chunk 4: Message Activity Page with Inspector

### Task 8: Message Activity — volume, breakdown, and message inspector

**Files:**
- Modify: `admin/pages/messages.py`

- [ ] **Step 1: Implement messages.py**

```python
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
```

- [ ] **Step 2: Test the page**

Run: `streamlit run admin/dashboard.py`
Navigate to Message Activity. Test: date range filter, type filter, user selector. When a user is selected, verify Message Inspector shows with expand/collapse.

- [ ] **Step 3: Commit**

```bash
git add admin/pages/messages.py
git commit -m "feat(admin): implement Message Activity page with inspector drill-down"
```

---

## Chunk 5: Alert Performance Page

### Task 9: Alert Performance — volume, response rates, mutes

**Files:**
- Modify: `admin/pages/alerts.py`

- [ ] **Step 1: Implement alerts.py**

```python
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
```

- [ ] **Step 2: Test the page**

Run: `streamlit run admin/dashboard.py`
Navigate to Alert Performance. Verify KPIs, severity chart, funnel, type table, mute table render.

- [ ] **Step 3: Commit**

```bash
git add admin/pages/alerts.py
git commit -m "feat(admin): implement Alert Performance page with funnel and mute patterns"
```

---

## Chunk 6: Feature Usage Page

### Task 10: Feature Usage — adoption, education effectiveness

**Files:**
- Modify: `admin/pages/features.py`

- [ ] **Step 1: Implement features.py**

```python
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
```

- [ ] **Step 2: Test the page**

Run: `streamlit run admin/dashboard.py`
Navigate to Feature Usage. Verify adoption bar chart, education table, usage details.

- [ ] **Step 3: Commit**

```bash
git add admin/pages/features.py
git commit -m "feat(admin): implement Feature Usage page with adoption chart and education tracking"
```

---

## Chunk 7: User Explorer Page

### Task 11: User Explorer — profile, activity timeline, feature usage

**Files:**
- Modify: `admin/pages/user_explorer.py`

- [ ] **Step 1: Implement user_explorer.py**

```python
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
```

- [ ] **Step 2: Test the page**

Run: `streamlit run admin/dashboard.py`
Navigate to User Explorer. Select a user, verify profile card, KPIs, sparkline, timeline, feature table.

- [ ] **Step 3: Commit**

```bash
git add admin/pages/user_explorer.py
git commit -m "feat(admin): implement User Explorer page with profile, timeline, feature usage"
```

---

## Chunk 8: Final Polish

### Task 12: Add .superpowers to .gitignore

**Files:**
- Modify: `.gitignore` (project root)

- [ ] **Step 1: Add .superpowers/ to .gitignore if not present**

Append to `.gitignore`:
```
.superpowers/
```

- [ ] **Step 2: Commit**

```bash
git add .gitignore
git commit -m "chore: add .superpowers/ to gitignore"
```

---

### Task 13: End-to-end verification

- [ ] **Step 1: Launch the dashboard**

Run: `cd /Users/scottmetcalf/projects/oppassistant && streamlit run admin/dashboard.py`

- [ ] **Step 2: Verify each page loads without errors**

Navigate through all 6 pages:
1. System Health — KPIs, workflow table, errors, chart
2. User Adoption — funnel, table with filters, personalization
3. Message Activity — filters, volume chart, type breakdown, inspector
4. Alert Performance — KPIs, severity chart, funnel, type table, mutes
5. Feature Usage — adoption chart, education table, usage details
6. User Explorer — profile, timeline, features

- [ ] **Step 3: Test manual refresh**

Click "Refresh Data" in sidebar. Verify data reloads.

- [ ] **Step 4: Final commit if any fixes needed**

```bash
git add -A admin/
git commit -m "feat(admin): complete admin dashboard with all 6 pages"
```
