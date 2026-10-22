#!/usr/bin/env python3
"""일별 시계열 수집 (GitHub Actions에서 실행). config/series.json 기준.

각 시계열은 data/series/<key>.csv (date,value)로 저장되며, 새로 받은 값으로 병합 갱신.
수집에 실패한 시계열은 기존 파일을 그대로 두고 data/series/_fetch_log.json에 기록.
"""
import csv
import datetime as dt
import io
import json
import os
import traceback
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SER_DIR = os.path.join(ROOT, "data", "series")
UA = {"User-Agent": "Mozilla/5.0 (daily-steel-briefing)"}


def http_get(url, data=None, headers=None, timeout=40):
    req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def src_fred(s, start):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={s['id']}&cosd={start}"
    raw = None
    for _ in range(3):
        try:
            raw = http_get(url, timeout=90).decode()
            break
        except Exception:  # noqa: BLE001
            continue
    if raw is None:
        raise TimeoutError("FRED 3회 시도 실패")
    out = {}
    for r in csv.reader(io.StringIO(raw)):
        if len(r) < 2 or r[0] in ("DATE", "observation_date"):
            continue
        try:
            out[r[0]] = float(r[1])
        except ValueError:
            pass
    return out


def src_yahoo(s, start):
    import yfinance as yf
    df = yf.download(s["ticker"], start=start, progress=False, auto_adjust=False)
    if df is None or df.empty:
        return {}
    close = df["Close"]
    if hasattr(close, "columns"):
        close = close.iloc[:, 0]
    out = {d.strftime("%Y-%m-%d"): float(v) for d, v in close.dropna().items()}
    if s["ticker"] == "^TNX" and out and max(out.values()) > 20:  # 과거 ^TNX는 x10 표기
        out = {k: v / 10 for k, v in out.items()}
    return out


def src_akshare_main(s, start):
    import akshare as ak
    df = ak.futures_main_sina(symbol=s["symbol"], start_date=start.replace("-", ""),
                              end_date=dt.date.today().strftime("%Y%m%d"))
    dcol = [c for c in df.columns if "日期" in c or c.lower() == "date"][0]
    ccol = [c for c in df.columns if "收盘" in c or c.lower() == "close"][0]
    return {str(r[dcol])[:10]: float(r[ccol]) for _, r in df.iterrows()}


KOMIS = "https://www.komis.or.kr"
KOMIS_PAGE = {"HP001": "BaseMetals", "HP002": "MinorMetals", "HP003": "IronOre", "HP004": "EtcMnrl"}


_KB = {}


def _komis_post(grp, path, params):
    """헤드리스 브라우저로 KOMIS 페이지를 연 뒤 같은 세션에서 AJAX POST(일반 요청은 거부됨)."""
    from playwright.sync_api import sync_playwright
    if "pw" not in _KB:
        _KB["pw"] = sync_playwright().start()
        _KB["browser"] = _KB["pw"].chromium.launch()
    if _KB.get("grp") != grp:
        if _KB.get("page"):
            _KB["page"].close()
        _KB["page"] = _KB["browser"].new_page(locale="ko-KR")
        _KB["page"].goto(f"{KOMIS}/Komis/RsrcPrice/{KOMIS_PAGE[grp]}", wait_until="networkidle", timeout=90000)
        _KB["grp"] = grp
    body = urllib.parse.urlencode(params)
    txt = _KB["page"].evaluate("""async ([u, b]) => { const r = await fetch(u, {method: 'POST', body: b,
        headers: {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8', 'X-Requested-With': 'XMLHttpRequest'}});
        return r.status + '\\n' + await r.text(); }""", [KOMIS + path, body])
    status, _, text = txt.partition("\n")
    if status != "200":
        raise RuntimeError(f"KOMIS {path} HTTP {status}")
    return json.loads(text)


def komis_close():
    if _KB.get("browser"):
        _KB["browser"].close()
        _KB["pw"].stop()


KOMIS_INFO = {}


def src_komis(s, start):
    """KOMIS 자원가격(일간). s: grp(HP003 등), mnrl(광종코드), crtr(가격기준 코드, 없으면 첫 번째)."""
    post = lambda path, prm: _komis_post(s["grp"], path, prm)  # noqa: E731
    crtrs = post("/Komis/RsrcPrice/ajax/getMnrlPriceCrtr", {"HP000": s["grp"], "mnrkndUnqCd": s["mnrl"]}).get("data", [])
    pick = next((c for c in crtrs if str(c.get("cdKey")) == str(s.get("crtr"))), crtrs[0] if crtrs else None)
    if not pick:
        raise RuntimeError("가격기준 없음")
    out, info = {}, None
    y0 = int(start[:4])
    params = {"mnrkndUnqRadioCd": s["mnrl"], "srchMnrkndUnqCd": s["mnrl"], "srchPrcCrtr": pick["cdKey"],
              "srchAvgOpt": "DAY", "srchField": "year", "srchStartDate": y0,
              "srchEndDate": dt.date.today().year, "srchCompareMnrkndUnqCd": "", "srchComparePrcCrtr": "[선택]"}
    if pick.get("spcfct"):
        params["spcfct"] = pick["spcfct"]
    res = post("/Komis/RsrcPrice/ajax/getMnrlPrcByMnrkndUnqCd", params)
    info = (res.get("dataAvg") or {}).get("INFO")
    for r in (res.get("data") or {}).get("defaultMnrl", []):
        try:
            d = r["crtrYmd"]
            out[f"{d[:4]}-{d[4:6]}-{d[6:8]}"] = float(str(r["cmercPrc"]).replace(",", ""))
        except (KeyError, ValueError):
            continue
    KOMIS_INFO[s["mnrl"]] = {"crtr_options": crtrs, "picked": pick, "info": info}
    return {k: v for k, v in out.items() if k >= start}


SOURCES = {"komis": src_komis, "fred": src_fred, "yahoo": src_yahoo, "akshare_main": src_akshare_main}


def merge_write(key, new):
    path = os.path.join(SER_DIR, f"{key}.csv")
    cur = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                cur[r["date"]] = r["value"]
    for k, v in new.items():
        cur[k] = f"{v:.6g}"
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "value"])
        for k in sorted(cur):
            w.writerow([k, cur[k]])
    return len(cur)


def main():
    cfg = json.load(open(os.path.join(ROOT, "config", "series.json"), encoding="utf-8"))
    os.makedirs(SER_DIR, exist_ok=True)
    log = {"run_utc": dt.datetime.utcnow().isoformat(timespec="seconds"), "series": {}}
    for key, spec in cfg["series"].items():
        entry = {"ok": False, "tried": []}
        for s in spec["sources"]:
            tag = s["type"] + ":" + str(s.get("id") or s.get("ticker") or s.get("symbol") or "")
            try:
                data = SOURCES[s["type"]](s, cfg["start"])
                if not data:
                    raise RuntimeError("empty")
                n = merge_write(key, data)
                entry.update(ok=True, source=tag, last=max(data), rows=n)
                break
            except Exception as e:  # noqa: BLE001
                entry["tried"].append({"source": tag, "error": f"{type(e).__name__}: {e}"[:300]})
                traceback.print_exc()
        log["series"][key] = entry
        print(key, "OK " + entry.get("source", "") + " " + entry.get("last", "") if entry["ok"] else "FAILED")
    komis_close()
    log["komis"] = KOMIS_INFO
    json.dump(log, open(os.path.join(SER_DIR, "_fetch_log.json"), "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
