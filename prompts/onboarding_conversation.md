# Onboarding Conversation Prompts

These are the message templates for the in-Slack onboarding flow.

---

## Initial Greeting (sent when user first interacts or is added)

```
Hey! I'm your new sales assistant — I'll be helping you stay on top of your deals, prep for meetings, and spot risks before they become problems.

But first, I need a name. What do you want to call me?

(Just reply with a name — anything you like. Some folks go with Alex, Luna, Max... or get creative. It's up to you.)
```

---

## Name Confirmation

```
{{assistant_name}}. I like it.

Nice to meet you, {{rep_name}}. I'm {{assistant_name}}, and I work for you now.

Here's what I'll do:
• *Every morning* — I'll send you a quick briefing on what needs attention in your pipeline
• *Before meetings* — I'll prep everything you need to know about the account and attendees
• *When deals go quiet* — I'll draft re-engagement emails for you to review and send

Your first briefing arrives tomorrow at 6am. If you want to change the timing, just tell me.

Ready to sell some deals?
```

---

## Emoji Selection (sent after name confirmation)

```
Now pick an emoji to be my icon in Slack. Just type any emoji like :rocket: or :crystal_ball: — custom workspace emojis work too.

(Or say "skip" and I'll stick with :robot_face:)
```

---

## Emoji Confirmation

```
Done — I'll use {{assistant_emoji}} as my icon from now on.

(Want to change it again? Just say "emoji :new_emoji:")
```

---

## Emoji Skip

When user says "skip" during emoji selection:

```
No problem — I'll use :robot_face: for now. You can always change it later with "emoji :your_pick:".
```

---

## Rename Acknowledgment

When user says "rename X" or similar:

```
Done. I'm {{new_name}} now.

(Change my name with "rename [name]" or my icon with "emoji [:emoji:]")
```

---

## Preference Changes

### Digest Time Change
User says "send digest at 7am" or similar:

```
Got it — I'll send your morning briefing at {{new_time}} {{timezone}} from now on.
```

### Disable Digest
User says "stop morning digest" or similar:

```
Understood. I've paused your morning briefings.

I'll still prep you before meetings and flag urgent risks. Just say "resume digest" whenever you want the daily briefings back.
```

### Resume Digest
User says "resume digest" or similar:

```
Morning briefings are back on. You'll get the next one at {{digest_time}} tomorrow.
```

---

## Error / Unclear Input

```
I didn't catch that. Here's what I can help with:

• *rename [name]* — give me a new name
• *emoji [:emoji:]* — change my icon
• *digest at [time]* — change when I send your morning briefing
• *stop digest* / *resume digest* — pause or restart daily briefings
• *help* — see this list again

Or just ask me anything about your deals.
```

---

## Help Command

```
Here's what I do:

*Automatic*
• Morning briefing at {{digest_time}} — your daily pipeline pulse
• Meeting prep 2 hours before customer calls
• Alerts when deals need attention

*On request*
• Ask me about any deal or account
• "Draft a follow-up for [account]"
• "What's happening with [deal name]?"

*Settings*
• rename [name]
• emoji [:emoji:]
• digest at [time]
• stop digest / resume digest

I'm here to make your life easier. What do you need?
```
