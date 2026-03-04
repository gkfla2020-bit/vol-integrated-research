#!/usr/bin/env python3
"""
자산 동조화 및 거시적 전환점 분석 - 통합 연구 논문
멀티모델 파이프라인: Opus 4.5 초안 → Sonnet 4.5 피드백 → Opus 4.6 최종
바시첵 모델 + DCC-GARCH + 주말 변동성 보정 + BTC 통합
"""

import os
import json
from datetime import datetime
from anthropic import Anthropic

def load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip()

load_env()
api_key = os.environ.get("CLAUDE_API_KEY", "")
if not api_key:
    raise ValueError("CLAUDE_API_KEY not found")
client = Anthropic(api_key=api_key)

# 분석 결과 로드
with open("vol_analysis_results.json", "r", encoding="utf-8") as f:
    VOL_DATA = json.load(f)
with open("analysis_results.json", "r", encoding="utf-8") as f:
    BOND_DATA = json.load(f)
with open("btc_analysis_results.json", "r", encoding="utf-8") as f:
    BTC_DATA = json.load(f)


# ============================================================
# 분석 결과 요약 (프롬프트용)
# ============================================================

ANALYSIS_SUMMARY = """
=== 통합 분석 결과 요약 ===

[연구 주제]
자산 동조화 및 거시적 전환점 분석: 바시첵 모델, DCC-GARCH, 주말 변동성 보정을 활용한 채권-원자재-비트코인 통합 연구
기간: 2000-2025 (원자재-채권), 2014-2025 (BTC 포함)
데이터: FRED (DGS10, DFII10, DFF, DTB3) + Yahoo Finance (GC=F, CL=F, HG=F, ^VIX, ^GSPC, BTC-USD, DX-Y.NYB)

[1. 바시첵(Vasicek) 모델 추정 결과]
단기금리(3개월 T-Bill) 평균회귀 모형: dr = a(b-r)dt + σdW

전체 기간:
  a (평균회귀속도) = 0.000626
  b (장기평균) = 1.21%
  σ (변동성) = 0.0451
  반감기 = 1,108일 (약 4.4년)

기간별 변화:
  Pre-Financialization (1995-2003): a=0.00297, b=0.30%, 반감기=233일, 평균금리=2.41%
  Financialization (2004-2021): a=0.00038, b=0.69%, 반감기=1,813일, 평균금리=1.17%
  Post-2022 Tightening: a=0.00410, b=5.30%, 반감기=169일, 평균금리=4.04%

핵심 발견: 금융화 시기(2004-2021) 평균회귀 속도가 극도로 느려짐(반감기 1,813일 ≈ 7.2년)
→ 양적완화로 인한 금리 고착화. 2022년 이후 반감기 169일로 급격히 단축 → 정상화 가속

[2. 기초 통계량 (3기간)]
Financialization (2004-2021, N=1,831):
  Gold: 연율수익률 5.49%, vol 14.82% | WTI: 5.15%, vol 49.13%
  Copper: 5.32%, vol 21.18% | SPX: 12.62%, vol 17.88%
  BTC: 63.98%, vol 73.74%
  Gold-Bond 상관: -0.303 | WTI-Bond: 0.204 | Copper-Bond: 0.188
  BTC-SPX: 0.162 | BTC-Gold: 0.081 | BTC-Bond: 0.026
  Bond10Y 평균: 2.85% | BEI: 2.05% | VIX: 18.92

Post-2022 Tightening (N=793):
  Gold: 13.97%, vol 14.60% | WTI: -2.39%, vol 37.47%
  Copper: 0.42%, vol 23.73% | SPX: 7.07%, vol 17.31%
  BTC: 19.07%, vol 55.90%
  Gold-Bond 상관: -0.341 | WTI-Bond: 0.121 | Copper-Bond: -0.065
  BTC-SPX: 0.420 | BTC-Gold: 0.092 | BTC-Bond: -0.055
  Bond10Y 평균: 3.75% | BEI: 2.36% | VIX: 19.24

[3. DCC-GARCH 결과]
Gold-Bond: a=0.01, b=0.98 (높은 지속성)
  2004-2021: mean=-0.323 | 2022~: mean=-0.352 (음의 상관 심화)
WTI-Bond: a=0.01, b=0.84
  2004-2021: mean=0.208 | 2022~: mean=0.203 (안정적 양의 상관)
Copper-Bond: a=0.01, b=0.98
  2004-2021: mean=0.142 | 2022~: mean=0.025 (양→거의 0으로 약화)
BTC-Bond: a=0.01, b=0.50 (낮은 지속성)
  2004-2021: mean=0.008 | 2022~: mean=0.006 (거의 무상관)
BTC-Gold: a=0.01, b=0.98
  2004-2021: mean=0.082 | 2022~: mean=0.077
BTC-SPX: a=0.01, b=0.98
  2004-2021: mean=0.126 | 2022~: mean=0.258 (급격한 동조화)

[4. 주말/공휴일 변동성 보정 (√ΔT)]
월요일 변동성 비율 (월요일/비월요일):
  BTC: 1.38 (가장 큰 주말 효과 - 24/7 거래)
  SPX: 1.13 | WTI: 1.11 | Gold: 1.04 | Copper: 0.91 | DXY: 0.86
→ BTC는 주말에도 거래되므로 월요일 수익률에 주말 정보가 누적되지 않으나,
  전통자산은 금-토-일 3일치 정보가 월요일에 반영 → √3 보정 필요

[5. 구조변화 검정 (Fisher z-변환)]
유의한 구조변화:
  구리-채권 2020 (COVID): 0.204 → 0.000 (p=0.000) *** (양의 상관 완전 소멸)
  구리-채권 2022 (금리인상): 0.171 → -0.059 (p=0.000) *** (음의 상관으로 전환)
  WTI-채권 2020 (COVID): 0.238 → 0.126 (p=0.003) *** (양의 상관 약화)
  금-채권 2020 (COVID): -0.357 → -0.283 (p=0.036) ** (음의 상관 약화)
  BTC-채권 2022 (금리인상): 0.031 → -0.073 (p=0.016) ** (음의 상관으로 전환)
  BTC-SPX 2020 (COVID): 0.020 → 0.392 (p=0.000) *** (급격한 동조화)
  BTC-SPX 2022 (금리인상): 0.171 → 0.414 (p=0.000) *** (동조화 심화)
  BTC-SPX 2024 (ETF): 0.215 → 0.351 (p=0.019) ** (ETF 후 추가 강화)

[6. Granger 인과성]
주요 유의한 결과:
  Bond → Gold: F=17.35, p=0.000 (lag=1) *** (가장 강한 인과)
  BTC → WTI: F=5.23, p=0.000 (lag=5) *** (에너지 연결고리)
  VIX → SPX: F=8.40, p=0.000 (lag=4) ***
  VIX → Gold: F=5.73, p=0.017 (lag=1) **
  VIX → WTI: F=3.98, p=0.000 (lag=8) ***
  VIX → BTC: F=2.25, p=0.021 (lag=8) **
  BTC → SPX: F=3.44, p=0.032 (lag=2) **
  BTC → Copper: F=3.03, p=0.004 (lag=7) ***
  Gold → WTI: F=2.63, p=0.015 (lag=6) **
  Gold → Copper: F=2.24, p=0.037 (lag=6) **
  Copper → WTI: F=4.09, p=0.017 (lag=2) **
  Bond → Copper: F=2.97, p=0.003 (lag=8) ***
  Gold → Bond: F=2.85, p=0.009 (lag=6) ***

[7. VAR 전이효과 (Diebold-Yilmaz)]
전체 기간 (BTC 제외, 2000~): 전이지수=7.8%, lag=3
  Gold 자체설명력: 99.1% | Bond: 85.9% | Copper: 86.1%
  Gold → Bond: 9.8% (가장 큰 전이)

BTC 포함 (2014~): 전이지수=10.2%, lag=8
  BTC 자체설명력: 98.1% | SPX: 82.9%
  BTC → SPX: 5.1% | Gold → Bond: 10.2%

기간별 전이지수:
  Financialization (2004-2021): 9.8%
  Post-2022: 11.6% (BTC 제외) / 12.0% (BTC 포함)
  → 2022년 이후 시장 간 연계성 강화

2022~ BTC 포함 전이:
  BTC → SPX: 18.0% (급격히 증가!)
  Gold → Bond: 11.0% | Gold → Copper: 16.2%

[8. 위기 시기 상관관계]
COVID Crash (2020.02-04):
  Gold-Bond: -0.031 (음의 상관 소멸) | BTC-SPX: 0.571 | BTC-Gold: 0.258
Rate Hike (2022.03-12):
  Gold-Bond: -0.362 (음의 상관 강화) | BTC-SPX: 0.573 | BTC-Gold: 0.124
SVB Crisis (2023.03-04):
  Gold-Bond: -0.664 (극단적 음의 상관) | BTC-Gold: 0.370 | BTC-SPX: 0.096

[9. 기대인플레이션 (Breakeven Inflation)]
BEI 평균: 1995-2003: 1.96% | 2004-2021: 2.05% | 2022~: 2.36%
금-BEI 구조변화 2022: 상관 0.022 → 0.026 (p=0.924, 유의하지 않음)

=== 선행 연구 결과 통합 ===

[채권-원자재 연구 (1995-2025)]
- Gold-Bond DCC: 1995-2003 mean=-0.222, 2004-2021 mean=-0.184, 2022~ mean=-0.320
- 2022년 구조변화: 상관 -0.129 → -0.359 (Z=6.18, p=0.000) ***
- Bond→Gold Granger: F=25.53, p=0.000 | Gold→Bond: F=3.22, p=0.012
- 전이효과: Gold→Bond 12.4%, WTI→Bond 3.7%

[BTC 연구 (2014-2025)]
- BTC-SPX DCC: P1(2014-17) 0.032 → P2(2018-21) 0.144 → P3(2022-25) 0.294
- BTC-Gold DCC: 0.048 → 0.084 → 0.109 (점진적 강화)
- BTC→WTI Granger: F=4.74, p=0.001 ***
- 위기별: COVID BTC-SPX=0.487, SVB BTC-Gold=0.303
- BTC 자체설명력: 99.0% (가장 독립적)
"""

