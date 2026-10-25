"""
Self-contained HTML view of a DeepEval run (written next to report.md by deepeval_judge.py).

One file, no network: overview cards per metric, a category × metric heatmap, judge agreement,
and an explorer over every score (filter, failing-only, search; click a row for the question,
the agent's answer, the reference, the judge's reason and the tools used).
"""
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

METRIC_LABELS = {
    "tool_selection": "Tool selection",
    "faithfulness": "Faithfulness",
    "answer_relevancy": "Answer relevancy",
    "correctness": "Correctness",
}
METRIC_HELP = {
    "tool_selection": "Deterministic: an acceptable tool was used. Every gradeable item.",
    "faithfulness": "Strict: share of the answer's claims supported by the tool outputs.",
    "answer_relevancy": "Share of statements that address the question. Low often means verbose, not wrong.",
    "correctness": "G-Eval against the gold reference answer.",
}


def write_html_report(run_dir: Path, summary: Dict[str, Any], rows: List[Dict[str, Any]],
                      items: Dict[str, Dict[str, Any]], thresholds: Dict[str, float]) -> Path:
    explorer = []
    for r in rows:
        item = items.get(r["id"], {})
        explorer.append({
            "id": r["id"], "category": r["category"], "metric": r["metric"], "score": r["score"],
            "success": r["success"], "reason": r.get("reason") or "",
            "question": item.get("question", ""), "answer": item.get("response", ""),
            "reference": item.get("reference", ""), "tools": (item.get("tools") or {}).get("called") or [],
        })
    data = {
        "summary": summary, "rows": explorer, "thresholds": thresholds,
        "labels": METRIC_LABELS, "help": METRIC_HELP,
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    # Embedded as JSON; "</" is escaped so answer text can never close the script tag
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    out = run_dir / "deepeval" / "report.html"
    out.write_text(TEMPLATE.replace("__TITLE__", html.escape(f"DeepEval · {summary.get('run', '')}"))
                   .replace("__DATA__", payload))
    return out


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root {
    --bg: #f6f7f9; --panel: #ffffff; --tint: #eef0f4; --fg: #1a212b; --soft: #4a5464; --muted: #6a7484;
    --line: #dde1e8; --accent: #a3222e; --good: #1f7a4d; --warn: #a76a00; --bad: #b42331;
    --good-bg: #e3f3ea; --warn-bg: #fbf0d9; --bad-bg: #fbe4e6;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #11151b; --panel: #1a2029; --tint: #202733; --fg: #e4e8ee; --soft: #b3bcc9; --muted: #8e98a7;
      --line: #2e3642; --accent: #e8707a; --good: #5cc98f; --warn: #e6b450; --bad: #f07a85;
      --good-bg: #173527; --warn-bg: #3a2f16; --bad-bg: #3d1d22;
    }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--fg);
         font: 14px/1.5 -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; }
  main { max-width: 1180px; margin: 0 auto; padding: 28px 16px 60px; }
  h1 { font-size: 22px; margin: 0 0 4px; }
  h2 { font-size: 15px; margin: 34px 0 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
  .meta { color: var(--muted); font-size: 13px; }
  .meta code { background: var(--tint); padding: 1px 6px; border-radius: 4px; }
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px; }
  .card { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; }
  .card .name { font-weight: 600; }
  .card .big { font-size: 30px; font-weight: 650; margin: 6px 0 2px; font-variant-numeric: tabular-nums; }
  .card .sub { color: var(--muted); font-size: 12.5px; }
  .card .help { color: var(--muted); font-size: 12px; margin-top: 8px; }
  .bar { height: 6px; background: var(--tint); border-radius: 3px; margin-top: 10px; overflow: hidden; }
  .bar > span { display: block; height: 100%; border-radius: 3px; }
  table { width: 100%; border-collapse: collapse; background: var(--panel); border: 1px solid var(--line);
          border-radius: 10px; overflow: hidden; }
  th, td { padding: 9px 12px; text-align: left; border-bottom: 1px solid var(--line); vertical-align: top; }
  th { font-size: 12px; color: var(--muted); font-weight: 600; background: var(--tint); }
  td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
  .heat { font-weight: 600; text-align: center; }
  .pill { display: inline-block; min-width: 46px; text-align: center; padding: 1px 8px; border-radius: 999px;
          font-size: 12.5px; font-weight: 600; font-variant-numeric: tabular-nums; }
  .ok { color: var(--good); background: var(--good-bg); }
  .mid { color: var(--warn); background: var(--warn-bg); }
  .low { color: var(--bad); background: var(--bad-bg); }
  .na { color: var(--muted); }
  .agree { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; }
  .note { color: var(--muted); font-size: 13px; margin-top: 10px; }
  .filters { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 12px; }
  select, input[type=search] { background: var(--panel); color: var(--fg); border: 1px solid var(--line);
          border-radius: 6px; padding: 6px 9px; font: inherit; }
  input[type=search] { flex: 1 1 220px; }
  button { background: var(--panel); color: var(--fg); border: 1px solid var(--line); border-radius: 6px;
           padding: 6px 14px; font: inherit; cursor: pointer; }
  button:hover { background: var(--tint); }
  label.chk { display: flex; gap: 6px; align-items: center; color: var(--soft); }
  tr.row { cursor: pointer; }
  tr.row:hover td { background: var(--tint); }
  tr.detail td { background: var(--bg); }
  .detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
  .detail-grid .full { grid-column: 1 / -1; }
  .k { font-size: 11.5px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); margin-bottom: 4px; }
  .v { white-space: pre-wrap; word-break: break-word; background: var(--panel); border: 1px solid var(--line);
       border-radius: 6px; padding: 8px 10px; max-height: 320px; overflow: auto; }
  .count { color: var(--muted); font-size: 13px; }
  @media (max-width: 720px) { .detail-grid { grid-template-columns: 1fr; } th:nth-child(2), td:nth-child(2) { display: none; } }
