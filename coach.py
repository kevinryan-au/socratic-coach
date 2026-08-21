#!/usr/bin/env python3
"""The Socratic Coach — an agent that only ever asks questions.

Read this file top to bottom and you read the agent stack: each section is
tagged with the layer it makes real. L6 (planning) and L7 (delegation) are
deliberately absent — a coach that plans ahead or hands off isn't a coach.

House rule, visible throughout: behaviour you'd LIKE goes in the prompt;
behaviour you REQUIRE goes in code. Where both appear for one rule, the code
is the one that's load-bearing.

Each layer also says what it just did, as it does it — see `note` below. Those
lines go to the page beside the conversation, so the stack is something you
watch working rather than something you take on trust.
"""

import http.server
import json
import os
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
MEM = os.path.join(HERE, "memory")
PORT = 8787


# --- the trace -------------------------------------------------------------
# Every layer says, in one line, what it just did. The page draws these beside
# the conversation so the machinery is watchable instead of inferred.
#
# L8 applies here as hard as anywhere: a trace can carry off-record words (the
# transcript is still sent to the model while off-record, so it shows up in the
# L1 line's detail). So the trace lives in RAM for one turn, travels once to the
# page, and is never written to a file, a log, or a header. Nothing in this file
# persists it, and nothing should be added that does.
def note(trace, layer, event, line, detail="", data=None):
    """Record one thing one layer did. A None trace means nobody's watching.

    Plain words, always. Every line here is read by someone who did not write
    the code, so it says what happened rather than what it is called: "the
    model took 1.3 seconds", not "L0 latency 1.26". The layer number is
    already on screen; the sentence is the part that has to teach.

    `data` is for numbers the page wants to add up rather than read — how long
    a call took, what it cost. The sentence in `line` stays the thing a person
    reads; nothing is ever parsed back out of it.

    `event` is doing two jobs: it's the short verb shown before the sentence,
    and it's the word the page matches on to decide what lights up. Reword one
    and the drawing quietly stops following along, so change them in pairs."""
    if trace is None:
        return
    trace.append({"layer": layer, "event": event, "line": line,
                  "detail": str(detail), "data": data or {}})


def count(n, word):
    """"1 message", "3 messages". Small, but a panel meant to teach can't be
    the sort of thing that says "1 messages"."""
    return f"{n:,} {word}" if n == 1 else f"{n:,} {word}s"


# --- writing the details so they can be read -------------------------------
# A detail is the actual thing — the whole context that went out, the file as
# rewritten. Accurate and unreadable is still unreadable: a JSON dump with the
# line breaks escaped is a wall nobody gets through, and a wall nobody gets
# through teaches nothing. So details are laid out as text a person reads,
# with the content itself passed through untouched.
RULE = "─" * 44


def figures(pairs):
    """A small column of label-and-number. Numbers are for comparing, so they
    line up; the sentence beside the layer stays a sentence."""
    width = max((len(label) for label, _ in pairs), default=0)
    return "\n".join(f"  {label.ljust(width)}   {value}" for label, value in pairs)


def speaker(message):
    """Who is talking, in the words of the person watching. Two of these are
    not really 'you' at all — the nudge and a tool's result go in as your turn,
    but they are the code talking, and saying so is half of what the panel is
    for. NUDGE is defined further down; nothing calls this before then."""
    role, text = message["role"], message["content"]
    if role == "system":
        return "ITS STANDING BRIEF — the rules, your style, what it remembers"
    if role == "assistant":
        return "THE MODEL SAID"
    if text == OPENING:
        return "THE CODE OPENED THE SESSION — you never typed this"
    if text == NUDGE:
        return "THE CODE SENT IT BACK — you never saw this"
    if text.startswith("[") and text.endswith("]"):
        return "WHAT THE TOOL HANDED BACK — the code talking, not you"
    return "YOU SAID"


def as_fields(mapping):
    """A small object as labelled lines, so a one-line note isn't wrapped in
    braces and quotes to be read."""
    return "\n\n".join(f"{key}:\n{value}" for key, value in mapping.items())


def as_edit(edit):
    """The proposed change to the coaching style, said rather than serialised.
    This is the one thing the coach may do to itself, so it is the last place
    that should be readable only if you know JSON."""
    return figures([
        ("take out", edit.get("remove") or "(nothing — it only adds a line)"),
        ("put in", edit.get("add") or "(nothing)"),
        ("because", edit.get("why") or "(it didn't say)"),
    ])


