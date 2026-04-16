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
