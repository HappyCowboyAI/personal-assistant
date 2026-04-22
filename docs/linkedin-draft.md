# LinkedIn Article + Post Draft

## LinkedIn Post (to promote the article)

---

I built a personal AI sales assistant for every rep on my team.

No backend code. No React app. No custom API.

Just an orchestration tool (n8n), an LLM, and our existing CRM data.

Every rep gets a named assistant — their own AI teammate that runs on a schedule and acts without being prompted:

- 6am: personalized pipeline briefing
- 2hrs before meetings: prep brief with participants, deal context, talking points
- After meetings: AI-generated recap with one-click Salesforce logging
- Twice weekly: silent account detection with draft re-engagement emails
- On demand: ICP analysis, deal intelligence, stakeholder maps, presentations

The assistant isn't a chatbot. It has its own agenda. It monitors your pipeline, spots risks before you do, and shows up in your Slack DM with the insight you needed but didn't think to ask for.

The whole system runs on three layers:
- Orchestration (n8n) for scheduling, routing, delivery
- LLM for reasoning and natural language generation
- CRM API for live sales data

13 workflows. Zero custom backend code. Every feature deployed in weeks, not months.

The full story of how I built it, what worked, and what I'd do differently:

[Link to article]

---

## LinkedIn Article

### I Built an AI Sales Assistant With No Backend Code — Here's How

**The problem nobody talks about in AI**

Most AI tools for sales reps are glorified search bars. You ask a question, you get an answer. That's useful, but it's not transformative.

The real problem isn't access to information — it's that reps don't know what to ask, or when to ask it. The deals that slip are the ones nobody was watching. The meeting you walked into unprepared happened because you were busy preparing for a different one.

I wanted to build something different: an AI assistant that doesn't wait to be asked. One that has its own agenda, monitors your pipeline, and proactively shows up with the insight you need — before you know you need it.

So I built one. For every rep on the team. With no custom backend code.

---

### What the assistant actually does

Each sales rep gets a named, personalized assistant delivered through Slack. They name it during onboarding (we have a Pikachu, a Jarvis, a Luna). It's not a shared bot — it's *their* assistant, with its own personality and voice.

Here's what it does without being asked:

**Every weekday morning at 6am**, it sends a personalized pipeline briefing. Not a data dump — a narrative. It reads through your open opportunities, flags what needs attention, and gives you a prioritized action list. The briefing adapts to your role: ICs get personal deal coaching, managers get team-level insights, execs get strategic pipeline views.

**Two hours before every customer meeting**, it sends a prep brief. Who's in the room, their roles, recent touchpoints, deal context, and specific talking points based on engagement patterns.

**After meetings end**, it generates a structured recap with AI-extracted action items. One click logs it to Salesforce. Another click creates tasks with smart assignees, durations, and categories.

**Twice a week**, it scans for silent accounts — customers who've gone quiet. Each alert includes an inline button that drafts a personalized re-engagement email, complete with the right contact's email address.

**On demand**, reps can ask for ICP analysis (won vs lost pattern fingerprinting), deal intelligence, stakeholder maps, or even generate branded presentation decks — all from a Slack DM.

The assistant isn't a chatbot. It has its own schedule, its own priorities, and it acts on them proactively.

---

### The architecture: three layers, zero backend code

The entire system runs on three layers:

**Orchestration: n8n**

n8n is an open-source workflow automation platform. Think of it as the nervous system — it handles scheduling, API routing, conditional logic, and delivery. Every feature is an n8n workflow: a visual graph of nodes that fetch data, transform it, call LLMs, and post results to Slack.

There are 13 workflows in production. The most complex one has 169 nodes. The simplest has 3. All of them were built visually in n8n's editor, exported as JSON, and version-controlled in git.

The key insight: **n8n replaces the backend**. No Express server, no Lambda functions, no database migrations for routing logic. The orchestration IS the code.

**Reasoning: LLM**

