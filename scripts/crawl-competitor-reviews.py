"""경쟁사 리뷰 크롤링 + 감성분석 → competitor-sentiment.json

경쟁사 네이버 브랜드스토어 리뷰를 크롤링하고 감성분석 수행.
크롤링 완료 후 analyze-reviews.py와 동일한 Gemini 감성분석 실행.

필수:
  NAVER_ID, NAVER_PW: 네이버 로그인 (.env)
  GEMINI_API_KEY: 감성분석용 (.env)

사용법:
  python scripts/crawl-competitor-reviews.py                     # 크롤링 + 분석
  python scripts/crawl-competitor-reviews.py --analyze-only      # 기존 CSV로 분석만
  python scripts/crawl-competitor-reviews.py --brands 한샘 까사미아  # 특정 브랜드만

경쟁사 브랜드스토어 정보:
  한샘: brand.naver.com/hanssem (merchantNo: 500064538)
  까사미아: brand.naver.com/casamia (merchantNo: 500136270)
"""

import argparse
import csv
import json
import math
import os
import sys
import time
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(PROJECT_DIR, "data")

# Competitor brand store configurations
COMPETITOR_STORES = {
    "한샘": {
        "store_name": "hanssem",
        "merchant_no": "500064538",
        "product_ids": [],  # Will be populated or use search
    },
    "까사미아": {
        "store_name": "casamia",
        "merchant_no": "500136270",
        "product_ids": [],
    },
}

MAX_PER_PRODUCT = 100
BATCH_SIZE = 50


def load_env():
    """Load environment variables from .env"""
    env_path = os.path.join(PROJECT_DIR, ".env")
    env_vars = {}
    for path in [
        env_path,
        os.path.expanduser("~/claude-projects/pkm/00-system/02-scripts/gemini-file-search/.env"),
        os.path.expanduser("~/Projects/pkm/00-system/02-scripts/gemini-file-search/.env"),
    ]:
        if os.path.exists(path):
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, val = line.split("=", 1)
                        env_vars[key.strip()] = val.strip().strip('"').strip("'")

    for key, val in env_vars.items():
        if key not in os.environ:
            os.environ[key] = val

    return env_vars


def crawl_brand_reviews_api(brand_name, store_config, max_products=10):
    """Crawl reviews using Naver Brand Store API (no Selenium needed)"""
    import urllib.request
    import urllib.parse

    merchant_no = store_config["merchant_no"]
    store_name = store_config["store_name"]
    all_reviews = []

    # First, get product list from brand store
    print(f"  [{brand_name}] 제품 목록 조회 중...")

    # Use the brand store product list API
    products_url = (
        f"https://smartstore.naver.com/i/v1/stores/{merchant_no}/products"
        f"?page=1&pageSize={max_products}&sortType=POPULAR"
    )

    try:
        req = urllib.request.Request(
            products_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": f"https://brand.naver.com/{store_name}",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            product_ids = [
                str(p.get("id") or p.get("productNo"))
                for p in data.get("simpleProducts", data.get("products", []))[:max_products]
            ]
    except Exception as e:
        print(f"    제품 목록 API 실패: {e}")
        product_ids = store_config.get("product_ids", [])

    if not product_ids:
        print(f"    [{brand_name}] 제품 ID 없음. 수동으로 product_ids 설정 필요.")
        return []

    print(f"  [{brand_name}] {len(product_ids)}개 제품 리뷰 수집 시작")

    for idx, product_no in enumerate(product_ids):
        print(f"    [{idx + 1}/{len(product_ids)}] 제품 {product_no}...")

        page = 1
        product_reviews = []

        while len(product_reviews) < MAX_PER_PRODUCT:
            review_url = (
                f"https://smartstore.naver.com/i/v1/reviews"
                f"?page={page}&pageSize=20&merchantNo={merchant_no}"
                f"&originProductNo={product_no}&sortType=RANKING"
            )

            try:
                req = urllib.request.Request(
                    review_url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                        "Referer": f"https://brand.naver.com/{store_name}/products/{product_no}",
                    },
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    review_data = json.loads(resp.read().decode("utf-8"))
                    reviews = review_data.get("contents", review_data.get("reviews", []))

                    if not reviews:
                        break

                    for r in reviews:
                        product_reviews.append({
                            "date": r.get("createDate", r.get("reviewCreatedDate", ""))[:10],
                            "rating": r.get("reviewScore", r.get("score", 0)),
                            "content": r.get("reviewContent", r.get("content", "")),
                            "product_name": r.get("productName", r.get("product", {}).get("name", "")),
                            "brand": brand_name,
                        })

                    if len(reviews) < 20:
                        break

                page += 1
                time.sleep(0.5)

            except Exception as e:
                print(f"      리뷰 API 오류: {e}")
                break

        all_reviews.extend(product_reviews[:MAX_PER_PRODUCT])
        print(f"      -> {len(product_reviews[:MAX_PER_PRODUCT])}개 수집")
        time.sleep(1)

    return all_reviews


