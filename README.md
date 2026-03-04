# When Correlations Break: Regime Shifts in Bond-Commodity-Bitcoin Nexus

채권-원자재-비트코인 간 관계의 구조적 변화 분석 (1995–2025)

**웹 버전**: https://gkfla2020-bit.github.io/research/vol-integrated-kr/

## 주요 결과

- 금융화 기간(2004-2021) 단기금리 평균회귀 반감기: 1,813일 → 2022년 긴축 후 169일
- BTC-SPX 상관관계: 2020년 0.020 → 2022년 이후 0.414
- BTC→SPX 전이효과: 18.0%

## 구조

```
├── vol_analysis.py                  # 메인 분석 (Vasicek + DCC-GARCH + VAR)
├── vol_pipeline.py                  # 파이프라인
├── vol_generate_html.py             # HTML 생성
├── data/
│   └── vol_analysis_results.json   # 분석 결과
├── charts/                          # 차트 6개
└── paper/
    ├── draft.md
    ├── final.md
    └── vol_research_paper.html
```

## 데이터 소스

- FRED API: DGS10, DFII10, DFF, DTB3
- Yahoo Finance: GC=F, CL=F, HG=F, ^VIX, ^GSPC, BTC-USD, DX-Y.NYB

## 실행

```bash
pip install pandas numpy yfinance arch statsmodels matplotlib scipy
python vol_analysis.py
```
