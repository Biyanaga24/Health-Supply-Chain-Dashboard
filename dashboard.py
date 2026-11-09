import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from datetime import timedelta
from datetime import date
from datetime import timezone
import sys
import os
import time
import requests
import re
from io import BytesIO
from supabase import create_client
from openpyxl.utils import get_column_letter
# Add the current directory to path
sys.path.append(os.path.dirname(__file__))

# Import authentication functions
from auth import show_login_page, show_profile_page, show_admin_panel


# ---------------------------------------------------
# Parent-page JS helpers (tab switching, clickable cards)
# ---------------------------------------------------
def _inject_parent_js(code):
    """Run JS against the main Streamlit page.
    1) inject a <script> into the parent page (survives reruns);
    2) if the page refused it (security policy), run the same code from the 0-height frame instead."""
    import json as _json, uuid as _uuid
    flag = "__inj_" + _uuid.uuid4().hex[:10]
    payload = _json.dumps("window['" + flag + "']=1;" + code)
    st.components.v1.html(
        "<script>(function(){var P=window.parent, D=P.document, C=" + payload + ";"
        "try{var s=D.createElement('script');s.textContent=C;D.head.appendChild(s);"
        "setTimeout(function(){try{s.remove();}catch(e){}},100);}catch(e){}"
        "if(!P['" + flag + "']){try{(new Function('window','document',C))(P,D);}catch(e){}}"
        "})();</script>",
        height=0
    )

LAZY_TABS = True   # set to False to build every tab on every run (the old behaviour)


def _tabs_for(page_name):
    """st.tabs for a page. On Streamlit >= 1.55 the tabs report which one is open (on_change='rerun'),
    so only the open tab's content is built instead of every tab on every interaction."""
    labels = NAV_TREE[page_name]
    try:
        import inspect
        if LAZY_TABS and 'on_change' in inspect.signature(st.tabs).parameters:
            return st.tabs(labels, key=f"main_tabs_{page_name}", on_change="rerun")
    except Exception:
        pass
    return st.tabs(labels)


def _tab_open(tab):
    """True when this tab should be built (always True on Streamlit versions without lazy tabs)."""
    try:
        v = getattr(tab, "open", True)
        return True if v is None else bool(v)
    except Exception:
        return True


_TAB_JS = """
(function(){
  var TOKEN = __TOKEN__, IDX = __IDX__, NEED = __NEED__, CLOSE = __CLOSE__, LABEL = __LABEL__;
  if (window.__navDone === TOKEN) { return; }
  if (window.__navTimer) { clearInterval(window.__navTimer); }
  var tries = 0, clicks = 0, lastClick = 0;
  function norm(t){ return (t || '').replace(/\\s+/g, ' ').trim(); }
  function allTabs(){
    return Array.prototype.slice.call(document.querySelectorAll('button[role="tab"], button[data-baseweb="tab"], [data-testid="stTab"]'));
  }
  function findTab(){
    var tabs = allTabs();
    for (var i = 0; i < tabs.length; i++) { if (norm(tabs[i].innerText) === LABEL) { return tabs[i]; } }
    return (tabs.length >= NEED) ? tabs[IDX] : null;
  }
  function isSel(t){ return t.getAttribute('aria-selected') === 'true'; }
  function press(t){
    ['pointerdown','mousedown','pointerup','mouseup','click'].forEach(function(type){
      t.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true, view: window}));
    });
  }
  function finish(){
    clearInterval(window.__navTimer); window.__navDone = TOKEN;
    if (CLOSE && window.innerWidth <= 768) {
      var b = document.querySelector('[data-testid="stSidebarCollapseButton"] button')
           || document.querySelector('[data-testid="stSidebarHeader"] button');
      if (b) { b.click(); }
    }
  }
  window.__navTimer = setInterval(function(){
    tries++;
    var now = Date.now(), t = findTab();
    if (t) {
      if (isSel(t)) { finish(); window.scrollTo({top: 0, behavior: 'smooth'}); return; }
      // Each click makes Streamlit rerun the app. Click at most twice, and wait for the rerun to settle
      // between clicks, so a slow rerun can never turn into a click/rerun loop.
      if (clicks < 2 && now - lastClick > 4000) {
        t.scrollIntoView({block: 'nearest', inline: 'center'});
        press(t); clicks++; lastClick = now;
      } else if (clicks >= 2 && now - lastClick > 6000) { finish(); return; }
    }
    if (tries > 300) { finish(); }   // ~45 s safety stop
  }, 150);
})();
"""

_SCROLL_JS = """
(function(){
  var TOKEN = __TOKEN__, IDX = __IDX__, CLOSE = __CLOSE__;
  if (window.__navDone === TOKEN) { return; }
  var tries = 0;
  var timer = setInterval(function(){
    tries++;
    var hs = document.querySelectorAll('[data-testid="stMain"] h2, section.main h2');
    if (hs.length > IDX) {
      clearInterval(timer);
      window.__navDone = TOKEN;
      hs[IDX].scrollIntoView({behavior: 'smooth', block: 'start'});
      if (CLOSE && window.innerWidth <= 768) {
        var b = document.querySelector('[data-testid="stSidebarCollapseButton"] button')
             || document.querySelector('[data-testid="stSidebarHeader"] button');
        if (b) { b.click(); }
      }
    } else if (tries > 200) { clearInterval(timer); }
  }, 100);
})();
"""

def _apply_nav_target(page_name, n_items, mode="tabs"):
    """Idempotent: re-injected on every run, but acts only once per sidebar click (token)."""
    tgt = st.session_state.get('nav_target')
    if not tgt or tgt.get('page') != page_name:
        return
    tpl = _TAB_JS if mode == "tabs" else _SCROLL_JS
    code = (tpl.replace("__TOKEN__", str(tgt['token']))
               .replace("__IDX__", str(int(tgt['idx'])))
               .replace("__NEED__", str(int(n_items)))
               .replace("__LABEL__", __import__("json").dumps(NAV_TREE[page_name][int(tgt['idx'])] if mode == "tabs" else ""))
               .replace("__CLOSE__", "true"))
    _inject_parent_js(code)

_CARD_JS = """
(function(){
  var LABELS = __LABELS__;
  function hideBtns(){
    document.querySelectorAll('button').forEach(function(b){
      var t = (b.innerText || '').trim();
      if (t.indexOf('Show ') === 0 && LABELS.indexOf(t.slice(5)) !== -1) {
        var c = b.closest('[data-testid="stElementContainer"]') || b.closest('.element-container') || b.parentElement;
        if (c && c.style.display !== 'none') { c.style.display = 'none'; }
      }
    });
  }
  hideBtns();
  if (window.__cardWired) { return; }
  window.__cardWired = true;
  setInterval(hideBtns, 400);
  document.addEventListener('click', function(e){
    var card = e.target.closest && e.target.closest('div[style*="cursor: pointer"]');
    if (!card) { return; }
    var p = card.querySelector('p');
    if (!p) { return; }
    var label = (p.innerText || '').trim();
    if (LABELS.indexOf(label) === -1) { return; }
    var btns = document.querySelectorAll('button');
    for (var i = 0; i < btns.length; i++) {
      if ((btns[i].innerText || '').trim() === 'Show ' + label) { btns[i].click(); break; }
    }
  }, true);
})();
"""

# ---------------------------------------------------
# Advanced HTML table (sortable, searchable, sticky header, badges, expiry chips)
# ---------------------------------------------------
_ADV_STATUS_COLORS = {
    "Stock Out": ("#c0392b", "#ffffff"), "Understock": ("#f1c40f", "#4a3b00"),
    "Normal Stock": ("#27ae60", "#ffffff"), "Overstock": ("#5dade2", "#08304a"),
}
_ADV_RISK_COLORS = {
    "Critical Risk": ("#8e44ad", "#ffffff"), "Risk of Stock out": ("#e67e22", "#ffffff"),
    "Expiry Risk": ("#e67e22", "#ffffff"),
}
_EXPIRY_RE = re.compile(r"[\d,\.]+\s*\([A-Za-z]{3,9}[-\s]\d{2,4}\)")


def _adv_table_html(df, height=620, search=True, wrap_cols=("Status",)):
    """Self-contained HTML table: click a header to sort, type to filter, sticky header + first column,
    status badges, expiry batches as chips, long text wrapped. Returns an HTML string."""
    import html as _h
    cols = [str(c) for c in df.columns]
    head = "".join(f"<th data-i='{i}' title='Click to sort'>{_h.escape(c)}<span class='ar'></span></th>" for i, c in enumerate(cols))
    rows = []
    for rec in df.itertuples(index=False, name=None):
        tds = []
        status = ""
        for c, v in zip(cols, rec):
            if c == "Stock Status":
                status = "" if v is None else str(v)
        for i, (c, v) in enumerate(zip(cols, rec)):
            try:
                empty = v is None or (not isinstance(v, str) and pd.isna(v))
            except Exception:
                empty = False
            txt = "" if empty else str(v)
            esc = _h.escape(txt)
            sortv = esc
            if c == "Material Description":
                bg = _ADV_STATUS_COLORS.get(status, ("#cfd8e3", ""))[0]
                cell = f"<td class='md' style='border-left:5px solid {bg}' data-s='{esc}'>{esc}</td>"
            elif c == "Stock Status" and txt:
                b, f = _ADV_STATUS_COLORS.get(txt, ("#95a5a6", "#fff"))
                cell = f"<td data-s='{esc}'><span class='bd' style='background:{b};color:{f}'>{esc}</span></td>"
            elif c == "Risk Type" and txt:
                b, f = _ADV_RISK_COLORS.get(txt, ("#95a5a6", "#fff"))
                cell = f"<td data-s='{esc}'><span class='bd' style='background:{b};color:{f}'>{esc}</span></td>"
            elif c == "Expiry":
                chips = _EXPIRY_RE.findall(txt) if txt else []
                if chips:
                    body = "".join(f"<span class='chip'>{_h.escape(x.strip())}</span>" for x in chips)
                elif txt:
                    body = "".join(f"<span class='chip'>{_h.escape(x.strip())}</span>" for x in txt.split(",") if x.strip())
                else:
                    body = ""
                cell = f"<td class='exp' data-s='{esc}'><div class='chips'>{body}</div></td>"
            elif c in wrap_cols:
                cell = f"<td class='wr' data-s='{esc}' title='{esc}'><div class='clamp'>{esc}</div></td>"
            elif c == "DOS":
                try:
                    pos = float(txt) > 0
                except Exception:
                    pos = False
                cell = (f"<td class='num' data-s='{esc}'>" + (f"<span class='bd' style='background:#e74c3c;color:#fff'>{esc}</span>" if pos else esc) + "</td>")
            else:
                t = txt.replace(",", "").replace("%", "").replace("-", "", 1) if txt else ""
                isnum = bool(t) and t.replace(".", "", 1).isdigit()
                neg = txt.startswith("-") and isnum
                cls = "num" if isnum else ""
                if neg:
                    cls += " neg"
                cell = f"<td class='{cls.strip()}' data-s='{esc}'>{esc}</td>"
            tds.append(cell)
        rows.append("<tr>" + "".join(tds) + "</tr>")
    box = "<input id='q' type='search' placeholder='🔍 Filter rows…'>" if search else ""
    return f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<style>
*{{box-sizing:border-box}} body{{margin:0;font-family:'Segoe UI',Roboto,Arial,sans-serif;font-size:13px;color:#1f2a38;background:transparent}}
#bar{{display:flex;gap:10px;align-items:center;margin:0 0 8px}} #q{{flex:1;padding:7px 12px;border:1px solid #c9d6e2;border-radius:20px;font-size:13px;outline:none}}
#q:focus{{border-color:#2e86c1;box-shadow:0 0 0 2px rgba(46,134,193,.2)}} #cnt{{color:#5b6b7b;font-size:12px;white-space:nowrap}}
#w{{height:{int(height)-46}px;overflow:auto;border:1px solid #d5dee8;border-radius:10px;background:#fff;box-shadow:0 2px 8px rgba(26,82,118,.08)}}
table{{border-collapse:separate;border-spacing:0;width:100%;min-width:max-content}}
th{{position:sticky;top:0;z-index:3;background:linear-gradient(#1f5f8b,#1a5276);color:#fff;text-align:left;padding:10px 12px;font-weight:600;cursor:pointer;white-space:nowrap;user-select:none;border-right:1px solid rgba(255,255,255,.12)}}
th:hover{{background:#2e86c1}} th .ar{{margin-left:6px;font-size:10px;opacity:.9}}
td{{padding:8px 12px;border-bottom:1px solid #edf1f5;vertical-align:top;background:#fff}}
tr:nth-child(even) td{{background:#f6f9fc}} tr:hover td{{background:#e8f3fb !important}}
td.md{{position:sticky;left:0;z-index:2;min-width:240px;max-width:340px;font-weight:600;color:#1a3a55;white-space:normal;box-shadow:2px 0 4px rgba(0,0,0,.05)}}
th:first-child{{position:sticky;left:0;z-index:4}}
td.num{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}} td.neg{{color:#c0392b;font-weight:600}}
td.exp{{min-width:230px;max-width:380px}} .chips{{display:flex;flex-wrap:wrap;gap:4px}}
.chip{{background:#fdf2e3;color:#8a4b08;border:1px solid #f5cf9c;border-radius:12px;padding:2px 9px;font-size:12px;white-space:nowrap}}
td.wr{{min-width:200px;max-width:340px}} .clamp{{display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;line-height:1.35}}
td.wr:hover .clamp{{-webkit-line-clamp:unset}}
.bd{{display:inline-block;padding:2px 10px;border-radius:12px;font-weight:600;font-size:12px;white-space:nowrap}}
@media (max-width:640px){{body{{font-size:12px}} td,th{{padding:7px 8px}} td.md{{min-width:150px;max-width:190px}}}}
</style></head><body>
<div id='bar'>{box}<span id='cnt'></span></div>
<div id='w'><table id='t'><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<script>
(function(){{
 var t=document.getElementById('t'),tb=t.tBodies[0],q=document.getElementById('q'),cnt=document.getElementById('cnt');
 var rows=Array.prototype.slice.call(tb.rows),dir={{}};
 function upd(){{var n=0;rows.forEach(function(r){{if(r.style.display!=='none')n++;}});cnt.textContent=n+' of '+rows.length+' rows';}}
 function num(s){{var x=parseFloat(String(s).replace(/[,%]/g,''));return isNaN(x)?null:x;}}
 t.tHead.addEventListener('click',function(e){{
  var th=e.target.closest('th');if(!th)return;var i=+th.dataset.i;dir[i]=dir[i]===1?-1:1;
  Array.prototype.forEach.call(t.tHead.rows[0].cells,function(c){{c.querySelector('.ar').textContent='';}});
  th.querySelector('.ar').textContent=dir[i]===1?'▲':'▼';
  rows.sort(function(a,b){{var x=a.cells[i].dataset.s,y=b.cells[i].dataset.s,nx=num(x),ny=num(y);
   if(nx!==null&&ny!==null)return (nx-ny)*dir[i];
   if(x===''&&y!=='')return 1; if(y===''&&x!=='')return -1;
   return x.localeCompare(y,undefined,{{numeric:true}})*dir[i];}});
  rows.forEach(function(r){{tb.appendChild(r);}});
 }});
 if(q)q.addEventListener('input',function(){{var v=q.value.toLowerCase();
  rows.forEach(function(r){{r.style.display=r.textContent.toLowerCase().indexOf(v)===-1?'none':'';}});upd();}});
 upd();
}})();
</script></body></html>"""


def render_adv_table(df, key=None, max_height=640, wrap_cols=("Status",)):
    """Show the advanced table in the page (height adapts to the number of rows)."""
    n = len(df)
    h = int(min(max_height, 130 + n * 46))
    st.components.v1.html(_adv_table_html(df, height=h, wrap_cols=wrap_cols), height=h + 6, scrolling=False)


# ---------------------------------------------------
# Floating assistant (reasoning over the dashboard's own data; optional Claude API if a key is in secrets)
# ---------------------------------------------------
_BOT_STOP = set("""the and for with what which how many much are is was were show list give tell me about of in on at to a an
all any this that these those please can you could would should stock status item items material materials medicine medicines
product products have has had there their from by do does need needs now current currently dashboard data info information
level levels month months qty quantity amount number total count""".split())


def _bf(x, d=0):
    try:
        if x is None or pd.isna(x):
            return "n/a"
        return f"{float(x):,.{d}f}"
    except Exception:
        return str(x)


def _bot_find_material(q, d):
    names = d['Material Description'].astype(str)
    low = names.str.lower()
    ql = q.lower()
    full = low[low.apply(lambda n: len(n) > 4 and n in ql)]
    if len(full):
        return d.loc[full.index[:1]]
    toks = [t for t in re.findall(r"[a-z0-9\-\+]{3,}", ql) if t not in _BOT_STOP]
    if not toks:
        return None
    score = low.apply(lambda n: sum(1 for t in toks if t in n))
    top = score.max()
    if top <= 0:
        return None
    hit = d.loc[score[score == top].index]
    if top == 1 and len(hit) > 6:
        return None
    return hit.head(6)


def _bot_material_profile(r):
    nm = float(r.get('NMOS')) if pd.notna(r.get('NMOS')) else None
    tm = float(r.get('TMOS')) if pd.notna(r.get('TMOS')) else None
    lines = [f"**{r['Material Description']}**",
             f"- Status: **{r.get('Stock Status', 'n/a')}** · NMOS {_bf(nm, 2)} · TMOS {_bf(tm, 2)} · AMC {_bf(r.get('AMC'))}",
             f"- Head Office {_bf(r.get('Head Office'))} · Hubs {_bf(r.get('Hubs'))} · NSOH {_bf(r.get('NSOH'))}"]
    if pd.notna(r.get('GF_MOS')):
        lines.append(f"- Gap to 18 months: **{_bf(r.get('GF_MOS'), 2)} MOS ≈ {_bf(r.get('GF_Qty'))} units**")
    if str(r.get('Expiry', '')).strip():
        lines.append(f"- Expiry batches: {r.get('Expiry')}")
    if str(r.get('Risk Type', '')).strip():
        lines.append(f"- Risk: **{r.get('Risk Type')}**")
    why = []
    st_ = r.get('Stock Status')
    if st_ == "Stock Out":
        why.append("NMOS < 1, so there is effectively no national stock." +
                   (" The pipeline (GIT/LC/WB/TMD) brings TMOS to " + _bf(tm, 1) + ", so " + ("follow up the inbound shipments urgently." if (tm or 0) >= 1 else "nothing meaningful is coming — place or expedite an order.") if tm is not None else ""))
    elif st_ == "Understock":
        why.append("Stock is below the minimum level; " + ("inbound pipeline lifts TMOS to " + _bf(tm, 1) + " — monitor arrival." if tm and nm is not None and tm > nm + 1 else "no sufficient pipeline — plan a replenishment."))
    elif st_ == "Overstock":
        why.append("Stock is above the maximum level — pause new orders and consider redistribution to avoid expiry.")
    elif st_ == "Normal Stock":
        why.append("Stock is within the target range.")
    if str(r.get('Risk Type', '')) in ("Expiry Risk", "Critical Risk"):
        why.append("Expiring batches may not be consumed at the current AMC — prioritise redistribution of the near-expiry batches.")
    if why:
        lines.append("\n**Reasoning:** " + " ".join(why))
    return "\n".join(lines)


def _bot_table(d, cols, n=10):
    cols = [c for c in cols if c in d.columns]
    t = d[cols].head(n).copy()
    for c in t.columns:
        if c != 'Material Description' and pd.api.types.is_numeric_dtype(t[c]):
            t[c] = t[c].apply(lambda v: _bf(v, 2 if c in ('NMOS', 'TMOS', 'GF_MOS') else 0))
    head = "| " + " | ".join(t.columns) + " |\n|" + "|".join(["---"] * len(t.columns)) + "|"
    body = "\n".join("| " + " | ".join(str(v).replace("|", "/") for v in r) + " |" for r in t.itertuples(index=False, name=None))
    return head + "\n" + body


def _bot_context(d):
    n = len(d)
    vc = d['Stock Status'].value_counts().to_dict() if 'Stock Status' in d.columns else {}
    rk = d['Risk Type'].fillna('').value_counts().to_dict() if 'Risk Type' in d.columns else {}
    return (f"Rows: {n}. Status counts: {vc}. Risk counts: {rk}. Avg procurement lead: {st.session_state.get('kpi_avg_proc_lead')} days.")


def _bot_llm(q, d, history):
    """Optional: Claude answers using a compact data digest. Only used when ANTHROPIC_API_KEY is in st.secrets."""
    try:
        key = st.secrets.get("ANTHROPIC_API_KEY")
    except Exception:
        key = None
    if not key:
        return None
    try:
        import requests
        cols = [c for c in ['Material Description', 'Head Office', 'Hubs', 'NSOH', 'AMC', 'NMOS', 'TMOS', 'GF_MOS', 'GF_Qty', 'Stock Status', 'Risk Type', 'Expiry'] if c in d.columns]
        digest = d[cols].head(150).to_csv(index=False)
        sysmsg = ("You are the assistant of the EPSS HPC Stock Management Dashboard. Answer only from the data given. "
                  "Think step by step internally, then give a short, precise answer with the key numbers and a recommendation. "
                  "Stock levels: <1 NMOS Stock Out; <6 Understock; 6-18 Normal; >18 Overstock (vaccines: <4, 4-10, >10). "
                  "GF_MOS = 18 - TMOS; GF_Qty = GF_MOS x AMC.\n" + _bot_context(d) + "\nData (first 150 rows, CSV):\n" + digest)
        msgs = [{"role": m["role"], "content": m["content"]} for m in history[-6:]] + [{"role": "user", "content": q}]
        r = requests.post("https://api.anthropic.com/v1/messages",
                          headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                          json={"model": "claude-sonnet-5-5", "max_tokens": 900, "system": sysmsg, "messages": msgs}, timeout=40)
        if r.status_code == 200:
            return "".join(b.get("text", "") for b in r.json().get("content", []))
    except Exception:
        return None
    return None


def _bot_answer(q, d, history=()):
    ql = q.lower().strip()
    if d is None or d.empty:
        return "There is no data for the current filters. Change the Program / Material filters in the sidebar and ask again."
    if re.fullmatch(r"(hi|hello|hey|good (morning|afternoon|evening)|help|\?)[!. ]*", ql):
        return ("Hello! I answer from the data currently filtered on the dashboard. Try:\n"
                "- *How many stock out items are there?*\n- *Which materials are at risk of expiry?*\n"
                "- *Show details of Artesunate*\n- *Top 10 materials by GF_Qty*\n- *Give me a summary* / *What should I prioritise?*")
    out = []
    n = len(d)
    status = d['Stock Status'] if 'Stock Status' in d.columns else pd.Series([''] * n, index=d.index)
    risk = d['Risk Type'].fillna('') if 'Risk Type' in d.columns else pd.Series([''] * n, index=d.index)
    sdef = [("stock out", "Stock Out"), ("stockout", "Stock Out"), ("understock", "Understock"), ("under stock", "Understock"),
            ("overstock", "Overstock"), ("over stock", "Overstock"), ("normal", "Normal Stock")]
    want_list = any(w in ql for w in ("list", "which", "show", "name", "what are", "who"))
    want_count = any(w in ql for w in ("how many", "count", "number of", "total"))

    # 1) lead time
    if "lead" in ql and ("time" in ql or "procure" in ql):
        v = st.session_state.get('kpi_avg_proc_lead')
        return (f"The average procurement lead time is **{v} days** (same figure as 📦 Avg Procurement Lead in the Procurement Lead Time tab)." if v is not None
                else "No procurement lead time records are available yet.")

    # 2) summary / priorities
    if any(w in ql for w in ("summary", "overview", "summarise", "summarize", "status of", "how are we", "overall")):
        vc = status.value_counts()
        avail = (pd.to_numeric(d.get('NMOS'), errors='coerce') > 1).mean() * 100 if 'NMOS' in d.columns else float('nan')
        out.append(f"**Overview ({n} materials in the current filter)**")
        for s_ in ("Stock Out", "Understock", "Normal Stock", "Overstock"):
            out.append(f"- {s_}: **{int(vc.get(s_, 0))}** ({vc.get(s_, 0) / n * 100:.0f}%)")
        out.append(f"- Availability (NMOS > 1): **{avail:.0f}%**")
        out.append(f"- At risk of stock out: **{int((risk == 'Risk of Stock out').sum())}** · Expiry risk: **{int((risk == 'Expiry Risk').sum())}** · Critical: **{int((risk == 'Critical Risk').sum())}**")
        if 'GF_Qty' in d.columns:
            gap = pd.to_numeric(d['GF_Qty'], errors='coerce')
            out.append(f"- Total units to reach 18 months (positive gaps): **{_bf(gap[gap > 0].sum())}**")
        v = st.session_state.get('kpi_avg_proc_lead')
        if v is not None:
            out.append(f"- Avg procurement lead time: **{v} days**")
        so = int((status == 'Stock Out').sum())
        out.append("\n**Reasoning:** " + ("Stock-outs are the first concern; " if so else "No stock-outs; ") +
                   ("overstock items should be redistributed before they expire." if int((status == 'Overstock').sum()) else "stock levels look balanced."))
        return "\n".join(out)

    if any(w in ql for w in ("prioritis", "prioritiz", "priority", "urgent", "recommend", "what should", "action")):
        t = d.copy()
        t['_n'] = pd.to_numeric(t.get('NMOS'), errors='coerce')
        t['_t'] = pd.to_numeric(t.get('TMOS'), errors='coerce')
        crit = t[(status.loc[t.index] == 'Stock Out') & (t['_t'].fillna(0) < 1)]
        pipe = t[(status.loc[t.index] == 'Stock Out') & (t['_t'].fillna(0) >= 1)]
        exp = t[risk.loc[t.index].isin(['Expiry Risk', 'Critical Risk'])]
        over = t[status.loc[t.index] == 'Overstock']
        out.append("**Suggested priorities (most urgent first)**")
        out.append(f"1. 🔴 **{len(crit)}** stock-out items with no meaningful pipeline (TMOS < 1) — order/expedite now." + (" e.g. " + ", ".join(crit['Material Description'].head(5)) if len(crit) else ""))
        out.append(f"2. 🟠 **{len(pipe)}** stock-out items that have stock inbound — follow up shipments." + (" e.g. " + ", ".join(pipe['Material Description'].head(5)) if len(pipe) else ""))
        out.append(f"3. 🟣 **{len(exp)}** items with expiry risk — redistribute near-expiry batches." + (" e.g. " + ", ".join(exp['Material Description'].head(5)) if len(exp) else ""))
        out.append(f"4. 🔵 **{len(over)}** overstocked items — stop new orders, rebalance between hubs.")
        out.append("\n**Reasoning:** an item with no stock and nothing inbound causes the quickest service failure, so it ranks above one whose stock is on the way; expiry loss and overstock are slower-moving.")
        return "\n".join(out)

    # 3) gap (GF)
    if "gf" in ql or "gap" in ql or "18 month" in ql or "target" in ql:
        if 'GF_Qty' in d.columns:
            t = d.copy()
            t['_g'] = pd.to_numeric(t['GF_Qty'], errors='coerce')
            m = re.search(r"top\s*(\d+)", ql)
            k = int(m.group(1)) if m else 10
            asc = any(w in ql for w in ("lowest", "most over", "excess", "surplus"))
            t = t.dropna(subset=['_g']).sort_values('_g', ascending=asc).head(k)
            out.append(f"**{'Largest surplus' if asc else 'Largest shortfall'} versus the 18-month target** (GF_MOS = 18 − TMOS, GF_Qty = GF_MOS × AMC):")
            out.append(_bot_table(t, ['Material Description', 'AMC', 'TMOS', 'GF_MOS', 'GF_Qty'], k))
            return "\n".join(out)

    # 4) ranking
    rank_cols = {"nmos": "NMOS", "amc": "AMC", "nsoh": "NSOH", "tmos": "TMOS", "hub": "Hubs", "head office": "Head Office"}
    if any(w in ql for w in ("top", "highest", "lowest", "most", "least", "largest", "smallest", "best", "worst")):
        for key, col in rank_cols.items():
            if key in ql and col in d.columns:
                m = re.search(r"(?:top|lowest|highest|bottom)\s*(\d+)", ql)
                k = int(m.group(1)) if m else 10
                asc = any(w in ql for w in ("lowest", "least", "smallest", "worst", "bottom"))
                t = d.copy()
                t['_v'] = pd.to_numeric(t[col], errors='coerce')
                t = t.dropna(subset=['_v']).sort_values('_v', ascending=asc).head(k)
                return f"**{'Lowest' if asc else 'Highest'} {k} by {col}:**\n" + _bot_table(t, ['Material Description', col, 'Stock Status'], k)

    # 5) risk questions
    if "expir" in ql or "risk" in ql:
        if "critical" in ql:
            sel, name = risk == 'Critical Risk', "Critical Risk"
        elif "expir" in ql:
            sel, name = risk.isin(['Expiry Risk', 'Critical Risk']), "Expiry Risk (incl. Critical)"
        else:
            sel, name = risk == 'Risk of Stock out', "Risk of Stock out"
        t = d[sel]
        out.append(f"**{len(t)}** material(s) with **{name}** in the current filter.")
        if len(t) and (want_list or not want_count):
            cols = ['Material Description', 'NMOS', 'AMC', 'Expiry'] if "expir" in ql else ['Material Description', 'NMOS', 'TMOS', 'Stock Status']
            out.append(_bot_table(t, cols, 15))
            if len(t) > 15:
                out.append(f"…and {len(t) - 15} more (click the card on the Dashboard to see all).")
        return "\n".join(out)

    # 6) status questions
    for key, val in sdef:
        if key in ql and "risk" not in ql:
            t = d[status == val]
            out.append(f"**{len(t)}** material(s) are **{val}** ({len(t) / n * 100:.0f}% of {n}).")
            if len(t) and (want_list or not want_count):
                out.append(_bot_table(t, ['Material Description', 'NMOS', 'TMOS', 'AMC'], 15))
                if len(t) > 15:
                    out.append(f"…and {len(t) - 15} more.")
            return "\n".join(out)

    # 7) material lookup
    hit = _bot_find_material(q, d)
    if hit is not None and len(hit):
        if len(hit) == 1:
            return _bot_material_profile(hit.iloc[0])
        out.append(f"I found {len(hit)} matching materials:")
        for _, r in hit.iterrows():
            out.append(f"- **{r['Material Description']}** — {r.get('Stock Status', '')}, NMOS {_bf(r.get('NMOS'), 2)}")
        out.append("\nName one of them for full details.")
        return "\n".join(out)

    # 8) optional LLM, else guidance
    llm = _bot_llm(q, d, list(history))
    if llm:
        return llm
    return ("I could not match that to the data. I can answer questions about **stock status counts and lists**, **risk / expiry**, "
            "**a specific material**, **top / lowest by NMOS, AMC, NSOH, GF_Qty**, **procurement lead time**, a **summary** or **priorities**.")


def _bot_panel():
    hist = st.session_state.setdefault('bot_history', [])
    d = st.session_state.get('_bot_df')
    box = st.container(height=340)
    with box:
        if not hist:
            st.markdown("👋 Ask me about stock status, risks, expiry, a material, or say **summary**.")
        for m in hist:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])
    with st.form("bot_form", clear_on_submit=True, border=False):
        q = st.text_input("Ask", placeholder="e.g. How many stock out items?", label_visibility="collapsed")
        c1, c2 = st.columns([3, 1])
        send = c1.form_submit_button("Send", use_container_width=True, type="primary")
        clr = c2.form_submit_button("Clear", use_container_width=True)
    if clr:
        st.session_state['bot_history'] = []
        st.rerun(scope="fragment")
    if send and q.strip():
        hist.append({"role": "user", "content": q.strip()})
        try:
            ans = _bot_answer(q.strip(), d, hist[:-1])
        except Exception as e:
            ans = f"Sorry, I could not work that out ({type(e).__name__}). Try rephrasing."
        hist.append({"role": "assistant", "content": ans})
        st.rerun(scope="fragment")


try:
    _bot_fragment = st.fragment(_bot_panel)
except Exception:
    _bot_fragment = _bot_panel


def render_floating_chatbot(d):
    st.session_state['_bot_df'] = d
    st.markdown("""
<style>
div[class*="st-key-floating_chat"] { position: fixed; bottom: 18px; right: 18px; z-index: 999990; width: auto !important; }
div[class*="st-key-floating_chat"] button[kind="secondary"], div[class*="st-key-floating_chat"] [data-testid="stPopover"] > button {
  border-radius: 28px; background: linear-gradient(135deg,#1a5276,#2e86c1); color: #fff; border: none;
  box-shadow: 0 6px 18px rgba(26,82,118,.45); padding: .55rem 1.1rem; font-weight: 600; }
div[class*="st-key-floating_chat"] [data-testid="stPopover"] > button p { color: #fff !important; }
div[data-testid="stPopoverBody"] { width: min(440px, 92vw) !important; max-height: 82vh; }
@media (max-width: 768px) { div[class*="st-key-floating_chat"] { bottom: 12px; right: 12px; } }
</style>""", unsafe_allow_html=True)
    with st.container(key="floating_chat"):
        with st.popover("💬 Ask Assistant"):
            st.markdown("**EPSS Stock Assistant**")
            _bot_fragment()


# ---------------------------------------------------
# Excel export helper (used by every download button)
# ---------------------------------------------------
_XL_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

def _xl(df, sheet_name="Data"):
    """Convert a DataFrame to styled .xlsx bytes for st.download_button."""
    from openpyxl.styles import Font as _F, PatternFill as _P, Alignment as _A
    d = df.copy()
    d.columns = [str(c) for c in d.columns]
    for c in d.columns:
        if d[c].dtype == "object" or pd.api.types.is_string_dtype(d[c]):
            d[c] = d[c].apply(lambda v: _XL_ILLEGAL.sub("", v) if isinstance(v, str) else v)
        elif str(d[c].dtype).startswith("datetime64") and getattr(d[c].dt, "tz", None) is not None:
            d[c] = d[c].dt.tz_localize(None)
    safe = re.sub(r"[\[\]:\*\?/\\]", "_", str(sheet_name))[:31] or "Data"
    out = BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        d.to_excel(w, sheet_name=safe, index=False)
        ws = w.sheets[safe]
        for cell in ws[1]:
            cell.font = _F(bold=True, color="FFFFFF")
            cell.fill = _P("solid", fgColor="1A5276")
            cell.alignment = _A(horizontal="left", vertical="center", wrap_text=True)
        for i, col in enumerate(d.columns, start=1):
            longest = max([len(str(col))] + [len(str(v)) for v in d[col].head(200).tolist() if v is not None])
            ws.column_dimensions[get_column_letter(i)].width = min(max(longest + 2, 10), 60)
        ws.freeze_panes = "A2"
        if len(d.columns) > 0:
            ws.auto_filter.ref = ws.dimensions
    out.seek(0)
    return out.getvalue()


# ---------------------------------------------------
# Supabase Configuration - Using Streamlit Secrets
# ---------------------------------------------------
@st.cache_resource
def init_supabase():
    """Initialize Supabase client"""
    try:
        supabase_url = st.secrets["SUPABASE_URL"]
        supabase_key = st.secrets["SUPABASE_KEY"]
        supabase = create_client(supabase_url, supabase_key)
        return supabase
    except Exception as e:
        st.error(f"Error connecting to Supabase: {e}")
        return None

def check_supabase_connection():
    """Check Supabase connection health"""
    try:
        if st.session_state.supabase_client:
            response = st.session_state.supabase_client.table("health_data").select("*").limit(1).execute()
            return True
    except Exception:
        return False
    return False

# ===================================================
# DOS TRACKING SUPABASE FUNCTIONS (DEFINED EARLY)
# ===================================================

def save_dos_tracking_to_supabase(dos_tracking_dict):
    """Save DOS tracking data to Supabase"""
    try:
        if st.session_state.get('supabase_client') is None:
            return False

        records = []
        for material, tracking_data in dos_tracking_dict.items():
            record = {
                'material_description': material,
                'start_date': tracking_data.get('start_date').isoformat() if tracking_data.get('start_date') else None,
                'last_check_date': tracking_data.get('last_check_date').isoformat() if tracking_data.get('last_check_date') else None,
                'current_dos': tracking_data.get('days', 0),
                'is_out_of_stock': tracking_data.get('is_out_of_stock', False),
                'last_nmos': tracking_data.get('last_nmos', 0)
            }
            records.append(record)

        if records:
            response = st.session_state.supabase_client.table("dos_tracking").upsert(records).execute()
            return True
        return False
    except Exception as e:
        st.error(f"Error saving DOS tracking to Supabase: {e}")
        return False

def load_dos_tracking_from_supabase():
    """Load DOS tracking data from Supabase"""
    try:
        if st.session_state.get('supabase_client') is None:
            return {}

        response = st.session_state.supabase_client.table("dos_tracking").select("*").execute()

        if response.data:
            dos_tracking = {}
            for record in response.data:
                material = record['material_description']
                start_date = None
                if record.get('start_date'):
                    try:
                        start_date = datetime.fromisoformat(record['start_date'])
                    except:
                        start_date = None

                last_check_date = None
                if record.get('last_check_date'):
                    try:
                        last_check_date = datetime.fromisoformat(record['last_check_date'])
                    except:
                        last_check_date = None

                dos_tracking[material] = {
                    'start_date': start_date,
                    'last_check_date': last_check_date,
                    'days': record.get('current_dos', 0),
                    'is_out_of_stock': record.get('is_out_of_stock', False),
                    'last_nmos': record.get('last_nmos', 0)
                }
            return dos_tracking
        return {}
    except Exception as e:
        # Table might not exist yet
        if "relation" in str(e) and "does not exist" in str(e):
            return {}
        st.error(f"Error loading DOS tracking from Supabase: {e}")
        return {}

def clear_dos_tracking_in_supabase():
    """Clear all DOS tracking data from Supabase"""
    try:
        if st.session_state.get('supabase_client') is None:
            return False

        response = st.session_state.supabase_client.table("dos_tracking").delete().neq("material_description", "").execute()
        return True
    except Exception as e:
        st.error(f"Error clearing DOS tracking: {e}")
        return False

def reset_dos_tracking():
    """Reset all DOS tracking data"""
    if clear_dos_tracking_in_supabase():
        st.session_state.dos_tracking = load_dos_tracking_from_supabase()
        st.session_state.pop('_main_frames_memo', None)
        st.success("✅ DOS tracking data has been reset!")
        return True
    return False
# ===================================================
# NSOH SNAPSHOT FUNCTIONS
# ===================================================

def load_nsoh_snapshots():
    """Load ALL NSOH snapshots from Supabase with pagination"""
    try:
        if st.session_state.get('supabase_client') is None:
            return pd.DataFrame()

        # Use pagination to get ALL data
        all_data = []
        page = 0
        page_size = 1000

        while True:
            response = st.session_state.supabase_client.table("ho_nsoh_snapshots") \
                .select("*") \
                .order("snapshot_date", desc=False) \
                .range(page * page_size, (page + 1) * page_size - 1) \
                .execute()

            if not response.data:
                break

            all_data.extend(response.data)

            # Stop when last page reached
            if len(response.data) < page_size:
                break

            page += 1

        if not all_data:
            return pd.DataFrame()

        df = pd.DataFrame(all_data)

        # Convert snapshot_date to datetime
        df['snapshot_date'] = pd.to_datetime(df['snapshot_date'])
        # Format as Month-Year for display
        df['Month_Year'] = df['snapshot_date'].dt.strftime('%b-%Y')

        return df
    except Exception as e:
        if "relation" in str(e) and "does not exist" in str(e):
            return pd.DataFrame()
        st.error(f"Error loading NSOH snapshots: {e}")
        return pd.DataFrame()

def save_nsoh_snapshot(material_description, nsoh_value, snapshot_date):
    """Save NSOH snapshot to Supabase"""
    try:
        if st.session_state.get('supabase_client') is None:
            return False

        # Check if entry already exists for this material and date
        existing = st.session_state.supabase_client.table("ho_nsoh_snapshots") \
            .select("*") \
            .eq("material_description", material_description) \
            .eq("snapshot_date", snapshot_date.isoformat()) \
            .execute()

        if existing.data:
            # Update existing
            response = st.session_state.supabase_client.table("ho_nsoh_snapshots") \
                .update({"nsoh": float(nsoh_value)}) \
                .eq("material_description", material_description) \
                .eq("snapshot_date", snapshot_date.isoformat()) \
                .execute()
        else:
            # Insert new
            record = {
                'material_description': material_description,
                'nsoh': float(nsoh_value),
                'snapshot_date': snapshot_date.isoformat()
            }
            response = st.session_state.supabase_client.table("ho_nsoh_snapshots").insert(record).execute()

        return True
    except Exception as e:
        st.error(f"Error saving NSOH snapshot: {e}")
        return False

def clear_nsoh_snapshots():
    """Clear all NSOH snapshots from Supabase"""
    try:
        if st.session_state.get('supabase_client') is None:
            return False

        response = st.session_state.supabase_client.table("ho_nsoh_snapshots").delete().neq("id", "").execute()
        return True
    except Exception as e:
        st.error(f"Error clearing NSOH snapshots: {e}")
        return False

def create_nsoh_pivot_table(snapshots_df):
    """Create a pivot table from snapshots: rows=Material Description, columns=Month_Year, values=NSOH"""
    if snapshots_df.empty:
        return pd.DataFrame()

    # Remove duplicates before pivoting
    snapshots_df_clean = snapshots_df.drop_duplicates(subset=['material_description', 'Month_Year'], keep='first')

    # Pivot the data
    pivot_df = snapshots_df_clean.pivot_table(
        index='material_description',
        columns='Month_Year',
        values='nsoh',
        aggfunc='first'  # Use first value if duplicates exist
    ).fillna(0)

    # Sort columns chronologically
    try:
        # Extract date from Month-Year for sorting
        date_order = sorted(pivot_df.columns, key=lambda x: pd.to_datetime(x, format='%b-%Y'))
        pivot_df = pivot_df[date_order]
    except:
        pass

    return pivot_df

def get_available_months(snapshots_df):
    """Get sorted list of available months from snapshots"""
    if snapshots_df.empty:
        return []

    # Get unique months and sort them
    months = snapshots_df['Month_Year'].unique().tolist()

    try:
        # Sort chronologically
        def parse_month(month_str):
            try:
                return pd.to_datetime(month_str, format='%b-%Y')
            except:
                try:
                    return pd.to_datetime(month_str)
                except:
                    return None

        months_with_dates = [(m, parse_month(m)) for m in months]
        months_with_dates = [(m, dt) for m, dt in months_with_dates if dt is not None]
        months_with_dates.sort(key=lambda x: x[1])
        sorted_months = [m for m, dt in months_with_dates]

        return sorted_months
    except Exception as e:
        return sorted(months)

def save_nsoh_snapshots_batch(materials_data, snapshot_date):
    """Save multiple NSOH snapshots in batch"""
    try:
        if st.session_state.get('supabase_client') is None:
            return False, 0

        saved_count = 0
        for item in materials_data:
            if save_nsoh_snapshot(item['material_description'], item['nsoh'], snapshot_date):
                saved_count += 1

        return True, saved_count
    except Exception as e:
        st.error(f"Error saving snapshots in batch: {e}")
        return False, 0
# ===================================================
# PO REQUESTED DATES FUNCTIONS
# ===================================================

def save_po_requested_date(po_number, material_description, requested_date):
    """Save or update requested date for a PO"""
    try:
        if st.session_state.get('supabase_client') is None:
            return False

        data = {
            'po_number': po_number,
            'material_description': material_description,
            'requested_date': requested_date.isoformat() if requested_date else None,
            'updated_at': datetime.now().isoformat()
        }

        # Use upsert to update if exists, insert if not
        response = st.session_state.supabase_client.table("po_requested_dates").upsert(
            data, 
            on_conflict="po_number,material_description"
        ).execute()

        return True
    except Exception as e:
        st.error(f"Error saving requested date: {e}")
        return False

def delete_po_requested_date(po_number, material_description):
    """Delete requested date for a PO"""
    try:
        if st.session_state.get('supabase_client') is None:
            return False

        response = st.session_state.supabase_client.table("po_requested_dates").delete().eq(
            "po_number", po_number
        ).eq("material_description", material_description).execute()

        return True
    except Exception as e:
        st.error(f"Error deleting requested date: {e}")
        return False

def load_all_requested_dates():
    """Load all requested dates from Supabase"""
    try:
        if st.session_state.get('supabase_client') is None:
            return {}

        response = st.session_state.supabase_client.table("po_requested_dates").select("*").execute()

        requested_dates = {}
        if response.data:
            for record in response.data:
                key = f"{record['po_number']}_{record['material_description']}"
                requested_date = None
                if record.get('requested_date'):
                    try:
                        requested_date = datetime.fromisoformat(record['requested_date']).date()
                    except:
                        requested_date = None
                requested_dates[key] = requested_date

        return requested_dates
    except Exception as e:
        if "relation" not in str(e):
            st.error(f"Error loading requested dates: {e}")
        return {}
# Check authentication
if 'auth' not in st.session_state:
    st.session_state['auth'] = False

if not st.session_state['auth']:
    show_login_page()
    st.stop()
# ===================================================
# PROCUREMENT LEAD TIME FUNCTIONS
# ===================================================

@st.cache_data(ttl=300, show_spinner=False)
def load_procurement_lead_time(cache_bust=0):
    """
    Load all procurement lead time records from Supabase.
    `cache_bust` is part of the cache key (NO leading underscore - Streamlit ignores such parameters),
    so bumping it after a save forces a fresh read instead of waiting for the 5-minute TTL.
    """
    try:
        if st.session_state.get('supabase_client') is None:
            return pd.DataFrame()

        all_data = []
        page = 0
        page_size = 1000

        while True:
            response = st.session_state.supabase_client.table("procurement_lead_time") \
                .select("*") \
                .order("posting_date", desc=True) \
                .range(page * page_size, (page + 1) * page_size - 1) \
                .execute()

            if not response.data:
                break
            all_data.extend(response.data)
            if len(response.data) < page_size:
                break
            page += 1

        if not all_data:
            return pd.DataFrame()

        df = pd.DataFrame(all_data)

        for col in ['epss_date', 'dmd_received_date', 'dmd_submission_date', 'posting_date']:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce')

        for col in ['request_quantity', 'po_quantity']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        return df
    except Exception as e:
        if "relation" in str(e) and "does not exist" in str(e):
            return pd.DataFrame()
        st.error(f"Error loading procurement lead time: {e}")
        return pd.DataFrame()


def _bust_proc_cache():
    """Force the next read of procurement records to hit Supabase."""
    st.session_state.proc_cache_bust = st.session_state.get('proc_cache_bust', 0) + 1
    try:
        load_procurement_lead_time.clear()
    except Exception:
        pass
    st.session_state.pop('_kpi_lead_memo', None)


_PROC_DATE_COLS = ['epss_date', 'dmd_received_date', 'dmd_submission_date', 'posting_date']
_PROC_EDITABLE = ['material_description', 'year_of_request', 'funding_source', 'request_quantity',
                  'po_number', 'po_quantity'] + _PROC_DATE_COLS


def _proc_parse(k, val):
    if val is None or (isinstance(val, float) and pd.isna(val)) or (isinstance(val, str) and val.strip() == ''):
        return None
    if k in _PROC_DATE_COLS:
        try:
            return pd.to_datetime(val).date().isoformat()
        except Exception:
            return None
    if k in ('request_quantity', 'po_quantity'):
        try:
            return float(str(val).replace(',', '').strip())
        except Exception:
            return None
    if k == 'year_of_request':
        try:
            return int(float(val))
        except Exception:
            return None
    return val.strip() if isinstance(val, str) else val


def _proc_autosave(editor_key):
    """data_editor on_change: write edited / added / deleted rows to Supabase right away."""
    client = st.session_state.get('supabase_client')
    state = st.session_state.get(editor_key) or {}
    if client is None or not state:
        return
    ids = st.session_state.get('_proc_row_ids', [])

    def _rid(i):
        i = int(i)
        if i < len(ids) and ids[i] is not None and not pd.isna(ids[i]):
            return int(ids[i])
        return None

    ok = err = skipped = 0
    now = datetime.now().isoformat()
    deleted_ids = [r for r in (_rid(i) for i in state.get('deleted_rows', [])) if r is not None]

    if deleted_ids:
        try:
            client.table("procurement_lead_time").delete().in_("id", deleted_ids).execute()
            ok += len(deleted_ids)
        except Exception as e:
            err += len(deleted_ids)
            st.session_state['_proc_flash_err'] = f"Delete error: {e}"

    for idx, changes in (state.get('edited_rows') or {}).items():
        rid = _rid(idx)
        if rid is None or rid in deleted_ids:
            continue
        rec = {k: _proc_parse(k, v) for k, v in changes.items() if k in _PROC_EDITABLE}
        if not rec:
            continue
        rec['updated_at'] = now
        try:
            client.table("procurement_lead_time").update(rec).eq("id", rid).execute()
            ok += 1
        except Exception as e:
            err += 1
            st.session_state['_proc_flash_err'] = f"Update error: {e}"

    new_rows = []
    for row in (state.get('added_rows') or []):
        rec = {k: _proc_parse(k, row.get(k)) for k in _PROC_EDITABLE if k in row}
        rec = {k: v for k, v in rec.items() if v is not None}
        if not rec.get('material_description'):
            skipped += 1          # incomplete new row: keep it in the editor until a material is chosen
            continue
        rec['updated_at'] = now
        new_rows.append(rec)
    if new_rows:
        try:
            client.table("procurement_lead_time").insert(new_rows).execute()
            ok += len(new_rows)
        except Exception as e:
            err += len(new_rows)
            st.session_state['_proc_flash_err'] = f"Insert error: {e}"

    if ok or err:
        _bust_proc_cache()
        st.session_state['proc_editor_ver'] = st.session_state.get('proc_editor_ver', 0) + 1
        if ok:
            log_dashboard_update("Edited procurement records", f"{ok} change(s) saved", ok)
            st.session_state['_proc_flash'] = f"✅ Saved automatically ({ok} change{'s' if ok != 1 else ''})."


def save_procurement_record(record_dict):
    """Insert a new procurement lead time record"""
    try:
        if st.session_state.get('supabase_client') is None:
            return False

        for key in ['epss_date', 'dmd_received_date', 'dmd_submission_date', 'posting_date']:
            if key in record_dict and record_dict[key] is not None:
                if hasattr(record_dict[key], 'isoformat'):
                    record_dict[key] = record_dict[key].isoformat()

        record_dict['updated_at'] = datetime.now().isoformat()
        record_dict.pop('id', None)

        st.session_state.supabase_client.table("procurement_lead_time").insert(record_dict).execute()
        return True
    except Exception as e:
        st.error(f"Error saving procurement record: {e}")
        return False


def update_procurement_record(record_id, record_dict):
    """Update an existing procurement lead time record"""
    try:
        if st.session_state.get('supabase_client') is None:
            return False

        for key in ['epss_date', 'dmd_received_date', 'dmd_submission_date', 'posting_date']:
            if key in record_dict and record_dict[key] is not None:
                if hasattr(record_dict[key], 'isoformat'):
                    record_dict[key] = record_dict[key].isoformat()

        record_dict['updated_at'] = datetime.now().isoformat()
        record_dict.pop('id', None)

        st.session_state.supabase_client.table("procurement_lead_time") \
            .update(record_dict).eq("id", record_id).execute()
        return True
    except Exception as e:
        st.error(f"Error updating procurement record: {e}")
        return False


def delete_procurement_record(record_id):
    """Delete a procurement lead time record"""
    try:
        if st.session_state.get('supabase_client') is None:
            return False
        st.session_state.supabase_client.table("procurement_lead_time") \
            .delete().eq("id", record_id).execute()
        return True
    except Exception as e:
        st.error(f"Error deleting record: {e}")
        return False


def calculate_procurement_lead_times(df):
    """
    Compute:
    - DMD Processing Days = DMD Submission - DMD Received   (whole days)
    - Procurement Lead Time = Posting Date - DMD Submission Date  (only if posted)
    - Procurement Process Time = Today - DMD Submission Date  (only if NOT posted)
    """
    if df.empty:
        return df
    df = df.copy()

    df['DMD Processing Days'] = (
        df['dmd_submission_date'] - df['dmd_received_date']
    ).dt.days

    today = pd.Timestamp(date.today())

    df['Procurement Lead Time'] = np.where(
        df['posting_date'].notna() & df['dmd_submission_date'].notna(),
        (df['posting_date'] - df['dmd_submission_date']).dt.days,
        np.nan
    )

    df['Procurement Process Time'] = np.where(
        df['posting_date'].isna() & df['dmd_submission_date'].notna(),
        (today - df['dmd_submission_date']).dt.days,
        np.nan
    )

    return df
# ===================================================
# LOOKUP POSTING DATE FROM NEW DELIVERIES
# ===================================================
def enrich_posting_date_from_deliveries(proc_df, deliveries_df):
    """
    Fill/overwrite posting_date in procurement records by matching
    Material Description + PO Number against New Deliveries data.

    Rule: When Material Description AND Purchase Order match,
    take the Posting Date from New Deliveries.
    """
    if proc_df is None or proc_df.empty:
        return proc_df
    if deliveries_df is None or deliveries_df.empty:
        return proc_df

    proc_df = proc_df.copy()
    deliveries_df = deliveries_df.copy()

    # Normalize keys for matching
    deliveries_df['PO Number'] = deliveries_df['PO Number'].astype(str).str.strip()
    deliveries_df['Material Description'] = deliveries_df['Material Description'].astype(str).str.strip()
    deliveries_df['Posting Date'] = pd.to_datetime(deliveries_df['Posting Date'], errors='coerce')

    # Build lookup: (Material, PO) -> latest posting date
    lookup = (
        deliveries_df
        .dropna(subset=['Posting Date'])
        .groupby(['Material Description', 'PO Number'])['Posting Date']
        .min()
        .to_dict()
    )

    # Normalize procurement keys
    proc_df['material_description'] = proc_df['material_description'].astype(str).str.strip()
    proc_df['po_number'] = proc_df['po_number'].astype(str).str.strip()

    def resolve_posting(row):
        key = (row['material_description'], row['po_number'])
        if key in lookup:
            return lookup[key]
        # Fallback: keep existing posting date if not found in deliveries
        return row.get('posting_date')

    proc_df['posting_date'] = proc_df.apply(resolve_posting, axis=1)
    proc_df['posting_date'] = pd.to_datetime(proc_df['posting_date'], errors='coerce')

    return proc_df

# ===================================================
# SESSION STATE INIT FOR PROCUREMENT CACHE BUST
# ===================================================
if 'proc_cache_bust' not in st.session_state:
    st.session_state.proc_cache_bust = 0
# ===================================================
# NORMALIZERS
# ===================================================
def _normalize_po(po):
    if po is None:
        return ""
    try:
        if pd.isna(po):
            return ""
    except Exception:
        pass
    s = str(po).strip().upper()
    if s.endswith(".0") and s[:-2].replace(".", "", 1).isdigit():
        s = s[:-2]
    return "".join(s.split())


def _normalize_material(mat):
    if mat is None:
        return ""
    try:
        if pd.isna(mat):
            return ""
    except Exception:
        pass
    return " ".join(str(mat).strip().upper().split())


# ===================================================
# SIDEBAR LINKAGE
# ===================================================
def _link_procurement_to_sidebar(proc_df, filtered_df):
    if proc_df is None or proc_df.empty:
        return proc_df
    if filtered_df is None or filtered_df.empty:
        return proc_df.iloc[0:0].copy()
    if 'Material Description' not in filtered_df.columns:
        return proc_df

    allowed_materials = set(
        filtered_df['Material Description']
        .dropna()
        .astype(str)
        .map(_normalize_material)
        .tolist()
    )
    if not allowed_materials:
        return proc_df.iloc[0:0].copy()

    out = proc_df.copy()
    out['_mat_key_norm'] = out['material_description'].apply(_normalize_material)
    out = out[out['_mat_key_norm'].isin(allowed_materials)]
    out = out.drop(columns=['_mat_key_norm'], errors='ignore')
    return out.reset_index(drop=True)


# ===================================================
# HELPER: Enrich Posting Date (EARLIEST) — match on Material + PO
# ===================================================
def enrich_posting_date_from_deliveries(proc_df, deliveries_df):
    """
    When (Material Description, PO Number) match, take the
    EARLIEST Posting Date from New Deliveries.
    """
    if proc_df is None or proc_df.empty:
        return proc_df
    if deliveries_df is None or deliveries_df.empty:
        return proc_df

    proc_df = proc_df.copy()
    deliveries_df = deliveries_df.copy()

    deliveries_df['_po_key']  = deliveries_df['PO Number'].apply(_normalize_po)
    deliveries_df['_mat_key'] = deliveries_df['Material Description'].apply(_normalize_material)
    deliveries_df['_post_dt'] = pd.to_datetime(deliveries_df['Posting Date'], errors='coerce')

    lookup = (
        deliveries_df
        .dropna(subset=['_post_dt'])
        .groupby(['_mat_key', '_po_key'])['_post_dt']
        .min()
        .to_dict()
    )

    proc_df['_po_key']  = proc_df['po_number'].apply(_normalize_po)
    proc_df['_mat_key'] = proc_df['material_description'].apply(_normalize_material)

    def resolve(row):
        return lookup.get((row['_mat_key'], row['_po_key']), row.get('posting_date'))

    proc_df['posting_date'] = proc_df.apply(resolve, axis=1)
    proc_df['posting_date'] = pd.to_datetime(proc_df['posting_date'], errors='coerce')
    proc_df = proc_df.drop(columns=['_po_key', '_mat_key'], errors='ignore')
    return proc_df


# ===================================================
# HELPER: Enrich Delivered Qty (SUM) — match on Material + PO
# ===================================================
def enrich_delivered_qty_from_deliveries(proc_df, deliveries_df):
    """
    Delivered Qty = SUM of Quantity grouped by (Material, PO).
    """
    if proc_df is None or proc_df.empty:
        return proc_df

    proc_df = proc_df.copy()

    if deliveries_df is None or deliveries_df.empty:
        if 'Delivered Qty' not in proc_df.columns:
            proc_df['Delivered Qty'] = None
        return proc_df

    deliveries_df = deliveries_df.copy()

    deliveries_df['_po_key']  = deliveries_df['PO Number'].apply(_normalize_po)
    deliveries_df['_mat_key'] = deliveries_df['Material Description'].apply(_normalize_material)

    deliveries_df['Quantity'] = (
        deliveries_df['Quantity']
        .astype(str)
        .str.replace(',', '', regex=False)
        .str.strip()
    )
    deliveries_df['Quantity'] = pd.to_numeric(deliveries_df['Quantity'], errors='coerce').fillna(0)

    final = deliveries_df.groupby(
        ['_mat_key', '_po_key'], as_index=False
    )['Quantity'].sum()

    table2_lookup = dict(
        zip(zip(final['_mat_key'], final['_po_key']), final['Quantity'])
    )

    proc_df['_po_key']  = proc_df['po_number'].apply(_normalize_po)
    proc_df['_mat_key'] = proc_df['material_description'].apply(_normalize_material)

    def _resolve(row):
        return table2_lookup.get((row['_mat_key'], row['_po_key']), None)

    proc_df['Delivered Qty'] = proc_df.apply(_resolve, axis=1)
    proc_df['Delivered Qty'] = pd.to_numeric(proc_df['Delivered Qty'], errors='coerce')

    proc_df = proc_df.drop(columns=['_po_key', '_mat_key'], errors='ignore')
    return proc_df


# ===================================================
# HELPER: PO Qty Variance
# ===================================================
def calculate_po_qty_variance(df):
    if df.empty:
        return df
    df = df.copy()
    po_qty = pd.to_numeric(df.get('po_quantity', 0), errors='coerce').fillna(0)
    delivered_qty = pd.to_numeric(df.get('Delivered Qty', 0), errors='coerce').fillna(0)
    df['PO Qty Variance'] = po_qty - delivered_qty
    return df



def _compute_avg_proc_lead_raw(base_df):
    """Same number as the tab's 'Avg Procurement Lead' (uses the tab's filter widgets' state)."""
    proc = load_procurement_lead_time(st.session_state.get('proc_cache_bust', 0))
    if proc is None or proc.empty:
        return None
    deliveries = globals().get('df_new_deliveries')
    if deliveries is not None and not deliveries.empty:
        proc = enrich_posting_date_from_deliveries(proc, deliveries)
        proc = enrich_delivered_qty_from_deliveries(proc, deliveries)
    if base_df is not None and not base_df.empty and 'Material Description' in base_df.columns:
        proc = _link_procurement_to_sidebar(proc, base_df)
    if proc.empty:
        return None
    proc = calculate_procurement_lead_times(proc)
    year_f = st.session_state.get('proc_lead_year_v6', 'All')
    fund_f = st.session_state.get('proc_lead_funding_v6', 'All')
    mat_f = st.session_state.get('proc_lead_material_v6', 'All')
    po_f = st.session_state.get('proc_lead_search_v6', '')
    if year_f != "All":
        proc = proc[proc['year_of_request'].astype(str) == year_f]
    if fund_f != "All":
        proc = proc[proc['funding_source'].astype(str) == fund_f]
    if mat_f != "All":
        proc = proc[proc['material_description'] == mat_f]
    if po_f:
        proc = proc[proc['po_number'].astype(str).str.contains(po_f, case=False, na=False)]
    avg = proc['Procurement Lead Time'].dropna().mean() if not proc.empty else 0
    return int(round(avg)) if pd.notna(avg) else 0


def _compute_avg_proc_lead(base_df):
    """Memoized wrapper: recompute only when records, filters or materials change."""
    try:
        deliveries = globals().get('df_new_deliveries')
        mat_sig = 0
        if base_df is not None and not base_df.empty and 'Material Description' in base_df.columns:
            mat_sig = int(pd.util.hash_pandas_object(base_df['Material Description'].astype(str), index=False).sum())
        key = (st.session_state.get('proc_cache_bust', 0),
               st.session_state.get('proc_lead_year_v6', 'All'), st.session_state.get('proc_lead_funding_v6', 'All'),
               st.session_state.get('proc_lead_material_v6', 'All'), st.session_state.get('proc_lead_search_v6', ''),
               mat_sig, 0 if deliveries is None else len(deliveries), date.today().isoformat())
    except Exception:
        return _compute_avg_proc_lead_raw(base_df)
    memo = st.session_state.get('_kpi_lead_memo')
    if memo and memo[0] == key:
        return memo[1]
    val = _compute_avg_proc_lead_raw(base_df)
    st.session_state['_kpi_lead_memo'] = (key, val)
    return val


# ---------------------------------------------------
# Page Setup
# ---------------------------------------------------
st.set_page_config(
    page_title="HPC STOCK MANAGEMENT DASHBORD", 
    layout="wide", 
    initial_sidebar_state="auto"
)

# ---------------------------------------------------
# CSS Styling with Mobile Responsiveness (ENHANCED)
# ---------------------------------------------------
st.markdown("""
<style>
    /* Main container */
    .stApp {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    }

    /* Metric cards */
    div[data-testid="stMetric"] {
        background: white;
        border-radius: 15px;
        padding: 15px;
        transition: all 0.3s ease;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }

    div[data-testid="stMetric"]:hover {
        transform: translateY(-5px);
        box-shadow: 0 8px 15px rgba(0,0,0,0.2);
        background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
    }

    /* Animations */
    @keyframes shake {
        0%, 100% { transform: translateX(0); }
        10%, 30%, 50%, 70%, 90% { transform: translateX(-2px); }
        20%, 40%, 60%, 80% { transform: translateX(2px); }
    }

    @keyframes vertical-shake {
        0%, 100% { transform: translateY(0); }
        10%, 30%, 50%, 70%, 90% { transform: translateY(-2px); }
        20%, 40%, 60%, 80% { transform: translateY(2px); }
    }

    @keyframes gentle-shake {
        0%, 100% { transform: translateX(0); }
        25%, 75% { transform: translateX(-1px); }
        50% { transform: translateX(1px); }
    }

    @keyframes float-shake {
        0%, 100% { transform: translateY(0) translateX(0); }
        20% { transform: translateY(-3px) translateX(2px); }
        40% { transform: translateY(0) translateX(-2px); }
        60% { transform: translateY(-2px) translateX(1px); }
        80% { transform: translateY(0) translateX(-1px); }
    }

    .stButton button:hover {
        animation: shake 0.5s ease-in-out;
        transform: scale(1.02);
        transition: all 0.3s ease;
    }

    div[data-testid="stMetricValue"]:hover {
        animation: gentle-shake 0.3s ease-in-out;
    }

    .stDownloadButton button:hover {
        animation: shake 0.4s ease-in-out;
    }

    button[data-baseweb="tab"]:hover {
        animation: gentle-shake 0.2s ease-in-out;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white !important;
    }

    /* Stock cards */
    .stock-card {
        border: 1px solid #ddd;
        border-radius: 10px;
        padding: 15px;
        margin: 5px;
        background-color: white;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        transition: all 0.3s ease;
    }

    .stock-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.15);
    }

    .gradient-text {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        font-weight: bold;
    }

    /* Tabs */
    button[data-baseweb="tab"] {
        font-size: 18px !important;
        font-weight: 700 !important;
        font-family: 'Times New Roman', sans-serif !important;
        padding: 10px 20px !important;
    }

    /* Legend box */
    .legend-box {
        margin: 10px 0 20px 0;
        padding: 15px;
        background-color: #f8f9fa;
        border-radius: 10px;
        border: 1px solid #dee2e6;
    }

    .legend-title {
        margin: 0 0 10px 0;
        font-size: 16px;
        font-weight: bold;
    }

    .legend-item {
        display: flex;
        align-items: center;
        gap: 8px;
    }

    .legend-color {
        width: 20px;
        height: 20px;
        border-radius: 3px;
    }

    /* Animated Header */
    .animated-header {
        animation: float-shake 3s ease-in-out infinite;
        display: inline-block;
    }

    .animated-subtitle {
        animation: float-shake 4s ease-in-out infinite;
        display: inline-block;
    }

    /* ============================================ */
    /* MOBILE RESPONSIVE STYLES - ENHANCED */
    /* ============================================ */
    @media only screen and (max-width: 768px) {
        .stApp {
            padding: 0.5rem !important;
        }
        div[data-testid="stMetric"] {
            margin-bottom: 10px !important;
            padding: 10px !important;
        }
        h1 {
            font-size: 22px !important;
            text-align: center !important;
        }
        h3 {
            font-size: 18px !important;
        }
        h4 {
            font-size: 16px !important;
        }
        button[data-baseweb="tab"] {
            font-size: 12px !important;
            padding: 6px 10px !important;
            white-space: nowrap !important;
        }
        [data-testid="stTabs"] {
            overflow-x: auto !important;
            white-space: nowrap !important;
            flex-wrap: nowrap !important;
        }
        [data-testid="stTabs"] button {
            flex: 0 0 auto !important;
        }
        .stock-card {
            padding: 8px !important;
            margin: 5px 0 !important;
        }
        .stock-card h4 {
            font-size: 14px !important;
        }
        .stock-card p {
            font-size: 12px !important;
            margin: 5px 0 !important;
        }
        .legend-box {
            padding: 8px !important;
        }
        .legend-item {
            font-size: 10px !important;
        }
        .legend-color {
            width: 14px !important;
            height: 14px !important;
        }
        .stDataFrame {
            overflow-x: auto !important;
        }
        div[data-testid="stMetricValue"] {
            font-size: 20px !important;
        }
        div[data-testid="stMetricLabel"] {
            font-size: 12px !important;
        }
        .stButton button {
            font-size: 12px !important;
            padding: 6px 12px !important;
        }
        [data-testid="stSidebar"] {
            width: 280px !important;
        }
        .stPlotlyChart {
            width: 100% !important;
            overflow-x: auto !important;
        }
    }

    @media only screen and (max-width: 480px) {
        h1 {
            font-size: 18px !important;
        }
        button[data-baseweb="tab"] {
            font-size: 10px !important;
            padding: 4px 8px !important;
        }
        div[data-testid="stMetricValue"] {
            font-size: 16px !important;
        }
    }

    @media only screen and (min-width: 769px) and (max-width: 1024px) {
        button[data-baseweb="tab"] {
            font-size: 14px !important;
            padding: 8px 14px !important;
        }
        h1 {
            font-size: 28px !important;
        }
        div[data-testid="stMetricValue"] {
            font-size: 22px !important;
        }
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------
# Narrower gap between the sidebar and the main panel (desktop)
# ---------------------------------------------------
st.markdown("""
<style>
@media only screen and (min-width: 769px) {
    [data-testid="stMainBlockContainer"], [data-testid="stAppViewBlockContainer"],
    section.main > div.block-container, .block-container {
        padding-left: 1rem !important;
        padding-right: 1.5rem !important;
        padding-top: 4rem !important;   /* clears Streamlit's fixed top bar (about 3.75rem) */
        max-width: 100% !important;
    }
}
/* helper elements that draw nothing (<style> blocks, 0-height script frames) must not add blank gaps */
[data-testid="stElementContainer"]:has(> [data-testid="stMarkdown"] [data-testid="stMarkdownContainer"] > style:only-child),
[data-testid="stElementContainer"]:has(> [data-testid="stMarkdown"] [data-testid="stMarkdownContainer"] > p > style:only-child),
.element-container:has(> [data-testid="stMarkdown"] [data-testid="stMarkdownContainer"] > style:only-child) {
    display: none !important;
}
[data-testid="stElementContainer"]:has(iframe[height="0"]), .element-container:has(iframe[height="0"]) {
    position: absolute !important; height: 0 !important; overflow: hidden !important; margin: 0 !important;
}
[data-testid="stMainBlockContainer"] h1.animated-header { margin: 0 !important; padding: 0 !important; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------
# MOBILE LAYER (phones & small tablets)
# ---------------------------------------------------
st.markdown("""
<style>
@media only screen and (max-width: 768px) {
    .block-container { padding: 3.75rem 0.75rem 3rem 0.75rem !important; max-width: 100% !important; }
    /* two cards per row on phones instead of one very long stack */
    [data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; gap: 0.5rem !important; }
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
    [data-testid="stHorizontalBlock"] > [data-testid="column"] {
        min-width: calc(50% - 0.5rem) !important;
        flex: 1 1 calc(50% - 0.5rem) !important;
    }
    .animated-header, .animated-subtitle { animation: none !important; display: block !important; }
    .stButton button, .stDownloadButton button { min-height: 44px; width: 100%; }
    [data-testid="stDataFrame"], [data-testid="stTable"] { overflow-x: auto !important; }
    [data-testid="stMarkdownContainer"] table { display: block; overflow-x: auto; }
    .js-plotly-plot, .plotly, .stPlotlyChart { max-width: 100% !important; }
    div[data-testid="stMetricValue"] { font-size: 18px !important; }
    div[data-testid="stMetricLabel"] p { font-size: 11px !important; }
    div[data-testid="stSelectbox"], div[data-testid="stMultiSelect"], div[data-testid="stTextInput"] { min-width: 0 !important; }
    [data-testid="stSidebar"] { min-width: 260px !important; }
}
@media only screen and (max-width: 480px) {
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
    [data-testid="stHorizontalBlock"] > [data-testid="column"] {
        min-width: 100% !important; flex: 1 1 100% !important;
    }
    h3 { font-size: 16px !important; }
    h5 { font-size: 14px !important; }
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------
# Initialize session state (CORRECT ORDER)
# ---------------------------------------------------
if 'data_timestamp' not in st.session_state:
    st.session_state.data_timestamp = datetime.now()
if 'auto_refresh' not in st.session_state:
    st.session_state.auto_refresh = False
if 'recommendations' not in st.session_state:
    st.session_state.recommendations = {}
if 'heatmap_page' not in st.session_state:
    st.session_state.heatmap_page = 1
if 'soh_heatmap_page' not in st.session_state:
    st.session_state.soh_heatmap_page = 1
if 'google_sheets_data' not in st.session_state:
    st.session_state.google_sheets_data = None
if 'branch_amc_data' not in st.session_state:
    st.session_state.branch_amc_data = None

# FIRST: Initialize supabase client
if 'supabase_client' not in st.session_state:
    st.session_state.supabase_client = init_supabase()

if 'lead_time_data' not in st.session_state:
    st.session_state.temp_requested_dates = {}

# SECOND: Load DOS tracking from Supabase (now client exists)
if 'dos_tracking' not in st.session_state:
    st.session_state.dos_tracking = load_dos_tracking_from_supabase()

# Continue with other session state variables
if 'branch_data' not in st.session_state:
    st.session_state.branch_data = None
if 'search_query' not in st.session_state:
    st.session_state.search_query = ""
if 'last_sheet_name' not in st.session_state:
    st.session_state.last_sheet_name = ""
if 'saved_recommendations' not in st.session_state:
    st.session_state.saved_recommendations = {}
if 'view_mode' not in st.session_state:
    st.session_state.view_mode = "table"
if 'risk_type_filter' not in st.session_state:
    st.session_state.risk_type_filter = ["All"] 
if 'subcategory_filter' not in st.session_state:
    st.session_state.subcategory_filter = "All"
if 'previous_nsoh_data' not in st.session_state:
    st.session_state.previous_nsoh_data = None
if 'nsoh_changes' not in st.session_state:
    st.session_state.nsoh_changes = None
if 'raw_previous_data' not in st.session_state:
    st.session_state.raw_previous_data = None
if 'material_views' not in st.session_state:
    st.session_state.material_views = {}
if 'user_activity' not in st.session_state:
    st.session_state.user_activity = []
if 'notifications' not in st.session_state:
    st.session_state.notifications = []
if 'previous_data_hash' not in st.session_state:
    st.session_state.previous_data_hash = None
if 'action_plan_tab' not in st.session_state:
    st.session_state.action_plan_tab = "📋 All Issues"
if 'last_dashboard_tab' not in st.session_state:
    st.session_state.last_dashboard_tab = None
if 'last_analytics_tab' not in st.session_state:
    st.session_state.last_analytics_tab = None
if 'last_summary_section' not in st.session_state:
    st.session_state.last_summary_section = None
if 'requested_dates' not in st.session_state:
    st.session_state.requested_dates = load_all_requested_dates()
if 'selected_programs' not in st.session_state:
    st.session_state.selected_programs = ["All"]

# Check connection periodically
if st.session_state.supabase_client and not check_supabase_connection():
    st.warning("⚠️ Supabase connection lost. Attempting to reconnect...")
    st.session_state.supabase_client = init_supabase()

# ---------------------------------------------------
# ---------------------------------------------------
# Program Hierarchy Configuration
# ---------------------------------------------------
PROGRAM_HIERARCHY = {
    "OI and Hepatitis": {
        "subcategories": ["AHD", "Hepatitis", "OI", "STI"],
        "is_parent": True
    },
    "TB": {
        "subcategories": ["Drug Susceptible -TB Medicine (DS-TB)", "Drug Resisitance -TB Medicine (DR-TB)", "Leprosy Medicines", "Nutrition"],
        "is_parent": True
    },
    "Lab TB": {
        "subcategories": ["TB diagnostics& Laboratory reagent", "TB Lab Supplies"],
        "is_parent": True
    },
    "HIV Lab": {
        "subcategories": ["HIV VL Reagents", "CD4 ,AHD &HIV RTKs"],
        "is_parent": True
    }
}

# ---------------------------------------------------
# Function to assign subcategories based on sequential order
# ---------------------------------------------------
def assign_subcategories_to_materials(df, subcategory_list):
    """Assign subcategory to each material based on sequential order in Material Description column"""
    subcategory_mapping = {}
    current_subcategory = None

    for idx in range(len(df)):
        material_desc = str(df.iloc[idx]['Material Description']).strip()

        # Check if this row is a subcategory header
        is_subcategory = False
        for subcat in subcategory_list:
            if material_desc == subcat:
                current_subcategory = subcat
                is_subcategory = True
                break

        # If not a subcategory header and we have a current subcategory, assign it
        if not is_subcategory and current_subcategory is not None:
            subcategory_mapping[material_desc] = current_subcategory

    return subcategory_mapping

def is_subcategory_header(material_desc, subcategory_list):
    """Check if a material description is actually a subcategory header"""
    return material_desc.strip() in subcategory_list

def filter_out_subcategory_headers(df, subcategory_list):
    """Remove subcategory header rows from the dataframe"""
    if subcategory_list is None or not subcategory_list:
        return df

    mask = ~df['Material Description'].astype(str).str.strip().isin(subcategory_list)
    return df[mask].copy()

# ---------------------------------------------------
# Expiry Risk Calculation Function
# ---------------------------------------------------
def parse_multiple_expiry_batches(expiry_str, amc):
    """Parse multiple batches and determine expiry risk"""
    try:
        if pd.isna(expiry_str) or expiry_str == "" or expiry_str is None:
            return False, ""

        expiry_str = str(expiry_str)
        pattern = r'(\d[\d,]*)\s*\(([A-Za-z]+)-(\d{4})\)'
        matches = re.findall(pattern, expiry_str)

        if not matches:
            return False, ""

        batches = []
        month_map = {'Jan':1, 'Feb':2, 'Mar':3, 'Apr':4, 'May':5, 'Jun':6,
                    'Jul':7, 'Aug':8, 'Sep':9, 'Oct':10, 'Nov':11, 'Dec':12}

        for quantity_str, month, year in matches:
            quantity = float(quantity_str.replace(',', ''))
            month_num = month_map.get(month[:3], 1)
            expiry_date = datetime(int(year), month_num, 1)
            batches.append({'quantity': quantity, 'expiry_date': expiry_date})

        batches.sort(key=lambda x: x['expiry_date'])

        if pd.isna(amc) or amc <= 0:
            return False, ""

        cumulative_stock = 0
        has_risk = False
        risk_details = []

        for batch in batches:
            months_until_expiry = max(0, (batch['expiry_date'].year - datetime.now().year) * 12 + 
                                      (batch['expiry_date'].month - datetime.now().month))
            cumulative_stock += batch['quantity']
            stock_needed = amc * months_until_expiry

            if cumulative_stock > stock_needed:
                excess = cumulative_stock - stock_needed
                batch_risk = min(batch['quantity'], excess)
                if batch_risk > 0:
                    has_risk = True
                    risk_details.append(f"{batch_risk:,.0f} units expiring {batch['expiry_date'].strftime('%b-%Y')}")

        return has_risk, "; ".join(risk_details) if risk_details else ""
    except Exception as e:
        return False, f"Error: {e}"

# ---------------------------------------------------
# Database Connection Functions
# ---------------------------------------------------
def load_national_data():
    """Load ALL national_data from Supabase with pagination"""
    try:
        if st.session_state.supabase_client is None:
            st.error("Supabase client not initialized")
            return pd.DataFrame()

        all_data = []
        page = 0
        page_size = 1000

        while True:
            response = st.session_state.supabase_client.table("health_data") \
                .select("*") \
                .range(page * page_size, (page + 1) * page_size - 1) \
                .execute()

            if not response.data:
                break

            all_data.extend(response.data)

            if len(response.data) < page_size:
                break

            page += 1

        if not all_data:
            st.warning("No data found in Supabase")
            return pd.DataFrame()

        df = pd.DataFrame(all_data)

        if 'id' in df.columns:
            df = df.drop(columns=['id'])

        column_mapping = {
            'material_description': 'Material Description',
            'adama_branch': 'Adama Branch',
            'addis_ababa_branch_1': 'Addis Ababa Branch 1',
            'addis_ababa_branch_2': 'Addis Ababa Branch 2',
            'arba_minch_branch': 'Arba Minch Branch',
            'assosa_branch': 'Assosa Branch',
            'bahir_dar_branch': 'Bahir Dar Branch',
            'dessie_branch': 'Dessie Branch',
            'dire_dawa_branch': 'Dire Dawa Branch',
            'gambela_branch': 'Gambela Branch',
            'gondar_branch': 'Gondar Branch',
            'hawassa_branch': 'Hawassa Branch',
            'jigjiga_branch': 'Jigjiga Branch',
            'jimma_branch': 'Jimma Branch',
            'kebridahar_branch': 'Kebridahar Branch',
            'mekele_branch': 'Mekele Branch',
            'negele_borena_branch': 'Negele Borena Branch',
            'nekemte_branch': 'Nekemte Branch',
            'semera_branch': 'Semera Branch',
            'shire_branch': 'Shire Branch',
            'head_office': 'Head Office',
            'hubs': 'Hubs',
            'nsoh': 'NSOH',
            'expiry': 'Expiry'
        }

        existing_mapping = {k: v for k, v in column_mapping.items() if k in df.columns}
        df = df.rename(columns=existing_mapping)

        df = df.loc[:, ~df.columns.str.contains("^Unnamed")]
        df.columns = df.columns.str.strip()

        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].fillna("")

        return df

    except Exception as e:
        st.error(f"Error loading data from Supabase: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def load_new_deliveries():
    """Load ALL new_deliveries data from Supabase with pagination"""

    try:
        if st.session_state.supabase_client is None:
            return pd.DataFrame()

        all_data = []
        page = 0
        page_size = 1000

        while True:

            response = (
                st.session_state.supabase_client
                .table("new_deliveries")
                .select("*")
                .range(page * page_size, (page + 1) * page_size - 1)
                .execute()
            )

            if not response.data:
                break

            all_data.extend(response.data)

            # Stop when last page reached
            if len(response.data) < page_size:
                break

            page += 1

        if not all_data:
            return pd.DataFrame()

        df = pd.DataFrame(all_data)

        # Remove id column
        if 'id' in df.columns:
            df = df.drop(columns=['id'])

        # Convert purchase_order to string
        if 'purchase_order' in df.columns:
            df['purchase_order'] = df['purchase_order'].astype(str)

        # Rename columns
        df = df.rename(columns={
            'material_description': 'Material Description',
            'posting_date': 'Posting Date',
            'purchase_order': 'PO Number',
            'quantity': 'Quantity'
        })

        # Convert date
        if 'Posting Date' in df.columns:
            df['Posting Date'] = pd.to_datetime(
                df['Posting Date'],
                errors='coerce'
            )

        # Convert quantity
        if 'Quantity' in df.columns:
            df['Quantity'] = pd.to_numeric(
                df['Quantity'],
                errors='coerce'
            )


        return df

    except Exception as e:
        st.error(f"Error loading New_deliveries data: {e}")
        return pd.DataFrame()

# ---------------------------------------------------
# Google Sheets loaders: retry, never cache a failure, fall back to the last good copy
# ---------------------------------------------------
@st.cache_resource
def _last_good_store():
    """Survives reruns and is shared by all sessions: last successfully loaded sheets + retry timers."""
    return {}


def _download_sheet_xlsx(sheet_id, attempts=2):
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
    last_error = None
    for i in range(attempts):
        try:
            session = requests.Session()
            session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
            session.trust_env = False
            response = session.get(url, timeout=(15, 90))      # (connect, read) seconds
            response.raise_for_status()
            return response.content
        except Exception as e:
            last_error = e
            if i < attempts - 1:
                time.sleep(2)
    raise last_error


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_branch_amc(sheet_id):
    """Raises on failure, so a failed download is never cached."""
    df = pd.read_excel(BytesIO(_download_sheet_xlsx(sheet_id)), header=0)
    df = df.loc[:, ~df.columns.str.contains("^Unnamed")]
    df.columns = df.columns.str.strip()
    for col in df.columns:
        if df[col].dtype == 'object':
            df[col] = df[col].fillna("")
    for col in df.columns:
        if df[col].dtype == 'object':
            df[col] = df[col].astype(str).str.replace(',', '', regex=False)
    return df


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_google_sheets(sheet_id):
    """Raises on failure, so a failed download is never cached."""
    sheets = pd.read_excel(BytesIO(_download_sheet_xlsx(sheet_id)), sheet_name=None, header=2)
    cleaned_sheets = {}
    for name, df in sheets.items():
        if df.empty:
            cleaned_sheets[name] = df
            continue
        df = df.loc[:, ~df.columns.str.contains("^Unnamed")]
        df.columns = df.columns.str.strip()
        for col in df.columns:
            try:
                if col in df.columns and len(df) > 0 and (pd.api.types.is_object_dtype(df[col]) or df[col].dtype == 'object'):
                    df[col] = df[col].fillna("")
            except Exception:
                continue
        cleaned_sheets[name] = df
    return cleaned_sheets


def _load_with_fallback(key, fetch_fn, sheet_id, session_attr, empty_value, label):
    store = _last_good_store()
    now = time.time()
    fallback = store.get(key)
    if fallback is None:
        fallback = st.session_state.get(session_attr)
    # After a failure, don't hammer Google on every click: reuse the last good copy for a minute
    if fallback is not None and now < store.get(key + "_retry_at", 0):
        st.warning(f"Showing the last loaded {label}. Google Sheets could not be reached a moment ago; retrying shortly.")
        return fallback
    try:
        data = fetch_fn(sheet_id)
        store[key] = data
        store[key + "_retry_at"] = 0
        st.session_state[session_attr] = data
        return data
    except Exception as e:
        store[key + "_retry_at"] = now + 60
        reason = f"{type(e).__name__}: {str(e)[:120]}"
        if fallback is not None:
            st.warning(f"Showing the last loaded {label}. Google Sheets could not be reached just now ({reason}).")
            return fallback
        st.error(f"Could not load {label} from Google Sheets ({reason}). "
                 f"Check the internet connection of the server running the dashboard, then refresh.")
        return empty_value


def load_branch_amc_from_google_sheets(sheet_id):
    """Load branch AMC data from Google Sheets"""
    return _load_with_fallback("branch_amc", _fetch_branch_amc, sheet_id, "branch_amc_data",
                               pd.DataFrame(columns=['Material Description']), "branch AMC data")


def load_google_sheets(sheet_id):
    """Load Google Sheets data (AMC and pipeline data)"""
    return _load_with_fallback("google_sheets", _fetch_google_sheets, sheet_id, "google_sheets_data",
                               {}, "program (AMC and pipeline) data")


def validate_upload_data(df):
    """Validate data before uploading to Supabase"""
    required_columns = ['Material Description', 'NSOH']
    missing_columns = [col for col in required_columns if col not in df.columns]

    if missing_columns:
        st.error(f"Missing required columns: {', '.join(missing_columns)}")
        return False

    if df['Material Description'].duplicated().any():
        st.warning("Duplicate Material Descriptions found. Only first occurrence will be kept.")
        df = df.drop_duplicates(subset=['Material Description'], keep='first')

    return True

# Load Issue Data from Supabase (Optimized for large datasets)
# ---------------------------------------------------
@st.cache_data(ttl=600, show_spinner=False)  # Cache for 10 minutes
def load_issue_data():
    """Load issue data from Supabase with pagination and caching for large datasets"""
    try:
        if st.session_state.supabase_client is None:
            return pd.DataFrame()

        # Use pagination to load all data efficiently
        all_data = []
        page = 0
        page_size = 10000  # Larger page size for better performance

        with st.spinner("Loading issue data..."):
            while True:
                response = (
                    st.session_state.supabase_client
                    .table("issue_data")
                    .select("material_descr, plant, region_descr, quantity,id")
                    .range(page * page_size, (page + 1) * page_size - 1)
                    .execute()
                )

                if not response.data:
                    break

                all_data.extend(response.data)

                # Stop when last page reached
                if len(response.data) < page_size:
                    break

                page += 1

        if not all_data:
            return pd.DataFrame()

        df = pd.DataFrame(all_data)

        # Rename columns for consistency
        df = df.rename(columns={
            'material_descr': 'Material Description',
            'plant': 'Plant',
            'region_descr': 'Region',
            'quantity': 'Quantity',
            'id':'ID'
        })

        # Convert quantity to numeric
        if 'Quantity' in df.columns:
            df['Quantity'] = pd.to_numeric(df['Quantity'], errors='coerce').fillna(0)

        return df

    except Exception as e:
        st.error(f"Error loading issue data: {e}")
        return pd.DataFrame()


# ---------------------------------------------------
# Create Aggregated Views for Issue Data (Performance Optimization)
# ---------------------------------------------------
@st.cache_data(ttl=600, show_spinner=False)
def get_issue_aggregated_by_plant(df):
    """Aggregate issue data by Plant for heatmap"""
    if df.empty:
        return pd.DataFrame()

    # Pivot to get Plant (Y-axis) x Material Description (X-axis)
    pivot_df = df.groupby(['Plant', 'Material Description'])['Quantity'].sum().reset_index()
    pivot_table = pivot_df.pivot_table(
        index='Plant', 
        columns='Material Description', 
        values='Quantity',
        fill_value=0
    )
    return pivot_table


@st.cache_data(ttl=600, show_spinner=False)
def get_issue_aggregated_by_region(df):
    """Aggregate issue data by Region for heatmap"""
    if df.empty:
        return pd.DataFrame()

    # Pivot to get Region (Y-axis) x Material Description (X-axis)
    pivot_df = df.groupby(['Region', 'Material Description'])['Quantity'].sum().reset_index()
    pivot_table = pivot_df.pivot_table(
        index='Region', 
        columns='Material Description', 
        values='Quantity',
        fill_value=0
    )
    return pivot_table
# ---------------------------------------------------
# Admin Functions for Supabase
# ---------------------------------------------------
def upload_to_supabase(df, table_name="health_data"):
    """Upload DataFrame to Supabase"""
    try:
        if st.session_state.supabase_client is None:
            st.error("Supabase client not initialized")
            return False

        reverse_mapping = {
            'Material Description': 'material_description',
            'Adama Branch': 'adama_branch',
            'Addis Ababa Branch 1': 'addis_ababa_branch_1',
            'Addis Ababa Branch 2': 'addis_ababa_branch_2',
            'Arba Minch Branch': 'arba_minch_branch',
            'Assosa Branch': 'assosa_branch',
            'Bahir Dar Branch': 'bahir_dar_branch',
            'Dessie Branch': 'dessie_branch',
            'Dire Dawa Branch': 'dire_dawa_branch',
            'Gambela Branch': 'gambela_branch',
            'Gondar Branch': 'gondar_branch',
            'Hawassa Branch': 'hawassa_branch',
            'Jigjiga Branch': 'jigjiga_branch',
            'Jimma Branch': 'jimma_branch',
            'Kebridahar Branch': 'kebridahar_branch',
            'Mekele Branch': 'mekele_branch',
            'Negele Borena Branch': 'negele_borena_branch',
            'Nekemte Branch': 'nekemte_branch',
            'Semera Branch': 'semera_branch',
            'Shire Branch': 'shire_branch',
            'Head Office': 'head_office',
            'Hubs': 'hubs',
            'NSOH': 'nsoh',
            'Expiry': 'expiry'
        }

        upload_columns = [col for col in reverse_mapping.keys() if col in df.columns]
        df_upload = df[upload_columns].copy()
        df_upload = df_upload.rename(columns=reverse_mapping)
        df_upload = df_upload.replace({np.nan: None})
        data = df_upload.to_dict(orient="records")

        response = st.session_state.supabase_client.table(table_name).insert(data).execute()

        st.success(f"Successfully uploaded {len(data)} records to Supabase!")
        return True
    except Exception as e:
        st.error(f"Error uploading to Supabase: {e}")
        return False

def clear_supabase_table(table_name="health_data"):
    """Clear all data from Supabase table"""
    try:
        if st.session_state.supabase_client is None:
            st.error("Supabase client not initialized")
            return False

        response = st.session_state.supabase_client.table(table_name).delete().neq("id", 0).execute()

        st.success(f"Successfully cleared table {table_name}!")
        return True
    except Exception as e:
        st.error(f"Error clearing table: {e}")
        return False

def get_table_info():
    """Get information about the Supabase table"""
    try:
        if st.session_state.supabase_client is None:
            return None

        response = st.session_state.supabase_client.table("health_data").select("*").execute()

        if response.data:
            df = pd.DataFrame(response.data)
            return {"rows": len(df), "columns": len(df.columns), "column_names": list(df.columns)}
        return None
    except Exception as e:
        st.error(f"Error getting table info: {e}")
        return None

# ===================================================
# DATA UPLOAD: Health Program SOH + Posting Date  ->  Supabase
# ---------------------------------------------------
# Users upload the raw SAP exports (Materials.xlsx / Posting.xlsx).
# Each file is checked and processed IN MEMORY first (same rules as the
# Health_Program_SOH_-Final and Posting_Date notebooks). Only a file that
# passes every check can be saved. A wrong / incomplete file only produces an
# error message on the upload page - the dashboard data is never touched.
# ===================================================
MAPPING_SHEET_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/12Z5xqX32QIzjoN6tNvGbjutMheXx5US1/export?format=csv&gid=593796364"
)

# Who may upload. None = every logged-in user. To restrict, e.g.: ("admin",)
UPLOAD_ALLOWED_ROLES = None

SOH_STOCK_COLUMNS = [
    'Unrestricted Stock', 'Stock in Quality Inspection', 'Blocked Stock', 'Stock in Transit'
]
SOH_REQUIRED_COLUMNS = [
    'Special Stock Type Description', 'Material Description', 'Storage Location',
    'Plant Name', 'Shelf Life Expiration Date'
] + SOH_STOCK_COLUMNS
SOH_EXCLUDED_STORAGE_LOCATIONS = ['DPWM', 'JPWM', 'APWM', 'BPWM', 'HPWM', 'MPWM', 'NPWM', 'JJPW']
SOH_BRANCHES = [
    'Adama Branch', 'Addis Ababa Branch 1', 'Addis Ababa Branch 2', 'Arba Minch Branch',
    'Assosa Branch', 'Bahir Dar Branch', 'Dessie Branch', 'Dire Dawa Branch', 'Gambela Branch',
    'Gondar Branch', 'Hawassa Branch', 'Jigjiga Branch', 'Jimma Branch', 'Kebridahar Branch',
    'Mekele Branch', 'Negele Borena Branch', 'Nekemte Branch', 'Semera Branch', 'Shire Branch'
]
SOH_EXPECTED_PLANTS = SOH_BRANCHES + ['Head Office']

POSTING_REQUIRED_COLUMNS = [
    'Valuation Type', 'Material Description', 'Purchase order', 'Posting Date', 'Quantity'
]

# Items export (Issue Data): Items.xlsx -> issue_data
ISSUE_REQUIRED_COLUMNS = [
    'Plant', 'Material Descr', 'Quantity', 'Net Value', 'Delivery Date', 'Region Descr'
]


class UploadValidationError(Exception):
    """Raised when an uploaded file is wrong / incomplete. Carries a list of readable problems."""
    def __init__(self, problems):
        if isinstance(problems, str):
            problems = [problems]
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


def _can_upload_data():
    user = st.session_state.get('user') or {}
    if UPLOAD_ALLOWED_ROLES is None:
        return bool(user)
    return user.get('role') in UPLOAD_ALLOWED_ROLES


# ---------- generic helpers (pure functions - no Streamlit calls) ----------
def _norm_header(c):
    return re.sub(r"\s+", " ", str(c)).strip().lower()


def _row_list(index_values, limit=8):
    """'rows 5, 9, 12 (and 3 more)' - the index is the 0-based pandas index, row 1 of the sheet is the header."""
    nums = [int(i) + 2 for i in list(index_values)]
    shown = ", ".join(str(n) for n in nums[:limit])
    more = f" (and {len(nums) - limit} more)" if len(nums) > limit else ""
    return f"row{'s' if len(nums) > 1 else ''} {shown}{more}"


def _read_uploaded_table(uploaded_file):
    """Read the first sheet of an .xlsx/.xlsm file or a .csv file into a DataFrame."""
    name = (getattr(uploaded_file, "name", "") or "").lower()
    if not name.endswith((".xlsx", ".xlsm", ".csv")):
        raise UploadValidationError("Unsupported file type. Please upload an Excel (.xlsx) or CSV (.csv) file.")
    try:
        uploaded_file.seek(0)
        if name.endswith(".csv"):
            try:
                df = pd.read_csv(uploaded_file)
            except UnicodeDecodeError:
                uploaded_file.seek(0)
                df = pd.read_csv(uploaded_file, encoding="latin-1")
        else:
            df = pd.read_excel(uploaded_file, engine="openpyxl")
    except Exception as e:
        raise UploadValidationError(
            f"The file could not be opened ({type(e).__name__}). Make sure it is a valid, "
            f"un-protected Excel/CSV file exported from SAP."
        )
    if df.empty:
        raise UploadValidationError("The file is empty - no data rows were found.")
    return df


def _standardise_headers(df):
    """Trim / case-fold headers so 'plant name ' still matches 'Plant Name'."""
    canon = {_norm_header(c): c for c in SOH_REQUIRED_COLUMNS + POSTING_REQUIRED_COLUMNS + ISSUE_REQUIRED_COLUMNS}
    df = df.rename(columns={c: canon[_norm_header(c)] for c in df.columns if _norm_header(c) in canon})
    return df.loc[:, ~df.columns.duplicated()]


def _require_columns(df, required, this_label, other_required, other_label):
    missing = [c for c in required if c not in df.columns]
    if not missing:
        return
    problems = []
    if all(c in df.columns for c in other_required):
        problems.append(
            f"This looks like a **{other_label}** file, not a **{this_label}** file. "
            f"Please upload it in the {other_label} tab instead."
        )
    problems.append(
        f"The file is not a valid {this_label} file. Missing required column(s): "
        + ", ".join(f"**{c}**" for c in missing) + "."
    )
    raise UploadValidationError(problems)


def _blank_mask(series):
    return series.isna() | series.astype(str).str.strip().isin(["", "nan", "None", "NaT"])


def _to_number(series):
    """Numeric cleaning identical to the notebook. Returns (values, mask of non-blank cells that are not numbers)."""
    if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
        return pd.to_numeric(series, errors='coerce').fillna(0.0).astype(float), pd.Series(False, index=series.index)
    s = series.astype(str).str.replace(',', '', regex=False)
    s = s.str.replace(r'[^\d\.\-]', '', regex=True)
    num = pd.to_numeric(s, errors='coerce')
    bad = num.isna() & ~_blank_mask(series)
    return num.fillna(0.0).astype(float), bad


def _mapping_table(mapping_df, need_factor):
    needed = ['Original', 'Mapped'] + (['Conversion Factor'] if need_factor else [])
    missing = [c for c in needed if mapping_df is None or c not in mapping_df.columns]
    if missing:
        raise UploadValidationError(
            "The material mapping Google Sheet is missing column(s): " + ", ".join(missing)
            + ". Nothing was saved - please contact the administrator."
        )
    m = mapping_df.dropna(subset=['Original', 'Mapped']).drop_duplicates(subset='Original', keep='last')
    return m


def _clean_records(df, whole_number_columns=()):
    """DataFrame -> list of JSON-safe dicts (no NaN / inf / numpy types)."""
    out = []
    for rec in df.to_dict(orient="records"):
        row = {}
        for k, v in rec.items():
            if isinstance(v, (np.integer,)):
                v = int(v)
            elif isinstance(v, (float, np.floating)):
                if pd.isna(v) or np.isinf(v):
                    v = None
                elif k in whole_number_columns and float(v).is_integer():
                    v = int(v)
                else:
                    v = float(v)
            elif v is pd.NaT or (not isinstance(v, str) and v is not None and pd.isna(v)):
                v = None
            row[k] = v
        out.append(row)
    return out


# ---------- 1) Health Program SOH ----------
def process_soh_upload(raw, mapping_df):
    """Port of Health_Program_SOH_-Final.ipynb. Returns dict(records, preview, warnings, summary)
    or raises UploadValidationError."""
    warnings, problems = [], []
    mapping = _mapping_table(mapping_df, need_factor=True)

    df = raw.dropna(how="all").copy()
    rows_read = len(df)

    # Only project stock
    stock_type = df['Special Stock Type Description'].astype(str).str.strip()
    df = df[stock_type == 'Project Stock'].copy()
    if df.empty:
        found = raw['Special Stock Type Description'].dropna().astype(str).str.strip().unique()[:5]
        raise UploadValidationError([
            "No rows with Special Stock Type Description = 'Project Stock' were found, so there is nothing to load.",
            "Values found in that column: " + (", ".join(f"'{v}'" for v in found) if len(found) else "(all empty)")
            + ". Please check that you exported the correct report."
        ])

    # Missing data elements
    miss = _blank_mask(df['Material Description'])
    if miss.any():
        problems.append(f"**Material Description** is empty in {int(miss.sum())} row(s) ({_row_list(df.index[miss])}).")
    miss = _blank_mask(df['Plant Name'])
    if miss.any():
        problems.append(f"**Plant Name** is empty in {int(miss.sum())} row(s) ({_row_list(df.index[miss])}).")

    for col in SOH_STOCK_COLUMNS:
        values, bad = _to_number(df[col])
        if bad.any():
            problems.append(
                f"**{col}** contains non-numeric values in {int(bad.sum())} row(s) ({_row_list(df.index[bad])})."
            )
        df[col] = values

    plants = df['Plant Name'].astype(str).str.strip()
    df['Plant Name'] = plants
    present = set(plants[~_blank_mask(df['Plant Name'])])
    unknown = sorted(present - set(SOH_EXPECTED_PLANTS))
    if unknown:
        problems.append(
            "Unrecognised **Plant Name** value(s): " + ", ".join(f"'{p}'" for p in unknown[:10])
            + ". This is either the wrong file or a new branch that must be added to the dashboard first."
        )
    elif len(present & set(SOH_EXPECTED_PLANTS)) < len(SOH_EXPECTED_PLANTS) / 2:
        problems.append(
            f"Only {len(present & set(SOH_EXPECTED_PLANTS))} of the {len(SOH_EXPECTED_PLANTS)} expected plants "
            f"are in this file - it does not look like the national stock-on-hand export."
        )

    if problems:
        raise UploadValidationError(problems)

    missing_plants = [p for p in SOH_EXPECTED_PLANTS if p not in present]
    if missing_plants:
        warnings.append(
            "No project stock rows for: " + ", ".join(missing_plants) + " - their stock is recorded as 0."
        )

    # Material mapping: conversion factors (applied to ORIGINAL names) then rename
    df['Material Description'] = df['Material Description'].astype(str)
    factor_map = dict(zip(mapping['Original'], pd.to_numeric(mapping['Conversion Factor'], errors='coerce')))
    factors = df['Material Description'].map(factor_map)
    factors = factors.where(factors.notna(), 1.0).astype(float)
    df[SOH_STOCK_COLUMNS] = df[SOH_STOCK_COLUMNS].mul(factors, axis=0)
    rename_map = dict(zip(mapping['Original'], mapping['Mapped'].astype(str)))
    df['Material Description'] = df['Material Description'].map(lambda x: rename_map.get(x, x))

    # Drop excluded storage locations
    df = df[~df['Storage Location'].isin(SOH_EXCLUDED_STORAGE_LOCATIONS)].copy()
    if df.empty:
        raise UploadValidationError("After removing the excluded storage locations no stock rows remain.")

    df['Plant_SOH'] = df['Unrestricted Stock'] + df['Stock in Quality Inspection'] + df['Stock in Transit']

    # Expiry text: "qty(Mon-YYYY), qty(Mon-YYYY)" per material (blocked stock excluded, as in the notebook)
    shelf = df[df['Plant_SOH'] != 0].copy()
    shelf['_expiry'] = pd.to_datetime(shelf['Shelf Life Expiration Date'], errors='coerce')
    non_blank = ~_blank_mask(shelf['Shelf Life Expiration Date'])
    unparsed = non_blank & shelf['_expiry'].isna()
    if non_blank.any() and int((non_blank & shelf['_expiry'].notna()).sum()) == 0:
        raise UploadValidationError(
            "None of the values in **Shelf Life Expiration Date** could be read as dates. "
            "Please check the column in the file."
        )
    if unparsed.any():
        warnings.append(
            f"{int(unparsed.sum())} stock row(s) have an unreadable Shelf Life Expiration Date and were left out "
            f"of the expiry column ({_row_list(shelf.index[unparsed], 5)})."
        )
    shelf = shelf.dropna(subset=['_expiry'])
    shelf['_month'] = shelf['_expiry'].dt.to_period('M')
    by_month = (
        shelf.groupby(['Material Description', '_month'], as_index=False)['Plant_SOH'].sum()
        .sort_values(['Material Description', '_month'])
    )
    by_month['_txt'] = [
        f"{int(round(q))}({p.strftime('%b-%Y')})" for q, p in zip(by_month['Plant_SOH'], by_month['_month'])
    ]
    expiry = by_month.groupby('Material Description')['_txt'].apply(lambda x: ', '.join(x)).rename('Expiry')

    # Plant pivot -> Hubs / NSOH
    pivot = pd.pivot_table(df, values='Plant_SOH', index='Material Description',
                           columns='Plant Name', aggfunc='sum', fill_value=0)
    for p in SOH_EXPECTED_PLANTS:
        if p not in pivot.columns:
            pivot[p] = 0.0
    pivot = pivot[SOH_EXPECTED_PLANTS].astype(float)
    pivot['NSOH'] = pivot.sum(axis=1)
    pivot['Hubs'] = pivot.drop(columns=['Head Office', 'NSOH']).sum(axis=1)

    final = pivot[SOH_EXPECTED_PLANTS + ['Hubs', 'NSOH']].join(expiry, how='left')
    final['Expiry'] = final['Expiry'].fillna("")
    final = final.reset_index().rename(columns={'index': 'Material Description'})
    final = final[['Material Description'] + SOH_EXPECTED_PLANTS + ['Hubs', 'NSOH', 'Expiry']]

    db = final.copy()
    db.columns = [c.strip().lower().replace(" ", "_") for c in db.columns]
    records = _clean_records(db)

    summary = {
        "Rows read": f"{rows_read:,}",
        "Materials": f"{len(final):,}",
        "Total NSOH": f"{final['NSOH'].sum():,.0f}",
        "Materials with expiry info": f"{int((final['Expiry'] != '').sum()):,}",
    }
    return {"records": records, "preview": final, "warnings": warnings, "summary": summary}


# ---------- 2) Posting Date ----------
def process_posting_upload(raw, mapping_df):
    """Port of Posting_Date.ipynb. Returns dict(records, preview, warnings, summary)
    or raises UploadValidationError."""
    warnings, problems = [], []
    mapping = _mapping_table(mapping_df, need_factor=False)

    df = raw.dropna(how="all").copy()
    rows_read = len(df)

    # Exclusions from the notebook
    df = df[~df['Valuation Type'].astype('string').str.contains('ZMS|ZMD', na=False)]
    df = df[~df['Purchase order'].astype(str).str.startswith("60")].copy()
    if df.empty:
        raise UploadValidationError("No rows are left after removing ZMS/ZMD valuation types and POs starting with 60.")

    # Missing data elements (checked before the Quantity > 0 filter so nothing disappears silently)
    miss = _blank_mask(df['Material Description'])
    if miss.any():
        problems.append(f"**Material Description** is empty in {int(miss.sum())} row(s) ({_row_list(df.index[miss])}).")

    dates = pd.to_datetime(df['Posting Date'], errors='coerce')
    bad = dates.isna()
    if bad.any():
        problems.append(
            f"**Posting Date** is empty or not a valid date in {int(bad.sum())} row(s) ({_row_list(df.index[bad])})."
        )
    else:
        out_of_range = (dates < pd.Timestamp("2000-01-01")) | (dates > pd.Timestamp.today() + pd.Timedelta(days=366))
        if out_of_range.any():
            problems.append(
                f"**Posting Date** has implausible dates (before 2000 or more than a year ahead) in "
                f"{int(out_of_range.sum())} row(s) ({_row_list(df.index[out_of_range])})."
            )

    qty = pd.to_numeric(df['Quantity'], errors='coerce')
    bad = qty.isna()
    if bad.any():
        problems.append(
            f"**Quantity** is empty or not a number in {int(bad.sum())} row(s) ({_row_list(df.index[bad])})."
        )

    if problems:
        raise UploadValidationError(problems)

    df['Posting Date'] = dates.dt.strftime('%Y-%m-%d')
    df['Quantity'] = qty

    # Material mapping (rename only)
    rename_map = dict(zip(mapping['Original'], mapping['Mapped'].astype(str)))
    df['Material Description'] = df['Material Description'].map(lambda x: rename_map.get(x, x))

    # Purchase order text
    po_blank = _blank_mask(df['Purchase order'])
    po = (df['Purchase order'].astype(str).str.replace(r"\.0$", "", regex=True).str.strip())
    df['Purchase order'] = po.where(~po_blank, "NO_PO")
    if po_blank.any():
        warnings.append(f"{int(po_blank.sum())} row(s) have no Purchase order and are saved as 'NO_PO'.")

    # Quantity > 0 only
    non_positive = int((df['Quantity'] <= 0).sum())
    df = df[df['Quantity'] > 0]
    if non_positive:
        warnings.append(f"{non_positive} row(s) with zero or negative Quantity were skipped.")
    if df.empty:
        raise UploadValidationError("No rows with a Quantity greater than 0 were found.")

    final = (
        df.groupby(['Material Description', 'Purchase order', 'Posting Date'], as_index=False)
        .agg({'Quantity': 'sum'})
    )
    db = final.rename(columns={
        'Material Description': 'material_description', 'Purchase order': 'purchase_order',
        'Posting Date': 'posting_date', 'Quantity': 'quantity'
    })
    records = _clean_records(db, whole_number_columns=('quantity',))

    summary = {
        "Rows read": f"{rows_read:,}",
        "Delivery lines": f"{len(final):,}",
        "Purchase orders": f"{final['Purchase order'].nunique():,}",
        "Materials": f"{final['Material Description'].nunique():,}",
        "Posting dates": f"{final['Posting Date'].min()} to {final['Posting Date'].max()}",
        "Total quantity": f"{final['Quantity'].sum():,.0f}",
    }
    return {"records": records, "preview": final, "warnings": warnings, "summary": summary}


# ---------- 3) Items (Issue Data) ----------
def process_issue_upload(raw, mapping_df):
    """Port of Health_Program_Issue_Data.ipynb. Returns dict(records, preview, warnings, summary)
    or raises UploadValidationError."""
    warnings, problems = [], []
    mapping = _mapping_table(mapping_df, need_factor=True)

    df = raw.dropna(how="all").copy()
    rows_read = len(df)

    # Net Value > 0 only (same as the notebook)
    net, _ = _to_number(df['Net Value'])
    not_issued = int((net <= 0).sum())
    df = df[net > 0].copy()
    if not_issued:
        warnings.append(f"{not_issued:,} row(s) with a Net Value of 0 or less (or empty) were skipped.")
    if df.empty:
        raise UploadValidationError("No rows with a Net Value greater than 0 were found.")

    # Missing / invalid data elements
    for col in ('Material Descr', 'Plant'):
        miss = _blank_mask(df[col])
        if miss.any():
            problems.append(f"**{col}** is empty in {int(miss.sum())} row(s) ({_row_list(df.index[miss])}).")

    dates = pd.to_datetime(df['Delivery Date'], errors='coerce')
    bad = dates.isna()
    if bad.any():
        problems.append(
            f"**Delivery Date** is empty or not a valid date in {int(bad.sum())} row(s) ({_row_list(df.index[bad])})."
        )
    else:
        out_of_range = (dates < pd.Timestamp("2000-01-01")) | (dates > pd.Timestamp.today() + pd.Timedelta(days=366))
        if out_of_range.any():
            problems.append(
                f"**Delivery Date** has implausible dates (before 2000 or more than a year ahead) in "
                f"{int(out_of_range.sum())} row(s) ({_row_list(df.index[out_of_range])})."
            )

    qty, bad_qty = _to_number(df['Quantity'])
    if bad_qty.any():
        problems.append(f"**Quantity** is not a number in {int(bad_qty.sum())} row(s) ({_row_list(df.index[bad_qty])}).")

    if problems:
        raise UploadValidationError(problems)

    df['Delivery Date'] = dates.dt.strftime('%Y-%m-%d')
    df['Quantity'] = qty

    # Conversion factor (by the ORIGINAL name), then rename - same order as the notebook
    factors = pd.to_numeric(mapping.set_index('Original')['Conversion Factor'], errors='coerce')
    df['Quantity'] = df['Quantity'] * df['Material Descr'].map(factors).fillna(1)
    rename_map = dict(zip(mapping['Original'], mapping['Mapped'].astype(str)))
    df['Material Descr'] = df['Material Descr'].map(lambda x: rename_map.get(x, x))

    # Region is needed for the regional views; rows without one cannot be keyed (the notebook dropped them too)
    no_region = _blank_mask(df['Region Descr'])
    if no_region.any():
        warnings.append(f"{int(no_region.sum())} row(s) have no Region Descr and were skipped.")
        df = df[~no_region]
    if df.empty:
        raise UploadValidationError("No rows are left after removing rows without a Region Descr.")

    final = (
        df.groupby(['Material Descr', 'Plant', 'Delivery Date', 'Region Descr'], as_index=False)['Quantity'].sum()
    )
    db = final.rename(columns={
        'Material Descr': 'material_descr', 'Plant': 'plant', 'Delivery Date': 'delivery_date',
        'Region Descr': 'region_descr', 'Quantity': 'quantity'
    })
    records = _clean_records(db)

    summary = {
        "Rows read": f"{rows_read:,}",
        "Issue lines": f"{len(final):,}",
        "Materials": f"{final['Material Descr'].nunique():,}",
        "Plants": f"{final['Plant'].nunique():,}",
        "Delivery dates": f"{final['Delivery Date'].min()} to {final['Delivery Date'].max()}",
        "Total quantity": f"{final['Quantity'].sum():,.0f}",
    }
    return {"records": records, "preview": final, "warnings": warnings, "summary": summary}


# ---------- Saving (only reachable after a file passed validation) ----------
def save_soh_to_supabase(records):
    """Replace health_data with the new records. New rows are inserted FIRST and the old rows are removed
    only after that succeeded, so a failure never leaves the dashboard without data."""
    client = st.session_state.get('supabase_client')
    if client is None:
        raise RuntimeError("Supabase client is not initialised.")

    last = client.table("health_data").select("id").order("id", desc=True).limit(1).execute()
    old_max = last.data[0]["id"] if last.data else 0
    try:
        for i in range(0, len(records), 500):
            client.table("health_data").insert(records[i:i + 500]).execute()
    except Exception:
        try:   # roll back the partial insert; the previous data is still intact
            client.table("health_data").delete().gt("id", old_max).execute()
        except Exception:
            pass
        raise
    if old_max:
        client.table("health_data").delete().lte("id", old_max).execute()
    return len(records)


def save_posting_to_supabase(records):
    """Upsert deliveries (same key as the notebook), so re-uploading the same file never creates duplicates."""
    client = st.session_state.get('supabase_client')
    if client is None:
        raise RuntimeError("Supabase client is not initialised.")
    for i in range(0, len(records), 500):
        client.table("new_deliveries").upsert(
            records[i:i + 500], on_conflict="purchase_order,posting_date,material_description"
        ).execute()
    return len(records)


# ===================================================
# UPDATE LOG - who updated the dashboard, and when
# ---------------------------------------------------
# Every data update (uploads, NSOH snapshots, procurement records, requested dates) is written to the
# Supabase table below. Times are stored in UTC and shown in East Africa Time (UTC+3, no daylight saving).
# ===================================================
UPDATE_LOG_TABLE = "dashboard_update_log"
UPDATE_LOG_ENABLED = False   # update history is switched off for now; set True (and create the table) to bring it back
UPDATE_LOG_SQL = """create table if not exists public.dashboard_update_log (
    id            bigint generated always as identity primary key,
    created_at    timestamptz not null default now(),
    updated_by    text,
    username      text,
    role          text,
    action        text,
    details       text,
    rows_affected integer
);
-- if Row Level Security is on for your other tables, allow this one the same way, for example:
alter table public.dashboard_update_log disable row level security;"""


def _can_view_update_log():
    user = st.session_state.get('user') or {}
    return user.get('role') in UPDATE_LOG_VIEW_ROLES


def log_dashboard_update(action, details="", rows=None):
    """Record who changed what. Never raises: a logging problem must not break the update itself."""
    if not UPDATE_LOG_ENABLED:
        return False
    try:
        client = st.session_state.get('supabase_client')
        user = st.session_state.get('user') or {}
        if client is None or not user:
            return False
        client.table(UPDATE_LOG_TABLE).insert({
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": str(user.get('full_name') or user.get('username') or user.get('email') or 'Unknown'),
            "username": str(user.get('username') or user.get('email') or ''),
            "role": str(user.get('role') or ''),
            "action": str(action)[:120],
            "details": str(details)[:500],
            "rows_affected": int(rows) if rows is not None else None,
        }).execute()
        st.session_state.pop('_update_log_err', None)
        try:
            load_update_log.clear()
        except Exception:
            pass
        return True
    except Exception as e:
        st.session_state['_update_log_err'] = str(e)[:300]
        return False


@st.cache_data(ttl=60, show_spinner=False)
def load_update_log(limit=1000):
    """Returns (DataFrame, error_text). Newest first, with Date and Time (East Africa Time)."""
    cols = ['Date', 'Time (EAT)', 'User', 'Username', 'Role', 'Action', 'Details', 'Records', '_ts']
    try:
        client = st.session_state.get('supabase_client')
        if client is None:
            return pd.DataFrame(columns=cols), "Supabase client is not initialised."
        rows = client.table(UPDATE_LOG_TABLE).select("*").order("created_at", desc=True).limit(limit).execute().data
        if not rows:
            return pd.DataFrame(columns=cols), None
        raw = pd.DataFrame(rows)
        ts = pd.to_datetime(raw['created_at'], utc=True, errors='coerce') + pd.Timedelta(hours=3)
        out = pd.DataFrame({
            'Date': ts.dt.strftime('%d %b %Y'),
            'Time (EAT)': ts.dt.strftime('%H:%M'),
            'User': raw.get('updated_by'),
            'Username': raw.get('username'),
            'Role': raw.get('role'),
            'Action': raw.get('action'),
            'Details': raw.get('details'),
            'Records': raw.get('rows_affected'),
            '_ts': ts.dt.tz_localize(None),
        })
        return out, None
    except Exception as e:
        return pd.DataFrame(columns=cols), str(e)


def _render_update_history():
    """Update history for the Upload Data page: only date & time (East Africa Time) and who updated."""
    st.markdown("#### 🕒 Update history")
    log_df, err = load_update_log()
    if log_df.empty:
        if err:
            if (st.session_state.get('user') or {}).get('role') == 'admin':
                st.error("The update history could not be read. If this is the first time, create the table once "
                         "in the Supabase SQL editor, then refresh this page:")
                st.code(UPDATE_LOG_SQL, language="sql")
                st.caption(f"Details: {err}")
            else:
                st.info("Update history is not available yet. Please ask an admin to set it up.")
        else:
            st.info("No updates have been recorded yet.")
        return
    shown = pd.DataFrame({
        "Date & time (EAT)": log_df['Date'] + "  " + log_df['Time (EAT)'],
        "Updated by": log_df['User'],
    }).head(100)
    st.dataframe(shown, use_container_width=True, hide_index=True, height=min(420, (len(shown) + 1) * 35 + 3))


def save_issue_to_supabase(records):
    """Upsert issue lines (same key as the notebook), so re-uploading the same file never creates duplicates."""
    client = st.session_state.get('supabase_client')
    if client is None:
        raise RuntimeError("Supabase client is not initialised.")
    for i in range(0, len(records), 1000):
        client.table("issue_data").upsert(
            records[i:i + 1000], on_conflict="material_descr,delivery_date,plant,region_descr"
        ).execute()
    return len(records)


# ---------- Upload page ----------
@st.cache_data(ttl=300, show_spinner=False)
def _fetch_mapping_table():
    r = requests.get(MAPPING_SHEET_CSV_URL, timeout=30)
    r.raise_for_status()
    return pd.read_csv(BytesIO(r.content))


UPLOAD_KINDS = {
    "soh": {
        "tab": "📦 Health Program SOH",
        "label": "Stock on Hand",
        "uploader": "Upload the Materials / stock-on-hand export (.xlsx or .csv)",
        "required": SOH_REQUIRED_COLUMNS,
        "other_required": POSTING_REQUIRED_COLUMNS, "other_label": "Posting Date",
        "process": process_soh_upload, "save": save_soh_to_supabase,
        "save_note": "Saving **replaces all current stock-on-hand data** shown on the dashboard.",
        "help": "Special Stock Type Description is filtered to 'Project Stock'; storage locations "
                + ", ".join(SOH_EXCLUDED_STORAGE_LOCATIONS) + " are excluded.",
    },
    "posting": {
        "tab": "🚚 Posting Date",
        "label": "Posting Date",
        "uploader": "Upload the Posting export (.xlsx or .csv)",
        "required": POSTING_REQUIRED_COLUMNS,
        "other_required": SOH_REQUIRED_COLUMNS, "other_label": "Health Program SOH",
        "process": process_posting_upload, "save": save_posting_to_supabase,
        "save_note": "Saving **adds new deliveries and updates matching ones** "
                     "(same PO + posting date + material); nothing else is deleted.",
        "help": "Valuation types ZMS/ZMD and POs starting with 60 are skipped; only quantities above 0 are kept.",
    },
    "issue": {
        "tab": "🧾 Items (Issue Data)",
        "label": "Items (Issue Data)",
        "uploader": "Upload the Items export (.xlsx or .csv)",
        "required": ISSUE_REQUIRED_COLUMNS,
        "other_required": SOH_REQUIRED_COLUMNS, "other_label": "Health Program SOH",
        "process": process_issue_upload, "save": save_issue_to_supabase,
        "save_note": "Saving **adds new issue lines and updates matching ones** "
                     "(same material + plant + region + delivery date); nothing is deleted.",
        "help": "Only rows with a Net Value above 0 are used. Quantities are multiplied by the conversion factor and "
                "materials are renamed using the material mapping Google Sheet, then summed per material, plant, "
                "delivery date and region.",
    },
}


def _check_uploaded_file(kind, uploaded_file):
    """Read + validate + process. Raises UploadValidationError for anything wrong with the file."""
    cfg = UPLOAD_KINDS[kind]
    raw = _standardise_headers(_read_uploaded_table(uploaded_file))
    _require_columns(raw, cfg["required"], cfg["label"], cfg["other_required"], cfg["other_label"])
    try:
        mapping_df = _fetch_mapping_table()
    except Exception as e:
        raise UploadValidationError(
            f"The material mapping Google Sheet could not be loaded ({type(e).__name__}). "
            f"Nothing was saved - please try again in a moment."
        )
    return cfg["process"](raw, mapping_df)


def _render_upload_panel(kind):
    cfg = UPLOAD_KINDS[kind]
    ctr_key, state_key = f"upl_{kind}_ctr", f"upl_{kind}_state"
    st.session_state.setdefault(ctr_key, 0)

    with st.expander("Required columns", expanded=False):
        st.write(", ".join(f"`{c}`" for c in cfg["required"]))
        st.caption(cfg["help"])

    uploaded = st.file_uploader(cfg["uploader"], type=["xlsx", "xlsm", "csv"],
                                key=f"upl_{kind}_file_{st.session_state[ctr_key]}")
    if uploaded is None:
        st.session_state.pop(state_key, None)
        return

    sig = (uploaded.name, uploaded.size)
    state = st.session_state.get(state_key)
    if not state or state.get("sig") != sig:
        with st.spinner("Checking file..."):
            try:
                state = {"sig": sig, "result": _check_uploaded_file(kind, uploaded), "errors": None}
            except UploadValidationError as e:
                state = {"sig": sig, "result": None, "errors": e.problems}
            except Exception as e:   # never let a bad file crash the page
                state = {"sig": sig, "result": None,
                         "errors": [f"The file could not be processed ({type(e).__name__}: {e}). "
                                    f"Please check that it is the correct, unmodified export."]}
        st.session_state[state_key] = state

    if state["errors"]:
        st.error("❌ This file was **not saved**. The dashboard data is unchanged. Please fix the following and upload again:")
        for p in state["errors"]:
            st.markdown(f"- {p}")
        return

    result = state["result"]
    st.success(f"✅ **{uploaded.name}** passed all checks and is ready to save.")
    for w in result["warnings"]:
        st.warning(w)
    cols = st.columns(len(result["summary"]))
    for c, (k, v) in zip(cols, result["summary"].items()):
        c.metric(k, v)
    with st.expander("Preview of the data that will be saved", expanded=False):
        st.dataframe(result["preview"].head(100), hide_index=True)
    st.info(cfg["save_note"])

    if st.button("💾 Confirm and save to Supabase", type="primary", key=f"upl_{kind}_save"):
        with st.spinner("Saving to Supabase..."):
            try:
                n = cfg["save"](result["records"])
            except Exception as e:
                st.error(f"❌ Saving to Supabase failed: {e}. "
                         + ("The previous data is still in place." if kind == "soh"
                            else "You can safely upload the same file again."))
                return
        st.cache_data.clear()
        st.session_state.data_timestamp = datetime.now()
        log_dashboard_update(f"Uploaded {cfg['label']}", uploaded.name, n)
        st.session_state[ctr_key] += 1
        st.session_state.pop(state_key, None)
        st.session_state["upl_flash"] = f"✅ {cfg['label']}: {n:,} records saved to Supabase. The dashboard now shows the new data."
        st.rerun()


def show_upload_data_page():
    st.markdown("<h1 style='font-size: 32px; font-weight: bold; font-family: Times New Roman;' "
                "class='gradient-text'>📤 Upload Data</h1>", unsafe_allow_html=True)
    flash = st.session_state.pop("upl_flash", None)
    if flash:
        st.success(flash)
    st.caption("Files are checked before anything is saved. If a file is wrong or has missing data, "
               "you will see what to fix and the dashboard stays exactly as it is.")

    try:
        stock_rows = st.session_state.supabase_client.table("health_data") \
            .select("id", count="exact").limit(1).execute().count
        deliv = load_new_deliveries()
        c1, c2, c3 = st.columns(3)
        c1.metric("Materials in stock data", f"{stock_rows:,}")
        c2.metric("Delivery lines", f"{len(deliv):,}")
        latest = deliv['Posting Date'].max() if not deliv.empty and 'Posting Date' in deliv.columns else None
        c3.metric("Latest posting date", latest.strftime('%Y-%m-%d') if pd.notna(latest) else "-")
    except Exception:
        pass

    tabs = st.tabs([UPLOAD_KINDS[k]["tab"] for k in UPLOAD_KINDS])
    for tab, kind in zip(tabs, UPLOAD_KINDS):
        with tab:
            _render_upload_panel(kind)

    if UPDATE_LOG_ENABLED:
        if st.session_state.get('_update_log_err'):
            st.warning("⚠️ The last update was saved, but it could not be added to the update history. "
                       "An admin needs to create the update-log table (see Update history below).")
        st.markdown("---")
        _render_update_history()


# ---------------------------------------------------
# calculate_stock_changes FUNCTION
# ---------------------------------------------------
def calculate_stock_changes(current_df, previous_df):
    """Calculate stock quantity changes - uses ONLY NSOH for comparison"""

    if previous_df is None or previous_df.empty:
        return None

    # Get NSOH from both dataframes
    current_data = current_df[['Material Description', 'NSOH']].copy()
    previous_data = previous_df[['Material Description', 'NSOH']].copy()

    # Convert to numeric and round to whole numbers
    for df in [current_data, previous_data]:
        df['NSOH'] = pd.to_numeric(df['NSOH'], errors='coerce').fillna(0)
        df['NSOH'] = df['NSOH'].round(0).astype(int)

    # Merge (use outer join to include all materials from both datasets)
    merged = current_data.merge(
        previous_data, 
        on='Material Description', 
        suffixes=('_now', '_previous'),
        how='outer'
    )

    # Fill NaN values with 0 for materials that only exist in one dataset
    merged['NSOH_now'] = merged['NSOH_now'].fillna(0)
    merged['NSOH_previous'] = merged['NSOH_previous'].fillna(0)

    # Convert to int for proper comparison
    merged['NSOH_now'] = merged['NSOH_now'].astype(int)
    merged['NSOH_previous'] = merged['NSOH_previous'].astype(int)

    # Calculate changes
    merged['NSOH_Change'] = merged['NSOH_now'] - merged['NSOH_previous']

    # Calculate percentage change (avoid division by zero)
    merged['NSOH_Change_Pct'] = np.where(
        merged['NSOH_previous'] > 0,
        (merged['NSOH_Change'] / merged['NSOH_previous']) * 100,
        0
    )

    # Filter out obviously bad data (anomalies like > 1 million change with 0 previous)
    merged = merged[~((merged['NSOH_previous'] == 0) & (abs(merged['NSOH_Change']) > 500000))]

    # Determine change type
    def get_change_type(row):
        if row['NSOH_Change'] > 0:
            return "📦 STOCK ADDED"
        elif row['NSOH_Change'] < 0:
            return "📉 STOCK CONSUMED"
        else:
            return "➖ NO CHANGE"

    merged['Change Type'] = merged.apply(get_change_type, axis=1)

    # Format numbers for display
    merged['NSOH_previous'] = merged['NSOH_previous'].apply(lambda x: f"{x:,}")
    merged['NSOH_now'] = merged['NSOH_now'].apply(lambda x: f"{x:,}")
    merged['NSOH_Change'] = merged['NSOH_Change'].apply(
        lambda x: f"{'+' if x > 0 else ''}{x:,}" if x != 0 else "0"
    )
    merged['NSOH_Change_Pct'] = merged['NSOH_Change_Pct'].apply(
        lambda x: f"{x:+.1f}%" if x != 0 else "0%"
    )

    # Sort by absolute NSOH change (largest first)
    merged['_sort_key'] = merged['NSOH_Change'].str.replace(',', '').str.replace('+', '').astype(int).abs()
    merged = merged.sort_values('_sort_key', ascending=False).drop('_sort_key', axis=1)

    # Select final columns
    result = merged[[
        'Material Description',
        'NSOH_previous', 'NSOH_now', 'NSOH_Change', 'NSOH_Change_Pct',
        'Change Type'
    ]].copy()

    return result

# ---------------------------------------------------
# load_national_data_with_hash FUNCTION
# ---------------------------------------------------
@st.cache_data(ttl=300, show_spinner=False)
def load_national_data_with_hash():
    """Load data from Supabase and return along with a hash for change detection"""
    try:
        if st.session_state.supabase_client is None:
            st.error("Supabase client not initialized")
            return pd.DataFrame(), None

        # Pagination to get ALL rows
        all_data = []
        page = 0
        page_size = 1000
        max_pages = 100  # Safety limit to prevent infinite loops

        while page < max_pages:
            response = st.session_state.supabase_client.table("health_data") \
                .select("*") \
                .range(page * page_size, (page + 1) * page_size - 1) \
                .execute()

            if not response.data:
                break

            all_data.extend(response.data)

            if len(response.data) < page_size:
                break

            page += 1

        if not all_data:
            st.warning("No data found in Supabase")
            return pd.DataFrame(), None

        df = pd.DataFrame(all_data)

        if 'id' in df.columns:
            df = df.drop(columns=['id'])

        column_mapping = {
            'material_description': 'Material Description',
            'adama_branch': 'Adama Branch',
            'addis_ababa_branch_1': 'Addis Ababa Branch 1',
            'addis_ababa_branch_2': 'Addis Ababa Branch 2',
            'arba_minch_branch': 'Arba Minch Branch',
            'assosa_branch': 'Assosa Branch',
            'bahir_dar_branch': 'Bahir Dar Branch',
            'dessie_branch': 'Dessie Branch',
            'dire_dawa_branch': 'Dire Dawa Branch',
            'gambela_branch': 'Gambela Branch',
            'gondar_branch': 'Gondar Branch',
            'hawassa_branch': 'Hawassa Branch',
            'jigjiga_branch': 'Jigjiga Branch',
            'jimma_branch': 'Jimma Branch',
            'kebridahar_branch': 'Kebridahar Branch',
            'mekele_branch': 'Mekele Branch',
            'negele_borena_branch': 'Negele Borena Branch',
            'nekemte_branch': 'Nekemte Branch',
            'semera_branch': 'Semera Branch',
            'shire_branch': 'Shire Branch',
            'head_office': 'Head Office',
            'hubs': 'Hubs',
            'nsoh': 'NSOH',
            'expiry': 'Expiry'
        }

        existing_mapping = {k: v for k, v in column_mapping.items() if k in df.columns}
        df = df.rename(columns=existing_mapping)
        df = df.loc[:, ~df.columns.str.contains("^Unnamed")]
        df.columns = df.columns.str.strip()

        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].fillna("")

        # Create a hash of NSOH values for change detection (using a safe method)
        if 'NSOH' in df.columns:
            # Convert to a stable string representation for hashing
            nsoh_tuple = tuple(pd.to_numeric(df['NSOH'], errors='coerce').fillna(0).round(0).tolist())
            nsoh_hash = hash(nsoh_tuple)
        else:
            nsoh_hash = hash(str(df.shape))

        return df, nsoh_hash

    except Exception as e:
        st.error(f"Error loading data from Supabase: {e}")
        return pd.DataFrame(), None

# ---------------------------------------------------
# DOS Tracking Function (UPDATED - NO DUPLICATE CODE)
# ---------------------------------------------------
def calculate_dos(current_df):
    """Calculate Days Out of Stock - stores persistently in Supabase"""
    from datetime import date, datetime, timedelta

    current_date = date.today()

    # Load existing DOS tracking from Supabase
    dos_tracking = load_dos_tracking_from_supabase()

    # Get current NMOS values from DataFrame
    current_nmos = {}
    for idx, row in current_df.iterrows():
        material = row.get('Material Description')
        if pd.isna(material):
            continue

        # Get NMOS value
        nmos = row.get('NMOS')
        try:
            if pd.isna(nmos) or nmos == "":
                nmos = 1  # Default to 1 if no data
            else:
                # ===== FIX: SAFELY STRIP COMMAS =====
                nmos = float(str(nmos).replace(',', ''))
        except (ValueError, TypeError):
            nmos = 1

        current_nmos[str(material)] = nmos

    # Helper function to convert to date if needed
    def ensure_date(d):
        if d is None:
            return None
        if isinstance(d, datetime):
            return d.date()
        return d

    # Update DOS tracking based on current NMOS
    updated_tracking = {}
    for material, nmos in current_nmos.items():
        is_out_of_stock = nmos < 1

        if material not in dos_tracking:
            # Initialize tracking for this material
            if is_out_of_stock:
                updated_tracking[material] = {
                    'start_date': current_date,
                    'days': 1,
                    'is_out_of_stock': True,
                    'last_nmos': nmos,
                    'last_check_date': current_date
                }
            else:
                updated_tracking[material] = {
                    'start_date': None,
                    'days': 0,
                    'is_out_of_stock': False,
                    'last_nmos': nmos,
                    'last_check_date': current_date
                }
        else:
            tracking = dos_tracking[material].copy()

            # Convert dates to date objects for comparison
            start_date = ensure_date(tracking.get('start_date'))
            last_check = ensure_date(tracking.get('last_check_date', current_date))
            previous_status = tracking.get('is_out_of_stock', False)
            previous_nmos = tracking.get('last_nmos', 1)

            # Check if status changed
            if is_out_of_stock != previous_status:
                if is_out_of_stock and not previous_status:
                    # JUST went out of stock - start counting from today
                    tracking['start_date'] = current_date
                    tracking['days'] = 1
                    tracking['is_out_of_stock'] = True
                elif not is_out_of_stock and previous_status:
                    # JUST came back in stock - reset to 0
                    tracking['start_date'] = None
                    tracking['days'] = 0
                    tracking['is_out_of_stock'] = False
            else:
                # Status unchanged
                if is_out_of_stock:
                    # Still out of stock - increment days
                    if start_date is not None:
                        # Calculate actual days from start date to today
                        tracking['days'] = (current_date - start_date).days
                        if tracking['days'] < 1:
                            tracking['days'] = 1
                    else:
                        # No start date but we're out of stock - set start date
                        tracking['start_date'] = current_date - timedelta(days=1)
                        tracking['days'] = 1
                    tracking['is_out_of_stock'] = True
                else:
                    # Still in stock - ensure days is 0
                    tracking['days'] = 0
                    tracking['is_out_of_stock'] = False

            # Update last known values
            tracking['last_nmos'] = nmos
            tracking['last_check_date'] = current_date
            updated_tracking[material] = tracking

    # Keep any materials from previous tracking that aren't in current data
    for material, tracking in dos_tracking.items():
        if material not in updated_tracking:
            updated_tracking[material] = tracking

    # Save updated tracking to Supabase
    save_dos_tracking_to_supabase(updated_tracking)

    # Return current DOS days for each material
    return {material: tracking['days'] for material, tracking in updated_tracking.items()}

# ---------------------------------------------------
# Recommendation Functions
# ---------------------------------------------------
def get_stock_out_recommendation(row):
    """Generate recommendation for Risk of Stock out based on pipeline status with PO numbers"""
    try:
        git_mos = row.get('GIT_MOS', 0)
        lc_mos = row.get('LC_MOS', 0)
        wb_mos = row.get('WB_MOS', 0)
        tmd_mos = row.get('TMD_MOS', 0)
        git_po = row.get('GIT_PO', '')
        lc_po = row.get('LC_PO', '')
        wb_po = row.get('WB_PO', '')
        tmd_po = row.get('TMD_PO', '')

        git_mos = pd.to_numeric(git_mos, errors='coerce') if not isinstance(git_mos, (int, float)) else git_mos
        lc_mos = pd.to_numeric(lc_mos, errors='coerce') if not isinstance(lc_mos, (int, float)) else lc_mos
        wb_mos = pd.to_numeric(wb_mos, errors='coerce') if not isinstance(wb_mos, (int, float)) else wb_mos
        tmd_mos = pd.to_numeric(tmd_mos, errors='coerce') if not isinstance(tmd_mos, (int, float)) else tmd_mos

        git_mos = git_mos if pd.notna(git_mos) else 0
        lc_mos = lc_mos if pd.notna(lc_mos) else 0
        wb_mos = wb_mos if pd.notna(wb_mos) else 0
        tmd_mos = tmd_mos if pd.notna(tmd_mos) else 0

        if git_mos > 0:
            po_text = f" PO {git_po}" if git_po and str(git_po) != 'nan' and str(git_po) != '' else ""
            return f"🚚 Expedite shipment{po_text} - goods in transit"
        elif git_mos == 0 and lc_mos > 0:
            po_text = f" PO {lc_po}" if lc_po and str(lc_po) != 'nan' and str(lc_po) != '' else ""
            return f"📄 Expedite L/C opening process{po_text}"
        elif git_mos == 0 and lc_mos == 0 and wb_mos > 0:
            po_text = f" PO {wb_po}" if wb_po and str(wb_po) != 'nan' and str(wb_po) != '' else ""
            return f"💰 Expedite budget transfer{po_text}"
        elif git_mos == 0 and lc_mos == 0 and wb_mos == 0 and tmd_mos > 0:
            po_text = f" PO {tmd_po}" if tmd_po and str(tmd_po) != 'nan' and str(tmd_po) != '' else ""
            return f"📋 Expedite tender process{po_text}"
        else:
            return "🔄 Initiate additional quantity - no pipeline stock"
    except Exception as e:
        return f"⚠️ Review supply chain status"

def get_expiry_risk_recommendation(row, cv_category=None):
    """Generate recommendation for Expiry Risk based on CV and distribution, including expiry quantity"""
    try:
        if cv_category is None:
            cv_category = row.get('CV Category', 'Unknown')

        hubs_pct = row.get('Hubs%', 0)
        ho_pct = row.get('Head Office%', 0)
        expiry_details = row.get('Expiry Risk Details', '')

        hubs_pct = pd.to_numeric(hubs_pct, errors='coerce') if not isinstance(hubs_pct, (int, float)) else hubs_pct
        ho_pct = pd.to_numeric(ho_pct, errors='coerce') if not isinstance(ho_pct, (int, float)) else ho_pct
        hubs_pct = hubs_pct if pd.notna(hubs_pct) else 0
        ho_pct = ho_pct if pd.notna(ho_pct) else 0

        expiry_info = f" [Expiry: {expiry_details}]" if expiry_details and expiry_details != "" else ""

        if cv_category == 'High variation':
            return f"🔄 Redistribution required - high variation across hubs{expiry_info}"
        elif hubs_pct < ho_pct:
            return f"📦 Push stock to hubs - hubs have lower stock than head office{expiry_info}"
        else:
            return f"🌍 Donate to other countries - excess stock for donation{expiry_info}"

    except Exception as e:
        return f"⚠️ Review expiry risk - check batch details"

# ---------------------------------------------------
# Utility Functions
# ---------------------------------------------------
def format_number_with_commas(x):
    try:
        if pd.isna(x) or x == "" or x is None:
            return ""
        if isinstance(x, str):
            x = x.replace(',', '')
            try:
                x = float(x) if x else np.nan
            except:
                return x
        if pd.isna(x):
            return ""
        x = round(x)
        return f"{x:,.0f}"
    except:
        return str(x) if x else ""

def format_mos_with_decimals(x):
    try:
        if pd.isna(x) or x == "" or x is None:
            return ""
        if isinstance(x, str):
            try:
                x = float(x) if x else np.nan
            except:
                return x
        if pd.isna(x):
            return ""
        return f"{x:.2f}"
    except:
        return str(x) if x else ""

# ---------------------------------------------------
# Stock level rules (months of stock). Vaccines use their own min / max.
# ---------------------------------------------------
DEFAULT_MIN_MOS, DEFAULT_MAX_MOS = 6, 18
VACCINE_MIN_MOS, VACCINE_MAX_MOS = 4, 10
# A program (sheet) name or a material description containing one of these words is treated as a vaccine.
VACCINE_KEYWORDS = ("vaccin",)
VACCINE_MATERIALS = set()


def _is_vaccine_text(text):
    t = str(text).lower()
    return any(k in t for k in VACCINE_KEYWORDS)


def compute_vaccine_materials(sheets):
    """Materials that belong to a vaccine program sheet."""
    out = set()
    for name, sdf in (sheets or {}).items():
        if _is_vaccine_text(name) and sdf is not None and 'Material Description' in getattr(sdf, 'columns', []):
            out.update(sdf['Material Description'].dropna().astype(str).str.strip())
    return out


def levels_for(materials):
    """(min_levels, max_levels) numpy arrays for a list/array of material descriptions."""
    mats = pd.Series(list(materials), dtype="object").astype(str).str.strip()
    is_v = mats.isin(VACCINE_MATERIALS) | mats.apply(_is_vaccine_text)
    return (np.where(is_v, VACCINE_MIN_MOS, DEFAULT_MIN_MOS).astype(float),
            np.where(is_v, VACCINE_MAX_MOS, DEFAULT_MAX_MOS).astype(float))


def program_levels(program_name):
    return (VACCINE_MIN_MOS, VACCINE_MAX_MOS) if _is_vaccine_text(program_name) else (DEFAULT_MIN_MOS, DEFAULT_MAX_MOS)


def nmos_range_stats(frame):
    """(% of materials within min-max, % overstocked) using each material's own min / max."""
    try:
        nm = pd.to_numeric(frame['NMOS'], errors='coerce').to_numpy(dtype=float)
        ok = ~np.isnan(nm)
        if not ok.any():
            return 0.0, 0.0
        lo, hi = levels_for(frame['Material Description'].to_numpy()[ok])
        v = nm[ok]
        return float(((v >= lo) & (v <= hi)).mean() * 100), float((v > hi).mean() * 100)
    except Exception:
        return 0.0, 0.0


def categorize_stock(nmos, min_level=DEFAULT_MIN_MOS, max_level=DEFAULT_MAX_MOS):
    try:
        if pd.isna(nmos) or nmos == "" or nmos is None:
            return ""
        x = float(nmos) if not isinstance(nmos, (int, float)) else nmos
        if x < 1:
            return "Stock Out"
        elif x < min_level:
            return "Understock"
        elif x <= max_level:
            return "Normal Stock"
        else:
            return "Overstock"
    except:
        return ""

def calculate_coefficient_of_variation(values):
    try:
        values = pd.to_numeric(values, errors='coerce')
        values = values[values.notna() & (values > 0)]
        if len(values) > 1:
            mean = values.mean()
            std = values.std()
            if mean > 0:
                return (std / mean) * 100
        return np.nan
    except:
        return np.nan

def calculate_risk(row):
    """Calculate risk of stock out - ONLY for NMOS >= 1 (Stock Out is separate)"""
    try:
        nmos = row['NMOS'] if pd.notna(row['NMOS']) else np.nan
        git_mos = row['GIT_MOS'] if pd.notna(row['GIT_MOS']) else 0
        lc_mos = row['LC_MOS'] if pd.notna(row['LC_MOS']) else 0
        wb_mos = row['WB_MOS'] if pd.notna(row['WB_MOS']) else 0
        tmd_mos = row['TMD_MOS'] if pd.notna(row['TMD_MOS']) else 0

        if pd.isna(nmos) or nmos < 1:
            return ""

        if 1 <= nmos < 2:
            return "Risk of Stock out"

        if 2 <= nmos < 4 and git_mos == 0:
            return "Risk of Stock out"

        if 4 <= nmos < 6 and git_mos == 0 and lc_mos == 0 and wb_mos == 0:
            return "Risk of Stock out"

        if 6 <= nmos < 7 and git_mos == 0 and lc_mos == 0 and wb_mos == 0 and tmd_mos == 0:
            return "Risk of Stock out"

        return ""
    except:
        return ""

# ---------------------------------------------------
# Load ALL data
# ---------------------------------------------------
amc_pipeline_sheet_id = "14VvZ7IyOmpM4SZrY5_ArHDgLkeFN4inW"
branch_amc_sheet_id = "12Z5xqX32QIzjoN6tNvGbjutMheXx5US1"

# Load data with hash for change detection
df_external, current_data_hash = load_national_data_with_hash()

if df_external.empty:
    st.error("No data in Supabase. Please upload data through admin panel.")
    st.stop()

# Initialize previous_data_hash if not exists
if 'previous_data_hash' not in st.session_state:
    st.session_state.previous_data_hash = None
    st.session_state.raw_previous_data = None
    st.session_state.nsoh_changes = None

# IMPORTANT: Only update previous data when hash changes (real data update)
if st.session_state.previous_data_hash != current_data_hash and current_data_hash is not None:
    # Data has changed - calculate changes using current (raw) vs previous (raw)
    if st.session_state.raw_previous_data is not None and not st.session_state.raw_previous_data.empty:
        st.session_state.nsoh_changes = calculate_stock_changes(df_external, st.session_state.raw_previous_data)

    # Update previous data to current
    st.session_state.raw_previous_data = df_external.copy()
    st.session_state.previous_data_hash = current_data_hash

df_new_deliveries = load_new_deliveries()
branch_amc_data = load_branch_amc_from_google_sheets(branch_amc_sheet_id)
google_sheets = load_google_sheets(amc_pipeline_sheet_id)

if df_external.empty:
    st.error("No data in Supabase. Please upload data through admin panel.")
    st.stop()

# ---------------------------------------------------
# Main-panel slots: [title] then [filters]. Filled later, but they keep this position on screen.
# ---------------------------------------------------
# ---------------------------------------------------
# User Info in Sidebar
# ---------------------------------------------------
with st.sidebar:
    st.markdown("<div style='background:#1a5276;border-radius:15px;padding:10px;text-align:center;width:60px'>"
                "<p style='color:white;font-weight:bold;margin:0'>EPSS</p></div>", unsafe_allow_html=True)
    st.title(f"Welcome, {st.session_state['user']['full_name']}!")
    st.caption(f"Role: {st.session_state['user']['role'].title()}")

    if st.session_state['user']['role'] == 'admin' and st.session_state.supabase_client:
        st.success("✅ Connected to Supabase")

    if st.session_state.notifications:
        st.markdown(f"### 🔔 Notifications ({len(st.session_state.notifications)})")
        for notif in st.session_state.notifications[:3]:
            st.warning(notif)

_title_slot = st.container()
_FILTER_PAGES = ("Dashboard", "Advanced Analytics", "Executive Summary")
_filters_visible = st.session_state.get('nav_page', 'Dashboard') in _FILTER_PAGES
_sb_flt = st.sidebar.container()   # filters live in the sidebar, right above Navigation
_fc = [_sb_flt] * 5 if _filters_visible else None
if _filters_visible:
    with _fc[4]:
        _vm_opts = ["Table View", "Card View", "📱 Mobile View"]
        _vm_idx = {"table": 0, "card": 1, "mobile": 2}.get(st.session_state.view_mode, 0)
        view_mode = st.selectbox("🎨 Display Settings", _vm_opts, index=_vm_idx)
        st.session_state.view_mode = {"Table View": "table", "Card View": "card"}.get(view_mode, "mobile")

# ---------------------------------------------------
# Program Selection - MULTI-SELECT (UPDATED)
# ---------------------------------------------------
if google_sheets:
    # Define program order based on sheets
    PROGRAM_ORDER_LIST = [
        "Malaria",
        "HIV", 
        "OI and Hepatitis",
        "Hepatitis",
        "STI",
        "TB",
        "Drug Susceptible -TB Medicine (DS-TB)",
        "Drug Resisitance -TB Medicine (DR-TB)",
        "Leprosy Medicines",
        "Nutrition",
        "Lab TB",
        "TB diagnostics& Laboratory reagent",
        "TB Lab Supplies",
        "HIV Lab",
        "HIV VL Reagents",
        "CD4 ,AHD &HIV RTKs"
    ]

    # Get all sheet names and sort them according to PROGRAM_ORDER_LIST
    sheet_names = list(google_sheets.keys())

    # Sort sheets according to PROGRAM_ORDER_LIST
    sorted_sheets = []
    for prog in PROGRAM_ORDER_LIST:
        if prog in sheet_names:
            sorted_sheets.append(prog)

    # Add any remaining sheets not in the list
    for sheet in sheet_names:
        if sheet not in sorted_sheets:
            sorted_sheets.append(sheet)

    # Add "All" at the beginning
    program_list = ["All"] + sorted_sheets
else:
    program_list = ["All"]

# --- Enforce program_access from user session (non-admins only) ---
if st.session_state['user'].get('role') != 'admin':
    _raw_prog = st.session_state['user'].get('program_access', 'All') or 'All'
    _allowed_progs = [p.strip() for p in _raw_prog.split(',') if p.strip()]
    if _allowed_progs and 'All' not in _allowed_progs:
        _allowed_set = set(_allowed_progs)
        program_list = ["All"] + [p for p in program_list if p in _allowed_set]
        if len(program_list) == 1:  # only "All" left means no match
            st.warning("⚠️ You don't have access to any programs. Contact your administrator.")
            st.stop()
        # Clamp any saved selection to only allowed programs
        _saved = st.session_state.get('selected_programs', ['All'])
        _clamped = [p for p in _saved if p == 'All' or p in _allowed_set]
        if not _clamped:
            _clamped = ['All']
        st.session_state.selected_programs = _clamped

# --- Is this user allowed to see ALL programs? (admins, or program_access contains "All") ---
_user_role_chk = st.session_state['user'].get('role')
_raw_prog_chk = st.session_state['user'].get('program_access', 'All') or 'All'
_allowed_chk = [p.strip() for p in _raw_prog_chk.split(',') if p.strip()]
_is_unrestricted = (_user_role_chk == 'admin') or (not _allowed_chk) or ('All' in _allowed_chk)

# Multi-select for programs
if _filters_visible:
    with _fc[0]:
        selected_programs = st.multiselect(
            "Program(s)",
            program_list,
            default=st.session_state.selected_programs if st.session_state.selected_programs else ["All"],
            key="program_multiselect"
        )
else:
    selected_programs = st.session_state.selected_programs if st.session_state.selected_programs else ["All"]

# Update session state
st.session_state.selected_programs = selected_programs

# Determine if "All" is selected
if "All" in selected_programs:
    # If "All" is selected, use all programs
    selected_programs_list = [p for p in program_list if p != "All"]
    show_all_programs = True
else:
    selected_programs_list = selected_programs
    show_all_programs = False

# Subcategory filter - only show if exactly one program is selected and it has subcategories
subcategory_options = ["All"]
show_subcategory_filter = False

if len(selected_programs_list) == 1:
    single_program = selected_programs_list[0]
    if single_program in PROGRAM_HIERARCHY and PROGRAM_HIERARCHY[single_program]["is_parent"]:
        subcategory_options = ["All"] + PROGRAM_HIERARCHY[single_program]["subcategories"]
        show_subcategory_filter = True

if show_subcategory_filter:
    if _filters_visible:
        with _fc[0]:
            subcategory_filter = st.selectbox("Subcategory", subcategory_options, key="subcategory_filter")
    else:
        subcategory_filter = st.session_state.get("subcategory_filter", "All")
        if subcategory_filter not in subcategory_options:
            subcategory_filter = "All"
else:
    subcategory_filter = "All"
    st.session_state.subcategory_filter = "All"

# ---------------------------------------------------
# Data loading based on selected programs
# ---------------------------------------------------
VACCINE_MATERIALS = compute_vaccine_materials(google_sheets)


def _frame_sig(obj):
    """Cheap content signature for a DataFrame or a dict of DataFrames."""
    try:
        items = obj.items() if isinstance(obj, dict) else [("_", obj)]
        parts = []
        for k, v in items:
            if v is None or not hasattr(v, "shape"):
                parts.append((str(k), None)); continue
            parts.append((str(k), v.shape, int(pd.util.hash_pandas_object(v.astype(str), index=False).sum())))
        return tuple(parts)
    except Exception:
        return ("bucket", int(time.time() // 300))

# The merge / NMOS / DOS / risk calculations below only depend on these inputs. Re-running them (and the
# Supabase DOS read + write inside calculate_dos) on every click made the app slow, so reuse the result
# until one of the inputs actually changes.
_frames_sig = (
    'v3-gf', current_data_hash, date.today().isoformat(), tuple(selected_programs_list), bool(show_all_programs),
    subcategory_filter, _frame_sig(google_sheets), _frame_sig(branch_amc_data)
)
_frames_memo = st.session_state.get('_main_frames_memo')
if _frames_memo is not None and _frames_memo.get('sig') == _frames_sig:
    df = _frames_memo['df'].copy()
    display_df = _frames_memo['display_df'].copy()
else:
    if show_all_programs or len(selected_programs_list) == 0:
        # Use only the programs in program_list (already filtered by user access)
        _allowed_sheet_names = set(p for p in program_list if p != "All")
        if google_sheets:
            all_dfs = []
            for name, df_program in google_sheets.items():
                if name not in _allowed_sheet_names:
                    continue
                if df_program.empty:
                    continue
                df_copy = df_program.copy()
                df_copy.columns = df_copy.columns.astype(str)
                if df_copy.columns.duplicated().any():
                    df_copy = df_copy.loc[:, ~df_copy.columns.duplicated()]
                all_dfs.append(df_copy)

            if all_dfs:
                try:
                    df_google = pd.concat(all_dfs, ignore_index=True, sort=False)
                except Exception as concat_error:
                    st.error(f"Error combining sheets: {concat_error}")
                    df_google = pd.DataFrame()
            else:
                df_google = pd.DataFrame()
        else:
            df_google = pd.DataFrame()
    else:
        # Combine selected programs
        all_dfs = []
        for program in selected_programs_list:
            if program in google_sheets:
                df_program = google_sheets[program].copy()
                df_program.columns = df_program.columns.astype(str)
                if df_program.columns.duplicated().any():
                    df_program = df_program.loc[:, ~df_program.columns.duplicated()]
                all_dfs.append(df_program)

        if all_dfs:
            try:
                df_google = pd.concat(all_dfs, ignore_index=True, sort=False)
            except Exception as concat_error:
                st.error(f"Error combining sheets: {concat_error}")
                df_google = pd.DataFrame()
        else:
            df_google = pd.DataFrame()

    if not df_google.empty:
        required_cols = [
            'Material Description', 'AMC',
            'GIT_PO', 'GIT_Qty', 'GIT_MOS',
            'LC_PO', 'LC_Qty', 'LC_MOS',
            'WB_PO', 'WB_Qty', 'WB_MOS',
            'TMD_PO', 'TMD_Qty', 'TMD_MOS', "Status"
        ]
        available_cols = [c for c in required_cols if c in df_google.columns]
        df_google = df_google[available_cols]
    else:
        df_google = pd.DataFrame()

    if not df_google.empty and not df_external.empty:
        if 'Material Description' in df_external.columns and 'Material Description' in df_google.columns:
            df_external = df_external.drop_duplicates(subset=['Material Description'], keep='first')
            df_google = df_google.drop_duplicates(subset=['Material Description'], keep='first')
            df = df_external.merge(df_google, on="Material Description", how="right")
            df = df.drop_duplicates(subset=['Material Description'], keep='first')
        else:
            st.error("Material Description column missing for merge")
            # Restricted users must never fall back to the full national data
            df = df_external.copy() if _is_unrestricted else df_external.iloc[0:0].copy()
    else:
        if _is_unrestricted:
            df = df_external.copy()
        else:
            # Restricted user but their program data is empty/unavailable:
            # show nothing instead of leaking every medicine.
            df = df_external.iloc[0:0].copy()
            st.warning("⚠️ No data available for your assigned program(s) right now. "
                       "Please refresh, or contact your administrator.")

    if not df.empty:
        if 'S/N' in df.columns:
            df = df.drop(columns=['S/N'])

        text_columns = ['Status', 'Expiry', 'GIT_PO', 'LC_PO', 'WB_PO', 'TMD_PO']
        numeric_columns = [col for col in df.columns if col not in text_columns + ['Material Description']]

        for col in numeric_columns:
            if col in df.columns:
                try:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                except Exception:
                    continue

        for col in text_columns:
            if col in df.columns:
                df[col] = df[col].fillna("").astype(str)

        # ===== FIX: Handle empty NSOH values ONLY =====
        # NSOH should be 0 when AMC > 0 and NSOH is empty/null
        if 'NSOH' in df.columns and 'AMC' in df.columns:
            # Convert to numeric (already done above, but ensure)
            df['NSOH'] = pd.to_numeric(df['NSOH'], errors='coerce')
            df['AMC'] = pd.to_numeric(df['AMC'], errors='coerce')

            # Where AMC > 0 and NSOH is NaN/empty, set NSOH to 0
            mask = (df['AMC'] > 0) & (df['NSOH'].isna())
            df.loc[mask, 'NSOH'] = 0

            # Fill remaining NSOH NaN with 0 (for materials with AMC <= 0 or missing)
            df['NSOH'] = df['NSOH'].fillna(0)

        # Calculate NMOS (after fixing NSOH)
        if 'NSOH' in df.columns and 'AMC' in df.columns:
            nsoh = pd.to_numeric(df['NSOH'], errors='coerce')
            amc = pd.to_numeric(df['AMC'], errors='coerce')

            # For AMC that is 0 or NaN, we cannot calculate NMOS
            # Replace 0 AMC with NaN to avoid division by zero
            amc = amc.replace(0, np.nan)

            # Calculate NMOS - where AMC is NaN, NMOS will be NaN
            nmos = nsoh / amc
            nmos = nmos.replace([np.inf, -np.inf], np.nan)
            df['NMOS'] = nmos.round(2)

        # Calculate DOS
        dos_dict = calculate_dos(df)
        df['DOS'] = df['Material Description'].map(dos_dict).fillna(0).astype(int)

        mos_cols = ['NMOS', 'GIT_MOS', 'LC_MOS', 'WB_MOS', 'TMD_MOS']
        available_mos = []
        for col in mos_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                available_mos.append(col)

        if available_mos:
            df['TMOS'] = df[available_mos].sum(axis=1)
        else:
            df['TMOS'] = np.nan

        # Gap to the 18-month target: GF_MOS = 18 - TMOS ; GF_Qty = GF_MOS x AMC (placed right after TMOS)
        _gf_mos = 18 - pd.to_numeric(df['TMOS'], errors='coerce')
        _gf_qty = _gf_mos * pd.to_numeric(df['AMC'], errors='coerce') if 'AMC' in df.columns else np.nan
        df['GF_MOS'] = _gf_mos.round(2)
        df['GF_Qty'] = pd.Series(_gf_qty, index=df.index).round(0)
        _cols_gf = [c for c in df.columns if c not in ('GF_MOS', 'GF_Qty')]
        _t = _cols_gf.index('TMOS') + 1
        df = df[_cols_gf[:_t] + ['GF_MOS', 'GF_Qty'] + _cols_gf[_t:]]

        if 'NMOS' in df.columns:
            _lo_lv, _hi_lv = levels_for(df['Material Description'])
            df['Stock Status'] = [categorize_stock(n_, a_, b_) for n_, a_, b_ in zip(df['NMOS'], _lo_lv, _hi_lv)]
        else:
            df['Stock Status'] = ""

        if 'Hubs' in df.columns and 'Head Office' in df.columns and 'NSOH' in df.columns:
            hubs_vals = pd.to_numeric(df['Hubs'], errors='coerce').fillna(0)
            ho_vals = pd.to_numeric(df['Head Office'], errors='coerce').fillna(0)
            nsoh_vals = pd.to_numeric(df['NSOH'], errors='coerce')
            valid_mask = nsoh_vals.notna() & (nsoh_vals > 0)
            df['Hubs%'] = np.where(valid_mask, (hubs_vals / nsoh_vals * 100).round(1), np.nan)
            df['Head Office%'] = np.where(valid_mask, (ho_vals / nsoh_vals * 100).round(1), np.nan)
            df['Distr. Gap'] = np.where(valid_mask, (df['Hubs%'] - df['Head Office%']).round(1), np.nan)
        else:
            df['Hubs%'] = np.nan
            df['Head Office%'] = np.nan
            df['Distr. Gap'] = np.nan

        if not branch_amc_data.empty and 'Material Description' in branch_amc_data.columns:
            branch_cols = [col for col in df.columns if 'Branch' in col or col == 'Material Description']
            if len(branch_cols) > 1:
                stock_data = df[branch_cols].copy()
                merged_cv = pd.merge(stock_data, branch_amc_data, on='Material Description', how='inner', suffixes=('_stock', '_amc'))

                if not merged_cv.empty:
                    branch_cols_list = [col for col in stock_data.columns if col != 'Material Description']
                    amc_cols = [col for col in branch_amc_data.columns if col != 'Material Description']
                    cv_calc_data = {'Material Description': merged_cv['Material Description']}

                    for i in range(min(len(branch_cols_list), len(amc_cols))):
                        stock_col = branch_cols_list[i]
                        amc_col = amc_cols[i]
                        stock_vals = pd.to_numeric(merged_cv[f"{stock_col}_stock"], errors='coerce')
                        amc_vals = pd.to_numeric(merged_cv[f"{amc_col}_amc"], errors='coerce')
                        with np.errstate(divide='ignore', invalid='ignore'):
                            mos_vals = np.where(amc_vals > 0, stock_vals / amc_vals, np.nan)
                        cv_calc_data[stock_col] = mos_vals

                    cv_df = pd.DataFrame(cv_calc_data)
                    mos_cols_for_cv = [col for col in cv_df.columns if col != 'Material Description']
                    cv_df['CV (%)'] = cv_df[mos_cols_for_cv].apply(lambda row: calculate_coefficient_of_variation(row), axis=1)
                    cv_df['CV (%)'] = cv_df['CV (%)'].round(1)

                    def categorize_cv(cv_value):
                        if pd.isna(cv_value):
                            return "Unknown"
                        elif cv_value < 50:
                            return "Low variation"
                        elif cv_value <= 100:
                            return "Moderate variation"
                        else:
                            return "High variation"

                    cv_df['CV Category'] = cv_df['CV (%)'].apply(categorize_cv)
                    df = df.merge(cv_df[['Material Description', 'CV Category']], on='Material Description', how='left')
                else:
                    df['CV Category'] = "Unknown"
            else:
                df['CV Category'] = "Unknown"
        else:
            df['CV Category'] = "Unknown"

        # Handle subcategory filtering BEFORE other operations
        # Only assign subcategories if exactly one program is selected
        if len(selected_programs_list) == 1:
            single_program = selected_programs_list[0]
            if single_program in PROGRAM_HIERARCHY:
                subcategory_list = PROGRAM_HIERARCHY[single_program]["subcategories"]
                # Assign subcategories to remaining materials
                subcategory_mapping = assign_subcategories_to_materials(df, subcategory_list)
                df['Assigned Subcategory'] = df['Material Description'].map(subcategory_mapping)

                # Apply subcategory filter if selected
                if subcategory_filter != "All":
                    df = df[df['Assigned Subcategory'] == subcategory_filter]
            else:
                df['Assigned Subcategory'] = None
        else:
            df['Assigned Subcategory'] = None

        if 'NMOS' in df.columns:
            df['Risk of Stock'] = df.apply(calculate_risk, axis=1)
        else:
            df['Risk of Stock'] = ""

        expiry_data = df.apply(lambda row: parse_multiple_expiry_batches(row.get('Expiry', ''), row.get('AMC', np.nan)), axis=1)
        df['Has Expiry Risk'] = expiry_data.apply(lambda x: x[0])
        df['Expiry Risk Details'] = expiry_data.apply(lambda x: x[1])

        risk_types = []
        for idx, row in df.iterrows():
            risk_of_stock = row.get('Risk of Stock', '') == 'Risk of Stock out'
            expiry_risk = row.get('Has Expiry Risk', False)

            if risk_of_stock and expiry_risk:
                risk_types.append("Critical Risk")
            elif risk_of_stock:
                risk_types.append("Risk of Stock out")
            elif expiry_risk:
                risk_types.append("Expiry Risk")
            else:
                risk_types.append("")
        df['Risk Type'] = risk_types

        # Store current data for next comparison
        st.session_state.raw_previous_data = df.copy()

        display_df = df.copy()
        text_columns_to_preserve = ['Material Description', 'Stock Status', 'Risk Type', 'Status', 'Expiry', 'GIT_PO', 'LC_PO', 'WB_PO', 'TMD_PO', 'CV Category', 'DOS']

        if 'Hubs%' in display_df.columns:
            text_columns_to_preserve.append('Hubs%')
        if 'Head Office%' in display_df.columns:
            text_columns_to_preserve.append('Head Office%')
        if 'Distr. Gap' in display_df.columns:
            text_columns_to_preserve.append('Distr. Gap')

        for col in display_df.columns:
            if col not in text_columns_to_preserve:
                if col in ['NMOS', 'GIT_MOS', 'LC_MOS', 'WB_MOS', 'TMD_MOS', 'TMOS', 'GF_MOS']:
                    display_df[col] = display_df[col].apply(format_mos_with_decimals)
                elif col in ['Hubs%', 'Head Office%', 'Distr. Gap']:
                    display_df[col] = display_df[col].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "")
                else:
                    display_df[col] = display_df[col].apply(format_number_with_commas)

    if 'display_df' in globals() and isinstance(display_df, pd.DataFrame):
        st.session_state['_main_frames_memo'] = {'sig': _frames_sig, 'df': df.copy(), 'display_df': display_df.copy()}

    # ========== MATERIAL FILTER SECTION WITH MULTI-SELECT ==========
if 'Material Description' in df.columns:
    # Handle NaN values in Material Description for sorting
    unique_materials = df['Material Description'].dropna().astype(str).unique()

    # Filter out subcategory headers from material list (dropdown only) if exactly one program
    if len(selected_programs_list) == 1 and selected_programs_list[0] in PROGRAM_HIERARCHY:
        subcategory_list = PROGRAM_HIERARCHY[selected_programs_list[0]]["subcategories"]
        unique_materials = [m for m in unique_materials if m not in subcategory_list]

    materials = ["All"] + sorted(unique_materials)

    statuses = ["All"] + sorted([s for s in df['Stock Status'].unique() if s != "" and pd.notna(s)]) if 'Stock Status' in df.columns else ["All"]

    risk_type_options = ["All", "Risk of Stock out", "Expiry Risk", "Critical Risk"]

    # MULTI-SELECT FILTERS
    _risk_default = st.session_state.risk_type_filter if isinstance(st.session_state.risk_type_filter, list) else ["All"]
    # keyed widgets: drop stored selections that are not in the current options, and keep them alive on pages
    # where the filter bar is not shown (assigning the key every run stops Streamlit from clearing it)
    st.session_state["flt_material"] = [m for m in st.session_state.get("flt_material", []) if m in materials]
    st.session_state["flt_status"] = [x for x in st.session_state.get("flt_status", []) if x in statuses]

    if _filters_visible:
        with _fc[1]:
            material_filter = st.multiselect("Material Description", materials, key="flt_material")
        with _fc[2]:
            status_filter = st.multiselect("Stock Status", statuses, key="flt_status")
        with _fc[3]:
            risk_type_filter = st.multiselect("Risk Type", risk_type_options, default=_risk_default)
        st.session_state.risk_type_filter = risk_type_filter
    else:
        material_filter = st.session_state["flt_material"]
        status_filter = st.session_state["flt_status"]
        risk_type_filter = _risk_default

    df_filtered = df.copy()
    display_df_filtered = display_df.copy()

    # ========== REMOVE SUBCATEGORY HEADERS FROM DATA ==========
    if len(selected_programs_list) == 1 and selected_programs_list[0] in PROGRAM_HIERARCHY:
        subcategory_list = PROGRAM_HIERARCHY[selected_programs_list[0]]["subcategories"]
        mask = ~df_filtered['Material Description'].astype(str).str.strip().isin(subcategory_list)
        df_filtered = df_filtered[mask].copy()
        display_df_filtered = display_df_filtered[mask].copy()

    # ========== APPLY MATERIAL FILTER (MULTI-SELECT) ==========
    if material_filter and "All" not in material_filter:
        df_filtered = df_filtered[df_filtered['Material Description'].isin(material_filter)]
        display_df_filtered = display_df_filtered[display_df_filtered['Material Description'].isin(material_filter)]

        # Track material views for each selected material
        for material in material_filter:
            if material not in st.session_state.material_views:
                st.session_state.material_views[material] = 0
            st.session_state.material_views[material] += 1

            # Track user activity
            if 'user' in st.session_state:
                st.session_state.user_activity.append({
                    'user': st.session_state['user']['email'],
                    'role': st.session_state['user']['role'],
                    'action': 'view_material',
                    'material': material,
                    'timestamp': datetime.now().isoformat()
                })

    # ========== APPLY STOCK STATUS FILTER (MULTI-SELECT) ==========
    if status_filter and "All" not in status_filter and 'Stock Status' in df_filtered.columns:
        df_filtered = df_filtered[df_filtered['Stock Status'].isin(status_filter)]
        display_df_filtered = display_df_filtered[display_df_filtered['Stock Status'].isin(status_filter)]

    # ========== APPLY RISK TYPE FILTER (MULTI-SELECT) ==========
    if risk_type_filter and "All" not in risk_type_filter:
        df_filtered = df_filtered[df_filtered['Risk Type'].isin(risk_type_filter)]
        display_df_filtered = display_df_filtered[display_df_filtered['Risk Type'].isin(risk_type_filter)]

    # ========== OPTIONAL: SHOW ACTIVE FILTERS SUMMARY ==========
    active_filters = []
    if risk_type_filter and "All" not in risk_type_filter:
        active_filters.append(f"Risk: {', '.join(risk_type_filter)}")
    if status_filter and "All" not in status_filter:
        active_filters.append(f"Status: {', '.join(status_filter)}")
    if material_filter and "All" not in material_filter:
        active_filters.append(f"Materials: {len(material_filter)} selected")
    if not show_all_programs and selected_programs_list:
        active_filters.append(f"Programs: {len(selected_programs_list)} selected")


else:
    st.error("Material Description column not found in the data")
    df_filtered = pd.DataFrame()
    display_df_filtered = pd.DataFrame()

# ===================================================
# NAVIGATION (expandable: pages -> tabs/sections)
# ===================================================
_is_admin = st.session_state['user']['role'] == 'admin'

# Full nav tree definition
_FULL_NAV_TREE = {
    "Dashboard": [
        "📋 Stock Status Table", "📈 KPIs & Analytics", "💡 Decision Briefs",
        "📍 Hubs Distribution", "📋 Procurement Lead Time", "🚚 New Deliveries"
    ],
    "Advanced Analytics": [
        "🏆 Branch Ranking", "🔄 Redistribution", "📧 Critical Alerts", "⏰ Expiry Notifications",
        "📊 Program Comparison", "🗺️ Regional Map", "📅 Report Scheduling"
    ],
    "Executive Summary": [
        "🎯 Performance Metrics", "📊 Stock Status", "⚠️ Risk Summary",
        "📍 Hubs Distribution", "🏆 Branch Ranking", "📊 Program Performance"
    ],
    "Issue Data": [],
}
if _can_upload_data():
    _FULL_NAV_TREE["Upload Data"] = []

# Filter pages based on main_tab_access (admins always see everything)
def _get_allowed_nav_tree():
    if _is_admin:
        return dict(_FULL_NAV_TREE)
    raw = st.session_state['user'].get('main_tab_access', 'All') or 'All'
    allowed = [t.strip() for t in raw.split(',') if t.strip()]
    if not allowed or 'All' in allowed:
        return dict(_FULL_NAV_TREE)
    # Map main_tab_access values to NAV_TREE keys
    _TAB_MAP = {
        "Dashboard":           "Dashboard",
        "Advanced Analytics":  "Advanced Analytics",
        "Upload":              "Upload Data",
        "Executive Summary":   "Executive Summary",
        "Issue Data":          "Issue Data",
    }
    return {
        nav_key: subs
        for tab_name, nav_key in _TAB_MAP.items()
        if tab_name in allowed and nav_key in _FULL_NAV_TREE
        for subs in [_FULL_NAV_TREE[nav_key]]
    }

NAV_TREE = _get_allowed_nav_tree()
# Profile / Admin Panel live in the "Users Control" group next to Logout
USER_PAGES = ["Profile"]
if _is_admin:
    USER_PAGES.append("Admin Panel")

if st.session_state.get('nav_page') not in NAV_TREE and st.session_state.get('nav_page') not in USER_PAGES:
    st.session_state.nav_page = "Dashboard"
if 'nav_sub' not in st.session_state:
    st.session_state.nav_sub = {}
if 'nav_token' not in st.session_state:
    st.session_state.nav_token = 0

if 'nav_expanded' not in st.session_state:
    st.session_state.nav_expanded = set()      # nothing expanded by default

def _go_nav(page_name, idx=None):
    st.session_state.nav_page = page_name
    if idx is not None:
        st.session_state.nav_sub[page_name] = idx
    st.session_state.nav_token += 1
    st.session_state.nav_target = {"page": page_name, "idx": idx if idx is not None else 0,
                                   "token": st.session_state.nav_token}

st.sidebar.markdown("""
<style>
/* ---- Sidebar navigation: aligned, subtle motion ---- */
section[data-testid="stSidebar"] div[class*="st-key-nav_"] button {
    justify-content: flex-start !important;
    text-align: left !important;
    border-radius: 8px !important;
    padding: 0.4rem 0.75rem !important;
    box-shadow: none !important;
    animation: none !important;
    transition: background-color .18s ease, transform .18s ease, border-color .18s ease !important;
}
section[data-testid="stSidebar"] div[class*="st-key-nav_"] button > div,
section[data-testid="stSidebar"] div[class*="st-key-nav_"] button p {
    justify-content: flex-start !important;
    text-align: left !important;
    width: 100%;
    margin: 0 !important;
}
section[data-testid="stSidebar"] div[class*="st-key-nav_"] button:hover {
    transform: translateX(3px) !important;
    animation: none !important;
}
section[data-testid="stSidebar"] div[class*="st-key-nav_"] button:active { transform: none !important; }
/* active page / tab = green */
section[data-testid="stSidebar"] div[class*="st-key-nav_"] button[kind="primary"],
section[data-testid="stSidebar"] div[class*="st-key-nav_"] button[data-testid="stBaseButton-primary"] {
    background-color: #27ae60 !important; border-color: #27ae60 !important; color: #ffffff !important;
}
section[data-testid="stSidebar"] div[class*="st-key-nav_"] button[kind="primary"] p,
section[data-testid="stSidebar"] div[class*="st-key-nav_"] button[data-testid="stBaseButton-primary"] p { color: #ffffff !important; }
section[data-testid="stSidebar"] div[class*="st-key-nav_"] button[kind="primary"]:hover,
section[data-testid="stSidebar"] div[class*="st-key-nav_"] button[data-testid="stBaseButton-primary"]:hover {
    background-color: #1e8449 !important; border-color: #1e8449 !important;
}
section[data-testid="stSidebar"] div[class*="st-key-nav_"] button[kind="primary"]:focus:not(:active),
section[data-testid="stSidebar"] div[class*="st-key-nav_"] button[data-testid="stBaseButton-primary"]:focus:not(:active) {
    border-color: #1e8449 !important; color: #ffffff !important; box-shadow: 0 0 0 0.15rem rgba(39,174,96,.35) !important;
}
section[data-testid="stSidebar"] div[class*="st-key-nav_sub_"] {
    width: calc(100% - 16px) !important;
    margin-left: 16px !important;
    border-left: none;
    padding-left: 0;
}
section[data-testid="stSidebar"] div[class*="st-key-nav_sub_"] button { font-size: 13px !important; padding: 0.3rem 0.6rem !important; }
/* active tab inside a page = blue (page stays green) */
section[data-testid="stSidebar"] div[class*="st-key-nav_sub_"] button[kind="primary"],
section[data-testid="stSidebar"] div[class*="st-key-nav_sub_"] button[data-testid="stBaseButton-primary"] {
    background-color: #2e86c1 !important; border-color: #2e86c1 !important; color: #ffffff !important;
}
section[data-testid="stSidebar"] div[class*="st-key-nav_sub_"] button[kind="primary"]:hover,
section[data-testid="stSidebar"] div[class*="st-key-nav_sub_"] button[data-testid="stBaseButton-primary"]:hover {
    background-color: #1f618d !important; border-color: #1f618d !important;
}
section[data-testid="stSidebar"] div[class*="st-key-nav_sub_"] button[kind="primary"]:focus:not(:active),
section[data-testid="stSidebar"] div[class*="st-key-nav_sub_"] button[data-testid="stBaseButton-primary"]:focus:not(:active) {
    border-color: #1f618d !important; box-shadow: 0 0 0 0.15rem rgba(46,134,193,.35) !important;
}
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 0.35rem; }
</style>
""", unsafe_allow_html=True)

st.sidebar.markdown("---")
st.sidebar.markdown("#### Navigation")
for _pg, _subs in NAV_TREE.items():
    _active = (st.session_state.nav_page == _pg)
    _open = _pg in st.session_state.nav_expanded
    _arrow = ("▾" if _open else "▸") if _subs else "•"
    if st.sidebar.button(f"{_arrow}  {_pg}", key=f"nav_pg_{_pg}",
                         use_container_width=True, type="primary" if _active else "secondary"):
        if _subs:
            if _open:
                st.session_state.nav_expanded.discard(_pg)      # collapse
            else:
                st.session_state.nav_expanded.add(_pg)          # expand
        if not _active:
            _go_nav(_pg)                                        # also open that page
        st.rerun()
    if _open and _subs:
        for _i, _sub in enumerate(_subs):
            _is_sub_active = _active and (st.session_state.nav_sub.get(_pg, 0) == _i)
            if st.sidebar.button(_sub, key=f"nav_sub_{_pg}_{_i}", use_container_width=True,
                                 type="primary" if _is_sub_active else "secondary"):
                _go_nav(_pg, _i)
                st.session_state.nav_close_sb = True
                st.rerun()

if st.session_state.pop('nav_close_sb', False):
    _inject_parent_js("""(function(){ if (window.innerWidth <= 768) {
        var b = document.querySelector('[data-testid="stSidebarCollapseButton"] button')
             || document.querySelector('[data-testid="stSidebarHeader"] button');
        if (b) { b.click(); } } })();""")

page = st.session_state.nav_page
st.sidebar.markdown("---")

# ===================================================
# NSOH SNAPSHOT MANAGEMENT - Sidebar (ADMIN ONLY)
# ===================================================
if st.session_state['user']['role'] == 'admin':
    with st.sidebar.expander("📊 NSOH Snapshot Management"):
        st.caption("Save NSOH snapshots for all materials")

        # Generate month-year options (last 24 months + next 6 months)
        today = date.today()
        month_options = []
        month_values = []

        # Generate last 24 months
        for i in range(24, -1, -1):
            month_date = today.replace(day=1) - timedelta(days=i*30)
            month_date = month_date.replace(day=1)
            month_label = month_date.strftime('%b-%Y')
            month_options.append(month_label)
            month_values.append(month_date)

        # Also include next 6 months
        for i in range(1, 7):
            month_date = today.replace(day=1) + timedelta(days=i*30)
            month_date = month_date.replace(day=1)
            month_label = month_date.strftime('%b-%Y')
            month_options.append(month_label)
            month_values.append(month_date)

        # Month selection for snapshot
        selected_month_label = st.selectbox(
            "📅 Select Month-Year to Save",
            month_options,
            index=24,  # Default to current month
            key="nsoh_snapshot_month"
        )

        # Find the date for the selected month
        selected_date = None
        for i, label in enumerate(month_options):
            if label == selected_month_label:
                selected_date = month_values[i]
                break

        if selected_date and not df_filtered.empty:
            # Single Save button - clean and simple
            if st.button("💾 Save", use_container_width=True, type="primary"):
                with st.spinner(f"Saving NSOH snapshots for {selected_month_label}..."):
                    # Prepare batch data
                    materials_data = []
                    for idx, row in df_filtered.iterrows():
                        material = row.get('Material Description')
                        if pd.isna(material):
                            continue

                        nsoh = row.get('NSOH', 0)
                        try:
                            nsoh = float(nsoh) if pd.notna(nsoh) else 0
                        except:
                            nsoh = 0

                        materials_data.append({
                            'material_description': material,
                            'nsoh': nsoh
                        })

                    # Batch save
                    success, saved_count = save_nsoh_snapshots_batch(materials_data, selected_date)

                    if success:
                        # Clear cache to refresh snapshot data
                        st.cache_data.clear()
                        st.session_state.nsoh_snapshots = load_nsoh_snapshots()
                        log_dashboard_update("Saved NSOH snapshot", selected_month_label, saved_count)
                        st.success(f"✅ Saved {saved_count} materials for {selected_month_label}")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("❌ Failed to save snapshots")
# ---------------------------------------------------
# Logout
# ---------------------------------------------------
st.sidebar.divider()
_USER_ICONS = {"Profile": "👤", "Admin Panel": "🛠️"}
if st.sidebar.button("🔄 Refresh", key="nav_refresh", use_container_width=True,
                     help="Reload the latest data from Supabase / Google Sheets"):
    try:
        st.cache_data.clear()
    except Exception:
        pass
    for _k in ('_main_frames_memo', '_kpi_lead_memo'):
        st.session_state.pop(_k, None)
    st.session_state['proc_cache_bust'] = st.session_state.get('proc_cache_bust', 0) + 1
    st.rerun()
st.sidebar.markdown("#### 👥 Users Control")
for _up in USER_PAGES:
    if st.sidebar.button(f"{_USER_ICONS.get(_up, '')}  {_up}", key="nav_user_" + _up.replace(" ", "_"),
                         use_container_width=True, type="primary" if page == _up else "secondary"):
        _go_nav(_up)
        st.session_state.nav_close_sb = True
        st.rerun()
if st.sidebar.button("🚪 Logout", key="nav_user_logout", use_container_width=True):
    st.session_state['auth'] = False
    st.session_state['user'] = None
    st.rerun()

if st.session_state.get('view_mode') == "mobile":
    st.markdown('''<style>
/* 📱 Mobile View: phone-sized single column layout on any screen */
.block-container { max-width: 480px !important; margin: 0 auto !important; padding-left: .6rem !important; padding-right: .6rem !important; }
</style>''', unsafe_allow_html=True)

render_floating_chatbot(df_filtered if 'df_filtered' in globals() and isinstance(df_filtered, pd.DataFrame) else df)

# ---------------------------------------------------
# Route to pages
# ---------------------------------------------------
if page == "Profile":
    show_profile_page()
    st.stop()
elif page == "Admin Panel" and st.session_state['user']['role'] == 'admin':
    show_admin_panel()
    st.stop()
elif page == "Upload Data" and _can_upload_data():
    show_upload_data_page()
    st.stop()
elif page == "Issue Data":
    # ===================================================
    # ISSUE DATA PAGE - WITH PROGRAM ORDER & PLANT A_AMC SECTION
    # ===================================================
    st.markdown("<h1 style='font-size: 32px; font-weight: bold; font-family: Times New Roman;' class='gradient-text'>📊 Issue Data Analysis</h1>", unsafe_allow_html=True)
    st.caption(f"Data as of: {st.session_state.data_timestamp.strftime('%Y-%m-%d %H:%M:%S')}")

    # Define Program Order
    PROGRAM_ORDER_LIST = [
        "Malaria",
        "HIV", 
        "OI and Hepatitis",
        "Hepatitis",
        "STI",
        "TB",
        "Drug Susceptible -TB Medicine (DS-TB)",
        "Drug Resisitance -TB Medicine (DR-TB)",
        "Leprosy Medicines",
        "Nutrition",
        "Lab TB",
        "TB diagnostics& Laboratory reagent",
        "TB Lab Supplies",
        "HIV Lab",
        "HIV VL Reagents",
        "CD4 ,AHD &HIV RTKs"
    ]

    # Check if Google Sheets data is available
    if google_sheets is None or len(google_sheets) == 0:
        st.error("Google Sheets data not available. Please check your Google Sheets connection.")
        st.stop()

    # Get materials from selected program in PROGRAM ORDER
    with st.spinner("Loading program materials from Google Sheets..."):
        if show_all_programs or len(selected_programs_list) == 0:
            all_program_materials = []
            for prog_name in PROGRAM_ORDER_LIST:
                if prog_name in google_sheets and 'Material Description' in google_sheets[prog_name].columns:
                    materials = google_sheets[prog_name]['Material Description'].dropna().tolist()
                    all_program_materials.extend(materials)
            for prog_name in google_sheets.keys():
                if prog_name not in PROGRAM_ORDER_LIST and 'Material Description' in google_sheets[prog_name].columns:
                    materials = google_sheets[prog_name]['Material Description'].dropna().tolist()
                    all_program_materials.extend(materials)
            program_materials = list(dict.fromkeys(all_program_materials))
        else:
            program_materials = []
            for prog_name in selected_programs_list:
                if prog_name in google_sheets and 'Material Description' in google_sheets[prog_name].columns:
                    materials = google_sheets[prog_name]['Material Description'].dropna().tolist()
                    program_materials.extend(materials)
            program_materials = list(dict.fromkeys(program_materials))

        if not program_materials:
            st.error(f"No material data found for selected programs.")
            st.stop()

    # Load ALL issue data from Supabase
    if st.session_state.supabase_client is None:
        st.error("Supabase client not initialized")
        st.stop()

    with st.spinner("Loading issue data from Supabase..."):
        all_data = []
        start = 0
        batch_size = 1000

        while True:
            try:
                result = (
                    st.session_state.supabase_client.table("issue_data")
                    .select("*")
                    .range(start, start + batch_size - 1)
                    .execute()
                )

                if not result.data:
                    break

                all_data.extend(result.data)
                start += batch_size

                if len(result.data) < batch_size:
                    break

            except Exception as e:
                st.error(f"Error loading data: {e}")
                break

        if not all_data:
            st.info("No issue data available. Please upload data to the issue_data table.")
            st.stop()

        issue_df = pd.DataFrame(all_data)

    # Rename columns
    column_rename = {
        'material_descr': 'Material Description',
        'plant': 'Plant',
        'delivery_date': 'Delivery Date',
        'region_descr': 'Region',
        'quantity': 'Quantity'
    }
    issue_df = issue_df.rename(columns=column_rename)

    # Clean data
    issue_df['Quantity'] = pd.to_numeric(issue_df['Quantity'], errors='coerce').fillna(0)
    if 'Delivery Date' in issue_df.columns:
        issue_df['Delivery Date'] = pd.to_datetime(issue_df['Delivery Date'], errors='coerce')

    # Filter by program materials
    issue_df = issue_df[issue_df['Material Description'].isin(program_materials)]

    if issue_df.empty:
        st.warning("No matching materials found between Issue Data and Google Sheets.")
        st.stop()

    # Remove Head Office from plants
    issue_df = issue_df[~issue_df['Plant'].str.contains('Head Office|HO01', case=False, na=False)]

    # ========== DATE RANGE FILTER ==========
    st.markdown("### 📅 Filter by Time (Delivery Date)")
    col_date1, col_date2 = st.columns(2)

    if 'Delivery Date' in issue_df.columns and issue_df['Delivery Date'].notna().any():
        min_date = issue_df['Delivery Date'].min().date()
        max_date = issue_df['Delivery Date'].max().date()

        with col_date1:
            start_date = st.date_input("From Date", value=min_date, min_value=min_date, max_value=max_date)
        with col_date2:
            end_date = st.date_input("To Date", value=max_date, min_value=min_date, max_value=max_date)

        mask = (issue_df['Delivery Date'].dt.date >= start_date) & (issue_df['Delivery Date'].dt.date <= end_date)
        display_issue_df = issue_df[mask].copy()
    else:
        display_issue_df = issue_df.copy()

    st.markdown("---")

    # ========== CALCULATE A_AMC (Overall and by Plant) — EXACT LAST 12 CALENDAR MONTHS ==========
    a_amc_overall = pd.DataFrame()
    plant_a_amc = pd.DataFrame()
    plant_amos_pivot = pd.DataFrame()

    if 'Delivery Date' in display_issue_df.columns and display_issue_df['Delivery Date'].notna().any():
        # Find the absolute latest delivery date in the whole dataset
        latest_date = display_issue_df['Delivery Date'].max()

        # Get the first day of that latest month
        latest_month_start = latest_date.replace(day=1)

        # Go back exactly 11 months to get the start of the 12-month window
        twelve_month_start = latest_month_start - pd.DateOffset(months=11)

        # Filter exactly to those 12 calendar months
        last_12_months = display_issue_df[display_issue_df['Delivery Date'] >= twelve_month_start].copy()

        if not last_12_months.empty:
            # Overall A_AMC (Average over the 12 months)
            last_12_months['YearMonth'] = last_12_months['Delivery Date'].dt.strftime('%Y-%m')
            monthly_totals = last_12_months.groupby(['Material Description', 'YearMonth'])['Quantity'].sum().reset_index()
            a_amc_calc = monthly_totals.groupby('Material Description')['Quantity'].mean().round(2)
            a_amc_overall = pd.DataFrame({
                'Material Description': a_amc_calc.index,
                'A_AMC': a_amc_calc.values.round(2)
            })

            # Calculate Plant A_AMC (Total over 12 months divided by 12)
            plant_last_12_months = last_12_months.groupby(['Material Description', 'Plant'])['Quantity'].sum().reset_index()
            plant_last_12_months['A_AMC'] = (plant_last_12_months['Quantity'] / 12).round(2)
            plant_a_amc = plant_last_12_months[['Material Description', 'Plant', 'A_AMC']]

            # ========== CALCULATE PLANT AMOS USING HSOH FROM HEALTH_DATA ==========
            if not plant_a_amc.empty and not df.empty:
                # Plant name mapping (issue_data -> health_data)
                issue_plants = plant_a_amc['Plant'].unique().tolist()
                health_branch_columns = [col for col in df.columns if 'Branch' in col and col != 'Material Description']

                plant_to_branch_mapping = {}

                for issue_plant in issue_plants:
                    matched_branch = None
                    plant_name_clean = issue_plant.split(' (')[0] if ' (' in issue_plant else issue_plant

                    if plant_name_clean in health_branch_columns:
                        matched_branch = plant_name_clean
                    else:
                        plant_name_lower = plant_name_clean.lower()
                        for branch_col in health_branch_columns:
                            if branch_col.lower() == plant_name_lower:
                                matched_branch = branch_col
                                break

                        if not matched_branch:
                            for branch_col in health_branch_columns:
                                branch_lower = branch_col.lower()
                                if plant_name_lower in branch_lower or branch_lower in plant_name_lower:
                                    matched_branch = branch_col
                                    break

                        if not matched_branch and ' (' in issue_plant and ')' in issue_plant:
                            code = issue_plant.split(' (')[1].replace(')', '')
                            code_lower = code.lower()
                            for branch_col in health_branch_columns:
                                if code_lower in branch_col.lower():
                                    matched_branch = branch_col
                                    break

                    if matched_branch:
                        plant_to_branch_mapping[issue_plant] = matched_branch

                # Build HSOH data
                hsoh_records = []

                for material in program_materials:
                    material_row = df[df['Material Description'] == material]
                    if material_row.empty:
                        continue

                    for issue_plant, branch_col in plant_to_branch_mapping.items():
                        if branch_col in material_row.columns:
                            hsoh_value = material_row[branch_col].iloc[0]
                            try:
                                hsoh_value = float(hsoh_value) if pd.notna(hsoh_value) else 0
                            except:
                                hsoh_value = 0

                            if hsoh_value > 0:
                                hsoh_records.append({
                                    'Material Description': material,
                                    'Plant': issue_plant,
                                    'HSOH': hsoh_value
                                })

                if hsoh_records:
                    hsoh_df = pd.DataFrame(hsoh_records)
                    plant_amos_df = hsoh_df.merge(
                        plant_a_amc,
                        on=['Material Description', 'Plant'],
                        how='inner'
                    )

                    if not plant_amos_df.empty:
                        plant_amos_df['AMOS'] = np.where(
                            plant_amos_df['A_AMC'] > 0,
                            plant_amos_df['HSOH'] / plant_amos_df['A_AMC'],
                            0
                        ).round(2)

                        plant_amos_pivot = plant_amos_df.pivot_table(
                            index='Material Description',
                            columns='Plant',
                            values='AMOS',
                            fill_value=0
                        ).round(2)

                        plant_amos_pivot = plant_amos_pivot.reindex([m for m in program_materials if m in plant_amos_pivot.index])

    # Create ordered material list based on program order
    ordered_materials = [m for m in program_materials if m in display_issue_df['Material Description'].values]

    # ========== DETAILED ISSUE DATA TABLES - 5 TABS ==========
    st.markdown("<h3 style='font-size: 24px; font-weight: bold;'>📋 Detailed Issue Data Tables</h3>", unsafe_allow_html=True)

    detail_tab1, detail_tab2, detail_tab3, detail_tab4, detail_tab5 = st.tabs([
        "📋 Issue Data by Time", 
        "🏭 Issue Data by Plant", 
        "📊 Plant A_AMC",
        "📈 Plant AMOS",
        "🗺️ Issue Data by Region"
    ])

    with detail_tab1:
        st.markdown("#### Material vs Month (with Overall A_AMC)")

        if 'Delivery Date' in display_issue_df.columns:
            monthly_detail = display_issue_df.copy()
            monthly_detail['Month'] = monthly_detail['Delivery Date'].dt.strftime('%b-%Y')
            monthly_pivot = monthly_detail.groupby(['Material Description', 'Month'])['Quantity'].sum().reset_index()
            monthly_table = monthly_pivot.pivot_table(index='Material Description', columns='Month', values='Quantity', fill_value=0)

            month_order = sorted(monthly_table.columns, key=lambda x: pd.to_datetime(x, format='%b-%Y'))
            monthly_table = monthly_table[month_order]
            monthly_table = monthly_table.reindex([m for m in ordered_materials if m in monthly_table.index])

            monthly_table = monthly_table.reset_index()
            if not a_amc_overall.empty:
                monthly_table = monthly_table.merge(a_amc_overall, on='Material Description', how='left')
                monthly_table['A_AMC'] = monthly_table['A_AMC'].fillna(0).round(2)
                cols = ['Material Description', 'A_AMC'] + [c for c in monthly_table.columns if c not in ['Material Description', 'A_AMC']]
                monthly_table = monthly_table[cols]

            monthly_table = monthly_table.set_index('Material Description')
            st.dataframe(monthly_table, use_container_width=True, height=500)

            st.download_button(
                label="📥 Download Material vs Month Data",
                data=monthly_table.reset_index().pipe(_xl),
                file_name=f"issue_data_monthly_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    with detail_tab2:
        st.markdown("#### Material vs Plant (Actual Issue Quantities)")

        plant_table = display_issue_df.groupby(['Material Description', 'Plant'])['Quantity'].sum().reset_index()
        plant_pivot_table = plant_table.pivot_table(index='Material Description', columns='Plant', values='Quantity', fill_value=0)
        plant_pivot_table = plant_pivot_table.reindex([m for m in ordered_materials if m in plant_pivot_table.index])

        st.dataframe(plant_pivot_table, use_container_width=True, height=500)

        st.download_button(
            label="📥 Download Material vs Plant Data",
            data=plant_pivot_table.reset_index().pipe(_xl),
            file_name=f"issue_data_plant_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    with detail_tab3:
        st.markdown("#### Plant A_AMC (Average Monthly Consumption)")
        st.caption("A_AMC by Plant = Total issue quantity from the last 12 calendar months of data divided by 12 months")

        if not plant_a_amc.empty:
            a_amc_pivot = plant_a_amc.pivot_table(
                index='Material Description', 
                columns='Plant', 
                values='A_AMC',
                fill_value=0
            ).round(2)
            a_amc_pivot = a_amc_pivot.reindex([m for m in ordered_materials if m in a_amc_pivot.index])

            st.dataframe(a_amc_pivot, use_container_width=True, height=500)

            st.download_button(
                label="📥 Download Plant A_AMC Data",
                data=a_amc_pivot.reset_index().pipe(_xl),
                file_name=f"plant_a_amc_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.info("No data available for A_AMC calculation. Need at least 12 months of delivery data.")

    with detail_tab4:
        st.markdown("#### Plant AMOS (Actual Month of Stock)")
        st.caption("AMOS = HSOH (from health_data) ÷ Plant A_AMC (from issue_data)")

        if not plant_amos_pivot.empty:
            st.dataframe(plant_amos_pivot, use_container_width=True, height=500)

            st.download_button(
                label="📥 Download Plant AMOS Data",
                data=plant_amos_pivot.reset_index().pipe(_xl),
                file_name=f"plant_amos_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.info("No AMOS data available. Need both HSOH (from health_data) and Plant A_AMC (from issue_data).")

    with detail_tab5:
        st.markdown("#### Material vs Region")

        region_table = display_issue_df.groupby(['Material Description', 'Region'])['Quantity'].sum().reset_index()
        region_pivot_table = region_table.pivot_table(index='Material Description', columns='Region', values='Quantity', fill_value=0)
        region_pivot_table = region_pivot_table.reindex([m for m in ordered_materials if m in region_pivot_table.index])

        st.dataframe(region_pivot_table, use_container_width=True, height=500)

        st.download_button(
            label="📥 Download Material vs Region Data",
            data=region_pivot_table.reset_index().pipe(_xl),
            file_name=f"issue_data_region_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    st.markdown("---")

    # ========== ANALYSIS 1: BY TIME ==========
    st.markdown("<h3 style='font-size: 24px; font-weight: bold;'>📅 Analysis by Time (Delivery Date)</h3>", unsafe_allow_html=True)

    if 'Delivery Date' in display_issue_df.columns and display_issue_df['Delivery Date'].notna().any():
        time_df = display_issue_df.copy()
        time_df['Year'] = time_df['Delivery Date'].dt.year
        time_df['Month'] = time_df['Delivery Date'].dt.strftime('%b-%Y')
        time_df['Quarter'] = time_df['Delivery Date'].dt.to_period('Q').astype(str)

        monthly_trend = time_df.groupby('Month')['Quantity'].sum().reset_index()
        monthly_trend['Sort_Date'] = pd.to_datetime(monthly_trend['Month'], format='%b-%Y')
        monthly_trend = monthly_trend.sort_values('Sort_Date')

        col_a1, col_a2 = st.columns(2)

        with col_a1:
            fig_monthly = px.line(
                monthly_trend, 
                x='Month', 
                y='Quantity',
                title='Monthly Issue Quantity Trend',
                markers=True,
                labels={'Quantity': 'Total Quantity', 'Month': 'Month'}
            )
            fig_monthly.update_layout(height=400, xaxis_tickangle=-45)
            st.plotly_chart(fig_monthly, use_container_width=True)

        with col_a2:
            yearly_trend = time_df.groupby('Year')['Quantity'].sum().reset_index()
            fig_yearly = px.bar(
                yearly_trend,
                x='Year',
                y='Quantity',
                title='Yearly Issue Quantity',
                color='Quantity',
                color_continuous_scale='Blues',
                text='Quantity'
            )
            fig_yearly.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
            fig_yearly.update_layout(height=400)
            st.plotly_chart(fig_yearly, use_container_width=True)

        quarterly_trend = time_df.groupby('Quarter')['Quantity'].sum().reset_index()
        fig_quarterly = px.bar(
            quarterly_trend,
            x='Quarter',
            y='Quantity',
            title='Quarterly Issue Quantity Trend',
            color='Quantity',
            color_continuous_scale='Viridis'
        )
        fig_quarterly.update_layout(height=400)
        st.plotly_chart(fig_quarterly, use_container_width=True)

    st.markdown("---")

    # ========== ANALYSIS 2: BY PLANT (with pagination) ==========
    st.markdown("<h3 style='font-size: 24px; font-weight: bold;'>🏭 Analysis by Plant (Hubs)</h3>", unsafe_allow_html=True)

    if 'Plant' in display_issue_df.columns:
        plant_summary = display_issue_df.groupby('Plant').agg({
            'Quantity': ['sum', 'mean', 'count']
        }).round(2)
        plant_summary.columns = ['Total Quantity', 'Avg Quantity', 'Number of Records']
        plant_summary = plant_summary.sort_values('Total Quantity', ascending=False).reset_index()

        col_p1, col_p2 = st.columns(2)

        with col_p1:
            top_plants = plant_summary.head(10)
            fig_plants = px.bar(
                top_plants,
                x='Plant',
                y='Total Quantity',
                title='Top 10 Plants by Issue Quantity',
                color='Total Quantity',
                color_continuous_scale='Reds',
                text='Total Quantity'
            )
            fig_plants.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
            fig_plants.update_layout(height=450, xaxis_tickangle=-45)
            st.plotly_chart(fig_plants, use_container_width=True)

        with col_p2:
            fig_plant_pie = px.pie(
                plant_summary.head(8),
                values='Total Quantity',
                names='Plant',
                title='Issue Distribution by Plant (Top 8)'
            )
            fig_plant_pie.update_traces(textposition='inside', textinfo='percent+label')
            fig_plant_pie.update_layout(height=450)
            st.plotly_chart(fig_plant_pie, use_container_width=True)

        # Plant vs Material heatmap with pagination
        st.markdown("#### 🔥 Plant vs Material - Issue Quantity Heatmap")

        plant_pivot = display_issue_df.groupby(['Plant', 'Material Description'])['Quantity'].sum().reset_index()
        plant_pivot = plant_pivot.pivot_table(index='Plant', columns='Material Description', values='Quantity', fill_value=0)

        all_materials = [m for m in ordered_materials if m in plant_pivot.columns]
        total_materials = len(all_materials)

        if 'plant_heatmap_page' not in st.session_state:
            st.session_state.plant_heatmap_page = 1

        materials_per_page = 10
        total_pages = (total_materials + materials_per_page - 1) // materials_per_page if total_materials > 0 else 1

        if total_pages > 1:
            col_prev, col_page, col_next = st.columns([1, 2, 1])
            with col_prev:
                if st.button("◀ Previous", key="plant_heatmap_prev") and st.session_state.plant_heatmap_page > 1:
                    st.session_state.plant_heatmap_page -= 1
                    st.rerun()
            with col_page:
                st.markdown(f"<p style='text-align: center;'>Page {st.session_state.plant_heatmap_page} of {total_pages}</p>", unsafe_allow_html=True)
            with col_next:
                if st.button("Next ▶", key="plant_heatmap_next") and st.session_state.plant_heatmap_page < total_pages:
                    st.session_state.plant_heatmap_page += 1
                    st.rerun()

        start_idx = (st.session_state.plant_heatmap_page - 1) * materials_per_page
        end_idx = min(start_idx + materials_per_page, total_materials)
        page_materials = all_materials[start_idx:end_idx]
        plant_pivot_page = plant_pivot[page_materials]

        fig_plant_heatmap = go.Figure(data=go.Heatmap(
            z=plant_pivot_page.values,
            y=plant_pivot_page.index,
            x=plant_pivot_page.columns,
            colorscale='Reds',
            text=plant_pivot_page.values,
            texttemplate='%{text:,.0f}',
            textfont={"size": 10},
            colorbar=dict(title="Quantity")
        ))
        fig_plant_heatmap.update_layout(
            xaxis_tickangle=-45,
            xaxis={'title': 'Material Description', 'tickfont': {'size': 10}},
            yaxis={'title': 'Plant'},
            height=max(400, 35 * len(plant_pivot_page) + 100),
            margin=dict(l=150, r=50, t=50, b=250)
        )
        st.plotly_chart(fig_plant_heatmap, use_container_width=True)

        # ============================================================
        # 🔥 PLANT VS MATERIAL - ACTUAL MONTH OF STOCK (AMOS) HEATMAP
        # ============================================================
        st.markdown("#### 🔥 Plant vs Material - Actual Month of Stock (AMOS)")
        st.caption("AMOS = HSOH (from health_data) ÷ Plant A_AMC (from issue_data)")

        if not plant_amos_pivot.empty:
            amos_pivot_transposed = plant_amos_pivot.T

            if 'page_materials' in dir() and page_materials:
                available_materials = [m for m in page_materials if m in amos_pivot_transposed.columns]
                if available_materials:
                    amos_pivot_page = amos_pivot_transposed[available_materials]
                else:
                    amos_pivot_page = amos_pivot_transposed.iloc[:, :min(10, len(amos_pivot_transposed.columns))]
            else:
                amos_pivot_page = amos_pivot_transposed.iloc[:, :min(10, len(amos_pivot_transposed.columns))]

            max_amos = amos_pivot_page.max().max() if not amos_pivot_page.empty else 12
            z_max = max(6, max_amos) if max_amos > 0 else 6

            pos_0_5 = 0.5 / z_max
            pos_1 = 1.0 / z_max
            pos_2 = 2.0 / z_max
            pos_4 = 4.0 / z_max
            pos_6 = 6.0 / z_max

            amos_colorscale = [
                [0.0, '#ff0000'],
                [pos_0_5, '#ff0000'],
                [pos_0_5 + 0.001, '#ff6600'],
                [pos_1, '#ff6600'],
                [pos_1 + 0.001, '#ffff00'],
                [pos_2, '#ffff00'],
                [pos_2 + 0.001, '#33cc33'],
                [pos_4, '#33cc33'],
                [pos_4 + 0.001, '#3366ff'],
                [pos_6, '#3366ff'],
                [pos_6 + 0.001, '#66ccff'],
                [1.0, '#66ccff']
            ]

            fig_amos_heatmap = go.Figure(data=go.Heatmap(
                z=amos_pivot_page.values,
                y=amos_pivot_page.index,
                x=amos_pivot_page.columns,
                colorscale=amos_colorscale,
                zmin=0,
                zmax=z_max,
                text=amos_pivot_page.values.round(2),
                texttemplate='%{text}',
                textfont={"size": 10},
                colorbar=dict(
                    title="AMOS (Months)",
                    tickvals=[0, 0.5, 1, 2, 4, 6],
                    ticktext=['0', '0.5', '1', '2', '4', '6']
                ),
                hovertemplate='<b>Material:</b> %{x}<br><b>Plant:</b> %{y}<br><b>AMOS:</b> %{z:.2f} months<br><extra></extra>'
            ))
            fig_amos_heatmap.update_layout(
                xaxis_tickangle=-45,
                xaxis={'title': 'Material Description', 'tickfont': {'size': 10}},
                yaxis={'title': 'Plant'},
                height=max(400, 35 * len(amos_pivot_page) + 100),
                margin=dict(l=150, r=50, t=50, b=250)
            )
            st.plotly_chart(fig_amos_heatmap, use_container_width=True)

            st.markdown("""
            <div style='background: #f8f9fa; padding: 10px; border-radius: 5px; margin-top: 10px;'>
                <p style='margin: 0; font-weight: bold;'>📊 AMOS Legend:</p>
                <div style='display: flex; gap: 15px; flex-wrap: wrap; margin-top: 5px;'>
                    <span><span style='background-color: #ff0000; padding: 2px 10px; border-radius: 3px; color: white;'>&lt;0.5</span> Stock Out</span>
                    <span><span style='background-color: #ff6600; padding: 2px 10px; border-radius: 3px; color: white;'>0.5-1</span> Understock</span>
                    <span><span style='background-color: #ffff00; padding: 2px 10px; border-radius: 3px; color: black;'>1-2</span> Low Normal</span>
                    <span><span style='background-color: #33cc33; padding: 2px 10px; border-radius: 3px; color: white;'>2-4</span> Normal</span>
                    <span><span style='background-color: #3366ff; padding: 2px 10px; border-radius: 3px; color: white;'>4-6</span> High</span>
                    <span><span style='background-color: #66ccff; padding: 2px 10px; border-radius: 3px; color: black;'>&gt;6</span> Very High</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("No AMOS data available for heatmap. Need both HSOH (from health_data) and Plant A_AMC (from issue_data).")

    st.markdown("---")

    # ========== ANALYSIS 3: BY REGION (with pagination) ==========
    st.markdown("<h3 style='font-size: 24px; font-weight: bold;'>🗺️ Analysis by Region</h3>", unsafe_allow_html=True)

    if 'Region' in display_issue_df.columns:
        region_summary = display_issue_df.groupby('Region').agg({
            'Quantity': ['sum', 'mean', 'count']
        }).round(2)
        region_summary.columns = ['Total Quantity', 'Avg Quantity', 'Number of Records']
        region_summary = region_summary.sort_values('Total Quantity', ascending=False).reset_index()

        col_r1, col_r2 = st.columns(2)

        with col_r1:
            fig_regions = px.bar(
                region_summary,
                x='Region',
                y='Total Quantity',
                title='Issue Quantity by Region',
                color='Total Quantity',
                color_continuous_scale='Oranges',
                text='Total Quantity'
            )
            fig_regions.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
            fig_regions.update_layout(height=450, xaxis_tickangle=-45)
            st.plotly_chart(fig_regions, use_container_width=True)

        with col_r2:
            fig_region_pie = px.pie(
                region_summary,
                values='Total Quantity',
                names='Region',
                title='Issue Distribution by Region'
            )
            fig_region_pie.update_traces(textposition='inside', textinfo='percent+label')
            fig_region_pie.update_layout(height=450)
            st.plotly_chart(fig_region_pie, use_container_width=True)

        # Region vs Material heatmap
        st.markdown("#### 🔥 Region vs Material - Issue Quantity Heatmap")

        region_pivot = display_issue_df.groupby(['Region', 'Material Description'])['Quantity'].sum().reset_index()
        region_pivot = region_pivot.pivot_table(index='Region', columns='Material Description', values='Quantity', fill_value=0)

        if 'page_materials' in dir() and page_materials:
            region_pivot_page = region_pivot[page_materials]
        else:
            region_pivot_page = region_pivot.iloc[:, :10]

        fig_region_heatmap = go.Figure(data=go.Heatmap(
            z=region_pivot_page.values,
            y=region_pivot_page.index,
            x=region_pivot_page.columns,
            colorscale='Oranges',
            text=region_pivot_page.values,
            texttemplate='%{text:,.0f}',
            textfont={"size": 10},
            colorbar=dict(title="Quantity")
        ))
        fig_region_heatmap.update_layout(
            xaxis_tickangle=-45,
            xaxis={'title': 'Material Description', 'tickfont': {'size': 10}},
            yaxis={'title': 'Region'},
            height=max(400, 35 * len(region_pivot_page) + 100),
            margin=dict(l=150, r=50, t=50, b=250)
        )
        st.plotly_chart(fig_region_heatmap, use_container_width=True)

    st.markdown("---")

    # ========== EXPORT ALL DATA ==========
    st.markdown("<h3 style='font-size: 20px; font-weight: bold;'>📥 Export All Filtered Data</h3>", unsafe_allow_html=True)

    st.download_button(
        label="📊 Download Full Issue Data (Excel)",
        data=display_issue_df.pipe(_xl),
        file_name=f"issue_data_full_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

    st.stop()
elif page == "Advanced Analytics":
    # ===================================================
    # ADVANCED ANALYTICS PAGE (Condensed for length)
    # ===================================================
    st.markdown("<h1 style='font-size: 32px; font-weight: bold; font-family: Times New Roman;' class='gradient-text'>Advanced Analytics Dashboard</h1>", unsafe_allow_html=True)

    # Section selector (linked to the sidebar) - only the selected section is rendered
    _apply_nav_target("Advanced Analytics", 7, "tabs")
    aa_tab1, aa_tab2, aa_tab3, aa_tab4, aa_tab5, aa_tab6, aa_tab9 = _tabs_for("Advanced Analytics")

    # ========== TAB 1: Branch Ranking ==========
    with aa_tab1:
        if _tab_open(aa_tab1):
            st.markdown("<h3 style='font-size: 24px; font-weight: bold;'>Branch Ranking</h3>", unsafe_allow_html=True)
            st.caption("Availability = materials with HMOS ≥ 0.5 (at least 2 weeks of stock)")
            st.caption("Ranking based on: Availability Score (0-4) + Avg HMOS Score (0-2) + Stock-out Score (0-3) = Max 9 points")

            if branch_amc_data is not None and not branch_amc_data.empty:
                branch_stock_cols = [col for col in df.columns if 'Branch' in col and col != 'Material Description']
                amc_branch_cols = [col for col in branch_amc_data.columns if col != 'Material Description']
                rankings = []

                for amc_branch in amc_branch_cols:
                    if amc_branch == 'Material Description':
                        continue

                    stock_col = None
                    for bc in branch_stock_cols:
                        if amc_branch == bc:
                            stock_col = bc
                            break

                    if stock_col:
                        try:
                            merged = pd.merge(
                                df[['Material Description', stock_col]], 
                                branch_amc_data[['Material Description', amc_branch]], 
                                on='Material Description', 
                                how='inner'
                            )

                            if not merged.empty:
                                stock_values = pd.to_numeric(merged[stock_col + '_x'], errors='coerce').fillna(0)
                                amc_values = pd.to_numeric(merged[amc_branch + '_y'], errors='coerce').fillna(1)
                                amc_values = amc_values.replace(0, 1)
                                branch_hmos = (stock_values / amc_values).values

                                Availability_count = np.sum(branch_hmos >= 0.5)
                                total_materials = len(branch_hmos)
                                Availability_pct = (Availability_count / total_materials * 100) if total_materials > 0 else 0
                                valid_hmos = branch_hmos[branch_hmos > 0]
                                avg_hmos = np.mean(valid_hmos) if len(valid_hmos) > 0 else 0
                                stock_out_materials = total_materials - Availability_count

                                # Scoring System
                                if Availability_pct == 100:
                                    Availability_points = 4
                                elif Availability_pct >= 85:
                                    Availability_points = 3
                                elif Availability_pct >= 75:
                                    Availability_points = 2
                                elif Availability_pct >= 55:
                                    Availability_points = 1
                                else:
                                    Availability_points = 0

                                if 2 <= avg_hmos <= 4:
                                    hmos_points = 2
                                elif (1 <= avg_hmos < 2) or (4 < avg_hmos <= 6):
                                    hmos_points = 1
                                else:
                                    hmos_points = 0

                                if stock_out_materials <= 10:
                                    stockout_points = 3
                                elif stock_out_materials <= 20:
                                    stockout_points = 2
                                else:
                                    stockout_points = 0

                                total_score = Availability_points + hmos_points + stockout_points

                                if total_score >= 8:
                                    rating = "🏆 EXCELLENT"
                                elif total_score >= 6:
                                    rating = "✅ GOOD"
                                elif total_score >= 4:
                                    rating = "⚠️ AVERAGE"
                                elif total_score >= 2:
                                    rating = "📉 BELOW AVERAGE"
                                else:
                                    rating = "🔴 CRITICAL"

                                rankings.append({
                                    'Branch': amc_branch,
                                    'Availability %': round(Availability_pct, 1),
                                    'Availability Points': Availability_points,
                                    'Avg HMOS': round(avg_hmos, 2),
                                    'HMOS Points': hmos_points,
                                    'Stock-outs': stock_out_materials,
                                    'Stock-out Points': stockout_points,
                                    'Total Score': total_score,
                                    'Rating': rating,
                                    'Total Materials': total_materials
                                })
                        except Exception:
                            continue

                if rankings:
                    rankings_df = pd.DataFrame(rankings).sort_values('Total Score', ascending=False)
                    rankings_df['Rank'] = range(1, len(rankings_df) + 1)

                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("🏆 Top Branch", rankings_df.iloc[0]['Branch'])
                        st.metric("📊 Best Score", f"{rankings_df.iloc[0]['Total Score']}/9 points")
                    with col2:
                        st.metric("📉 Bottom Branch", rankings_df.iloc[-1]['Branch'])
                        st.metric("⚠️ Worst Score", f"{rankings_df.iloc[-1]['Total Score']}/9 points")

                    st.markdown("---")

                    st.dataframe(
                        rankings_df[['Rank', 'Branch', 'Availability %', 'Availability Points', 
                                    'Avg HMOS', 'HMOS Points', 'Stock-outs', 
                                    'Stock-out Points', 'Total Score', 'Rating']],
                        use_container_width=True,
                        hide_index=True
                    )

                    fig = px.bar(rankings_df, x='Branch', y='Total Score', color='Total Score',
                                color_continuous_scale='RdYlGn', title='Branch Performance Scores (Max 9 points)',
                                text='Total Score', range_y=[0, 9])
                    fig.add_hline(y=6, line_dash="dash", line_color="green", annotation_text="Good (6+)")
                    fig.add_hline(y=3, line_dash="dash", line_color="red", annotation_text="Poor (<3)")
                    fig.update_traces(textposition='outside')
                    fig.update_layout(height=500, xaxis_tickangle=-45)
                    st.plotly_chart(fig, use_container_width=True)

                    with st.expander("📖 Scoring System Explanation", expanded=False):
                        st.markdown("""
                    **Branch Ranking Scoring System (Max 9 points)**

                    **1. Availability Points (0-4)**
                    - 100% = 4 points | 85-99% = 3 points | 75-84% = 2 points | 55-74% = 1 point | <55% = 0 points

                    **2. Avg HMOS Points (0-2)**
                    - 2-4 months = 2 points | 1-2 or 4-6 months = 1 point | Otherwise = 0 points

                    **3. Stock-out Points (0-3)**
                    - 0-10 stock-outs = 3 points | 10-20 stock-outs = 2 points | >20 stock-outs = 0 points
                    """)

                    st.download_button("📥 Download Branch Ranking Data (Excel)", 
                                      data=rankings_df.pipe(_xl),
                                      file_name=f"branch_ranking_{datetime.now().strftime('%Y%m%d')}.xlsx",
                                      mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
                else:
                    st.info("No branch data available for ranking")
            else:
                st.info("Branch AMC data not available")

    # ========== TAB 2: Redistribution Recommendations ==========
    with aa_tab2:
        if _tab_open(aa_tab2):
            st.markdown("<h3 style='font-size: 24px; font-weight: bold;'>Stock Redistribution Recommendations</h3>", unsafe_allow_html=True)
            st.info("""
        **Redistribution Criteria:**
        - Trigger: Expiry Risk **OR** Understock (National NMOS < 6) **OR** Branch HMOS > 8
        - Source Branch: HMOS > 8
        - Target Branch: HMOS < 0.5
        - Target HMOS after transfer: 5 months
        """)

            if branch_amc_data is not None and not branch_amc_data.empty:
                branch_stock_cols = [col for col in df.columns if 'Branch' in col and col != 'Material Description']
                amc_branch_cols = [col for col in branch_amc_data.columns if col != 'Material Description']
                recommendations = []

                df_aligned = df.set_index('Material Description')
                amc_aligned = branch_amc_data.set_index('Material Description')
                common_materials = df_aligned.index.intersection(amc_aligned.index)

                for material in list(common_materials):
                    material_row = df[df['Material Description'] == material]
                    if material_row.empty:
                        continue

                    has_expiry_risk = material_row.iloc[0].get('Has Expiry Risk', False)
                    national_nmos = material_row.iloc[0].get('NMOS', 10)
                    if pd.isna(national_nmos):
                        national_nmos = 10

                    is_understock = national_nmos < levels_for([material])[0][0]
                    trigger = has_expiry_risk or is_understock

                    if not trigger:
                        continue

                    branch_hmos = {}
                    branch_stock = {}
                    branch_amc_val = {}

                    for amc_branch in amc_branch_cols:
                        stock_col = None
                        for bc in branch_stock_cols:
                            if amc_branch == bc:
                                stock_col = bc
                                break

                        if stock_col and stock_col in df_aligned.columns:
                            try:
                                stock = pd.to_numeric(df_aligned.loc[material, stock_col], errors='coerce')
                                amc = pd.to_numeric(amc_aligned.loc[material, amc_branch], errors='coerce')
                                if pd.isna(stock):
                                    stock = 0
                                if pd.isna(amc) or amc <= 0:
                                    amc = 1
                                hmos = stock / amc
                                branch_hmos[amc_branch] = hmos
                                branch_stock[amc_branch] = stock
                                branch_amc_val[amc_branch] = amc
                            except Exception:
                                continue

                    overstocked = [b for b, hmos in branch_hmos.items() if hmos > 8]
                    understocked = [b for b, hmos in branch_hmos.items() if 0 < hmos < 0.5]

                    for source in overstocked:
                        for target in understocked:
                            if source != target:
                                excess = (branch_hmos[source] - 5) * branch_amc_val[source]
                                deficit = (5 - branch_hmos[target]) * branch_amc_val[target]
                                transfer_qty = min(max(0, excess), max(0, deficit))

                                if transfer_qty > 0 and transfer_qty >= branch_amc_val[target]:
                                    if has_expiry_risk and is_understock:
                                        priority = "URGENT"
                                    elif has_expiry_risk or is_understock:
                                        priority = "HIGH"
                                    else:
                                        priority = "MEDIUM"

                                    recommendations.append({
                                        'Material': material,
                                        'Trigger': ('Expiry Risk' if has_expiry_risk else '') + (' + Understock' if is_understock else ''),
                                        'Source Branch': source,
                                        'Target Branch': target,
                                        'Source HMOS': round(branch_hmos[source], 2),
                                        'Target HMOS': round(branch_hmos[target], 2),
                                        'Recommended Transfer Qty': int(transfer_qty),
                                        'Priority': priority
                                    })

                if recommendations:
                    st.dataframe(pd.DataFrame(recommendations), use_container_width=True, hide_index=True)
                    total_qty = sum(r['Recommended Transfer Qty'] for r in recommendations)
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("🔄 Total Transfer Opportunities", len(recommendations))
                    with col2:
                        st.metric("📦 Total Recommended Transfer", f"{int(total_qty):,} units")
                    with col3:
                        urgent = len([r for r in recommendations if r['Priority'] == 'URGENT'])
                        st.metric("⚠️ Urgent Transfers", urgent)
                    st.download_button("📥 Download Redistribution Plan", 
                                      pd.DataFrame(recommendations).pipe(_xl), 
                                      "redistribution_plan.xlsx")
                else:
                    st.success("✅ No redistribution opportunities identified.")
            else:
                st.info("Branch AMC data not available")

    # ========== TAB 3: Critical Alerts ==========
    with aa_tab3:
        if _tab_open(aa_tab3):
            st.markdown("<h3 style='font-size: 24px; font-weight: bold;'>Critical Stock-Out Alerts</h3>", unsafe_allow_html=True)

            critical_items = []
            for idx, row in df_filtered.iterrows():
                nmos = row.get('NMOS', 0)
                if pd.notna(nmos) and nmos < 0.5:
                    rec = get_stock_out_recommendation(row)
                    critical_items.append({
                        'Material': row['Material Description'],
                        'NMOS': round(nmos, 2),
                        'NSOH': row.get('NSOH', 0),
                        'AMC': row.get('AMC', 0),
                        'Stock Status': 'CRITICAL STOCK OUT',
                        'Recommendation': rec
                    })
                elif pd.notna(nmos) and nmos < 1:
                    rec = get_stock_out_recommendation(row)
                    critical_items.append({
                        'Material': row['Material Description'],
                        'NMOS': round(nmos, 2),
                        'NSOH': row.get('NSOH', 0),
                        'AMC': row.get('AMC', 0),
                        'Stock Status': 'STOCK OUT',
                        'Recommendation': rec
                    })

            if critical_items:
                critical_df = pd.DataFrame(critical_items)
                st.error(f"⚠️ {len(critical_items)} critical items requiring immediate attention!")
                col1, col2 = st.columns(2)
                with col1:
                    critical_count = len([c for c in critical_items if c['Stock Status'] == 'CRITICAL STOCK OUT'])
                    st.metric("🔴 Critical Stock-Outs", critical_count, delta="URGENT", delta_color="inverse")
                with col2:
                    stockout_count = len([c for c in critical_items if c['Stock Status'] == 'STOCK OUT'])
                    st.metric("🟡 Stock Out", stockout_count)
                st.dataframe(critical_df, use_container_width=True, hide_index=True)
                if st.button("📧 Send Email Alerts (Simulated)"):
                    st.success(f"✅ Email alert would be sent to supply chain team with {len(critical_items)} critical items")
            else:
                st.success("✅ No critical stock-outs detected. All materials have adequate stock levels!")

    # ========== TAB 4: Expiry Notifications ==========
    with aa_tab4:
        if _tab_open(aa_tab4):
            st.markdown("<h3 style='font-size: 24px; font-weight: bold;'>Expiring Stock Notifications</h3>", unsafe_allow_html=True)

            notifications = []
            current_date = datetime.now()

            for idx, row in df_filtered.iterrows():
                expiry_str = row.get('Expiry', '')
                if pd.isna(expiry_str) or expiry_str == '':
                    continue

                amc = row.get('AMC', 0)
                try:
                    amc = float(amc) if pd.notna(amc) else 0
                except:
                    amc = 0

                if amc <= 0:
                    continue

                pattern = r'(\d[\d,]*)\s*\(([A-Za-z]+)-(\d{4})\)'
                matches = re.findall(pattern, str(expiry_str))
                month_map = {'Jan':1, 'Feb':2, 'Mar':3, 'Apr':4, 'May':5, 'Jun':6,
                            'Jul':7, 'Aug':8, 'Sep':9, 'Oct':10, 'Nov':11, 'Dec':12}

                for qty_str, month, year in matches:
                    try:
                        qty = float(qty_str.replace(',', ''))
                        month_num = month_map.get(month[:3], 1)
                        expiry_date = datetime(int(year), month_num, 1)
                        months_to_expiry = (expiry_date.year - current_date.year) * 12 + (expiry_date.month - current_date.month)
                        months_of_stock_this_batch = qty / amc

                        if months_of_stock_this_batch <= months_to_expiry:
                            continue

                        if months_to_expiry <= 3:
                            priority = "🔴 CRITICAL"
                        elif months_to_expiry <= 6:
                            priority = "🟡 HIGH"
                        elif months_to_expiry <= 12:
                            priority = "🔵 MEDIUM"
                        else:
                            continue

                        rec = get_expiry_risk_recommendation(row)

                        notifications.append({
                            'Material': row['Material Description'],
                            'Priority': priority,
                            'Message': f"{int(qty):,} units expiring in {months_to_expiry} month(s)",
                            'Recommendation': rec,
                            'Quantity': int(qty),
                            'Expiry Date': expiry_date.strftime('%b-%Y'),
                            'Months Left': months_to_expiry,
                            'Months to Consume': round(months_of_stock_this_batch, 1)
                        })
                    except:
                        continue

            if notifications:
                notif_df = pd.DataFrame(notifications).sort_values('Months Left')
                st.warning(f"⚠️ {len(notifications)} items with expiring stock that cannot be fully consumed before expiry")

                priority_counts = notif_df['Priority'].value_counts()
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("🔴 Critical (≤3 months)", priority_counts.get("🔴 CRITICAL", 0))
                with col2:
                    st.metric("🟡 High (≤6 months)", priority_counts.get("🟡 HIGH", 0))
                with col3:
                    st.metric("🔵 Medium (≤12 months)", priority_counts.get("🔵 MEDIUM", 0))

                st.dataframe(notif_df[['Material', 'Priority', 'Message', 'Recommendation', 'Quantity', 'Expiry Date', 'Months to Consume']], 
                            use_container_width=True, hide_index=True)

                if st.button("📢 Add to Dashboard Notifications"):
                    for _, row in notif_df.head(5).iterrows():
                        st.session_state.notifications.append(f"{row['Priority']}: {row['Material']} - {row['Message']}")
                    st.success(f"Added {min(5, len(notifications))} notifications to sidebar")
                    st.rerun()
            else:
                st.success("✅ No expiring stock detected. All expiring batches can be consumed before their expiry date!")

    # ========== TAB 5: Program Comparison ==========
    with aa_tab5:
        if _tab_open(aa_tab5):
            st.markdown("<h3 style='font-size: 24px; font-weight: bold;'>Program Performance Comparison</h3>", unsafe_allow_html=True)
            st.caption("Ranking based on: Availability (100%=1), SAP (≥65%=1), Stock-out Rate (0%=1), Overstock Rate (0%=1), Avg NMOS (6-18 months; vaccines 4-10 = 1)")

            if google_sheets and len(google_sheets) > 0:
                program_metrics = []

                for program_name, program_df in google_sheets.items():
                    if program_df.empty:
                        continue

                    if 'Material Description' in program_df.columns and 'Material Description' in df.columns:
                        merged = program_df[['Material Description']].merge(
                            df[['Material Description', 'NMOS']], on='Material Description', how='left'
                        )
                        nmos_values = pd.to_numeric(merged['NMOS'], errors='coerce').dropna()

                        if len(nmos_values) > 0:
                            Availability = (nmos_values > 1).mean() * 100
                            sap, overstock_rate = nmos_range_stats(merged)
                            stock_out_rate = (nmos_values < 1).mean() * 100
                            avg_nmos = nmos_values.mean()
                        else:
                            Availability = sap = stock_out_rate = overstock_rate = 0
                            avg_nmos = 0

                        program_metrics.append({
                            'Program': program_name,
                            'Availability (%)': round(Availability, 1),
                            'SAP Achievement (%)': round(sap, 1),
                            'Stock-out Rate (%)': round(stock_out_rate, 1),
                            'Overstock Rate (%)': round(overstock_rate, 1),
                            'Avg NMOS': round(avg_nmos, 2),
                            'Total Materials': len(merged)
                        })

                if program_metrics:
                    for item in program_metrics:
                        composite_score = 0
                        if item['Availability (%)'] == 100:
                            composite_score += 1
                        if item['SAP Achievement (%)'] >= 65:
                            composite_score += 1
                        if item['Stock-out Rate (%)'] == 0:
                            composite_score += 1
                        if item['Overstock Rate (%)'] == 0:
                            composite_score += 1
                        _lo_p, _hi_p = program_levels(item['Program'])
                        if _lo_p <= item['Avg NMOS'] <= _hi_p:
                            composite_score += 1
                        item['Composite Score'] = composite_score

                    comparison_df = pd.DataFrame(program_metrics).sort_values(['Composite Score', 'Availability (%)'], ascending=[False, False])
                    comparison_df['Rank'] = range(1, len(comparison_df) + 1)
                    comparison_df = comparison_df.drop(columns=['Composite Score'])

                    top_program = comparison_df.iloc[0]['Program']
                    top_Availability = comparison_df.iloc[0]['Availability (%)']
                    bottom_program = comparison_df.iloc[-1]['Program']
                    bottom_Availability = comparison_df.iloc[-1]['Availability (%)']

                    col_left, col_right = st.columns(2)
                    with col_left:
                        st.markdown(f"""
                    <div style='background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); border-radius: 15px; padding: 15px; text-align: center;'>
                        <div style='font-size: 32px;'>🏆</div>
                        <div style='font-size: 18px; font-weight: bold; color: white;'>{top_program}</div>
                        <div><span style='font-size: 24px; font-weight: bold; color: white;'>{top_Availability}%</span><span style='color: white;'> Availability</span></div>
                    </div>
                    """, unsafe_allow_html=True)
                    with col_right:
                        st.markdown(f"""
                    <div style='background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); border-radius: 15px; padding: 15px; text-align: center;'>
                        <div style='font-size: 32px;'>📉</div>
                        <div style='font-size: 18px; font-weight: bold; color: white;'>{bottom_program}</div>
                        <div><span style='font-size: 24px; font-weight: bold; color: white;'>{bottom_Availability}%</span><span style='color: white;'> Availability</span></div>
                    </div>
                    """, unsafe_allow_html=True)

                    st.dataframe(comparison_df, use_container_width=True, hide_index=True)

                    fig = go.Figure()
                    fig.add_trace(go.Bar(x=comparison_df['Program'], y=comparison_df['Availability (%)'], name='Availability (%)', text=comparison_df['Availability (%)'].apply(lambda x: f'{x}%'), textposition='outside', marker_color='skyblue'))
                    fig.add_trace(go.Bar(x=comparison_df['Program'], y=comparison_df['SAP Achievement (%)'], name='SAP Achievement (%)', text=comparison_df['SAP Achievement (%)'].apply(lambda x: f'{x}%'), textposition='outside', marker_color='lightgreen'))
                    fig.update_layout(title='Key Metrics Comparison', xaxis_title='Program', yaxis_title='Percentage (%)', barmode='group', height=500, xaxis_tickangle=-45)
                    st.plotly_chart(fig, use_container_width=True)

                    if len(comparison_df) >= 2:
                        categories = ['Availability (%)', 'SAP Achievement (%)', 'Stock-out Rate (%)', 'Overstock Rate (%)']
                        prog1 = comparison_df.iloc[0]
                        prog2 = comparison_df.iloc[1]
                        fig_radar = go.Figure()
                        fig_radar.add_trace(go.Scatterpolar(r=[prog1[c] for c in categories], theta=categories, fill='toself', name=prog1['Program']))
                        fig_radar.add_trace(go.Scatterpolar(r=[prog2[c] for c in categories], theta=categories, fill='toself', name=prog2['Program']))
                        fig_radar.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])), showlegend=True, title="Top 2 Programs Comparison", height=500)
                        st.plotly_chart(fig_radar, use_container_width=True)
                else:
                    st.info("No program comparison data available")
            else:
                st.info("Google Sheets data not available for program comparison")

        # ========== TAB 6: Regional Map ==========
    with aa_tab6:
        if _tab_open(aa_tab6):
            st.markdown("<h3 style='font-size: 24px; font-weight: bold;'>Regional Stock Distribution Map</h3>", unsafe_allow_html=True)
            st.caption("🔴 Red = HMOS < 2 (Understock) | 🟢 Green = HMOS 2-4 (Normal) | 🔵 Skyblue = HMOS > 4 (Overstock)")

            branch_coords = {
                'Adama Branch': [8.5483, 39.2696],
                'Addis Ababa Branch 1': [9.0320, 38.7469],
                'Addis Ababa Branch 2': [9.0320, 38.7469],
                'Arba Minch Branch': [6.0333, 37.5500],
                'Assosa Branch': [10.0667, 34.5333],
                'Bahir Dar Branch': [11.5742, 37.3613],
                'Dessie Branch': [11.1333, 39.6333],
                'Dire Dawa Branch': [9.6000, 41.8500],
                'Gambela Branch': [8.2500, 34.5833],
                'Gondar Branch': [12.6000, 37.4667],
                'Hawassa Branch': [7.0500, 38.4667],
                'Jigjiga Branch': [9.3500, 42.8000],
                'Jimma Branch': [7.6667, 36.8333],
                'Mekele Branch': [13.4967, 39.4769],
                'Shire Branch': [14.1000, 38.2833]
            }

            if branch_amc_data is not None and not branch_amc_data.empty:
                branch_stock_cols = [col for col in df.columns if 'Branch' in col and col != 'Material Description']
                map_data = []

                for stock_col in branch_stock_cols:
                    if stock_col in branch_amc_data.columns:
                        merged = pd.merge(
                            df[['Material Description', stock_col]],
                            branch_amc_data[['Material Description', stock_col]],
                            on='Material Description',
                            how='inner'
                        )
                        if not merged.empty:
                            stock_values = pd.to_numeric(merged[stock_col + '_x'], errors='coerce').fillna(0)
                            amc_values = pd.to_numeric(merged[stock_col + '_y'], errors='coerce').fillna(1)
                            amc_values = amc_values.replace(0, 1)
                            hmos_values = (stock_values / amc_values).values
                            valid_hmos = hmos_values[hmos_values > 0]
                            avg_hmos = np.mean(valid_hmos) if len(valid_hmos) > 0 else 0

                            if avg_hmos < 2:
                                status = "Understock"
                            elif avg_hmos <= 4:
                                status = "Normal"
                            else:
                                status = "Overstock"

                            coords = branch_coords.get(stock_col, [9.0, 38.0])
                            map_data.append({
                                'Branch': stock_col,
                                'Latitude': coords[0],
                                'Longitude': coords[1],
                                'Average HMOS': round(avg_hmos, 2),
                                'Status': status
                            })

                if map_data:
                    map_df = pd.DataFrame(map_data)

                    # ============================================================
                    # ✅ FIXED: Use scatter_geo instead of scatter_mapbox
                    #    (no Mapbox token required — works on Streamlit Cloud)
                    # ============================================================
                    fig = px.scatter_geo(
                        map_df,
                        lat='Latitude',
                        lon='Longitude',
                        size='Average HMOS',
                        size_max=30,
                        color='Status',
                        hover_name='Branch',
                        hover_data={'Average HMOS': True, 'Latitude': False, 'Longitude': False},
                        color_discrete_map={
                            'Understock': 'red',
                            'Normal': 'green',
                            'Overstock': 'skyblue'
                        },
                        title='Branch Stock Distribution Map (Average HMOS)'
                    )

                    fig.update_geos(
                        showcountries=True,
                        showcoastlines=True,
                        showland=True,
                        showlakes=False,
                        landcolor="lightgray",
                        countrycolor="white",
                        coastlinecolor="white",
                        fitbounds="locations",   # auto-zoom to Ethiopia
                        projection_type="natural earth"
                    )

                    fig.update_layout(
                        height=600,
                        margin=dict(l=0, r=0, t=50, b=0),
                        legend=dict(
                            orientation="h",
                            yanchor="bottom",
                            y=1.02,
                            xanchor="right",
                            x=1
                        )
                    )

                    st.plotly_chart(fig, use_container_width=True)

                    # Summary table below the map
                    st.markdown("### 📋 Branch Summary")
                    summary_display = map_df[['Branch', 'Average HMOS', 'Status']].copy()
                    summary_display = summary_display.sort_values('Average HMOS', ascending=False)
                    st.dataframe(
                        summary_display,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            'Branch': st.column_config.TextColumn('Branch', width='medium'),
                            'Average HMOS': st.column_config.NumberColumn('Average HMOS', format='%.2f', width='small'),
                            'Status': st.column_config.TextColumn('Status', width='small')
                        }
                    )

                    # Quick stats
                    col_m1, col_m2, col_m3 = st.columns(3)
                    with col_m1:
                        understock_count = len(map_df[map_df['Status'] == 'Understock'])
                        st.metric("🔴 Understock Branches", understock_count)
                    with col_m2:
                        normal_count = len(map_df[map_df['Status'] == 'Normal'])
                        st.metric("🟢 Normal Branches", normal_count)
                    with col_m3:
                        overstock_count = len(map_df[map_df['Status'] == 'Overstock'])
                        st.metric("🔵 Overstock Branches", overstock_count)

                    # Download button
                    st.download_button(
                        label="📥 Download Regional Map Data (Excel)",
                        data=map_df.pipe(_xl),
                        file_name=f"regional_map_{datetime.now().strftime('%Y%m%d')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                else:
                    st.info("Map data not available. Please ensure branch stock and AMC data are loaded.")
            else:
                st.info("Branch AMC data not available for map")

    # ========== TAB 9: Report Scheduling ==========
    with aa_tab9:
        if _tab_open(aa_tab9):
            st.markdown("<h3 style='font-size: 24px; font-weight: bold;'>Automated Report Scheduling</h3>", unsafe_allow_html=True)
            st.info("Configure automated reports to be sent via email on a schedule")

            col1, col2 = st.columns(2)
            with col1:
                report_type = st.selectbox("Report Type", ["Weekly Summary", "Monthly Full Report", "Quarterly Trend Analysis"])
                schedule_day = st.selectbox("Schedule Day", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"])
            with col2:
                recipient_email = st.text_input("Recipient Email", value=st.session_state['user']['email'])
                schedule_time = st.time_input("Schedule Time", value=datetime.now().replace(hour=8, minute=0))

            st.markdown("### Report Content Options")
            include_sections = st.multiselect("Include Sections", 
                                              ["Stock Status", "KPIs & Analytics", "Decision Briefs", 
                                               "Branch Rankings", "Redistribution Recommendations", "Expiry Alerts"],
                                              default=["Stock Status", "KPIs & Analytics"])

            if st.button("📅 Schedule Report", use_container_width=True, type="primary"):
                st.success(f"✅ Report scheduled! {report_type} will be sent to {recipient_email} every {schedule_day} at {schedule_time.strftime('%H:%M')}")
                st.info("📧 In production, this would connect to a cron job / scheduler to automatically generate and email reports")

                st.markdown("### 📄 Report Preview")
                preview_df = df_filtered.head(10)[['Material Description', 'NMOS', 'Stock Status', 'Risk Type']].copy()
                st.dataframe(preview_df, use_container_width=True)
                st.download_button("📥 Download Sample Report", preview_df.pipe(_xl), f"{report_type.replace(' ', '_')}_sample.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

            st.markdown("---")
            st.markdown("### 📧 Email Configuration (Admin Only)")
            if st.session_state['user']['role'] == 'admin':
                smtp_server = st.text_input("SMTP Server", placeholder="smtp.gmail.com")
                smtp_port = st.number_input("SMTP Port", value=587)
                sender_email = st.text_input("Sender Email")
                sender_password = st.text_input("Sender Password", type="password")
                if st.button("💾 Save Email Settings"):
                    st.success("Email settings saved (simulated)")
            else:
                st.info("Contact administrator to configure email settings")

    st.stop()

elif page == "Executive Summary":
    # ===================================================
    # EXECUTIVE SUMMARY PAGE
    # ===================================================
    st.markdown("<h1 style='font-size: 36px; font-weight: bold; font-family: Times New Roman;' class='gradient-text'>📊 Executive Summary Dashboard</h1>", unsafe_allow_html=True)
    st.caption(f"Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Program: {', '.join(selected_programs_list) if selected_programs_list else 'All Programs'}")

    # Sidebar -> section navigation
    _apply_nav_target("Executive Summary", 6, "scroll")

    # Check if we have data
    if df_filtered.empty:
        st.warning("No data available for the selected filters.")
        st.stop()

    # Calculate metrics only if data exists
    Availability = 0
    sap_achievement = 0
    avg_avail_gap = 0

    if 'NMOS' in df_filtered.columns and not df_filtered.empty:
        nmos_values = pd.to_numeric(df_filtered['NMOS'], errors='coerce').dropna()
        if len(nmos_values) > 0:
            Availability = (nmos_values > 1).mean() * 100
            sap_achievement = nmos_range_stats(df_filtered)[0]

        if 'Distr. Gap' in df_filtered.columns:
            avail_gap_values = pd.to_numeric(df_filtered['Distr. Gap'], errors='coerce').dropna()
            if len(avail_gap_values) > 0:
                avg_avail_gap = avail_gap_values.mean()

    # Initialize other variables
    total_cv_materials = 0
    low_variation = 0
    moderate_variation = 0
    high_variation = 0
    low_pct = 0
    mod_pct = 0
    high_pct = 0
    top_branch = "N/A"
    bottom_branch = "N/A"
    top_score = 0
    bottom_score = 0
    top_program = "N/A"
    bottom_program = "N/A"
    top_program_score = 0
    bottom_program_score = 0

    # SECTION 1: PERFORMANCE METRICS
    st.markdown("---")
    st.markdown("<h2 style='font-size: 28px; font-weight: bold;'>🎯 1. Performance Metrics</h2>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"""
        <div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 15px; padding: 20px; color: white;'>
            <h3 style='margin:0; font-size: 14px; opacity:0.9'>Availability</h3>
            <p style='margin:0; font-size: 36px; font-weight: bold;'>{Availability:.1f}%</p>
            <p style='margin:0; font-size: 12px; opacity:0.8'>Target: 100%</p>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div style='background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); border-radius: 15px; padding: 20px; color: white;'>
            <h3 style='margin:0; font-size: 14px; opacity:0.9'>SAP ACHIEVEMENT</h3>
            <p style='margin:0; font-size: 36px; font-weight: bold;'>{sap_achievement:.1f}%</p>
            <p style='margin:0; font-size: 12px; opacity:0.8'>Target: 65%</p>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown(f"""
        <div style='background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); border-radius: 15px; padding: 20px; color: white;'>
            <h3 style='margin:0; font-size: 14px; opacity:0.9'>Distr. Gap</h3>
            <p style='margin:0; font-size: 36px; font-weight: bold;'>{avg_avail_gap:.1f}%</p>
            <p style='margin:0; font-size: 12px; opacity:0.8'>Hubs% - Head Office%</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # SECTION 2: STOCK STATUS
    st.markdown("<h2 style='font-size: 28px; font-weight: bold;'>📊 2. Stock Status</h2>", unsafe_allow_html=True)

    total_materials = len(df_filtered)
    stock_out_count = len(df_filtered[df_filtered['Stock Status'] == 'Stock Out']) if 'Stock Status' in df_filtered.columns else 0
    understock_count = len(df_filtered[df_filtered['Stock Status'] == 'Understock']) if 'Stock Status' in df_filtered.columns else 0
    normal_count = len(df_filtered[df_filtered['Stock Status'] == 'Normal Stock']) if 'Stock Status' in df_filtered.columns else 0
    overstock_count = len(df_filtered[df_filtered['Stock Status'] == 'Overstock']) if 'Stock Status' in df_filtered.columns else 0

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("📦 Total Materials", total_materials)
    with col2:
        st.metric("🔴 Stock Out", stock_out_count, delta=f"-{stock_out_count}" if stock_out_count > 0 else "0", delta_color="inverse")
    with col3:
        st.metric("🟡 Understock", understock_count)
    with col4:
        st.metric("🟢 Normal Stock", normal_count)
    with col5:
        st.metric("🔵 Overstock", overstock_count)

    # SECTION 3: RISK SUMMARY
    st.markdown("---")
    st.markdown("<h2 style='font-size: 28px; font-weight: bold;'>⚠️ 3. Risk Summary</h2>", unsafe_allow_html=True)

    critical_risk = len(df_filtered[df_filtered['Risk Type'] == 'Critical Risk']) if 'Risk Type' in df_filtered.columns else 0
    risk_stock_out = len(df_filtered[df_filtered['Risk Type'] == 'Risk of Stock out']) if 'Risk Type' in df_filtered.columns else 0
    expiry_risk = len(df_filtered[df_filtered['Risk Type'] == 'Expiry Risk']) if 'Risk Type' in df_filtered.columns else 0

    st.markdown(f"""
    <table style='width: 100%; border-collapse: collapse; margin: 20px 0;'>
        <tr style='background-color: #ff4444; color: white; text-align: center;'>
            <th style='padding: 15px; font-size: 18px; border-radius: 10px 0 0 0;'>🔴 CRITICAL RISK</th>
            <th style='padding: 15px; font-size: 18px; background-color: #ffa500;'>🟡 RISK OF STOCK OUT</th>
            <th style='padding: 15px; font-size: 18px; background-color: #ff9800; border-radius: 0 10px 0 0;'>⚠️ EXPIRY RISK</th>
        </tr>
        <tr style='text-align: center; background-color: #f8f9fa;'>
            <td style='padding: 20px; font-size: 42px; font-weight: bold; color: #ff4444;'>{critical_risk}</td>
            <td style='padding: 20px; font-size: 42px; font-weight: bold; color: #ffa500;'>{risk_stock_out}</td>
            <td style='padding: 20px; font-size: 42px; font-weight: bold; color: #ff9800;'>{expiry_risk}</td>
        </tr>
        <tr style='text-align: center; background-color: #ffffff;'>
            <td style='padding: 10px; font-size: 14px;'>require URGENT attention</td>
            <td style='padding: 10px; font-size: 14px;'>need expediting</td>
            <td style='padding: 10px; font-size: 14px;'>approaching expiration</td>
        </tr>
    </table>
    """, unsafe_allow_html=True)

    # SECTION 4: HUBS DISTRIBUTION
    st.markdown("---")
    st.markdown("<h2 style='font-size: 28px; font-weight: bold;'>📍 4. Stock Distribution Across Hubs by MOS</h2>", unsafe_allow_html=True)

    if 'CV Category' in df_filtered.columns and not df_filtered.empty:
        cv_counts = df_filtered['CV Category'].value_counts()
        total_cv_materials = len(df_filtered[df_filtered['CV Category'] != 'Unknown'])

        low_variation = cv_counts.get('Low variation', 0)
        moderate_variation = cv_counts.get('Moderate variation', 0)
        high_variation = cv_counts.get('High variation', 0)

        if total_cv_materials > 0:
            low_pct = (low_variation / total_cv_materials * 100)
            mod_pct = (moderate_variation / total_cv_materials * 100)
            high_pct = (high_variation / total_cv_materials * 100)

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("📊 Total Materials", total_cv_materials)
        with col2:
            st.metric("🟢 Low Variation (<50%)", f"{low_variation} ({low_pct:.1f}%)")
        with col3:
            st.metric("🟡 Moderate Variation (50-100%)", f"{moderate_variation} ({mod_pct:.1f}%)")
        with col4:
            st.metric("🔴 High Variation (>100%)", f"{high_variation} ({high_pct:.1f}%)")
    else:
        st.info("CV Category data not available")

    # SECTION 5: BRANCH RANKING
    st.markdown("---")
    st.markdown("<h2 style='font-size: 28px; font-weight: bold;'>🏆 5. Branch Ranking</h2>", unsafe_allow_html=True)
    st.caption("Availability = materials with HMOS ≥ 0.5 (at least 2 weeks of stock)")
    st.caption("Ranking based on: Availability Score (0-4) + Avg HMOS Score (0-2) + Stock-out Score (0-3) = Max 9 points")

    if branch_amc_data is not None and not branch_amc_data.empty and not df.empty:
        branch_stock_cols = [col for col in df.columns if 'Branch' in col and col != 'Material Description']
        amc_branch_cols = [col for col in branch_amc_data.columns if col != 'Material Description']
        rankings = []

        for amc_branch in amc_branch_cols:
            stock_col = None
            for bc in branch_stock_cols:
                if amc_branch == bc:
                    stock_col = bc
                    break

            if stock_col and stock_col in df.columns and amc_branch in branch_amc_data.columns:
                try:
                    merged = pd.merge(
                        df[['Material Description', stock_col]].dropna(subset=['Material Description']), 
                        branch_amc_data[['Material Description', amc_branch]].dropna(subset=['Material Description']), 
                        on='Material Description', 
                        how='inner'
                    )

                    if not merged.empty:
                        stock_values = pd.to_numeric(merged[stock_col + '_x'], errors='coerce').fillna(0)
                        amc_values = pd.to_numeric(merged[amc_branch + '_y'], errors='coerce').fillna(1)
                        amc_values = amc_values.replace(0, 1)
                        branch_hmos = (stock_values / amc_values).values

                        Availability_count = np.sum(branch_hmos >= 0.5)
                        total_materials_branch = len(branch_hmos)
                        valid_hmos = branch_hmos[branch_hmos > 0]
                        avg_hmos = np.mean(valid_hmos) if len(valid_hmos) > 0 else 0
                        stock_out_materials = total_materials_branch - Availability_count

                        if total_materials_branch > 0:
                            Availability_pct = (Availability_count / total_materials_branch * 100)
                            if Availability_pct == 100:
                                Availability_points = 4
                            elif Availability_pct >= 85:
                                Availability_points = 3
                            elif Availability_pct >= 75:
                                Availability_points = 2
                            elif Availability_pct >= 55:
                                Availability_points = 1
                            else:
                                Availability_points = 0
                        else:
                            Availability_points = 0

                        if 2 <= avg_hmos <= 4:
                            hmos_points = 2
                        elif (1 <= avg_hmos < 2) or (4 < avg_hmos <= 6):
                            hmos_points = 1
                        else:
                            hmos_points = 0

                        if stock_out_materials <= 10:
                            stockout_points = 3
                        elif stock_out_materials <= 20:
                            stockout_points = 2
                        else:
                            stockout_points = 0

                        total_score = Availability_points + hmos_points + stockout_points

                        rankings.append({
                            'Branch': amc_branch,
                            'Total Score': total_score
                        })
                except Exception:
                    continue

        if rankings:
            rankings_df = pd.DataFrame(rankings).sort_values('Total Score', ascending=False)
            top_branch = rankings_df.iloc[0]['Branch']
            bottom_branch = rankings_df.iloc[-1]['Branch']
            top_score = rankings_df.iloc[0]['Total Score']
            bottom_score = rankings_df.iloc[-1]['Total Score']

            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"""
                <div style='background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); border-radius: 15px; padding: 20px; color: white; text-align: center;'>
                    <h3 style='margin:0; font-size: 16px; opacity:0.9'>🏆 TOP BRANCH</h3>
                    <p style='margin: 10px 0 0 0; font-size: 28px; font-weight: bold;'>{top_branch}</p>
                    <p style='margin: 0; font-size: 14px;'>Score: {top_score}/9 points</p>
                </div>
                """, unsafe_allow_html=True)
            with col2:
                st.markdown(f"""
                <div style='background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); border-radius: 15px; padding: 20px; color: white; text-align: center;'>
                    <h3 style='margin:0; font-size: 16px; opacity:0.9'>📉 BOTTOM BRANCH</h3>
                    <p style='margin: 10px 0 0 0; font-size: 28px; font-weight: bold;'>{bottom_branch}</p>
                    <p style='margin: 0; font-size: 14px;'>Score: {bottom_score}/9 points</p>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No branch ranking data available")
    else:
        st.info("Branch AMC data not available for ranking")

    # SECTION 6: PROGRAM PERFORMANCE
    st.markdown("---")
    st.markdown("<h2 style='font-size: 28px; font-weight: bold;'>📊 6. Program Performance</h2>", unsafe_allow_html=True)
    st.caption("Ranking based on: Availability (100%=1), SAP (≥65%=1), Stock-out Rate (0%=1), Overstock Rate (0%=1), Avg NMOS (6-18 months; vaccines 4-10 = 1) = Max 5 points")

    if google_sheets and len(google_sheets) > 0 and not df.empty:
        program_metrics = []
        for program_name, program_df in google_sheets.items():
            if program_df.empty or 'Material Description' not in program_df.columns:
                continue

            merged = program_df[['Material Description']].merge(
                df[['Material Description', 'NMOS']], on='Material Description', how='left'
            )
            nmos_values = pd.to_numeric(merged['NMOS'], errors='coerce').dropna()

            if len(nmos_values) > 0:
                composite_score = 0
                Availability_prog = (nmos_values > 1).mean() * 100
                if Availability_prog == 100:
                    composite_score += 1
                sap_prog = nmos_range_stats(merged)[0]
                if sap_prog >= 65:
                    composite_score += 1
                stock_out_rate = (nmos_values < 1).mean() * 100
                if stock_out_rate == 0:
                    composite_score += 1
                overstock_rate = nmos_range_stats(merged)[1]
                if overstock_rate == 0:
                    composite_score += 1
                avg_nmos_prog = nmos_values.mean()
                _lo_p, _hi_p = program_levels(program_name)
                if _lo_p <= avg_nmos_prog <= _hi_p:
                    composite_score += 1

                program_metrics.append({
                    'Program': program_name,
                    'Composite Score': composite_score
                })

        if program_metrics:
            prog_df = pd.DataFrame(program_metrics).sort_values('Composite Score', ascending=False)
            top_program = prog_df.iloc[0]['Program']
            bottom_program = prog_df.iloc[-1]['Program']
            top_program_score = prog_df.iloc[0]['Composite Score']
            bottom_program_score = prog_df.iloc[-1]['Composite Score']

            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"""
                <div style='background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); border-radius: 15px; padding: 20px; color: white; text-align: center;'>
                    <h3 style='margin:0; font-size: 16px; opacity:0.9'>🥇 TOP PROGRAM</h3>
                    <p style='margin: 10px 0 0 0; font-size: 28px; font-weight: bold;'>{top_program}</p>
                    <p style='margin: 0; font-size: 14px;'>Score: {top_program_score}/5 points</p>
                </div>
                """, unsafe_allow_html=True)
            with col2:
                st.markdown(f"""
                <div style='background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); border-radius: 15px; padding: 20px; color: white; text-align: center;'>
                    <h3 style='margin:0; font-size: 16px; opacity:0.9'>📉 BOTTOM PROGRAM</h3>
                    <p style='margin: 10px 0 0 0; font-size: 28px; font-weight: bold;'>{bottom_program}</p>
                    <p style='margin: 0; font-size: 14px;'>Score: {bottom_program_score}/5 points</p>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No program data available for comparison")
    else:
        st.info("Google Sheets data not available for program comparison")

    st.markdown("---")

    summary_text = f"""
EXECUTIVE SUMMARY REPORT
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Program: {', '.join(selected_programs_list) if selected_programs_list else 'All Programs'}

================================================================================
1. PERFORMANCE METRICS
================================================================================
• Availability: {Availability:.1f}% (Target: 100%)
• SAP Achievement: {sap_achievement:.1f}% (Target: 65%)
• Distr. Gap: {avg_avail_gap:.1f}%

================================================================================
2. STOCK STATUS
================================================================================
• Total Materials: {total_materials}
• Stock Out: {stock_out_count}
• Understock: {understock_count}
• Normal Stock: {normal_count}
• Overstock: {overstock_count}

================================================================================
3. RISK SUMMARY
================================================================================
• Critical Risk: {critical_risk}
• Risk of Stock Out: {risk_stock_out}
• Expiry Risk: {expiry_risk}

================================================================================
4. STOCK DISTRIBUTION ACROSS HUBS
================================================================================
• Total Materials: {total_cv_materials}
• Low Variation (<50%): {low_variation} ({low_pct:.1f}%)
• Moderate Variation (50-100%): {moderate_variation} ({mod_pct:.1f}%)
• High Variation (>100%): {high_variation} ({high_pct:.1f}%)

================================================================================
5. BRANCH RANKING
================================================================================
• Top Branch: {top_branch} ({top_score}/9 points)
• Bottom Branch: {bottom_branch} ({bottom_score}/9 points)

================================================================================
6. PROGRAM PERFORMANCE
================================================================================
• Top Program: {top_program} ({top_program_score}/5 points)
• Bottom Program: {bottom_program} ({bottom_program_score}/5 points)
================================================================================
    """

    st.download_button(
        label="📥 Download Executive Summary Report",
        data=summary_text,
        file_name=f"executive_summary_{datetime.now().strftime('%Y%m%d')}.txt",
        mime="text/plain",
        use_container_width=True,
        type="primary"
    )

    st.stop()
# ===================================================
# MAIN DASHBOARD (7 Tabs)
# ===================================================
else:
    # Define program_display at the top of the Dashboard page
    if show_all_programs or len(selected_programs_list) == 0:
        program_display = "All Programs"
    elif len(selected_programs_list) == 1:
        program_display = selected_programs_list[0]
    else:
        program_display = f"{len(selected_programs_list)} Programs"

    if subcategory_filter != "All" and len(selected_programs_list) == 1:
        program_display = f"{selected_programs_list[0]} - {subcategory_filter}"

    # Header: title only (EPSS badge is in the sidebar, filters + display settings sit right below this title)
    with _title_slot:
        st.markdown("""
        <h1 class='animated-header' style='font-size: 32px; font-weight: bold; font-family: Times New Roman; margin: 0; padding: 0; line-height: 1.2; text-align: center; display: block; width: 100%;'>HPC STOCK MANAGEMENT DASHBOARD</h1>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # Quick Summary Section - Use program_display here
    if show_all_programs or len(selected_programs_list) == 0:
        program_name = "All Programs"
    elif len(selected_programs_list) == 1:
        program_name = selected_programs_list[0]
    else:
        program_name = f"{len(selected_programs_list)} Programs"

    if subcategory_filter != "All" and len(selected_programs_list) == 1:
        program_name = f"{selected_programs_list[0]} - {subcategory_filter}"

    # Calculate metrics
    if not df_filtered.empty and 'NMOS' in df_filtered.columns:
        nmos_values = pd.to_numeric(df_filtered['NMOS'], errors='coerce').dropna()
        Availability = (nmos_values > 1).mean() * 100 if len(nmos_values) > 0 else 0
        sap = nmos_range_stats(df_filtered)[0] if len(nmos_values) > 0 else 0

        if 'Distr. Gap' in df_filtered.columns:
            avail_gap_values = pd.to_numeric(df_filtered['Distr. Gap'], errors='coerce').dropna()
            avg_avail_gap = avail_gap_values.mean() if len(avail_gap_values) > 0 else 0
        else:
            avg_avail_gap = 0

        # Avg. Lead Time = Avg Procurement Lead (synced from the Procurement Lead Time tab)
        try:
            # same base as the Procurement Lead Time tab (global df), so the numbers match
            _kpi_lead = _compute_avg_proc_lead(df)
        except Exception:
            _kpi_lead = st.session_state.get('kpi_avg_proc_lead')
        st.session_state['kpi_avg_proc_lead'] = _kpi_lead
        avg_lead_time_display = f"{_kpi_lead} days" if _kpi_lead is not None else "N/A"

        # Calculate stock status counts
        total_items = len(df_filtered)
        stock_out = len(df_filtered[df_filtered['Stock Status'] == 'Stock Out']) if 'Stock Status' in df_filtered.columns else 0
        understock = len(df_filtered[df_filtered['Stock Status'] == 'Understock']) if 'Stock Status' in df_filtered.columns else 0
        normal = len(df_filtered[df_filtered['Stock Status'] == 'Normal Stock']) if 'Stock Status' in df_filtered.columns else 0
        overstock = len(df_filtered[df_filtered['Stock Status'] == 'Overstock']) if 'Stock Status' in df_filtered.columns else 0

        # Calculate Decision Brief metrics
        stock_out_items = len(df_filtered[df_filtered['Stock Status'] == 'Stock Out']) if 'Stock Status' in df_filtered.columns else 0
        at_risk_stock_out = len(df_filtered[df_filtered['Risk Type'] == 'Risk of Stock out']) if 'Risk Type' in df_filtered.columns else 0
        at_risk_expiry = len(df_filtered[df_filtered['Risk Type'] == 'Expiry Risk']) + len(df_filtered[df_filtered['Risk Type'] == 'Critical Risk']) if 'Risk Type' in df_filtered.columns else 0

        # Items with Problems = SUM of all problems
        items_with_problems = stock_out_items + at_risk_stock_out + at_risk_expiry

        # Quick Summary Box with Total Items in title
        st.markdown(f"""
        <div style='background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); border-radius: 15px; padding: 15px; border: 1px solid #dee2e6; margin-bottom: 15px;'>
            <h4 style='margin: 0 0 10px 0; font-size: 16px; font-weight: bold; color: #1a5276;'>📊 {program_name} Quick Summary  |  📦 Total Items: {total_items}</h4>
        </div>
        """, unsafe_allow_html=True)

        # ========== ROW 1: KPIs (Gradient Background, White Text) ==========
        st.markdown("<p style='font-size: 14px; font-weight: bold; color: #1a5276; margin-bottom: 5px;'>📈 KPIs</p>", unsafe_allow_html=True)
        col_a, col_s, col_g, col_lead = st.columns(4)
        with col_a:
            st.markdown(f"""
            <div style='text-align: center; padding: 10px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 10px; margin: 5px; transition: all 0.3s ease; cursor: pointer;'>
                <p style='margin: 0; font-size: 14px; color: white; opacity: 0.9'>Availability</p>
                <p style='margin: 0; font-size: 24px; font-weight: bold; color: white;'>{Availability:.1f}%</p>
            </div>
            """, unsafe_allow_html=True)
        with col_s:
            st.markdown(f"""
            <div style='text-align: center; padding: 10px; background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); border-radius: 10px; margin: 5px; transition: all 0.3s ease; cursor: pointer;'>
                <p style='margin: 0; font-size: 14px; color: white; opacity: 0.9'>SAP</p>
                <p style='margin: 0; font-size: 24px; font-weight: bold; color: white;'>{sap:.1f}%</p>
            </div>
            """, unsafe_allow_html=True)
        with col_g:
            st.markdown(f"""
            <div style='text-align: center; padding: 10px; background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); border-radius: 10px; margin: 5px; transition: all 0.3s ease; cursor: pointer;'>
                <p style='margin: 0; font-size: 14px; color: white; opacity: 0.9'>Distr. Gap</p>
                <p style='margin: 0; font-size: 24px; font-weight: bold; color: white;'>{avg_avail_gap:.1f}%</p>
            </div>
            """, unsafe_allow_html=True)
        with col_lead:
            st.markdown(f"""
            <div style='text-align: center; padding: 10px; background: linear-gradient(135deg, #fa709a 0%, #fee140 100%); border-radius: 10px; margin: 5px; transition: all 0.3s ease; cursor: pointer;'>
                <p style='margin: 0; font-size: 14px; color: white; opacity: 0.9'>Avg.Lead Time</p>
                <p style='margin: 0; font-size: 24px; font-weight: bold; color: white;'>{avg_lead_time_display}</p>
            </div>
            """, unsafe_allow_html=True)

        # ========== ROW 2: Stock Status (White Background, Black Text) - CLICKABLE ==========
        st.markdown("<p style='font-size: 14px; font-weight: bold; color: #1a5276; margin: 15px 0 5px 0;'>📊 Stock Status</p>", unsafe_allow_html=True)
        _stock_cards = [
            ("so", "Stock Out", "#e74c3c", stock_out),
            ("us", "Understock", "#f39c12", understock),
            ("ns", "Normal Stock", "#27ae60", normal),
            ("os", "Overstock", "#2980b9", overstock),
        ]
        for _col, (_k, _lbl, _clr, _val) in zip(st.columns(4), _stock_cards):
            with _col:
                if True:
                    st.markdown(f"""
                    <div style='text-align: center; padding: 10px; background: white; border-radius: 10px; margin: 5px; transition: all 0.3s ease; box-shadow: 0 2px 4px rgba(0,0,0,0.1); cursor: pointer;'>
                        <p style='margin: 0; font-size: 14px; color: {_clr}; font-weight: bold;'>{_lbl}</p>
                        <p style='margin: 0; font-size: 24px; font-weight: bold; color: #333;'>{_val}</p>
                    </div>
                    """, unsafe_allow_html=True)
                    if st.button(f"Show {_lbl}", key=f"cardbtn_{_k}", use_container_width=True):
                        st.session_state.card_filter = None if st.session_state.get('card_filter') == _k else _k
                        st.rerun()

        # ========== ROW 3: Items with Problems (Black Background, White Text, Rounded Box) - CLICKABLE ==========
        st.markdown("<p style='font-size: 14px; font-weight: bold; color: #1a5276; margin: 15px 0 5px 0;'>⚠️ Items with Problems</p>", unsafe_allow_html=True)
        _problem_cards = [
            ("pr", "Items with Problems", "#9b59b6", items_with_problems, "13px", "12px"),
            ("po", "Stock Out Items", "#e74c3c", stock_out_items, "13px", "12px"),
            ("pk", "At Risk of Stock Out", "#f39c12", at_risk_stock_out, "13px", "12px"),
            ("pe", "At Risk of Expiry", "#e67e22", at_risk_expiry, "13px", "12px"),
        ]
        for _col, (_k, _lbl, _clr, _val, _fs, _pad) in zip(st.columns(4), _problem_cards):
            with _col:
                if True:
                    st.markdown(f"""
                    <div style='text-align: center; padding: 12px; background: #1a1a2e; border-radius: 25px; margin: 5px; border: 1px solid #333; transition: all 0.3s ease; cursor: pointer;'>
                        <p style='margin: 0; font-size: 13px; color: {_clr}; font-weight: bold;'>{_lbl}</p>
                        <p style='margin: 5px 0 0 0; font-size: 26px; font-weight: bold; color: white;'>{_val}</p>
                    </div>
                    """, unsafe_allow_html=True)
                    if st.button(f"Show {_lbl}", key=f"cardbtn_{_k}", use_container_width=True):
                        st.session_state.card_filter = None if st.session_state.get('card_filter') == _k else _k
                        st.rerun()

        # Cards stay exactly as designed; the click is forwarded to a hidden Streamlit button.
        st.markdown("""
        <style>
        div[class*="st-key-cardbtn_"] { display: none !important; }
        </style>
        """, unsafe_allow_html=True)
        _card_labels = [c[1] for c in _stock_cards] + [c[1] for c in _problem_cards]
        _inject_parent_js(_CARD_JS.replace("__LABELS__", __import__("json").dumps(_card_labels)))

        # ----- Detail table for the clicked card -----
        _CARD_DEFS = {
            "so": ("🔴 Stock Out", lambda d: d['Stock Status'] == 'Stock Out'),
            "us": ("🟡 Understock", lambda d: d['Stock Status'] == 'Understock'),
            "ns": ("🟢 Normal Stock", lambda d: d['Stock Status'] == 'Normal Stock'),
            "os": ("🔵 Overstock", lambda d: d['Stock Status'] == 'Overstock'),
            "pr": ("⚠️ Items with Problems", lambda d: (d['Stock Status'] == 'Stock Out') | (d['Risk Type'].fillna('') != '')),
            "po": ("🔴 Stock Out Items", lambda d: d['Stock Status'] == 'Stock Out'),
            "pk": ("🟡 At Risk of Stock Out", lambda d: d['Risk Type'] == 'Risk of Stock out'),
            "pe": ("🟠 At Risk of Expiry", lambda d: d['Risk Type'].isin(['Expiry Risk', 'Critical Risk'])),
        }
        _sel = st.session_state.get('card_filter')
        if _sel in _CARD_DEFS:
            _title, _fn = _CARD_DEFS[_sel]
            _want = ['Material Description', 'Head Office', 'Hubs', 'NSOH', 'Expiry', 'AMC', 'NMOS', 'Status']
            _cols = [c for c in _want if c in df_filtered.columns]
            _detail = df_filtered[_fn(df_filtered)][_cols].copy()
            # Keep the same arrangement as the Program(s) selection in the sidebar
            _order = ([p_ for p_ in program_list if p_ != "All"] if show_all_programs else list(selected_programs_list))
            _rank = {p_: i_ for i_, p_ in enumerate(_order)}
            _prog_of, _pos_of = {}, {}
            for _pn in _order:
                _pdf = (google_sheets or {}).get(_pn)
                if _pdf is None or 'Material Description' not in _pdf.columns:
                    continue
                for _i, _m in enumerate(_pdf['Material Description'].astype(str).str.strip()):
                    if _m not in _prog_of:
                        _prog_of[_m] = _pn
                        _pos_of[_m] = _i
            _mkey = _detail['Material Description'].astype(str).str.strip()
            _detail['_r'] = _mkey.map(lambda m_: _rank.get(_prog_of.get(m_), 10_000))
            _detail['_p'] = _mkey.map(lambda m_: _pos_of.get(m_, 10_000_000))
            _detail = _detail.sort_values(['_r', '_p'], kind='stable').drop(columns=['_r', '_p']).reset_index(drop=True)

            st.markdown(f"<h4 style='color:#1a5276; margin: 10px 0 0 0;'>{_title} — {len(_detail)} material(s)</h4>", unsafe_allow_html=True)
            _shown = _detail.copy()
            for _c in ['Head Office', 'Hubs', 'NSOH', 'AMC']:
                if _c in _shown.columns:
                    _shown[_c] = _shown[_c].apply(format_number_with_commas)
            if 'NMOS' in _shown.columns:
                _shown['NMOS'] = _shown['NMOS'].apply(format_mos_with_decimals)
            render_adv_table(_shown, max_height=560)
            _c1, _c2 = st.columns(2)
            with _c1:
                st.download_button(
                    "📥 Download this table (Excel)",
                    data=_xl(_detail, _title[2:].strip()),
                    file_name=f"{re.sub(r'[^A-Za-z0-9]+', '_', _title[2:].strip())}_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True, type="primary", key=f"dl_card_{_sel}"
                )
            with _c2:
                if st.button("✖ Close table", use_container_width=True, key="close_card_table"):
                    st.session_state.card_filter = None
                    st.rerun()

        # Add CSS for shake animation on all rows
        st.markdown("""
        <style>
        div[style*="cursor: pointer;"]:hover {
            animation: gentle-shake 0.3s ease-in-out;
            transform: translateY(-3px);
            transition: all 0.3s ease;
        }
        @keyframes gentle-shake {
            0%, 100% { transform: translateX(0); }
            25%, 75% { transform: translateX(-3px); }
            50% { transform: translateX(3px); }
        }
        </style>
        """, unsafe_allow_html=True)

        st.markdown("---")

    # Section selector (linked to the sidebar) - only the selected section is rendered
    _apply_nav_target("Dashboard", 6, "tabs")
    tab1, tab2, tab3, tab4, tab6, tab7 = _tabs_for("Dashboard")


   # ---------------------------------------------------
# TAB 1 - Stock Status Table
# ---------------------------------------------------
with tab1:
    if _tab_open(tab1):
        st.markdown("<h3 style='font-size: 28px; font-weight: bold; font-family: Times New Roman;'>Complete Stock Status Table</h3>", unsafe_allow_html=True)

        if not display_df_filtered.empty and 'Material Description' in display_df_filtered.columns:
            search_query = st.text_input(
                "Search by Material Description or any column value:",
                value=st.session_state.search_query,
                placeholder="Type to search... (e.g., 'artesunate', 'stock out', 'shipped')",
                key="search_input"
            )

            if search_query != st.session_state.search_query:
                st.session_state.search_query = search_query
                st.rerun()

            search_df = display_df_filtered.copy()

            if st.session_state.search_query:
                search_term = st.session_state.search_query.lower()
                string_df = search_df.astype(str)
                mask = string_df.apply(
                    lambda col: col.str.lower().str.contains(search_term, na=False, regex=False)
                ).any(axis=1)
                search_df = search_df[mask]
                st.info(f"🔍 Found {len(search_df)} matching records for '{st.session_state.search_query}'")
                if st.button("🗑️ Clear Search"):
                    st.session_state.search_query = ""
                    st.rerun()
            else:
                st.info(f"📊 Showing all {len(search_df)} records")

            # Column ordering
            cols = list(search_df.columns)
            if 'Material Description' in cols:
                cols.remove('Material Description')
                cols.insert(0, 'Material Description')
            if 'NMOS' in cols and 'AMC' in cols:
                cols.remove('NMOS')
                amc_index = cols.index('AMC') if 'AMC' in cols else 0
                cols.insert(amc_index + 1, 'NMOS')
            if 'DOS' in cols:
                cols.remove('DOS')
                nmos_index = cols.index('NMOS') if 'NMOS' in cols else 0
                cols.insert(nmos_index + 1, 'DOS')
            if 'Risk Type' in cols and 'Stock Status' in cols:
                cols.remove('Risk Type')
                status_index = cols.index('Stock Status') if 'Stock Status' in cols else 0
                cols.insert(status_index + 1, 'Risk Type')

            cols = [c for c in cols if c in search_df.columns]
            search_df = search_df[cols]

            if st.session_state.view_mode in ("card", "mobile"):
                st.markdown("### 📇 Card View")
                cols_per_row = 1 if st.session_state.view_mode == "mobile" else 2
                for i in range(0, len(search_df), cols_per_row):
                    card_cols = st.columns(cols_per_row)
                    for j, col in enumerate(card_cols):
                        idx = i + j
                        if idx < len(search_df):
                            row = search_df.iloc[idx]
                            status = row.get('Stock Status', '')
                            color_map = {
                                "Stock Out": "#ff4444",
                                "Understock": "#ffa500",
                                "Normal Stock": "#4CAF50",
                                "Overstock": "#2196F3"
                            }
                            border_color = color_map.get(status, "#ddd")
                            risk_type_value = row.get('Risk Type', 'N/A')
                            risk_color = {
                                "Critical Risk": "#9b59b6",
                                "Risk of Stock out": "#ffa500",
                                "Expiry Risk": "#ffa500"
                            }.get(risk_type_value, border_color)

                            material_desc = row.get('Material Description', 'N/A')
                            if pd.isna(material_desc) or material_desc is None:
                                material_desc = 'N/A'
                            else:
                                material_desc = str(material_desc)[:60]

                            dos_value = row.get('DOS', 0)
                            if pd.isna(dos_value):
                                dos_value = 0

                            with col:
                                st.markdown(f"""
                            <div class="stock-card" style='border-left: 4px solid {border_color};'>
                                <h4 style='color: {border_color}; margin-bottom: 10px;'>{material_desc}</h4>
                                <p><strong>📦 NSOH:</strong> {row.get('NSOH', 'N/A')}</p>
                                <p><strong>📈 AMC:</strong> {row.get('AMC', 'N/A')}</p>
                                <p><strong>⏰ NMOS:</strong> <span style='color: {border_color}; font-weight: bold;'>{row.get('NMOS', 'N/A')}</span></p>
                                <p><strong>📊 S/Status:</strong> {row.get('Stock Status', 'N/A')}</p>
                                <p><strong>📊 Status:</strong> {row.get('Status', 'N/A')}</p>
                                <p><strong>🔄 TMOS:</strong> {row.get('TMOS', 'N/A')}</p>
                                <p><strong>🎯 GF_MOS:</strong> {row.get('GF_MOS', 'N/A')} &nbsp; <strong>GF_Qty:</strong> {row.get('GF_Qty', 'N/A')}</p>
                                <p><strong>⚠️ Risk Type:</strong> <span style='color: {risk_color}; font-weight: bold;'>{risk_type_value}</span></p>
                            </div>
                            """, unsafe_allow_html=True)
            else:
                def color_row(row):
                    colors = {
                        "Stock Out": "background-color:red;color:white",
                        "Understock": "background-color:yellow",
                        "Normal Stock": "background-color:green;color:white",
                        "Overstock": "background-color:skyblue"
                    }
                    styles = [''] * len(row)
                    for i, col in enumerate(row.index):
                        if col == 'Material Description':
                            styles[i] = colors.get(row['Stock Status'], '')
                            break
                    return styles

                styled = search_df.style.apply(color_row, axis=1)

                def color_risk_type(val):
                    if val == "Critical Risk":
                        return 'background-color: #9b59b6; color: white'
                    elif val == "Risk of Stock out":
                        return 'background-color: #ffa500; color: white'
                    elif val == "Expiry Risk":
                        return 'background-color: #ffa500; color: white'
                    return ''

                styled = styled.map(color_risk_type, subset=['Risk Type'])

                def color_dos(val):
                    if pd.notna(val) and val > 0:
                        return 'background-color: #ff4444; color: white; font-weight: bold'
                    return ''

                if 'DOS' in search_df.columns:
                    styled = styled.map(color_dos, subset=['DOS'])

                column_config = {
                    "Material Description": st.column_config.TextColumn("Material Description", width=300, pinned=True),
                    "Risk Type": st.column_config.TextColumn("Risk Type", width=150),
                    "DOS": st.column_config.NumberColumn("DOS (Days)", width=100)
                }

                st.dataframe(styled, column_config=column_config, use_container_width=True, hide_index=True, height=min(800, (len(search_df) + 1) * 35))

                st.markdown("""
            <div class="legend-box">
                <h5 class="legend-title">📊 Color Legend - Stock Status:</h5>
                <div style="display: flex; gap: 20px; flex-wrap: wrap;">
                    <div class="legend-item"><div class="legend-color" style="background-color: red;"></div><span><strong>Red</strong> = Stock Out (NMOS &lt; 1)</span></div>
                    <div class="legend-item"><div class="legend-color" style="background-color: yellow;"></div><span><strong>Yellow</strong> = Understock (1 ≤ NMOS &lt; 6; vaccines &lt; 4)</span></div>
                    <div class="legend-item"><div class="legend-color" style="background-color: green;"></div><span><strong>Green</strong> = Normal Stock (6 ≤ NMOS ≤ 18; vaccines 4 ≤ NMOS ≤ 10)</span></div>
                    <div class="legend-item"><div class="legend-color" style="background-color: skyblue;"></div><span><strong>Blue</strong> = Overstock (NMOS > 18; vaccines > 10)</span></div>
                    <div class="legend-item"><div class="legend-color" style="background-color: #9b59b6;"></div><span><strong>Purple</strong> = Critical Risk</span></div>
                    <div class="legend-item"><div class="legend-color" style="background-color: #ffa500;"></div><span><strong>Orange</strong> = Risk of Stock out or Expiry Risk</span></div>
                    <div class="legend-item"><div class="legend-color" style="background-color: #ff4444;"></div><span><strong>Red DOS</strong> = Days Out of Stock (>0 days)</span></div>
                </div>
            </div>
            """, unsafe_allow_html=True)

                    # ==================================================================
            # DOWNLOAD REPORT — Advanced, share-ready, per-program sheets (Excel only)
            # ==================================================================
            st.markdown("---")
            st.markdown("<h4 style='font-size: 20px; font-weight: bold; font-family: Times New Roman;'>📥 Download Report</h4>", unsafe_allow_html=True)

            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

            try:
                from openpyxl.worksheet.errors import IgnoredError
                _HAS_IGNORED_ERRORS = True
            except Exception:
                IgnoredError = None
                _HAS_IGNORED_ERRORS = False

            # ------------------------------------------------------------------
            # 1) Determine report_columns (Material Description → TMOS)
            # ------------------------------------------------------------------
            report_columns = []
            if 'Material Description' in df_filtered.columns:
                report_columns.append('Material Description')

            all_columns = list(df_filtered.columns)

            columns_to_exclude = ['Stock Status', 'Risk of Stock', 'Hubs%', 'Head Office%',
                                  'Distr. Gap', 'CV (%)', 'CV Category', 'Has Expiry Risk',
                                  'Expiry Risk Details', 'Assigned Subcategory', 'Risk Type', 'DOS']

            if 'Material Description' in all_columns and 'TMOS' in all_columns:
                mat_index = all_columns.index('Material Description')
                tmos_index = all_columns.index('TMOS')
                if 'GF_Qty' in all_columns:
                    tmos_index = max(tmos_index, all_columns.index('GF_Qty'))
                all_cols_between = all_columns[mat_index:tmos_index + 1]

                if 'AMC' in all_cols_between and 'NMOS' in all_cols_between:
                    for col in all_cols_between:
                        if col not in columns_to_exclude:
                            report_columns.append(col)
                    if 'AMC' in report_columns:
                        amc_pos = report_columns.index('AMC')
                        report_columns.insert(amc_pos + 1, 'NMOS')
                else:
                    for col in all_cols_between:
                        if col not in columns_to_exclude:
                            report_columns.append(col)
            else:
                for col in all_columns:
                    if col not in columns_to_exclude:
                        report_columns.append(col)

            report_columns = list(dict.fromkeys(report_columns))
            if 'Material Description' in report_columns:
                report_columns.remove('Material Description')
                report_columns.insert(0, 'Material Description')

            # ------------------------------------------------------------------
            # 2) Column classification
            # ------------------------------------------------------------------
            TEXT_COLUMNS  = {'Material Description', 'Status', 'Expiry'}
            PO_COLUMNS    = {'GIT_PO', 'LC_PO', 'WB_PO', 'TMD_PO'}
            FLOAT_COLUMNS = {'NMOS', 'GIT_MOS', 'LC_MOS', 'WB_MOS', 'TMD_MOS', 'TMOS', 'GF_MOS'}

            BRANCH_COLUMNS = {c for c in report_columns if 'Branch' in c}

            FIXED_WIDTHS = {
                'Expiry': 48,
                'Status': 50,
            }
            MD_WIDTH = 32

            # ------------------------------------------------------------------
            # 3) Build clean data
            # ------------------------------------------------------------------
            def _is_subcategory_header(material):
                if not isinstance(material, str):
                    return False
                for parent, meta in PROGRAM_HIERARCHY.items():
                    if material.strip() in meta.get("subcategories", []):
                        return True
                return False

            def _clean_text(s):
                if s is None:
                    return None
                try:
                    if pd.isna(s):
                        return None
                except Exception:
                    pass
                s = str(s).strip().lstrip("'\"")
                if s == "" or s.lower() == "nan":
                    return None
                if s.endswith(".0") and s[:-2].replace(".", "", 1).replace(",", "").isdigit():
                    s = s[:-2]
                return s

            def _stack_pos(val):
                """Return PO value:
               - Single PO       -> integer (real number, no triangle, no decimals)
               - Multiple POs    -> text, one PO per line (forced-text to avoid triangle)
            """
                if val is None:
                    return None
                try:
                    if pd.isna(val):
                        return None
                except Exception:
                    pass

                s = str(val).strip().lstrip("'\"")
                if s == "" or s.lower() == "nan":
                    return None

                parts = re.split(r"[,\;\|\n]+", s)
                cleaned = []
                for p in parts:
                    p = p.strip().lstrip("'\"")
                    if not p:
                        continue
                    if p.endswith(".0") and p[:-2].replace(".", "", 1).isdigit():
                        p = p[:-2]
                    cleaned.append(p)

                if not cleaned:
                    return None

                # Single PO → store as integer (real number, no triangle, no float)
                if len(cleaned) == 1:
                    try:
                        return int(cleaned[0])
                    except ValueError:
                        return cleaned[0]

                # Multiple POs → stacked text with forced-text marker
                return "'" + "\n".join(cleaned)

            def _coerce_value(col, val):
                if val is None:
                    return None
                try:
                    if pd.isna(val):
                        return None
                except Exception:
                    pass

                if col in PO_COLUMNS:
                    return _stack_pos(val)
                if col in TEXT_COLUMNS:
                    return _clean_text(val)

                s = str(val).replace(",", "").strip()
                if s == "" or s.lower() == "nan":
                    return None
                try:
                    num = float(s)
                except Exception:
                    return None

                if col in FLOAT_COLUMNS:
                    return round(num, 2)
                return int(round(num))

            def _clean_sheet_df(df_part):
                df_out = df_part[report_columns].copy()
                for col in df_out.columns:
                    df_out[col] = df_out[col].apply(lambda v: _coerce_value(col, v))
                return df_out

            def _build_ordered_materials(program_name):
                if program_name not in google_sheets:
                    return []
                prog_df = google_sheets[program_name]
                if prog_df.empty or 'Material Description' not in prog_df.columns:
                    return []
                subcats = PROGRAM_HIERARCHY.get(program_name, {}).get("subcategories", [])
                ordered = []
                current_sub = None
                for mat in prog_df['Material Description'].dropna().tolist():
                    mat_str = str(mat).strip()
                    if mat_str in subcats:
                        current_sub = mat_str
                    else:
                        ordered.append((current_sub, mat_str))
                return ordered

            SUBCAT_PALETTE = [
                "1F4E78", "2E75B6", "7030A0", "C00000",
                "BF8F00", "375623", "833C00", "203864",
            ]

            TITLE_FILL  = PatternFill("solid", fgColor="1A5276")
            HEADER_FILL = PatternFill("solid", fgColor="2E75B6")
            BAND_FILL   = PatternFill("solid", fgColor="F2F7FB")

            TITLE_FONT  = Font(name="Times New Roman", size=14, bold=True, color="FFFFFF")
            HEADER_FONT = Font(name="Times New Roman", size=12, bold=True, color="FFFFFF")
            SUBCAT_FONT = Font(name="Times New Roman", size=12, bold=True, color="FFFFFF")
            DATA_FONT   = Font(name="Times New Roman", size=12, color="1F2A38")

            thin = Side(border_style="thin", color="B8C6D6")
            BORDER = Border(left=thin, right=thin, top=thin, bottom=thin)

            LEFT_WRAP_TOP = Alignment(horizontal="left", vertical="top", wrap_text=True)

            def _branch_header_text(name):
                if name not in BRANCH_COLUMNS:
                    return name
                parts = name.rsplit(" ", 1)
                if len(parts) == 2:
                    return parts[0] + "\n" + parts[1]
                return name

            # ------------------------------------------------------------------
            # 4) Build {sheet_name: rows}
            # ------------------------------------------------------------------
            sheets_to_write = {}

            def _build_sheet_rows(program_name, filtered_df):
                ordered_mats = _build_ordered_materials(program_name)
                if not ordered_mats:
                    clean = _clean_sheet_df(filtered_df)
                    return [("header", None)] + [("data", r) for _, r in clean.iterrows()]
                clean_df = _clean_sheet_df(filtered_df)
                clean_df = clean_df.set_index('Material Description', drop=False)
                rows = [("header", None)]
                current_sub_emitted = None
                for subcat, material in ordered_mats:
                    if material not in clean_df.index:
                        continue
                    if subcat and subcat != current_sub_emitted:
                        rows.append(("subcategory", subcat))
                        current_sub_emitted = subcat
                    matches = clean_df.loc[[material]]
                    if isinstance(matches, pd.DataFrame):
                        for _, r in matches.iterrows():
                            rows.append(("data", r))
                    else:
                        rows.append(("data", matches))
                return rows

            if show_all_programs or len(selected_programs_list) == 0:
                ordered_programs = list(PROGRAM_ORDER_LIST) + [
                    p for p in google_sheets.keys() if p not in PROGRAM_ORDER_LIST
                ]
                for prog_name in ordered_programs:
                    if prog_name not in google_sheets:
                        continue
                    prog_sheet_df = google_sheets[prog_name]
                    if prog_sheet_df.empty or 'Material Description' not in prog_sheet_df.columns:
                        continue
                    prog_materials = prog_sheet_df['Material Description'].dropna().tolist()
                    prog_materials = [m for m in prog_materials if not _is_subcategory_header(m)]
                    prog_filtered = df_filtered[df_filtered['Material Description'].isin(prog_materials)].copy()
                    if prog_filtered.empty:
                        continue
                    sheets_to_write[prog_name] = _build_sheet_rows(prog_name, prog_filtered)

            elif len(selected_programs_list) == 1:
                prog_name = selected_programs_list[0]
                sheet_label = prog_name
                if subcategory_filter != "All":
                    sheet_label = f"{prog_name} - {subcategory_filter}"
                if prog_name in google_sheets:
                    sheets_to_write[sheet_label] = _build_sheet_rows(prog_name, df_filtered)
                else:
                    clean = _clean_sheet_df(df_filtered)
                    sheets_to_write[sheet_label] = [("header", None)] + [("data", r) for _, r in clean.iterrows()]

            else:
                for prog_name in selected_programs_list:
                    if prog_name not in google_sheets:
                        continue
                    prog_sheet_df = google_sheets[prog_name]
                    if prog_sheet_df.empty or 'Material Description' not in prog_sheet_df.columns:
                        continue
                    prog_materials = prog_sheet_df['Material Description'].dropna().tolist()
                    prog_materials = [m for m in prog_materials if not _is_subcategory_header(m)]
                    prog_filtered = df_filtered[df_filtered['Material Description'].isin(prog_materials)].copy()
                    if prog_filtered.empty:
                        continue
                    sheets_to_write[prog_name] = _build_sheet_rows(prog_name, prog_filtered)

            # ------------------------------------------------------------------
            # 5) Descriptive file label
            # ------------------------------------------------------------------
            if show_all_programs or len(selected_programs_list) == 0:
                file_label = "All Programs"
            elif len(selected_programs_list) == 1:
                file_label = selected_programs_list[0]
                if subcategory_filter != "All":
                    file_label = f"{file_label} - {subcategory_filter}"
            elif len(selected_programs_list) == 2:
                file_label = f"{selected_programs_list[0]} and {selected_programs_list[1]}"
            else:
                file_label = ", ".join(selected_programs_list[:-1]) + f" and {selected_programs_list[-1]}"

            safe_file_label = re.sub(r'[\[\]:\*\?/\\]', '', file_label).strip()
            safe_file_label = re.sub(r'\s+', ' ', safe_file_label)

            file_name = (
                f"{safe_file_label} Medicines Monthly National and Pipeline Stock Status Report "
            f"{datetime.now().strftime('%Y%m%d')}.xlsx"
            )

            # ------------------------------------------------------------------
            # 6) Compute column widths
            # ------------------------------------------------------------------
            def _compute_col_widths(sheets_map):
                widths = {}
                for col in report_columns:
                    if col in FIXED_WIDTHS:
                        widths[col] = FIXED_WIDTHS[col]
                        continue
                    if col == 'Material Description':
                        widths[col] = MD_WIDTH
                        continue
                    if col in PO_COLUMNS:
                        widths[col] = 14
                        continue
                    if col in BRANCH_COLUMNS:
                        widths[col] = 14
                        continue
                    if col in FLOAT_COLUMNS:
                        widths[col] = 12
                        continue

                    header_len = len(str(col))
                    max_val_len = 0
                    for _sheet, rows in sheets_map.items():
                        for rt, payload in rows:
                            if rt != "data":
                                continue
                            v = payload[col] if col in payload.index else None
                            if v is None:
                                continue
                            try:
                                if pd.isna(v):
                                    continue
                            except Exception:
                                pass
                            s = str(v)
                            if s.strip() == "":
                                continue
                            for line in s.split("\n"):
                                max_val_len = max(max_val_len, len(line))

                    w = max(header_len, max_val_len) + 2
                    widths[col] = min(max(w, 10), 30)

                return widths

            COL_WIDTHS = _compute_col_widths(sheets_to_write)

            # ------------------------------------------------------------------
            # 7) Write workbook
            # ------------------------------------------------------------------
            if not sheets_to_write:
                st.warning("⚠️ No data available to generate the report. Please adjust your filters.")
            else:
                output = BytesIO()
                try:
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        pd.DataFrame().to_excel(writer, sheet_name="__tmp__", index=False)
                        del writer.book["__tmp__"]

                        used_names = set()
                        n_cols = len(report_columns)
                        last_col_letter = get_column_letter(n_cols)

                        col_formats = {}
                        for col in report_columns:
                            if col in PO_COLUMNS or col in TEXT_COLUMNS:
                                col_formats[col] = "@"
                            elif col in FLOAT_COLUMNS:
                                col_formats[col] = "#,##0.00"
                            else:
                                col_formats[col] = "#,##0"

                        po_col_letters = [
                            get_column_letter(report_columns.index(c) + 1)
                            for c in report_columns if c in PO_COLUMNS
                        ]
                        md_col_letter = get_column_letter(report_columns.index('Material Description') + 1) \
                            if 'Material Description' in report_columns else None
                        md_col_width = COL_WIDTHS.get('Material Description', MD_WIDTH)

                        for sheet_name, rows in sheets_to_write.items():
                            safe_name = re.sub(r'[\[\]:\*\?/\\]', '_', str(sheet_name)).strip()
                            safe_name = safe_name[:31] if safe_name else "Sheet"
                            base_name = safe_name
                            i = 1
                            while safe_name in used_names:
                                suffix = f"_{i}"
                                safe_name = base_name[:31 - len(suffix)] + suffix
                                i += 1
                            used_names.add(safe_name)

                            ws = writer.book.create_sheet(title=safe_name)

                            # ---------- Row 1: Title ----------
                            ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n_cols)
                            tcell = ws.cell(
                                row=1, column=1,
                                value=f"{sheet_name.upper()} — Medicines Monthly National and Pipeline Stock Status Report"
                            )
                            tcell.font = TITLE_FONT
                            tcell.fill = TITLE_FILL
                            tcell.alignment = LEFT_WRAP_TOP
                            ws.row_dimensions[1].height = 30

                            # ---------- Row 2: Column header ----------
                            header_row_idx = 2
                            for c_idx, col_name in enumerate(report_columns, start=1):
                                display_name = _branch_header_text(col_name)
                                cell = ws.cell(row=header_row_idx, column=c_idx, value=display_name)
                                cell.font = HEADER_FONT
                                cell.fill = HEADER_FILL
                                cell.alignment = Alignment(
                                    horizontal="left",
                                    vertical="top",
                                    wrap_text=True,
                                    shrink_to_fit=False,
                                )
                                cell.border = BORDER
                            ws.row_dimensions[header_row_idx].height = 50

                            # ---------- Rows 3+: Data ----------
                            current_row = header_row_idx + 1
                            data_band_index = 0
                            subcat_color_idx = 0

                            for row_type, payload in rows:
                                if row_type == "header":
                                    continue

                                if row_type == "subcategory":
                                    ws.merge_cells(start_row=current_row, start_column=1,
                                                   end_row=current_row, end_column=n_cols)
                                    cell = ws.cell(row=current_row, column=1, value=f"▶  {payload}")
                                    color = SUBCAT_PALETTE[subcat_color_idx % len(SUBCAT_PALETTE)]
                                    subcat_color_idx += 1
                                    cell.fill = PatternFill("solid", fgColor=color)
                                    cell.font = SUBCAT_FONT
                                    cell.alignment = Alignment(horizontal="left", vertical="top",
                                                               indent=1, wrap_text=False)
                                    cell.border = BORDER
                                    for c_idx in range(2, n_cols + 1):
                                        ws.cell(row=current_row, column=c_idx).border = BORDER
                                    ws.row_dimensions[current_row].height = 22
                                    current_row += 1
                                    data_band_index = 0
                                    continue

                                if row_type == "data":
                                    r = payload
                                    band_fill = BAND_FILL if data_band_index % 2 == 1 else None

                                    # ---- estimate lines for each column ----
                                    md_lines = 1
                                    other_max_lines = 1
                                    for col_name in report_columns:
                                        val = r[col_name] if col_name in r.index else None
                                        if val is None:
                                            continue
                                        try:
                                            if pd.isna(val):
                                                continue
                                        except Exception:
                                            pass
                                        text = str(val)
                                        if text.strip() == "":
                                            continue
                                        cw = COL_WIDTHS.get(col_name, 18)
                                        total_lines = 0
                                        for part in text.split("\n"):
                                            total_lines += max(1, -(-len(part) // max(1, cw)))
                                        if col_name == 'Material Description':
                                            md_lines = max(md_lines, total_lines)
                                        else:
                                            other_max_lines = max(other_max_lines, total_lines)

                                    estimated_lines = max(md_lines, other_max_lines)
                                    needed_height = max(32, estimated_lines * 18)

                                    for c_idx, col_name in enumerate(report_columns, start=1):
                                        val = r[col_name] if col_name in r.index else None
                                        cell = ws.cell(row=current_row, column=c_idx)

                                        is_blank = False
                                        if val is None:
                                            is_blank = True
                                        else:
                                            try:
                                                if pd.isna(val):
                                                    is_blank = True
                                            except Exception:
                                                pass
                                            if isinstance(val, str) and val.strip() == "":
                                                is_blank = True

                                        if not is_blank:
                                            if col_name in PO_COLUMNS:
                                                # int → real number, no triangle, no decimals
                                                # '…' string → forced text (multi-PO stacked)
                                                if isinstance(val, str) and val.startswith("'"):
                                                    cell.value = val
                                                    cell.number_format = "@"
                                                elif isinstance(val, (int, float)):
                                                    cell.value = int(val)
                                                    cell.number_format = "0"
                                                else:
                                                    cell.value = str(val)
                                                    cell.number_format = "@"
                                            elif col_name in TEXT_COLUMNS:
                                                cell.value = str(val)
                                                cell.data_type = "s"
                                                cell.number_format = "@"
                                            else:
                                                cell.value = val
                                                cell.number_format = col_formats.get(col_name, "General")

                                        cell.font = DATA_FONT
                                        cell.alignment = LEFT_WRAP_TOP
                                        cell.border = BORDER
                                        if band_fill:
                                            cell.fill = band_fill

                                    # Force Material Description's own wrap height
                                    if md_col_letter is not None:
                                        md_text = r['Material Description'] if 'Material Description' in r.index else None
                                        if md_text is not None:
                                            try:
                                                md_is_na = pd.isna(md_text)
                                            except Exception:
                                                md_is_na = False
                                            if not md_is_na and str(md_text).strip() != "":
                                                s = str(md_text)
                                                md_lines_needed = 0
                                                for part in s.split("\n"):
                                                    md_lines_needed += max(1, -(-len(part) // max(1, md_col_width)))
                                                md_min_height = max(32, md_lines_needed * 18)
                                                needed_height = max(needed_height, md_min_height)

                                    ws.row_dimensions[current_row].height = needed_height
                                    data_band_index += 1
                                    current_row += 1

                            # ---------- Freeze + AutoFilter ----------
                            ws.freeze_panes = ws.cell(row=header_row_idx + 1, column=1)
                            ws.auto_filter.ref = f"A{header_row_idx}:{last_col_letter}{current_row - 1}"

                            # ---------- Kill green triangles on PO columns (SAFE) ----------
                            last_data_row = current_row - 1
                            try:
                                if _HAS_IGNORED_ERRORS and hasattr(ws, "ignored_errors"):
                                    for col_letter in po_col_letters:
                                        rng = f"{col_letter}{header_row_idx + 1}:{col_letter}{last_data_row}"
                                        ws.ignored_errors.append(
                                            IgnoredError(
                                                sqref=rng,
                                                numberStoredAsText=True,
                                                formula=False,
                                                emptyCellReference=False,
                                                listDataValidation=False,
                                                calculatedColumn=False,
                                                twoDigitTextYear=False,
                                                unlockedFormula=False,
                                                evalError=False,
                                            )
                                        )
                            except Exception:
                                pass

                            # ---------- Column widths + hide branch columns ----------
                            for c_idx, col_name in enumerate(report_columns, start=1):
                                letter = get_column_letter(c_idx)
                                width = COL_WIDTHS.get(col_name, 18)
                                ws.column_dimensions[letter].width = width

                                if col_name in BRANCH_COLUMNS:
                                    ws.column_dimensions[letter].hidden = True

                    output.seek(0)

                    # ------------------------------------------------------------------
                    # 8) Download button
                    # ------------------------------------------------------------------
                    n_sheets = len(sheets_to_write)

                    st.download_button(
                        label=f"📊 Download {program_display} Monthly National and Pipeline Stock Status Report (Excel)",
                        data=output,
                        file_name=file_name,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                        type="primary",
                        key="download_monthly_report_excel"
                    )
                    st.caption(
                        f"Report includes columns from Material Description to TMOS "
                    f"({len(report_columns)} columns) — {n_sheets} sheet(s), fully formatted with "
                    f"colorful headings, subcategory separators, frozen header, autofilter, "
                    f"wrapped text, stacked PO numbers, hidden branch columns and banded rows."
                    )

                except Exception as excel_error:
                    st.error(f"❌ Error creating Excel file: {excel_error}")
                    st.info("Please check the data and try again. No CSV fallback will be produced.")

            # ============================================
            # 📈 NSOH HISTORICAL TREND SECTION - INSIDE TAB 1 ONLY
            # ============================================
            st.markdown("---")
            st.markdown("<h4 style='font-size: 20px; font-weight: bold; font-family: Times New Roman;'>📈 NSOH Historical Trend</h4>", unsafe_allow_html=True)
            st.caption("Historical NSOH values from saved snapshots - rows are materials, columns are months with NSOH values")

            # Load snapshots from Supabase with caching
            @st.cache_data(ttl=300, show_spinner=False)
            def get_cached_nsoh_snapshots():
                """Cached version of load_nsoh_snapshots"""
                return load_nsoh_snapshots()

            # Use cached version
            if 'nsoh_snapshots' not in st.session_state:
                st.session_state.nsoh_snapshots = get_cached_nsoh_snapshots()

            snapshots_df = st.session_state.nsoh_snapshots

            if not snapshots_df.empty:
                # Create pivot table
                pivot_df = create_nsoh_pivot_table(snapshots_df)

                if not pivot_df.empty:
                    # Filter to only materials that are in the current filtered dataset
                    materials_in_filter = df_filtered['Material Description'].dropna().unique()
                    pivot_df = pivot_df[pivot_df.index.isin(materials_in_filter)]

                    # ============================================
                    # DATE RANGE FILTER - User selectable
                    # ============================================
                    st.markdown("#### 📅 Select Date Range")

                    # Get available months from the pivot table
                    available_months = get_available_months(snapshots_df)

                    if available_months:
                        # Create columns for the date range selector
                        col_date_from, col_date_to = st.columns(2)

                        with col_date_from:
                            # Default: the last 12 available months (or all of them if fewer than 12)
                            default_from_index = max(0, len(available_months) - 12)

                            selected_from = st.selectbox(
                                "From Month",
                                available_months,
                                index=default_from_index,
                                key="nsoh_trend_from"
                            )

                        with col_date_to:
                            # Default to last available month
                            default_to_index = len(available_months) - 1

                            selected_to = st.selectbox(
                                "To Month",
                                available_months,
                                index=default_to_index,
                                key="nsoh_trend_to"
                            )

                        # Validate selection
                        from_idx = available_months.index(selected_from)
                        to_idx = available_months.index(selected_to)

                        if from_idx <= to_idx:
                            # Filter columns based on selected date range
                            selected_months = available_months[from_idx:to_idx + 1]

                            # Filter the pivot table to only include selected months
                            pivot_df_filtered = pivot_df[selected_months]

                            st.info(f"📊 Showing data from {selected_from} to {selected_to} ({len(selected_months)} months)")
                        else:
                            st.warning("⚠️ 'From' date must be earlier than 'To' date. Please select a valid range.")
                            pivot_df_filtered = pivot_df
                    else:
                        st.info("No date data available")
                        pivot_df_filtered = pivot_df

                    if not pivot_df_filtered.empty:
                        # Sort materials by program order
                        master_order = []

                        # Get materials from selected programs in order
                        if show_all_programs or len(selected_programs_list) == 0:
                            # All programs - follow program order
                            for prog_name in PROGRAM_ORDER_LIST:
                                if prog_name in google_sheets and 'Material Description' in google_sheets[prog_name].columns:
                                    materials = google_sheets[prog_name]['Material Description'].dropna().tolist()
                                    # Filter out subcategory headers
                                    if prog_name in PROGRAM_HIERARCHY:
                                        subcategory_list = PROGRAM_HIERARCHY[prog_name]["subcategories"]
                                        materials = [m for m in materials if m not in subcategory_list]
                                    master_order.extend(materials)
                            # Add any remaining programs
                            for prog_name in google_sheets.keys():
                                if prog_name not in PROGRAM_ORDER_LIST and 'Material Description' in google_sheets[prog_name].columns:
                                    materials = google_sheets[prog_name]['Material Description'].dropna().tolist()
                                    if prog_name in PROGRAM_HIERARCHY:
                                        subcategory_list = PROGRAM_HIERARCHY[prog_name]["subcategories"]
                                        materials = [m for m in materials if m not in subcategory_list]
                                    master_order.extend(materials)
                        else:
                            # Selected programs only
                            for prog_name in selected_programs_list:
                                if prog_name in google_sheets and 'Material Description' in google_sheets[prog_name].columns:
                                    materials = google_sheets[prog_name]['Material Description'].dropna().tolist()
                                    # Filter out subcategory headers
                                    if prog_name in PROGRAM_HIERARCHY:
                                        subcategory_list = PROGRAM_HIERARCHY[prog_name]["subcategories"]
                                        materials = [m for m in materials if m not in subcategory_list]
                                    master_order.extend(materials)

                        # Remove duplicates while preserving order
                        seen = set()
                        master_order_unique = []
                        for m in master_order:
                            if m not in seen:
                                seen.add(m)
                                master_order_unique.append(m)
                        master_order = master_order_unique

                        # Remove duplicates from pivot_df_filtered index BEFORE reindexing
                        pivot_df_filtered = pivot_df_filtered.loc[~pivot_df_filtered.index.duplicated(keep='first')]

                        # Reorder pivot_df according to master order (only materials that exist in pivot)
                        pivot_df_filtered = pivot_df_filtered.reindex([m for m in master_order if m in pivot_df_filtered.index])

                        # Display the pivot table
                        st.dataframe(
                            pivot_df_filtered,
                            use_container_width=True,
                            height=min(600, (len(pivot_df_filtered) + 1) * 35)
                        )

                        # Download button for pivot table
                        st.download_button(
                            label="📥 Download NSOH Trend Data (Excel)",
                            data=pivot_df_filtered.reset_index().pipe(_xl),
                            file_name=f"nsoh_trend_{datetime.now().strftime('%Y%m%d')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True,
                            key="download_nsoh_trend"
                        )

                        # ============================================
                        # MATERIAL TREND VISUALIZATION
                        # ============================================
                        st.markdown("---")
                        st.markdown("#### 📊 NSOH Trend Visualization")

                        # Get material list
                        material_list = pivot_df_filtered.index.tolist()

                        if material_list:
                            # Dropdown for material selection
                            selected_material = st.selectbox(
                                "Select a material to view its NSOH trend:",
                                material_list,
                                key="nsoh_trend_material_select"
                            )

                            # Display the trend for the selected material
                            if selected_material and selected_material in pivot_df_filtered.index:
                                # Get the data for the selected material
                                material_data = pivot_df_filtered.loc[selected_material]

                                # Create a line chart
                                fig_trend = go.Figure()

                                fig_trend.add_trace(go.Scatter(
                                    x=material_data.index,
                                    y=material_data.values,
                                    mode='lines+markers+text',
                                    name=selected_material[:50] if len(selected_material) > 50 else selected_material,
                                    line=dict(color='#1a5276', width=3),
                                    marker=dict(size=10, color='#1a5276'),
                                    text=material_data.values,
                                    texttemplate='%{text:,.0f}',
                                    textposition='top center',
                                    textfont=dict(
                                        size=12,
                                        color='#1a5276',
                                        family='Arial Black'
                                    ),
                                    fill='tozeroy',
                                    fillcolor='rgba(26, 82, 118, 0.25)',
                                    hovertemplate='<b>%{x}</b><br>NSOH: %{y:,.0f} units<extra></extra>'
                                ))

                                fig_trend.add_hline(y=0, line_dash="dash", line_color="gray", line_width=1)

                                fig_trend.update_layout(
                                    title=f"NSOH Trend for {selected_material[:50]}" if len(selected_material) <= 50 else f"NSOH Trend for {selected_material[:47]}...",
                                    xaxis_title="Month",
                                    yaxis_title="NSOH (Units)",
                                    height=450,
                                    hovermode='x unified',
                                    plot_bgcolor='white',
                                    margin=dict(l=50, r=50, t=60, b=80)
                                )

                                fig_trend.update_xaxes(
                                    tickangle=0,
                                    gridcolor='lightgray',
                                    showgrid=True,
                                    gridwidth=0.5,
                                    range=[-0.5, len(material_data.index) - 0.5]
                                )

                                y_max = material_data.values.max() if len(material_data.values) > 0 else 100
                                y_min = material_data.values.min() if len(material_data.values) > 0 else 0
                                y_padding = (y_max - y_min) * 0.15 if y_max > y_min else 10

                                fig_trend.update_yaxes(
                                    gridcolor='lightgray',
                                    showgrid=True,
                                    gridwidth=0.5,
                                    zeroline=True,
                                    zerolinecolor='gray',
                                    zerolinewidth=1,
                                    range=[y_min - y_padding, y_max + y_padding + 10]
                                )

                                st.plotly_chart(fig_trend, use_container_width=True)
                            else:
                                st.info("Select a material to view its NSOH trend.")
                    else:
                        st.info("No data available for the selected date range.")
                else:
                    st.info("No pivot data available after filtering.")
            else:
                st.info("No NSOH snapshots available. Use the 'NSOH Snapshot Management' section in the sidebar to save snapshots.")
        else:
            st.warning("No data available to display in the stock status table.")

        # ===================================================
    # TAB 2 - KPIs & Analytics
    # ===================================================
with tab2:
    if _tab_open(tab2):
        if show_all_programs or len(selected_programs_list) == 0:
            program_display = "All Programs"
        elif len(selected_programs_list) == 1:
            program_display = selected_programs_list[0]
        else:
            program_display = f"{len(selected_programs_list)} Programs"

        if subcategory_filter != "All" and len(selected_programs_list) == 1:
            program_display = f"{selected_programs_list[0]} - {subcategory_filter}"

        st.markdown(f"<h3 style='font-size: 28px; font-weight: bold; font-family: Times New Roman;'>{program_display} Medicines Performance Metrics</h3>", unsafe_allow_html=True)

        if not df_filtered.empty and 'NMOS' in df_filtered.columns:
            nmos_values = pd.to_numeric(df_filtered['NMOS'], errors='coerce').dropna()
            Availability = (nmos_values > 1).mean() * 100 if len(nmos_values) > 0 else 0
            sap = nmos_range_stats(df_filtered)[0] if len(nmos_values) > 0 else 0

            if 'Distr. Gap' in df_filtered.columns:
                avail_gap_values = pd.to_numeric(df_filtered['Distr. Gap'], errors='coerce').dropna()
                avg_avail_gap = avail_gap_values.mean() if len(avail_gap_values) > 0 else 0
            else:
                avg_avail_gap = 0

            avail_delta = Availability - 100

            if -5 <= avg_avail_gap <= 5:
                avail_gap_status = "✅ Within Target (-5% to 5%)"
                avail_gap_delta = None
            elif avg_avail_gap > 5:
                avail_gap_status = f"⚠️ Above Target (+{avg_avail_gap - 5:.1f}% over)"
                avail_gap_delta = f"+{avg_avail_gap - 5:.1f}%"
            else:
                avail_gap_status = f"⚠️ Below Target ({avg_avail_gap + 5:.1f}% under)"
                avail_gap_delta = f"{avg_avail_gap + 5:.1f}%"

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("📈 Availability", f"{Availability:.1f}%", delta=f"{avail_delta:+.1f}%", delta_color="inverse")
                st.caption("Target: 100%")
            with col2:
                st.metric("🎯 SAP Achievement", f"{sap:.1f}%", delta=f"{sap - 65:.1f}%")
                st.caption("Target: 65%")
            with col3:
                st.metric("📊 Distr. Gap (Hubs% - Head Office%)", f"{avg_avail_gap:.1f}%", delta=avail_gap_delta, delta_color="inverse" if avg_avail_gap > 5 or avg_avail_gap < -5 else "off")
                st.caption(avail_gap_status)

            st.markdown("---")

            def create_kpi_fig(value, target, title):
                color = 'red' if value < target else 'black'
                return go.Figure(go.Indicator(mode="gauge+number", value=value, number={'suffix': '%', 'font': {'size': 36, 'color': color}}, title={'text': f"<b>{title}</b>", 'font': {'size': 24}}, gauge={'axis': {'range': [0, 100]}, 'bar': {'color': 'skyblue'}}))

            col1, col2 = st.columns(2)
            with col1:
                st.plotly_chart(create_kpi_fig(Availability, 100, "Availability"), use_container_width=True)
            with col2:
                st.plotly_chart(create_kpi_fig(sap, 65, "SAP"), use_container_width=True)

            try:
                if 'Stock Status' in df_filtered.columns:
                    status_counts = df_filtered['Stock Status'].replace("", np.nan).dropna().value_counts()
                    if not status_counts.empty:
                        fig = px.pie(values=status_counts.values, names=status_counts.index, hole=0.5, color=status_counts.index, color_discrete_map={"Stock Out": "red", "Understock": "yellow", "Normal Stock": "green", "Overstock": "skyblue"})
                        fig.update_traces(textposition='inside', textinfo='percent+value', textfont_size=16)
                        total_count = len(df_filtered[df_filtered['Stock Status'] != ""])
                        fig.update_layout(title={'text': f"{program_display} Stock Status (Total: {total_count} items)", 'x': 0, 'xanchor': 'left', 'font': {'size': 20, 'weight': 'bold'}}, annotations=[dict(text=f"Total<br>{total_count}", x=0.5, y=0.5, font_size=20, showarrow=False)])
                        st.plotly_chart(fig, use_container_width=True)
            except Exception:
                pass

            st.markdown("### 🚚 Pipeline Status Analysis")
            pipeline_cols = [col for col in ['GIT_MOS', 'LC_MOS', 'WB_MOS', 'TMD_MOS'] if col in df_filtered.columns]
            if pipeline_cols:
                pipeline_summary = df_filtered[pipeline_cols].sum()
                if pipeline_summary.sum() > 0:
                    fig_pipeline = px.pie(values=pipeline_summary.values, names=pipeline_summary.index, title="Pipeline MOS Distribution", color_discrete_sequence=px.colors.sequential.Blues_r)
                    fig_pipeline.update_traces(textposition='inside', textinfo='percent+label')
                    st.plotly_chart(fig_pipeline, use_container_width=True)
                else:
                    st.info("No pipeline data available")
            else:
                st.info("Pipeline MOS columns not available")

            st.markdown("### ⚠️ Critical Items - Stock Out")
            stock_out_items = df_filtered[df_filtered['Stock Status'] == 'Stock Out'][['Material Description', 'NSOH', 'AMC', 'NMOS']].copy()
            if not stock_out_items.empty:
                stock_out_items = stock_out_items.sort_values('NMOS').head(10)
                fig_stock_out = go.Figure(data=[go.Bar(x=stock_out_items['Material Description'], y=stock_out_items['NMOS'], marker_color='red', text=stock_out_items['NMOS'].round(2), textposition='outside', name='NMOS')])
                fig_stock_out.update_layout(title="Top 10 Stock Out Items (Lowest NMOS)", xaxis_title="Material Description", yaxis_title="Months of Stock (NMOS)", height=400, xaxis_tickangle=-45)
                st.plotly_chart(fig_stock_out, use_container_width=True)
            else:
                st.success("✅ No stock out items found!")

            try:
                if 'Material Description' in df_filtered.columns and 'NMOS' in df_filtered.columns:
                    mos_cols_chart = ['Material Description', 'NMOS', 'GIT_MOS', 'LC_MOS', 'WB_MOS', 'TMD_MOS', 'TMOS']
                    available_cols = [c for c in mos_cols_chart if c in df_filtered.columns]
                    mos_df = df_filtered[available_cols].copy()
                    mos_df['NMOS'] = pd.to_numeric(mos_df['NMOS'], errors='coerce')
                    mos_df = mos_df[mos_df['NMOS'].notna()]
                    if not mos_df.empty:
                        for c in ['GIT_MOS', 'LC_MOS', 'WB_MOS', 'TMD_MOS', 'TMOS']:
                            if c in mos_df.columns:
                                mos_df[c] = pd.to_numeric(mos_df[c], errors='coerce').fillna(0)

                        mos_df = mos_df.sort_values('NMOS', ascending=True).reset_index(drop=True)
                        split_len = 40
                        mos_df['Material_split'] = mos_df['Material Description'].apply(lambda x: '<br>'.join([str(x)[i:i + split_len] for i in range(0, len(str(x)), split_len)]))
                        _lo_c, _hi_c = levels_for(mos_df['Material Description'])
                        mos_df['NMOS_color'] = ["red" if x < 1 else "yellow" if x < lo_ else "green" if x <= hi_ else "skyblue"
                                                for x, lo_, hi_ in zip(mos_df['NMOS'], _lo_c, _hi_c)]

                        split_size = 10
                        for i in range(0, len(mos_df), split_size):
                            df_chunk = mos_df.iloc[i:i + split_size].copy()
                            df_chunk = df_chunk.iloc[::-1].reset_index(drop=True)
                            fig = go.Figure()
                            fig.add_trace(go.Bar(y=df_chunk['Material_split'], x=df_chunk['NMOS'], name='NMOS', orientation='h', marker=dict(color=df_chunk['NMOS_color']), text=df_chunk['NMOS'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else ""), textposition='inside', textfont_size=12, hovertemplate='NMOS: %{x:.1f} months<extra></extra>'))

                            pipeline_traces = [('GIT_MOS', 'cyan', 'GIT MOS'), ('LC_MOS', 'plum', 'LC MOS'), ('WB_MOS', 'gray', 'WB MOS'), ('TMD_MOS', 'orange', 'TMD MOS')]
                            for col, color, label in pipeline_traces:
                                if col in df_chunk.columns and (df_chunk[col] > 0).any():
                                    fig.add_trace(go.Bar(y=df_chunk['Material_split'], x=df_chunk[col], name=label, orientation='h', marker_color=color, text=df_chunk[col].apply(lambda x: f"{x:.1f}" if x > 0 else ""), textposition='inside', textfont_size=12, hovertemplate=f'{label}: %{{x:.1f}} months<extra></extra>'))

                            if 'TMOS' in df_chunk.columns:
                                fig.add_trace(go.Scatter(y=df_chunk['Material_split'], x=df_chunk['TMOS'], mode='text', text=df_chunk['TMOS'].apply(lambda x: f"TMOS: {x:.2f}" if x > 0 else ""), textposition='middle right', showlegend=False, textfont_size=12))

                            original_start = i + 1
                            original_end = i + len(df_chunk)
                            chart_title = f'{program_display} Stock Status - National and Pipeline (Medicines {original_start}-{original_end})'
                            fig.update_layout(barmode='stack', title=chart_title, xaxis_title='Months of Stock', yaxis_title='Material Description', height=max(500, 35 * len(df_chunk)), showlegend=True, legend=dict(orientation="v", yanchor="bottom", y=1.02, xanchor="right", x=1), margin=dict(l=20, r=120, t=60, b=20))
                            st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.error(f"Error creating MOS chart: {e}")

            try:
                if all(col in df_filtered.columns for col in ['Hubs', 'Head Office', 'NSOH', 'Material Description']):
                    hubs_vals = pd.to_numeric(df_filtered['Hubs'], errors='coerce').fillna(0)
                    ho_vals = pd.to_numeric(df_filtered['Head Office'], errors='coerce').fillna(0)
                    nsoh_vals = pd.to_numeric(df_filtered['NSOH'], errors='coerce')
                    valid_nsoh_mask = nsoh_vals.notna() & (nsoh_vals > 0)
                    if valid_nsoh_mask.any():
                        valid_indices = valid_nsoh_mask[valid_nsoh_mask].index
                        hubs_vals_valid = hubs_vals[valid_indices]
                        ho_vals_valid = ho_vals[valid_indices]
                        nsoh_vals_valid = nsoh_vals[valid_indices]
                        materials_valid = df_filtered.loc[valid_indices, 'Material Description']
                        hubs_pct = (hubs_vals_valid / nsoh_vals_valid * 100).fillna(0)
                        ho_pct = (ho_vals_valid / nsoh_vals_valid * 100).fillna(0)
                        nsoh_formatted = nsoh_vals_valid.apply(lambda x: f"{x:,.0f}")
                        bar_df = pd.DataFrame({'Material Description': materials_valid, 'Hubs%': hubs_pct, 'Head Office%': ho_pct, 'NSOH_display': nsoh_formatted}).reset_index(drop=True)
                        bar_df = bar_df.sort_values('Hubs%')
                        bar_df['Material_split'] = bar_df['Material Description'].apply(lambda x: '<br>'.join([str(x)[i:i + 25] for i in range(0, len(str(x)), 25)]))
                        n = 11
                        for i in range(0, len(bar_df), n):
                            df_chunk = bar_df.iloc[i:i + n]
                            fig_bar = go.Figure()
                            fig_bar.add_trace(go.Bar(y=df_chunk['Material_split'], x=df_chunk['Hubs%'], name='Hubs%', orientation='h', marker_color='skyblue', text=df_chunk['Hubs%'].apply(lambda x: f"{x:.1f}%" if x > 0 else ""), textposition='inside', textfont_size=12))
                            fig_bar.add_trace(go.Bar(y=df_chunk['Material_split'], x=df_chunk['Head Office%'], name='Head Office%', orientation='h', marker_color='orange', text=df_chunk['Head Office%'].apply(lambda x: f"{x:.1f}%" if x > 0 else ""), textposition='inside', textfont_size=12))
                            for idx, row in df_chunk.iterrows():
                                fig_bar.add_annotation(x=row['Hubs%'] + row['Head Office%'] + 2, y=row['Material_split'], text=f"NSOH: {row['NSOH_display']}", showarrow=False, font=dict(size=12), xanchor='left', yanchor='middle')
                            fig_bar.update_layout(barmode='stack', title=f'{program_display} Stock Distribution - Hubs vs Head Office (Materials {i + 1}-{i + len(df_chunk)})', xaxis_title='Percentage of NSOH (%)', yaxis_title='Material Description', xaxis={'range': [0, 120]}, height=max(600, 40 * len(df_chunk)), margin=dict(r=150))
                            st.plotly_chart(fig_bar, use_container_width=True)
                    else:
                        st.info("No materials with valid NSOH (>0) to display.")
            except Exception:
                pass
        else:
            st.info("No data available for KPI calculations.")

    # ---------------------------------------------------
# TAB 3 - Decision Briefs (UPDATED)
# ---------------------------------------------------
with tab3:
    if _tab_open(tab3):
        if show_all_programs or len(selected_programs_list) == 0:
            st.markdown("<h3 style='font-size: 28px; font-weight: bold; font-family: Times New Roman;'>All Programs - Medicines Needing Immediate Action</h3>", unsafe_allow_html=True)
        else:
            st.markdown(f"<h3 style='font-size: 28px; font-weight: bold; font-family: Times New Roman;'>{program_display} Medicines Needing Immediate Action</h3>", unsafe_allow_html=True)

        if not df_filtered.empty and 'Material Description' in df_filtered.columns:
            decision_df = df_filtered[['Material Description', 'NSOH', 'Expiry', 'AMC', 'NMOS', 'Status', 'Risk Type', 'Stock Status', 'Expiry Risk Details', 
                                       'GIT_MOS', 'LC_MOS', 'WB_MOS', 'TMD_MOS', 'GIT_PO', 'LC_PO', 'WB_PO', 'TMD_PO', 'Hubs%', 'Head Office%', 'CV Category']].copy()

            def get_identified_problems(row):
                if row.get('Stock Status') == 'Stock Out':
                    return "Stock Out"
                risk = row.get('Risk Type', '')
                if risk and risk != '':
                    risk = risk.replace('[', '').replace(']', '')
                    return risk
                return ''

            decision_df['Identified Problems'] = decision_df.apply(get_identified_problems, axis=1)

            def get_automated_recommendation(row):
                problem = row.get('Identified Problems', '')
                if problem == 'Expiry Risk':
                    cv_cat = row.get('CV Category', 'Unknown')
                    return get_expiry_risk_recommendation(row, cv_cat)
                elif problem == 'Critical Risk':
                    stock_rec = get_stock_out_recommendation(row)
                    cv_cat = row.get('CV Category', 'Unknown')
                    expiry_rec = get_expiry_risk_recommendation(row, cv_cat)
                    return f"{stock_rec}\n{expiry_rec}"
                elif problem in ['Risk of Stock out', 'Stock Out']:
                    return get_stock_out_recommendation(row)
                return ''

            decision_df['Recommendation'] = decision_df.apply(get_automated_recommendation, axis=1)
            decision_df = decision_df[decision_df['Identified Problems'] != ''].copy()

            if len(decision_df) > 0:
                for col in ['NSOH', 'AMC']:
                    if col in decision_df.columns:
                        decision_df[col] = decision_df[col].apply(format_number_with_commas)
                if 'NMOS' in decision_df.columns:
                    decision_df['NMOS'] = decision_df['NMOS'].apply(format_mos_with_decimals)
                if 'Hubs%' in decision_df.columns:
                    decision_df['Hubs%'] = decision_df['Hubs%'].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "")
                if 'Head Office%' in decision_df.columns:
                    decision_df['Head Office%'] = decision_df['Head Office%'].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "")

                # ============================================
                # COLORFUL QUICK SUMMARY
                # ============================================
                st.markdown("<h4 style='font-size: 24px; font-weight: bold; font-family: Times New Roman; margin-bottom: 15px;'>Quick Summary</h4>", unsafe_allow_html=True)

                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.markdown(f"""
                <div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 15px; padding: 20px; text-align: center; color: white; box-shadow: 0 4px 6px rgba(0,0,0,0.1);'>
                    <p style='margin: 0; font-size: 14px; opacity: 0.9;'>📋 Items with Problems</p>
                    <p style='margin: 5px 0 0 0; font-size: 32px; font-weight: bold;'>{len(decision_df)}</p>
                </div>
                """, unsafe_allow_html=True)
                with col2:
                    stock_out_count = len(decision_df[decision_df['Identified Problems'] == 'Stock Out'])
                    st.markdown(f"""
                <div style='background: linear-gradient(135deg, #ff4444 0%, #cc0000 100%); border-radius: 15px; padding: 20px; text-align: center; color: white; box-shadow: 0 4px 6px rgba(0,0,0,0.1);'>
                    <p style='margin: 0; font-size: 14px; opacity: 0.9;'>🔴 Stock Out</p>
                    <p style='margin: 5px 0 0 0; font-size: 32px; font-weight: bold;'>{stock_out_count}</p>
                </div>
                """, unsafe_allow_html=True)
                with col3:
                    risk_count = len(decision_df[decision_df['Identified Problems'] == 'Risk of Stock out'])
                    st.markdown(f"""
                <div style='background: linear-gradient(135deg, #ffa500 0%, #ff6b00 100%); border-radius: 15px; padding: 20px; text-align: center; color: white; box-shadow: 0 4px 6px rgba(0,0,0,0.1);'>
                    <p style='margin: 0; font-size: 14px; opacity: 0.9;'>🟡 Risk of Stock Out</p>
                    <p style='margin: 5px 0 0 0; font-size: 32px; font-weight: bold;'>{risk_count}</p>
                </div>
                """, unsafe_allow_html=True)
                with col4:
                    expiry_count = len(decision_df[decision_df['Identified Problems'] == 'Expiry Risk']) + len(decision_df[decision_df['Identified Problems'] == 'Critical Risk'])
                    st.markdown(f"""
                <div style='background: linear-gradient(135deg, #9b59b6 0%, #7d3c98 100%); border-radius: 15px; padding: 20px; text-align: center; color: white; box-shadow: 0 4px 6px rgba(0,0,0,0.1);'>
                    <p style='margin: 0; font-size: 14px; opacity: 0.9;'>⚠️ Expiry Risk</p>
                    <p style='margin: 5px 0 0 0; font-size: 32px; font-weight: bold;'>{expiry_count}</p>
                </div>
                """, unsafe_allow_html=True)

                st.markdown("---")

                # ============================================
                # PROBLEM CHECKBOX FILTERS (NO INFO TEXT, NO SELECT/CLEAR BUTTONS)
                # ============================================
                st.markdown("### 🔍 Filter by Problem Type")

                problem_types = sorted(decision_df['Identified Problems'].unique())
                problem_filters = {}

                # Create 2 columns for checkboxes
                col_left, col_right = st.columns(2)

                mid_point = (len(problem_types) + 1) // 2

                for idx, problem in enumerate(problem_types):
                    count = len(decision_df[decision_df['Identified Problems'] == problem])
                    checkbox_key = f"filter_problem_{problem.replace(' ', '_').replace('/', '_')}"

                    if checkbox_key not in st.session_state:
                        st.session_state[checkbox_key] = True

                    if idx < mid_point:
                        with col_left:
                            st.session_state[checkbox_key] = st.checkbox(
                                f"{problem} ({count})",
                                value=st.session_state[checkbox_key],
                                key=f"cb_{checkbox_key}"
                            )
                            problem_filters[problem] = st.session_state[checkbox_key]
                    else:
                        with col_right:
                            st.session_state[checkbox_key] = st.checkbox(
                                f"{problem} ({count})",
                                value=st.session_state[checkbox_key],
                                key=f"cb_{checkbox_key}"
                            )
                            problem_filters[problem] = st.session_state[checkbox_key]

                # Apply filters
                selected_problems = [problem for problem, is_checked in problem_filters.items() if is_checked]

                if selected_problems:
                    decision_df_filtered = decision_df[decision_df['Identified Problems'].isin(selected_problems)]
                else:
                    decision_df_filtered = decision_df

                st.markdown("---")

                st.markdown("### ✏️ Sales and Operational Planning")
                st.info("💡 Recommendations are auto-generated based on pipeline status (with PO numbers) and distribution patterns. You can edit them as needed.")

                display_columns = ['Material Description', 'NSOH', 'Expiry', 'AMC', 'NMOS', 'Status', 'CV Category', 'Identified Problems', 'Recommendation']
                available_display_columns = [col for col in display_columns if col in decision_df_filtered.columns]

                column_config = {
                    "Material Description": st.column_config.TextColumn("Material", width=250, disabled=True, pinned=True),
                    "NSOH": st.column_config.TextColumn("NSOH", width=100, disabled=True),
                    "Expiry": st.column_config.TextColumn("Expiry", width=120, disabled=True),
                    "AMC": st.column_config.TextColumn("AMC", width=100, disabled=True),
                    "NMOS": st.column_config.TextColumn("NMOS", width=80, disabled=True),
                    "Status": st.column_config.TextColumn("Status", width=100, disabled=True),
                    "CV Category": st.column_config.TextColumn("CV Category", width=120, disabled=True),
                    "Identified Problems": st.column_config.TextColumn("Problem", width=120, disabled=True),
                    "Recommendation": st.column_config.TextColumn("Recommendation", width=450, disabled=False)
                }

                edited_result = st.data_editor(
                    decision_df_filtered[available_display_columns],
                    column_config=column_config,
                    use_container_width=True, 
                    hide_index=True, 
                    height=min(600, (len(decision_df_filtered) + 1) * 45), 
                    num_rows="fixed"
                )

                for idx, row in edited_result.iterrows():
                    st.session_state.saved_recommendations[row['Material Description']] = {
                        'recommendation': row['Recommendation']
                    }

                col_download1, col_download2 = st.columns(2)
                with col_download1:
                    st.download_button(
                        label="📥 Download Current View (Excel)", 
                        data=edited_result.pipe(_xl), 
                        file_name=f"{program_display.replace(' ', '_')}_decision_briefs_{datetime.now().strftime('%Y%m%d')}.xlsx".replace(" ", "_"), 
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                with col_download2:
                    st.download_button(
                        label="📊 Download Full Data (Excel)", 
                        data=decision_df.pipe(_xl), 
                        file_name=f"{program_display.replace(' ', '_')}_decision_briefs_full_{datetime.now().strftime('%Y%m%d')}.xlsx".replace(" ", "_"), 
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )

                if st.button("🗑️ Clear All Recommendations", use_container_width=True):
                    st.session_state.saved_recommendations = {}
                    st.rerun()

                st.markdown("---")

                if len(decision_df_filtered) > 0:
                    st.markdown("### 📇 Card View with Recommendations")

                    for idx, row in decision_df_filtered.iterrows():
                        identified_problem = row.get('Identified Problems', '')

                        if identified_problem == "Critical Risk":
                            status_color = "#9b59b6"
                        elif identified_problem == "Stock Out":
                            status_color = "#ff4444"
                        elif identified_problem in ["Risk of Stock out", "Expiry Risk"]:
                            status_color = "#ffa500"
                        else:
                            status_color = "#ffa500"

                        recommendation_text = row.get('Recommendation', '')
                        cv_category = row.get('CV Category', 'N/A')

                        material_desc = row.get('Material Description', 'N/A')
                        if pd.isna(material_desc) or material_desc is None:
                            material_desc = 'N/A'
                        else:
                            material_desc = str(material_desc)[:60]

                        expiry_details = row.get('Expiry Risk Details', '')
                        expiry_display = row.get('Expiry', 'N/A')
                        if expiry_details and expiry_details != '':
                            expiry_display = f"{expiry_display} ⚠️ {expiry_details}"

                        st.markdown(f"""
                    <div class="stock-card" style='border-left: 4px solid {status_color}; margin-bottom: 15px;'>
                        <h4 style='color: {status_color}; margin-bottom: 10px;'>{material_desc}</h4>
                        <p><strong>📦 NSOH:</strong> {row.get('NSOH', 'N/A')}</p>
                        <p><strong>📅 Expiry:</strong> {expiry_display}</p>
                        <p><strong>📈 AMC:</strong> {row.get('AMC', 'N/A')}</p>
                        <p><strong>⏰ NMOS:</strong> <span style='color: {status_color}; font-weight: bold;'>{row.get('NMOS', 'N/A')}</span></p>
                        <p><strong>📊 Status:</strong> {row.get('Status', 'N/A')}</p>
                        <p><strong>⚠️ Identified Problem:</strong> <span style='color: {status_color}; font-weight: bold;'>{identified_problem}</span></p>
                        <p><strong>📊 CV Category:</strong> {cv_category}</p>
                        <p><strong>💡 Recommendation:</strong> <span style='background-color: #f0f2f6; padding: 5px; border-radius: 5px; display: inline-block;'>{recommendation_text}</span></p>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.warning("No items match the selected problem filters.")
            else:
                st.success("✅ No medicines with identified problems! All items are within normal stock levels.")
                st.balloons()
        else:
            st.info("No data available.")

# ---------------------------------------------------
# TAB 4 - Hubs Distribution (COMPLETE FIXED CODE)
# ---------------------------------------------------
with tab4:
    if _tab_open(tab4):
        try:
            # ===== CRITICAL FIX: REMOVE COMMAS FROM STRING NUMBERS =====
            for col in df.columns:
                if df[col].dtype == 'object':
                    df[col] = df[col].astype(str).str.replace(',', '', regex=False)
            # ===========================================================

            if not df.empty:
                if branch_amc_data is not None and 'Material Description' in df.columns and 'Material Description' in branch_amc_data.columns and not branch_amc_data.empty:
                    branch_cols = [col for col in df.columns if 'Branch' in col or col == 'Material Description']
                    gh = df[branch_cols].copy() if branch_cols else pd.DataFrame()

                    st.markdown("<h4 style='font-size: 24px; font-weight: bold; font-family: Times New Roman;'>Stock Distribution Across Hubs by MOS</h4>", unsafe_allow_html=True)

                    merged_df = pd.merge(gh, branch_amc_data, on='Material Description', how='inner', suffixes=('_gh', '_cf'))

                    if not merged_df.empty:
                        gh_cols = [col for col in gh.columns if col != 'Material Description']
                        cf_cols = [col for col in branch_amc_data.columns if col != 'Material Description']
                        division_data = {'Material Description': merged_df['Material Description']}

                        min_cols = min(len(gh_cols), len(cf_cols))

                        for i in range(min_cols):
                            gh_col = gh_cols[i]
                            cf_col = cf_cols[i]
                            display_col_name = gh_col
                            gh_values = pd.to_numeric(merged_df[f"{gh_col}_gh"], errors='coerce')
                            cf_values = pd.to_numeric(merged_df[f"{cf_col}_cf"], errors='coerce')
                            with np.errstate(divide='ignore', invalid='ignore'):
                                division_result = np.where(cf_values != 0, gh_values / cf_values, np.nan)
                            division_data[display_col_name] = division_result

                        division_df = pd.DataFrame(division_data)
                        division_df = division_df.replace([np.inf, -np.inf], np.nan).round(2)

                        if division_df.shape[1] > 1:
                            branch_cols_list = [col for col in division_df.columns if col != 'Material Description']
                            division_df['CV (%)'] = division_df[branch_cols_list].apply(lambda row: calculate_coefficient_of_variation(row), axis=1)
                            division_df['CV (%)'] = division_df['CV (%)'].round(1)
                            cols = ['Material Description', 'CV (%)'] + branch_cols_list
                            division_df = division_df[cols]

                            def categorize_cv(cv_value):
                                if pd.isna(cv_value):
                                    return "Unknown"
                                elif cv_value < 50:
                                    return "Low variation"
                                elif cv_value <= 100:
                                    return "Moderate variation"
                                else:
                                    return "High variation"

                            division_df['CV Category'] = division_df['CV (%)'].apply(categorize_cv)
                            cv_counts = division_df['CV Category'].value_counts()

                            col1, col2, col3, col4 = st.columns(4)
                            with col1:
                                st.metric("Total Materials", len(division_df))
                            if 'Low variation' in cv_counts:
                                with col2:
                                    low_count = cv_counts['Low variation']
                                    low_pct = (low_count / len(division_df) * 100) if len(division_df) > 0 else 0
                                    st.metric("Low Variation (<50%)", f"{low_count} ({low_pct:.1f}%)")
                            if 'Moderate variation' in cv_counts:
                                with col3:
                                    mod_count = cv_counts['Moderate variation']
                                    mod_pct = (mod_count / len(division_df) * 100) if len(division_df) > 0 else 0
                                    st.metric("Moderate Variation (50-100%)", f"{mod_count} ({mod_pct:.1f}%)")
                            if 'High variation' in cv_counts:
                                with col4:
                                    high_count = cv_counts['High variation']
                                    high_pct = (high_count / len(division_df) * 100) if len(division_df) > 0 else 0
                                    st.metric("High Variation (>100%)", f"{high_count} ({high_pct:.1f}%)")

                            # ============================================
                            # GET MASTER MATERIAL ORDER FROM PROGRAM (WITH DEDUPLICATION - FIXED)
                            # ============================================
                            # Initialize as empty list
                            master_material_order = []

                            # Use a set to track seen materials for deduplication
                            seen_materials = set()

                            # Define program order
                            program_order_list = ["Malaria", "HIV", "OI", "Hepatitis", "STI", "TB", "Drug Susceptible -TB Medicine (DS-TB)", "Drug Resisitance -TB Medicine (DR-TB)",
                                                  "Leprosy Medicines", "Nutrition","Lab TB","TB diagnostics& Laboratory reagent","TB Lab Supplies","HIV VL Reagents","CD4 _AHD _HIV_RTKs"]

                            if google_sheets:
                                # Collect materials in program order - WITH DEDUPLICATION
                                for prog in program_order_list:
                                    if prog in google_sheets:
                                        prog_df = google_sheets[prog]
                                        if 'Material Description' in prog_df.columns:
                                            for material in prog_df['Material Description'].dropna().tolist():
                                                # Skip subcategory headers
                                                is_header = False
                                                if prog in PROGRAM_HIERARCHY:
                                                    subcategory_list = PROGRAM_HIERARCHY[prog]["subcategories"]
                                                    if material in subcategory_list:
                                                        is_header = True
                                                if not is_header and material not in seen_materials:
                                                    seen_materials.add(material)
                                                    master_material_order.append(material)

                                # Add any remaining programs not in the predefined list - WITH DEDUPLICATION
                                for prog in google_sheets.keys():
                                    if prog not in program_order_list:
                                        prog_df = google_sheets[prog]
                                        if 'Material Description' in prog_df.columns:
                                            for material in prog_df['Material Description'].dropna().tolist():
                                                if material not in seen_materials:
                                                    seen_materials.add(material)
                                                    master_material_order.append(material)

                            # If no program order found, use sorted order (also deduplicated)
                            if not master_material_order:
                                master_material_order = sorted(df['Material Description'].dropna().unique())

                            # ============================================
                            # MOS Heatmap - Using master program order (WITH FIX)
                            # ============================================
                            if division_df.shape[1] > 2:
                                branch_cols_list = [col for col in division_df.columns if col not in ['Material Description', 'CV (%)', 'CV Category']]
                                heatmap_df = division_df.copy()

                                # CRITICAL FIX: Remove duplicates from heatmap_df index BEFORE reindexing
                                heatmap_df = heatmap_df.set_index('Material Description')
                                # Remove duplicate indices from heatmap_df itself
                                heatmap_df = heatmap_df[~heatmap_df.index.duplicated(keep='first')]

                                # Then filter master_material_order to only include materials in heatmap_df
                                # AND remove any duplicates
                                unique_master_order = []
                                for m in master_material_order:
                                    if m in heatmap_df.index and m not in unique_master_order:
                                        unique_master_order.append(m)

                                # Reindex with the unique ordered list
                                heatmap_df = heatmap_df.reindex(unique_master_order)
                                heatmap_df = heatmap_df.reset_index()

                                heatmap_df_indexed = heatmap_df.set_index('Material Description')
                                heatmap_df_indexed = heatmap_df_indexed[branch_cols_list]
                                heatmap_df_transposed = heatmap_df_indexed.T
                                total_materials = len(heatmap_df_transposed.columns)
                                materials_per_page = 11

                                if total_materials > materials_per_page:
                                    total_pages = (total_materials + materials_per_page - 1) // materials_per_page
                                    col1, col2, col3 = st.columns([1, 3, 1])
                                    with col1:
                                        if st.button("◀ Previous", key="heatmap_prev"):
                                            if st.session_state.heatmap_page > 1:
                                                st.session_state.heatmap_page -= 1
                                                st.rerun()
                                    with col2:
                                        st.markdown(f"<h5 style='text-align: center;'>Page {st.session_state.heatmap_page} of {total_pages}</h5>", unsafe_allow_html=True)
                                    with col3:
                                        if st.button("Next ▶", key="heatmap_next"):
                                            if st.session_state.heatmap_page < total_pages:
                                                st.session_state.heatmap_page += 1
                                                st.rerun()
                                    start_idx = (st.session_state.heatmap_page - 1) * materials_per_page
                                    end_idx = min(start_idx + materials_per_page, total_materials)
                                    page_materials = heatmap_df_transposed.columns[start_idx:end_idx]
                                    heatmap_page_df = heatmap_df_transposed[page_materials]
                                    st.info(f"Showing materials {start_idx + 1} to {end_idx} of {total_materials}")
                                else:
                                    heatmap_page_df = heatmap_df_transposed

                                fig = go.Figure(data=go.Heatmap(
                                    z=heatmap_page_df.values, y=heatmap_page_df.index, x=heatmap_page_df.columns,
                                    colorscale=[[0.0, 'red'], [0.125, 'yellow'], [0.5, 'green'], [1.0, 'skyblue']],
                                    zmin=0, zmax=8, text=heatmap_page_df.values.round(1), texttemplate='%{text}', textfont={"size": 14},
                                    colorbar=dict(title="MOS", tickvals=[0.5, 1, 2, 4, 6, 8], ticktext=['0.5', '1', '2', '4', '6', '8+']),
                                    hovertemplate='<b>Material:</b> %{x}<br><b>Branch:</b> %{y}<br><b>MOS:</b> %{z:.2f} months<br><extra></extra>'
                                ))
                                fig.update_layout(xaxis={'title': 'Material Description', 'tickangle': -45, 'tickfont': {'size': 12}}, 
                                                yaxis={'title': 'Branches', 'tickfont': {'size': 12}}, height=650, margin=dict(l=120, r=120, t=50, b=200))
                                st.plotly_chart(fig, use_container_width=True)

                                st.markdown("#### MOS Thresholds:")
                                col1, col2, col3, col4 = st.columns(4)
                                with col1:
                                    st.markdown("🔴 **< 0.5** : Stock Out")
                                with col2:
                                    st.markdown("🟡 **0.5 - 1** : Understock")
                                with col3:
                                    st.markdown("🟢 **1 - 4** : Normal Stock")
                                with col4:
                                    st.markdown("🔵 **> 4** : Overstock")

                                # ============================================
                                # EPSS Hubs SOH Heatmap (WITH FIX)
                                # ============================================
                                st.markdown("---")
                                st.markdown("<h5 style='font-size: 20px; font-weight: bold;'>🔥 EPSS Stock on Hand (SOH) Heatmap</h5>", unsafe_allow_html=True)

                                # Add filter option
                                heatmap_filter = st.radio(
                                    "Select View:",
                                    ["🏪 Hubs Only", "🏢 With Head Office"],
                                    horizontal=True,
                                    key="soh_heatmap_filter",
                                    index=1
                                )

                                branch_soh_cols = []
                                for col in df.columns:
                                    if 'Branch' in col:
                                        branch_soh_cols.append(col)
                                    elif col.startswith('Hub') and col not in ['Hubs', 'Hubs%']:
                                        branch_soh_cols.append(col)

                                branch_soh_cols = list(set(branch_soh_cols))
                                branch_soh_cols = [col for col in branch_soh_cols if col != 'Material Description']
                                branch_soh_cols = sorted(branch_soh_cols)

                                if branch_soh_cols:
                                    # Create heatmap data with branches
                                    heatmap_data = df[['Material Description'] + branch_soh_cols].copy()

                                    for col in branch_soh_cols:
                                        heatmap_data[col] = pd.to_numeric(heatmap_data[col], errors='coerce').fillna(0)

                                    # CRITICAL FIX: Remove duplicates and reindex
                                    heatmap_data_indexed = heatmap_data.set_index('Material Description')
                                    # Remove duplicate indices
                                    heatmap_data_indexed = heatmap_data_indexed[~heatmap_data_indexed.index.duplicated(keep='first')]

                                    # Create unique ordered list
                                    unique_master_order_soh = []
                                    for m in master_material_order:
                                        if m in heatmap_data_indexed.index and m not in unique_master_order_soh:
                                            unique_master_order_soh.append(m)

                                    heatmap_data_indexed = heatmap_data_indexed.reindex(unique_master_order_soh)
                                    heatmap_data_indexed = heatmap_data_indexed.fillna(0)
                                    heatmap_data_transposed = heatmap_data_indexed.T

                                    # Add Head Office
                                    if heatmap_filter == "🏢 With Head Office" and 'Head Office' in df.columns:
                                        head_office_data = df[['Material Description', 'Head Office']].copy()
                                        head_office_data['Head Office'] = pd.to_numeric(head_office_data['Head Office'], errors='coerce').fillna(0)
                                        head_office_data = head_office_data.set_index('Material Description')
                                        # Remove duplicates
                                        head_office_data = head_office_data[~head_office_data.index.duplicated(keep='first')]
                                        head_office_data = head_office_data.reindex(unique_master_order_soh)
                                        head_office_data = head_office_data.fillna(0)
                                        head_office_data = head_office_data.T
                                        head_office_data.index = ['🏢 Head Office']

                                        # Ensure columns match
                                        common_materials = heatmap_data_transposed.columns.intersection(head_office_data.columns)
                                        heatmap_data_transposed = heatmap_data_transposed[common_materials]
                                        head_office_aligned = head_office_data[common_materials]

                                        combined_heatmap = pd.concat([heatmap_data_transposed, head_office_aligned])
                                    else:
                                        combined_heatmap = heatmap_data_transposed

                                    total_materials_soh = len(combined_heatmap.columns)
                                    materials_per_page_soh = 10

                                    if 'soh_heatmap_page' not in st.session_state:
                                        st.session_state.soh_heatmap_page = 1

                                    if total_materials_soh > materials_per_page_soh:
                                        total_pages_soh = (total_materials_soh + materials_per_page_soh - 1) // materials_per_page_soh

                                        col_prev, col_page, col_next = st.columns([1, 3, 1])
                                        with col_prev:
                                            if st.button("◀ Previous", key="soh_heatmap_prev"):
                                                if st.session_state.soh_heatmap_page > 1:
                                                    st.session_state.soh_heatmap_page -= 1
                                                    st.rerun()
                                        with col_page:
                                            st.markdown(f"<p style='text-align: center;'>Page {st.session_state.soh_heatmap_page} of {total_pages_soh}</p>", unsafe_allow_html=True)
                                        with col_next:
                                            if st.button("Next ▶", key="soh_heatmap_next"):
                                                if st.session_state.soh_heatmap_page < total_pages_soh:
                                                    st.session_state.soh_heatmap_page += 1
                                                    st.rerun()

                                        start_idx_soh = (st.session_state.soh_heatmap_page - 1) * materials_per_page_soh
                                        end_idx_soh = min(start_idx_soh + materials_per_page_soh, total_materials_soh)
                                        page_materials_soh = combined_heatmap.columns[start_idx_soh:end_idx_soh]
                                        heatmap_page_df_soh = combined_heatmap[page_materials_soh]
                                    else:
                                        heatmap_page_df_soh = combined_heatmap

                                    if not heatmap_page_df_soh.empty:
                                        # ============================================
                                        # VISUALIZATION FIXES (Layout & Readability)
                                        # ============================================

                                        # 1. Determine available screen width (responsive layout)
                                        max_plot_width = 1600  # Fallback max width
                                        if 'st' in globals():
                                            try:
                                                # Get browser width if possible, otherwise use a safe default for Streamlit
                                                max_plot_width = 1200 
                                            except:
                                                pass

                                        # 2. Calculate dynamic width based on number of materials (columns)
                                        # Base width per material: 100px, minimum total width: 800px
                                        num_cols = len(heatmap_page_df_soh.columns)
                                        base_col_width = 100
                                        dynamic_width = max(800, num_cols * base_col_width)
                                        # Cap at max_plot_width to prevent horizontal scrolling if there are too many
                                        final_width = min(dynamic_width, max_plot_width)

                                        # 3. Calculate dynamic height based on rows (branches)
                                        # Base height per row: 45px, minimum total height: 400px
                                        num_rows = len(heatmap_page_df_soh.index)
                                        base_row_height = 45
                                        dynamic_height = max(400, num_rows * base_row_height + 80) # +80 for title

                                        # 4. Create text array: Suppress zeros to prevent clutter
                                        # If value is 0, show empty string, else format with commas
                                        text_values = []
                                        for row_vals in heatmap_page_df_soh.values:
                                            new_row = []
                                            for val in row_vals:
                                                if val == 0:
                                                    new_row.append('')
                                                else:
                                                    new_row.append(f"{int(val):,}")
                                            text_values.append(new_row)

                                        # 5. Create the Heatmap
                                        fig_soh = go.Figure(data=go.Heatmap(
                                            z=heatmap_page_df_soh.values,
                                            y=heatmap_page_df_soh.index,
                                            x=heatmap_page_df_soh.columns,
                                            colorscale='Reds',
                                            zmin=0,
                                            zmax=heatmap_page_df_soh.max().max() if not heatmap_page_df_soh.empty else 1,
                                            text=text_values, # Using cleaned array
                                            texttemplate='%{text}',
                                            textfont={"size": 12}, # Slightly larger font for readability
                                            colorbar=dict(
                                                title="Stock on Hand (Units)", 
                                                title_side="right", 
                                                ticks="outside",
                                                thickness=15, # Proportional thickness
                                                len=0.75 # Proportional length
                                            ),
                                            hovertemplate='<b>Material:</b> %{x}<br><b>Location:</b> %{y}<br><b>SOH:</b> %{z:,.0f} units<br><extra></extra>'
                                        ))

                                        # 6. Layout Best Practices
                                        fig_soh.update_layout(
                                            title="EPSS Stock on Hand Distribution",
                                            xaxis={
                                                'title': 'Material Description', 
                                                'tickangle': -45, # Rotate labels for readability
                                                'tickfont': {'size': 11}, 
                                                'automargin': True,
                                                'side': 'bottom'
                                            },
                                            yaxis={
                                                'title': 'Location', 
                                                'tickfont': {'size': 12},
                                                'automargin': True # Ensures branch names don't get cut off
                                            },
                                            # Apply dynamic width and height
                                            width=final_width, 
                                            height=dynamic_height,
                                            # Increase margins significantly so labels don't overlap edges
                                            margin=dict(
                                                l=180,  # Larger left margin for branch names
                                                r=50, 
                                                t=80,  # Margin for title
                                                b=250  # Large bottom margin for rotated X-axis labels
                                            ),
                                            # Responsive best practices for Streamlit
                                            autosize=True,
                                            paper_bgcolor='rgba(0,0,0,0)',
                                            plot_bgcolor='rgba(0,0,0,0)'
                                        )

                                        st.plotly_chart(fig_soh, use_container_width=True)
                                    else:
                                        st.info("No data available for heatmap")
                                else:
                                    st.info("No branch/hub stock data available for heatmap")

                                st.markdown("---")
                                st.markdown("<h5 style='font-size: 20px; font-weight: bold;'>Full Branch MOS Data with CV</h5>", unsafe_allow_html=True)
                                display_division_df = division_df.copy()
                                display_division_df['CV (%)'] = display_division_df['CV (%)'].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "")
                                st.dataframe(display_division_df, use_container_width=True, height=400, hide_index=True)
                                st.download_button(label="Download Hubs MOS with CV", data=division_df.pipe(_xl), file_name="hubs_mos_distribution_with_cv.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

                                st.markdown("---")
                                st.markdown("<h5 style='font-size: 20px; font-weight: bold;'>EPSS Hubs SOH</h5>", unsafe_allow_html=True)
                                st.dataframe(gh, use_container_width=True, height=400, hide_index=True)

                                st.markdown("---")
                                st.markdown("<h5 style='font-size: 20px; font-weight: bold;'>EPSS Hubs AMC Data (from Google Sheets)</h5>", unsafe_allow_html=True)
                                st.dataframe(branch_amc_data, use_container_width=True, height=400, hide_index=True)
                            else:
                                st.warning("Not enough branch columns for heatmap")
                        else:
                            st.warning("No matching Material Description found")
                    elif branch_amc_data is None or branch_amc_data.empty:
                        st.info("Branch AMC data is currently unavailable.")
                        if not df.empty and 'Material Description' in df.columns:
                            branch_cols = [col for col in df.columns if 'Branch' in col or col == 'Material Description']
                            gh = df[branch_cols].copy() if branch_cols else df[['Material Description']].copy()
                            st.dataframe(gh, use_container_width=True, height=400, hide_index=True)
                    else:
                        st.error("'Material Description' column not found")
                else:
                    st.warning("Main dataframe is empty.")
            else:
                st.warning("Main dataframe is empty.")
        except Exception as e:
            st.error(f"Error processing files: {e}")

   # ---------------------------------------------------
# TAB 6 - Procurement Lead Time (FULLY REVISED)
# Linked to sidebar via the globally-filtered `df`
# ---------------------------------------------------

# ===================================================
# HELPER: Build Smart Table
# ===================================================
def build_smart_procurement_table(filtered_df, material_options=None):
    if filtered_df is None or filtered_df.empty:
        return pd.DataFrame()

    work = filtered_df.copy().reset_index(drop=True)

    if 'material_description' in work.columns and 'po_number' in work.columns:
        work['_mat_key'] = work['material_description'].apply(_normalize_material)
        work['_po_key'] = work['po_number'].apply(_normalize_po)
        work = work.drop_duplicates(subset=['_mat_key', '_po_key'], keep='first')
        work = work.drop(columns=['_mat_key', '_po_key'], errors='ignore')

    work['PO Qty Variance'] = (
        pd.to_numeric(work.get('po_quantity', 0), errors='coerce').fillna(0)
        - pd.to_numeric(work.get('Delivered Qty', 0), errors='coerce').fillna(0)
    )

    def _status(row):
        po_qty = row.get('po_quantity', 0) or 0
        del_qty = row.get('Delivered Qty', 0)
        posting = row.get('posting_date')
        if pd.isna(del_qty):
            del_qty = 0
        if pd.notna(posting) and po_qty > 0 and del_qty >= po_qty:
            return "✅ Fully Delivered"
        elif del_qty > 0 and del_qty < po_qty:
            return "🟡 Partially Delivered"
        elif pd.notna(posting) and del_qty == 0:
            return "⚠️ Posted - No Delivery"
        elif pd.isna(posting):
            return "⏳ In Progress"
        return ""

    work['Status'] = work.apply(_status, axis=1)

    ordered_cols = [
        'material_description', 'year_of_request', 'funding_source',
        'request_quantity', 'epss_date', 'dmd_received_date', 'dmd_submission_date',
        'po_number', 'po_quantity', 'Delivered Qty', 'posting_date',
        'DMD Processing Days', 'Procurement Lead Time', 'Procurement Process Time',
        'PO Qty Variance', 'Status',
    ]
    ordered_cols = [c for c in ordered_cols if c in work.columns]
    smart = work[ordered_cols].copy()

    if 'year_of_request' in smart.columns:
        smart = smart.sort_values(
            by=['year_of_request', 'material_description'],
            ascending=[False, True], na_position='last'
        ).reset_index(drop=True)
    else:
        smart = smart.sort_values(
            by=['material_description'], ascending=[True]
        ).reset_index(drop=True)

    smart.index = range(len(smart))
    smart.index.name = None
    return smart


# ===================================================
# HELPER: Export XLSX
# ===================================================
def export_smart_table_to_xlsx(smart_df, program_label="All Programs"):
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    if smart_df.empty:
        return None

    output = BytesIO()

    rename_map = {
        'material_description': 'Material Description',
        'year_of_request': 'Year',
        'funding_source': 'Source of Fund',
        'request_quantity': 'Request Qty',
        'epss_date': 'EPSS Date',
        'dmd_received_date': 'DMD Received Date',
        'dmd_submission_date': 'DMD Submission Date',
        'po_number': 'PO Number',
        'po_quantity': 'PO Qty',
        'Delivered Qty': 'Delivered Qty',
        'posting_date': 'Posting Date',
        'DMD Processing Days': 'DMD Proc. (Days)',
        'Procurement Lead Time': 'Proc. Lead (Days)',
        'Procurement Process Time': 'Proc. Process (Days)',
        'PO Qty Variance': 'PO Qty Variance',
        'Status': 'Status',
    }

    export_order = [
        'material_description', 'year_of_request', 'funding_source',
        'request_quantity', 'epss_date', 'dmd_received_date', 'dmd_submission_date',
        'po_number', 'po_quantity', 'Delivered Qty', 'posting_date',
        'DMD Processing Days', 'Procurement Lead Time', 'Procurement Process Time',
        'PO Qty Variance', 'Status',
    ]
    export_order = [c for c in export_order if c in smart_df.columns]
    export_df = smart_df[export_order].copy().rename(columns=rename_map)

    for col in ['EPSS Date', 'DMD Received Date', 'DMD Submission Date', 'Posting Date']:
        if col in export_df.columns:
            export_df[col] = pd.to_datetime(export_df[col], errors='coerce').dt.strftime('%Y-%m-%d')

    qty_cols = ['Request Qty', 'PO Qty', 'Delivered Qty', 'PO Qty Variance']
    for col in qty_cols:
        if col in export_df.columns:
            export_df[col] = pd.to_numeric(export_df[col], errors='coerce')

    for col in ['DMD Proc. (Days)', 'Proc. Lead (Days)', 'Proc. Process (Days)']:
        if col in export_df.columns:
            export_df[col] = pd.to_numeric(export_df[col], errors='coerce').round(0)

    export_df = export_df.where(pd.notna(export_df), None)

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        sheet_name = "Procurement Lead Time"
        export_df.to_excel(writer, sheet_name=sheet_name, index=False)
        ws = writer.sheets[sheet_name]

        title_font = Font(name="Times New Roman", size=14, bold=True, color="FFFFFF")
        header_font = Font(name="Times New Roman", size=11, bold=True, color="FFFFFF")
        data_font = Font(name="Times New Roman", size=11, color="1F2A38")

        title_fill = PatternFill("solid", fgColor="1A5276")
        header_fill = PatternFill("solid", fgColor="E67E22")
        band_fill = PatternFill("solid", fgColor="FDF2E3")
        shortfall_fill = PatternFill("solid", fgColor="FADBD8")
        over_fill = PatternFill("solid", fgColor="D5F5E3")

        thin = Side(border_style="thin", color="B8C6D6")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)

        n_cols = len(export_df.columns)
        last_col = get_column_letter(n_cols)

        ws.insert_rows(1)
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n_cols)
        tcell = ws.cell(row=1, column=1,
                        value=f"{program_label} — Health Program Procurement Lead Time")
        tcell.font = title_font
        tcell.fill = title_fill
        tcell.alignment = Alignment(horizontal="left", vertical="center")
        ws.row_dimensions[1].height = 28

        for c_idx in range(1, n_cols + 1):
            cell = ws.cell(row=2, column=c_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
            cell.border = border
        ws.row_dimensions[2].height = 32

        variance_col_idx = None
        qty_col_indexes = []
        for idx, col_name in enumerate(export_df.columns, start=1):
            if col_name == 'PO Qty Variance':
                variance_col_idx = idx
            if col_name in qty_cols:
                qty_col_indexes.append(idx)

        for r_idx in range(3, 3 + len(export_df)):
            band = (r_idx % 2 == 1)
            for c_idx in range(1, n_cols + 1):
                cell = ws.cell(row=r_idx, column=c_idx)
                cell.font = data_font
                cell.border = border
                cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
                if band:
                    cell.fill = band_fill
                if c_idx in qty_col_indexes:
                    cell.number_format = '#,##0'

            if variance_col_idx is not None:
                vcell = ws.cell(row=r_idx, column=variance_col_idx)
                try:
                    val = vcell.value
                    if val is not None:
                        v = float(val)
                        if v > 0:
                            vcell.fill = shortfall_fill
                        elif v < 0:
                            vcell.fill = over_fill
                except Exception:
                    pass

        for c_idx, col_name in enumerate(export_df.columns, start=1):
            letter = get_column_letter(c_idx)
            header_len = len(str(col_name))
            max_len = header_len
            for r_idx in range(3, 3 + len(export_df)):
                v = ws.cell(row=r_idx, column=c_idx).value
                if v is not None:
                    formatted = f"{v:,}" if c_idx in qty_col_indexes and isinstance(v, (int, float)) else str(v)
                    max_len = max(max_len, len(formatted))
            ws.column_dimensions[letter].width = min(max(max_len + 2, 12), 55)

        ws.freeze_panes = "A3"
        ws.auto_filter.ref = f"A2:{last_col}{2 + len(export_df)}"

    output.seek(0)
    return output


# ===================================================
# HELPER: Quick Add form
# ===================================================
def _render_quick_add_form(material_options):
    if st.session_state['user']['role'] != 'admin':
        return

    st.markdown("### ➕ Quick Add New Procurement Record")
    with st.expander("➕ Add New Record", expanded=False):
        with st.form("quick_add_procurement_v6", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)

            with c1:
                f_mat = st.selectbox(
                    "Material Description *",
                    options=["-- Select Material --"] + material_options,
                    key="add_material_select_v6"
                )
                f_year = st.number_input("Year of Request", min_value=2000, max_value=2100,
                                         value=datetime.now().year, step=1, key="add_year_v6")
                f_funding = st.text_input("Source of Fund", placeholder="e.g., SDG, GF, Treasury",
                                          key="add_funding_text_v6")
            with c2:
                f_req_qty = st.number_input("Request Quantity", min_value=0.0, step=1.0,
                                            value=0.0, key="add_req_qty_v6")
                f_po = st.text_input("PO Number", placeholder="e.g., 4500012345", key="add_po_v6")
                f_po_qty = st.number_input("PO Quantity", min_value=0.0, step=1.0,
                                           value=0.0, key="add_po_qty_v6")
            with c3:
                st.markdown("**Dates** *(leave blank if not available)*")
                f_epss = st.date_input("EPSS Date", value=None, key="add_epss_date_v6")
                f_dmd_rec = st.date_input("DMD Received Date", value=None, key="add_dmd_rec_date_v6")
                f_dmd_sub = st.date_input("DMD Submission Date", value=None, key="add_dmd_sub_date_v6")
                f_posting = st.date_input("Posting Date", value=None, key="add_posting_date_v6")

            submitted = st.form_submit_button("💾 Save Record", use_container_width=True, type="primary")

            if submitted:
                if not f_mat or f_mat == "-- Select Material --":
                    st.error("⚠️ Please select a Material Description")
                elif not f_funding or f_funding.strip() == "":
                    st.error("⚠️ Please enter a Source of Fund")
                else:
                    record = {
                        'material_description': f_mat,
                        'year_of_request': int(f_year),
                        'funding_source': f_funding.strip(),
                        'request_quantity': float(f_req_qty) if f_req_qty else None,
                        'po_number': f_po.strip() if f_po else None,
                        'po_quantity': float(f_po_qty) if f_po_qty else None,
                        'epss_date': f_epss,
                        'dmd_received_date': f_dmd_rec,
                        'dmd_submission_date': f_dmd_sub,
                        'posting_date': f_posting,
                    }
                    if save_procurement_record(record):
                        _bust_proc_cache()
                        log_dashboard_update("Added procurement record", str(f_mat)[:200], 1)
                        st.success(f"✅ Saved record for {f_mat[:50]}")
                        st.rerun()


# ===================================================
# HELPER: per-column width
# ===================================================
def _compute_html_column_widths(display_df, header_labels, cap=280, floor=100):
    widths = []
    for col in display_df.columns:
        header = header_labels.get(col, col)
        max_chars = len(str(header))
        series = display_df[col].astype(str)
        if not series.empty:
            max_len = series.str.len().max()
            if pd.notna(max_len):
                max_chars = max(max_chars, int(max_len))
        px = int(max_chars * 8.5) + 24
        px = max(floor, min(px, cap))
        widths.append(px)
    return widths



def _sync_kpi_avg_proc_lead(value):
    """Remember the tab's Avg Procurement Lead. The KPI card computes the same number itself,
    so this must never force a rerun (a mismatch used to be able to loop)."""
    st.session_state['kpi_avg_proc_lead'] = value


# ===================================================
# FRAGMENT: Tab renderer
# ===================================================
@st.fragment
def render_procurement_lead_time_tab():
    st.markdown(
        "<h3 style='font-size: 28px; font-weight: bold; font-family: Times New Roman;'>"
        "⏱️ Procurement Lead Time Tracking</h3>",
        unsafe_allow_html=True
    )

    # 0) Sidebar-filtered df
    base_df = None
    if 'df' in globals() and isinstance(df, pd.DataFrame):
        base_df = df
    elif 'filtered_df' in globals() and isinstance(filtered_df, pd.DataFrame):
        base_df = filtered_df
    elif 'df_filtered' in globals() and isinstance(df_filtered, pd.DataFrame):
        base_df = df_filtered

    for _key in ('filtered_df', 'df_filtered', 'sidebar_filtered_df', 'df'):
        try:
            _candidate = st.session_state.get(_key)
            if isinstance(_candidate, pd.DataFrame) and not _candidate.empty:
                base_df = _candidate
                break
        except Exception:
            continue

    # 1) Load
    proc_df = load_procurement_lead_time(st.session_state.get('proc_cache_bust', 0))

    if proc_df.empty:
        _sync_kpi_avg_proc_lead(None)
        st.info("📭 No procurement lead time records yet. Use '➕ Quick Add New Procurement Record' below.")
        fallback_materials = []
        if base_df is not None and not base_df.empty and 'Material Description' in base_df.columns:
            fallback_materials = sorted(
                base_df['Material Description'].dropna().astype(str).unique().tolist()
            )
        _render_quick_add_form(fallback_materials)
        return

    # 1a) Enrich — only against df_new_deliveries
    deliveries_source = None
    if 'df_new_deliveries' in globals() and not df_new_deliveries.empty:
        deliveries_source = df_new_deliveries

    if deliveries_source is not None and not deliveries_source.empty:
        proc_df = enrich_posting_date_from_deliveries(proc_df, deliveries_source)
        proc_df = enrich_delivered_qty_from_deliveries(proc_df, deliveries_source)

    # 1b) Link to sidebar
    if base_df is not None and not base_df.empty and 'Material Description' in base_df.columns:
        proc_df = _link_procurement_to_sidebar(proc_df, base_df)

    if not proc_df.empty and 'material_description' in proc_df.columns:
        material_options = sorted(
            proc_df['material_description'].dropna().astype(str).unique().tolist()
        )
    elif base_df is not None and not base_df.empty and 'Material Description' in base_df.columns:
        material_options = sorted(
            base_df['Material Description'].dropna().astype(str).unique().tolist()
        )
    else:
        material_options = []

    if proc_df.empty:
        _sync_kpi_avg_proc_lead(None)
        st.info("📭 No procurement lead time records match the current sidebar filters.")
        _render_quick_add_form(material_options)
        return

    proc_df = calculate_procurement_lead_times(proc_df)
    proc_df = calculate_po_qty_variance(proc_df)

    # ============================================
    # 3) FILTERS
    # ============================================
    st.markdown("### 🔍 Filters")
    fc1, fc2, fc3, fc4 = st.columns([1, 1, 1, 2])

    with fc1:
        year_opts = ["All"] + sorted(
            [str(int(y)) for y in proc_df['year_of_request'].dropna().unique()], reverse=True
        )
        year_filter = st.selectbox("Year of Request", year_opts, key="proc_lead_year_v6")
    with fc2:
        funding_opts = ["All"] + sorted([str(f) for f in proc_df['funding_source'].dropna().unique()])
        funding_filter = st.selectbox("Source of Fund", funding_opts, key="proc_lead_funding_v6")
    with fc3:
        mat_filter_opts = ["All"] + sorted(proc_df['material_description'].dropna().unique().tolist())
        mat_filter = st.selectbox("Material", mat_filter_opts, key="proc_lead_material_v6")
    with fc4:
        po_search = st.text_input("🔍 Search PO Number", placeholder="e.g., '4500006952'", key="proc_lead_search_v6")

    filtered = proc_df.copy()
    if year_filter != "All":
        filtered = filtered[filtered['year_of_request'].astype(str) == year_filter]
    if funding_filter != "All":
        filtered = filtered[filtered['funding_source'].astype(str) == funding_filter]
    if mat_filter != "All":
        filtered = filtered[filtered['material_description'] == mat_filter]
    if po_search:
        filtered = filtered[filtered['po_number'].astype(str).str.contains(po_search, case=False, na=False)]

    if 'year_of_request' in filtered.columns:
        filtered = filtered.sort_values(
            by=['year_of_request'], ascending=False, na_position='last'
        ).reset_index(drop=True)

    st.markdown("---")

    # ============================================
    # 4) SUMMARY METRICS
    # ============================================
    st.markdown("### 📊 Summary Metrics")
    avg_dmd_proc = filtered['DMD Processing Days'].dropna().mean() if not filtered.empty else 0
    avg_proc_lead = filtered['Procurement Lead Time'].dropna().mean() if not filtered.empty else 0
    avg_proc_process = filtered['Procurement Process Time'].dropna().mean() if not filtered.empty else 0
    _sync_kpi_avg_proc_lead(int(round(avg_proc_lead)) if pd.notna(avg_proc_lead) else 0)

    k1, k2, k3 = st.columns(3)
    with k1:
        st.markdown(f"""
        <div style='background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); border-radius: 12px; padding: 15px; text-align: center; color: white;'>
            <p style='margin: 0; font-size: 13px; opacity: 0.9;'>⏱️ Avg DMD Processing</p>
            <p style='margin: 5px 0 0 0; font-size: 28px; font-weight: bold;'>{round(avg_dmd_proc) if pd.notna(avg_dmd_proc) else 0} days</p>
        </div>
        """, unsafe_allow_html=True)
    with k2:
        st.markdown(f"""
        <div style='background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); border-radius: 12px; padding: 15px; text-align: center; color: white;'>
            <p style='margin: 0; font-size: 13px; opacity: 0.9;'>📦 Avg Procurement Lead</p>
            <p style='margin: 5px 0 0 0; font-size: 28px; font-weight: bold;'>{round(avg_proc_lead) if pd.notna(avg_proc_lead) else 0} days</p>
        </div>
        """, unsafe_allow_html=True)
    with k3:
        st.markdown(f"""
        <div style='background: linear-gradient(135deg, #fa709a 0%, #fee140 100%); border-radius: 12px; padding: 15px; text-align: center; color: white;'>
            <p style='margin: 0; font-size: 13px; opacity: 0.9;'>📅 Avg. Days Outstanding</p>
            <p style='margin: 5px 0 0 0; font-size: 28px; font-weight: bold;'>{round(avg_proc_process) if pd.notna(avg_proc_process) else 0} days</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # ============================================
    # 5) SMART TABLE
    # ============================================
    st.markdown("### 🧠 Health Program Procurement Lead Time — Smart Summary")
    smart_df = build_smart_procurement_table(filtered, material_options)

    if not smart_df.empty:
        smart_display = smart_df.copy().reset_index(drop=True)

        for col in ['epss_date', 'dmd_received_date', 'dmd_submission_date', 'posting_date']:
            if col in smart_display.columns:
                smart_display[col] = pd.to_datetime(
                    smart_display[col], errors='coerce'
                ).dt.strftime('%Y-%m-%d').fillna('')

        for col in ['DMD Processing Days', 'Procurement Lead Time', 'Procurement Process Time']:
            if col in smart_display.columns:
                smart_display[col] = smart_display[col].apply(
                    lambda x: int(round(x)) if pd.notna(x) else ''
                )

        for col in ['request_quantity', 'po_quantity', 'Delivered Qty', 'PO Qty Variance']:
            if col in smart_display.columns:
                smart_display[col] = smart_display[col].apply(
                    lambda x: f"{int(x):,}" if pd.notna(x) and x != '' else ''
                )

        if 'year_of_request' in smart_display.columns:
            smart_display['year_of_request'] = smart_display['year_of_request'].apply(
                lambda x: int(x) if pd.notna(x) else ''
            )

        smart_display = smart_display.where(pd.notna(smart_display), '')
        for col in smart_display.columns:
            smart_display[col] = smart_display[col].apply(
                lambda x: '' if x is None else x
            )

        display_rename = {
            'material_description': 'Material Description',
            'year_of_request': 'Year',
            'funding_source': 'Source of Fund',
            'request_quantity': 'Request Qty',
            'epss_date': 'EPSS Date',
            'dmd_received_date': 'DMD Received Date',
            'dmd_submission_date': 'DMD Submission Date',
            'po_number': 'PO Number',
            'po_quantity': 'PO Qty',
            'Delivered Qty': 'Delivered Qty',
            'posting_date': 'Posting Date',
            'DMD Processing Days': 'DMD Proc. (Days)',
            'Procurement Lead Time': 'Proc. Lead (Days)',
            'Procurement Process Time': 'Proc. Process (Days)',
            'PO Qty Variance': 'PO Qty Variance',
            'Status': 'Status',
        }
        smart_display = smart_display.rename(columns=display_rename).reset_index(drop=True)
        smart_display.index.name = None

        table_styles = [
            {'selector': 'table',
             'props': [('border-collapse', 'collapse'),
                       ('font-size', '12px'),
                       ('font-family', 'Arial, sans-serif'),
                       ('table-layout', 'fixed'),
                       ('width', '100%')]},
            {'selector': 'thead th',
             'props': [('background-color', '#E67E22'),
                       ('color', 'white'),
                       ('font-weight', 'bold'),
                       ('font-size', '13px'),
                       ('text-align', 'left'),
                       ('padding', '10px 12px'),
                       ('border-bottom', '2px solid #B85C00'),
                       ('border-right', '1px solid #B85C00'),
                       ('white-space', 'nowrap')]},
            {'selector': 'tbody tr:nth-child(odd)',
             'props': [('background-color', '#FFFFFF')]},
            {'selector': 'tbody tr:nth-child(even)',
             'props': [('background-color', '#FDF2E3')]},
            {'selector': 'tbody tr:hover',
             'props': [('background-color', '#FFE8CC')]},
            {'selector': 'tbody td',
             'props': [('padding', '8px 12px'),
                       ('border-bottom', '1px solid #F0D9BC'),
                       ('border-right', '1px solid #F0D9BC'),
                       ('white-space', 'nowrap'),
                       ('color', '#1F2A38'),
                       ('font-size', '12px')]},
        ]

        styler = smart_display.style.set_table_styles(table_styles)

        qty_display_cols = ['Request Qty', 'PO Qty', 'Delivered Qty', 'PO Qty Variance']
        qty_present = [c for c in qty_display_cols if c in smart_display.columns]
        if qty_present:
            styler = styler.set_properties(subset=qty_present, **{'text-align': 'right'})

        if 'PO Qty Variance' in smart_display.columns:
            def _variance_color(val):
                try:
                    s = str(val).strip()
                    if s == '':
                        return ''
                    v = float(s.replace(',', ''))
                    if v > 0:
                        return 'background-color: #FADBD8; color: #922B21; font-weight: bold;'
                    elif v < 0:
                        return 'background-color: #D5F5E3; color: #1E8449; font-weight: bold;'
                    else:
                        return 'background-color: #EAECEE; color: #566573;'
                except Exception:
                    return ''
            styler = styler.map(_variance_color, subset=['PO Qty Variance'])

        if 'Status' in smart_display.columns:
            def _status_color(val):
                v = str(val)
                if '✅' in v:
                    return 'color: #1E8449; font-weight: bold;'
                if '🟡' in v:
                    return 'color: #B9770E; font-weight: bold;'
                if '⚠️' in v:
                    return 'color: #922B21; font-weight: bold;'
                if '⏳' in v:
                    return 'color: #1A5276; font-weight: bold;'
                return ''
            styler = styler.map(_status_color, subset=['Status'])

        col_widths = _compute_html_column_widths(
            smart_display, {c: c for c in smart_display.columns}, cap=280, floor=100
        )
        total_min_width = sum(col_widths)

        colgroup_html = "<colgroup>" + "".join(
            f'<col style="width:{w}px;">' for w in col_widths
        ) + "</colgroup>"

        table_html = styler.to_html(index=False)

        import re as _re
        table_html = _re.sub(r'(<thead>\s*<tr>\s*)<th[^>]*>\s*</th>', r'\1', table_html, count=1)
        table_html = _re.sub(r'(<tr[^>]*>)\s*<th[^>]*>.*?</th>', r'\1', table_html)
        table_html = _re.sub(r'(<tr[^>]*>)\s*<td[^>]*>\s*</td>', r'\1', table_html)
        table_html = _re.sub(
            r'(<table[^>]*>)',
            lambda m: m.group(1) + colgroup_html,
            table_html,
            count=1
        )

        scrollable_html = (
            '<div style="width:100%;overflow-x:auto;overflow-y:visible;'
            'border:1px solid #E1E8F0;border-radius:10px;'
            'box-shadow:0 4px 12px rgba(0,0,0,0.06);'
            'padding-bottom:6px;-webkit-overflow-scrolling:touch;">'
            f'<div style="min-width:{total_min_width}px;padding:2px;">'
            f'{table_html}'
            '</div>'
            '</div>'
            '<style>'
            'div[data-testid="stMarkdownContainer"] table thead th:empty {'
            'display:none !important;padding:0 !important;border:none !important;'
            'width:0 !important;max-width:0 !important;min-width:0 !important;}'
            'div[data-testid="stMarkdownContainer"] table tbody td:first-child:empty {'
            'display:none !important;padding:0 !important;border:none !important;'
            'width:0 !important;max-width:0 !important;min-width:0 !important;}'
            'div[data-testid="stMarkdownContainer"] table thead th {'
            'position:sticky !important;top:0;z-index:2;}'
            'div[data-testid="stMarkdownContainer"] > div::-webkit-scrollbar {height:10px;}'
            'div[data-testid="stMarkdownContainer"] > div::-webkit-scrollbar-thumb {'
            'background:#B8C6D6;border-radius:5px;}'
            'div[data-testid="stMarkdownContainer"] > div::-webkit-scrollbar-track {'
            'background:#F0F4F9;border-radius:5px;}'
            '</style>'
        )
        st.markdown(scrollable_html, unsafe_allow_html=True)

        program_label = program_display if 'program_display' in globals() else "All Programs"
        xlsx_bytes = export_smart_table_to_xlsx(smart_df, program_label)
        if xlsx_bytes is not None:
            st.download_button(
                label="📥 Download Health Program Procurement Lead Time (XLSX)",
                data=xlsx_bytes,
                file_name=f"Health_Program_Procurement_Lead_Time_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                type="primary",
                key="download_proc_lead_xlsx_v6",
            )
    else:
        st.info("No records to summarize for the current filters.")

    st.markdown("---")

    # ============================================
    # 6) LEAD TIME ANALYSIS
    # ============================================
    st.markdown("### 📈 Lead Time Analysis")
    viz_df = filtered.dropna(subset=['DMD Processing Days']).copy()
    if not viz_df.empty:
        vc1, vc2 = st.columns(2)
        with vc1:
            trend_source = filtered.copy()
            trend_source['Effective_Days'] = trend_source['Procurement Lead Time'].fillna(
                trend_source['Procurement Process Time']
            )
            trend_source = trend_source.dropna(subset=['dmd_submission_date', 'Effective_Days'])
            if not trend_source.empty:
                trend_source['Month'] = trend_source['dmd_submission_date'].dt.strftime('%b-%Y')
                monthly = trend_source.groupby('Month').agg({
                    'Effective_Days': 'mean',
                    'DMD Processing Days': 'mean'
                }).reset_index()
                try:
                    monthly['sort_key'] = pd.to_datetime(monthly['Month'], format='%b-%Y')
                    monthly = monthly.sort_values('sort_key').drop(columns=['sort_key'])
                except Exception:
                    pass

                fig_trend = go.Figure()
                fig_trend.add_trace(go.Scatter(
                    x=monthly['Month'], y=monthly['Effective_Days'].round(0),
                    mode='lines+markers', name='Procurement (Lead or Process)',
                    line=dict(color='#f5576c', width=3), marker=dict(size=8)
                ))
                fig_trend.add_trace(go.Scatter(
                    x=monthly['Month'], y=monthly['DMD Processing Days'].round(0),
                    mode='lines+markers', name='DMD Processing Days',
                    line=dict(color='#11998e', width=3), marker=dict(size=8)
                ))
                fig_trend.update_layout(
                    title='Average Lead Time Trend by Month',
                    xaxis_title='Month', yaxis_title='Days',
                    height=400, xaxis_tickangle=-45
                )
                st.plotly_chart(fig_trend, use_container_width=True)
        with vc2:
            dist_df = filtered.dropna(subset=['Procurement Lead Time'])
            if not dist_df.empty:
                fig_hist = px.histogram(
                    dist_df, x='Procurement Lead Time', nbins=20,
                    title='Distribution of Procurement Lead Time (Posted only)',
                    color_discrete_sequence=['#667eea']
                )
                fig_hist.update_layout(
                    height=400, xaxis_title='Days', yaxis_title='Count',
                    xaxis=dict(tickformat='d')
                )
                st.plotly_chart(fig_hist, use_container_width=True)
    else:
        st.info("Not enough data to generate visualizations.")

    st.markdown("---")

    # ============================================
    # 7) TOP 10
    # ============================================
    st.markdown("#### 🏆 Top 10 Materials by Avg Procurement Lead Time")
    top_src = filtered.dropna(subset=['Procurement Lead Time'])
    top_src = top_src[
        top_src['material_description'].notna() &
        (top_src['material_description'].astype(str).str.strip() != "")
    ]
    if not top_src.empty:
        top_mat = top_src.groupby('material_description').agg({
            'Procurement Lead Time': 'mean',
            'DMD Processing Days': 'mean',
            'po_number': 'count'
        }).round(0).sort_values('Procurement Lead Time', ascending=False).head(10).reset_index()
        top_mat = top_mat.rename(columns={'po_number': 'PO Count'})

        def _mat_label(row):
            mat = str(row['material_description'])
            return mat[:55] + '…' if len(mat) > 55 else mat

        top_mat['label'] = top_mat.apply(_mat_label, axis=1)

        fig_top = go.Figure()
        fig_top.add_trace(go.Bar(
            y=top_mat['label'],
            x=top_mat['Procurement Lead Time'],
            name='Procurement Lead Time',
            orientation='h',
            marker_color='#f5576c',
            text=top_mat['Procurement Lead Time'].astype(int).astype(str) + 'd',
            textposition='outside',
            customdata=top_mat[['DMD Processing Days', 'PO Count']].values,
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Procurement Lead Time: %{x:.0f} days<br>"
                "DMD Processing: %{customdata[0]:.0f} days<br>"
                "PO Count: %{customdata[1]}"
                "<extra></extra>"
            )
        ))
        fig_top.update_layout(
            title="Top 10 Materials by Average Procurement Lead Time (Posted only)",
            height=max(400, 35 * len(top_mat) + 80),
            xaxis_title='Average Days',
            yaxis=dict(autorange='reversed'),
            margin=dict(l=320, r=60)
        )
        st.plotly_chart(fig_top, use_container_width=True)
    else:
        st.info("No materials with procurement lead time data to display.")

    st.markdown("---")

    # ============================================
    # 8) EDITABLE RECORDS
    # ============================================
    st.markdown("### 📋 Procurement Lead Time Records")
    st.caption("Edit any cell, add a row (+) or delete rows — every change is saved automatically and the tables above update right away.")

    display_cols = [
        'material_description', 'year_of_request', 'funding_source',
        'request_quantity', 'po_number', 'po_quantity',
        'Delivered Qty', 'PO Qty Variance',
        'epss_date', 'dmd_received_date', 'dmd_submission_date', 'posting_date',
        'DMD Processing Days', 'Procurement Lead Time', 'Procurement Process Time'
    ]
    available_cols = [c for c in display_cols if c in filtered.columns]
    table_df = filtered[available_cols].copy()
    row_ids = filtered['id'].reset_index(drop=True).tolist() if 'id' in filtered.columns else []

    for col in ['epss_date', 'dmd_received_date', 'dmd_submission_date', 'posting_date']:
        if col in table_df.columns:
            table_df[col] = table_df[col].dt.strftime('%Y-%m-%d')
    for col in ['DMD Processing Days', 'Procurement Lead Time', 'Procurement Process Time']:
        if col in table_df.columns:
            table_df[col] = table_df[col].apply(lambda x: int(round(x)) if pd.notna(x) else "")
    for col in ['request_quantity', 'po_quantity', 'Delivered Qty', 'PO Qty Variance']:
        if col in table_df.columns:
            table_df[col] = table_df[col].apply(
                lambda x: f"{int(x):,}" if pd.notna(x) and x != "" else ""
            )

    table_df = table_df.where(pd.notna(table_df), "")
    for col in table_df.columns:
        table_df[col] = table_df[col].apply(
            lambda x: "" if x is None or (isinstance(x, float) and pd.isna(x)) else x
        )
    table_df = table_df.reset_index(drop=True)

    st.session_state['_proc_row_ids'] = row_ids
    _ed_key = f"proc_lead_editor_v6_{st.session_state.get('proc_editor_ver', 0)}"
    _flash = st.session_state.pop('_proc_flash', None)
    _flash_err = st.session_state.pop('_proc_flash_err', None)
    if _flash:
        st.success(_flash)
    if _flash_err:
        st.error(_flash_err)

    if st.session_state['user']['role'] == 'admin':
        edited = st.data_editor(
            table_df,
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            key=_ed_key,
            on_change=_proc_autosave,
            args=(_ed_key,),
            column_config={
                'material_description': st.column_config.SelectboxColumn(
                    'Material Description', width='large', options=material_options, required=True
                ),
                'year_of_request': st.column_config.NumberColumn('Year', width='small'),
                'funding_source': st.column_config.TextColumn('Source of Fund', width='small'),
                'request_quantity': st.column_config.TextColumn('Req Qty', width='small'),
                'po_number': st.column_config.TextColumn('PO Number', width='medium'),
                'po_quantity': st.column_config.TextColumn('PO Qty', width='small'),
                'Delivered Qty': st.column_config.TextColumn('Delivered Qty', width='small', disabled=True),
                'PO Qty Variance': st.column_config.TextColumn('PO Qty Variance', width='small', disabled=True),
                'epss_date': st.column_config.TextColumn('EPSS Date', width='small'),
                'dmd_received_date': st.column_config.TextColumn('DMD Rcvd', width='small'),
                'dmd_submission_date': st.column_config.TextColumn('DMD Sub', width='small'),
                'posting_date': st.column_config.TextColumn('Posting Date (Auto)', width='small'),
                'DMD Processing Days': st.column_config.NumberColumn('DMD Proc.', disabled=True, width='small', format='%d'),
                'Procurement Lead Time': st.column_config.NumberColumn('Proc. Lead', disabled=True, width='small', format='%d'),
                'Procurement Process Time': st.column_config.NumberColumn('Proc. Process', disabled=True, width='small', format='%d'),
            }
        )

        st.markdown("##### 🗑️ Delete Records")
        del_col1, del_col2 = st.columns([3, 1])
        with del_col1:
            delete_options = filtered.apply(
                lambda r: f"ID {int(r['id'])} | {str(r['material_description'])[:40]} | PO {r.get('po_number', 'N/A')}",
                axis=1
            ).tolist()
            delete_map = dict(zip(delete_options, filtered['id'].astype(int).tolist()))
            to_delete = st.selectbox("Select a record to delete", ["-- Select --"] + delete_options, key="del_record_select_v6")
        with del_col2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🗑️ Delete", use_container_width=True, type="secondary",
                         disabled=(to_delete == "-- Select --"), key="del_proc_v6"):
                if to_delete in delete_map:
                    if delete_procurement_record(delete_map[to_delete]):
                        _bust_proc_cache()
                        log_dashboard_update("Deleted procurement record", str(to_delete)[:200], 1)
                        st.success("✅ Record deleted")
                        st.rerun()
    else:
        st.dataframe(table_df, use_container_width=True, hide_index=True)

    st.markdown("---")
    _render_quick_add_form(material_options)


# ---- Render the tab content ----
with tab6:
    if _tab_open(tab6):
        render_procurement_lead_time_tab()

         # ---------------------------------------------------
    # TAB 7 - New Deliveries with Lead Time Tracking
    # ---------------------------------------------------
with tab7:
    if _tab_open(tab7):
        if not df_new_deliveries.empty and not show_all_programs and len(selected_programs_list) == 1 and selected_programs_list[0] in google_sheets:
            program_materials = google_sheets[selected_programs_list[0]]['Material Description'].dropna().tolist()
            df_new_deliveries = df_new_deliveries[df_new_deliveries['Material Description'].isin(program_materials)]

        st.markdown("<h3 style='font-size: 28px; font-weight: bold; font-family: Times New Roman;'>🚚 New Deliveries Tracking with Lead Time</h3>", unsafe_allow_html=True)
        st.caption("Track incoming deliveries - Enter Requested Date for each PO to calculate Lead Time = Posting Date - Requested Date")

        # Add CSS for shake animation on hover (SLOWED DOWN)
        st.markdown("""
        <style>
        @keyframes shake {
            0%, 100% { transform: translateX(0); }
            10%, 30%, 50%, 70%, 90% { transform: translateX(-2px); }
            20%, 40%, 60%, 80% { transform: translateX(2px); }
        }
        .stat-card:hover {
            animation: shake 0.8s ease-in-out;
            transform: scale(1.02);
            transition: all 0.3s ease;
        }
        </style>
        """, unsafe_allow_html=True)

        if not df_new_deliveries.empty:
            df_new_deliveries['Posting Date'] = pd.to_datetime(df_new_deliveries['Posting Date'], errors='coerce')

            # Convert PO Number to string
            df_new_deliveries['PO Number'] = df_new_deliveries['PO Number'].astype(str)

            # ============================================
            # CALCULATE LEAD TIME STATISTICS
            # ============================================
            temp_stats_df = df_new_deliveries.copy()
            temp_stats_df['Requested Date'] = temp_stats_df.apply(
                lambda row: st.session_state.requested_dates.get(f"{row['PO Number']}_{row['Material Description']}", None) if 'requested_dates' in st.session_state else None,
                axis=1
            )

            def calc_lead_value(row):
                req_date = row['Requested Date']
                posting = row['Posting Date']
                if req_date and pd.notna(posting):
                    try:
                        if hasattr(req_date, 'date'):
                            req_date = req_date.date()
                        if hasattr(posting, 'date'):
                            posting = posting.date()
                        days = (posting - req_date).days
                        return days if days >= 0 else None
                    except:
                        return None
                return None

            temp_stats_df['Lead Time Value'] = temp_stats_df.apply(calc_lead_value, axis=1)
            lead_values = temp_stats_df['Lead Time Value'].dropna().tolist()

            if lead_values:
                min_lead = round(min(lead_values))
                max_lead = round(max(lead_values))
                avg_lead = round(sum(lead_values) / len(lead_values))
            else:
                min_lead = max_lead = avg_lead = 0

            total_deliveries = len(df_new_deliveries)
            unique_pos_count = df_new_deliveries['PO Number'].nunique()

            if not df_new_deliveries.empty and 'Posting Date' in df_new_deliveries.columns:
                newest_row = df_new_deliveries.loc[df_new_deliveries['Posting Date'].idxmax()]
                newest_po = newest_row.get('PO Number', 'N/A')
                newest_date = newest_row.get('Posting Date', datetime.now()).strftime('%d/%m/%y')
            else:
                newest_po = "N/A"
                newest_date = "N/A"

            # ============================================
            # STATISTICS - ROW 1 (3 cards, no Saved Dates)
            # ============================================
            st.markdown("### 📊 PO Delivery Statistics")

            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown(f"""
                <div class="stat-card" style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 15px; padding: 20px; text-align: center; color: white; cursor: pointer;'>
                    <p style='font-size: 14px; margin: 0; opacity: 0.9;'>📦 TOTAL DELIVERIES</p>
                    <p style='font-size: 32px; font-weight: bold; margin: 5px 0;'>{total_deliveries:,}</p>
                </div>
                """, unsafe_allow_html=True)
            with col2:
                st.markdown(f"""
                <div class="stat-card" style='background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); border-radius: 15px; padding: 20px; text-align: center; color: white; cursor: pointer;'>
                    <p style='font-size: 14px; margin: 0; opacity: 0.9;'>📋 UNIQUE POs</p>
                    <p style='font-size: 32px; font-weight: bold; margin: 5px 0;'>{unique_pos_count:,}</p>
                </div>
                """, unsafe_allow_html=True)
            with col3:
                st.markdown(f"""
                <div class="stat-card" style='background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); border-radius: 15px; padding: 20px; text-align: center; color: white; cursor: pointer;'>
                    <p style='font-size: 14px; margin: 0; opacity: 0.9;'>🆕 NEWEST PO</p>
                    <p style='font-size: 20px; font-weight: bold; margin: 5px 0;'>{newest_po}</p>
                    <p style='font-size: 12px; margin: 0; opacity: 0.8;'>{newest_date}</p>
                </div>
                """, unsafe_allow_html=True)

            # Row 2: Lead Time Stats
            st.markdown("<br>", unsafe_allow_html=True)
            col4, col5, col6 = st.columns(3)
            with col4:
                lead_color = "#28a745" if min_lead < 60 else "#ffc107" if min_lead < 120 else "#dc3545"
                st.markdown(f"""
                <div class="stat-card" style='background: linear-gradient(135deg, #ffecd2 0%, #fcb69f 100%); border-radius: 15px; padding: 20px; text-align: center; cursor: pointer;'>
                    <p style='font-size: 14px; margin: 0; opacity: 0.8;'>⏱️ MIN LEAD TIME</p>
                    <p style='font-size: 32px; font-weight: bold; margin: 5px 0; color: {lead_color};'>{min_lead} days</p>
                </div>
                """, unsafe_allow_html=True)
            with col5:
                lead_color = "#28a745" if max_lead < 60 else "#ffc107" if max_lead < 120 else "#dc3545"
                st.markdown(f"""
                <div class="stat-card" style='background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%); border-radius: 15px; padding: 20px; text-align: center; cursor: pointer;'>
                    <p style='font-size: 14px; margin: 0; opacity: 0.8;'>🐢 MAX LEAD TIME</p>
                    <p style='font-size: 32px; font-weight: bold; margin: 5px 0; color: {lead_color};'>{max_lead} days</p>
                </div>
                """, unsafe_allow_html=True)
            with col6:
                lead_color = "#28a745" if avg_lead < 60 else "#ffc107" if avg_lead < 120 else "#dc3545"
                st.markdown(f"""
                <div class="stat-card" style='background: linear-gradient(135deg, #d4fc79 0%, #96e6a1 100%); border-radius: 15px; padding: 20px; text-align: center; cursor: pointer;'>
                    <p style='font-size: 14px; margin: 0; opacity: 0.8;'>📊 Avg.Lead Time</p>
                    <p style='font-size: 32px; font-weight: bold; margin: 5px 0; color: {lead_color};'>{avg_lead} days</p>
                </div>
                """, unsafe_allow_html=True)

            st.markdown("---")

            # ============================================
            # DATE RANGE FILTER (UPDATED TO WORK WITH REQUESTED DATE)
            # ============================================
            st.markdown("#### 📅 Date Range Filter")

            # Add radio button to choose filter type
            filter_type = st.radio(
                "Filter by:",
                ["Posting Date", "Requested Date (Saved Only)"],
                horizontal=True,
                key="date_filter_type"
            )

            col_date1, col_date2 = st.columns(2)

            # Get available dates based on filter type
            if filter_type == "Posting Date":
                available_dates = df_new_deliveries['Posting Date'].dropna()
                if not available_dates.empty:
                    min_date = available_dates.min().date()
                    max_date = available_dates.max().date()
                else:
                    min_date = datetime.now().date()
                    max_date = datetime.now().date()

                with col_date1:
                    start_date = st.date_input("From Date", value=min_date, min_value=min_date, max_value=max_date, key="start_date_posting")
                with col_date2:
                    end_date = st.date_input("To Date", value=max_date, min_value=min_date, max_value=max_date, key="end_date_posting")

                # Apply filter based on Posting Date
                mask_date = (df_new_deliveries['Posting Date'].dt.date >= start_date) & (df_new_deliveries['Posting Date'].dt.date <= end_date)
                filtered_delivery_df = df_new_deliveries[mask_date].copy()

            else:  # Filter by Requested Date
                # First, add requested dates to dataframe
                temp_req_df = df_new_deliveries.copy()
                temp_req_df['Requested Date'] = temp_req_df.apply(
                    lambda row: st.session_state.requested_dates.get(f"{row['PO Number']}_{row['Material Description']}", None) if 'requested_dates' in st.session_state else None,
                    axis=1
                )

                # Filter to only rows with requested dates
                requested_rows = temp_req_df[temp_req_df['Requested Date'].notna()].copy()

                if not requested_rows.empty:
                    # Convert requested dates to datetime
                    requested_rows['Requested Date'] = pd.to_datetime(requested_rows['Requested Date'])
                    min_date = requested_rows['Requested Date'].min().date()
                    max_date = requested_rows['Requested Date'].max().date()
                else:
                    min_date = datetime.now().date()
                    max_date = datetime.now().date()
                    st.info("No saved Requested Dates available to filter.")

                with col_date1:
                    start_date = st.date_input("From Date", value=min_date, min_value=min_date, max_value=max_date, key="start_date_requested")
                with col_date2:
                    end_date = st.date_input("To Date", value=max_date, min_value=min_date, max_value=max_date, key="end_date_requested")

                # Apply filter based on Requested Date (only for rows with requested dates)
                mask_date = (requested_rows['Requested Date'].dt.date >= start_date) & (requested_rows['Requested Date'].dt.date <= end_date)
                filtered_requested = requested_rows[mask_date].copy()

                # Also include deliveries that have NO requested date?
                include_no_date = st.checkbox("Include deliveries without Requested Date", value=False, key="include_no_date")
                if include_no_date:
                    no_date_rows = temp_req_df[temp_req_df['Requested Date'].isna()].copy()
                    filtered_delivery_df = pd.concat([filtered_requested, no_date_rows], ignore_index=True)
                else:
                    filtered_delivery_df = filtered_requested

            st.markdown("---")

                        # ============================================
            # ENTER REQUESTED DATE BY PO (MOVED HERE)
            # ============================================
            st.markdown("### ✏️ Enter Requested Date by PO")

            # Use the original unfiltered df for PO selection to avoid confusion
            # Filter out NaN values from PO Number column
            unique_pos = df_new_deliveries['PO Number'].dropna().unique()
            # Convert all to string and filter out any 'nan' strings
            unique_pos = [str(po) for po in unique_pos if str(po).lower() != 'nan' and po != '']
            po_options = sorted(unique_pos)

            selected_po = st.selectbox("Select Purchase Order:", ["-- Select a PO --"] + po_options, key="po_selector_leadtime")

            if selected_po != "-- Select a PO --":
                po_number = selected_po
                po_materials = df_new_deliveries[df_new_deliveries['PO Number'].astype(str) == po_number]

                st.info(f"PO {po_number} has {len(po_materials)} material(s)")

                for idx, row in po_materials.iterrows():
                    material_name = row['Material Description']
                    if pd.isna(material_name):
                        continue

                    key = f"{po_number}_{material_name}"
                    current_date = st.session_state.requested_dates.get(key, None) if 'requested_dates' in st.session_state else None

                    unique_id = f"{po_number}_{idx}_{str(material_name).replace(' ', '_')[:30]}"

                    col1, col2, col3 = st.columns([3, 1.5, 1])
                    with col1:
                        st.write(f"**{material_name}**")
                        qty = row['Quantity']
                        if pd.notna(qty):
                            st.write(f"Quantity: {int(qty):,}" if qty else "N/A")
                        else:
                            st.write("Quantity: N/A")
                    with col2:
                        new_date = st.date_input(
                            "Requested Date",
                            value=current_date if current_date else datetime.now().date(),
                            key=f"req_date_{unique_id}",
                            label_visibility="collapsed"
                        )
                    with col3:
                        if st.button(f"💾 Save", key=f"save_{unique_id}", use_container_width=True):
                            if save_po_requested_date(po_number, str(material_name), new_date):
                                if 'requested_dates' not in st.session_state:
                                    st.session_state.requested_dates = {}
                                st.session_state.requested_dates[key] = new_date
                                log_dashboard_update("Updated requested date", f"{material_name} | PO {po_number} | {new_date}", 1)
                                st.success(f"✅ Saved for {material_name}")
                                st.rerun()
                            else:
                                st.error("Error saving")

                    if current_date:
                        if st.button(f"🗑️ Clear", key=f"clear_{unique_id}"):
                            if delete_po_requested_date(po_number, str(material_name)):
                                if key in st.session_state.requested_dates:
                                    del st.session_state.requested_dates[key]
                                st.success(f"✅ Cleared for {material_name}")
                                st.rerun()
                    st.markdown("---")

            # ============================================
            # SEARCH FILTER
            # ============================================
            search_delivery = st.text_input("🔍 Search by Material, PO Number", placeholder="e.g., 'artesunate' or '4500006862'")

            if search_delivery and not filtered_delivery_df.empty:
                mask = filtered_delivery_df.astype(str).apply(
                    lambda col: col.str.contains(search_delivery, case=False, na=False)
                ).any(axis=1)
                filtered_delivery_df = filtered_delivery_df[mask]
                st.info(f"Found {len(filtered_delivery_df)} matching deliveries")

            # ============================================
            # MATERIALS WITH REQUESTED DATE ONLY
            # ============================================
            st.markdown("### 📋 Materials with Requested Date Only")

            if not filtered_delivery_df.empty:
                temp_df = filtered_delivery_df.copy()
                temp_df['Requested Date'] = temp_df.apply(
                    lambda row: st.session_state.requested_dates.get(f"{row['PO Number']}_{row['Material Description']}", None) if 'requested_dates' in st.session_state else None,
                    axis=1
                )

                def calculate_lead_time_value(row):
                    req_date = row['Requested Date']
                    posting = row['Posting Date']
                    if req_date and pd.notna(posting):
                        try:
                            if hasattr(req_date, 'date'):
                                req_date = req_date.date()
                            if hasattr(posting, 'date'):
                                posting = posting.date()
                            days = (posting - req_date).days
                            return days if days >= 0 else None
                        except:
                            return None
                    return None

                temp_df['Lead Time Value'] = temp_df.apply(calculate_lead_time_value, axis=1)
                requested_only_df = temp_df[temp_df['Requested Date'].notna()].copy()

                if not requested_only_df.empty:
                    requested_only_df['Requested Date Display'] = requested_only_df['Requested Date'].apply(
                        lambda x: x.strftime('%Y-%m-%d') if hasattr(x, 'strftime') else str(x)
                    )
                    requested_only_df['Lead Time Display'] = requested_only_df['Lead Time Value'].apply(
                        lambda x: f"{x} days" if x else ""
                    )
                    requested_only_df['Quantity Display'] = requested_only_df['Quantity'].apply(
                        lambda x: f"{int(x):,}" if pd.notna(x) else "0"
                    )
                    if 'Posting Date' in requested_only_df.columns:
                        requested_only_df['Posting Date Display'] = requested_only_df['Posting Date'].dt.strftime('%Y-%m-%d')

                    display_cols_requested = ['Material Description', 'PO Number', 'Posting Date Display', 'Quantity Display', 'Requested Date Display', 'Lead Time Display']
                    display_cols_requested = [col for col in display_cols_requested if col in requested_only_df.columns]

                    st.dataframe(
                        requested_only_df[display_cols_requested].rename(columns={
                            'Posting Date Display': 'Posting Date',
                            'Quantity Display': 'Quantity',
                            'Lead Time Display': 'Lead Time'
                        }),
                        column_config={
                            'Material Description': st.column_config.TextColumn('Material Description', width=350),
                            'PO Number': st.column_config.TextColumn('PO Number', width=130),
                            'Posting Date': st.column_config.TextColumn('Posting Date', width=100),
                            'Quantity': st.column_config.TextColumn('Quantity', width=80),
                            'Requested Date': st.column_config.TextColumn('Requested Date', width=100),
                            'Lead Time': st.column_config.TextColumn('Lead Time', width=100)
                        },
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.info("No materials with Requested Date found in the filtered data.")
            else:
                st.info("No data available after filtering.")

            st.markdown("---")

            # ============================================
            # TABLE 1: DETAILED DELIVERIES
            # ============================================
            if not filtered_delivery_df.empty:
                display_df = filtered_delivery_df.copy()
                if 'Quantity' in display_df.columns:
                    display_df['Quantity'] = pd.to_numeric(display_df['Quantity'], errors='coerce')
                    display_df['Quantity_display'] = display_df['Quantity'].apply(format_number_with_commas)
                else:
                    display_df['Quantity_display'] = 'N/A'

                if 'Posting Date' in display_df.columns:
                    display_df['Posting Date_display'] = display_df['Posting Date'].dt.strftime('%Y-%m-%d')

                display_df['Requested Date'] = display_df.apply(
                    lambda row: st.session_state.requested_dates.get(f"{row['PO Number']}_{row['Material Description']}", None) if 'requested_dates' in st.session_state else None,
                    axis=1
                )

                display_df['Requested Date Display'] = display_df['Requested Date'].apply(
                    lambda x: x.strftime('%Y-%m-%d') if hasattr(x, 'strftime') else (x if x else '')
                )

                def calculate_lead_time_display(row):
                    req_date = row['Requested Date']
                    posting = row['Posting Date']
                    if req_date and pd.notna(posting):
                        try:
                            if hasattr(req_date, 'date'):
                                req_date = req_date.date()
                            if hasattr(posting, 'date'):
                                posting = posting.date()
                            days = (posting - req_date).days
                            if days < 0:
                                return "⚠️ Future"
                            elif days < 120:
                                return f"🟢 {days} days"
                            elif days < 180:
                                return f"🟡 {days} days"
                            else:
                                return f"🔴 {days} days"
                        except:
                            return "Error"
                    elif req_date:
                        return "⏳ Awaiting"
                    elif pd.notna(posting):
                        return "❌ No date"
                    return ""

                display_df['Lead Time'] = display_df.apply(calculate_lead_time_display, axis=1)

                st.markdown("### 📋 Table 1: Detailed Deliveries with Lead Time")

                if 'Posting Date_display' in display_df.columns:
                    display_df = display_df.sort_values('Posting Date_display', ascending=False)

                display_cols = ['Material Description', 'Posting Date_display', 'PO Number', 'Quantity_display', 'Requested Date Display', 'Lead Time']
                display_cols = [col for col in display_cols if col in display_df.columns]
                display_rename = {'Quantity_display': 'Quantity', 'Requested Date Display': 'Requested Date', 'Posting Date_display': 'Posting Date'}

                st.dataframe(
                    display_df[display_cols].rename(columns=display_rename),
                    column_config={
                        'Material Description': st.column_config.TextColumn('Material Description', width=300),
                        'Posting Date': st.column_config.TextColumn('Posting Date', width=100),
                        'PO Number': st.column_config.TextColumn('PO Number', width=130),
                        'Quantity': st.column_config.TextColumn('Quantity', width=80),
                        'Requested Date': st.column_config.TextColumn('Requested Date', width=100),
                        'Lead Time': st.column_config.TextColumn('Lead Time', width=100)
                    },
                    use_container_width=True,
                    hide_index=True
                )

                st.markdown("---")

                # ============================================
                # TABLE 2: SUMMARIZED DELIVERIES
                # ============================================
                st.markdown("### 📊 Table 2: Summarized Deliveries (Same Material + PO Combined)")
                st.caption("When the same Material Description and PO Number appear multiple times, quantities are summed up")

                summary_df = filtered_delivery_df.copy()
                if 'Quantity' in summary_df.columns:
                    summary_df['Quantity'] = pd.to_numeric(summary_df['Quantity'], errors='coerce')

                grouped_summary = summary_df.groupby(['Material Description', 'PO Number']).agg({
                    'Quantity': 'sum',
                    'Posting Date': 'count'
                }).rename(columns={'Quantity': 'Total Quantity', 'Posting Date': 'Number of Deliveries'}).reset_index()

                grouped_summary['Total Quantity'] = grouped_summary['Total Quantity'].apply(format_number_with_commas)

                st.dataframe(
                    grouped_summary,
                    column_config={
                        'Material Description': st.column_config.TextColumn('Material Description', width=350),
                        'PO Number': st.column_config.TextColumn('PO Number', width=150),
                        'Total Quantity': st.column_config.TextColumn('Total Quantity', width=100),
                        'Number of Deliveries': st.column_config.NumberColumn('Number of Deliveries', width=100)
                    },
                    use_container_width=True,
                    hide_index=True
                )

                st.markdown("---")

                # ============================================
                # TOP NEW DELIVERIES
                # ============================================
                st.markdown("### 🏆 Top New Deliveries (Highest Quantity)")

                top_deliveries = filtered_delivery_df.copy()
                if 'Quantity' in top_deliveries.columns:
                    top_deliveries['Quantity'] = pd.to_numeric(top_deliveries['Quantity'], errors='coerce')

                top_grouped = top_deliveries.groupby('Material Description').agg({
                    'Quantity': 'sum'
                }).reset_index().sort_values('Quantity', ascending=False).head(10)

                top_grouped['Quantity'] = top_grouped['Quantity'].apply(format_number_with_commas)

                col_top1, col_top2, col_top3, col_top4, col_top5 = st.columns(5)
                for i, (idx, row) in enumerate(top_grouped.head(5).iterrows()):
                    with [col_top1, col_top2, col_top3, col_top4, col_top5][i]:
                        st.metric(f"#{i+1}", row['Material Description'][:30], delta=row['Quantity'])

                st.dataframe(
                    top_grouped,
                    column_config={
                        'Material Description': st.column_config.TextColumn('Material Description', width=400),
                        'Quantity': st.column_config.TextColumn('Total Quantity', width=150)
                    },
                    use_container_width=True,
                    hide_index=True
                )

                st.markdown("---")

                # ============================================
                # NEWEST PURCHASE ORDERS
                # ============================================
                st.markdown("### 🆕 Newest Purchase Orders (Last 10)")

                newest_pos = filtered_delivery_df.copy()
                if 'Posting Date' in newest_pos.columns:
                    newest_pos['Posting Date'] = pd.to_datetime(newest_pos['Posting Date'], errors='coerce')
                    newest_pos = newest_pos.sort_values('Posting Date', ascending=False).drop_duplicates(subset=['PO Number']).head(10)

                    newest_pos['Posting Date'] = newest_pos['Posting Date'].dt.strftime('%Y-%m-%d')
                    if 'Quantity' in newest_pos.columns:
                        newest_pos['Quantity'] = pd.to_numeric(newest_pos['Quantity'], errors='coerce')
                        newest_pos['Quantity'] = newest_pos['Quantity'].apply(format_number_with_commas)

                    newest_display_cols = ['PO Number', 'Posting Date', 'Material Description', 'Quantity']
                    newest_display_cols = [col for col in newest_display_cols if col in newest_pos.columns]

                    st.dataframe(
                        newest_pos[newest_display_cols],
                        column_config={
                            'PO Number': st.column_config.TextColumn('PO Number', width=150),
                            'Posting Date': st.column_config.TextColumn('Posting Date', width=120),
                            'Material Description': st.column_config.TextColumn('Material Description', width=300),
                            'Quantity': st.column_config.TextColumn('Quantity', width=100)
                        },
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.info("No posting date data available to determine newest POs")

                st.markdown("---")

                # ============================================
                # EXPORT BUTTONS
                # ============================================
                col_dl1, col_dl2 = st.columns(2)
                with col_dl1:
                    export_cols = ['Material Description', 'Posting Date_display', 'PO Number', 'Quantity_display', 'Requested Date Display', 'Lead Time']
                    export_cols = [col for col in export_cols if col in display_df.columns]
                    st.download_button(
                        label="📥 Download Detailed View (Excel)",
                        data=display_df[export_cols].rename(columns=display_rename).pipe(_xl),
                        file_name=f"new_deliveries_detailed_{start_date}_{end_date}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                with col_dl2:
                    st.download_button(
                        label="📥 Download Summarized View (Excel)",
                        data=grouped_summary.pipe(_xl),
                        file_name=f"new_deliveries_summarized_{start_date}_{end_date}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )

                if len(filtered_delivery_df) > len(grouped_summary):
                    st.info(f"📊 {len(filtered_delivery_df)} detailed records combined into {len(grouped_summary)} summarized records")

                # ============================================
                # SAVED REQUESTED DATES SUMMARY
                # ============================================
                st.markdown("---")
                st.markdown("### 📊 Saved Requested Dates Summary")

                if 'requested_dates' in st.session_state and st.session_state.requested_dates:
                    summary_rows = []
                    for key, req_date in st.session_state.requested_dates.items():
                        parts = key.split("_", 1)
                        po = parts[0]
                        material = parts[1] if len(parts) > 1 else ""
                        summary_rows.append({
                            'PO Number': po,
                            'Material': material[:60],
                            'Requested Date': req_date.strftime('%Y-%m-%d') if hasattr(req_date, 'strftime') else str(req_date)
                        })
                    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

                    if st.button("🗑️ Clear All Saved Requested Dates", use_container_width=True):
                        for key, req_date in st.session_state.requested_dates.items():
                            parts = key.split("_", 1)
                            po = parts[0]
                            material = parts[1] if len(parts) > 1 else ""
                            delete_po_requested_date(po, material)
                        st.session_state.requested_dates = {}
                        st.success("✅ All requested dates cleared!")
                        st.rerun()
                else:
                    st.info("No saved requested dates. Select a PO above and click Save.")
            else:
                st.info("No data available after filtering. Please adjust your date range or include deliveries without Requested Date.")

        else:
            st.info("No new deliveries data available. Please upload data to the New_deliveries table in Supabase.")
            st.caption("Expected columns: material_description, posting_date, purchase_order, quantity")
# ---------------------------------------------------
# Download Filtered Data
# ---------------------------------------------------
if not display_df_filtered.empty and 'Material Description' in display_df_filtered.columns and page != "Advanced Analytics" and page != "Executive Summary":
    st.divider()
    st.download_button(label="📥 Download Full Data (Excel)", data=display_df_filtered.pipe(_xl), 
                      file_name=f"full_stock_dashboard_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx", 
                      mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