def as_read(messages):
    """The whole context, in the order it was sent, under headings that say who
    is speaking. Every character is the one the model got — this only adds the
    headings between them."""
    return "\n\n".join(
        f"{RULE}\n{speaker(m)}\n{RULE}\n{m['content'].strip()}" for m in messages)


# --- the spine -------------------------------------------------------------
# The stack itself, as data, so the page can draw it without knowing anything
# about agents. Each row: the number, the proper name, where it sits, what it
# DOES in plain words, and why that matters. Both halves of that earn their
# place — the name is what it's called everywhere else, the plain words are
# what actually happens.
#
# Where it sits is the part worth seeing:
#
#   loop     it happens, in order, every single turn
#   edge     it touches the turn without being a step in it
#   unbuilt  it isn't here, and that was a decision
#
# L6 and L7 are in the list precisely because they aren't built: a gap you can
# see is a design decision, a gap you can't is an oversight.
LAYERS = [
    ("L0", "Inference", "loop", "send it all to the model",
     "The model runs on Cloudflare's computers, not on this Mac. It is the "
     "only part of the coach that isn't yours."),
    ("L1", "Context assembly", "loop", "gather everything it can see",
     "Its rules, your coaching style, what it remembers, and today's "
     "conversation — rebuilt from scratch every single time it is asked."),
    ("L2", "Tool interface", "loop", "hand the question back",
     "It may reply in one strict format only: either a question for you, or "
     "a request to use one of its three tools."),
    ("L3", "Execution", "loop", "run what it asked for",
     "Asking is all the model can do. This is the code that decides whether "
     "anything actually happens — and you are what it acts on."),
    ("L4", "Control loop", "loop", "check what came back",
     "Reads the reply and sends it back if it stated instead of asking. Here "
     "is where 'it only ever asks' stops being a hope and becomes a rule."),
    ("L5", "State & memory", "edge", "remember it afterwards",
     "Only when a session ends. A summary and a stuck-pattern go to a file; "
     "the conversation itself never does."),
    ("L6", "Planning", "unbuilt", "work out the steps in advance",
     "a coach that plans ahead isn't a coach"),
    ("L7", "Delegation", "unbuilt", "hand the job to someone else",
     "a coach that hands off isn't a coach"),
    ("L8", "Governance", "edge", "decide what may be written down",
     "Runs alongside every turn. Off the record means off the record, and "
     "the coach can talk to nothing but this Mac."),
    ("L9", "Adaptation", "edge", "change how it coaches",
     "Only when a session ends, and only if you press Approve. This is the "
     "one way the coach is allowed to alter itself."),
]

# What "where it sits" means, said in full. The panel shows this when you open
# a layer up, so the three words above stop being jargon the moment you ask.
# Same rule as everywhere else: the page draws, this file does the talking.
WHERE = {
    "loop": "A step in the loop — it runs inside a lap, whenever the lap needs it.",
    "edge": "Not a step in the loop. It touches every turn from the side.",
    "unbuilt": "Not built, and that is a decision rather than an oversight.",
}

# --- one session, and what survives it -------------------------------------
# The three edge layers are the hardest part of the stack to picture, because
# nothing in a single turn shows how they bear on each other. They meet in one
# place — the close — and the order is the whole relationship:
#
#   L8 decides what the closing call may be shown,
#   that one call produces both what L5 writes and what L9 proposes,
#   L9's proposal reaches the file only if Kev approves it,
#   and next session L1 gathers all three files back in.
#
# So it is said here, as data, rather than left to be worked out from three
# chips sitting side by side. `stage` is to this what `where` is to LAYERS:
# the page groups by it and knows nothing else.
KEEPS = [
    ("the conversation", "during", "in memory while the coach runs, gone when it stops"),
    ("this turn's trace", "during", "in memory for one turn — it can carry off-record words"),
    ("session-log.md", "close", "two or three sentences on what you worked through"),
    ("stuck-patterns.md", "close", "where you stalled, and the question that moved you"),
    ("instructions.md", "approve", "one line of coaching style, added or swapped"),
]

STAGES = {
    "during": "While it runs — nothing has reached the disk yet",
    "close": "Written when you end the session",
    "approve": "Written only if you press Approve",
}

