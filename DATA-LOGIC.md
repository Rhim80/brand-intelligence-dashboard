# Brand Intelligence Dashboard - 데이터 & 마케팅 로직 문서

> 대시보드의 모든 지표가 "어떤 데이터에서, 어떤 계산으로, 왜 이 숫자가 나왔는지" 판단할 수 있도록 정리한 문서

---

## 1. 데이터 소스 구조

| 파일 | 수집 방법 | 데이터 범위 |
|------|----------|------------|
| `search-volume.json` | 네이버 광고 API (키워드 도구) | 일룸 + 경쟁 4사, 월간 검색량 |
| `trend.json` | 네이버 데이터랩 (상대 검색량) | 24개월 월별 트렌드 + 계절성 |
| `keyword-clusters.json` | Gemini 2.0 Flash (LLM 클러스터링) | 5,183개 키워드 풀 → 5개 페르소나 |
| `consumer-journey.json` | Gemini 2.0 Flash (의도 분류) | 500개 키워드 → 3단계 여정 분류 |
| `ai-sov.json` | ChatGPT-4o + Gemini Pro 직접 질의 | 10개 질문 x 2모델 x 3회 = 60회 응답 |
| `reviews-sentiment.json` | 다나와 리뷰 크롤링 + Gemini 분석 | 일룸 리뷰 (6개월) |
| `strategy-matrix.json` | Tab 1-5 데이터 종합 + Claude 전략 제안 | 7개 전략 항목 |

---

## 2. 핵심 지표 계산식

### 2.1 Share of Search (SOS)

**의미**: 카테고리 내 브랜드 검색 점유율. 마케팅에서 SOS는 시장 점유율(Market Share)의 선행 지표로 간주됨.

```
SOS = 브랜드 월간 검색량 / 전체 5개 브랜드 검색량 합계 x 100
```

**데이터 경로**: `search-volume.json → current.brands.{브랜드}.total`

**판단 기준**:
- SOS > 30%: 시장 리더 (카테고리 대표 브랜드)
- SOS 15-30%: 주요 경쟁자
- SOS < 15%: 틈새 플레이어

**한계**: 5개 브랜드만 추적하므로 전체 시장 대비가 아닌 "추적 브랜드 군 내" 점유율. 자코모처럼 소파 전문 브랜드는 카테고리 특성이 달라 직접 비교에 한계 있음.

---

### 2.2 YoY (전년 동기 대비)

**의미**: 브랜드 검색량의 연간 성장/하락률.

```
YoY = (올해 검색량 - 작년 동월 검색량) / 작년 동월 검색량 x 100
```

**데이터 경로**: `search-volume.json → current` vs `historical[]` 중 동일 월 매칭

**판단 기준**:
- YoY > +10%: 브랜드 관심 급증 (캠페인 효과 또는 트렌드)
- YoY -5% ~ +10%: 안정적
- YoY < -5%: 관심 감소 (경쟁사 대비 약세 신호)

---

### 2.3 AI SOV (AI Share of Voice)

**의미**: AI 플랫폼(ChatGPT, Gemini)이 가구 추천 질문에 우리 브랜드를 얼마나 언급하는지.

```
AI SOV = 해당 브랜드 언급 횟수 / 전체 브랜드 언급 횟수 합계 x 100
```

**데이터 경로**: `ai-sov.json → sov_score.brands`

**세부 지표 3개**:

| 지표 | 계산식 | 의미 |
|------|--------|------|
| 언급률 (Mention Rate) | 브랜드 언급된 응답 수 / 60회 | AI가 이 브랜드를 "알고 있고 추천 후보에 넣는" 비율 |
| 1순위 추천률 (First Rec) | 첫 번째로 언급된 횟수 / 60회 | AI가 "첫 번째로 떠올리는" 비율 (Top of Mind) |
| 문맥별 언급률 (by_context) | 특정 문맥 질문에서 언급 비율 | 어떤 카테고리에서 강한지/약한지 |

**문맥 카테고리 4개**:
- `general_recommendation`: "좋은 가구 브랜드 추천" (일반)
- `kids_furniture`: "초등학생 책상 추천" (키즈)
- `living_room`: "거실 소파 추천" (거실)
- `value_for_money`: "가성비 가구 추천" (가성비)

