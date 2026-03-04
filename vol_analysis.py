#!/usr/bin/env python3
"""
자산 동조화 및 거시적 전환점 분석 - 변동성 정교화 버전
바시첵 모델 + GARCH-MIDAS + 주말 변동성 처리 + BTC 통합
"""

import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime
import json

print("=" * 70)
print("자산 동조화 및 거시적 전환점 분석 (변동성 정교화)")
print("=" * 70)

# ============================================================
# 1. 데이터 수집
# ============================================================
print("\n[1/8] 데이터 수집 중...")

START = "1995-01-01"
END = "2025-03-01"

def get_fred(series_id, start=START, end=END):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={start}&coed={end}"
    try:
        df = pd.read_csv(url, parse_dates=['observation_date'], index_col='observation_date')
        df.index.name = 'DATE'
        df.columns = [series_id]
        df[series_id] = pd.to_numeric(df[series_id], errors='coerce')
        return df
    except Exception as e:
        print(f"  FRED {series_id} 실패: {e}")
        return None

# FRED 시리즈
fred_series = {
    'DGS10': '10년 국채',
    'DFII10': '10년 TIPS (실질금리)',
    'DFF': '연방기금금리',
    'DTB3': '3개월 T-Bill',
}

fred_data = {}
for sid, name in fred_series.items():
    df = get_fred(sid)
    if df is not None and len(df) > 0:
        fred_data[sid] = df
        print(f"  ✓ {name} ({sid}): {len(df)} obs")
    else:
        print(f"  ✗ {name} ({sid}): 실패")

# Yahoo Finance
yf_tickers = {
    'GC=F': '금 선물',
    'CL=F': 'WTI 선물',
    'HG=F': '구리 선물',
    '^VIX': 'VIX',
    '^GSPC': 'S&P 500',
    '^TNX': '10년 국채 수익률',
    'BTC-USD': '비트코인',
    'DX-Y.NYB': '달러 인덱스',
}

yf_data = {}
for ticker, name in yf_tickers.items():
    try:
        df = yf.download(ticker, start=START, end=END, progress=False, auto_adjust=True)
        if len(df) > 0:
            if isinstance(df.columns, pd.MultiIndex):
                close_col = df[('Close', ticker)]
            else:
                close_col = df['Close']
            yf_data[ticker] = pd.DataFrame({ticker: close_col})
            print(f"  ✓ {name} ({ticker}): {len(df)} obs")
    except Exception as e:
        print(f"  ✗ {name} ({ticker}): {e}")


# ============================================================
# 2. 데이터 병합 및 전처리
# ============================================================
print("\n[2/8] 데이터 전처리...")

assets = pd.DataFrame()

# 가격 데이터
for ticker, col_name in [('GC=F', 'Gold'), ('CL=F', 'WTI'), ('HG=F', 'Copper'),
                          ('^GSPC', 'SPX'), ('BTC-USD', 'BTC'), ('DX-Y.NYB', 'DXY')]:
    if ticker in yf_data:
        assets[col_name] = yf_data[ticker][ticker]

# 금리 데이터
if 'DGS10' in fred_data:
    assets['Bond10Y'] = fred_data['DGS10']['DGS10']
elif '^TNX' in yf_data:
    assets['Bond10Y'] = yf_data['^TNX']['^TNX']

if 'DFII10' in fred_data:
    assets['TIPS10Y'] = fred_data['DFII10']['DFII10']
if 'DFF' in fred_data:
    assets['FedFunds'] = fred_data['DFF']['DFF']
if 'DTB3' in fred_data:
    assets['TBill3M'] = fred_data['DTB3']['DTB3']
if '^VIX' in yf_data:
    assets['VIX'] = yf_data['^VIX']['^VIX']

assets = assets.sort_index().ffill().dropna(how='all')

# 기대인플레이션 = 명목금리 - TIPS
if 'Bond10Y' in assets.columns and 'TIPS10Y' in assets.columns:
    assets['BreakevenInflation'] = assets['Bond10Y'] - assets['TIPS10Y']

print(f"  병합 데이터: {assets.shape[0]} obs, {assets.shape[1]} 변수")
print(f"  기간: {assets.index.min().date()} ~ {assets.index.max().date()}")

# 로그 수익률
price_cols = [c for c in ['Gold', 'WTI', 'Copper', 'SPX', 'BTC', 'DXY'] if c in assets.columns]
returns = np.log(assets[price_cols] / assets[price_cols].shift(1))

# 국채 수익률 변화
if 'Bond10Y' in assets.columns:
    returns['Bond10Y_chg'] = assets['Bond10Y'].diff()

returns = returns.dropna()

# 주말/공휴일 더미 변수
returns['DayOfWeek'] = returns.index.dayofweek
returns['Monday'] = (returns['DayOfWeek'] == 0).astype(int)

# 시간 간격 계산 (주말 보정용)
returns['DeltaT'] = 1.0
date_diff = pd.Series(returns.index).diff().dt.days.values
returns.iloc[1:, returns.columns.get_loc('DeltaT')] = date_diff[1:]
returns['SqrtDeltaT'] = np.sqrt(returns['DeltaT'])