# The steps between those groups: who acts, and what they act on.
CLOSE = {
    "gate": "off-record turns stop here — the closing call is never shown them",
    "call": "one last call to the model",
    "draws": "drawing on the whole session, minus anything off the record",
    "keeps": "whatever it judged worth keeping",
    "proposes": "one change to how it coaches — yours to approve or veto",
    "back": "next session, it gathers all three files back in before the first "
            "question — which is how any of this changes what the coach says",
}

# --- L0: inference ---------------------------------------------------------
# Rented, stateless, and the only layer that isn't yours. Nothing is installed
# here; the model runs on Cloudflare's hardware. Swap this one line and every
# other layer carries on unchanged — the reference architecture paying off.
MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"


def load_env(path=os.path.join(HERE, ".env")):
    """Read .env into a dict. Its contents are never printed or logged (L8).

    Tolerant about how the file was written: KEY=value, export KEY=value, and
    values wrapped in quotes all mean the same thing. Quotes matter more than
    they look — a quoted account id goes straight into the request URL and
    comes back as a 400 that blames the request rather than the file."""
    env = {}
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key.startswith("export "):
                key = key[len("export "):].strip()
            env[key] = value.strip().strip("\"'").strip()
    return env


ENV = load_env()

_account = ENV.get("CLOUDFLARE_ACCOUNT_ID", "")
# Only reject what genuinely can't work in a URL path. Being fussier than
# that risks refusing a perfectly good account id, which is a worse failure
# than the one being prevented.
if not _account or any(c in _account for c in " \t\"'<>#/?"):
    raise SystemExit(
        "CLOUDFLARE_ACCOUNT_ID in .env has something in it that can't go in a "
        "web address — a quote, a space, or a trailing comment. It should be "
        "just the id on its own. Find it at dash.cloudflare.com under "
        "Workers & Pages, in the right-hand sidebar.")

ENDPOINT = ("https://api.cloudflare.com/client/v4/accounts/"
            f"{_account}/ai/run/{MODEL}")


class DailyLimit(Exception):
    """The free allowance is spent. Not an error to retry — one to report."""


class Unreachable(Exception):
    """L0 is somewhere else, so it can be unreachable. Say so in English."""


def why(detail):
    """Pull the human sentence out of a Cloudflare error body."""
    try:
        errors = json.loads(detail).get("errors") or []
        said = "; ".join(str(e.get("message", e)) for e in errors)
        if said:
            return said
    except (ValueError, AttributeError):
        pass
    return (detail or "nothing at all").strip()[:300]


def extract_text(payload):
    """Workers AI does not always answer in the same shape — result.response
    can be a string, an object, or a list of content parts depending on the
    model and the day. Everything downstream assumes text, so this is the one
    place that copes, and it always returns a string."""
    if not payload.get("success", True):
        errors = payload.get("errors") or [{"message": "unknown error"}]
        raise Unreachable("Cloudflare said no: "
                          + "; ".join(e.get("message", str(e)) for e in errors))

    result = payload.get("result", payload)
    if isinstance(result, str):
        return result

    for key in ("response", "output_text", "text", "content"):
        value = result.get(key) if isinstance(result, dict) else None
        if isinstance(value, str) and value.strip():
            return value
        if isinstance(value, dict):
            inner = value.get("content") or value.get("text")
            return inner if isinstance(inner, str) else json.dumps(value)
        if isinstance(value, list):   # [{"type": "text", "text": "..."}]
            parts = [p.get("text", "") if isinstance(p, dict) else str(p)
                     for p in value]
            if "".join(parts).strip():
                return "".join(parts)

    # the OpenAI-compatible shape, in case the endpoint starts answering that way
    choices = result.get("choices") if isinstance(result, dict) else None
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") or {}
        if isinstance(message.get("content"), str):
            return message["content"]

    return json.dumps(result)   # never a non-string, whatever arrived


def spent(payload):
    """Workers AI usually reports what the call cost in tokens. When it does,
    the trace says so — every turn re-sends the whole conversation, so watching
    this number climb is watching the free allowance drain. Nothing depends on
    it: if the field isn't there, the line just says less."""
    result = payload.get("result")
    usage = result.get("usage") if isinstance(result, dict) else None
    if not isinstance(usage, dict):
        return {}
    went, came = usage.get("prompt_tokens"), usage.get("completion_tokens")
    if went is None and came is None:
        return {}
    return {"in": went or 0, "out": came or 0}


