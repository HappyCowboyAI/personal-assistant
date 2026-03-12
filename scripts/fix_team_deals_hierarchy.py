#!/usr/bin/env python3
"""
Fix: Sales Digest team_deals showing zero pipeline

Root cause: ootb_user_manager field returns empty strings for all users,
so managerToReports map is empty, so team_deals scope finds no reports.

Fixes:
1. Add ootb_user_manager_email column to Fetch User Hierarchy request
2. Update Parse Hierarchy to key managerToReports by manager EMAIL (not name)
   - The existing `managerToReports[userEmail]` fallback in Filter User Opps
     then works correctly when manager email is available
3. Update Filter User Opps to handle missing hierarchy gracefully:
   - If no reports found via hierarchy, use all opps sorted by close date (top 25)
   - Logs a warning in the digest prompt so it's visible
"""

import json
import os
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

SALES_DIGEST_ID = "7sinwSgjkEA40zDj"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}


def fetch_workflow(workflow_id):
    resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{workflow_id}", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def push_workflow(workflow_id, wf):
    payload = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": wf.get("settings", {}),
        "staticData": wf.get("staticData"),
    }
    resp = requests.put(
        f"{N8N_BASE_URL}/api/v1/workflows/{workflow_id}",
        headers=HEADERS,
        json=payload,
    )
    if not resp.ok:
        print(f"ERROR {resp.status_code}: {resp.text[:500]}")
        resp.raise_for_status()
    return resp.json()


def find_node(nodes, name_substr):
    for n in nodes:
        if name_substr.lower() in n["name"].lower():
            return n
    return None


# ─────────────────────────────────────────────────────────────
# New code for Parse Hierarchy
# Keys managerToReports by manager EMAIL (not name)
# Also retains name-based keying as a secondary index
# ─────────────────────────────────────────────────────────────
PARSE_HIERARCHY_CODE = r"""// Parse CSV from People.ai User hierarchy export
const csvData = $('Fetch User Hierarchy').first().json.data;

if (!csvData) {
  return [{ json: { hierarchy: {}, managerToReports: {}, userCount: 0, error: 'No hierarchy data returned' } }];
}

const lines = csvData.split('\n').filter(l => l.trim());
if (lines.length < 2) {
  return [{ json: { hierarchy: {}, managerToReports: {}, userCount: 0, error: 'Hierarchy CSV has no data rows' } }];
}

function parseCsvLine(line) {
  const result = [];
  let current = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (inQuotes && i + 1 < line.length && line[i + 1] === '"') {
        current += '"';
        i++;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (ch === ',' && !inQuotes) {
      result.push(current.trim());
      current = '';
    } else {
      current += ch;
    }
  }
  result.push(current.trim());
  return result;
}

const headers = parseCsvLine(lines[0]);
const headerMap = {};
headers.forEach((h, i) => { headerMap[h] = i; });

function getField(row, ...names) {
  for (const name of names) {
    if (headerMap[name] !== undefined && row[headerMap[name]]) {
      return row[headerMap[name]];
    }
  }
  return '';
}

const hierarchy = {};
const managerToReports = {};

function addReport(key, report) {
  if (!key) return;
  const k = key.toLowerCase().trim();
  if (!k) return;
  if (!managerToReports[k]) managerToReports[k] = [];
  // Avoid duplicates
  if (!managerToReports[k].some(r => r.email === report.email)) {
    managerToReports[k].push(report);
  }
}

for (let i = 1; i < lines.length; i++) {
  const row = parseCsvLine(lines[i]);
  if (row.length < headers.length) continue;

  const name  = getField(row, 'ootb_user_name', 'User Name', 'Name');
  const email = getField(row, 'ootb_user_email', 'User Email', 'Email').toLowerCase().trim();
  const manager      = getField(row, 'ootb_user_manager', 'Manager', 'User Manager');
  const managerEmail = getField(row, 'ootb_user_manager_email', 'Manager Email', 'User Manager Email').toLowerCase().trim();

  if (email) {
    hierarchy[email] = { name, email, manager, managerEmail };
  }

  // Key by manager email (preferred — exact match, no fuzzy needed)
  if (managerEmail) {
    addReport(managerEmail, { name, email });
  }
  // Key by manager name (fallback for when email isn't available)
  if (manager) {
    addReport(manager, { name, email });
  }
}

return [{ json: { hierarchy, managerToReports, userCount: Object.keys(hierarchy).length } }];
"""

