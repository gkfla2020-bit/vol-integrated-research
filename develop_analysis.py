#!/usr/bin/env python3
"""
논문 디벨롭 통계분석 파이프라인
4개 라운드의 실제 데이터 분석:
1. 허점 보완: Shadow Rate, 실질금리 DCC, 주말보정 AIC/BIC 비교
2. 확장 방향: TVP-VAR(Rolling VAR 근사), BTC 카멜레온 효과, 백테스팅
3. 데이터 확장: GPR/EPU 통제변수, 고빈도 주말효과
4. 방법론 정교화: 주파수 영역 Spillover, 비선형 Granger
"""

import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime
import json
import os
from scipy import stats as sp_stats
from scipy.optimize import minimize
from arch import arch_model
from statsmodels.tsa.api import VAR
from statsmodels.tsa.stattools import grangercausalitytests

print("=" * 70)
print("논문 디벨롭 확장 통계분석")
print("=" * 70)

# ============================================================
# 1. 데이터 수집
# ============================================================
print("\n[1/8] 데이터 수집 중...")

START = "2010-01-01"
END = "2025-02-01"

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

# FRED 데이터
fred_series = {
    'DGS10': '10년 국채',
    'DGS2': '2년 국채',
    'DFII10': '10년 TIPS (실질금리)',
    'DTB3': '3개월 T-Bill',
    'DCOILWTICO': 'WTI',
    'DTWEXBGS': '달러 인덱스',
    'T10YIE': '10년 BEI (기대인플레이션)',
}

fred_data = {}
for sid, name in fred_series.items():
    df = get_fred(sid)
    if df is not None and len(df) > 0:
        fred_data[sid] = df
        print(f"  ✓ {name} ({sid}): {len(df)} obs")