def analyze_sentiment(reviews, brand_name):
    """Gemini API로 감성분석 (analyze-reviews.py와 동일 로직)"""
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
    all_results = []
    total_batches = math.ceil(len(reviews) / BATCH_SIZE)

    for i in range(0, len(reviews), BATCH_SIZE):
        batch = reviews[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        print(f"    [{brand_name}] 배치 {batch_num}/{total_batches} ({len(batch)}건)...")

        reviews_text = "\n---\n".join(
            f"[{j}] [{r['date']}] 별점:{r['rating']}\n{r['content']}"
            for j, r in enumerate(batch)
        )

        prompt = f"""다음 가구 브랜드({brand_name}) 리뷰 {len(batch)}개를 분석해줘.

각 리뷰에 대해:
1. sentiment: positive / neutral / negative
2. topics: 해당되는 토픽들 (품질, 디자인, 가격, 배송/설치, AS/서비스 중 복수 선택)

리뷰들:
{reviews_text}

반드시 JSON 배열만 응답해줘:
[{{"idx": 0, "sentiment": "positive", "topics": ["품질"]}}]"""

        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=prompt,
                    config={"temperature": 0.1, "max_output_tokens": 8192},
                )
                text = response.text
                start = text.find("[")
                end = text.rfind("]") + 1
                if start >= 0 and end > start:
                    all_results.extend(json.loads(text[start:end]))
                    break
            except Exception as e:
                print(f"      API 오류 (시도 {attempt + 1}): {e}")
                time.sleep(2)
        else:
            # Fallback
            for j, r in enumerate(batch):
                all_results.append({
                    "idx": j,
                    "sentiment": "positive" if r["rating"] >= 4 else ("negative" if r["rating"] <= 2 else "neutral"),
                    "topics": ["품질"],
                })

        time.sleep(1)

    # Aggregate
    total = len(all_results)
    sentiments = {"positive": 0, "neutral": 0, "negative": 0}
    topics = {}

    for idx, result in enumerate(all_results):
        sent = result.get("sentiment", "neutral")
        sentiments[sent] = sentiments.get(sent, 0) + 1

        for topic in result.get("topics", []):
            if topic not in topics:
                topics[topic] = {"positive": 0, "neutral": 0, "negative": 0, "count": 0}
            topics[topic][sent] += 1
            topics[topic]["count"] += 1

    pos_rate = sentiments["positive"] / total if total else 0
    neg_rate = sentiments["negative"] / total if total else 0
    avg_rating = round(sum(r.get("rating", 0) for r in reviews) / len(reviews), 1) if reviews else 0

    by_topic = {}
    for topic, data in topics.items():
        tc = data["count"]
        by_topic[topic] = {
            "positive": round(data["positive"] / tc, 2),
            "neutral": round(data["neutral"] / tc, 2),
            "negative": round(data["negative"] / tc, 2),
            "mention_count": tc,
        }

    return {
        "overall": {
            "positive": round(pos_rate, 2),
            "neutral": round(sentiments["neutral"] / total, 2) if total else 0,
            "negative": round(neg_rate, 2),
            "avg_rating": avg_rating,
            "sentiment_score": round((pos_rate - neg_rate) * 100),
        },
        "by_topic": by_topic,
        "review_count": total,
    }


def main():
    parser = argparse.ArgumentParser(description="경쟁사 리뷰 크롤링 + 감성분석")
    parser.add_argument("--analyze-only", action="store_true", help="기존 CSV로 분석만 수행")
    parser.add_argument("--brands", nargs="+", default=list(COMPETITOR_STORES.keys()),
                       help="크롤링할 브랜드 (기본: 한샘 까사미아)")
    parser.add_argument("--max-products", type=int, default=10, help="브랜드당 최대 제품 수")
    args = parser.parse_args()

    load_env()

    print("=" * 55)
    print("경쟁사 리뷰 크롤링 + 감성분석")
    print("=" * 55)
    print(f"대상 브랜드: {', '.join(args.brands)}")

    output = {
        "meta": {
            "source": "네이버 브랜드스토어 경쟁사 리뷰 크롤링 + Gemini 감성분석",
            "collected_at": datetime.now().strftime("%Y-%m-%d"),
            "brands_analyzed": args.brands,
        },
        "brands": {},
    }

    for brand_name in args.brands:
        if brand_name not in COMPETITOR_STORES:
            print(f"\n[{brand_name}] 브랜드스토어 정보 없음, 건너뜀")
            continue

        store_config = COMPETITOR_STORES[brand_name]
        csv_path = os.path.join(DATA_DIR, f"{store_config['store_name']}_reviews.csv")

        # Crawl or load
        if args.analyze_only and os.path.exists(csv_path):
            print(f"\n[{brand_name}] 기존 CSV 로드: {csv_path}")
            reviews = []
            with open(csv_path, encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    reviews.append({
                        "date": row.get("date", ""),
                        "rating": int(row.get("rating", 0)),
                        "content": row.get("content", ""),
                        "product_name": row.get("product_name", ""),
                        "brand": brand_name,
                    })
        else:
            print(f"\n[{brand_name}] 리뷰 크롤링 시작...")
            reviews = crawl_brand_reviews_api(brand_name, store_config, args.max_products)

            if reviews:
                # Save CSV
                fieldnames = ["date", "rating", "content", "product_name", "brand"]
                with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                    writer.writeheader()
                    writer.writerows(reviews)
                print(f"  CSV 저장: {csv_path} ({len(reviews)}건)")

        if not reviews:
            print(f"  [{brand_name}] 리뷰 없음")
            continue

        print(f"\n  [{brand_name}] 감성분석 시작 ({len(reviews)}건)...")
        sentiment = analyze_sentiment(reviews, brand_name)

        if sentiment:
            output["brands"][brand_name] = sentiment
            print(f"  [{brand_name}] 완료: 긍정 {sentiment['overall']['positive']:.0%}, "
                  f"부정 {sentiment['overall']['negative']:.0%}, "
                  f"감성점수 {sentiment['overall']['sentiment_score']}")

    # Save output
    output_path = os.path.join(DATA_DIR, "competitor-sentiment.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 55}")
    print(f"competitor-sentiment.json 저장 완료")
    for brand, data in output["brands"].items():
        print(f"  {brand}: {data['review_count']}건, 감성점수 {data['overall']['sentiment_score']}")


if __name__ == "__main__":
    main()
