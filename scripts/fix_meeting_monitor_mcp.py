"""
Fix: Add MCP probe to Meeting Data Monitor.

After getting today's meetings from the Query API, for each unique account
with a completed meeting, uses an AI Agent + Backstory MCP to check if
SalesAI has transcript/enrichment data for that meeting.

New flow:
  Cron → Auth → Query → Fetch → Parse Meetings → Split Batches →
  [loop] → Has Ended? → Build Probe Prompt → Probe Agent → Parse Probe →
  [done] → Build Report → Open DM → Post Report

Usage:
    N8N_API_KEY=... python scripts/fix_meeting_monitor_mcp.py
"""

import json
from n8n_helpers import (
    uid, find_node, fetch_workflow, push_workflow, sync_local,
    ANTHROPIC_CRED, MCP_CRED, SLACK_CRED,
)

WF_ID = "qydIaf2GFaxJjHcI"
SCOTT_EMAIL = "scott.metcalf@people.ai"
SHREYAS_EMAIL = "shreyas.gore@people.ai"
SCOTT_SLACK_ID = "U061WJ6RMJS"


def main():
    print(f"Fetching Meeting Data Monitor {WF_ID}...")
    wf = fetch_workflow(WF_ID)
    nodes = wf["nodes"]
    connections = wf["connections"]
    print(f"  {len(nodes)} nodes")

    # ── Update Parse & Filter to output one item per meeting ──
    parse_node = find_node(nodes, "Parse & Filter Meetings")
    if not parse_node:
        print("  ERROR: 'Parse & Filter Meetings' not found")
        return

    parse_node["parameters"]["jsCode"] = """// Parse CSV and filter for Scott + Shreyas meetings
// Output one item per completed meeting for MCP probing
const csvText = $input.first().json.data || $input.first().json.body || '';
const WATCH_EMAILS = ['""" + SCOTT_EMAIL + """', '""" + SHREYAS_EMAIL + """'];

const lines = csvText.trim().split('\\n');
if (lines.length < 2) {
  return [{ json: { meetings: [], noMeetings: true } }];
}

// Parse CSV headers
const headers = [];
let inQuotes = false;
let current = '';
for (const ch of lines[0]) {
  if (ch === '"') { inQuotes = !inQuotes; continue; }
  if (ch === ',' && !inQuotes) { headers.push(current.trim()); current = ''; continue; }
  current += ch;
}
headers.push(current.trim());

function parseRow(line) {
  const vals = [];
  let inQ = false, cur = '';
  for (const ch of line) {
    if (ch === '"') { inQ = !inQ; continue; }
    if (ch === ',' && !inQ) { vals.push(cur.trim()); cur = ''; continue; }
    cur += ch;
  }
  vals.push(cur.trim());
  const obj = {};
  headers.forEach((h, i) => obj[h] = vals[i] || '');
  return obj;
}

const now = new Date();
const tz = 'America/Los_Angeles';
const results = [];

for (let i = 1; i < lines.length; i++) {
  if (!lines[i].trim()) continue;
  const row = parseRow(lines[i]);

  const emails = (row['Activity Participants (Email)'] || '').toLowerCase();
  const isOurs = WATCH_EMAILS.some(e => emails.includes(e));
  if (!isOurs) continue;

  const meetingTime = new Date(row['Activity date'] || '');
  const elapsed = (now - meetingTime) / 3600000;
  const hasEnded = elapsed > 0.25; // ended at least 15 min ago

  const subject = row['Subject'] || '[no subject]';
  const account = row['Account (name)'] || '';
  const meetingPT = meetingTime.toLocaleTimeString('en-US', { timeZone: tz, hour: 'numeric', minute: '2-digit' });

  // Who from our team
  const nameList = (row['Activity Participants (Name)'] || '').split(';').map(n => n.trim());
  const emailList = (row['Activity Participants (Email)'] || '').split(';').map(e => e.trim());
  const ourPeople = [];
  emailList.forEach((e, idx) => {
    if (WATCH_EMAILS.includes(e.toLowerCase())) {
      ourPeople.push(nameList[idx] || e);
    }
  });

  results.push({
    meetingId: row['Activity'] || '',
    time: meetingPT,
    elapsed: hasEnded ? elapsed.toFixed(1) + 'h ago' : 'upcoming',
    elapsedHours: elapsed,
    hasEnded,
    subject: subject.length > 60 ? subject.substring(0, 57) + '...' : subject,
    account: account || '[unmatched]',
    rep: ourPeople.join(', '),
    needsProbe: hasEnded && !!account,
  });
}

// Sort by time
results.sort((a, b) => a.elapsedHours - b.elapsedHours);

return results.map(m => ({ json: m }));
"""
    print("  Updated Parse & Filter to output per-meeting items")

    # ── Get position reference ──
    parse_pos = parse_node["position"]

    # ── Add SplitInBatches to process meetings one at a time ──
    split_node = {
        "parameters": {"batchSize": 1, "options": {}},
        "id": uid(),
        "name": "Split Meetings",
        "type": "n8n-nodes-base.splitInBatches",
        "typeVersion": 3,
        "position": [parse_pos[0] + 220, parse_pos[1]],
    }
    nodes.append(split_node)

    # ── If node: needs MCP probe? ──
    if_node = {
        "parameters": {
            "conditions": {
                "options": {"version": 2, "caseSensitive": True, "typeValidation": "strict"},
                "combinator": "and",
                "conditions": [{
                    "id": uid(),
                    "operator": {"name": "filter.operator.equals", "type": "boolean", "operation": "equals"},
                    "leftValue": "={{ $json.needsProbe }}",
                    "rightValue": True,
                }],
            },
        },
        "id": uid(),
        "name": "Needs Probe?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [parse_pos[0] + 440, parse_pos[1]],
    }
    nodes.append(if_node)

    # ── Build probe prompt ──
    probe_prompt = {
        "parameters": {
            "jsCode": """// Build a targeted probe question for SalesAI
const meeting = $input.first().json;
const account = meeting.account;
const subject = meeting.subject;
const time = meeting.time;

const prompt = `Check the most recent activity for the account "${account}". ` +
  `I had a meeting today at ${time} titled "${subject}". ` +
  `Tell me: does your data include specific discussion topics, action items, or meeting notes from this meeting? ` +
  `Reply with EXACTLY one of these formats:\\n` +
  `- ENRICHED: [brief summary of what discussion data you found]\\n` +
  `- NOT_ENRICHED: [what data you do have, e.g. "only calendar metadata"]\\n` +
  `Be concise. One line only.`;

const systemPrompt = 'You are a data availability checker. Use Backstory MCP tools to look up recent activity for the specified account. ' +
  'Check if the specific meeting has discussion content (topics, action items, notes) or just calendar metadata. ' +
  'Reply in the exact format requested. Be brief and factual.';

return [{ json: { ...meeting, probePrompt: prompt, probeSystem: systemPrompt } }];
"""
        },
        "id": uid(),
        "name": "Build Probe Prompt",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [parse_pos[0] + 660, parse_pos[1] - 80],
    }
    nodes.append(probe_prompt)

    # ── AI Agent for MCP probe ──
    probe_agent = {
        "parameters": {
            "promptType": "define",
            "text": "={{ $json.probePrompt }}",
            "options": {
                "systemMessage": "={{ $json.probeSystem }}",
                "maxIterations": 5,
            },
        },
        "id": uid(),
        "name": "Probe Agent",
        "type": "@n8n/n8n-nodes-langchain.agent",
        "typeVersion": 1.7,
        "position": [parse_pos[0] + 880, parse_pos[1] - 80],
    }
    nodes.append(probe_agent)

    # ── LLM for probe agent (use Haiku for cost efficiency) ──
    probe_llm = {
        "parameters": {
            "model": {
                "__rl": True,
                "value": "claude-haiku-4-5-20251001",
                "mode": "list",
                "cachedResultName": "Claude Haiku 4.5",
            },
            "options": {},
        },
        "id": uid(),
        "name": "Probe LLM",
        "type": "@n8n/n8n-nodes-langchain.lmChatAnthropic",
        "typeVersion": 1.3,
        "position": [parse_pos[0] + 780, parse_pos[1] + 120],
        "credentials": {"anthropicApi": ANTHROPIC_CRED},
    }
    nodes.append(probe_llm)

    # ── MCP tool for probe ──
    probe_mcp = {
        "parameters": {
            "endpointUrl": "https://mcp.people.ai/mcp",
            "authentication": "multipleHeadersAuth",
            "options": {},
        },
        "id": uid(),
        "name": "Probe MCP",
        "type": "@n8n/n8n-nodes-langchain.mcpClientTool",
        "typeVersion": 1.2,
        "position": [parse_pos[0] + 980, parse_pos[1] + 120],
        "credentials": {"httpMultipleHeadersAuth": MCP_CRED},
    }
    nodes.append(probe_mcp)

    # ── Parse probe result ──
    parse_probe = {
        "parameters": {
            "jsCode": """// Extract probe result and merge back with meeting data
const input = $input.first().json;
const agentOutput = input.output || input.text || '';

let probeStatus = 'UNKNOWN';
let probeDetail = '';

if (agentOutput.includes('ENRICHED:') && !agentOutput.includes('NOT_ENRICHED')) {
  probeStatus = 'ENRICHED';
  probeDetail = agentOutput.split('ENRICHED:')[1]?.trim() || '';
} else if (agentOutput.includes('NOT_ENRICHED')) {
  probeStatus = 'NOT_ENRICHED';
  probeDetail = agentOutput.split('NOT_ENRICHED:')[1]?.trim() || '';
} else {
  probeDetail = agentOutput.substring(0, 200);
}

// Get meeting data from upstream
const meeting = $('Build Probe Prompt').first().json;

return [{ json: {
  ...meeting,
  probeStatus,
  probeDetail: probeDetail.substring(0, 150),
} }];
"""
        },
        "id": uid(),
        "name": "Parse Probe",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [parse_pos[0] + 1100, parse_pos[1] - 80],
    }
    nodes.append(parse_probe)

    # ── Skip probe: just mark as not probed ──
    skip_probe = {
        "parameters": {
            "jsCode": """// Meeting doesn't need probing (upcoming or no account)
const meeting = $input.first().json;
return [{ json: {
  ...meeting,
  probeStatus: meeting.hasEnded ? 'NO_ACCOUNT' : 'UPCOMING',
  probeDetail: '',
} }];
"""
        },
        "id": uid(),
        "name": "Skip Probe",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [parse_pos[0] + 660, parse_pos[1] + 120],
    }
    nodes.append(skip_probe)

    # ── Build Report: aggregate all probed meetings into one Slack message ──
    build_report = {
        "parameters": {
            "jsCode": """// Aggregate all meeting probe results into a Slack report
const items = $('Split Meetings').all();
const now = new Date();
const tz = 'America/Los_Angeles';
const nowPT = now.toLocaleTimeString('en-US', { timeZone: tz, hour: 'numeric', minute: '2-digit' });
const datePT = now.toLocaleDateString('en-US', { timeZone: tz, weekday: 'long', month: 'short', day: 'numeric' });

if (!items.length || items[0].json.noMeetings) {
  return [{ json: { summary: `:mag: *Meeting Data Monitor* — ${datePT} at ${nowPT} PT\\n_No meetings found today._` } }];
}

let summary = `:mag: *Meeting Data Monitor* — ${datePT} at ${nowPT} PT\\n`;
summary += `_Tracking: Scott Metcalf, Shreyas Gore_\\n\\n`;

// Status icons
const statusIcon = {
  'ENRICHED': ':green_circle:',
  'NOT_ENRICHED': ':yellow_circle:',
  'NO_ACCOUNT': ':orange_circle:',
  'UPCOMING': ':calendar:',
  'UNKNOWN': ':grey_question:',
};

// Legend
summary += ':green_circle: transcript data available  :yellow_circle: no transcript yet  :calendar: upcoming\\n\\n';

let enriched = 0, notEnriched = 0, upcoming = 0;

for (const item of items) {
  const m = item.json;
  const icon = statusIcon[m.probeStatus] || ':grey_question:';

  summary += `${icon} *${m.time}* — ${m.subject} (${m.elapsed})\\n`;
  summary += `    _${m.account}_ | ${m.rep || ''}\\n`;

  if (m.probeStatus === 'ENRICHED') {
    summary += `    :memo: ${m.probeDetail}\\n`;
    enriched++;
  } else if (m.probeStatus === 'NOT_ENRICHED') {
    summary += `    :hourglass_flowing_sand: ${m.probeDetail || 'Calendar data only — no transcript yet'}\\n`;
    notEnriched++;
  } else if (m.probeStatus === 'UPCOMING') {
    upcoming++;
  }
  summary += '\\n';
}

summary += `---\\n_:green_circle: ${enriched} enriched | :yellow_circle: ${notEnriched} waiting | :calendar: ${upcoming} upcoming_`;

return [{ json: { summary } }];
"""
        },
        "id": uid(),
        "name": "Build Report",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [parse_pos[0] + 1320, parse_pos[1]],
    }
    nodes.append(build_report)

    # ── Rewire connections ──
    # Old: Parse & Filter → Open DM → Post Report
    # New: Parse & Filter → Split Meetings → [loop body] → ... → [done] → Build Report → Open DM → Post Report

    # Remove old connections from Parse & Filter
    connections.pop("Parse & Filter Meetings", None)
    connections.pop("Open DM", None)
    connections.pop("Post Report", None)

    connections["Parse & Filter Meetings"] = {
        "main": [[{"node": "Split Meetings", "type": "main", "index": 0}]]
    }

    # SplitInBatches v3: output 0 = done, output 1 = loop
    connections["Split Meetings"] = {
        "main": [
            [{"node": "Build Report", "type": "main", "index": 0}],  # done
            [{"node": "Needs Probe?", "type": "main", "index": 0}],  # loop
        ]
    }

    # If true → Build Probe Prompt, If false → Skip Probe
    connections["Needs Probe?"] = {
        "main": [
            [{"node": "Build Probe Prompt", "type": "main", "index": 0}],  # true
            [{"node": "Skip Probe", "type": "main", "index": 0}],  # false
        ]
    }

    connections["Build Probe Prompt"] = {
        "main": [[{"node": "Probe Agent", "type": "main", "index": 0}]]
    }

    connections["Probe Agent"] = {
        "main": [[{"node": "Parse Probe", "type": "main", "index": 0}]]
    }

    connections["Parse Probe"] = {
        "main": [[{"node": "Split Meetings", "type": "main", "index": 0}]]
    }

    connections["Skip Probe"] = {
        "main": [[{"node": "Split Meetings", "type": "main", "index": 0}]]
    }

    connections["Build Report"] = {
        "main": [[{"node": "Open DM", "type": "main", "index": 0}]]
    }

    connections["Open DM"] = {
        "main": [[{"node": "Post Report", "type": "main", "index": 0}]]
    }

    # ── Sub-node connections (LLM + MCP → Agent) ──
    # These use ai_languageModel and ai_tool connection types
    connections["Probe LLM"] = {
        "ai_languageModel": [[{"node": "Probe Agent", "type": "ai_languageModel", "index": 0}]]
    }

    connections["Probe MCP"] = {
        "ai_tool": [[{"node": "Probe Agent", "type": "ai_tool", "index": 0}]]
    }

    print(f"  Added 8 new nodes (agent trio + probe logic + report)")
    print(f"  Rewired connections")

    print(f"\n=== Pushing workflow ===")
    result = push_workflow(WF_ID, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")
    sync_local(result, "Meeting Data Monitor.json")
    print(f"\nDone! Now has MCP probe for each completed meeting.")


if __name__ == "__main__":
    main()
