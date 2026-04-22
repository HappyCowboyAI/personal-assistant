#!/usr/bin/env python3
"""
Fix Backstory Presentation workflow reliability.

Problem: Presentations come out with only 2 slides (fallback) because:
1. The Confluence MCP tool may fail (SSE connection issues), causing the agent to error
2. With continueOnFail:true, the agent output is an error object, not slide JSON
3. Parse Slide JSON can't extract valid slides from the error output

Fixes:
1. Improve Parse Slide JSON to detect agent errors and log them
2. Make Confluence MCP optional (remove it as a required tool — Backstory MCP is enough)
3. Strengthen the system prompt to emphasize JSON-only output
4. Add error recovery: if agent fails, create a basic presentation from the prompt alone
"""

import json
import os
import uuid
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

PRESENTATION_WF_ID = "lJypxYaw0BmUsTV8"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}


def uid():
    return str(uuid.uuid4())


def fetch_workflow(wf_id):
    resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def push_workflow(wf_id, wf):
    payload = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
               "settings": wf.get("settings", {}), "staticData": wf.get("staticData")}
    resp = requests.put(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}", headers=HEADERS, json=payload)
    resp.raise_for_status()
    return resp.json()


def sync_local(wf, filename):
    path = os.path.join(REPO_ROOT, "n8n", "workflows", filename)
    with open(path, "w") as f:
        json.dump(wf, f, indent=4)
    print(f"  Synced {path}")


# Updated system prompt — removes mandatory Confluence research, emphasizes JSON output
UPDATED_RESOLVE_CODE = r"""const input = $('Workflow Input Trigger').first().json;

const BRAND_SPEC = `You are a presentation architect for Backstory. Create structured JSON that will be rendered into branded Google Slides.

SLIDE TYPES (use these type values exactly):

1. "title" — Opening slide. Always first.
   {type:"title", title:"...", subtitle:"..."}

2. "agenda" — Bulleted outline of topics.
   {type:"agenda", title:"Agenda", items:[
     {text:"Topic 1", subitems:["Detail A","Detail B"]},
     {text:"Topic 2"}
   ]}

3. "section_divider" — Section break. Use between major sections.
   {type:"section_divider", title:"Section Name"}

4. "stats" — Three metrics with values, labels, change indicators.
   {type:"stats", title:"Key Metrics", stats:[
     {value:"99.9%", label:"Uptime", change:"+0.2%"},
     {value:"142ms", label:"P95 Latency", change:"-23ms"},
     {value:"2.4M", label:"Daily Requests", change:"+18%"}
   ]}

5. "two_column" — Side-by-side content (wins/challenges, pros/cons).
   {type:"two_column", title:"...",
    left:{header:"Left Title", items:["Item 1","Item 2"]},
    right:{header:"Right Title", items:["Item 1","Item 2"]}}

6. "three_column_cards" — Three colored cards with bullet items.
   {type:"three_column_cards", title:"...", cards:[
     {title:"Card 1", items:["Item A","Item B"]},
     {title:"Card 2", items:["Item A","Item B"]},
     {title:"Card 3", items:["Item A","Item B"]}
   ]}

7. "four_column_timeline" — Quarterly/phase timeline.
   {type:"four_column_timeline", title:"...", quarters:[
     {label:"Q1", focus:"Theme", value:"Initiative", note:"Details"},
     {label:"Q2", focus:"Theme", value:"Initiative", note:"Details"},
     {label:"Q3", focus:"Theme", value:"Initiative", note:"Details"},
     {label:"Q4", focus:"Theme", value:"Initiative", note:"Details"}
   ]}

8. "thank_you" — Closing slide. Always last.
   {type:"thank_you", title:"Thank You"}

GUIDELINES:
- 6-12 slides typical. Always start with title, end with thank_you.
- Use section_divider between major topic areas.
- Use stats when you have 3 quantitative metrics.
- Use two_column for comparisons or contrasts.
- Use three_column_cards for 3 parallel items (teams, priorities).
- Use four_column_timeline for chronological plans.
- Keep text concise — bullet points, not paragraphs.
- Stats values should be short (e.g. "$2.4M", "99.9%", "142ms").

CRITICAL OUTPUT RULES:
- Your FINAL response must be ONLY a valid JSON object. Nothing else.
- No prose before or after. No markdown fences. No explanation.
- Do NOT wrap the JSON in \`\`\`json blocks.
- The JSON must start with { and end with }
- Format: {"title":"Presentation Title","slides":[...]}`;

const RESEARCH_INSTRUCTIONS = `
RESEARCH TOOLS — USE WHEN RELEVANT:
You have access to Backstory MCP tools for account intelligence, sales data, and engagement metrics.

- If the topic involves customers, accounts, deals, or pipeline, use Backstory tools to gather real data.
- Use find_account, get_account_status, ask_sales_ai_about_account to pull engagement data.
- If tools return no results or error, proceed without them — create the best presentation you can from context alone.
- NEVER let a tool failure prevent you from generating the slide JSON.

REMEMBER: After any research, your FINAL output must be ONLY the JSON object. No commentary.`;

const systemPrompt = BRAND_SPEC + RESEARCH_INSTRUCTIONS;
const agentPrompt = input.presentationPrompt || 'Create a general company overview presentation';

return [{ json: {
  systemPrompt,
  agentPrompt,
  channelId: input.channelId,
  assistantName: input.assistantName || 'Your Assistant',
  assistantEmoji: input.assistantEmoji || ':robot_face:',
  presentationPrompt: input.presentationPrompt
}}];
"""

