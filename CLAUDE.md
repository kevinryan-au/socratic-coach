# CLAUDE.md — build brief: The Socratic Coach

You are building a small agent WITH Kev, not just for him. This file is the complete spec.
Read it fully before doing anything. The design is settled — build it, don't redesign it.

## What we're building

**The Socratic Coach**: a local agent that helps Kev think through decisions by asking
questions — one at a time, never giving answers or advice. It runs as a lite app:
`coach.py` serves a chat page in the browser at localhost. Kev never uses the terminal
to talk to it; he double-clicks a launcher and a browser tab opens.

This is also an AI Education teaching build. Kev has a house model of agents — the
L0–L9 agent stack — and the whole point is that he watches each layer become real code.

## The agent stack (use these exact names and numbers)

| Layer | Name | In this build |
|---|---|---|
| L0 | Inference | Cloudflare Workers AI free tier, called over REST. No model files on the Mac. |
| L1 | Context assembly | The message list coach.py builds each turn: constitution + instructions.md + relevant notes + session so far |
| L2 | Tool interface | Three tools only: `save_note`, `go_off_record`, `end_session` |
| L3 | Execution / effectors | Running those tools + showing the question in the chat page. **The user is the environment**: Kev's typed reply is the "tool result" |
| L4 | Control loop | The while-loop; also the question-checker and the consecutive-call cap |
| L5 | State & memory | `memory/session-log.md` + `memory/stuck-patterns.md` |
| L6 | Planning | **Deliberately not built** — don't add it |
| L7 | Delegation | **Deliberately not built** — don't add it |
| L8 | Governance | Enforced in code: localhost-only, one folder, off-record really means off-record, human veto on instruction edits |
| L9 | Adaptation | `memory/instructions.md` — evolves only via proposed-edit-plus-veto |

## Locked decisions — do not re-litigate

1. **Free only, hard constraint.** L0 = Cloudflare Workers AI free allowance (10,000
   neurons/day). Never the Anthropic API, never any metered API, no OAuth workarounds.
   (You, Claude Code, run on Kev's Max plan — that's fine; the *coach* must be free to run.)
2. **No terminal for Kev.** Terminal appears only during setup, one paste-ready command
   at a time. The finished coach is browser-only.
3. **Never answers, only asks** — soft rule in the prompt, hard rule in code (see
   question-checker below). House rule to preserve in comments: *behaviour you'd like
   goes in the prompt; behaviour you require goes in code.*
   **The first question of a session is an invitation, not a diagnosis.** "Ask about the
   thing being avoided" is good practice once there is something to work with, and an
   accusation on turn one, when there is no conversation to have avoided anything in. Kev
   types nothing to open a session, so the code types the opening turn (`OPENING`) — which
   makes that framing a decision made in the file, not a mood the model was in.
4. **Done is Kev's call.** The model may propose ending a session; only Kev ends it.
5. **The second loop ships last**: after each session the coach proposes ONE edit to
   instructions.md; it is applied only if Kev clicks Approve.
6. Keep it small and readable. Target ~150 lines for coach.py. Bias hard toward the
   Python standard library (http.server, urllib, json) — zero pip installs if possible.
   Part of the lesson is "nothing hidden".

## Folder layout (build exactly this)

```
AI Education/coach/
├─ CLAUDE.md               ← this file
├─ Start Coach.command     ← double-click: starts coach.py, opens the chat tab
├─ coach.py                ← the agent: L1, L2, L3, L4, L8 — with layer-numbered comments
├─ index.html              ← the chat page (a window onto the agent, not the agent)
├─ .env                    ← CLOUDFLARE_ACCOUNT_ID + CLOUDFLARE_API_TOKEN — the only secrets
└─ memory/
   ├─ session-log.md       ← L5: per-session summaries
   ├─ stuck-patterns.md    ← L5: where Kev gets stuck, what question unlocked him
   └─ instructions.md      ← L9: coaching style, seeded then evolved via veto
```