**판단 기준**:
- SOV > 25%: 해당 카테고리 AI 리더
- SOV 15-25%: 경쟁 위치
- SOV < 15%: AI 존재감 부족

**한계**: 60회 샘플링으로 통계적 유의성 낮음. AI 응답은 매번 다르므로 "트렌드 지표"로만 활용. 절대값보다 브랜드 간 상대 비교가 의미 있음.

---

### 2.4 감성 점수 (Sentiment Score)

**의미**: 리뷰 텍스트의 긍정/부정 비율을 종합한 점수.

```
sentiment_score = (긍정 비율 - 부정 비율) x 100
```

예: 긍정 72%, 부정 8% → score = (0.72 - 0.08) x 100 = 64

**데이터 경로**: `reviews-sentiment.json → overall.sentiment_score`

**토픽별 분석** (`by_topic`): 디자인, 품질, 가격, 배송/설치, 기능성, AS 등 주제별로 긍정/부정/중립 비율 분리.

**판단 기준**:
- Score > 50: 전반적 긍정 (건강한 브랜드)
- Score 30-50: 혼재 (특정 토픽에 이슈)
- Score < 30: 부정 우세 (긴급 대응 필요)

**제품별 분석** (`by_product`): 개별 제품의 리뷰 수, 평균 별점, 감성 점수를 비교하여 "어떤 제품이 문제인지" 특정.

---

### 2.5 계절성 지수 (Seasonality Index)

**의미**: 월별 검색량이 연평균 대비 얼마나 높은지/낮은지.

```
계절성 지수 = 해당 월 검색량 / 12개월 평균 검색량 x 100
```

**데이터 경로**: `trend.json → seasonality.{브랜드}.{월}`

**판단 기준**:
- 지수 > 110: 성수기 (시즌 마케팅 집중 구간)
- 지수 92-110: 평균 수준
- 지수 < 92: 비수기 (프로모션/가격 전략 필요)

---

## 3. 자동 계산 함수 (Tier 1)

대시보드가 JSON 로드 후 실시간으로 계산하는 5개 함수. 데이터 파일에는 원본만 저장하고, 파생 지표는 브라우저에서 계산.

### 3.1 `computeBrandProfile(brandName)`

**목적**: 각 브랜드의 강점 + 포지셔닝을 자동 요약

**로직**:
1. `ai-sov.by_context`에서 해당 브랜드의 최고 언급률 문맥을 찾음
2. `search-volume`에서 검색량 순위 계산
3. `trend.monthly` 최근 3개월 vs 이전 3개월 평균 비교 → 상승/하락/안정 판단
4. `sov_score`로 포지셔닝 등급 결정

**트렌드 판단 기준**:
```
변화율 = (최근 3개월 평균 - 이전 3개월 평균) / 이전 3개월 평균 x 100
> +5%: 상승세 / < -5%: 하락세 / 그 외: 안정적
```

**포지셔닝 등급**:
```
SOV > 25%: 시장 리더 / SOV > 15%: 주요 경쟁자 / SOV <= 15%: 틈새 플레이어
```

**사용처**: Market 탭 - 경쟁사 포지셔닝 비교 테이블의 "강점", "포지셔닝" 컬럼

---

### 3.2 `computeOverviewInsights()`

**목적**: Strength / Weakness / Opportunity 인사이트 카드 자동 생성

**Strength 로직**:
1. `ai-sov.by_context`에서 자사 브랜드가 1위인 문맥이 있는지 확인
2. 있으면 → "해당 문맥 리더십" + keyword-clusters에서 관련 클러스터 검색량 보강
3. 없으면 → `reviews-sentiment.by_topic`에서 긍정률 가장 높은 토픽 사용

**Weakness 로직**:
- SOS 순위 + 1위 대비 격차 (%p)
- AI 언급률 순위

**Opportunity 로직**:
- `keyword-clusters`에서 가장 큰 클러스터(신혼/키즈 제외) 중 미개척 시장 추출

**사용처**: Overview 탭 - KPI 카드 아래 3열 인사이트 카드

---

### 3.3 `computePathExamples()`

**목적**: 소비자 검색 경로 시각화 (이탈 경로 + 유입 경로)

