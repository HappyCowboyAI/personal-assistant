# Admin & Analytics Dashboard — Design Spec

**Date:** 2026-03-11
**Status:** Draft

## Overview

A local Streamlit dashboard for monitoring the OppAssistant platform — operational health, user adoption, message activity, alert performance, feature usage, and per-user drill-downs. Runs on localhost, queries Supabase directly with service role key. No external deployment.

## Audiences

- **Now:** Super-admin (Scott) — full visibility across all users, workflows, and data
- **Later:** Customer admins — org-scoped view of their users' engagement (deferred, not in this spec)

## Tech Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Framework | **Streamlit** | Python-native, zero build step, good for data dashboards. Already using Python for scripts. |
| Data | **Supabase Python client** (`supabase-py`) | Direct queries with service role key. All data already in Supabase. |
| n8n Health | **n8n REST API** | `/api/v1/workflows` and `/api/v1/executions` for workflow status and error history. |
| Charts | **Plotly** via `st.plotly_chart` | Richer than native Streamlit charts. Stacked bars, funnels, time series. |
| Layout | **Sidebar navigation** | `st.sidebar` with page selector. Persistent left nav with 6 pages. |
| Run command | `streamlit run admin/dashboard.py` | Single entry point, all pages as functions or separate files in `admin/pages/`. |

## Project Structure

```
admin/
├── dashboard.py          # Entry point — sidebar nav, page routing
├── config.py             # Supabase + n8n credentials, constants
├── pages/
│   ├── health.py         # System Health page
│   ├── adoption.py       # User Adoption page
│   ├── messages.py       # Message Activity page
│   ├── alerts.py         # Alert Performance page
│   ├── features.py       # Feature Usage page
│   └── user_explorer.py  # User Explorer page
├── data/
│   ├── supabase_client.py  # Shared Supabase connection
│   └── n8n_client.py       # n8n API client (workflow status, executions)
└── requirements.txt      # streamlit, supabase, plotly, pandas
```

## Page Designs

### Page 1: System Health

**Purpose:** Is everything working? Operational status at a glance.

**Data sources:**
- n8n REST API: `GET /api/v1/workflows` (active status, names)
- n8n REST API: `GET /api/v1/executions?limit=100&status=error` (recent failures)
- n8n REST API: `GET /api/v1/executions?limit=500` (execution counts by workflow)
- Supabase: `messages` table count for last 24h

**Layout:**
1. **KPI row** (4 metric cards):
   - Active Workflows (count of active / total)
   - Executions (24h) (total successful executions)
   - Errors (24h) (failed executions count, red if > 0)
   - Messages Delivered (24h) (count from messages table)

2. **Workflow Status table:**
   - Columns: Workflow Name, Status (Active/Inactive), Last Execution Time, Last Status (Success/Error)
   - Color-coded status indicators
   - Sorted by last execution time (most recent first)

3. **Recent Errors table:**
   - Columns: Workflow, Error Message, Execution ID, Timestamp
   - Last 20 errors
   - Each row links to n8n execution URL (clickable)

4. **Execution volume chart:**
   - Stacked bar chart: executions per hour over last 24h, colored by workflow
   - Helps spot scheduling gaps or unusual patterns

**Refresh:** Auto-refresh via `st.fragment(run_every=timedelta(seconds=60))` on the System Health page. Manual refresh button on all pages.

### Page 2: User Adoption

**Purpose:** Are people onboarding and staying active?

**Data sources:**
- Supabase: `users` table (all fields)
- Supabase: `messages` table (last message per user for "last active" calculation)

**Layout:**
1. **KPI row:**
   - Total Users
   - Onboarded (onboarding_state = 'complete')
   - Active This Week (users with messages in last 7 days)
   - Drop-off Rate (% stuck in awaiting_name or awaiting_emoji > 7 days)

2. **Onboarding Funnel:**
   - Horizontal bar chart or funnel: new → awaiting_name → awaiting_emoji → complete
   - Shows count at each stage

3. **Users table:**
   - Columns: Name (from email), Email, State, Assistant Name, Digest Scope, Focus, Last Active
   - Sortable by any column
   - Color-coded state badges
   - Filterable by onboarding_state, digest_scope
   - Click a user row → navigates to User Explorer with that user pre-selected

4. **Personalization stats:**
   - % with custom assistant name
   - % with custom emoji
   - % with custom persona
   - Distribution of digest_scope values (pie or bar)

### Page 3: Message Activity

