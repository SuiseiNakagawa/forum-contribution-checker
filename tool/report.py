"""HTML pages for the results: one page per class and an index of classes."""
from __future__ import annotations

import html
import json
from pathlib import Path

ASSETS = Path(__file__).resolve().parent / "report_assets"
CSS = (ASSETS / "style.css").read_text()
JS = (ASSETS / "page.js").read_text()


def hms(sec: float) -> str:
    """Seconds -> m:ss or h:mm:ss (video position)."""
    sec = max(0, int(round(sec)))
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


PILL_NAMES = {"answers_question": "Answers the question", "instructor_uptake": "Instructor picks it up",
              "newness": "New vs earlier turns"}
TOP_N = 3   # picks per student shown with review buttons


def _student_html(c, a):
    e = html.escape
    if a and a["units"]:
        return " ".join(
            e(u["text"]) if u["kind"] == "substance" else
            f'<span class="{"rs" if u["kind"] == "restating" else "bk"}" title="{e(u["why"])}">{e(u["text"])}</span>'
            for u in a["units"])
    return e(c["student"]["text"]) or '<span class="empty">(no words recognised)</span>'


def _ctx(c, label, part):
    txt = c[part]["text"]
    return f'<div class="ctx"><b>{label}</b>{html.escape(txt)}</div>' if txt else ""


def _snippet(text, n=70):
    ws = text.split()
    return " ".join(ws[:n]) + (" ..." if len(ws) > n else "")


