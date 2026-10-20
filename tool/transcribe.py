#!/usr/bin/env python3
"""Transcribe the student turns saved by the Forum button.

Input:  forum_class_<id>.json files (from the button's "Save for transcription"),
        all of them in ~/Downloads unless paths are given. With nothing new, it
        refreshes the classes already processed (re-analysis only, no re-transcription).
Output: results/index.html                 (every class; opens automatically)
        results/<class id>/transcript.html  (per-student ranking + review buttons, all turns)
        results/<class id>/transcripts.jsonl (word-level cache; reruns skip done turns)
        results/<class id>/analysis.csv      (substance vs bookkeeping + signals, see analyze.py)

For each turn, only its window (about 20 s before to 20 s after) is read from
the class video over the network. Audio is decoded in memory, transcribed by a
local Whisper model, and never written to disk or sent anywhere.

Gentle on an 8 GB M1: small model (int8, under 1 GB RAM), 4 CPU threads, one
window at a time. The launcher also runs it at low priority.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from audio import Recording, Whisper
from report import hms, write_index, write_report

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
TOL_MS = 0.3        # s of slack at turn edges (the button saves millisecond timing)
TOL_OLD = 0.75      # exports from before millisecond timing used whole seconds


def say(msg=""):
    print(msg, flush=True)


# ------------------------------------------------------------- the input --

def find_exports() -> list[Path]:
    """All files saved by the Forum button in ~/Downloads, oldest first."""
    downloads = Path.home() / "Downloads"
    try:
        return sorted(downloads.glob("forum_class_*.json"), key=lambda p: p.stat().st_mtime)
    except PermissionError:
        sys.exit("macOS blocked access to Downloads. Allow it (System Settings > Privacy & Security >\n"
                 "Files and Folders > Terminal > Downloads) and run this again.")


def load_export(path: Path):
    data = json.loads(path.read_text())
    if data.get("format") != "forum-transcribe/v1":
        sys.exit(f"{path.name} isn't a file saved by the Forum button.")
    out = RESULTS / str(data["class-id"])
    out.mkdir(parents=True, exist_ok=True)
    dest = out / "export.json"
    if path.resolve() != dest.resolve():
        # Keep the latest export with its results (and out of Downloads).
        shutil.move(str(path), dest)
    return data, out


def link_expires(data) -> float | None:
    e = (data.get("recording") or {}).get("expires")
    return datetime.fromisoformat(e.replace("Z", "+00:00")).timestamp() if e else None


# ------------------------------------------------------ splitting a turn --

def split(words, turn, tol=TOL_MS):
    """Absolute-timed words -> before / student / after, by word midpoint.
    words: (start, end, text), or [start, text] from older transcripts (kept as they are)."""
    parts = {"before": [], "student": [], "after": []}
    for w in words:
        s, text = w[0], w[-1]
        e = w[1] if len(w) >= 3 else s
        mid = (s + e) / 2
        key = "before" if mid < turn["start"] - tol else "after" if mid > turn["end"] + tol else "student"
        parts[key].append([round(s, 2), round(e, 2), text] if len(w) >= 3 else [round(s, 2), text])
    return {k: {"text": "".join(x[-1] for x in v).strip(), "words": v} for k, v in parts.items()}


# --------------------------------------------------------------- pipeline --

class Session:
    """Things loaded once per run and shared across classes."""
    whisper = None


def process_class(data, out: Path, session: Session):
    """Transcribe what's missing (if the link is still valid), analyse, write the page.
    Returns (page path, True if everything is transcribed)."""
    turns = sorted(data["turns"], key=lambda t: t["start"])
    tol = TOL_MS if data.get("timing") == "forum-ms" else TOL_OLD
    say(f"\n=== {data.get('course', '')} — {data.get('title', '')} ===")
    if (data.get("recording-parts") or 1) > 1:
        say(f"Note: this class was recorded in {data['recording-parts']} parts; times assume the video joins them in order.")

    cache_path = out / "transcripts.jsonl"
    cache = {}
    if cache_path.exists():
        for line in cache_path.read_text().splitlines():
            if line.strip():
                rec = json.loads(line)
                cache[rec["id"]] = rec
    # Re-split saved transcripts with the current turn timings (no re-transcription needed),
    # so timing fixes apply to classes already done. Only if a turn no longer overlaps its
    # saved window at all (it's a different turn) is it dropped and transcribed again.
    if cache:
        by_id = {t["id"]: t for t in turns}
        for tid in list(cache):
            c, t = cache[tid], by_id.get(tid)
            if t is None:
                continue
            if t["end"] < c["window"][0] or t["start"] > c["window"][1]:
                del cache[tid]
                continue
            # keep only words inside the turn's current window (e.g. context no longer reaches
            # into a breakout, where the recording follows one group)
            lo, hi = t["window"]
            words = [w for part in ("before", "student", "after") for w in c[part]["words"]
                     if lo - 0.5 <= w[0] <= hi + 0.5]
            cache[tid] = {"id": tid, "window": [max(lo, c["window"][0]), min(hi, c["window"][1])], **split(words, t, tol)}
        cache_path.write_text("".join(json.dumps(c) + "\n" for c in cache.values()))
    todo = [t for t in turns if t["id"] not in cache]
    say(f"{len(turns)} turns; {len(turns) - len(todo)} already done, {len(todo)} to transcribe.")

    exp = link_expires(data)
    if todo and exp and exp - time.time() < 120:
        say("The video link for this class has expired (links last about 2 hours): save it again in Forum and rerun.")
        todo = []
    if todo:
        if session.whisper is None:
            say("Loading the speech model (the first time this downloads about 0.5 GB)...")
            session.whisper = Whisper()
        say("Opening the class video...")
        rec = Recording(data["recording"]["url"])
        audio_total = sum(t["window"][1] - t["window"][0] for t in todo)
        say(f"Transcribing {hms(audio_total)} of audio in {len(todo)} short clips. The Mac stays usable;"
            " you can leave this running.\n")
        started, done_audio = time.time(), 0.0
        with cache_path.open("a") as f:
            for i, t in enumerate(todo, 1):
                if exp and exp - time.time() < 30:
                    say("\nThe video link just expired. Progress is saved: save the class again in Forum and rerun.")
                    break
                lo, hi = t["window"]
                t0 = time.time()
                try:
                    audio = rec.window(lo, hi)
                    hint = ". ".join(x for x in [data.get("course"), t.get("segment")] if x)
                    words = [(s + lo, e + lo, w) for s, e, w in session.whisper.words(audio, hint)]
                except Exception as err:  # keep going; the turn is retried next run
                    say(f"  [{i}/{len(todo)}] {hms(t['start'])} {t['student']}: skipped ({err})")
                    continue
                entry = {"id": t["id"], "window": [lo, hi], **split(words, t, tol)}
                f.write(json.dumps(entry) + "\n")
                f.flush()
                cache[t["id"]] = entry
                done_audio += hi - lo
                rate = (time.time() - started) / done_audio
                left = (audio_total - done_audio) * rate
                say(f"  [{i}/{len(todo)}] {hms(t['start'])} {t['student']}: "
                    f"{len(entry['student']['words'])} words ({time.time() - t0:.0f} s)   ~{hms(left)} left")
        rec.close()

    analysis, sim_name = None, ""
    if cache:
        say("Analysing (the first time this downloads a ~90 MB model)...")
        try:
            from analyze import analyze_class
            analysis, sim_name = analyze_class(data, turns, cache, out)
        except Exception as err:  # never lose the transcript page over the analysis
            say(f"  Analysis failed ({err}); writing the plain transcript page.")
    page = write_report(data, turns, cache, out, analysis, sim_name)
    complete = all(t["id"] in cache for t in turns)
    say(f"Page: {page}" + ("" if complete else f"  ({sum(t['id'] not in cache for t in turns)} turns still to do)"))
    return page, complete


def main(argv=None):
    ap = argparse.ArgumentParser(description="Transcribe student turns saved by the Forum button.")
    ap.add_argument("exports", nargs="*", help="forum_class_<id>.json files (default: all in Downloads)")
    ap.add_argument("--no-open", action="store_true", help="don't open the result page when done")
    a = ap.parse_args(argv)

    paths = [Path(p).expanduser() for p in a.exports] if a.exports else find_exports()
    classes = [load_export(p) for p in paths]
    if not classes:
        prior = sorted(RESULTS.glob("*/export.json"))
        if not prior:
            sys.exit("No saved class found in Downloads.\n"
                     "In Forum, open the class's Assess Class > Video page, click the bookmark,\n"
                     "then click \"Save for transcription\". Then run this again.")
        say("Nothing new in Downloads: refreshing the classes already here (no re-transcription).")
        classes = [(json.loads(p.read_text()), p.parent) for p in prior]
    else:
        say(f"Found {len(classes)} saved class{'es' if len(classes) != 1 else ''}.")

    session, pages, incomplete = Session(), [], []
    for data, out in classes:
        page, complete = process_class(data, out, session)
        pages.append(page)
        if not complete:
            incomplete.append(data.get("title") or str(data["class-id"]))
    index = write_index(RESULTS)
    say(f"\nDone. All classes: {index}")
    if incomplete:
        say("Not finished (save these again in Forum and rerun): " + "; ".join(incomplete))
    if not a.no_open and sys.platform == "darwin":
        subprocess.run(["open", str(pages[0] if len(pages) == 1 else index)])


if __name__ == "__main__":
    main()