**이탈 경로 로직**:
1. `consumer-journey.stages.consideration.exit_signals.competitors`에서 경쟁사별 이탈 데이터 추출
2. 각 경쟁사의 sample 키워드에서 구체적 검색어 추출
3. "일룸 {카테고리} → {경쟁사 제품}" 형태의 경로 생성

**유입 경로 로직**:
1. awareness 단계의 일반 키워드(브랜드명 미포함)를 출발점으로
2. consideration 단계의 자사 브랜드 키워드를 도착점으로
3. "침대 → 일룸책상" 형태의 경로 생성

**사용처**: Consumer Journey 탭 - 검색 경로 예시 섹션

---

### 3.4 `computeActionPlan()`

**목적**: AI SOV 갭 분석 기반 3단계 액션 플랜 자동 생성

**로직**:
1. `ai-sov.by_context`의 4개 문맥 각각에서:
   - 자사 브랜드 언급률 vs 1위 브랜드 언급률의 갭(차이) 계산
2. 갭이 큰 순서대로 정렬 (가장 열위인 문맥부터)
3. 상위 3개를 액션 아이템으로 변환

**우선순위 기준**:
```
갭 > 30%p: high / 갭 <= 30%p: medium
```

**목표 산정**:
```
목표 언급률 = 현재 언급률 + (갭 x 50%) (단, 1위 언급률 초과 불가)
```

**사용처**: AI 분석 탭 - "AI 대응 3단계 액션 플랜"

---

### 3.5 `computeSeasonalityInsights()`

**목적**: 계절성 데이터에서 Strength/Weakness/Opportunity 자동 추출

**Strength 로직**: 계절성 지수 >= 110인 월 → 성수기 마케팅 타이밍
**Weakness 로직**: 계절성 지수 <= 92인 월 → 비수기 프로모션 필요
**Opportunity 로직**: 비수기(지수 <= 95) 직후에 반등(지수 >= 105)하는 구간 → 마케팅 투입 최적 시점

**사용처**: Market 탭 - 계절성 인사이트 카드

---

## 4. 탭별 마케팅 로직 해설

### Tab 0: Overview

**핵심 질문**: "우리 브랜드의 현재 위치는?"

| 지표 | 보는 법 |
|------|---------|
| SOS | 높을수록 좋음. 1위 대비 격차가 줄고 있으면 긍정 신호 |
| 월간 검색량 | 절대 규모. YoY와 함께 봐야 의미 있음 |
| 시장 순위 | 5개 브랜드 중 위치. 3위 이하면 인지도 개선 필요 |
| 감성 점수 | 리뷰 건강도. 50 이상이면 양호, 30 이하면 위기 |
| Strength/Weakness/Opportunity | 다른 탭 데이터를 교차 분석한 자동 요약 |

---

### Tab 1: 시장분석

**핵심 질문**: "시장이 어떻게 변하고 있고, 경쟁사 대비 우리 위치는?"

- **24개월 트렌드**: 상대 검색량이므로 "기울기"가 중요. 우상향이면 관심 증가
- **계절성 패턴**: 매년 반복되는 검색량 패턴. 마케팅 예산 배분의 근거
- **경쟁사 포지셔닝 테이블**: SOS + YoY + AI 강점 + 포지셔닝을 한눈에 비교
- **연도별 추이**: 장기적 SOS 변화 추적

**마케팅 판단 포인트**:
- 계절성 지수 110+ 월의 2-3주 전에 캠페인 시작
- 비수기(지수 92-)에는 가격 프로모션으로 기저 수요 확보
- 경쟁사 중 YoY 급등하는 브랜드 = 경계 대상

---

### Tab 2: 소비자 여정

**핵심 질문**: "소비자가 어디서 이탈하고, 경쟁사로 넘어가는가?"

**3단계 퍼널**:
```
인지 (카테고리 검색) → 비교 (브랜드 검색) → 구매 (가격/매장 검색)
```

- **인지 → 비교 전환율**: 카테고리 검색자 중 브랜드 검색으로 넘어오는 비율
- **비교 → 구매 전환율**: 극히 낮음 (2%). 온라인 구매 검색 자체가 적은 카테고리 특성
- **추정 이탈 방향**: 비교 단계에서 경쟁사 키워드가 함께 검색되는 빈도로 추정

**한계**: GA(Google Analytics) 없이 실제 이탈률 측정 불가. 키워드 동시 검색 빈도 기반 "추정 이탈 경향"임.

