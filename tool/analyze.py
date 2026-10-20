"""Unsupervised analysis of transcribed student turns (no training, no labels).

For each turn:
  1. Split the student's words into sentences (punctuation or pauses > 0.8 s).
     Silence and throat-clearing produce no words, so they never count.
  2. Mark each sentence as
       substance    - contributes content
       bookkeeping  - procedural, checking, warming up, agreeing, handing off
                      (close in meaning to an example in bookkeeping_phrases.txt,
                       or almost no content words)
       restating    - repeats the instructor's question without adding to it
     When unsure, a sentence stays "substance", so real answers aren't hidden.
  3. Measure, on the substance part only:
       substance_sec     speaking time of substance sentences
       answers_question  similarity(instructor's words before, substance)
       instructor_uptake similarity(substance, instructor's words after)
       revoicing         share of the student's content words the instructor repeats
       newness           1 - similarity to the most similar earlier student turn
  Signals are also given as low / mid / high relative to the class (thirds).
  4. Noteworthiness (0-100) = the average of five within-class percentiles, equally
     weighted: amount of substance, share of the turn that is substance, answers the
     question, instructor picks it up, newness. Missing signals are left out of the
     average. Turns with fewer than MIN_WORDS substance words are not ranked.
     Each student's turns are then ranked by it, with the strongest and weakest
     signals listed as the reason.

Similarity = cosine similarity of sentence embeddings from all-MiniLM-L6-v2
(small, ~90 MB, run with onnxruntime). If it can't be downloaded, falls back to
word-overlap (TF-IDF) vectors.
"""
from __future__ import annotations

import csv
import json
import re
import zlib
from collections import Counter
from math import log
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PHRASES = HERE / "bookkeeping_phrases.txt"
MODEL_SOURCES = [("sentence-transformers/all-MiniLM-L6-v2", "onnx/model.onnx"),
                 ("Xenova/all-MiniLM-L6-v2", "onnx/model.onnx")]
PAUSE = 0.8          # s of silence that ends a sentence
MIN_WORDS = 8        # substance words needed before judging a turn
MIN_CONTEXT = 5      # words needed in the before/after text

STOP = set("""a about above after again against all am an and any are as at be because been before being
below between both but by can could did do does doing down during each few for from further had has
have having he her here hers herself him himself his how i if in into is it its itself let me more most
my myself no nor not of off on once only or other our ours ourselves out over own same she should so
some such than that the their theirs them themselves then there these they this those through to too
under until up very was we were what when where which while who whom why will with would you your
yours yourself yourselves i'm it's that's there's don't didn't isn't aren't wasn't can't i'd i've
we're you're they're what's let's gonna wanna also maybe""".split())
FILLER = set("""um umm uh uhh erm er hmm mm mhm like yeah yes yep okay ok right well basically actually
just kind sort guess mean know think thing things stuff really pretty sorry thanks thank oh wait
alright cool sure""".split())


def tokens(text: str):
    return re.findall(r"[a-z][a-z'-]*", text.lower())


def content_words(text: str):
    return [w for w in tokens(text) if w not in STOP and w not in FILLER and len(w) > 2]


# ------------------------------------------------------------ similarity --

class MiniLM:
    name = "all-MiniLM-L6-v2 sentence embeddings"
    proto_t, echo_t = 0.55, 0.60

    def __init__(self):
        from huggingface_hub import hf_hub_download
        from tokenizers import Tokenizer
        import onnxruntime as ort
        last = None
        for repo, fname in MODEL_SOURCES:
            try:
                model_path = hf_hub_download(repo, fname)
                tok_path = hf_hub_download(repo, "tokenizer.json")
                break
            except Exception as e:  # try the next copy
                last = e
        else:
            raise RuntimeError(f"couldn't download the similarity model ({last})")
        self.tok = Tokenizer.from_file(tok_path)
        self.tok.enable_truncation(max_length=256)
        self.tok.enable_padding()
        so = ort.SessionOptions()
        so.intra_op_num_threads, so.inter_op_num_threads = 2, 1
        self.sess = ort.InferenceSession(model_path, so, providers=["CPUExecutionProvider"])
        self.inputs = {i.name for i in self.sess.get_inputs()}
        self.cache = {}

    def encode(self, texts):
        need = [t for t in dict.fromkeys(texts) if t not in self.cache]
        for i in range(0, len(need), 32):
            batch = need[i:i + 32]
            enc = self.tok.encode_batch(batch)
            ids = np.array([e.ids for e in enc], dtype=np.int64)
            mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
            feed = {"input_ids": ids, "attention_mask": mask, "token_type_ids": np.zeros_like(ids)}
            out = self.sess.run(None, {k: v for k, v in feed.items() if k in self.inputs})[0]
            if out.ndim == 3:   # token vectors -> mean over real tokens
                m = mask[..., None].astype(np.float32)
                out = (out * m).sum(1) / np.clip(m.sum(1), 1e-9, None)
            out = out / np.clip(np.linalg.norm(out, axis=1, keepdims=True), 1e-9, None)
            for t, v in zip(batch, out):
                self.cache[t] = v.astype(np.float32)
        return np.stack([self.cache[t] for t in texts]) if texts else np.zeros((0, 1), np.float32)