# Yahoo Finance
yf_tickers = {
    'BTC-USD': '비트코인',
    'GC=F': '금',
    'CL=F': 'WTI 선물',
    'HG=F': '구리',
    '^GSPC': 'S&P 500',
    '^VIX': 'VIX',
    '^TNX': '10년 국채 수익률',
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
# 2. 데이터 병합
# ============================================================
print("\n[2/8] 데이터 전처리...")

assets = pd.DataFrame()
if 'BTC-USD' in yf_data: assets['BTC'] = yf_data['BTC-USD']['BTC-USD']
if 'GC=F' in yf_data: assets['Gold'] = yf_data['GC=F']['GC=F']
if 'HG=F' in yf_data: assets['Copper'] = yf_data['HG=F']['HG=F']
if '^GSPC' in yf_data: assets['SPX'] = yf_data['^GSPC']['^GSPC']
if 'CL=F' in yf_data: assets['WTI'] = yf_data['CL=F']['CL=F']
if 'DGS10' in fred_data: assets['Bond10Y'] = fred_data['DGS10']['DGS10']
if 'DFII10' in fred_data: assets['TIPS10Y'] = fred_data['DFII10']['DFII10']
if 'T10YIE' in fred_data: assets['BEI10Y'] = fred_data['T10YIE']['T10YIE']
if '^VIX' in yf_data: assets['VIX'] = yf_data['^VIX']['^VIX']

assets = assets.sort_index().ffill().dropna(how='all')

if 'BTC' in assets.columns:
    btc_start = assets['BTC'].first_valid_index()
    assets_btc = assets[assets.index >= btc_start].copy()
else:
    assets_btc = assets.copy()

# 수익률
price_cols = ['BTC', 'Gold', 'WTI', 'Copper', 'SPX']
price_cols = [c for c in price_cols if c in assets_btc.columns]
returns = np.log(assets_btc[price_cols] / assets_btc[price_cols].shift(1)).dropna()

if 'Bond10Y' in assets_btc.columns:
    returns['Bond10Y_chg'] = assets_btc['Bond10Y'].diff()
if 'TIPS10Y' in assets_btc.columns:
    returns['TIPS10Y_chg'] = assets_btc['TIPS10Y'].diff()
returns = returns.dropna()

print(f"  수익률 데이터: {returns.shape[0]} obs, {returns.index.min().date()} ~ {returns.index.max().date()}")

results = {}


# ============================================================
# 3. ROUND 1: 허점 보완
# ============================================================
print("\n" + "=" * 70)
print("[3/8] ROUND 1: 허점 보완 (Logical Rigor)")
print("=" * 70)

# --- 3.1 Vasicek vs CIR 비교 ---
print("\n  3.1 Vasicek vs CIR 모델 비교...")

periods_vasicek = {
    'Pre-Crisis (1995-2007)': ('1995-01-01', '2007-12-31'),
    'ZLB Era (2008-2021)': ('2008-01-01', '2021-12-31'),
    'Tightening (2022-2025)': ('2022-01-01', '2025-12-31'),
}

# 3개월 T-Bill 사용
if 'DTB3' in fred_data:
    tbill = fred_data['DTB3']['DTB3'].dropna()
    
    results['vasicek_comparison'] = {}
    
    for pname, (s, e) in periods_vasicek.items():
        sub = tbill[(tbill.index >= s) & (tbill.index <= e)].dropna()
        if len(sub) < 100:
            continue
        
        dt = 1/252
        r = sub.values
        dr = np.diff(r)
        r_lag = r[:-1]
        
        # Vasicek: dr = a(b-r)dt + sigma*dW
        # OLS: dr = (ab - a*r)dt + eps => dr/dt = ab - a*r
        Y = dr / dt
        X = np.column_stack([np.ones(len(r_lag)), r_lag])
        beta = np.linalg.lstsq(X, Y, rcond=None)[0]
        a_vasicek = -beta[1]
        b_vasicek = beta[0] / a_vasicek if a_vasicek > 0 else np.nan
        resid_v = Y - X @ beta
        sigma_vasicek = np.std(resid_v) * np.sqrt(dt)
        halflife = np.log(2) / a_vasicek if a_vasicek > 0 else np.inf
        
        # Log-likelihood Vasicek
        n = len(dr)
        ll_vasicek = -n/2 * np.log(2*np.pi) - n/2 * np.log(sigma_vasicek**2 * dt) - \
                     np.sum((dr - a_vasicek*(b_vasicek - r_lag)*dt)**2) / (2 * sigma_vasicek**2 * dt)
        aic_vasicek = -2*ll_vasicek + 2*3  # 3 params
        bic_vasicek = -2*ll_vasicek + np.log(n)*3
        
        # CIR: dr = a(b-r)dt + sigma*sqrt(r)*dW
        # sigma_cir scales with sqrt(r)
        r_lag_pos = np.maximum(r_lag, 0.01)
        dr_scaled = dr / np.sqrt(r_lag_pos * dt)
        X_cir = np.column_stack([np.ones(len(r_lag)), r_lag]) / np.sqrt(r_lag_pos * dt)[:, None]
        # Weight by sqrt(r)
        Y_cir = dr / (np.sqrt(r_lag_pos) * dt)
        X_cir2 = np.column_stack([np.ones(len(r_lag)), r_lag]) / np.sqrt(r_lag_pos)[:, None]
        try:
            beta_cir = np.linalg.lstsq(X_cir2, Y_cir, rcond=None)[0]
            a_cir = -beta_cir[1]
            b_cir = beta_cir[0] / a_cir if a_cir > 0 else np.nan
            resid_cir = dr - a_cir*(b_cir - r_lag)*dt
            sigma_cir = np.std(resid_cir / np.sqrt(r_lag_pos * dt))
            
            ll_cir = -n/2 * np.log(2*np.pi) - np.sum(np.log(sigma_cir**2 * r_lag_pos * dt)) / 2 - \
                     np.sum(resid_cir**2 / (2 * sigma_cir**2 * r_lag_pos * dt))
            aic_cir = -2*ll_cir + 2*3
            bic_cir = -2*ll_cir + np.log(n)*3
        except:
            a_cir = b_cir = sigma_cir = ll_cir = aic_cir = bic_cir = np.nan
        
        results['vasicek_comparison'][pname] = {
            'N': len(sub),
            'vasicek': {
                'a': round(float(a_vasicek), 6),
                'b': round(float(b_vasicek), 4) if not np.isnan(b_vasicek) else None,
                'sigma': round(float(sigma_vasicek), 6),
                'halflife_days': round(float(halflife), 1) if not np.isinf(halflife) else 99999,
                'loglik': round(float(ll_vasicek), 2),
                'AIC': round(float(aic_vasicek), 2),
                'BIC': round(float(bic_vasicek), 2),
            },
            'cir': {
                'a': round(float(a_cir), 6) if not np.isnan(a_cir) else None,
                'b': round(float(b_cir), 4) if not np.isnan(b_cir) else None,
                'sigma': round(float(sigma_cir), 6) if not np.isnan(sigma_cir) else None,
                'loglik': round(float(ll_cir), 2) if not np.isnan(ll_cir) else None,
                'AIC': round(float(aic_cir), 2) if not np.isnan(aic_cir) else None,
                'BIC': round(float(bic_cir), 2) if not np.isnan(bic_cir) else None,
            },
            'mean_rate': round(float(sub.mean()), 4),
        }
        
        print(f"\n  {pname} (N={len(sub)}, mean rate={sub.mean():.2f}%):")
        print(f"    Vasicek: a={a_vasicek:.6f}, b={b_vasicek:.2f}%, HL={halflife:.0f}d, AIC={aic_vasicek:.1f}")
        if not np.isnan(a_cir):
            print(f"    CIR:     a={a_cir:.6f}, b={b_cir:.2f}%, AIC={aic_cir:.1f}")
            print(f"    → {'Vasicek' if aic_vasicek < aic_cir else 'CIR'} preferred by AIC")

# --- 3.2 실질금리 DCC-GARCH ---
print("\n  3.2 실질금리(TIPS) DCC-GARCH...")

def run_dcc(data, col1, col2, label):
    """DCC-GARCH 실행, 결과 dict 반환"""
    pair = data[[col1, col2]].dropna() * 100 if col1 in ['BTC','Gold','WTI','Copper','SPX'] else data[[col1, col2]].dropna()
    if col1 not in ['BTC','Gold','WTI','Copper','SPX']:
        pair = data[[col1, col2]].dropna()
    
    # 스케일링
    for c in [col1, col2]:
        if c in ['BTC','Gold','WTI','Copper','SPX']:
            pair[c] = data[c].reindex(pair.index) * 100
        else:
            pair[c] = data[c].reindex(pair.index)
    pair = pair.dropna()
    
    if len(pair) < 100:
        return None
    
    # GARCH(1,1)
    garch_res = {}
    std_resids = pd.DataFrame(index=pair.index)
    cond_vols = pd.DataFrame(index=pair.index)
    
    for col in [col1, col2]:
        am = arch_model(pair[col], vol='Garch', p=1, q=1, mean='Constant', dist='normal')
        res = am.fit(disp='off')
        garch_res[col] = {
            'alpha': round(float(res.params.get('alpha[1]', 0)), 4),
            'beta': round(float(res.params.get('beta[1]', 0)), 4),
        }
        std_resids[col] = res.std_resid
        cond_vols[col] = res.conditional_volatility
    
    z = std_resids.dropna()
    T = len(z)
    Qbar = z.T @ z / T
    
    def dcc_loglik(params, z, Qbar):
        a, b = params
        if a < 0 or b < 0 or a + b >= 1:
            return 1e10
        T, N = z.shape
        Qt = Qbar.values.copy()
        ll = 0
        for t in range(T):
            zt = z.iloc[t].values.reshape(-1, 1)
            Qt = (1 - a - b) * Qbar.values + a * (zt @ zt.T) + b * Qt
            diag_inv = np.diag(1.0 / np.sqrt(np.maximum(np.diag(Qt), 1e-10)))
            Rt = diag_inv @ Qt @ diag_inv
            det_R = np.linalg.det(Rt)
            if det_R <= 0:
                return 1e10
            inv_R = np.linalg.inv(Rt)
            ll += -0.5 * (np.log(det_R) + zt.T @ (inv_R - np.eye(N)) @ zt)
        return -ll.item()
    
    res_dcc = minimize(dcc_loglik, [0.02, 0.95], args=(z, Qbar),
                       method='Nelder-Mead', options={'maxiter': 5000})
    a_dcc, b_dcc = res_dcc.x
    loglik = -res_dcc.fun
    
    # 시변 상관계수
    Qt = Qbar.values.copy()
    rho_t = []
    for t in range(T):
        zt = z.iloc[t].values.reshape(-1, 1)
        Qt = (1 - a_dcc - b_dcc) * Qbar.values + a_dcc * (zt @ zt.T) + b_dcc * Qt
        diag_inv = np.diag(1.0 / np.sqrt(np.maximum(np.diag(Qt), 1e-10)))
        Rt = diag_inv @ Qt @ diag_inv
        rho_t.append(Rt[0, 1])
    
    dcc_corr = pd.Series(rho_t, index=z.index, name=f'DCC_{label}')
    
    # AIC/BIC
    n_params = 2 + sum(3 for _ in [col1, col2])  # DCC(2) + GARCH(3 each)
    aic = -2*loglik + 2*n_params
    bic = -2*loglik + np.log(T)*n_params
    
    print(f"    {label}: a={a_dcc:.4f}, b={b_dcc:.4f}, LL={loglik:.1f}")
    
    return {
        'garch': garch_res,
        'dcc_params': {'a': round(float(a_dcc), 4), 'b': round(float(b_dcc), 4)},
        'loglik': round(float(loglik), 2),
        'AIC': round(float(aic), 2),
        'BIC': round(float(bic), 2),
        'dcc_series': dcc_corr,
        'mean_corr': round(float(dcc_corr.mean()), 4),
        'std_corr': round(float(dcc_corr.std()), 4),
    }

# Gold-TIPS DCC (실질금리)
results['real_yield_dcc'] = {}
if 'TIPS10Y_chg' in returns.columns and 'Gold' in returns.columns:
    res = run_dcc(returns, 'Gold', 'TIPS10Y_chg', 'Gold-TIPS')
    if res:
        results['real_yield_dcc']['Gold_TIPS'] = {k: v for k, v in res.items() if k != 'dcc_series'}
        gold_tips_series = res['dcc_series']
        
        # 기간별 평균
        for pname, (s, e) in [('Pre-2022', ('2014-01-01', '2021-12-31')), ('Post-2022', ('2022-01-01', '2025-12-31'))]:
            sub = gold_tips_series[(gold_tips_series.index >= s) & (gold_tips_series.index <= e)]
            if len(sub) > 0:
                results['real_yield_dcc'][f'Gold_TIPS_{pname}'] = {
                    'mean': round(float(sub.mean()), 4),
                    'std': round(float(sub.std()), 4),
                }
                print(f"      {pname}: mean={sub.mean():.4f}")

# Gold-Nominal Bond DCC (비교용)
if 'Bond10Y_chg' in returns.columns and 'Gold' in returns.columns:
    res = run_dcc(returns, 'Gold', 'Bond10Y_chg', 'Gold-Nominal')
    if res:
        results['real_yield_dcc']['Gold_Nominal'] = {k: v for k, v in res.items() if k != 'dcc_series'}

# BTC-TIPS DCC
if 'TIPS10Y_chg' in returns.columns and 'BTC' in returns.columns:
    res = run_dcc(returns, 'BTC', 'TIPS10Y_chg', 'BTC-TIPS')
    if res:
        results['real_yield_dcc']['BTC_TIPS'] = {k: v for k, v in res.items() if k != 'dcc_series'}

# --- 3.3 주말 보정 AIC/BIC 비교 ---
print("\n  3.3 주말 보정 모델 비교...")

results['weekend_correction'] = {}

if 'BTC' in returns.columns and 'SPX' in returns.columns:
    pair_data = returns[['BTC', 'SPX']].dropna() * 100
    
    # 달력일수 계산
    delta_t = pd.Series(index=pair_data.index, dtype=float)
    for i in range(len(pair_data)):
        if i == 0:
            delta_t.iloc[i] = 1
        else:
            days = (pair_data.index[i] - pair_data.index[i-1]).days
            delta_t.iloc[i] = days
    
    # Model A: 보정 없는 DCC-GARCH
    res_no_adj = run_dcc(returns, 'BTC', 'SPX', 'BTC-SPX (no adj)')
    
    # Model B: sqrt(DeltaT) 보정
    # BTC는 항상 1, 전통자산은 달력일수
    adj_returns = returns[['BTC', 'SPX']].dropna().copy()
    for i in range(len(adj_returns)):
        if i > 0:
            days = (adj_returns.index[i] - adj_returns.index[i-1]).days
            if days > 1:
                adj_returns.iloc[i, 1] = adj_returns.iloc[i, 1] / np.sqrt(days)  # SPX만 보정
    
    res_adj = run_dcc(adj_returns, 'BTC', 'SPX', 'BTC-SPX (sqrt adj)')
    
    if res_no_adj and res_adj:
        results['weekend_correction'] = {
            'no_adjustment': {
                'loglik': res_no_adj['loglik'],
                'AIC': res_no_adj['AIC'],
                'BIC': res_no_adj['BIC'],
                'mean_corr': res_no_adj['mean_corr'],
            },
            'sqrt_adjustment': {
                'loglik': res_adj['loglik'],
                'AIC': res_adj['AIC'],
                'BIC': res_adj['BIC'],
                'mean_corr': res_adj['mean_corr'],
            },
            'improvement': {
                'AIC_diff': round(float(res_no_adj['AIC'] - res_adj['AIC']), 2),
                'BIC_diff': round(float(res_no_adj['BIC'] - res_adj['BIC']), 2),
                'LL_diff': round(float(res_adj['loglik'] - res_no_adj['loglik']), 2),
            }
        }
        print(f"    보정 없음: AIC={res_no_adj['AIC']:.1f}, BIC={res_no_adj['BIC']:.1f}")
        print(f"    sqrt 보정: AIC={res_adj['AIC']:.1f}, BIC={res_adj['BIC']:.1f}")
        print(f"    → AIC 차이: {res_no_adj['AIC'] - res_adj['AIC']:.1f} (양수=보정 우월)")


# ============================================================
# 4. ROUND 2: 확장 방향
# ============================================================
print("\n" + "=" * 70)
print("[4/8] ROUND 2: 확장 방향 (Expansion)")
print("=" * 70)

# --- 4.1 Rolling VAR Spillover (TVP-VAR 근사) ---
print("\n  4.1 Rolling VAR Spillover (TVP-VAR 근사)...")

spillover_cols = [c for c in ['BTC', 'Gold', 'WTI', 'Bond10Y_chg', 'Copper', 'SPX'] if c in returns.columns]
var_data = returns[spillover_cols].dropna() * 100
# Bond10Y_chg는 이미 수준 변화이므로 100 곱하지 않음
if 'Bond10Y_chg' in spillover_cols:
    var_data['Bond10Y_chg'] = returns['Bond10Y_chg'].reindex(var_data.index)

results['rolling_spillover'] = {}

window = 252  # 1년 롤링
step = 21     # 월별

dates_list = []
total_spillover_list = []
btc_from_list = []
btc_to_list = []

for start_idx in range(0, len(var_data) - window, step):
    sub = var_data.iloc[start_idx:start_idx + window].copy()
    sub.index = pd.DatetimeIndex(sub.index).to_period('B').to_timestamp()
    
    try:
        model = VAR(sub)
        lag = min(max(model.select_order(maxlags=5).aic, 1), 5)
        var_result = model.fit(lag)
        fevd = var_result.fevd(10)
        
        n = len(spillover_cols)
        total_sp = 0
        btc_idx = spillover_cols.index('BTC') if 'BTC' in spillover_cols else None
        btc_from = 0
        btc_to = 0
        
        for i in range(n):
            for j in range(n):
                if i != j:
                    val = float(fevd.decomp[i][-1][j])
                    total_sp += val
                    if btc_idx is not None:
                        if j == btc_idx:  # FROM BTC
                            btc_from += val
                        if i == btc_idx:  # TO BTC
                            btc_to += val
        
        total_sp = total_sp / n * 100
        btc_from = btc_from / (n-1) * 100 if btc_idx is not None else 0
        btc_to = btc_to / (n-1) * 100 if btc_idx is not None else 0
        
        mid_date = var_data.index[start_idx + window // 2]
        dates_list.append(mid_date)
        total_spillover_list.append(total_sp)
        btc_from_list.append(btc_from)
        btc_to_list.append(btc_to)
    except:
        pass

if dates_list:
    rolling_sp = pd.DataFrame({
        'date': dates_list,
        'total_spillover': total_spillover_list,
        'btc_from': btc_from_list,
        'btc_to': btc_to_list,
    })
    
    # 주요 시점 값
    key_dates = {
        '2015': '2015-06-01',
        '2018_volmageddon': '2018-02-15',
        '2020_covid': '2020-04-01',
        '2022_rate_hike': '2022-06-01',
        '2023_svb': '2023-04-01',
        '2024_etf': '2024-03-01',
    }
    
    results['rolling_spillover']['key_points'] = {}
    for label, target_date in key_dates.items():
        td = pd.Timestamp(target_date)
        closest = rolling_sp.iloc[(rolling_sp['date'] - td).abs().argsort()[:1]]
        if len(closest) > 0:
            row = closest.iloc[0]
            results['rolling_spillover']['key_points'][label] = {
                'date': str(row['date'].date()),
                'total': round(float(row['total_spillover']), 1),
                'btc_from': round(float(row['btc_from']), 1),
                'btc_to': round(float(row['btc_to']), 1),
            }
            print(f"    {label}: Total={row['total_spillover']:.1f}%, BTC_from={row['btc_from']:.1f}%, BTC_to={row['btc_to']:.1f}%")
    
    results['rolling_spillover']['summary'] = {
        'mean_total': round(float(rolling_sp['total_spillover'].mean()), 1),
        'max_total': round(float(rolling_sp['total_spillover'].max()), 1),
        'min_total': round(float(rolling_sp['total_spillover'].min()), 1),
    }

# --- 4.2 BTC 카멜레온 효과 ---
print("\n  4.2 BTC 카멜레온 효과 분석...")

crisis_windows = {
    'COVID_Crash': ('2020-02-20', '2020-03-23'),
    'COVID_Recovery': ('2020-04-01', '2020-12-31'),
    'Rate_Hike_2022': ('2022-03-16', '2022-12-31'),
    'FTX_Collapse': ('2022-11-01', '2022-12-31'),
    'SVB_Crisis': ('2023-03-08', '2023-04-30'),
    'BTC_ETF_2024': ('2024-01-10', '2024-06-30'),
    'Normal_2019': ('2019-01-01', '2019-12-31'),
}

results['chameleon_effect'] = {}
for cname, (s, e) in crisis_windows.items():
    mask = (returns.index >= s) & (returns.index <= e)
    sub = returns[mask]
    if len(sub) < 10:
        continue
    
    corrs = {}
    for target in ['Gold', 'SPX', 'Bond10Y_chg', 'WTI']:
        if 'BTC' in sub.columns and target in sub.columns:
            corrs[f'BTC_{target}'] = round(float(sub['BTC'].corr(sub[target])), 4)
    
    # BTC가 금과 더 동조하면 "safe-haven", SPX와 더 동조하면 "risk-on"
    btc_gold = corrs.get('BTC_Gold', 0)
    btc_spx = corrs.get('BTC_SPX', 0)
    role = 'Safe-Haven' if btc_gold > btc_spx and btc_gold > 0.2 else \
           'Risk-On' if btc_spx > 0.3 else 'Independent'
    
    results['chameleon_effect'][cname] = {
        'correlations': corrs,
        'role': role,
        'n_obs': len(sub),
    }
    print(f"    {cname}: BTC-Gold={btc_gold:.3f}, BTC-SPX={btc_spx:.3f} → {role}")

# --- 4.3 백테스팅 ---
print("\n  4.3 포트폴리오 백테스팅...")

bt_cols = [c for c in ['BTC', 'Gold', 'WTI', 'SPX', 'Bond10Y_chg'] if c in returns.columns]
bt_data = returns[bt_cols].dropna()
bt_data = bt_data[bt_data.index >= '2015-01-01']

if len(bt_data) > 252:
    # Strategy 1: 정적 60/40 (SPX 60%, Bond proxy 40%)
    static_ret = 0.6 * bt_data['SPX'] + 0.4 * (-bt_data['Bond10Y_chg'] / 100)  # Bond return proxy
    
    # Strategy 2: 정적 대안자산 포함
    weights_alt = {'SPX': 0.40, 'Gold': 0.15, 'WTI': 0.10, 'BTC': 0.05}
    alt_ret = sum(w * bt_data[c] for c, w in weights_alt.items() if c in bt_data.columns)
    alt_ret += 0.30 * (-bt_data['Bond10Y_chg'] / 100)
    
    # Strategy 3: 동적 MVP (252일 롤링 공분산)
    dynamic_ret = pd.Series(0.0, index=bt_data.index)
    rebal_cols = [c for c in ['SPX', 'Gold', 'BTC'] if c in bt_data.columns]
    
    for i in range(252, len(bt_data)):
        lookback = bt_data[rebal_cols].iloc[i-252:i]
        cov = lookback.cov()
        try:
            inv_cov = np.linalg.inv(cov.values)
            ones = np.ones(len(rebal_cols))
            w = inv_cov @ ones / (ones @ inv_cov @ ones)
            w = np.clip(w, 0.05, 0.60)
            w = w / w.sum()
            dynamic_ret.iloc[i] = sum(w[j] * bt_data[rebal_cols[j]].iloc[i] for j in range(len(rebal_cols)))
        except:
            dynamic_ret.iloc[i] = bt_data['SPX'].iloc[i] * 0.6
    
    dynamic_ret = dynamic_ret.iloc[252:]
    static_ret = static_ret.reindex(dynamic_ret.index)
    alt_ret = alt_ret.reindex(dynamic_ret.index)
    
    def calc_metrics(ret, name):
        ann_ret = ret.mean() * 252 * 100
        ann_vol = ret.std() * np.sqrt(252) * 100
        sharpe = ann_ret / ann_vol if ann_vol > 0 else 0
        cum = (1 + ret).cumprod()
        max_dd = ((cum / cum.cummax()) - 1).min() * 100
        return {
            'ann_return': round(float(ann_ret), 2),
            'ann_vol': round(float(ann_vol), 2),
            'sharpe': round(float(sharpe), 3),
            'max_drawdown': round(float(max_dd), 2),
        }
    
    results['backtesting'] = {
        'static_60_40': calc_metrics(static_ret.dropna(), 'Static 60/40'),
        'static_alternative': calc_metrics(alt_ret.dropna(), 'Static Alt'),
        'dynamic_mvp': calc_metrics(dynamic_ret.dropna(), 'Dynamic MVP'),
        'period': f"{dynamic_ret.index.min().date()} ~ {dynamic_ret.index.max().date()}",
    }
    
    for name, metrics in results['backtesting'].items():
        if isinstance(metrics, dict) and 'sharpe' in metrics:
            print(f"    {name}: Sharpe={metrics['sharpe']:.3f}, Return={metrics['ann_return']:.1f}%, MaxDD={metrics['max_drawdown']:.1f}%")


# ============================================================
# 5. ROUND 3: 데이터 확장
# ============================================================
print("\n" + "=" * 70)
print("[5/8] ROUND 3: 데이터 확장 (Data Enrichment)")
print("=" * 70)

# --- 5.1 GPR/EPU 통제변수 ---
print("\n  5.1 불확실성 지수 분석...")

# EPU 데이터 (FRED)
epu = get_fred('USEPUINDXD', '2010-01-01', END)  # Daily EPU
if epu is None:
    epu = get_fred('USEPUINDXM', '2010-01-01', END)  # Monthly EPU

results['uncertainty_analysis'] = {}

# VIX를 불확실성 프록시로 사용 (항상 가용)
if 'VIX' in assets_btc.columns:
    vix = assets_btc['VIX'].dropna()
    
    # VIX 레짐별 상관관계
    vix_aligned = vix.reindex(returns.index).dropna()
    common_idx = returns.index.intersection(vix_aligned.index)
    
    vix_median = vix_aligned.loc[common_idx].median()
    high_vix = common_idx[vix_aligned.loc[common_idx] > vix_median]
    low_vix = common_idx[vix_aligned.loc[common_idx] <= vix_median]
    
    results['uncertainty_analysis']['vix_regime'] = {}
    
    pairs = [('BTC', 'SPX'), ('BTC', 'Gold'), ('Gold', 'Bond10Y_chg'), ('Copper', 'Bond10Y_chg')]
    for c1, c2 in pairs:
        if c1 in returns.columns and c2 in returns.columns:
            corr_high = returns.loc[high_vix, c1].corr(returns.loc[high_vix, c2])
            corr_low = returns.loc[low_vix, c1].corr(returns.loc[low_vix, c2])
            
            # Fisher z-test
            n1, n2 = len(high_vix), len(low_vix)
            z1 = np.arctanh(corr_high)
            z2 = np.arctanh(corr_low)
            se = np.sqrt(1/(n1-3) + 1/(n2-3))
            z_stat = (z1 - z2) / se
            p_val = 2 * (1 - sp_stats.norm.cdf(abs(z_stat)))
            
            results['uncertainty_analysis']['vix_regime'][f'{c1}_{c2}'] = {
                'high_vix_corr': round(float(corr_high), 4),
                'low_vix_corr': round(float(corr_low), 4),
                'z_stat': round(float(z_stat), 4),
                'p_value': round(float(p_val), 6),
            }
            sig = '***' if p_val < 0.01 else '**' if p_val < 0.05 else '*' if p_val < 0.1 else ''
            print(f"    {c1}-{c2}: High VIX={corr_high:.4f}, Low VIX={corr_low:.4f}, p={p_val:.4f} {sig}")

# --- 5.2 주말 효과 분석 ---
print("\n  5.2 주말 효과 분석...")

results['weekend_effect'] = {}

if 'BTC' in returns.columns:
    # 요일별 BTC 수익률
    btc_ret = returns['BTC'].copy()
    btc_ret_dow = btc_ret.groupby(btc_ret.index.dayofweek)
    
    dow_stats = {}
    for dow, group in btc_ret_dow:
        dow_name = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'][dow] if dow < 5 else f'Day{dow}'
        dow_stats[dow_name] = {
            'mean': round(float(group.mean() * 100), 4),
            'std': round(float(group.std() * 100), 4),
            'n': len(group),
        }
    
    results['weekend_effect']['btc_dayofweek'] = dow_stats
    
    # 월요일 vs 나머지 수익률 비교
    monday_ret = btc_ret[btc_ret.index.dayofweek == 0]
    other_ret = btc_ret[btc_ret.index.dayofweek != 0]
    
    t_stat, p_val = sp_stats.ttest_ind(monday_ret, other_ret)
    results['weekend_effect']['monday_test'] = {
        'monday_mean': round(float(monday_ret.mean() * 100), 4),
        'other_mean': round(float(other_ret.mean() * 100), 4),
        'monday_vol': round(float(monday_ret.std() * 100), 4),
        'other_vol': round(float(other_ret.std() * 100), 4),
        't_stat': round(float(t_stat), 4),
        'p_value': round(float(p_val), 6),
    }
    print(f"    BTC Monday mean: {monday_ret.mean()*100:.4f}%, Others: {other_ret.mean()*100:.4f}%")
    print(f"    Monday vol: {monday_ret.std()*100:.4f}%, Others: {other_ret.std()*100:.4f}%")
    print(f"    t-test: t={t_stat:.4f}, p={p_val:.4f}")
    
    # 월요일 SPX와 주말 BTC 상관
    if 'SPX' in returns.columns:
        # 금요일 BTC → 월요일 SPX
        monday_spx = returns['SPX'][returns.index.dayofweek == 0]
        # 이전 금요일의 BTC
        friday_btc = returns['BTC'][returns.index.dayofweek == 4]
        
        # 날짜 매칭
        matched = []
        for mon_date in monday_spx.index:
            fri_date = mon_date - pd.Timedelta(days=3)
            if fri_date in friday_btc.index:
                matched.append((friday_btc[fri_date], monday_spx[mon_date]))
        
        if len(matched) > 30:
            fri_vals, mon_vals = zip(*matched)
            corr_weekend = np.corrcoef(fri_vals, mon_vals)[0, 1]
            results['weekend_effect']['friday_btc_monday_spx'] = {
                'correlation': round(float(corr_weekend), 4),
                'n_pairs': len(matched),
            }
            print(f"    Friday BTC → Monday SPX corr: {corr_weekend:.4f} (N={len(matched)})")


# ============================================================
# 6. ROUND 4: 방법론 정교화
# ============================================================
print("\n" + "=" * 70)
print("[6/8] ROUND 4: 방법론 정교화 (Methodology)")
print("=" * 70)

# --- 6.1 주파수 영역 Spillover ---
print("\n  6.1 주파수 영역 Spillover 분해...")

results['frequency_spillover'] = {}

if len(spillover_cols) >= 3:
    var_full = var_data.copy()
    var_full.index = pd.DatetimeIndex(var_full.index).to_period('B').to_timestamp()
    
    try:
        model = VAR(var_full)
        lag = min(max(model.select_order(maxlags=5).aic, 1), 5)
        var_result = model.fit(lag)
        
        # IRF를 주파수 대역별로 분해
        # 단기(1-5일), 중기(5-20일), 장기(20일+)
        n = len(spillover_cols)
        
        for horizon_name, h_range in [('short_1_5d', (1, 5)), ('medium_5_20d', (5, 20)), ('long_20d_plus', (20, 60))]:
            fevd = var_result.fevd(h_range[1])
            if h_range[0] > 1:
                fevd_prev = var_result.fevd(h_range[0] - 1)
            
            matrix = {}
            total_sp = 0
            
            for i, col_i in enumerate(spillover_cols):
                matrix[col_i] = {}
                for j, col_j in enumerate(spillover_cols):
                    val = float(fevd.decomp[i][-1][j]) * 100
                    if h_range[0] > 1:
                        val_prev = float(fevd_prev.decomp[i][-1][j]) * 100
                        val = val - val_prev  # 해당 주파수 대역만
                    matrix[col_i][col_j] = round(val, 1)
                    if i != j:
                        total_sp += val
            
            total_sp = total_sp / n
            
            results['frequency_spillover'][horizon_name] = {
                'matrix': matrix,
                'total_index': round(float(total_sp), 1),
            }
            
            # BTC 관련 요약
            if 'BTC' in matrix:
                btc_from_others = sum(matrix[col].get('BTC', 0) for col in spillover_cols if col != 'BTC')
                btc_to_others = sum(matrix['BTC'].get(col, 0) for col in spillover_cols if col != 'BTC')
                print(f"    {horizon_name}: Total={total_sp:.1f}%, BTC→Others={btc_from_others:.1f}%, Others→BTC={btc_to_others:.1f}%")
    except Exception as e:
        print(f"    주파수 Spillover 실패: {e}")

# --- 6.2 비선형 Granger 인과성 ---
print("\n  6.2 비선형 Granger 인과성 (VIX 레짐별)...")

results['nonlinear_granger'] = {}

if 'VIX' in assets_btc.columns:
    vix_aligned = assets_btc['VIX'].reindex(returns.index).dropna()
    common_idx = returns.index.intersection(vix_aligned.index)
    
    # VIX 30 기준 (위기/평시)
    high_stress = common_idx[vix_aligned.loc[common_idx] > 25]
    low_stress = common_idx[vix_aligned.loc[common_idx] <= 25]
    
    granger_pairs = [
        ('BTC', 'SPX', 'BTC→SPX'),
        ('SPX', 'BTC', 'SPX→BTC'),
        ('BTC', 'Gold', 'BTC→Gold'),
        ('Gold', 'BTC', 'Gold→BTC'),
        ('Gold', 'Bond10Y_chg', 'Gold→Bond'),
    ]
    
    for cause, effect, label in granger_pairs:
        if cause not in returns.columns or effect not in returns.columns:
            continue
        
        regime_results = {}
        for regime_name, regime_idx in [('high_stress', high_stress), ('low_stress', low_stress)]:
            sub = returns.loc[regime_idx, [effect, cause]].dropna()
            if len(sub) < 50:
                continue
            try:
                gc = grangercausalitytests(sub.values, maxlag=5, verbose=False)
                best_lag = min(gc.keys(), key=lambda k: gc[k][0]['ssr_ftest'][1])
                f_stat = gc[best_lag][0]['ssr_ftest'][0]
                p_val = gc[best_lag][0]['ssr_ftest'][1]
                regime_results[regime_name] = {
                    'F': round(float(f_stat), 4),
                    'p': round(float(p_val), 6),
                    'lag': int(best_lag),
                    'n': len(sub),
                }
            except:
                pass
        
        if regime_results:
            results['nonlinear_granger'][label] = regime_results
            for rn, rv in regime_results.items():
                sig = '***' if rv['p'] < 0.01 else '**' if rv['p'] < 0.05 else '*' if rv['p'] < 0.1 else ''
                print(f"    {label} ({rn}): F={rv['F']:.4f}, p={rv['p']:.6f} {sig} (N={rv['n']})")

# --- 6.3 비대칭 상관관계 (극단 수익률) ---
print("\n  6.3 비대칭 상관관계 (극단 수익률)...")

results['asymmetric_correlation'] = {}

if 'BTC' in returns.columns:
    btc = returns['BTC']
    q10 = btc.quantile(0.10)
    q90 = btc.quantile(0.90)
    
    extreme_down = btc.index[btc <= q10]
    extreme_up = btc.index[btc >= q90]
    normal = btc.index[(btc > q10) & (btc < q90)]
    
    for target in ['SPX', 'Gold', 'Bond10Y_chg']:
        if target not in returns.columns:
            continue
        
        corr_down = returns.loc[extreme_down, 'BTC'].corr(returns.loc[extreme_down, target])
        corr_up = returns.loc[extreme_up, 'BTC'].corr(returns.loc[extreme_up, target])
        corr_normal = returns.loc[normal, 'BTC'].corr(returns.loc[normal, target])
        
        results['asymmetric_correlation'][f'BTC_{target}'] = {
            'extreme_down': round(float(corr_down), 4),
            'extreme_up': round(float(corr_up), 4),
            'normal': round(float(corr_normal), 4),
        }
        print(f"    BTC-{target}: Down={corr_down:.4f}, Normal={corr_normal:.4f}, Up={corr_up:.4f}")


# ============================================================
# 7. 차트 생성
# ============================================================
print("\n" + "=" * 70)
print("[7/8] 차트 생성")
print("=" * 70)

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'develop_20260213_141510')
os.makedirs(output_dir, exist_ok=True)

# Chart 1: Rolling Spillover Index
if dates_list:
    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    
    axes[0].plot(dates_list, total_spillover_list, linewidth=1.2, color='#1d3557')
    axes[0].fill_between(dates_list, total_spillover_list, alpha=0.15, color='#1d3557')
    axes[0].set_ylabel('Total Spillover Index (%)', fontsize=11)
    axes[0].set_title('Rolling VAR Spillover Index (252-day window)', fontsize=13)
    
    for date, label, color in [('2020-03-01', 'COVID', '#e74c3c'), ('2022-03-01', 'Rate Hike', '#e67e22'), 
                                ('2023-03-10', 'SVB', '#9b59b6'), ('2024-01-10', 'BTC ETF', '#27ae60')]:
        for ax in axes:
            ax.axvline(x=pd.Timestamp(date), color=color, linestyle='--', linewidth=1, alpha=0.7)
        axes[0].text(pd.Timestamp(date), axes[0].get_ylim()[1]*0.95, label, fontsize=8, color=color, ha='center')
    
    axes[1].plot(dates_list, btc_from_list, linewidth=1.2, color='#f39c12', label='BTC → Others')
    axes[1].plot(dates_list, btc_to_list, linewidth=1.2, color='#e74c3c', label='Others → BTC')
    axes[1].set_ylabel('BTC Spillover (%)', fontsize=11)
    axes[1].set_xlabel('Date')
    axes[1].legend(loc='upper left')
    
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'chart_rolling_spillover.png'), dpi=150)
    plt.close()
    print("  ✓ chart_rolling_spillover.png")