</style>
</head>
<body>
<main>
  <h1>DeepEval report</h1>
  <div class="meta" id="meta"></div>

  <h2>Overview</h2>
  <div class="cards" id="cards"></div>

  <h2>By category</h2>
  <div id="heat"></div>

  <div id="agreement"></div>

  <h2>All scores</h2>
  <div class="filters">
    <select id="f-cat"><option value="">All categories</option></select>
    <select id="f-metric"><option value="">All metrics</option></select>
    <label class="chk"><input type="checkbox" id="f-fail"> Failing only</label>
    <label class="chk"><input type="checkbox" id="f-llm" checked> LLM metrics only</label>
    <input type="search" id="f-q" placeholder="Search question, answer or reason">
    <span class="count" id="count"></span>
  </div>
  <table>
    <thead><tr><th>Item</th><th>Category</th><th>Metric</th><th class="num">Score</th><th>Result</th><th>Judge's reason</th></tr></thead>
    <tbody id="rows"></tbody>
  </table>
  <p><button id="more" hidden>Show all</button></p>
  <p class="note">Regenerate: <code>.venv-eval/bin/python -m eval.deepeval_judge --run &lt;run&gt; --report-only</code></p>
</main>
<script id="data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const S = D.summary, M = S.metrics || {};
const el = (tag, attrs = {}, ...kids) => {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) k === 'class' ? n.className = v : n.setAttribute(k, v);
  for (const k of kids) n.append(k instanceof Node ? k : document.createTextNode(k ?? ''));
  return n;
};
const fmt = v => v == null ? '–' : (+v).toFixed(2);
const pct = v => v == null ? '–' : Math.round(v * 100) + '%';
const tone = (v, t) => v == null ? 'na' : v >= (t ?? 0.8) ? 'ok' : v >= (t ?? 0.8) * 0.75 ? 'mid' : 'low';
const color = v => v == null ? 'var(--tint)' : v >= 0.85 ? 'var(--good)' : v >= 0.6 ? 'var(--warn)' : 'var(--bad)';

document.getElementById('meta').append(
  'Run ', el('code', {}, S.run || ''), ' · judge ', el('code', {}, S.judge || ''), ' · generated ', D.generated);

const cards = document.getElementById('cards');
for (const key of ['tool_selection', 'faithfulness', 'answer_relevancy', 'correctness']) {
  const m = M[key]; if (!m) continue;
  const bar = el('div', {class: 'bar'}, el('span', {style: `width:${(m.mean || 0) * 100}%;background:${color(m.mean)}`}));
  cards.append(el('div', {class: 'card'},
    el('div', {class: 'name'}, D.labels[key] || key),
    el('div', {class: 'big'}, fmt(m.mean)),
    el('div', {class: 'sub'}, `${pct(m.pass_rate)} pass (≥ ${D.thresholds[key]}) · ${m.n} items` +
      (m.judge_errors ? ` · ${m.judge_errors} judge errors` : '')),
    bar, el('div', {class: 'help'}, D.help[key] || '')));
}
if (M.oos_refusal) {
  const r = M.oos_refusal;
  cards.append(el('div', {class: 'card'}, el('div', {class: 'name'}, 'Out-of-scope refusal'),
    el('div', {class: 'big'}, pct(r.rate)), el('div', {class: 'sub'}, `${r.n} items · deterministic`),
    el('div', {class: 'bar'}, el('span', {style: `width:${r.rate * 100}%;background:${color(r.rate)}`})),
    el('div', {class: 'help'}, 'Off-topic questions stopped by the intent gate.')));
}

// Category × metric heatmap
const metrics = ['correctness', 'faithfulness', 'answer_relevancy', 'tool_selection'].filter(k => M[k]);
const cats = [...new Set(D.rows.map(r => r.category))].sort();
const avg = (c, k) => { const v = D.rows.filter(r => r.category === c && r.metric === k && r.score != null).map(r => r.score);
                        return v.length ? {mean: v.reduce((a, b) => a + b, 0) / v.length, n: v.length} : null; };
