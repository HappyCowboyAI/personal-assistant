"""
Fix:
1. DM followup prompt must require email addresses in To/CC lines
2. Mailto button should appear even without a To email (prefill subject/body only)

Usage:
    N8N_API_KEY=... python scripts/fix_draft_emails_required.py
"""

from n8n_helpers import (
    find_node, fetch_workflow, push_workflow, sync_local,
    WF_EVENTS_HANDLER,
)


def main():
    print(f"Fetching Events Handler {WF_EVENTS_HANDLER}...")
    wf = fetch_workflow(WF_EVENTS_HANDLER)
    nodes = wf["nodes"]
    print(f"  {len(nodes)} nodes")

    changes = 0

    # ── 1. Update Build DM System Prompt — require email addresses ──
    prompt_node = find_node(nodes, "Build DM System Prompt")
    if prompt_node:
        code = prompt_node["parameters"]["jsCode"]

        old_to = "'*To:* {primary recipient(s)}',"
        new_to = "'*To:* {Name} ({email@company.com}) — ALWAYS include email addresses. Use People.ai MCP to look up contact emails. If you cannot find an email, still include the name.',"

        if old_to in code:
            code = code.replace(old_to, new_to)
            prompt_node["parameters"]["jsCode"] = code
            print("  Updated followup prompt to require email addresses in To line")
            changes += 1
        else:
            print("  WARNING: Could not find To format line in followup prompt")

    # ── 2. Update Format DM Draft Mailto — show button even without To email ──
    mailto_node = find_node(nodes, "Format DM Draft Mailto")
    if mailto_node:
        code = mailto_node["parameters"]["jsCode"]

        # Replace the condition that requires toEmail
        old_cond = "if (toEmail) {"
        new_cond = "if (toEmail || subject) {"

        if old_cond in code:
            code = code.replace(old_cond, new_cond)
            changes += 1
            print("  Updated mailto node: show button even without To email")

        # Also fix the mailto URL builder to handle missing toEmail
        old_url = "mailtoUrl = 'mailto:' + encodeURIComponent(toEmail);"
        new_url = "mailtoUrl = 'mailto:' + (toEmail ? encodeURIComponent(toEmail) : '');"

        if old_url in code:
            code = code.replace(old_url, new_url)
            changes += 1
            print("  Updated mailto URL builder for missing toEmail")

        # Fix the truncation path too
        old_trunc = "mailtoUrl = 'mailto:' + encodeURIComponent(toEmail) + '?' + params2.join('&');"
        new_trunc = "mailtoUrl = 'mailto:' + (toEmail ? encodeURIComponent(toEmail) : '') + '?' + params2.join('&');"

        if old_trunc in code:
            code = code.replace(old_trunc, new_trunc)
            changes += 1
            print("  Updated truncation path for missing toEmail")

        mailto_node["parameters"]["jsCode"] = code

    if changes == 0:
        print("  No changes")
        return

    print(f"\n=== Pushing ({changes} changes) ===")
    result = push_workflow(WF_EVENTS_HANDLER, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")
    sync_local(result, "Slack Events Handler.json")
    print(f"\nDone! {len(result['nodes'])} total nodes")


if __name__ == "__main__":
    main()
