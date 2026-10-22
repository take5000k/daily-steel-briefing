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
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SER_DIR = os.path.join(ROOT, "data", "series")
UA = {"User-Agent": "Mozilla/5.0 (daily-steel-briefing)"}


def http_get(url, data=None, headers=None, timeout=40):
    req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def src_fred(s, start):
    raw = http_get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={s['id']}&cosd={start}").decode()
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


SOURCES = {"fred": src_fred, "yahoo": src_yahoo, "akshare_main": src_akshare_main}


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
    json.dump(log, open(os.path.join(SER_DIR, "_fetch_log.json"), "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
