# 일일 작성 절차 (평일 07:30 KST 예약 작업용)

발행일 D(오늘, 한국시간). 07:00에 GitHub Actions가 일별 시계열(`data/series`)을 먼저 갱신해 둔 상태에서 시작.

## 1. 준비
1. 저장소 최신화(`git pull`). `data/series/_fetch_log.json`에서 수집 실패 시계열 확인.
2. 직전 영업일 브리핑 `data/briefings/<D-1>.json`을 복사해 `data/briefings/<D>.json` 초안으로 사용(값은 모두 새로 확인).

## 2. 수치 조사 (WebSearch, 추정 금지)
- 기준: 각 일자 열은 D 07:30 시점 최신 확정치 → 「D」 열 = 직전 영업일 마감, 「D-1」 열 = 그 전 영업일 마감.
- 자동 수집 시계열(미국 10년물·WTI·Brent·원/달러·SHFE 철근/열연·DCE 철광석/원료탄·KOMIS 철광석/제철용탄)은 수집 성공 시 수기 입력 불필요. 실패 시에만 동일 기준 값을 `values`에 입력.
- 원/달러는 서울 15:30 종가(ECOS 731Y003) 기준으로 `values.usdkrw` 입력(자동 수집값은 Yahoo 기준이라 수기값 우선).
- 미국 10년물은 미 재무부 Par Yield(=FRED DGS10) 기준.
- 중국 철근 현물(상하이 HRB400 20mm), 열연 현물(西本 steelx2), 국가통계국 순별 가격, 중국 철근·열연 주간 재고(목·금 발표), HMS 80:20 CFR 튀르키예, 일본 H2 입찰가를 갱신.
- 월간·연간 통계(worldsteel 조강, 중국 해관 수입, 관세청 HS7204 수입 등)는 신규 발표가 있을 때만 갱신하고, 막대그래프용 `data/monthly/<key>.csv`에도 행 추가.
- 확인 불가 값은 비우거나 "확인 제한". 계산값은 `note`에 산식, 출처는 `src`에 기재.

## 3. 주요 동향
- 대상: worldsteel, IEA, steelx2.com, KOMIS, 스틸데일리, 한국철강자원협회, 한국철강협회, 철강금속신문(+매크로는 연합뉴스·Reuters 보완).
- 직전 영업일~D 기사 10~15건: 매크로 3, 철강 4, 철광석·제철용탄·철스크랩 각 2 내외.
- 실제 확인한 URL만 사용. 요약은 3~5줄, 자체 문장, 명사형 어미(~함, ~됨, ~전망).

## 4. 핵심 요약 3줄
① 매크로 ② 철강 ③ 원료. 명사형 어미.

## 5. 생성·게시
```
python scripts/build.py --date <D> --base-url https://<owner>.github.io/<repo>
git add data docs && git commit -m "briefing: <D>" && git push
```
게시 후 `https://<owner>.github.io/<repo>/<D>.html` 응답(200)과 표·뉴스 표시 확인.

## 6. 메일 발송
- 수신: hsko@simpac.com, Outlook(Microsoft 365) 발송, bodyType html.
- 제목: `Daily Steel & Macro Briefing(YYYY.MM.DD)`
- 본문: `docs/email/<D>.html` 내용(표 + 주요 동향 + 페이지 링크).
- 휴일·발송 실패 시 사유를 기록하고 다음 실행에서 이어서 처리.
