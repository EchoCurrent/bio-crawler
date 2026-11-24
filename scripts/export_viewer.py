#!/usr/bin/env python3
"""
静态情报库查看器生成器

读取 research.db 全部条目, 按关键词规则分类, 生成自包含的单文件 HTML:
  viewer/index.html  (双击浏览器打开即可, 无需服务器)

用法:
  venv/bin/python scripts/export_viewer.py
  venv/bin/python scripts/export_viewer.py --db data/research.db --out viewer/index.html
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT))

from render_table_report import classify  # noqa: E402  (复用同一套关键词规则, 与飞书日报口径一致)

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>生物医学情报库</title>
<style>
:root { --bg:#16181d; --bg2:#1e2128; --bg3:#262a33; --fg:#d8dce3; --fg-dim:#8b93a1;
        --accent:#4f8cff; --accent2:#7c5cff; --ok:#3fb96f; --warn:#d8a03f; --line:#2e333d; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--fg);
       font:14px/1.6 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif; }
header { padding:14px 20px; background:var(--bg2); border-bottom:1px solid var(--line);
         display:flex; flex-wrap:wrap; gap:12px; align-items:center; position:sticky; top:0; z-index:9; }
h1 { font-size:17px; margin:0; }
.stats { color:var(--fg-dim); font-size:12.5px; }
.stats b { color:var(--accent); }
.controls { display:flex; flex-wrap:wrap; gap:8px; margin-left:auto; align-items:center; }
input[type=search], select {
  background:var(--bg3); color:var(--fg); border:1px solid var(--line); border-radius:8px;
  padding:6px 10px; font-size:13px; outline:none; }
input[type=search] { width:220px; }
input[type=search]:focus { border-color:var(--accent); }
button {
  background:var(--bg3); color:var(--fg); border:1px solid var(--line); border-radius:8px;
  padding:6px 12px; font-size:13px; cursor:pointer; }
button:hover { border-color:var(--accent); }
button.primary { background:var(--accent); border-color:var(--accent); color:#fff; }
#chips { padding:10px 20px; display:flex; flex-wrap:wrap; gap:6px; background:var(--bg2);
         border-bottom:1px solid var(--line); }
.chip { border-radius:999px; padding:3px 11px; font-size:12.5px; background:var(--bg3);
        border:1px solid var(--line); cursor:pointer; color:var(--fg-dim); }
.chip .n { color:var(--fg-dim); margin-left:4px; font-size:11px; }
.chip.active { background:var(--accent); border-color:var(--accent); color:#fff; }
.chip.active .n { color:#dce8ff; }
main { padding:0 20px 40px; }
table { width:100%; border-collapse:collapse; margin-top:14px; }
th, td { text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:top; }
th { color:var(--fg-dim); font-weight:600; font-size:12.5px; position:sticky; top:108px;
     background:var(--bg); cursor:pointer; user-select:none; white-space:nowrap; }
tr:hover td { background:var(--bg2); }
td.title { max-width:380px; }
td.title a { color:var(--accent); text-decoration:none; }
td.title a:hover { text-decoration:underline; }
td .sum { color:var(--fg-dim); font-size:12.5px; display:block; margin-top:2px; }
.kw { display:inline-block; background:var(--bg3); border-radius:6px; padding:1px 7px;
      font-size:12px; color:var(--accent2); white-space:nowrap; }
.rel-high { color:var(--ok); font-weight:600; }
.rel-medium { color:var(--warn); }
.alts { color:var(--fg-dim); font-size:11.5px; margin-top:2px; }
.alts a { color:var(--fg-dim); }
.empty { padding:40px; text-align:center; color:var(--fg-dim); }
footer { padding:10px 20px; color:var(--fg-dim); font-size:12px; border-top:1px solid var(--line); }
</style>
</head>
<body>
<header>
  <h1>🧬 生物医学情报库</h1>
  <span class="stats" id="stats"></span>
  <div class="controls">
    <input type="search" id="q" placeholder="搜索标题 / 摘要 / 来源…">
    <select id="f-sub"><option value="">全部子方向</option></select>
    <select id="f-rel"><option value="">全部相关度</option><option value="high">high</option><option value="medium">medium</option></select>
    <select id="f-sort">
      <option value="new">按入库时间</option>
      <option value="ptime">按发布时间</option>
      <option value="rel">相关度优先</option>
    </select>
    <button class="primary" id="btn-csv">导出筛选结果 CSV</button>
    <button id="btn-reset">重置</button>
  </div>
</header>
<div id="chips"></div>
<main><table id="tbl">
  <thead><tr>
    <th data-k="title">标题</th><th data-k="kw">关键词</th><th data-k="src">来源</th>
    <th data-k="ptime">时间</th><th data-k="rel">相关度</th>
  </tr></thead>
  <tbody id="rows"></tbody>
</table><div class="empty" id="empty" style="display:none">没有匹配的记录</div></main>
<footer>生成时间: __GEN_TIME__ · 数据源: research.db · 关键词分类规则与飞书日报一致</footer>
<script>
const DATA = __DATA_JSON__;
const esc = s => (s||"").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const state = { q:"", kw:null, sub:"", rel:"", sort:"new" };

const kwCounts = {};
DATA.forEach(r => { kwCounts[r.kw] = (kwCounts[r.kw]||0) + 1; });

const chipsEl = document.getElementById("chips");
function renderChips() {
  const keys = Object.entries(kwCounts).sort((a,b) => b[1]-a[1]);
  chipsEl.innerHTML = keys.map(([k,n]) =>
    `<span class="chip ${state.kw===k?'active':''}" data-kw="${esc(k)}">${esc(k)}<span class="n">${n}</span></span>`
  ).join("");
}
chipsEl.addEventListener("click", e => {
  const c = e.target.closest(".chip"); if (!c) return;
  state.kw = state.kw === c.dataset.kw ? null : c.dataset.kw;
  renderChips(); render();
});

const subSel = document.getElementById("f-sub");
[...new Set(DATA.map(r => r.sub).filter(Boolean))].sort().forEach(s => {
  const o = document.createElement("option"); o.value = s; o.textContent = s; subSel.appendChild(o);
});
subSel.onchange = e => { state.sub = e.target.value; render(); };
document.getElementById("f-rel").onchange = e => { state.rel = e.target.value; render(); };
document.getElementById("f-sort").onchange = e => { state.sort = e.target.value; render(); };
document.getElementById("q").oninput = e => { state.q = e.target.value.trim().toLowerCase(); render(); };
document.getElementById("btn-reset").onclick = () => {
  Object.assign(state, { q:"", kw:null, sub:"", rel:"", sort:"new" });
  document.getElementById("q").value = ""; subSel.value = ""; 
  document.getElementById("f-rel").value = ""; document.getElementById("f-sort").value = "new";
  renderChips(); render();
};

function filtered() {
  let rows = DATA.filter(r => {
    if (state.kw && r.kw !== state.kw) return false;
    if (state.sub && r.sub !== state.sub) return false;
    if (state.rel && r.rel !== state.rel) return false;
    if (state.q) {
      const hay = (r.title + " " + r.sum + " " + r.src).toLowerCase();
      if (!hay.includes(state.q)) return false;
    }
    return true;
  });
  if (state.sort === "rel") rows.sort((a,b) => (a.rel==="high"?0:1) - (b.rel==="high"?0:1));
  else if (state.sort === "ptime") rows.sort((a,b) => (b.ptime||"").localeCompare(a.ptime||""));
  else rows.sort((a,b) => (b.created||"").localeCompare(a.created||""));
  return rows;
}

function render() {
  const rows = filtered();
  const nHigh = rows.filter(r => r.rel === "high").length;
  document.getElementById("stats").innerHTML =
    `显示 <b>${rows.length}</b> / ${DATA.length} 条 · 其中 high <b>${nHigh}</b> 条`;
  const tbody = document.getElementById("rows");
  document.getElementById("empty").style.display = rows.length ? "none" : "";
  tbody.innerHTML = rows.map(r => `
    <tr>
      <td class="title"><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a>
        <span class="sum">${esc(r.sum)}</span>
        ${r.alts && r.alts.length ? `<span class="alts">交叉来源: ${r.alts.map(a=>`<a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.source||"link")}</a>`).join(" · ")}</span>` : ""}
      </td>
      <td><span class="kw">${esc(r.kw)}</span></td>
      <td>${esc(r.src)}</td>
      <td>${esc(r.ptime || (r.created||"").slice(0,10) || "-")}</td>
      <td class="rel-${esc(r.rel)}">${esc(r.rel)}</td>
    </tr>`).join("");
}

document.getElementById("btn-csv").onclick = () => {
  const rows = filtered();
  const head = ["标题","关键词","来源","摘要","相关度","发布时间","入库时间","链接","交叉来源"];
  const q = v => `"${String(v??"").replace(/"/g,'""')}"`;
  const lines = [head.join(",")].concat(rows.map(r => [
    q(r.title), q(r.kw), q(r.src), q(r.sum), q(r.rel), q(r.ptime), q((r.created||"").slice(0,19)),
    q(r.url), q((r.alts||[]).map(a => `${a.source}: ${a.url}`).join("; "))
  ].join(",")));
  const blob = new Blob(["\ufeff" + lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `情报库筛选_${rows.length}条.csv`;
  a.click(); URL.revokeObjectURL(a.href);
};

renderChips(); render();
</script>
</body>
</html>
"""


