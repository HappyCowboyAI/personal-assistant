"""
Fix: Use HTTP Request nodes for Confluence (not fetch in Code node).

fetch() likely fails silently in n8n's sandboxed Code node VM. Switch to
native HTTP Request nodes which are proven to work.

Flow:
  Resolve → Build CQL → Search Confluence → Extract Best Page →
  Read Page → Enrich Prompt → Presentation Agent

Usage:
    N8N_API_KEY=... python3 scripts/fix_presentation_confluence_http.py
"""

import json
import uuid
from n8n_helpers import (
    find_node, fetch_workflow, push_workflow, sync_local,
)

WF_PRESENTATION = "lJypxYaw0BmUsTV8"
ATLASSIAN_BASIC_AUTH = {"id": "LttEseXWsthjfiYz", "name": "Atlassian Basic Auth"}


def uid():
    return str(uuid.uuid4())


# Step 1: Build CQL query from presentation prompt
BUILD_CQL_CODE = r"""const input = $('Resolve Presentation Identity').first().json;
const prompt = (input.agentPrompt || '').toLowerCase();

const stopWords = new Set(['a','an','the','for','and','or','of','to','in','on','with','about',
  'create','build','make','presentation','slide','slides','deck','our','my','their','this',
  'that','please','can','you','want','need','give','me','us','show','overview','deep','dive']);
const words = prompt.split(/\s+/).filter(w => w.length > 2 && !stopWords.has(w));
const topic = words.join(' ');

// Title search is more precise than text search
const cql = 'type=page AND title~"' + topic + '"';

return [{ json: { ...input, cql, topic } }];
"""

# Step 3: Extract best page ID + build context from search results
EXTRACT_PAGE_CODE = r"""const input = $('Build Confluence CQL').first().json;
const searchData = $('Search Confluence').first().json;
const results = searchData.results || [];

let bestPageId = '';
let excerpts = '';

for (const r of results) {
  const id = r.content?.id || '';
  const title = r.title || '';
  const excerpt = (r.excerpt || '').substring(0, 400);
  const space = r.resultGlobalContainer?.title || '';

  if (!bestPageId && id) {
    bestPageId = id;
  }
  if (title) {
    excerpts += '- ' + title + ' [' + space + ']: ' + excerpt + '\n';
  }
}

return [{ json: { ...input, bestPageId, excerpts, searchResultCount: results.length } }];
"""

# Step 5: Combine page content + search excerpts into enriched prompt
ENRICH_PROMPT_CODE = r"""const input = $('Extract Best Page').first().json;

let pageContent = '';
try {
  const pageData = $('Read Confluence Page').first().json;
  const title = pageData.title || '';
  const html = pageData.body?.view?.value || '';
  // Strip HTML to plain text
  const text = html.replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"').replace(/&#39;/g, "'")
    .replace(/\s+/g, ' ').trim().substring(0, 6000);

  if (text.length > 100) {
    pageContent = '\n\n## CONFLUENCE: ' + title + '\n' + text;
  }
} catch(e) {
  // Read Page might have no data if no page was found
}

let confluenceContext = '';
if (pageContent || input.excerpts) {
  confluenceContext = '\n\n## INTERNAL CONFLUENCE DOCUMENTATION\n';
  confluenceContext += 'USE THIS REAL DATA in your slides. Do not ignore this section.\n';
  if (pageContent) {
    confluenceContext += pageContent + '\n\n';
  }
  if (input.excerpts) {
    confluenceContext += '\n### Other related pages:\n' + input.excerpts;
  }
}

return [{ json: {
  ...input,
  systemPrompt: input.systemPrompt + confluenceContext,
  confluenceFound: pageContent.length > 0 || input.excerpts.length > 0
}}];
"""


