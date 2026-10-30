from __future__ import annotations
import re
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.tsa.stattools import adfuller
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.holtwinters import (
    ExponentialSmoothing, SimpleExpSmoothing, Holt,
)
from statsmodels.tsa.seasonal import seasonal_decompose
from sklearn.metrics import (
    mean_absolute_error, mean_squared_error,
    mean_absolute_percentage_error, r2_score,
)
from sklearn.linear_model import LinearRegression

warnings.filterwarnings("ignore")


# ============================================================================
# INTERNAL HELPERS
# ============================================================================

_MONTH_RE = re.compile(r'^[A-Za-z]{3}-\d{4}$')


def _month_columns(df: pd.DataFrame) -> list:
    """Return month columns (Mon-YYYY) sorted chronologically."""
    cols = [c for c in df.columns if _MONTH_RE.match(str(c))]
    return sorted(cols, key=lambda m: pd.to_datetime(m, format='%b-%Y'))


@lru_cache(maxsize=128)
def cached_adfuller(data_tuple):
    try:
        r = adfuller(np.array(data_tuple))
        return r[1], r[0]
    except Exception:
        return 1.0, 0


def fast_trend_strength(data_series):
    x = np.arange(len(data_series))
    y = data_series.values if hasattr(data_series, 'values') else np.asarray(data_series)
    n = len(x)
    x_mean, y_mean = x.mean(), y.mean()
    num = np.sum((x - x_mean) * (y - y_mean))
    den = np.sqrt(np.sum((x - x_mean) ** 2) * np.sum((y - y_mean) ** 2))
    if den == 0:
        return 0, 0, 1.0
    r = num / den
    r2 = r ** 2
    if n > 2:
        t_stat = r * np.sqrt((n - 2) / (1 - r2 + 1e-8))
        p_value = 2 * stats.t.sf(np.abs(t_stat), n - 2)
    else:
        p_value = 1.0
    slope = num / np.sum((x - x_mean) ** 2)
    return r2, slope, p_value


def get_recommended_model_by_criteria(chars):
    if not chars['is_stationary']:
        return "SARIMA" if chars['has_seasonality'] else "ARIMA"
    if chars['has_trend'] and chars['has_seasonality']:
        return "TES"
    if chars['has_trend'] and not chars['has_seasonality']:
        return "DES"
    if not chars['has_trend']:
        if chars['has_seasonality']:
            return "SARIMA" if chars['volatility_level'] == "High" else "TES"
        if chars['volatility_level'] == "Low":
            return "SMA"
        if chars['volatility_level'] == "Moderate":
            return "EMA"
        return "SES"
    return "SES"


def get_candidate_models(chars):
    if chars['is_stationary'] and chars['has_trend'] and chars['has_seasonality']:
        c = ['TES', 'SARIMA']
    elif chars['is_stationary'] and chars['has_trend'] and not chars['has_seasonality']:
        c = ['DES', 'SES']
    elif chars['is_stationary'] and not chars['has_trend'] and chars['has_seasonality']:
        c = ['SARIMA', 'TES'] if chars['volatility_level'] == 'High' else ['TES', 'SARIMA']
    elif chars['is_stationary'] and not chars['has_trend'] and not chars['has_seasonality']:
        if chars['volatility_level'] == 'Low':
            c = ['SMA', 'SES']
        elif chars['volatility_level'] == 'Moderate':
            c = ['EMA', 'SES']
        else:
            c = ['SES', 'ARIMA']
    elif not chars['is_stationary'] and chars['has_seasonality']:
        c = ['SARIMA', 'ARIMA']
    elif not chars['is_stationary'] and not chars['has_seasonality']:
        c = ['ARIMA', 'SES']
    else:
        c = ['SES', 'SMA', 'ARIMA']
    return c[:3]


# ============================================================================
# MONTHLY ANALYSIS
# ============================================================================

