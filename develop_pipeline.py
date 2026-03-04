#!/usr/bin/env python3
"""
논문 디벨롭 멀티모델 파이프라인
기존 논문의 특정 섹션을 Opus→Sonnet→Opus로 보완/확장

4가지 디벨롭 포인트:
1. 허점 보완 (Vasicek ZLB, 실질금리, 주말보정 정당화)
2. 확장 방향 (TVP-VAR, BTC 카멜레온 효과, 백테스팅)
3. 데이터 확장 (ETF Flow, 고빈도, GPR/EPU, On-chain)
4. 방법론 정교화 (Frequency-Domain Spillover, 비선형 Granger)
"""

import os
import json
from datetime import datetime
from anthropic import Anthropic

def load_env():
    # 상위 디렉토리의 .env도 확인
    for env_path in [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"),
    ]:
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        os.environ[key.strip()] = value.strip()
            break

load_env()
api_key = os.environ.get("CLAUDE_API_KEY", "")
if not api_key:
    raise ValueError("CLAUDE_API_KEY not found. .env 파일에 CLAUDE_API_KEY를 설정하세요.")
client = Anthropic(api_key=api_key)

# 기존 최종 논문 로드
FINAL_PAPER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "vol_3_final_20260208_231823.md")
with open(FINAL_PAPER_PATH, "r", encoding="utf-8") as f:
    EXISTING_PAPER = f.read()

# 분석 결과 로드
base_dir = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(base_dir, "vol_analysis_results.json"), "r", encoding="utf-8") as f:
    VOL_DATA = json.load(f)
with open(os.path.join(base_dir, "analysis_results.json"), "r", encoding="utf-8") as f:
    BOND_DATA = json.load(f)
with open(os.path.join(base_dir, "btc_analysis_results.json"), "r", encoding="utf-8") as f:
    BTC_DATA = json.load(f)


def call_api(model, prompt, max_tokens=16000):
    """API 호출"""
    print(f"\n  [{model}] 호출 중...")
    if "opus" in model:
        result = []
        with client.messages.stream(
            model=model, max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}]
        ) as stream:
            for text in stream.text_stream:
                result.append(text)
                print(text, end="", flush=True)
        print()
        return "".join(result)
    else:
        resp = client.messages.create(
            model=model, max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )
        text = resp.content[0].text
        print(text)
        return text



# ============================================================
# 디벨롭 포인트 정의
# ============================================================