class WordOverlap:
    """Fallback: TF-IDF over content words, hashed into a fixed-size vector."""
    name = "word overlap (TF-IDF) - similarity model unavailable"
    proto_t, echo_t = 0.45, 0.50
    DIM = 4096

    def __init__(self, corpus):
        docs = [set(content_words(d)) for d in corpus if d]
        n = max(1, len(docs))
        df = Counter(w for d in docs for w in d)
        self.idf = {w: log((1 + n) / (1 + c)) + 1 for w, c in df.items()}

    def encode(self, texts):
        out = np.zeros((len(texts), self.DIM), np.float32)
        for i, t in enumerate(texts):
            for w, c in Counter(content_words(t)).items():
                out[i, zlib.crc32(w.encode()) % self.DIM] += c * self.idf.get(w, 1.0)
        return out / np.clip(np.linalg.norm(out, axis=1, keepdims=True), 1e-9, None)


_EMB = None


def get_embedder(fallback_corpus):
    """The sentence model, loaded once per run; word overlap if it can't be loaded."""
    global _EMB
    if _EMB is None:
        try:
            _EMB = MiniLM()
        except Exception as e:
            print(f"  (similarity model unavailable: {e}; using word overlap instead)", flush=True)
            _EMB = False
    return _EMB if _EMB else WordOverlap(fallback_corpus)


def load_phrases():
    if not PHRASES.exists():
        return []
    return [l.strip() for l in PHRASES.read_text().splitlines() if l.strip() and not l.lstrip().startswith("#")]


def cos(a, b):
    return float(np.dot(a, b))


# --------------------------------------------------------------- per turn --

END = re.compile(r"[.?!][\"')\]]*$")


def sentences(words):
    """words: [[start, end, text]] (older cache: [[start, text]]) -> sentence units."""
    norm = []
    for i, w in enumerate(words):
        if len(w) >= 3:
            s, e, t = w[0], w[1], w[2]
        else:
            s, t = w
            nxt = words[i + 1][0] if i + 1 < len(words) else s + 0.4
            e = min(nxt, s + 1.0)
        norm.append((s, max(e, s), t))
    out, cur = [], []
    for i, (s, e, t) in enumerate(norm):
        cur.append((s, e, t))
        nxt = norm[i + 1][0] if i + 1 < len(norm) else None
        if nxt is None or END.search(t.strip()) or nxt - e > PAUSE:
            out.append({"start": cur[0][0], "end": cur[-1][1], "text": "".join(x[2] for x in cur).strip()})
            cur = []
    return out


def classify(units, prompt, emb, proto_vecs):
    if not units:
        return
    U = emb.encode([u["text"] for u in units])
    proto = (U @ proto_vecs.T).max(1) if len(proto_vecs) else np.zeros(len(units))
    p_words = set(content_words(prompt))
    p_vec = emb.encode([prompt])[0] if len(tokens(prompt)) >= MIN_CONTEXT else None
    for u, sp, v in zip(units, proto, U):
        cw = content_words(u["text"])
        new = [w for w in cw if w not in p_words]
        echo = cos(v, p_vec) if p_vec is not None else 0.0
        if len(cw) <= 1:
            u["kind"], u["why"] = "bookkeeping", "no content words"
        elif sp >= emb.proto_t and len(new) <= 4:
            u["kind"], u["why"] = "bookkeeping", "procedural, checking, warming up or agreeing"
        elif p_vec is not None and echo >= emb.echo_t and len(new) <= 2:
            u["kind"], u["why"] = "restating", "restates the question"
        else:
            u["kind"], u["why"] = "substance", ""
        u["proto_sim"], u["echo_sim"] = round(float(sp), 3), round(echo, 3)


