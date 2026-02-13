"""
네이버 검색광고 API를 이용한 브랜드 검색량 수집

기능:
  1. 5개 브랜드 월간 검색량 (PC/Mobile) 자동 수집
  2. 연관키워드 수집 (--related 옵션)
  3. search-volume.json 자동 갱신 (기존 historical 보존)

사용법:
  # 브랜드 검색량만 수집
  python scripts/collect-search-volume.py

  # 연관키워드도 함께 수집 (data/related-keywords.json 저장)
  python scripts/collect-search-volume.py --related

  # 수동 모드 (API 없이 직접 입력)
  python scripts/collect-search-volume.py --manual

필요 환경변수 (.env):
  NAVER_AD_CUSTOMER_ID
  NAVER_AD_API_KEY
  NAVER_AD_SECRET
"""

import json
import os
import sys
import time
import hmac
import hashlib
import base64
from datetime import datetime
from urllib.parse import urlencode

try:
    import requests
except ImportError:
    print("requests 패키지가 필요합니다: pip install requests")
    sys.exit(1)

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

# --------------------------------------------------
# 경로 설정
# --------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)

# .env 로드
env_path = os.path.join(PROJECT_DIR, ".env")
if load_dotenv:
    load_dotenv(env_path)
else:
    # python-dotenv 없으면 수동 파싱
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip()

# Config 로드
with open(os.path.join(PROJECT_DIR, "config.json"), encoding="utf-8") as f:
    config = json.load(f)

# API 설정
BASE_URL = "https://api.naver.com"
CUSTOMER_ID = os.environ.get("NAVER_AD_CUSTOMER_ID", "")
API_KEY = os.environ.get("NAVER_AD_API_KEY", "")
SECRET_KEY = os.environ.get("NAVER_AD_SECRET", "")


# --------------------------------------------------
# 인증
# --------------------------------------------------
def generate_signature(timestamp, method, uri):
    """HMAC-SHA256 서명 생성"""
    message = f"{timestamp}.{method}.{uri}"
    sign = hmac.new(
        SECRET_KEY.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    )
    return base64.b64encode(sign.digest()).decode("utf-8")


def get_headers(method, uri):
    """API 요청 헤더 생성"""
    timestamp = str(int(time.time() * 1000))
    signature = generate_signature(timestamp, method, uri)
    return {
        "Content-Type": "application/json; charset=UTF-8",
        "X-Timestamp": timestamp,
        "X-API-KEY": API_KEY,
        "X-Customer": str(CUSTOMER_ID),
        "X-Signature": signature,
    }


# --------------------------------------------------
# API 호출
# --------------------------------------------------
def fetch_keyword_stats(keywords):
    """
    키워드도구 API 호출 - 키워드별 검색량 조회

    Args:
        keywords: 쉼표 구분 키워드 문자열 또는 리스트

    Returns:
        keywordList (list of dict)
    """
    if isinstance(keywords, list):
        keywords = ",".join(keywords)

    uri = "/keywordstool"
    method = "GET"
    # API는 hintKeywords에 공백을 허용하지 않음 → 공백 제거
    keywords_cleaned = keywords.replace(" ", "")

    params = {
        "hintKeywords": keywords_cleaned,
        "showDetail": "1",
    }

    headers = get_headers(method, uri)

    resp = requests.get(BASE_URL + uri, params=params, headers=headers, timeout=30)

    if resp.status_code != 200:
        print(f"  API 오류 [{resp.status_code}]: {resp.text}")
        return []

    data = resp.json()
    return data.get("keywordList", [])


def parse_volume(value):
    """검색량 값 파싱 ('< 10' 처리)"""
    if isinstance(value, str):
        if "<" in value:
            return 5  # '< 10' → 5로 추정
        try:
            return int(value.replace(",", ""))
        except ValueError:
            return 0
    return int(value) if value else 0


