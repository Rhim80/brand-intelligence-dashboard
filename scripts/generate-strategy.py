"""전략 매트릭스 자동 생성 → strategy-matrix.json

모든 데이터 파일을 분석하여 Gemini API로 전략 매트릭스를 자동 생성.
impact = 검색량 x SOS 갭 기반, feasibility = AI 평가.

필수:
  GEMINI_API_KEY: 환경변수 또는 .env 파일

사용법:
  python scripts/generate-strategy.py
  python scripts/generate-strategy.py --dry-run    # 데이터 요약만 출력
"""

import argparse
import json
import os
import sys
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(PROJECT_DIR, "data")


def load_env():
    """Load environment variables from .env"""
    for path in [
        os.path.join(PROJECT_DIR, ".env"),
        os.path.expanduser("~/claude-projects/pkm/00-system/02-scripts/gemini-file-search/.env"),
        os.path.expanduser("~/Projects/pkm/00-system/02-scripts/gemini-file-search/.env"),
    ]:
        if os.path.exists(path):
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, val = line.split("=", 1)
                        if key.strip() not in os.environ:
                            os.environ[key.strip()] = val.strip().strip('"').strip("'")


def load_all_data():
    """Load all JSON data files"""
    data = {}
    files = [
        "search-volume", "trend", "keyword-clusters",
        "consumer-journey", "ai-sov", "reviews-sentiment",
        "competitor-sentiment",
    ]
    for name in files:
        path = os.path.join(DATA_DIR, f"{name}.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                data[name] = json.load(f)
        else:
            data[name] = None
    return data


def load_config():
    """Load config.json"""
    with open(os.path.join(PROJECT_DIR, "config.json"), encoding="utf-8") as f:
        return json.load(f)


def summarize_data(data, config):
    """Create concise summaries of each data source for the prompt"""
    brand = config["brand"]["name"]
    competitors = [c["name"] for c in config["competitors"]]
    all_brands = [brand] + competitors
    summaries = {}

    # Search volume summary
    sv = data.get("search-volume")
    if sv:
        current = sv["current"]["brands"]
        all_total = sum(current.get(b, {}).get("total", 0) for b in all_brands)
        brand_total = current.get(brand, {}).get("total", 0)
        sos = (brand_total / all_total * 100) if all_total else 0
        sorted_brands = sorted(all_brands, key=lambda b: current.get(b, {}).get("total", 0), reverse=True)
        rank_parts = []
        for b in sorted_brands:
            vol = current.get(b, {}).get("total", 0)
            rank_parts.append(f"{b}({vol:,})")
        summaries["search_volume"] = (
            f"{brand} SOS: {sos:.1f}% (검색량 {brand_total:,}). "
            f"순위: {', '.join(rank_parts)}"
        )

    # AI SOV summary
    ai = data.get("ai-sov")
    if ai:
        mention = ai["mention_rate"]["brands"]
        sov = ai["sov_score"]["brands"]
        ctx = ai.get("by_context", {})
        ctx_labels = {"general_recommendation": "일반", "kids_furniture": "키즈", "living_room": "거실", "value_for_money": "가성비"}
        ctx_parts = []
        for k, v in ctx.items():
            sorted_ctx = sorted(v.items(), key=lambda x: x[1], reverse=True)
            brand_rate = v.get(brand, 0)
            top_brand = sorted_ctx[0][0] if sorted_ctx else "?"
            ctx_parts.append(f"{ctx_labels.get(k, k)}: {brand}={brand_rate*100:.0f}%(1위={top_brand})")
        summaries["ai_sov"] = (
            f"{brand} SOV: {sov.get(brand, 0):.1f}%, 언급률: {mention.get(brand, {}).get('rate', 0)*100:.0f}%. "
            f"문맥별: {'; '.join(ctx_parts)}"
        )

    # Reviews summary
    rev = data.get("reviews-sentiment")
    if rev:
        overall = rev["overall"]
        topics = rev.get("by_topic", {})
        weak_topics = [(t, d) for t, d in topics.items() if d.get("negative", 0) > 0.1]
        weak_topics.sort(key=lambda x: x[1]["negative"], reverse=True)
        weak_parts = []
        for t, d in weak_topics[:3]:
            neg_pct = d["negative"] * 100
            weak_parts.append(f"{t}(부정 {neg_pct:.0f}%)")
        summaries["reviews"] = (
            f"전체: 긍정 {overall['positive']*100:.0f}%, 부정 {overall['negative']*100:.0f}%, "
            f"감성점수 {overall['sentiment_score']}. "
            f"약점 토픽: {', '.join(weak_parts)}"
        )

    # Consumer journey summary
    cj = data.get("consumer-journey")
    if cj:
        stages = cj["stages"]
        exits = stages.get("consideration", {}).get("exit_signals", {}).get("competitors", {})
        exit_parts = [f"{k}({v['share']*100:.0f}%)" for k, v in sorted(exits.items(), key=lambda x: x[1].get("share", 0), reverse=True)[:3]]
        summaries["journey"] = (
            f"퍼널: 인지({stages.get('awareness',{}).get('total_volume',0):,}) → "
            f"비교({stages.get('consideration',{}).get('total_volume',0):,}) → "
            f"구매({stages.get('conversion',{}).get('total_volume',0):,}). "
            f"이탈 방향: {', '.join(exit_parts)}"
        )

    # Keyword clusters summary
    kc = data.get("keyword-clusters")
    if kc:
        clusters = kc.get("clusters", [])
        cl_parts = [f"{c['persona']}({c['share']*100:.0f}%, {c['total_volume']:,})" for c in clusters]
        summaries["clusters"] = f"클러스터: {'; '.join(cl_parts)}"

    # Competitor sentiment (if available)
    cs = data.get("competitor-sentiment")
    if cs and cs.get("brands"):
        comp_parts = []
        for b, d in cs["brands"].items():
            comp_parts.append(f"{b}(긍정 {d['overall']['positive']*100:.0f}%, 감성 {d['overall']['sentiment_score']})")
        summaries["competitor_reviews"] = f"경쟁사 리뷰: {'; '.join(comp_parts)}"

    return summaries


def calculate_impact_scores(data, config):
    """Calculate data-driven impact scores for strategies"""
    brand = config["brand"]["name"]
    competitors = [c["name"] for c in config["competitors"]]
    all_brands = [brand] + competitors

    scores = {}

    sv = data.get("search-volume")
    ai = data.get("ai-sov")

    if sv and ai:
        current = sv["current"]["brands"]
        all_total = sum(current.get(b, {}).get("total", 0) for b in all_brands)
        brand_total = current.get(brand, {}).get("total", 0)
        brand_sos = brand_total / all_total if all_total else 0

        # Top brand SOS
        top_brand = max(all_brands, key=lambda b: current.get(b, {}).get("total", 0))
        top_sos = current.get(top_brand, {}).get("total", 0) / all_total if all_total else 0
        sos_gap = top_sos - brand_sos

        # AI SOV gap
        sov = ai["sov_score"]["brands"]
        top_sov_brand = max(sov, key=lambda b: sov[b])
        sov_gap = sov[top_sov_brand] - sov.get(brand, 0)

        scores["sos_gap"] = round(sos_gap * 100, 1)
        scores["sov_gap"] = round(sov_gap, 1)
        scores["brand_total"] = brand_total
        scores["all_total"] = all_total

    return scores


def generate_strategy(data, config, summaries, scores):
    """Use Gemini to generate strategy matrix"""
    try:
        from google import genai
    except ImportError:
        print("google-genai 패키지가 필요합니다: pip install google-genai")
        return None

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("GEMINI_API_KEY가 설정되지 않았습니다.")
        return None

    client = genai.Client(api_key=api_key)
    brand = config["brand"]["name"]

    data_summary = "\n".join(f"- {k}: {v}" for k, v in summaries.items())

    prompt = f"""다음 데이터를 분석하여 {brand}의 브랜드 전략을 5-7개 제안하라.

데이터 요약:
{data_summary}

추가 수치:
- SOS 갭 (1위 대비): {scores.get('sos_gap', '?')}%p
- AI SOV 갭 (1위 대비): {scores.get('sov_gap', '?')}%p
- 브랜드 월간 검색량: {scores.get('brand_total', '?'):,}

각 전략에 대해 다음 정보를 포함:
- id: 순서 번호 (1부터)
- label: 전략명 (간결, 10자 이내)
- category: "강점 활용" / "약점 보완" / "신규 기회" / "위협 대응" 중 하나
- priority: "critical" / "high" / "medium" 중 하나
- impact: 영향도 점수 (50-100, 검색량 x 점유율갭 고려)
- feasibility: 실행 용이성 점수 (50-100, 리소스 투입 대비 효과)
- description: 전략 설명 (1-2문장)
- data_basis: 근거 데이터 수치 (구체적 숫자 포함)
- actions: 실행 항목 3개 (구체적)
- expected_impact: 예상 효과 (구체적 수치 포함)

JSON 형식으로만 응답:
{{"matrix_items": [
  {{"id": 1, "label": "전략명", "category": "강점 활용", "priority": "critical", "impact": 92, "feasibility": 85, "description": "설명", "data_basis": "근거", "actions": ["항목1", "항목2", "항목3"], "expected_impact": "효과"}}
]}}"""

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config={
                    "temperature": 0.3,
                    "response_mime_type": "application/json",
                },
            )
            result = json.loads(response.text)
            if "matrix_items" in result:
                return result
        except json.JSONDecodeError:
            text = response.text
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    result = json.loads(text[start:end])
                    if "matrix_items" in result:
                        return result
                except json.JSONDecodeError:
                    pass
            print(f"  JSON 파싱 실패 (시도 {attempt + 1})")
        except Exception as e:
            print(f"  API 오류 (시도 {attempt + 1}): {e}")

    return None


