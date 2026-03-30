"""
Fix: Re-enable Confluence MCP research in Backstory Presentation workflow.

The Confluence MCP node is already wired to the Presentation Agent with working
OAuth2 credentials (mL7GmjUrxj1FpYxZ), but the system prompt was stripped of
Confluence instructions by fix_presentation_reliability.py (SSE was unreliable).

Now that the credential works, update the system prompt to instruct the agent
to search Confluence for relevant internal docs before generating slides.

Usage:
    N8N_API_KEY=... python3 scripts/fix_presentation_confluence.py
"""

from n8n_helpers import (
    find_node, fetch_workflow, push_workflow, sync_local,
)

WF_PRESENTATION = "lJypxYaw0BmUsTV8"


NEW_RESOLVE_CODE = r"""const input = $('Workflow Input Trigger').first().json;

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
RESEARCH TOOLS — USE THEM PROACTIVELY:
You have two powerful research tools. Use them BEFORE generating slides to gather real data.

1. CONFLUENCE (Atlassian) — Internal company documentation, architecture, processes, project plans.
   - ALWAYS search Confluence first when the topic involves internal company information.
   - Key spaces to search:
     • Product Development (PD) — product specs, roadmaps, feature docs
     • Engineering (ENG) — architecture, technical docs, runbooks
     • Analytics (AN) — data models, dashboards, metrics definitions
     • Customer Development (CD) — customer research, use cases
     • Customer Success Group (CS) — onboarding, adoption, health scores
     • Marketing (MAR) — messaging, positioning, competitive intel
     • Company (COM) — company-wide announcements, strategy, OKRs
     • Product Feedback (PF) — customer feedback, feature requests
     • ClosePlan (CP/CPDOC) — deal execution methodology
   - Search broadly — try 2-3 different queries if the first doesn't return results.
   - Pull real data, metrics, project details, and technical specifics into your slides.
   - Use real names, dates, and facts from Confluence — never fabricate internal data.

2. PEOPLE.AI MCP — Account intelligence, sales data, engagement metrics, deal activity.
   - Use for any presentation involving customers, accounts, deals, or pipeline.
   - Pull real engagement data, meeting history, and relationship intelligence.
   - Great for QBRs, account reviews, pipeline analyses, and executive briefings.

RESEARCH WORKFLOW:
1. Read the user prompt carefully — identify what topics need research.
2. Search Confluence for relevant internal docs (try 2-3 searches with different terms).
3. Read the most relevant Confluence pages to extract real data and context.
4. If the topic involves accounts/customers/deals, also query People.ai MCP.
5. Synthesize findings into structured, data-rich slides with real information.

IMPORTANT:
- If tools return no results or error, proceed without them — create the best presentation you can from context alone.
- NEVER let a tool failure prevent you from generating the slide JSON.
- After all research, your FINAL output must be ONLY the JSON object. No commentary.`;

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


def main():
    print(f"Fetching Backstory Presentation {WF_PRESENTATION}...")
    wf = fetch_workflow(WF_PRESENTATION)
    nodes = wf["nodes"]
    print(f"  {len(nodes)} nodes")

    # Verify Confluence MCP is wired in
    confluence_found = False
    for node in nodes:
        if node["name"] == "Confluence MCP":
            confluence_found = True
            creds = node.get("credentials", {})
            print(f"  Confluence MCP: endpoint={node['parameters'].get('endpointUrl')}")
            print(f"  Confluence MCP: credential={creds}")
            break

    if not confluence_found:
        print("  WARNING: Confluence MCP node not found in workflow!")
        print("  The node needs to be added and wired to Presentation Agent as ai_tool")
        return

    # Update Resolve Presentation Identity with Confluence instructions
    node = find_node(nodes, "Resolve Presentation Identity")
    if not node:
        print("  ERROR: Resolve Presentation Identity not found")
        return

    node["parameters"]["jsCode"] = NEW_RESOLVE_CODE
    print("  Updated Resolve Presentation Identity:")
    print("    + Confluence research instructions (search spaces, read pages)")
    print("    + Key space directory (PD, ENG, AN, CD, CS, MAR, COM, PF, CP)")
    print("    + Research workflow (search → read → synthesize)")
    print("    + Graceful fallback if tools fail")

    # Bump maxIterations to give agent room for Confluence research
    agent = find_node(nodes, "Presentation Agent")
    if agent:
        old_iters = agent["parameters"]["options"].get("maxIterations", 10)
        agent["parameters"]["options"]["maxIterations"] = 20
        print(f"  Presentation Agent maxIterations: {old_iters} → 20")

    print(f"\n=== Pushing Backstory Presentation ===")
    result = push_workflow(WF_PRESENTATION, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")
    sync_local(result, "Backstory Presentation.json")

    print("\nDone! Presentation agent now uses Confluence + People.ai MCP.")
    print("  Confluence: search internal docs, pull real data into slides")
    print("  People.ai: account intelligence, engagement metrics")
    print("  Test: presentation Q1 engineering review")


if __name__ == "__main__":
    main()