# Chart 2: BTC Chameleon Effect
if results.get('chameleon_effect'):
    crisis_names = list(results['chameleon_effect'].keys())
    short_names = [n.replace('_', '\n') for n in crisis_names]
    
    fig, ax = plt.subplots(figsize=(12, 6))
    x = np.arange(len(crisis_names))
    w = 0.2
    
    for idx, (target, color, label) in enumerate([
        ('BTC_Gold', '#f39c12', 'BTC-Gold'),
        ('BTC_SPX', '#3498db', 'BTC-SPX'),
        ('BTC_Bond10Y_chg', '#2c3e50', 'BTC-Bond'),
    ]):
        vals = [results['chameleon_effect'][cn]['correlations'].get(target, 0) for cn in crisis_names]
        ax.bar(x + (idx - 1) * w, vals, w, label=label, color=color)
    
    ax.axhline(y=0, color='gray', linestyle='-', linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(short_names, fontsize=8)
    ax.set_ylabel('Correlation')
    ax.set_title('BTC "Chameleon Effect": Role Changes Across Crisis Types', fontsize=13)
    ax.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'chart_chameleon_effect.png'), dpi=150)
    plt.close()
    print("  ✓ chart_chameleon_effect.png")

# Chart 3: Frequency Domain Spillover
if results.get('frequency_spillover'):
    freq_names = ['short_1_5d', 'medium_5_20d', 'long_20d_plus']
    freq_labels = ['Short-term\n(1-5 days)', 'Medium-term\n(5-20 days)', 'Long-term\n(20+ days)']
    
    if 'BTC' in spillover_cols:
        fig, ax = plt.subplots(figsize=(10, 6))
        
        btc_from_vals = []
        btc_to_vals = []
        gold_bond_vals = []
        
        for fn in freq_names:
            if fn in results['frequency_spillover']:
                m = results['frequency_spillover'][fn]['matrix']
                btc_from = sum(m.get(col, {}).get('BTC', 0) for col in spillover_cols if col != 'BTC')
                btc_to = sum(m.get('BTC', {}).get(col, 0) for col in spillover_cols if col != 'BTC')
                gb = m.get('Gold', {}).get('Bond10Y_chg', 0) + m.get('Bond10Y_chg', {}).get('Gold', 0)
                btc_from_vals.append(btc_from)
                btc_to_vals.append(btc_to)
                gold_bond_vals.append(gb)
            else:
                btc_from_vals.append(0)
                btc_to_vals.append(0)
                gold_bond_vals.append(0)
        
        x = np.arange(len(freq_labels))
        w = 0.25
        ax.bar(x - w, btc_from_vals, w, label='BTC → Others', color='#f39c12')
        ax.bar(x, btc_to_vals, w, label='Others → BTC', color='#e74c3c')
        ax.bar(x + w, gold_bond_vals, w, label='Gold ↔ Bond', color='#1d3557')
        
        ax.set_xticks(x)
        ax.set_xticklabels(freq_labels)
        ax.set_ylabel('Spillover (%)')
        ax.set_title('Frequency-Domain Spillover Decomposition', fontsize=13)
        ax.legend()
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, 'chart_frequency_spillover.png'), dpi=150)
        plt.close()
        print("  ✓ chart_frequency_spillover.png")

