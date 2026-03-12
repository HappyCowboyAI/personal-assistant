#!/usr/bin/env python3
"""
Add 'presentation' command to Slack Events Handler + create Backstory Presentation sub-workflow.
- User types: presentation <prompt>
- Claude researches content (optionally via Confluence MCP), generates structured slide JSON
- n8n creates a Google Slides presentation with Backstory branding via Google Slides API
- User gets an editable Google Drive link in Slack
"""

import json
import os
import uuid
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

SLACK_EVENTS_ID = "QuQbIaWetunUOFUW"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

SLACK_CRED = {"id": "LluVuiMJ8NUbAiG7", "name": "Slackbot Auth Token"}
ANTHROPIC_CRED = {"id": "rlAz7ZSl4y6AwRUq", "name": "Anthropic account 2"}
GDRIVE_CRED = {"id": "bZEY1tGIQmLuqXRA", "name": "n8nClaw"}

# Atlassian MCP — user must create Multi-Header Auth credential in n8n and update this ID
ATLASSIAN_MCP_ENDPOINT = "https://mcp.atlassian.com/v1/sse"
ATLASSIAN_MCP_CRED = {"id": "PLACEHOLDER_UPDATE_ME", "name": "Atlassian MCP Multi-Header"}

# Google Drive image file IDs (public folder)
IMG_WORDMARK = "1GMUqmxGqOLoMqsxpiUSduo2hUzE4ei_J"
IMG_BOOKS_DARK = "1pA1og8eOMnQE4yBT8h9z2oeGneMqCyii"
IMG_BOOKS_WHITE = "1cL8RmMHzCscyLIdd3Y83RaM_yVXZI6SS"
IMG_GRADIENT = "1edNwnzGIyQPv3v0D0JzpqRllAfmkIIwY"


def uid():
    return str(uuid.uuid4())


def fetch_workflow(wf_id):
    resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def push_workflow(wf_id, wf):
    payload = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
               "settings": wf.get("settings", {}), "staticData": wf.get("staticData")}
    resp = requests.put(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}", headers=HEADERS, json=payload)
    resp.raise_for_status()
    return resp.json()


def sync_local(wf, filename):
    path = os.path.join(REPO_ROOT, "n8n", "workflows", filename)
    with open(path, "w") as f:
        json.dump(wf, f, indent=4)
    print(f"  Synced {path}")


# ============================================================
# Parse Presentation Command — Events Handler routing
# ============================================================
PARSE_PRESENTATION_CMD_CODE = r"""const data = $('Route by State').first().json;
const text = (data.text || '').trim();
const prompt = text.replace(/^presentation\s*/i, '').trim();

return [{
  json: {
    ...data,
    presentationPrompt: prompt,
    isValid: prompt.length > 0,
    responseText: prompt.length > 0 ? '' : data.assistantEmoji + ' Please include a description. Example:\n`presentation Build a Q1 engineering review`'
  }
}];
"""


# ============================================================
# Resolve Presentation Identity — builds system + agent prompts
# ============================================================
RESOLVE_PRESENTATION_IDENTITY_CODE = r"""const input = $('Workflow Input Trigger').first().json;

const BRAND_SPEC = `You are a presentation architect for Backstory. Create structured JSON that will be rendered into branded Google Slides.

SLIDE TYPES (use these type values exactly):

1. "title" — Opening slide. Always first.
   {type:"title", title:"...", subtitle:"..."}

2. "agenda" — Bulleted outline of topics.
   {type:"agenda", title:"Agenda", items:[
     {text:"Topic 1", subitems:["Detail A","Detail B"]},
     {text:"Topic 2"}
   ]}

3. "section_divider" — Section break. Use between major sections.
   {type:"section_divider", title:"Section Name"}

4. "stats" — Three metrics with values, labels, change indicators.
   {type:"stats", title:"Key Metrics", stats:[
     {value:"99.9%", label:"Uptime", change:"+0.2%"},
     {value:"142ms", label:"P95 Latency", change:"-23ms"},
     {value:"2.4M", label:"Daily Requests", change:"+18%"}
   ]}

5. "two_column" — Side-by-side content (wins/challenges, pros/cons).
   {type:"two_column", title:"...",
    left:{header:"Left Title", items:["Item 1","Item 2"]},
    right:{header:"Right Title", items:["Item 1","Item 2"]}}

6. "three_column_cards" — Three colored cards with bullet items.
   {type:"three_column_cards", title:"...", cards:[
     {title:"Card 1", items:["Item A","Item B"]},
     {title:"Card 2", items:["Item A","Item B"]},
     {title:"Card 3", items:["Item A","Item B"]}
   ]}

7. "four_column_timeline" — Quarterly/phase timeline.
   {type:"four_column_timeline", title:"...", quarters:[
     {label:"Q1", focus:"Theme", value:"Initiative", note:"Details"},
     {label:"Q2", focus:"Theme", value:"Initiative", note:"Details"},
     {label:"Q3", focus:"Theme", value:"Initiative", note:"Details"},
     {label:"Q4", focus:"Theme", value:"Initiative", note:"Details"}
   ]}

8. "thank_you" — Closing slide. Always last.
   {type:"thank_you", title:"Thank You"}

GUIDELINES:
- 6-12 slides typical. Always start with title, end with thank_you.
- Use section_divider between major topic areas.
- Use stats when you have 3 quantitative metrics.
- Use two_column for comparisons or contrasts.
- Use three_column_cards for 3 parallel items (teams, priorities).
- Use four_column_timeline for chronological plans.
- Keep text concise — bullet points, not paragraphs.
- Stats values should be short (e.g. "$2.4M", "99.9%", "142ms").

OUTPUT: Return ONLY a valid JSON object. No prose. No markdown fences.
{"title":"Presentation Title","slides":[...]}`;

const CONFLUENCE_INSTRUCTIONS = `
RESEARCH TOOLS — USE THEM PROACTIVELY:
You have two powerful research tools. Use them BEFORE generating slides to gather real data.

1. CONFLUENCE MCP — Company documentation, architecture, processes, project plans.
   - ALWAYS search Confluence first to find relevant pages about the topic.
   - Pull real data, metrics, diagrams, and technical details into your slides.
   - Search broadly — try multiple queries if the first doesn't return results.

2. PEOPLE.AI MCP — Account intelligence, sales data, engagement metrics, deal activity.
   - Use for any presentation involving customers, accounts, deals, or pipeline.
   - Pull real engagement data, meeting history, and relationship intelligence.
   - Great for QBRs, account reviews, pipeline analyses, and executive briefings.

RESEARCH WORKFLOW:
1. Read the user prompt carefully.
2. Search Confluence for relevant internal docs (2-3 searches).
3. If the topic involves accounts/customers/deals, query People.ai MCP.
4. Synthesize findings into structured, data-rich slides.
5. Use real numbers, names, and facts from your research — never fabricate data.

If tools return no results, proceed with the prompt context alone.`;

const systemPrompt = BRAND_SPEC + CONFLUENCE_INSTRUCTIONS;
const agentPrompt = input.presentationPrompt || 'Create a general company overview presentation';

return [{ json: {
  systemPrompt,
  agentPrompt,
  channelId: input.channelId,
  assistantName: input.assistantName || 'Your Assistant',
  assistantEmoji: input.assistantEmoji || ':robot_face:',
  presentationPrompt: input.presentationPrompt
}}];
"""


