# GitHub Pages Admin Deployment Guide — Design Spec

**Date:** 2026-04-16
**Status:** Approved
**Repo:** `HappyCowboyAI/personal-assistant`
**Live URL:** `https://happycowboyai.github.io/personal-assistant/`

---

## Summary

A customer-facing admin deployment guide for the People.ai Personal Assistant, published as a GitHub Pages site from the existing repository. Built with Docsify (client-side markdown renderer), styled to the Backstory brand guide, with multi-page sidebar navigation.

**Audience:** Admins and IT teams deploying the assistant for their organization.

---

## Framework & Deployment

- **Framework:** Docsify — zero build step, client-side markdown rendering
- **Hosting:** GitHub Pages deploying `docs/site/` via a minimal GitHub Actions workflow
- **Routing:** Hash-based SPA (`#/prerequisites`, `#/slack-setup`, etc.)
- **Plugins:** Search (built-in), copy-code button
- **Jekyll bypass:** `.nojekyll` file in `docs/site/`
- **GitHub Actions:** A ~10-line workflow that deploys only `docs/site/` to Pages on push to `main`. Required because GitHub Pages natively only serves from `/` or `/docs` — and the existing `docs/` folder contains internal documentation (specs, plans, GETTING_STARTED.md) that should not be part of the public site

---

## File Layout

All site files live in a new `docs/site/` subdirectory to avoid conflicts with existing `docs/` content (GETTING_STARTED.md, backstorybrandguide.md, plans/, specs/, etc.). GitHub Pages will be configured to serve from `docs/site/`.

```
docs/site/
├── index.html              # Docsify loader
├── _sidebar.md             # Sidebar navigation
├── _coverpage.md           # Landing cover page
├── README.md               # Overview / home page
├── .nojekyll               # Skip Jekyll processing
├── css/
│   └── backstory.css       # Backstory brand theme overrides
├── assets/
│   ├── wordmark-dark.png   # Backstory logo (white version for dark sidebar)
│   ├── books-icon-white.png
│   └── gradient-stripe.png
├── prerequisites.md
├── slack-setup.md
├── database-setup.md
├── n8n-setup.md
├── onboarding-config.md
├── workflow-reference.md
└── troubleshooting.md
```

### Sidebar Navigation (`_sidebar.md`)

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

---

## Visual Design — Backstory Theme

Custom CSS overrides Docsify's default theme to match the Backstory brand guide (v2.0).

### Color Mapping

| Role | Token | Value |
|------|-------|-------|
| Sidebar background | Graphite | `#171721` |
| Sidebar text | White | `#FFFFFF` |
| Sidebar active link | Horizon | `#6296AD` |
| Page background | White | `#FFFFFF` |
| Body text | Graphite | `#171721` |
| Headings | Black | `#000000` |
| Links & accent | Horizon | `#6296AD` |
| Code block background | Surface Gray tint | `#F5F5F6` |
| Inline code | Cinder | `#C05527` |
| Tip/callout boxes | Horizon tint | `rgba(98, 150, 173, 0.1)` |
| Warning callouts | Cinder tint | `rgba(192, 85, 39, 0.1)` |

### Typography

LL Kleisch and KMR Waldenburg are custom fonts unlikely to be available for web embedding. Fallback strategy:

- **Headings:** `Georgia, 'Times New Roman', serif` — approximates LL Kleisch's editorial serif feel
- **Body/UI:** `-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif` — approximates KMR Waldenburg's clean sans-serif
- **Code/data:** `'Chivo Mono', 'Fira Mono', 'Courier New', monospace`

If web font files (.woff2) for the brand fonts become available, they can be added via `@font-face` declarations in `backstory.css`.

### Sidebar Design

- Dark Graphite (`#171721`) background with white text
- Backstory wordmark (white version) displayed at top of sidebar
- Active page: Horizon (`#6296AD`) left border + Horizon text color
- Hover state: subtle Horizon tint background

### General Principles

Per the brand guide: color used sparingly as accent, not decoration. High contrast. Restrained. Professional.

