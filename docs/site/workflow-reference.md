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
