"""
AI SOV (Share of Voice) 측정 → ai-sov.json 생성

10개 질문 x 3개 AI 모델 x 10회 반복 = 300회 응답에서
브랜드 언급 빈도와 1순위 추천률을 측정합니다.

필수 환경변수:
  ANTHROPIC_API_KEY: Claude API
  OPENAI_API_KEY: OpenAI API
  GOOGLE_API_KEY: Gemini API

사용법:
  export ANTHROPIC_API_KEY=your_api_key_here
  export OPENAI_API_KEY=your_api_key_here
  export GOOGLE_API_KEY=your_api_key_here
  python scripts/test-ai-sov.py [--repeats 10]
"""

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)

QUESTIONS = [
    "한국에서 좋은 가구 브랜드 추천해줘",
    "30대 부부에게 맞는 소파 브랜드는?",
    "초등학생 책상 어디 브랜드가 좋아?",
    "가성비 좋은 가구 브랜드 알려줘",
    "가구 인테리어 브랜드 순위",
    "일룸과 한샘 중 어디가 나아?",
    "거실 소파 추천 브랜드",
    "아이방 꾸미기 추천 가구",
    "프리미엄 가구 브랜드 한국",
    "이사할때 가구 어디서 사?",
]

QUESTION_CONTEXTS = {
    0: "general_recommendation",
    1: "living_room",
    2: "kids_furniture",
    3: "value_for_money",
    4: "general_recommendation",
    5: "general_recommendation",
    6: "living_room",
    7: "kids_furniture",
    8: "general_recommendation",
    9: "general_recommendation",
}


def load_config():
    with open(os.path.join(PROJECT_DIR, "config.json"), encoding="utf-8") as f:
        return json.load(f)


def get_brands(config):
    return [config["brand"]["name"]] + [c["name"] for c in config["competitors"]]


def query_claude(question):
    """Claude API 호출"""
    try:
        import anthropic

        client = anthropic.Anthropic()
        resp = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=500,
            messages=[{"role": "user", "content": question}],
        )
        return resp.content[0].text
    except Exception as e:
        print(f"  Claude error: {e}")
        return ""


def query_openai(question):
    """OpenAI API 호출"""
    try:
        from openai import OpenAI

        client = OpenAI()
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": question}],
            max_tokens=500,
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"  OpenAI error: {e}")
        return ""


def query_gemini(question):
    """Gemini API 호출"""
    try:
        import google.generativeai as genai

        genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))
        model = genai.GenerativeModel("gemini-2.0-flash")
        resp = model.generate_content(question)
        return resp.text
    except Exception as e:
        print(f"  Gemini error: {e}")
        return ""


MODEL_FUNCTIONS = {
    "Claude-3.5": query_claude,
    "ChatGPT-4o": query_openai,
    "Gemini-Pro": query_gemini,
}


def extract_mentions(text, brands):
    """응답에서 브랜드 언급 추출"""
    mentions = []
    first_mention = None
    first_pos = len(text)

    for brand in brands:
        if brand in text:
            mentions.append(brand)
            pos = text.index(brand)
            if pos < first_pos:
                first_pos = pos
                first_mention = brand

    return mentions, first_mention