def thirds(values):
    v = sorted(x for x in values if x is not None)
    if len(v) < 6:
        return lambda x: None
    lo, hi = v[len(v) // 3], v[2 * len(v) // 3]
    return lambda x: None if x is None else ("low" if x < lo else "high" if x >= hi else "mid")


# signal -> (label when strong, label when weak)
FEATURES = {
    "substance_sec": ("more substance than most", "less substance than most"),
    "substance_share": ("focused (little bookkeeping)", "diluted (much bookkeeping or pausing)"),
    "answers_question": ("answers the question", "loosely tied to the question"),
    "instructor_uptake": ("instructor builds on it", "instructor doesn't pick it up"),
    "newness": ("new idea", "repeats earlier points"),
}


def rank_turns(res, meta):
    """Noteworthiness per turn (mean within-class percentile of FEATURES) and rank within student."""
    elig = [r for r in res.values() if r["substance_words"] >= MIN_WORDS]
    cols = {k: sorted(r[k] for r in elig if r[k] is not None) for k in FEATURES}

    def pct(k, x):
        v = cols[k]
        if x is None or len(v) < 2:
            return None
        below = sum(1 for y in v if y < x)
        equal = sum(1 for y in v if y == x)
        return (below + 0.5 * (equal - 1)) / (len(v) - 1)

    for r in res.values():
        r["noteworthiness"], r["rank"], r["strong"], r["weak"] = None, None, [], []
        if r["substance_words"] < MIN_WORDS:
            continue
        ps = {k: pct(k, r[k]) for k in FEATURES}
        ps = {k: p for k, p in ps.items() if p is not None}
        if not ps:
            continue
        r["noteworthiness"] = round(100 * sum(ps.values()) / len(ps))
        r["strong"] = [FEATURES[k][0] for k, p in sorted(ps.items(), key=lambda kv: -kv[1]) if p >= 2 / 3]
        r["weak"] = [FEATURES[k][1] for k, p in sorted(ps.items(), key=lambda kv: kv[1]) if p <= 1 / 3]
    by_student = {}
    for r in res.values():
        by_student.setdefault(meta[r["id"]]["student"], []).append(r)
    for rs in by_student.values():
        ranked = sorted((r for r in rs if r["noteworthiness"] is not None),
                        key=lambda r: (-r["noteworthiness"], meta[r["id"]]["start"]))
        for i, r in enumerate(ranked, 1):
            r["rank"] = i


def analyze_class(data, turns, cache, out: Path):
    """Returns {turn id: analysis}; writes analysis.csv and analysis.json in out."""
    phrases = load_phrases()
    texts = [t for c in cache.values() for t in (c["before"]["text"], c["student"]["text"], c["after"]["text"])]
    emb = get_embedder(texts + phrases)
    proto_vecs = emb.encode(phrases) if phrases else np.zeros((0, 1), np.float32)

    res = {}
    for t in sorted(turns, key=lambda t: t["start"]):
        c = cache.get(t["id"])
        if not c:
            continue
        before, after = c["before"]["text"], c["after"]["text"]
        units = sentences(c["student"]["words"])
        classify(units, before, emb, proto_vecs)
        sub = [u for u in units if u["kind"] == "substance"]
        sub_text = " ".join(u["text"] for u in sub)
        sub_sec = sum(u["end"] - u["start"] for u in sub)
        n_sub = len(tokens(sub_text))
        ok = n_sub >= MIN_WORDS
        sv = emb.encode([sub_text])[0] if ok else None
        r = {
            "id": t["id"], "units": units, "substance_text": sub_text,
            "speech_sec": t.get("speech"), "substance_sec": round(sub_sec, 1), "substance_words": n_sub,
            "substance_share": round(min(1.0, sub_sec / t["speech"]), 3) if t.get("speech") else None,
            "answers_question": round(cos(emb.encode([before])[0], sv), 3) if ok and len(tokens(before)) >= MIN_CONTEXT else None,
            "instructor_uptake": round(cos(sv, emb.encode([after])[0]), 3) if ok and len(tokens(after)) >= MIN_CONTEXT else None,
            "revoicing": None, "newness": None, "_vec": sv,
        }
        sc, ac = set(content_words(sub_text)), set(content_words(after))
        if ok and sc and len(tokens(after)) >= MIN_CONTEXT:
            r["revoicing"] = round(len(sc & ac) / len(sc), 3)
        res[t["id"]] = r

    # newness: compared with all earlier substantive student turns in this class
    earlier = []
    for r in res.values():
        if r["_vec"] is None:
            continue
        r["newness"] = round(1 - max(cos(r["_vec"], e) for e in earlier), 3) if earlier else 1.0
        earlier.append(r["_vec"])

    keys = ["answers_question", "instructor_uptake", "newness"]
    level = {k: thirds([r[k] for r in res.values()]) for k in keys}
    for r in res.values():
        r.pop("_vec")
        r["levels"] = {k: level[k](r[k]) for k in keys}

    meta = {t["id"]: t for t in turns}
    rank_turns(res, meta)
    with (out / "analysis.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "student", "video_sec", "speech_sec", "substance_sec", "substance_share", "substance_words",
                    "answers_question", "instructor_uptake", "revoicing", "newness", "noteworthiness", "rank_in_student",
                    "substance_text", "bookkeeping_text"])
        for r in res.values():
            t = meta[r["id"]]
            bk = " ".join(u["text"] for u in r["units"] if u["kind"] != "substance")
            w.writerow([r["id"], t["student"], round(t["start"], 1), r["speech_sec"], r["substance_sec"], r["substance_share"],
                        r["substance_words"], r["answers_question"], r["instructor_uptake"], r["revoicing"], r["newness"],
                        r["noteworthiness"], r["rank"], r["substance_text"], bk])
    (out / "analysis.json").write_text(json.dumps({"similarity": emb.name, "turns": res}, indent=1))
    return res, emb.name
