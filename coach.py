#!/usr/bin/env python3
"""The Socratic Coach — an agent that only ever asks questions.

Read this file top to bottom and you read the agent stack: each section is
tagged with the layer it makes real. L6 (planning) and L7 (delegation) are
deliberately absent — a coach that plans ahead or hands off isn't a coach.

House rule, visible throughout: behaviour you'd LIKE goes in the prompt;
behaviour you REQUIRE goes in code. Where both appear for one rule, the code
is the one that's load-bearing.
"""

import http.server
import json
import os
import threading
import urllib.error
import urllib.request
import webbrowser
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
MEM = os.path.join(HERE, "memory")
PORT = 8787

# --- L0: inference ---------------------------------------------------------
# Rented, stateless, and the only layer that isn't yours. Nothing is installed
# here; the model runs on Cloudflare's hardware. Swap this one line and every
# other layer carries on unchanged — the reference architecture paying off.
MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"


def load_env(path=os.path.join(HERE, ".env")):
    """Read .env into a dict. Its contents are never printed or logged (L8)."""
    env = {}
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip()
    return env


ENV = load_env()
ENDPOINT = ("https://api.cloudflare.com/client/v4/accounts/"
            f"{ENV['CLOUDFLARE_ACCOUNT_ID']}/ai/run/{MODEL}")


class DailyLimit(Exception):
    """The free allowance is spent. Not an error to retry — one to report."""


class Unreachable(Exception):
    """L0 is somewhere else, so it can be unreachable. Say so in English."""


