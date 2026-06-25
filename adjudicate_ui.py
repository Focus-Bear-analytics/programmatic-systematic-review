"""Human adjudication UI for two-rater LLM disagreements.

The protocol calls for two LLM raters with a HUMAN adjudicating disagreements.
This is a small self-contained local web app (Python standard library only —
no Flask/Streamlit needed) that:

  * loads the two-rater output (``enriched.csv``; or resumes ``adjudicated.csv``)
  * auto-resolves rows where both raters already agree on every consensus field
  * presents each remaining DISAGREEMENT one at a time: title, abstract, and the
    two raters' labels side by side, with the conflicting fields highlighted
  * lets you pick the Final value per field (keyboard-driven), then writes
    ``Final_<field>`` + ``Human_<field>`` and marks ``Adjudicated = human``
  * is resumable — already-adjudicated rows are skipped on restart

Usage:
    poetry run python adjudicate_ui.py [<config>]   # default: adults
    # then open http://localhost:8000

Keyboard shortcuts (in the browser):
    a / b     pick rater A's / rater B's value for the focused field
    1..9      pick the n-th allowed value for the focused field
    Tab       move focus to the next field
    Enter     save this paper and go to the next
    [ / ]     previous / next paper without saving
"""

from __future__ import annotations

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pandas as pd

sys.path.insert(0, os.getcwd())
from steps.config import load_config, set_active  # noqa: E402
from steps.constants import COL_ABSTRACT, COL_TITLE, DUPLICATE_COL, NO, YES  # noqa: E402
from steps.io import is_missing_abstract  # noqa: E402
from steps.schema import ALLOWED, CONSENSUS_FIELDS  # noqa: E402

PORT = int(os.getenv("ADJ_UI_PORT", "8000"))
ADJUDICATED_COL = "Adjudicated"
HUMAN = "human"
# Show every disagreement (ADJ_UI_ALL=1) instead of only decision-relevant ones.
SHOW_ALL = os.getenv("ADJ_UI_ALL", "0") not in ("0", "", "false", "False")

# A consensus field for which BOTH raters pick an excluding value — NOT necessarily
# the SAME one. If both raters agree the paper is excluded on a criterion (e.g. one
# says telecoaching and the other telecounselling — both are out; or one says review
# and the other commentary — both non-empirical), then no human adjudication of any
# field could flip the include/exclude outcome, so the paper is "dead" and skipped.
# This is what shrinks the human queue: we don't ask the human to resolve
# disagreements on papers already excluded on some criterion by both raters.
EXCLUDING_AGREED = {
    "has_adults": {"no"},
    "neurotypes": {"neither_adhd_nor_autistic"},
    "study_type": {"review", "protocol", "proposal", "commentary"},
    "intervention_type": {
        "no_intervention", "data_collection_only", "parent_training",
        "telecoaching", "telecounselling", "wearable", "vr_ar", "video_modeling",
        "non_software_based",
    },
}

# The mirror image: values that all KEEP the paper in on that criterion. If both
# raters pick an including value (need not be the same — e.g. one says audhd and
# the other autistic; or one mobile_app and the other web_app), the paper passes
# that criterion regardless, so the disagreement can't flip inclusion and needs
# no human adjudication. A row is only queued when some field STRADDLES the
# include/exclude line (one rater in, the other out/ambiguous).
INCLUDING_AGREED = {
    "has_adults": {"yes"},
    "study_type": {"empirical_with_results", "qualitative_only_study", "case_study"},
    "intervention_type": {"mobile_app", "web_app", "software_tool"},
    "neurotypes": {"adhd", "autistic", "audhd"},
}

_lock = threading.Lock()