DEVELOP_POINTS = {
    "round1": {
        "title": "허점 보완 (Logical Rigor)",
        "description": """
이 라운드에서는 기존 논문의 3가지 핵심 허점을 보완한다:

① Vasicek 모델의 한계와 ZLB(제로금리 하한) 문제
- 1995~2025년 데이터에는 장기 제로 금리 기간(2008~2021)이 포함
- Vasicek 모델은 금리가 음수로 내려갈 수 있고, 변동성이 금리 수준과 무관(sigma 상수)
- CIR 모델이나 Shadow Rate 모델(Wu-Xia)을 쓰지 않은 이유를 방어해야 함
- 양적완화 기간 분석을 위해 Shadow Rate 데이터 사용 또는 GARCH-Vasicek 결합 모형 고려
- 최소한 Vasicek을 선택한 이유(평균회귀 속도 a의 직관적 해석 중시 등)를 방법론에서 방어

② 실질금리(Real Yield) vs 명목금리
- 금은 명목금리가 아니라 실질금리(TIPS)에 반응
- 2022년 이후는 인플레이션 기대와 명목금리가 동시에 움직인 시기
- 10년물 TIPS(실질금리)와의 상관관계를 DCC-GARCH로 분석 추가
- 금의 안전자산 성격은 실질금리와의 역상관에서 기인

③ 주말 보정 방법론의 계량적 정당화
- sqrt(ΔT) 보정의 DCC-GARCH 수렴성과 통계적 일관성 증명
- 보정 전/후 모델의 Log-Likelihood, AIC/BIC 비교 표 제시
- 이 보정이 통계적 적합성을 높였음을 보여야 함
""",
    },
    "round2": {
        "title": "확장 방향성 (Expansion Strategy)",
        "description": """
이 라운드에서는 3가지 확장 방향을 추가한다:

① TVP-VAR (Time-Varying Parameter VAR) 도입
- 현재는 특정 시점 기준 Sub-sample 분석 → 레짐 변화는 점진적일 수 있음
- TVP-VAR로 전이효과(Spillover)가 매일 어떻게 변하는지 시계열로 보여줌
- "Regime Shift"라는 제목에 훨씬 부합하는 고차원 분석

② 비트코인의 '카멜레온 효과' 이론화
- SVB 사태 때 BTC가 금과 동조화된 현상을 'Liquidity vs. Hedge' 가설로 체계화
- "시장 전체 유동성 위기(COVID) 시 Risk-on 자산, 시스템적 신용 위기(SVB) 시 Alternative Safe-haven"
- 위기 유형별 BTC 역할 변화를 이론적으로 정립

③ 포트폴리오 성과 테스트 (Backtesting)
- 정적 자산배분(60/40) vs DCC-GARCH 시변 상관관계 반영 동적 자산배분(Dynamic MVP)
- 샤프 지수 비교로 연구 결과의 실무적 유용성 증명
""",
    },
    "round3": {
        "title": "데이터 확장 (Data-Driven Enrichment)",
        "description": """
이 라운드에서는 가격 데이터 외 동인(Driver) 데이터를 추가한다:

① 기관 자금 흐름 데이터 (ETF Flow)
- BTC-SPX 상관관계 급등의 원인을 '심리'가 아닌 '수급'으로 증명
- BlackRock(IBIT) 등 BTC 현물 ETF Net Inflow → DCC 변동 설명 회귀분석

② 고빈도 데이터 (High-Frequency Data)
- BTC 주말 수익률이 월요일 개장 전 전통자산 기대수익률에 선반영(Price Discovery)되는지
- 5분봉/1시간봉 데이터로 주말 보정(sqrt(ΔT))의 정당성 부여

③ 글로벌 불확실성 지수 (GPR & EPU)
- Geopolitical Risk Index, Economic Policy Uncertainty를 통제변수로
- 구리-채권 관계 붕괴가 '전쟁/공급망' vs '통화정책' 중 어디서 기인하는지 분리

④ On-chain 데이터 (BTC 특화)
- HODL Waves, 거래소 내 잔액 데이터
- 시장 구조적 레짐 변화가 Speculator→Investor 전환 과정임을 데이터로 입증
""",
    },
    "round4": {
        "title": "방법론적 정교화 (Methodological Sophistication)",
        "description": """
이 라운드에서는 2가지 고급 방법론을 추가한다:

① 주파수 영역 전이효과 (Frequency-Domain Spillover)
- 현재 Diebold-Yilmaz는 전 기간 통합 결과
- Baruník and Křehlík (2018) 방법론으로 단기(1~5일), 중기(5~20일), 장기(20일+) 분해
- 기대 결과: "BTC-주식 동조화는 단기 투기적 흐름에서 강하고, 금-채권은 장기 펀더멘탈에서 발생"

② 비선형 인과성 검정 (Non-linear Granger Causality)
- 전통 Granger는 선형 관계만 포착
- Diks and Panchenko (2006) 비선형 인과성 검정 추가
- "평시에는 무관한 자산들이 위기 시기에만 특정 방향으로 정보를 주고받는다" 입증
""",
    },
}


