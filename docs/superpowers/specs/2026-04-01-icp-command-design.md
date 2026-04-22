# ICP Command — Design Spec

**Date:** 2026-04-01
**Status:** Draft
**Origin:** Ported from accountinsights project (`icp_calibration_v1.json`)

## Overview

Add an `icp` command to the Backstory Personal Assistant with three modes:

| Command | Mode | What it does | Runtime |
|---------|------|-------------|---------|
| `icp` | calibrate | Full win pattern fingerprint — 30 won vs 30 lost, 15 deep dives | 3-5 min |
| `icp targets` | targets | Surface unengaged accounts matching ICP, filtered by user role | ~30 sec |
| `icp <company>` | compare | Score a specific account against the winning pattern | ~30 sec |

All results delivered as a DM to the requesting user.

## Command Routing

The Slack Events Handler (`QuQbIaWetunUOFUW`) Route by State code node adds a `cmd_icp` route:

```
if text == "icp"                     → route: cmd_icp, mode: calibrate
if text == "icp targets"             → route: cmd_icp, mode: targets
if text starts with "icp " (other)   → route: cmd_icp, mode: compare, companyName: remainder
```

The Switch node gets a new `cmd_icp` output that wires to:
1. **Open Bot DM** — `conversations.open` with the user's Slack ID to get the DM channel ID
2. **Send ICP Thinking** — posts a mode-specific thinking message to the DM channel
3. **Prepare ICP Input** — builds the sub-workflow payload (includes `channelId` from step 1)
4. **Execute ICP Workflow** — calls the sub-workflow

### Thinking Messages

- calibrate: `:mag: Running ICP calibration — analyzing won vs lost patterns... this takes 3-5 minutes.`
- targets: `:mag: Finding target accounts matching your ICP... give me about 30 seconds.`
- compare: `:mag: Comparing *{companyName}* against your winning pattern... give me about 30 seconds.`

## Sub-workflow Architecture

One new sub-workflow ("ICP Analysis") receives a payload and branches by mode.

### Input Payload

```json
{
  "mode": "calibrate | targets | compare",
  "companyName": "",
  "userId": "uuid",
  "slackUserId": "U...",
  "email": "user@people.ai",
  "channelId": "DM channel ID",
  "assistantName": "Pikachu",
  "assistantEmoji": ":pikachu:",
  "assistantPersona": "short responses for busy professionals",
  "digestScope": "my_deals | team_deals | top_pipeline",
  "repName": "Scott Metcalf"
}
```

### Mode: Calibrate

Ported from `icp_calibration_v1.json` (28 nodes). Core flow:

1. **Get Auth Token** — Backstory OAuth client credentials
2. **Fetch Winners** (parallel) — Insights API export: `closed_won_opportunities_last_fyear > 0`, top 30
3. **Fetch Losers** (parallel) — Insights API export: `closed_lost_opportunities_last_fyear > 0 AND closed_won == 0`, top 30
4. **Parse CSVs** — Extract metrics from pipe-delimited response
5. **Compute Derived Ratios** — For each account:
   - Meeting Quality Ratio: `meetings_30d / (meetings_30d + emails_30d)`
   - Executive Coverage Ratio: `execs_engaged_30d / people_contacted_30d`
   - Email Responsiveness: `emails_received_30d / emails_sent_30d`
   - Contact Velocity: `(people_7d / people_30d) * 4.286`
   - Stakeholder Breadth: `people_contacted_30d / 4.3`
6. **Select Top 15 Winners** — Stratified by revenue tier (5 top, 5 mid, 5 bottom)
7. **Loop Deep Dives** — For each of 15 winners, Claude + Backstory MCP extracts:
   - Meeting cadence, meeting ratio, exec ratio
   - Committee formation, engagement arc
   - Executive entry timing
8. **Merge All Data** — Winners (30) + Losers (30) + Deep Dives (15)
9. **Generate Fingerprint** — Claude Sonnet analyzes merged data, outputs Slack mrkdwn
10. **Post to DM** — `chat.postMessage` with personalized assistant identity

### Mode: Targets

1. **Get Auth Token** — Backstory OAuth
2. **Fetch Accounts** — Insights API with ownership filter based on `digestScope`:
   - `my_deals` (AE): `ootb_account_original_owner = user email`
   - `team_deals` (Manager): `ootb_account_original_owner IN (user email + direct reports)`
   - `top_pipeline` (Exec): no owner filter
3. **Filter Low Engagement** — Code node filters to accounts with low activity but ICP-matching firmographics
4. **Targets Agent** — Claude + Backstory MCP scores and ranks target accounts
5. **Post to DM** — Compact ranked list with ICP scores

For Manager scope: the user hierarchy (manager → reports) is fetched via Query API user object export, same pattern as the Sales Digest workflow.

### Mode: Compare

1. **Compare Agent** — Claude + Backstory MCP with system prompt containing ICP benchmarks. Agent calls:
   - `find_account(companyName)` — locate the account
   - `get_account_status(account_id)` — engagement metrics
   - `get_engaged_people(account_id)` — stakeholder details
   - `get_recent_account_activity(account_id)` — 90-day timeline