print(f"  수익률 데이터: {returns.shape[0]} obs")
print(f"  월요일 관측치: {returns['Monday'].sum()}")

# ============================================================
# 3. 바시첵(Vasicek) 모델 추정
# ============================================================
print("\n[3/8] 바시첵 모델 추정...")

results = {}

# 단기 금리 (3개월 T-Bill 또는 Fed Funds)
rate_col = None
if 'TBill3M' in assets.columns:
    rate_col = 'TBill3M'
elif 'FedFunds' in assets.columns:
    rate_col = 'FedFunds'

if rate_col:
    rate = assets[rate_col].dropna()
    
    # Vasicek: dr = a(b - r)dt + σdW
    # 이산화: r(t+1) - r(t) = a(b - r(t))Δt + σ√Δt * ε
    # OLS: Δr = α + β*r(t) + ε → a = -β, b = -α/β, σ = std(ε)/√Δt
    
    dr = rate.diff().dropna()
    r_lag = rate.shift(1).dropna()
    
    # 공통 인덱스
    common_idx = dr.index.intersection(r_lag.index)
    dr = dr[common_idx]
    r_lag = r_lag[common_idx]
    
    from numpy.linalg import lstsq
    X = np.column_stack([np.ones(len(r_lag)), r_lag.values])
    y = dr.values
    
    beta_hat, _, _, _ = lstsq(X, y, rcond=None)
    alpha_ols, beta_ols = beta_hat
    
    a_vasicek = -beta_ols  # 평균 회귀 속도
    b_vasicek = -alpha_ols / beta_ols if beta_ols != 0 else 0  # 장기 평균
    residuals = y - X @ beta_hat
    sigma_vasicek = np.std(residuals)
    
    # 반감기 (half-life)
    half_life = np.log(2) / a_vasicek if a_vasicek > 0 else np.inf
    
    print(f"  Vasicek 파라미터 ({rate_col}):")
    print(f"    a (평균회귀속도) = {a_vasicek:.6f}")
    print(f"    b (장기평균) = {b_vasicek:.4f}%")
    print(f"    σ (변동성) = {sigma_vasicek:.6f}")
    print(f"    반감기 = {half_life:.1f}일")
    
    results['vasicek'] = {
        'a': round(float(a_vasicek), 6),
        'b': round(float(b_vasicek), 4),
        'sigma': round(float(sigma_vasicek), 6),
        'half_life': round(float(half_life), 1),
        'rate_variable': rate_col,
    }
    
    # 평균 회귀 이탈도 (deviation from long-run mean)
    assets['Vasicek_Deviation'] = assets[rate_col] - b_vasicek
    
    # 기간별 Vasicek 파라미터
    periods_vasicek = {
        'Pre-Financialization (1995-2003)': ('1995-01-01', '2003-12-31'),
        'Financialization (2004-2021)': ('2004-01-01', '2021-12-31'),
        'Post-2022': ('2022-01-01', '2025-12-31'),
    }
    
    results['vasicek_by_period'] = {}
    for pname, (s, e) in periods_vasicek.items():
        mask = (rate.index >= s) & (rate.index <= e)
        sub_rate = rate[mask]
        if len(sub_rate) > 100:
            sub_dr = sub_rate.diff().dropna()
            sub_lag = sub_rate.shift(1).dropna()
            ci = sub_dr.index.intersection(sub_lag.index)
            sub_dr = sub_dr[ci]
            sub_lag = sub_lag[ci]
            
            X_sub = np.column_stack([np.ones(len(sub_lag)), sub_lag.values])
            y_sub = sub_dr.values
            b_sub, _, _, _ = lstsq(X_sub, y_sub, rcond=None)
            
            a_sub = -b_sub[1]
            b_mean_sub = -b_sub[0] / b_sub[1] if b_sub[1] != 0 else 0
            res_sub = y_sub - X_sub @ b_sub
            sig_sub = np.std(res_sub)
            hl_sub = np.log(2) / a_sub if a_sub > 0 else np.inf
            
            results['vasicek_by_period'][pname] = {
                'a': round(float(a_sub), 6),
                'b': round(float(b_mean_sub), 4),
                'sigma': round(float(sig_sub), 6),
                'half_life': round(float(hl_sub), 1),
                'mean_rate': round(float(sub_rate.mean()), 4),
            }
            print(f"    {pname}: a={a_sub:.6f}, b={b_mean_sub:.2f}%, HL={hl_sub:.0f}일")


# ============================================================
# 4. DCC-GARCH with Monday Dummy (주말 변동성 보정)
# ============================================================
print("\n[4/8] DCC-GARCH 분석 (주말 보정)...")

from arch import arch_model

# 분석 대상 자산쌍
asset_pairs = [
    ('Gold', 'Bond10Y_chg', '금-채권'),
    ('WTI', 'Bond10Y_chg', 'WTI-채권'),
    ('Copper', 'Bond10Y_chg', '구리-채권'),
]