# ─────────────────────────────────────────────────────────────
# Updated Filter User Opps — team_deals section only
# Full replacement of the node's JS code
# ─────────────────────────────────────────────────────────────
FILTER_USER_OPPS_CODE = r"""// Filter opportunities for this user based on digest_scope and daily theme
const user         = $input.first().json;
const allOpps      = $('Parse Opps CSV').first().json.opps || [];
const hierarchyData = $('Parse Hierarchy').first().json;

const userEmail  = (user.email || '').toLowerCase().trim();
const digestScope = user.digest_scope || 'my_deals';

// Derive rep name from email (fallback)
const emailLocal = userEmail.split('@')[0] || '';
const repName    = emailLocal.split('.').map(p => p.charAt(0).toUpperCase() + p.slice(1)).join(' ');
const repLower   = repName.toLowerCase();

// Quarter/date helpers
const now = new Date();
const curYear = now.getFullYear();
const curMonth = now.getMonth(); // 0-indexed

function getQuarterEnd(monthsAhead) {
  const target = new Date(now);
  target.setMonth(target.getMonth() + monthsAhead);
  const m = target.getMonth();
  const q = Math.floor(m / 3);
  const qEndMonth = (q + 1) * 3 - 1; // last month of quarter
  const qEndYear  = target.getFullYear();
  return new Date(qEndYear, qEndMonth + 1, 0); // last day of that month
}

const fiscalYearEnd = new Date(curYear, 11, 31);
const twoQtrEnd     = getQuarterEnd(6);

function parseCloseDate(str) {
  if (!str) return null;
  const d = new Date(str);
  return isNaN(d.getTime()) ? null : d;
}

function isBefore(d, cutoff) {
  return d && d <= cutoff;
}

// Daily theme (Monday=1 ... Friday=5)
const dayOfWeek = now.getDay();
const themes = {
  1: 'full_pipeline',
  2: 'engagement_shifts',
  3: 'at_risk',
  4: 'momentum',
  5: 'week_review'
};
const theme = themes[dayOfWeek] || 'full_pipeline';

// ── Scope filtering ──────────────────────────────────────────

let userOpps = [];
let scopeLabel = '';
let hierarchyMissing = false;

if (digestScope === 'my_deals') {
  // IC: own deals within fiscal year
  userOpps = allOpps.filter(opp => {
    const owners = (opp.owners || opp.ownerName || opp.owner || '').toLowerCase();
    if (!owners.includes(repLower)) return false;
    const cd = parseCloseDate(opp.closeDate || opp['Close Date'] || opp.close_date);
    return !cd || isBefore(cd, fiscalYearEnd);
  });
  scopeLabel = `${repName}'s Deals`;

} else if (digestScope === 'team_deals') {
  const managerToReports = hierarchyData.managerToReports || {};

  // Collect direct reports — try email key first (most reliable), then name key
  const reportSet = new Map(); // email → {name, email}

  // 1. Direct lookup by manager email (preferred)
  const byEmail = managerToReports[userEmail] || [];
  for (const r of byEmail) {
    if (r.email) reportSet.set(r.email, r);
  }

  // 2. Fuzzy lookup by manager name (fallback)
  for (const [mgrKey, reports] of Object.entries(managerToReports)) {
    if (mgrKey === userEmail) continue; // already handled
    if (mgrKey.includes(repLower) || repLower.includes(mgrKey)) {
      for (const r of reports) {
        if (r.email && !reportSet.has(r.email)) reportSet.set(r.email, r);
      }
    }
  }

  // 3. Infer from hierarchy: find users whose managerEmail === userEmail
  const hierarchyMap = hierarchyData.hierarchy || {};
  for (const [email, info] of Object.entries(hierarchyMap)) {
    const mgrEmail = (info.managerEmail || '').toLowerCase().trim();
    if (mgrEmail === userEmail && !reportSet.has(email)) {
      reportSet.set(email, { name: info.name, email });
    }
  }

  const reportEntries = Array.from(reportSet.values());
  const reportNames   = reportEntries.map(r => (r.name || '').toLowerCase()).filter(Boolean);
  const reportEmails  = reportEntries.map(r => (r.email || '').toLowerCase()).filter(Boolean);

  if (reportEntries.length > 0) {
    // Filter opps by direct report owners
    userOpps = allOpps.filter(opp => {
      const owners     = (opp.owners || opp.ownerName || opp.owner || '').toLowerCase();
      const ownerEmail = (opp.ownerEmail || opp.owner_email || '').toLowerCase();
      const cd = parseCloseDate(opp.closeDate || opp['Close Date'] || opp.close_date);
      if (!isBefore(cd, twoQtrEnd)) return false;
      // Match by email first, then by name
      if (ownerEmail && reportEmails.some(e => ownerEmail.includes(e) || e.includes(ownerEmail))) return true;
      return reportNames.some(n => n && owners.includes(n));
    });
    scopeLabel = `${repName}'s Team Pipeline`;
  } else {
    // Hierarchy unavailable — fall back to top pipeline (all opps, sorted by amount)
    hierarchyMissing = true;
    userOpps = allOpps
      .filter(opp => {
        const cd = parseCloseDate(opp.closeDate || opp['Close Date'] || opp.close_date);
        return isBefore(cd, twoQtrEnd);
      })
      .sort((a, b) => {
        const amtA = parseFloat(String(a.amount || a.Amount || 0).replace(/[$,]/g, '')) || 0;
        const amtB = parseFloat(String(b.amount || b.Amount || 0).replace(/[$,]/g, '')) || 0;
        return amtB - amtA;
      })
      .slice(0, 25);
    scopeLabel = 'Top Pipeline (hierarchy unavailable)';
  }

} else if (digestScope === 'top_pipeline') {
  // Exec: top 25 deals by amount within 2 quarters
  userOpps = allOpps
    .filter(opp => {
      const cd = parseCloseDate(opp.closeDate || opp['Close Date'] || opp.close_date);
      return isBefore(cd, twoQtrEnd);
    })
    .sort((a, b) => {
      const amtA = parseFloat(String(a.amount || a.Amount || 0).replace(/[$,]/g, '')) || 0;
      const amtB = parseFloat(String(b.amount || b.Amount || 0).replace(/[$,]/g, '')) || 0;
      return amtB - amtA;
    })
    .slice(0, 25);
  scopeLabel = 'Top Pipeline';

} else if (digestScope && digestScope.startsWith('person:')) {
  // Custom: specific person's deals
  const targetEmail = digestScope.replace('person:', '').toLowerCase().trim();
  const targetLocal = targetEmail.split('@')[0] || '';
  const targetName  = targetLocal.split('.').map(p => p.charAt(0).toUpperCase() + p.slice(1)).join(' ').toLowerCase();
  userOpps = allOpps.filter(opp => {
    const owners     = (opp.owners || opp.ownerName || opp.owner || '').toLowerCase();
    const ownerEmail = (opp.ownerEmail || opp.owner_email || '').toLowerCase();
    const cd = parseCloseDate(opp.closeDate || opp['Close Date'] || opp.close_date);
    if (!isBefore(cd, fiscalYearEnd)) return false;
    if (ownerEmail && ownerEmail.includes(targetEmail)) return true;
    return owners.includes(targetName);
  });
  scopeLabel = `${targetEmail}'s Deals`;

} else {
  // Default fallback: my_deals
  userOpps = allOpps.filter(opp => {
    const owners = (opp.owners || opp.ownerName || opp.owner || '').toLowerCase();
    return owners.includes(repLower);
  });
  scopeLabel = `${repName}'s Deals`;
}

// ── Theme filtering ──────────────────────────────────────────

let themeNote = '';

if (theme === 'at_risk') {
  const RISK_STAGES = ['discovery', 'qualification', 'needs analysis', 'value proposition'];
  const soonMs = 30 * 24 * 60 * 60 * 1000;
  userOpps = userOpps.filter(opp => {
    const score = parseFloat(opp.engagementScore || opp.engagement_score || opp.score || 100);
    const cd    = parseCloseDate(opp.closeDate || opp['Close Date'] || opp.close_date);
    const stage = (opp.stage || opp.Stage || '').toLowerCase();
    const closingSoon = cd && (cd - now) < soonMs;
    const earlyStage  = RISK_STAGES.some(s => stage.includes(s));
    return score < 40 || (closingSoon && earlyStage);
  });
  themeNote = 'Focused on at-risk deals (low engagement or closing soon in early stage)';
} else if (theme === 'momentum') {
  userOpps = [...userOpps].sort((a, b) => {
    const sA = parseFloat(a.engagementScore || a.engagement_score || a.score || 0);
    const sB = parseFloat(b.engagementScore || b.engagement_score || b.score || 0);
    return sB - sA;
  });
  themeNote = 'Sorted by engagement momentum (highest first)';
}

// ── Build opp table ──────────────────────────────────────────

function fmt(opp) {
  const name   = opp.name || opp.Name || opp.opportunityName || 'Unknown';
  const amount = opp.amount || opp.Amount || '';
  const stage  = opp.stage || opp.Stage || '';
  const close  = opp.closeDate || opp['Close Date'] || opp.close_date || '';
  const owner  = opp.owners || opp.ownerName || opp.owner || '';
  const score  = opp.engagementScore || opp.engagement_score || opp.score || '';
  return `| ${name} | ${amount} | ${stage} | ${close} | ${owner} | ${score} |`;
}

let oppTable = '';
if (userOpps.length > 0) {
  const header = '| Deal | Amount | Stage | Close Date | Owner | Engagement |\n|------|--------|-------|------------|-------|------------|';
  oppTable = header + '\n' + userOpps.slice(0, 30).map(fmt).join('\n');
} else {
  oppTable = '(no deals matched the current filter)';
}

// Hierarchy warning for debugging
const hierarchyWarning = hierarchyMissing
  ? '\n\n⚠️ Note: Manager hierarchy data was not available in the export — showing top pipeline as fallback.'
  : '';

return [{
  json: {
    userOpps,
    scopeLabel,
    themeNote,
    oppTable: oppTable + hierarchyWarning,
    digestScope,
    theme,
    userEmail,
    repName,
    totalOppCount: allOpps.length,
    reportCount: digestScope === 'team_deals' ? (userOpps.length) : undefined,
    hierarchyMissing: hierarchyMissing || undefined,
  }
}];
"""


