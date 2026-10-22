#!/usr/bin/env python3
"""Daily Steel & Macro Briefing 사이트 생성기 (표준 라이브러리만 사용).

입력
  config/indicators.json        지표 구성(섹션·블록·행)
  data/series/<key>.csv         일별 시계열 (date,value) — fetch_series.py가 갱신
  data/monthly/<key>.csv        월·주·연 단위 시계열 (period,value) — 막대그래프용
  data/briefings/<YYYY-MM-DD>.json  일자별 수기 입력값(values)·주요 동향(news)·출처(sources)

출력
  docs/<YYYY-MM-DD>.html        일자별 브리핑 (한 번 만들면 고정, --force 시 재생성)
  docs/email/<YYYY-MM-DD>.html  메일 본문용(인라인 스타일, 그래프 제외)
  docs/index.html, docs/dates.json  일자 목록

기준 시점 규칙
  각 일자(D) 페이지는 D일 한국시간 07:30 시점의 확정치 스냅샷.
  「D」 열 = D 이전 최신 관측치(미국 지표는 직전 뉴욕 마감, 국내 지표는 직전 서울 마감),
  「D-1」 열 = 그 직전 관측치. 기간 평균은 해당 기간 내 관측치 단순평균.
"""
import argparse
import csv
import datetime as dt
import html
import json
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = os.path.join(ROOT, "config", "indicators.json")
SERIES_DIR = os.path.join(ROOT, "data", "series")
MONTHLY_DIR = os.path.join(ROOT, "data", "monthly")
BRIEF_DIR = os.path.join(ROOT, "data", "briefings")
DOCS = os.path.join(ROOT, "docs")
SITE_TITLE = "Daily Steel & Macro Briefing"
CHART_START = dt.date(2025, 1, 1)
NA = "확인 제한"

PALETTE = ["#1f4e79", "#c0504d", "#4f8a3c", "#d08c1f", "#6b4c9a", "#2a8c8c", "#7f7f7f"]


# ---------------------------------------------------------------- data
def load_series(key):
    path = os.path.join(SERIES_DIR, f"{key}.csv")
    out = []
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                out.append((dt.date.fromisoformat(r["date"]), float(r["value"])))
            except (ValueError, KeyError, TypeError):
                continue
    out.sort()
    return out


def load_periodic(key):
    path = os.path.join(MONTHLY_DIR, f"{key}.csv")
    out = []
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                out.append((r["period"].strip(), float(r["value"])))
            except (ValueError, KeyError, TypeError):
                continue
    out.sort()
    return out


def prev_month(y, m):
    return (y - 1, 12) if m == 1 else (y, m - 1)


def columns(d):
    """보고일 d 기준 10개 값 열 정의."""
    y, m = d.year, d.month
    cols = []
    cols.append(dict(id="y", label=f"{y-1}년", rng=(dt.date(y - 1, 1, 1), dt.date(y - 1, 12, 31))))
    if m >= 7:
        cols.append(dict(id="h", label=f"{y}년 상반기", rng=(dt.date(y, 1, 1), dt.date(y, 6, 30))))
    else:
        cols.append(dict(id="h", label=f"{y-1}년 하반기", rng=(dt.date(y - 1, 7, 1), dt.date(y - 1, 12, 31))))
    qi = (m - 1) // 3  # 완료된 분기 수
    qy, qn = (y, qi) if qi > 0 else (y - 1, 4)
    qs = dt.date(qy, (qn - 1) * 3 + 1, 1)
    qe_m = qn * 3
    qe = dt.date(qy + (1 if qe_m == 12 else 0), 1 if qe_m == 12 else qe_m + 1, 1) - dt.timedelta(days=1)
    cols.append(dict(id="q", label=f"{qy}년 {qn}Q", rng=(qs, qe)))
    py, pm = prev_month(y, m)
    pe = dt.date(y, m, 1) - dt.timedelta(days=1)
    cols.append(dict(id="pm", label=f"{py}년 {pm}월", rng=(dt.date(py, pm, 1), pe)))
    last = prev_business_day(d)
    cols.append(dict(id="mtd", label=f"{y}년 {m}월", sub=f"({m}.1~{last.day} 평균)" if last.month == m else "", rng=(dt.date(y, m, 1), d)))
    cols.append(dict(id="p1", label=f"{m}.1~10", rng=(dt.date(y, m, 1), dt.date(y, m, 10))))
    cols.append(dict(id="p2", label=f"{m}.11~20", rng=(dt.date(y, m, 11), dt.date(y, m, 20))))
    d1 = prev_business_day(d)
    d1c, d0c = prev_business_day(d1), d1
    cols.append(dict(id="d1", label=f"{d1.month}월{d1.day}일", sub=f"({d1c.month}.{d1c.day} 마감)", day=d1))
    cols.append(dict(id="d0", label=f"{d.month}월{d.day}일", sub=f"({d0c.month}.{d0c.day} 마감)", day=d))
    cols.append(dict(id="chg", label="전일대비"))
    return cols


