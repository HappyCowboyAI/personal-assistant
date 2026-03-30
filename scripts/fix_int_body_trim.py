"""
Fix: Stop email body extraction at signature in Interactive Handler formatters.

Same fix as fix_email_body_trim.py but for the Interactive Handler which
uses `agentOutput` instead of `output`.

Usage:
    N8N_API_KEY=... python scripts/fix_int_body_trim.py
"""

from n8n_helpers import (
    find_node, fetch_workflow, push_workflow, sync_local,
    WF_INTERACTIVE_HANDLER,
)

OLD_EXTRACT = """let body = '';
if (subjectMatch) {
  const startIdx = agentOutput.indexOf(subjectMatch[0]) + subjectMatch[0].length;
  let endIdx = agentOutput.length;

  // Find where the email body ends
  const endMarkers = ['\\n*Next Steps', '\\n_Reply in this thread', '\\n---\\n_'];
  for (const marker of endMarkers) {
    const idx = agentOutput.indexOf(marker, startIdx);
    if (idx > -1 && idx < endIdx) endIdx = idx;
  }

  body = agentOutput.substring(startIdx, endIdx).trim();
  // Strip the --- dividers
  body = body.replace(/^---\\s*/, '').replace(/\\s*---$/, '').trim();
}"""

NEW_EXTRACT = """// Extract email body between the --- dividers (after Subject, before trailing ---)
let body = '';
if (subjectMatch) {
  const startIdx = agentOutput.indexOf(subjectMatch[0]) + subjectMatch[0].length;
  let afterSubject = agentOutput.substring(startIdx);

  // The email body is typically wrapped in --- dividers
  const openDivider = afterSubject.indexOf('---');
  if (openDivider > -1) {
    const bodyStart = openDivider + 3;
    const closeDivider = afterSubject.indexOf('\\n---', bodyStart);
    if (closeDivider > -1) {
      body = afterSubject.substring(bodyStart, closeDivider).trim();
    } else {
      body = afterSubject.substring(bodyStart).trim();
    }
  } else {
    body = afterSubject.trim();
  }

  // Trim at any Slack UI chrome that leaked through
  const uiMarkers = [
    '\\n_Reply in this thread',
    '\\n_Reply to adjust',
    '\\n:warning:',
    '\\n\\u26a0',
    '\\n*Next Steps',
  ];
  for (const marker of uiMarkers) {
    const idx = body.indexOf(marker);
    if (idx > -1) body = body.substring(0, idx).trim();
  }

  body = body.replace(/^---\\s*/, '').replace(/\\s*---$/, '').trim();
}"""


def fix_formatter(wf, node_name):
    node = find_node(wf["nodes"], node_name)
    if not node:
        print(f"  WARNING: '{node_name}' not found")
        return 0

    code = node["parameters"]["jsCode"]

    if OLD_EXTRACT in code:
        code = code.replace(OLD_EXTRACT, NEW_EXTRACT)
        node["parameters"]["jsCode"] = code
        print(f"  Updated body extraction in '{node_name}'")
        return 1
    elif "Slack UI chrome" in code:
        print(f"  '{node_name}' already updated")
        return 0
    else:
        print(f"  WARNING: Could not find extraction block in '{node_name}'")
        return 0


def main():
    print(f"Fetching Interactive Handler {WF_INTERACTIVE_HANDLER}...")
    wf = fetch_workflow(WF_INTERACTIVE_HANDLER)
    print(f"  {len(wf['nodes'])} nodes")

    changes = 0
    changes += fix_formatter(wf, "Format Draft with Mailto")
    changes += fix_formatter(wf, "Format Re-engagement with Mailto")

    if changes:
        print(f"\n=== Pushing Interactive Handler ({changes} changes) ===")
        result = push_workflow(WF_INTERACTIVE_HANDLER, wf)
        print(f"  HTTP 200, {len(result['nodes'])} nodes")
        sync_local(result, "Interactive Events Handler.json")

    print("\nDone!")


if __name__ == "__main__":
    main()