def fix_sales_digest():
    print("Fetching Sales Digest workflow...")
    wf = fetch_workflow(SALES_DIGEST_ID)
    nodes = wf["nodes"]

    # ── Fix 1: Fetch User Hierarchy — add ootb_user_manager_email column ──
    fetch_node = find_node(nodes, "Fetch User Hierarchy")
    if fetch_node:
        body_str = fetch_node["parameters"].get("jsonBody", "{}")
        try:
            body = json.loads(body_str)
        except json.JSONDecodeError:
            body = {"object": "user", "columns": []}

        cols = body.get("columns", [])
        existing_slugs = [c.get("slug") for c in cols]

        if "ootb_user_manager_email" not in existing_slugs:
            cols.append({"slug": "ootb_user_manager_email"})
            body["columns"] = cols
            fetch_node["parameters"]["jsonBody"] = json.dumps(body)
            print(f"  ✓ Added ootb_user_manager_email to Fetch User Hierarchy")
        else:
            print(f"  ✓ ootb_user_manager_email already present")
    else:
        print("  ✗ Could not find 'Fetch User Hierarchy' node")

    # ── Fix 2: Parse Hierarchy — key by email instead of name ──
    parse_node = find_node(nodes, "Parse Hierarchy")
    if parse_node:
        parse_node["parameters"]["jsCode"] = PARSE_HIERARCHY_CODE
        print("  ✓ Updated Parse Hierarchy to key managerToReports by email")
    else:
        print("  ✗ Could not find 'Parse Hierarchy' node")

    # ── Fix 3: Filter User Opps — robust team_deals with fallback ──
    filter_node = find_node(nodes, "Filter User Opps")
    if filter_node:
        filter_node["parameters"]["jsCode"] = FILTER_USER_OPPS_CODE
        print("  ✓ Updated Filter User Opps with robust team_deals logic")
    else:
        print("  ✗ Could not find 'Filter User Opps' node")

    # Push
    print("\nPushing updated workflow to n8n...")
    result = push_workflow(SALES_DIGEST_ID, wf)
    print(f"  ✓ Pushed — workflow '{result.get('name')}' updated")

    # Sync local JSON
    local_path = os.path.join(REPO_ROOT, "n8n/workflows/Sales Digest.json")
    print(f"\nSyncing local file...")
    fresh = fetch_workflow(SALES_DIGEST_ID)
    with open(local_path, "w") as f:
        json.dump(fresh, f, indent=2)
    print(f"  ✓ Saved to {local_path}")


if __name__ == "__main__":
    fix_sales_digest()