---

## Security — Credential Scrubbing

All content uses placeholder values. No real credentials, IDs, tokens, or URLs from the live environment.

| Sensitive Item | Placeholder |
|---|---|
| API keys | `your-api-key-here` |
| Database URLs | `postgresql://host:5432/dbname` |
| Slack bot tokens | `xoxb-your-bot-token` |
| People.ai client ID/secret | `your-client-id` / `your-client-secret` |
| Webhook URLs | `https://your-n8n-instance.com/webhook/...` |
| Slack user IDs | `U0EXAMPLE` |
| n8n credential IDs | `your-credential-id` |
| Email addresses | `admin@yourcompany.com` |
| Workato webhook URLs | `https://webhooks.workato.com/webhooks/rest/your-recipe-id/...` |
| Supabase project URLs | `https://your-project.supabase.co` |

### Rules

- Guide pages are written fresh (adapted from existing docs), never copied verbatim from files containing real values
- SQL DDL from migration files is safe to include (no credentials in schema definitions)
- Workflow JSON snippets show structure only — credential blocks replaced with placeholders
- No content sourced from MEMORY.md or memory files
- The n8n `Get Auth Token` node body (contains real People.ai client_id/secret) must never appear
- `.gitignore` verified before publishing to ensure no `.env` or secrets files in `docs/site/`

---

## Content Plan

### 1. Overview (README.md)

**Source:** Adapted from `people-ai-personal-assistant.md`

- What the Personal Assistant is and what it does for sales reps
- Architecture overview: n8n (orchestration) → Claude (reasoning) → People.ai (intelligence) → Slack (delivery) → PostgreSQL (data)
- Text-based architecture diagram
- What admins are setting up and what the end result looks like
- Link to each setup section

### 2. Prerequisites (prerequisites.md)

**Source:** Adapted from `docs/GETTING_STARTED.md`

- Accounts and access needed:
  - Slack workspace with admin access
  - PostgreSQL-compatible database (Supabase, RDS, self-hosted, etc.)
  - n8n instance (cloud or self-hosted)
  - Anthropic API key
  - People.ai API credentials (client ID + secret for OAuth, MCP auth headers)
- Minimum permissions/roles for each service
- Network requirements (webhook endpoints must be publicly accessible)

### 3. Slack App Setup (slack-setup.md)

**Source:** Adapted from `slack/SETUP.md`

- Creating the Slack app in the Slack API console
- Required bot token scopes (especially `chat:write.customize` for personalized assistant names)
- Event subscriptions configuration and webhook URL
- Slash command registration (`/bs` for Backstory)
- Interactivity webhook URL
- Installing the app to the workspace

### 4. Database Setup (database-setup.md)

**Source:** Adapted from `supabase/migrations/001_initial_schema.sql`, `002_role_based_digest.sql`; genericized from Supabase-specific references

- Schema overview: tables and their purpose (organizations, users, messages, pending_actions, conversations, alert_history, feature_catalog, etc.)
- Full PostgreSQL DDL — generic CREATE TABLE statements, indexes, triggers, helper functions
- Multi-tenancy design: everything scoped to `organization_id`
- Row-Level Security policy guidance (concept + example policies, not Supabase-specific syntax)
- REST API layer notes: any PostgREST-compatible layer works (Supabase, Hasura, self-hosted PostgREST, or direct connection)
- Initial seed data (default organization, alert types, feature catalog entries)

### 5. n8n Setup (n8n-setup.md)

**Source:** Adapted from `docs/GETTING_STARTED.md`

- Importing workflow JSON files from the repo
- Credential configuration with placeholder examples:
  - Slack bot token (HTTP Header Auth)
  - Anthropic API key
  - People.ai MCP (Multi-Header Auth)
  - People.ai OAuth (client credentials for Query API)
  - Database connection (Supabase API or direct PostgreSQL)
- Activating workflows
- Verifying webhook endpoints are reachable
- Timezone configuration (workflows default to `America/Los_Angeles`)