def analyze_data_characteristics_optimized(data_series):
    results = {
        'is_stationary': False, 'has_trend': False, 'has_seasonality': False,
        'trend_strength': 0, 'seasonal_strength': 0, 'trend_direction': 'none',
        'trend_pvalue': 1.0, 'cv': 0, 'volatility_level': 'Low',
        'adf_pvalue': 1.0, 'trend_ambiguous': False, 'seasonal_ambiguous': False,
        'expert_decision_needed': False,
    }
    data_clean = data_series[data_series >= 0]
    if len(data_clean) < 6:
        return results

    adf_pvalue, _ = cached_adfuller(tuple(data_clean.values))
    results['is_stationary'] = adf_pvalue < 0.05
    results['adf_pvalue'] = adf_pvalue

    try:
        ts, slope, p = fast_trend_strength(data_clean)
        results['trend_strength'] = ts
        results['trend_pvalue'] = p
        results['trend_direction'] = 'up' if slope > 0 else 'down' if slope < 0 else 'none'
        results['has_trend'] = ts > 0.35 and p < 0.05
        results['trend_ambiguous'] = 0.3 <= ts <= 0.5
    except Exception:
        results['has_trend'] = False

    if len(data_clean) >= 24:
        try:
            decomp = seasonal_decompose(data_clean.values, model='additive',
                                        period=12, extrapolate_trend='freq')
            sv = np.var(decomp.seasonal)
            rv = np.var(decomp.resid)
            tv = sv + rv
            if tv > 0:
                results['seasonal_strength'] = 1 - (rv / tv)
            results['has_seasonality'] = results['seasonal_strength'] > 0.35
            results['seasonal_ambiguous'] = 0.3 <= results['seasonal_strength'] <= 0.5
        except Exception:
            pass

    results['expert_decision_needed'] = (
        results['trend_ambiguous'] or results['seasonal_ambiguous']
    )
    results['cv'] = data_clean.std() / (data_clean.mean() + 1e-6)
    results['volatility_level'] = (
        "Low" if results['cv'] < 0.3
        else "Moderate" if results['cv'] < 0.6
        else "High"
    )
    return results


# ============================================================================
# MONTHLY MODEL TRAINING
# ============================================================================

def train_sma_with_params(train_data, test_data):
    best_mae, best_forecast, best_window = float('inf'), None, 2
    for window in [2, 3, 4]:
        if window > len(train_data):
            continue
        forecasts, last = [], list(train_data.values[-window:])
        for _ in range(len(test_data)):
            f = np.mean(last[-window:])
            forecasts.append(f)
            last.append(f)
        mae = mean_absolute_error(test_data.values[:len(forecasts)], forecasts)
        if mae < best_mae:
            best_mae, best_forecast, best_window = mae, forecasts, window
    return (np.array(best_forecast) if best_forecast is not None else None,
            best_window)


def train_ema_with_params(train_data, test_data):
    best_mae, best_forecast, best_span, best_alpha = float('inf'), None, 2, 0.5
    for span in [2, 3, 4]:
        if span > len(train_data):
            continue
        alpha = 2 / (span + 1)
        forecasts, ema = [], np.mean(train_data.values[-span:])
        for i in range(len(test_data)):
            if i == 0:
                ema = alpha * train_data.values[-1] + (1 - alpha) * ema
            else:
                ema = alpha * forecasts[-1] + (1 - alpha) * ema
            forecasts.append(ema)
        mae = mean_absolute_error(test_data.values[:len(forecasts)], forecasts)
        if mae < best_mae:
            best_mae, best_forecast, best_span, best_alpha = mae, forecasts, span, alpha
    return (np.array(best_forecast) if best_forecast is not None else None,
            best_span, best_alpha)


