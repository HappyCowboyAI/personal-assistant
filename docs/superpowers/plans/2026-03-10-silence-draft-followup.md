# Silence Alert — Draft Follow-up Email Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Draft Follow-up" option to silence alert overflow menus that uses a Claude agent with People.ai MCP to draft a re-engagement email with recommended contacts.

**Architecture:** Single Python script (`scripts/add_silence_draft_followup.py`) modifies three live n8n workflows via the API. Overflow menus get a 4th option ("Draft Follow-up"). The Interactive Events Handler gets a new routing branch that posts a "Drafting..." thread reply, runs a re-engagement agent, and replaces it with the draft via `chat.update`.

**Tech Stack:** Python 3, n8n REST API, Slack Block Kit, Claude Sonnet 4.5 via LangChain agent, People.ai MCP

**Spec:** `docs/superpowers/specs/2026-03-10-silence-draft-followup-design.md`

---

## File Structure

| File | Action | Purpose |
|------|--------|---------|
| `scripts/add_silence_draft_followup.py` | Create | Main script — modifies 3 workflows |
| `scripts/n8n_helpers.py` | Read only | Shared helpers (node factories, API functions) |
| `n8n/workflows/Silence Contract Monitor.json` | Auto-synced | Updated by script after push |
| `n8n/workflows/On-Demand Silence Check.json` | Auto-synced | Updated by script after push |
| `n8n/workflows/Interactive Events Handler.json` | Auto-synced | Updated by script after push |

---

## Chunk 1: Overflow Menu Updates + Script Skeleton

### Task 1: Create script skeleton with imports and constants

**Files:**
- Create: `scripts/add_silence_draft_followup.py`

- [ ] **Step 1: Create the script file with imports and JS constants**

```python
#!/usr/bin/env python3
"""
Add "Draft Follow-up" option to silence alert overflow menus.

Changes three workflows:
1. Silence Contract Monitor (cron) — adds "Draft Follow-up" as first overflow option
2. On-Demand Silence Check — same overflow menu update
3. Interactive Events Handler — adds routing + agent flow for drafting re-engagement emails

Design spec: docs/superpowers/specs/2026-03-10-silence-draft-followup-design.md
"""

from n8n_helpers import (
    find_node, fetch_workflow, push_workflow, sync_local,
    uid, make_code_node, make_slack_http_node, make_agent_trio,
    WF_SILENCE_MONITOR, WF_INTERACTIVE_HANDLER,
    SLACK_CHAT_POST, SLACK_CHAT_UPDATE,
    NODE_IF,
)

# Workflow IDs
WF_ON_DEMAND = "7QaWpTuTp6oNVFjM"

# ── JS: Route Silence Action ──────────────────────────────────────────
# Inserted BEFORE Parse Mute Action. Routes 'fd' to draft flow, others to mute flow.
ROUTE_SILENCE_ACTION_CODE = r"""const payload = $('Parse Interactive Payload').first().json;
const selectedValue = payload.selectedOptionValue || '';

const pipeIdx = selectedValue.indexOf('|');
if (pipeIdx === -1) {
  return [{ json: { error: 'Invalid selection value', selectedValue } }];
}

const actionCode = selectedValue.substring(0, pipeIdx);
const accountName = selectedValue.substring(pipeIdx + 1);

const userRecord = $('Lookup User (Action)').first().json;

return [{
  json: {
    actionCode,
    accountName,
    channelId: payload.channelId,
    messageTs: payload.messageTs,
    assistantName: userRecord.assistant_name || userRecord.org_default_assistant_name || 'Aria',
    assistantEmoji: userRecord.assistant_emoji || userRecord.org_default_assistant_emoji || ':sparkles:',
    repName: userRecord.full_name || 'there',
    userId: userRecord.id || '',
    organizationId: userRecord.organization_id || '',
    isDraftFollowup: actionCode === 'fd',
    selectedOptionValue: selectedValue,
    // Pass through for mute path
    messageBlocks: payload.messageBlocks || [],
  }
}];"""

# ── JS: Build Re-engagement Prompt ────────────────────────────────────
BUILD_REENGAGEMENT_PROMPT_CODE = r"""// Use cross-node ref — $input is the Slack API response from Post Drafting Message
const data = $('Route Silence Action').first().json;
const accountName = data.accountName;
const repName = data.repName;
const assistantName = data.assistantName;

const systemPrompt = `You are ${assistantName}, a personal sales assistant for ${repName}.

