# The Socratic Coach

A small agent that helps me think by asking questions — one at a time — and never giving
answers or advice. It runs on my Mac: double-click a file, a browser tab opens, and the
questions start.

It is also a teaching build. Each layer of the
[agent stack](https://kevin-ryan.com/work/the-agent-stack.html) becomes real code, one
phase at a time, tagged in `coach.py` so the file reads as the stack.

## Running it

Double-click **`Coach.app`**. No terminal window, no commands — it starts the coach, opens
the chat page and gets out of the way. Drag it to the Dock once and that's the only thing
you ever touch. To stop: press **Quit** in the chat page.

It also takes care of itself: on every launch it quietly pulls the newest build before
starting, and if anything goes wrong — no keys, no Python, no internet — it says so in a
normal Mac dialog rather than failing silently.

Double-click it again while a session is open and it offers to restart on the new build,
or leaves you where you are. It doesn't hang around in the background waiting to be asked;
the coach itself keeps running until you quit it from the page.

Two other ways in, for when you want to see the works:

| | |
|---|---|
| `Start Coach.command` | The same thing as a visible shell script. A Terminal window opens and you can watch it run. |
| `python3 coach.py` | The actual program. Everything above is a wrapper around this line. |

To stop it: press **Quit** in the chat page (or close the Terminal window, if you started
it that way).

## What it depends on

```
Start Coach.command  →  python3 coach.py  →  api.cloudflare.com  →  Llama 3.3 70B
```

- **Python 3** — standard library only. Nothing to install.
- **A Cloudflare Workers AI account** — where the model actually runs. Free tier.
- **A browser.**

That is the whole list. Nothing from Anthropic: no Claude, no Claude Code, no key of
theirs, no call to them. Claude Code *wrote* this code; it is not *in* it. Delete Claude
Code from this Mac and the coach runs exactly the same.

(`CLAUDE.md` in this folder is the build brief. It is read while building, never at runtime.)

## L0 — the model

There is no model on this laptop. The coach sends each turn to Cloudflare Workers AI and
gets a question back. Rented, stateless, and the only layer that isn't mine.

Setup, once:

1. **Account ID** — go to https://dash.cloudflare.com → **Workers & Pages**. The Account ID
   is in the right-hand sidebar. Copy it.
2. **API token** — **My Profile → API Tokens → Create Token** → use the **Workers AI**
   template. Copy the token now: Cloudflare shows it exactly once.
3. Copy `.env.example` to `.env` and paste both values in.
4. Check the account is on the **Workers Free** plan.

Step 4 is the one that matters most. On the free plan, running out returns an error. That is
the whole safety mechanism behind "this must be free to run".

### The free allowance

10,000 neurons a day, resetting at midnight UTC — about 11 cents of compute, which is two
to four full coaching sessions. Each turn re-sends the conversation so far, so a long
session costs more than a short one. Run out and the coach says so and waits for tomorrow.

### Swapping the brain

One line near the top of `coach.py`:

```python
MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
```

Change that line and every other layer carries on unchanged. That is what building in
layers buys.

## Build phases

- [x] **Phase 1 — L0 speaks.** Cloudflare account, token, `.env`, and a ten-line script that
      asks one question and prints the answer. **Done** — the model answered from Python.
- [x] **Phase 2 — the loop and the app.** `coach.py` + `index.html`: context assembly (L1),
      three tools (L2), running them (L3), the loop (L4). A full session in the browser.
- [x] **Phase 3 — memory (L5).** Ending a session writes a summary and any stuck-pattern,
      and the next session opens carrying both.
- [x] **Phase 4 — hardening (L4 + L8).** Advice gets bounced and re-asked; off-record leaves
      no trace; a cap of five model calls without me; the server binds to localhost only.
- [x] **Phase 5 — the second loop (L9).** The coach proposes one edit to its own
      instructions, shown as a diff. It only changes if I click Approve.
- [x] **Phase 6 — the launcher.** `Start Coach.command`, double-clickable. Built out of
      order, on purpose: without it, running the coach means typing terminal commands, and
      the whole point is that it shouldn't.

L6 (planning) and L7 (delegation) are deliberately not built. A coach that plans ahead or
hands off isn't a coach.

All six are written and tested. What none of it has done yet is meet the real model — every
test used a stub. The first honest run is the first time I open it.

## A session, start to finish

1. Double-click **`Start Coach.command`**. A browser tab opens and the coach asks something.
2. Answer. It asks again. It cannot do anything else — if it states rather than asks, the
   code re-prompts it twice and then shows the reply flagged in amber.
3. Say you want to go off the record and it stops recording, permanently for that session.
   An amber pill appears in the header. Nothing after that point is written down, and none
   of it is shown to the model that writes the summary.
4. Click **End session** when you're done — only you can end it. It writes a summary and,
   if it noticed one, a stuck-pattern.
5. It then proposes **one** change to its own coaching style, as a diff, with Approve and
   Veto. Approve rewrites `memory/instructions.md`. Veto writes nothing.

## Watching it work

There's a panel down the right-hand side — **Hide the works** in the header turns it off,
and it remembers which way you left it.

The top half is the stack itself: L0 to L9, lighting up as each layer does something, with
a running count of how many times it has fired this session. L6 and L7 sit there greyed out
and struck through, saying why they aren't built. An absence you can see is a decision; an
absence you can't is an oversight.

The bottom half is the trace: every layer says, in one line, what it just did. A turn where
the coach tried to give advice reads like this —

```
L4  lap — 1 of 5 allowed without you
L1  assembled — 4,668 chars — constitution 808 · style 619 · log 2500 · stuck 68
                · 9 msgs so far · session-log cut to the last 2500
L0  answered — llama-3.3-70b-instruct-fp8-fast · 1.84s · 1420 tokens in, 24 out
L4  parse — envelope found inside 29 chars of surrounding prose
L4  bounced — not a question — nudging it, 1 of 2
L4  lap — 2 of 5 allowed without you
...
L2  asked — the envelope came back as a question — that convention is L2
L8  ledger — transcript 10 msgs · recordable 10 msgs
```

That `bounced` line used to be invisible: the question-checker did its job silently, so the
only ones I ever saw were the failures it couldn't fix. It is the house rule with its
sleeves rolled up — the constitution *asks* for a question, and those six lines of Python
*require* one.

Any line with a `⌄` opens. Click the `L1` line and you get the entire context that went to
the model, verbatim — every character it could see before it wrote a word. Click `L0` and
you get the raw reply, before anything parsed it.

Two lines are worth watching in particular:

- **`L1 assembled`** — the number climbs every turn, because every turn re-sends the whole
  conversation. That is the free allowance draining, in real time, and it is why the memory
  files are cut to the last 2,500 characters.
- **`L8 ledger`** — two counts that normally match. Go off the record and they stop
  matching, and the gap between them is exactly the material the closing summary will never
  be shown.

**The trace is never written down.** Not to a file, not to a log, not to the browser's
storage — only the show/hide preference is remembered. It lives in memory for one turn, goes
to the page once, and is gone when the tab closes. It has to work that way: while I'm off
the record the transcript is still being sent to the model, so it still appears in the `L1`
detail. Anything that persisted the trace would be a hole straight through "off the record",
so nothing does — and nothing should be added that does.

## How new builds arrive

`Start Coach.command` runs `git pull` before it starts the coach. So double-clicking it
both updates the code and runs it — there's no separate "download the new version" step,
and no terminal. If the pull fails (no internet, local edits), it says so and runs the
version already on the Mac rather than refusing to start.

`memory/instructions.md` is the exception, and it has to be. It's tracked — watching the
coaching style change over time *is* Phase 5 — but the coach also rewrites it whenever I
approve an L9 edit, and git won't update a folder with a tracked file sitting dirty. So the
second loop working was quietly what stopped new builds arriving; the coach improving
itself was the reason it could never be improved.

The launcher now copies that file aside, updates, and puts it back. If an update ever
changes the starter style too, mine wins outright: the version in the repo is a seed, mine
is what the sessions have shaped. Any *other* tracked file being edited by hand still stops
the update and says so — an unexplained change to the program should be announced, not
quietly pocketed.

## What stays on this Mac

`.gitignore` keeps three things out of this public repo, permanently:

- `.env` — the Cloudflare keys.
- `memory/session-log.md` — what I actually talked about.
- `memory/stuck-patterns.md` — where I get stuck.

Those were ignored from the first commit, not added later. Git history is permanent: a file
pushed once and deleted afterwards is still sitting in the log where anyone can pull it back.
"Off the record" only means something if it was never pushed in the first place.

`memory/instructions.md` **is** in the repo. That is the coaching style, not a record of
anything I said — and watching it change over time is the whole of Phase 5.

## Layout

```
coach/
├─ CLAUDE.md              the build brief
├─ README.md              this file
├─ .env                   Cloudflare keys — never committed
├─ .env.example           the key names, no values
├─ coach.py               the agent: L1, L2, L3, L4, L5, L8, L9
├─ index.html             the chat page — a window onto the agent, not the agent
├─ Coach.app              the app: double-click this one
├─ Start Coach.command    the same thing, as a visible script
└─ memory/
   ├─ instructions.md     L9 — coaching style, evolves with my approval
   ├─ session-log.md      L5 — session summaries
   └─ stuck-patterns.md   L5 — where I get stuck
```

`session-log.md` and `stuck-patterns.md` don't exist until the first session ends — the
coach creates them. Everything else is there from the clone.