METHODOLOGY_GUIDE = """
[Google Docs 연구 방법론 가이드 핵심]

1. 바시첵 모델: dr = a(b-r)dt + σdW
   - 단기금리의 평균회귀 특성 분석
   - 기간별 파라미터 변화로 통화정책 레짐 식별
   - 반감기(half-life) = ln(2)/a로 정책 전환 속도 측정

2. DCC-GARCH with Monday Dummy:
   - 주말/공휴일 비거래일 보정: √ΔT 시간 조정
   - 월요일 더미 변수로 주말 정보 누적 효과 통제
   - BTC는 24/7 거래 → 전통자산과 다른 주말 패턴

3. 기대인플레이션 (Breakeven Inflation):
   - BEI = 명목금리(DGS10) - TIPS(DFII10)
   - 인플레이션 기대와 원자재 가격의 관계 분석

4. 구조변화 시점:
   - 2004: 금 ETF(GLD) 도입 → 원자재 금융화
   - 2008: 글로벌 금융위기
   - 2020: COVID-19 → 양적완화 극대화
   - 2022: 연준 금리인상 → 긴축 전환
   - 2024: BTC 현물 ETF 승인

5. 통합 분석 프레임워크:
   - 채권-원자재 동조화 (1995~) + BTC 편입 (2014~)
   - 거시적 전환점에서의 상관관계 구조변화
   - VIX → 자산 인과관계로 위험 전이 경로 식별
"""