## How to work with Kev

- Kev is not technical. One command at a time, paste-ready, no placeholders when the
  real value is known. zsh gotchas apply (stuck `dquote>` prompts; `#` comments don't
  paste well). He's on macOS (MacBook Air).
- Explain as you go, layer by layer: keep the correct technical terms but give each a
  plain-words explanation and a "so what". Upbeat get-the-most-out-of-it tone, never
  cautionary hand-wringing.
- At the end of each phase, DEMO the layer you just built: show it running, then one
  or two sentences of "that was L_n — here's what just became real".
- Comment the code with layer tags (`# --- L4: control loop ---`) so the file reads
  as the stack.
- Never display, log, or screenshot the contents of .env. Add nothing to the folder
  beyond the layout above without saying why.

## Build phases (in order — each ends with a working demo)

**Phase 1 — L0 speaks.**
Walk Kev through, in the browser (he clicks, you wait): create a free Cloudflare
account; find the Account ID; create a Workers AI API token. Store both in `.env`.
Write a ten-line test script that sends one question to the model and prints the reply.
✅ Done when: the model answers from Python. Demo: "that's L0 — rented, stateless, and
the only layer that isn't yours."

**Phase 2 — the loop and the app.**
coach.py: assemble context (L1), define the three tools (L2), execute them (L3), loop
(L4); serve index.html — a clean, minimal chat page — at http://127.0.0.1:8787.
The model replies in a strict JSON envelope your L4 parses: either
`{"ask": "…one question…"}` or `{"tool": "…", "args": {…}}`. That convention IS L2 made
visible — explain it that way.
✅ Done when: Kev holds a full Socratic session in his browser. (No memory yet — say so:
"it's a stranger every session; that's what L5 fixes.")

**Phase 3 — memory (L5).**
end_session writes a session summary + any stuck-patterns. On start, load both files
into L1. ✅ Done when: a new session opens with a callback to the previous one.

**Phase 4 — hardening (L4 + L8).**
(a) Question-checker in code: if a reply is neither a sanctioned tool call nor ends
with a question, re-prompt with a nudge, max 2 retries, then show it flagged.
(b) go_off_record: while on, nothing from those turns is ever written to disk; show
an "off the record" indicator in the page.
(c) Cap consecutive model calls without Kev's input at 5.
(d) Server binds 127.0.0.1 only.
✅ Done when: advice gets bounced and an off-record confession leaves zero trace in memory/.

**Phase 5 — the second loop (L9).**
At session end the coach proposes ONE edit to instructions.md, shown in the page as a
diff with Approve / Veto buttons. Only Approve writes the file.
✅ Done when: instructions.md has evolved once, with Kev's consent. This is the demo of
his "Second Loop" essay concept — say so at the moment it happens.

**Phase 6 — the launcher.**
`Start Coach.command`: starts coach.py if not running, opens the chat tab. Make it
double-clickable (chmod +x; handle Gatekeeper if it complains).
✅ Done when: laptop-open → double-click → thinking with the coach in under ten seconds.

There are now two launchers — `Coach.app` (the one he double-clicks) and `Start
Coach.command` (the same thing with the lid off) — and both pull before starting. Two
rules hold in both, and both were once true of only one of them:

- **`memory/instructions.md` is set aside before the pull and handed back after.** It is
  the one tracked file the coach rewrites (L9), so an update that touched it would be
  refused, and the better the coach got at improving itself the more stuck it would be.
  A copy, never a stash — a stash can come back as conflict markers in the middle of the
  coaching style, which the coach would then read out as its own instructions.
- **A refused update says so, and says why.** Silence and success used to print the same
  line, which is exactly how the guard above went missing from one launcher for four
  builds without anyone noticing.

Change one launcher, change both.

## Technical notes

