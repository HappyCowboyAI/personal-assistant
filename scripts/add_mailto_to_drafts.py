"""
Add mailto "Open in Email" button to follow-up and re-engagement email drafts.

Inserts a Code node after each draft agent that parses To/Subject/Body from
the agent's Slack mrkdwn output and builds a mailto: URL. The draft is then
posted as Block Kit with the original text + a mailto button.

Usage:
    N8N_API_KEY=... python scripts/add_mailto_to_drafts.py
"""

from n8n_helpers import (
    uid, find_node, fetch_workflow, push_workflow, sync_local,
    WF_INTERACTIVE_HANDLER, NODE_CODE,
)

MAILTO_CODE = r"""
// Parse To, Subject, Body from agent draft and build mailto link
const agentOutput = $('AGENT_NODE').first().json.output || '';
const context = $('CONTEXT_NODE').first().json;

// Parse fields from Slack mrkdwn format
const toMatch = agentOutput.match(/\*To:\*\s*(.+)/i);
const ccMatch = agentOutput.match(/\*CC:\*\s*(.+)/i);
const subjectMatch = agentOutput.match(/\*Subject:\*\s*(.+)/i);

// Extract email address from "Name (Title) <email>" or plain email
function extractEmail(line) {
  const angleMatch = line.match(/<([^>]+@[^>]+)>/);
  if (angleMatch) return angleMatch[1].trim();
  const plainMatch = line.match(/[\w.+-]+@[\w.-]+\.\w+/);
  if (plainMatch) return plainMatch[0].trim();
  return line.trim();
}

const toRaw = toMatch ? toMatch[1].trim() : '';
const ccRaw = ccMatch ? ccMatch[1].trim() : '';
const toEmail = toRaw ? extractEmail(toRaw) : '';
const ccEmail = ccRaw ? extractEmail(ccRaw) : '';
const subject = subjectMatch ? subjectMatch[1].trim() : '';

// Extract email body: between Subject line and "Next Steps" / "_Reply in this thread"
let body = '';
if (subjectMatch) {
  const startIdx = agentOutput.indexOf(subjectMatch[0]) + subjectMatch[0].length;
  let endIdx = agentOutput.length;

  // Find where the email body ends
  const endMarkers = ['\n*Next Steps', '\n_Reply in this thread', '\n---\n_'];
  for (const marker of endMarkers) {
    const idx = agentOutput.indexOf(marker, startIdx);
    if (idx > -1 && idx < endIdx) endIdx = idx;
  }

  body = agentOutput.substring(startIdx, endIdx).trim();
  // Strip the --- dividers
  body = body.replace(/^---\s*/, '').replace(/\s*---$/, '').trim();
}

// Strip Slack mrkdwn for plain-text email body
const plainBody = body
  .replace(/\*([^*]+)\*/g, '$1')   // bold
  .replace(/_([^_]+)_/g, '$1')     // italic
  .replace(/•/g, '-')               // bullets
  .replace(/\n{3,}/g, '\n\n');      // excess newlines

// Build mailto URL
let mailtoUrl = '';
if (toEmail) {
  const params = [];
  if (subject) params.push('subject=' + encodeURIComponent(subject));
  if (ccEmail) params.push('cc=' + encodeURIComponent(ccEmail));
  if (plainBody) params.push('body=' + encodeURIComponent(plainBody));
  mailtoUrl = 'mailto:' + encodeURIComponent(toEmail);
  if (params.length) mailtoUrl += '?' + params.join('&');
}

// Truncate mailto URL if too long (browser limit ~2000 chars)
const MAX_URL = 2000;
if (mailtoUrl.length > MAX_URL) {
  // Rebuild with truncated body
  const truncBody = plainBody.substring(0, 800) + '\n\n[... see draft in Slack thread for full text]';
  const params2 = [];
  if (subject) params2.push('subject=' + encodeURIComponent(subject));
  if (ccEmail) params2.push('cc=' + encodeURIComponent(ccEmail));
  params2.push('body=' + encodeURIComponent(truncBody));
  mailtoUrl = 'mailto:' + encodeURIComponent(toEmail) + '?' + params2.join('&');
}

// Build Block Kit: draft text + mailto button
const blocks = [
  {
    type: "section",
    text: { type: "mrkdwn", text: agentOutput.substring(0, 2999) }
  }
];

if (mailtoUrl) {
  blocks.push({
    type: "actions",
    elements: [{
      type: "button",
      text: { type: "plain_text", text: ":email: Open in Email", emoji: true },
      url: mailtoUrl,
      style: "primary"
    }]
  });
}

return [{
  json: {
    blocks: JSON.stringify(blocks),
    fallbackText: agentOutput,
    mailtoUrl,
    toEmail,
    subject,
  }
}];
"""


def build_mailto_node(name, agent_node_name, context_node_name, position):
    """Create the mailto formatter Code node with correct cross-node refs."""
    code = MAILTO_CODE.replace("AGENT_NODE", agent_node_name).replace(
        "CONTEXT_NODE", context_node_name
    )
    return {
        "parameters": {"jsCode": code},
        "id": uid(),
        "name": name,
        "type": NODE_CODE,
        "typeVersion": 2,
        "position": position,
    }