def write_report(data, turns, cache, out: Path, analysis=None, sim_name="") -> Path:
    e = html.escape
    analysis = analysis or {}
    students = sorted({t["student"] for t in turns}, key=str.lower)
    sno = {s: i for i, s in enumerate(students, 1)}
    done = [t for t in turns if t["id"] in cache]
    missing = len(turns) - len(done)

    # ---- By student
    blocks_s = []
    for s in students:
        ts = [t for t in done if t["student"] == s]
        if not ts:
            continue
        ranked = sorted((t for t in ts if (analysis.get(t["id"]) or {}).get("rank")),
                        key=lambda t: analysis[t["id"]]["rank"])
        unranked = [t for t in ts if t not in ranked]
        picks = []
        for t in ranked[:TOP_N]:
            a, c = analysis[t["id"]], cache[t["id"]]
            why = ""
            if a["strong"]:
                why += f'<span class="s">Strong: {e(", ".join(a["strong"]))}</span>'
            if a["weak"]:
                why += (" &middot; " if why else "") + f'<span class="w">Weak: {e(", ".join(a["weak"]))}</span>'
            fmt = lambda x: "" if x is None else x
            picks.append(
                f'<div class="pick"><div class="hd"><span class="rk">#{a["rank"]}</span><span class="tm">{hms(t["start"])}</span>'
                f'<span class="nw">Noteworthiness {a["noteworthiness"]}<span class="meter"><i style="width:{a["noteworthiness"]}%"></i></span></span>'
                f'<span class="info">{a["substance_sec"]:.0f} s substance of a {round(t["speech"])} s turn</span></div>'
                f'<div class="why">{why}</div>'
                f'<div class="say">{e(_snippet(a["substance_text"]))}</div>'
                f'<details class="cx"><summary>Context (before / full turn / after)</summary>{_ctx(c, "Before", "before")}'
                f'<div class="say">{_student_html(c, a)}</div>{_ctx(c, "After", "after")}</details>'
                f'<div class="rate" data-turn="{e(t["id"])}" data-time="{hms(t["start"])}" data-sno="{sno[s]}" data-rank="{a["rank"]}" '
                f'data-nw="{a["noteworthiness"]}" data-sub="{a["substance_sec"]}" data-share="{fmt(a["substance_share"])}" '
                f'data-ans="{fmt(a["answers_question"])}" data-upt="{fmt(a["instructor_uptake"])}" data-new="{fmt(a["newness"])}">'
                f'<span class="small">Matches your memory?</span>'
                f'<button data-v="yes">Noteworthy</button><button data-v="no">Not really</button><button data-v="unsure">Can\'t recall</button>'
                f'<input placeholder="Note (optional, avoid names)"></div></div>')
        rest = ranked[TOP_N:] + unranked
        more = ""
        if rest:
            rows = "".join(
                f'<div class="row"><span class="tm">{hms(t["start"])}</span><span>'
                + (f'#{analysis[t["id"]]["rank"]} &middot; noteworthiness {analysis[t["id"]]["noteworthiness"]}'
                   if t in ranked else "too little substance to rank")
                + f' &middot; {round(t["speech"])} s turn</span></div>' for t in sorted(rest, key=lambda t: t["start"]))
            more = f'<details class="more"><summary>{len(rest)} more turn{"s" if len(rest) != 1 else ""}</summary>{rows}</details>'
        if not picks:
            picks.append('<div class="small">No turn with enough substance to rank.</div>')
        blocks_s.append(f'<section class="student"><div class="shd"><h2>{e(s)}</h2>'
                        f'<span class="info">{len(ts)} turn{"s" if len(ts) != 1 else ""} &middot; {len(ranked)} ranked</span></div>'
                        f'{"".join(picks)}{more}</section>')

    # ---- All turns
    blocks_a = []
    for t in turns:
        c = cache.get(t["id"])
        if not c:
            continue
        a = analysis.get(t["id"])
        sub_html, pills, attrs = "", "", ""
        if a:
            share = a["substance_share"] or 0
            sub_html = (f'<span class="nw">{a["substance_sec"]:.0f} s substance'
                        f'<span class="meter"><i style="width:{100 * share:.0f}%"></i></span></span>')
            lv = a["levels"]
            if any(lv.values()):
                pills = '<div class="pills">' + "".join(
                    f'<span class="pill {lv[k]}">{PILL_NAMES[k]}: {lv[k]}</span>' for k in PILL_NAMES if lv.get(k)) + "</div>"
            elif a["substance_words"] < 8:
                pills = '<div class="pills"><span class="pill">Too little substance to judge</span></div>'
            attrs = (f' data-sub="{a["substance_sec"]}" data-mostlybk="{1 if share < 0.3 else 0}"'
                     + (f' data-nw="{a["noteworthiness"]}"' if a["noteworthiness"] is not None else "")
                     + "".join(f' data-{k}="{a[v]}"' for k, v in
                               [("ans", "answers_question"), ("upt", "instructor_uptake"), ("new", "newness")] if a[v] is not None))
        blocks_a.append(
            f'<div class="turn" data-who="{e(t["student"])}" data-t="{t["start"]}"{attrs}><div class="hd">'
            f'<span class="tm">{hms(t["start"])}</span><span class="who">{e(t["student"])}</span>'
            f'<span class="info">{round(t["speech"])} s turn &middot; {e(t.get("kind", ""))}'
            f'{" &middot; " + e(t["segment"]) if t.get("segment") else ""}</span>{sub_html}</div>'
            f'{pills}{_ctx(c, "Before", "before")}<div class="say">{_student_html(c, a)}</div>{_ctx(c, "After", "after")}</div>')

    help_html = (
        '<details class="help"><summary>How to read this page</summary>'
        '<p><b>Noteworthiness</b> (0-100) averages five signals, each compared with the rest of this class: how much '
        'substance the turn has, how little of it is bookkeeping, how closely it answers what was said just before, how much '
        'the instructor builds on it afterwards, and how new it is compared with earlier student turns. '
        '"Strong" and "Weak" list which signals pushed a turn up or down. Nothing was trained; it is a rough guide for '
        'deciding what to listen to.</p>'
        '<p>In transcripts, <b>black</b> text is substance and <span style="color:var(--faint)">grey</span> is bookkeeping '
        '(checking the question, warming up, agreeing, handing off). "Before" and "after" are whatever was said around the '
        f'student, usually the instructor. Similarity: {e(sim_name or "n/a")}. Automatic transcripts make mistakes, '
        'especially with names and technical terms. Times are positions in the class video.</p></details>')
    review_html = ('<div class="review"><b>Reviewing?</b> For each student, check the top picks against your memory of the class '
                   'and mark them. Then click <b>Download ratings</b> and send the file back. It contains no names or '
                   'transcript text (keep names out of the notes too). Your marks are kept in this browser if you close the page.</div>')
    options = "".join(f'<option value="{e(s)}">{e(s)}</option>' for s in students)
    no_analysis = "" if analysis else '<div class="review">Analysis unavailable for this run; showing transcripts only.</div>'
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(data.get("title") or f"Class {data['class-id']}")}</title>
<style>{CSS}</style></head><body data-cid="{e(str(data['class-id']))}"><main>
<div class="small"><a href="../index.html">&larr; All classes</a></div>
<h1>{e(data.get("title") or f"Class {data['class-id']}")}</h1>
<div class="meta">{e(data.get("course", ""))} &middot; {e((data.get("date") or "")[:10])} &middot; {len(done)} turns transcribed{f" ({missing} not yet, run again to finish)" if missing else ""}</div>
{no_analysis}{review_html}{help_html}
<div class="top"><button class="tab on" data-v="bystudent">By student</button><button class="tab" data-v="allturns">All turns</button>
<span class="rated" id="nrated"></span><button class="btn" id="dl">Download ratings</button></div>
<div id="bystudent">{"".join(blocks_s) or '<p class="small">Nothing to rank yet.</p>'}</div>
<div id="allturns" hidden>
<div class="bar"><input type="search" id="q" placeholder="Search names or words..." autocomplete="off">
<select id="who"><option value="">Everyone</option>{options}</select>
<select id="sort"><option value="t">Sort: time</option><option value="nw">Sort: noteworthiness</option><option value="sub">Sort: most substance</option>
<option value="ans">Sort: answers the question</option><option value="upt">Sort: instructor picks it up</option><option value="new">Sort: newest idea</option></select>
<label><input type="checkbox" id="hidebk"> Hide mostly bookkeeping</label></div>
<div id="list">{"".join(blocks_a)}</div></div>
<p class="note">Made by the forum-contribution-checker tool. Everything on this page stays on this computer.</p>
</main><script>{JS}</script></body></html>"""
    path = out / "transcript.html"
    path.write_text(page)
    return path


def write_index(results: Path) -> Path:
    """results/index.html: every class processed so far."""
    e = html.escape
    rows = []
    for exp in sorted(results.glob("*/export.json")):
        try:
            d = json.loads(exp.read_text())
        except Exception:
            continue
        page = exp.parent / "transcript.html"
        n_done = sum(1 for l in (exp.parent / "transcripts.jsonl").read_text().splitlines() if l.strip()) \
            if (exp.parent / "transcripts.jsonl").exists() else 0
        title = e(d.get("title") or exp.parent.name)
        link = f'<a href="{exp.parent.name}/transcript.html">{title}</a>' if page.exists() else title
        rows.append(((d.get("date") or ""), f'<tr><td>{e((d.get("date") or "")[:10])}</td><td>{e(d.get("course", ""))}</td>'
                     f'<td>{link}</td><td>{n_done} of {len(d.get("turns", []))}</td></tr>'))
    body = "".join(r for _, r in sorted(rows, reverse=True)) or '<tr><td colspan="4">No classes yet.</td></tr>'
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Forum classes</title><style>{CSS}
table{{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}}
td,th{{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);font-size:14px}} th{{color:var(--mute);font-weight:600;font-size:13px}}
</style></head><body><main><h1>Forum classes</h1>
<div class="meta">Every class transcribed on this computer. Open one to see each student's most noteworthy turns.</div>
<div class="review"><b>Reviewing?</b> In each class, mark whether the top picks match your memory, then click
<b>Download ratings</b> on that page and send the files back. They contain no names or transcript text.</div>
<table><tr><th>Date</th><th>Course</th><th>Class</th><th>Turns transcribed</th></tr>{body}</table></main></body></html>"""
    path = results / "index.html"
    path.write_text(page)
    return path