You have access to People.ai MCP tools for CRM data, account activity, meeting details, and engagement data.

**RE-ENGAGEMENT EMAIL DRAFT MODE**

The account *${accountName}* has gone silent — there has been no recent engagement. Your job is to draft a compelling re-engagement email.

**STEP 1: RESEARCH** (use People.ai MCP tools)
1. Look up the account — current deal status, stage, open opportunities
2. Find engaged contacts — roles, titles, last activity dates. Prioritize:
   - Contacts ${repName} has had direct interaction with
   - Decision-makers relevant to open opportunities
3. Check recent activity history — what was the last engagement, when, and with whom?
4. Look for company news or context that could inform the outreach

**STEP 2: IDENTIFY RECIPIENTS**
- Pick the best primary recipient (To:) — the person most likely to respond
- Optionally suggest a CC if there's a relevant secondary contact
- For each, note their title and how long since last contact

**STEP 3: DRAFT THE EMAIL**

**FORMAT** (Slack mrkdwn):

:email: *Re-engagement Draft — ${accountName}*

*To:* Contact Name (Title) — last contact X days ago
*CC:* Contact Name (Title) — last contact X days ago
*Subject:* concise subject line

---
email body (150-250 words)
---

_Reply in this thread to adjust the tone, recipients, or ask me to revise._

**RULES:**
- 150-250 words in the email body
- Do NOT write a generic "just checking in" email — reference specific context you found
- Include a clear next step or call to action
- Use contact names, not generic "team"
- If there are open opportunities, weave that context in naturally
- Tone: professional but warm — adapt based on relationship depth and deal stage
- Do NOT use ### headers or markdown headers
- Keep total output under 3000 characters
- If you cannot find any engaged contacts, say so clearly and suggest the rep check Salesforce for the account team`;

const agentPrompt = `Draft a re-engagement email for the silent account: ${accountName}. Research the account and contacts first using your People.ai tools.`;

return [{
  json: {
    ...data,
    systemPrompt,
    agentPrompt,
  }
}];"""


def main():
    print("=== Silence Alert — Draft Follow-up ===\n")
    # TODO: implement workflow modifications
    print("Done!")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify script runs without errors**

Run: `cd /Users/scottmetcalf/projects/oppassistant && python3 -c "import scripts.add_silence_draft_followup"`
Expected: No import errors (just needs `N8N_API_KEY` set to avoid runtime error from n8n_helpers)

---

### Task 2: Update overflow menus in Silence Contract Monitor (cron)

**Files:**
- Modify: `scripts/add_silence_draft_followup.py`

The cron workflow's `Build Alert Message` node has JS code that builds overflow options. We need to add "Draft Follow-up" as the first option.

- [ ] **Step 1: Add the cron overflow menu update function**

Add to the script after the constants, before `main()`:

```python
def update_cron_overflow():
    """Add 'Draft Follow-up' as first overflow option in Silence Contract Monitor."""
    print("=== Updating Silence Contract Monitor (cron) ===\n")
    wf = fetch_workflow(WF_SILENCE_MONITOR)
    nodes = wf["nodes"]

    alert_node = find_node(nodes, "Build Alert Message")
    code = alert_node["parameters"]["jsCode"]

    # Check if already has Draft Follow-up
    if "Draft Follow-up" in code:
        print("  'Draft Follow-up' already in overflow menu")
        return None

    # Find the options array in the overflow menu and prepend Draft Follow-up
    old_options = """options: [
        {
          text: { type: "plain_text", text: "Snooze 7d" },
          value: ("s7|" + acctName).slice(0, 75)
        },"""

    new_options = """options: [
        {
          text: { type: "plain_text", text: "Draft Follow-up" },
          value: ("fd|" + acctName).slice(0, 75)
        },
        {
          text: { type: "plain_text", text: "Snooze 7d" },
          value: ("s7|" + acctName).slice(0, 75)
        },"""

    if old_options not in code:
        print("  ERROR: Could not find overflow options pattern in Build Alert Message")
        print("  Trying to find the options array...")
        # Fallback: look for the compact format
        old_compact = '{ text: { type: "plain_text", text: "Snooze 7d" }, value: ("s7|" + acctName).slice(0, 75) },'
        new_compact = '{ text: { type: "plain_text", text: "Draft Follow-up" }, value: ("fd|" + acctName).slice(0, 75) },\n        { text: { type: "plain_text", text: "Snooze 7d" }, value: ("s7|" + acctName).slice(0, 75) },'
        if old_compact in code:
            code = code.replace(old_compact, new_compact, 1)
            print("  Added 'Draft Follow-up' (compact format)")
        else:
            print("  ERROR: Could not find any options pattern — update manually")
            return None
    else:
        code = code.replace(old_options, new_options, 1)
        print("  Added 'Draft Follow-up' as first overflow option")

    alert_node["parameters"]["jsCode"] = code
    return wf