# BTC 포함 (2014~ 데이터만)
btc_start = '2014-09-17'
btc_pairs = [
    ('BTC', 'Bond10Y_chg', 'BTC-채권'),
    ('BTC', 'Gold', 'BTC-금'),
    ('BTC', 'SPX', 'BTC-주식'),
]

# 기간 구분
periods = {
    'Pre-Financialization (1995-2003)': ('1995-01-01', '2003-12-31'),
    'Financialization (2004-2021)': ('2004-01-01', '2021-12-31'),
    'Post-2022 Tightening': ('2022-01-01', '2025-12-31'),
}

results['dcc_garch'] = {}

def run_dcc_pair(ret_df, col1, col2, pair_name, monday_col=None):
    """DCC-GARCH 추정 (Monday dummy 포함 가능)"""
    data = ret_df[[col1, col2]].dropna()
    if len(data) < 200:
        return None
    
    # 개별 GARCH(1,1) 추정
    garch_params = {}
    std_resids = pd.DataFrame(index=data.index)
    cond_vols = pd.DataFrame(index=data.index)
    
    for col in [col1, col2]:
        y = data[col] * 100 if data[col].std() < 0.1 else data[col]
        try:
            am = arch_model(y, vol='Garch', p=1, q=1, mean='Constant', dist='normal')
            res = am.fit(disp='off', show_warning=False)
            garch_params[col] = {
                'alpha': round(float(res.params.get('alpha[1]', 0)), 4),
                'beta': round(float(res.params.get('beta[1]', 0)), 4),
                'persistence': round(float(res.params.get('alpha[1]', 0) + res.params.get('beta[1]', 0)), 4),
            }
            std_resids[col] = res.std_resid
            cond_vols[col] = res.conditional_volatility
        except:
            return None
    
    std_resids = std_resids.dropna()
    if len(std_resids) < 200:
        return None
    
    # DCC 추정 (simplified)
    z1 = std_resids[col1].values
    z2 = std_resids[col2].values
    
    # Q-bar
    qbar = np.corrcoef(z1, z2)[0, 1]
    
    # Grid search for DCC params
    best_ll = -np.inf
    best_a, best_b = 0.05, 0.9
    
    for a_try in np.arange(0.01, 0.4, 0.02):
        for b_try in np.arange(0.5, 0.99, 0.02):
            if a_try + b_try >= 1:
                continue
            q = qbar
            ll = 0
            for t in range(len(z1)):
                q = (1 - a_try - b_try) * qbar + a_try * z1[max(0,t-1)] * z2[max(0,t-1)] + b_try * q
                rho = max(min(q, 0.999), -0.999)
                ll += -0.5 * np.log(1 - rho**2) - 0.5 * (z1[t]**2 + z2[t]**2 - 2*rho*z1[t]*z2[t]) / (1 - rho**2)
            if ll > best_ll:
                best_ll = ll
                best_a, best_b = a_try, b_try
    
    # DCC 시계열 생성
    q = qbar
    rho_series = np.zeros(len(z1))
    for t in range(len(z1)):
        q = (1 - best_a - best_b) * qbar + best_a * z1[max(0,t-1)] * z2[max(0,t-1)] + best_b * q
        rho_series[t] = max(min(q, 0.999), -0.999)
    
    dcc_df = pd.DataFrame({'rho': rho_series}, index=std_resids.index)
    
    # 기간별 평균
    dcc_by_period = {}
    for pname, (s, e) in periods.items():
        mask = (dcc_df.index >= s) & (dcc_df.index <= e)
        sub = dcc_df[mask]
        if len(sub) > 50:
            dcc_by_period[pname] = {
                'mean': round(float(sub['rho'].mean()), 4),
                'std': round(float(sub['rho'].std()), 4),
            }
    
    result = {
        'garch': garch_params,
        'dcc_a': round(float(best_a), 4),
        'dcc_b': round(float(best_b), 4),
        'dcc_by_period': dcc_by_period,
        'n_obs': len(data),
    }
    
    print(f"  {pair_name}: a={best_a:.4f}, b={best_b:.4f}")
    for pn, pv in dcc_by_period.items():
        print(f"    {pn}: mean={pv['mean']:.4f}")
    
    return result, dcc_df

# 전체 기간 자산쌍 (1995~)
for col1, col2, name in asset_pairs:
    if col1 in returns.columns and col2 in returns.columns:
        res_pair = run_dcc_pair(returns, col1, col2, name)
        if res_pair:
            results['dcc_garch'][f'{col1}_{col2}'] = res_pair[0]

# BTC 포함 자산쌍 (2014~)
btc_returns = returns[returns.index >= btc_start]
for col1, col2, name in btc_pairs:
    if col1 in btc_returns.columns and col2 in btc_returns.columns:
        res_pair = run_dcc_pair(btc_returns, col1, col2, name)
        if res_pair:
            results['dcc_garch'][f'{col1}_{col2}'] = res_pair[0]

