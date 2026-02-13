"""일룸 브랜드스토어 배치 리뷰 크롤링

한 번의 로그인 세션으로 여러 제품의 리뷰를 수집.
기존 naver-brand-reviews.py의 fetch_reviews/crawl_reviews를 재사용.
"""
import csv
import json
import os
import sys
import time
from datetime import datetime

# review-analyzer 스킬 경로 추가
SKILL_SCRIPTS = os.path.expanduser("~/.claude/skills/review-analyzer/scripts")
sys.path.insert(0, SKILL_SCRIPTS)

from cookie_extractor import load_env, NaverSession

# naver-brand-reviews.py의 함수 임포트
sys.path.insert(0, SKILL_SCRIPTS)
import importlib.util
spec = importlib.util.spec_from_file_location("nbr", os.path.join(SKILL_SCRIPTS, "naver-brand-reviews.py"))
nbr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nbr)

MERCHANT_NO = "500152098"
STORE_NAME = "iloom"
MAX_PER_PRODUCT = 100
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

# 카테고리 페이지에서 수집한 제품 ID (상위 15개)
PRODUCT_IDS = [
    "7574782088",
    "11659509026",
    "7673958894",
    "6070150695",
    "5249391817",
    "2369741389",
    "12348939202",
    "5570092006",
    "4902801286",
    "6070150040",
    "5249393101",
    "5249391896",
    "12349000687",
    "12143229900",
    "8173413025",
]


def main():
    naver_id, naver_pw = load_env()
    if not naver_id:
        print("Error: .env에 NAVER_ID/NAVER_PW 필요")
        sys.exit(1)

    first_url = f"https://brand.naver.com/{STORE_NAME}/products/{PRODUCT_IDS[0]}"
    session = NaverSession()
    if not session.login(naver_id, naver_pw, product_url=first_url):
        print("로그인 실패")
        sys.exit(1)

    all_reviews = []
    product_stats = []

    try:
        for i, product_no in enumerate(PRODUCT_IDS):
            print(f"\n{'='*50}")
            print(f"[{i+1}/{len(PRODUCT_IDS)}] 제품 {product_no}")

            # 제품 페이지로 이동
            product_url = f"https://brand.naver.com/{STORE_NAME}/products/{product_no}"
            session.driver.get(product_url)
            time.sleep(3)

            # crawl_reviews 사용 (session 전달)
            reviews = nbr.crawl_reviews(
                MERCHANT_NO, product_no,
                session=session,
                max_reviews=MAX_PER_PRODUCT,
                sort="RANKING"
            )

            all_reviews.extend(reviews)

            if reviews:
                product_name = reviews[0].get("product_name", "unknown")
                product_stats.append({
                    "product_no": product_no,
                    "name": product_name,
                    "count": len(reviews),
                })
                print(f"  => 수집: {len(reviews)}개 ({product_name[:40]})")
            else:
                print(f"  => 리뷰 없음 또는 실패")

            time.sleep(1)

    finally:
        session.close()

    # CSV 저장
    output_path = os.path.join(OUTPUT_DIR, "iloom_all_reviews.csv")
    fieldnames = ["date", "rating", "content", "writer", "product_name", "product_option", "has_photo", "image_count"]

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_reviews)

    print(f"\n{'='*50}")
    print(f"전체 수집: {len(all_reviews)}개 리뷰")
    print(f"CSV: {output_path}")
    print(f"\n제품별:")
    for stat in product_stats:
        print(f"  {stat['name'][:50]:50s} {stat['count']:>4d}개")


if __name__ == "__main__":
    main()
