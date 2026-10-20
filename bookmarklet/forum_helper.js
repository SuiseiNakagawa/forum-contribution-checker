/* Forum contributions helper (bookmarklet source).
   Click on a Forum class page: lists student speaking turns from Forum's
   own event log. On the Assess Class > Video tab, clicking a turn jumps the
   video there. Runs entirely in your browser as you; sends nothing anywhere. */
(async () => {
  const PANEL_ID = 'fch-panel';
  const existing = document.getElementById(PANEL_ID);
  if (existing) { existing.remove(); return; }

  const GAP = 5;          /* s of no student speech that counts as "stands alone" */
  const MERGE = 3;        /* merge a student's events closer than this */
  const NOISE = 1;        /* ignore blips shorter than this as neighbours */

  const css = `
#fch-panel{position:fixed;top:12px;right:12px;bottom:12px;width:400px;max-width:calc(100vw - 24px);z-index:2147483647;
 background:#fff;color:#1d1d1f;border:1px solid #d2d2d7;border-radius:12px;box-shadow:0 12px 40px rgba(0,0,0,.18);
 font:13px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;display:flex;flex-direction:column;overflow:hidden}
#fch-panel *{box-sizing:border-box;font:inherit;color:inherit}
#fch-panel .hd{padding:12px 14px 8px;border-bottom:1px solid #e5e5ea}
#fch-panel .tt{display:flex;justify-content:space-between;align-items:center;gap:8px}
#fch-panel h2{margin:0;font-size:15px;font-weight:600}
#fch-panel .x{border:0;background:#f2f2f7;border-radius:6px;width:26px;height:26px;cursor:pointer;font-size:16px;line-height:1}
#fch-panel .sub{color:#6e6e73;font-size:12px;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#fch-panel .ctl{display:grid;grid-template-columns:1fr 1fr;gap:6px 8px;padding:8px 14px;border-bottom:1px solid #e5e5ea;font-size:12px}
#fch-panel .ctl label{display:flex;flex-direction:column;gap:2px;color:#6e6e73}
#fch-panel .ctl select,#fch-panel .ctl input[type=number]{border:1px solid #d2d2d7;border-radius:6px;padding:4px 6px;background:#fff;color:#1d1d1f}
#fch-panel .ctl .chk{display:flex;flex-direction:row;align-items:center;justify-content:flex-start;text-align:left;gap:6px;grid-column:1/3;color:#1d1d1f;margin:0}
#fch-panel input[type=checkbox]{width:auto;height:auto;margin:0;flex:none;position:static;opacity:1;appearance:auto}
#fch-panel .tt{cursor:move;user-select:none}
#fch-panel .btns{display:flex;gap:6px}
#fch-panel.min{bottom:auto!important;height:auto!important}
#fch-panel.min>:not(.hd):not(style){display:none!important}
#fch-panel .msg{margin:8px 14px 0;padding:8px 10px;border-radius:8px;background:#fff8e6;border:1px solid #f5d98b;font-size:12px}
#fch-panel .msg a{color:#0b57d0}
#fch-panel .list{overflow:auto;flex:1;padding:4px 6px 8px}
#fch-panel .row{display:block;width:100%;text-align:left;border:0;background:transparent;border-radius:8px;padding:7px 8px;cursor:pointer}
#fch-panel .row:hover{background:#f2f2f7}
#fch-panel .row.on{background:#e8f0fe}
#fch-panel .row.brk .nm,#fch-panel .row.brk .tm{opacity:.5}
#fch-panel .l1{display:flex;gap:8px;align-items:baseline}
#fch-panel .tm{font-variant-numeric:tabular-nums;color:#0b57d0;min-width:52px}
#fch-panel .nm{font-weight:600;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#fch-panel .ln{font-variant-numeric:tabular-nums;color:#6e6e73}
#fch-panel .bar{height:3px;border-radius:2px;background:#0b57d0;opacity:.35;margin:3px 0 0 60px}
#fch-panel .l2{color:#6e6e73;font-size:12px;margin-left:60px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#fch-panel .ft{padding:8px 14px;border-top:1px solid #e5e5ea;color:#6e6e73;font-size:11px}
#fch-panel .exp{display:flex;align-items:center;gap:8px;padding:8px 14px;border-bottom:1px solid #e5e5ea}
#fch-panel .exp button{border:0;border-radius:8px;background:#0b57d0;color:#fff;padding:6px 12px;cursor:pointer;font-weight:600;white-space:nowrap}
#fch-panel .exp button:disabled{opacity:.6;cursor:default}
#fch-panel .exp span{color:#6e6e73;font-size:11px;line-height:1.3}`;

  const el = (tag, attrs = {}, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === 'class') n.className = v; else if (k === 'text') n.textContent = v;
      else if (k.startsWith('on')) n.addEventListener(k.slice(2), v); else n.setAttribute(k, v);
    }
    kids.forEach((c) => c && n.append(c));
    return n;
  };
  const hms = (s) => { s = Math.max(0, Math.round(s)); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60;
    return (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(x).padStart(2, '0'); };

  const panel = el('div', { id: PANEL_ID });
  panel.append(el('style', { text: css }));
  const head = el('div', { class: 'hd' },
    el('div', { class: 'tt', title: 'Drag to move' }, el('h2', { text: 'Student contributions' }),
      el('div', { class: 'btns' },
        el('button', { class: 'x', title: 'Minimize', text: '–', onclick: (e) => {
          panel.classList.toggle('min'); e.currentTarget.textContent = panel.classList.contains('min') ? '+' : '–'; } }),
        el('button', { class: 'x', title: 'Close', text: '×', onclick: () => panel.remove() }))),
    el('div', { class: 'sub', text: 'Loading…' }));
  panel.append(head);
  document.body.append(panel);
  const sub = head.querySelector('.sub');
  head.querySelector('.tt').addEventListener('mousedown', (e) => {
    if (e.target.closest('button')) return;
    const r = panel.getBoundingClientRect(), dx = e.clientX - r.left, dy = e.clientY - r.top;
    const move = (ev) => {
      const top = Math.min(innerHeight - 40, Math.max(0, ev.clientY - dy));
      panel.style.left = Math.min(innerWidth - 120, Math.max(0, ev.clientX - dx)) + 'px';
      panel.style.top = top + 'px';
      panel.style.right = 'auto';
      if (!panel.classList.contains('min')) {
        panel.style.bottom = 'auto';
        panel.style.height = Math.max(160, Math.min(r.height, innerHeight - top - 12)) + 'px';
      }
    };
    const up = () => { removeEventListener('mousemove', move); removeEventListener('mouseup', up); };
    addEventListener('mousemove', move); addEventListener('mouseup', up); e.preventDefault();
  });
  const fail = (text, link) => {
    const m = el('div', { class: 'msg', text });
    if (link) m.append(' ', el('a', { href: link[1], text: link[0] }));
    panel.append(m); sub.textContent = '';
  };

  const cm = location.pathname.match(/classes\/(\d+)/);
  if (!cm) { fail('Open a Forum class page first, then click the button again.'); return; }
  const cid = cm[1];
  const get = (p) => fetch(p, { credentials: 'include', headers: { Accept: 'application/json' } })
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); });

  let cls, evs;
  try {
    [cls, evs] = await Promise.all([get(`/api/v1/classes/${cid}/class_edit_page`),
      get(`/api/v1/class_grader/classes/${cid}/class-events`)]);
  } catch (e) { fail(`Couldn't load this class's data (error ${e.message}). You may not have grader access to it.`); return; }

  /* A recording can have several parts (stopped and restarted). The class video is taken to be
     the parts joined in order, so wall-clock time maps to video time part by part. */
  const parts = (cls['recording-sessions'] || []).filter((r) => r['recording-started'])
    .map((r) => ({ s: Date.parse(r['recording-started']) / 1000,
                   e: r['recording-ended'] ? Date.parse(r['recording-ended']) / 1000 : Infinity }))
    .sort((a, b) => a.s - b.s);
  if (!parts.length) { fail('This class has no recording, so there is nothing to line up with.'); return; }
  let acc = 0;
  for (const x of parts) { x.off = acc; acc += x.e - x.s; }
  const recLen = acc;   /* Infinity if a part has no end time */
  const epoch = (iso) => Date.parse(iso) / 1000;
  const toVideo = (sec) => {   /* wall-clock seconds -> video seconds; null if not recorded */
    for (const x of parts) if (sec >= x.s - 1 && sec <= x.e + 1) return x.off + Math.max(0, sec - x.s);
    return null;
  };
  /* Forum's "timestamp" is in milliseconds: the END of speech for voice events, the start for others.
     The start-time/end-time strings are rounded down to whole seconds. */
  const msStamp = (e) => { const t = Number(e.timestamp); return Number.isFinite(t) && t > 1e12 ? t / 1000 : null; };
  const T = cls['teacher-user-id'];

  const meta = {}, order = [];
  for (const sec of (cls.timeline || {})['timeline-sections'] || []) {
    for (const g of sec['timeline-segments'] || []) {
      meta[String(g.id)] = { title: (g.details || {}).title || '', op: (g.details || {}).op || '' };
      order.push(String(g.id));
    }
  }
  const count = (arr) => arr.reduce((m, k) => ((m[k] = (m[k] || 0) + 1), m), {});
  const top = (m) => Object.keys(m).sort((a, b) => m[b] - m[a])[0];
  const voice = evs.filter((e) => e['event-type'] === 'voice' && e['actor-id'] !== T);
  const segRooms = count(evs.filter((e) => e['event-type'] === 'timeline-segment').map((e) => String(e['room-id'])));
  const main = top(segRooms) || top(count(voice.map((e) => String(e['room-id']))));

  const nameOf = (e) => { const a = e.actor || {};
    return `${a['first-name'] || ''} ${a['last-name'] || ''}`.trim() || `user ${e['actor-id']}`; };
  const raw = voice.map((e) => {
    const ms = (e['event-data'] || {}).duration;
    const d = typeof ms === 'number' ? ms / 1000 : null;
    const stamp = msStamp(e);
    let endW, startW;
    if (stamp !== null && d !== null) { endW = stamp; startW = stamp - d; }
    else { startW = epoch(e['start-time']); endW = d !== null ? startW + d : epoch(e['end-time']); }
    let s = toVideo(startW);
    if (s === null) { const en = toVideo(endW); if (en === null) return null; s = Math.max(0, en - (endW - startW)); }
    return { id: e['actor-id'], name: nameOf(e), room: String(e['room-id']), s, e: s + (endW - startW), sp: d ?? (endW - startW) };
  }).filter(Boolean).sort((a, b) => a.s - b.s);

  const turns = [];
  const byRoom = {};
  raw.forEach((x) => (byRoom[x.room] = byRoom[x.room] || []).push(x));
  for (const [room, list] of Object.entries(byRoom)) {
    const merged = [];
    for (const x of list) {
      const l = merged[merged.length - 1];
      if (l && l.id === x.id && x.s - l.e <= MERGE) { l.e = Math.max(l.e, x.e); l.sp += x.sp; }
      else merged.push({ ...x });
    }
    merged.forEach((t) => (t.main = room === main));
    turns.push(...merged);
  }
  turns.sort((a, b) => a.s - b.s);

  const marks = evs.filter((e) => e['event-type'] === 'timeline-segment' && String(e['room-id']) === main)
    .map((e) => { const w = msStamp(e) ?? epoch(e['start-time']);
      return [toVideo(w) ?? (w < parts[0].s ? 0 : null), String((e['event-data'] || {})['timeline-segment-id'])]; })
    .filter((m) => m[0] !== null).sort((a, b) => a[0] - b[0]);
  const segAt = (t) => { let sid = order[0]; for (const [w, s] of marks) { if (w <= t) sid = s; else break; }
    return meta[sid] || { title: '', op: '' }; };

  /* Breakouts: the recording follows one group, so main-room speech in that window may be credited
     to the wrong person, and the audio isn't the main room. A breakout runs from its lesson-plan click
     until the breakout room goes quiet (or, if no breakout speech was logged, until the next click). */
  const breakouts = marks.map(([w, sid], i) => ({ s: w, next: i + 1 < marks.length ? marks[i + 1][0] : recLen, op: (meta[sid] || {}).op }))
    .filter((m) => m.op === 'breakout')
    .map((m) => {
      const br = raw.filter((x) => x.room !== main && x.s >= m.s - 5 && x.s < m.next + 5);
      return { s: m.s, e: br.length ? Math.min(m.next, Math.max(...br.map((x) => x.e)) + 2) : m.next };
    });
  const inBreakout = (t) => breakouts.some((b) => t >= b.s && t < b.e);

  for (const t of turns) {
    let prev = null, next = null;
    for (const o of turns) {
      if (o.room !== t.room || o.id === t.id || o.sp < NOISE) continue;
      if (o.s < t.s && (!prev || o.e > prev.e)) prev = o;
      if (o.s > t.s && (!next || o.s < next.s)) next = o;
    }
    t.prev = prev; t.next = next;
    t.before = prev && t.s - prev.e < GAP ? prev : null;
    t.after = next && next.s - t.e < GAP ? next : null;
    t.alone = !t.before && !t.after;
    t.kind = t.alone ? 'Stands alone'
      : t.before && t.after ? 'Exchange between students'
      : t.before ? `Responds to ${t.before.name}` : `Followed by ${t.after.name}`;
    t.seg = segAt(t.s);
    t.breakout = t.main && inBreakout(t.s);
    if (t.breakout) t.kind = 'During breakouts (not transcribed or ranked)';
  }

  const mainTurns = turns.filter((t) => t.main);
  mainTurns.forEach((t, i) => (t.tid = `${cid}-${String(i + 1).padStart(3, '0')}`));
  const otherRooms = turns.length - mainTurns.length;
  const students = [...new Set(mainTurns.map((t) => t.name))].sort((a, b) => a.localeCompare(b));
  sub.textContent = `${cls['course-title'] || ''} · ${cls.title || ''}`;
  sub.title = sub.textContent;

  const sel = el('select', {}, el('option', { value: '', text: 'Everyone' }), ...students.map((s) => el('option', { value: s, text: s })));
  const minIn = el('input', { type: 'number', min: '0', step: '1', value: '4' });
  const sortSel = el('select', {}, el('option', { value: 'time', text: 'Time' }), el('option', { value: 'len', text: 'Longest first' }));
  const leadSel = el('select', {}, el('option', { value: '0', text: 'Right at the turn' }),
    el('option', { value: '5', text: '5 s before' }), el('option', { value: '15', text: '15 s before (hear the question)' }));
  leadSel.value = '5';
  const alone = el('input', { type: 'checkbox' });
  const ctl = el('div', { class: 'ctl' },
    el('label', {}, 'Student', sel), el('label', {}, 'At least (seconds)', minIn),
    el('label', {}, 'Sort by', sortSel), el('label', {}, 'Jump to', leadSel),
    el('label', { class: 'chk' }, alone, 'Only turns that stand alone (no other student within 5 s)'));
  panel.append(ctl);

  /* Save the turns plus a short-lived video link for the "Transcribe class" tool on the Mac. */
  const WIN = 20;  /* seconds of context before and after each turn */
  const expBtn = el('button', { text: 'Save for transcription' });
  const expTxt = el('span', { text: 'Saves the turns (at least the length above) to Downloads for the "Transcribe class" tool.' });
  expBtn.addEventListener('click', async () => {
    expBtn.disabled = true; expBtn.textContent = 'Preparing…';
    try {
      const urls = await get(`/api/v1/recording-sessions/${cid}/generate_recording_urls`);
      const url = urls.lowres || urls.highres;
      if (!url) throw new Error('no video link');
      const exp = Number(new URL(url).searchParams.get('Expires')) * 1000 || null;
      const min = Number(minIn.value) || 0;
      const chosen = mainTurns.filter((t) => t.sp >= min && !t.breakout);
      const clip = (t, lo, hi) => {   /* context windows never reach into a breakout */
        for (const b of breakouts) {
          if (b.e <= t.s && lo < b.e) lo = b.e;
          if (b.s >= t.e && hi > b.s) hi = b.s;
        }
        return [Math.min(lo, t.s), Math.max(hi, t.e)];
      };
      const r2 = (x) => Math.round(x * 100) / 100;
      const data = {
        format: 'forum-transcribe/v1', 'exported-at': new Date().toISOString(), 'class-id': Number(cid),
        timing: 'forum-ms', 'recording-parts': parts.length,
        course: cls['course-title'] || '', title: cls.title || '', date: cls.date || '',
        recording: { url, expires: exp ? new Date(exp).toISOString() : null, 'length-sec': isFinite(recLen) ? r2(recLen) : null },
        turns: chosen.map((t) => ({
          id: t.tid, student: t.name, start: r2(t.s), end: r2(t.e), speech: r2(t.sp), kind: t.kind, segment: t.seg.title,
          window: clip(t, Math.max(0, t.s - WIN, t.prev ? t.prev.e : 0),
                       Math.min(recLen, t.e + WIN, t.next ? t.next.s : Infinity)).map(r2),
        })),
      };
      const href = URL.createObjectURL(new Blob([JSON.stringify(data)], { type: 'application/json' }));
      const a = el('a', { href, download: `forum_class_${cid}.json` });
      document.body.append(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(href), 10000);
      expBtn.textContent = 'Saved ✓';
      expTxt.textContent = `${chosen.length} turns saved to Downloads. Now double-click "Transcribe class" in your forum-contribution-checker folder` +
        (exp ? ` before ${new Date(exp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} (the video link expires then).` : '.');
    } catch (e) {
      expBtn.textContent = 'Save for transcription';
      expTxt.textContent = `Couldn’t get the video link (${e.message}). You need grader access to this class's recording.`;
    }
    expBtn.disabled = false;
  });
  panel.append(el('div', { class: 'exp' }, expBtn, expTxt));

  const note = el('div', { class: 'msg', style: 'display:none' });
  panel.append(note);
  const list = el('div', { class: 'list' });
  panel.append(list);
  const foot = el('div', { class: 'ft' });
  panel.append(foot);

  const reviewUrl = location.pathname.replace(/(classes\/\d+).*/, '$1/review?tab=video');
  const video = () => document.querySelector('video');
  const maxSp = Math.max(1, ...mainTurns.map((t) => t.sp));

  const render = () => {
    const min = Number(minIn.value) || 0;
    let rows = mainTurns.filter((t) => t.sp >= min && (!sel.value || t.name === sel.value) && (!alone.checked || t.alone));
    if (sortSel.value === 'len') rows = rows.slice().sort((a, b) => b.sp - a.sp);
    list.replaceChildren(...rows.map((t) => {
      const b = el('button', { class: 'row' + (t.breakout ? ' brk' : ''), title: 'Jump the video here' },
        el('div', { class: 'l1' }, el('span', { class: 'tm', text: hms(t.s) }), el('span', { class: 'nm', text: t.name }),
          el('span', { class: 'ln', text: `${Math.round(t.sp)} s` })),
        el('div', { class: 'bar', style: `width:${Math.max(4, 100 * t.sp / maxSp) * 0.8}%` }),
        el('div', { class: 'l2', text: [t.kind, t.seg.title].filter(Boolean).join(' · ') }));
      b.addEventListener('click', () => {
        const v = video();
        if (!v) {
          note.replaceChildren('To jump to moments, open Assess Class → Video, then click the bookmark again. ',
            el('a', { href: reviewUrl, text: 'Open the video tab' }));
          note.style.display = ''; return;
        }
        list.querySelectorAll('.row.on').forEach((r) => r.classList.remove('on'));
        b.classList.add('on');
        v.currentTime = Math.max(0, t.s - Number(leadSel.value));
        const p = v.play(); if (p && p.catch) p.catch(() => {});
      });
      return b;
    }));
    const people = new Set(rows.map((t) => t.name)).size;
    const nb = rows.filter((t) => t.breakout).length;
    foot.textContent = `${rows.length} turns from ${people} students` +
      (nb ? ` · ${nb} during breakouts (not transcribed or ranked)` : '') +
      (otherRooms ? ` · ${otherRooms} breakout-room turns not shown` : '') +
      ' · Times are positions in the class video. Forum logs student speech only, so the instructor is never listed.';
  };
  [sel, minIn, sortSel, alone].forEach((c) => c.addEventListener('input', render));
  if (parts.length > 1) {
    panel.insertBefore(el('div', { class: 'msg', text: `This class was recorded in ${parts.length} parts (the recording was restarted). ` +
      'Times assume the video joins the parts in order; spot-check a turn after the restart.' }), list);
  }
  if (!video()) {
    note.replaceChildren('You are not on the video tab, so clicking a turn can’t jump yet. ',
      el('a', { href: reviewUrl, text: 'Open Assess Class → Video' }), ' and click the bookmark again.');
    note.style.display = '';
  }
  render();
})();
