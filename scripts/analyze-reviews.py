"""
리뷰 감성분석 → reviews-sentiment.json 생성

기존 review-analyzer 스킬의 크롤링 결과(CSV)를 로드하여
Claude API로 감성분석을 수행합니다.

필수 환경변수:
  ANTHROPIC_API_KEY: Anthropic API 키

사용법:
  1. review-analyzer 스킬로 리뷰 크롤링 (CSV 생성)
  2. export ANTHROPIC_API_KEY=your_api_key_here
  3. python scripts/analyze-reviews.py --csv /path/to/reviews.csv
"""

import argparse
import csv
import json
import math
import os
import sys

try:
    import anthropic
except ImportError:
    print("anthropic 패키지가 필요합니다: pip install anthropic")
    sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)

BATCH_SIZE = 30  # Claude API 1회 호출당 리뷰 수


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


def analyze_batch(reviews_batch):
    """Claude API로 리뷰 배치 감성분석"""
    client = anthropic.Anthropic()

    reviews_text = "\n---\n".join(
        f"[{r['date']}] 별점:{r['rating']} 제품:{r['product']}\n{r['content']}"
        for r in reviews_batch
    )

    prompt = f"""다음 가구 리뷰들을 분석해줘.

각 리뷰에 대해:
1. sentiment: positive / neutral / negative
2. topics: 해당되는 토픽들 (품질, 디자인, 가격, 배송/설치, AS/서비스 중)
3. key_point: 핵심 포인트 한 줄

리뷰들:
{reviews_text}

JSON 배열로 응답해줘:
[
  {{"idx": 0, "sentiment": "positive", "topics": ["품질", "디자인"], "key_point": "소재 품질 만족"}}
]"""

    response = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text
    start = text.find("[")
    end = text.rfind("]") + 1
    return json.loads(text[start:end])


def main():
    parser = argparse.ArgumentParser(description="리뷰 감성분석")
    parser.add_argument("--csv", required=True, help="리뷰 CSV 파일 경로")
    args = parser.parse_args()

    if not os.path.exists(args.csv):
        print(f"파일을 찾을 수 없습니다: {args.csv}")
        sys.exit(1)

    reviews = load_reviews(args.csv)
    print(f"리뷰 {len(reviews)}건 로드 완료")

    # Batch analysis
    all_results = []
    total_batches = math.ceil(len(reviews) / BATCH_SIZE)

    for i in range(0, len(reviews), BATCH_SIZE):
        batch = reviews[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        print(f"  배치 {batch_num}/{total_batches} 분석 중... ({len(batch)}건)")
        results = analyze_batch(batch)
        all_results.extend(results)

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

    # Build output
    output = {
        "meta": {
            "source": "네이버 브랜드스토어 리뷰 크롤링 + Claude 감성분석",
            "collected_at": __import__("datetime").datetime.now().strftime("%Y-%m"),
            "total_reviews": total,
            "csv_source": os.path.basename(args.csv),
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

    output_path = os.path.join(PROJECT_DIR, "data", "reviews-sentiment.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nreviews-sentiment.json 저장 완료")
    print(f"  전체: 긍정 {pos_rate:.0%} / 부정 {neg_rate:.0%}")
    print(f"  감성 점수: {output['overall']['sentiment_score']}")


if __name__ == "__main__":
    main()