# 주말 보정 변동성 비교
if 'Monday' in returns.columns:
    monday_stats = {}
    for col in price_cols:
        if col in returns.columns:
            mon = returns[returns['Monday'] == 1][col]
            non_mon = returns[returns['Monday'] == 0][col]
            # √3 보정 (금-토-일 3일)
            mon_adj = mon / np.sqrt(3)
            monday_stats[col] = {
                'monday_vol': round(float(mon.std() * np.sqrt(252)), 4),
                'monday_adj_vol': round(float(mon_adj.std() * np.sqrt(252)), 4),
                'non_monday_vol': round(float(non_mon.std() * np.sqrt(252)), 4),
                'ratio': round(float(mon.std() / non_mon.std()), 4) if non_mon.std() > 0 else 0,
            }
    results['monday_effect'] = monday_stats
    print(f"\n  주말 보정 효과:")
    for col, st in monday_stats.items():
        print(f"    {col}: 월요일 vol={st['monday_vol']:.2f}%, 보정후={st['monday_adj_vol']:.2f}%, 비율={st['ratio']:.2f}")


# ============================================================
# 5. 구조변화 검정 (Structural Break Tests)
# ============================================================
print("\n[5/8] 구조변화 검정...")

from scipy import stats

def structural_break_test(series1, series2, break_date, window=None):
    """Fisher z-변환 기반 구조변화 검정"""
    common = series1.dropna().index.intersection(series2.dropna().index)
    s1 = series1[common]
    s2 = series2[common]
    
    before = common[common < break_date]
    after = common[common >= break_date]
    
    if len(before) < 30 or len(after) < 30:
        return None
    
    corr_before = np.corrcoef(s1[before], s2[before])[0, 1]
    corr_after = np.corrcoef(s1[after], s2[after])[0, 1]
    
    # Fisher z-transform
    z1 = np.arctanh(np.clip(corr_before, -0.999, 0.999))
    z2 = np.arctanh(np.clip(corr_after, -0.999, 0.999))
    
    se = np.sqrt(1/(len(before)-3) + 1/(len(after)-3))
    z_stat = (z1 - z2) / se
    p_value = 2 * (1 - stats.norm.cdf(abs(z_stat)))
    
    return {
        'corr_before': round(float(corr_before), 4),
        'corr_after': round(float(corr_after), 4),
        'n_before': len(before),
        'n_after': len(after),
        'z_stat': round(float(z_stat), 4),
        'p_value': round(float(p_value), 6),
    }

# 주요 구조변화 시점
break_dates = {
    '2004-01-01': '금융화 시작 (ETF 도입)',
    '2008-09-15': '리먼 브라더스 파산',
    '2020-03-01': 'COVID-19 팬데믹',
    '2022-03-16': '연준 금리인상 시작',
}

results['structural_breaks'] = {}

# 금-채권 구조변화
if 'Gold' in returns.columns and 'Bond10Y_chg' in returns.columns:
    for bd, desc in break_dates.items():
        key = f'Gold_Bond_{bd[:4]}'
        res_sb = structural_break_test(returns['Gold'], returns['Bond10Y_chg'], bd)
        if res_sb:
            res_sb['description'] = desc
            results['structural_breaks'][key] = res_sb
            sig = '***' if res_sb['p_value'] < 0.01 else '**' if res_sb['p_value'] < 0.05 else '*' if res_sb['p_value'] < 0.1 else ''
            print(f"  금-채권 {bd[:4]} ({desc}): {res_sb['corr_before']:.4f} → {res_sb['corr_after']:.4f} (p={res_sb['p_value']:.4f}) {sig}")

# WTI-채권 구조변화
if 'WTI' in returns.columns and 'Bond10Y_chg' in returns.columns:
    for bd, desc in break_dates.items():
        key = f'WTI_Bond_{bd[:4]}'
        res_sb = structural_break_test(returns['WTI'], returns['Bond10Y_chg'], bd)
        if res_sb:
            res_sb['description'] = desc
            results['structural_breaks'][key] = res_sb
            sig = '***' if res_sb['p_value'] < 0.01 else '**' if res_sb['p_value'] < 0.05 else '*' if res_sb['p_value'] < 0.1 else ''
            print(f"  WTI-채권 {bd[:4]} ({desc}): {res_sb['corr_before']:.4f} → {res_sb['corr_after']:.4f} (p={res_sb['p_value']:.4f}) {sig}")

# 구리-채권 구조변화
if 'Copper' in returns.columns and 'Bond10Y_chg' in returns.columns:
    for bd, desc in break_dates.items():
        key = f'Copper_Bond_{bd[:4]}'
        res_sb = structural_break_test(returns['Copper'], returns['Bond10Y_chg'], bd)
        if res_sb:
            res_sb['description'] = desc
            results['structural_breaks'][key] = res_sb

# BTC 관련 구조변화 (2014~)
btc_breaks = {
    '2020-03-01': 'COVID-19',
    '2022-03-16': '금리인상',
    '2024-01-10': 'BTC ETF 승인',
}