def main():
    parser = argparse.ArgumentParser(description="전략 매트릭스 자동 생성 (Gemini)")
    parser.add_argument("--dry-run", action="store_true", help="데이터 요약만 출력")
    args = parser.parse_args()

    load_env()

    print("=" * 55)
    print("전략 매트릭스 자동 생성 (Gemini)")
    print("=" * 55)

    config = load_config()
    data = load_all_data()

    print(f"\n브랜드: {config['brand']['name']}")
    print(f"로드된 데이터: {', '.join(k for k, v in data.items() if v)}")

    summaries = summarize_data(data, config)
    scores = calculate_impact_scores(data, config)

    print(f"\n데이터 요약:")
    for key, val in summaries.items():
        print(f"  [{key}] {val}")

    print(f"\n영향도 점수 기준:")
    print(f"  SOS 갭: {scores.get('sos_gap', '?')}%p")
    print(f"  SOV 갭: {scores.get('sov_gap', '?')}%p")

    if args.dry_run:
        print("\n[DRY RUN] API 호출 없이 종료합니다.")
        return

    print(f"\nGemini API로 전략 생성 중...")
    result = generate_strategy(data, config, summaries, scores)

    if not result:
        print("전략 생성 실패")
        sys.exit(1)

    output = {
        "meta": {
            "source": "전체 데이터 종합 + Gemini 전략 제안",
            "collected_at": datetime.now().strftime("%Y-%m-%d"),
            "methodology": "Y축(영향도) = 검색량 x SOS 갭, X축(실행성) = AI 평가",
            "data_sources": list(summaries.keys()),
        },
        "matrix_items": result["matrix_items"],
    }

    output_path = os.path.join(DATA_DIR, "strategy-matrix.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nstrategy-matrix.json 저장 완료")
    print(f"  전략 {len(output['matrix_items'])}개 생성:")
    for item in output["matrix_items"]:
        print(f"    [{item['priority']}] {item['label']} (impact:{item['impact']}, feasibility:{item['feasibility']})")


if __name__ == "__main__":
    main()