# --------------------------------------------------
# 브랜드 검색량 수집
# --------------------------------------------------
def collect_brand_volumes():
    """5개 브랜드 검색량 수집"""
    brand_name = config["brand"]["name"]
    all_brands = [brand_name] + [c["name"] for c in config["competitors"]]

    print(f"브랜드 검색량 수집 중... ({len(all_brands)}개 브랜드)")
    print(f"  대상: {', '.join(all_brands)}")

    # 한 번에 조회 (쉼표 구분)
    keyword_list = fetch_keyword_stats(all_brands)

    if not keyword_list:
        print("  API 응답이 비어있습니다.")
        return None

    # 브랜드명 정확 매칭으로 검색량 추출
    brands_data = {}
    for brand in all_brands:
        matched = None
        for kw in keyword_list:
            if kw.get("relKeyword") == brand:
                matched = kw
                break

        if matched:
            pc = parse_volume(matched.get("monthlyPcQcCnt", 0))
            mobile = parse_volume(matched.get("monthlyMobileQcCnt", 0))
            brands_data[brand] = {
                "pc": pc,
                "mobile": mobile,
                "total": pc + mobile,
            }
            print(f"  {brand}: PC {pc:,} + Mobile {mobile:,} = {pc + mobile:,}")
        else:
            print(f"  {brand}: 정확히 일치하는 키워드 없음 (연관 결과만 반환됨)")
            # 연관 결과 중 가장 유사한 것 찾기
            for kw in keyword_list:
                if brand in kw.get("relKeyword", ""):
                    pc = parse_volume(kw.get("monthlyPcQcCnt", 0))
                    mobile = parse_volume(kw.get("monthlyMobileQcCnt", 0))
                    brands_data[brand] = {
                        "pc": pc,
                        "mobile": mobile,
                        "total": pc + mobile,
                    }
                    print(f"    -> '{kw['relKeyword']}' 사용: {pc + mobile:,}")
                    break

    return brands_data


# --------------------------------------------------
# 연관키워드 수집
# --------------------------------------------------
def collect_related_keywords():
    """config의 keyword_seeds로 연관키워드 수집"""
    seeds = config.get("keyword_seeds", [])
    if not seeds:
        seeds = [config["brand"]["name"]]

    print(f"\n연관키워드 수집 중... (시드: {len(seeds)}개)")

    all_keywords = {}

    for seed in seeds:
        print(f"  '{seed}' 조회중...")
        keyword_list = fetch_keyword_stats(seed)
        time.sleep(0.2)  # API 부하 방지

        for kw in keyword_list:
            rel = kw.get("relKeyword", "")
            if rel and rel not in all_keywords:
                pc = parse_volume(kw.get("monthlyPcQcCnt", 0))
                mobile = parse_volume(kw.get("monthlyMobileQcCnt", 0))
                all_keywords[rel] = {
                    "keyword": rel,
                    "pc": pc,
                    "mobile": mobile,
                    "total": pc + mobile,
                    "competition": kw.get("compIdx", ""),
                    "source_seed": seed,
                }

        print(f"    -> {len(keyword_list)}개 반환 (누적: {len(all_keywords)}개)")

    # 검색량 내림차순 정렬
    sorted_keywords = sorted(
        all_keywords.values(), key=lambda x: x["total"], reverse=True
    )

    # 저장
    output = {
        "meta": {
            "source": "네이버 검색광고 API (keywordstool)",
            "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "seed_keywords": seeds,
            "total_keywords": len(sorted_keywords),
        },
        "keywords": sorted_keywords,
    }

    output_path = os.path.join(PROJECT_DIR, "data", "related-keywords.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n  related-keywords.json 저장 완료: {len(sorted_keywords)}개 키워드")
    print(f"  상위 10개:")
    for kw in sorted_keywords[:10]:
        print(f"    {kw['keyword']}: {kw['total']:,}")

    return sorted_keywords


