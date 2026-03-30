"""
Add mailto "Open in Email" button to DM followup/re-engagement drafts.

The DM conversation agent path (Events Handler) posts drafts as plain text.
Insert a Code node between DM Conversation Agent → DM Post Answer that
detects email drafts (contains *To:* and *Subject:*) and adds a mailto button.
For non-draft responses, passes through unchanged.

Usage:
    N8N_API_KEY=... python scripts/add_mailto_to_dm_draft.py
"""

from n8n_helpers import (
    uid, find_node, fetch_workflow, push_workflow, sync_local,
    WF_EVENTS_HANDLER, NODE_CODE,
)

MAILTO_CODE = r"""
// If the agent output looks like an email draft, add a mailto button.
// Otherwise pass through unchanged for general DM responses.
const output = $json.output || $json.text || '';
const promptData = $('Build DM System Prompt').first().json;

const toMatch = output.match(/\*To:\*\s*(.+)/i);
const ccMatch = output.match(/\*CC:\*\s*(.+)/i);
const subjectMatch = output.match(/\*Subject:\*\s*(.+)/i);

// Not an email draft — pass through as plain text
if (!toMatch || !subjectMatch) {
  return [{ json: { ...($json), isDraft: false, blocks: null, fallbackText: output } }];
}

// Extract email from "Name (Title) <email>" or plain email
function extractEmail(line) {
  const angleMatch = line.match(/<([^>]+@[^>]+)>/);
  if (angleMatch) return angleMatch[1].trim();
  const plainMatch = line.match(/[\w.+-]+@[\w.-]+\.\w+/);
  if (plainMatch) return plainMatch[0].trim();
  return '';
}

const toEmail = extractEmail(toMatch[1]);
const ccEmail = ccMatch ? extractEmail(ccMatch[1]) : '';
const subject = subjectMatch[1].trim();

// Extract body between Subject and ending markers
let body = '';
if (subjectMatch) {
  const startIdx = output.indexOf(subjectMatch[0]) + subjectMatch[0].length;
  let endIdx = output.length;
  const endMarkers = ['\n*Next Steps', '\n_Reply in this thread', '\n---\n_'];
  for (const marker of endMarkers) {
    const idx = output.indexOf(marker, startIdx);
    if (idx > -1 && idx < endIdx) endIdx = idx;
  }
  body = output.substring(startIdx, endIdx).trim();
  body = body.replace(/^---\s*/, '').replace(/\s*---$/, '').trim();
}

// Strip Slack mrkdwn for plain-text email
const plainBody = body
  .replace(/\*([^*]+)\*/g, '$1')
  .replace(/_([^_]+)_/g, '$1')
  .replace(/•/g, '-')
  .replace(/\n{3,}/g, '\n\n');

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

// Truncate if too long
if (mailtoUrl.length > 2000) {
  const truncBody = plainBody.substring(0, 800) + '\n\n[... see full draft in Slack]';
  const params2 = [];
  if (subject) params2.push('subject=' + encodeURIComponent(subject));
  if (ccEmail) params2.push('cc=' + encodeURIComponent(ccEmail));
  params2.push('body=' + encodeURIComponent(truncBody));
  mailtoUrl = 'mailto:' + encodeURIComponent(toEmail) + '?' + params2.join('&');
}

// Build Block Kit
const blocks = [
  { type: "section", text: { type: "mrkdwn", text: output.substring(0, 2999) } }
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

return [{ json: { ...($json), isDraft: true, blocks: JSON.stringify(blocks), fallbackText: output } }];
"""


def main():
    print(f"Fetching Events Handler {WF_EVENTS_HANDLER}...")
    wf = fetch_workflow(WF_EVENTS_HANDLER)
    nodes = wf["nodes"]
    connections = wf["connections"]
    print(f"  {len(nodes)} nodes")

    agent = find_node(nodes, "DM Conversation Agent")
    post = find_node(nodes, "DM Post Answer")
    if not agent or not post:
        print("  ERROR: Could not find DM Conversation Agent or DM Post Answer")
        return

    # Position the new node between agent and post
    agent_pos = agent["position"]
    post_pos = post["position"]
    mid_x = (agent_pos[0] + post_pos[0]) // 2
    mid_y = (agent_pos[1] + post_pos[1]) // 2

    # Shift DM Post Answer right
    post["position"] = [post_pos[0] + 220, post_pos[1]]

    # Create the mailto formatter node
    mailto_node = {
        "parameters": {"jsCode": MAILTO_CODE},
        "id": uid(),
        "name": "Format DM Draft Mailto",
        "type": NODE_CODE,
        "typeVersion": 2,
        "position": [mid_x, mid_y],
    }
    nodes.append(mailto_node)
    print("  Added 'Format DM Draft Mailto' node")

    # Rewire: Agent → Mailto → Post Answer
    if "DM Conversation Agent" in connections:
        connections["DM Conversation Agent"]["main"] = [[{
            "node": "Format DM Draft Mailto",
            "type": "main",
            "index": 0,
        }]]
        print("  Rewired: DM Conversation Agent → Format DM Draft Mailto")

    connections["Format DM Draft Mailto"] = {
        "main": [[{
            "node": "DM Post Answer",
            "type": "main",
            "index": 0,
        }]]
    }
    print("  Wired: Format DM Draft Mailto → DM Post Answer")

    # Update DM Post Answer to use blocks when available (draft), plain text otherwise
    old_body = post["parameters"]["jsonBody"]
    new_body = (
        '={{ JSON.stringify(Object.assign('
        '{ channel: $("Build DM System Prompt").first().json.channelId,'
        ' ts: $("DM Post Thinking").first().json.ts,'
        ' text: $json.fallbackText || "Sorry, I was unable to generate a response." },'
        ' $json.isDraft && $json.blocks ? { blocks: JSON.parse($json.blocks) } : {}'
        ')) }}'
    )
    post["parameters"]["jsonBody"] = new_body
    print("  Updated DM Post Answer to use blocks for drafts")

    print(f"\n=== Pushing workflow ===")
    result = push_workflow(WF_EVENTS_HANDLER, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")

    print("\n=== Syncing ===")
    sync_local(result, "Slack Events Handler.json")
    print(f"\nDone! {len(result['nodes'])} total nodes")


if __name__ == "__main__":
    main()