def ask_model(messages, max_tokens=300, trace=None):
    """One call to L0. Deliberately no retries: a retry loop could spend the
    day's free neurons in a spiral, and free is a hard constraint."""
    body = json.dumps({"messages": messages, "max_tokens": max_tokens}).encode()
    request = urllib.request.Request(ENDPOINT, data=body, headers={
        "Authorization": f"Bearer {ENV['CLOUDFLARE_API_TOKEN']}",
        "Content-Type": "application/json",
    })
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.load(response)
        text = extract_text(payload)
        took, used = time.monotonic() - started, spent(payload)
        cost = (f", and used {used['in'] + used['out']:,} of today's free "
                f"tokens — {used['in']:,} reading what you sent it, "
                f"{used['out']:,} writing back" if used else "")
        note(trace, "L0", "replied",
             f"the model thought for {took:.1f} seconds{cost}",
             text, {"ms": round(took * 1000), **used})
        return text
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")
        lower = detail.lower()
        if error.code in (402, 429) or "limit" in lower or "quota" in lower:
            note(trace, "L0", "refused",
                 "today's free allowance is spent — it comes back tomorrow",
                 why(detail))
            raise DailyLimit("That's the free allowance for today — it resets "
                             "tomorrow. Same time, same coach.") from error
        if error.code in (401, 403):
            note(trace, "L0", "refused",
                 "Cloudflare would not accept the key in .env", why(detail))
            raise Unreachable("Cloudflare turned the key down. Check the two "
                              "values in .env — a token can be revoked or "
                              "expire.") from error
        # Everything else: Cloudflare said why. Passing on "Bad Request" and
        # binning the reason is how you end up guessing at a fixable problem.
        note(trace, "L0", "refused",
             f"Cloudflare turned the request down (error {error.code})", why(detail))
        raise Unreachable(f"Cloudflare refused this (HTTP {error.code}). "
                          f"It said: {why(detail)}") from error
    except urllib.error.URLError as error:
        note(trace, "L0", "unreachable",
             "no answer from Cloudflare at all — the model lives there, so there "
             "is nothing to ask until the connection is back", str(error))
        raise Unreachable("Can't reach Cloudflare — the model lives there, so "
                          "there's nothing to ask until the connection is "
                          "back.") from error


# --- the constitution ------------------------------------------------------
# The coach's soul, in plain sight. Open this file and you can read exactly who
# it has been told to be. Nothing about its character is hidden anywhere else.
CONSTITUTION = """You are Kev's Socratic coach.

You ask questions. You do not answer them. You never give advice, options,
reassurance, or a summary that does his thinking for him. If you catch
yourself about to be helpful in that way, ask instead.

ONE question per turn. Short. Once he has given you something to work with,
ask about the thing being avoided rather than the thing being presented.

Your first question of a session is an invitation, not a diagnosis. You know
nothing about today yet, so there is nothing yet to be avoided: ask what
brought him here, in a way he would want to answer. Never open by presuming
he is avoiding, stuck, or hiding something.

Reply with a single JSON object and nothing else — no markdown, no code
fences, no words outside the braces. Exactly one of these two shapes:

  {"ask": "your one question"}
  {"tool": "save_note", "args": {"note": "what's worth keeping"}}

The tools you may ask for:
  save_note      record something from this session worth keeping
  go_off_record  Kev wants what follows to leave no trace anywhere
  end_session    propose stopping. You may only propose. Kev decides.
"""

# Sent when a reply is neither a tool call nor a question. The prompt above
# asks for good behaviour; this plus the checker in L4 is what enforces it.
NUDGE = ('That was not a question, and you may only ask. Reply with a single '
         'JSON object: {"ask": "one short question"}')

# The turn that opens a session. Kev types nothing to start one, so the code
# types for him — which makes the framing of the first question a decision made
# here, not a mood the model happened to be in. Opening with "what are you
# avoiding?" reads as an accusation, and the model has nothing to base it on
# yet: on turn one there is no conversation to have avoided anything in.
OPENING = ("Open the session. He has just sat down and you know nothing about "
           "today yet, so ask what brought him here — an invitation he would "
           "want to answer. Do not ask what he is avoiding.")