# --------------------------------------------------
# search-volume.json 갱신
# --------------------------------------------------
def update_search_volume_json(brands_data):
    """기존 JSON의 historical을 보존하면서 current 갱신"""
    output_path = os.path.join(PROJECT_DIR, "data", "search-volume.json")
    current_month = datetime.now().strftime("%Y-%m")

    # 기존 데이터 로드
    existing = {}
    if os.path.exists(output_path):
        with open(output_path, encoding="utf-8") as f:
            existing = json.load(f)

    historical = existing.get("historical", [])
    demographics = existing.get("demographics", {})

    # 현재 데이터가 이미 historical에 있으면 교체, 없으면 추가
    existing_months = [h["date"] for h in historical]
    new_history_entry = {
        "date": current_month,
        "brands": {name: {"total": d["total"]} for name, d in brands_data.items()},
    }

    if current_month in existing_months:
        idx = existing_months.index(current_month)
        historical[idx] = new_history_entry
    else:
        historical.append(new_history_entry)

    # 날짜순 정렬
    historical.sort(key=lambda x: x["date"])

    # 출력 구성
    output = {
        "meta": {
            "source": "네이버 검색광고 API (keywordstool)",
            "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "note": "자동 수집 (collect-search-volume.py)",
        },
        "current": {
            "date": current_month,
            "brands": brands_data,
        },
        "historical": historical,
        "demographics": demographics if demographics else {
            "source": "네이버 데이터랩 쇼핑인사이트 (수동 확인 필요)",
            "gender": {},
            "age": {},
            "device": {},
        },
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # Summary
    total_all = sum(b["total"] for b in brands_data.values())
    brand_name = config["brand"]["name"]
    brand_total = brands_data.get(brand_name, {}).get("total", 0)
    sos = (brand_total / total_all * 100) if total_all > 0 else 0

    print(f"\nsearch-volume.json 갱신 완료")
    print(f"  {brand_name} SOS: {sos:.1f}%")
    print(f"  {brand_name} 검색량: {brand_total:,}")
    print(f"  전체 시장: {total_all:,}")
    print(f"  히스토리: {len(historical)}개월")


# --------------------------------------------------
# 수동 모드 (기존 호환)
# --------------------------------------------------
def manual_mode():
    """API 없이 수동 데이터 입력"""
    print("수동 모드: 마피아넷 조회 결과를 입력하세요")
    brand_name = config["brand"]["name"]
    all_brands = [brand_name] + [c["name"] for c in config["competitors"]]

    brands_data = {}
    for brand in all_brands:
        print(f"\n  {brand}:")
        try:
            pc = int(input("    PC 검색량: ").replace(",", ""))
            mobile = int(input("    Mobile 검색량: ").replace(",", ""))
        except (ValueError, EOFError):
            print("    건너뜀")
            continue
        brands_data[brand] = {"pc": pc, "mobile": mobile, "total": pc + mobile}

    if brands_data:
        update_search_volume_json(brands_data)


# --------------------------------------------------
# 메인
# --------------------------------------------------
def main():
    # API 키 확인
    if "--manual" in sys.argv:
        manual_mode()
        return

    if not all([CUSTOMER_ID, API_KEY, SECRET_KEY]):
        print("환경변수가 설정되지 않았습니다.")
        print("  .env 파일에 다음을 설정하세요:")
        print("    NAVER_AD_CUSTOMER_ID=...")
        print("    NAVER_AD_API_KEY=...")
        print("    NAVER_AD_SECRET=...")
        print("\n수동 모드로 전환하려면: python collect-search-volume.py --manual")
        sys.exit(1)

    print("=" * 50)
    print("네이버 검색광고 API - 브랜드 검색량 수집")
    print("=" * 50)

    # 1. 브랜드 검색량 수집
    brands_data = collect_brand_volumes()
    if brands_data:
        update_search_volume_json(brands_data)

    # 2. 연관키워드 수집 (옵션)
    if "--related" in sys.argv:
        collect_related_keywords()

    print("\n완료!")


if __name__ == "__main__":
    main()