```

- [ ] **Step 2: Wire up in main()**

```python
def main():
    print("=== Silence Alert — Draft Follow-up ===\n")

    # 1. Silence Contract Monitor — add overflow option
    wf1 = update_cron_overflow()
    if wf1:
        result1 = push_workflow(WF_SILENCE_MONITOR, wf1)
        print(f"  Pushed cron: {len(result1['nodes'])} nodes")
        sync_local(fetch_workflow(WF_SILENCE_MONITOR), "Silence Contract Monitor.json")

    print("\nDone!")


if __name__ == "__main__":
    main()
```

---

### Task 3: Update overflow menus in On-Demand Silence Check

**Files:**
- Modify: `scripts/add_silence_draft_followup.py`

Same pattern as cron — the on-demand `Build Alert Message` node also has an overflow menu.

- [ ] **Step 1: Add the on-demand overflow menu update function**

```python
def update_od_overflow():
    """Add 'Draft Follow-up' as first overflow option in On-Demand Silence Check."""
    print("\n=== Updating On-Demand Silence Check ===\n")
    wf = fetch_workflow(WF_ON_DEMAND)
    nodes = wf["nodes"]

    alert_node = find_node(nodes, "Build Alert Message")
    code = alert_node["parameters"]["jsCode"]

    if "Draft Follow-up" in code:
        print("  'Draft Follow-up' already in overflow menu")
        return None

    # The on-demand version uses compact single-line format
    old_compact = '{ text: { type: "plain_text", text: "Snooze 7d" }, value: ("s7|" + acctName).slice(0, 75) },'
    new_compact = '{ text: { type: "plain_text", text: "Draft Follow-up" }, value: ("fd|" + acctName).slice(0, 75) },\n        { text: { type: "plain_text", text: "Snooze 7d" }, value: ("s7|" + acctName).slice(0, 75) },'

    if old_compact in code:
        code = code.replace(old_compact, new_compact, 1)
        print("  Added 'Draft Follow-up' as first overflow option")
    else:
        print("  ERROR: Could not find overflow options pattern — update manually")
        return None

    alert_node["parameters"]["jsCode"] = code
    return wf
```

- [ ] **Step 2: Add to main()**

```python
    # 2. On-Demand Silence Check — add overflow option
    wf2 = update_od_overflow()
    if wf2:
        result2 = push_workflow(WF_ON_DEMAND, wf2)
        print(f"  Pushed on-demand: {len(result2['nodes'])} nodes")
        sync_local(fetch_workflow(WF_ON_DEMAND), "On-Demand Silence Check.json")