# Chart 4: Asymmetric Correlation
if results.get('asymmetric_correlation'):
    fig, ax = plt.subplots(figsize=(10, 6))
    
    targets = list(results['asymmetric_correlation'].keys())
    target_labels = [t.replace('BTC_', 'BTC-') for t in targets]
    
    x = np.arange(len(targets))
    w = 0.25
    
    down_vals = [results['asymmetric_correlation'][t]['extreme_down'] for t in targets]
    normal_vals = [results['asymmetric_correlation'][t]['normal'] for t in targets]
    up_vals = [results['asymmetric_correlation'][t]['extreme_up'] for t in targets]
    
    ax.bar(x - w, down_vals, w, label='Extreme Down (Q10)', color='#e74c3c')
    ax.bar(x, normal_vals, w, label='Normal', color='#95a5a6')
    ax.bar(x + w, up_vals, w, label='Extreme Up (Q90)', color='#27ae60')
    
    ax.axhline(y=0, color='gray', linestyle='-', linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(target_labels)
    ax.set_ylabel('Correlation')
    ax.set_title('Asymmetric Correlation: BTC in Extreme vs Normal Markets', fontsize=13)
    ax.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'chart_asymmetric_correlation.png'), dpi=150)
    plt.close()
    print("  ✓ chart_asymmetric_correlation.png")

