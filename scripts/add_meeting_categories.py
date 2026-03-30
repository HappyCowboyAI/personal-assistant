"""
Add AI-suggested meeting categories to the Meeting Recap → Save to Salesforce flow.

Modifies three workflows:
1. Follow-up Cron (JhDuCvZdFN4PFTOW): Build Recap Context, Parse Recap Output, Build Recap Card
2. Slack Events Handler (QuQbIaWetunUOFUW): Recap Build Context, Recap Parse Output OD, Recap Build Card OD
3. Interactive Events Handler (JgVjCqoT6ZwGuDL1): Parse Interactive Payload, Open Recap SF Modal, Build Edited Activity Payload
"""

from n8n_helpers import (
    find_node, modify_workflow,
    WF_FOLLOWUP_CRON, WF_EVENTS_HANDLER, WF_INTERACTIVE_HANDLER,
)

# ── Category instructions to inject into system prompts ──────────────

CATEGORY_JSON_FRAGMENT = ''',
  "cs_category": "best match from: Account & Renewal Management, Expansion & Upsell, Customer Training, Internal Deal Support (Legal/Fin/Sec), Product & Engineering Inquiry, Strategic Account & Territory Planning, Sales Operations & Coaching",
  "sales_category": "best match from: Prospecting & Qualification, Solution Presentation & Demo, Commercials & Negotiation, Technical Scoping & Solutioning, Onboarding & Implementation, Account & Renewal Management",
  "meeting_category": "best match from: Discovery Meeting, Demo Meeting, Proposal Meeting, Security Meeting, Procurement Meeting, Legal Meeting"
}'''

CATEGORY_INSTRUCTIONS = '''

Based on the meeting content, select the single best-matching value for each category field. Use the exact picklist value string. If none fit well, use null.'''

# ── Parse node category extraction snippet ───────────────────────────

PARSE_CATEGORY_FIELDS = """
    csCategory: recap.cs_category || null,
    salesCategory: recap.sales_category || null,
    meetingCategory: recap.meeting_category || null,"""

# ── Save payload category fields ─────────────────────────────────────

SAVE_PAYLOAD_CATEGORY_FIELDS = """  cs_category: recap.csCategory || '',
  sales_category: recap.salesCategory || '',
  meeting_category: recap.meetingCategory || '',"""


def patch_system_prompt(code):
    """Add category fields to the JSON schema in the system prompt."""
    # The JSON schema ends with "follow_up_context": "..." }
    # Replace the closing } with category fields
    old = '  "follow_up_context": "context to enrich a follow-up email"\n}'
    new = '  "follow_up_context": "context to enrich a follow-up email"' + CATEGORY_JSON_FRAGMENT
    if old not in code:
        raise ValueError(f"Could not find JSON schema closing in system prompt")
    code = code.replace(old, new)

    # Add category instructions after the RULES section
    old2 = '- Output ONLY the JSON object — no prose, no markdown fences`;'
    new2 = '- Output ONLY the JSON object — no prose, no markdown fences' + CATEGORY_INSTRUCTIONS + '`;'
    if old2 not in code:
        raise ValueError("Could not find RULES end marker for category instructions")
    code = code.replace(old2, new2)
    return code


def patch_parse_output(code):
    """Add category extraction to parse recap output node."""
    old = "    followUpContext: recap.follow_up_context || ''"
    new = "    followUpContext: recap.follow_up_context || ''," + PARSE_CATEGORY_FIELDS
    if old not in code:
        raise ValueError("Could not find followUpContext in parse output node")
    code = code.replace(old, new)
    return code


def patch_build_card(code, is_od=False):
    """Add category fields to the save payload in the card builder."""
    # Find the savePayload JSON.stringify block — add categories after sentiment
    old = "  sentiment: recap.sentiment,"
    new = "  sentiment: recap.sentiment,\n" + SAVE_PAYLOAD_CATEGORY_FIELDS
    if old not in code:
        raise ValueError("Could not find sentiment field in savePayload")
    code = code.replace(old, new)
    return code