def prev_business_day(d):
    p = d - dt.timedelta(days=1)
    while p.weekday() >= 5:
        p -= dt.timedelta(days=1)
    return p


def asof(series, day):
    """day 07:30 KST 시점 최신 관측치 = day 이전(미포함) 마지막 값."""
    last = None
    for t, v in series:
        if t < day:
            last = (t, v)
        else:
            break
    return last


def compute_row(series, d, cols):
    vals, notes = {}, {}
    usable = [(t, v) for t, v in series if t < d]
    for c in cols:
        cid = c["id"]
        if "rng" in c:
            a, b = c["rng"]
            if a >= d:
                continue
            xs = [v for t, v in usable if a <= t <= b]
            if xs:
                vals[cid] = statistics.fmean(xs)
                notes[cid] = f"{len(xs)}개 관측치 평균"
        elif cid in ("d0", "d1"):
            hit = asof(series, c["day"])
            if hit:
                vals[cid] = hit[1]
                notes[cid] = f"{hit[0].month}.{hit[0].day} 마감"
    if isinstance(vals.get("d0"), float) and isinstance(vals.get("d1"), float):
        vals["chg"] = vals["d0"] - vals["d1"]
    return vals, notes


# ---------------------------------------------------------------- format
def fmt(v, dec):
    if v is None or v == "":
        return NA
    if isinstance(v, (int, float)):
        return f"{v:,.{dec}f}"
    return str(v)


def fmt_chg(v, dec):
    if not isinstance(v, (int, float)):
        return (fmt(v, dec), "")
    if abs(v) < 10 ** (-dec) / 2:
        return ("0", "flat")
    s = f"{v:+,.{dec}f}"
    return (("▲ " + s[1:]) if v > 0 else ("▼ " + s[1:]), "up" if v > 0 else "down")


def esc(s):
    return html.escape(str(s), quote=True)


# ---------------------------------------------------------------- build one day
def build_rows(cfg, d, brief):
    """섹션별 표 데이터와 그래프 데이터 생성."""
    cols = columns(d)
    manual = brief.get("values", {})
    out = []
    for sec in cfg["sections"]:
        parts = []
        for part in sec["parts"]:
            blocks = []
            for blk in part["blocks"]:
                rows, chart_series = [], []
                for r in blk["rows"]:
                    vals, notes = {}, {}
                    daily = load_series(r["series"]) if r.get("series") else []
                    if daily:
                        vals, notes = compute_row(daily, d, cols)
                    m = manual.get(r["key"], {})
                    for k, v in m.items():
                        if k in ("note", "src"):
                            continue
                        if v is not None:
                            vals[k] = v  # 수기값 우선
                    if "chg" not in m and isinstance(vals.get("d0"), (int, float)) and isinstance(vals.get("d1"), (int, float)):
                        vals["chg"] = vals["d0"] - vals["d1"]
                    rows.append(dict(cfg=r, vals=vals, notes=notes, note=m.get("note", ""), src=m.get("src", "")))
                    if blk["chart"] == "line" and daily:
                        pts = [(t.isoformat(), v) for t, v in daily if CHART_START <= t < d]
                        chart_series.append(dict(name=r["name"], unit=r["unit"], points=pts))
                    else:
                        per = load_periodic(r["key"])
                        if per:
                            chart_series.append(dict(name=r["name"], unit=r["unit"], points=per))
                blocks.append(dict(cfg=blk, rows=rows, chart=chart_series))
            parts.append(dict(cfg=part, blocks=blocks))
        out.append(dict(cfg=sec, parts=parts))
    return cols, out