def call_api(model, prompt, max_tokens):
    """API 호출 (Opus는 streaming)"""
    print(f"  [{model}] 호출 중...")
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


def step1_opus_draft():
    """Step 1: Opus 4.5가 초안 작성"""
    print("=" * 80)
    print("STEP 1: Claude Opus 4.5 - 통합 연구 논문 초안 작성")
    print("=" * 80)

    prompt = f"""당신은 금융경제학 분야의 최고 수준 연구자이다.

아래는 (1) 실제 데이터 분석 결과, (2) 연구 방법론 가이드이다.
이를 기반으로 완성도 높은 학술 논문 초안을 작성해야 한다.

{ANALYSIS_SUMMARY}

{METHODOLOGY_GUIDE}

[요구사항]
1. 위 실제 분석 결과의 수치를 정확히 반영한다. 수치를 임의로 변경하지 않는다.
2. 이 논문의 차별점은:
   (a) 바시첵 모델로 단기금리 평균회귀 특성의 기간별 변화를 분석 (기존 연구에 없음)
   (b) 주말/공휴일 변동성 보정(√ΔT)을 DCC-GARCH에 적용 (방법론적 기여)
   (c) 채권-원자재 동조화(1995~)와 BTC 편입(2014~)을 하나의 프레임워크로 통합
   (d) 기대인플레이션(BEI)을 매개변수로 활용
   (e) 거시적 전환점(2004 금융화, 2008 GFC, 2020 COVID, 2022 긴축)에서의 구조변화 체계적 분석
3. 실제 존재하는 논문만 인용한다 (가짜 인용 절대 금지)
4. 데이터 출처를 정확히 명시한다
5. 선행 연구 결과(채권-원자재, BTC)를 자연스럽게 통합한다

[논문 구조]
- Abstract (영문, 300단어 내외)
- 1. 서론 (연구 배경, 기여점, 가설 4-5개)
- 2. 문헌 검토 (채권-원자재 동조화, BTC 금융화, 변동성 모델링, 구조변화)
- 3. 방법론
  3.1 바시첵 모델 (수식, 추정 방법, 반감기)
  3.2 DCC-GARCH with 주말 보정 (수식, √ΔT, Monday dummy)
  3.3 구조변화 검정 (Fisher z-변환)
  3.4 Granger 인과성 및 VAR 전이효과
- 4. 데이터 및 기초 통계 (실제 수치 표 포함)
- 5. 실증 분석 결과
  5.1 바시첵 모델: 금리 레짐과 평균회귀
  5.2 DCC-GARCH: 시변 상관관계
  5.3 주말 변동성 보정 효과
  5.4 구조변화 검정
  5.5 Granger 인과성
  5.6 VAR 전이효과
- 6. 위기 시기 심층 분석 (COVID, 금리인상, SVB)
- 7. BTC 통합 분석 (금융화, 디지털 금, 에너지 연계)
- 8. 강건성 검정 및 추가 분석
- 9. 결론 및 시사점
- References

문체: 학술 논문체(~한다, ~이다, ~된다). 한국어 작성, 학술용어 영문 병기.
분량: 최소 8000자 이상, 상세하게."""

    return call_api("claude-opus-4-20250514", prompt, 16000)