# ============================================================
# Parse Slide JSON — extract JSON from agent output
# ============================================================
PARSE_SLIDE_JSON_CODE = r"""const agentOutput = $('Presentation Agent').first().json;
const text = agentOutput.output || agentOutput.text || JSON.stringify(agentOutput);

let parsed = null;

// Try direct parse
try { parsed = JSON.parse(text); } catch (e) {}

// Try extracting from markdown code block
if (!parsed) {
  const m = text.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (m) try { parsed = JSON.parse(m[1].trim()); } catch (e) {}
}

// Try extracting raw JSON object
if (!parsed) {
  const m = text.match(/\{[\s\S]*\}/);
  if (m) try { parsed = JSON.parse(m[0]); } catch (e) {}
}

// Fallback
if (!parsed || !parsed.slides || !Array.isArray(parsed.slides)) {
  parsed = {
    title: "Presentation",
    slides: [
      {type: "title", title: "Presentation", subtitle: "Content generation incomplete"},
      {type: "thank_you", title: "Thank You"}
    ]
  };
}

// Ensure bookend slides
if (parsed.slides[0] && parsed.slides[0].type !== 'title') {
  parsed.slides.unshift({type: 'title', title: parsed.title || 'Presentation', subtitle: ''});
}
if (parsed.slides[parsed.slides.length - 1].type !== 'thank_you') {
  parsed.slides.push({type: 'thank_you', title: 'Thank You'});
}

return [{ json: parsed }];
"""


