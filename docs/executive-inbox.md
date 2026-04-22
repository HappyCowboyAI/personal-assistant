# AI Executive Inbox
### Programmable Executive Attention — Design & Build Spec

**Owner:** Scott Metcalf
**Role:** Head of AI, Backstory
**Status:** Active Experiment → Potential Company Blueprint
**Version:** v3.0

---

## The Honest Premise

This starts as a personal productivity experiment. It does not become a "company-wide operating model" until Phase 2 produces data worth showing anyone.

The core bet: an executive's inbox is not a communication tool — it's an attention allocation system. Right now that system is entirely manual, reactive, and undifferentiated. A tiered AI layer makes it selective, proactive, and measurable.

The goal is not to automate email. The goal is to free executive attention for the things that actually require it.

**The unfair advantage:** Backstory is a relationship intelligence platform. Every email that arrives can be immediately enriched with engagement scores, deal context, stakeholder maps, and relationship health — before a single classification rule fires. This is what separates this system from every generic email AI on the market.

---

## How Backstory Powers This System

Most email triage systems are flying blind on sender context. They classify by domain keywords, whitelist rules, or email content alone. This system has a relationship graph.

When an email arrives, before any classification logic runs, the system asks Backstory:

> *Who is this person, what's my relationship with them, what deals are active on their account, and how healthy is that relationship right now?*

The answers determine everything downstream — tier assignment, draft context, urgency, and routing.

### What Backstory Provides Per Email

| Signal | Source | Use |
|--------|--------|-----|
| Account match | `find_account` (domain lookup) | Identifies sender's company |
| Engagement score | `get_account_status` | Primary tier signal |
| Relationship health | `get_account_status` | Escalation trigger |
| Recent activity | `get_recent_account_activity` | Draft context |
| Open opportunities | `get_opportunity_status` | Risk flag (never auto-send on open deals) |
| Key stakeholders | `get_engaged_people` | Routing decisions |
| Account news | `account_company_news` | Context for drafts |

This isn't enrichment — it's the classification engine.

---

## The Assistant Alias

`scott.metcalf+assistant@people.ai` already routes to Scott's inbox. This becomes the foundation of the entire system — not just a detail.

**What the alias solves:**

**Transparency without a footer.** Emails sent FROM `scott.metcalf+assistant@people.ai` carry their own disclosure. The From address *is* the transparency statement. No verbose footer required. Sophisticated recipients understand the signal; others just get a quality response. Either way it's honest and defensible.

**Closed reply loop.** Replies to assistant-sent emails come back addressed to the +assistant alias — same sender, same context, same handling rules. The pipeline is self-reinforcing with no extra engineering.

**Inbound trust signal.** If someone emails the +assistant alias directly, they already know about and are comfortable with AI handling. The TO address in the webhook header distinguishes this from regular inbound — a useful signal for tier assignment.

**Outbound identity.** The assistant has its own email identity. The FROM address can be display-named "Scott Metcalf (AI Assistant)" or just left as the alias. Either way it's distinct, traceable, and honest.

---

## Backstory Already Captures Everything

Backstory captures email metadata and body from all of Scott's emails every 15 minutes, matching them to accounts and opportunities automatically.

**What this means for the system:**

- **Activity write-back is already solved.** When the assistant sends a reply from `+assistant@people.ai`, Backstory logs it as an email activity against the account. Engagement scores update automatically. No engineering required.
- **Email body available for the last 15 days.** `get_recent_account_activity` returns full email content for recent conversations — what was said, what was asked. Beyond 15 days, only metadata (subject, sender, date) is retained. Still useful for relationship signals, just not verbatim content.
- **48-hour lag for insights and dashboards.** Backstory processes captured data into insights within 48 hours. This means the *current inbound email* will not yet be in Backstory — it must be read directly from the Gmail webhook. Backstory enrichment covers everything *before* this email.
- **Sensitive content is automatically filtered.** Emails flagged as HR, legal, financial, or personal have their body redacted by Backstory before CRM sync. For our system, this is a feature: a redacted body is itself a signal to apply more conservative tier handling.

**The data split:**

