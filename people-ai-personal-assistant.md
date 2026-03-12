# People.ai Personal Assistant — Project Concept

> A conversational, agentic AI assistant that works for sales reps around the clock — built on People.ai intelligence, delivered through Slack and email, orchestrated with n8n.

---

## The Core Idea

A named, personal AI assistant for every sales rep that monitors their pipeline continuously and delivers the right insight at the right moment — without being asked. Not a dashboard to check. Not a chatbot to prompt. An assistant that does the work while the rep is focused on selling (and while they sleep).

The product is built on three pillars:

**People.ai as the intelligence layer** — engagement scores, activity signals, deal health, stakeholder intel from the last 30 days of communications.

**Claude (Anthropic API) as the reasoning layer** — synthesizing signals into natural language briefings, drafting follow-ups, identifying risk patterns, writing personalized outputs.

**n8n as the orchestration layer** — scheduling workflows, routing API calls, handling conditional logic, delivering outputs to Slack and email without custom backend infrastructure.

---

## Why Naming the Assistant Matters

The single most important product decision is letting each rep name their assistant.

When a rep names their assistant — ScottAI, Max, Luna, Aria — they own it. The mental model shifts from "the company's AI tool watching my deals" to "my assistant who works for me." This dramatically lowers AI adoption anxiety, which is one of the biggest barriers in enterprise software right now.

The viral mechanic this creates is powerful: when a rep gets a great pre-meeting briefing and the call goes well, they tell a colleague — and they use the assistant's name. "Honestly ScottAI had everything ready for me." That's word of mouth you can't buy.

**Onboarding step one is not "connect your CRM." It is "what do you want to call your assistant?"**

---

## Competitive Context

Both primary competitors have mobile and assistant presence, but occupy distinct territory:

**Gong** owns call intelligence — recordings, summaries, coaching. Their mobile app lets reps listen to calls and get AI summaries on the go.

**Clari** owns forecasting — pipeline roll-ups, commit calls, manager-layer review. Their mobile app is built for the VP reviewing the weekly number.

**The gap People.ai can own:** rep-level deal intelligence at the moment of a customer interaction. The "here's what's happening in my deals right now and what should I do next" layer. Neither Gong nor Clari is squarely focused on that at-risk deal / next best action angle that People.ai's engagement scoring enables.

A named personal assistant positions around a distinct persona and moment — the rep in the field who needs actionable guidance, not recordings or forecast commits.

---

## What Sellers Actually Want

The core seller pain is cognitive load. Reps juggle 20+ deals, hundreds of emails, multiple tools, and a manager asking for forecast updates. A great assistant reduces that burden by doing the thinking, not just surfacing the data.

What sellers want an assistant to deliver:

**"Tell me what matters today"** — not a dashboard to interpret, but a prioritized list of what needs attention and why.

**"Help me prepare for this conversation"** — before a call, give me everything in 30 seconds: who I'm talking to, where the deal stands, what was discussed last time, what to push on.

**"Draft this for me"** — write the follow-up email, the re-engagement message, the champion summary. With deal context already baked in.

**"What should I say to get this unstuck"** — not just data, but a recommendation grounded in the specific deal situation.

**"Don't make me update Salesforce"** — capture activity automatically, surface what's missing, remove the daily CRM hygiene tax.

The pattern: sellers want the assistant to do the thinking, not just show the information.

---

## Key Features

### 🌅 Nightly Deal Digest
Every morning, each rep receives a personalized briefing in Slack from their named assistant. It covers pipeline changes since yesterday, deals that need attention today, engagement score movements, and any new risks detected. No prompt required — it just arrives.

### 📋 Pre-Meeting Briefing
Triggered by calendar events, two hours before any customer meeting the assistant automatically assembles a full prep packet: who's attending, their engagement history, recent email and call activity, deal risks, and suggested talking points. Delivered to Slack or email.

### ✉️ Auto-Drafted Follow-Ups
When a deal goes dark, the assistant drafts a personalized re-engagement email with context from the last conversation. It surfaces in Slack as a one-click approval — the rep reviews, taps send. The assistant does the writing, the human makes the call.

### ⚠️ Stakeholder Drift Alerts
When a champion hasn't engaged in three weeks, the assistant flags it proactively — without being asked. It surfaces who else to activate and suggests an approach.

### 📊 Forecast Anomaly Detection
A deal that's been "Commit" for 60 days with declining engagement gets flagged to the manager automatically before the forecast call. No one has to notice it manually.