**마케팅 판단 포인트**:
- 이탈 1위 경쟁사에 대한 비교 콘텐츠 제작 우선
- 유입 경로상 일반 키워드 → 브랜드 키워드 연결 SEO 강화

---

### Tab 3: 키워드 클러스터

**핵심 질문**: "어떤 소비자 유형이 있고, 각각 뭘 원하는가?"

5개 페르소나 클러스터 (LLM 기반 분류):

| 클러스터 | 검색량 점유 | 일룸 관련도 |
|----------|-----------|------------|
| 신혼부부 | 44% (최대) | 간접 (이케아/한샘이 주도) |
| 이사/리모델링 | 18% | 낮음 (한샘/리바트 주도) |
| 1인 가구 | 14% | 낮음 (가격 민감) |
| 키즈맘/키즈대디 | 13% | **높음** (일룸 직접 검색 포함) |
| 직장인 | 11% | 중간 (모션데스크 기회) |

**마케팅 판단 포인트**:
- 키즈맘 클러스터 = 일룸의 홈그라운드. 여기서 리더십 유지가 최우선
- 신혼부부 44%가 최대 시장이나 이케아/한샘이 장악 → 진입 난이도 높음
- 직장인 클러스터의 모션데스크 = 성장 기회 (데스커 대비 차별화 가능)

---

### Tab 4: AI 분석 + 리뷰

**핵심 질문**: "AI가 우리를 어떻게 인식하고, 고객은 뭐에 만족/불만인가?"

**AI SOV 분석**:
- 한샘이 AI에서 압도적 1위 (SOV 35.4%). 언급률 77%
- 일룸은 까사미아와 동률 3위 (SOV 20.0%). 언급률 43%
- 키즈 가구 문맥에서만 일룸이 한샘과 공동 1위 (50%)
- 가성비 문맥에서 일룸 최하위 (17%) vs 이케아/한샘 100%

**리뷰 감성 분석**:
- 토픽별 긍정/부정/중립 비율 시각화
- 부정 감성 높은 토픽 = 개선 우선순위
- 월별 감성 추이 = 개선 시책의 효과 모니터링

**마케팅 판단 포인트**:
- AI SOV 격차 = 구조화 데이터(위키, 브랜드 페이지) 최적화 시급
- 리뷰 부정 토픽 = 운영 개선 우선순위 (배송/설치, 가격 등)
- 문맥별 갭이 큰 곳 = 콘텐츠 마케팅으로 AI 학습 데이터 투입

---

### Tab 5: 전략 매트릭스

**핵심 질문**: "뭘 먼저 해야 하는가?"

**매트릭스 축**:
- Y축 (Impact): 검색량 규모 x SOS 갭 x 감성 데이터로 영향도 산정
- X축 (Feasibility): 실행 난이도 수동 평가 (리소스, 기간, 복잡도)

**우선순위 등급**:
```
Critical: Impact 높음 + Feasibility 높음 → 지금 당장 실행
High: Impact 높음 + Feasibility 보통 → 단기 계획 수립
Medium: Impact 보통 → 중기 로드맵에 편성
```

**각 전략 항목의 data_basis 필드**: 해당 전략이 "어떤 데이터에서 도출되었는지" 근거 명시

---

## 5. 데이터 간 교차 참조 관계

```
search-volume ──┬── Overview: SOS, 순위, YoY
                ├── Market: 경쟁사 비교, 연도별 추이
                └── computeBrandProfile(): 검색량 순위

trend ──────────┬── Market: 24개월 트렌드 차트
                ├── computeBrandProfile(): 트렌드 방향
                └── computeSeasonalityInsights(): 계절성

keyword-clusters ┬── Clusters 탭: 페르소나별 시각화
                 └── computeOverviewInsights(): 기회 클러스터

consumer-journey ┬── Journey 탭: 퍼널 + 이탈 방향
                 └── computePathExamples(): 검색 경로

ai-sov ─────────┬── AI 탭: SOV, 언급률, 1순위, 문맥별
                ├── computeBrandProfile(): AI 강점 문맥
                ├── computeOverviewInsights(): Strength/Weakness
                └── computeActionPlan(): 갭 기반 액션

reviews-sentiment┬── AI 탭: 토픽 감성, 제품별 분석, 월별 추이
                 └── computeOverviewInsights(): 리뷰 기반 Strength

strategy-matrix ─── Strategy 탭: 우선순위 매트릭스 + 액션 카드
```

