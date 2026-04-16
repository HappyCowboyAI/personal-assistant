# GitHub Pages Admin Guide — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and deploy a Backstory-branded customer-facing admin deployment guide as a Docsify site on GitHub Pages.

**Architecture:** Docsify (client-side markdown renderer) served from `docs/site/` via GitHub Actions. Custom CSS applies Backstory brand tokens. Eight markdown pages adapted from existing documentation with all credentials scrubbed to placeholders.

**Tech Stack:** Docsify 4.x, GitHub Pages, GitHub Actions, CSS custom properties, HTML

**Spec:** `docs/superpowers/specs/2026-04-16-github-pages-admin-guide-design.md`

---

### Task 1: Scaffold Site Directory and Docsify Loader

**Files:**
- Create: `docs/site/index.html`
- Create: `docs/site/.nojekyll`

- [ ] **Step 1: Create the `.nojekyll` file**

Create an empty file to prevent GitHub Pages from running Jekyll processing:

```
docs/site/.nojekyll
```

(Empty file — no content needed.)

- [ ] **Step 2: Create the Docsify `index.html` loader**

Create `docs/site/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Backstory — Admin Guide</title>
  <meta name="description" content="Deployment guide for the People.ai Personal Assistant">
  <!-- Docsify base theme -->
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/docsify@4/lib/themes/vue.css">
  <!-- Backstory brand overrides -->
  <link rel="stylesheet" href="css/backstory.css">
  <!-- Favicon -->
  <link rel="icon" href="assets/books-icon-dark.png" type="image/png">
</head>
<body>
  <div id="app">Loading...</div>
  <script>
    window.$docsify = {
      name: 'Admin Guide',
      logo: 'assets/wordmark-dark.png',
      loadSidebar: true,
      subMaxLevel: 2,
      search: {
        placeholder: 'Search...',
        noData: 'No results.',
        depth: 3
      },
      auto2top: true,
      coverpage: true,
      notFoundPage: true,
      themeable: {
        readyTransition: true
      }
    };
  </script>
  <!-- Docsify core -->
  <script src="https://cdn.jsdelivr.net/npm/docsify@4"></script>
  <!-- Plugins -->
  <script src="https://cdn.jsdelivr.net/npm/docsify@4/lib/plugins/search.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/docsify-copy-code@2"></script>
</body>
</html>
```

- [ ] **Step 3: Verify directory structure**

Run: `ls -la docs/site/`

Expected: `index.html` and `.nojekyll` present.

- [ ] **Step 4: Commit**

```bash
git add docs/site/index.html docs/site/.nojekyll
git commit -m "feat(docs): scaffold Docsify site with index.html and .nojekyll"
```

---

### Task 2: Backstory Brand CSS Theme

**Files:**
- Create: `docs/site/css/backstory.css`

- [ ] **Step 1: Create the custom theme CSS**

Create `docs/site/css/backstory.css`:

```css
/* ==========================================================
   Backstory Brand Theme for Docsify
   Based on Backstory Brand Guidelines v2.0 (March 2026)
   ========================================================== */

/* --- Brand Tokens --- */
:root {
  /* Primary */
  --bs-black: #000000;
  --bs-graphite: #171721;
  --bs-surface-gray: #BBBCBC;
  --bs-horizon: #6296AD;
  --bs-white: #FFFFFF;

  /* Secondary */
  --bs-plum: #B08FA2;
  --bs-mint: #8FCDA8;
  --bs-cinder: #C05527;
  --bs-indigo: #275198;
  --bs-cobalt: #21B5FF;

  /* Functional */
  --bs-code-bg: #F5F5F6;
  --bs-tip-bg: rgba(98, 150, 173, 0.1);
  --bs-warn-bg: rgba(192, 85, 39, 0.1);

  /* Docsify theme variable overrides */
  --theme-color: var(--bs-horizon);
  --sidebar-background: var(--bs-graphite);
  --sidebar-nav-link-color: rgba(255, 255, 255, 0.75);
  --sidebar-nav-link-color--active: var(--bs-white);
  --sidebar-nav-link-color--hover: var(--bs-white);
  --sidebar-nav-link-border-color--active: var(--bs-horizon);
  --text-color-base: var(--bs-graphite);
  --heading-color: var(--bs-black);
  --link-color: var(--bs-horizon);
  --link-color--hover: #4a7a90;
  --code-inline-color: var(--bs-cinder);
  --code-inline-background: var(--bs-code-bg);
  --blockquote-border-color: var(--bs-horizon);
  --notice-tip-border-color: var(--bs-horizon);
}

/* --- Typography --- */
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
}

.markdown-section h1,
.markdown-section h2,
.markdown-section h3 {
  font-family: Georgia, 'Times New Roman', serif;
  font-weight: 400;
  letter-spacing: -0.02em;
}

.markdown-section h1 {
  font-size: 2.2rem;
  border-bottom: 2px solid var(--bs-horizon);
  padding-bottom: 0.4rem;
}

.markdown-section h2 {
  font-size: 1.6rem;
  border-bottom: 1px solid var(--bs-surface-gray);
  padding-bottom: 0.3rem;
}

.markdown-section h3 {
  font-size: 1.25rem;
}

.markdown-section code,
.markdown-section pre {
  font-family: 'Chivo Mono', 'Fira Mono', 'Courier New', monospace;
}

/* --- Sidebar --- */
.sidebar {
  background: var(--bs-graphite);
  color: var(--bs-white);
}

.sidebar .sidebar-nav {
  padding-top: 1rem;
}

.sidebar .sidebar-nav a {
  color: rgba(255, 255, 255, 0.75);
  font-size: 0.95rem;
  padding: 6px 16px;
  display: block;
  transition: color 0.15s, border-color 0.15s;
  border-left: 3px solid transparent;
}

.sidebar .sidebar-nav a:hover {
  color: var(--bs-white);
  text-decoration: none;
}

.sidebar .sidebar-nav a.active {
  color: var(--bs-white);
  border-left-color: var(--bs-horizon);
  font-weight: 600;
}

/* Sidebar logo */
.sidebar .app-name-link img {
  max-width: 160px;
  padding: 1.5rem 1rem 0.5rem 1rem;
}

.sidebar .app-name-link {
  text-align: left;
  padding-left: 1rem;
}

.app-name {
  display: block;
  color: rgba(255, 255, 255, 0.5);
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  padding: 0 1rem 1rem 1rem;
  font-family: 'Chivo Mono', 'Fira Mono', monospace;
}

/* --- Code Blocks --- */
.markdown-section pre {
  background: var(--bs-code-bg);
  border-radius: 6px;
  border: 1px solid #E8E8E8;
  padding: 1rem;
}

.markdown-section pre > code {
  color: var(--bs-graphite);
  font-size: 0.875rem;
}

.markdown-section code {
  background: var(--bs-code-bg);
  color: var(--bs-cinder);
  border-radius: 3px;
  padding: 2px 6px;
  font-size: 0.875em;
}

.markdown-section pre > code {
  background: transparent;
  color: var(--bs-graphite);
  padding: 0;
}

/* --- Tables --- */
.markdown-section table {
  border-collapse: collapse;
  width: 100%;
  margin: 1rem 0;
}

.markdown-section table th {
  background: var(--bs-graphite);
  color: var(--bs-white);
  font-weight: 600;
  text-align: left;
  padding: 10px 14px;
  font-size: 0.875rem;
}

.markdown-section table td {
  padding: 10px 14px;
  border-bottom: 1px solid #E8E8E8;
  font-size: 0.875rem;
}

.markdown-section table tr:hover td {
  background: var(--bs-tip-bg);
}

/* --- Blockquotes as callouts --- */
.markdown-section blockquote {
  border-left: 4px solid var(--bs-horizon);
  background: var(--bs-tip-bg);
  padding: 12px 20px;
  margin: 1.5rem 0;
  border-radius: 0 6px 6px 0;
}

.markdown-section blockquote p {
  margin: 0;
}

/* Warning callouts (blockquotes starting with ⚠️) */
.markdown-section blockquote:has(p:first-child > strong:first-child) {
  border-left-color: var(--bs-cinder);
  background: var(--bs-warn-bg);
}

/* --- Cover page --- */
.cover {
  background: var(--bs-graphite) !important;
  color: var(--bs-white) !important;
}

.cover h1 {
  color: var(--bs-white);
  font-family: Georgia, 'Times New Roman', serif;
  font-weight: 400;
  font-size: 3rem;
}

.cover p:last-child a {
  background: var(--bs-horizon) !important;
  color: var(--bs-white) !important;
  border: none !important;
  border-radius: 6px;
  padding: 12px 32px;
  font-weight: 600;
  transition: background 0.15s;
}

.cover p:last-child a:hover {
  background: #4a7a90 !important;
}

.cover blockquote {
  border: none;
  background: transparent;
  color: rgba(255, 255, 255, 0.65);
}

.cover .cover-main {
  max-width: 600px;
}

/* --- Search --- */
.search input {
  background: rgba(255, 255, 255, 0.08) !important;
  border: 1px solid rgba(255, 255, 255, 0.15) !important;
  color: var(--bs-white) !important;
  border-radius: 4px;
}

.search input::placeholder {
  color: rgba(255, 255, 255, 0.4) !important;
}

.search .results-panel {
  background: var(--bs-graphite);
}

.search .matching-post {
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.search .matching-post a {
  color: var(--bs-white);
}

/* --- Responsive --- */
@media (max-width: 768px) {
  .markdown-section {
    padding: 1.5rem;
  }

  .markdown-section h1 {
    font-size: 1.75rem;
  }
}
```