def table_html(cols, part, inline=False):
    th = "padding:6px 8px;border:1px solid #c9d3df;background:#1f4e79;color:#fff;font-weight:600;font-size:12px;white-space:nowrap;text-align:center"
    td = "padding:5px 8px;border:1px solid #d9e0e8;font-size:12px;text-align:right;white-space:nowrap"
    tdl = "padding:5px 8px;border:1px solid #d9e0e8;font-size:12px;text-align:left;white-space:nowrap"
    grp = "padding:5px 8px;border:1px solid #d9e0e8;font-size:12px;font-weight:700;background:#eef3f8;text-align:left"
    s = (lambda x: f' style="{x}"') if inline else (lambda x: "")
    h = [f'<table class="dt"{s("border-collapse:collapse;width:100%")}><thead><tr>']
    h.append(f'<th class="c-name"{s(th)}>구분</th>')
    for c in cols:
        sub = f'<br><span class="sub">{esc(c["sub"])}</span>' if c.get("sub") else ""
        h.append(f'<th{s(th)}>{esc(c["label"])}{sub}</th>')
    h.append("</tr></thead><tbody>")
    for blk in part["blocks"]:
        if len(blk["rows"]) > 1 or blk["cfg"]["title"] != blk["rows"][0]["cfg"]["name"]:
            h.append(f'<tr class="grp"><td colspan="{len(cols)+1}"{s(grp)}>{esc(blk["cfg"]["title"])}</td></tr>')
        for row in blk["rows"]:
            r = row["cfg"]
            dec = r.get("dec", 1)
            title_attr = f' title="{esc(row["note"])}"' if row["note"] else ""
            h.append(f'<tr><td class="c-name"{s(tdl)}{title_attr}>{esc(r["name"])} <span class="unit">({esc(r["unit"])})</span></td>')
            for c in cols:
                v = row["vals"].get(c["id"])
                if c["id"] == "chg":
                    txt, cls = fmt_chg(v, dec)
                    color = {"up": "#c0392b", "down": "#1f6fb2"}.get(cls, "#333")
                    h.append(f'<td class="chg {cls}"{s(td + ";color:" + color)}>{esc(txt)}</td>')
                else:
                    txt = fmt(v, dec)
                    cls = ' class="na"' if txt == NA else ""
                    tip = row["notes"].get(c["id"], "")
                    tip_attr = f' title="{esc(tip)}"' if tip and not inline else ""
                    style = td + (";color:#9aa5b1" if txt == NA else "")
                    h.append(f"<td{cls}{tip_attr}{s(style)}>{esc(txt)}</td>")
            h.append("</tr>")
    h.append("</tbody></table>")
    return "".join(h)


def notes_html(part):
    items = []
    for blk in part["blocks"]:
        for row in blk["rows"]:
            bits = [b for b in (row["note"], row["src"]) if b]
            if bits:
                label = row["cfg"]["name"] if blk["cfg"]["title"] in row["cfg"]["name"] or len(blk["rows"]) == 1 else f'{blk["cfg"]["title"]} · {row["cfg"]["name"]}'
                items.append(f'<li><b>{esc(label)}</b>: {esc(" / ".join(bits))}</li>')
    return f'<details class="rn"><summary>작성 기준·출처 비고 ({len(items)}건)</summary><ul class="rownotes">{"".join(items)}</ul></details>' if items else ""