```

---

## Chunk 2: Interactive Events Handler — Routing + Draft Flow

### Task 4: Insert Route Silence Action node and rewire

**Files:**
- Modify: `scripts/add_silence_draft_followup.py`

Currently: `Route Action (output 8) → Parse Mute Action → Upsert Mute → Update Alert Message`

After: `Route Action (output 8) → Route Silence Action → [if fd] → draft flow` / `→ [else] → Parse Mute Action → Upsert Mute → Update Alert Message`

The Route Silence Action code node parses the action code and outputs `isDraftFollowup`. An IF node routes `fd` to the draft path, everything else to the existing mute path.

- [ ] **Step 1: Add the Interactive Events Handler update function**

```python
def update_interactive_handler():
    """Add draft follow-up routing + agent flow to Interactive Events Handler."""
    print("\n=== Updating Interactive Events Handler ===\n")
    wf = fetch_workflow(WF_INTERACTIVE_HANDLER)
    nodes = wf["nodes"]
    connections = wf["connections"]
    changes = 0

    # ── 1. Insert Route Silence Action code node ──
    route_silence_name = "Route Silence Action"
    if not find_node(nodes, route_silence_name):
        # Position between Route Action and Parse Mute Action
        parse_mute = find_node(nodes, "Parse Mute Action")
        pm_pos = parse_mute["position"]

        route_silence = make_code_node(
            route_silence_name,
            ROUTE_SILENCE_ACTION_CODE,
            [pm_pos[0], pm_pos[1] - 200],  # Above Parse Mute Action
        )
        nodes.append(route_silence)
        changes += 1
        print(f"  Added '{route_silence_name}'")

        # Rewire: Route Action (Silence Mute output) → Route Silence Action
        # Find which output index connects to Parse Mute Action
        route_action_conns = connections.get("Route Action", {}).get("main", [])
        for i, output in enumerate(route_action_conns):
            for conn in output:
                if conn.get("node") == "Parse Mute Action":
                    route_action_conns[i] = [{"node": route_silence_name, "type": "main", "index": 0}]
                    print(f"  Rewired Route Action output {i} → {route_silence_name}")
                    break

    else:
        print(f"  '{route_silence_name}' already exists")

    # ── 2. Insert Is Draft Followup? IF node ──
    if_draft_name = "Is Draft Followup?"
    if not find_node(nodes, if_draft_name):
        rs_node = find_node(nodes, route_silence_name)
        rs_pos = rs_node["position"]

        if_draft = {
            "parameters": {
                "conditions": {
                    "options": {"version": 2, "caseSensitive": True, "typeValidation": "strict"},
                    "combinator": "and",
                    "conditions": [{
                        "id": uid(),
                        "operator": {"name": "filter.operator.equals", "type": "boolean", "operation": "equals"},
                        "leftValue": "={{ $json.isDraftFollowup }}",
                        "rightValue": True,
                    }],
                },
            },
            "id": uid(),
            "name": if_draft_name,
            "type": NODE_IF,
            "typeVersion": 2.2,
            "position": [rs_pos[0] + 250, rs_pos[1]],
        }
        nodes.append(if_draft)
        changes += 1
        print(f"  Added '{if_draft_name}'")

        # Wire: Route Silence Action → Is Draft Followup?
        connections[route_silence_name] = {"main": [[
            {"node": if_draft_name, "type": "main", "index": 0}
        ]]}

        # Wire: Is Draft Followup? false (output 1) → Parse Mute Action
        # Wire: Is Draft Followup? true (output 0) → Post Drafting Message (added next)
        # For now, wire false → Parse Mute Action
        connections[if_draft_name] = {"main": [
            [],  # output 0 (true) — will be wired to Post Drafting Message
            [{"node": "Parse Mute Action", "type": "main", "index": 0}],  # output 1 (false)
        ]}
        print("  Wired: Route Silence Action → IF → [false] Parse Mute Action")

    else:
        print(f"  '{if_draft_name}' already exists")

    # ── 3. Update Parse Mute Action to use Route Silence Action's output ──
    parse_mute = find_node(nodes, "Parse Mute Action")
    old_code = parse_mute["parameters"]["jsCode"]
    if "Route Silence Action" not in old_code:
        # Replace selectedOptionValue source — now comes from Route Silence Action
        new_code = old_code.replace(
            "const selectedValue = payload.selectedOptionValue || '';",
            "const routeData = $('Route Silence Action').first().json;\n"
            "const selectedValue = routeData.selectedOptionValue || '';",
        )
        # Also update messageBlocks source
        new_code = new_code.replace(
            "const messageBlocks = payload.messageBlocks || [];",
            "const messageBlocks = routeData.messageBlocks || [];",
        )
        parse_mute["parameters"]["jsCode"] = new_code
        changes += 1
        print("  Updated Parse Mute Action to reference Route Silence Action")
    else:
        print("  Parse Mute Action already references Route Silence Action")

    return wf, changes