| Data source | What it provides |
|-------------|-----------------|
| Gmail webhook | Current inbound email (body, headers, TO address) |
| Backstory | Everything prior: relationship health, engagement score, recent email history (body ≤15 days, metadata beyond) |

This is a clean division. Read the current email from Gmail. Understand the relationship from Backstory.

---

## Architecture

```
Email arrives → scott.metcalf@people.ai or +assistant alias
         ↓
  Gmail webhook: read email body + headers
  Note TO address (regular vs +assistant alias)
         ↓
  Extract sender email + domain
         ↓
  Backstory (parallel):
    find_account(domain)
    → get_account_status          [engagement score, health trend]
    → get_recent_account_activity [email body ≤15 days, metadata beyond]
    → get_opportunity_status      [open deals, stage, amount, close date]
         ↓
  ┌──────────────────────────────────────────────────┐
  │  TIER SIGNAL 1: Relationship (Backstory)          │
  │  High score + open deal → Tier 0                 │
  │  In CRM + any activity → Tier 1 minimum          │
  │  Not in CRM → intent classification decides       │
  │  Health declining + open deal → auto-Tier 0      │
  │                                                   │
  │  TIER SIGNAL 2: Inbound alias                     │
  │  TO=+assistant → sender opted in, lower friction  │
  │  TO=regular → apply conservative defaults         │
  │                                                   │
  │  TIER SIGNAL 3: Sensitive content flag            │
  │  Body redacted by Backstory → bump tier up        │
  └──────────────────────────────────────────────────┘
         ↓
  Claude: intent + sentiment + risk signals
  (receives: current email + Backstory context package)
         ↓
  Final tier = most conservative of all signals
         ↓
  Draft — grounded in:
    • Current email content (Gmail)
    • Prior conversation threads (Backstory, ≤15 days full, older = metadata)
    • Account health + deal context (Backstory)
    • Scott's voice spec + examples (Supabase)
         ↓
  [Auto-send FROM +assistant | Queue for approval | Archive]
         ↓
  Supabase: audit log
  Slack: daily digest
  Backstory: captures assistant's sent emails as activities automatically ✓
```

**Stack:**
- Gmail OAuth → n8n webhook trigger + send
- Backstory MCP (already available) — relationship enrichment + activity history
- Claude — intent classification + context-enriched drafting
- Google Sheets — Tier 0 whitelist (editable without touching n8n), audit log
- Gmail labels — `AI-Handled`, `AI-Archived`, `AI-Draft-Pending` (audit trail lives with the emails)
- n8n Static Data — ephemeral state (recent-contact flags, 24hr cooldowns)
- Slack — approval UX + daily digest

**No Supabase needed for Phase 1.** Everything is readable and editable without touching the workflow. Add a database only if this becomes multi-user.

One new credential beyond existing infra: Gmail OAuth. Everything else is already available.

---

## The Tier Model

Tier assignment uses **both** Backstory relationship data and Claude intent classification. The more conservative tier always wins.

---

### Tier 0 — Protected (Never Auto-Send)

**Who:** Board, CEO, exec team, investors, strategic accounts with open deals, any account with engagement score > 70

**Defined by:**
- Named list in Supabase (manually maintained for the innermost circle)
- Backstory signals: open opportunity + high engagement score
- Any account where relationship health is flagged as "at risk"

**AI role:**
- Surface immediately in Slack with account summary (deal stage, engagement trend, last touchpoint)
- Draft a context-enriched suggested response — never shown to sender
- Never send. Never archive.

**The Backstory difference:** A seemingly routine email from a customer gets auto-promoted to Tier 0 when Backstory shows their engagement dropped 25% this month and renewal is in 60 days. The email content doesn't have to reveal that — the relationship data does.

---

### Tier 1 — Draft + Approve

**Who:** Employees, partners, known vendors, warm inbound from CRM contacts with activity history

**Defined by:**
- Internal `@people.ai` domain
- CRM match with any logged activity (meeting, email, call)
- Backstory engagement score 30–70

**AI role:**
- Query `get_recent_account_activity` → pull last 3 interactions as draft context
- Draft response in Scott's voice, grounded in actual relationship history
- Surface in Slack: approve / edit / decline — one tap
- Batch approval for low-stakes drafts