def charts_html(part, sec_id, idx_start):
    h, specs, i = [], [], idx_start
    for blk in part["blocks"]:
        cid = f"ch{i}"
        i += 1
        title = blk["cfg"]["title"]
        unit = blk["rows"][0]["cfg"]["unit"]
        if not blk["chart"]:
            h.append(f'<div class="chart empty"><h4>{esc(title)} <span class="unit">({esc(unit)})</span></h4>'
                     f'<p>그래프용 시계열 {NA} — 데이터 확보 시 자동 표시</p></div>')
            continue
        h.append(f'<div class="chart"><h4>{esc(title)} <span class="unit">({esc(unit)})</span></h4>'
                 f'<div class="cbox"><canvas id="{cid}"></canvas></div></div>')
        specs.append(dict(id=cid, type=blk["cfg"]["chart"], series=blk["chart"]))
    return "".join(h), specs, i


NEWS_ORDER = ["매크로", "철강", "원료-철광석", "원료-제철용탄", "원료-철스크랩"]


def news_html(news, inline=False):
    th = "padding:6px 8px;border:1px solid #c9d3df;background:#1f4e79;color:#fff;font-size:12px;text-align:center"
    td = "padding:6px 8px;border:1px solid #d9e0e8;font-size:12px;vertical-align:top;text-align:left"
    s = (lambda x: f' style="{x}"') if inline else (lambda x: "")
    news = sorted(news, key=lambda n: (NEWS_ORDER.index(n["category"]) if n["category"] in NEWS_ORDER else 99))
    h = [f'<table class="nt"{s("border-collapse:collapse;width:100%")}><thead><tr>'
         f'<th{s(th)}>구분</th><th{s(th)}>매체명</th><th{s(th)}>기사명</th><th{s(th)}>주요내용</th></tr></thead><tbody>']
    for n in news:
        cat = n["category"].replace("원료-", "원료 · ")
        summ = "".join(f"<li>{esc(x)}</li>" for x in n.get("summary", []))
        date = f'<br><span class="sub">{esc(n.get("date", ""))}</span>' if n.get("date") else ""
        h.append(f'<tr><td class="cat"{s(td + ";white-space:nowrap;font-weight:600")}>{esc(cat)}</td>'
                 f'<td{s(td + ";white-space:nowrap")}>{esc(n["media"])}{date}</td>'
                 f'<td{s(td)}><a href="{esc(n["url"])}" target="_blank" rel="noopener">{esc(n["title"])}</a></td>'
                 f'<td{s(td)}><ul{s("margin:0;padding-left:16px")}>{summ}</ul></td></tr>')
    if not news:
        h.append(f'<tr><td colspan="4"{s(td)}>{NA}</td></tr>')
    h.append("</tbody></table>")
    return "".join(h)