```

- [ ] **Step 2: Verify the IF node output convention**

n8n IF node v2.2 outputs:
- Output 0 = true (condition matched)
- Output 1 = false (condition not matched)

This matches our wiring: true → draft flow, false → mute flow.

---

### Task 5: Add Post Drafting Message + Build Re-engagement Prompt + Agent + Post Draft

**Files:**
- Modify: `scripts/add_silence_draft_followup.py`

These nodes form the draft follow-up chain on the IF true path.

- [ ] **Step 1: Add the draft flow nodes to `update_interactive_handler`**

Continue inside `update_interactive_handler()` after the IF node section:

```python
    # ── 4. Add Post Drafting Message (Thinking... in thread) ──
    post_drafting_name = "Post Drafting Message"
    if not find_node(nodes, post_drafting_name):
        if_node = find_node(nodes, if_draft_name)
        if_pos = if_node["position"]

        drafting_body = (
            '={{ JSON.stringify({ '
            'channel: $json.channelId, '
            'thread_ts: $json.messageTs, '
            'text: "Drafting a follow-up for *" + $json.accountName + "*... give me a moment.", '
            'username: $json.assistantName, '
            'icon_emoji: $json.assistantEmoji '
            '}) }}'
        )
        post_drafting = make_slack_http_node(
            post_drafting_name,
            SLACK_CHAT_POST,
            drafting_body,
            [if_pos[0] + 300, if_pos[1] - 200],
        )
        nodes.append(post_drafting)
        changes += 1
        print(f"  Added '{post_drafting_name}'")

        # Wire IF true → Post Drafting Message
        connections[if_draft_name]["main"][0] = [
            {"node": post_drafting_name, "type": "main", "index": 0}
        ]
    else:
        print(f"  '{post_drafting_name}' already exists")

    # ── 5. Add Build Re-engagement Prompt ──
    build_prompt_name = "Build Re-engagement Prompt"
    if not find_node(nodes, build_prompt_name):
        pd_node = find_node(nodes, post_drafting_name)
        pd_pos = pd_node["position"]

        build_prompt = make_code_node(
            build_prompt_name,
            BUILD_REENGAGEMENT_PROMPT_CODE,
            [pd_pos[0] + 300, pd_pos[1]],
        )
        nodes.append(build_prompt)
        changes += 1
        print(f"  Added '{build_prompt_name}'")

        # Wire: Post Drafting Message → Build Re-engagement Prompt
        connections[post_drafting_name] = {"main": [[
            {"node": build_prompt_name, "type": "main", "index": 0}
        ]]}
    else:
        print(f"  '{build_prompt_name}' already exists")

    # ── 6. Add Re-engagement Draft Agent trio ──
    agent_name = "Re-engagement Draft Agent"
    if not find_node(nodes, agent_name):
        bp_node = find_node(nodes, build_prompt_name)
        bp_pos = bp_node["position"]

        agent_nodes = make_agent_trio(
            agent_name=agent_name,
            suffix="Re-engage",
            system_prompt_expr="={{ $json.systemPrompt }}",
            user_prompt_expr="={{ $json.agentPrompt }}",
            position=[bp_pos[0] + 300, bp_pos[1]],
            connections=connections,
        )
        nodes.extend(agent_nodes)
        changes += 1
        print(f"  Added agent trio: {agent_name}")

        # Wire: Build Re-engagement Prompt → Re-engagement Draft Agent
        connections[build_prompt_name] = {"main": [[
            {"node": agent_name, "type": "main", "index": 0}
        ]]}
    else:
        print(f"  '{agent_name}' already exists")

    # ── 7. Add Post Draft to Thread (chat.update) ──
    post_draft_name = "Post Draft to Thread"
    if not find_node(nodes, post_draft_name):
        agent_node = find_node(nodes, agent_name)
        agent_pos = agent_node["position"]

        # Use chat.update to replace "Drafting..." with the draft
        # $json.output comes from the agent; channel/ts from upstream nodes
        draft_body = (
            '={{ JSON.stringify({ '
            'channel: $("Route Silence Action").first().json.channelId, '
            'ts: $("Post Drafting Message").first().json.ts, '
            'text: $json.output || "I couldn\'t draft a follow-up for *" + '
            '$("Route Silence Action").first().json.accountName + '
            '"*. Try asking me directly: `/bs who should I reach out to at " + '
            '$("Route Silence Action").first().json.accountName + "?`", '
            'username: $("Route Silence Action").first().json.assistantName, '
            'icon_emoji: $("Route Silence Action").first().json.assistantEmoji '
            '}) }}'
        )
        post_draft = make_slack_http_node(
            post_draft_name,
            SLACK_CHAT_UPDATE,
            draft_body,
            [agent_pos[0] + 300, agent_pos[1]],
        )
        nodes.append(post_draft)
        changes += 1
        print(f"  Added '{post_draft_name}'")

        # Wire: Re-engagement Draft Agent → Post Draft to Thread
        connections[agent_name] = {"main": [[
            {"node": post_draft_name, "type": "main", "index": 0}
        ]]}
    else:
        print(f"  '{post_draft_name}' already exists")

    return wf, changes