def extract_tags(tags_json: str):
    """tags 是 JSON 数组: [subtopic, 'relevance:high'?, alt_sources_json?]"""
    sub, rel, alts = "", "medium", []
    try:
        tags = json.loads(tags_json or "[]")
    except json.JSONDecodeError:
        return sub, rel, alts
    for t in tags:
        if isinstance(t, str):
            if t.startswith("relevance:"):
                rel = t.split(":", 1)[1]
            else:
                sub = t
            try:
                parsed = json.loads(t)
                if isinstance(parsed, list):
                    alts = parsed
            except (json.JSONDecodeError, TypeError):
                pass
    return sub, rel, alts


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(PROJECT_ROOT / "data" / "research.db"))
    p.add_argument("--out", default=str(PROJECT_ROOT / "viewer" / "index.html"))
    args = p.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, account_name, title, url, publish_time, digest, category, tags, created_at "
        "FROM articles ORDER BY created_at DESC, id DESC"
    ).fetchall()
    conn.close()

    records = []
    for r in rows:
        sub, rel, alts = extract_tags(r["tags"])
        summary = (r["digest"] or "")[:120]
        records.append({
            "id": r["id"],
            "title": r["title"],
            "url": r["url"],
            "kw": classify({"title": r["title"], "summary": summary}),
            "src": r["account_name"],
            "sum": summary,
            "rel": rel,
            "ptime": r["publish_time"] or "",
            "sub": sub,
            "created": r["created_at"] or "",
            "alts": alts,
        })

    data_json = json.dumps(records, ensure_ascii=False).replace("</", "<\\/")
    from datetime import datetime
    html = (HTML_TEMPLATE
            .replace("__DATA_JSON__", data_json)
            .replace("__GEN_TIME__", datetime.now().strftime("%Y-%m-%d %H:%M")))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    size_mb = out.stat().st_size / 1024 / 1024
    print(f"已生成 {out} ({len(records)} 条, {size_mb:.2f} MB)")


if __name__ == "__main__":
    main()
