#!/usr/bin/env python3
"""Add content-based task dedup to Follow-up Cron workflow."""
import json
import os
import subprocess
import sys
import tempfile
import uuid

API_BASE = 'https://scottai.trackslife.com/api/v1'
WF_ID = 'JhDuCvZdFN4PFTOW'
SUPABASE_REST = 'https://rhrlnkbphxntxxxcrgvv.supabase.co'
SUPABASE_CRED_ID = 'ASRWWkQ0RSMOpNF1'

def api(method, path, body=None):
    args = ['curl', '-sS', '-X', method,
            '-H', f'X-N8N-API-KEY: {os.environ["N8N_KEY"]}',
            '-H', 'Content-Type: application/json',
            '-H', 'Accept: application/json',
            '-w', '\n__HTTP__%{http_code}']
    if body is not None:
        # Use a temp file to avoid shell escaping issues for large payloads
        tf = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        json.dump(body, tf)
        tf.close()
        args += ['--data-binary', f'@{tf.name}']
    args.append(f'{API_BASE}{path}')
    result = subprocess.run(args, capture_output=True, text=True)
    if body is not None:
        os.unlink(tf.name)
    out = result.stdout
    marker = '\n__HTTP__'
    idx = out.rfind(marker)
    code = int(out[idx + len(marker):].strip())
    body_text = out[:idx] if idx >= 0 else out
    if code >= 400:
        print(f'HTTP {code} on {method} {path}:\n{body_text[:800]}', file=sys.stderr)
        sys.exit(1)
    return json.loads(body_text or '{}')

# 1. Fetch live workflow
wf = api('GET', f'/workflows/{WF_ID}')
nodes = wf['nodes']
print(f'Fetched "{wf["name"]}" — {len(nodes)} nodes')

# 2. Modify Build Auto-Save Payload — add activity_uid to task context
for n in nodes:
    if n['name'] == 'Build Auto-Save Payload':
        code = n['parameters']['jsCode']
        old = """    meeting_subject: m.subject || '',
    assignee_name: t.owner || '',"""
        new = """    meeting_subject: m.subject || '',
    activity_uid: m.activityUid || '',
    assignee_name: t.owner || '',"""
        if old in code:
            n['parameters']['jsCode'] = code.replace(old, new)
            print('  ✓ Patched Build Auto-Save Payload')
        elif 'activity_uid: m.activityUid' in code:
            print('  (already patched) Build Auto-Save Payload')
        else:
            print('  ✗ Could not find insertion point in Build Auto-Save Payload')
            sys.exit(1)
        break

# 3. Positions
claim_pos = [4192, 496]
parse_pos = [4416, 496]
if_pos = [4640, 496]
send_tasks_new_pos = [4864, 496]

# 4. Move Send Tasks to CRM right
for n in nodes:
    if n['name'] == 'Send Tasks to CRM':
        n['position'] = send_tasks_new_pos
        break

# 5. Build new nodes
claim_node = {
    "parameters": {
        "method": "POST",
        "url": f"{SUPABASE_REST}/rest/v1/rpc/claim_task_slot",
        "authentication": "predefinedCredentialType",
        "nodeCredentialType": "supabaseApi",
        "sendHeaders": True,
        "headerParameters": {
            "parameters": [
                {"name": "Content-Type", "value": "application/json"},
                {"name": "Accept", "value": "application/json"},
            ]
        },
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify({\n  p_account: $json.webhook_payload.context.account_name || '',\n  p_assignee: $json.webhook_payload.context.assignee_email || $json.webhook_payload.context.user_email || '',\n  p_subject: $json.webhook_payload.fields.Subject || '',\n  p_activity_uid: $json.webhook_payload.context.activity_uid || ''\n}) }}",
        "options": {},
    },
    "id": str(uuid.uuid4()),
    "name": "Claim Task Slot",
    "type": "n8n-nodes-base.httpRequest",
    "typeVersion": 4.2,
    "position": claim_pos,
    "alwaysOutputData": True,
    "onError": "continueRegularOutput",
    "credentials": {
        "supabaseApi": {"id": SUPABASE_CRED_ID, "name": "Supabase account"}
    },
}