---

## 6. 주의사항 및 한계

### 데이터 한계
1. **SOS는 5개 브랜드 한정**: 시디즈, 데스커, 니스툴그로우 등 카테고리별 강자가 빠져있음
2. **AI SOV 샘플 60회**: 통계적 유의성 부족. 방향성 참고만 가능
3. **소비자 여정 = 키워드 기반 추정**: 실제 클릭/구매 데이터(GA) 없음
4. **리뷰 = 다나와 한정**: 네이버, 쿠팡 등 다른 플랫폼 리뷰 미포함
5. **키워드 클러스터 = LLM 분류**: 수동 검증 필요. 같은 키워드가 다른 클러스터에 속할 수 있음

### 자동 계산 한계
1. **포지셔닝 등급**은 SOV 기준 단일 축. 실제 시장 포지셔닝은 가격대, 카테고리 전문성 등 다차원
2. **액션 플랜 목표치**(갭 x 50%)는 경험적 추정. 실제 달성 가능성은 별도 검증 필요
3. **Opportunity 추출**은 검색량 기준. 수익성, 경쟁 강도는 미반영

### 데이터 갱신 주기
- 검색량/트렌드: 월 1회 갱신 권장 (네이버 데이터 월 단위 업데이트)
- AI SOV: 분기 1회 재측정 (AI 모델 업데이트 반영)
- 리뷰 감성: 월 1회 크롤링 + 분석
- 전략 매트릭스: 분기 1회 리뷰 (데이터 변화 반영)

---

## 7. 외부 소스 기반 로직 검증

> 2026-02 기준, 마케팅 업계 표준/연구와 대시보드 로직을 대조한 결과

### 7.1 Share of Search (SOS) - 업계 표준 부합

**근거**: Les Binet(IPA)의 연구에서 SOS와 시장 점유율 간 평균 83% 상관관계 확인. 자동차(9-12개월), 에너지(0-3개월), 모바일(6개월) 등 카테고리별로 SOS가 시장 점유율의 선행 지표 역할.

**대시보드 적합성**:
- 계산식 `브랜드 검색량 / 전체 검색량 x 100` → 업계 표준과 동일
- 5개 브랜드만 추적하는 점은 한계. 업계에서도 "추적 브랜드 선정 바이어스"가 SOS의 주요 한계로 지적됨
- 브랜드명이 일반 명사가 아닌 고유 브랜드(일룸, 이케아 등)이므로 검색 오염 리스크 낮음

