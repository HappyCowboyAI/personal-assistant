#!/usr/bin/env python3
"""
Add feature usage tracking to 3 workflows.

Inserts Supabase RPC tracking nodes (HTTP POST to `track_feature_usage`) into:

1. Events Handler — DM Conversation tracking
   After "DM Post Answer", before "Prepare DM Conv Data":
     DM Post Answer → Track DM Conv Usage → Prepare DM Conv Data → ...

2. Events Handler — Meeting Brief tracking
   After "Execute On-Demand Digest" (terminal node on brief path):
     Execute On-Demand Digest → Track Brief Usage

3. Backstory SlackBot — Backstory tracking
   After "Update Original Message" and "DM Post Answer1", before "Prepare Conversation Data":
     Update Original Message  ─┐
     DM Post Answer1          ─┴→ Track Backstory Usage → Prepare Conversation Data → ...

Each tracking node:
  - POSTs to Supabase RPC `track_feature_usage(p_user_id, p_feature_id)`
  - Uses `continueOnFail: True` so tracking never breaks the main flow
  - Is inserted inline in the connection chain
"""

from n8n_helpers import (
    uid,
    find_node,
    modify_workflow,
    WF_EVENTS_HANDLER,
    WF_BACKSTORY,
    SUPABASE_URL,
    SUPABASE_CRED,
    NODE_HTTP_REQUEST,
)


# ── Tracking Node Factory ────────────────────────────────────────────


def make_tracking_node(name, feature_id, user_id_expr, position):
    """Create a Supabase RPC tracking node for feature usage."""
    return {
        "parameters": {
            "method": "POST",
            "url": f"{SUPABASE_URL}/rest/v1/rpc/track_feature_usage",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "supabaseApi",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Content-Type", "value": "application/json"},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": (
                f'={{{{ JSON.stringify({{ p_user_id: {user_id_expr},'
                f' p_feature_id: "{feature_id}" }}) }}}}'
            ),
            "options": {},
        },
        "id": uid(),
        "name": name,
        "type": NODE_HTTP_REQUEST,
        "typeVersion": 4.2,
        "position": position,
        "credentials": {"supabaseApi": SUPABASE_CRED},
        "continueOnFail": True,
    }


# ── Connection Helpers ────────────────────────────────────────────────


def rewire_connection(connections, source_name, source_output_index,
                      old_target_name, new_target_name):
    """
    In `connections[source_name]["main"][source_output_index]`, replace
    occurrences of old_target_name with new_target_name.
    Returns True if a replacement was made.
    """
    main = connections.get(source_name, {}).get("main", [])
    if source_output_index >= len(main):
        return False

    targets = main[source_output_index]
    replaced = False
    for t in targets:
        if t["node"] == old_target_name:
            t["node"] = new_target_name
            replaced = True
    return replaced


def add_connection(connections, source_name, target_name,
                   source_output_index=0, target_type="main", target_index=0):
    """
    Add a connection: source_name --[main:source_output_index]--> target_name.
    Creates intermediate dicts/lists as needed.
    """
    if source_name not in connections:
        connections[source_name] = {}
    if "main" not in connections[source_name]:
        connections[source_name]["main"] = []

    main = connections[source_name]["main"]
    # Extend list if needed
    while len(main) <= source_output_index:
        main.append([])

    main[source_output_index].append({
        "node": target_name,
        "type": target_type,
        "index": target_index,
    })


# ── Events Handler Modifier ──────────────────────────────────────────


def modify_events_handler(nodes, connections):
    changes = 0

    # ── Guard: already applied? ───────────────────────────────────
    node_names = [n["name"] for n in nodes]
    if "Track DM Conv Usage" in node_names:
        print("  Guard: 'Track DM Conv Usage' already exists — skipping DM conv tracking")
    else:
        changes += add_dm_conv_tracking(nodes, connections)

    if "Track Brief Usage" in node_names:
        print("  Guard: 'Track Brief Usage' already exists — skipping brief tracking")
    else:
        changes += add_brief_tracking(nodes, connections)

    return changes


def add_dm_conv_tracking(nodes, connections):
    """
    Insert tracking inline between DM Post Answer and Prepare DM Conv Data.

    Before: DM Post Answer → Prepare DM Conv Data
    After:  DM Post Answer → Track DM Conv Usage → Prepare DM Conv Data
    """
    dm_post_answer = find_node(nodes, "DM Post Answer")
    prepare_dm = find_node(nodes, "Prepare DM Conv Data")
    if not dm_post_answer or not prepare_dm:
        print("  ERROR: Could not find 'DM Post Answer' or 'Prepare DM Conv Data'")
        return 0

    # Position: between DM Post Answer [3568, 4400] and Prepare DM Conv Data [3792, 4400]
    # Shift Prepare DM Conv Data and all downstream nodes right by 250
    dm_downstream = [
        "Prepare DM Conv Data", "Create DM Conversation",
        "Log DM User Msg", "Log DM Assistant Msg",
    ]
    for name in dm_downstream:
        n = find_node(nodes, name)
        if n:
            n["position"][0] += 250

    tracking_pos = [3680, 4400]  # Between DM Post Answer and shifted Prepare DM Conv Data

    # User ID expression: Route by State outputs dbUserId, which flows through
    # Build DM System Prompt as dbUserId
    user_id_expr = '$("Build DM System Prompt").first().json.dbUserId'

    tracking_node = make_tracking_node(
        name="Track DM Conv Usage",
        feature_id="dm_conversation",
        user_id_expr=user_id_expr,
        position=tracking_pos,
    )
    nodes.append(tracking_node)

    # Rewire: DM Post Answer → Track DM Conv Usage (instead of Prepare DM Conv Data)
    rewire_connection(connections, "DM Post Answer", 0,
                      "Prepare DM Conv Data", "Track DM Conv Usage")

    # Wire: Track DM Conv Usage → Prepare DM Conv Data
    add_connection(connections, "Track DM Conv Usage", "Prepare DM Conv Data")

    print("  Added 'Track DM Conv Usage' between DM Post Answer and Prepare DM Conv Data")
    return 1


