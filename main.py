"""
vol-integrated-research
=======================
채권-원자재-비트코인 레짐 전환 분석 프로젝트 구조 안내

실행:
    python main.py          # 이 안내 출력
    python vol_analysis.py  # 실제 분석 실행
"""

import os

FILES = {
    # ── 코드 ──────────────────────────────────────────────────────────────
    "vol_analysis.py": (
        "메인 분석 스크립트. "
        "FRED/yfinance에서 데이터를 받아 "
        "① Vasicek 평균회귀 추정, "
        "② DCC-GARCH(√ΔT 주말 보정), "
        "③ Granger 인과검정, "
        "④ VAR 전이효과(Spillover Index) 순서로 분석하고 "
        "차트 6개와 JSON 결과를 저장한다."
    ),
    "vol_pipeline.py": (
        "분석 파이프라인 래퍼. "
        "vol_analysis.py의 각 단계를 순서대로 호출하고 "
        "중간 결과를 로깅한다."
    ),
    "vol_generate_html.py": (
        "분석 결과(JSON + 차트)를 읽어 "
        "논문 형식의 HTML 리포트를 생성한다."
    ),

    # ── 데이터 ────────────────────────────────────────────────────────────
    "data/vol_analysis_results.json": (
        "vol_analysis.py 실행 결과. "
        "Vasicek 파라미터, DCC 상관계수, 전이지수 등 "
        "수치 결과가 JSON으로 저장되어 있다."
    ),

    # ── 차트 ──────────────────────────────────────────────────────────────
    "charts/vol_chart_vasicek.png": (
        "Vasicek 모델 평균회귀 속도(a) 및 반감기 추이. "
        "금융화 기간(2004-2021)과 긴축 전환(2022~) 비교."
    ),
    "charts/vol_chart_rolling_corr.png": (
        "채권-금, 채권-구리, 채권-WTI 롤링 상관관계 (252일 윈도우)."
    ),
    "charts/vol_chart_btc_rolling.png": (
        "BTC-SPX, BTC-Gold DCC-GARCH 동적 상관관계. "
        "2020년 이후 BTC 금융시장 편입 과정을 시각화."
    ),
    "charts/vol_chart_monday_effect.png": (
        "√ΔT 주말 보정 전후 BTC 변동성 비교. "
        "월요일 더미 효과 검증."
    ),
    "charts/vol_chart_spillover.png": (
        "VAR 기반 전이효과(Spillover Index) 히트맵. "
        "레짐별(전체/금융화/긴축) 자산 간 충격 전달 강도."
    ),
    "charts/vol_chart_bei_gold.png": (
        "손익분기 인플레이션(BEI = 10Y - TIPS)과 금 가격 관계. "
        "인플레이션 헤지 자산으로서 금의 역할 변화."
    ),

    # ── 논문 ──────────────────────────────────────────────────────────────
    "paper/draft.md": (
        "논문 1차 초안 (Markdown). "
        "연구 설계 및 방법론 초기 버전."
    ),
    "paper/final.md": (
        "논문 최종본 (Markdown). "
        "결론 및 기여 정리 완료본."
    ),
    "paper/vol_research_paper.html": (
        "논문 HTML 렌더링 버전. "
        "수식·차트 포함 웹 뷰어용."
    ),
}

def main():
    print("=" * 60)
    print("vol-integrated-research  파일 구조")
    print("=" * 60)

    current_section = None
    section_map = {
        "vol_": "[ 코드 ]",
        "data/": "[ 데이터 ]",
        "charts/": "[ 차트 ]",
        "paper/": "[ 논문 ]",
    }

    for path, desc in FILES.items():
        # 섹션 헤더
        for prefix, label in section_map.items():
            if path.startswith(prefix) and current_section != label:
                current_section = label
                print(f"\n{label}")
                break

        exists = "✓" if os.path.exists(path) else "✗"
        print(f"  {exists}  {path}")
        print(f"       {desc}")

    print("\n" + "=" * 60)
    print("분석 실행:  python vol_analysis.py")
    print("HTML 생성:  python vol_generate_html.py")
    print("=" * 60)

if __name__ == "__main__":
    main()