class State:
    """Holds the working DataFrame, the disagreement queue, and persistence."""

    def __init__(self, slug: str):
        self.cfg = load_config(slug)
        # Optionally point at a review sub-directory (e.g. ADJ_REVIEW_SUBDIR=snowball
        # to adjudicate the snowball arm's snowball/enriched.csv instead of the base
        # review), matching how classify-snowball.py isolates its outputs.
        subdir = os.getenv("ADJ_REVIEW_SUBDIR", "").strip()
        if subdir:
            import dataclasses
            self.cfg = dataclasses.replace(self.cfg, review_subdir=subdir)
        set_active(self.cfg)
        # Only fields that affect THIS review's inclusion drive the queue. The age
        # gate uses screening.require_age (has_adults for the adults review); the
        # OTHER age field (has_under_18) can't change inclusion, so a disagreement
        # on it alone must NOT require adjudication.
        age = {"has_adults", "has_under_18"}
        require_age = (self.cfg.raw.get("screening") or {}).get("require_age")
        self.queue_fields = ([f for f in CONSENSUS_FIELDS if f not in age or f == require_age]
                             if require_age in age else list(CONSENSUS_FIELDS))
        self.slug = slug
        self.a_pref, self.b_pref, self.a_label, self.b_label = ("", "", "", "")
        self.out_path = self.cfg.adjudicated_csv
        self.df: pd.DataFrame = pd.DataFrame()
        self.queue: list[int] = []
        self._load()

    # --- loading -----------------------------------------------------------

    def _resolve_prefixes(self, df: pd.DataFrame) -> None:
        """Pick the rater column prefixes, falling back to legacy names if needed.

        Lets the UI work on EXISTING data (OpenAI_/Gemini_ columns) as well as
        fresh runs with the configured prefixes (e.g. Nova_/Sonnet_).
        """
        a = self.cfg.rater_a.column_prefix
        b = self.cfg.rater_b.column_prefix
        a_label, b_label = self.cfg.rater_a.label, self.cfg.rater_b.label

        def has_cols(pref: str) -> bool:
            return any(f"{pref}_{f}" in df.columns for f in CONSENSUS_FIELDS)

        if not has_cols(a) and has_cols("OpenAI"):
            a, a_label = "OpenAI", f"{a_label} (legacy col: OpenAI)"
        if not has_cols(b) and has_cols("Gemini"):
            b, b_label = "Gemini", f"{b_label} (legacy col: Gemini)"
        # Combined dataset (build-combined-dataset.py) normalises both arms'
        # raters into RaterA_/RaterB_ columns; per-row model is in RaterA_model/
        # RaterB_model. Use those when present.
        if not has_cols(a) and has_cols("RaterA"):
            a, a_label = "RaterA", "Rater A"
        if not has_cols(b) and has_cols("RaterB"):
            b, b_label = "RaterB", "Rater B"
        self.a_pref, self.b_pref, self.a_label, self.b_label = a, b, a_label, b_label

    def _ensure_final_cols(self, df: pd.DataFrame) -> pd.DataFrame:
        for f in CONSENSUS_FIELDS:
            for col in (f"Final_{f}", f"Human_{f}"):
                if col not in df.columns:
                    df[col] = ""
        if ADJUDICATED_COL not in df.columns:
            df[ADJUDICATED_COL] = ""
        return df.astype(
            {c: object for c in df.columns if c.startswith(("Final_", "Human_")) or c == ADJUDICATED_COL}
        )

    def _nz(self, v) -> str:
        return str(v).strip().lower()

    def _present(self, v) -> bool:
        s = self._nz(v)
        return s not in ("", "nan")

    def _field_includes(self, f: str, av, bv) -> bool:
        """True if both raters keep the paper IN on field f — i.e. equal-and-not-
        excluding, or both in the including set. Used to detect rows that are
        included regardless of how the disagreement is resolved."""
        av, bv = self._nz(av), self._nz(bv)
        if av == bv:
            return av not in EXCLUDING_AGREED.get(f, set())
        inc = INCLUDING_AGREED.get(f, set())
        return av in inc and bv in inc

    def _load(self) -> None:
        # Resume from adjudicated.csv if present, else start from enriched.csv.
        if os.path.exists(self.out_path):
            df = pd.read_csv(self.out_path, dtype=str).fillna("")
            src = self.out_path
        elif os.path.exists(self.cfg.enriched_csv):
            df = pd.read_csv(self.cfg.enriched_csv, dtype=str).fillna("")
            src = self.cfg.enriched_csv
        else:
            raise FileNotFoundError(
                f"No enriched.csv or adjudicated.csv for config '{self.slug}'. "
                "Run the classify step first."
            )
        self._resolve_prefixes(df)
        df = self._ensure_final_cols(df)

        # Agreement pass + queue build (mirrors steps/adjudicate.py).
        queue_all: list[int] = []      # every disagreement
        queue_relevant: list[int] = []  # disagreements that could change inclusion
        agreed = 0
        skipped_dead = 0
        for idx, row in df.iterrows():
            if str(row.get(DUPLICATE_COL, "")).strip().upper() == YES:
                continue
            if is_missing_abstract(str(row.get(COL_ABSTRACT, "") or "")):
                continue
            a = {f: row.get(f"{self.a_pref}_{f}") for f in self.queue_fields}
            b = {f: row.get(f"{self.b_pref}_{f}") for f in self.queue_fields}
            if not all(self._present(a[f]) and self._present(b[f]) for f in self.queue_fields):
                continue
            already = str(row.get(ADJUDICATED_COL, "")).strip().lower()
            if already in (HUMAN, "y", "yes", "no", "n"):
                continue  # resolved already (human, or auto-agreed)
            if all(self._nz(a[f]) == self._nz(b[f]) for f in self.queue_fields):
                for f in self.queue_fields:
                    df.at[idx, f"Final_{f}"] = a[f]
                df.at[idx, ADJUDICATED_COL] = NO
                agreed += 1
                continue
            # It's a disagreement on >= 1 field.
            queue_all.append(idx)
            # Outcome is already determined (no human needed) if EITHER:
            #  - dead: some field has BOTH raters on an excluding value -> excluded; or
            #  - included: EVERY field has both raters on an including value -> included.
            # Only when some field STRADDLES the line (and nothing is dead) can a
            # human change the include/exclude outcome.
            dead = any(
                self._nz(a[f]) in EXCLUDING_AGREED.get(f, set())
                and self._nz(b[f]) in EXCLUDING_AGREED.get(f, set())
                for f in self.queue_fields
            )
            included = all(self._field_includes(f, a[f], b[f]) for f in self.queue_fields)
            if dead or included:
                skipped_dead += 1
            else:
                queue_relevant.append(idx)

        self.df = df
        self.queue_all = queue_all
        self.queue_relevant = queue_relevant
        self.queue = queue_all if SHOW_ALL else queue_relevant
        self.agreed = agreed
        self.skipped_dead = skipped_dead
        mode = "ALL" if SHOW_ALL else "decision-relevant"
        print(
            f"[{self.slug}] loaded {src}: {len(df)} rows | {agreed} auto-agreed | "
            f"{len(queue_all)} total disagreements | "
            f"{len(queue_relevant)} decision-relevant "
            f"({skipped_dead} skipped: already excluded by an agreed criterion) | "
            f"queue mode = {mode}",
            flush=True,
        )
        if agreed:
            # Persist the agreement pass so progress survives a restart.
            self._save_df()

    # --- persistence -------------------------------------------------------

    def _save_df(self) -> None:
        os.makedirs(self.cfg.review_dir, exist_ok=True)
        self.df.to_csv(self.out_path, index=False)

    def save_decision(self, idx: int, decisions: dict) -> None:
        with _lock:
            for f in CONSENSUS_FIELDS:
                if f in decisions:
                    val = decisions[f]
                    self.df.at[idx, f"Final_{f}"] = val
                    self.df.at[idx, f"Human_{f}"] = val
            self.df.at[idx, ADJUDICATED_COL] = HUMAN
            self._save_df()

    # --- view models -------------------------------------------------------

    def progress(self) -> dict:
        resolved = int(
            (self.df[ADJUDICATED_COL].astype(str).str.lower() == HUMAN).sum()
        )
        remaining = [i for i in self.queue if self._nz(self.df.at[i, ADJUDICATED_COL]) != HUMAN]
        return {
            "slug": self.slug,
            "a_label": self.a_label,
            "b_label": self.b_label,
            "mode": "all" if SHOW_ALL else "decision-relevant",
            "total_disagreements": len(self.queue),
            "total_all": len(getattr(self, "queue_all", self.queue)),
            "total_relevant": len(getattr(self, "queue_relevant", self.queue)),
            "skipped_dead": getattr(self, "skipped_dead", 0),
            "resolved": resolved,
            "remaining": len(remaining),
            "agreed": getattr(self, "agreed", 0),
            "queue": [int(i) for i in self.queue],
            "remaining_idxs": [int(i) for i in remaining],
            "fields": self.queue_fields,
            "allowed": {f: ALLOWED[f] for f in self.queue_fields},
        }

    def paper(self, idx: int) -> dict:
        row = self.df.loc[idx]
        fields = []
        for f in self.queue_fields:
            a = str(row.get(f"{self.a_pref}_{f}", "")).strip()
            b = str(row.get(f"{self.b_pref}_{f}", "")).strip()
            cur = str(row.get(f"Final_{f}", "")).strip() or str(row.get(f"Human_{f}", "")).strip()
            # Pre-select fields the raters already agree on, so the human only has
            # to resolve the actual disagreement(s) (and isn't blocked by "pick a
            # value for every field" on the agreed ones).
            if not cur and a and a.lower() == b.lower():
                cur = a
            fields.append({
                "name": f,
                "a": a,
                "b": b,
                "agree": a.lower() == b.lower(),
                "allowed": ALLOWED[f],
                "current": cur,
            })
        # Show rater reasoning if present (helps the human decide).
        a_reason = str(row.get(f"{self.a_pref}_reasoning", "")).strip()
        b_reason = str(row.get(f"{self.b_pref}_reasoning", "")).strip()
        return {
            "idx": int(idx),
            "title": str(row.get(COL_TITLE, "")),
            "abstract": str(row.get(COL_ABSTRACT, "")),
            "doi": str(row.get("DOI", "")),
            "journal": str(row.get("Journal", "")),
            "year": str(row.get("Year", "")),
            "a_reason": a_reason,
            "b_reason": b_reason,
            "resolved": self._nz(row.get(ADJUDICATED_COL, "")) == HUMAN,
            "fields": fields,
        }