The LLM is the brain. It takes structured data (pipeline metrics, meeting transcripts, engagement signals) and turns it into natural language briefings, recaps, and analysis. It also acts as an agent — using tool calls to research accounts, look up contacts, and pull live CRM data via MCP (Model Context Protocol).

Every feature has a carefully crafted system prompt. The prompts enforce Slack formatting rules, personality, word limits, and output structure. Prompt engineering isn't a side task — it's a core part of the product.

**Intelligence: CRM API**

The CRM platform provides the data layer — engagement scores, activity signals, deal health, stakeholder data. The LLM connects to it both through structured API queries (for bulk data like pipeline exports) and through MCP tools (for conversational research).

This three-layer stack means I can build a new feature in days:
1. Design the prompt
2. Wire the data flow in n8n
3. Connect to Slack

No deployment pipeline. No infrastructure changes. No code review for a new REST endpoint. Just connect the nodes and activate the workflow.

---

### What I learned building this

**1. Proactive beats reactive, every time.**

The morning digest is the most-used feature — not because reps couldn't look up their pipeline, but because they never would at 6am. The assistant does the work of checking every deal, every morning, before the rep's first coffee. That's the difference between an AI tool and an AI teammate.

**2. Personality matters more than you think.**

Letting reps name their assistant and choose an emoji sounds trivial. It's not. The moment a rep names their bot "Pikachu" and sees messages from Pikachu in their Slack, something shifts. They start saying "Pikachu told me" in meetings. They trust it more. They engage more. Identity creates relationship, and relationship drives adoption.

**3. The hardest part isn't the AI — it's the data plumbing.**

80% of development time was spent on: parsing CSV responses, handling API edge cases, managing credential refresh, wiring Slack Block Kit formatting, and debugging n8n node connections. The LLM calls are the easy part. Getting the right data to the LLM in the right format at the right time — that's where the work is.

**4. Start with the schedule, not the chatbot.**

Most AI assistants start as chatbots and try to add proactive features later. I did the opposite — started with scheduled briefings and added on-demand features after. This meant the assistant was delivering value from day one, before any rep typed a single message. The on-demand features came later as "oh, I wish I could ask it about..." moments from the team.

**5. No-code doesn't mean no complexity.**

The Slack Events Handler workflow has 169 nodes. The routing logic handles 22 different command types. There's a state machine for onboarding, a pending action system for confirmations, and role-based content scoping. It's complex software — it just happens to be built without writing traditional code. The discipline of good software design (separation of concerns, clear interfaces, error handling) applies just as much to workflow automation.

**6. Ship the simple version, then let usage tell you what to build next.**

The first version was a morning digest. That's it. One workflow, one prompt, one Slack message. Everything else — meeting briefs, recaps, silence alerts, ICP analysis, presentations — came from watching how reps used (or didn't use) the first feature. The silence alert "Draft Email" button exists because a rep said "cool, now what do I do about it?" That's the signal to build the next thing.

---

### The numbers

- 13 production workflows
- 22 Slack commands
- 12 distinct skills (digest, meeting brief, recap, tasks, insights, silence, ICP, backstory, stakeholders, presentations, business reviews, deal watch)
- 3 proactive features running on cron schedules
- 0 lines of traditional backend code
- Weeks to build each feature, not months

---

### What's next

The assistant is heading toward true agency — taking actions, not just providing insights. Draft emails from silence alerts was the first step. Next: calendar-aware scheduling, automated follow-up sequences, and cross-rep collaboration signals.

The moat isn't the technology — it's the data flywheel. The more reps interact with their assistant, the better it understands their workflow, their deals, and their communication style. Every interaction makes the next one more useful.

If you're thinking about building something similar: start with n8n (or any orchestration layer), connect your CRM data, add an LLM, and ship a scheduled briefing to Slack. You'll be surprised how fast the product builds itself from there.

---

*I'm building AI-powered sales tools at Backstory. If you're working on similar problems or want to see a demo, reach out.*