def main():
    print(f"Fetching Interactive Events Handler workflow {WF_INTERACTIVE_HANDLER}...")
    wf = fetch_workflow(WF_INTERACTIVE_HANDLER)
    nodes = wf["nodes"]
    connections = wf["connections"]
    print(f"  {len(nodes)} nodes")

    changes = 0

    # ── 1. Follow-up Draft path ──────────────────────────────────────
    agent_node = find_node(nodes, "Followup Draft Agent")
    post_node = find_node(nodes, "Post Draft Reply")

    if agent_node and post_node:
        # Get agent position to place new node between agent and post
        agent_pos = agent_node["position"]
        post_pos = post_node["position"]
        mid_x = (agent_pos[0] + post_pos[0]) // 2
        mid_y = (agent_pos[1] + post_pos[1]) // 2

        # Shift Post Draft Reply right to make room
        post_node["position"] = [post_pos[0] + 220, post_pos[1]]

        # Create the mailto formatter node
        mailto_node = build_mailto_node(
            "Format Draft with Mailto",
            "Followup Draft Agent",
            "Build Followup Context",
            [mid_x, mid_y],
        )
        nodes.append(mailto_node)
        print("  Added 'Format Draft with Mailto' node")

        # Rewire: Agent → Mailto → Post Draft Reply
        # Remove old: Agent → Post Draft Reply
        if "Followup Draft Agent" in connections:
            connections["Followup Draft Agent"]["main"] = [[{
                "node": "Format Draft with Mailto",
                "type": "main",
                "index": 0,
            }]]
            print("  Rewired: Followup Draft Agent → Format Draft with Mailto")

        # Add: Mailto → Post Draft Reply
        connections["Format Draft with Mailto"] = {
            "main": [[{
                "node": "Post Draft Reply",
                "type": "main",
                "index": 0,
            }]]
        }
        print("  Wired: Format Draft with Mailto → Post Draft Reply")

        # Modify Post Draft Reply to use blocks from the mailto node
        old_body = post_node["parameters"]["jsonBody"]
        new_body = '={{ JSON.stringify({ channel: $("Build Followup Context").first().json.channelId, thread_ts: $("Build Followup Context").first().json.messageTs, text: $json.fallbackText || "Draft ready", blocks: JSON.parse($json.blocks), username: $("Build Followup Context").first().json.assistantName, icon_emoji: $("Build Followup Context").first().json.assistantEmoji }) }}'
        post_node["parameters"]["jsonBody"] = new_body
        print("  Updated Post Draft Reply to use Block Kit with mailto button")

        changes += 4
    else:
        print("  WARNING: Could not find Followup Draft Agent or Post Draft Reply")

    # ── 2. Re-engagement Draft path ──────────────────────────────────
    re_agent = find_node(nodes, "Re-engagement Draft Agent")
    re_post = find_node(nodes, "Post Draft to Thread")

    if re_agent and re_post:
        re_agent_pos = re_agent["position"]
        re_post_pos = re_post["position"]
        mid_x = (re_agent_pos[0] + re_post_pos[0]) // 2
        mid_y = (re_agent_pos[1] + re_post_pos[1]) // 2

        re_post["position"] = [re_post_pos[0] + 220, re_post_pos[1]]

        re_mailto_node = build_mailto_node(
            "Format Re-engagement with Mailto",
            "Re-engagement Draft Agent",
            "Build Re-engagement Prompt",
            [mid_x, mid_y],
        )
        nodes.append(re_mailto_node)
        print("  Added 'Format Re-engagement with Mailto' node")

        if "Re-engagement Draft Agent" in connections:
            connections["Re-engagement Draft Agent"]["main"] = [[{
                "node": "Format Re-engagement with Mailto",
                "type": "main",
                "index": 0,
            }]]
            print("  Rewired: Re-engagement Draft Agent → Format Re-engagement with Mailto")

        connections["Format Re-engagement with Mailto"] = {
            "main": [[{
                "node": "Post Draft to Thread",
                "type": "main",
                "index": 0,
            }]]
        }
        print("  Wired: Format Re-engagement with Mailto → Post Draft to Thread")

        # Modify Post Draft to Thread to use blocks
        # This node uses chat.update (not postMessage) — updating the "Drafting..." message
        old_body = re_post["parameters"]["jsonBody"]
        new_body = '={{ JSON.stringify({ channel: $("Route Silence Action").first().json.channelId, ts: $("Post Drafting Message").first().json.ts, text: $json.fallbackText || "Draft ready", blocks: JSON.parse($json.blocks), username: $("Route Silence Action").first().json.assistantName, icon_emoji: $("Route Silence Action").first().json.assistantEmoji }) }}'
        re_post["parameters"]["jsonBody"] = new_body
        print("  Updated Post Draft to Thread to use Block Kit with mailto button")

        changes += 4
    else:
        print("  WARNING: Could not find Re-engagement Draft Agent or Post Draft to Thread")

    if changes == 0:
        print("\nNo changes made")
        return

    print(f"\n=== Pushing workflow ({changes} changes) ===")
    result = push_workflow(WF_INTERACTIVE_HANDLER, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")

    print("\n=== Syncing ===")
    sync_local(result, "Interactive Events Handler.json")

    print(f"\nDone! {len(result['nodes'])} total nodes")


if __name__ == "__main__":
    main()