def step2_sonnet_feedback(draft):
    """Step 2: Sonnet 4.5가 비판적 피드백"""
    print("\n" + "=" * 80)
    print("STEP 2: Claude Sonnet 4.5 - 비판적 피드백")
    print("=" * 80)

    prompt = f"""당신은 금융경제학 분야의 엄격한 학술 심사위원이다.

아래 논문은 실제 데이터 분석 결과를 기반으로 작성되었다. 철저히 검토하고 피드백을 제공한다.

[실제 분석 결과 (참고용)]
{ANALYSIS_SUMMARY}

[논문 초안]
{draft}

[심사 기준 - 각 10점, 총 100점]
1. 연구 질문의 독창성과 명확성
2. 바시첵 모델 활용의 적절성과 해석
3. DCC-GARCH 방법론 (주말 보정 포함)
4. 데이터 활용의 정확성 (실제 분석 수치와 일치하는가?)
5. 구조변화 분석의 깊이
6. BTC 통합 분석의 완성도
7. 논리적 일관성과 서사 구조
8. 문헌 검토의 충실도 (실제 논문 인용 여부)
9. 위기 시기 분석의 깊이
10. 실용적 가치 (포트폴리오/정책 시사점)

[출력]
각 항목별 점수 + 코멘트, 그리고:
- 총점: /100
- 핵심 강점 3가지
- 반드시 수정할 사항 5가지 (우선순위순)
- 추가 아이디어 3가지
- 삭제/축소할 부분

문체: ~한다, ~이다, ~된다"""

    return call_api("claude-sonnet-4-20250514", prompt, 8000)