PAGE_CSS = """
:root{--ink:#1d2733;--muted:#5b6876;--line:#d9e0e8;--head:#1f4e79;--band:#eef3f8;--bg:#f6f8fb;--card:#fff;--up:#c0392b;--down:#1f6fb2}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:'Noto Sans KR',system-ui,-apple-system,'Malgun Gothic',sans-serif;line-height:1.5}
header{background:var(--head);color:#fff;padding:18px 16px}
header .wrap{display:flex;flex-wrap:wrap;gap:12px;align-items:center;justify-content:space-between}
header h1{margin:0;font-size:22px;letter-spacing:-.3px}header .basis{font-size:12px;opacity:.85;margin-top:4px}
nav.dates{display:flex;gap:6px;align-items:center}nav.dates a,nav.dates select{color:#fff;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.3);border-radius:6px;padding:5px 9px;font-size:13px;text-decoration:none}
nav.dates select option{color:#000}
.wrap{max-width:1280px;margin:0 auto}main{padding:8px 16px 48px}
section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin:18px 0}
section h2{margin:0 0 12px;font-size:18px;color:var(--head)}h3{font-size:15px;margin:22px 0 8px;color:var(--ink);border-left:4px solid var(--head);padding-left:8px}
.tscroll{overflow-x:auto}
table.dt,table.nt{border-collapse:collapse;width:100%;font-size:12.5px}
.dt th,.nt th{background:var(--head);color:#fff;font-weight:600;padding:7px 8px;border:1px solid #c9d3df;white-space:nowrap}
.dt{table-layout:fixed;min-width:980px}.dt th.c-name{width:21%}.dt th{white-space:normal!important;word-break:keep-all}
.dt td{padding:6px 8px;border:1px solid var(--line);text-align:right;font-variant-numeric:tabular-nums;word-break:keep-all;overflow-wrap:anywhere}
.dt td.c-name{text-align:left;position:sticky;left:0;background:#fff}
.dt tr.grp td{background:var(--band);font-weight:700;text-align:left}
.dt td.na{color:#9aa5b1;font-size:11px}
details.rn{margin:8px 0 0}details.rn summary{cursor:pointer;font-size:12px;color:var(--muted)}.chg.up{color:var(--up)}.chg.down{color:var(--down)}
.unit,.sub{font-size:11px;color:var(--muted);font-weight:400}th .sub{color:#d6e2ee}
.nt td{padding:8px;border:1px solid var(--line);vertical-align:top}.nt ul{margin:0;padding-left:16px}.nt td.cat{white-space:nowrap;font-weight:600}
.nt a{color:var(--head)}
.charts{display:flex;flex-direction:column;gap:14px;margin-top:14px}
.chart{border:1px solid var(--line);border-radius:8px;padding:10px 12px}.chart h4{margin:0 0 6px;font-size:14px}
.cbox{position:relative;height:260px}.chart.empty p{color:var(--muted);font-size:13px;margin:4px 0}
ul.rownotes{font-size:11.5px;color:var(--muted);margin:8px 0 0;padding-left:18px}
.foot{font-size:12px;color:var(--muted)}.foot li{margin:2px 0}
.summary ul{margin:0;padding-left:20px}.summary li{margin:4px 0;font-size:14px}
@media (max-width:640px){header h1{font-size:18px}.cbox{height:220px}section{padding:12px}}
"""

CHART_JS = """
const SPECS = %s; const PAL = %s;
function fmtLbl(s){return s.length===10? s.slice(2).replace(/-/g,'.') : s}
for (const sp of SPECS){
  const el=document.getElementById(sp.id); if(!el) continue;
  const labels=[...new Set(sp.series.flatMap(s=>s.points.map(p=>p[0])))].sort();
  const ds=sp.series.map((s,i)=>{const m=new Map(s.points); return {label:s.name, data:labels.map(l=>m.has(l)?m.get(l):null),
    borderColor:PAL[i%%PAL.length], backgroundColor:sp.type==='bar'?PAL[i%%PAL.length]+'cc':PAL[i%%PAL.length],
    borderWidth:sp.type==='bar'?0:1.6, pointRadius:0, spanGaps:true, tension:0}});
  new Chart(el,{type:sp.type,data:{labels:labels.map(fmtLbl),datasets:ds},options:{responsive:true,maintainAspectRatio:false,
    interaction:{mode:'index',intersect:false},plugins:{legend:{display:ds.length>1,position:'top',labels:{boxWidth:12,font:{size:11}}},
    tooltip:{callbacks:{label:c=>`${c.dataset.label}: ${c.parsed.y==null?'-':c.parsed.y.toLocaleString()}`}}},
    scales:{x:{ticks:{maxTicksLimit:12,autoSkip:true,font:{size:10}},grid:{display:false}},y:{ticks:{font:{size:10}},grace:'5%%'}}}});
}
fetch('dates.json').then(r=>r.json()).then(ds=>{const sel=document.getElementById('datesel'); if(!sel) return;
  ds.forEach(x=>{const o=document.createElement('option');o.value=x;o.textContent=x.replace(/-/g,'.');if(x===CUR)o.selected=true;sel.appendChild(o)});
  sel.onchange=()=>location.href=sel.value+'.html';
  const i=ds.indexOf(CUR); const pv=document.getElementById('prev'), nx=document.getElementById('next');
  if(i>=0&&i<ds.length-1){pv.href=ds[i+1]+'.html'}else{pv.style.visibility='hidden'}
  if(i>0){nx.href=ds[i-1]+'.html'}else{nx.style.visibility='hidden'}}).catch(()=>{});
"""