def find_best_arima_auto_fast(train_data):
    best_aic, best_order, best_model = float('inf'), None, None
    n = len(train_data)
    max_p = 1 if n < 24 else 2
    max_q = 1 if n < 24 else 2
    for p in range(max_p + 1):
        for d in range(2):
            for q in range(max_q + 1):
                try:
                    m = ARIMA(train_data, order=(p, d, q)).fit(
                        method_kwargs={'disp': False, 'maxiter': 100})
                    if m.aic < best_aic:
                        best_aic, best_order, best_model = m.aic, (p, d, q), m
                except Exception:
                    continue
    return best_model, best_order, best_aic


def train_sarima_with_params(train_data, test_data):
    """SARIMA with graceful fallback for short history."""
    if len(train_data) < 12:
        try:
            m = ARIMA(train_data.values, order=(1, 1, 1)).fit(
                method_kwargs={'disp': False, 'maxiter': 100})
            f = np.asarray(m.forecast(steps=len(test_data))).flatten()
            tv = test_data.values.flatten()
            return (f,
                    mean_absolute_error(tv, f),
                    np.sqrt(mean_squared_error(tv, f)),
                    mean_absolute_percentage_error(tv, f) * 100,
                    r2_score(tv, f) if len(tv) > 1 else -999,
                    (1, 1, 1),
                    (0, 0, 0, 12))
        except Exception:
            return None

    best_aic, best_model, best_order, best_sorder = float('inf'), None, None, None
    max_p = 1 if len(train_data) < 18 else 2
    max_q = 1 if len(train_data) < 18 else 2
    try_seasonal = len(train_data) >= 24

    for p in range(max_p + 1):
        for d in [0, 1]:
            for q in range(max_q + 1):
                if try_seasonal:
                    seasons = [(P, D, Q, 12)
                               for P in [0, 1] for D in [0, 1] for Q in [0, 1]]
                else:
                    seasons = [(0, 0, 0, 12)]
                for sorder in seasons:
                    try:
                        m = SARIMAX(train_data.values, order=(p, d, q),
                                    seasonal_order=sorder,
                                    enforce_stationarity=False,
                                    enforce_invertibility=False).fit(
                            disp=False, maxiter=100)
                        if m.aic < best_aic:
                            best_aic, best_model = m.aic, m
                            best_order, best_sorder = (p, d, q), sorder
                    except Exception:
                        continue

    if best_model is None:
        return None
    try:
        f = np.asarray(best_model.forecast(steps=len(test_data))).flatten()
        tv = test_data.values.flatten()
        return (f,
                mean_absolute_error(tv, f),
                np.sqrt(mean_squared_error(tv, f)),
                mean_absolute_percentage_error(tv, f) * 100,
                r2_score(tv, f) if len(tv) > 1 else -999,
                best_order, best_sorder)
    except Exception:
        return None


def train_des_with_params(train_data, test_data):
    try:
        m = Holt(train_data.values).fit(optimized=True)
        f = m.forecast(steps=len(test_data))
        tv = test_data.values
        return (f,
                mean_absolute_error(tv, f),
                np.sqrt(mean_squared_error(tv, f)),
                mean_absolute_percentage_error(tv, f) * 100,
                r2_score(tv, f) if len(tv) > 1 else -999,
                m.params.get('smoothing_level', 0.5),
                m.params.get('smoothing_trend', 0.5))
    except Exception:
        return None, None, None, None, None, None, None