**The Backstory difference:** The draft isn't generic — it references real context. "Good to hear from you — sounds like the Q1 sync with [name] went well" because the system knows about that meeting.

---

### Tier 2 — Auto-Send (Logged)

**Who:** Scheduling requests, speaking/podcast invites, event inquiries, known repeat inbound patterns

**Defined by:**
- No CRM match (not a known contact)
- No negative sentiment signals
- No open deal or revenue context
- Intent clearly low-stakes (schedule, invite, inquiry)

**AI role:**
- Draft and send automatically in Scott's voice
- Log in daily Slack digest with full email + response visible
- Escalation triggers override to Tier 1 automatically

**What does NOT belong in Tier 2:**
- Senders whose domain appears in Backstory as a current or past account — even if the contact isn't in CRM personally
- Any email mentioning pricing, contracts, or legal terms
- "Generic AI inquiries" — too broad (catches journalists, analysts, regulators)
- New contacts from company domains that ARE in CRM

---

### Tier 3 — Handle Silently

**Who:** Cold outbound sales, mass prospecting, newsletter spam, irrelevant solicitations

**Defined by:**
- No CRM match
- Cold outbound signals (bulk send headers, unsubscribe links, pitch language)
- No engagement with any Backstory account

**AI role:**
- Archive immediately
- Optional: polite one-line decline for higher-effort cold outreach
- **10% random sample surfaced in daily digest** — non-negotiable

The 10% sample exists because Tier 3 classification will have errors. A high-value contact who isn't in CRM yet will occasionally land here. You need to see it before the relationship is lost.

---

## Context-Enriched Drafting

This is the feature that separates this system from generic email AI.

Most email AI produces tonally-correct responses. This produces contextually-accurate, tonally-correct responses.

**Standard email AI:**
> "Thanks for reaching out! Happy to connect soon to discuss."

**Context-enriched (Backstory + Claude):**
> "Good timing on this — I know the team wrapped up onboarding last month and things should be hitting their stride. Happy to loop in [CSM name] on the technical question and get you on the calendar for a strategic check-in."

The system knows about the onboarding because `get_recent_account_activity` returned it. It knows the CSM because `get_engaged_people` returned them. The AI didn't guess — it read the relationship.

**What gets injected into every Tier 0/1 draft prompt:**
- Account name, engagement score, trend direction
- Current opportunity: stage, amount, close date
- Last 3 touchpoints: who, when, what
- Key internal stakeholders (AE, CSM) on the account
- Any recent news or signals from `account_company_news`
- Scott's voice spec + 3 calibrated example emails

---

## Relationship Health as an Escalation Signal

This is the most underexplored capability in the original design.

Backstory tracks relationship health over time. A declining engagement score from an existing account is a warning signal — regardless of what the email says.

**Escalation rules based on relationship data:**

| Condition | Action |
|-----------|--------|
| Engagement dropped >20% this month | Auto-promote to Tier 0, Slack alert with trend |
| Open deal in Stage 4+ (closing) | Lock to Tier 0, never auto-send |
| "At risk" account flag | Lock to Tier 0 |
| Contact is economic buyer on open deal | Tier 0 regardless of email intent |
| First email from known account domain | Tier 1 minimum, introduce to AE/CSM |
| Engagement trending up significantly | Surface in digest as "positive signal" |

The goal: the system responds to relationship context, not just email content. An email that reads as casual — "Hey Scott, quick question" — gets treated very differently when Backstory shows a $500K renewal at risk.

---

## Stakeholder Routing

Not every email Scott receives should be answered by Scott.

When Backstory identifies that:
- The sender is a customer contact with an assigned AE or CSM
- The email is operational rather than strategic
- The right person to respond is internal but not Scott

The system can:
1. Draft a response that CC's or hands off to the right person
2. Forward with context to the internal owner
3. Flag in Slack: "This looks like it belongs to [AE name] on the Acme account — route or respond?"

This protects Scott from becoming a support channel while keeping relationships intact.

---

## Activity Logging Back to CRM

Every email the system handles should be logged as an activity in Backstory.