def ask_model(messages, max_tokens=300):
    """One call to L0. Deliberately no retries: a retry loop could spend the
    day's free neurons in a spiral, and free is a hard constraint."""
    body = json.dumps({"messages": messages, "max_tokens": max_tokens}).encode()
    request = urllib.request.Request(ENDPOINT, data=body, headers={
        "Authorization": f"Bearer {ENV['CLOUDFLARE_API_TOKEN']}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)["result"]["response"]
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace").lower()
        if error.code in (402, 429) or "limit" in detail or "quota" in detail:
            raise DailyLimit("That's the free allowance for today — it resets "
                             "tomorrow. Same time, same coach.") from error
        if error.code in (401, 403):
            raise Unreachable("Cloudflare turned the key down. Check the two "
                              "values in .env — a token can be revoked or "
                              "expire.") from error
        raise
    except urllib.error.URLError as error:
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

ONE question per turn. Short. Ask about the thing being avoided rather than
the thing being presented.

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
def build_messages(session):
    system = (CONSTITUTION
              + "\n--- your coaching style (L9 — it evolves) ---\n"
              + read_file(STYLE)
              + "\n--- previous sessions (L5 — what you remember) ---\n"
              + (read_file(LOG)[-MEMORY_TAIL:] or "None yet. This is the first.")
              + "\n--- where Kev tends to get stuck (L5) ---\n"
              + (read_file(STUCK)[-MEMORY_TAIL:] or "Nothing noticed yet."))
    return [{"role": "system", "content": system}] + session


# --- L2: tool interface ----------------------------------------------------
# Three tools, and the JSON envelope above IS the interface — that convention
# is L2 made visible. Asking is all the model does; the code below decides
# what actually happens.
TOOLS = ("save_note", "go_off_record", "end_session")


# --- L3: execution / effectors ---------------------------------------------
# The part that actually does it, then reports back. Note who the environment
# is here: Kev. His typed reply is the "tool result" that comes back into L1.
def run_tool(name, args, state):
    if name == "save_note":
        state["notes"].append(args.get("note", ""))
        return "noted"
    if name == "go_off_record":
        state["off_record"] = True          # L8: one-way. There is no going back on.
        return "off the record from here — nothing more will be written down"
    if name == "end_session":
        return "ending proposed — Kev decides, not you"
    return f"no such tool: {name}"


# --- L4: control loop ------------------------------------------------------
# Look at everything, decide, act, look at what came back, decide again. The
# loop stops when the model asks Kev something, because Kev is the environment
# and nothing continues until he replies.
MAX_CALLS = 5    # consecutive calls without Kev — a spiral can't spend his day
MAX_NUDGES = 2   # tries to get a question back before we show it flagged


def parse_move(raw):
    """The strict envelope, leniently found. Models like to add a sentence
    either side of their JSON; that's cosmetic, so we don't punish it."""
    try:
        return json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        return None


def is_question(text):
    return text.strip().endswith("?")


def take_turn(state):
    """One turn: as many laps as the model needs, ending when it asks Kev
    something. The question-checker lives here — in code, not in the prompt."""
    nudges = 0
    for _ in range(MAX_CALLS):
        raw = ask_model(build_messages(state["session"]))
        remember(state, {"role": "assistant", "content": raw})
        move = parse_move(raw)

        # L4: the question-checker. Not a tool call, not a question -> nudge.
        if move is None or ("ask" in move and not is_question(move["ask"])):
            if nudges < MAX_NUDGES:
                nudges += 1
                remember(state, {"role": "user", "content": NUDGE})
                continue
            shown = raw if move is None else move["ask"]
            return {"ask": shown, "flagged": True}

        if "ask" in move:
            return {"ask": move["ask"], "off_record": state["off_record"]}

        name = move.get("tool")
        result = run_tool(name, move.get("args", {}), state)
        remember(state, {"role": "user", "content": f"[{name}: {result}]"})
        if name == "end_session":
            return {"ask": "Shall we stop there?", "propose_end": True,
                    "off_record": state["off_record"]}

    return {"ask": "I went round five times without you. Where were we?",
            "flagged": True}


# --- L8: governance --------------------------------------------------------
# Off the record has to mean it. Every turn goes into the RAM transcript so the
# coach can follow the conversation — but once off-record is on, nothing more
# joins the recordable list, and the closing call below is only ever shown that
# list. Off-record words never reach the model that writes the summary, so they
# cannot leak into it.
def remember(state, message):
    state["session"].append(message)
    if not state["off_record"]:
        state["recordable"].append(message)


def close_session(state):
    """Kev ended it (only he can). Write what's worth keeping, and propose one
    change to the coaching style — proposed, not applied."""
    notes = "\n".join(f"- {n}" for n in state["notes"]) or "none"
    closing = build_messages(state["recordable"]) + [
        {"role": "user", "content": f"Notes you saved:\n{notes}\n\n{CLOSING}"}]
    result = parse_move(ask_model(closing, max_tokens=500)) or {}

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

    edit = result.get("edit") or {}
    return {"summary": summary, "wrote": wrote, "edit": edit,
            "off_record": state["off_record"],
            "style": read_file(STYLE)}


# --- L9: adaptation --------------------------------------------------------
# The second loop. The coach may propose one edit to its own instructions;
# this function is the ONLY thing that writes them, and it runs only when Kev
# has clicked Approve. Veto costs nothing and leaves no trace.
def apply_edit(edit):
    style = read_file(STYLE)
    remove, add = (edit.get("remove") or "").strip(), (edit.get("add") or "").strip()
    if not add:
        return False
    if remove and remove in style:
        style = style.replace(remove, add, 1)
    else:
        style = style.rstrip() + "\n" + add + "\n"
    with open(STYLE, "w") as handle:
        handle.write(style)
    return True


STATE = {"session": [], "recordable": [], "notes": [], "off_record": False}


# --- L3 + L8: the page, and the walls --------------------------------------
# The page is a window onto the agent, not the agent. The server binds to
# 127.0.0.1 only, so this is a thing on Kev's desk and not a thing on the web.
class Handler(http.server.BaseHTTPRequestHandler):

    def _send(self, code, payload, ctype="application/json"):
        body = payload.encode() if isinstance(payload, str) else payload
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as handle:
                self._send(200, handle.read(), "text/html; charset=utf-8")
        else:
            self._send(404, "not found", "text/plain")

    def do_POST(self):
        try:
            if self.path == "/say":
                said = self._body().get("said", "").strip()
                remember(STATE, {"role": "user", "content": said or
                                 "Open the session. Ask your first question."})
                self._send(200, json.dumps(take_turn(STATE)))
            elif self.path == "/end":          # only Kev reaches this
                self._send(200, json.dumps(close_session(STATE)))
            elif self.path == "/approve":      # L9, and only with consent
                ok = apply_edit(self._body().get("edit") or {})
                self._send(200, json.dumps({"applied": ok,
                                            "style": read_file(STYLE)}))
            else:
                self._send(404, json.dumps({"ask": "no such thing"}))
        except (DailyLimit, Unreachable) as known:
            self._send(200, json.dumps({"ask": str(known), "flagged": True}))
        except Exception as error:  # never a wall of red Python in the page
            self._send(200, json.dumps({"ask": f"Something broke: {error}",
                                        "flagged": True}))

    def log_message(self, *args):
        pass  # L8: nothing said in a session goes to a log, not even a URL


if __name__ == "__main__":
    server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)  # L8: local only
    # Coach.app opens the page itself (in a cleaner window), so it asks us not to.
    if not os.environ.get("COACH_NO_BROWSER"):
        threading.Timer(0.5, webbrowser.open, [f"http://127.0.0.1:{PORT}"]).start()
    print(f"The coach is listening on http://127.0.0.1:{PORT}   (Ctrl-C to stop)")
    server.serve_forever()