# ── Workflow 1: Follow-up Cron ────────────────────────────────────────

def modify_followup_cron(nodes, connections):
    changes = 0

    # 1. Build Recap Context — patch system prompt
    node = find_node(nodes, "Build Recap Context")
    if not node:
        raise ValueError("Node 'Build Recap Context' not found")
    old_code = node["parameters"]["jsCode"]
    new_code = patch_system_prompt(old_code)
    if new_code != old_code:
        node["parameters"]["jsCode"] = new_code
        changes += 1
        print("  [1/3] Patched Build Recap Context system prompt")

    # 2. Parse Recap Output — extract categories
    node = find_node(nodes, "Parse Recap Output")
    if not node:
        raise ValueError("Node 'Parse Recap Output' not found")
    old_code = node["parameters"]["jsCode"]
    new_code = patch_parse_output(old_code)
    if new_code != old_code:
        node["parameters"]["jsCode"] = new_code
        changes += 1
        print("  [2/3] Patched Parse Recap Output category extraction")

    # 3. Build Recap Card — add categories to save payload
    node = find_node(nodes, "Build Recap Card")
    if not node:
        raise ValueError("Node 'Build Recap Card' not found")
    old_code = node["parameters"]["jsCode"]
    new_code = patch_build_card(old_code)
    if new_code != old_code:
        node["parameters"]["jsCode"] = new_code
        changes += 1
        print("  [3/3] Patched Build Recap Card save payload")

    return changes


# ── Workflow 2: Slack Events Handler ──────────────────────────────────

def modify_events_handler(nodes, connections):
    changes = 0

    # 1. Recap Build Context — patch system prompt (same structure)
    node = find_node(nodes, "Recap Build Context")
    if not node:
        raise ValueError("Node 'Recap Build Context' not found")
    old_code = node["parameters"]["jsCode"]
    new_code = patch_system_prompt(old_code)
    if new_code != old_code:
        node["parameters"]["jsCode"] = new_code
        changes += 1
        print("  [1/3] Patched Recap Build Context system prompt")

    # 2. Recap Parse Output OD — extract categories
    node = find_node(nodes, "Recap Parse Output OD")
    if not node:
        raise ValueError("Node 'Recap Parse Output OD' not found")
    old_code = node["parameters"]["jsCode"]
    new_code = patch_parse_output(old_code)
    if new_code != old_code:
        node["parameters"]["jsCode"] = new_code
        changes += 1
        print("  [2/3] Patched Recap Parse Output OD category extraction")

    # 3. Recap Build Card OD — add categories to save payload
    node = find_node(nodes, "Recap Build Card OD")
    if not node:
        raise ValueError("Node 'Recap Build Card OD' not found")
    old_code = node["parameters"]["jsCode"]
    new_code = patch_build_card(old_code, is_od=True)
    if new_code != old_code:
        node["parameters"]["jsCode"] = new_code
        changes += 1
        print("  [3/3] Patched Recap Build Card OD save payload")

    return changes


# ── Workflow 3: Interactive Events Handler ────────────────────────────

STATIC_SELECT_HANDLER = """    } else if (el.type === 'static_select') {
      submittedValues[aId] = el.selected_option ? el.selected_option.value : null;
    }"""