STATE: State | None = None


# --- HTTP handler ---------------------------------------------------------

INDEX_HTML = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Adjudication — {slug}</title>
<style>
  :root { --bg:#0f1216; --card:#181d24; --line:#2a323d; --fg:#e6edf3; --mut:#9aa7b4;
          --a:#3b82f6; --b:#a855f7; --ok:#22c55e; --warn:#f59e0b; --pick:#1f6feb; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--fg); font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
  header { position:sticky; top:0; background:var(--card); border-bottom:1px solid var(--line);
           padding:10px 18px; display:flex; align-items:center; gap:16px; z-index:5; }
  header h1 { font-size:15px; margin:0; font-weight:600; }
  .bar { flex:1; height:8px; background:#0c0f13; border-radius:6px; overflow:hidden; }
  .bar > div { height:100%; background:var(--ok); width:0%; transition:width .25s; }
  .prog { color:var(--mut); font-variant-numeric:tabular-nums; white-space:nowrap; }
  main { max-width:1080px; margin:0 auto; padding:18px; }
  .meta { color:var(--mut); font-size:13px; margin-bottom:6px; }
  .title { font-size:19px; font-weight:650; margin:2px 0 10px; }
  .abstract { background:var(--card); border:1px solid var(--line); border-radius:10px;
              padding:14px 16px; max-height:320px; overflow:auto; white-space:pre-wrap; color:#cdd6df; }
  table { width:100%; border-collapse:collapse; margin-top:18px; }
  th,td { text-align:left; padding:10px 12px; border-bottom:1px solid var(--line); vertical-align:top; }
  th { color:var(--mut); font-weight:600; font-size:12px; text-transform:uppercase; letter-spacing:.04em; }
  tr.disagree { background:rgba(245,158,11,.13); box-shadow:inset 4px 0 0 var(--warn); }
  tr.disagree .fname { color:var(--warn); }
  tr.agree td { opacity:.5; }
  tr.agree:hover td { opacity:.85; }
  .badge { display:inline-block; margin-left:8px; padding:1px 7px; border-radius:999px;
           background:var(--warn); color:#211a00; font-size:10px; font-weight:800;
           letter-spacing:.05em; vertical-align:middle; }
  .fname { font-weight:600; }
  .rval { display:inline-block; padding:2px 8px; border-radius:6px; font-size:13px; }
  .rval.diff { outline:2px solid var(--warn); outline-offset:1px; }
  .rA { background:rgba(59,130,246,.16); color:#bcd4ff; }
  .rB { background:rgba(168,85,247,.16); color:#e4ccff; }
  .opts { display:flex; flex-wrap:wrap; gap:6px; }
  .opt { padding:4px 10px; border:1px solid var(--line); border-radius:999px; cursor:pointer;
         background:#10151b; color:var(--fg); font-size:13px; user-select:none; }
  .opt:hover { border-color:var(--a); }
  .opt.sel { background:var(--pick); border-color:var(--pick); color:#fff; font-weight:600; }
  .opt .k { opacity:.55; font-size:11px; margin-right:3px; }
  .reason { color:var(--mut); font-size:12.5px; margin-top:4px; font-style:italic; }
  footer { position:sticky; bottom:0; background:var(--card); border-top:1px solid var(--line);
           padding:12px 18px; display:flex; gap:10px; align-items:center; }
  button { background:var(--ok); color:#06210f; border:0; border-radius:8px; padding:9px 16px;
           font-weight:650; cursor:pointer; font-size:14px; }
  button.sec { background:#222a33; color:var(--fg); }
  button:disabled { opacity:.4; cursor:not-allowed; }
  .hint { color:var(--mut); font-size:12px; }
  .done { text-align:center; padding:60px 20px; color:var(--mut); }
  kbd { background:#0c0f13; border:1px solid var(--line); border-radius:4px; padding:1px 6px; font-size:11px; }
  a { color:#8ab4ff; }
</style></head>
<body>
<header>
  <h1>Adjudication · {slug}</h1>
  <div class="bar"><div id="barfill"></div></div>
  <div class="prog" id="prog">…</div>
</header>
<main id="main"><div class="done">Loading…</div></main>
<footer>
  <button class="sec" id="prev">‹ Prev <kbd>[</kbd></button>
  <button class="sec" id="next">Next › <kbd>]</kbd></button>
  <div style="flex:1"></div>
  <span class="hint" id="fieldhint"></span>
  <button id="save">Save &amp; Next <kbd>↵</kbd></button>
</footer>
<script>
let META=null, ORDER=[], pos=0, paper=null, focusField=0;

async function boot(){
  META = await (await fetch('/api/meta')).json();
  ORDER = META.remaining_idxs.length ? META.remaining_idxs : META.queue;
  if(!ORDER.length){ renderDone(); updateProg(); return; }
  pos = 0; await load(); updateProg();
}
function updateProg(){
  // "remaining" = what's left in this session's working list; "resolved" = rows
  // you've adjudicated (cumulative). Total = resolved + remaining (the queue
  // shrinks as re-classification auto-excludes rows, so use a live denominator).
  const remaining = ORDER.length;
  const total = META.resolved + remaining;
  const pct = total ? Math.round(100*META.resolved/total) : 100;
  document.getElementById('barfill').style.width = pct+'%';
  document.getElementById('prog').textContent =
    `${remaining} left · ${META.resolved} done · ${META.agreed} auto-agreed`;
}
async function load(){
  const idx = ORDER[pos];
  paper = await (await fetch('/api/paper?idx='+idx)).json();
  focusField = paper.fields.findIndex(f=>!f.agree); if(focusField<0) focusField=0;
  render();
}
function render(){
  if(!paper){ renderDone(); return; }
  const f = paper.fields.map((fd,i)=>{
    const opts = fd.allowed.map((v,j)=>{
      const sel = (fd.current||'').toLowerCase()===v.toLowerCase() ? ' sel':'';
      return `<span class="opt${sel}" data-field="${i}" data-val="${v}"><span class="k">${j+1}</span>${v}</span>`;
    }).join('');
    const aMatch = fd.a.toLowerCase()===(fd.current||'').toLowerCase();
    const bMatch = fd.b.toLowerCase()===(fd.current||'').toLowerCase();
    const diff = fd.agree?'':' diff';
    return `<tr class="${fd.agree?'agree':'disagree'}" data-row="${i}">
      <td class="fname">${fd.name}${fd.agree?'':'<span class="badge">DISAGREEMENT</span>'}</td>
      <td><span class="rval rA${diff}">${fd.a||'—'}</span><div class="hint">${META.a_label}</div></td>
      <td><span class="rval rB${diff}">${fd.b||'—'}</span><div class="hint">${META.b_label}</div></td>
      <td><div class="opts">${opts}</div></td>
    </tr>`;
  }).join('');
  const reasons = (paper.a_reason||paper.b_reason) ? `
     <tr><td></td>
       <td colspan="1"><div class="reason">${esc(paper.a_reason)}</div></td>
       <td colspan="2"><div class="reason">${esc(paper.b_reason)}</div></td></tr>`:'';
  const doi = paper.doi ? ` · <a href="https://doi.org/${paper.doi}" target="_blank">${paper.doi}</a>`:'';
  document.getElementById('main').innerHTML = `
    <div class="meta">${esc(paper.journal)} ${paper.year?('· '+paper.year):''}${doi} · row ${paper.idx} · ${pos+1}/${ORDER.length}</div>
    <div class="title">${esc(paper.title)}</div>
    <div class="abstract">${esc(paper.abstract)||'<i>no abstract</i>'}</div>
    <table><thead><tr><th>Field</th><th>Rater A</th><th>Rater B</th><th>Your decision</th></tr></thead>
    <tbody>${f}${reasons}</tbody></table>`;
  document.querySelectorAll('.opt').forEach(el=>{
    el.onclick=()=>{ pick(+el.dataset.field, el.dataset.val); };
  });
  highlightFocus();
}
function esc(s){ return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }
function pick(fi,val){ paper.fields[fi].current = val; render(); focusField=fi; highlightFocus(); }
function highlightFocus(){
  document.querySelectorAll('tr[data-row]').forEach(tr=>tr.style.outline='');
  const tr=document.querySelector(`tr[data-row="${focusField}"]`);
  if(tr) tr.style.outline='2px solid var(--a)';
  const fd=paper && paper.fields[focusField];
  document.getElementById('fieldhint').textContent = fd ? `focused: ${fd.name} — press a/b or 1-${fd.allowed.length}` : '';
}
function allResolved(){ return paper.fields.every(fd=>fd.current && fd.current.length); }
async function save(){
  if(!paper) return;
  if(!allResolved()){ alert('Pick a value for every field first.'); return; }
  const decisions={}; paper.fields.forEach(fd=>decisions[fd.name]=fd.current);
  await fetch('/api/save',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({idx:paper.idx, decisions})});
  META.resolved++;
  ORDER.splice(pos,1);
  updateProg();
  if(pos>=ORDER.length) pos=ORDER.length-1;
  if(!ORDER.length){ paper=null; renderDone(); return; }
  await load();
  window.scrollTo({top:0, behavior:'smooth'});
}
function renderDone(){
  document.getElementById('main').innerHTML =
    `<div class="done"><h2>✓ All disagreements adjudicated</h2>
     <p>${META.resolved} resolved by you · ${META.agreed} auto-agreed by the two raters.</p>
     <p>Final labels written to <code>${META.slug}</code> adjudicated.csv.</p></div>`;
  document.getElementById('fieldhint').textContent='';
}
document.getElementById('save').onclick=save;
document.getElementById('prev').onclick=async()=>{ if(pos>0){pos--; await load();} };
document.getElementById('next').onclick=async()=>{ if(pos<ORDER.length-1){pos++; await load();} };
document.addEventListener('keydown',e=>{
  if(!paper) return;
  if(e.key==='Enter'){ e.preventDefault(); save(); }
  else if(e.key===']'){ if(pos<ORDER.length-1){pos++; load();} }
  else if(e.key==='['){ if(pos>0){pos--; load();} }
  else if(e.key==='Tab'){ e.preventDefault(); focusField=(focusField+1)%paper.fields.length; highlightFocus(); }
  else if(e.key==='a'||e.key==='A'){ pick(focusField, paper.fields[focusField].a); }
  else if(e.key==='b'||e.key==='B'){ pick(focusField, paper.fields[focusField].b); }
  else if(/^[1-9]$/.test(e.key)){ const fd=paper.fields[focusField]; const v=fd.allowed[+e.key-1]; if(v) pick(focusField, v); }
});
boot();
</script>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # quiet
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj).encode("utf-8"), "application/json")

    def do_GET(self):
        assert STATE is not None
        parsed = urlparse(self.path)
        if parsed.path == "/":
            html = INDEX_HTML.replace("{slug}", STATE.slug)
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
        elif parsed.path == "/api/meta":
            self._json(STATE.progress())
        elif parsed.path == "/api/paper":
            qs = parse_qs(parsed.query)
            idx = int(qs.get("idx", ["-1"])[0])
            try:
                self._json(STATE.paper(idx))
            except KeyError:
                self._json({"error": f"no row {idx}"}, 404)
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):
        assert STATE is not None
        if urlparse(self.path).path != "/api/save":
            self._send(404, b"not found", "text/plain")
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        idx = int(payload.get("idx", -1))
        decisions = payload.get("decisions", {})
        try:
            STATE.save_decision(idx, decisions)
            self._json({"ok": True})
        except Exception as e:  # noqa: BLE001
            self._json({"ok": False, "error": str(e)}, 500)


def main() -> int:
    global STATE
    slug = sys.argv[1] if len(sys.argv) > 1 else "adults"
    STATE = State(slug)
    if not STATE.queue:
        print("Nothing to adjudicate — all rows agree or are already resolved.")
        print(f"(Final labels are in {STATE.out_path})")
        # Still serve, so the user sees the 'done' screen.
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"\n  Adjudication UI for '{slug}' → http://localhost:{PORT}")
    print(f"  {len(STATE.queue)} disagreements to resolve. Ctrl-C to stop.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