def main():
    print(f"Fetching Backstory Presentation {WF_PRESENTATION}...")
    wf = fetch_workflow(WF_PRESENTATION)
    nodes = wf["nodes"]
    connections = wf["connections"]
    print(f"  {len(nodes)} nodes")

    # --- Remove old Search Confluence node ---
    for i, n in enumerate(nodes):
        if n["name"] == "Search Confluence":
            nodes.pop(i)
            print(f"  Removed old Search Confluence ({n['type']})")
            break
    if "Search Confluence" in connections:
        del connections["Search Confluence"]

    # Also remove Read Confluence Page if it exists (leftover tool node)
    for i, n in enumerate(nodes):
        if n["name"] == "Read Confluence Page":
            nodes.pop(i)
            print(f"  Removed old Read Confluence Page ({n['type']})")
            break
    if "Read Confluence Page" in connections:
        del connections["Read Confluence Page"]

    # --- Get positions ---
    resolve_pos = [420, 400]
    agent_pos = [640, 400]
    for n in nodes:
        if n["name"] == "Resolve Presentation Identity":
            resolve_pos = n["position"]
        if n["name"] == "Presentation Agent":
            agent_pos = n["position"]

    # Spread nodes evenly between Resolve and Agent
    x_start = resolve_pos[0] + 220
    x_step = 220
    y = resolve_pos[1]

    # --- Add new nodes ---

    # 1. Build Confluence CQL
    build_cql = {
        "parameters": {"jsCode": BUILD_CQL_CODE},
        "id": uid(),
        "name": "Build Confluence CQL",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [x_start, y]
    }
    nodes.append(build_cql)
    print("  Added Build Confluence CQL")

    # 2. Search Confluence (HTTP Request)
    search_http = {
        "parameters": {
            "method": "GET",
            "url": "=https://peopleai.atlassian.net/wiki/rest/api/search?cql={{ encodeURIComponent($json.cql) }}&limit=5",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "httpBasicAuth",
            "options": {"timeout": 15000}
        },
        "id": uid(),
        "name": "Search Confluence",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [x_start + x_step, y],
        "credentials": {"httpBasicAuth": ATLASSIAN_BASIC_AUTH},
        "continueOnFail": True
    }
    nodes.append(search_http)
    print("  Added Search Confluence (HTTP Request)")

    # 3. Extract Best Page
    extract_page = {
        "parameters": {"jsCode": EXTRACT_PAGE_CODE},
        "id": uid(),
        "name": "Extract Best Page",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [x_start + x_step * 2, y]
    }
    nodes.append(extract_page)
    print("  Added Extract Best Page")

    # 4. Read Confluence Page (HTTP Request)
    read_http = {
        "parameters": {
            "method": "GET",
            "url": "=https://peopleai.atlassian.net/wiki/rest/api/content/{{ $json.bestPageId }}?expand=body.view",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "httpBasicAuth",
            "options": {"timeout": 15000}
        },
        "id": uid(),
        "name": "Read Confluence Page",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [x_start + x_step * 3, y],
        "credentials": {"httpBasicAuth": ATLASSIAN_BASIC_AUTH},
        "continueOnFail": True
    }
    nodes.append(read_http)
    print("  Added Read Confluence Page (HTTP Request)")

    # 5. Enrich Agent Prompt
    enrich = {
        "parameters": {"jsCode": ENRICH_PROMPT_CODE},
        "id": uid(),
        "name": "Enrich Agent Prompt",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [x_start + x_step * 4, y]
    }
    nodes.append(enrich)
    print("  Added Enrich Agent Prompt")

    # --- Rewire connections ---
    connections["Resolve Presentation Identity"] = {
        "main": [[{"node": "Build Confluence CQL", "type": "main", "index": 0}]]
    }
    connections["Build Confluence CQL"] = {
        "main": [[{"node": "Search Confluence", "type": "main", "index": 0}]]
    }
    connections["Search Confluence"] = {
        "main": [[{"node": "Extract Best Page", "type": "main", "index": 0}]]
    }
    connections["Extract Best Page"] = {
        "main": [[{"node": "Read Confluence Page", "type": "main", "index": 0}]]
    }
    connections["Read Confluence Page"] = {
        "main": [[{"node": "Enrich Agent Prompt", "type": "main", "index": 0}]]
    }
    connections["Enrich Agent Prompt"] = {
        "main": [[{"node": "Presentation Agent", "type": "main", "index": 0}]]
    }
    print("  Wired: Resolve → Build CQL → Search → Extract → Read Page → Enrich → Agent")

    # Update Agent to read from Enrich node
    agent = find_node(nodes, "Presentation Agent")
    agent["parameters"]["options"]["systemMessage"] = "={{ $('Enrich Agent Prompt').first().json.systemPrompt }}"
    agent["parameters"]["text"] = "={{ $('Enrich Agent Prompt').first().json.agentPrompt }}"
    print("  Updated Agent to read from Enrich Agent Prompt")

    # Move Agent position to make room
    agent["position"] = [x_start + x_step * 5, y]

    print(f"\n=== Pushing Backstory Presentation ===")
    result = push_workflow(WF_PRESENTATION, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")
    sync_local(result, "Backstory Presentation.json")

    print("\nDone! Confluence via HTTP Request nodes (proven pattern):")
    print("  Build CQL → Search (HTTP) → Extract → Read Page (HTTP) → Enrich → Agent")
    print("  No fetch() in Code nodes — all HTTP via native n8n nodes")


if __name__ == "__main__":
    main()