parse_node = {
    "parameters": {
        "jsCode": (
            "// Normalize PostgREST scalar response: true/false as raw JSON body.\n"
            "// n8n wraps this in different shapes depending on version.\n"
            "const item = $input.first();\n"
            "const body = item.json;\n"
            "let claimed = false;\n"
            "if (body === true) claimed = true;\n"
            "else if (typeof body === 'object' && body !== null) {\n"
            "  // Check common wrappers\n"
            "  if (body.claim_task_slot === true) claimed = true;\n"
            "  else if (Array.isArray(body) && body[0] === true) claimed = true;\n"
            "  else if (body.data === true) claimed = true;\n"
            "}\n"
            "// Pass the original webhook_payload through so Send Tasks to CRM still has it\n"
            "const payload = $('Prepare Task Payloads').all()[item.pairedItem?.item ?? 0]?.json?.webhook_payload;\n"
            "return [{ json: { claimed, webhook_payload: payload } }];"
        )
    },
    "id": str(uuid.uuid4()),
    "name": "Parse Claim Result",
    "type": "n8n-nodes-base.code",
    "typeVersion": 2,
    "position": parse_pos,
}

if_node = {
    "parameters": {
        "conditions": {
            "options": {
                "version": 2,
                "leftValue": "",
                "caseSensitive": True,
                "typeValidation": "strict",
            },
            "conditions": [
                {
                    "id": str(uuid.uuid4()),
                    "leftValue": "={{ $json.claimed }}",
                    "rightValue": True,
                    "operator": {"type": "boolean", "operation": "true", "singleValue": True},
                }
            ],
            "combinator": "and",
        },
        "options": {},
    },
    "id": str(uuid.uuid4()),
    "name": "Task Claimed?",
    "type": "n8n-nodes-base.if",
    "typeVersion": 2.2,
    "position": if_pos,
}

# 6. Remove any existing instances of the new nodes (idempotent re-run)
nodes = [n for n in nodes if n['name'] not in ('Claim Task Slot', 'Parse Claim Result', 'Task Claimed?')]
nodes.extend([claim_node, parse_node, if_node])
print(f'  ✓ Added 3 new nodes')

# 7. Update connections
conns = wf['connections']
# Prepare Task Payloads → Claim Task Slot (was → Send Tasks to CRM)
conns['Prepare Task Payloads'] = {'main': [[{'node': 'Claim Task Slot', 'type': 'main', 'index': 0}]]}
# Claim Task Slot → Parse Claim Result
conns['Claim Task Slot'] = {'main': [[{'node': 'Parse Claim Result', 'type': 'main', 'index': 0}]]}
# Parse Claim Result → Task Claimed?
conns['Parse Claim Result'] = {'main': [[{'node': 'Task Claimed?', 'type': 'main', 'index': 0}]]}
# Task Claimed? [true] → Send Tasks to CRM; [false] → nothing
conns['Task Claimed?'] = {'main': [
    [{'node': 'Send Tasks to CRM', 'type': 'main', 'index': 0}],  # true branch
    []  # false branch (skip)
]}
print('  ✓ Updated connections')

# 8. PUT workflow back (n8n requires specific fields only)
put_body = {
    'name': wf['name'],
    'nodes': nodes,
    'connections': conns,
    'settings': wf.get('settings', {}),
    'staticData': wf.get('staticData', None),
}
result = api('PUT', f'/workflows/{WF_ID}', put_body)
print(f'  ✓ Updated workflow (versionId={result.get("versionId")})')
print(f'\nLive workflow: {API_BASE.replace("/api/v1","")}/workflow/{WF_ID}')