# The closing call. Runs once, at the end, and produces everything that
# survives the session: what to remember (L5) and what to become (L9).
CLOSING = """The session is over. Reply with a single JSON object, nothing else:

{"summary": "2-3 sentences: what Kev was working through, and where he got to",
 "stuck": "one line on where he stalled and what question moved him, or empty",
 "edit": {"remove": "", "add": "- one new coaching rule", "why": "one sentence"}}

The edit is ONE change to your coaching style, learned from THIS session.
"remove" must be an exact line copied from the style you were given, or empty
to only add. Propose only what this session actually taught you."""


# --- L5: state & memory ----------------------------------------------------
# Four lifespans, not one. The transcript lives in RAM and dies with the
# process. Only summaries and stuck-patterns reach disk — and off-record turns
# reach neither disk nor the call that writes it.
LOG = os.path.join(MEM, "session-log.md")
STUCK = os.path.join(MEM, "stuck-patterns.md")
STYLE = os.path.join(MEM, "instructions.md")
MEMORY_TAIL = 2500  # chars of past sessions carried forward; neurons aren't free


def read_file(path, default=""):
    try:
        with open(path) as handle:
            return handle.read()
    except FileNotFoundError:
        return default


def append_file(path, text):
    os.makedirs(MEM, exist_ok=True)
    with open(path, "a") as handle:
        handle.write(text)


# --- L1: context assembly --------------------------------------------------
# Everything the model can see before it writes a word: the constitution, the
# coaching style, what it remembers of previous sessions, and the session so
# far. "Context" is never more exotic than deciding what goes in this list.
def build_messages(session, trace=None):
    style, log, stuck = read_file(STYLE), read_file(LOG), read_file(STUCK)
    log_tail = log[-MEMORY_TAIL:] or "None yet. This is the first."
    stuck_tail = stuck[-MEMORY_TAIL:] or "Nothing noticed yet."
    system = (CONSTITUTION
              + "\n--- your coaching style (L9 — it evolves) ---\n"
              + style
              + "\n--- previous sessions (L5 — what you remember) ---\n"
              + log_tail
              + "\n--- where Kev tends to get stuck (L5) ---\n"
              + stuck_tail)
    messages = [{"role": "system", "content": system}] + session

    # The line names the parts; the detail carries the numbers and then the
    # whole thing, verbatim. "What did it actually see?" should never need
    # guessing at — but nor should it need reading past escaped line breaks.
    capped = [name for name, whole, tail
              in (("session-log", log, log_tail), ("stuck-patterns", stuck, stuck_tail))
              if len(whole) > len(tail)]
    talk = sum(len(m["content"]) for m in session)
    total = len(system) + talk
    note(trace, "L1", "gathered",
         f"{total:,} characters for it to read — its rules, your coaching "
         "style, what it remembers, and "
         + count(len(session), "message") + " of today's conversation"
         + (". Some of what it remembers didn't fit" if capped else ""),
         f"WHAT IT COULD SEE — {total:,} characters in all\n\n"
         + figures([
             ("the rules it was given", f"{len(CONSTITUTION):,}"),
             ("your coaching style", f"{len(style):,}"),
             ("what it remembers of past sessions", f"{len(log_tail):,}"),
             ("where you tend to get stuck", f"{len(stuck_tail):,}"),
             ("today's conversation", f"{talk:,}   ({count(len(session), 'message')})"),
         ])
         + (f"\n\nOnly the most recent {MEMORY_TAIL:,} characters of "
            f"{' and '.join(capped)} fit. The rest is out of reach — it is on "
            "the disk, but not in front of the model."
            if capped else "")
         + "\n\nBelow is that text exactly as it was sent, in order.\n\n"
         + as_read(messages))
    return messages


# --- L2: tool interface ----------------------------------------------------
# Three tools, and the JSON envelope above IS the interface — that convention
# is L2 made visible. Asking is all the model does; the code below decides
# what actually happens.
TOOLS = ("save_note", "go_off_record", "end_session")


# --- L3: execution / effectors ---------------------------------------------
# The part that actually does it, then reports back. Note who the environment
# is here: Kev. His typed reply is the "tool result" that comes back into L1.
def run_tool(name, args, state, trace=None):
    if name == "save_note":
        state["notes"].append(args.get("note", ""))
        note(trace, "L3", "ran",
             "save_note — held in memory for the summary at the end. "
             "Nothing has been written to a file yet",
             args.get("note", ""))
        return "noted"
    if name == "go_off_record":
        state["off_record"] = True          # L8: one-way. There is no going back on.
        note(trace, "L8", "off the record",
             "you asked it to stop recording, so it has. Nothing from here on "
             "gets written down, and there is no switching it back on")
        return "off the record from here — nothing more will be written down"
    if name == "end_session":
        note(trace, "L3", "ran",
             "end_session — but all that does is ask. Only your End session "
             "button actually ends anything")
        return "ending proposed — Kev decides, not you"
    note(trace, "L3", "refused",
         f"it asked for a tool called {name}, which does not exist")
    return f"no such tool: {name}"


