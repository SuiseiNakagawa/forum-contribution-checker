#!/bin/bash
# Double-click to transcribe the class you saved with the Forum button.
# First run: sets up a private Python environment in tool/.venv (one time).
cd "$(dirname "$0")" || exit 1
clear
echo "Forum class transcription"
echo "========================="
echo

VENV="tool/.venv"
if [ ! -x "$VENV/bin/python" ]; then
  PY=""
  for c in python3 /opt/homebrew/bin/python3 /usr/local/bin/python3 "$HOME/anaconda3/bin/python3" \
           "$HOME/opt/anaconda3/bin/python3" /opt/anaconda3/bin/python3 "$HOME/miniconda3/bin/python3" /usr/bin/python3; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
      PY="$c"; break
    fi
  done
  if [ -z "$PY" ]; then
    echo "Couldn't find Python 3.9 or newer on this Mac."
    echo "Install it from https://www.python.org/downloads/ and double-click this file again."
    read -r -p "Press Enter to close."; exit 1
  fi
  echo "First run: setting things up (one time, a few minutes)..."
  if ! "$PY" -m venv "$VENV" || ! "$VENV/bin/python" -m pip install --quiet --upgrade pip \
     || ! "$VENV/bin/python" -m pip install --quiet -r tool/requirements.txt; then
    echo; echo "Setup failed (see the messages above). Check your internet connection and try again."
    rm -rf "$VENV"
    read -r -p "Press Enter to close."; exit 1
  fi
  echo "Setup done."; echo
fi

# Keep the Mac awake while running, at low priority so it stays responsive.
caffeinate -i nice -n 10 "$VENV/bin/python" tool/transcribe.py "$@"
echo
read -r -p "Press Enter to close this window."