- [ ] **Step 2: Verify file exists**

Run: `ls -la docs/site/css/`

Expected: `backstory.css` present.

- [ ] **Step 3: Commit**

```bash
git add docs/site/css/backstory.css
git commit -m "feat(docs): add Backstory brand CSS theme for Docsify"
```

---

### Task 3: Copy Brand Assets

**Files:**
- Create: `docs/site/assets/wordmark-dark.png` (copy from `assets/backstory/BS/files/`)
- Create: `docs/site/assets/books-icon-white.png` (copy from `assets/backstory/BS/files/`)
- Create: `docs/site/assets/books-icon-dark.png` (copy from `assets/backstory/BS/files/`)
- Create: `docs/site/assets/gradient-stripe.png` (copy from `assets/backstory/BS/files/`)

- [ ] **Step 1: Create assets directory and copy brand files**

```bash
mkdir -p docs/site/assets
cp assets/backstory/BS/files/wordmark-dark.png docs/site/assets/
cp assets/backstory/BS/files/books-icon-white.png docs/site/assets/
cp assets/backstory/BS/files/books-icon-dark.png docs/site/assets/
cp assets/backstory/BS/files/gradient-stripe.png docs/site/assets/
```

- [ ] **Step 2: Verify assets copied**

Run: `ls -la docs/site/assets/`

Expected: All four `.png` files present.

- [ ] **Step 3: Commit**

```bash
git add docs/site/assets/
git commit -m "feat(docs): add Backstory brand assets for site"
```

---

### Task 4: Cover Page and Sidebar Navigation

**Files:**
- Create: `docs/site/_coverpage.md`
- Create: `docs/site/_sidebar.md`

- [ ] **Step 1: Create the cover page**

Create `docs/site/_coverpage.md`:

```markdown
![logo](assets/books-icon-white.png ':size=80')

# Personal Assistant

> Admin Deployment Guide

A step-by-step guide to deploying the People.ai Personal Assistant — a proactive, AI-powered sales assistant delivered through Slack.

[Get Started](#overview)
```

- [ ] **Step 2: Create the sidebar navigation**

Create `docs/site/_sidebar.md`:

```markdown
- [Overview](/)
- [Prerequisites](prerequisites.md)
- [Slack App Setup](slack-setup.md)
- [Database Setup](database-setup.md)
- [n8n Setup](n8n-setup.md)
- [Onboarding Configuration](onboarding-config.md)
- [Workflow Reference](workflow-reference.md)
- [Troubleshooting](troubleshooting.md)
```

- [ ] **Step 3: Commit**

```bash
git add docs/site/_coverpage.md docs/site/_sidebar.md
git commit -m "feat(docs): add cover page and sidebar navigation"
```

---

### Task 5: Overview Page (README.md)

**Files:**
- Create: `docs/site/README.md`

- [ ] **Step 1: Write the overview page**

Create `docs/site/README.md`. Adapted from `people-ai-personal-assistant.md` — no credentials, customer-facing tone.

