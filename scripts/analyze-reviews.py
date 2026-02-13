"""
리뷰 감성분석 → reviews-sentiment.json 생성

크롤링 결과(CSV)를 로드하여 Gemini 2.0 Flash API로 감성분석 수행.

필수:
  GEMINI_API_KEY: 환경변수 또는 .env 파일

사용법:
  python scripts/analyze-reviews.py --csv data/iloom_all_reviews.csv
"""

import argparse
import csv
import json
import math
import os
import sys
import time
from datetime import datetime

try:
    from google import genai
except ImportError:
    print("google-genai 패키지가 필요합니다: pip install google-genai")
    sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)

BATCH_SIZE = 50  # Gemini Flash는 큰 배치 가능

# .env 파일에서 GEMINI_API_KEY 로드
def load_api_key():
    key = os.environ.get("GEMINI_API_KEY", "")
    if key:
        return key
    # 프로젝트 .env
    for env_path in [
        os.path.join(PROJECT_DIR, ".env"),
        os.path.expanduser("~/claude-projects/pkm/00-system/02-scripts/gemini-file-search/.env"),
        os.path.expanduser("~/Projects/pkm/00-system/02-scripts/gemini-file-search/.env"),
    ]:
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("GEMINI_API_KEY="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


GEMINI_API_KEY = load_api_key()


def load_reviews(csv_path):
    """CSV에서 리뷰 로드"""
    reviews = []
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            reviews.append(
                {
                    "date": row.get("date", ""),
                    "rating": int(row.get("rating", 0)),
                    "content": row.get("content", ""),
                    "product": row.get("product_name", ""),
                }
            )
    return reviews


def analyze_batch(client, reviews_batch, batch_num, total_batches):
    """Gemini API로 리뷰 배치 감성분석"""
    reviews_text = "\n---\n".join(
        f"[{i}] [{r['date']}] 별점:{r['rating']} 제품:{r['product']}\n{r['content']}"
        for i, r in enumerate(reviews_batch)
    )

    prompt = f"""다음 가구 브랜드(일룸) 리뷰 {len(reviews_batch)}개를 분석해줘.

각 리뷰에 대해:
1. sentiment: positive / neutral / negative
2. topics: 해당되는 토픽들 (품질, 디자인, 가격, 배송/설치, AS/서비스 중 복수 선택)
3. key_point: 핵심 포인트 한 줄 (한국어)

리뷰들:
{reviews_text}

반드시 JSON 배열만 응답해줘. 다른 텍스트 없이:
[
  {{"idx": 0, "sentiment": "positive", "topics": ["품질", "디자인"], "key_point": "소재 품질 만족"}},
  ...
]"""

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config={
                    "temperature": 0.1,
                    "max_output_tokens": 8192,
                },
            )
            text = response.text
            start = text.find("[")
            end = text.rfind("]") + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
            print(f"    JSON 파싱 실패 (시도 {attempt+1})")
        except Exception as e:
            print(f"    API 오류 (시도 {attempt+1}): {e}")
            time.sleep(2)

    # fallback: 각 리뷰를 별점 기반으로 분류
    print(f"    fallback: 별점 기반 분류")
    return [
        {
            "idx": i,
            "sentiment": "positive" if r["rating"] >= 4 else ("negative" if r["rating"] <= 2 else "neutral"),
            "topics": ["품질"],
            "key_point": r["content"][:30] if r["content"] else "",
        }
        for i, r in enumerate(reviews_batch)
    ]


