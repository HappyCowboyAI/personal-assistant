# Workflow Reference

The assistant is powered by a set of n8n workflows, each handling a specific function. This page documents what each workflow does and when it runs.

All workflow JSON files are in the [`n8n/workflows/`](https://github.com/HappyCowboyAI/personal-assistant/tree/main/n8n/workflows) directory. No API keys or secrets are embedded — credentials are referenced by ID with `YOUR_*` placeholders.

> **LLM flexibility:** The workflows use n8n's AI Agent node for reasoning. Any LLM supported by n8n works — Claude, ChatGPT, Gemini, Mistral, or a self-hosted model. Swap the LLM model node in the n8n editor to use your preferred provider.

> **To import:** In n8n, go to **Workflows → Import from File**, select the JSON, then update credential references to match your instance. See [n8n Setup](n8n-setup.md) for details.

## Core Workflows

### Sales Digest

| Property | Value |
|----------|-------|
| Trigger | Cron: 6am weekdays (Mon–Fri) |
| Purpose | Generate and deliver personalized morning pipeline briefings |
| Integrations | Backstory Query API, Backstory MCP, LLM (Claude, ChatGPT, etc.), Slack, PostgreSQL |
| Download | [`Sales Digest.json`](https://github.com/HappyCowboyAI/personal-assistant/blob/main/n8n/workflows/Sales%20Digest.json) |

Fetches the Backstory user hierarchy and all open opportunities via the Query API. For each active user, filters opportunities by their digest scope (IC/Manager/Exec), applies a daily theme (Monday: full pipeline, Tuesday: engagement shifts, Wednesday: at-risk, Thursday: momentum, Friday: week review), then runs an AI agent with Backstory MCP tools to generate a Slack Block Kit briefing. Delivers via personalized Slack DM and logs to the database.

### Backstory SlackBot

| Property | Value |
|----------|-------|
| Trigger | Webhook: `/bs` slash command |
| Purpose | On-demand Q&A about accounts, deals, and pipeline |
| Integrations | Backstory MCP, LLM (Claude, ChatGPT, etc.), Slack |
| Download | [`Backstory SlackBot.json`](https://github.com/HappyCowboyAI/personal-assistant/blob/main/n8n/workflows/Backstory%20SlackBot.json) |

Handles the `/bs` slash command. Acknowledges immediately (Slack's 3-second timeout), then runs an AI agent with Backstory MCP tools to answer the question. Responds via DM (response_url) or channel thread depending on where the command was invoked.

### Slack Events Handler

| Property | Value |
|----------|-------|
| Trigger | Webhook: Slack Events API |
| Purpose | Onboarding, settings commands, DM conversations |
| Integrations | Slack, PostgreSQL |
| Download | [`Slack Events Handler.json`](https://github.com/HappyCowboyAI/personal-assistant/blob/main/n8n/workflows/Slack%20Events%20Handler.json) |

Handles all Slack events: new user onboarding (name → emoji → complete), settings commands (rename, emoji, persona, scope, digest toggle), and conversational DM routing. Routes events through a multi-output switch based on user state and message content.

### Interactive Events Handler

| Property | Value |
|----------|-------|
| Trigger | Webhook: Slack Interactivity |
| Purpose | Button clicks, modal submissions, App Home interactions |
| Integrations | Slack, PostgreSQL, Workato (Salesforce) |
| Download | [`Interactive Events Handler.json`](https://github.com/HappyCowboyAI/personal-assistant/blob/main/n8n/workflows/Interactive%20Events%20Handler.json) |

Handles block_actions (button clicks in messages) and view_submission (modal form submissions). Powers the App Home settings panel, meeting recap save-to-CRM modals, task creation modals, and various interactive features.

## Scheduled Workflows

### Meeting Prep Cron

| Property | Value |
|----------|-------|
| Trigger | Cron: every 15 minutes |
| Purpose | Poll for upcoming meetings and generate prep packets |
| Integrations | Backstory API, LLM (Claude, ChatGPT, etc.), Slack |
| Download | [`Meeting Prep Cron.json`](https://github.com/HappyCowboyAI/personal-assistant/blob/main/n8n/workflows/Meeting%20Prep%20Cron.json) |

Checks Backstory for meetings starting within the next 2 hours. For each upcoming meeting, calls the Meeting Brief sub-workflow to generate and deliver a prep packet.

### Silence Contract Monitor

| Property | Value |
|----------|-------|
| Trigger | Cron: 6:30am weekdays |
| Purpose | Detect deals with no engagement activity |
| Integrations | Backstory Query API, LLM (Claude, ChatGPT, etc.), Slack, PostgreSQL |
| Download | [`Silence Contract Monitor.json`](https://github.com/HappyCowboyAI/personal-assistant/blob/main/n8n/workflows/Silence%20Contract%20Monitor.json) |

Identifies opportunities where key contacts have gone silent. Alerts the rep with context and suggested re-engagement actions.

### Deal Watch Cron

| Property | Value |
|----------|-------|
| Trigger | Cron: 7am weekdays |
| Purpose | Track opportunity stage transitions |
| Integrations | Backstory Query API, Slack, PostgreSQL |
| Download | [`Deal Watch Cron.json`](https://github.com/HappyCowboyAI/personal-assistant/blob/main/n8n/workflows/Deal%20Watch%20Cron.json) |

Monitors for deals that have changed stage, close date, or amount. Notifies reps of significant movements in their pipeline.

### Follow-up Cron

| Property | Value |
|----------|-------|
| Trigger | Cron: 9am + 4pm weekdays |
| Purpose | Meeting recaps, action hub, and task resolution |
| Integrations | Backstory API, LLM (Claude, ChatGPT, etc.), Slack, Workato (Salesforce), PostgreSQL |
| Download | [`Follow-up Cron.json`](https://github.com/HappyCowboyAI/personal-assistant/blob/main/n8n/workflows/Follow-up%20Cron.json) |

Generates AI-powered meeting recaps for recently completed meetings with Salesforce integration via an AI agent with Backstory MCP tools. Also runs a parallel task resolution branch that checks for completed tasks.

### Weekly Profile Sync

| Property | Value |
|----------|-------|
| Trigger | Cron: Sunday 10pm PT |
| Purpose | Sync Slack profile data to the database |
| Integrations | Slack, PostgreSQL |
| Download | [`Weekly Profile Sync.json`](https://github.com/HappyCowboyAI/personal-assistant/blob/main/n8n/workflows/Weekly%20Profile%20Sync.json) |

Fetches updated profile information (department, division, title) from Slack for all users and updates the database. Ensures digest scope stays accurate as roles change.

### Daily Usage Report

| Property | Value |
|----------|-------|
| Trigger | Cron: 8am weekdays |
| Purpose | Daily analytics — interactions, active users, skills used |
| Integrations | PostgreSQL, Slack |
| Download | [`Daily Usage Report.json`](https://github.com/HappyCowboyAI/personal-assistant/blob/main/n8n/workflows/Daily%20Usage%20Report.json) |

Queries the message log for the previous day's activity and posts a summary to the admin channel with interaction counts, active users, top skills, and CRM action counts.

### Weekly Usage Report

| Property | Value |
|----------|-------|
| Trigger | Cron: Friday 4pm PT |
| Purpose | Weekly trends — adoption funnel, drop-off detection |
| Integrations | PostgreSQL, Slack |
| Download | [`Weekly Usage Report.json`](https://github.com/HappyCowboyAI/personal-assistant/blob/main/n8n/workflows/Weekly%20Usage%20Report.json) |

Week-over-week comparison of daily interaction patterns, adoption funnel, and user engagement trends.

### Feature Education Cron

| Property | Value |
|----------|-------|
| Trigger | Scheduled |
| Purpose | Progressive feature tips for users |
| Integrations | PostgreSQL, Slack |
| Download | [`Feature Education Cron.json`](https://github.com/HappyCowboyAI/personal-assistant/blob/main/n8n/workflows/Feature%20Education%20Cron.json) |

Sends periodic feature tips based on the user's usage history, introducing capabilities they haven't tried yet.

## Sub-Workflows

These workflows are called by other workflows (not triggered directly):

| Workflow | Called By | Purpose | Download |
|----------|----------|---------|----------|
| On-Demand Digest | Slack Events Handler | Generates a digest on request (`brief`) | [`On-Demand Digest.json`](https://github.com/HappyCowboyAI/personal-assistant/blob/main/n8n/workflows/On-Demand%20Digest.json) |
| On-Demand Insights | Slack Events Handler | Deep pipeline intelligence (`insights`) | [`On-Demand Insights.json`](https://github.com/HappyCowboyAI/personal-assistant/blob/main/n8n/workflows/On-Demand%20Insights.json) |
| Meeting Brief | Meeting Prep Cron | Generates a single meeting prep packet | [`Meeting Brief.json`](https://github.com/HappyCowboyAI/personal-assistant/blob/main/n8n/workflows/Meeting%20Brief.json) |
| On-Demand Silence Check | Slack Events Handler | Runs a silence check on request (`silence`) | [`On-Demand Silence Check.json`](https://github.com/HappyCowboyAI/personal-assistant/blob/main/n8n/workflows/On-Demand%20Silence%20Check.json) |
| Backstory Presentation | Backstory SlackBot | Generates branded Google Slides | [`Backstory Presentation.json`](https://github.com/HappyCowboyAI/personal-assistant/blob/main/n8n/workflows/Backstory%20Presentation.json) |
| Opportunity Insights | Slack Events Handler | Stalled/at-risk/accelerating analysis | [`Opportunity Insights.json`](https://github.com/HappyCowboyAI/personal-assistant/blob/main/n8n/workflows/Opportunity%20Insights.json) |
| Continue Conversation | Slack Events Handler | Multi-turn DM conversations | [`Continue Conversation.json`](https://github.com/HappyCowboyAI/personal-assistant/blob/main/n8n/workflows/Continue%20Conversation.json) |
| Task Callback Handler | Workato webhook | Processes SF task completions | [`Task Callback Handler.json`](https://github.com/HappyCowboyAI/personal-assistant/blob/main/n8n/workflows/Task%20Callback%20Handler.json) |
| Task Resolution Handler | Follow-up Cron | Checks for completed tasks | [`Task Resolution Handler.json`](https://github.com/HappyCowboyAI/personal-assistant/blob/main/n8n/workflows/Task%20Resolution%20Handler.json) |
| BBR Generator | Backstory SlackBot | Business review presentations | [`BBR Generator.json`](https://github.com/HappyCowboyAI/personal-assistant/blob/main/n8n/workflows/BBR%20Generator.json) |
| ICP Analysis | Slack Events Handler | ICP fit analysis | [`ICP Analysis.json`](https://github.com/HappyCowboyAI/personal-assistant/blob/main/n8n/workflows/ICP%20Analysis.json) |

## Utility Workflows

| Workflow | Purpose | Download |
|----------|---------|----------|
| Announcement Broadcast | Send messages to all users | [`Announcement Broadcast.json`](https://github.com/HappyCowboyAI/personal-assistant/blob/main/n8n/workflows/Announcement%20Broadcast.json) |
| Conversation Cleanup | Clean up stale conversation state | [`Conversation Cleanup.json`](https://github.com/HappyCowboyAI/personal-assistant/blob/main/n8n/workflows/Conversation%20Cleanup.json) |
| Executive Inbox | C-suite portfolio summary | [`Executive Inbox.json`](https://github.com/HappyCowboyAI/personal-assistant/blob/main/n8n/workflows/Executive%20Inbox.json) |
| Meeting Data Monitor | Monitor meeting data quality | [`Meeting Data Monitor.json`](https://github.com/HappyCowboyAI/personal-assistant/blob/main/n8n/workflows/Meeting%20Data%20Monitor.json) |

