"""
네이버 데이터랩 API → trend.json 수집 스크립트

네이버 데이터랩 통합검색어 트렌드 API를 호출하여
5개 브랜드의 24개월 검색 트렌드를 수집합니다.

필수 환경변수:
  NAVER_CLIENT_ID: 네이버 개발자센터 Client ID
  NAVER_CLIENT_SECRET: 네이버 개발자센터 Client Secret

API 등록: https://developers.naver.com/apps/#/register
  - 사용 API: 데이터랩 (검색어트렌드)

사용법:
  export NAVER_CLIENT_ID=your_client_id_here
  export NAVER_CLIENT_SECRET=your_client_secret_here
  python scripts/collect-trend.py
"""

import json
import os
import sys
from datetime import datetime, timedelta

try:
    import requests
except ImportError:
    print("requests 패키지가 필요합니다: pip install requests")
    sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)

NAVER_CLIENT_ID = os.environ.get("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET")
DATALAB_URL = "https://openapi.naver.com/v1/datalab/search"


def load_config():
    with open(os.path.join(PROJECT_DIR, "config.json"), encoding="utf-8") as f:
        return json.load(f)


def get_trend_data(keywords_groups, start_date, end_date, time_unit="month"):
    """네이버 데이터랩 API 호출"""
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        print("ERROR: NAVER_CLIENT_ID, NAVER_CLIENT_SECRET 환경변수를 설정하세요.")
        print("  export NAVER_CLIENT_ID=your_client_id_here")
        print("  export NAVER_CLIENT_SECRET=your_client_secret_here")
        sys.exit(1)

    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
        "Content-Type": "application/json",
    }

    body = {
        "startDate": start_date,
        "endDate": end_date,
        "timeUnit": time_unit,
        "keywordGroups": keywords_groups,
    }

    resp = requests.post(DATALAB_URL, headers=headers, json=body)
    if resp.status_code != 200:
        print(f"API Error {resp.status_code}: {resp.text}")
        sys.exit(1)

    return resp.json()


def collect_trends():
    config = load_config()
    all_brands = [config["brand"]["name"]] + [c["name"] for c in config["competitors"]]

    # 24개월 전부터 오늘까지
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=config["analysis_period"]["trend_months"] * 30)).strftime("%Y-%m-%d")

    # 네이버 데이터랩: 최대 5개 키워드 그룹
    keyword_groups = [
        {"groupName": name, "keywords": [name]} for name in all_brands[:5]
    ]

    print(f"Collecting trend data: {start_date} ~ {end_date}")
    print(f"Brands: {', '.join(all_brands[:5])}")

    result = get_trend_data(keyword_groups, start_date, end_date)

    # 결과 변환
    monthly = {}
    for group in result.get("results", []):
        brand_name = group["title"]
        for point in group["data"]:
            period = point["period"][:7]  # "2024-03"
            if period not in monthly:
                monthly[period] = {"date": period}
            monthly[period][brand_name] = round(point["ratio"], 1)

    monthly_list = sorted(monthly.values(), key=lambda x: x["date"])

    output = {
        "meta": {
            "source": "네이버 데이터랩 API (상대값)",
            "collected_at": datetime.now().strftime("%Y-%m"),
            "period": f"{start_date[:7]} ~ {end_date[:7]} ({config['analysis_period']['trend_months']}개월)",
            "note": "상대값 100 = 기간 내 최대 검색량 월",
        },
        "monthly": monthly_list,
        "seasonality": {},  # TODO: 월별 평균 계산
    }

    output_path = os.path.join(PROJECT_DIR, "data", "trend.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\ntrend.json 생성 완료: {output_path}")
    print(f"데이터 포인트: {len(monthly_list)}개월")


if __name__ == "__main__":
    collect_trends()
