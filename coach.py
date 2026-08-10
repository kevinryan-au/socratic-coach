#!/usr/bin/env python3
"""The Socratic Coach — an agent that only ever asks questions.

Read this file top to bottom and you read the agent stack: each section is
tagged with the layer it makes real. L6 (planning) and L7 (delegation) are
deliberately absent — a coach that plans ahead or hands off isn't a coach.

House rule, visible throughout: behaviour you'd LIKE goes in the prompt;
behaviour you REQUIRE goes in code.
"""

import http.server
import json
import os
import threading
import urllib.error
import urllib.request
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8787

# --- L0: inference ---------------------------------------------------------
# Rented, stateless, and the only layer that isn't yours. Nothing is installed
# here; the model runs on Cloudflare's hardware. Swap this one line and every
# other layer carries on unchanged — that's the reference architecture paying off.
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
    """The free allowance is spent. Not an error to retry — an error to report."""


def ask_model(messages):
    """One call to L0. Deliberately no retries: a retry loop could spend the
    day's free neurons in a spiral, and free is a hard constraint."""
    body = json.dumps({"messages": messages, "max_tokens": 300}).encode()
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
        raise


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


# --- L1: context assembly --------------------------------------------------
# Everything the model can see before it writes a word. Right now that is the
# constitution, the coaching style, and the session so far. Phase 3 adds memory
# of past sessions to this same list — "context" is never more exotic than
# deciding what goes in the list.
def build_messages(session):
    with open(os.path.join(HERE, "memory", "instructions.md")) as handle:
        style = handle.read()
    system = CONSTITUTION + "\n--- coaching style (L9, evolves) ---\n" + style
    return [{"role": "system", "content": system}] + session


# --- L2: tool interface ----------------------------------------------------
# Three tools, and the JSON envelope above IS the interface — that convention
# is L2 made visible. Asking is all the model does; the code below decides
# what actually happens.
TOOLS = ("save_note", "go_off_record", "end_session")


# --- L3: execution / effectors ---------------------------------------------
# The part that actually does it, then reports back. Note who the environment
# is here: Kev. His typed reply is the "tool result" that comes back into L1.
# (Phase 2 keeps notes in RAM only — nothing touches disk until L5 exists.)
def run_tool(name, args, state):
    if name == "save_note":
        state["notes"].append(args.get("note", ""))
        return "noted"
    if name == "go_off_record":
        state["off_record"] = True
        return "off the record from here"
    if name == "end_session":
        return "ending proposed — Kev decides, not you"
    return f"no such tool: {name}"


# --- L4: control loop ------------------------------------------------------
# Look at everything, decide, act, look at what came back, decide again. The
# loop stops when the model asks Kev something, because Kev is the environment
# and nothing can continue until he replies.
MAX_CALLS = 5  # consecutive calls without Kev — a spiral can't spend his day


def take_turn(state):
    for _ in range(MAX_CALLS):
        raw = ask_model(build_messages(state["session"]))
        state["session"].append({"role": "assistant", "content": raw})
        try:
            move = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
        except ValueError:
            return {"ask": raw, "flagged": True}

        if "ask" in move:
            return {"ask": move["ask"]}

        name = move.get("tool")
        result = run_tool(name, move.get("args", {}), state)
        state["session"].append({"role": "user", "content": f"[{name}: {result}]"})
        if name == "end_session":
            return {"ask": "Shall we stop there?", "propose_end": True}

    return {"ask": "I went round five times without you. Where were we?",
            "flagged": True}


# --- L5: state & memory ----------------------------------------------------
# Phase 2 has none. The session lives in RAM and dies with the process — it is
# a stranger every time you open it. That is exactly what Phase 3 fixes.
STATE = {"session": [], "notes": [], "off_record": False}


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

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as handle:
                self._send(200, handle.read(), "text/html; charset=utf-8")
        else:
            self._send(404, "not found", "text/plain")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        said = json.loads(self.rfile.read(length) or b"{}").get("said", "").strip()
        STATE["session"].append({"role": "user", "content": said or
                                 "Open the session. Ask your first question."})
        try:
            self._send(200, json.dumps(take_turn(STATE)))
        except DailyLimit as limit:
            self._send(200, json.dumps({"ask": str(limit), "flagged": True}))
        except Exception as error:  # never a wall of red Python in the page
            self._send(200, json.dumps({"ask": f"Something broke: {error}",
                                        "flagged": True}))

    def log_message(self, *args):
        pass  # L8: nothing said in a session goes to a log, not even a URL


if __name__ == "__main__":
    server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)  # L8: local only
    threading.Timer(0.5, webbrowser.open, [f"http://127.0.0.1:{PORT}"]).start()
    print(f"The coach is listening on http://127.0.0.1:{PORT}   (Ctrl-C to stop)")
    server.serve_forever()