# ============================================================
# Build Batch Update — THE CORE brand positioning node
# Converts structured slide JSON → Google Slides API batchUpdate requests
# ============================================================
BUILD_BATCH_UPDATE_CODE = r"""const slides = $('Parse Slide JSON').first().json.slides;
const presId = $('Create Blank Presentation').first().json.presentationId;
const defaultSlideId = $('Create Blank Presentation').first().json.slides[0].objectId;

const EMU = (inches) => Math.round(inches * 914400);

const RGB = {
  black:       {red:0, green:0, blue:0},
  graphite:    {red:0.090, green:0.090, blue:0.129},
  surfaceGray: {red:0.733, green:0.737, blue:0.737},
  horizon:     {red:0.384, green:0.588, blue:0.678},
  white:       {red:1, green:1, blue:1},
  plum:        {red:0.667, green:0.561, blue:0.627},
  mint:        {red:0.812, green:0.980, blue:0.847},
  ember:       {red:0.816, green:0.286, blue:0.067},
  navy:        {red:0.004, green:0.173, blue:0.282},
  sky:         {red:0.131, green:0.710, blue:1},
  salmon:      {red:0.910, green:0.627, blue:0.565}
};

const IMG = {
  wordmark:   'https://lh3.googleusercontent.com/d/""" + IMG_WORDMARK + r"""',
  booksDark:  'https://lh3.googleusercontent.com/d/""" + IMG_BOOKS_DARK + r"""',
  booksWhite: 'https://lh3.googleusercontent.com/d/""" + IMG_BOOKS_WHITE + r"""',
  gradient:   'https://lh3.googleusercontent.com/d/""" + IMG_GRADIENT + r"""'
};

const reqs = [];
const imgReqs = [];
let idC = 0;
const gid = (p) => 'bs_' + p + '_' + (idC++);

// Delete default blank slide
reqs.push({deleteObject: {objectId: defaultSlideId}});

// Helper: create text box
function tb(sid, id, x, y, w, h) {
  reqs.push({createShape: {
    objectId: id, shapeType: 'TEXT_BOX',
    elementProperties: {
      pageObjectId: sid,
      size: {width: {magnitude: EMU(w), unit: 'EMU'}, height: {magnitude: EMU(h), unit: 'EMU'}},
      transform: {scaleX: 1, scaleY: 1, translateX: EMU(x), translateY: EMU(y), unit: 'EMU'}
    }
  }});
}

function ins(id, text) {
  if (!text) return;
  reqs.push({insertText: {objectId: id, text: String(text), insertionIndex: 0}});
}

function sty(id, s) {
  const ts = {};
  const f = [];
  if (s.ff) { ts.fontFamily = s.ff; f.push('fontFamily'); }
  if (s.fs) { ts.fontSize = {magnitude: s.fs, unit: 'PT'}; f.push('fontSize'); }
  if (s.b !== undefined) { ts.bold = s.b; f.push('bold'); }
  if (s.i !== undefined) { ts.italic = s.i; f.push('italic'); }
  if (s.c) { ts.foregroundColor = {opaqueColor: {rgbColor: s.c}}; f.push('foregroundColor'); }
  if (f.length === 0) return;
  reqs.push({updateTextStyle: {objectId: id, style: ts, fields: f.join(','), textRange: {type: 'ALL'}}});
}

function align(id, a) {
  reqs.push({updateParagraphStyle: {objectId: id, style: {alignment: a}, fields: 'alignment', textRange: {type: 'ALL'}}});
}

function rect(sid, id, x, y, w, h, color) {
  reqs.push({createShape: {
    objectId: id, shapeType: 'ROUND_RECTANGLE',
    elementProperties: {
      pageObjectId: sid,
      size: {width: {magnitude: EMU(w), unit: 'EMU'}, height: {magnitude: EMU(h), unit: 'EMU'}},
      transform: {scaleX: 1, scaleY: 1, translateX: EMU(x), translateY: EMU(y), unit: 'EMU'}
    }
  }});
  reqs.push({updateShapeProperties: {
    objectId: id,
    shapeProperties: {
      shapeBackgroundFill: {solidFill: {color: {rgbColor: color}}},
      outline: {propertyState: 'NOT_RENDERED'}
    },
    fields: 'shapeBackgroundFill,outline'
  }});
}

function colorStripe(sid, y) {
  const cs = [RGB.surfaceGray, RGB.plum, RGB.horizon, RGB.salmon, RGB.surfaceGray];
  cs.forEach((c, i) => {
    const id = gid('cs');
    reqs.push({createShape: {
      objectId: id, shapeType: 'RECTANGLE',
      elementProperties: {
        pageObjectId: sid,
        size: {width: {magnitude: EMU(2), unit: 'EMU'}, height: {magnitude: EMU(0.525), unit: 'EMU'}},
        transform: {scaleX: 1, scaleY: 1, translateX: EMU(i * 2), translateY: EMU(y), unit: 'EMU'}
      }
    }});
    reqs.push({updateShapeProperties: {
      objectId: id,
      shapeProperties: {shapeBackgroundFill: {solidFill: {color: {rgbColor: c}}}, outline: {propertyState: 'NOT_RENDERED'}},
      fields: 'shapeBackgroundFill,outline'
    }});
  });
}

function addWordmark(sid, x, y, w, h) {
  imgReqs.push({createImage: {objectId: gid('wm'), url: IMG.wordmark,
    elementProperties: {pageObjectId: sid,
      size: {width: {magnitude: EMU(w), unit: 'EMU'}, height: {magnitude: EMU(h), unit: 'EMU'}},
      transform: {scaleX: 1, scaleY: 1, translateX: EMU(x), translateY: EMU(y), unit: 'EMU'}}}});
}

function addBooksDark(sid, x, y) {
  imgReqs.push({createImage: {objectId: gid('bd'), url: IMG.booksDark,
    elementProperties: {pageObjectId: sid,
      size: {width: {magnitude: EMU(0.7), unit: 'EMU'}, height: {magnitude: EMU(0.55), unit: 'EMU'}},
      transform: {scaleX: 1, scaleY: 1, translateX: EMU(x), translateY: EMU(y), unit: 'EMU'}}}});
}

function addNavyStripe(sid) {
  imgReqs.push({createImage: {objectId: gid('gs'), url: IMG.gradient,
    elementProperties: {pageObjectId: sid,
      size: {width: {magnitude: EMU(1.8), unit: 'EMU'}, height: {magnitude: EMU(5.625), unit: 'EMU'}},
      transform: {scaleX: 1, scaleY: 1, translateX: EMU(8.2), translateY: EMU(0), unit: 'EMU'}}}});
  imgReqs.push({createImage: {objectId: gid('bw'), url: IMG.booksWhite,
    elementProperties: {pageObjectId: sid,
      size: {width: {magnitude: EMU(0.7), unit: 'EMU'}, height: {magnitude: EMU(0.55), unit: 'EMU'}},
      transform: {scaleX: 1, scaleY: 1, translateX: EMU(8.55), translateY: EMU(4.55), unit: 'EMU'}}}});
}

// --- Process each slide ---
slides.forEach((slide, idx) => {
  const sid = 'slide_' + idx;
  reqs.push({createSlide: {objectId: sid, insertionIndex: idx}});
  reqs.push({updatePageProperties: {objectId: sid,
    pageProperties: {pageBackgroundFill: {solidFill: {color: {rgbColor: RGB.white}}}},
    fields: 'pageBackgroundFill'}});

  switch (slide.type) {
    case 'title': {
      const t = gid('t'); tb(sid, t, 0.5, 1.4, 9, 1.2); ins(t, slide.title || '');
      sty(t, {ff:'Cardo', fs:60, b:true, c:RGB.black}); align(t, 'CENTER');
      if (slide.subtitle) {
        const s = gid('t'); tb(sid, s, 0.5, 2.6, 9, 0.6); ins(s, slide.subtitle);
        sty(s, {ff:'Cardo', fs:24, i:true, c:RGB.graphite}); align(s, 'CENTER');
      }
      addWordmark(sid, 3.5, 3.4, 3.0, 0.5);
      colorStripe(sid, 5.1);
      break;
    }
    case 'agenda': {
      const t = gid('t'); tb(sid, t, 0.5, 0.5, 8, 0.8); ins(t, slide.title || 'Agenda');
      sty(t, {ff:'Cardo', fs:40, b:true, c:RGB.black});
      let y = 1.5;
      (slide.items || []).forEach(item => {
        const text = typeof item === 'string' ? item : item.text;
        const id = gid('t'); tb(sid, id, 0.6, y, 8, 0.5); ins(id, '\u25CF  ' + text);
        sty(id, {ff:'Roboto', fs:22, b:true, c:RGB.black}); y += 0.5;
        if (item.subitems) {
          item.subitems.forEach(sub => {
            const s = gid('t'); tb(sid, s, 1.5, y, 7, 0.4); ins(s, '\u2013  ' + sub);
            sty(s, {ff:'Roboto', fs:18, c:RGB.graphite}); y += 0.4;
          });
        }
        y += 0.15;
      });
      addBooksDark(sid, 8.8, 4.6);
      break;
    }
    case 'section_divider': {
      const t = gid('t'); tb(sid, t, 0.5, 2.0, 9, 1.2); ins(t, slide.title || '');
      sty(t, {ff:'Cardo', fs:56, b:true, c:RGB.black}); align(t, 'CENTER');
      addWordmark(sid, 3.5, 3.8, 3.0, 0.5);
      colorStripe(sid, 5.1);
      break;
    }
    case 'stats': {
      const t = gid('t'); tb(sid, t, 0.5, 0.5, 8, 0.8); ins(t, slide.title || 'Key Metrics');
      sty(t, {ff:'Cardo', fs:40, b:true, c:RGB.black});
      const pos = [1.2, 4.2, 7.2];
      (slide.stats || []).slice(0,3).forEach((st, i) => {
        const v = gid('t'); tb(sid, v, pos[i], 1.8, 2.5, 1.0); ins(v, st.value || '');
        sty(v, {ff:'Cardo', fs:54, b:true, c:RGB.navy}); align(v, 'CENTER');
        const l = gid('t'); tb(sid, l, pos[i], 2.9, 2.5, 0.4); ins(l, st.label || '');
        sty(l, {ff:'Roboto', fs:18, c:RGB.graphite}); align(l, 'CENTER');
        if (st.change) {
          const c = gid('t'); tb(sid, c, pos[i], 3.3, 2.5, 0.4); ins(c, st.change);
          sty(c, {ff:'Roboto', fs:16, b:true, c:RGB.horizon}); align(c, 'CENTER');
        }
      });
      addBooksDark(sid, 8.8, 4.6);
      break;
    }
    case 'two_column': {
      const t = gid('t'); tb(sid, t, 0.5, 0.4, 8, 0.8); ins(t, slide.title || '');
      sty(t, {ff:'Cardo', fs:40, b:true, c:RGB.black});
      [{d:slide.left, x:0.5, clr:RGB.horizon}, {d:slide.right, x:5.2, clr:RGB.ember}].forEach(col => {
        if (!col.d) return;
        const h = gid('t'); tb(sid, h, col.x, 1.3, 4.2, 0.5); ins(h, col.d.header || '');
        sty(h, {ff:'Roboto', fs:24, b:true, c:col.clr});
        const items = (col.d.items || []).map(it => '\u2022 ' + it).join('\n');
        const b = gid('t'); tb(sid, b, col.x, 1.85, 4.2, 3.5); ins(b, items);
        sty(b, {ff:'Roboto', fs:16, c:RGB.graphite});
      });
      addBooksDark(sid, 8.85, 4.65);
      break;
    }
    case 'three_column_cards': {
      const t = gid('t'); tb(sid, t, 0.5, 0.4, 7, 0.8); ins(t, slide.title || '');
      sty(t, {ff:'Cardo', fs:40, b:true, c:RGB.black});
      const cx = [0.5, 3.0, 5.5]; const cc = [RGB.horizon, RGB.plum, RGB.ember];
      (slide.cards || []).slice(0,3).forEach((card, i) => {
        rect(sid, gid('r'), cx[i], 1.4, 2.4, 3.5, cc[i]);
        const ct = gid('t'); tb(sid, ct, cx[i]+0.15, 1.55, 2.1, 0.5); ins(ct, card.title || '');
        sty(ct, {ff:'Roboto', fs:24, b:true, c:RGB.white});
        const items = (card.items || []).map(it => '\u2022 ' + it).join('\n');
        const ci = gid('t'); tb(sid, ci, cx[i]+0.15, 2.2, 2.1, 2.5); ins(ci, items);
        sty(ci, {ff:'Roboto', fs:14, c:RGB.white});
      });
      addNavyStripe(sid);
      break;
    }
    case 'four_column_timeline': {
      const t = gid('t'); tb(sid, t, 0.5, 0.4, 7, 0.8); ins(t, slide.title || '');
      sty(t, {ff:'Cardo', fs:40, b:true, c:RGB.black});
      const qx = [0.5, 2.45, 4.4, 6.35]; const qc = [RGB.horizon, RGB.plum, RGB.ember, RGB.navy];
      (slide.quarters || []).slice(0,4).forEach((q, i) => {
        const ql = gid('t'); tb(sid, ql, qx[i], 1.3, 1.8, 0.4); ins(ql, q.label || '');
        sty(ql, {ff:'Roboto', fs:20, b:true, c:RGB.black}); align(ql, 'CENTER');
        rect(sid, gid('r'), qx[i], 1.75, 1.8, 3.0, qc[i]);
        const fl = gid('t'); tb(sid, fl, qx[i], 1.9, 1.8, 0.35); ins(fl, 'Focus Area');
        sty(fl, {ff:'Roboto', fs:11, c:RGB.white}); align(fl, 'CENTER');
        const fv = gid('t'); tb(sid, fv, qx[i], 2.3, 1.8, 0.5); ins(fv, q.focus || q.value || '');
        sty(fv, {ff:'Cardo', fs:24, b:true, c:RGB.white}); align(fv, 'CENTER');
        if (q.note) {
          const n = gid('t'); tb(sid, n, qx[i], 3.8, 1.8, 0.35); ins(n, q.note);
          sty(n, {ff:'Roboto', fs:11, c:RGB.white}); align(n, 'CENTER');
        }
      });
      addNavyStripe(sid);
      break;
    }
    case 'thank_you': {
      const t = gid('t'); tb(sid, t, 0.5, 1.8, 9, 1.5);
      ins(t, (slide.title || 'THANK YOU').toUpperCase());
      sty(t, {ff:'Cardo', fs:72, b:true, c:RGB.black}); align(t, 'CENTER');
      addWordmark(sid, 3.5, 3.5, 3.0, 0.5);
      colorStripe(sid, 5.1);
      break;
    }
    default: {
      const t = gid('t'); tb(sid, t, 0.5, 0.5, 8, 0.8); ins(t, slide.title || '');
      sty(t, {ff:'Cardo', fs:40, b:true, c:RGB.black});
      if (slide.body) {
        const b = gid('t'); tb(sid, b, 0.5, 1.5, 9, 3.5); ins(b, slide.body);
        sty(b, {ff:'Roboto', fs:18, c:RGB.graphite});
      }
      addBooksDark(sid, 8.85, 4.65);
      break;
    }
  }
});

return [{ json: { requests: reqs, imageRequests: imgReqs, presentationId: presId } }];
"""


