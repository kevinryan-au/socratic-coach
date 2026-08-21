#!/bin/zsh
# Double-click this. It fetches the latest build, checks the coach has what it
# needs, then starts it and opens the chat page. Nothing hidden — it's a page.

cd "$(dirname "$0")" || exit 1     # run from this folder, wherever it lives

# memory/instructions.md is tracked, and it is the one tracked file the coach
# rewrites by itself — every approved L9 edit changes it. git then refuses to
# touch the folder if an update would overwrite it, so the second loop working
# is quietly what stops new builds arriving. Set the copy aside, update, put it
# back.
#
# Deliberately a copy rather than a stash: a stash has to be reapplied, and if
# an update ever edits this file too, reapplying it leaves conflict markers
# sitting in the middle of the coaching style — which the coach then reads out
# as though you'd written it. A copy can't conflict. Your version wins
# outright, and that's the right way round: the file in the repo is a starting
# seed, yours is what the sessions have shaped it into.
#
# Coach.app does exactly this, in Contents/MacOS/Coach. It is written out twice
# because each launcher has to be readable on its own — this one drifted and
# went without the guard for four builds, so: change one, change both.
KEEP=""
if [ -f memory/instructions.md ] &&
   ! git diff --quiet -- memory/instructions.md 2>/dev/null; then
  KEEP="$(mktemp "${TMPDIR:-/tmp}/coachstyle.XXXXXX" 2>/dev/null)"
  # Give up the working copy only once there is definitely a copy to hand back.
  # Discarding first and finding out afterwards that the copy failed would lose
  # the style outright, which is the one thing worse than not updating.
  if [ -n "$KEEP" ] && cp memory/instructions.md "$KEEP" 2>/dev/null; then
    git checkout --quiet -- memory/instructions.md >/dev/null 2>&1
  else
    KEEP=""
  fi
fi

echo "Checking for a newer build..."
# Not silenced. A refused update and an update with nothing to fetch printed
# the same reassuring line before, which is how a coach that had stopped
# updating looked exactly like one that was up to date.
if git pull --quiet --ff-only; then
  echo "  up to date."
else
  echo ""
  echo "  Couldn't install a newer build - running the version already here."
  echo "  git said why just above. Your coaching style isn't the reason:"
  echo "  that gets set aside and handed back either way."
  echo ""
fi

if [ -n "$KEEP" ]; then
  cp "$KEEP" memory/instructions.md
  rm -f "$KEEP"
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo ""
  echo "python3 isn't installed, and the coach is a Python program."
  echo "Opening the Command Line Tools installer should fix it: xcode-select --install"
  echo ""
  echo "Press return to close."
  read _
  exit 1
fi

if [ ! -f .env ]; then
  echo ""
  echo "There's no .env file, so the coach can't reach the model."
  echo "Copy .env.example to .env and put your two Cloudflare values in it."
  echo ""
  echo "Press return to close."
  read _
  exit 1
fi

echo "Starting the coach..."
echo "Leave this window open while you're thinking. Close it to stop."
echo ""
exec python3 coach.py
