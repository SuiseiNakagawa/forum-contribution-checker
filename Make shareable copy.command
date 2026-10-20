#!/bin/bash
# Makes a zip of this tool to give to someone else (e.g. a reviewer), WITHOUT your
# results (transcripts and ratings contain student names and speech) and without
# the installed Python environment (it sets itself up again on their Mac).
cd "$(dirname "$0")" || exit 1
OUT="${1:-$HOME/Desktop/forum-contribution-checker (share).zip}"
rm -f "$OUT"
zip -r -q "$OUT" . \
  -x "results/*" -x "tool/.venv/*" -x "*__pycache__*" -x "*.DS_Store" -x ".git/*" -x ".pytest_cache/*" \
     -x "advanced/*" -x "data/*" -x "out/*" -x "forum_class_*.json" -x "ratings_class_*.csv"
# keep an empty results folder so the tool has somewhere to write
TMP=$(mktemp -d) && mkdir -p "$TMP/results" && touch "$TMP/results/.keep" && (cd "$TMP" && zip -q "$OUT" results/.keep) && rm -rf "$TMP"
echo "Shareable copy saved: $OUT"
echo "It does not include your results/ folder. The recipient unzips it and follows README.md."
read -r -p "Press Enter to close."