- Endpoint: `POST https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/run/{MODEL}`
  with `Authorization: Bearer {TOKEN}`. Check the current Workers AI model catalog and
  pick a capable free chat model (llama-3.3-70b-instruct-fp8-fast class); prefer quality
  of questioning over speed. Make the model id a one-line constant so it's swappable —
  and point out that swappability is the reference architecture paying off.
- Free-tier budget: 10,000 neurons/day. A coaching session is a trickle; don't add
  retries that could loop-spend. On daily-limit errors, fail with a friendly message
  in the chat page ("the free allowance resets tomorrow").
- The constitution (system prompt) lives in coach.py as a readable triple-quoted
  string near the top — Kev should be able to open the file and read his coach's soul.
  Seed instructions.md with a short starter style; everything else it learns via Phase 5.
- Session transcript stays in RAM during a session; only summaries/notes touch disk
  (except off-record, which touches nothing).

## Phase sizing

Kev works in 5-hour Max windows. Phases 1–2 fit in one sitting; 3–4 in another;
5–6 in a third. Never start a phase you can't demo within the window.

## Added after the six phases

**The works panel** — the loop drawn, and the path each turn took through it, so the stack
is watchable while it runs rather than only readable in the source. Not a layer of its own;
instrumentation *of* the layers.

- Every layer calls `note(trace, ...)` as it acts. `coach.py` owns the whole description of
  the stack (the `LAYERS` table, served at `/stack`, where each layer declares whether it
  sits in the `loop`, at the `edge`, or is `unbuilt`) and every line of every trace.
  `index.html` owns only the drawing — where boxes go, which way arrows point. It knows
  nothing about agents: same rule as before, a window onto the agent, not the agent.
- Show the loop as a loop. A list in L0–L9 order is a taxonomy, not a mechanism — it was
  tried first and taught nothing, because execution order is L4→L1→L0→L4→L2, so the lights
  jump around and the eye can't follow a path. Both back-edges rejoin at L1; drawing them
  any other way would hide why the context is rebuilt every lap.
- **Plain words first, everywhere in the panel.** This is the "explain as you go" rule from
  above, applied to the running app: every trace line says what happened, not what it is
  called — "the model thought for 1.3 seconds", never "L0 latency 1.26". The layer number
  is already on screen; the sentence is the part doing the teaching. Same for the boxes:
  what it does on top, the proper name underneath, both from `LAYERS`.
- Give it the room. The conversation is one question at a time and needs far less width
  than the works do; the panel takes about half the window when it's showing.
- **Two timescales, not one.** The loop drawing shows a turn; underneath it, "one session,
  and what survives it" shows the close — because L5, L8 and L9 never appear in a turn's
  path, and their whole relationship is the *order* they act in at the end (L8 gates what the
  closing call sees → that one call yields both L5's writes and L9's proposal → L9 needs
  consent → L1 gathers all three back in next session). Three chips in a row can't say that.
  It comes from `KEEPS`/`STAGES`/`CLOSE` in `coach.py`, grouped by `stage` the way the layers
  are grouped by `where`.
- **Every part of the drawing opens.** A box, a chip, an unbuilt line and a reason-it-went-
  round are all handles on one layer; clicking any of them shows that layer's own words —
  `does`, `sits`, `note`, all from `LAYERS`. One at a time, under the drawing. A tooltip
  isn't enough: it can't be reached by keyboard, can't be read twice, and vanishes.
- **A detail is for reading, not decoding.** The whole context, the raw reply, the file as
  rewritten — laid out as text with headings that say who was speaking, never a JSON dump
  with the line breaks escaped. The content itself is passed through untouched; accurate and
  unreadable is still unreadable.
- The trace is **RAM for one turn, then gone**. Never a file, never a log, never
  localStorage. While off-record the transcript is still sent to the model, so it appears in
  the L1 detail — persisting the trace anywhere would be a hole straight through L8's
  off-record promise. Don't add an export, a save, or a replay.
- Keep it in step: a new layer, tool, or check should say what it did, or the panel starts
  lying by omission.