def run_develop_round(round_key, round_info):
    """하나의 디벨롭 라운드를 멀티모델로 실행"""
    title = round_info["title"]
    description = round_info["description"]

    print("\n" + "=" * 80)
    print(f"  ROUND: {title}")
    print("=" * 80)

    # Step 1: Opus 초안 - 해당 섹션 보완/확장 작성
    print(f"\n--- Step 1: Opus 4 초안 ({title}) ---")
    draft_prompt = f"""당신은 금융경제학 분야의 최고 수준 연구자이다.

아래는 기존에 작성된 논문이다:

{EXISTING_PAPER[:12000]}

[디벨롭 요청]
{description}

[지시사항]
1. 위 디벨롭 포인트를 반영하여, 기존 논문에 삽입/교체할 수 있는 형태로 새로운 섹션을 작성한다.
2. 기존 논문의 분석 수치는 그대로 유지하되, 새로운 분석 프레임워크와 해석을 추가한다.
3. 실제 존재하는 논문만 인용한다 (가짜 인용 절대 금지).
4. 각 포인트별로 명확한 소제목을 달아 기존 논문의 어디에 삽입할지 표시한다.
5. 수식이 필요한 경우 LaTeX 형식으로 작성한다.
6. 표(Table)가 필요한 경우 마크다운 표로 작성한다.

문체: 학술 논문체(~한다, ~이다, ~된다). 한국어 작성, 학술용어 영문 병기.
분량: 최소 4000자 이상, 상세하게."""

    draft = call_api("claude-opus-4-20250514", draft_prompt, 12000)

    # Step 2: Sonnet 피드백
    print(f"\n--- Step 2: Sonnet 4 피드백 ({title}) ---")
    feedback_prompt = f"""당신은 금융경제학 분야의 엄격한 학술 심사위원이다.

[기존 논문의 맥락]
{EXISTING_PAPER[:6000]}

[디벨롭 요청 사항]
{description}

[위 요청에 대해 작성된 초안]
{draft}

[심사 기준]
1. 디벨롭 요청 사항을 충실히 반영했는가?
2. 기존 논문과의 일관성이 유지되는가?
3. 수식과 방법론이 정확한가?
4. 인용이 실제 존재하는 논문인가?
5. 논리적 비약이 없는가?
6. 실무적 시사점이 충분한가?

[출력]
- 각 항목별 점수(10점 만점) + 코멘트
- 총점: /60
- 반드시 수정할 사항 3가지
- 추가 보완 아이디어 2가지

문체: ~한다, ~이다, ~된다"""

    feedback = call_api("claude-sonnet-4-20250514", feedback_prompt, 6000)

    # Step 3: Opus 최종본
    print(f"\n--- Step 3: Opus 4 최종본 ({title}) ---")
    final_prompt = f"""당신은 금융경제학 분야의 최고 수준 연구자이다.

[기존 논문]
{EXISTING_PAPER[:8000]}

[디벨롭 요청]
{description}

[초안]
{draft}

[심사위원 피드백]
{feedback}

[지시사항]
1. 심사위원의 '반드시 수정할 사항' 모두 반영
2. '추가 보완 아이디어' 적절히 통합
3. 기존 논문에 자연스럽게 삽입할 수 있는 형태로 최종 작성
4. 각 섹션 앞에 [삽입 위치: 기존 논문의 X.X 섹션 뒤/대체] 형태로 표시
5. 실제 존재하는 논문만 인용
6. 마지막에 [피드백 반영 요약] 추가

문체: ~한다, ~이다, ~된다. 한국어, 학술용어 영문 병기.
분량: 초안보다 더 상세하게. 최소 5000자."""

    final = call_api("claude-opus-4-20250514", final_prompt, 14000)

    return draft, feedback, final


def main():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"develop_{ts}")
    os.makedirs(output_dir, exist_ok=True)

    print(f"=== 논문 디벨롭 멀티모델 파이프라인 시작 ({ts}) ===")
    print(f"=== 출력 디렉토리: {output_dir} ===\n")

    all_results = {}

    for round_key in ["round1", "round2", "round3", "round4"]:
        round_info = DEVELOP_POINTS[round_key]
        print(f"\n{'#' * 80}")
        print(f"# {round_key.upper()}: {round_info['title']}")
        print(f"{'#' * 80}")

        draft, feedback, final = run_develop_round(round_key, round_info)
        all_results[round_key] = {
            "title": round_info["title"],
            "draft": draft,
            "feedback": feedback,
            "final": final,
        }

        # 라운드별 저장
        for step, content in [("1_draft", draft), ("2_feedback", feedback), ("3_final", final)]:
            path = os.path.join(output_dir, f"{round_key}_{step}.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"# {round_info['title']} - {step}\n\n{content}")

        print(f"\n  ✅ {round_key} 완료: draft={len(draft)}자, feedback={len(feedback)}자, final={len(final)}자")

    # 통합 리포트 저장
    full_report = f"# 논문 디벨롭 통합 리포트\n생성: {ts}\n\n"
    for rk, rv in all_results.items():
        full_report += f"\n{'=' * 60}\n## {rk}: {rv['title']}\n{'=' * 60}\n\n"
        full_report += f"### 초안 (Opus)\n\n{rv['draft']}\n\n"
        full_report += f"### 피드백 (Sonnet)\n\n{rv['feedback']}\n\n"
        full_report += f"### 최종본 (Opus)\n\n{rv['final']}\n\n"

    report_path = os.path.join(output_dir, "full_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(full_report)

    print(f"\n{'=' * 80}")
    print(f"=== 전체 파이프라인 완료! ===")
    print(f"=== 출력: {output_dir}/ ===")
    print(f"  - round1~4 각 3파일 (draft/feedback/final)")
    print(f"  - full_report.md (통합)")
    print(f"{'=' * 80}")

    return output_dir


if __name__ == "__main__":
    main()