def add_brief_tracking(nodes, connections):
    """
    Add tracking after Execute On-Demand Digest (terminal node on brief path).

    Before: Execute On-Demand Digest (terminal)
    After:  Execute On-Demand Digest → Track Brief Usage (terminal)
    """
    exec_digest = find_node(nodes, "Execute On-Demand Digest")
    if not exec_digest:
        print("  ERROR: Could not find 'Execute On-Demand Digest'")
        return 0

    # Position: to the right of Execute On-Demand Digest [3344, 2592]
    tracking_pos = [3594, 2592]

    # User ID: Parse Brief passes through Route by State data which includes dbUserId
    # Prepare Digest Input references $('Parse Brief').first().json.dbUserId
    # We can do the same from the tracking node.
    user_id_expr = '$("Route by State").first().json.dbUserId'

    tracking_node = make_tracking_node(
        name="Track Brief Usage",
        feature_id="meeting_brief",
        user_id_expr=user_id_expr,
        position=tracking_pos,
    )
    nodes.append(tracking_node)

    # Wire: Execute On-Demand Digest → Track Brief Usage
    add_connection(connections, "Execute On-Demand Digest", "Track Brief Usage")

    print("  Added 'Track Brief Usage' after Execute On-Demand Digest")
    return 1


# ── Backstory SlackBot Modifier ───────────────────────────────────────


def modify_backstory(nodes, connections):
    changes = 0

    node_names = [n["name"] for n in nodes]
    if "Track Backstory Usage" in node_names:
        print("  Guard: 'Track Backstory Usage' already exists — skipping")
        return 0

    # The Backstory workflow has two paths that converge at Prepare Conversation Data:
    #   Channel: Update Original Message → Prepare Conversation Data
    #   DM:      DM Post Answer1         → Prepare Conversation Data
    #
    # Insert tracking node inline:
    #   Update Original Message  ─┐
    #   DM Post Answer1          ─┴→ Track Backstory Usage → Prepare Conversation Data

    update_orig = find_node(nodes, "Update Original Message")
    dm_answer = find_node(nodes, "DM Post Answer1")
    prepare_conv = find_node(nodes, "Prepare Conversation Data")
    if not update_orig or not dm_answer or not prepare_conv:
        print("  ERROR: Could not find required nodes in Backstory workflow")
        return 0

    # Shift Prepare Conversation Data and downstream nodes right by 250
    backstory_downstream = [
        "Prepare Conversation Data", "Create Conversation",
        "Log User Message", "Log Assistant Message",
    ]
    for name in backstory_downstream:
        n = find_node(nodes, name)
        if n:
            n["position"][0] += 250

    # Position: where Prepare Conversation Data used to be [5056, 2108]
    tracking_pos = [5056, 2108]

    # User ID: Lookup User returns the Supabase row, which has `id` as the UUID.
    # Resolve Assistant Identity stores it as `dbUserId`.
    user_id_expr = '$("Resolve Assistant Identity").first().json.dbUserId'

    tracking_node = make_tracking_node(
        name="Track Backstory Usage",
        feature_id="backstory",
        user_id_expr=user_id_expr,
        position=tracking_pos,
    )
    nodes.append(tracking_node)

    # Rewire both paths: replace Prepare Conversation Data with Track Backstory Usage
    rewire_connection(connections, "Update Original Message", 0,
                      "Prepare Conversation Data", "Track Backstory Usage")
    rewire_connection(connections, "DM Post Answer1", 0,
                      "Prepare Conversation Data", "Track Backstory Usage")

    # Wire: Track Backstory Usage → Prepare Conversation Data
    add_connection(connections, "Track Backstory Usage", "Prepare Conversation Data")

    print("  Added 'Track Backstory Usage' before Prepare Conversation Data")
    changes += 1

    return changes


# ── Main ──────────────────────────────────────────────────────────────


def main():
    print("=" * 60)
    print("Adding feature usage tracking to workflows")
    print("=" * 60)

    print("\n--- Events Handler (DM Conv + Brief tracking) ---")
    modify_workflow(
        WF_EVENTS_HANDLER,
        "Slack Events Handler.json",
        modify_events_handler,
    )

    print("\n--- Backstory SlackBot (Backstory tracking) ---")
    modify_workflow(
        WF_BACKSTORY,
        "Backstory SlackBot.json",
        modify_backstory,
    )

    print("\nDone.")


if __name__ == "__main__":
    main()