**Purpose:** What's the assistant producing? Volume trends, type breakdown, content inspection.

**Data sources:**
- Supabase: `messages` table
- Supabase: `conversations` table (for multi-turn metrics)

**Layout:**
1. **Filters bar:**
   - Date range picker (default: last 7 days)
   - Message type multi-select (digest, meeting_prep, alert, conversation, slash_command, follow_up_draft)
   - User selector (dropdown of all users, default: All)

2. **KPI row:**
   - Total Messages (filtered)
   - Avg/Day
   - Active Users (distinct user_ids in filtered range)
   - Avg Turns/Conversation (from conversations table)

3. **Daily Volume chart:**
   - Stacked bar chart: message count per day, colored by message_type
   - Time series with Plotly for hover details

4. **Type breakdown:**
   - Pie or donut chart: message distribution by type
   - Table: type, count, % of total

5. **Message Inspector** (detail drill-down):
   - Activated when a specific user is selected in the filter
   - Shows chronological list of messages for that user
   - Each message card shows:
     - Direction indicator: 🗣️ User Prompt (inbound) or 🤖 Assistant Response (outbound)
     - Message type badge (digest, meeting_prep, conversation, etc.)
     - Timestamp
     - Content preview (first 200 chars, expandable to full content)
     - Metadata JSON viewer (expandable)
   - Grouped by conversation_id when available (shows prompt → response threads)
   - Pagination or infinite scroll for users with many messages

### Page 4: Alert Performance

**Purpose:** Are alerts helping reps? What gets acted on vs ignored?

**Data sources:**
- Supabase: `alert_history` table
- Supabase: `alert_types` table (for display names)
- Supabase: `muted_alerts` table
- Supabase: `user_alert_preferences` table

**Layout:**
1. **KPI row:**
   - Total Alerts (7 days)
   - Response Rate (% with status = acknowledged or acted)
   - Avg Time to Action (delivered_at → resolved_at)
   - Active Mutes (count of unmuted_at IS NULL)

2. **Alert volume chart:**
   - Bar chart: alerts per day, colored by severity (info/warning/critical)
   - Filterable by alert type

3. **Response funnel:**
   - Funnel visualization: delivered → acknowledged → acted (vs dismissed/expired)
   - Per alert type breakdown

4. **Alert type table:**
   - Columns: Alert Type, Count (7d), Acted %, Dismissed %, Avg Response Time
   - Highlights which alert types drive action vs get ignored

5. **Mute patterns:**
   - Table of active mutes: User, Alert Type, Entity, Mute Reason, Muted Since
   - Helps identify if users are muting too aggressively

### Page 5: Feature Usage

**Purpose:** Which features are being adopted? Is education working?

**Data sources:**
- Supabase: `feature_usage` table
- Supabase: `feature_catalog` table
- Supabase: `education_log` table

**Layout:**
1. **KPI row:**
   - Features Adopted (distinct features with use_count > 0 across all users)
   - Avg Features/User
   - Education Tips Sent (7 days)
   - Tip → Usage Conversion (% of educated features that get used within 7 days)

