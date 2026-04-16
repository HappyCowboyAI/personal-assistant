# Overview

The People.ai Personal Assistant is a proactive, AI-powered sales assistant delivered through your team's chat platform. Each sales rep gets a named, personalized assistant that monitors their pipeline and delivers insights without being prompted.

> **Supported platforms:** Slack (primary), Microsoft Teams, and Google Chat. This guide is written with Slack as the reference platform, with Teams and Google Chat alternatives noted where the setup differs.

The assistant is not a chatbot — it's an agent with its own agenda that runs on a schedule and acts proactively.

## What It Does

- **Morning Pipeline Digests** — Every weekday, each rep receives a personalized briefing covering pipeline changes, deal risks, engagement shifts, and recommended actions
- **On-Demand Intelligence** — Reps ask questions about accounts, opportunities, and pipeline via chat commands and get answers grounded in CRM data
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
| **Delivery** | Slack, Teams, or Google Chat | All user interaction — onboarding, digests, commands, approvals |
| **Data Store** | PostgreSQL | Multi-tenant user/org data, message logs, pending actions |

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Schedule    │────▶│     n8n      │────▶│  Chat Platform│
│  (Cron/Event) │     │ Orchestrator │     │  (Delivery)   │
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

A single bot serves all users. How the personalized name appears depends on the platform:

| Platform | Per-Message Name Override | How It Works |
|----------|--------------------------|-------------|
| **Slack** | Yes | `chat:write.customize` scope overrides display name and avatar per message |
| **Microsoft Teams** | No | Bot has a fixed name set in Azure Bot Service. Personalization uses the greeting text instead (e.g., "Hey, it's ScottAI") |
| **Google Chat** | No | App has a fixed name set in Google Cloud Console. Same greeting-based personalization as Teams |

## What This Guide Covers

This guide walks through deploying the assistant for your organization:

1. **[Prerequisites](prerequisites.md)** — Accounts and access you need
2. **[Chat Platform Setup](slack-setup.md)** — Configuring Slack, Microsoft Teams, or Google Chat
3. **[Database Setup](database-setup.md)** — Schema and tables
4. **[n8n Setup](n8n-setup.md)** — Importing workflows and configuring credentials
5. **[Onboarding Configuration](onboarding-config.md)** — Setting org defaults and customization options
6. **[Workflow Reference](workflow-reference.md)** — What each workflow does and when it runs
7. **[Troubleshooting](troubleshooting.md)** — Common issues and how to resolve them
