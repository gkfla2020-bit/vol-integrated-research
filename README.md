# When Correlations Break: Regime Shifts in Bond-Commodity-Bitcoin Nexus

채권-원자재-비트코인 간 관계의 구조적 변화 분석 (1995–2025)

웹 버전: https://gkfla2020-bit.github.io/research/vol-integrated-kr/

---

## 주요 결과

- 금융화 기간(2004-2021) 단기금리 평균회귀 반감기: 1,813일 → 2022년 긴축 후 169일
- BTC-SPX 상관관계: 2020년 0.020 → 2022년 이후 0.414
- BTC→SPX 전이효과: 18.0%

---

## 파일 구조

### 코드

| 파일 | 설명 |
|------|------|
| `vol_analysis.py` | 메인 분석. FRED/yfinance 데이터 수집 → Vasicek 평균회귀 추정 → DCC-GARCH(√ΔT 주말 보정) → Granger 인과검정 → VAR 전이효과 순서로 실행. 차트 6개와 JSON 결과 저장 |
| `vol_pipeline.py` | 분석 파이프라인 래퍼. vol_analysis.py 각 단계를 순서대로 호출하고 중간 결과 로깅 |
| `vol_generate_html.py` | JSON + 차트를 읽어 논문 형식 HTML 리포트 생성 |
| `main.py` | 프로젝트 파일 구조 안내 출력 (`python main.py`) |

### 데이터

| 파일 | 설명 |
|------|------|
| `data/vol_analysis_results.json` | 분석 수치 결과. Vasicek 파라미터, DCC 상관계수, 전이지수 등 |

### 차트

| 파일 | 설명 |
|------|------|
| `charts/vol_chart_vasicek.png` | Vasicek 평균회귀 속도(a) 및 반감기 추이. 금융화 기간 vs 긴축 전환 비교 |
| `charts/vol_chart_rolling_corr.png` | 채권-금, 채권-구리, 채권-WTI 롤링 상관관계 (252일 윈도우) |
| `charts/vol_chart_btc_rolling.png` | BTC-SPX, BTC-Gold DCC-GARCH 동적 상관관계. 2020년 이후 BTC 편입 과정 |
| `charts/vol_chart_monday_effect.png` | √ΔT 주말 보정 전후 BTC 변동성 비교. 월요일 더미 효과 검증 |
| `charts/vol_chart_spillover.png` | VAR 전이효과 히트맵. 레짐별(전체/금융화/긴축) 자산 간 충격 전달 강도 |
| `charts/vol_chart_bei_gold.png` | 손익분기 인플레이션(BEI)과 금 가격 관계. 인플레이션 헤지로서 금의 역할 변화 |

### 논문

| 파일 | 설명 |
|------|------|
| `paper/draft.md` | 논문 1차 초안. 연구 설계 및 방법론 초기 버전 |
| `paper/final.md` | 논문 최종본. 결론 및 기여 정리 완료 |
| `paper/vol_research_paper.html` | 수식·차트 포함 HTML 렌더링 버전 |

---

## 데이터 소스

- FRED API: DGS10, DFII10, DFF, DTB3
- Yahoo Finance: GC=F, CL=F, HG=F, ^VIX, ^GSPC, BTC-USD, DX-Y.NYB

## 실행

```bash
pip install pandas numpy yfinance arch statsmodels matplotlib scipy
python vol_analysis.py
```