**Sources**:
- [WARC: Share of search can predict market share](https://www.warc.com/newsandopinion/news/share-of-search-can-predict-market-share/en-gb/44232)
- [Marketing Week: Share of search represents 83% of market share](https://www.marketingweek.com/share-of-search-market-share/)
- [LBBOnline: Les Binet 10 key Findings](https://lbbonline.com/news/les-binet-unveils-share-of-search-metric-with-10-key-findings)
- [Robert af Klintberg Ryberg: SOS limitations](https://medium.com/@robert_ryberg/share-of-search-is-not-always-the-saviour-many-brands-hope-for-7ed706cbd183)

---

### 7.2 AI SOV - 방법론 적절, 샘플 사이즈 경계선

**근거**: AI SOV는 2025-2026 마케팅 업계의 신규 핵심 KPI로 부상. HubSpot, Superlines, GAIO Tech 등이 측정 도구를 출시. 계산 공식은 `브랜드 언급 / 전체 브랜드 언급 x 100`이 업계 표준.

**샘플 사이즈**: Passionfruit Research에 따르면 프롬프트당 60-100회 실행이 통계적으로 의미 있는 최소치. 60회 미만은 "random noise"이며, 100회에서 안정적 수치 도출. 대시보드의 60회는 하한선에 해당.

**대시보드 적합성**:
- 계산식 → 업계 표준과 동일
- 문맥별 분류 (general, kids, living, value) → 업계 best practice인 "query selection by context"와 부합
- 10개 질문 x 2 모델 x 3회 = 60회 → 최소 권장치 하한. 100회로 증가 권장
- Perplexity, Claude 등 플랫폼 추가 시 신뢰도 향상

**Sources**:
- [GAIO Tech: AI Share of Voice measurement guide](https://gaiotech.ai/blog/ai-share-of-voice-ai-sov-how-to-measure-your-brand-s-presence-in-ai-search)
- [Superlines: AI SoV as #1 marketing KPI](https://www.superlines.io/articles/why-ai-search-share-of-voice-is-your-new-number-1-marketing-kpi)
- [Passionfruit: Why AI brand recommendations change](https://www.getpassionfruit.com/blog/why-ai-brand-recommendations-change-with-every-query-research-analysis-and-strategic-implications)
- [HubSpot: AI Share of Voice Tool](https://www.hubspot.com/aeo-grader/share-of-voice)
- [Birdeye: AI search Share of Voice](https://birdeye.com/blog/ai-share-of-voice/)

---

### 7.3 감성 점수 (Sentiment Score) - 로직 적절, NPS와 혼동 주의

**근거**: NPS(Net Promoter Score)와 유사한 net score 방식(긍정 - 부정)은 감성 분석에서 일반적으로 사용. 토픽별 분리 분석은 "find-and-fix cycle"의 핵심으로 업계에서 적극 권장.

**벤치마크 주의**: NPS 업계 평균은 B2C 16-80, B2B 37-69. 대시보드 감성 점수는 리뷰 기반이므로 NPS와 직접 비교 불가. 클라이언트 보고 시 "리뷰 감성 net score"로 명확히 구분 필요.

**대시보드 적합성**:
- `(긍정 - 부정) x 100` → 업계 표준 net score
- 토픽별 분리 분석 → best practice
- 감성 분석 도입 기업이 미도입 대비 NPS 70% 개선 (Amra & Elma 2025)

**Sources**:
- [Amra and Elma: Sentiment Analysis in Marketing Statistics 2025](https://www.amraandelma.com/sentiment-analysis-in-marketing-statistics/)
- [SentiSum: NPS Sentiment Analysis](https://www.sentisum.com/library/customer-sentiment-analysis-boost-nps)
- [Retently: NPS Benchmark 2025](https://www.retently.com/blog/good-net-promoter-score/)

---

### 7.4 키워드 클러스터링 (Persona) - 방법론 현대적, 2차 검증 권장

**근거**: 2025년 기준 AI/ML 기반 세그멘테이션이 전통적 K-means를 대체하는 추세. LLM 기반 클러스터링은 행동+인구통계+심리적 데이터를 혼합하는 "하이브리드 접근"의 일종.

**업계 권장 프로세스**: 2단계 검증(1차 클러스터링 → 2차 iterative refinement). Silhouette Score 등 정량 검증으로 클러스터 품질 확인.

**대시보드 적합성**:
- LLM 1회 분류 → 현대적 방법이나 2차 검증 단계 없음
- 페르소나 5개 도출 → 업계 권장 "meaningful, measurable, accessible, actionable" 기준 부합
- 각 클러스터에 needs, pain_points, marketing_strategy 포함 → 실행 가능한 세그먼트 설계

**Sources**:
- [iPullRank: Segmentation Methods to Build Personas](https://ipullrank.com/resources/guides-ebooks/personas-guide/chapter-4)
- [MarketingCourse.org: Advanced Customer Segmentation 2025](https://marketingcourse.org/advanced-customer-segmentation-how-data-is-defining-personas-in-2025/)
- [Ziggy Agency: Cluster Analysis for Personas and Keywords](https://ziggy.agency/resource/cluster-analysis-personas-keywords/)

---

### 7.5 소비자 여정 (Keyword Intent) - 프레임워크 표준

**근거**: Awareness → Consideration → Conversion 3단계는 HubSpot, Ahrefs, Neil Patel 등 업계 표준 buyer's journey 프레임워크. 키워드 의도(intent modifiers) 기반 분류도 SEO 업계 best practice.

**대시보드 적합성**:
- 3단계 퍼널 분류 → 업계 표준
- 키워드 의도 기반 분류 → 표준 방법론
- 이탈 경로 추정(키워드 동시 검색 패턴) → 업계 표준에는 없는 독자적 접근이나, GA 없는 환경에서의 합리적 대안
- "GA 없이 실제 이탈률 측정 불가" 한계 명시 → 적절한 판단

**Sources**:
- [HubSpot: Buyer Journey Keyword Research](https://blog.hubspot.com/marketing/buyer-journey-keywords)
- [GrowByData: The Keyword Funnel](https://growbydata.com/what-is-keyword-funnel/)
- [Neil Patel: Keywords for Each Funnel Stage](https://neilpatel.com/blog/keywords-to-use-for-awareness-consideration-decision/)

---

### 7.6 계절성 지수 - 업계 표준 완전 부합

**근거**: Seasonal decomposition(시계열 분해)은 마케팅 예산 배분의 표준 방법론. 월별 검색량 / 연평균으로 지수화하는 방식은 Google Trends, SEOClarity 등이 동일하게 사용.

**대시보드 적합성**:
- `해당 월 / 12개월 평균 x 100` → 표준 계절성 지수
- 성수기(110+) / 비수기(92-) 구분 → 합리적 임계값
- 마케팅 예산 배분 근거로 활용 → 업계 권장과 정확히 일치

**Sources**:
- [Chapters: Search Seasonality Guide 2026](https://chapters-eg.com/blog/digital-marketing/search-seasonality-guide/)
- [SEOClarity: Seasonality Matters for SEO](https://www.seoclarity.net/blog/seasonality-matters-seo-projections-14403/)
- [Karola Karlson: Seasonal Marketing Budget Planning](https://karolakarlson.com/seasonal-marketing-budget-planning/)

---

### 7.7 종합 평가

| 로직 | 업계 적합도 | 현 상태 | 개선 포인트 |
|------|-----------|---------|------------|
| SOS | 표준 | 적합 | 추적 브랜드 확대 고려 |
| AI SOV | 표준 (신규 KPI) | 최소치 | 샘플 60→100회, 플랫폼 추가 |
| 감성 점수 | 적절 | 적합 | NPS와 혼동 방지 표기 |
| 키워드 클러스터 | 현대적 | 적합 | 2차 검증 단계 추가 |
| 소비자 여정 | 표준 | 적합 | GA 연동 시 정확도 대폭 향상 |
| 계절성 지수 | 표준 | 적합 | 현행 유지 |

---

## 8. GA 연동 로드맵

> 소비자 여정의 "추정 이탈"을 "실측 이탈"로 전환하기 위한 Google Analytics 연동 계획

### 현재 한계
- 키워드 동시 검색 빈도 기반 "추정 이탈 경향"만 가능
- 실제 사이트 방문 → 이탈 → 경쟁사 이동 경로 추적 불가
- 전환율(구매/장바구니/상담신청) 데이터 없음

### GA4 연동 시 추가 가능한 지표

| 지표 | GA4 소스 | 대시보드 반영 위치 |
|------|---------|-----------------|
| 실제 이탈률 (Bounce Rate) | `engagement_rate` | Consumer Journey 탭 - 단계별 이탈률 |
| 유입 채널별 전환 | `session_source/medium` + `conversions` | Overview 탭 - 채널 효과 |
| 검색 키워드 → 랜딩 | `page_location` + `session_source` | Consumer Journey 탭 - 실측 경로 |
| 제품별 조회/전환 | `view_item` + `purchase` events | AI 탭 - 제품 리뷰 vs 실제 전환 비교 |
| 경쟁사 비교 페이지 체류 | `engagement_time` on comparison pages | Market 탭 - 비교 콘텐츠 효과 |

### 연동 방식 (정적 대시보드 유지)

현재 대시보드는 정적 HTML + JSON 구조이므로, GA4 실시간 연동 대신 **배치 방식** 권장:

1. **GA4 → BigQuery Export** (무료, 일 1회 자동)
2. **BigQuery → Python 스크립트** (GA 지표 추출 + JSON 변환)
3. **JSON → 대시보드 자동 반영** (기존 파이프라인과 동일)

```
GA4 → BigQuery (일 1회) → scripts/extract-ga.py → data/ga-metrics.json → index.html
```

### 우선순위
1. **Phase 1**: 일룸 공식몰 GA4 접근 권한 확보 (클라이언트 협조 필요)
2. **Phase 2**: 이탈률 + 유입 채널 데이터 추가 (Consumer Journey 정확도 향상)
3. **Phase 3**: 제품별 전환 데이터 연동 (리뷰 감성 vs 실제 매출 상관 분석)