2. **Feature adoption grid:**
   - Heatmap or bar chart: each feature × adoption rate (% of onboarded users who've used it)
   - Sorted by adoption rate
   - Color intensity = use_count depth

3. **Education effectiveness:**
   - Table: Feature, Tips Sent, First Use Within 7d, Conversion %
   - Shows which drip education actually drives adoption

4. **Time-to-first-use:**
   - Distribution chart: days from onboarding_complete to first use, per feature
   - Identifies which features users discover naturally vs need prompting

### Page 6: User Explorer

**Purpose:** Deep-dive into any single user's complete profile and activity.

**Data sources:**
- Supabase: `users` table (profile)
- Supabase: `messages` table (activity feed)
- Supabase: `alert_history` table (alerts received)
- Supabase: `pending_actions` table (draft approvals)
- Supabase: `feature_usage` table (features used)
- Supabase: `education_log` table (tips received)
- Supabase: `conversations` table (conversation history)

**Layout:**
1. **User selector:** Dropdown at top to pick a user

2. **Profile card:**
   - Name, email, Slack ID, assistant name/emoji/persona
   - Onboarding state, digest_scope, focus, timezone
   - Preferences: digest_enabled, meeting_prep_enabled, followup_enabled, tips_enabled
   - Created at, last active

3. **Activity summary:**
   - KPI cards: Messages (7d), Alerts (7d), Drafts Approved/Rejected, Features Used
   - Mini sparkline of daily message count (last 30 days)

4. **Activity timeline:**
   - Chronological feed of all interactions: messages sent, alerts received, drafts actioned, features used
   - Each item shows type icon, timestamp, preview
   - Expandable content
   - Filterable by activity type

5. **Feature usage profile:**
   - Table: Feature, First Used, Last Used, Use Count
   - Shows which features this specific user has adopted

## Data Access Patterns

### Supabase Queries

All queries use the Supabase Python client with service role key (bypasses RLS):

```python
from supabase import create_client
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
```

Key query patterns:
- **Messages by date range:** `supabase.table('messages').select('*').gte('sent_at', start).lte('sent_at', end)`
- **Messages by user:** Add `.eq('user_id', user_id)`
- **Users with last active:** Fetch users and messages separately, compute max(sent_at) per user in pandas. `supabase-py` does not support SQL JOINs — all cross-table aggregations are done in Python with pandas after fetching each table.
- **Alert response rates:** Fetch `alert_history`, group by status in pandas, calculate percentages
- **Feature adoption:** Fetch `feature_usage` and `users` separately, merge in pandas on user_id, filter to onboarding_state='complete', count distinct features

**Important:** `supabase-py` is a PostgREST client — it supports filters, ordering, and pagination but NOT SQL JOINs or GROUP BY. All aggregation and cross-table logic happens in Python with pandas DataFrames after fetching raw rows.

### n8n API Queries

```python
import requests
headers = {"X-N8N-API-KEY": N8N_API_KEY}

# Workflows (returns all, no pagination needed)
workflows = requests.get(f"{N8N_URL}/api/v1/workflows", headers=headers).json()

# Executions — paginate with cursor. n8n returns max 250 per request.
# Use startedAfter/startedBefore ISO params to filter by time range.
executions = requests.get(
    f"{N8N_URL}/api/v1/executions",
    headers=headers,
    params={"limit": 250, "status": "error", "startedAfter": "2026-03-11T00:00:00Z"}
).json()
# If response has nextCursor, fetch next page with &cursor=<value>
```

### Caching

- Use `@st.cache_data(ttl=60)` for Supabase queries (1 minute cache)
- Use `@st.cache_data(ttl=30)` for n8n API calls (30 second cache)
- Manual refresh button clears all caches via `st.cache_data.clear()`

### Auto-Refresh

Use `st.fragment(run_every=timedelta(seconds=60))` (Streamlit 1.33+) for the System Health page auto-refresh. Other pages use manual refresh only.

## Empty States & Error Handling

- All pages show a centered `st.info("No data yet — ...")` message when queries return empty results
- API connection failures (Supabase or n8n) show `st.error()` with exception message and a retry button
- Loading states use `st.spinner("Loading...")` context manager around data fetches
- n8n API errors (e.g., 401, 500) are caught and shown inline, don't crash the page

## Message Inspector — Direction Handling

The `messages.direction` column tracks inbound (user prompts) and outbound (assistant responses). Inbound messages are logged by the Slack Events Handler when users send DMs. If a user's conversation messages only have outbound entries, the inspector shows them as assistant-initiated (digests, alerts, briefs) without a prompt above. Conversations with both directions show the prompt → response threading.

## Configuration

All credentials loaded from environment variables via `python-dotenv`. No hardcoded secrets in code.

```python
# admin/config.py
from dotenv import load_dotenv
import os

load_dotenv()  # loads .env file

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
N8N_URL = os.environ["N8N_URL"]
N8N_API_KEY = os.environ["N8N_API_KEY"]
```

The `.env` file (gitignored) contains:
```
SUPABASE_URL=https://rhrlnkbphxntxxxcrgvv.supabase.co
SUPABASE_SERVICE_KEY=<service-role-key>
N8N_URL=https://scottai.trackslife.com
N8N_API_KEY=<api-key>
```

## Security

- Runs on localhost only — no external access
- Service role key stored in `.env` file (gitignored)
- No authentication needed (local dev tool)
- Customer admin auth deferred to future phase

## Dependencies

```
streamlit>=1.33
supabase>=2.0
plotly>=5.18
pandas>=2.0
python-dotenv>=1.0
```

## Future Considerations (Out of Scope)

- Customer admin portal with org-scoped views and Slack SSO
- Real-time WebSocket updates from Supabase
- Export to CSV/PDF
- Alerting rules (e.g., Slack notification when error rate spikes)
- A/B test tracking for prompt variants
- Cost tracking (Anthropic API usage per message)