def analyze_monthly(client, reviews):
    """월별로 그룹핑하여 감성분석 → monthly_trend 생성"""
    from collections import defaultdict

    monthly_groups = defaultdict(list)
    for r in reviews:
        if r["date"]:
            # date format: YYYY-MM-DD or YYYY.MM.DD
            date_str = r["date"].replace(".", "-")
            month = date_str[:7]  # YYYY-MM
            monthly_groups[month].append(r)

    monthly_trend = []
    sorted_months = sorted(monthly_groups.keys())

    for month in sorted_months:
        month_reviews = monthly_groups[month]
        count = len(month_reviews)

        if count == 0:
            continue

        # Batch analyze this month's reviews
        all_results = []
        total_batches = math.ceil(count / BATCH_SIZE)

        for i in range(0, count, BATCH_SIZE):
            batch = month_reviews[i : i + BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1
            print(f"    {month} 배치 {batch_num}/{total_batches} ({len(batch)}건)...")
            results = analyze_batch(client, batch, batch_num, total_batches)
            all_results.extend(results)
            time.sleep(1)

        # Aggregate monthly sentiment
        sentiments = {"positive": 0, "neutral": 0, "negative": 0}
        for result in all_results:
            sent = result.get("sentiment", "neutral")
            sentiments[sent] = sentiments.get(sent, 0) + 1

        pos_rate = sentiments["positive"] / count if count else 0
        neu_rate = sentiments["neutral"] / count if count else 0
        neg_rate = sentiments["negative"] / count if count else 0
        avg_rating = round(
            sum(r.get("rating", 0) for r in month_reviews) / count, 1
        ) if count else 0

        monthly_trend.append({
            "date": month,
            "count": count,
            "positive": round(pos_rate, 2),
            "neutral": round(neu_rate, 2),
            "negative": round(neg_rate, 2),
            "avg_rating": avg_rating,
            "sentiment_score": round((pos_rate - neg_rate) * 100),
        })

    return monthly_trend


def main():
    parser = argparse.ArgumentParser(description="리뷰 감성분석 (Gemini)")
    parser.add_argument("--csv", required=True, help="리뷰 CSV 파일 경로")
    parser.add_argument("--monthly", action="store_true", help="월별 감성분석 포함 (실제 Gemini 분석)")
    args = parser.parse_args()

    if not os.path.exists(args.csv):
        print(f"파일을 찾을 수 없습니다: {args.csv}")
        sys.exit(1)

    if not GEMINI_API_KEY:
        print("GEMINI_API_KEY가 설정되지 않았습니다.")
        sys.exit(1)

    client = genai.Client(api_key=GEMINI_API_KEY)
    reviews = load_reviews(args.csv)
    print(f"리뷰 {len(reviews)}건 로드 완료")

    # Batch analysis
    all_results = []
    total_batches = math.ceil(len(reviews) / BATCH_SIZE)

    for i in range(0, len(reviews), BATCH_SIZE):
        batch = reviews[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        print(f"  배치 {batch_num}/{total_batches} 분석 중... ({len(batch)}건)")
        results = analyze_batch(client, batch, batch_num, total_batches)
        all_results.extend(results)
        time.sleep(1)  # rate limit

    # Aggregate
    sentiments = {"positive": 0, "neutral": 0, "negative": 0}
    topics = {}
    products = {}

    for idx, result in enumerate(all_results):
        review = reviews[idx] if idx < len(reviews) else {}
        sent = result.get("sentiment", "neutral")
        sentiments[sent] = sentiments.get(sent, 0) + 1

        for topic in result.get("topics", []):
            if topic not in topics:
                topics[topic] = {"positive": 0, "neutral": 0, "negative": 0, "count": 0}
            topics[topic][sent] += 1
            topics[topic]["count"] += 1

        prod = review.get("product", "기타")
        if prod not in products:
            products[prod] = {"count": 0, "ratings": [], "sentiments": []}
        products[prod]["count"] += 1
        products[prod]["ratings"].append(review.get("rating", 0))
        products[prod]["sentiments"].append(sent)

    total = len(all_results)
    pos_rate = sentiments["positive"] / total if total else 0
    neg_rate = sentiments["negative"] / total if total else 0

    # Calculate date range for period
    dates = [r.get("date", "") for r in reviews if r.get("date")]
    dates_clean = [d.replace(".", "-") for d in dates if d]
    min_date = min(dates_clean)[:7] if dates_clean else ""
    max_date = max(dates_clean)[:7] if dates_clean else ""
    period = f"{min_date} ~ {max_date}" if min_date and max_date else ""

    # Build output
    output = {
        "meta": {
            "source": "네이버 브랜드스토어 리뷰 크롤링 + Gemini 2.0 Flash 감성분석",
            "collected_at": datetime.now().strftime("%Y-%m"),
            "total_reviews": total,
            "csv_source": os.path.basename(args.csv),
            "period": period,
        },
        "overall": {
            "positive": round(pos_rate, 2),
            "neutral": round(sentiments["neutral"] / total, 2) if total else 0,
            "negative": round(neg_rate, 2),
            "avg_rating": round(
                sum(r.get("rating", 0) for r in reviews) / len(reviews), 1
            )
            if reviews
            else 0,
            "sentiment_score": round((pos_rate - neg_rate) * 100),
        },
        "by_topic": {},
        "by_product": {},
    }

    for topic, data in topics.items():
        tc = data["count"]
        output["by_topic"][topic] = {
            "positive": round(data["positive"] / tc, 2),
            "neutral": round(data["neutral"] / tc, 2),
            "negative": round(data["negative"] / tc, 2),
            "mention_count": tc,
        }

    for prod, data in products.items():
        pc = data["count"]
        avg_r = round(sum(data["ratings"]) / pc, 1) if pc else 0
        pos_c = data["sentiments"].count("positive")
        neg_c = data["sentiments"].count("negative")
        output["by_product"][prod] = {
            "count": pc,
            "avg_rating": avg_r,
            "sentiment_score": round((pos_c - neg_c) / pc * 100) if pc else 0,
        }

    # Monthly trend
    if args.monthly:
        print(f"\n월별 감성분석 실행 중...")
        output["monthly_trend"] = analyze_monthly(client, reviews)
        print(f"  {len(output['monthly_trend'])}개 월 분석 완료")
    else:
        # Fallback: rating-based monthly estimate (for quick runs without --monthly)
        from collections import defaultdict

        monthly_groups = defaultdict(list)
        for r in reviews:
            if r["date"]:
                date_str = r["date"].replace(".", "-")
                month = date_str[:7]
                monthly_groups[month].append(r)

        monthly_trend = []
        for month in sorted(monthly_groups.keys()):
            mrs = monthly_groups[month]
            count = len(mrs)
            if count == 0:
                continue
            # Use overall analysis results for this month's reviews
            month_indices = [i for i, r in enumerate(reviews)
                          if r.get("date", "").replace(".", "-")[:7] == month]
            pos = sum(1 for idx in month_indices
                     if idx < len(all_results) and all_results[idx].get("sentiment") == "positive")
            neg = sum(1 for idx in month_indices
                     if idx < len(all_results) and all_results[idx].get("sentiment") == "negative")
            avg_r = round(sum(r.get("rating", 0) for r in mrs) / count, 1)
            monthly_trend.append({
                "date": month,
                "count": count,
                "positive": round(pos / count, 2) if count else 0,
                "neutral": round((count - pos - neg) / count, 2) if count else 0,
                "negative": round(neg / count, 2) if count else 0,
                "avg_rating": avg_r,
                "sentiment_score": round((pos - neg) / count * 100) if count else 0,
            })
        output["monthly_trend"] = monthly_trend

    output_path = os.path.join(PROJECT_DIR, "data", "reviews-sentiment.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nreviews-sentiment.json 저장 완료")
    print(f"  전체: 긍정 {pos_rate:.0%} / 부정 {neg_rate:.0%}")
    print(f"  감성 점수: {output['overall']['sentiment_score']}")
    print(f"  토픽별:")
    for topic, data in output["by_topic"].items():
        print(f"    {topic}: 긍정 {data['positive']:.0%} / 부정 {data['negative']:.0%} ({data['mention_count']}건)")
    if output.get("monthly_trend"):
        print(f"  월별 추이: {len(output['monthly_trend'])}개 월")


if __name__ == "__main__":
    main()