def build_day(cfg, d, brief):
    cols, secs = build_rows(cfg, d, brief)
    dot = d.strftime("%Y.%m.%d")
    title = f"{SITE_TITLE}({dot})"
    body, specs, ci = [], [], 0
    email = []
    if brief.get("summary"):
        lis = "".join(f"<li>{esc(x)}</li>" for x in brief["summary"])
        body.append(f'<section class="summary"><h2>핵심 요약</h2><ul>{lis}</ul></section>')
    for sec in secs:
        body.append(f'<section id="{sec["cfg"]["id"]}"><h2>{esc(sec["cfg"]["title"])}</h2>')
        email.append(f'<h2 style="font-size:16px;color:#1f4e79;margin:22px 0 8px">{esc(sec["cfg"]["title"])}</h2>')
        for part in sec["parts"]:
            if part["cfg"]["title"]:
                body.append(f'<h3>{esc(part["cfg"]["title"])}</h3>')
                email.append(f'<h3 style="font-size:14px;margin:14px 0 6px">{esc(part["cfg"]["title"])}</h3>')
            body.append(f'<div class="tscroll">{table_html(cols, part)}</div>{notes_html(part)}')
            email.append(table_html(cols, part, inline=True))
            ch, sp, ci = charts_html(part, sec["cfg"]["id"], ci)
            specs += sp
            body.append(f'<div class="charts">{ch}</div>')
        body.append("</section>")
    news = brief.get("news", [])
    body.append(f'<section id="news"><h2>4. 주요 동향</h2><div class="tscroll">{news_html(news)}</div></section>')
    email.append(f'<h2 style="font-size:16px;color:#1f4e79;margin:22px 0 8px">4. 주요 동향</h2>{news_html(news, inline=True)}')
    srcs = brief.get("sources", [])
    src_html = "".join(f'<li>{esc(x["name"])}' + (f' — <a href="{esc(x["url"])}" target="_blank" rel="noopener">{esc(x["url"])}</a>' if x.get("url") else "") + "</li>" for x in srcs)
    basis = brief.get("basis") or "각 일자 열은 해당일 한국시간 07:30 기준 최신 확정치(미국 지표: 직전 뉴욕 마감, 국내 지표: 직전 서울 마감). 기간 열은 기간 내 관측치 단순평균. 일별 데이터가 없는 지표는 최신 발표치를 반영하고 일별 열은 「확인 제한」으로 표기."
    body.append(f'<section class="foot"><h2>작성 기준 및 출처</h2><p>{esc(basis)}</p><ul>{src_html}</ul></section>')

    page = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;600;700&display=swap" rel="stylesheet">
<style>{PAGE_CSS}</style></head><body>
<header><div class="wrap"><div><h1>{esc(title)}</h1><div class="basis">발행 {esc(d.isoformat())} 07:30 KST · <a href="index.html" style="color:#fff">전체 일자 목록</a></div></div>
<nav class="dates"><a id="prev" href="#">◀ 이전</a><select id="datesel" aria-label="일자 선택"></select><a id="next" href="#">다음 ▶</a></nav></div></header>
<main class="wrap">{''.join(body)}</main>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<script>const CUR="{d.isoformat()}";{CHART_JS % (json.dumps(specs, ensure_ascii=False), json.dumps(PALETTE))}</script>
</body></html>"""
    return page, title, "".join(email)


def email_html(title, inner, url, summary):
    summ = "".join(f"<li>{esc(x)}</li>" for x in summary)
    summ_html = f'<div style="background:#eef3f8;border-left:4px solid #1f4e79;padding:10px 14px;margin:12px 0"><b>핵심 요약</b><ul style="margin:6px 0 0;padding-left:18px">{summ}</ul></div>' if summary else ""
    return f"""<div style="font-family:'Malgun Gothic',Arial,sans-serif;color:#1d2733;max-width:1100px">