### 6. Onboarding Configuration (onboarding-config.md)

**Source:** Adapted from `CLAUDE.md` design decisions + `prompts/onboarding_conversation.md`

- Setting organization defaults: assistant name, emoji, persona
- The resolution chain: user override → org default → hardcoded fallback
- Onboarding state machine: `new` → `awaiting_name` → `awaiting_emoji` → `complete`
- Digest scope options and how they map to roles:
  - `my_deals` (IC: AE, SDR, BDR)
  - `team_deals` (Manager, Director)
  - `top_pipeline` (VP, SVP, CRO)
- How digest scope is auto-detected from Slack profile title/division
- Customizable assistant persona (freeform text injected into prompts)

### 7. Workflow Reference (workflow-reference.md)

**Source:** Written fresh from CLAUDE.md workflow descriptions

A table of all production workflows with:

| Column | Description |
|--------|-------------|
| Name | Workflow name |
| Trigger | Cron schedule, webhook, or sub-workflow |
| Schedule | When it runs (e.g., "6am PT weekdays") |
| Purpose | One-line description |
| Key integrations | Which services it touches |

Workflows to document:
- Sales Digest (daily briefings)
- Backstory Slack Bot (`/bs` command)
- Slack Events Handler (onboarding + settings + commands)
- Interactive Events Handler (button actions, modals)
- Meeting Prep Cron + Meeting Brief (pre-meeting intelligence)
- Silence Contract Monitor + On-Demand Silence Check (deal silence alerts)
- Deal Watch Cron (opportunity stage transitions)
- Follow-up Cron (meeting recaps + task resolution)
- Weekly Profile Sync (Slack profile → database sync)
- On-Demand Digest (sub-workflow)
- Backstory Presentation (Google Slides generation)
- Task Resolution Handler (async SF task completion)

No credential IDs, webhook URLs, or internal implementation details — just what each workflow does and when.

### 8. Troubleshooting (troubleshooting.md)

**Source:** Adapted from `docs/GETTING_STARTED.md` troubleshooting + common patterns

- Common issues organized by integration point:
  - Slack: bot not posting, wrong assistant name, missing emoji
  - Database: migration errors, RLS blocking queries
  - n8n: workflow not triggering, credential errors, webhook timeouts
  - People.ai: auth failures, empty data exports, MCP connection issues
- Verification steps: how to test each integration independently
- FAQ: digest not arriving, onboarding stuck, how to re-trigger a digest

---

## Docsify Configuration

The `index.html` file configures Docsify with:

```javascript
window.$docsify = {
  name: 'Backstory Admin Guide',
  repo: false,
  loadSidebar: true,
  subMaxLevel: 2,
  search: 'auto',
  auto2top: true,
  coverpage: true,
  themeable: {
    readyTransition: true
  }
}
```

Plugins loaded:
- `docsify-search` — full-text search across all pages
- `docsify-copy-code` — copy button on code blocks (useful for SQL, config snippets)

---

## GitHub Actions Workflow

A minimal workflow at `.github/workflows/deploy-docs.yml`:

```yaml
name: Deploy Admin Guide
on:
  push:
    branches: [main]
    paths: ['docs/site/**']
permissions:
  pages: write
  id-token: write
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

Only triggers on changes to `docs/site/` — normal code pushes don't trigger a deploy.

---

## Cover Page

The `_coverpage.md` provides a branded landing page before the user enters the guide:

- Backstory logo (books icon)
- Title: "Personal Assistant — Admin Guide"
- Tagline: one-line description of the product
- "Get Started" button linking to the Overview page
- Backstory Graphite background with Horizon accent

---

## What's Out of Scope

- End-user guide for sales reps (separate effort)
- Buyer/marketing site (different audience, different content)
- Automated CI/CD pipeline (not needed — push to main deploys)
- Custom interactive components (animated walkthroughs, Slack mockups from the reference site — nice-to-have for a future iteration)
- Version-specific documentation (single current version for now)