def train_tes_with_params(train_data, test_data):
    """TES with graceful fallback to DES for short history."""
    try:
        period = min(12, len(train_data) // 2)
        if period >= 2:
            m = ExponentialSmoothing(
                train_data.values, trend='add', seasonal='add',
                seasonal_periods=period).fit(optimized=True)
            f = m.forecast(steps=len(test_data))
            tv = test_data.values
            return (f,
                    mean_absolute_error(tv, f),
                    np.sqrt(mean_squared_error(tv, f)),
                    mean_absolute_percentage_error(tv, f) * 100,
                    r2_score(tv, f) if len(tv) > 1 else -999,
                    m.params.get('smoothing_level', 0.5),
                    m.params.get('smoothing_trend', 0.5),
                    m.params.get('smoothing_seasonal', 0.5))
    except Exception:
        pass
    # Fallback to DES
    try:
        m = Holt(train_data.values).fit(optimized=True)
        f = m.forecast(steps=len(test_data))
        tv = test_data.values
        return (f,
                mean_absolute_error(tv, f),
                np.sqrt(mean_squared_error(tv, f)),
                mean_absolute_percentage_error(tv, f) * 100,
                r2_score(tv, f) if len(tv) > 1 else -999,
                m.params.get('smoothing_level', 0.5),
                m.params.get('smoothing_trend', 0.5),
                0.0)
    except Exception:
        return None, None, None, None, None, None, None, None


def generate_future_forecast_fast(data_series, model_name, forecast_months):
    dp = data_series[data_series >= 0]
    last_date = dp.index[-1]
    future_dates = pd.date_range(
        start=last_date, periods=forecast_months + 1, freq='MS')[1:]
    try:
        if model_name == 'SMA':
            w = 3
            vals, last = [], list(dp.values[-w:])
            for _ in range(forecast_months):
                f = np.mean(last[-w:])
                vals.append(f); last.append(f)
        elif model_name == 'EMA':
            span = 3; alpha = 2 / (span + 1)
            vals, ema = [], np.mean(dp.values[-span:])
            for i in range(forecast_months):
                ema = (alpha * dp.values[-1] + (1 - alpha) * ema) if i == 0 \
                      else (alpha * vals[-1] + (1 - alpha) * ema)
                vals.append(ema)
        elif model_name == 'ARIMA':
            m = ARIMA(dp.values, order=(1, 1, 1)).fit(
                method_kwargs={'disp': False})
            vals = m.forecast(steps=forecast_months)
        elif model_name == 'SARIMA':
            try:
                m = SARIMAX(dp.values, order=(1, 1, 1),
                            seasonal_order=(1, 1, 1, 12)).fit(disp=False)
                vals = m.forecast(steps=forecast_months)
            except Exception:
                m = ARIMA(dp.values, order=(1, 1, 1)).fit(
                    method_kwargs={'disp': False})
                vals = m.forecast(steps=forecast_months)
        elif model_name == 'SES':
            m = SimpleExpSmoothing(dp.values).fit(optimized=True)
            vals = m.forecast(steps=forecast_months)
        elif model_name == 'DES':
            m = Holt(dp.values).fit(optimized=True)
            vals = m.forecast(steps=forecast_months)
        elif model_name == 'TES':
            period = min(12, len(dp) // 2)
            if period >= 2:
                m = ExponentialSmoothing(dp.values, trend='add',
                                         seasonal='add',
                                         seasonal_periods=period).fit(optimized=True)
                vals = m.forecast(steps=forecast_months)
            else:
                m = Holt(dp.values).fit(optimized=True)
                vals = m.forecast(steps=forecast_months)
        else:
            vals = np.full(forecast_months, dp.mean())
        return np.maximum(vals, 0), future_dates
    except Exception:
        vals = np.full(forecast_months, dp.mean())
        return vals, future_dates


def process_single_material_optimized(material_name, data_series,
                                      train_pct, forecast_months):
    try:
        md = data_series[data_series >= 0]
        if len(md) < 6:
            return None

        chars = analyze_data_characteristics_optimized(md)
        rec = get_recommended_model_by_criteria(chars)
        cands = get_candidate_models(chars)

        train_size = max(3, int(len(md) * train_pct / 100))
        train, test = md[:train_size], md[train_size:]

        all_models = ['SMA', 'EMA', 'SES', 'DES', 'TES', 'ARIMA', 'SARIMA']
        trained = {}

        if len(test) > 0:
            for mname in all_models:
                try:
                    if mname == 'SMA':
                        f, w = train_sma_with_params(train, test)
                        if f is not None:
                            trained[mname] = {
                                'mae': mean_absolute_error(test.values, f),
                                'rmse': np.sqrt(mean_squared_error(test.values, f)),
                                'mape': mean_absolute_percentage_error(test.values, f) * 100,
                                'r2': r2_score(test.values, f) if len(test) > 1 else -999,
                                'params': f"window={w}"
                            }
                    elif mname == 'EMA':
                        f, s, a = train_ema_with_params(train, test)
                        if f is not None:
                            trained[mname] = {
                                'mae': mean_absolute_error(test.values, f),
                                'rmse': np.sqrt(mean_squared_error(test.values, f)),
                                'mape': mean_absolute_percentage_error(test.values, f) * 100,
                                'r2': r2_score(test.values, f) if len(test) > 1 else -999,
                                'params': f"span={s}, a={a:.3f}"
                            }
                    elif mname == 'ARIMA':
                        m, order, _ = find_best_arima_auto_fast(train.values)
                        if m is not None:
                            f = m.forecast(steps=len(test))
                            trained[mname] = {
                                'mae': mean_absolute_error(test.values, f),
                                'rmse': np.sqrt(mean_squared_error(test.values, f)),
                                'mape': mean_absolute_percentage_error(test.values, f) * 100,
                                'r2': r2_score(test.values, f) if len(test) > 1 else -999,
                                'params': f"p={order[0]}, d={order[1]}, q={order[2]}"
                            }
                    elif mname == 'SARIMA':
                        r = train_sarima_with_params(train, test)
                        if r is not None:
                            f, mae_, rmse_, mape_, r2_, o, so = r
                            trained[mname] = {
                                'mae': mae_, 'rmse': rmse_, 'mape': mape_, 'r2': r2_,
                                'params': f"p={o[0]}, d={o[1]}, q={o[2]}, "
                                          f"P={so[0]}, D={so[1]}, Q={so[2]}, s=12"
                            }
                    elif mname == 'SES':
                        m = SimpleExpSmoothing(train.values).fit(optimized=True)
                        f = m.forecast(steps=len(test))
                        trained[mname] = {
                            'mae': mean_absolute_error(test.values, f),
                            'rmse': np.sqrt(mean_squared_error(test.values, f)),
                            'mape': mean_absolute_percentage_error(test.values, f) * 100,
                            'r2': r2_score(test.values, f) if len(test) > 1 else -999,
                            'params': f"a={m.params.get('smoothing_level', 0.5):.3f}"
                        }
                    elif mname == 'DES':
                        f, mae_, rmse_, mape_, r2_, a, b = train_des_with_params(train, test)
                        if f is not None:
                            trained[mname] = {
                                'mae': mae_, 'rmse': rmse_, 'mape': mape_, 'r2': r2_,
                                'params': f"a={a:.3f}, b={b:.3f}"
                            }
                    elif mname == 'TES':
                        f, mae_, rmse_, mape_, r2_, a, b, g = train_tes_with_params(train, test)
                        if f is not None:
                            trained[mname] = {
                                'mae': mae_, 'rmse': rmse_, 'mape': mape_, 'r2': r2_,
                                'params': f"a={a:.3f}, b={b:.3f}, g={g:.3f}"
                            }
                except Exception:
                    continue

        best = 'SES'
        if trained:
            best = min(trained.items(), key=lambda x: x[1]['mape'])[0]

        all_forecasts = {}
        for mname in all_models:
            try:
                fv, fd = generate_future_forecast_fast(md, mname, forecast_months)
                if fv is not None:
                    all_forecasts[mname] = {
                        'values': fv, 'total': fv.sum(), 'avg': fv.mean(),
                        'min': fv.min(), 'max': fv.max(), 'dates': fd,
                    }
            except Exception:
                continue

        return {
            'material_name': material_name,
            'characteristics': chars,
            'candidate_models': cands,
            'recommended_model_criteria': rec,
            'trained_models': trained,
            'best_model': best,
            'all_forecasts': all_forecasts,
            'data_series': md,
            'data_full': data_series,
        }
    except Exception as e:
        return {'material_name': material_name, 'error': str(e)}


# ============================================================================
# YEARLY MODELS
# ============================================================================

def analyze_yearly_characteristics(data_series):
    dc = data_series
    if len(dc) < 2:
        return {
            'recommended': 'Naive Forecast', 'reason': 'Insufficient data',
            'cv': 0, 'volatility_level': 'Low', 'has_trend': False,
            'trend_direction': 'none', 'data_points': len(dc),
            'mean': dc.mean() if len(dc) > 0 else 0,
            'std': 0, 'min': 0, 'max': 0,
        }
    x = np.arange(len(dc))
    y = dc.values
    slope, intercept = np.polyfit(x, y, 1)
    mean_val = dc.mean()
    has_strong_trend = abs(slope) > (mean_val * 0.1) if mean_val > 0 else False
    cv = dc.std() / (mean_val + 1e-6)
    y_pred = slope * x + intercept
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r2 = 1 - (ss_res / (ss_tot + 1e-6))
    results = {
        'has_trend': has_strong_trend, 'trend_strength': r2,
        'trend_direction': 'up' if slope > 0 else 'down',
        'trend_slope': slope, 'cv': cv,
        'volatility_level': 'Low' if cv < 0.2 else 'Moderate' if cv < 0.4 else 'High',
        'is_stationary': cv < 0.3, 'data_points': len(dc),
        'mean': mean_val, 'std': dc.std(),
        'min': dc.min(), 'max': dc.max(),
    }
    if has_strong_trend and r2 > 0.7:
        results['recommended'] = 'Linear Trend'
    elif has_strong_trend:
        results['recommended'] = 'Holt Linear Trend'
    elif cv < 0.15:
        results['recommended'] = 'Simple Moving Average'
    elif cv < 0.3:
        results['recommended'] = 'Weighted Moving Average'
    elif cv < 0.5:
        results['recommended'] = 'Simple Exponential Smoothing'
    else:
        results['recommended'] = 'Naive Forecast'
    return results


def naive_forecast_yearly(data, years):
    last = data.iloc[-1] if len(data) > 0 else 0
    return np.array([last] * years), f"Last year: {last:.0f}"


def sma_yearly(data, years):
    avg = data.mean() if len(data) > 0 else 0
    return np.array([avg] * years), f"SMA: {avg:.0f}"


def wma_yearly(data, years):
    if len(data) >= 3:
        w = [0.2, 0.3, 0.5]
        v = np.sum(data.values[-3:] * w)
    elif len(data) == 2:
        v = 0.4 * data.iloc[-2] + 0.6 * data.iloc[-1]
    elif len(data) == 1:
        v = data.iloc[-1]
    else:
        v = 0
    return np.array([v] * years), f"WMA: {v:.0f}"


def ses_yearly(data, years):
    try:
        if len(data) >= 2:
            m = SimpleExpSmoothing(data.values).fit(optimized=True)
            f = m.forecast(steps=years)
            a = m.params.get('smoothing_level', 0.5)
            return np.maximum(f, 0), f"a={a:.3f}"
    except Exception:
        pass
    if len(data) > 0:
        return np.array([data.mean()] * years), "Fallback to mean"
    return np.array([0] * years), "No data"


def linear_trend_yearly(data, years):
    if len(data) >= 2:
        x = np.arange(len(data))
        y = data.values
        m = LinearRegression().fit(x.reshape(-1, 1), y)
        fx = np.arange(len(data), len(data) + years)
        f = m.predict(fx.reshape(-1, 1))
        return np.maximum(f, 0), (
            f"y = {m.coef_[0]:.1f}x + {m.intercept_:.0f} "
            f"(R2={m.score(x.reshape(-1,1), y):.3f})"
        )
    if len(data) > 0:
        return np.array([data.mean()] * years), "Fallback to mean"
    return np.array([0] * years), "No data"


def cagr_yearly(data, years):
    if len(data) >= 2:
        first, last, n = data.iloc[0], data.iloc[-1], len(data) - 1
        if first > 0 and n > 0 and last > 0:
            cagr = (last / first) ** (1 / n) - 1
            vals, cur = [], last
            for _ in range(years):
                cur *= (1 + cagr)
                vals.append(max(0, cur))
            return np.array(vals), f"CAGR: {cagr*100:.1f}%"
    if len(data) > 0:
        return np.array([data.mean()] * years), "Fallback to mean"
    return np.array([0] * years), "No data"


def growth_rate_yearly(data, years):
    if len(data) >= 2:
        rates = []
        for i in range(1, len(data)):
            if data.iloc[i - 1] > 0:
                rates.append((data.iloc[i] - data.iloc[i - 1]) / data.iloc[i - 1])
        if rates:
            avg = np.mean(rates)
            vals, cur = [], data.iloc[-1]
            for _ in range(years):
                cur *= (1 + avg)
                vals.append(max(0, cur))
            return np.array(vals), f"Avg growth: {avg*100:.1f}%"
    if len(data) > 0:
        return np.array([data.mean()] * years), "Fallback to mean"
    return np.array([0] * years), "No data"


def holt_yearly(data, years):
    try:
        if len(data) >= 3:
            m = Holt(data.values).fit(optimized=True)
            f = m.forecast(steps=years)
            a = m.params.get('smoothing_level', 0.5)
            b = m.params.get('smoothing_trend', 0.5)
            return np.maximum(f, 0), f"a={a:.3f}, b={b:.3f}"
    except Exception:
        pass
    if len(data) > 0:
        return linear_trend_yearly(data, years)
    return np.array([0] * years), "No data"


YEARLY_MODELS = {
    'Naive Forecast': naive_forecast_yearly,
    'Simple Moving Average': sma_yearly,
    'Weighted Moving Average': wma_yearly,
    'Simple Exponential Smoothing': ses_yearly,
    'Linear Trend': linear_trend_yearly,
    'CAGR Projection': cagr_yearly,
    'Growth Rate Forecast': growth_rate_yearly,
    'Holt Linear Trend': holt_yearly,
}


def train_yearly_models(train_data, test_data):
    out = {}
    if len(test_data) == 0:
        return out
    for name, fn in YEARLY_MODELS.items():
        try:
            f, p = fn(train_data, len(test_data))
            if len(f) == len(test_data):
                out[name] = {
                    'mae': mean_absolute_error(test_data.values, f),
                    'rmse': np.sqrt(mean_squared_error(test_data.values, f)),
                    'mape': mean_absolute_percentage_error(test_data.values, f) * 100,
                    'r2': r2_score(test_data.values, f) if len(test_data) > 1 else -999,
                    'params': p, 'forecast': f,
                }
        except Exception:
            continue
    return out


def generate_yearly_forecast(data_series, model_name, forecast_years):
    fn = YEARLY_MODELS.get(model_name)
    if fn is None:
        mean_val = data_series.mean() if len(data_series) > 0 else 0
        f = np.full(forecast_years, mean_val)
        return {'values': f, 'total': f.sum(), 'avg': mean_val,
                'first_year': mean_val, 'last_year': mean_val,
                'params': "Fallback"}
    f, p = fn(data_series, forecast_years)
    return {
        'values': f, 'total': f.sum(), 'avg': f.mean(),
        'first_year': f[0] if len(f) > 0 else 0,
        'last_year': f[-1] if len(f) > 0 else 0,
        'params': p,
    }


def process_yearly_material(material_name, data_series,
                             train_pct, forecast_years):
    try:
        data = pd.Series(data_series).fillna(0) \
            if not isinstance(data_series, pd.Series) else data_series.fillna(0).copy()
        if len(data) < 2:
            return {'material_name': material_name,
                    'error': f'Insufficient data: only {len(data)} year(s)'}

        chars = analyze_yearly_characteristics(data)
        rec = chars.get('recommended', 'Simple Moving Average')

        train_size = max(2, int(len(data) * train_pct / 100))
        train, test = data.iloc[:train_size], data.iloc[train_size:]

        trained = train_yearly_models(train, test) if len(test) > 0 else {}
        best = rec
        if trained:
            valid = {k: v for k, v in trained.items()
                     if v['mape'] != float('inf')}
            if valid:
                best = min(valid.items(), key=lambda x: x[1]['mape'])[0]

        all_forecasts = {
            name: generate_yearly_forecast(data, name, forecast_years)
            for name in YEARLY_MODELS
        }

        return {
            'material_name': material_name,
            'characteristics': chars,
            'recommended_model': rec,
            'best_model': best,
            'trained_models': trained,
            'all_forecasts': all_forecasts,
            'data_series': data,
            'historical_years': list(range(1, len(data) + 1)),
            'historical_values': data.values.tolist(),
            'forecast_years': list(range(len(data) + 1,
                                           len(data) + forecast_years + 1)),
        }
    except Exception as e:
        return {'material_name': material_name, 'error': str(e)}


# ============================================================================
# BATCH PROCESSING
# ============================================================================

def process_material_batch(material_list, df, train_pct, horizon, forecast_type):
    results = {}

    def _process_one(material):
        series = df[material]
        if forecast_type == "Monthly":
            return process_single_material_optimized(
                material, series, train_pct, horizon)
        return process_yearly_material(
            material, series, train_pct, horizon)

    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(_process_one, m): m for m in material_list}
        for fut in as_completed(futures):
            m = futures[fut]
            try:
                r = fut.result()
                if r:
                    results[m] = r
            except Exception as e:
                results[m] = {'material_name': m, 'error': str(e)}
    return results


# ============================================================================
# NEW ENTRY POINTS — issue_pivot -> forecast input
# ============================================================================

def build_monthly_forecast_input(issue_pivot_df: pd.DataFrame):
    """
    issue_pivot (Material Description x Mon-YYYY) -> date-indexed DataFrame
    that process_material_batch expects.
    """
    if issue_pivot_df is None or issue_pivot_df.empty:
        return pd.DataFrame(), []

    month_cols = _month_columns(issue_pivot_df)
    if not month_cols:
        return pd.DataFrame(), []

    df = issue_pivot_df.set_index('Material Description')[month_cols].T.copy()
    df.index = pd.to_datetime(
        [pd.to_datetime(m, format='%b-%Y') for m in month_cols])
    df.index.name = 'Month'
    df = df.astype(float)
    materials = [str(c) for c in df.columns.tolist()]
    return df, materials


def build_yearly_forecast_input(issue_pivot_df: pd.DataFrame):
    """
    Aggregate monthly issues to yearly sums, keep last 3 calendar years
    as Year_1, Year_2, Year_3.
    """
    if issue_pivot_df is None or issue_pivot_df.empty:
        return pd.DataFrame(), []

    month_cols = _month_columns(issue_pivot_df)
    if not month_cols:
        return pd.DataFrame(), []

    monthly_df, materials = build_monthly_forecast_input(issue_pivot_df)
    if monthly_df.empty:
        return pd.DataFrame(), []

    yearly = monthly_df.groupby(monthly_df.index.year).sum()
    last_years = yearly.tail(3)

    if last_years.shape[0] < 3:
        pad = 3 - last_years.shape[0]
        zero_rows = pd.DataFrame(0.0, index=range(pad),
                                 columns=last_years.columns)
        last_years = pd.concat([zero_rows, last_years], axis=0).reset_index(drop=True)
    else:
        last_years = last_years.reset_index(drop=True)

    last_years.columns = ['Year_1', 'Year_2', 'Year_3']
    last_years.index = materials
    last_years.index.name = 'Material Description'
    return last_years, materials


def run_forecast(df, materials, forecast_type, train_pct, horizon):
    if df.empty or not materials:
        return {}
    return process_material_batch(
        materials, df, train_pct, horizon, forecast_type)