# --- L4: control loop ------------------------------------------------------
# Look at everything, decide, act, look at what came back, decide again. The
# loop stops when the model asks Kev something, because Kev is the environment
# and nothing continues until he replies.
MAX_CALLS = 5    # consecutive calls without Kev — a spiral can't spend his day
MAX_NUDGES = 2   # tries to get a question back before we show it flagged


def parse_move(raw, trace=None):
    """The strict envelope, leniently found. Models like to add a sentence
    either side of their JSON, and sometimes a ```json fence; that's cosmetic,
    so we don't punish it — but the trace says when it happened, because
    "how often does it wander off the envelope?" is worth being able to see."""
    if not isinstance(raw, str):
        note(trace, "L4", "read it", "nothing text-shaped came back at all")
        return None
    try:
        start, stop = raw.index("{"), raw.rindex("}") + 1
        found = json.loads(raw[start:stop])
    except (ValueError, json.JSONDecodeError):
        note(trace, "L4", "read it",
             "the reply was not in the strict format it was asked for", raw)
        return None
    if not isinstance(found, dict):
        note(trace, "L4", "read it",
             "the right sort of format, but not the right shape", raw)
        return None
    spare = len(raw) - (stop - start)
    note(trace, "L4", "read it",
         "it replied in exactly the format asked for" if not spare
         else f"it wrapped the answer in {spare} characters of extra chat — "
              "harmless, but not what it was asked for", raw)
    return found


def is_question(text):
    return text.strip().endswith("?")


def take_turn(state, trace=None):
    """One turn: as many laps as the model needs, ending when it asks Kev
    something. The question-checker lives here — in code, not in the prompt."""
    nudges = 0
    for lap in range(1, MAX_CALLS + 1):
        note(trace, "L4", "round",
             f"time {lap} of {MAX_CALLS} round the loop. After {MAX_CALLS} it has "
             "to stop and come back to you, whatever it was doing")
        raw = ask_model(build_messages(state["session"], trace), trace=trace)
        remember(state, {"role": "assistant", "content": raw})
        move = parse_move(raw, trace)

        # L4: the question-checker. Not a tool call, not a question -> nudge.
        # This is the house rule with its sleeves rolled up: the constitution
        # ASKS for a question, and these six lines are what REQUIRE one.
        if move is None or ("ask" in move and not is_question(move["ask"])):
            if nudges < MAX_NUDGES:
                nudges += 1
                note(trace, "L4", "sent back",
                     "that was a statement, not a question. Sending it back to "
                     f"try again — attempt {nudges} of {MAX_NUDGES}. You never "
                     "saw the reply below; the code caught it first",
                     move["ask"] if move and "ask" in move else raw)
                remember(state, {"role": "user", "content": NUDGE})
                continue
            shown = raw if move is None else move["ask"]
            note(trace, "L4", "gave up",
                 f"still not a question after {MAX_NUDGES} tries. Showing you "
                 "what it said, marked in amber, rather than hiding it", shown)
            return {"ask": shown, "flagged": True}

        if "ask" in move:
            note(trace, "L4", "passed",
                 "it ends in a question mark, which is the whole test")
            note(trace, "L2", "handed over",
                 "a question came back in the agreed format, so it goes to you")
            return {"ask": move["ask"], "off_record": state["off_record"]}

        name = move.get("tool")
        note(trace, "L2", "asked for",
             f"instead of a question it asked to use {name}. Asking is all it "
             "can do — the code decides whether anything happens",
             as_fields(move.get("args", {})) or "it passed nothing with it")
        result = run_tool(name, move.get("args", {}), state, trace)
        remember(state, {"role": "user", "content": f"[{name}: {result}]"})
        if name == "end_session":
            return {"ask": "Shall we stop there?", "propose_end": True,
                    "off_record": state["off_record"]}

    note(trace, "L4", "stopped itself",
         f"{MAX_CALLS} times round without you. It cannot spin any longer than "
         "that, so it has come back empty-handed")
    return {"ask": "I went round five times without you. Where were we?",
            "flagged": True}