```

- [ ] **Step 2: Note on `chat.update` ts field**

The `Post Drafting Message` node calls `chat.postMessage` which returns `{ ok: true, ts: "1234.5678", ... }`. The response body is available as `$json` in the next node but we reference it via `$("Post Drafting Message").first().json.ts` since Build Re-engagement Prompt sits between them. However, `chat.postMessage` returns the `ts` inside a nested structure. The actual path in n8n HTTP Request response is `$("Post Drafting Message").first().json.ts` — this works because n8n flattens the JSON response body.

**Important**: Slack's `chat.postMessage` returns `{ "ok": true, "channel": "...", "ts": "...", "message": {...} }`. The `ts` is at the top level of the response, so `$("Post Drafting Message").first().json.ts` is correct.

---

### Task 6: Wire up main() and test

**Files:**
- Modify: `scripts/add_silence_draft_followup.py`

- [ ] **Step 1: Complete main()**

```python
def main():
    print("=== Silence Alert — Draft Follow-up ===\n")

    # 1. Silence Contract Monitor — add overflow option
    wf1 = update_cron_overflow()
    if wf1:
        result1 = push_workflow(WF_SILENCE_MONITOR, wf1)
        print(f"  Pushed cron: {len(result1['nodes'])} nodes")
        sync_local(fetch_workflow(WF_SILENCE_MONITOR), "Silence Contract Monitor.json")

    # 2. On-Demand Silence Check — add overflow option
    wf2 = update_od_overflow()
    if wf2:
        result2 = push_workflow(WF_ON_DEMAND, wf2)
        print(f"  Pushed on-demand: {len(result2['nodes'])} nodes")
        sync_local(fetch_workflow(WF_ON_DEMAND), "On-Demand Silence Check.json")

    # 3. Interactive Events Handler — routing + agent flow
    wf3, changes3 = update_interactive_handler()
    if changes3 > 0:
        result3 = push_workflow(WF_INTERACTIVE_HANDLER, wf3)
        print(f"  Pushed interactive: {len(result3['nodes'])} nodes ({changes3} changes)")
        sync_local(fetch_workflow(WF_INTERACTIVE_HANDLER), "Interactive Events Handler.json")
    else:
        print("  No changes needed for Interactive Events Handler")

    print("\n=== Done! ===")
```

- [ ] **Step 2: Run the script**

Run: `N8N_API_KEY=<key> python3 scripts/add_silence_draft_followup.py`

Expected output:
```
=== Silence Alert — Draft Follow-up ===

=== Updating Silence Contract Monitor (cron) ===
  Added 'Draft Follow-up' as first overflow option
  Pushed cron: 22 nodes

=== Updating On-Demand Silence Check ===
  Added 'Draft Follow-up' as first overflow option
  Pushed on-demand: 13 nodes

=== Updating Interactive Events Handler ===
  Added 'Route Silence Action'
  Added 'Is Draft Followup?'
  Updated Parse Mute Action to reference Route Silence Action
  Added 'Post Drafting Message'
  Added 'Build Re-engagement Prompt'
  Added agent trio: Re-engagement Draft Agent
  Added 'Post Draft to Thread'
  Pushed interactive: 42 nodes (7 changes)

=== Done! ===
```

- [ ] **Step 3: Verify in n8n editor**

Open `https://scottai.trackslife.com` and check the Interactive Events Handler workflow:
1. Route Action output 8 (Silence Mute) → Route Silence Action → Is Draft Followup?
2. IF true → Post Drafting Message → Build Re-engagement Prompt → Re-engagement Draft Agent → Post Draft to Thread
3. IF false → Parse Mute Action → Upsert Mute → Update Alert Message

---

### Task 7: Manual testing

- [ ] **Step 1: Test "Draft Follow-up" from on-demand silence check**

DM the bot: `silence`
- Verify overflow menu shows 4 options with "Draft Follow-up" first
- Click "Draft Follow-up" on an account
- Verify: "Drafting a follow-up for *AccountName*..." appears as thread reply
- Verify: Message gets replaced with email draft including To/CC/Subject and email body

- [ ] **Step 2: Test mute actions still work**

From the same silence alert:
- Click "Snooze 7d" on a different account
- Verify: confirmation message replaces the account line (existing behavior preserved)

- [ ] **Step 3: Test "Mark as Lost" still works**

- Click "Mark as Lost" on another account
- Verify: confirmation with Salesforce suggestion appears