def main():
    parser = argparse.ArgumentParser(description="AI SOV 측정")
    parser.add_argument("--repeats", type=int, default=10, help="반복 횟수 (기본 10)")
    parser.add_argument(
        "--models",
        nargs="+",
        default=list(MODEL_FUNCTIONS.keys()),
        help="테스트할 모델",
    )
    args = parser.parse_args()

    config = load_config()
    brands = get_brands(config)
    models = [m for m in args.models if m in MODEL_FUNCTIONS]

    total_calls = len(QUESTIONS) * len(models) * args.repeats
    print(f"AI SOV 측정 시작")
    print(f"  질문: {len(QUESTIONS)}개")
    print(f"  모델: {', '.join(models)}")
    print(f"  반복: {args.repeats}회")
    print(f"  총 호출: {total_calls}회\n")

    # Results tracking
    mention_counts = defaultdict(lambda: defaultdict(int))  # model -> brand -> count
    first_rec_counts = defaultdict(lambda: defaultdict(int))  # model -> brand -> count
    context_mentions = defaultdict(lambda: defaultdict(int))  # context -> brand -> count
    total_per_model = defaultdict(int)
    context_totals = defaultdict(int)

    call_count = 0
    for repeat in range(args.repeats):
        for q_idx, question in enumerate(QUESTIONS):
            for model_name in models:
                call_count += 1
                print(
                    f"\r  [{call_count}/{total_calls}] {model_name} - Q{q_idx+1} (rep {repeat+1})",
                    end="",
                )

                query_fn = MODEL_FUNCTIONS[model_name]
                response = query_fn(question)
                total_per_model[model_name] += 1

                ctx = QUESTION_CONTEXTS.get(q_idx, "general_recommendation")
                context_totals[ctx] += 1

                mentions, first = extract_mentions(response, brands)

                for brand in mentions:
                    mention_counts[model_name][brand] += 1
                    context_mentions[ctx][brand] += 1

                if first:
                    first_rec_counts[model_name][first] += 1

                time.sleep(0.5)  # Rate limiting

    print(f"\n\n측정 완료! 결과 집계 중...\n")

    # Aggregate
    total_responses = sum(total_per_model.values())
    total_mention_all = defaultdict(int)
    total_first_all = defaultdict(int)

    for model in models:
        for brand in brands:
            total_mention_all[brand] += mention_counts[model][brand]
            total_first_all[brand] += first_rec_counts[model][brand]

    all_mentions = sum(total_mention_all.values())

    # Build output
    output = {
        "meta": {
            "source": "AI SOV 자동 측정 (scripts/test-ai-sov.py)",
            "collected_at": __import__("datetime").datetime.now().strftime("%Y-%m"),
            "methodology": f"{len(QUESTIONS)}개 질문 x {len(models)}개 AI모델 x {args.repeats}회 반복 = {total_responses}회 응답 분석",
            "models": models,
        },
        "questions": QUESTIONS,
        "mention_rate": {
            "description": f"전체 {total_responses}회 응답 중 브랜드 언급 비율",
            "brands": {},
        },
        "first_recommendation": {
            "description": f"1순위로 추천된 비율 (전체 {total_responses}회 중)",
            "brands": {},
        },
        "by_model": {},
        "by_context": {},
        "sov_score": {
            "description": "AI SOV = 언급 횟수 / 전체 브랜드 언급 x 100",
            "brands": {},
        },
    }

    for brand in brands:
        mc = total_mention_all[brand]
        fc = total_first_all[brand]
        output["mention_rate"]["brands"][brand] = {
            "mentions": mc,
            "rate": round(mc / total_responses, 2) if total_responses else 0,
        }
        output["first_recommendation"]["brands"][brand] = {
            "count": fc,
            "rate": round(fc / total_responses, 2) if total_responses else 0,
        }
        output["sov_score"]["brands"][brand] = (
            round(mc / all_mentions * 100, 1) if all_mentions else 0
        )

    for model in models:
        tm = total_per_model[model]
        output["by_model"][model] = {
            "mention_rate": {
                b: round(mention_counts[model][b] / tm, 2) if tm else 0
                for b in brands
            },
            "first_rec": {
                b: round(first_rec_counts[model][b] / tm, 2) if tm else 0
                for b in brands
            },
        }

    for ctx in set(QUESTION_CONTEXTS.values()):
        tc = context_totals[ctx]
        output["by_context"][ctx] = {
            b: round(context_mentions[ctx][b] / tc, 2) if tc else 0 for b in brands
        }

    output_path = os.path.join(PROJECT_DIR, "data", "ai-sov.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"ai-sov.json 저장 완료\n")

    # Summary
    print("=== AI SOV Summary ===")
    for brand in sorted(brands, key=lambda b: output["sov_score"]["brands"][b], reverse=True):
        sov = output["sov_score"]["brands"][brand]
        mr = output["mention_rate"]["brands"][brand]["rate"]
        fr = output["first_recommendation"]["brands"][brand]["rate"]
        print(f"  {brand:8s} | SOV: {sov:5.1f}% | 언급률: {mr:.0%} | 1순위: {fr:.0%}")


if __name__ == "__main__":
    main()