# ============================================================
# CREATE BACKSTORY PRESENTATION SUB-WORKFLOW
# ============================================================
def create_presentation_workflow():
    print("\n=== Creating Backstory Presentation workflow ===")

    nodes = [
        # 1. Workflow Input Trigger
        {
            "parameters": {"inputSource": "passthrough"},
            "id": uid(),
            "name": "Workflow Input Trigger",
            "type": "n8n-nodes-base.executeWorkflowTrigger",
            "typeVersion": 1.1,
            "position": [200, 400]
        },
        # 2. Resolve Presentation Identity
        {
            "parameters": {"jsCode": RESOLVE_PRESENTATION_IDENTITY_CODE},
            "id": uid(),
            "name": "Resolve Presentation Identity",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [420, 400]
        },
        # 3. Presentation Agent
        {
            "parameters": {
                "promptType": "define",
                "text": "={{ $('Resolve Presentation Identity').first().json.agentPrompt }}",
                "options": {
                    "systemMessage": "={{ $('Resolve Presentation Identity').first().json.systemPrompt }}",
                    "maxIterations": 20
                }
            },
            "id": uid(),
            "name": "Presentation Agent",
            "type": "@n8n/n8n-nodes-langchain.agent",
            "typeVersion": 1.7,
            "position": [640, 400],
            "continueOnFail": True
        },
        # 4. Anthropic Chat Model (sub-node)
        {
            "parameters": {
                "model": {
                    "__rl": True, "mode": "list",
                    "value": "claude-sonnet-4-5-20250929",
                    "cachedResultName": "Claude Sonnet 4.5"
                },
                "options": {}
            },
            "id": uid(),
            "name": "Anthropic Chat Model",
            "type": "@n8n/n8n-nodes-langchain.lmChatAnthropic",
            "typeVersion": 1.3,
            "position": [648, 624],
            "credentials": {"anthropicApi": ANTHROPIC_CRED}
        },
        # 5. Confluence MCP (sub-node)
        {
            "parameters": {
                "endpointUrl": ATLASSIAN_MCP_ENDPOINT,
                "authentication": "multipleHeadersAuth",
                "options": {}
            },
            "id": uid(),
            "name": "Confluence MCP",
            "type": "@n8n/n8n-nodes-langchain.mcpClientTool",
            "typeVersion": 1.2,
            "position": [776, 624],
            "credentials": {"httpMultipleHeadersAuth": ATLASSIAN_MCP_CRED}
        },
        # 6. Parse Slide JSON
        {
            "parameters": {"jsCode": PARSE_SLIDE_JSON_CODE},
            "id": uid(),
            "name": "Parse Slide JSON",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [860, 400]
        },
        # 7. Create Blank Presentation
        {
            "parameters": {
                "method": "POST",
                "url": "https://slides.googleapis.com/v1/presentations",
                "authentication": "predefinedCredentialType",
                "nodeCredentialType": "googleSlidesOAuth2Api",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [{"name": "Content-Type", "value": "application/json"}]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify({title: $('Parse Slide JSON').first().json.title || 'Backstory Presentation'}) }}",
                "options": {}
            },
            "id": uid(),
            "name": "Create Blank Presentation",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [1080, 400],
            "credentials": {"googleSlidesOAuth2Api": GDRIVE_CRED}
        },
        # 8. Build Batch Update
        {
            "parameters": {"jsCode": BUILD_BATCH_UPDATE_CODE},
            "id": uid(),
            "name": "Build Batch Update",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1300, 400]
        },
        # 9. Populate Slides (batchUpdate — shapes, text, styles)
        {
            "parameters": {
                "method": "POST",
                "url": "=https://slides.googleapis.com/v1/presentations/{{ $json.presentationId }}:batchUpdate",
                "authentication": "predefinedCredentialType",
                "nodeCredentialType": "googleSlidesOAuth2Api",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [{"name": "Content-Type", "value": "application/json"}]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify({requests: $('Build Batch Update').first().json.requests}) }}",
                "options": {}
            },
            "id": uid(),
            "name": "Populate Slides",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [1520, 400],
            "credentials": {"googleSlidesOAuth2Api": GDRIVE_CRED}
        },
        # 10. Add Images (batchUpdate — logos, icons, gradient stripe)
        {
            "parameters": {
                "method": "POST",
                "url": "=https://slides.googleapis.com/v1/presentations/{{ $('Build Batch Update').first().json.presentationId }}:batchUpdate",
                "authentication": "predefinedCredentialType",
                "nodeCredentialType": "googleSlidesOAuth2Api",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [{"name": "Content-Type", "value": "application/json"}]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify({requests: $('Build Batch Update').first().json.imageRequests}) }}",
                "options": {}
            },
            "id": uid(),
            "name": "Add Images",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [1740, 400],
            "credentials": {"googleSlidesOAuth2Api": GDRIVE_CRED},
            "continueOnFail": True
        },
        # 11. Share Presentation (Google Drive — anyone with link can edit)
        {
            "parameters": {
                "method": "POST",
                "url": "=https://www.googleapis.com/drive/v3/files/{{ $('Build Batch Update').first().json.presentationId }}/permissions",
                "authentication": "predefinedCredentialType",
                "nodeCredentialType": "googleDriveOAuth2Api",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [{"name": "Content-Type", "value": "application/json"}]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "{\"role\": \"writer\", \"type\": \"anyone\"}",
                "options": {}
            },
            "id": uid(),
            "name": "Share Presentation",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [1960, 400],
            "credentials": {"googleDriveOAuth2Api": GDRIVE_CRED}
        },
        # 12. Send Presentation Link (Slack)
        {
            "parameters": {
                "method": "POST",
                "url": "https://slack.com/api/chat.postMessage",
                "authentication": "genericCredentialType",
                "genericAuthType": "httpHeaderAuth",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [{"name": "Content-Type", "value": "application/json"}]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify({ channel: $('Resolve Presentation Identity').first().json.channelId, text: $('Resolve Presentation Identity').first().json.assistantEmoji + ' Your *Backstory* presentation is ready!\\n\\n<https://docs.google.com/presentation/d/' + $('Build Batch Update').first().json.presentationId + '/edit|:open_book: ' + ($('Parse Slide JSON').first().json.title || 'Presentation') + '>', username: $('Resolve Presentation Identity').first().json.assistantName, icon_emoji: $('Resolve Presentation Identity').first().json.assistantEmoji, unfurl_links: false, unfurl_media: false }) }}",
                "options": {}
            },
            "id": uid(),
            "name": "Send Presentation Link",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [2180, 400],
            "credentials": {"httpHeaderAuth": SLACK_CRED},
            "continueOnFail": True
        }
    ]

    connections = {
        "Workflow Input Trigger": {"main": [[{"node": "Resolve Presentation Identity", "type": "main", "index": 0}]]},
        "Resolve Presentation Identity": {"main": [[{"node": "Presentation Agent", "type": "main", "index": 0}]]},
        "Presentation Agent": {"main": [[{"node": "Parse Slide JSON", "type": "main", "index": 0}]]},
        "Parse Slide JSON": {"main": [[{"node": "Create Blank Presentation", "type": "main", "index": 0}]]},
        "Create Blank Presentation": {"main": [[{"node": "Build Batch Update", "type": "main", "index": 0}]]},
        "Build Batch Update": {"main": [[{"node": "Populate Slides", "type": "main", "index": 0}]]},
        "Populate Slides": {"main": [[{"node": "Add Images", "type": "main", "index": 0}]]},
        "Add Images": {"main": [[{"node": "Share Presentation", "type": "main", "index": 0}]]},
        "Share Presentation": {"main": [[{"node": "Send Presentation Link", "type": "main", "index": 0}]]},
        # Sub-node connections
        "Anthropic Chat Model": {"ai_languageModel": [[{"node": "Presentation Agent", "type": "ai_languageModel", "index": 0}]]},
        "Confluence MCP": {"ai_tool": [[{"node": "Presentation Agent", "type": "ai_tool", "index": 0}]]}
    }

    workflow = {
        "name": "Backstory Presentation",
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1"}
    }

    resp = requests.post(f"{N8N_BASE_URL}/api/v1/workflows", headers=HEADERS, json=workflow)
    resp.raise_for_status()
    result = resp.json()
    wf_id = result["id"]
    print(f"  Created: ID={wf_id}, {len(result['nodes'])} nodes")

    resp3 = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}", headers=HEADERS)
    resp3.raise_for_status()
    sync_local(resp3.json(), "Backstory Presentation.json")

    return wf_id