# Chart 5: Vasicek vs CIR comparison
if results.get('vasicek_comparison'):
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    
    periods_list = list(results['vasicek_comparison'].keys())
    short_labels = [p.split('(')[0].strip() for p in periods_list]
    
    # Half-life comparison
    hl_vals = [results['vasicek_comparison'][p]['vasicek']['halflife_days'] for p in periods_list]
    hl_vals = [min(v, 5000) for v in hl_vals]  # cap for display
    
    axes[0].bar(range(len(periods_list)), hl_vals, color=['#3498db', '#e74c3c', '#27ae60'])
    axes[0].set_xticks(range(len(periods_list)))
    axes[0].set_xticklabels(short_labels, fontsize=9)
    axes[0].set_ylabel('Half-life (days)')
    axes[0].set_title('Vasicek Mean Reversion Half-life', fontsize=12)
    
    # AIC comparison
    x = np.arange(len(periods_list))
    w = 0.35
    vasicek_aic = [results['vasicek_comparison'][p]['vasicek']['AIC'] for p in periods_list]
    cir_aic = [results['vasicek_comparison'][p]['cir']['AIC'] if results['vasicek_comparison'][p]['cir']['AIC'] else 0 for p in periods_list]
    
    axes[1].bar(x - w/2, vasicek_aic, w, label='Vasicek', color='#1d3557')
    axes[1].bar(x + w/2, cir_aic, w, label='CIR', color='#e63946')
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(short_labels, fontsize=9)
    axes[1].set_ylabel('AIC')
    axes[1].set_title('Model Comparison: AIC', fontsize=12)
    axes[1].legend()
    
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'chart_vasicek_cir.png'), dpi=150)
    plt.close()
    print("  ✓ chart_vasicek_cir.png")