**Why this matters:** If the system sends a Tier 2 auto-response on Scott's behalf, Backstory doesn't know it happened — the engagement signal goes unrecorded, and the relationship data drifts from reality.

**What to log:**
- Email received + classified tier
- Response sent (with body, for Tier 1/2)
- Response deferred (for Tier 0 — human responded later)
- No response (Tier 3 archive)

This keeps the relationship intelligence current and makes the system's actions visible in the CRM — not just in Slack.

**This problem is already solved.** Backstory captures all email activity automatically and matches it against accounts and opportunities. The system doesn't need to write back — it just needs to read forward.

---

## The Voice Problem (Concrete)

**How to define the voice:**

1. **Seed examples:** Pull 20–30 sent emails that represent Scott's preferred tone — short replies, substantive replies, polite declines, enthusiasm, internal vs. external. Label them by context type.

2. **Voice spec document (500 words):** Communication style — formality level, typical greeting, sign-off convention, sentence length preference, what you never say ("Certainly!", "Per my last email", "Circling back", any corporate filler).

3. **System prompt construction:** Claude receives: voice spec + 3 labeled examples calibrated to the email type (customer, internal, external stranger) + Backstory account context.

4. **Feedback loop:** Every Tier 1 draft that gets edited before approval is logged with a diff. Monthly review identifies drift patterns. Voice spec updated accordingly.

**Drift signal:** Edit rate > 40% means the voice spec needs work. Edit rate < 10% means Tier 2 can likely expand.

---

## The Escalation Mechanism

**Option A — Explicit sender trigger:**
Footer: *Reply with `[human]` anywhere in your message to request personal review.*

**Option B — AI-detected auto-escalation (primary):**
- Negative sentiment above threshold
- Legal language: contract, liability, counsel, litigation
- Urgency signals: urgent, ASAP, emergency, escalate
- Press / analyst affiliation detected in signature
- Backstory relationship health signals (see above)
- Open deal context found in enrichment

When triggered: downgrade to Tier 1, Slack alert with reason code.

**Recommended: Both.** Option B handles cases where the sender won't think to use the keyword. Option A is the explicit escape hatch they can share.

---

## Proactive Outreach (Phase 3 Concept)

The inbox doesn't have to be purely reactive.

Backstory knows:
- Which accounts haven't had executive contact in 30+ days
- Which deals are going quiet before a close date
- Which stakeholders have gone dark
- Which renewal conversations haven't started

The system could surface: *"You haven't been in touch with [contact] at [account] in 6 weeks — their deal is in Stage 3. Want to draft a check-in?"*

One tap → draft → send. The executive agenda is shaped by relationship intelligence, not just inbound volume.

This is the version of the system that becomes a company story.

---

## Transparency

**The alias is the disclosure.** `scott.metcalf+assistant@people.ai` in the From field is self-explanatory to anyone who looks. No footer disclaimer required for Tier 2 auto-sends.

For Tier 1 (draft + approve), Scott is sending — the From address is his regular address. No disclosure needed because it's his approved response.

**Optional soft footer for Tier 2** (if desired):
> *Sent via Scott's AI assistant. Reply with `[human]` to request personal review.*

Short. Not apologetic. Gives recipients the escape hatch without making the disclosure the centerpiece of every message.

**The alias as a public-facing feature.** Over time, Scott can share the +assistant address publicly — on a website, in a bio, on LinkedIn. "For general inquiries, reach my assistant at scott.metcalf+assistant@people.ai." This sets expectations upfront and self-selects senders into the right pipeline before the email even arrives.

---

## Observability

**Daily Slack digest:**
- Emails received, by tier breakdown
- Tier 2 auto-sent: full list with links to review
- Tier 3 archived: count + 10% sample
- Escalations: how many, why, triggered by what
- Tier 0 flagged: account summary + Backstory context
- Drafts pending approval

**Monthly metrics:**
- Tier 1 edit rate (target: 10–30%)
- Tier 2 escalation rate (target: < 5%)
- Tier 3 misclassification catches (from sample review)
- Estimated time saved
- Relationship health trend for Tier 0 contacts

---

