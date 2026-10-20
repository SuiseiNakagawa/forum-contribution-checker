// Behaviour of results/<class>/transcript.html: review buttons, ratings download, tabs, sorting.
const CID = document.body.dataset.cid, KEY = 'fcc-ratings-' + CID;
let ratings = {};
try { ratings = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) {}
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(ratings)); } catch (e) {} count(); };
const count = () => { const n = Object.values(ratings).filter(r => r.v).length;
  document.getElementById('nrated').textContent = n ? `${n} pick${n === 1 ? '' : 's'} rated` : 'No picks rated yet'; };
document.querySelectorAll('.rate').forEach(box => {
  const id = box.dataset.turn, r = ratings[id] || {};
  box.querySelectorAll('button').forEach(b => { if (b.dataset.v === r.v) b.classList.add('on');
    b.addEventListener('click', () => { const cur = ratings[id] || {}; cur.v = cur.v === b.dataset.v ? '' : b.dataset.v; ratings[id] = cur;
      box.querySelectorAll('button').forEach(x => x.classList.toggle('on', x.dataset.v === cur.v)); save(); }); });
  const inp = box.querySelector('input'); inp.value = r.note || '';
  inp.addEventListener('input', () => { const cur = ratings[id] || {}; cur.note = inp.value; ratings[id] = cur; save(); });
});
count();
document.getElementById('dl').addEventListener('click', () => {
  const cols = ['class_id','turn_id','video_time','student_no','rank_in_student','noteworthiness','substance_sec','substance_share',
                'answers_question','instructor_uptake','newness','rating','note'];
  const q = v => /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
  const rows = [cols.join(',')];
  document.querySelectorAll('.rate').forEach(box => { const d = box.dataset, r = ratings[d.turn] || {};
    rows.push([CID, d.turn, d.time, d.sno, d.rank, d.nw, d.sub, d.share, d.ans, d.upt, d.new, r.v || '', r.note || ''].map(x => q(String(x ?? ''))).join(',')); });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([rows.join('\n') + '\n'], { type: 'text/csv' }));
  a.download = `ratings_class_${CID}.csv`; document.body.append(a); a.click(); a.remove();
});
const tabs = document.querySelectorAll('.tab');
tabs.forEach(t => t.addEventListener('click', () => { tabs.forEach(x => x.classList.toggle('on', x === t));
  document.getElementById('bystudent').hidden = t.dataset.v !== 'bystudent'; document.getElementById('allturns').hidden = t.dataset.v !== 'allturns'; }));
const q = document.getElementById('q'), who = document.getElementById('who'), srt = document.getElementById('sort'),
      hb = document.getElementById('hidebk'), list = document.getElementById('list'), cards = [...list.children];
function f() { const t = q.value.toLowerCase(), w = who.value, k = srt.value;
  cards.slice().sort((a, b) => k === 't' ? a.dataset.t - b.dataset.t : (b.dataset[k] || -9) - (a.dataset[k] || -9)).forEach(d => list.appendChild(d));
  cards.forEach(d => { d.style.display = (!w || d.dataset.who === w) && (!t || d.textContent.toLowerCase().includes(t)) && (!hb.checked || d.dataset.mostlybk !== '1') ? '' : 'none'; }); }
[q, who, srt, hb].forEach(x => x.addEventListener('input', f));