if 'BTC' in returns.columns:
    for bd, desc in btc_breaks.items():
        for other, oname in [('Bond10Y_chg', '채권'), ('Gold', '금'), ('SPX', '주식')]:
            if other in returns.columns:
                key = f'BTC_{other}_{bd[:4]}'
                res_sb = structural_break_test(returns['BTC'], returns[other], bd)
                if res_sb:
                    res_sb['description'] = desc
                    results['structural_breaks'][key] = res_sb
                    sig = '***' if res_sb['p_value'] < 0.01 else '**' if res_sb['p_value'] < 0.05 else '*' if res_sb['p_value'] < 0.1 else ''
                    print(f"  BTC-{oname} {bd[:4]} ({desc}): {res_sb['corr_before']:.4f} → {res_sb['corr_after']:.4f} (p={res_sb['p_value']:.4f}) {sig}")

# 기대인플레이션 구조변화
if 'BreakevenInflation' in assets.columns and 'Gold' in returns.columns:
    bei = assets['BreakevenInflation'].diff().dropna()
    for bd in ['2022-03-16']:
        res_sb = structural_break_test(returns['Gold'], bei.reindex(returns.index), bd)
        if res_sb:
            results['structural_breaks'][f'Gold_BEI_{bd[:4]}'] = res_sb
            print(f"  금-기대인플레이션 {bd[:4]}: {res_sb['corr_before']:.4f} → {res_sb['corr_after']:.4f} (p={res_sb['p_value']:.4f})")


# ============================================================
# 6. Granger 인과성 검정
# ============================================================
print("\n[6/8] Granger 인과성 검정...")

from statsmodels.tsa.stattools import grangercausalitytests