# Improved Parse Slide JSON with better error detection and extraction
UPDATED_PARSE_CODE = r"""const agentOutput = $('Presentation Agent').first().json;

// Extract text from various possible agent output structures
let text = '';
if (agentOutput.output) {
  text = agentOutput.output;
} else if (agentOutput.text) {
  text = agentOutput.text;
} else if (agentOutput.error) {
  // Agent errored — log it
  console.log('Presentation Agent error:', JSON.stringify(agentOutput.error).substring(0, 500));
  text = '';
} else {
  text = JSON.stringify(agentOutput);
}

let parsed = null;

// Strategy 1: Direct parse (agent returned clean JSON)
try { parsed = JSON.parse(text.trim()); } catch (e) {}

// Strategy 2: Extract from markdown code block
if (!parsed) {
  const m = text.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (m) try { parsed = JSON.parse(m[1].trim()); } catch (e) {}
}

// Strategy 3: Find the outermost JSON object with slides array
if (!parsed) {
  // Look for {"title":... pattern
  const start = text.indexOf('{"');
  if (start >= 0) {
    // Find matching closing brace by counting braces
    let depth = 0;
    let end = -1;
    for (let i = start; i < text.length; i++) {
      if (text[i] === '{') depth++;
      else if (text[i] === '}') {
        depth--;
        if (depth === 0) { end = i + 1; break; }
      }
    }
    if (end > start) {
      try { parsed = JSON.parse(text.substring(start, end)); } catch (e) {}
    }
  }
}

// Strategy 4: Try extracting any JSON object (greedy regex)
if (!parsed) {
  const m = text.match(/\{[\s\S]*\}/);
  if (m) try { parsed = JSON.parse(m[0]); } catch (e) {}
}

// Validate: must have slides array
if (parsed && (!parsed.slides || !Array.isArray(parsed.slides) || parsed.slides.length === 0)) {
  console.log('Parsed JSON but no valid slides array. Keys:', Object.keys(parsed).join(', '));
  parsed = null;
}

// Fallback — create a meaningful single-slide deck from the prompt
if (!parsed) {
  const prompt = $('Resolve Presentation Identity').first().json.presentationPrompt || 'Presentation';
  console.log('WARNING: Could not parse agent output. First 500 chars:', text.substring(0, 500));
  parsed = {
    title: prompt.substring(0, 80),
    slides: [
      {type: "title", title: prompt.substring(0, 80), subtitle: "Content generation needs retry"},
      {type: "two_column", title: "Overview",
        left: {header: "Key Points", items: ["Content generation encountered an issue", "Please retry the presentation command"]},
        right: {header: "Next Steps", items: ["Try again with a more specific prompt", "Check n8n execution logs for details"]}},
      {type: "thank_you", title: "Thank You"}
    ]
  };
}

// Ensure bookend slides
if (parsed.slides[0] && parsed.slides[0].type !== 'title') {
  parsed.slides.unshift({type: 'title', title: parsed.title || 'Presentation', subtitle: ''});
}
if (parsed.slides[parsed.slides.length - 1].type !== 'thank_you') {
  parsed.slides.push({type: 'thank_you', title: 'Thank You'});
}

return [{ json: parsed }];
"""


def upgrade_presentation_workflow(wf):
    print(f"\n=== Fixing Backstory Presentation reliability ===")
    nodes = wf["nodes"]
    connections = wf["connections"]

    changes = 0

    # --- 1. Update Resolve Presentation Identity with improved prompt ---
    for node in nodes:
        if node["name"] == "Resolve Presentation Identity":
            node["parameters"]["jsCode"] = UPDATED_RESOLVE_CODE
            print("  Updated Resolve Presentation Identity (stronger JSON instructions, optional research)")
            changes += 1
            break

    # --- 2. Update Parse Slide JSON with better error handling ---
    for node in nodes:
        if node["name"] == "Parse Slide JSON":
            node["parameters"]["jsCode"] = UPDATED_PARSE_CODE
            print("  Updated Parse Slide JSON (better extraction, error logging)")
            changes += 1
            break

    # --- 3. Remove Confluence MCP as a tool (keep Backstory MCP) ---
    # The Confluence MCP SSE connection is unreliable and causes agent failures.
    # If it's needed later, it can be re-added once the credential/endpoint is stable.
    confluence_node = None
    for i, node in enumerate(nodes):
        if node["name"] == "Confluence MCP":
            confluence_node = node
            nodes.pop(i)
            print("  Removed Confluence MCP tool (unreliable SSE, causes agent failures)")
            changes += 1
            break

    # Remove Confluence MCP from connections
    if "Confluence MCP" in connections:
        del connections["Confluence MCP"]
        print("  Removed Confluence MCP connection")

    # --- 4. Increase agent maxIterations for complex research ---
    for node in nodes:
        if node["name"] == "Presentation Agent":
            node["parameters"]["options"]["maxIterations"] = 15
            print("  Set Presentation Agent maxIterations to 15")
            changes += 1
            break

    print(f"  Total changes: {changes}")
    print(f"  Total nodes: {len(nodes)}")
    return wf


def main():
    print("Fetching Backstory Presentation workflow...")
    wf = fetch_workflow(PRESENTATION_WF_ID)
    print(f"  {len(wf['nodes'])} nodes")

    wf = upgrade_presentation_workflow(wf)

    print("\n=== Pushing updated workflow ===")
    result = push_workflow(PRESENTATION_WF_ID, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")

    print("\n=== Syncing local file ===")
    sync_local(result, "Backstory Presentation.json")

    print("\nDone! Presentation workflow should now be more reliable:")
    print("  - Stronger JSON-only output instructions")
    print("  - Removed unreliable Confluence MCP (Backstory MCP remains)")
    print("  - Better JSON extraction with multiple strategies")
    print("  - Meaningful fallback deck instead of empty 2 slides")


if __name__ == "__main__":
    main()
