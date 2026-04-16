# Personal Assistant — Admin Deployment Guide

A proactive, AI-powered sales assistant delivered through your team's chat platform. Each rep gets a named, personalized assistant that monitors their pipeline and delivers insights — before they ask.

> **Supported platforms:** Slack (primary), Microsoft Teams, and Google Chat. This guide covers Slack as the reference platform, with Teams and Google Chat alternatives noted where setup differs.

---

## At a Glance

| | |
|---|---|
| **⏱ Deploy Time** | 2–4 hours |
| **🔧 Workflows** | 27 importable n8n JSONs |
| **🤖 LLM** | Any — Claude, ChatGPT, Gemini, Mistral |
| **📡 Data** | People.ai MCP + Query API |
| **💬 Delivery** | Slack, Teams, or Google Chat |

---

## What Reps Get

### Proactive (runs on its own)

| Feature | When | What |
|---------|------|------|
| **Morning Digest** | 6am weekdays | Role-aware pipeline briefing — risks, next steps, engagement signals |
| **Meeting Brief** | 2hr before meetings | Participant history, deal context, talking points |
| **Meeting Recap** | After meetings | AI summary, action items, one-click Salesforce save |
| **Deal Watch** | 7am weekdays | Stage transitions, amount changes, close date shifts |
| **Silence Alert** | 6:30am weekdays | Accounts going quiet — before it's too late |

### On-Demand (type a command)

| Command | What It Does |
|---------|-------------|
| `brief` | Instant pipeline briefing |
| `recap <account>` | Meeting recap with CRM integration |
| `insights` | Deep analysis — stalled, at-risk, accelerating deals |
| `stakeholders <account>` | Engagement map across the buying committee |
| `silence` | Which accounts have gone dark |
| `presentation <topic>` | Auto-generate a branded slide deck |
| *Just ask anything* | Natural language questions about deals and accounts |

---

## Architecture

The assistant runs on a three-layer stack — no custom backend code required.

| Layer | Component | Role |
|-------|-----------|------|
| **Orchestration** | n8n | Scheduling, API routing, conditional logic, message delivery |
| **Reasoning** | LLM (Claude, ChatGPT, Gemini, etc.) | Synthesizes data into natural language briefings and recommendations |
| **Intelligence** | People.ai API + MCP | Engagement scores, activity signals, deal health, stakeholder data |
| **Delivery** | Slack, Teams, or Google Chat | All user interaction — onboarding, digests, commands, approvals |
| **Data Store** | PostgreSQL | Multi-tenant user/org data, message logs, pending actions |

```
┌──────────────┐     ┌──────────────┐     ┌───────────────┐
│   Schedule    │────▶│     n8n      │────▶│ Chat Platform │
│  (Cron/Event) │     │ Orchestrator │     │  (Delivery)   │
└──────────────┘     └──────┬───────┘     └───────────────┘
                            │
                    ┌───────┴───────┐
                    │               │
              ┌─────▼─────┐  ┌─────▼──────┐
              │    LLM     │  │ People.ai  │
              │ (Reasoning)│  │ (Intel)    │
              └───────────┘  └────────────┘
                    │
              ┌─────▼──────┐
              │ PostgreSQL  │
              │   (Data)    │
              └────────────┘
```

---

## Personalization

The most important product decision: **every rep names their own assistant.** When a rep picks a name — ScottAI, Luna, Aria — the mental model shifts from "the company's AI tool" to "my assistant." This drives adoption.

A single bot serves all users. How the name appears depends on the platform:

| Platform | Per-Message Name Override | How It Works |
|----------|--------------------------|-------------|
| **Slack** | ✅ Yes | `chat:write.customize` overrides display name and avatar per message |
| **Microsoft Teams** | ❌ No | Fixed bot name — personalization via greeting text ("Hey, it's ScottAI") |
| **Google Chat** | ❌ No | Fixed app name — same greeting-based approach as Teams |

---

## Deployment Steps

| Step | Page | Time |
|------|------|------|
| 1 | [Prerequisites](prerequisites.md) | 10 min |
| 2 | [Chat Platform Setup](slack-setup.md) | 30–45 min |
| 3 | [Database Setup](database-setup.md) | 20 min |
| 4 | [n8n Setup](n8n-setup.md) | 45–60 min |
| 5 | [Onboarding Configuration](onboarding-config.md) | 15 min |
| 6 | [Workflow Reference](workflow-reference.md) | Reference |
| 7 | [Troubleshooting](troubleshooting.md) | As needed |

> **Source code:** All workflow JSONs, database migrations, and prompt templates are in the [GitHub repository](https://github.com/HappyCowboyAI/personal-assistant).