# ============================================================
# ADD PRESENTATION COMMAND TO SLACK EVENTS HANDLER
# ============================================================
def upgrade_events_handler(wf, pres_wf_id):
    print(f"\n=== Adding presentation command (Pres WF ID: {pres_wf_id}) ===")
    nodes = wf["nodes"]
    connections = wf["connections"]

    node_names = [n["name"] for n in nodes]
    if "Parse Presentation" in node_names:
        print("  Parse Presentation already exists — skipping")
        return wf

    # --- 1. Update Route by State ---
    for node in nodes:
        if node["name"] == "Route by State":
            old_code = node["parameters"]["jsCode"]
            # Insert after insights command
            new_code = old_code.replace(
                "else if (lower === 'insights' || lower.startsWith('insights ')) route = 'cmd_insights';",
                "else if (lower === 'insights' || lower.startsWith('insights ')) route = 'cmd_insights';\n  else if (lower === 'presentation' || lower.startsWith('presentation ')) route = 'cmd_presentation';"
            )
            if new_code == old_code:
                # Fallback: insert after brief
                new_code = old_code.replace(
                    "else if (lower === 'brief' || lower.startsWith('brief ')) route = 'cmd_brief';",
                    "else if (lower === 'brief' || lower.startsWith('brief ')) route = 'cmd_brief';\n  else if (lower === 'presentation' || lower.startsWith('presentation ')) route = 'cmd_presentation';"
                )
            node["parameters"]["jsCode"] = new_code
            print("  Updated Route by State with 'presentation' command")
            break

    # --- 2. Add "Presentation" output to Switch Route ---
    for node in nodes:
        if node["name"] == "Switch Route":
            node["parameters"]["rules"]["values"].append({
                "outputKey": "Presentation",
                "conditions": {
                    "options": {"version": 2, "leftValue": "", "caseSensitive": True, "typeValidation": "strict"},
                    "combinator": "and",
                    "conditions": [{
                        "id": uid(),
                        "operator": {"name": "filter.operator.equals", "type": "string", "operation": "equals"},
                        "leftValue": "={{ $json.route }}",
                        "rightValue": "cmd_presentation"
                    }]
                },
                "renameOutput": True
            })
            output_idx = len(node["parameters"]["rules"]["values"]) - 1
            print(f"  Added 'Presentation' output to Switch Route (output {output_idx})")
            break
    else:
        output_idx = 11

    # --- 3. Add Parse Presentation ---
    parse_id = uid()
    nodes.append({
        "parameters": {"jsCode": PARSE_PRESENTATION_CMD_CODE},
        "id": parse_id,
        "name": "Parse Presentation",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [2180, 2720]
    })
    print(f"  Added Parse Presentation")

    # --- 4. Add Is Valid Presentation? ---
    is_valid_id = uid()
    nodes.append({
        "parameters": {
            "conditions": {
                "options": {"version": 2, "leftValue": "", "caseSensitive": True, "typeValidation": "strict"},
                "conditions": [{
                    "id": uid(),
                    "leftValue": "={{ $json.isValid }}",
                    "rightValue": True,
                    "operator": {"type": "boolean", "operation": "true"}
                }],
                "combinator": "and"
            },
            "options": {}
        },
        "id": is_valid_id,
        "name": "Is Valid Presentation?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [2420, 2720]
    })

    # --- 5. Send Presentation Generating ---
    send_gen_id = uid()
    nodes.append({
        "parameters": {
            "method": "POST",
            "url": "https://slack.com/api/chat.postMessage",
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Content-Type", "value": "application/json"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ channel: $json.channelId, text: $json.assistantEmoji + ' Building your Backstory presentation... this takes about 2 minutes.', username: $json.assistantName, icon_emoji: $json.assistantEmoji, unfurl_links: false, unfurl_media: false }) }}",
            "options": {}
        },
        "id": send_gen_id,
        "name": "Send Presentation Generating",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [2660, 2620],
        "credentials": {"httpHeaderAuth": SLACK_CRED}
    })

    # --- 6. Prepare Presentation Input ---
    prepare_id = uid()
    nodes.append({
        "parameters": {
            "jsCode": "return [{ json: $('Is Valid Presentation?').first().json }];"
        },
        "id": prepare_id,
        "name": "Prepare Presentation Input",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [2900, 2620]
    })

    # --- 7. Execute Presentation ---
    exec_id = uid()
    nodes.append({
        "parameters": {
            "workflowId": {"__rl": True, "mode": "id", "value": pres_wf_id},
            "options": {}
        },
        "id": exec_id,
        "name": "Execute Presentation",
        "type": "n8n-nodes-base.executeWorkflow",
        "typeVersion": 1.2,
        "position": [3140, 2620]
    })

    # --- 8. Send Presentation Error ---
    send_error_id = uid()
    nodes.append({
        "parameters": {
            "method": "POST",
            "url": "https://slack.com/api/chat.postMessage",
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Content-Type", "value": "application/json"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ channel: $json.channelId, text: $json.responseText, username: $json.assistantName, icon_emoji: $json.assistantEmoji, unfurl_links: false, unfurl_media: false }) }}",
            "options": {}
        },
        "id": send_error_id,
        "name": "Send Presentation Error",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [2660, 2820],
        "credentials": {"httpHeaderAuth": SLACK_CRED}
    })

    # --- 9. Wire connections ---
    if "Switch Route" not in connections:
        connections["Switch Route"] = {"main": []}
    switch_outputs = connections["Switch Route"]["main"]
    while len(switch_outputs) <= output_idx:
        switch_outputs.append([])
    switch_outputs[output_idx] = [{"node": "Parse Presentation", "type": "main", "index": 0}]

    connections["Parse Presentation"] = {
        "main": [[{"node": "Is Valid Presentation?", "type": "main", "index": 0}]]
    }
    connections["Is Valid Presentation?"] = {
        "main": [
            [{"node": "Send Presentation Generating", "type": "main", "index": 0}],
            [{"node": "Send Presentation Error", "type": "main", "index": 0}]
        ]
    }
    connections["Send Presentation Generating"] = {
        "main": [[{"node": "Prepare Presentation Input", "type": "main", "index": 0}]]
    }
    connections["Prepare Presentation Input"] = {
        "main": [[{"node": "Execute Presentation", "type": "main", "index": 0}]]
    }

    print(f"  Wired: Switch[{output_idx}] → Parse → Valid? → [yes: Generating → Prepare → Execute] [no: Error]")

    # --- 10. Update Build Help Response ---
    for node in nodes:
        if node["name"] == "Build Help Response":
            old_code = node["parameters"]["jsCode"]
            old_marker = '"*Pause or restart:*'
            pres_section = (
                '"*Presentations:*\\n" +\n'
                '    "`presentation <prompt>` \\u2014 create a Backstory-branded Google Slides deck\\n\\n" +\n'
                '    "*Pause or restart:*'
            )
            new_code = old_code.replace(old_marker, pres_section)
            if new_code == old_code:
                print("  WARNING: Could not find help text marker")
            else:
                print("  Updated Build Help Response with presentation section")
            node["parameters"]["jsCode"] = new_code
            break

    print(f"  Total nodes: {len(nodes)}")
    return wf