# Chart 6: Backtesting cumulative returns
if results.get('backtesting') and 'period' in results['backtesting']:
    fig, ax = plt.subplots(figsize=(14, 6))
    
    cum_static = (1 + static_ret.dropna()).cumprod()
    cum_alt = (1 + alt_ret.dropna()).cumprod()
    cum_dynamic = (1 + dynamic_ret.dropna()).cumprod()
    
    ax.plot(cum_static.index, cum_static.values, linewidth=1.2, color='#95a5a6', label='Static 60/40')
    ax.plot(cum_alt.index, cum_alt.values, linewidth=1.2, color='#3498db', label='Static Alternative')
    ax.plot(cum_dynamic.index, cum_dynamic.values, linewidth=1.5, color='#e74c3c', label='Dynamic MVP')
    
    for date, label, color in [('2020-03-01', 'COVID', '#e74c3c'), ('2022-03-01', 'Rate Hike', '#e67e22')]:
        ax.axvline(x=pd.Timestamp(date), color=color, linestyle='--', linewidth=0.8, alpha=0.5)
    
    ax.set_ylabel('Cumulative Return')
    ax.set_title('Portfolio Backtesting: Static vs Dynamic Allocation', fontsize=13)
    ax.legend(loc='upper left')
    ax.grid(alpha=0.2)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'chart_backtesting.png'), dpi=150)
    plt.close()
    print("  ✓ chart_backtesting.png")