```markdown
# Overview

The People.ai Personal Assistant is a proactive, AI-powered sales assistant delivered through Slack. Each sales rep gets a named, personalized assistant that monitors their pipeline and delivers insights without being prompted.

The assistant is not a chatbot — it's an agent with its own agenda that runs on a schedule and acts proactively.

## What It Does

- **Morning Pipeline Digests** — Every weekday, each rep receives a personalized briefing covering pipeline changes, deal risks, engagement shifts, and recommended actions
- **On-Demand Intelligence** — Reps ask questions about accounts, opportunities, and pipeline via Slack commands and get answers grounded in CRM data
- **Meeting Preparation** — Before customer meetings, the assistant assembles prep packets with attendee history, deal context, and suggested talking points
- **Stakeholder Alerts** — When deal engagement drops or key contacts go silent, the assistant flags it proactively
- **Re-engagement Drafts** — For stalled deals, the assistant drafts follow-up messages that reps can review and send with one click

## Architecture

The assistant is built on a three-layer stack:

| Layer | Component | Role |
|-------|-----------|------|
| **Orchestration** | n8n | Scheduling, API routing, conditional logic, message delivery |
| **Reasoning** | Claude (Anthropic API) | Synthesizes data into natural language briefings and recommendations |
| **Intelligence** | People.ai API + MCP | Engagement scores, activity signals, deal health, stakeholder data |
| **Delivery** | Slack | All user interaction — onboarding, digests, commands, approvals |
| **Data Store** | PostgreSQL | Multi-tenant user/org data, message logs, pending actions |

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Schedule    │────▶│     n8n      │────▶│    Slack     │
│  (Cron/Event) │     │ Orchestrator │     │  (Delivery)  │
└──────────────┘     └──────┬───────┘     └──────────────┘
                            │
                    ┌───────┴───────┐
                    │               │
              ┌─────▼─────┐  ┌─────▼──────┐
              │  Claude    │  │ People.ai  │
              │ (Reasoning)│  │ (Intel)    │
              └───────────┘  └────────────┘
                    │
              ┌─────▼─────┐
              │ PostgreSQL │
              │  (Data)    │
              └───────────┘
```

## Personalization

The most important product decision: every rep names their own assistant. When a rep names their assistant — ScottAI, Luna, Aria — the mental model shifts from "the company's AI tool" to "my assistant." This drives adoption and word-of-mouth.

A single Slack bot serves all users. Slack's `chat:write.customize` scope allows the bot to override its display name and avatar per message, so each rep sees messages from their named assistant.

## What This Guide Covers

This guide walks through deploying the assistant for your organization:

1. **[Prerequisites](prerequisites.md)** — Accounts and access you need
2. **[Slack App Setup](slack-setup.md)** — Creating and configuring the Slack bot
3. **[Database Setup](database-setup.md)** — Schema and tables
4. **[n8n Setup](n8n-setup.md)** — Importing workflows and configuring credentials
5. **[Onboarding Configuration](onboarding-config.md)** — Setting org defaults and customization options
6. **[Workflow Reference](workflow-reference.md)** — What each workflow does and when it runs
7. **[Troubleshooting](troubleshooting.md)** — Common issues and how to resolve them
```

- [ ] **Step 2: Commit**

```bash
git add docs/site/README.md
git commit -m "feat(docs): add overview page"
```

---

### Task 6: Prerequisites Page

**Files:**
- Create: `docs/site/prerequisites.md`

- [ ] **Step 1: Write the prerequisites page**

Create `docs/site/prerequisites.md`. Adapted from `docs/GETTING_STARTED.md` with Supabase references genericized.

```markdown
# Prerequisites

Before starting the deployment, ensure you have the following accounts and access.

## Required Accounts