# --- L8: governance --------------------------------------------------------
# Off the record has to mean it. Every turn goes into the RAM transcript so the
# coach can follow the conversation — but once off-record is on, nothing more
# joins the recordable list, and the closing call below is only ever shown that
# list. Off-record words never reach the model that writes the summary, so they
# cannot leak into it.
def remember(state, message):
    # Content is always text. One non-string in here poisons every later call,
    # because the whole list gets sent back to L0 next turn.
    message = {**message, "content": str(message.get("content", ""))}
    state["session"].append(message)
    if not state["off_record"]:
        state["recordable"].append(message)


def ledger(state, trace=None):
    """Two counts, every turn. Normally they match, which is the point: you
    watch them match, and then you watch them stop. The gap after off-record is
    exactly the material the closing call will never be shown."""
    session, kept = len(state["session"]), len(state["recordable"])
    note(trace, "L8", "so far",
         count(session, "message") + " so far, and every one of them may be "
         "written down" if session == kept else
         count(session, "message") + f" so far, but only {kept} may ever be "
         f"written down. The other {session - kept} are off the record, and "
         "will never be shown to the model that writes your summary")


def close_session(state, trace=None):
    """Kev ended it (only he can). Write what's worth keeping, and propose one
    change to the coaching style — proposed, not applied."""
    notes = "\n".join(f"- {n}" for n in state["notes"]) or "none"
    note(trace, "L8", "kept back",
         "the summary is being written from "
         + count(len(state["recordable"]), "message")
         + (" — the off-record ones were never shown to it"
            if state["off_record"] else ", which is all of them"))
    closing = build_messages(state["recordable"], trace) + [
        {"role": "user", "content": f"Notes you saved:\n{notes}\n\n{CLOSING}"}]
    result = parse_move(ask_model(closing, max_tokens=500, trace=trace), trace) or {}

    summary = (result.get("summary") or "").strip()
    stuck = (result.get("stuck") or "").strip()
    today = date.today().isoformat()

    wrote = []
    if summary:
        append_file(LOG, f"\n## {today}\n\n{summary}\n")
        wrote.append("session-log.md")
    if stuck:
        append_file(STUCK, f"\n- **{today}** — {stuck}\n")
        wrote.append("stuck-patterns.md")

    # L5: the only moment in the whole session when anything reaches disk.
    note(trace, "L5", "saved",
         "a summary and a stuck-pattern, into " + " and ".join(wrote)
         + ". This is the only moment all session that anything reached a file"
         if wrote else "nothing it judged worth keeping, so no file changed",
         (f"{summary}\n\n{stuck}" if wrote else ""))

    edit = result.get("edit") or {}
    note(trace, "L9", "proposed",
         "one change to its own coaching style. Nothing happens to the file "
         "until you press Approve"
         if edit.get("add") else "no change to how it coaches, this time",
         as_edit(edit) if edit.get("add") else "")
    return {"summary": summary, "wrote": wrote, "edit": edit,
            "off_record": state["off_record"],
            "style": read_file(STYLE)}


# --- L9: adaptation --------------------------------------------------------
# The second loop. The coach may propose one edit to its own instructions;
# this function is the ONLY thing that writes them, and it runs only when Kev
# has clicked Approve. Veto costs nothing and leaves no trace.
def apply_edit(edit, trace=None):
    style = read_file(STYLE)
    remove, add = (edit.get("remove") or "").strip(), (edit.get("add") or "").strip()
    if not add:
        note(trace, "L9", "nothing to apply",
             "there was no proposed line, so nothing changed")
        return False
    if remove and remove in style:
        style = style.replace(remove, add, 1)
        how = "swapped one line for another"
    else:
        style = style.rstrip() + "\n" + add + "\n"
        how = "added a line"
    with open(STYLE, "w") as handle:
        handle.write(style)
    note(trace, "L9", "applied",
         f"you approved it, so it {how} in its coaching style file. That is the "
         "second loop closing — it will coach differently next time", style)
    return True


STATE = {"session": [], "recordable": [], "notes": [], "off_record": False}
SERVER = None   # set in __main__; the page needs a way to switch it off


