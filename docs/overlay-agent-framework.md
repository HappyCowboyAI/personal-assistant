# Overlay Agent Framework

## Origin

CEO Jason Ambrose identified the need for a testimonial-tracking agent — something to birddog account teams into getting customer ROI stories, drafting writeups, and tracking approvals. The insight: this is a general pattern that applies to any **overlay team** that needs to drive action through account owners.

## The Problem

Overlay teams (Customer Marketing, AI Innovation, Alliances, Enablement) don't own accounts but need account teams to take action. Today this is manual: spreadsheets, Slack pings, lost follow-ups. Nobody owns the end-to-end tracking, so things stall.

## The Pattern

Every overlay role follows the same loop:

```
Scan for signals → Surface candidates → Nudge account team → Track to outcome
```

| Overlay Role | "Candidates" | Signals | Nudge Target | Desired Outcome |
|---|---|---|---|---|
| Customer Marketing | Testimonial candidates | High engagement, renewal, expansion | AE/CSM | Published case study |
| AI Innovation | AI adoption candidates | Low AI feature usage, high potential | AE/CSM | Customer AI activation |
| Partner/Alliances | Co-sell candidates | Partner ecosystem overlap, deal stage | AE | Joint deal motion |
| Customer Success | Expansion candidates | Usage growth, champion engagement | AE | Upsell/cross-sell |
| Presales/SE | Technical validation | POC readiness, technical champion | AE | Completed POC |
| Enablement | Training candidates | Low adoption, new feature rollout | CSM/AE | Training completed |

## Architecture

### Design Principles

- **No Supabase dependency** — data lives in Salesforce for productizability
- **n8n for orchestration only** — crons, Slack delivery, Claude agent calls
- **People.ai MCP for signals** — engagement scores, activity data, deal history
- **Slack for delivery** — personalized DMs, interactive buttons, channel digests
- **Generic framework** — same workflow handles any initiative type, only the Claude prompt changes

### Salesforce Object Model

Two custom objects:

```
Campaign_Initiative__c (the overlay program)
├── Name                    -- "Q1 Testimonial Pipeline", "AI Activation Push"
├── Type__c                 -- picklist: testimonial, ai_adoption, co_sell, expansion, poc, training
├── Owner__c                -- the overlay team lead (Kimberly, Scott, etc.)
├── Scoring_Criteria__c     -- JSON config defining what signals matter for this initiative
│                              e.g. {"min_engagement_score": 80, "recent_renewal": true,
│                                    "min_deal_size": 100000}
├── Nudge_Cadence_Days__c   -- how often to follow up (default: 7)
├── Slack_Channel__c        -- optional channel for pipeline updates (e.g. #testimonial-pipeline)
├── Status__c               -- Active / Paused / Completed
├── Created_Date
└── Last_Scan_Date__c       -- when the agent last scanned for candidates

Initiative_Candidate__c (each account being tracked)
├── Initiative__c           -- lookup → Campaign_Initiative__c
├── Account__c              -- lookup → Account
├── Stage__c                -- picklist: Identified → Engaged → In Progress → Completed → Skipped
├── Assigned_To__c          -- the account owner being nudged (lookup → User)
├── AI_Score__c             -- numeric score: why this account was selected
├── AI_Rationale__c         -- long text: Claude's explanation of why this is a good candidate
├── Last_Nudge_Date__c      -- when the last Slack nudge was sent
├── Next_Nudge_Date__c      -- when the next nudge should fire
├── Nudge_Count__c          -- how many times we've nudged
├── Story_Draft__c          -- long text: Claude-generated draft (testimonial, activation plan, etc.)
├── Outcome_Notes__c        -- what happened (free text from account owner)
├── Completed_Date__c
└── Skip_Reason__c          -- why it was skipped (optional)
```

### n8n Workflows

Three workflows, all generic across initiative types:

#### 1. Initiative Scan Cron (weekly)

```
Schedule Trigger (weekly)
  → Get Active Initiatives (Salesforce SOQL: Campaign_Initiative__c WHERE Status = Active)
  → Split In Batches (per initiative)
    → Get Scoring Criteria (from initiative record)
    → Query People.ai MCP (engagement scores, activity data matching criteria)
    → Score Candidates (Claude agent: rank accounts, explain rationale)
    → Get Existing Candidates (Salesforce: Initiative_Candidate__c for this initiative)
    → Filter New Candidates (Code: skip accounts already tracked)
    → Create Candidate Records (Salesforce: insert Initiative_Candidate__c)
    → Notify Initiative Owner (Slack DM: "Found 3 new candidates for your Q1 Testimonial Pipeline")
```

#### 2. Nudge Cron (daily)