## Risk Register

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| Auto-response to strategic contact damages relationship | High | Low | Tier 0 hard protection + Backstory open deal lock |
| Tone drift | Medium | Medium | Monthly calibration, edit rate monitoring |
| Missing signal in Tier 3 | Medium | Medium | 10% sample in daily digest |
| CRM data lag causes wrong tier assignment | Medium | Low | Enrichment freshness check; default to Tier 1 on stale data |
| Activity not logged → engagement score drifts | Medium | Medium | Phase 2: write-back to Backstory |
| Proactive outreach feels intrusive | Low | Low | Opt-in per suggestion, not auto-send |
| Transparency statement causes over-escalation | Low | Low | A/B test footer copy |

---

## Rollout

### Phase 0 — Voice Definition (1 week, before building anything)
- Curate 20–30 seed emails
- Write voice spec document
- Draft Tier 0 named list
- Confirm email platform (Gmail or Outlook)
- Test Backstory domain lookup on sample senders

### Phase 1 — Classify + Draft, No Auto-Send (4 weeks)
- Gmail connected, all inbound classified and enriched
- Backstory context pulled for every CRM-matched sender
- Drafts generated for Tier 1 and Tier 2 — human sends all
- Measure: classification accuracy, draft quality, edit rate
- Gate: >70% of drafts sendable as-is

### Phase 2 — Tier 2 Auto-Send (6–8 weeks)
- Tier 2 sends automatically, logged in daily digest
- Relationship health escalation rules active
- Monitor: escalation rate, tone feedback, any relationship friction
- Gate: zero Tier 0 misclassifications, edit rate stable

### Phase 3 — Scale Decision + Proactive Layer
- Review Phase 2 data
- If working: internal case study, evaluate multi-user version
- If not: diagnose and fix before expanding scope
- Proactive outreach suggestions (opt-in, not auto-send)
- Activity write-back to Backstory CRM

---

## Gmail-Specific Implementation Notes

**Email platform: Gmail (Google Workspace)** ✓

**Inbound trigger:** n8n Gmail node, polling every 1 minute for Phase 1. Upgrade to Gmail Pub/Sub push notifications for Phase 2 (true real-time, requires Google Cloud project setup).

**Credentials:** Google OAuth2 — same flow as the existing Google Slides and Drive credentials in n8n. New credential with Gmail scopes: `gmail.readonly` + `gmail.send` + `gmail.modify` (for archiving Tier 3).

**The + alias outbound — confirmed working ✓**
`scott.metcalf+assistant@people.ai` sends and receives correctly. Recipients see the full alias in the From field. Replies return to the alias. No IT involvement required. The closed reply loop is confirmed.

**Reading the TO address:** Gmail API returns the full `To` header including + suffix. n8n's Gmail trigger exposes headers — detect `+assistant` in the TO field to identify opted-in inbound.

**Sending:** Gmail API `users.messages.send` with From header set to the alias. Works if alias is configured under "Send mail as."

**Archiving Tier 3:** Gmail API `users.messages.modify` — remove `INBOX` label, add custom `AI-Archived` label. Keeps audit trail, doesn't permanently delete.

---

## Open Design Decisions

Remaining decisions before building:

1. **Approval UX:** Slack buttons (fastest, already built for other workflows) vs. lightweight web UI (better for batch review). Start with Slack — already proven in this stack.

2. **Backstory data staleness threshold:** If `get_account_status` returns data last updated > 30 days ago, default to Tier 1 rather than trust the classification score. What's the right window? Suggest 14 days for active accounts, 45 days for known-dormant.

3. **Who is on the Tier 0 named list?** Write it now, before building. Named list lives in Supabase. Don't leave for later — this is the most important safety decision in the system.

4. **AE/CSM routing:** Does the "this email belongs to the account team, not Scott" routing feature add value in Phase 1, or does it create internal noise before the system is proven? Suggest deferring to Phase 2.

5. **Outbound alias:** Confirmed working ✓ — `scott.metcalf+assistant@people.ai` sends and receives correctly with no IT required.

---

## The Key Question

**Personal experiment or company initiative?**

Start as: personal experiment.