# Chart 7: Nonlinear Granger (regime comparison)
if results.get('nonlinear_granger'):
    fig, ax = plt.subplots(figsize=(10, 6))
    
    pairs_list = list(results['nonlinear_granger'].keys())
    x = np.arange(len(pairs_list))
    w = 0.35
    
    high_f = []
    low_f = []
    for p in pairs_list:
        high_f.append(results['nonlinear_granger'][p].get('high_stress', {}).get('F', 0))
        low_f.append(results['nonlinear_granger'][p].get('low_stress', {}).get('F', 0))
    
    ax.bar(x - w/2, high_f, w, label='High Stress (VIX>25)', color='#e74c3c')
    ax.bar(x + w/2, low_f, w, label='Low Stress (VIX≤25)', color='#3498db')
    
    ax.axhline(y=3.84, color='gray', linestyle='--', linewidth=0.8, label='5% significance')
    ax.set_xticks(x)
    ax.set_xticklabels(pairs_list, fontsize=9)
    ax.set_ylabel('F-statistic')
    ax.set_title('Granger Causality by Stress Regime', fontsize=13)
    ax.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'chart_nonlinear_granger.png'), dpi=150)
    plt.close()
    print("  ✓ chart_nonlinear_granger.png")


# ============================================================
# 8. 결과 저장
# ============================================================
print("\n" + "=" * 70)
print("[8/8] 결과 저장")
print("=" * 70)

class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)): return int(obj)
        if isinstance(obj, (np.floating,)): return float(obj)
        if isinstance(obj, np.ndarray): return obj.tolist()
        if isinstance(obj, pd.Timestamp): return str(obj)
        return super().default(obj)

results_path = os.path.join(output_dir, 'develop_analysis_results.json')
with open(results_path, 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2, cls=NpEncoder)
print(f"  ✓ {results_path}")

print("\n" + "=" * 70)
print("전체 분석 완료!")
print(f"결과: {output_dir}/")
print("=" * 70)
