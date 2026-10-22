# Daily Steel & Macro Briefing

매 영업일 07:30(KST) 발행하는 매크로·철강·원료 데일리 브리핑. GitHub Pages에서 일자별로 열람.

- 목록: `https://<owner>.github.io/<repo>/` → 일자 클릭 시 해당 일자 브리핑
- 각 브리핑: 1. 매크로 / 2. 철강 지표 / 3. 원료 지표(철광석·제철용탄·철스크랩) / 4. 주요 동향
- 표 열: 전년, 상반기, 직전 분기, 전월, 당월(MTD), 상순(1~10), 중순(11~20), 전일, 당일, 전일대비

## 구조

| 경로 | 내용 | 갱신 주체 |
|---|---|---|
| `config/indicators.json` | 섹션·블록·행 구성(가격 블록 최상단) | 수동 |
| `config/series.json` | 일별 시계열 자동 수집 소스 | 수동 |
| `data/series/*.csv` | 일별 시계열(금리·유가·환율·중국 철근/열연 등) | GitHub Actions(평일 07:00 KST) |
| `data/monthly/*.csv` | 월·주·연 시계열(생산·판매·재고·수출입) — 막대그래프 | Claude 일일 작업 |
| `data/briefings/YYYY-MM-DD.json` | 일자별 수기값·핵심 요약·주요 동향·출처 | Claude 일일 작업 |
| `scripts/fetch_series.py` | 시계열 수집 | — |
| `scripts/build.py` | 페이지 생성(표준 라이브러리만 사용) | — |
| `docs/` | GitHub Pages 루트(일자별 HTML, index, 메일 본문) | build.py |

## 작성 기준

- 일자 열(전일·당일)은 발행일 07:30 KST 기준 최신 확정치(미국 지표: 직전 뉴욕 마감, 국내: 직전 서울 마감).
- 기간 열은 기간 내 관측치 단순평균. 일별 데이터가 없는 지표는 최신 발표치 반영, 일별 열은 「확인 제한」.
- 추정 금지. 확인 불가 값은 「확인 제한」, 불가피한 계산값은 비고에 산식 명기.
- 한 번 발행된 일자 페이지는 고정(재생성은 Actions의 `rebuild_date` 입력으로만).

## 수기 입력 형식 (`data/briefings/YYYY-MM-DD.json`)

```json
{
  "summary": ["핵심 요약 1", "핵심 요약 2", "핵심 요약 3"],
  "values": {"cs_world": {"y": 1849.0, "pm": "(8월) 150.2", "note": "worldsteel 2026.9 발표", "src": "worldsteel"}},
  "news": [{"category": "철강", "media": "스틸데일리", "title": "...", "url": "https://...", "date": "2026-10-21", "summary": ["...", "..."]}],
  "sources": [{"name": "worldsteel", "url": "https://worldsteel.org"}]
}
```
값 키: `y`(전년) `h`(상반기) `q`(분기) `pm`(전월) `mtd` `p1` `p2` `d1`(전일) `d0`(당일) `chg`(전일대비). 수기값이 자동 계산값보다 우선.