2. **Post to DM** — Single-account fit report with dimension scores and recommendations

Compare mode works independently — ICP benchmarks are embedded in the system prompt (derived from the calibration methodology). No need to run `icp` first.

## Output Formats

### Calibrate

Slack mrkdwn posted as Block Kit sections:

```
:dart: WIN PATTERN FINGERPRINT
Calibrated: 2026-04-01
Based on: 30 winners vs 30 losers (last 12 months)
Deep dive: 15 winner activity timelines analyzed

:bar_chart: BEHAVIORAL BENCHMARKS
| Dimension | Winner Median | Loser Median | Gap | Signal |
|-----------|--------------|-------------|-----|--------|
| Meeting Quality | 42% | 14% | +28% | Strong |
| Executive Coverage | 24% | 8% | +16% | Strong |
| Email Responsiveness | 0.52 | 0.18 | +0.34 | Strong |
| Contact Velocity | 1.3 | 0.7 | +0.6 | Moderate |
| Stakeholder Breadth | 3.1/wk | 1.4/wk | +1.7 | Moderate |

:trophy: TOP DIFFERENTIATORS (ranked)
1. Meeting depth — winners 42% vs losers 14%
2. Executive involvement — 3x higher ratio
3. Bi-directional email — 0.52 vs 0.18

:scales: RECOMMENDED ICP SCORING WEIGHTS
- Meeting Quality: 30%
- Executive Coverage: 25%
- Email Responsiveness: 20%
- Contact Velocity: 15%
- Stakeholder Breadth: 10%

:chart_with_upwards_trend: WINNER ENGAGEMENT ARC
- Weeks 1-2: 1-2 meetings, exploratory
- Weeks 3-4: Executive enters, cadence increases
- Weeks 5-8: Committee forms, 2-3 new stakeholders
- Weeks 8-12: Peak meetings, multi-department

:no_entry_sign: ANTI-PATTERNS
1. Email-heavy (>85% email, <15% meetings)
2. Single-threaded (no new contacts after 30d)
3. Executive ghosting (exec attends then vanishes)

:dart: SCORING THRESHOLDS
- STRONG FIT (>0.70): Meeting ratio >35%, exec coverage >20%, responsive
- MODERATE FIT (0.40-0.70): Meeting ratio 20-35%, some exec access
- WEAK FIT (<0.40): Email-heavy, single-threaded, no exec access
```

### Targets

```
:dart: ICP Target Accounts
5 accounts match your winning pattern but have low engagement:

:large_green_circle: *TechCorp Inc* — ICP Score: 0.82 (Strong Fit)
   Industry match, right revenue band, no recent activity
:large_green_circle: *Acme Global* — ICP Score: 0.71 (Strong Fit)
   Executive contacts exist but no meetings in 90 days
:large_yellow_circle: *DataFlow Ltd* — ICP Score: 0.55 (Moderate Fit)
   Good firmographics, needs executive engagement
```

### Compare

```
:dart: ICP Fit Report — Flexera

Overall Score: 0.48 (Moderate Fit)

:white_check_mark: Meeting Quality: 0.38 (near benchmark 0.42)
:warning: Executive Coverage: 0.12 (below benchmark 0.24)
:white_check_mark: Email Responsiveness: 0.55 (above benchmark 0.52)
:red_circle: Contact Velocity: 0.4 (below benchmark 1.3)
:warning: Stakeholder Breadth: 0.9 (below benchmark 3.1)

:bulb: Recommendation: Expand executive engagement — only 1 of 8 contacts
is a decision-maker. Schedule an exec-level meeting to improve fit.
```

## Credentials

All existing credentials in the oppassistant n8n instance:

| Credential | ID | Usage |
|-----------|-----|-------|
| Anthropic | `rlAz7ZSl4y6AwRUq` | Claude Sonnet for analysis agents |
| Backstory MCP | `wvV5pwBeIL7f2vLG` | MCP tools (deep dives, compare) |
| Slack Auth | `LluVuiMJ8NUbAiG7` | chat.postMessage for results |
| Supabase | `ASRWWkQ0RSMOpNF1` | User lookup (identity, digestScope) |

Backstory OAuth client credentials for Query API (same as Silence Contract Monitor):
- `client_id`: hardcoded in Get Auth Token node
- `client_secret`: hardcoded in Get Auth Token node
- Token endpoint: `https://api.people.ai/v3/auth/tokens`

## No New Database Tables

Calibration runs on demand — no persistent storage. The fingerprint is generated fresh each time. Compare mode uses benchmarks embedded in the prompt (not stored from a prior calibrate run).

## Delivery

All three modes deliver results to the **user's DM** via `chat.postMessage` with personalized `username` (assistantName) and `icon_emoji` (assistantEmoji). No email, no channel posts.

## Not In Scope

- Persisting the fingerprint to Supabase for cross-mode reference
- Scheduling calibration runs (cron)
- Sharing fingerprints with team members
- Email delivery of results
