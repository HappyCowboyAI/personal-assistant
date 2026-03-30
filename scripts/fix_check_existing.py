"""
Fix: Check Existing Announce node URL expression not evaluating.

The URL has {{ $json.dbUserId }} but n8n needs ={{ expr }} format
for expression evaluation in URL parameters.

Usage:
    N8N_API_KEY=... python scripts/fix_check_existing.py
"""

from n8n_helpers import find_node, modify_workflow, WF_EVENTS_HANDLER, SUPABASE_URL


def modifier(nodes, connections):
    changes = 0

    # Fix Check Existing Announce — needs ={{ }} not {{ }}
    node = find_node(nodes, "Check Existing Announce")
    if node:
        old_url = node["parameters"]["url"]
        print(f"  Old URL: {old_url}")
        # The make_supabase_http_node builds the URL as SUPABASE_URL/rest/v1/<path>
        # The path has {{ $json.dbUserId }} but needs ={{ $json.dbUserId }}
        # Actually, n8n expressions in URL fields need the whole URL to be an expression
        # Let's use the expression format
        new_url = f"={SUPABASE_URL}/rest/v1/pending_actions?action_type=eq.announcement_broadcast&status=eq.pending&user_id=eq.{{{{ $json.dbUserId }}}}"
        node["parameters"]["url"] = new_url
        print(f"  New URL: {new_url}")
        changes += 1

    # Also fix Check Pending Action — same issue
    node2 = find_node(nodes, "Check Pending Action")
    if node2:
        old_url = node2["parameters"]["url"]
        print(f"  Old Check Pending URL: {old_url}")
        new_url = f"={SUPABASE_URL}/rest/v1/pending_actions?action_type=eq.announcement_broadcast&status=eq.pending&user_id=eq.{{{{ $('Lookup User').first().json.id }}}}"
        node2["parameters"]["url"] = new_url
        print(f"  New Check Pending URL: {new_url}")
        changes += 1

    # Fix Mark Approved, Mark Rejected, Mark Expired — same pattern
    for name in ["Mark Approved", "Mark Rejected", "Mark Expired"]:
        node = find_node(nodes, name)
        if node:
            old_url = node["parameters"]["url"]
            print(f"  Old {name} URL: {old_url}")
            new_url = f"={SUPABASE_URL}/rest/v1/pending_actions?id=eq.{{{{ $json.pendingActionId }}}}"
            node["parameters"]["url"] = new_url
            print(f"  New {name} URL: {new_url}")
            changes += 1

    # Fix Store Pending Action — POST doesn't need URL expressions but let's verify
    node = find_node(nodes, "Store Pending Action")
    if node:
        print(f"  Store Pending Action URL: {node['parameters']['url']} (should be fine)")

    return changes


if __name__ == "__main__":
    result = modify_workflow(
        WF_EVENTS_HANDLER,
        "Slack Events Handler.json",
        modifier,
    )
    print(f"\nDone! {len(result['nodes'])} total nodes")