```
Schedule Trigger (daily, 9am)
  → Get Due Nudges (Salesforce SOQL: Initiative_Candidate__c
      WHERE Next_Nudge_Date__c <= TODAY AND Stage__c NOT IN ('Completed', 'Skipped'))
  → Split In Batches (per candidate)
    → Get Initiative Details (type, context)
    → Build Nudge Message (Claude agent: personalized message based on initiative type,
        account context from People.ai, nudge count)
    → Resolve Slack User (map Assigned_To email → Slack user ID)
    → Send Nudge DM (Slack chat.postMessage with interactive buttons:
        "Working on it" / "Need help" / "Skip" / "Done")
    → Update Nudge Tracking (Salesforce: Last_Nudge_Date, Next_Nudge_Date, Nudge_Count)
```

#### 3. Interactive Handler (button clicks)

Extends existing Interactive Events Handler or new webhook:

```
Webhook (Slack block_actions)
  → Parse Action (which button, which candidate)
  → Switch by Action:
    → "Working on it" → Update stage to In Progress, reset nudge cadence
    → "Need help" → Notify initiative owner, offer to draft content
    → "Skip" → Modal: ask for skip reason → Update stage to Skipped
    → "Done" → Update stage to Completed, notify initiative owner
    → "Draft Story" → Claude agent generates draft from People.ai data
        → Attach to Salesforce record → DM draft to account owner for review
```

### Claude Prompt Design

The same workflow calls Claude with different system prompts based on `Initiative.Type__c`:

**Testimonial scoring prompt:**
```
You are evaluating whether {account} is a good testimonial candidate.
Consider: engagement score ({score}), recent renewal ({renewal_date}),
deal size ({deal_size}), champion relationships ({contacts}).
Score 0-100 and explain your rationale in 2-3 sentences.
```

**AI Adoption scoring prompt:**
```
You are evaluating whether {account} is a good candidate for AI activation.
Consider: current AI feature adoption ({adoption_pct}), account value ({arr}),
recent SE engagement ({se_meetings}), technical champion presence ({tech_contacts}).
Score 0-100 and explain your rationale.
```

**Nudge message prompt:**
```
You are nudging {assigned_to} about {account} for the "{initiative_name}" program.
This is nudge #{nudge_count}. Previous stage: {stage}.
Context from People.ai: {engagement_summary}.
Write a brief, friendly Slack message (3-4 sentences) that:
- References specific recent activity or signals
- Makes a clear ask
- Doesn't feel like spam (vary the approach based on nudge_count)
```

## Implementation Plan

### Phase 1: Testimonial MVP (internal, 1-2 weeks)

1. **Salesforce setup**: Create the two custom objects with fields above
2. **Seed data**: Kimberly manually creates the first `Campaign_Initiative__c` for testimonials
3. **Scan workflow**: Weekly cron that queries People.ai for high-engagement renewed accounts, scores them with Claude, creates candidate records
4. **Nudge workflow**: Daily cron that DMs account owners with context and buttons
5. **Interactive handler**: Button clicks update Salesforce stages
6. **Draft generation**: "Draft Story" button triggers Claude to write a testimonial framework from People.ai data

### Phase 2: AI Innovation Initiative (internal, add-on)

- Create a second `Campaign_Initiative__c` for AI adoption
- Same workflows, different scoring criteria and prompts
- Validates the framework is truly generic

### Phase 3: Productize

- Package as a People.ai feature: "Initiative Tracking"
- Customer creates initiatives in Salesforce, agent runs against their People.ai data
- Configuration UI for scoring criteria (or Claude-powered natural language config: "Find me accounts that renewed in the last 6 months with engagement scores above 80")
- Reporting dashboard in Salesforce

## Key Decisions Still Open

1. **Salesforce auth in n8n**: Need OAuth credentials for People.ai's Salesforce instance. Do we use a service account or connected app?
2. **Slack user resolution**: How do we map Salesforce User → Slack user ID? Options: email match against Slack users.list, or store Slack IDs on the Salesforce User record
3. **Scope of first initiative**: Should the testimonial MVP auto-discover candidates (fully agentic) or start with Kimberly seeding candidates manually (agent just nudges and drafts)?
4. **Channel vs DM**: Should pipeline updates go to a shared channel (#testimonial-pipeline) or just DM the initiative owner?
5. **Escalation**: What happens when nudges are ignored? Auto-escalate to manager after N nudges?

## Product Positioning

Jason's insight: "This would be valuable to other software customers." The framework maps to a real market need:

- **Every B2B company** has overlay teams struggling with the same coordination problem
- **People.ai's unique advantage**: the engagement signals that power candidate scoring already exist in the platform
- **Natural extension**: "We already tell you who's engaged. Now we help your overlay teams act on it."
- **Differentiation**: Not just a pipeline tracker — it's AI-powered candidate discovery + personalized nudging + content generation

The testimonial use case is the wedge. The overlay orchestration framework is the platform.
