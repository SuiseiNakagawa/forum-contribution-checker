"""Offline tests with synthetic data only (no network, no model downloads)."""
import json

import pytest

import analyze
import report
import transcribe


def words_from(text, start, step=0.4):
    out, t = [], start
    for w in text.split():
        out.append([round(t, 2), round(t + step * 0.8, 2), " " + w])
        t += step
    return out


QUESTION = "So what is the difference between supervised and unsupervised learning? What role do labels play?"


def make_turn(tid, student, start, end, before, said, after):
    turn = {"id": tid, "student": student, "start": start, "end": end, "speech": end - start,
            "kind": "Stands alone", "segment": "Test", "window": [start - 20, end + 20]}
    words = words_from(before, start - 15) + said + words_from(after, end + 1)
    return turn, {"id": tid, "window": turn["window"], **transcribe.split(words, turn)}


# --------------------------------------------------------------- splitting

def test_split_assigns_words_by_midpoint():
    turn = {"start": 10.0, "end": 20.0}
    words = [(5.0, 5.3, " before"), (9.8, 10.1, " edge"), (15.0, 15.3, " inside"), (25.0, 25.3, " after")]
    parts = transcribe.split(words, turn)
    assert parts["before"]["text"] == "before"
    assert parts["student"]["text"] == "edge inside"   # within the 0.3 s tolerance
    assert parts["after"]["text"] == "after"


def test_split_keeps_older_two_field_words():
    parts = transcribe.split([[12.0, " old"]], {"start": 10.0, "end": 20.0})
    assert parts["student"]["words"] == [[12.0, " old"]]


def test_sentences_break_on_punctuation_and_pauses():
    words = words_from("Can you hear me?", 0) + words_from("Supervised learning uses labels", 5)
    units = analyze.sentences(words)
    assert [u["text"] for u in units] == ["Can you hear me?", "Supervised learning uses labels"]


# ---------------------------------------------------------------- analysis

@pytest.fixture
def scripted_class(tmp_path):
    specs = [
        ("1-001", "Ana", 100, 125, QUESTION,
         words_from("Sorry, can you hear me? Just to make sure I understand the question, you're asking about "
                    "the difference between supervised and unsupervised learning, right?", 105, 0.55)
         + words_from("Supervised learning trains on labeled examples, unsupervised finds clusters without labels.", 120),
         "Exactly, labeled examples versus finding clusters without labels. Good."),
        ("1-002", "Ben", 300, 330, QUESTION,
         words_from("The key difference is that supervised learning needs labeled training data so the model "
                    "learns a mapping from inputs to outputs. Unsupervised learning has no labels, so it looks "
                    "for structure like clusters.", 300.5),
         "Great point about labeled training data and finding structure."),
        ("1-003", "Ana", 500, 512, "Does anyone want to add to that?",
         words_from("Yeah, I agree with what she said. That's all I wanted to say.", 500.5),
         "Okay thanks, let's move on."),
        ("1-004", "Cy", 900, 925, "What could go wrong with a model trained on biased data?",
         words_from("If historical hiring data is biased, a classifier will reproduce that bias, so fairness "
                    "audits and reweighting the training set matter.", 900.5),
         "That's an important point about fairness audits and reweighting."),
    ]
    turns, cache = [], {}
    for spec in specs:
        t, c = make_turn(*spec)
        turns.append(t)
        cache[t["id"]] = c
    data = {"class-id": 1, "title": "Synthetic class", "course": "Test course", "date": "2026-10-01"}
    res, _ = analyze.analyze_class(data, turns, cache, tmp_path)
    return data, turns, cache, res, tmp_path


def test_bookkeeping_is_separated_from_substance(scripted_class):
    *_, res, _ = scripted_class
    kinds = [u["kind"] for u in res["1-001"]["units"]]
    assert kinds[0] == "bookkeeping"            # "Sorry, can you hear me?"
    assert kinds[-1] == "substance"             # the actual answer
    assert res["1-001"]["substance_share"] < 0.3
    assert res["1-003"]["substance_words"] == 0  # pure agreement / hand-off


def test_noteworthiness_and_per_student_ranks(scripted_class):
    *_, res, _ = scripted_class
    assert res["1-003"]["noteworthiness"] is None and res["1-003"]["rank"] is None
    ranked = [r for r in res.values() if r["noteworthiness"] is not None]
    assert all(0 <= r["noteworthiness"] <= 100 for r in ranked)
    assert res["1-001"]["rank"] == 1             # Ana's only rankable turn
    assert "diluted (much bookkeeping or pausing)" in res["1-001"]["weak"]


def test_analysis_csv_has_no_missing_columns(scripted_class):
    *_, out = scripted_class
    header = (out / "analysis.csv").read_text().splitlines()[0].split(",")
    assert {"noteworthiness", "rank_in_student", "substance_sec"} <= set(header)


# ------------------------------------------------------------------ report

def test_pages_render(scripted_class, tmp_path):
    data, turns, cache, res, out = scripted_class
    page = report.write_report(data, turns, cache, out, res, "test")
    html = page.read_text()
    assert html.count('class="student"') == 3
    assert 'id="dl"' in html and "Download ratings" in html
    (tmp_path / "1").mkdir(exist_ok=True)
    (tmp_path / "1" / "export.json").write_text(json.dumps({**data, "turns": turns}))
    index = report.write_index(tmp_path).read_text()
    assert "Synthetic class" in index


def test_hms():
    assert report.hms(65) == "1:05" and report.hms(3725) == "1:02:05"


# ------------------------------------------------------------------- audio

def test_recording_window_is_sample_accurate(tmp_path):
    """Builds a 30 s file with a beep at 12 s and reads a window around it."""
    av = pytest.importorskip("av")
    np = pytest.importorskip("numpy")
    from audio import SR, Recording

    path = str(tmp_path / "beep.m4a")
    rate = 44100
    t = np.arange(30 * rate) / rate
    signal = np.where((t >= 12) & (t < 12.5), 0.5 * np.sin(2 * np.pi * 1000 * t), 0.0).astype(np.float32)
    with av.open(path, "w") as out:
        stream = out.add_stream("aac", rate=rate)
        stream.layout = "mono"
        for i in range(0, len(signal), 1024):
            frame = av.AudioFrame.from_ndarray(signal[None, i:i + 1024], format="flt", layout="mono")
            frame.sample_rate = rate
            for pkt in stream.encode(frame):
                out.mux(pkt)
        for pkt in stream.encode(None):
            out.mux(pkt)

    rec = Recording(path)
    audio = rec.window(10.0, 14.0)
    rec.close()
    assert abs(len(audio) - 4 * SR) < SR * 0.01
    onset = 10.0 + np.argmax(np.abs(audio) > 0.1) / SR
    assert abs(onset - 12.0) < 0.05
