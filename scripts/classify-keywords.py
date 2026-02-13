"""
Gemini API로 연관키워드 분류 파이프라인

Pipeline:
  1. related-keywords.json 로드 (9,265개)
  2. 가구/인테리어 관련 키워드 heuristic 필터링
  3. Gemini API로 의도 분류 (배치 처리)
  4. Gemini API로 페르소나 클러스터링
  5. consumer-journey.json + keyword-clusters.json 저장

사용법:
  python scripts/classify-keywords.py
  python scripts/classify-keywords.py --dry-run    # 필터링만 (API 호출 없음)
  python scripts/classify-keywords.py --top 300     # 상위 N개만 분류

필요 환경변수:
  GEMINI_API_KEY (.env 파일)
"""

import json
import os
import sys
import time
from datetime import datetime

try:
    from google import genai
except ImportError:
    print("google-genai 패키지가 필요합니다: pip install google-genai")
    sys.exit(1)

# --------------------------------------------------
# 경로 및 환경 설정
# --------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)

# .env 로드
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(PROJECT_DIR, ".env"))
except ImportError:
    env_path = os.path.join(PROJECT_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Config 로드
with open(os.path.join(PROJECT_DIR, "config.json"), encoding="utf-8") as f:
    config = json.load(f)

BRAND = config["brand"]["name"]
COMPETITORS = [c["name"] for c in config["competitors"]]
ALL_BRANDS = [BRAND] + COMPETITORS

# --------------------------------------------------
# Heuristic 필터링 키워드
# --------------------------------------------------
FURNITURE_TERMS = [
    # 가구 유형
    "가구", "책상", "소파", "쇼파", "침대", "의자", "수납", "옷장", "책장", "선반",
    "테이블", "서랍", "매트리스", "쿠션", "식탁", "찬장", "화장대",
    "신발장", "행거", "리클라이너", "벤치", "스툴", "협탁", "장식장",
    "TV장", "tv장", "거울", "진열장", "콘솔", "사이드", "수납장",
    "책꽂이", "모션베드", "씽크대", "붙박이장", "장롱", "장농", "이불장",
    "침대프레임", "베드프레임", "헤드보드", "데스크", "데스크테리어",
    # 공간
    "거실", "침실", "아이방", "서재", "주방", "현관", "드레스룸", "베란다",
    # 제품 특성
    "모션데스크", "전동", "높이조절", "패브릭", "가죽", "원목", "대리석",
    "모듈러", "붙박이", "벽선반", "조립", "접이식", "확장형", "성장형",
    # 구매 관련
    "인테리어", "꾸미기", "리모델링", "배치", "풍수",
    "신혼", "혼수", "이사", "원룸", "자취", "기숙사",
    "배송", "설치", "AS", "a/s", "교환", "반품", "할인", "세일",
    "가격", "매장", "아울렛", "중고", "쿠폰", "후기", "리뷰",
    # 브랜드 관련
    "데스커", "시디즈", "에몬스", "리바트", "퍼시스", "듀오백",
    "니트리", "보루네오", "체리쉬", "룸앤", "무인양품", "스칸디나",
]

# 명확히 무관한 키워드 (세계지도, 여행 등 노이즈)
EXCLUDE_TERMS = [
    "세계지도", "벽지", "도배", "페인트", "타일", "바닥재",
    "에어컨", "냉장고", "세탁기", "청소기",
    "노트북", "핸드폰", "이어폰", "헤드폰",
    "화장품", "향수",
    "자동차", "오토바이",
    "여행", "호텔", "펜션", "캠핑",
    "맛집", "베이커리",
    "영화", "드라마",
    "주식", "코인",
    "반도체", "상록회관", "웨딩박람회", "웨딩드레스",
    "혼주한복", "결혼반지", "출산선물", "출산준비",
    "전시회", "박람회",
]


# --------------------------------------------------
# 필터링
# --------------------------------------------------
def is_furniture_related(keyword):
    """가구/인테리어 관련 키워드 여부 판단"""
    kw = keyword.lower()

    # 브랜드명 포함 → 관련
    for brand in ALL_BRANDS:
        if brand.lower() in kw or brand.lower().replace(" ", "") in kw:
            return True

    # 가구 용어 포함 → 관련 (exclude보다 먼저 체크)
    for term in FURNITURE_TERMS:
        if term in kw:
            return True

    # 제외 키워드 체크
    for term in EXCLUDE_TERMS:
        if term in kw:
            return False

    return False


def filter_keywords(keywords, min_volume=50):
    """Heuristic 필터링 + 볼륨 임계값"""
    relevant = []
    filtered_out = []

    for kw in keywords:
        if kw["total"] < min_volume:
            continue
        if is_furniture_related(kw["keyword"]):
            relevant.append(kw)
        else:
            filtered_out.append(kw)

    return relevant, filtered_out


# --------------------------------------------------
# Gemini API 호출
# --------------------------------------------------
def create_client():
    """Gemini 클라이언트 생성"""
    return genai.Client(api_key=GEMINI_API_KEY)


def call_gemini(client, prompt, max_retries=3):
    """Gemini API 호출 + 재시도"""
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config={
                    "temperature": 0.1,
                    "response_mime_type": "application/json",
                },
            )
            return json.loads(response.text)
        except json.JSONDecodeError:
            # JSON 파싱 실패 시 텍스트에서 추출 시도
            text = response.text
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
            print(f"    JSON 파싱 실패 (시도 {attempt + 1}/{max_retries})")
        except Exception as e:
            print(f"    API 오류 (시도 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)

    return None


# --------------------------------------------------
# 의도 분류
# --------------------------------------------------
def classify_intent(client, keywords):
    """키워드 의도 분류 (배치 처리)"""
    all_results = []
    batch_size = 150
    total_batches = (len(keywords) + batch_size - 1) // batch_size

    for i in range(0, len(keywords), batch_size):
        batch = keywords[i:i + batch_size]
        batch_num = i // batch_size + 1

        print(f"  배치 {batch_num}/{total_batches} ({len(batch)}개)...")

        kw_lines = "\n".join(
            f"- {k['keyword']} ({k['total']:,})" for k in batch
        )

        prompt = f"""한국 가구 시장 검색 키워드를 구매 의도 3단계로 분류해주세요.

주 브랜드: {BRAND}
경쟁사: {', '.join(COMPETITORS)}

분류 기준:
- awareness: 카테고리/니즈 기반 탐색. 특정 브랜드 없이 정보 검색.
  예: "거실 소파 추천", "아이방 꾸미기", "가구 브랜드 순위", "학생 책상"
- consideration: 브랜드 비교, 리뷰, 후기, 특정 브랜드 제품 탐색.
  예: "{BRAND} vs 한샘", "{BRAND} 후기", "이케아 책상", "{BRAND} 소파"
- conversion: 가격, 매장, 할인, 구매처, AS, 배송, 설치 검색.
  예: "{BRAND} 가격", "{BRAND} 매장", "이케아 할인", "{BRAND} AS"

키워드 목록:
{kw_lines}

JSON 형식:
{{"results": [{{"keyword": "키워드", "volume": 검색량숫자, "stage": "awareness|consideration|conversion"}}]}}"""

        result = call_gemini(client, prompt)
        if result and "results" in result:
            all_results.extend(result["results"])
            print(f"    -> {len(result['results'])}개 분류 완료")
        else:
            print(f"    -> 분류 실패, 기본값(awareness) 적용")
            for kw in batch:
                all_results.append({
                    "keyword": kw["keyword"],
                    "volume": kw["total"],
                    "stage": "awareness",
                })

        time.sleep(0.5)

    return all_results


# --------------------------------------------------
# 페르소나 클러스터링
# --------------------------------------------------
def cluster_personas(client, keywords):
    """키워드 페르소나 클러스터링"""
    # 상위 300개로 클러스터링 (비용 효율)
    top_kws = keywords[:300]

    kw_lines = "\n".join(
        f"- {k['keyword']} ({k['total']:,})" for k in top_kws
    )

    prompt = f"""한국 가구 시장 검색 키워드를 구매자 페르소나 4-6개 그룹으로 분류해주세요.

주 브랜드: {BRAND}
카테고리: 가구/인테리어

각 그룹에 다음 정보를 부여해주세요:
- id: 영문 slug (예: "kids-parent")
- persona: 페르소나명 (예: "키즈맘/키즈대디")
- description: 특성 설명 (1-2문장)
- keywords: 해당 그룹 키워드 배열 [{{"keyword": "키워드", "volume": 검색량}}]
- needs: 주요 니즈 3-5개
- pain_points: 고충 2-3개

키워드 목록:
{kw_lines}

JSON 형식:
{{"clusters": [{{"id": "slug", "persona": "이름", "description": "설명", "keywords": [{{"keyword": "키워드", "volume": 검색량}}], "needs": ["니즈"], "pain_points": ["고충"]}}]}}"""

    result = call_gemini(client, prompt)
    return result


# --------------------------------------------------
# 이탈 시그널 분석
# --------------------------------------------------
def analyze_exit_signals(classified_keywords):
    """비교(consideration) 단계에서 경쟁사 이탈 방향 분석"""
    consideration_kws = [
        k for k in classified_keywords if k.get("stage") == "consideration"
    ]

    competitors_exit = {}
    for comp in COMPETITORS:
        mentions = [
            k for k in consideration_kws
            if comp in k.get("keyword", "")
        ]
        if mentions:
            competitors_exit[comp] = {
                "mention_count": len(mentions),
                "share": round(len(mentions) / max(len(consideration_kws), 1), 2),
                "sample": [m["keyword"] for m in sorted(
                    mentions, key=lambda x: x.get("volume", 0), reverse=True
                )[:3]],
            }

    total_comp_mentions = sum(c["mention_count"] for c in competitors_exit.values())
    other_count = len(consideration_kws) - total_comp_mentions
    if other_count > 0:
        competitors_exit["기타"] = {
            "mention_count": other_count,
            "share": round(other_count / max(len(consideration_kws), 1), 2),
        }

    return competitors_exit


# --------------------------------------------------
# JSON 저장
# --------------------------------------------------
def save_consumer_journey(classified_keywords, total_relevant):
    """consumer-journey.json 저장"""
    stages = {"awareness": [], "consideration": [], "conversion": []}

    for item in classified_keywords:
        stage = item.get("stage", "awareness")
        if stage in stages:
            stages[stage].append(item)

    total_vol = sum(k.get("volume", 0) for k in classified_keywords)
    exit_signals = analyze_exit_signals(classified_keywords)

    labels = {
        "awareness": "인지 (Awareness)",
        "consideration": "비교 (Consideration)",
        "conversion": "구매 (Conversion)",
    }
    descriptions = {
        "awareness": "카테고리/니즈 기반 검색",
        "consideration": "브랜드 비교/리뷰 검색",
        "conversion": "가격/구매처/매장 검색",
    }

    journey = {
        "meta": {
            "source": "Gemini API 키워드 의도 분류",
            "collected_at": datetime.now().strftime("%Y-%m-%d"),
            "total_keywords_analyzed": len(classified_keywords),
            "total_keywords_pool": total_relevant,
            "classification_method": "3-stage intent classification (Gemini 2.0 Flash)",
            "note": "GA 없이 실제 이탈률 측정 불가. 검색 키워드 기반 '추정 이탈 경향'으로 해석 필요.",
        },
        "stages": {},
        "funnel_summary": {},
    }

    for stage_key, items in stages.items():
        stage_vol = sum(i.get("volume", 0) for i in items)
        journey["stages"][stage_key] = {
            "label": labels[stage_key],
            "description": descriptions[stage_key],
            "keyword_count": len(items),
            "total_volume": stage_vol,
            "share": round(len(items) / max(len(classified_keywords), 1), 2),
            "sample_keywords": sorted(
                items, key=lambda x: x.get("volume", 0), reverse=True
            )[:10],
        }

    # 비교 단계에 이탈 시그널 추가
    if exit_signals:
        journey["stages"]["consideration"]["exit_signals"] = {
            "note": "비교 키워드에서 경쟁사 언급 빈도 = 추정 이탈 방향",
            "competitors": exit_signals,
        }

    # 퍼널 요약
    aw_vol = journey["stages"]["awareness"]["total_volume"]
    co_vol = journey["stages"]["consideration"]["total_volume"]
    cv_vol = journey["stages"]["conversion"]["total_volume"]

    journey["funnel_summary"] = {
        "awareness_to_consideration": round(co_vol / max(aw_vol, 1), 2),
        "consideration_to_conversion": round(cv_vol / max(co_vol, 1), 2),
        "estimated_leak_rate": round(1 - (cv_vol / max(aw_vol, 1)), 2),
        "primary_leak_destination": max(
            exit_signals.items(),
            key=lambda x: x[1].get("mention_count", 0)
        )[0] if exit_signals else "unknown",
    }

    output_path = os.path.join(PROJECT_DIR, "data", "consumer-journey.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(journey, f, ensure_ascii=False, indent=2)

    return journey


def save_keyword_clusters(cluster_result, total_relevant):
    """keyword-clusters.json 저장"""
    colors = ["#8b5cf6", "#ec4899", "#06b6d4", "#f59e0b", "#22c55e", "#ef4444"]

    clusters_output = {
        "meta": {
            "source": "Gemini API 키워드 클러스터링",
            "collected_at": datetime.now().strftime("%Y-%m-%d"),
            "total_keywords_pool": total_relevant,
            "clustering_method": "LLM-based persona clustering (Gemini 2.0 Flash)",
        },
        "clusters": [],
    }

    total_vol = sum(
        sum(k.get("volume", 0) for k in cl.get("keywords", []))
        for cl in cluster_result.get("clusters", [])
    )

    for i, cl in enumerate(cluster_result.get("clusters", [])):
        cl_volume = sum(k.get("volume", 0) for k in cl.get("keywords", []))
        clusters_output["clusters"].append({
            "id": cl.get("id", f"cluster-{i + 1}"),
            "persona": cl.get("persona", f"그룹 {i + 1}"),
            "description": cl.get("description", ""),
            "color": colors[i % len(colors)],
            "keyword_count": len(cl.get("keywords", [])),
            "total_volume": cl_volume,
            "share": round(cl_volume / max(total_vol, 1), 2),
            "top_keywords": sorted(
                cl.get("keywords", []),
                key=lambda x: x.get("volume", 0),
                reverse=True,
            )[:7],
            "needs": cl.get("needs", []),
            "pain_points": cl.get("pain_points", []),
        })

    output_path = os.path.join(PROJECT_DIR, "data", "keyword-clusters.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(clusters_output, f, ensure_ascii=False, indent=2)

    return clusters_output


# --------------------------------------------------
# 메인
# --------------------------------------------------
def main():
    dry_run = "--dry-run" in sys.argv
    top_n = 500  # 기본: 상위 500개

    for i, arg in enumerate(sys.argv):
        if arg == "--top" and i + 1 < len(sys.argv):
            top_n = int(sys.argv[i + 1])

    # API 키 확인
    if not dry_run and not GEMINI_API_KEY:
        print("GEMINI_API_KEY가 설정되지 않았습니다.")
        print("  .env 파일에 GEMINI_API_KEY=... 를 추가하세요.")
        sys.exit(1)

    print("=" * 55)
    print("키워드 분류 파이프라인 (Gemini 2.0 Flash)")
    print("=" * 55)

    # Step 1: 키워드 로드
    input_path = os.path.join(PROJECT_DIR, "data", "related-keywords.json")
    with open(input_path, encoding="utf-8") as f:
        raw_data = json.load(f)

    all_keywords = raw_data["keywords"]
    print(f"\n[1/5] 키워드 로드: {len(all_keywords)}개")

    # Step 2: Heuristic 필터링
    relevant, filtered_out = filter_keywords(all_keywords, min_volume=50)
    print(f"\n[2/5] 가구/인테리어 관련 필터링")
    print(f"  관련: {len(relevant)}개")
    print(f"  제외: {len(filtered_out)}개")
    print(f"  볼륨 50 미만 제외: {len(all_keywords) - len(relevant) - len(filtered_out)}개")

    # 상위 N개 선택
    relevant_top = relevant[:top_n]
    print(f"\n  분류 대상: 상위 {len(relevant_top)}개 (검색량 기준)")
    print(f"  상위 10개:")
    for kw in relevant_top[:10]:
        print(f"    {kw['keyword']}: {kw['total']:,}")

    if dry_run:
        print("\n[DRY RUN] API 호출 없이 필터링 결과만 출력합니다.")
        print(f"\n제외된 키워드 상위 20개:")
        for kw in filtered_out[:20]:
            print(f"  {kw['keyword']}: {kw['total']:,}")
        return

    # Gemini 클라이언트 생성
    client = create_client()

    # Step 3: 의도 분류
    print(f"\n[3/5] 의도 분류 (Gemini API)...")
    classified = classify_intent(client, relevant_top)
    print(f"  총 {len(classified)}개 분류 완료")

    # 분류 통계
    stage_counts = {}
    for item in classified:
        s = item.get("stage", "unknown")
        stage_counts[s] = stage_counts.get(s, 0) + 1
    for stage, count in sorted(stage_counts.items()):
        print(f"    {stage}: {count}개")

    # Step 4: 페르소나 클러스터링
    print(f"\n[4/5] 페르소나 클러스터링 (Gemini API)...")
    cluster_result = cluster_personas(client, relevant_top)

    if cluster_result and "clusters" in cluster_result:
        print(f"  {len(cluster_result['clusters'])}개 그룹 생성")
        for cl in cluster_result["clusters"]:
            print(f"    {cl.get('persona', '?')}: {len(cl.get('keywords', []))}개 키워드")
    else:
        print("  클러스터링 실패. 기본 클러스터 사용.")
        cluster_result = {"clusters": []}

    # Step 5: 저장
    print(f"\n[5/5] JSON 저장...")

    journey = save_consumer_journey(classified, len(relevant))
    print(f"  consumer-journey.json 저장 완료")
    for stage_key, stage_data in journey["stages"].items():
        print(f"    {stage_data['label']}: {stage_data['keyword_count']}개 ({stage_data['total_volume']:,})")

    clusters = save_keyword_clusters(cluster_result, len(relevant))
    print(f"  keyword-clusters.json 저장 완료")
    for cl in clusters["clusters"]:
        print(f"    {cl['persona']}: {cl['keyword_count']}개 ({cl['total_volume']:,})")

    # 퍼널 요약
    fs = journey.get("funnel_summary", {})
    print(f"\n퍼널 요약:")
    print(f"  인지 -> 비교 전환율: {fs.get('awareness_to_consideration', 0):.0%}")
    print(f"  비교 -> 구매 전환율: {fs.get('consideration_to_conversion', 0):.0%}")
    print(f"  추정 이탈률: {fs.get('estimated_leak_rate', 0):.0%}")
    print(f"  주요 이탈 방향: {fs.get('primary_leak_destination', '?')}")

    print("\n완료!")


if __name__ == "__main__":
    main()
