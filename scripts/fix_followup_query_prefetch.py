"""
Fix: Add Query API pre-fetch for today's meetings in the DM followup path.

Currently the on-demand followup relies entirely on MCP to discover meetings.
MCP data lags 3-4 hours, so the agent misses today's meetings.

Fix: Insert 3 nodes (Auth → Build Query → Fetch) between "Is Conversational?"
and "Build DM System Prompt". The meeting data is injected into the followup
prompt so the agent knows exactly which meetings happened today.

For non-followup commands, the meeting data is fetched but ignored by
Build DM System Prompt.

Usage:
    N8N_API_KEY=... python scripts/fix_followup_query_prefetch.py
"""

from n8n_helpers import (
    uid, find_node, fetch_workflow, push_workflow, sync_local,
    WF_EVENTS_HANDLER,
)


def main():
    print(f"Fetching Events Handler {WF_EVENTS_HANDLER}...")
    wf = fetch_workflow(WF_EVENTS_HANDLER)
    nodes = wf["nodes"]
    connections = wf["connections"]
    print(f"  {len(nodes)} nodes")

    # ── Get position reference from Build DM System Prompt ──
    build_prompt = find_node(nodes, "Build DM System Prompt")
    if not build_prompt:
        print("  ERROR: Build DM System Prompt not found")
        return
    bp_pos = build_prompt["position"]

    # ── 1. Add "DM Followup Auth" node ──
    auth_node = {
        "parameters": {
            "method": "POST",
            "url": "https://api.people.ai/v3/auth/tokens",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Content-Type", "value": "application/x-www-form-urlencoded"}
                ]
            },
            "sendBody": True,
            "specifyBody": "string",
            "body": "client_id=YOUR_CLIENT_ID&client_secret=YOUR_CLIENT_SECRET&grant_type=client_credentials",
            "options": {},
        },
        "id": uid(),
        "name": "DM Followup Auth",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [bp_pos[0] - 660, bp_pos[1]],
        "continueOnFail": True,
    }
    nodes.append(auth_node)

    # ── 2. Add "DM Build Meeting Query" node ──
    query_code = r"""// Build query for today's meetings (last 24h to catch late ones)
const now = Date.now();
const twentyFourHoursAgo = now - 24 * 60 * 60 * 1000;

const query = {
  object: "activity",
  filter: {
    "$and": [
      { attribute: { slug: "ootb_activity_type" }, clause: { "$eq": "meeting" } },
      { attribute: { slug: "ootb_activity_external" }, clause: { "$eq": true } },
      { attribute: { slug: "ootb_activity_timestamp" }, clause: { "$gte": twentyFourHoursAgo } },
      { attribute: { slug: "ootb_activity_timestamp" }, clause: { "$lte": now } }
    ]
  },
  columns: [
    { slug: "ootb_activity_uid" },
    { slug: "ootb_activity_timestamp" },
    { slug: "ootb_activity_subject" },
    { slug: "ootb_activity_account_name" },
    { slug: "ootb_activity_participants", variation_id: "ootb_activity_participants_email" },
    { slug: "ootb_activity_participants", variation_id: "ootb_activity_participants_name" }
  ],
  sort: [{ attribute: { slug: "ootb_activity_timestamp" }, direction: "desc" }]
};

return [{ json: { ...($input.first().json), meetingQuery: JSON.stringify(query) } }];
"""

    query_node = {
        "parameters": {"jsCode": query_code},
        "id": uid(),
        "name": "DM Build Meeting Query",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [bp_pos[0] - 440, bp_pos[1]],
    }
    nodes.append(query_node)

    # ── 3. Add "DM Fetch Today Meetings" node ──
    fetch_node = {
        "parameters": {
            "method": "POST",
            "url": "https://api.people.ai/v3/beta/insights/export",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Content-Type", "value": "application/json"},
                    {"name": "Authorization", "value": "=Bearer {{ $('DM Followup Auth').first().json.access_token }}"},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ $json.meetingQuery }}",
            "options": {"response": {"response": {"responseFormat": "text"}}},
        },
        "id": uid(),
        "name": "DM Fetch Today Meetings",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [bp_pos[0] - 220, bp_pos[1]],
        "continueOnFail": True,
    }
    nodes.append(fetch_node)

    # ── 4. Rewire connections ──
    # Old: Is Conversational? [true] → Build DM System Prompt
    # New: Is Conversational? [true] → DM Followup Auth → DM Build Meeting Query
    #      → DM Fetch Today Meetings → Build DM System Prompt

    # Update Is Conversational? true output
    is_conv = connections.get("Is Conversational?", {})
    if is_conv:
        main_outputs = is_conv.get("main", [])
        if main_outputs and len(main_outputs) > 0:
            # Replace true output target
            main_outputs[0] = [{"node": "DM Followup Auth", "type": "main", "index": 0}]
            print("  Rewired: Is Conversational? → DM Followup Auth")

    connections["DM Followup Auth"] = {
        "main": [[{"node": "DM Build Meeting Query", "type": "main", "index": 0}]]
    }
    connections["DM Build Meeting Query"] = {
        "main": [[{"node": "DM Fetch Today Meetings", "type": "main", "index": 0}]]
    }
    connections["DM Fetch Today Meetings"] = {
        "main": [[{"node": "Build DM System Prompt", "type": "main", "index": 0}]]
    }

    print("  Added 3 nodes: DM Followup Auth → DM Build Meeting Query → DM Fetch Today Meetings")
    print("  Wired: → Build DM System Prompt")

    # ── 5. Update Build DM System Prompt to inject meeting context ──
    code = build_prompt["parameters"]["jsCode"]

    # Find the followup section and inject meeting context
    # After the "TODAY IS" line, add the meeting list from Query API
    old_today_line = "'## CRITICAL: DATA LATENCY PROTOCOL',"
    new_meeting_context = r"""'## TODAY\'S MEETINGS (from calendar/Query API — NOT dependent on transcript ingestion):',
    '',
    (() => {
      try {
        const csv = $('DM Fetch Today Meetings').first().json.data || '';
        if (!csv || csv.trim().length < 10) return '_No meeting data available from Query API._';
        const lines = csv.trim().split('\n');
        if (lines.length < 2) return '_No meetings found in the last 24 hours._';

        // Parse CSV
        const hdrs = [];
        let hField = '', hInQ = false;
        for (const ch of lines[0]) {
          if (ch === '"') { hInQ = !hInQ; continue; }
          if ((ch === ',' || ch === '\t') && !hInQ) { hdrs.push(hField.trim()); hField = ''; continue; }
          hField += ch;
        }
        hdrs.push(hField.trim());

        function parseRow(line) {
          const vals = []; let f = '', q = false;
          for (let i = 0; i < line.length; i++) {
            const c = line[i];
            if (c === '"') { q = !q; continue; }
            if (c === '[') { q = true; continue; }
            if (c === ']') { q = false; continue; }
            if (c === ',' && !q) { vals.push(f.trim()); f = ''; continue; }
            f += c;
          }
          vals.push(f.trim());
          return vals;
        }

        function getCol(row, name) {
          const idx = hdrs.findIndex(h => h.toLowerCase().includes(name.toLowerCase()));
          return idx >= 0 ? (row[idx] || '') : '';
        }

        const tz = 'America/Los_Angeles';
        const meetingLines = [];
        for (let i = 1; i < Math.min(lines.length, 20); i++) {
          if (!lines[i].trim()) continue;
          const row = parseRow(lines[i]);
          const subject = getCol(row, 'Subject') || '[no subject]';
          const account = getCol(row, 'Account') || '[unmatched]';
          const ts = getCol(row, 'date') || getCol(row, 'timestamp');
          const participants = getCol(row, 'Email') || '';
          let timeStr = '';
          try {
            const d = new Date(ts);
            timeStr = d.toLocaleTimeString('en-US', { timeZone: tz, hour: 'numeric', minute: '2-digit' });
          } catch(e) { timeStr = ts; }
          meetingLines.push('- ' + timeStr + ' | ' + account + ' | "' + subject + '" | Participants: ' + participants);
        }
        if (meetingLines.length === 0) return '_No external meetings found._';
        return meetingLines.join('\n');
      } catch(e) {
        return '_Could not fetch meeting data: ' + e.message + '_';
      }
    })(),
    '',
    'Use the meeting list above to identify which meeting the user is asking about.',
    'Even if MCP does not have transcript data yet, you KNOW these meetings happened.',
    'Draft based on the meeting title, account, and participants — add a note that details will improve once transcript data syncs.',
    '',
    '## CRITICAL: DATA LATENCY PROTOCOL',"""

    if old_today_line in code:
        code = code.replace(old_today_line, new_meeting_context)
        build_prompt["parameters"]["jsCode"] = code
        print("  Updated Build DM System Prompt: injected Query API meeting list into followup prompt")
    else:
        print("  WARNING: Could not find insertion point in Build DM System Prompt")
        print(f"  Looking for: {old_today_line}")

    # ── Push ──
    print(f"\n=== Pushing Events Handler ===")
    result = push_workflow(WF_EVENTS_HANDLER, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")
    sync_local(result, "Slack Events Handler.json")

    print("\nDone! On-demand followup now pre-fetches today's meetings via Query API.")
    print("  - DM Followup Auth → DM Build Meeting Query → DM Fetch Today Meetings")
    print("  - Meeting list injected into followup prompt as structured context")
    print("  - Agent can see today's meetings immediately (no 3-4h MCP lag)")
    print("  - MCP still used for enrichment (transcripts, topics, action items)")


if __name__ == "__main__":
    main()