# ============================================================
# MAIN
# ============================================================
def activate_workflow(wf_id):
    resp = requests.post(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}/activate", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def main():
    # Step 1: Create Backstory Presentation sub-workflow
    pres_wf_id = create_presentation_workflow()

    # Step 1b: Activate
    print("\n=== Activating Backstory Presentation ===")
    activate_workflow(pres_wf_id)
    print(f"  Activated: {pres_wf_id}")

    # Step 2: Update Slack Events Handler
    print("\nFetching Slack Events Handler...")
    events_wf = fetch_workflow(SLACK_EVENTS_ID)
    print(f"  {len(events_wf['nodes'])} nodes")

    events_wf = upgrade_events_handler(events_wf, pres_wf_id)

    print("\n=== Pushing Slack Events Handler ===")
    result = push_workflow(SLACK_EVENTS_ID, events_wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")

    print("\n=== Syncing local file ===")
    sync_local(result, "Slack Events Handler.json")

    print(f"\nDone! Backstory Presentation workflow ID: {pres_wf_id}")
    print("Users can now type: presentation <prompt>")
    print("\nNOTE: Before testing, you need to:")
    print("  1. Create Atlassian MCP Multi-Header Auth credential in n8n")
    print(f"     Then update credential ID in Backstory Presentation workflow (currently: {ATLASSIAN_MCP_CRED['id']})")
    print("  2. Verify Google Slides OAuth2 credential has presentations scope")
    print("     (Using existing Google Drive credential — may need scope update)")


if __name__ == "__main__":
    main()
