# Forum contribution checker

Helps graders find each student's most noteworthy contributions in a Forum
class without watching the whole recording. It is a triage aid, not a grader:
it suggests what to listen to, and a person decides.

Everything runs on your own computer. Audio is never saved or uploaded, and
nothing is trained on student data.

## 1. The Forum button (no install)

Double-click **Install Forum button.html** and follow the steps on that page:
drag the button to your bookmarks bar, open a class's **Assess Class → Video**
page, and click the bookmark.

A panel lists every student speaking turn: time, name, length, and whether it
"stands alone" or is part of an exchange between students. Clicking a turn
jumps the video there.

## 2. Transcripts and rankings (runs on your Mac)

1. In the Forum panel, click **Save for transcription**. A small file goes to
   Downloads with the turn times and a video link that works for about 2 hours.
   You can save several classes before going on.
2. Double-click **Transcribe class**. It processes every saved class in
   Downloads, one after another.
   - **First time only:** it sets itself up (about 400 MB) and downloads two
     models (about 0.6 GB in total). macOS may ask whether Terminal can access
     Downloads. Click OK.
   - It transcribes each turn with about 20 seconds of context before and
     after, showing progress and time left.
3. When it finishes, the results open in your browser: one page per class,
   plus an index of all classes (`results/index.html`).

Double-clicking **Transcribe class** with nothing new in Downloads refreshes
all existing classes, for example after you edit the bookkeeping phrases. It
never re-transcribes. If a video link expires partway through, progress is
kept: save that class again in Forum and rerun.

### What each class page shows

**By student** (the default view) shows each student's turns ranked by
**noteworthiness** (0-100), with the top 3 shown in full. Each pick shows:

- its time in the video and how many seconds of it are substance;
- why it ranked where it did, for example "Strong: answers the question, new
  idea · Weak: diluted (much bookkeeping or pausing)";
- what the student said, with the full context (before / turn / after) one
  click away;
- review buttons (see below).

**All turns** shows every transcribed turn in time order. You can sort it by
noteworthiness or by any single signal, and filter by student or search.

### How noteworthiness works

Each student turn is split into sentences. **Bookkeeping** is greyed out:
checking the question, "can you hear me", warming up, agreeing, handing off.
Silence and throat-clearing contain no words, so they never count. Then five
signals are measured, each compared with the rest of the class (percentiles):

| Signal | Meaning |
|---|---|
| Amount of substance | Seconds of substance in the turn |
| Focus | Share of the turn that is substance (diluted turns score low) |
| Answers the question | Similarity between the substance and what was said just before |
| Instructor builds on it | Similarity between the substance and what was said just after |
| New idea | Difference from earlier student turns in the class |

Noteworthiness is their plain average. There are no weights to tune and no
training. Turns with fewer than 8 words of substance are not ranked.
"Similarity" is cosine similarity from a small sentence model
(all-MiniLM-L6-v2). The numbers are also saved in
`results/<class id>/analysis.csv`.

**Tuning:** `tool/bookkeeping_phrases.txt` lists example bookkeeping
sentences. Add phrases students actually use, then double-click **Transcribe
class** again.

## 3. Checking the picks (for reviewers)

The point is to test whether the top picks match the memory of someone who
was in the class.

1. On each class page, in **By student**, read each student's top picks (open
   "Context" if needed) and mark them **Noteworthy**, **Not really** or
   **Can't recall**. Add a note if useful, without names.
2. Click **Download ratings**. It saves `ratings_class_<id>.csv`, containing
   only IDs, video times, the scores and your marks. There are no names and no
   transcript text, so it is safe to send back.
3. Marks are kept in the browser if you close the page, as long as you reopen
   it in the same browser on the same computer.

**To give the tool to a reviewer:** double-click **Make shareable copy**. It
puts a zip on your Desktop **without** your `results/` folder. The reviewer
unzips it and starts at step 1 with their own Forum account. They need grader
access to the classes they review.

## Privacy and your Mac

- Only the parts of the video around each turn are read, and only into
  memory. Transcription and analysis run on the computer. Nothing is uploaded.
- Transcripts contain student names and speech. They stay in `results/`, which
  is excluded from git and from the shareable copy.
- Built for an 8 GB M1: a small speech model (under 1 GB of memory), at most 4
  of 8 processor cores, low priority, one short clip at a time. The Mac stays
  awake while it runs.

## Limits

- Forum only logs when *students* speak, so "before" and "after" are whatever
  was said around the student. Usually that's the instructor, but it can be
  silence or another student.
- Automatic transcripts make mistakes, especially with names and technical
  terms.
- **Breakouts:** the recording follows one group, so breakout time is left out.
  Breakout-room speech is never counted. Main-room turns that start while a
  breakout is running (from its lesson-plan click until the breakout room goes
  quiet, or until the next click) are listed in the panel but not transcribed
  or ranked. Context windows never reach into a breakout. A real debrief that
  starts before the instructor moves the lesson plan on can be left out too.
- Noteworthiness is relative to the class. A top pick is the best *in that
  class*, not good in any absolute sense.
- Turn times use Forum's millisecond timestamps. If a recording was stopped and
  restarted, the tool assumes the video joins the parts in order, and says so.
- For a 100-minute class with 50 turns, it reads roughly three quarters of the
  video file over the network. Raise "At least (seconds)" in the panel before
  saving to transcribe fewer turns.
- **Transcribe class** is macOS only for now.

## How it works (for developers)

```
Forum class page ──(bookmarklet, runs in your logged-in browser)──► forum_class_<id>.json
   voice events → student turns (ms timing, recording parts, breakouts excluded)
   + a short-lived signed link to the recording

forum_class_<id>.json ──► tool/transcribe.py
   audio.py    read only each turn's window (PyAV, HTTP range requests) → Whisper small.en (faster-whisper)
   transcribe  split words into before / student / after by timestamp; cache in transcripts.jsonl
   analyze.py  sentences → substance vs bookkeeping (nearest prototype, all-MiniLM-L6-v2 via ONNX Runtime)
               → five signals → within-class percentiles → noteworthiness, per-student ranks
   report.py   results/<class>/transcript.html and results/index.html
```

The bookmarklet uses Forum's own web endpoints with your existing browser
session. It stores no credentials and can only see what your account can see.
Use it within your institution's policies on recordings and student data.

**Tests:** `pip install -r requirements-dev.txt` then `python -m pytest tests`.
They are offline and use synthetic data only (no models are downloaded).

## Repository layout

| | |
|---|---|
| `Install Forum button.html` | Set up the bookmark button (generated by `bookmarklet/build.py`) |
| `Transcribe class.command` | Double-click: set up once, then transcribe saved classes and build rankings |
| `Make shareable copy.command` | Double-click: zip the tool without your results |
| `bookmarklet/` | The button: `forum_helper.js` (source), `build.py`, install page template |
| `tool/transcribe.py` | Pipeline and command line |
| `tool/audio.py` | Reading audio windows from the recording; local Whisper |
| `tool/analyze.py` | Substance vs bookkeeping, signals, noteworthiness |
| `tool/report.py`, `tool/report_assets/` | Result pages (HTML, CSS, JS) |
| `tool/bookkeeping_phrases.txt` | Editable example bookkeeping sentences |
| `tests/` | Offline tests |
| `results/` | Your transcripts and rankings (private, never committed) |