| Service | What You Need | Sign Up |
|---------|---------------|---------|
| **Slack** | Workspace admin access | [slack.com](https://slack.com) |
| **PostgreSQL Database** | Any Postgres-compatible database (Supabase, AWS RDS, self-hosted, etc.) | Varies by provider |
| **n8n** | Cloud or self-hosted instance | [n8n.io](https://n8n.io) |
| **Anthropic** | API key for Claude | [console.anthropic.com](https://console.anthropic.com) |
| **People.ai** | API credentials (client ID + secret) and MCP access | Contact your People.ai account team |

## Access Requirements

### Slack
- **Admin access** to the workspace where the bot will be installed
- Ability to create and install Slack apps
- Ability to approve OAuth scopes for bots

### PostgreSQL Database
- A running PostgreSQL instance (version 13+)
- Ability to create tables, indexes, triggers, and functions
- A REST API layer is recommended for n8n integration (e.g., Supabase, PostgREST, Hasura)
- Connection credentials (host, port, database name, user, password)

### n8n
- An accessible n8n instance with a **public URL** for webhook endpoints
- Admin access to create credentials and import workflows
- If self-hosted: HTTPS enabled (required for Slack webhook verification)

### Anthropic
- An API key with access to Claude models
- The assistant uses Claude Sonnet for all reasoning tasks

### People.ai
- **OAuth client credentials** (client ID + client secret) for the Query API — used to fetch pipeline data and user hierarchy
- **MCP endpoint access** with multi-header authentication — used for real-time CRM queries during agent reasoning
- Your People.ai account team can provision both

## Network Requirements

Your n8n instance must expose the following webhook endpoints to the public internet (Slack sends events to these):

| Endpoint | Purpose |
|----------|---------|
| `https://your-n8n-instance.com/webhook/slack-events` | Slack event subscriptions (DMs, mentions, app home) |
| `https://your-n8n-instance.com/webhook/slack-interactive` | Button clicks, modal submissions |
| `https://your-n8n-instance.com/webhook/bs` | `/bs` slash command handler |

> These URLs will be configured in the Slack App Setup step.
```

- [ ] **Step 2: Commit**

```bash
git add docs/site/prerequisites.md
git commit -m "feat(docs): add prerequisites page"
```

---

### Task 7: Slack App Setup Page

**Files:**
- Create: `docs/site/slack-setup.md`

- [ ] **Step 1: Write the Slack setup page**

Create `docs/site/slack-setup.md`. Adapted from `slack/SETUP.md` with real URLs scrubbed.

```markdown
# Slack App Setup

This guide walks through creating and configuring the Slack bot.

## Create the Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Click **Create New App** → **From scratch**
3. Name: `People.ai Assistant` (or your preferred name)
4. Select your workspace
5. Click **Create App**

## Configure Bot Permissions

Navigate to **OAuth & Permissions** and add these **Bot Token Scopes**:

### Required Scopes

| Scope | Purpose |
|-------|---------|
| `chat:write` | Send messages to users |
| `chat:write.customize` | Override bot name and avatar per message — **this is critical** for personalized assistant names |
| `im:history` | Read DM history for conversation context |
| `im:read` | Access DM channels |
| `im:write` | Open DM conversations with users |
| `channels:history` | Read messages in public channels (for multi-turn thread conversations) |
| `users:read` | Get user info (name, timezone) |
| `users:read.email` | Get user email for People.ai matching |

### Optional Scopes (for future features)

| Scope | Purpose |
|-------|---------|
| `files:write` | Attach files to messages |
| `reactions:write` | Add emoji reactions |

> **Important:** The `chat:write.customize` scope is what enables the personalized assistant experience. Without it, all messages will show the default bot name instead of each rep's chosen assistant name.

## Enable Event Subscriptions

1. Navigate to **Event Subscriptions**
2. Toggle **Enable Events** to On
3. Set **Request URL** to:
   ```
   https://your-n8n-instance.com/webhook/slack-events
   ```
4. Under **Subscribe to bot events**, add:
   - `message.im` — DMs to the bot
   - `message.channels` — Messages in public channels (for multi-turn threads)
   - `app_home_opened` — Renders the App Home settings tab
   - `app_mention` — @mentions in channels (optional)
5. Click **Save Changes**

> Slack will send a verification challenge to your webhook URL. Your n8n Slack Events Handler workflow must be active and accessible for this to succeed.

## Enable App Home

1. Navigate to **App Home**
2. Under **Show Tabs**, enable the **Home Tab**
3. Optionally enable the **Messages Tab**

The Home Tab serves as a settings panel where reps can view and modify their assistant preferences.

## Enable Interactivity

1. Navigate to **Interactivity & Shortcuts**
2. Toggle **Interactivity** to On
3. Set **Request URL** to:
   ```
   https://your-n8n-instance.com/webhook/slack-interactive
   ```

This handles button clicks and modal submissions (e.g., App Home settings edits, meeting recap save-to-CRM modals).

## Register Slash Commands

1. Navigate to **Slash Commands**
2. Click **Create New Command**
3. Configure:

| Field | Value |
|-------|-------|
| Command | `/bs` |
| Request URL | `https://your-n8n-instance.com/webhook/bs` |
| Short Description | Ask your sales assistant a question |
| Usage Hint | `[your question about an account, deal, or pipeline]` |

## Install to Workspace

1. Navigate to **Install App**
2. Click **Install to Workspace**
3. Review permissions and click **Allow**
4. Copy the **Bot User OAuth Token** (starts with `xoxb-`)

> Save this token securely — you will need it when configuring n8n credentials.

## Verify Installation

1. In Slack, find your bot in the Apps section
2. Open a DM with the bot
3. Send any message

If the n8n Slack Events Handler workflow is active, you should see the onboarding flow trigger. If not, check the Troubleshooting page.

## Production: Customer Workspace OAuth

For deploying to customer workspaces (multi-tenant), you will need full OAuth 2.0:

1. Enable **OAuth 2.0** in your Slack app settings
2. Add **Redirect URLs** for your auth flow
3. Store per-tenant tokens securely in your database
4. Handle token refresh

### Rate Limits

Key Slack API rate limits:

| Method | Tier | Approximate Limit |
|--------|------|-------------------|
| `chat.postMessage` | Tier 2 | ~20 per minute |
| `conversations.open` | Tier 3 | ~50 per minute |
| `users.info` | Tier 2 | ~20 per minute |

For high-volume deployments, implement queuing in your n8n workflows.
```

- [ ] **Step 2: Commit**

```bash
git add docs/site/slack-setup.md
git commit -m "feat(docs): add Slack app setup page"
```

---

### Task 8: Database Setup Page

**Files:**
- Create: `docs/site/database-setup.md`

- [ ] **Step 1: Write the database setup page**

Create `docs/site/database-setup.md`. Adapted from `supabase/migrations/001_initial_schema.sql` and `002_role_based_digest.sql`, genericized to standard PostgreSQL.

```markdown
# Database Setup

The assistant uses a PostgreSQL database for multi-tenant user data, message history, and pending actions. Any PostgreSQL-compatible database works (Supabase, AWS RDS, Google Cloud SQL, self-hosted, etc.).

## Requirements

- PostgreSQL 13 or later
- Ability to create tables, indexes, triggers, and functions
- A **REST API layer** is recommended for integration with n8n (e.g., PostgREST, Supabase, Hasura). Direct PostgreSQL connections also work via n8n's Postgres node.

## Schema Overview

| Table | Purpose |
|-------|---------|
| `organizations` | Customer/tenant records with default assistant settings |
| `users` | Sales rep profiles, assistant preferences, onboarding state |
| `messages` | Delivery log for all assistant messages (inbound + outbound) |
| `pending_actions` | Drafts awaiting user approval (emails, CRM updates) |

## Run the Schema Migration

Execute the following SQL against your PostgreSQL database.

### Core Tables

```sql
-- Organizations (customers/tenants)
CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    default_assistant_name TEXT DEFAULT 'Aria',
    default_assistant_emoji TEXT DEFAULT ':robot_face:',
    default_assistant_persona TEXT DEFAULT 'direct, action-oriented, conversational',
    default_assistant_avatar_url TEXT,
    peopleai_api_key_encrypted TEXT,
    slack_workspace_id TEXT,
    slack_bot_token_encrypted TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Users (sales reps)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    slack_user_id TEXT,
    peopleai_user_id TEXT,
    assistant_name TEXT,
    assistant_emoji TEXT,
    assistant_persona TEXT,
    assistant_avatar_url TEXT,
    timezone TEXT DEFAULT 'America/Los_Angeles',
    digest_enabled BOOLEAN DEFAULT TRUE,
    digest_time TIME DEFAULT '06:00:00',
    meeting_prep_enabled BOOLEAN DEFAULT TRUE,
    meeting_prep_minutes_before INTEGER DEFAULT 120,
    onboarding_state TEXT DEFAULT 'new',
    department TEXT,
    division TEXT,
    digest_scope TEXT DEFAULT 'my_deals'
        CHECK (digest_scope IN ('my_deals', 'team_deals', 'top_pipeline')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(organization_id, email),
    UNIQUE(organization_id, slack_user_id)
);

-- Message history
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    message_type TEXT NOT NULL,
    channel TEXT NOT NULL,
    direction TEXT DEFAULT 'outbound',
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    sent_at TIMESTAMPTZ DEFAULT NOW()
);

-- Pending actions (drafts awaiting approval)
CREATE TABLE pending_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    action_type TEXT NOT NULL,
    opportunity_id TEXT,
    draft_content TEXT NOT NULL,
    context JSONB DEFAULT '{}',
    status TEXT DEFAULT 'pending',
    slack_message_ts TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '24 hours',
    resolved_at TIMESTAMPTZ
);
```

### Indexes

```sql
CREATE INDEX idx_users_slack ON users(slack_user_id);
CREATE INDEX idx_users_org ON users(organization_id);
CREATE INDEX idx_users_digest_scope ON users(digest_scope);
CREATE INDEX idx_messages_user ON messages(user_id, sent_at DESC);
CREATE INDEX idx_messages_type ON messages(user_id, message_type);
CREATE INDEX idx_pending_actions_user ON pending_actions(user_id, status);
```

### Auto-Update Trigger

```sql
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER organizations_updated_at
    BEFORE UPDATE ON organizations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
```

### Helper Functions

These functions implement the assistant identity resolution chain: user override → org default → hardcoded fallback.

```sql
CREATE OR REPLACE FUNCTION get_assistant_name(p_user_id UUID)
RETURNS TEXT AS $$
DECLARE
    v_user_name TEXT;
    v_org_name TEXT;
BEGIN
    SELECT u.assistant_name, o.default_assistant_name
    INTO v_user_name, v_org_name
    FROM users u
    JOIN organizations o ON u.organization_id = o.id
    WHERE u.id = p_user_id;
    RETURN COALESCE(v_user_name, v_org_name, 'Aria');
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION get_assistant_emoji(p_user_id UUID)
RETURNS TEXT AS $$
DECLARE
    v_user_emoji TEXT;
    v_org_emoji TEXT;
BEGIN
    SELECT u.assistant_emoji, o.default_assistant_emoji
    INTO v_user_emoji, v_org_emoji
    FROM users u
    JOIN organizations o ON u.organization_id = o.id
    WHERE u.id = p_user_id;
    RETURN COALESCE(v_user_emoji, v_org_emoji, ':robot_face:');
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION get_assistant_persona(p_user_id UUID)
RETURNS TEXT AS $$
DECLARE
    v_user_persona TEXT;
    v_org_persona TEXT;
BEGIN
    SELECT u.assistant_persona, o.default_assistant_persona
    INTO v_user_persona, v_org_persona
    FROM users u
    JOIN organizations o ON u.organization_id = o.id
    WHERE u.id = p_user_id;
    RETURN COALESCE(v_user_persona, v_org_persona, 'direct, action-oriented, conversational');
END;
$$ LANGUAGE plpgsql;
```

## Seed Data

After running the migration, seed your first organization:

```sql
INSERT INTO organizations (name, slug, default_assistant_name)
VALUES ('Your Company', 'your-company', 'Aria');
```

Add yourself as a test user:

```sql
INSERT INTO users (organization_id, email, slack_user_id)
SELECT id, 'admin@yourcompany.com', 'U0EXAMPLE'
FROM organizations WHERE slug = 'your-company';
```

> To find your Slack user ID: click your profile in Slack → "..." menu → "Copy member ID".

## Row-Level Security

For production multi-tenant deployments, enable Row-Level Security (RLS) to ensure data isolation between organizations:

```sql
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users scoped to organization"
  ON users FOR ALL
  USING (organization_id = current_setting('app.current_org_id')::uuid);

ALTER TABLE messages ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Messages scoped to user's organization"
  ON messages FOR ALL
  USING (user_id IN (
    SELECT id FROM users
    WHERE organization_id = current_setting('app.current_org_id')::uuid
  ));
```

> The specific RLS implementation depends on your database provider and authentication layer. The examples above use PostgreSQL session variables — adapt to your setup (Supabase auth, Hasura permissions, application-level filtering, etc.).

## Column Reference

### `users` Table — Key Fields

| Column | Type | Description |
|--------|------|-------------|
| `onboarding_state` | TEXT | `new` → `awaiting_name` → `awaiting_emoji` → `complete` |
| `assistant_name` | TEXT | User's chosen name (NULL = use org default) |
| `assistant_emoji` | TEXT | User's chosen emoji (NULL = use org default) |
| `assistant_persona` | TEXT | Freeform personality description (NULL = use org default) |
| `digest_enabled` | BOOLEAN | Whether the user receives daily digests |
| `digest_scope` | TEXT | `my_deals` (IC), `team_deals` (Manager), `top_pipeline` (Exec) |
| `department` | TEXT | From Slack profile — used for digest scope detection |
| `division` | TEXT | From Slack profile — used for role inference |

### `messages` Table — Message Types

| `message_type` | Description |
|----------------|-------------|
| `digest` | Daily pipeline briefing |
| `meeting_prep` | Pre-meeting intelligence packet |
| `follow_up_draft` | Re-engagement email draft |
| `alert` | Proactive risk/silence alert |
| `conversation` | Multi-turn thread message |
| `slash_command` | `/bs` command response |
```

- [ ] **Step 2: Commit**

```bash
git add docs/site/database-setup.md
git commit -m "feat(docs): add database setup page with generic PostgreSQL schema"
```

---

### Task 9: n8n Setup Page

**Files:**
- Create: `docs/site/n8n-setup.md`

- [ ] **Step 1: Write the n8n setup page**

Create `docs/site/n8n-setup.md`. Adapted from `docs/GETTING_STARTED.md` and `docs/ENV_TEMPLATE.md` with all credentials as placeholders.

```markdown
# n8n Setup

This guide covers importing workflows, configuring credentials, and activating the assistant in n8n.

## Create Credentials

In n8n, go to **Settings → Credentials → Add Credential** and create the following:

### Slack Bot Token

| Field | Value |
|-------|-------|
| Type | HTTP Header Auth |
| Header Name | `Authorization` |
| Header Value | `Bearer xoxb-your-bot-token` |

> Use the Bot User OAuth Token from the Slack App Setup step.

### Anthropic API

| Field | Value |
|-------|-------|
| Type | Anthropic API |
| API Key | `sk-ant-your-api-key` |

### People.ai MCP (Multi-Header Auth)

| Field | Value |
|-------|-------|
| Type | HTTP Multiple Headers Auth |
| Headers | As provided by your People.ai account team |

> The MCP endpoint is used for real-time CRM queries during agent reasoning. Your People.ai team will provide the required authentication headers.

### People.ai Query API (OAuth)

The Sales Digest workflow uses People.ai's Query API with OAuth client credentials to fetch pipeline data. The client ID and secret are embedded in the workflow's authentication node — update them after import.

### Database Connection

Choose one of:

**Option A — REST API (recommended for Supabase / PostgREST)**

| Field | Value |
|-------|-------|
| Type | Supabase API (or HTTP Header Auth for PostgREST) |
| Host | `https://your-database-rest-endpoint.com` |
| API Key | `your-service-role-key` |

**Option B — Direct PostgreSQL**

| Field | Value |
|-------|-------|
| Type | PostgreSQL |
| Host | `your-db-host.com` |
| Port | `5432` |
| Database | `your-database-name` |
| User | `your-db-user` |
| Password | `your-db-password` |

## Import Workflows

1. Go to **Workflows → Import from File**
2. Import the workflow JSON files from the `n8n/workflows/` directory in the repository
3. For each imported workflow, update credential references to match the credential names you created above

### Key Workflows to Import

| File | Purpose | Activate? |
|------|---------|-----------|
| `Sales Digest.json` | Daily pipeline briefings (6am weekdays) | Yes |
| `Backstory SlackBot.json` | `/bs` slash command handler | Yes |
| `Slack Events Handler.json` | Onboarding, settings, DM conversations | Yes |

> Import all workflow files from the repository. Some are sub-workflows (called by other workflows) and need to be present for the main workflows to function.

## Update Credential References

After importing each workflow:

1. Open the workflow in the editor
2. Click on each node that has a credential warning (yellow triangle)
3. Select the matching credential you created above
4. Save the workflow

### Common Credential Mappings

| Node Type | Credential to Use |
|-----------|-------------------|
| Slack `chat.postMessage` (HTTP Request) | Slack Bot Token |
| Anthropic Chat Model | Anthropic API |
| People.ai MCP Client | People.ai MCP (Multi-Header) |
| Supabase nodes | Database Connection |
| People.ai Query API (HTTP Request) | Update the OAuth token node in-workflow |

## Update Webhook URLs

If your n8n instance URL differs from what's in the workflow JSONs, update the webhook trigger nodes:

| Webhook Path | Used By |
|--------------|---------|
| `/webhook/slack-events` | Slack Events Handler |
| `/webhook/slack-interactive` | Interactive Events Handler |
| `/webhook/bs` | Backstory SlackBot |

## Configure Timezone

The Sales Digest workflow defaults to `America/Los_Angeles` (Pacific Time). To change:

1. Open the workflow
2. Go to **Settings** (gear icon)
3. Update the **Timezone** setting

## Activate Workflows

1. Open each workflow
2. Toggle the **Active** switch in the top-right corner
3. Verify the webhook URLs are registered (n8n will show them in the trigger node)

> Start with the Slack Events Handler — this enables onboarding. Then activate the Sales Digest and Backstory SlackBot.

## Verify Setup

### Test the Slash Command

1. In Slack, type `/bs What are my top accounts?`
2. You should see a "Thinking..." response followed by a detailed answer
3. If nothing happens, check the n8n execution logs

### Test the Digest Manually

1. Open the Sales Digest workflow in n8n
2. Click **Execute Workflow** to run it manually
3. Check your Slack DMs for the briefing

### Test Onboarding

1. In Slack, open a DM with your bot
2. Send any message
3. The onboarding flow should ask you to name your assistant
4. Verify the name appears in your database: `SELECT assistant_name FROM users WHERE slack_user_id = 'your-slack-id';`
```

- [ ] **Step 2: Commit**

```bash
git add docs/site/n8n-setup.md
git commit -m "feat(docs): add n8n setup page"
```

---

### Task 10: Onboarding Configuration Page

**Files:**
- Create: `docs/site/onboarding-config.md`

- [ ] **Step 1: Write the onboarding configuration page**

Create `docs/site/onboarding-config.md`:

```markdown
# Onboarding Configuration

The assistant personalizes itself for each rep through an in-Slack onboarding flow. This page covers how to configure defaults and how the onboarding process works.

## Organization Defaults

Set defaults for your organization in the `organizations` table:

| Column | Purpose | Example |
|--------|---------|---------|
| `default_assistant_name` | Fallback name if a rep hasn't chosen one | `Aria` |
| `default_assistant_emoji` | Fallback emoji for Slack messages | `:robot_face:` |
| `default_assistant_persona` | Default personality description | `direct, action-oriented, conversational` |

```sql
UPDATE organizations
SET default_assistant_name = 'Aria',
    default_assistant_emoji = ':robot_face:',
    default_assistant_persona = 'direct, action-oriented, conversational'
WHERE slug = 'your-company';
```

## Resolution Chain

The assistant resolves its identity using a three-level fallback:

```
User-level override → Organization default → Hardcoded fallback
```

For example, if a rep has set `assistant_name = 'ScottAI'`, they see "ScottAI." If they haven't, they see the org default. If neither is set, they see "Aria."

This applies to name, emoji, and persona independently — a rep could override their name but use the org default emoji.

## Onboarding State Machine

When a new user first DMs the bot, the onboarding flow walks them through personalization:

```
new → awaiting_name → awaiting_emoji → complete
```

| State | What Happens |
|-------|-------------|
| `new` | Bot sends a greeting and asks: "What do you want to call me?" |
| `awaiting_name` | Rep replies with a name → saved to `assistant_name` → bot asks for an emoji |
| `awaiting_emoji` | Rep replies with an emoji → saved to `assistant_emoji` → onboarding complete |
| `complete` | All features active — digests, commands, alerts |

> Reps can change their assistant's name, emoji, or persona at any time by DMing the bot with commands like `rename Luna`, `emoji :star:`, or `persona witty and data-driven`.

## Digest Scope

The `digest_scope` column controls what pipeline data each user sees in their daily briefing:

| Scope | Role | Briefing Content |
|-------|------|-----------------|
| `my_deals` | IC (AE, SDR, BDR) | Personal pipeline — the rep's own opportunities |
| `team_deals` | Manager, Director | Team pipeline — direct reports' opportunities |
| `top_pipeline` | VP, SVP, CRO, Chief | Organization pipeline — top 25 deals by amount |

### Automatic Scope Detection

Digest scope is auto-detected from the rep's **Slack profile title** (Division field) during onboarding:

| Slack Division Contains | Assigned Scope |
|------------------------|----------------|
| Account Executive, SDR, BDR | `my_deals` |
| Manager, Director | `team_deals` |
| VP, SVP, CRO, Chief | `top_pipeline` |

Reps can manually change their scope via DM: `scope team` or `scope exec`.

### Manual Override

```sql
UPDATE users SET digest_scope = 'team_deals'
WHERE email = 'manager@yourcompany.com';
```

## Assistant Persona

The `assistant_persona` field accepts freeform text that gets injected into the AI's system prompt. This controls the tone and style of all assistant output.

Examples:
- `direct, action-oriented, conversational` (default)
- `witty and casual with a bias toward action`
- `formal and data-driven, focused on metrics`
- `encouraging and supportive, celebrates wins`

Each rep can set their own persona via DM: `persona witty and casual`.
```

- [ ] **Step 2: Commit**

```bash
git add docs/site/onboarding-config.md
git commit -m "feat(docs): add onboarding configuration page"
```

---

### Task 11: Workflow Reference Page

**Files:**
- Create: `docs/site/workflow-reference.md`

- [ ] **Step 1: Write the workflow reference page**

Create `docs/site/workflow-reference.md`:

```markdown
# Workflow Reference

The assistant is powered by a set of n8n workflows, each handling a specific function. This page documents what each workflow does and when it runs.

## Core Workflows

### Sales Digest

| Property | Value |
|----------|-------|
| Trigger | Cron: 6am weekdays (Mon–Fri) |
| Purpose | Generate and deliver personalized morning pipeline briefings |
| Integrations | People.ai Query API, People.ai MCP, Claude, Slack, PostgreSQL |

Fetches the People.ai user hierarchy and all open opportunities via the Query API. For each active user, filters opportunities by their digest scope (IC/Manager/Exec), applies a daily theme (Monday: full pipeline, Tuesday: engagement shifts, Wednesday: at-risk, Thursday: momentum, Friday: week review), then runs a Claude agent with People.ai MCP tools to generate a Slack Block Kit briefing. Delivers via personalized Slack DM and logs to the database.

### Backstory SlackBot

| Property | Value |
|----------|-------|
| Trigger | Webhook: `/bs` slash command |
| Purpose | On-demand Q&A about accounts, deals, and pipeline |
| Integrations | People.ai MCP, Claude, Slack |

Handles the `/bs` slash command. Acknowledges immediately (Slack's 3-second timeout), then runs a Claude agent with People.ai MCP tools to answer the question. Responds via DM (response_url) or channel thread depending on where the command was invoked.

### Slack Events Handler

| Property | Value |
|----------|-------|
| Trigger | Webhook: Slack Events API |
| Purpose | Onboarding, settings commands, DM conversations |
| Integrations | Slack, PostgreSQL |

Handles all Slack events: new user onboarding (name → emoji → complete), settings commands (rename, emoji, persona, scope, digest toggle), and conversational DM routing. Routes events through a multi-output switch based on user state and message content.

### Interactive Events Handler

| Property | Value |
|----------|-------|
| Trigger | Webhook: Slack Interactivity |
| Purpose | Button clicks, modal submissions, App Home interactions |
| Integrations | Slack, PostgreSQL, Workato (Salesforce) |

Handles block_actions (button clicks in messages) and view_submission (modal form submissions). Powers the App Home settings panel, meeting recap save-to-CRM modals, task creation modals, and various interactive features.

## Scheduled Workflows

### Meeting Prep Cron

| Property | Value |
|----------|-------|
| Trigger | Cron: every 15 minutes |
| Purpose | Poll for upcoming meetings and generate prep packets |
| Integrations | People.ai API, Claude, Slack |

Checks People.ai for meetings starting within the next 2 hours. For each upcoming meeting, calls the Meeting Brief sub-workflow to generate and deliver a prep packet.

### Silence Contract Monitor

| Property | Value |
|----------|-------|
| Trigger | Cron: 6:30am weekdays |
| Purpose | Detect deals with no engagement activity |
| Integrations | People.ai Query API, Claude, Slack, PostgreSQL |

Identifies opportunities where key contacts have gone silent. Alerts the rep with context and suggested re-engagement actions.

### Deal Watch Cron

| Property | Value |
|----------|-------|
| Trigger | Cron: 7am weekdays |
| Purpose | Track opportunity stage transitions |
| Integrations | People.ai Query API, Slack, PostgreSQL |

Monitors for deals that have changed stage, close date, or amount. Notifies reps of significant movements in their pipeline.

### Follow-up Cron

| Property | Value |
|----------|-------|
| Trigger | Cron: 9am + 4pm weekdays |
| Purpose | Meeting recaps, action hub, and task resolution |
| Integrations | People.ai API, Claude, Slack, Workato (Salesforce), PostgreSQL |

Generates AI-powered meeting recaps for recently completed meetings with Salesforce integration. Also runs a parallel task resolution branch that checks for completed tasks.

### Weekly Profile Sync

| Property | Value |
|----------|-------|
| Trigger | Cron: Sunday 10pm PT |
| Purpose | Sync Slack profile data to the database |
| Integrations | Slack, PostgreSQL |

Fetches updated profile information (department, division, title) from Slack for all users and updates the database. Ensures digest scope stays accurate as roles change.

## Sub-Workflows

These workflows are called by other workflows (not triggered directly):

| Workflow | Called By | Purpose |
|----------|----------|---------|
| On-Demand Digest | Slack Events Handler | Generates a digest on request (user types `digest`) |
| Meeting Brief | Meeting Prep Cron | Generates a single meeting prep packet |
| On-Demand Silence Check | Slack Events Handler | Runs a silence check on request (user types `silence`) |
| Backstory Presentation | Backstory SlackBot | Generates branded Google Slides from agent output |
| Task Resolution Handler | Webhook callback | Processes completed tasks from Salesforce via Workato |
```

- [ ] **Step 2: Commit**

```bash
git add docs/site/workflow-reference.md
git commit -m "feat(docs): add workflow reference page"
```

---

### Task 12: Troubleshooting Page

**Files:**
- Create: `docs/site/troubleshooting.md`

- [ ] **Step 1: Write the troubleshooting page**

Create `docs/site/troubleshooting.md`:

```markdown
# Troubleshooting

Common issues and how to resolve them, organized by integration point.

## Slack Issues

### Bot doesn't respond to DMs

1. Check that the **Slack Events Handler** workflow is active in n8n
2. Verify Event Subscriptions are enabled in your Slack app settings
3. Confirm the webhook URL (`https://your-n8n-instance.com/webhook/slack-events`) is correct and accessible
4. Check n8n execution logs for incoming events
5. Ensure the `message.im` bot event is subscribed

### Messages show the default bot name instead of the assistant name

1. Verify the `chat:write.customize` scope is added to your Slack app
2. **Reinstall the app** after adding new scopes (scope changes require reinstallation)
3. Check that the `username` parameter is being passed in Slack API calls
4. Verify the user has an `assistant_name` value in the database

### "missing_scope" error

1. Go to **OAuth & Permissions** in your Slack app settings
2. Add the missing scope
3. Reinstall the app to your workspace

### Slash command times out

Slack requires a response within 3 seconds. The workflow must acknowledge the command immediately before running the agent.

1. Check that the "Acknowledge" node runs before the agent node
2. Verify the webhook URL for the slash command matches the n8n workflow

## Database Issues

### Migration fails

1. Ensure you're running PostgreSQL 13 or later
2. Check that `gen_random_uuid()` is available (requires the `pgcrypto` extension on older versions):
   ```sql
   CREATE EXTENSION IF NOT EXISTS pgcrypto;
   ```
3. Run the migrations in order: core schema first, then role-based digest additions

### Queries return empty results with RLS enabled

If Row-Level Security is enabled but the API requests aren't setting the organization context:

1. Verify your REST API layer passes the organization ID
2. For service-level access (n8n workflows), use a service role key that bypasses RLS
3. Check the RLS policies match your authentication approach

## n8n Issues

### Workflow doesn't trigger on schedule

1. Check that the workflow is **Active** (toggle in top-right)
2. Verify the timezone setting matches your intended schedule
3. Check n8n system logs for scheduler errors
4. For manual testing, click **Execute Workflow** to run immediately

### Credential errors

1. Open the workflow and click on nodes with yellow warning triangles
2. Select the correct credential for each node
3. Test the credential connection using n8n's built-in test button
4. For HTTP Request nodes, verify the auth type matches (Header Auth vs. Multi-Header Auth)

### Webhook not receiving events

1. Ensure your n8n instance has a **public HTTPS URL**
2. Check that the webhook path in n8n matches the URL configured in Slack
3. Test the webhook with a curl request:
   ```bash
   curl -X POST https://your-n8n-instance.com/webhook/slack-events \
     -H "Content-Type: application/json" \
     -d '{"type": "url_verification", "challenge": "test"}'
   ```
4. You should receive the challenge string back

## People.ai Issues

### Authentication failures (401)

1. **Query API (OAuth):** Verify the client ID and secret are correct. Request a new token to test:
   ```bash
   curl -X POST https://api.people.ai/v3/auth/tokens \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "client_id=your-client-id&client_secret=your-client-secret&grant_type=client_credentials"
   ```
2. **MCP endpoint:** Verify the multi-header authentication values with your People.ai account team

### Query API returns empty data

1. Confirm your service account has access to the relevant data
2. Check the export filter — ensure `ootb_opportunity_is_closed` is set to `false` for open opportunities
3. Verify the column slugs in the export request match the People.ai schema

### MCP connection fails in agent node

1. Verify the MCP endpoint URL is correct (`https://mcp.people.ai/mcp` or the canary endpoint)
2. Check that the credential type is **HTTP Multiple Headers Auth** (not single header)
3. Ensure the n8n node's `endpointUrl` field is set (not `url`)

## Common Scenarios

### Digest not arriving

1. Is the user's `onboarding_state` set to `complete`?
2. Is `digest_enabled` set to `true`?
3. Does the user have a valid `slack_user_id`?
4. Check the Sales Digest execution log in n8n for errors on that user

### Onboarding stuck

| Symptom | Check |
|---------|-------|
| No greeting received | Is the Slack Events Handler active? Is `message.im` subscribed? |
| Greeting received but no name prompt | Check the routing logic in the Switch node |
| Name saved but no emoji prompt | Check the node connecting name capture to emoji prompt |
| State shows `complete` but no digests | Check `digest_enabled` and that the Sales Digest workflow is active |

### How to re-trigger a digest manually

1. Open the Sales Digest workflow in n8n
2. Click **Execute Workflow**
3. This runs the full digest for all active users

To trigger for a single user, you can also use the On-Demand Digest sub-workflow if it's configured.

## Getting Help

If you're stuck after working through this page:

1. Check the n8n execution logs — they show the full data flow for each run
2. Verify each integration independently (Slack, database, People.ai, Claude)
3. Contact your People.ai account team for API access issues
```

- [ ] **Step 2: Commit**

```bash
git add docs/site/troubleshooting.md
git commit -m "feat(docs): add troubleshooting page"
```

---

### Task 13: GitHub Actions Deploy Workflow

**Files:**
- Create: `.github/workflows/deploy-docs.yml`

- [ ] **Step 1: Create the GitHub Actions workflow**

Create `.github/workflows/deploy-docs.yml`:

```yaml
name: Deploy Admin Guide

on:
  push:
    branches: [main]
    paths: ['docs/site/**']

permissions:
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/upload-pages-artifact@v3
        with:
          path: docs/site
      - id: deployment
        uses: actions/deploy-pages@v4
```

- [ ] **Step 2: Verify file exists**

Run: `cat .github/workflows/deploy-docs.yml`

Expected: YAML content with `paths: ['docs/site/**']` and `path: docs/site`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/deploy-docs.yml
git commit -m "ci: add GitHub Actions workflow to deploy admin guide to Pages"
```

---

### Task 14: Enable GitHub Pages on the Repository

**Files:** None (GitHub API configuration)

- [ ] **Step 1: Enable GitHub Pages with Actions source**

```bash
gh api repos/HappyCowboyAI/personal-assistant/pages \
  -X POST \
  -f build_type=workflow \
  --silent 2>/dev/null || \
gh api repos/HappyCowboyAI/personal-assistant/pages \
  -X PUT \
  -f build_type=workflow \
  --silent
```

> This configures GitHub Pages to deploy via GitHub Actions (rather than from a branch). If Pages is already enabled, the PUT updates the configuration.

- [ ] **Step 2: Verify Pages is enabled**

```bash
gh api repos/HappyCowboyAI/personal-assistant/pages --jq '.build_type'
```

Expected: `workflow`

- [ ] **Step 3: Push to trigger deploy**

```bash
git push origin main
```

- [ ] **Step 4: Check deployment status**

```bash
gh run list --workflow=deploy-docs.yml --limit=1
```

Expected: A workflow run in "completed" / "success" state.

- [ ] **Step 5: Verify the live site**

Open `https://happycowboyai.github.io/personal-assistant/` in a browser. Verify:
- Cover page renders with Backstory branding (dark background, white text, logo)
- "Get Started" button navigates to the Overview page
- Sidebar shows all 8 navigation links
- Search works
- Each page loads and renders correctly
- No real credentials, URLs, or IDs appear anywhere

---

### Task 15: Final Credential Audit

**Files:** All `docs/site/*.md` files

- [ ] **Step 1: Scan all site files for potential credential leaks**

```bash
grep -rn -E '(xoxb-|sk-ant-|ASRWWkQ|LluVuiMJ|rlAz7Z|wvV5pw|rhrlnkb|scottai\.trackslife|n8n\.peoplesync|U061WJ6|people\.ai/v3/auth|client_id=Yl1J|2rT0SWrg|cfff4d3a)' docs/site/
```

Expected: **No matches.** If any real credential values appear, fix them immediately.

- [ ] **Step 2: Scan for internal hostnames**

```bash
grep -rn -E '(trackslife\.com|peoplesync\.ai|rhrlnkb)' docs/site/
```

Expected: **No matches.**

- [ ] **Step 3: Commit any fixes if needed, then tag the release**

```bash
git tag v1.0.0-docs -m "Initial admin guide deployment"
git push origin v1.0.0-docs
```