def step3_opus_final(draft, feedback):
    """Step 3: Opus 4.6이 피드백 반영 최종본"""
    print("\n" + "=" * 80)
    print("STEP 3: Claude Opus 4.6 - 피드백 반영 최종본")
    print("=" * 80)

    prompt = f"""당신은 금융경제학 분야의 최고 수준 연구자이다.
아래는 당신이 작성한 초안과 심사위원 피드백이다. 피드백을 모두 반영하여 최종본을 작성한다.

[실제 분석 결과 (반드시 이 수치를 사용)]
{ANALYSIS_SUMMARY}

[초안]
{draft}

[심사위원 피드백]
{feedback}

[지시사항]
1. 심사위원의 '반드시 수정할 사항' 모두 반영
2. '추가 아이디어' 적절히 통합
3. '삭제/축소' 권고 반영
4. 점수 낮은 항목 집중 보강
5. 실제 분석 수치를 정확히 사용 (임의 변경 금지)
6. 실제 존재하는 논문만 인용
7. 바시첵 모델 해석을 더 깊이 있게 (통화정책 레짐 전환과 연결)
8. 주말 변동성 보정의 실무적 의미를 강조
9. BTC 통합 분석에서 '디지털 금' vs '위험자산' 이분법을 넘어선 해석
10. 포트폴리오 시사점을 구체적으로 (헤지 전략, 배분 비율 등)

마지막에 [피드백 반영 요약] 섹션 추가.

문체: ~한다, ~이다, ~된다. 한국어, 학술용어 영문 병기.
분량: 초안보다 더 길고 상세하게. 최소 10000자."""

    return call_api("claude-opus-4-20250514", prompt, 16000)


def main():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"=== 통합 연구 멀티모델 파이프라인 시작 ({ts}) ===\n")

    draft = step1_opus_draft()
    print(f"\n  초안 완료: {len(draft)}자\n")

    feedback = step2_sonnet_feedback(draft)
    print(f"\n  피드백 완료: {len(feedback)}자\n")

    final = step3_opus_final(draft, feedback)
    print(f"\n  최종본 완료: {len(final)}자\n")

    # 저장
    for name, content in [
        (f"vol_1_draft_{ts}.md", "# Step 1: Opus 4.5 초안\n\n" + draft),
        (f"vol_2_feedback_{ts}.md", "# Step 2: Sonnet 4.5 피드백\n\n" + feedback),
        (f"vol_3_final_{ts}.md", "# Step 3: Opus 4.6 최종본\n\n" + final),
        (f"vol_full_report_{ts}.md", f"# 통합 연구 멀티모델 파이프라인 결과\n생성: {ts}\n\n---\n## Phase 1: 초안 (Opus 4.5)\n\n{draft}\n\n---\n## Phase 2: 피드백 (Sonnet 4.5)\n\n{feedback}\n\n---\n## Phase 3: 최종본 (Opus 4.6)\n\n{final}"),
    ]:
        with open(name, "w", encoding="utf-8") as f:
            f.write(content)

    print(f"\n=== 파이프라인 완료! ===")
    print(f"  vol_1_draft_{ts}.md")
    print(f"  vol_2_feedback_{ts}.md")
    print(f"  vol_3_final_{ts}.md")
    print(f"  vol_full_report_{ts}.md")
    return ts, final


if __name__ == "__main__":
    main()
