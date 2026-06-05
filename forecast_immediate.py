import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from statsmodels.tsa.stattools import adfuller
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.holtwinters import ExponentialSmoothing, SimpleExpSmoothing, Holt
from statsmodels.tsa.seasonal import seasonal_decompose
from sklearn.metrics import mean_absolute_error, mean_squared_error, mean_absolute_percentage_error, r2_score
from sklearn.linear_model import LinearRegression
import warnings
import re
import datetime
import time
from scipy import stats
warnings.filterwarnings("ignore")

# Page configuration
st.set_page_config(
    page_title="Health Program Medicines Forecasting Dashboard",
    page_icon="📊",
    layout="wide"
)

# Custom CSS for better table styling
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Times+New+Roman&display=swap');
    html, body, [class*="css"] { font-family: 'Times New Roman', Times, serif; }
    .main-header {
        background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
        padding: 0.8rem;
        border-radius: 12px;
        margin-bottom: 1rem;
    }
    .main-header h1 { font-size: 1.6rem !important; color: white; margin: 0; }
    .main-header p { font-size: 0.85rem !important; color: white; margin: 0; opacity: 0.9; }
    h2 { font-size: 1.3rem !important; color: #1e3c72; border-left: 4px solid #2a5298; padding-left: 12px; margin: 0.5rem 0; }
    .info-box {
        background: linear-gradient(135deg, #e3f2fd 0%, #bbdef5 100%);
        padding: 0.8rem;
        border-radius: 10px;
        margin: 0.8rem 0;
        border-left: 4px solid #1e3c72;
    }
    .char-badge {
        background: linear-gradient(135deg, #2a5298 0%, #1e3c72 100%);
        color: white;
        padding: 6px 14px;
        border-radius: 25px;
        margin: 5px;
        font-size: 0.8rem;
        font-weight: 600;
        display: inline-block;
    }
    .stButton > button {
        background: linear-gradient(90deg, #1e3c72 0%, #2a5298 100%);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.4rem 0.8rem;
        font-weight: bold;
    }
    .progress-container {
        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
        border-radius: 12px;
        padding: 1.5rem;
        margin: 1rem 0;
        text-align: center;
        border: 1px solid #dee2e6;
    }
    .stProgress > div > div { background-color: #1e3c72; }
    .checkbox-group {
        background-color: #f8f9fa;
        padding: 15px;
        border-radius: 8px;
        margin: 10px 0;
        border: 1px solid #dee2e6;
    }
    .all-models-header {
        font-weight: bold;
        margin-bottom: 10px;
        color: #1e3c72;
    }
    .metric-good {
        color: #28a745;
        font-weight: bold;
    }
    .metric-moderate {
        color: #ffc107;
        font-weight: bold;
    }
    .metric-poor {
        color: #dc3545;
        font-weight: bold;
    }
    .decision-table {
        width: 100%;
        border-collapse: collapse;
        margin: 20px 0;
        font-family: Times New Roman;
    }
    .decision-table th {
        background-color: #1e3c72;
        color: white;
        padding: 10px;
        text-align: center;
        font-weight: bold;
    }
    .decision-table td {
        padding: 8px;
        text-align: center;
        border: 1px solid #ddd;
    }
    .decision-table tbody tr:nth-child(even) {
        background-color: #f5f9ff;
    }
    .decision-table tbody tr:nth-child(odd) {
        background-color: #ffffff;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header"><h1 style="color: white; margin: 0;">📊 Health Program Medicines Forecasting Dashboard</h1><p style="color: white; margin: 0; opacity: 0.9;">Multi-Material Batch Processing | Manual Model Selection</p></div>', unsafe_allow_html=True)

# Initialize session state
if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = False
if 'df' not in st.session_state:
    st.session_state.df = None
if 'materials' not in st.session_state:
    st.session_state.materials = []
if 'all_materials_data' not in st.session_state:
    st.session_state.all_materials_data = {}
if 'batch_processed' not in st.session_state:
    st.session_state.batch_processed = False
if 'processing_complete' not in st.session_state:
    st.session_state.processing_complete = False
if 'forecast_months' not in st.session_state:
    st.session_state.forecast_months = 12
if 'material_selected_models' not in st.session_state:
    st.session_state.material_selected_models = {}

# Sidebar
st.sidebar.markdown("## 📁 Data Upload")
uploaded_file = st.sidebar.file_uploader("Choose an Excel file", type=["xlsx", "xls"])
st.sidebar.markdown("---")
st.sidebar.markdown("## ⚙️ Settings")
forecast_months_auto = st.sidebar.slider("Forecast Months", 6, 36, 12)
train_pct_auto = st.sidebar.slider("Training Data %", 50, 90, 70)

# ============= FUNCTIONS =============
def is_date_column(col_name):
    try:
        if isinstance(col_name, (pd.Timestamp, datetime.datetime)):
            return True
        pd.to_datetime(str(col_name))
        return True
    except:
        return False

def parse_column_to_date(col):
    try:
        if isinstance(col, (pd.Timestamp, datetime.datetime)):
            return col
        return pd.to_datetime(str(col))
    except:
        return None

def clean_value(value):
    if pd.isna(value):
        return 0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(',', '').strip())
    except:
        return 0

def parse_and_load_data(file):
    try:
        df_raw = pd.read_excel(file)
        material_col = df_raw.columns[0]
        materials = []
        material_data_map = {}

        for idx, row in df_raw.iterrows():
            material = str(row[material_col]).strip()
            if pd.notna(row[material_col]) and material not in ['', 'nan', 'None']:
                materials.append(material)
                material_data_map[material] = {}

        date_columns = []
        for col in df_raw.columns[1:]:
            if is_date_column(col):
                date = parse_column_to_date(col)
                if date:
                    date_columns.append((col, date))

        for col, date in date_columns:
            for idx, row in df_raw.iterrows():
                material = str(row[material_col]).strip()
                if material in material_data_map:
                    value = clean_value(row[col])
                    if value > 0:
                        material_data_map[material][date] = value

        all_dates = sorted(set([date for material_data in material_data_map.values() for date in material_data.keys()]))
        data_dict = {}
        for material in materials:
            data_dict[material] = [material_data_map[material].get(date, 0) for date in all_dates]

        df = pd.DataFrame(data_dict, index=all_dates)
        df = df.loc[:, (df != 0).any(axis=0)]
        materials = df.columns.tolist()
        return df, materials
    except Exception as e:
        st.sidebar.error(f"Error: {str(e)}")
        return None, None

def calculate_trend_strength(data_series):
    x = np.arange(len(data_series))
    y = data_series.values
    slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
    return r_value ** 2, slope, p_value

def classify_volatility(cv):
    if cv < 0.3: return "Low"
    elif cv < 0.6: return "Moderate"
    else: return "High"

def analyze_data_characteristics(data_series):
    results = {
        'is_stationary': False, 'has_trend': False, 'has_seasonality': False,
        'trend_strength': 0, 'seasonal_strength': 0, 'trend_direction': 'none',
        'trend_pvalue': 1.0, 'cv': 0, 'volatility_level': 'Low',
        'adf_pvalue': 1.0, 'trend_ambiguous': False, 'seasonal_ambiguous': False,
        'expert_decision_needed': False
    }

    data_clean = data_series[data_series > 0]
    if len(data_clean) < 6:
        return results

    try:
        adf_result = adfuller(data_clean.values)
        results['is_stationary'] = adf_result[1] < 0.05
        results['adf_pvalue'] = adf_result[1]
    except:
        results['is_stationary'] = False

    try:
        trend_strength, slope, p_value = calculate_trend_strength(data_clean)
        results['trend_strength'] = trend_strength
        results['trend_pvalue'] = p_value
        results['trend_direction'] = 'up' if slope > 0 else 'down' if slope < 0 else 'none'
        results['has_trend'] = trend_strength > 0.35 and p_value < 0.05
        results['trend_ambiguous'] = 0.3 <= trend_strength <= 0.5
    except:
        results['has_trend'] = False

    if len(data_clean) >= 24:
        try:
            decomp = seasonal_decompose(data_clean.values, model='additive', period=12, extrapolate_trend='freq')
            seasonal_var = np.var(decomp.seasonal)
            resid_var = np.var(decomp.resid)
            total_var = seasonal_var + resid_var
            if total_var > 0:
                results['seasonal_strength'] = 1 - (resid_var / total_var)
            results['has_seasonality'] = results['seasonal_strength'] > 0.35
            results['seasonal_ambiguous'] = 0.3 <= results['seasonal_strength'] <= 0.5
        except:
            pass

    results['expert_decision_needed'] = results['trend_ambiguous'] or results['seasonal_ambiguous']
    results['cv'] = data_clean.std() / (data_clean.mean() + 1e-6)
    results['volatility_level'] = classify_volatility(results['cv'])

    return results

def get_candidate_models(chars):
    candidates = []

    if chars['is_stationary'] and not chars['has_trend'] and not chars['has_seasonality'] and chars['volatility_level'] == 'Low':
        candidates = ['SES', 'SMA']
    elif chars['is_stationary'] and not chars['has_trend'] and not chars['has_seasonality'] and chars['volatility_level'] == 'Moderate':
        candidates = ['EMA', 'SES']
    elif chars['is_stationary'] and not chars['has_trend'] and not chars['has_seasonality'] and chars['volatility_level'] == 'High':
        candidates = ['EMA', 'ARIMA', 'SES']
    elif chars['is_stationary'] and chars['has_trend'] and not chars['has_seasonality']:
        candidates = ['DES', 'SES', 'SMA']
    elif chars['is_stationary'] and chars['has_trend'] and chars['has_seasonality'] and chars['volatility_level'] in ['Low', 'Moderate']:
        candidates = ['TES', 'SARIMA', 'DES']
    elif chars['is_stationary'] and chars['has_trend'] and chars['has_seasonality'] and chars['volatility_level'] == 'High':
        candidates = ['SARIMA', 'TES', 'ARIMA']
    elif not chars['is_stationary'] and not chars['has_trend'] and not chars['has_seasonality']:
        candidates = ['ARIMA', 'SES', 'EMA']
    elif not chars['is_stationary'] and chars['has_trend'] and not chars['has_seasonality']:
        candidates = ['ARIMA', 'DES', 'SES']
    elif not chars['is_stationary'] and chars['has_trend'] and chars['has_seasonality']:
        candidates = ['SARIMA', 'ARIMA', 'TES']
    elif not chars['is_stationary'] and not chars['has_trend'] and chars['has_seasonality']:
        candidates = ['SARIMA', 'TES', 'ARIMA']
    else:
        candidates = ['SES', 'SMA', 'ARIMA']

    return candidates[:3]

def find_best_arima_auto(train_data):
    best_aic = float('inf')
    best_order = None
    best_model = None
    n = len(train_data)
    max_p = 1 if n < 24 else 2
    max_q = 1 if n < 24 else 2
    for p in range(max_p + 1):
        for d in range(2):
            for q in range(max_q + 1):
                try:
                    model = ARIMA(train_data, order=(p, d, q))
                    fitted = model.fit(method_kwargs={'disp': False, 'maxiter': 100})
                    if fitted.aic < best_aic:
                        best_aic = fitted.aic
                        best_order = (p, d, q)
                        best_model = fitted
                except:
                    continue
    return best_model, best_order, best_aic

def find_best_sarima_auto(train_data, seasonal_period=12):
    if len(train_data) < 24:
        return None, None, None, None, None
    best_aic = float('inf')
    best_model = None
    best_order = None
    best_seasonal_order = None
    for p in [0, 1]:
        for d in [0, 1]:
            for q in [0, 1]:
                for P in [0, 1]:
                    for D in [0, 1]:
                        for Q in [0, 1]:
                            try:
                                model = SARIMAX(train_data, order=(p, d, q), seasonal_order=(P, D, Q, seasonal_period))
                                fitted = model.fit(disp=False, maxiter=100)
                                if fitted.aic < best_aic:
                                    best_aic = fitted.aic
                                    best_model = fitted
                                    best_order = (p, d, q)
                                    best_seasonal_order = (P, D, Q, seasonal_period)
                            except:
                                continue
    return best_model, best_order, best_seasonal_order, best_aic, None

def train_sma(train_data, test_data):
    best_mae = float('inf')
    best_forecast = None
    for window in [2, 3, 4]:
        if window > len(train_data):
            continue
        forecasts = []
        last_values = list(train_data.values[-window:])
        for i in range(len(test_data)):
            forecast = np.mean(last_values[-window:])
            forecasts.append(forecast)
            last_values.append(forecast)
        mae = mean_absolute_error(test_data.values[:len(forecasts)], forecasts)
        if mae < best_mae:
            best_mae = mae
            best_forecast = forecasts
    return np.array(best_forecast) if best_forecast is not None else None

def train_ema(train_data, test_data):
    best_mae = float('inf')
    best_forecast = None
    for span in [2, 3, 4]:
        if span > len(train_data):
            continue
        alpha = 2 / (span + 1)
        forecasts = []
        ema_value = np.mean(train_data.values[-span:])
        for i in range(len(test_data)):
            if i == 0:
                ema_value = alpha * train_data.values[-1] + (1 - alpha) * ema_value
            else:
                ema_value = alpha * forecasts[-1] + (1 - alpha) * ema_value
            forecasts.append(ema_value)
        mae = mean_absolute_error(test_data.values[:len(forecasts)], forecasts)
        if mae < best_mae:
            best_mae = mae
            best_forecast = forecasts
    return np.array(best_forecast) if best_forecast is not None else None

def train_des(train_data, test_data):
    try:
        model = Holt(train_data.values).fit(optimized=True)
        forecast = model.forecast(steps=len(test_data))
        mae = mean_absolute_error(test_data.values, forecast)
        rmse = np.sqrt(mean_squared_error(test_data.values, forecast))
        mape = mean_absolute_percentage_error(test_data.values, forecast) * 100
        try:
            r2 = r2_score(test_data.values, forecast)
        except:
            r2 = -999
        return forecast, mae, rmse, mape, r2
    except:
        return None, None, None, None, None

def train_tes(train_data, test_data):
    try:
        period = min(12, len(train_data) // 2)
        if period >= 2:
            model = ExponentialSmoothing(train_data.values, trend='add', seasonal='add', seasonal_periods=period).fit(optimized=True)
            forecast = model.forecast(steps=len(test_data))
            mae = mean_absolute_error(test_data.values, forecast)
            rmse = np.sqrt(mean_squared_error(test_data.values, forecast))
            mape = mean_absolute_percentage_error(test_data.values, forecast) * 100
            try:
                r2 = r2_score(test_data.values, forecast)
            except:
                r2 = -999
            return forecast, mae, rmse, mape, r2
    except:
        pass
    return None, None, None, None, None

def train_sarima(train_data, test_data):
    """Train SARIMA model"""
    try:
        if len(train_data) < 24:
            return None, None, None, None, None

        # Try different orders
        best_aic = float('inf')
        best_model = None
        best_forecast = None

        for p in [0, 1]:
            for d in [0, 1]:
                for q in [0, 1]:
                    for P in [0, 1]:
                        for D in [0, 1]:
                            for Q in [0, 1]:
                                try:
                                    model = SARIMAX(train_data.values, 
                                                  order=(p, d, q), 
                                                  seasonal_order=(P, D, Q, 12))
                                    fitted = model.fit(disp=False, maxiter=100)
                                    if fitted.aic < best_aic:
                                        best_aic = fitted.aic
                                        best_model = fitted
                                except:
                                    continue

        if best_model is not None:
            forecast = best_model.forecast(steps=len(test_data))
            mae = mean_absolute_error(test_data.values, forecast)
            rmse = np.sqrt(mean_squared_error(test_data.values, forecast))
            mape = mean_absolute_percentage_error(test_data.values, forecast) * 100
            try:
                r2 = r2_score(test_data.values, forecast)
            except:
                r2 = -999
            return forecast, mae, rmse, mape, r2
    except:
        pass
    return None, None, None, None, None

def generate_future_forecast(data_series, model_name, forecast_months):
    data_positive = data_series[data_series > 0]
    last_date = data_positive.index[-1]
    future_dates = pd.date_range(start=last_date, periods=forecast_months + 1, freq='MS')[1:]

    try:
        if model_name == 'SMA':
            window = 3
            forecast_values = []
            last_values = list(data_positive.values[-window:])
            for _ in range(forecast_months):
                fcast = np.mean(last_values[-window:])
                forecast_values.append(fcast)
                last_values.append(fcast)
        elif model_name == 'EMA':
            span = 3
            alpha = 2 / (span + 1)
            forecast_values = []
            ema_value = np.mean(data_positive.values[-span:])
            for i in range(forecast_months):
                if i == 0:
                    ema_value = alpha * data_positive.values[-1] + (1 - alpha) * ema_value
                else:
                    ema_value = alpha * forecast_values[-1] + (1 - alpha) * ema_value
                forecast_values.append(ema_value)
        elif model_name == 'ARIMA':
            model = ARIMA(data_positive.values, order=(1, 1, 1)).fit(method_kwargs={'disp': False})
            forecast_values = model.forecast(steps=forecast_months)
        elif model_name == 'SARIMA':
            model = SARIMAX(data_positive.values, order=(1, 1, 1), seasonal_order=(1, 1, 1, 12)).fit(disp=False)
            forecast_values = model.forecast(steps=forecast_months)
        elif model_name == 'SES':
            model = SimpleExpSmoothing(data_positive.values).fit(optimized=True)
            forecast_values = model.forecast(steps=forecast_months)
        elif model_name == 'DES':
            model = Holt(data_positive.values).fit(optimized=True)
            forecast_values = model.forecast(steps=forecast_months)
        elif model_name == 'TES':
            period = min(12, len(data_positive) // 2)
            if period >= 2:
                model = ExponentialSmoothing(data_positive.values, trend='add', seasonal='add', seasonal_periods=period).fit(optimized=True)
                forecast_values = model.forecast(steps=forecast_months)
            else:
                model = Holt(data_positive.values).fit(optimized=True)
                forecast_values = model.forecast(steps=forecast_months)
        else:
            forecast_values = np.full(forecast_months, data_positive.mean())

        return np.maximum(forecast_values, 0), future_dates
    except:
        forecast_values = np.full(forecast_months, data_positive.mean())
        return forecast_values, future_dates

def process_single_material(material_name, data_series, train_pct, forecast_months):
    try:
        material_data = data_series[data_series > 0]
        if len(material_data) < 6:
            return None

        chars = analyze_data_characteristics(material_data)
        candidates = get_candidate_models(chars)

        train_size = max(3, int(len(material_data) * train_pct / 100))
        train = material_data[:train_size]
        test = material_data[train_size:]

        all_models = ['SMA', 'EMA', 'SES', 'DES', 'TES', 'ARIMA', 'SARIMA']
        trained_models = {}

        if len(test) > 0:
            for model_name in all_models:
                try:
                    if model_name == 'SMA':
                        forecast = train_sma(train, test)
                        if forecast is not None:
                            mae = mean_absolute_error(test.values, forecast)
                            rmse = np.sqrt(mean_squared_error(test.values, forecast))
                            mape = mean_absolute_percentage_error(test.values, forecast) * 100
                            try:
                                r2 = r2_score(test.values, forecast)
                            except:
                                r2 = -999
                            trained_models[model_name] = {'mae': mae, 'rmse': rmse, 'mape': mape, 'r2': r2}

                    elif model_name == 'EMA':
                        forecast = train_ema(train, test)
                        if forecast is not None:
                            mae = mean_absolute_error(test.values, forecast)
                            rmse = np.sqrt(mean_squared_error(test.values, forecast))
                            mape = mean_absolute_percentage_error(test.values, forecast) * 100
                            try:
                                r2 = r2_score(test.values, forecast)
                            except:
                                r2 = -999
                            trained_models[model_name] = {'mae': mae, 'rmse': rmse, 'mape': mape, 'r2': r2}

                    elif model_name == 'ARIMA':
                        model, order, aic = find_best_arima_auto(train.values)
                        if model:
                            forecast = model.forecast(steps=len(test))
                            mae = mean_absolute_error(test.values, forecast)
                            rmse = np.sqrt(mean_squared_error(test.values, forecast))
                            mape = mean_absolute_percentage_error(test.values, forecast) * 100
                            try:
                                r2 = r2_score(test.values, forecast)
                            except:
                                r2 = -999
                            trained_models[model_name] = {'mae': mae, 'rmse': rmse, 'mape': mape, 'r2': r2}

                    elif model_name == 'SARIMA':
                        forecast, mae, rmse, mape, r2 = train_sarima(train, test)
                        if forecast is not None:
                            trained_models[model_name] = {'mae': mae, 'rmse': rmse, 'mape': mape, 'r2': r2}

                    elif model_name == 'SES':
                        model = SimpleExpSmoothing(train.values).fit(optimized=True)
                        forecast = model.forecast(steps=len(test))
                        mae = mean_absolute_error(test.values, forecast)
                        rmse = np.sqrt(mean_squared_error(test.values, forecast))
                        mape = mean_absolute_percentage_error(test.values, forecast) * 100
                        try:
                            r2 = r2_score(test.values, forecast)
                        except:
                            r2 = -999
                        trained_models[model_name] = {'mae': mae, 'rmse': rmse, 'mape': mape, 'r2': r2}

                    elif model_name == 'DES':
                        forecast, mae, rmse, mape, r2 = train_des(train, test)
                        if forecast is not None:
                            trained_models[model_name] = {'mae': mae, 'rmse': rmse, 'mape': mape, 'r2': r2}

                    elif model_name == 'TES':
                        forecast, mae, rmse, mape, r2 = train_tes(train, test)
                        if forecast is not None:
                            trained_models[model_name] = {'mae': mae, 'rmse': rmse, 'mape': mape, 'r2': r2}
                except Exception as e:
                    continue

        best_model_name = 'SES'
        if trained_models:
            best_model_name = min(trained_models.items(), key=lambda x: x[1]['mape'])[0]

        all_forecasts = {}
        for model_name in all_models:
            try:
                forecast_values, future_dates = generate_future_forecast(material_data, model_name, forecast_months)
                if forecast_values is not None:
                    all_forecasts[model_name] = {
                        'values': forecast_values,
                        'total': forecast_values.sum(),
                        'avg': forecast_values.mean(),
                        'min': forecast_values.min(),
                        'max': forecast_values.max(),
                        'dates': future_dates
                    }
            except:
                continue

        return {
            'material_name': material_name,
            'characteristics': chars,
            'candidate_models': candidates,
            'trained_models': trained_models,
            'best_model': best_model_name,
            'all_forecasts': all_forecasts,
            'data_series': material_data,
            'data_full': data_series
        }
    except Exception as e:
        return {'material_name': material_name, 'error': str(e)}

# ============= MAIN APP =============
if uploaded_file is not None:
    if not st.session_state.data_loaded:
        with st.spinner("Loading data..."):
            df, materials = parse_and_load_data(uploaded_file)
            if df is not None and not df.empty and len(materials) > 0:
                st.session_state.df = df
                st.session_state.materials = materials
                st.session_state.data_loaded = True
                st.sidebar.success(f"✅ Loaded {len(materials)} materials")
            else:
                st.sidebar.error("Failed to load data.")

    if st.session_state.data_loaded and not st.session_state.batch_processed:
        st.markdown("## 🔄 Processing All Materials")
        st.markdown('<div class="progress-container">', unsafe_allow_html=True)
        st.markdown("📊 Processing all materials. This may take a few moments depending on the number of materials.")

        progress_bar = st.progress(0)
        status_text = st.empty()

        all_results = {}
        total_materials = len(st.session_state.materials)

        for idx, material in enumerate(st.session_state.materials):
            status_text.markdown(f"**Processing:** {material} ({idx+1}/{total_materials})")
            progress_bar.progress(idx / total_materials)

            data_series = st.session_state.df[material]
            result = process_single_material(material, data_series, train_pct_auto, forecast_months_auto)
            if result and 'error' not in result:
                all_results[material] = result

            progress_bar.progress((idx + 1) / total_materials)

        progress_bar.progress(1.0)
        status_text.markdown("✅ **Processing complete!** All materials are now ready.")
        st.markdown('</div>', unsafe_allow_html=True)

        st.session_state.all_materials_data = all_results
        st.session_state.batch_processed = True
        st.session_state.processing_complete = True
        st.session_state.forecast_months = forecast_months_auto

if st.session_state.processing_complete and st.session_state.all_materials_data:
    materials_with_data = list(st.session_state.all_materials_data.keys())

    if len(materials_with_data) > 0:
        # Model Selection Decision Table
        st.markdown("## 📋 Model Selection Decision Table")

        decision_html = """
        <table class="decision-table">
            <thead>
                <tr><th>Stationary</th><th>Trend</th><th>Seasonality</th><th>Volatility</th><th>Recommended Models</th></tr>
            </thead>
            <tbody>
                <tr><td>Yes</td><td>No</td><td>No</td><td>Low</td><td>SES, SMA</td></tr>
                <tr><td>Yes</td><td>No</td><td>No</td><td>Moderate</td><td>EMA, SES</td></tr>
                <tr><td>Yes</td><td>Yes</td><td>No</td><td>Any</td><td>DES</td></tr>
                <tr><td>Yes</td><td>Yes</td><td>Yes</td><td>Low/Moderate</td><td>TES</td></tr>
                <tr><td>No</td><td>No</td><td>No</td><td>High</td><td>ARIMA</td></tr>
                <tr><td>No</td><td>Yes</td><td>No</td><td>High</td><td>ARIMA</td></tr>
                <tr><td>No</td><td>Yes</td><td>Yes</td><td>High</td><td>SARIMA</td></tr>
            </tbody>
        </table>
        """
        st.markdown(decision_html, unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("## 📊 All Materials Summary with Forecast")

        # Build summary data with enhanced columns
        summary_data = []
        for material, data in st.session_state.all_materials_data.items():
            chars = data['characteristics']

            # Get recommended model and its forecast total
            recommended_model = data['candidate_models'][0] if data['candidate_models'] else "N/A"
            forecast_total = "N/A"
            if recommended_model in data['all_forecasts']:
                forecast_total = f"{data['all_forecasts'][recommended_model]['total']:,.0f}"

            summary_data.append({
                "Material": material[:50],
                "Records": len(data['data_series']),
                "P-value": f"{chars['adf_pvalue']:.4f}",
                "Stationary": "Yes" if chars['is_stationary'] else "No",
                "Trend Strength": f"{chars['trend_strength']:.3f}",
                "Seasonal Strength": f"{chars['seasonal_strength']:.3f}",
                "Volatility": f"{chars['cv']:.3f} ({chars['volatility_level']})",
                "Recommended Model": recommended_model,
                "Forecast Total (Next 12 Months)": forecast_total
            })

        summary_df = pd.DataFrame(summary_data)
        st.dataframe(summary_df, use_container_width=True, hide_index=True)

        # Download button
        csv_summary = summary_df.to_csv(index=False)
        st.download_button("📥 Download Summary CSV", csv_summary, "forecast_summary.csv", "text/csv")

        st.markdown("---")
        st.markdown("## 📈 Individual Material Analysis")

        selected_material = st.selectbox(
            "Select Material to Analyze",
            materials_with_data,
            key="material_selector_individual"
        )

        if selected_material:
            data = st.session_state.all_materials_data[selected_material]
            chars = data['characteristics']

            st.markdown("### 📊 Data Characteristics Analysis")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.markdown(f'<div class="char-badge">📌 Stationarity: {"Stationary" if chars["is_stationary"] else "Non-Stationary"}<br>p={chars["adf_pvalue"]:.4f}</div>', unsafe_allow_html=True)
            with col2:
                st.markdown(f'<div class="char-badge">📈 Trend: {"Yes" if chars["has_trend"] else "No"}<br>Strength: {chars["trend_strength"]:.3f}</div>', unsafe_allow_html=True)
            with col3:
                st.markdown(f'<div class="char-badge">📅 Seasonality: {"Yes" if chars["has_seasonality"] else "No"}<br>Strength: {chars["seasonal_strength"]:.3f}</div>', unsafe_allow_html=True)
            with col4:
                st.markdown(f'<div class="char-badge">⚡ Volatility: {chars["volatility_level"]}<br>CV: {chars["cv"]:.3f}</div>', unsafe_allow_html=True)

            if chars['expert_decision_needed']:
                st.warning("⚠️ **Expert Decision Needed:** Trend or seasonality strength is between 0.3-0.5. Review metrics carefully.")

            # Manual Model Selection with Checkboxes - MOVED TO TOP (BEFORE Performance Comparison)
            st.markdown("### 🎯 Manual Model Selection (All Models)")
            st.markdown("*Check the models you want to use for forecasting. You can select multiple models to compare.*")

            all_available_models = ['SMA', 'EMA', 'SES', 'DES', 'TES', 'ARIMA', 'SARIMA']
            available_models = [m for m in all_available_models if m in data['all_forecasts']]

            checkbox_key = f"checkbox_{selected_material}"
            if checkbox_key not in st.session_state:
                st.session_state[checkbox_key] = {model: False for model in available_models}
                if data['candidate_models'] and data['candidate_models'][0] in st.session_state[checkbox_key]:
                    st.session_state[checkbox_key][data['candidate_models'][0]] = True

            st.markdown('<div class="checkbox-group">', unsafe_allow_html=True)
            st.markdown('<div class="all-models-header">📊 Select Forecasting Models:</div>', unsafe_allow_html=True)

            cols = st.columns(4)
            selected_models = []
            for idx, model in enumerate(available_models):
                col_idx = idx % 4
                with cols[col_idx]:
                    model_label = model
                    if model in data['trained_models']:
                        mape_val = data['trained_models'][model]['mape']
                        model_label = f"{model} (MAPE: {mape_val:.1f}%)"

                    is_checked = st.checkbox(
                        model_label, 
                        value=st.session_state[checkbox_key].get(model, False),
                        key=f"chk_{selected_material}_{model}"
                    )
                    if is_checked:
                        selected_models.append(model)
                    st.session_state[checkbox_key][model] = is_checked

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("✅ Select All Models", key=f"select_all_{selected_material}"):
                    for model in available_models:
                        st.session_state[checkbox_key][model] = True
                    st.rerun()
            with col_btn2:
                if st.button("❌ Clear All Models", key=f"clear_all_{selected_material}"):
                    for model in available_models:
                        st.session_state[checkbox_key][model] = False
                    st.rerun()

            st.markdown('</div>', unsafe_allow_html=True)

            # Model Performance Comparison - Now below Manual Model Selection
            if data['trained_models']:
                st.markdown("### 📊 Model Performance Comparison (Validation Data)")
                st.markdown("*Lower values are better for MAE, RMSE, MAPE. Higher R² is better.*")

                perf_data = []
                # Ensure all 7 models are in order
                model_order = ['SMA', 'EMA', 'SES', 'DES', 'TES', 'ARIMA', 'SARIMA']
                for name in model_order:
                    if name in data['trained_models']:
                        model_data = data['trained_models'][name]
                        # Color code MAPE
                        mape_val = model_data['mape']
                        if mape_val < 30:
                            mape_display = f'<span class="metric-good">{mape_val:.2f}%</span>'
                        elif mape_val < 50:
                            mape_display = f'<span class="metric-moderate">{mape_val:.2f}%</span>'
                        else:
                            mape_display = f'<span class="metric-poor">{mape_val:.2f}%</span>'

                        # Color code R²
                        r2_val = model_data['r2'] if model_data['r2'] != -999 else 0
                        if r2_val > 0.7:
                            r2_display = f'<span class="metric-good">{r2_val:.4f}</span>'
                        elif r2_val > 0.4:
                            r2_display = f'<span class="metric-moderate">{r2_val:.4f}</span>'
                        else:
                            r2_display = f'<span class="metric-poor">{r2_val:.4f}</span>'

                        perf_data.append({
                            "Model": name,
                            "MAE": f"{model_data['mae']:,.0f}",
                            "RMSE": f"{model_data['rmse']:,.0f}",
                            "MAPE": mape_display,
                            "R²": r2_display
                        })

                # Create HTML table with zebra striping
                if perf_data:
                    html_table = '<table style="width:100%; border-collapse: collapse; font-family: Times New Roman;">'
                    html_table += '<thead><tr style="background-color: #1e3c72; color: white;">'
                    html_table += '<th style="padding: 10px; text-align: center;">Model</th>'
                    html_table += '<th style="padding: 10px; text-align: center;">MAE</th>'
                    html_table += '<th style="padding: 10px; text-align: center;">RMSE</th>'
                    html_table += '<th style="padding: 10px; text-align: center;">MAPE</th>'
                    html_table += '<th style="padding: 10px; text-align: center;">R²</th>'
                    html_table += '</tr></thead><tbody>'

                    for i, row in enumerate(perf_data):
                        bg_color = '#f5f9ff' if i % 2 == 0 else '#ffffff'
                        html_table += f'<tr style="background-color: {bg_color};">'
                        html_table += f'<td style="padding: 8px; text-align: center; border: 1px solid #ddd;"><b>{row["Model"]}</b></td>'
                        html_table += f'<td style="padding: 8px; text-align: center; border: 1px solid #ddd;">{row["MAE"]}</td>'
                        html_table += f'<td style="padding: 8px; text-align: center; border: 1px solid #ddd;">{row["RMSE"]}</td>'
                        html_table += f'<td style="padding: 8px; text-align: center; border: 1px solid #ddd;">{row["MAPE"]}</td>'
                        html_table += f'<td style="padding: 8px; text-align: center; border: 1px solid #ddd;">{row["R²"]}</td>'
                        html_table += '</tr>'

                    html_table += '</tbody></table>'
                    st.markdown(html_table, unsafe_allow_html=True)

            if not selected_models:
                st.warning("⚠️ Please select at least one model to generate forecast.")
            elif len(selected_models) >= 1:
                if st.button("📊 Generate Forecasts for Selected Models", key=f"gen_forecast_{selected_material}"):
                    st.session_state.material_selected_models[selected_material] = selected_models

                    st.markdown("### 🔍 Compare Selected Model Forecasts")

                    first_date = data['data_series'].index[-1]
                    future_dates = pd.date_range(start=first_date, periods=st.session_state.forecast_months + 1, freq='MS')[1:]

                    fig, ax = plt.subplots(figsize=(14, 6))
                    ax.plot(data['data_full'].index, data['data_full'].values, marker='o', linewidth=2, markersize=4, color='#2E86AB', label='Historical Data')

                    colors = ['#E63946', '#F4A261', '#2A9D8F', '#9B5DE5', '#E9C46A', '#1E88E5', '#FF6B6B']
                    for i, model in enumerate(selected_models):
                        fc = data['all_forecasts'][model]
                        ax.plot(future_dates, fc['values'], '--', linewidth=2.5, marker='s', markersize=5, 
                               color=colors[i % len(colors)], label=f'{model} Forecast')

                    ax.axvline(x=data['data_series'].index[-1], color='gray', linestyle=':', alpha=0.7, label='Forecast Start')
                    ax.set_xlabel("Date", fontsize=12)
                    ax.set_ylabel("Demand Quantity", fontsize=12)
                    ax.set_title(f"{selected_material[:60]} - {st.session_state.forecast_months}-Month Forecast Comparison", fontsize=14)
                    ax.legend(loc='best', fontsize=10)
                    ax.grid(True, alpha=0.3)
                    plt.xticks(rotation=45)
                    plt.tight_layout()
                    st.pyplot(fig)

                    forecast_summary = []
                    for model in selected_models:
                        fc = data['all_forecasts'][model]
                        forecast_summary.append({
                            "Model": model,
                            "Total Forecast": f"{fc['total']:,.0f}",
                            "Monthly Avg": f"{fc['avg']:,.0f}",
                            "Min Month": f"{fc['min']:,.0f}",
                            "Max Month": f"{fc['max']:,.0f}"
                        })
                    st.dataframe(pd.DataFrame(forecast_summary), use_container_width=True, hide_index=True)

if not st.session_state.data_loaded:
    st.markdown("""
    <div class="info-box">
    <h3>👈 Please upload your Excel file to begin</h3>
    <p><strong>File Format:</strong> First column = Material Description, Other columns = Monthly data</p>
    <p><strong>Available Models:</strong> SMA, EMA, SES, DES, TES, ARIMA, SARIMA</p>
    <p><strong>Evaluation Metrics:</strong> MAE, RMSE, MAPE, R² are all displayed for informed model selection.</p>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")
st.markdown('<div style="text-align: center; color: #6c757d; padding: 15px;">🏥 Health Program Medicines Demand Forecasting Dashboard | Multi-Material Batch Processing | All 7 Models Available for Manual Selection</div>', unsafe_allow_html=True)
