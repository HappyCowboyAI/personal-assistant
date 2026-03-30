"""
Fix: Replace broken Confluence MCP node with HTTP Request Tools using REST API.

The Atlassian MCP (SSE + Streamable HTTP) both fail with "We are having trouble
completing this action." Replace with two HTTP Request Tool nodes that use the
Confluence REST API with Basic Auth (email + API token):

1. Search Confluence — CQL search, returns page titles + excerpts
2. Read Confluence Page — fetch full page content by ID

Both are wired to the Presentation Agent as ai_tool connections so the agent
can call them when it needs internal company data for presentations.

Usage:
    N8N_API_KEY=... python3 scripts/fix_presentation_confluence_rest.py
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


def main():
    print(f"Fetching Backstory Presentation {WF_PRESENTATION}...")
    wf = fetch_workflow(WF_PRESENTATION)
    nodes = wf["nodes"]
    connections = wf["connections"]
    print(f"  {len(nodes)} nodes")

    # --- 1. Remove broken Confluence MCP node ---
    confluence_idx = None
    for i, node in enumerate(nodes):
        if node["name"] == "Confluence MCP":
            confluence_idx = i
            break

    if confluence_idx is not None:
        nodes.pop(confluence_idx)
        print("  Removed broken Confluence MCP node")
    else:
        print("  Confluence MCP node not found (already removed?)")

    # Remove Confluence MCP from connections
    if "Confluence MCP" in connections:
        del connections["Confluence MCP"]
        print("  Removed Confluence MCP connections")

    # --- 2. Add "Search Confluence" HTTP Request Tool ---
    search_node_id = uid()
    search_node = {
        "parameters": {
            "description": "Search Confluence for internal company documentation. Use this to find pages about product features, engineering architecture, roadmaps, processes, competitive intel, customer research, and any internal company information. Pass a search query and get back page titles, excerpts, space names, and page IDs. Use the page IDs with the Read Confluence Page tool to get full content.",
            "method": "GET",
            "url": "https://peopleai.atlassian.net/wiki/rest/api/search",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "httpBasicAuth",
            "sendQuery": True,
            "parametersQuery": {
                "values": [
                    {
                        "name": "cql",
                        "value": "={query}",
                        "valueProvider": "fieldValue"
                    },
                    {
                        "name": "limit",
                        "value": "5"
                    }
                ]
            },
            "placeholderDefinitions": {
                "values": [
                    {
                        "name": "query",
                        "description": "CQL search query. Examples: 'type=page AND text~\"product roadmap\"', 'type=page AND space=ENG AND text~\"architecture\"', 'type=page AND text~\"competitive analysis\"'. Always include type=page. Use text~ for full-text search.",
                        "type": "string"
                    }
                ]
            },
            "optimizeResponse": True,
            "responseMapping": "={{ const results = ($response.body.results || []).map(r => ({ title: r.title, excerpt: (r.excerpt || '').substring(0, 300), pageId: r.content?.id, space: r.resultGlobalContainer?.title, url: 'https://peopleai.atlassian.net/wiki' + (r.url || '') })); return JSON.stringify(results); }}"
        },
        "id": search_node_id,
        "name": "Search Confluence",
        "type": "@n8n/n8n-nodes-langchain.toolHttpRequest",
        "typeVersion": 1.1,
        "position": [776, 640],
        "credentials": {
            "httpBasicAuth": ATLASSIAN_BASIC_AUTH
        }
    }
    nodes.append(search_node)
    print("  Added 'Search Confluence' HTTP Request Tool")

    # --- 3. Add "Read Confluence Page" HTTP Request Tool ---
    read_node_id = uid()
    read_node = {
        "parameters": {
            "description": "Read the full content of a Confluence page by its page ID. Use this after searching to get detailed content from the most relevant pages. Returns the page title and body text (HTML stripped to plain text).",
            "method": "GET",
            "url": "=https://peopleai.atlassian.net/wiki/rest/api/content/{pageId}?expand=body.view",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "httpBasicAuth",
            "placeholderDefinitions": {
                "values": [
                    {
                        "name": "pageId",
                        "description": "The Confluence page ID (numeric string) obtained from the Search Confluence tool results.",
                        "type": "string"
                    }
                ]
            },
            "optimizeResponse": True,
            "responseMapping": "={{ const title = $response.body.title || ''; const html = $response.body?.body?.view?.value || ''; const text = html.replace(/<[^>]+>/g, ' ').replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '\"').replace(/\\s+/g, ' ').trim().substring(0, 5000); return JSON.stringify({ title, content: text }); }}"
        },
        "id": read_node_id,
        "name": "Read Confluence Page",
        "type": "@n8n/n8n-nodes-langchain.toolHttpRequest",
        "typeVersion": 1.1,
        "position": [920, 640],
        "credentials": {
            "httpBasicAuth": ATLASSIAN_BASIC_AUTH
        }
    }
    nodes.append(read_node)
    print("  Added 'Read Confluence Page' HTTP Request Tool")

    # --- 4. Wire both tools to Presentation Agent ---
    connections["Search Confluence"] = {
        "ai_tool": [[{"node": "Presentation Agent", "type": "ai_tool", "index": 0}]]
    }
    connections["Read Confluence Page"] = {
        "ai_tool": [[{"node": "Presentation Agent", "type": "ai_tool", "index": 0}]]
    }
    print("  Wired both tools to Presentation Agent as ai_tool")

    print(f"\n=== Pushing Backstory Presentation ===")
    result = push_workflow(WF_PRESENTATION, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")
    sync_local(result, "Backstory Presentation.json")

    print("\nDone! Confluence access via REST API (Basic Auth).")
    print("  Search Confluence: CQL search → page titles, excerpts, IDs")
    print("  Read Confluence Page: full page content by ID")
    print("  Both wired to Presentation Agent as tools")
    print("  Test: presentation Q1 engineering review")


if __name__ == "__main__":
    main()