Upgrade to company initiative when Phase 2 produces:
- Measurable time savings (hours/week, not minutes)
- Zero relationship damage
- Acceptable draft quality without heavy editing
- A Backstory-specific story about relationship intelligence as the differentiator

That last point is the company angle. The story isn't "Scott automated his email." The story is "Backstory's relationship intelligence made executive communication measurably smarter." That's a product story, a press story, and an internal culture story — all from the same experiment.

The inbox becomes a testbed. The data becomes the pitch.

---

## Path to Customer Product

The personal experiment is the design lab. The customer product is the goal. Here's what changes.

### The Defensible Moat

No third-party email AI knows:
- Which accounts are at risk before the rep even reads the email
- Who the decision makers are and how engaged they are
- What was discussed in the last meeting (body captured for 15 days)
- Which deals are closing this quarter and at what stage

That's the moat. An email assistant powered by Backstory relationship intelligence is defensible in a way that generic AI email tools aren't. The classification engine *is* the product differentiation.

---

### Two Product Models

**Model A — Executive Intelligence Layer**
*Closer to the personal experiment design*

- Target: CROs, VP Sales, C-suite, and their direct reports
- Full tier model including controlled auto-send
- Personalized voice, personal Tier 0 protection
- Positioning: "Programmable executive attention for revenue leaders"
- Risk: higher — auto-send at executive level requires trust and robust guardrails

**Model B — Rep-Level Draft Assist** *(recommended first product)*

- Target: AEs, CSMs, Account Managers
- Draft-only — AI drafts context-enriched responses, rep approves and sends
- No auto-send — safer, easier to sell past enterprise security and compliance
- Positioning: "Every customer email answered with full deal context in 30 seconds"
- Risk: lower — no unsupervised sends, rep is always in the loop

Model B is the better first product. Draft-only is far easier to sell to enterprise (legal, compliance, and IT all have fewer objections), the user base is 10x larger, and the ROI story is simple: reps respond faster with more context, without leaving their inbox to dig through Salesforce.

Model A is where you go after Model B is proven. Same infrastructure, higher autonomy dial.

---

### What Changes Architecturally for Customer Scale

| Personal experiment | Customer product |
|---------------------|-----------------|
| One voice spec, hardcoded | Per-user voice onboarding at setup (3-5 example emails) |
| Google Sheet for Tier 0 list | Per-user config in Supabase (multi-tenant) |
| Scott's Backstory OAuth | Per-user Backstory OAuth — each rep reads their own data |
| Gmail label audit trail | Per-user audit log with org-level admin visibility |
| Slack for approvals | In-context approval: Gmail plugin, mobile, or Slack per-user |
| n8n Static Data for state | Multi-tenant state management |
| No admin layer | RevOps console: org-level Tier 0 domains, auto-send policy by role |

**The per-user Backstory OAuth is the critical unlock.** Each user's assistant must access their relationship data, not a shared service account. This is the primary engineering question that determines product feasibility and timeline.

---

### What the Personal Experiment Needs to Prove

Before pitching this as a customer product, the experiment needs to answer:

1. **Does Backstory enrichment actually improve classification?** Are known CRM contacts getting correctly elevated vs. cold contacts?
2. **Does context-enriched drafting produce meaningfully better drafts?** Would a rep send the AI draft, or rewrite it?
3. **What's the real time savings number?** Measured, not estimated. Emails handled × average response time saved = hours per week. That's the ROI slide.
4. **What breaks at volume?** Classification errors, voice drift, false escalations — which failure modes matter at scale?

Phase 1 (draft-only, 4 weeks) answers questions 2 and 4.
Phase 2 (limited auto-send, 6-8 weeks) answers questions 1 and 3.

With that data, you have a case study. With a case study, you have a product pitch.

---

### The Product Story

*"Your reps spend hours every week answering customer emails from memory — digging through Salesforce for context, guessing at deal stage, trying to remember what was said on the last call. Backstory already knows all of that. We connect the two: every inbound customer email gets an AI-drafted response grounded in live relationship intelligence. Reps review and send in 30 seconds. The CRM stays current automatically — Backstory was already capturing everything."*

That story works for any enterprise sales org. It extends Backstory's existing value proposition — relationship intelligence — into the surface reps live in every day: their inbox.
