"""
Fix: Replace broken Confluence tool nodes with a pre-fetch Code node.

The toolHttpRequest approach doesn't work reliably — the agent constructs bad
CQL queries and gets wrong results. Instead, use the two-layer pattern:
1. Pre-search Confluence deterministically using the prompt topic words
2. Read top 3 pages
3. Inject the content into the agent's system prompt as context

This is the same pattern that works for meeting prep (Query API pre-fetch).

Usage:
    N8N_API_KEY=... python3 scripts/fix_presentation_confluence_prefetch.py
"""

import json
import uuid
from n8n_helpers import (
    find_node, fetch_workflow, push_workflow, sync_local,
)

WF_PRESENTATION = "lJypxYaw0BmUsTV8"


def uid():
    return str(uuid.uuid4())


SEARCH_CONFLUENCE_CODE = r"""// Pre-fetch Confluence pages relevant to the presentation topic
const input = $('Resolve Presentation Identity').first().json;
const prompt = (input.agentPrompt || '');
const promptLower = prompt.toLowerCase();

// Extract key topic words (remove common filler)
const stopWords = new Set(['a','an','the','for','and','or','of','to','in','on','with','about',
  'create','build','make','presentation','slide','slides','deck','our','my','their','this',
  'that','please','can','you','want','need','give','me','us','show','overview','deep','dive']);
const words = promptLower.split(/\s+/).filter(w => w.length > 2 && !stopWords.has(w));

// Build multiple CQL queries: title-based (precise) then text-based (broad)
const queries = [];
if (words.length > 0) {
  // Full phrase title search
  queries.push('type=page AND title~"' + words.join(' ') + '"');
  // Shorter phrase if prompt is long
  if (words.length > 3) {
    queries.push('type=page AND title~"' + words.slice(0, 3).join(' ') + '"');
  }
  // Text search fallback
  queries.push('type=page AND text~"' + words.join(' ') + '"');
}

const baseUrl = 'https://peopleai.atlassian.net/wiki/rest/api';
const auth = 'Basic ' + Buffer.from('scott.metcalf@people.ai:REDACTED_ATLASSIAN_TOKEN_1').toString('base64');
const headers = { 'Authorization': auth, 'Accept': 'application/json' };

// Run searches, collect unique pages
const seenIds = new Set();
const pages = [];

for (const cql of queries) {
  if (pages.length >= 5) break;
  try {
    const url = baseUrl + '/search?cql=' + encodeURIComponent(cql) + '&limit=5';
    const resp = await fetch(url, { headers });
    if (!resp.ok) continue;
    const data = await resp.json();
    for (const r of (data.results || [])) {
      const id = r.content?.id;
      if (!id || seenIds.has(id)) continue;
      seenIds.add(id);
      pages.push({ id, title: r.title, excerpt: (r.excerpt || '').substring(0, 300), space: r.resultGlobalContainer?.title || '' });
    }
  } catch(e) { /* continue on error */ }
}

// Read full content of top 3 pages
const fullPages = [];
for (const page of pages.slice(0, 3)) {
  try {
    const resp = await fetch(baseUrl + '/content/' + page.id + '?expand=body.view', { headers });
    if (!resp.ok) continue;
    const data = await resp.json();
    const html = data.body?.view?.value || '';
    const text = html.replace(/<[^>]+>/g, ' ').replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&')
      .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"')
      .replace(/\s+/g, ' ').trim().substring(0, 4000);
    fullPages.push({ title: page.title, space: page.space, content: text });
  } catch(e) { /* continue on error */ }
}

// Build context string to inject into system prompt
let confluenceContext = '';
if (fullPages.length > 0) {
  confluenceContext = '\n\n## CONFLUENCE RESEARCH RESULTS\nThe following internal Confluence pages were found about this topic. USE THIS REAL DATA in your slides — do not fabricate information when you have real content below:\n\n';
  for (const p of fullPages) {
    confluenceContext += '### ' + p.title + ' [' + p.space + ']\n' + p.content + '\n\n---\n\n';
  }
}

return [{ json: {
  ...input,
  systemPrompt: input.systemPrompt + confluenceContext,
  confluencePageCount: fullPages.length,
  confluenceSearchResults: pages.length
}}];
"""


def main():
    print(f"Fetching Backstory Presentation {WF_PRESENTATION}...")
    wf = fetch_workflow(WF_PRESENTATION)
    nodes = wf["nodes"]
    connections = wf["connections"]
    print(f"  {len(nodes)} nodes")

    # --- 1. Remove old tool nodes ---
    for name in ["Search Confluence", "Read Confluence Page"]:
        for i, n in enumerate(nodes):
            if n["name"] == name:
                nodes.pop(i)
                print(f"  Removed {name} ({n['type']})")
                break
        if name in connections:
            del connections[name]

    # --- 2. Add Search Confluence Code node ---
    search_node = {
        "parameters": {"jsCode": SEARCH_CONFLUENCE_CODE},
        "id": uid(),
        "name": "Search Confluence",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [530, 400]
    }
    nodes.append(search_node)
    print("  Added Search Confluence Code node (pre-fetch + read)")

    # --- 3. Rewire: Resolve → Search Confluence → Agent ---
    connections["Resolve Presentation Identity"] = {
        "main": [[{"node": "Search Confluence", "type": "main", "index": 0}]]
    }
    connections["Search Confluence"] = {
        "main": [[{"node": "Presentation Agent", "type": "main", "index": 0}]]
    }
    print("  Wired: Resolve → Search Confluence → Presentation Agent")

    # --- 4. Update Agent to read enriched prompt from Search Confluence ---
    agent = find_node(nodes, "Presentation Agent")
    agent["parameters"]["options"]["systemMessage"] = "={{ $('Search Confluence').first().json.systemPrompt }}"
    agent["parameters"]["text"] = "={{ $('Search Confluence').first().json.agentPrompt }}"
    print("  Updated Agent to read from Search Confluence output")

    print(f"\n=== Pushing Backstory Presentation ===")
    result = push_workflow(WF_PRESENTATION, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")
    sync_local(result, "Backstory Presentation.json")

    print("\nDone! Confluence is now pre-fetched (two-layer pattern):")
    print("  1. Extract topic words from presentation prompt")
    print("  2. Search Confluence with title~ queries (precise)")
    print("  3. Read top 3 full pages")
    print("  4. Inject content into agent's system prompt")
    print("  Agent sees real Confluence data as context, not tools")


if __name__ == "__main__":
    main()