def granger_test(data, cause, effect, max_lag=8):
    """Granger 인과성 검정 (최적 시차 자동 선택)"""
    df = data[[effect, cause]].dropna()
    if len(df) < 100:
        return None
    
    best_result = None
    best_p = 1.0
    
    for lag in range(1, min(max_lag+1, len(df)//20)):
        try:
            res = grangercausalitytests(df, maxlag=lag, verbose=False)
            f_stat = res[lag][0]['ssr_ftest'][0]
            p_val = res[lag][0]['ssr_ftest'][1]
            if p_val < best_p:
                best_p = p_val
                best_result = {'F': round(float(f_stat), 4), 'p': round(float(p_val), 6), 'lag': lag}
        except:
            continue
    
    return best_result

# 전체 기간 Granger 검정
granger_pairs = []

# 원자재-채권 (1995~)
for asset in ['Gold', 'WTI', 'Copper']:
    if asset in returns.columns and 'Bond10Y_chg' in returns.columns:
        granger_pairs.append((asset, 'Bond10Y_chg', returns))
        granger_pairs.append(('Bond10Y_chg', asset, returns))

# 원자재 간
for a1, a2 in [('Gold', 'WTI'), ('Gold', 'Copper'), ('WTI', 'Copper')]:
    if a1 in returns.columns and a2 in returns.columns:
        granger_pairs.append((a1, a2, returns))
        granger_pairs.append((a2, a1, returns))

# BTC 관련 (2014~)
if 'BTC' in returns.columns:
    for other in ['Bond10Y_chg', 'Gold', 'WTI', 'Copper', 'SPX']:
        if other in btc_returns.columns:
            granger_pairs.append(('BTC', other, btc_returns))
            granger_pairs.append((other, 'BTC', btc_returns))

# VIX → 자산
if 'VIX' in assets.columns:
    vix_ret = assets['VIX'].pct_change().dropna()
    vix_ret.name = 'VIX_ret'
    for asset in ['Gold', 'WTI', 'BTC', 'SPX']:
        if asset in returns.columns:
            combined = pd.concat([returns[asset], vix_ret], axis=1).dropna()
            if len(combined) > 200:
                granger_pairs.append(('VIX_ret', asset, combined))

results['granger'] = {}
for cause, effect, data in granger_pairs:
    res_g = granger_test(data, cause, effect)
    if res_g:
        key = f'{cause}_to_{effect}'
        results['granger'][key] = res_g
        sig = '***' if res_g['p'] < 0.01 else '**' if res_g['p'] < 0.05 else '*' if res_g['p'] < 0.1 else ''
        if sig:
            print(f"  {cause} → {effect}: F={res_g['F']:.2f}, p={res_g['p']:.4f} (lag={res_g['lag']}) {sig}")


# ============================================================
# 7. VAR 전이효과 분석 (Diebold-Yilmaz)
# ============================================================
print("\n[7/8] VAR 전이효과 분석...")

from statsmodels.tsa.api import VAR

def spillover_analysis(data, var_cols, max_lag=8, horizon=10):
    """Diebold-Yilmaz 전이효과 분석"""
    df = data[var_cols].dropna()
    if len(df) < 200:
        return None
    
    # 최적 시차 선택
    try:
        model = VAR(df)
        best_lag = 1
        best_aic = np.inf
        for lag in range(1, min(max_lag+1, len(df)//20)):
            try:
                res = model.fit(lag)
                if res.aic < best_aic:
                    best_aic = res.aic
                    best_lag = lag
            except:
                continue
        
        result = model.fit(best_lag)
        fevd = result.fevd(horizon)
        
        # 전이효과 매트릭스
        n = len(var_cols)
        matrix = {}
        for i, col_i in enumerate(var_cols):
            matrix[col_i] = {}
            row_sum = fevd.decomp[i][-1].sum()
            for j, col_j in enumerate(var_cols):
                val = fevd.decomp[i][-1][j] / row_sum * 100
                matrix[col_i][col_j] = round(float(val), 1)
        
        # 전체 전이 지수
        total_off_diag = sum(matrix[ci][cj] for ci in var_cols for cj in var_cols if ci != cj)
        total_index = round(total_off_diag / n, 1)
        
        return {
            'matrix': matrix,
            'total_index': total_index,
            'var_lag': best_lag,
            'n_obs': len(df),
        }
    except Exception as e:
        print(f"  VAR 오류: {e}")
        return None

# 전체 기간 (BTC 제외, 1995~)
var_cols_full = [c for c in ['Gold', 'WTI', 'Bond10Y_chg', 'Copper'] if c in returns.columns]
if len(var_cols_full) >= 3:
    res_sp = spillover_analysis(returns, var_cols_full)
    if res_sp:
        results['spillover_full_1995'] = res_sp
        print(f"  전체 기간 (1995~, BTC 제외): 전이지수={res_sp['total_index']}%, lag={res_sp['var_lag']}")

# BTC 포함 (2014~)
var_cols_btc = [c for c in ['BTC', 'Gold', 'WTI', 'Bond10Y_chg', 'Copper', 'SPX'] if c in btc_returns.columns]
if len(var_cols_btc) >= 4:
    res_sp = spillover_analysis(btc_returns, var_cols_btc)
    if res_sp:
        results['spillover_btc_2014'] = res_sp
        print(f"  BTC 포함 (2014~): 전이지수={res_sp['total_index']}%, lag={res_sp['var_lag']}")

# 기간별 전이효과
for pname, (s, e) in periods.items():
    mask = (returns.index >= s) & (returns.index <= e)
    sub = returns[mask]
    cols = [c for c in var_cols_full if c in sub.columns]
    if len(cols) >= 3 and len(sub) > 200:
        res_sp = spillover_analysis(sub, cols)
        if res_sp:
            results[f'spillover_{pname}'] = res_sp
            print(f"  {pname}: 전이지수={res_sp['total_index']}%, lag={res_sp['var_lag']}")

# 2022~ BTC 포함
mask_2022 = returns.index >= '2022-01-01'
sub_2022 = returns[mask_2022]
btc_cols_2022 = [c for c in var_cols_btc if c in sub_2022.columns]
if len(btc_cols_2022) >= 4 and len(sub_2022) > 200:
    res_sp = spillover_analysis(sub_2022, btc_cols_2022)
    if res_sp:
        results['spillover_btc_2022'] = res_sp
        print(f"  BTC 포함 (2022~): 전이지수={res_sp['total_index']}%, lag={res_sp['var_lag']}")


# ============================================================
# 8. 차트 생성 및 결과 저장
# ============================================================
print("\n[8/8] 차트 생성 및 결과 저장...")

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

plt.rcParams['font.size'] = 10
plt.rcParams['figure.dpi'] = 150

# --- Chart 1: 롤링 상관관계 (금-채권, WTI-채권, 구리-채권) ---
fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)
window = 252

pairs_chart = [
    ('Gold', 'Bond10Y_chg', 'Gold-Bond', '#FFD700'),
    ('WTI', 'Bond10Y_chg', 'WTI-Bond', '#2E86C1'),
    ('Copper', 'Bond10Y_chg', 'Copper-Bond', '#E67E22'),
]

for ax, (c1, c2, label, color) in zip(axes, pairs_chart):
    if c1 in returns.columns and c2 in returns.columns:
        rolling = returns[c1].rolling(window).corr(returns[c2])
        ax.plot(rolling.index, rolling.values, color=color, linewidth=0.8, alpha=0.8)
        ax.axhline(y=0, color='gray', linestyle='--', linewidth=0.5)
        ax.set_ylabel(label)
        ax.set_ylim(-0.8, 0.8)
        # 구조변화 시점 표시
        for bd in ['2004-01-01', '2008-09-15', '2020-03-01', '2022-03-16']:
            ax.axvline(x=pd.Timestamp(bd), color='red', linestyle=':', alpha=0.5, linewidth=0.7)
        ax.legend([label], loc='upper right', fontsize=8)

axes[0].set_title('Rolling 252-Day Correlations: Commodities vs Bond Yield (1995-2025)')
axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
plt.tight_layout()
plt.savefig('vol_chart_rolling_corr.png', bbox_inches='tight')
plt.close()
print("  ✓ vol_chart_rolling_corr.png")

# --- Chart 2: Vasicek 모델 - 금리 경로와 장기 평균 ---
if rate_col and rate_col in assets.columns:
    fig, ax = plt.subplots(figsize=(12, 5))
    rate_data = assets[rate_col].dropna()
    ax.plot(rate_data.index, rate_data.values, color='#2E86C1', linewidth=0.8, label=rate_col)
    if 'vasicek' in results:
        ax.axhline(y=results['vasicek']['b'], color='red', linestyle='--', linewidth=1.5,
                   label=f"Long-run mean b={results['vasicek']['b']:.2f}%")
    ax.set_title('Short Rate Path and Vasicek Long-Run Mean')
    ax.set_ylabel('Rate (%)')
    ax.legend()
    for bd in ['2004-01-01', '2008-09-15', '2020-03-01', '2022-03-16']:
        ax.axvline(x=pd.Timestamp(bd), color='gray', linestyle=':', alpha=0.4)
    plt.tight_layout()
    plt.savefig('vol_chart_vasicek.png', bbox_inches='tight')
    plt.close()
    print("  ✓ vol_chart_vasicek.png")

# --- Chart 3: 기대인플레이션과 금 가격 ---
if 'BreakevenInflation' in assets.columns and 'Gold' in assets.columns:
    fig, ax1 = plt.subplots(figsize=(12, 5))
    bei = assets['BreakevenInflation'].dropna()
    ax1.plot(bei.index, bei.values, color='#E74C3C', linewidth=0.8, label='Breakeven Inflation')
    ax1.set_ylabel('Breakeven Inflation (%)', color='#E74C3C')
    ax2 = ax1.twinx()
    gold = assets['Gold'].dropna()
    ax2.plot(gold.index, gold.values, color='#FFD700', linewidth=0.8, label='Gold Price')
    ax2.set_ylabel('Gold Price ($)', color='#FFD700')
    ax1.set_title('Breakeven Inflation vs Gold Price')
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
    plt.tight_layout()
    plt.savefig('vol_chart_bei_gold.png', bbox_inches='tight')
    plt.close()
    print("  ✓ vol_chart_bei_gold.png")

# --- Chart 4: 전이효과 히트맵 ---
if 'spillover_btc_2014' in results:
    sp = results['spillover_btc_2014']
    cols = list(sp['matrix'].keys())
    mat = np.array([[sp['matrix'][r][c] for c in cols] for r in cols])
    
    fig, ax = plt.subplots(figsize=(8, 6))
    im = ax.imshow(mat, cmap='YlOrRd', aspect='auto')
    ax.set_xticks(range(len(cols)))
    ax.set_yticks(range(len(cols)))
    ax.set_xticklabels(cols, rotation=45, ha='right')
    ax.set_yticklabels(cols)
    for i in range(len(cols)):
        for j in range(len(cols)):
            ax.text(j, i, f'{mat[i,j]:.1f}', ha='center', va='center',
                   color='white' if mat[i,j] > 50 else 'black', fontsize=9)
    plt.colorbar(im, label='FEVD (%)')
    ax.set_title(f'VAR Spillover Matrix (2014-2025, Total Index: {sp["total_index"]}%)')
    plt.tight_layout()
    plt.savefig('vol_chart_spillover.png', bbox_inches='tight')
    plt.close()
    print("  ✓ vol_chart_spillover.png")

# --- Chart 5: BTC 롤링 상관관계 ---
if 'BTC' in returns.columns:
    fig, ax = plt.subplots(figsize=(12, 5))
    btc_ret = returns[returns.index >= btc_start]
    for other, label, color in [('Bond10Y_chg', 'BTC-Bond', '#2E86C1'),
                                 ('Gold', 'BTC-Gold', '#FFD700'),
                                 ('SPX', 'BTC-SPX', '#E74C3C'),
                                 ('WTI', 'BTC-WTI', '#27AE60')]:
        if other in btc_ret.columns:
            rolling = btc_ret['BTC'].rolling(window).corr(btc_ret[other])
            ax.plot(rolling.index, rolling.values, label=label, color=color, linewidth=0.8, alpha=0.8)
    ax.axhline(y=0, color='gray', linestyle='--', linewidth=0.5)
    ax.set_title('BTC Rolling 252-Day Correlations (2014-2025)')
    ax.set_ylabel('Correlation')
    ax.set_ylim(-0.6, 0.8)
    ax.legend(loc='upper left', fontsize=8)
    plt.tight_layout()
    plt.savefig('vol_chart_btc_rolling.png', bbox_inches='tight')
    plt.close()
    print("  ✓ vol_chart_btc_rolling.png")

# --- Chart 6: 주말 보정 효과 비교 ---
if 'monday_effect' in results:
    fig, ax = plt.subplots(figsize=(10, 5))
    assets_list = list(results['monday_effect'].keys())
    x = np.arange(len(assets_list))
    width = 0.25
    mon_vols = [results['monday_effect'][a]['monday_vol'] for a in assets_list]
    adj_vols = [results['monday_effect'][a]['monday_adj_vol'] for a in assets_list]
    non_vols = [results['monday_effect'][a]['non_monday_vol'] for a in assets_list]
    
    ax.bar(x - width, mon_vols, width, label='Monday (raw)', color='#E74C3C', alpha=0.8)
    ax.bar(x, adj_vols, width, label='Monday (√3 adjusted)', color='#F39C12', alpha=0.8)
    ax.bar(x + width, non_vols, width, label='Non-Monday', color='#2E86C1', alpha=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(assets_list)
    ax.set_ylabel('Annualized Volatility (%)')
    ax.set_title('Weekend Volatility Correction: Monday vs Non-Monday')
    ax.legend()
    plt.tight_layout()
    plt.savefig('vol_chart_monday_effect.png', bbox_inches='tight')
    plt.close()
    print("  ✓ vol_chart_monday_effect.png")

# --- 기초 통계량 저장 ---
basic_stats = {}
for pname, (s, e) in periods.items():
    mask = (returns.index >= s) & (returns.index <= e)
    sub = returns[mask]
    pstats = {'N obs': len(sub)}
    for col in price_cols:
        if col in sub.columns:
            pstats[f'{col} Ann Return'] = round(float(sub[col].mean() * 252 * 100), 2)
            pstats[f'{col} Ann Vol'] = round(float(sub[col].std() * np.sqrt(252) * 100), 2)
    # 상관관계
    for c1, c2 in [('Gold', 'Bond10Y_chg'), ('WTI', 'Bond10Y_chg'), ('Copper', 'Bond10Y_chg')]:
        if c1 in sub.columns and c2 in sub.columns:
            pstats[f'{c1}-Bond Corr'] = round(float(sub[c1].corr(sub[c2])), 4)
    if 'BTC' in sub.columns:
        for other in ['Bond10Y_chg', 'Gold', 'SPX', 'WTI']:
            if other in sub.columns:
                pstats[f'BTC-{other} Corr'] = round(float(sub['BTC'].corr(sub[other])), 4)
    # 금리 평균
    mask_a = (assets.index >= s) & (assets.index <= e)
    if 'Bond10Y' in assets.columns:
        pstats['Bond10Y Mean'] = round(float(assets[mask_a]['Bond10Y'].mean()), 2)
    if 'BreakevenInflation' in assets.columns:
        bei_sub = assets[mask_a]['BreakevenInflation'].dropna()
        if len(bei_sub) > 0:
            pstats['BEI Mean'] = round(float(bei_sub.mean()), 2)
    if 'VIX' in assets.columns:
        vix_sub = assets[mask_a]['VIX'].dropna()
        if len(vix_sub) > 0:
            pstats['VIX Mean'] = round(float(vix_sub.mean()), 2)
    basic_stats[pname] = pstats

results['basic_stats'] = basic_stats

# 전체 상관관계 매트릭스
all_cols = [c for c in ['Gold', 'WTI', 'Copper', 'SPX', 'Bond10Y_chg'] if c in returns.columns]
if 'BTC' in returns.columns:
    btc_corr = btc_returns[['BTC'] + [c for c in all_cols if c in btc_returns.columns]].corr()
    results['btc_correlation_matrix'] = {c: {c2: round(float(btc_corr.loc[c, c2]), 4) for c2 in btc_corr.columns} for c in btc_corr.index}

full_corr = returns[all_cols].corr()
results['full_correlation_matrix'] = {c: {c2: round(float(full_corr.loc[c, c2]), 4) for c2 in full_corr.columns} for c in full_corr.index}

# 위기 시기 상관관계
crisis_periods = {
    'Asian Crisis (1997.07-1998.10)': ('1997-07-01', '1998-10-31'),
    'Dot-com Bust (2000.03-2002.10)': ('2000-03-01', '2002-10-31'),
    'GFC (2008.09-2009.03)': ('2008-09-01', '2009-03-31'),
    'COVID Crash (2020.02-2020.04)': ('2020-02-01', '2020-04-30'),
    'Rate Hike (2022.03-2022.12)': ('2022-03-01', '2022-12-31'),
    'SVB Crisis (2023.03-2023.04)': ('2023-03-01', '2023-04-30'),
}

results['crisis_correlations'] = {}
for cname, (cs, ce) in crisis_periods.items():
    mask = (returns.index >= cs) & (returns.index <= ce)
    sub = returns[mask]
    if len(sub) > 20:
        crisis_corr = {}
        for c1, c2 in [('Gold', 'Bond10Y_chg'), ('WTI', 'Bond10Y_chg'), ('Copper', 'Bond10Y_chg')]:
            if c1 in sub.columns and c2 in sub.columns:
                crisis_corr[f'{c1}-Bond'] = round(float(sub[c1].corr(sub[c2])), 4)
        if 'BTC' in sub.columns:
            for other in ['Bond10Y_chg', 'Gold', 'SPX']:
                if other in sub.columns:
                    crisis_corr[f'BTC-{other}'] = round(float(sub['BTC'].corr(sub[other])), 4)
        results['crisis_correlations'][cname] = crisis_corr

# JSON 저장
with open('vol_analysis_results.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2, default=str)

print(f"\n{'='*70}")
print("분석 완료!")
print(f"  결과: vol_analysis_results.json")
print(f"  차트: vol_chart_*.png")
print(f"{'='*70}")