def modify_interactive_handler(nodes, connections):
    changes = 0

    # 1. Parse Interactive Payload — add static_select handling
    node = find_node(nodes, "Parse Interactive Payload")
    if not node:
        raise ValueError("Node 'Parse Interactive Payload' not found")
    old_code = node["parameters"]["jsCode"]
    if "static_select" not in old_code:
        # Insert after the radio_buttons handler
        old_radio = "    } else if (el.type === 'radio_buttons') {\n      submittedValues[aId] = el.selected_option ? el.selected_option.value : null;\n    }"
        new_radio = old_radio + "\n" + STATIC_SELECT_HANDLER
        if old_radio not in old_code:
            raise ValueError("Could not find radio_buttons handler in Parse Interactive Payload")
        node["parameters"]["jsCode"] = old_code.replace(old_radio, new_radio)
        changes += 1
        print("  [1/3] Patched Parse Interactive Payload for static_select")
    else:
        print("  [1/3] Parse Interactive Payload already handles static_select")

    # 2. Open Recap SF Modal — add category dropdowns + store in metadata
    node = find_node(nodes, "Open Recap SF Modal")
    if not node:
        raise ValueError("Node 'Open Recap SF Modal' not found")
    old_code = node["parameters"]["jsCode"]
    if "cs_category" not in old_code:
        # Add category fields to privateMetadata
        old_meta = "  assistant_emoji: context.assistant_emoji || ':robot_face:',\n});"
        new_meta = """  assistant_emoji: context.assistant_emoji || ':robot_face:',
  cs_category: context.cs_category || '',
  sales_category: context.sales_category || '',
  meeting_category: context.meeting_category || '',
});"""
        if old_meta not in old_code:
            raise ValueError("Could not find privateMetadata closing in Open Recap SF Modal")
        old_code = old_code.replace(old_meta, new_meta)

        # Add category dropdown blocks after tasks_block
        category_blocks = """
      // ── AI-suggested category dropdowns ──
      {
        type: "divider"
      },
      {
        type: "section",
        text: { type: "mrkdwn", text: "*:brain: AI-Suggested Categories*" }
      },
      ...(function() {
        const csOpts = [
          "Account & Renewal Management",
          "Expansion & Upsell",
          "Customer Training",
          "Internal Deal Support (Legal/Fin/Sec)",
          "Product & Engineering Inquiry",
          "Strategic Account & Territory Planning",
          "Sales Operations & Coaching"
        ].map(v => ({ text: { type: "plain_text", text: v }, value: v }));

        const salesOpts = [
          "DID NOT HAPPEN",
          "Prospecting & Qualification",
          "Solution Presentation & Demo",
          "Commercials & Negotiation",
          "Technical Scoping & Solutioning",
          "Onboarding & Implementation",
          "Account & Renewal Management"
        ].map(v => ({ text: { type: "plain_text", text: v }, value: v }));

        const meetOpts = [
          "Discovery Meeting",
          "Demo Meeting",
          "Proposal Meeting",
          "Security Meeting",
          "Procurement Meeting",
          "Legal Meeting"
        ].map(v => ({ text: { type: "plain_text", text: v }, value: v }));

        const blocks = [];

        const csBlock = {
          type: "input",
          block_id: "cs_category_block",
          label: { type: "plain_text", text: "CS Category" },
          element: {
            type: "static_select",
            action_id: "cs_category_value",
            placeholder: { type: "plain_text", text: "Select CS Category" },
            options: csOpts,
          },
          optional: true
        };
        if (context.cs_category && csOpts.some(o => o.value === context.cs_category)) {
          csBlock.element.initial_option = { text: { type: "plain_text", text: context.cs_category }, value: context.cs_category };
        }
        blocks.push(csBlock);

        const salesBlock = {
          type: "input",
          block_id: "sales_category_block",
          label: { type: "plain_text", text: "Category (Sales)" },
          element: {
            type: "static_select",
            action_id: "sales_category_value",
            placeholder: { type: "plain_text", text: "Select Sales Category" },
            options: salesOpts,
          },
          optional: true
        };
        if (context.sales_category && salesOpts.some(o => o.value === context.sales_category)) {
          salesBlock.element.initial_option = { text: { type: "plain_text", text: context.sales_category }, value: context.sales_category };
        }
        blocks.push(salesBlock);

        const meetBlock = {
          type: "input",
          block_id: "meeting_category_block",
          label: { type: "plain_text", text: "Category (Meeting Type)" },
          element: {
            type: "static_select",
            action_id: "meeting_category_value",
            placeholder: { type: "plain_text", text: "Select Meeting Type" },
            options: meetOpts,
          },
          optional: true
        };
        if (context.meeting_category && meetOpts.some(o => o.value === context.meeting_category)) {
          meetBlock.element.initial_option = { text: { type: "plain_text", text: context.meeting_category }, value: context.meeting_category };
        }
        blocks.push(meetBlock);

        return blocks;
      })(),"""

        old_blocks_end = """      {
        type: "input",
        block_id: "tasks_block",
        label: { type: "plain_text", text: "Action Items" },
        element: {
          type: "plain_text_input",
          action_id: "tasks_value",
          multiline: true,
          initial_value: tasks
        },
        optional: true
      }
    ]"""
        new_blocks_end = """      {
        type: "input",
        block_id: "tasks_block",
        label: { type: "plain_text", text: "Action Items" },
        element: {
          type: "plain_text_input",
          action_id: "tasks_value",
          multiline: true,
          initial_value: tasks
        },
        optional: true
      },""" + category_blocks + """
    ]"""

        if old_blocks_end not in old_code:
            raise ValueError("Could not find tasks_block closing in Open Recap SF Modal")
        old_code = old_code.replace(old_blocks_end, new_blocks_end)
        node["parameters"]["jsCode"] = old_code
        changes += 1
        print("  [2/3] Patched Open Recap SF Modal with category dropdowns")
    else:
        print("  [2/3] Open Recap SF Modal already has categories")

    # 3. Build Edited Activity Payload — extract categories and add to webhook payload
    node = find_node(nodes, "Build Edited Activity Payload")
    if not node:
        raise ValueError("Node 'Build Edited Activity Payload' not found")
    old_code = node["parameters"]["jsCode"]
    if "cs_category" not in old_code:
        # Add category extraction after tasks extraction
        old_tasks = "const tasks = vals.tasks_value || '';"
        new_tasks = """const tasks = vals.tasks_value || '';
const csCategory = vals.cs_category_value || meta.cs_category || '';
const salesCategory = vals.sales_category_value || meta.sales_category || '';
const meetingCategory = vals.meeting_category_value || meta.meeting_category || '';"""
        if old_tasks not in old_code:
            raise ValueError("Could not find tasks extraction in Build Edited Activity Payload")
        old_code = old_code.replace(old_tasks, new_tasks)

        # Add categories to fields
        old_fields = """    fields: {
      Subject: meta.meeting_subject || 'Customer Meeting',
      Description: description,
      ActivityDate: new Date().toLocaleDateString('en-CA', { timeZone: 'America/Los_Angeles' }),
    },"""
        new_fields = """    fields: {
      Subject: meta.meeting_subject || 'Customer Meeting',
      Description: description,
      ActivityDate: new Date().toLocaleDateString('en-CA', { timeZone: 'America/Los_Angeles' }),
      cs_category: csCategory,
      sales_category: salesCategory,
      meeting_category: meetingCategory,
    },"""
        if old_fields not in old_code:
            raise ValueError("Could not find fields in Build Edited Activity Payload")
        old_code = old_code.replace(old_fields, new_fields)
        node["parameters"]["jsCode"] = old_code
        changes += 1
        print("  [3/3] Patched Build Edited Activity Payload with categories")
    else:
        print("  [3/3] Build Edited Activity Payload already has categories")

    return changes


# ── Main ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Adding meeting categories to Recap → Save to SF flow")
    print("=" * 60)

    print("\n── Workflow 1: Follow-up Cron ──")
    modify_workflow(WF_FOLLOWUP_CRON, "Follow-up Cron.json", modify_followup_cron)

    print("\n── Workflow 2: Slack Events Handler ──")
    modify_workflow(WF_EVENTS_HANDLER, "Slack Events Handler.json", modify_events_handler)

    print("\n── Workflow 3: Interactive Events Handler ──")
    modify_workflow(WF_INTERACTIVE_HANDLER, "Interactive Events Handler.json", modify_interactive_handler)

    print("\n" + "=" * 60)
    print("All three workflows updated successfully!")
    print("=" * 60)