<h1 style="font-size:20px;color:#1f4e79;margin:0 0 4px">{esc(title)}</h1>
<p style="font-size:12px;color:#5b6876;margin:0">그래프·전체 화면: <a href="{esc(url)}">{esc(url)}</a></p>
{summ_html}{inner}
<p style="font-size:11px;color:#5b6876;margin-top:18px">각 일자 열은 발행일 07:30 KST 기준 최신 확정치. 「확인 제한」은 해당 주기 데이터 미발표 또는 미확보.</p></div>"""


def build_index(dates):
    items = []
    cur_m = None
    for d in dates:
        dd = dt.date.fromisoformat(d)
        m = f"{dd.year}년 {dd.month}월"
        if m != cur_m:
            if cur_m:
                items.append("</ul>")
            items.append(f"<h3>{m}</h3><ul class='dl'>")
            cur_m = m
        wd = "월화수목금토일"[dd.weekday()]
        items.append(f'<li><a href="{d}.html">{SITE_TITLE}({dd.strftime("%Y.%m.%d")})</a> <span class="unit">({wd})</span></li>')
    if cur_m:
        items.append("</ul>")
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{SITE_TITLE}</title><link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;600;700&display=swap" rel="stylesheet">
<style>{PAGE_CSS} ul.dl{{list-style:none;padding:0;margin:0}} ul.dl li{{padding:9px 4px;border-bottom:1px solid var(--line)}} ul.dl a{{color:var(--head);font-weight:600;text-decoration:none}}</style></head>
<body><header><div class="wrap"><div><h1>{SITE_TITLE}</h1><div class="basis">일자를 누르면 해당 일자 브리핑이 열립니다 · 매 영업일 07:30 KST 발행</div></div></div></header>
<main class="wrap"><section>{''.join(items) or '<p>발행된 브리핑 없음</p>'}</section></main></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="특정 일자만 생성(YYYY-MM-DD)")
    ap.add_argument("--force", action="store_true", help="이미 생성된 일자도 재생성")
    ap.add_argument("--base-url", default=os.environ.get("SITE_URL", ""))
    a = ap.parse_args()
    cfg = json.load(open(CFG, encoding="utf-8"))
    os.makedirs(os.path.join(DOCS, "email"), exist_ok=True)
    dates = sorted(f[:-5] for f in os.listdir(BRIEF_DIR) if f.endswith(".json"))
    built = []
    for ds in dates:
        if a.date and ds != a.date:
            continue
        out = os.path.join(DOCS, f"{ds}.html")
        if os.path.exists(out) and not a.force and not a.date:
            continue
        brief = json.load(open(os.path.join(BRIEF_DIR, f"{ds}.json"), encoding="utf-8"))
        d = dt.date.fromisoformat(ds)
        page, title, inner = build_day(cfg, d, brief)
        open(out, "w", encoding="utf-8").write(page)
        url = (a.base_url.rstrip("/") + f"/{ds}.html") if a.base_url else f"{ds}.html"
        open(os.path.join(DOCS, "email", f"{ds}.html"), "w", encoding="utf-8").write(
            email_html(title, inner, url, brief.get("summary", [])))
        built.append(ds)
    pub = sorted((f[:-5] for f in os.listdir(DOCS) if f[:4].isdigit() and f.endswith(".html")), reverse=True)
    json.dump(pub, open(os.path.join(DOCS, "dates.json"), "w"), ensure_ascii=False)
    open(os.path.join(DOCS, "index.html"), "w", encoding="utf-8").write(build_index(pub))
    open(os.path.join(DOCS, ".nojekyll"), "w").close()
    print("built:", built or "(none)", "| published dates:", len(pub))


if __name__ == "__main__":
    sys.exit(main())
