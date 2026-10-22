#!/usr/bin/env python3
"""KOMIS 가격 페이지를 헤드리스 브라우저로 열어
(1) 가격표를 불러오는 XHR 요청(URL·메서드·폼데이터·응답 일부)과
(2) 화면에 렌더링된 가격표·선택 가능한 광종 목록을 기록한다.
결과: data/series/_komis_probe.json  (GitHub Actions 'komis-probe' 워크플로에서 실행)
"""
import json
import os

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES = [
    "https://www.komis.or.kr/Komis/RsrcPrice/IronOre",
    "https://www.komis.or.kr/Komis/RsrcPrice/BaseMetals",
    "https://www.komis.or.kr/Komis/RsrcPrice/MinorMetals",
    "https://www.komis.or.kr/Komis/RsrcPrice/EtcMnrl",
]


def main():
    out = {"pages": []}
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(locale="ko-KR")
        for url in PAGES:
            rec = {"url": url, "xhr": [], "tables": [], "selects": {}, "error": None}
            page = ctx.new_page()

            def on_resp(resp, rec=rec):
                rq = resp.request
                if rq.resource_type in ("xhr", "fetch"):
                    try:
                        body = resp.text()[:3000]
                    except Exception:  # noqa: BLE001
                        body = None
                    rec["xhr"].append({"method": rq.method, "url": rq.url, "post": rq.post_data,
                                       "status": resp.status, "body_head": body})

            page.on("response", on_resp)
            try:
                page.goto(url, wait_until="networkidle", timeout=60000)
                page.wait_for_timeout(3000)
                rec["selects"] = page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('select')].map(s =>
                    [s.id || s.name, [...s.options].map(o => [o.value, o.textContent.trim()])]))""")
                # 검색 버튼 클릭 시도
                for sel in ["text=검색", "button:has-text('검색')", "a:has-text('검색')"]:
                    try:
                        page.click(sel, timeout=3000)
                        page.wait_for_timeout(4000)
                        break
                    except Exception:  # noqa: BLE001
                        continue
                rec["tables"] = page.evaluate("""() => [...document.querySelectorAll('table')].map(t =>
                    [...t.querySelectorAll('tr')].slice(0, 15).map(r => [...r.children].map(c => c.textContent.trim())))""")
            except Exception as e:  # noqa: BLE001
                rec["error"] = f"{type(e).__name__}: {e}"[:500]
            out["pages"].append(rec)
            page.close()
        b.close()
    path = os.path.join(ROOT, "data", "series", "_komis_probe.json")
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("saved", path, [(r["url"], len(r["xhr"]), r["error"]) for r in out["pages"]])


if __name__ == "__main__":
    main()
