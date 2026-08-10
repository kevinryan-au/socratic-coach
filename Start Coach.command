#!/bin/zsh
# Double-click this. It fetches the latest build, checks the coach has what it
# needs, then starts it and opens the chat page. Nothing hidden — it's a page.

cd "$(dirname "$0")" || exit 1     # run from this folder, wherever it lives

echo "Checking for a newer build..."
if git pull --quiet --ff-only 2>/dev/null; then
  echo "  up to date."
else
  echo "  couldn't check just now - running the version already here."
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