const heat = el('table', {}, el('thead', {}, el('tr', {}, el('th', {}, 'Category'),
  ...metrics.map(k => el('th', {class: 'num'}, D.labels[k])))));
const hb = el('tbody');
for (const c of cats) {
  hb.append(el('tr', {}, el('td', {}, c), ...metrics.map(k => {
    const a = avg(c, k);
    return el('td', {class: 'heat', title: a ? `${a.n} items` : 'not scored'},
      a ? el('span', {class: 'pill ' + tone(a.mean, D.thresholds[k])}, fmt(a.mean)) : el('span', {class: 'na'}, '–'));
  })));
}
heat.append(hb);
document.getElementById('heat').append(heat);

// Judge agreement
if (S.judge_agreement) {
  const a = S.judge_agreement;
  const box = document.getElementById('agreement');
  box.append(el('h2', {}, 'Agreement with the run\\'s Gemini judge (faithfulness)'));
  const stat = (name, value, sub) => el('div', {class: 'card'}, el('div', {class: 'name'}, name),
    el('div', {class: 'big'}, value), el('div', {class: 'sub'}, sub));
  box.append(el('div', {class: 'agree'},
    stat('DeepEval mean', fmt(a.deepeval_mean), `${a.n} items scored by both`),
    stat('Gemini judge mean', fmt(a.gemini_judge_mean), 'same-family judge'),
    stat('Pearson r', a.pearson == null ? '–' : a.pearson.toFixed(2), 'noisy on small samples'),
    stat('Agree: fully supported', pct(a.fully_supported_agreement), 'same verdict on "every claim supported"')));
  box.append(el('p', {class: 'note'}, 'Where the judges disagree, read the item by hand: that is where a score is least trustworthy.'));
}

// Explorer
const fc = document.getElementById('f-cat'), fm = document.getElementById('f-metric');
cats.forEach(c => fc.append(el('option', {value: c}, c)));
[...new Set(D.rows.map(r => r.metric))].sort().forEach(m => fm.append(el('option', {value: m}, D.labels[m] || m)));
const tbody = document.getElementById('rows');
const PAGE = 50;
let showAll = false;
function render() {
  const cat = fc.value, met = fm.value, fail = document.getElementById('f-fail').checked;
  const llmOnly = document.getElementById('f-llm').checked && !met;
  const q = document.getElementById('f-q').value.toLowerCase();
  const list = D.rows.filter(r => (!cat || r.category === cat) && (!met || r.metric === met)
      && (!fail || r.success === false) && (!llmOnly || r.metric !== 'tool_selection')
      && (!q || (r.question + ' ' + r.answer + ' ' + r.reason).toLowerCase().includes(q)))
    .sort((a, b) => (a.score ?? 2) - (b.score ?? 2) || a.id.localeCompare(b.id));
  tbody.replaceChildren();
  const more = document.getElementById('more');
  more.hidden = showAll || list.length <= PAGE;
  more.textContent = `Show all ${list.length}`;
  for (const r of showAll ? list : list.slice(0, PAGE)) {
    const result = r.score == null ? el('span', {class: 'na'}, 'error')
      : el('span', {class: 'pill ' + (r.success ? 'ok' : 'low')}, r.success ? 'pass' : 'fail');
    const row = el('tr', {class: 'row'}, el('td', {}, r.id), el('td', {}, r.category), el('td', {}, D.labels[r.metric] || r.metric),
      el('td', {class: 'num'}, el('span', {class: 'pill ' + tone(r.score, D.thresholds[r.metric])}, fmt(r.score))),
      el('td', {}, result), el('td', {}, (r.reason || '').slice(0, 140) + ((r.reason || '').length > 140 ? '…' : '')));
    const box = (k, v, full) => el('div', {class: full ? 'full' : ''}, el('div', {class: 'k'}, k), el('div', {class: 'v'}, v || '–'));
    const detail = el('tr', {class: 'detail', hidden: ''}, el('td', {colspan: '6'}, el('div', {class: 'detail-grid'},
      box('Question', r.question, true), box("Agent's answer", r.answer), box('Reference answer', r.reference),
      box("Judge's reason", r.reason, true), box('Tools used', r.tools.join(', '), true))));
    row.addEventListener('click', () => detail.hidden = !detail.hidden);
    tbody.append(row, detail);
  }
  const shown = showAll ? list.length : Math.min(list.length, PAGE);
  document.getElementById('count').textContent = `${shown} shown · ${list.length} match · ${D.rows.length} scores`;
}
document.getElementById('more').addEventListener('click', () => { showAll = true; render(); });
['f-cat', 'f-metric', 'f-fail', 'f-llm'].forEach(id => document.getElementById(id).addEventListener('change', () => { showAll = false; render(); }));
document.getElementById('f-q').addEventListener('input', render);
render();
</script>
</body>
</html>
"""