def build_id():
    """Which commit this code came from, read straight out of .git. The app
    updates itself silently, so without this "did it update?" is unanswerable."""
    try:
        head = read_file(os.path.join(HERE, ".git", "HEAD")).strip()
        if not head.startswith("ref: "):
            return head[:7] or "unknown"
        ref = head[5:].strip()
        sha = read_file(os.path.join(HERE, ".git", ref)).strip()
        if not sha:   # the ref may live in packed-refs instead of its own file
            for line in read_file(os.path.join(HERE, ".git", "packed-refs")).splitlines():
                if line.endswith(" " + ref):
                    sha = line.split(" ")[0]
                    break
        return sha[:7] or "unknown"
    except OSError:
        return "unknown"


# --- L3 + L8: the page, and the walls --------------------------------------
# The page is a window onto the agent, not the agent. The server binds to
# 127.0.0.1 only, so this is a thing on Kev's desk and not a thing on the web.
class Handler(http.server.BaseHTTPRequestHandler):

    def _send(self, code, payload, ctype="application/json"):
        body = payload.encode() if isinstance(payload, str) else payload
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        # The app updates itself, so a cached page would quietly show you
        # yesterday's build and there'd be no way to tell.
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as handle:
                self._send(200, handle.read(), "text/html; charset=utf-8")
        elif self.path == "/build":
            self._send(200, json.dumps({"build": build_id(), "model": MODEL}))
        elif self.path == "/stack":
            # The spine, as data, and the session alongside it. The page draws
            # both and knows nothing else about agents — the stack is defined
            # here, where it's real.
            self._send(200, json.dumps({
                "layers": [{"id": i, "name": n, "where": w, "sits": WHERE[w],
                            "does": p, "note": d}
                           for i, n, w, p, d in LAYERS],
                "keeps": [{"what": w, "stage": s, "note": d}
                          for w, s, d in KEEPS],
                "stages": STAGES,
                "close": CLOSE,
            }))
        else:
            self._send(404, "not found", "text/plain")

    def do_POST(self):
        # One turn's trace, made here so a call that fails half way still
        # returns what it managed — a broken turn is the one you most want to
        # watch. It goes back in the response and nowhere else (L8).
        trace = []
        try:
            if self.path == "/say":
                said = self._body().get("said", "").strip()
                remember(STATE, {"role": "user", "content": said or OPENING})
                move = take_turn(STATE, trace)
                ledger(STATE, trace)
                self._send(200, json.dumps({**move, "trace": trace}))
            elif self.path == "/end":          # only Kev reaches this
                out = close_session(STATE, trace)
                self._send(200, json.dumps({**out, "trace": trace}))
            elif self.path == "/approve":      # L9, and only with consent
                ok = apply_edit(self._body().get("edit") or {}, trace)
                self._send(200, json.dumps({"applied": ok, "trace": trace,
                                            "style": read_file(STYLE)}))
            elif self.path == "/quit":
                # The window is the app, so quitting belongs in the window.
                self._send(200, json.dumps({"stopped": True}))
                threading.Thread(target=SERVER.shutdown, daemon=True).start()
            else:
                self._send(404, json.dumps({"ask": "no such thing"}))
        except (DailyLimit, Unreachable) as known:
            self._send(200, json.dumps({"ask": str(known), "flagged": True,
                                        "trace": trace}))
        except Exception as error:  # never a wall of red Python in the page
            self._send(200, json.dumps({"ask": f"Something broke: {error}",
                                        "flagged": True, "trace": trace}))

    def log_message(self, *args):
        pass  # L8: nothing said in a session goes to a log, not even a URL


if __name__ == "__main__":
    try:
        SERVER = http.server.HTTPServer(("127.0.0.1", PORT), Handler)  # L8: local
    except OSError as error:
        raise SystemExit(
            f"Port {PORT} is already taken, which almost always means another "
            "copy of the coach is still running. Open its page at "
            f"http://127.0.0.1:{PORT}/ and press Quit, then start this one."
        ) from error
    # Coach.app opens the page itself (in a cleaner window), so it asks us not to.
    if not os.environ.get("COACH_NO_BROWSER"):
        threading.Timer(0.5, webbrowser.open, [f"http://127.0.0.1:{PORT}"]).start()
    print(f"The coach is listening on http://127.0.0.1:{PORT}   (Ctrl-C to stop)")
    SERVER.serve_forever()