### 🧹 CRM Hygiene on Autopilot
Missing close dates, stale stages, deals with no activity logged — the assistant detects these and either updates them automatically or sends a targeted nudge to the rep.

---

## The Agentic Shift

The distinction that makes this a product rather than a chatbot: **the rep doesn't have to ask.**

A chatbot waits for a prompt. An agent has its own agenda — it knows what good pipeline health looks like and pursues it continuously. The assistant isn't reactive, it's proactive. It runs while the rep sleeps.

The key design question is how much autonomy the agent has. A spectrum from "drafts everything, human approves" to "sends emails on the rep's behalf automatically." Most reps will want to stay closer to the approval end initially — but trust and autonomy can expand as the relationship develops. This maps naturally to the naming and ownership dynamic: the more a rep feels the assistant is theirs, the more autonomy they'll extend to it.

---

## Technical Architecture

### Stack
| Layer | Tool |
|-------|------|
| Orchestration | n8n |
| Intelligence | People.ai MCP + Insights API |
| Reasoning | Claude via Anthropic API |
| Delivery | Slack + Email |
| Data store | Supabase (or Airtable for v1) |

### Slack Personalization
A single Slackbot serves all users. Slack's API allows display name and avatar overrides per message — so each rep receives a message that appears to come from their named assistant, without requiring a separate bot per user. In n8n this is a single field on every Slack node.

### Onboarding Flow (Entirely in Slack)
1. Bot DMs new user: *"Hi! Before we get started — what do you want to call me?"*
2. Rep replies with a name
3. n8n stores: Slack user ID → assistant name, People.ai ID, preferences
4. Bot confirms: *"Nice to meet you. I'm ScottAI. Your first briefing arrives tomorrow morning."*

No external onboarding UI needed for v1. The naming conversation, the daily digest, the meeting prep, the email draft approvals — all in Slack.

### Rename Command
Rep DMs the bot "rename Max" at any point. n8n catches the pattern and updates their record. The assistant feels alive and responsive.

---

## Build Sequence (Solo Developer)

### Month 1 — Nightly Digest
A cron trigger in n8n fires at 6am, pulls open opportunities from People.ai, passes data to Claude with a briefing prompt, and posts a personalized Slack DM from the named assistant. Get this in front of 2–3 real reps internally. Gather feedback obsessively.

**v1 scope:** 6–8 n8n nodes, one Google Sheet as data store, one Slackbot, one Claude prompt.

### Month 2 — Pre-Meeting Briefing
Add a calendar trigger. Two hours before any customer meeting, the assistant assembles and delivers a prep packet automatically. Now the agent has two moments of value daily.

### Month 3 — First Agentic Action
Add one action the assistant can take: draft a re-engagement email and surface it in Slack for one-click approval. This is the transition from notification system to agent. The rep doesn't write the email — they just approve it.

### Month 4 — Shareable Demo
By now: real users, real feedback, a compelling demo, a story. This is when you start convincing others to join the project.

---

## Designing for Customers from Day One

Although the initial build is internal, the architecture should assume multiple customers from the start. Retrofitting multi-tenancy is painful.

**What this means practically:**

**Database scoping** — every record scoped to a customer organization, not just a user. Airtable is fine for internal v1, Supabase for anything customer-facing.

**Slack OAuth** — each customer installs the bot in their own workspace. This requires a proper Slack app with OAuth rather than a simple webhook. Plan for this before building the customer-facing version.

**Credential storage** — each customer brings their own People.ai API credentials. These need secure per-tenant storage, not a config file.

**Two-level naming** — for customers, the company sets a default assistant name and persona. Individual reps can customize on top of that. "Your company default is Aria, but you can rename her whatever you want."

**Admin UI** — eventually a simple web page where a new customer connects their People.ai account, connects their Slack workspace, sets their default assistant persona, and sees who's onboarded. This is a month 3–4 problem but worth knowing it's coming.

**The core n8n workflow logic, Claude prompting, and Slack delivery pattern translates directly from internal to customer use.** That's the reusable IP. Design it cleanly from the start.

---

## The Opportunity

The technology here is almost secondary to the relationship design. What makes a named personal assistant compelling isn't the AI — it's the ownership, the habit, and the trust that builds over time as the assistant proves its value.

The assistant that helps a rep close a big deal won't be remembered as "the People.ai tool." It'll be remembered by its name. That's the moat.

---

*Document generated from a product exploration conversation. Last updated February 2026.*
