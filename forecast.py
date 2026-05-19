import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from statsmodels.tsa.stattools import adfuller
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.holtwinters import ExponentialSmoothing, SimpleExpSmoothing, Holt
from statsmodels.tsa.seasonal import seasonal_decompose
from sklearn.metrics import mean_absolute_error, mean_squared_error, mean_absolute_percentage_error
from sklearn.linear_model import LinearRegression
import warnings
import re
import datetime
from scipy import stats
warnings.filterwarnings("ignore")

# Page configuration
st.set_page_config(
    page_title="Health Program Medicines Forecasting Dashboard",
    page_icon="📊",
    layout="wide"
)

# Custom CSS for attractive styling with Times Roman
st.markdown("""
<style>
    /* Global font settings */
    @import url('https://fonts.googleapis.com/css2?family=Times+New+Roman&display=swap');

    html, body, [class*="css"] {
        font-family: 'Times New Roman', Times, serif;
    }

    /* Main header styling */
    .main-header {
        background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
        padding: 0.8rem;
        border-radius: 12px;
        margin-bottom: 1rem;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
    }

    .main-header h1 {
        font-size: 1.6rem !important;
        font-family: 'Times New Roman', Times, serif;
        font-weight: bold;
    }

    .main-header p {
        font-size: 0.85rem !important;
        font-family: 'Times New Roman', Times, serif;
    }

    /* Section headers */
    h2, .stMarkdown h2 {
        font-size: 1.3rem !important;
        font-family: 'Times New Roman', Times, serif;
        font-weight: bold;
        color: #1e3c72;
        border-left: 4px solid #2a5298;
        padding-left: 12px;
        margin-top: 0.5rem;
        margin-bottom: 0.75rem;
    }

    h3, .stMarkdown h3 {
        font-size: 1.1rem !important;
        font-family: 'Times New Roman', Times, serif;
        font-weight: 600;
        color: #2a5298;
        margin-top: 0.4rem;
        margin-bottom: 0.6rem;
    }

    h4, .stMarkdown h4 {
        font-size: 0.95rem !important;
        font-family: 'Times New Roman', Times, serif;
        font-weight: 600;
        color: #3a6b9e;
        margin-top: 0.3rem;
        margin-bottom: 0.5rem;
    }

    /* Metric card styling */
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 0.8rem;
        border-radius: 10px;
        color: white;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        transition: transform 0.2s;
    }

    .metric-card:hover {
        transform: translateY(-2px);
    }

    .metric-card label {
        font-size: 0.85rem !important;
        font-family: 'Times New Roman', Times, serif;
    }

    .metric-card div {
        font-size: 1.2rem !important;
        font-weight: bold;
    }

    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #f8f9fa 0%, #e9ecef 100%);
        border-right: 1px solid #dee2e6;
    }

    [data-testid="stSidebar"] h2 {
        font-size: 1.1rem !important;
        color: #1e3c72;
    }

    /* Button styling */
    .stButton > button {
        background: linear-gradient(90deg, #1e3c72 0%, #2a5298 100%);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.4rem 0.8rem;
        font-weight: bold;
        font-family: 'Times New Roman', Times, serif;
        font-size: 0.85rem;
        transition: all 0.3s ease;
    }

    .stButton > button:hover {
        background: linear-gradient(90deg, #2a5298 0%, #1e3c72 100%);
        transform: scale(1.02);
        box-shadow: 0 2px 8px rgba(0,0,0,0.2);
    }

    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 4px;
    }

    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        padding: 6px 12px;
        font-weight: 600;
        font-family: 'Times New Roman', Times, serif;
        font-size: 0.85rem;
    }

    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
        color: white;
    }

    /* Info box styling */
    .info-box {
        background: linear-gradient(135deg, #e3f2fd 0%, #bbdef5 100%);
        padding: 0.8rem;
        border-radius: 10px;
        margin: 0.8rem 0;
        border-left: 4px solid #1e3c72;
        font-family: 'Times New Roman', Times, serif;
        font-size: 0.85rem;
    }

    /* Success box styling */
    .success-box {
        background: linear-gradient(135deg, #c8e6c9 0%, #a5d6a7 100%);
        padding: 0.8rem;
        border-radius: 10px;
        margin: 0.8rem 0;
        border-left: 4px solid #2e7d32;
        font-family: 'Times New Roman', Times, serif;
        font-size: 0.85rem;
    }

    /* Warning box styling */
    .warning-box {
        background: linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%);
        padding: 0.8rem;
        border-radius: 10px;
        margin: 0.8rem 0;
        border-left: 4px solid #e65100;
        font-family: 'Times New Roman', Times, serif;
        font-size: 0.85rem;
    }

    /* Dataframe styling */
    .dataframe {
        font-family: 'Times New Roman', Times, serif;
        font-size: 0.8rem;
    }

    /* Metric container */
    [data-testid="stMetricValue"] {
        font-size: 1.1rem !important;
        font-family: 'Times New Roman', Times, serif;
        font-weight: bold;
    }

    [data-testid="stMetricLabel"] {
        font-size: 0.8rem !important;
        font-family: 'Times New Roman', Times, serif;
    }

    /* Selectbox styling */
    .stSelectbox label {
        font-size: 0.85rem !important;
        font-family: 'Times New Roman', Times, serif;
        font-weight: 500;
    }

    /* Expander styling */
    .streamlit-expanderHeader {
        font-family: 'Times New Roman', Times, serif;
        font-size: 0.85rem;
        font-weight: 600;
        background-color: #f8f9fa;
        border-radius: 8px;
    }

    /* Alert/info messages */
    .stAlert {
        font-family: 'Times New Roman', Times, serif;
        font-size: 0.85rem;
    }

    /* Caption text */
    .caption {
        font-size: 0.75rem;
        color: #6c757d;
        font-family: 'Times New Roman', Times, serif;
        font-style: italic;
    }
</style>
""", unsafe_allow_html=True)

# Title with gradient styling - smaller font
st.markdown('<div class="main-header"><h1 style="color: white; margin: 0;">📊 Health Program Medicines Forecasting Dashboard</h1><p style="color: white; margin: 0; opacity: 0.9;">Time Series Analysis and Demand Forecasting</p></div>', unsafe_allow_html=True)

# Initialize session state
if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = False
if 'df' not in st.session_state:
    st.session_state.df = None
if 'materials' not in st.session_state:
    st.session_state.materials = []

# Sidebar for file upload
st.sidebar.markdown("## 📁 Data Upload")
st.sidebar.markdown("---")

uploaded_file = st.sidebar.file_uploader(
    "Choose an Excel file",
    type=["xlsx", "xls"],
    help="Upload your Excel file with Material Description and monthly columns"
)

def is_date_column(col_name):
    """Check if column name is a date column (not a summary column)"""
    col_str = str(col_name).strip()

    summary_patterns = [
        r'Apr \d{4}-Mar \d{4}',
        r'Total',
        r'Sum',
        r'Average',
        r'Mean',
    ]

    for pattern in summary_patterns:
        if re.search(pattern, col_str, re.IGNORECASE):
            return False

    try:
        if isinstance(col_name, (pd.Timestamp, datetime.datetime)):
            return True
        pd.to_datetime(col_str)
        return True
    except:
        return False

def parse_column_to_date(col):
    """Convert column name to date object"""
    try:
        if isinstance(col, (pd.Timestamp, datetime.datetime)):
            return col
        col_str = str(col).strip()

        formats = ['%b-%y', '%b-%Y', '%B-%y', '%B-%Y', '%b %Y', '%B %Y']
        for fmt in formats:
            try:
                return pd.to_datetime(col_str, format=fmt)
            except:
                continue

        return pd.to_datetime(col_str)
    except:
        return None

def clean_value(value):
    """Clean numeric values by removing commas and converting to float"""
    if pd.isna(value):
        return 0
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).replace(',', '').replace(' ', '').strip()
    try:
        return float(cleaned)
    except:
        return 0

def parse_and_load_data(file):
    """Parse Excel file with Material Description and monthly columns"""
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
            elif isinstance(col, (pd.Timestamp, datetime.datetime)):
                date_columns.append((col, col))

        if len(date_columns) == 0:
            for col in df_raw.columns[1:]:
                try:
                    date = pd.to_datetime(col)
                    date_columns.append((col, date))
                except:
                    pass

        for material in materials:
            material_data_map[material] = {}

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

        non_zero_counts = (df > 0).sum()
        df = df.loc[:, non_zero_counts >= 3]

        materials = df.columns.tolist()

        return df, materials

    except Exception as e:
        st.sidebar.error(f"Error: {str(e)}")
        import traceback
        st.sidebar.code(traceback.format_exc())
        return None, None

def get_fiscal_year(date):
    """Get fiscal year for a given date (April-March fiscal year)"""
    if date.month >= 4:
        return date.year
    else:
        return date.year - 1

def get_fiscal_year_label(date):
    """Get formatted fiscal year label (e.g., 'FY 2024/25')"""
    if date.month >= 4:
        start_year = date.year
        end_year = date.year + 1
    else:
        start_year = date.year - 1
        end_year = date.year
    return f"FY {start_year}/{str(end_year)[-2:]}"

def linear_forecast_with_yearly_data(data_series, forecast_years=3, n_points=None):
    """
    Linear forecast using ANNUAL data (aggregated by fiscal year)
    Returns monthly predictions for the forecast period
    """
    df_temp = pd.DataFrame({
        'Date': data_series.index,
        'Demand': data_series.values
    })

    df_temp['Fiscal_Year'] = df_temp['Date'].apply(get_fiscal_year)
    yearly_data = df_temp.groupby('Fiscal_Year')['Demand'].sum().sort_index()

    if n_points is not None and n_points < len(yearly_data):
        yearly_data = yearly_data.iloc[-n_points:]

    if len(yearly_data) < 3:
        return None, None, None, None

    X = np.arange(len(yearly_data)).reshape(-1, 1)
    y = yearly_data.values
    model = LinearRegression()
    model.fit(X, y)

    future_X = np.arange(len(yearly_data), len(yearly_data) + forecast_years).reshape(-1, 1)
    yearly_predictions = model.predict(future_X)
    yearly_predictions = np.maximum(yearly_predictions, 0)

    monthly_predictions = []
    for year_pred in yearly_predictions:
        monthly_predictions.extend([year_pred / 12] * 12)

    return np.array(monthly_predictions), yearly_predictions, model, yearly_data

def simple_average_forecast(data_series, forecast_years=3, n_points=None):
    """Simple average forecast using ANNUAL data"""
    df_temp = pd.DataFrame({
        'Date': data_series.index,
        'Demand': data_series.values
    })
    df_temp['Fiscal_Year'] = df_temp['Date'].apply(get_fiscal_year)
    yearly_data = df_temp.groupby('Fiscal_Year')['Demand'].sum().sort_index()

    if n_points is not None and n_points < len(yearly_data):
        yearly_data = yearly_data.iloc[-n_points:]

    if len(yearly_data) == 0:
        return None, None

    avg_yearly = yearly_data.mean()
    yearly_predictions = np.full(forecast_years, avg_yearly)

    monthly_predictions = []
    for year_pred in yearly_predictions:
        monthly_predictions.extend([year_pred / 12] * 12)

    return np.array(monthly_predictions), yearly_predictions

def weighted_average_forecast(data_series, forecast_years=3, n_points=None):
    """Weighted average forecast with optimal weights that minimize forecast error"""
    df_temp = pd.DataFrame({
        'Date': data_series.index,
        'Demand': data_series.values
    })
    df_temp['Fiscal_Year'] = df_temp['Date'].apply(get_fiscal_year)
    yearly_data = df_temp.groupby('Fiscal_Year')['Demand'].sum().sort_index()

    if n_points is not None and n_points < len(yearly_data):
        yearly_data = yearly_data.iloc[-n_points:]

    if len(yearly_data) < 2:
        return None, None

    best_mape = float('inf')
    best_lambda = 0.5

    for lam in np.arange(0.1, 1.0, 0.05):
        weights = np.exp(-lam * np.arange(len(yearly_data))[::-1])
        weights = weights / weights.sum()

        total_mape = 0
        for i in range(len(yearly_data)):
            train_indices = [j for j in range(len(yearly_data)) if j != i]
            test_value = yearly_data.iloc[i]

            if len(train_indices) > 0:
                train_yearly = yearly_data.iloc[train_indices]
                train_weights = weights[train_indices]
                train_weights = train_weights / train_weights.sum()
                pred = np.sum(train_yearly * train_weights)

                if test_value > 0:
                    mape = abs((test_value - pred) / test_value) * 100
                    total_mape += mape

        avg_mape = total_mape / len(yearly_data)
        if avg_mape < best_mape:
            best_mape = avg_mape
            best_lambda = lam

    optimal_weights = np.exp(-best_lambda * np.arange(len(yearly_data))[::-1])
    optimal_weights = optimal_weights / optimal_weights.sum()
    weighted_avg = np.sum(yearly_data * optimal_weights)
    yearly_predictions = np.full(forecast_years, weighted_avg)

    monthly_predictions = []
    for year_pred in yearly_predictions:
        monthly_predictions.extend([year_pred / 12] * 12)

    return np.array(monthly_predictions), yearly_predictions

if uploaded_file is not None:
    with st.spinner("Loading data..."):
        df, materials = parse_and_load_data(uploaded_file)

        if df is not None and not df.empty and len(materials) > 0:
            st.session_state.df = df
            st.session_state.materials = materials
            st.session_state.data_loaded = True
            st.sidebar.success(f"✅ Loaded {len(materials)} materials")

            if len(df.index) > 0:
                start_date = df.index[0]
                end_date = df.index[-1]
                if hasattr(start_date, 'strftime'):
                    st.sidebar.info(f"📅 Date range: {start_date.strftime('%b-%Y')} to {end_date.strftime('%b-%Y')}")
                else:
                    st.sidebar.info(f"📅 Date range: {start_date} to {end_date}")
                st.sidebar.info(f"📊 Total months: {len(df.index)}")
        else:
            st.sidebar.error("Failed to load data. Please check your file format.")

if st.session_state.data_loaded:
    df = st.session_state.df
    materials = st.session_state.materials

    st.markdown("## 📦 Select Material for Analysis")
    selected_material = st.selectbox(
        "Choose a material description",
        materials,
        key="material_selector"
    )

    material_data_full = df[selected_material]
    material_data = material_data_full[material_data_full > 0]

    st.markdown("## 📊 Data Overview")

    if len(material_data) > 0:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            st.metric("📋 Total Records (with demand)", len(material_data))
            st.markdown('</div>', unsafe_allow_html=True)
        with col2:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            st.metric("📅 Total Months in Timeline", len(material_data_full))
            st.markdown('</div>', unsafe_allow_html=True)
        with col3:
            start_date = material_data.index[0].strftime('%b-%Y') if hasattr(material_data.index[0], 'strftime') else str(material_data.index[0])
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            st.metric("📅 Start Date", start_date)
            st.markdown('</div>', unsafe_allow_html=True)
        with col4:
            end_date = material_data.index[-1].strftime('%b-%Y') if hasattr(material_data.index[-1], 'strftime') else str(material_data.index[-1])
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            st.metric("📅 End Date", end_date)
            st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.warning("No valid data for this material")
        st.stop()

    # Create 6 tabs (combined stationarity and decomposition)
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📈 Data Explorer", 
        "📅 Fiscal Year Comparison",
        "🔍 Stationarity & Decomposition",
        "📉 Model Training & Comparison",
        "🔮 Forecasting",
        "📊 Results"
    ])

    with tab1:
        st.markdown(f"### Data Preview - {selected_material[:50]}...")

        display_df = material_data_full.to_frame(name="Demand")
        if hasattr(display_df.index, 'strftime'):
            display_df.index = display_df.index.strftime('%b-%Y')

        st.write("**Transposed View (Dates as columns, Demand as row)**")
        transposed_display = display_df.T
        st.dataframe(transposed_display, use_container_width=True)

        st.markdown("### 📈 Time Series Plot with Trend Line")
        fig, ax = plt.subplots(figsize=(14, 6))

        ax.plot(material_data_full.index, material_data_full.values, 
                marker='o', linewidth=2, markersize=6, 
                color='#2E86AB', label='Actual Demand')

        x = np.arange(len(material_data_full.index))
        y = material_data_full.values
        z = np.polyfit(x, y, 1)
        p = np.poly1d(z)
        ax.plot(material_data_full.index, p(x), 
                linestyle='--', linewidth=2.5, color='#E63946', 
                label=f'Trend Line (slope: {z[0]:.1f})')

        prev_y = None
        for i, (date, value) in enumerate(zip(material_data_full.index, material_data_full.values)):
            if value > 0:
                if prev_y is not None and abs(value - prev_y) < (max(material_data_full.values) * 0.05):
                    offset = 15 if i % 2 == 0 else -15
                else:
                    offset = 10

                ax.annotate(f'{value:.0f}', 
                           xy=(date, value), 
                           xytext=(0, offset), 
                           textcoords='offset points',
                           fontsize=8,
                           ha='center',
                           alpha=0.7,
                           bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.7))
                prev_y = value

        ax.set_xlabel("Date", fontsize=11)
        ax.set_ylabel("Demand Quantity", fontsize=11)
        ax.set_title(f"{selected_material[:60]}...", fontsize=12)
        ax.legend(loc='best', fontsize=9)
        ax.grid(True, alpha=0.3)
        plt.xticks(rotation=45, fontsize=9)
        plt.yticks(fontsize=9)
        plt.tight_layout()
        st.pyplot(fig)

        st.markdown("### 📊 Demand Distribution")
        fig2, ax2 = plt.subplots(figsize=(14, 6))

        n_bins = min(20, len(material_data))
        ax2.hist(material_data.values, bins=n_bins, color='#2E86AB', 
                edgecolor='black', alpha=0.7, density=True, label='Histogram')

        kde = stats.gaussian_kde(material_data.values)
        x_range = np.linspace(material_data.min(), material_data.max(), 100)
        ax2.plot(x_range, kde(x_range), color='#E63946', linewidth=2, label='Density Curve')

        mean_val = material_data.mean()
        median_val = material_data.median()
        ax2.axvline(mean_val, color='#2A9D8F', linestyle='--', linewidth=2, label=f'Mean: {mean_val:,.0f}')
        ax2.axvline(median_val, color='#E9C46A', linestyle='--', linewidth=2, label=f'Median: {median_val:,.0f}')

        ax2.set_xlabel("Demand Quantity", fontsize=11)
        ax2.set_ylabel("Density", fontsize=11)
        ax2.set_title("Demand Distribution with Density Curve", fontsize=12)
        ax2.legend(loc='best', fontsize=9)
        ax2.grid(True, alpha=0.3)
        plt.tight_layout()
        st.pyplot(fig2)

        # Summary statistics side by side with explanation
        col_left, col_right = st.columns([1, 1])

        with col_left:
            st.markdown("### 📋 Summary Statistics (Non-Zero Values)")
            stats_summary = material_data.describe()
            cv = (stats_summary['std'] / stats_summary['mean']) * 100 if stats_summary['mean'] > 0 else 0
            skewness = material_data.skew()
            q1 = material_data.quantile(0.25)
            q3 = material_data.quantile(0.75)
            iqr = q3 - q1

            stats_df = pd.DataFrame({
                "Metric": ["Count", "Mean", "Median", "Std Dev", "Min", "Q1 (25th)", "Q3 (75th)", "Max", "IQR", "CV (%)", "Skewness"],
                "Value": [
                    f"{stats_summary['count']:,.0f}", f"{stats_summary['mean']:,.0f}", f"{median_val:,.0f}",
                    f"{stats_summary['std']:,.0f}", f"{stats_summary['min']:,.0f}", f"{q1:,.0f}",
                    f"{q3:,.0f}", f"{stats_summary['max']:,.0f}", f"{iqr:,.0f}", f"{cv:.1f}%", f"{skewness:.2f}"
                ]
            })
            st.dataframe(stats_df, hide_index=True, use_container_width=True)

        with col_right:
            st.markdown('<div class="info-box">', unsafe_allow_html=True)
            st.markdown("### 📖 Understanding the Statistics")
            st.markdown("""
            **Key Statistics Explained:**
            - **Mean**: Average demand - sensitive to outliers
            - **Median**: Middle value when sorted - better for skewed data
            - **CV < 30%**: Low variability | **CV 30-60%**: Moderate | **CV > 60%**: High variability
            - **Skewness**: Positive = right-skewed (more low values, few high spikes)
            """)
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("### 🔍 Outlier Detection (Box Plot)")
        fig3, ax3 = plt.subplots(figsize=(14, 5))
        ax3.boxplot(material_data.values, vert=True, patch_artist=True,
                   boxprops=dict(facecolor='#2E86AB', alpha=0.7),
                   medianprops=dict(color='#E63946', linewidth=2))
        ax3.set_ylabel("Demand Quantity", fontsize=11)
        ax3.set_title(f"Box Plot - {selected_material[:50]}...", fontsize=12)
        ax3.grid(True, alpha=0.3, axis='y')
        ax3.tick_params(labelsize=9)

        q1_val = material_data.quantile(0.25)
        q3_val = material_data.quantile(0.75)
        iqr_val = q3_val - q1_val
        upper_bound = q3_val + 1.5 * iqr_val
        outliers = material_data[material_data > upper_bound]
        if len(outliers) > 0:
            ax3.text(1.1, upper_bound, f'Upper bound: {upper_bound:,.0f}\nOutliers: {len(outliers)}', 
                    fontsize=8, verticalalignment='bottom')

        plt.tight_layout()
        st.pyplot(fig3)

    with tab2:
        st.markdown(f"### 📅 Fiscal Year Comparison (April-March) - {selected_material[:50]}...")
        st.markdown('<div class="info-box">This chart compares demand across different fiscal years (April to March), helping identify year-over-year trends and seasonal patterns.</div>', unsafe_allow_html=True)

        if len(material_data_full) >= 12:
            df_fiscal = pd.DataFrame({
                'Date': material_data_full.index,
                'Demand': material_data_full.values
            })

            df_fiscal['Fiscal_Year_Num'] = df_fiscal['Date'].apply(get_fiscal_year)
            df_fiscal['Fiscal_Year_Label'] = df_fiscal['Date'].apply(get_fiscal_year_label)
            df_fiscal = df_fiscal.sort_values('Date')
            df_fiscal['Month_Short'] = df_fiscal['Date'].dt.strftime('%b')

            month_order = {4:1, 5:2, 6:3, 7:4, 8:5, 9:6, 10:7, 11:8, 12:9, 1:10, 2:11, 3:12}
            df_fiscal['Month_Num'] = df_fiscal['Date'].dt.month.map(month_order)
            df_fiscal_monthly = df_fiscal.sort_values('Month_Num')

            fiscal_pivot = df_fiscal_monthly.pivot(index='Month_Short', columns='Fiscal_Year_Label', values='Demand')
            month_seq = ['Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'Mar']
            fiscal_pivot = fiscal_pivot.reindex(month_seq)

            colors = ['#2E86AB', '#E63946', '#2A9D8F', '#E9C46A', '#9B5DE5', '#F4A261']
            markers = ['o', 's', '^', 'D', 'v', '<']

            st.markdown("#### 📈 Monthly Demand Pattern by Fiscal Year")
            fig1, ax1 = plt.subplots(figsize=(14, 7))

            years_sorted = sorted(fiscal_pivot.columns, key=lambda x: int(x.split('/')[0].split()[-1]))
            for i, year in enumerate(years_sorted):
                col = fiscal_pivot[year]
                if not col.isna().all():
                    ax1.plot(fiscal_pivot.index, col.values, 
                           marker=markers[i % len(markers)], 
                           linewidth=2.5, 
                           markersize=8,
                           color=colors[i % len(colors)], 
                           label=year,
                           markevery=1)

                    for j, (month, value) in enumerate(zip(fiscal_pivot.index, col.values)):
                        if not pd.isna(value) and value > 0:
                            offset = 15 if j % 2 == 0 else -15
                            ax1.annotate(f'{value:,.0f}', 
                                       xy=(month, value), 
                                       xytext=(0, offset),
                                       textcoords='offset points',
                                       fontsize=8,
                                       ha='center',
                                       bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.8, edgecolor='gray', linewidth=0.5))

            ax1.set_xlabel("Month", fontsize=11)
            ax1.set_ylabel("Demand Quantity", fontsize=11)
            ax1.set_title(f"Monthly Demand by Fiscal Year\n{selected_material[:60]}", fontsize=12)
            ax1.legend(loc='upper left', bbox_to_anchor=(1, 1), fontsize=9)
            ax1.grid(True, alpha=0.3)
            ax1.tick_params(labelsize=9)
            plt.xticks(rotation=45)
            plt.tight_layout()
            st.pyplot(fig1)

            st.markdown("#### 📊 Average Monthly Demand Across All Fiscal Years")
            fig4, ax4 = plt.subplots(figsize=(14, 7))

            monthly_avg = fiscal_pivot.mean(axis=1)
            bars = ax4.bar(monthly_avg.index, monthly_avg.values, 
                           color='#2E86AB', alpha=0.7, edgecolor='black', width=0.7)

            for bar, avg in zip(bars, monthly_avg.values):
                if not pd.isna(avg):
                    ax4.annotate(f'{avg:,.0f}',
                                xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                                xytext=(0, 8),
                                textcoords="offset points",
                                ha='center',
                                va='bottom',
                                fontsize=9,
                                fontweight='bold')

            ax4.set_xlabel("Month", fontsize=11)
            ax4.set_ylabel("Average Demand", fontsize=11)
            ax4.set_title("Average Monthly Demand Across All Fiscal Years", fontsize=12)
            ax4.grid(True, alpha=0.3, axis='y')
            ax4.tick_params(labelsize=9)
            plt.xticks(rotation=45)
            plt.tight_layout()
            st.pyplot(fig4)

            st.markdown("#### 📊 Year-over-Year Total Demand Comparison")
            fig2, ax2 = plt.subplots(figsize=(14, 7))

            yearly_totals = df_fiscal.groupby('Fiscal_Year_Label')['Demand'].sum().sort_index(key=lambda x: x.str.extract(r'(\d+)')[0].astype(int))
            bars = ax2.bar(yearly_totals.index, yearly_totals.values, 
                           color=colors[:len(yearly_totals)], 
                           edgecolor='black',
                           alpha=0.8,
                           width=0.6)

            for bar, total in zip(bars, yearly_totals.values):
                height = bar.get_height()
                ax2.annotate(f'{total:,.0f}',
                            xy=(bar.get_x() + bar.get_width() / 2, height),
                            xytext=(0, 10),
                            textcoords="offset points",
                            ha='center',
                            va='bottom',
                            fontsize=9,
                            fontweight='bold')

            ax2.set_xlabel("Fiscal Year", fontsize=11)
            ax2.set_ylabel("Total Annual Demand", fontsize=11)
            ax2.set_title("Year-over-Year Total Demand Comparison", fontsize=12)
            ax2.grid(True, alpha=0.3, axis='y')
            ax2.tick_params(labelsize=9)
            plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha='right')
            plt.tight_layout()
            st.pyplot(fig2)

            st.markdown("#### 📅 Monthly Demand Timeline (Chronological Order)")
            fig3, ax3 = plt.subplots(figsize=(14, 7))

            fiscal_years_chrono = sorted(df_fiscal['Fiscal_Year_Label'].unique(), 
                                           key=lambda x: int(x.split('/')[0].split()[-1]))

            for i, fiscal_year in enumerate(fiscal_years_chrono):
                year_data = df_fiscal[df_fiscal['Fiscal_Year_Label'] == fiscal_year]
                if len(year_data) > 0:
                    ax3.plot(year_data['Date'], year_data['Demand'], 
                            marker=markers[i % len(markers)],
                            linewidth=2.5,
                            markersize=7,
                            color=colors[i % len(colors)],
                            label=fiscal_year)

                    for idx, row in year_data.iterrows():
                        if row['Demand'] > 0:
                            ax3.annotate(f'{row["Demand"]:,.0f}',
                                       xy=(row['Date'], row['Demand']),
                                       xytext=(0, 10),
                                       textcoords='offset points',
                                       fontsize=8,
                                       ha='center',
                                       bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.7))

            ax3.set_xlabel("Date (Month-Year)", fontsize=11)
            ax3.set_ylabel("Demand Quantity", fontsize=11)
            ax3.set_title(f"Monthly Demand with Fiscal Year Coloring (Chronological Order)\n{selected_material[:60]}", fontsize=12)
            ax3.legend(loc='upper left', bbox_to_anchor=(1, 1), fontsize=9)
            ax3.grid(True, alpha=0.3)
            ax3.tick_params(labelsize=9)
            plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45, ha='right')
            plt.tight_layout()
            st.pyplot(fig3)

            st.markdown("#### 📊 Fiscal Year Summary")

            summary_data = []
            for year in fiscal_pivot.columns:
                year_data = fiscal_pivot[year].dropna()
                if len(year_data) > 0:
                    summary_data.append({
                        "Fiscal Year": year,
                        "Total Demand": f"{year_data.sum():,.0f}",
                        "Average Monthly": f"{year_data.mean():,.0f}",
                        "Peak Month": f"{year_data.idxmax()} ({year_data.max():,.0f})",
                        "Lowest Month": f"{year_data.idxmin()} ({year_data.min():,.0f})",
                        "Months of Data": len(year_data)
                    })

            if summary_data:
                summary_df = pd.DataFrame(summary_data)
                st.dataframe(summary_df, use_container_width=True, hide_index=True)

            if len(fiscal_pivot.columns) >= 2:
                st.markdown("#### 📈 Year-over-Year Growth Analysis")
                cols = list(fiscal_pivot.columns)
                growth_rates = []

                for i in range(1, len(cols)):
                    prev_year_total = fiscal_pivot[cols[i-1]].sum()
                    curr_year_total = fiscal_pivot[cols[i]].sum()
                    if prev_year_total > 0:
                        growth = ((curr_year_total - prev_year_total) / prev_year_total) * 100
                        growth_rates.append({
                            "Period": f"{cols[i-1]} → {cols[i]}",
                            "Growth Rate": f"{growth:+.1f}%",
                            "Change in Units": f"{curr_year_total - prev_year_total:+,.0f}",
                            "Previous Year Total": f"{prev_year_total:,.0f}",
                            "Current Year Total": f"{curr_year_total:,.0f}"
                        })

                if growth_rates:
                    growth_df = pd.DataFrame(growth_rates)
                    st.dataframe(growth_df, use_container_width=True, hide_index=True)

                    last_growth = growth_rates[-1]
                    growth_value = float(last_growth['Growth Rate'].replace('%', '').replace('+', ''))
                    if growth_value > 10:
                        st.warning(f"⚠️ **High growth detected!** {last_growth['Period']}: {last_growth['Growth Rate']} growth. Ensure supply chain capacity can handle increasing demand.")
                    elif growth_value < -10:
                        st.info(f"ℹ️ **Significant decrease detected:** {last_growth['Period']}: {last_growth['Growth Rate']}. Investigate potential causes.")

            st.markdown("#### 📊 Monthly Pattern Analysis")
            col1, col2, col3 = st.columns(3)

            with col1:
                avg_monthly = fiscal_pivot.mean(axis=1)
                if len(avg_monthly) > 0:
                    highest_avg_month = avg_monthly.idxmax()
                    st.metric("Highest Average Month", highest_avg_month, f"{avg_monthly.max():,.0f} units avg")

            with col2:
                peak_months = {}
                for year in fiscal_pivot.columns:
                    year_data = fiscal_pivot[year].dropna()
                    if len(year_data) > 0:
                        peak_month = year_data.idxmax()
                        peak_months[peak_month] = peak_months.get(peak_month, 0) + 1

                if peak_months:
                    most_common_peak = max(peak_months, key=peak_months.get)
                    st.metric("Most Common Peak Month", most_common_peak, f"{peak_months[most_common_peak]} of {len(fiscal_pivot.columns)} years")

            with col3:
                cv_by_month = fiscal_pivot.std(axis=1) / fiscal_pivot.mean(axis=1) * 100
                if len(cv_by_month) > 0:
                    most_stable_month = cv_by_month.idxmin()
                    st.metric("Most Stable Month", most_stable_month, f"CV: {cv_by_month.min():.1f}%")
        else:
            st.warning(f"Not enough data for fiscal year comparison. Need at least 12 months of data. Currently have {len(material_data_full)} months.")

    # Combined Stationarity and Decomposition tab
    with tab3:
        st.markdown(f"### Stationarity Test - {selected_material[:50]}...")

        if len(material_data) >= 3:
            from statsmodels.graphics.tsaplots import plot_acf, plot_pacf

            result = adfuller(material_data.values)

            col1, col2 = st.columns(2)
            with col1:
                st.metric("ADF Statistic", f"{result[0]:.4f}")
                st.metric("p-value", f"{result[1]:.6f}")

            with col2:
                is_stationary = result[1] < 0.05
                st.metric("Is Stationary?", "✅ Yes" if is_stationary else "❌ No")
                st.info(f"Critical Values:\n1%: {result[4]['1%']:.4f}\n5%: {result[4]['5%']:.4f}\n10%: {result[4]['10%']:.4f}")

            st.markdown("---")
            if result[1] < 0.05:
                st.success("✅ **The time series is stationary** (p-value < 0.05)")
            else:
                st.warning("⚠️ **The time series is NOT stationary** (p-value >= 0.05)")

            # Show graph for BOTH stationary and non-stationary data
            if len(material_data) > 1:
                # First differencing
                diff_data = material_data.diff().dropna()

                fig, ax = plt.subplots(figsize=(14, 5))

                # Scatter plot ONLY (no lines)
                ax.scatter(
                    diff_data.index,
                    diff_data.values,
                    color='green' if is_stationary else 'orange',
                    s=60,
                    alpha=0.8,
                    label='First Difference'
                )

                # Horizontal zero line
                ax.axhline(y=0, color='red', linestyle='--', alpha=0.5)

                # Labels
                ax.set_xlabel("Date", fontsize=11)
                ax.set_ylabel("Differenced Quantity", fontsize=11)

                # Dynamic title
                ax.set_title(
                    "Stationarity Visualization (Points Only - No Connecting Lines)",
                    fontsize=12
                )

                ax.legend(fontsize=9)
                ax.tick_params(labelsize=9)

                # Grid
                ax.grid(True, alpha=0.3)

                # Rotate dates
                plt.xticks(rotation=45)

                plt.tight_layout()

                # Display
                st.pyplot(fig)

            # ACF and PACF Plots
            st.markdown("---")
            st.markdown("#### 📊 Autocorrelation (ACF) and Partial Autocorrelation (PACF) Plots")
            st.info("ACF and PACF plots help identify AR and MA terms for ARIMA modeling.")

            col1, col2 = st.columns(2)

            with col1:
                # ACF Plot
                fig_acf, ax_acf = plt.subplots(figsize=(10, 6))
                plot_acf(material_data.values, lags=min(20, len(material_data)//2), ax=ax_acf, alpha=0.05)
                ax_acf.set_title("Autocorrelation Function (ACF)", fontsize=11)
                ax_acf.set_xlabel("Lags", fontsize=10)
                ax_acf.set_ylabel("Autocorrelation", fontsize=10)
                ax_acf.grid(True, alpha=0.3)
                ax_acf.tick_params(labelsize=9)
                plt.tight_layout()
                st.pyplot(fig_acf)

            with col2:
                # PACF Plot
                fig_pacf, ax_pacf = plt.subplots(figsize=(10, 6))
                plot_pacf(material_data.values, lags=min(20, len(material_data)//2), ax=ax_pacf, alpha=0.05, method='ywm')
                ax_pacf.set_title("Partial Autocorrelation Function (PACF)", fontsize=11)
                ax_pacf.set_xlabel("Lags", fontsize=10)
                ax_pacf.set_ylabel("Partial Autocorrelation", fontsize=10)
                ax_pacf.grid(True, alpha=0.3)
                ax_pacf.tick_params(labelsize=9)
                plt.tight_layout()
                st.pyplot(fig_pacf)

            # Interpretation guide
            with st.expander("📖 How to interpret ACF/PACF plots"):
                st.markdown("""
                **ACF (Autocorrelation Function) Interpretation:**
                - **Slowly decaying ACF** → Indicates non-stationary data (need differencing)
                - **Sharp cut-off after lag q** → MA(q) model
                - **Exponential decay** → AR model

                **PACF (Partial Autocorrelation Function) Interpretation:**
                - **Sharp cut-off after lag p** → AR(p) model
                - **Exponential decay** → MA model
                - **No significant correlations** → White noise

                **For ARIMA Model Selection:**
                - If ACF cuts off after lag q and PACF decays → Use MA(q)
                - If PACF cuts off after lag p and ACF decays → Use AR(p)
                - If both decay slowly → Need differencing (increase d)

                **Blue shaded area** = 95% confidence interval (correlations within this area are not significant)
                """)
        else:
            st.warning(f"Not enough data for stationarity test (need at least 3 data points). Currently have {len(material_data)}.")

        st.markdown("---")
        st.markdown(f"### Seasonal Decomposition - {selected_material[:50]}...")

        if len(material_data_full) >= 12:
            st.info("Seasonal decomposition helps identify trend, seasonal patterns, and residuals in your time series data.")

            col1, col2 = st.columns(2)
            with col1:
                decomp_model_type = st.selectbox(
                    "Decomposition Model Type",
                    ["additive", "multiplicative"],
                    key="decomp_model_select"
                )

            with col2:
                decomp_period = st.number_input(
                    "Seasonal Period (months)",
                    min_value=2,
                    max_value=24,
                    value=12,
                    key="decomp_period_select"
                )

            if st.button("Run Seasonal Decomposition", key="run_decomp"):
                try:
                    decomposition = seasonal_decompose(
                        material_data_full.values, 
                        model=decomp_model_type,
                        period=min(decomp_period, len(material_data_full) // 2),
                        extrapolate_trend='freq'
                    )

                    fig, axes = plt.subplots(4, 1, figsize=(14, 12))

                    axes[0].plot(material_data_full.index, material_data_full.values, color='#2E86AB')
                    axes[0].set_title('Original Series', fontsize=11)
                    axes[0].set_ylabel('Demand', fontsize=10)
                    axes[0].grid(True, alpha=0.3)
                    axes[0].tick_params(labelsize=9)

                    axes[1].plot(material_data_full.index, decomposition.trend, color='#E9C46A')
                    axes[1].set_title('Trend Component', fontsize=11)
                    axes[1].set_ylabel('Trend', fontsize=10)
                    axes[1].grid(True, alpha=0.3)
                    axes[1].tick_params(labelsize=9)

                    axes[2].plot(material_data_full.index, decomposition.seasonal, color='#2A9D8F')
                    axes[2].set_title('Seasonal Component', fontsize=11)
                    axes[2].set_ylabel('Seasonal', fontsize=10)
                    axes[2].grid(True, alpha=0.3)
                    axes[2].tick_params(labelsize=9)

                    axes[3].plot(material_data_full.index, decomposition.resid, color='#E63946')
                    axes[3].set_title('Residual Component', fontsize=11)
                    axes[3].set_ylabel('Residual', fontsize=10)
                    axes[3].set_xlabel('Date', fontsize=10)
                    axes[3].grid(True, alpha=0.3)
                    axes[3].tick_params(labelsize=9)

                    plt.tight_layout()
                    st.pyplot(fig)

                    seasonal_strength = 1 - (np.var(decomposition.resid) / np.var(decomposition.seasonal + decomposition.resid))
                    trend_strength = 1 - (np.var(decomposition.resid) / np.var(decomposition.trend + decomposition.resid))

                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Seasonal Strength", f"{seasonal_strength:.3f}")
                    with col2:
                        st.metric("Trend Strength", f"{trend_strength:.3f}")
                    with col3:
                        recommendation = "Use multiplicative" if seasonal_strength > 0.5 and trend_strength > 0.5 else "Use additive"
                        st.metric("Recommendation", recommendation)

                    st.session_state['decomposition_results'] = decomposition

                except Exception as e:
                    st.error(f"Decomposition failed: {str(e)}")
        else:
            st.warning(f"Not enough data for seasonal decomposition. Need at least 12 months. Currently have {len(material_data_full)} months.")

    with tab4:
        st.markdown(f"### Model Training & Comparison - {selected_material[:50]}...")

        if len(material_data) < 6:
            st.warning(f"Not enough data for model training. Need at least 6 months of data. Currently have {len(material_data)} months.")
        else:
            col1, col2 = st.columns(2)
            with col1:
                train_pct = st.slider(
                    "Training Data Percentage", 
                    min_value=50, 
                    max_value=90, 
                    value=70,
                    key="train_pct_slider"
                )

            train_size = max(3, int(len(material_data) * train_pct / 100))
            train = material_data[:train_size]
            test = material_data[train_size:]

            with col2:
                st.info(f"📊 **Split Summary**\n\n- Training: {len(train)} months ({train_pct}%)\n- Testing: {len(test)} months ({100-train_pct}%)")

            if len(test) == 0:
                st.warning("Not enough data for testing. Please reduce training percentage.")
                st.stop()

            st.markdown("#### Select Models to Train")
            col1, col2, col3, col4, col5, col6 = st.columns(6)
            with col1:
                run_sma = st.checkbox("Simple MA", value=True, key="train_sma")
            with col2:
                run_ema = st.checkbox("Exponential MA", value=True, key="train_ema")
            with col3:
                run_arima = st.checkbox("ARIMA", value=True, key="train_arima")
            with col4:
                run_ses = st.checkbox("SES", value=True, key="train_ses")
            with col5:
                run_des = st.checkbox("DES/Holt", value=True, key="train_des")
            with col6:
                run_tes = st.checkbox("TES/HW", value=True, key="train_tes")

            st.markdown("---")
            st.markdown("#### ⚙️ Exponential Smoothing Configuration (For DES & TES)")
            st.info("Change these options to see how different configurations affect model performance!")

            col1, col2, col3 = st.columns(3)
            with col1:
                trend_type = st.selectbox(
                    "📈 Trend Type",
                    options=["add", "mul", None],
                    format_func=lambda x: "Additive" if x == "add" else "Multiplicative" if x == "mul" else "None (No Trend)",
                    key="trend_type_select"
                )

            with col2:
                seasonal_type = st.selectbox(
                    "📅 Seasonal Type (for TES only)",
                    options=["add", "mul", None],
                    format_func=lambda x: "Additive" if x == "add" else "Multiplicative" if x == "mul" else "None (No Seasonality)",
                    key="seasonal_type_select"
                )

            with col3:
                seasonal_period = st.number_input(
                    "Seasonal Period (months) - for TES",
                    min_value=2,
                    max_value=24,
                    value=12,
                    key="seasonal_period_select"
                )

            def find_best_arima(train_data, max_p=2, max_d=1, max_q=2):
                best_aic = float('inf')
                best_order = None
                best_model = None

                for p in range(max_p + 1):
                    for d in range(max_d + 1):
                        for q in range(max_q + 1):
                            try:
                                model = ARIMA(train_data, order=(p, d, q))
                                fitted = model.fit()
                                if fitted.aic < best_aic:
                                    best_aic = fitted.aic
                                    best_order = (p, d, q)
                                    best_model = fitted
                            except:
                                continue
                return best_model, best_order, best_aic

            if st.button(f"🚀 Train Models", type="primary", use_container_width=True, key="train_button"):
                results = {}
                progress_text = st.empty()

                if run_sma:
                    progress_text.text("Training Simple Moving Average model...")
                    try:
                        best_mae = float('inf')
                        best_forecast_sma = None
                        best_window = 3

                        for window in range(2, min(7, len(train) + 1)):
                            forecasts = []
                            for i in range(len(test)):
                                if i == 0:
                                    window_data = train.values[-window:]
                                else:
                                    window_data = list(train.values[-(window):]) + forecasts[:i] if len(train.values) >= window else list(train.values) + forecasts[:i]
                                    window_data = window_data[-window:]

                                forecast = np.mean(window_data)
                                forecasts.append(forecast)

                            mae = mean_absolute_error(test.values[:len(forecasts)], forecasts)
                            if mae < best_mae:
                                best_mae = mae
                                best_forecast_sma = forecasts
                                best_window = window

                        results['SMA'] = {'forecast': np.array(best_forecast_sma)[:len(test)], 'window': best_window}
                    except Exception as e:
                        st.warning(f"Simple Moving Average failed: {str(e)[:100]}")

                if run_ema:
                    progress_text.text("Training Exponential Moving Average model...")
                    try:
                        best_mae = float('inf')
                        best_forecast_ema = None
                        best_span = 3

                        for span in range(2, min(7, len(train) + 1)):
                            alpha = 2 / (span + 1)
                            forecasts = []
                            ema_value = np.mean(train.values[-span:])

                            for i in range(len(test)):
                                if i == 0:
                                    ema_value = alpha * train.values[-1] + (1 - alpha) * ema_value
                                else:
                                    ema_value = alpha * forecasts[-1] + (1 - alpha) * ema_value
                                forecasts.append(ema_value)

                            mae = mean_absolute_error(test.values[:len(forecasts)], forecasts)
                            if mae < best_mae:
                                best_mae = mae
                                best_forecast_ema = forecasts
                                best_span = span

                        results['EMA'] = {'forecast': np.array(best_forecast_ema)[:len(test)], 'span': best_span}
                    except Exception as e:
                        st.warning(f"Exponential Moving Average failed: {str(e)[:100]}")

                if run_arima:
                    progress_text.text("Training ARIMA model...")
                    try:
                        model_arima, order, aic = find_best_arima(train.values)
                        if model_arima:
                            forecast_arima = model_arima.forecast(steps=len(test))
                            results['ARIMA'] = {'forecast': forecast_arima, 'order': order, 'aic': aic}
                        else:
                            model_arima = ARIMA(train.values, order=(1, 1, 1)).fit()
                            forecast_arima = model_arima.forecast(steps=len(test))
                            results['ARIMA'] = {'forecast': forecast_arima, 'order': (1, 1, 1), 'aic': model_arima.aic}
                    except Exception as e:
                        st.warning(f"ARIMA failed: {str(e)[:100]}")

                if run_ses:
                    progress_text.text("Training Simple Exponential Smoothing (SES)...")
                    try:
                        model_ses = SimpleExpSmoothing(train.values).fit(optimized=True)
                        forecast_ses = model_ses.forecast(steps=len(test))
                        results['SES'] = {'forecast': forecast_ses, 'alpha': model_ses.params['smoothing_level'] if hasattr(model_ses, 'params') else None}
                    except Exception as e:
                        st.warning(f"SES failed: {str(e)[:100]}")

                if run_des:
                    trend_text = "additive" if trend_type == "add" else "multiplicative" if trend_type == "mul" else "no"
                    progress_text.text(f"Training Double Exponential Smoothing (DES) with {trend_text} trend...")
                    try:
                        if trend_type is None:
                            model_des = SimpleExpSmoothing(train.values).fit(optimized=True)
                            results['DES'] = {'forecast': model_des.forecast(steps=len(test)), 'alpha': model_des.params['smoothing_level'] if hasattr(model_des, 'params') else None, 'beta': None, 'trend_type': 'none'}
                        elif trend_type == 'add':
                            model_des = Holt(train.values).fit(optimized=True)
                            results['DES'] = {'forecast': model_des.forecast(steps=len(test)), 'alpha': model_des.params['smoothing_level'] if hasattr(model_des, 'params') else None, 'beta': model_des.params['smoothing_trend'] if hasattr(model_des, 'params') and 'smoothing_trend' in model_des.params else None, 'trend_type': 'additive'}
                        else:
                            model_des = ExponentialSmoothing(train.values, trend='mul', seasonal=None).fit(optimized=True)
                            results['DES'] = {'forecast': model_des.forecast(steps=len(test)), 'alpha': model_des.params['smoothing_level'] if hasattr(model_des, 'params') else None, 'beta': model_des.params['smoothing_trend'] if hasattr(model_des, 'params') and 'smoothing_trend' in model_des.params else None, 'trend_type': 'multiplicative'}
                    except Exception as e:
                        st.warning(f"DES failed: {str(e)[:100]}")

                if run_tes:
                    trend_text = "additive" if trend_type == "add" else "multiplicative" if trend_type == "mul" else "none"
                    season_text = "additive" if seasonal_type == "add" else "multiplicative" if seasonal_type == "mul" else "none"
                    progress_text.text(f"Training Triple Exponential Smoothing (TES) with {trend_text} trend and {season_text} seasonality...")
                    try:
                        seasonal_periods_actual = min(seasonal_period, len(train) // 2)
                        if seasonal_periods_actual >= 2:
                            model_tes = ExponentialSmoothing(train.values, trend=trend_type if trend_type else None, seasonal=seasonal_type if seasonal_type else None, seasonal_periods=seasonal_periods_actual).fit(optimized=True)
                            forecast_tes = model_tes.forecast(steps=len(test))
                            results['TES'] = {'forecast': forecast_tes, 'alpha': model_tes.params['smoothing_level'] if hasattr(model_tes, 'params') else None, 'beta': model_tes.params['smoothing_trend'] if hasattr(model_tes, 'params') and 'smoothing_trend' in model_tes.params else None, 'gamma': model_tes.params['smoothing_seasonal'] if hasattr(model_tes, 'params') and 'smoothing_seasonal' in model_tes.params else None, 'trend_type': trend_type, 'seasonal_type': seasonal_type, 'seasonal_periods': seasonal_periods_actual}
                        else:
                            st.info(f"Not enough data for seasonal model. Need at least {seasonal_period * 2} months.")
                    except Exception as e:
                        st.warning(f"TES failed: {str(e)[:100]}")

                progress_text.empty()

                if results:
                    metrics = []
                    color_map = {'SMA': '#F4A261', 'EMA': '#E76F51', 'ARIMA': '#E63946', 'SES': '#2A9D8F', 'DES': '#E9C46A', 'TES': '#9B5DE5'}

                    for name, result in results.items():
                        forecast = result['forecast'][:len(test)]
                        forecast = np.maximum(forecast, 0)

                        mae = mean_absolute_error(test.values, forecast)
                        mse = mean_squared_error(test.values, forecast)
                        rmse = np.sqrt(mse)
                        mape = mean_absolute_percentage_error(test.values, forecast) * 100

                        metric_dict = {"Model": name, "MAE": f"{mae:,.0f}", "MSE": f"{mse:,.0f}", "RMSE": f"{rmse:,.0f}", "MAPE": f"{mape:.2f}%"}

                        params_str = ""
                        if name == 'SMA' and 'window' in result:
                            params_str = f"Window={result['window']}"
                        elif name == 'EMA' and 'span' in result:
                            params_str = f"Span={result['span']}"
                        elif name == 'ARIMA' and 'order' in result:
                            params_str = f"ARIMA{result['order']}"
                        elif name == 'SES' and 'alpha' in result and result['alpha'] is not None:
                            params_str = f"α={result['alpha']:.4f}"
                        elif name == 'DES':
                            params = []
                            if result.get('alpha') is not None:
                                params.append(f"α={result['alpha']:.4f}")
                            if result.get('beta') is not None:
                                params.append(f"β={result['beta']:.4f}")
                            if result.get('trend_type'):
                                params.append(f"trend={result['trend_type']}")
                            params_str = ", ".join(params)
                        elif name == 'TES':
                            params = []
                            if result.get('alpha') is not None:
                                params.append(f"α={result['alpha']:.4f}")
                            if result.get('beta') is not None:
                                params.append(f"β={result['beta']:.4f}")
                            if result.get('gamma') is not None:
                                params.append(f"γ={result['gamma']:.4f}")
                            if result.get('trend_type'):
                                params.append(f"trend={result['trend_type']}")
                            if result.get('seasonal_type'):
                                params.append(f"season={result['seasonal_type']}")
                            if result.get('seasonal_periods'):
                                params.append(f"period={result['seasonal_periods']}")
                            params_str = ", ".join(params)

                        if params_str:
                            metric_dict["Parameters"] = params_str

                        metrics.append(metric_dict)

                    st.markdown("#### 📊 Model Performance Metrics")
                    st.dataframe(pd.DataFrame(metrics), use_container_width=True, hide_index=True)

                    valid_metrics = [m for m in metrics if m['MAPE'] not in ['inf', 'nan', 'inf%'] and 'inf' not in m['MAPE']]
                    if valid_metrics:
                        best_model = min(valid_metrics, key=lambda x: float(x['MAPE'].replace('%', '')))
                        st.success(f"🏆 **Best Model: {best_model['Model']}** with MAPE = {best_model['MAPE']}")

                        fig, ax = plt.subplots(figsize=(14, 7))
                        ax.plot(material_data.index, material_data.values, label='Actual', color='#2E86AB', linewidth=2, marker='o')
                        forecast_dates = test.index

                        for name, result in results.items():
                            if name in color_map:
                                forecast_values = result['forecast'][:len(forecast_dates)]
                                forecast_values = np.maximum(forecast_values, 0)
                                ax.plot(forecast_dates, forecast_values, label=name, color=color_map[name], linestyle='--', linewidth=2, marker='s')

                        ax.set_xlabel("Date", fontsize=11)
                        ax.set_ylabel("Quantity", fontsize=11)
                        ax.set_title(f"{selected_material[:60]} - Model Comparison", fontsize=12)
                        ax.legend(fontsize=9)
                        ax.grid(True, alpha=0.3)
                        ax.tick_params(labelsize=9)
                        plt.xticks(rotation=45)
                        st.pyplot(fig)

                        st.session_state['trained_models'] = results
                        st.session_state['test_data'] = test
                        st.session_state['best_model_name'] = best_model['Model']
                    else:
                        st.error("Could not determine best model from metrics")
                else:
                    st.error("No models were successfully trained.")

    with tab5:
        st.markdown(f"### Future Forecasting - {selected_material[:50]}...")

        if len(material_data) >= 3:
            st.markdown("#### 📊 Forecast Configuration")
            col1, col2 = st.columns(2)
            with col1:
                forecast_type = st.radio(
                    "Select forecast approach:",
                    ["Monthly Models (SMA, EMA, ARIMA, SES, DES, TES)", "Annual Aggregation Methods (Linear, Simple Avg, Weighted Avg)"],
                    key="forecast_type_radio"
                )

            if "Monthly Models" in forecast_type:
                forecast_periods = st.number_input("Number of months to forecast", min_value=1, max_value=48, value=12, key="forecast_months")
            else:
                forecast_years = st.number_input("Number of years to forecast", min_value=1, max_value=10, value=3, key="forecast_years")
                forecast_periods = forecast_years * 12

                st.markdown("#### 📊 Select Annual Forecasting Methods")
                col1, col2, col3 = st.columns(3)
                with col1:
                    use_linear_method = st.checkbox("Linear Regression", value=True, key="use_linear")
                with col2:
                    use_simple_avg_method = st.checkbox("Simple Average", value=True, key="use_simple_avg")
                with col3:
                    use_weighted_avg_method = st.checkbox("Weighted Average (Optimal)", value=True, key="use_weighted_avg")

            st.markdown("#### 📊 Data Points Selection for Forecasting")
            col1, col2 = st.columns(2)
            with col1:
                use_all_data = st.radio(
                    "Select data points to use for forecasting:",
                    ["Use all available data", "Use last N years only"],
                    key="data_points_selection"
                )

            n_years_for_forecast = None
            if use_all_data == "Use last N years only":
                with col2:
                    temp_df = pd.DataFrame({'Date': material_data_full.index, 'Demand': material_data_full.values})
                    temp_df['Fiscal_Year'] = temp_df['Date'].apply(get_fiscal_year)
                    available_years = temp_df['Fiscal_Year'].nunique()

                    n_years_for_forecast = st.slider(
                        f"Number of fiscal years to use (max: {available_years})",
                        min_value=1,
                        max_value=available_years,
                        value=min(3, available_years),
                        key="n_years_forecast"
                    )
                    st.info(f"Using last {n_years_for_forecast} fiscal years of data for forecasting")

            st.markdown("#### Select Models for Forecasting")
            if "Monthly Models" in forecast_type:
                col1, col2, col3, col4, col5, col6 = st.columns(6)
                with col1:
                    use_sma = st.checkbox("Simple MA", value=True, key="forecast_sma")
                with col2:
                    use_ema = st.checkbox("Exponential MA", value=True, key="forecast_ema")
                with col3:
                    use_arima = st.checkbox("ARIMA", value=True, key="forecast_arima")
                with col4:
                    use_ses = st.checkbox("SES", value=True, key="forecast_ses")
                with col5:
                    use_des = st.checkbox("DES/Holt", value=True, key="forecast_des")
                with col6:
                    use_tes = st.checkbox("TES/HW", value=True, key="forecast_tes")
            else:
                use_sma = use_ema = use_arima = use_ses = use_des = use_tes = False

            st.markdown("---")
            st.markdown("#### ⚙️ Configuration Options")

            if "Monthly Models" in forecast_type:
                st.info("Configure the monthly forecasting models below:")
                col1, col2, col3 = st.columns(3)
                with col1:
                    forecast_trend = st.selectbox("📈 Trend Type (for DES/TES)", options=["add", "mul", None], format_func=lambda x: "Additive" if x == "add" else "Multiplicative" if x == "mul" else "None (No Trend)", key="forecast_trend_select")

                with col2:
                    if use_tes:
                        forecast_season = st.selectbox("📅 Seasonal Type (for TES only)", options=["add", "mul", None], format_func=lambda x: "Additive" if x == "add" else "Multiplicative" if x == "mul" else "None (No Seasonality)", key="forecast_season_select")
                    else:
                        forecast_season = None

                with col3:
                    if use_tes:
                        forecast_seasonal_period = st.number_input("Seasonal Period (months)", min_value=2, max_value=24, value=12, key="forecast_seasonal_period")
                    else:
                        forecast_seasonal_period = 12
            else:
                forecast_trend = None
                forecast_season = None
                forecast_seasonal_period = 12

            if st.button("🔮 Generate Future Forecast", type="primary", use_container_width=True, key="generate_forecast"):
                if use_all_data == "Use last N years only" and n_years_for_forecast is not None:
                    temp_df = pd.DataFrame({'Date': material_data_full.index, 'Demand': material_data_full.values})
                    temp_df['Fiscal_Year'] = temp_df['Date'].apply(get_fiscal_year)
                    available_years = sorted(temp_df['Fiscal_Year'].unique())
                    last_n_years = available_years[-n_years_for_forecast:]
                    fiscal_years_series = pd.Series(temp_df['Fiscal_Year'].values, index=material_data_full.index)
                    mask = fiscal_years_series.isin(last_n_years)
                    forecast_data = material_data_full[mask]
                    st.info(f"📊 Using last {n_years_for_forecast} fiscal years of data for forecasting (from {forecast_data.index[0].strftime('%b-%Y')} to {forecast_data.index[-1].strftime('%b-%Y')})")
                else:
                    forecast_data = material_data_full
                    st.info(f"📊 Using all {len(forecast_data)} months of data for forecasting")

                fig, ax = plt.subplots(figsize=(14, 7))
                ax.plot(forecast_data.index, forecast_data.values, label='Historical (Data used for forecasting)', color='#2E86AB', linewidth=2, marker='o')

                future_forecasts = {}
                color_map = {'SMA': '#F4A261', 'EMA': '#E76F51', 'ARIMA': '#E63946', 'SES': '#2A9D8F', 'DES': '#E9C46A', 'TES': '#9B5DE5', 
                            'Linear (Yearly)': '#A569BD', 'Simple Average (Yearly)': '#1ABC9C', 'Weighted Average (Yearly)': '#E67E22'}

                last_date = forecast_data.index[-1]
                if hasattr(last_date, 'strftime'):
                    future_dates = pd.date_range(start=last_date, periods=forecast_periods + 1, freq='MS')[1:]
                else:
                    future_dates = pd.date_range(start=pd.Timestamp.now(), periods=forecast_periods, freq='MS')

                if "Annual Aggregation Methods" in forecast_type:
                    if use_linear_method:
                        try:
                            monthly_pred, yearly_pred, linear_model, yearly_data = linear_forecast_with_yearly_data(
                                forecast_data, forecast_years, 
                                n_years_for_forecast if use_all_data == "Use last N years only" else None
                            )

                            if monthly_pred is not None:
                                monthly_pred = monthly_pred[:forecast_periods]
                                future_forecasts['Linear (Yearly)'] = pd.Series(monthly_pred, index=future_dates)
                                ax.plot(future_dates, monthly_pred, label=f'Linear Regression', color=color_map['Linear (Yearly)'], linestyle='--', linewidth=2.5, marker='s')
                                linear_total = monthly_pred.sum()
                                st.success(f"📊 **Linear Regression Total for {forecast_years} year(s): {linear_total:,.0f} units**")

                                st.markdown("#### 📈 Linear Regression - Yearly Forecast Breakdown")
                                yearly_breakdown = []
                                for i, year_pred in enumerate(yearly_pred):
                                    yearly_breakdown.append({
                                        "Year": f"Year {i+1}",
                                        "Total Annual Demand": f"{year_pred:,.0f}",
                                        "Monthly Average": f"{year_pred/12:,.0f}"
                                    })
                                st.dataframe(pd.DataFrame(yearly_breakdown), use_container_width=True, hide_index=True)

                                if yearly_data is not None and len(yearly_data) > 0:
                                    with st.expander("📊 Historical Yearly Data (Used for Linear Regression)"):
                                        yearly_df = pd.DataFrame({
                                            'Fiscal Year': yearly_data.index,
                                            'Total Annual Demand': yearly_data.values
                                        })
                                        st.dataframe(yearly_df, use_container_width=True, hide_index=True)
                                        if linear_model is not None:
                                            st.info(f"📐 **Regression Equation:** Yearly Demand = {linear_model.coef_[0]:.0f} × Year + {linear_model.intercept_:.0f}")
                            else:
                                st.warning("Not enough yearly data for linear forecast. Need at least 3 fiscal years of data.")
                        except Exception as e:
                            st.warning(f"Linear forecast failed: {str(e)[:200]}")

                    if use_simple_avg_method:
                        try:
                            monthly_pred, yearly_pred = simple_average_forecast(
                                forecast_data, forecast_years,
                                n_years_for_forecast if use_all_data == "Use last N years only" else None
                            )

                            if monthly_pred is not None:
                                monthly_pred = monthly_pred[:forecast_periods]
                                future_forecasts['Simple Average (Yearly)'] = pd.Series(monthly_pred, index=future_dates)
                                ax.plot(future_dates, monthly_pred, label=f'Simple Average', color=color_map['Simple Average (Yearly)'], linestyle='--', linewidth=2.5, marker='s')
                                simple_total = monthly_pred.sum()
                                st.success(f"📊 **Simple Average Total for {forecast_years} year(s): {simple_total:,.0f} units**")

                                st.markdown("#### 📈 Simple Average - Yearly Forecast Breakdown")
                                yearly_breakdown = []
                                for i, year_pred in enumerate(yearly_pred):
                                    yearly_breakdown.append({
                                        "Year": f"Year {i+1}",
                                        "Total Annual Demand": f"{year_pred:,.0f}",
                                        "Monthly Average": f"{year_pred/12:,.0f}"
                                    })
                                st.dataframe(pd.DataFrame(yearly_breakdown), use_container_width=True, hide_index=True)
                            else:
                                st.warning("Not enough yearly data for simple average forecast. Need at least 1 fiscal year of data.")
                        except Exception as e:
                            st.warning(f"Simple average forecast failed: {str(e)[:200]}")

                    if use_weighted_avg_method:
                        try:
                            monthly_pred, yearly_pred = weighted_average_forecast(
                                forecast_data, forecast_years,
                                n_years_for_forecast if use_all_data == "Use last N years only" else None
                            )

                            if monthly_pred is not None:
                                monthly_pred = monthly_pred[:forecast_periods]
                                future_forecasts['Weighted Average (Yearly)'] = pd.Series(monthly_pred, index=future_dates)
                                ax.plot(future_dates, monthly_pred, label=f'Weighted Average (Optimal)', color=color_map['Weighted Average (Yearly)'], linestyle='--', linewidth=2.5, marker='s')
                                weighted_total = monthly_pred.sum()
                                st.success(f"📊 **Weighted Average Total for {forecast_years} year(s): {weighted_total:,.0f} units**")

                                st.markdown("#### 📈 Weighted Average - Yearly Forecast Breakdown")
                                yearly_breakdown = []
                                for i, year_pred in enumerate(yearly_pred):
                                    yearly_breakdown.append({
                                        "Year": f"Year {i+1}",
                                        "Total Annual Demand": f"{year_pred:,.0f}",
                                        "Monthly Average": f"{year_pred/12:,.0f}"
                                    })
                                st.dataframe(pd.DataFrame(yearly_breakdown), use_container_width=True, hide_index=True)
                            else:
                                st.warning("Not enough yearly data for weighted average forecast. Need at least 2 fiscal years of data.")
                        except Exception as e:
                            st.warning(f"Weighted average forecast failed: {str(e)[:200]}")

                if "Monthly Models" in forecast_type:
                    if use_sma:
                        try:
                            data_values = forecast_data.values
                            best_window = 3
                            best_mae = float('inf')

                            for window in range(2, min(7, len(data_values))):
                                forecasts = []
                                for i in range(window, len(data_values)):
                                    window_data = data_values[i-window:i]
                                    forecast = np.mean(window_data)
                                    forecasts.append(forecast)

                                if len(forecasts) > 0:
                                    actual = data_values[window:]
                                    if len(actual) == len(forecasts):
                                        mae = mean_absolute_error(actual, forecasts)
                                        if mae < best_mae:
                                            best_mae = mae
                                            best_window = window

                            forecast_sma = []
                            last_values = list(data_values[-best_window:])

                            for _ in range(forecast_periods):
                                forecast = np.mean(last_values[-best_window:])
                                forecast_sma.append(forecast)
                                last_values.append(forecast)
                                if len(last_values) > best_window:
                                    last_values = last_values[-best_window:]

                            forecast_sma = np.maximum(forecast_sma, 0)
                            future_forecasts['SMA'] = pd.Series(forecast_sma, index=future_dates)
                            ax.plot(future_dates, forecast_sma, label=f'SMA (window={best_window})', color=color_map['SMA'], linestyle='--', linewidth=2, marker='s')
                        except Exception as e:
                            st.warning(f"SMA forecast failed: {str(e)[:100]}")

                    if use_ema:
                        try:
                            data_values = forecast_data.values
                            best_span = 3
                            best_mae = float('inf')

                            for span in range(2, min(7, len(data_values))):
                                alpha = 2 / (span + 1)
                                forecasts = []
                                ema_value = np.mean(data_values[:span])

                                for i in range(span, len(data_values)):
                                    ema_value = alpha * data_values[i-1] + (1 - alpha) * ema_value
                                    forecasts.append(ema_value)

                                if len(forecasts) > 0:
                                    actual = data_values[span:]
                                    if len(actual) == len(forecasts):
                                        mae = mean_absolute_error(actual, forecasts)
                                        if mae < best_mae:
                                            best_mae = mae
                                            best_span = span

                            alpha = 2 / (best_span + 1)
                            forecast_ema = []
                            ema_value = np.mean(data_values[-best_span:])

                            for _ in range(forecast_periods):
                                ema_value = alpha * (forecast_ema[-1] if forecast_ema else data_values[-1]) + (1 - alpha) * ema_value
                                forecast_ema.append(ema_value)

                            forecast_ema = np.maximum(forecast_ema, 0)
                            future_forecasts['EMA'] = pd.Series(forecast_ema, index=future_dates)
                            ax.plot(future_dates, forecast_ema, label=f'EMA (span={best_span})', color=color_map['EMA'], linestyle='--', linewidth=2, marker='s')
                        except Exception as e:
                            st.warning(f"EMA forecast failed: {str(e)[:100]}")

                    if use_arima:
                        try:
                            def find_best_arima_full(train_data):
                                best_aic = float('inf')
                                best_order = None
                                best_model = None
                                max_p = min(3, len(train_data) // 3)
                                max_q = min(3, len(train_data) // 3)

                                for p in range(max_p + 1):
                                    for d in range(2):
                                        for q in range(max_q + 1):
                                            try:
                                                model = ARIMA(train_data, order=(p, d, q))
                                                fitted = model.fit()
                                                if fitted.aic < best_aic:
                                                    best_aic = fitted.aic
                                                    best_order = (p, d, q)
                                                    best_model = fitted
                                            except:
                                                continue
                                return best_model, best_order, best_aic

                            data_for_forecast = forecast_data.values
                            model, order, aic = find_best_arima_full(data_for_forecast)
                            if model:
                                forecast = model.forecast(steps=forecast_periods)
                            else:
                                model = ARIMA(data_for_forecast, order=(1, 1, 1)).fit()
                                forecast = model.forecast(steps=forecast_periods)

                            forecast = np.maximum(forecast, 0)
                            future_forecasts['ARIMA'] = pd.Series(forecast, index=future_dates)
                            ax.plot(future_dates, forecast, label='ARIMA Forecast', color=color_map['ARIMA'], linestyle='--', linewidth=2, marker='s')
                        except Exception as e:
                            st.warning(f"ARIMA forecast failed: {str(e)[:100]}")

                    if use_ses:
                        try:
                            model = SimpleExpSmoothing(forecast_data.values).fit(optimized=True)
                            forecast = model.forecast(steps=forecast_periods)
                            forecast = np.maximum(forecast, 0)
                            future_forecasts['SES'] = pd.Series(forecast, index=future_dates)
                            ax.plot(future_dates, forecast, label='SES Forecast', color=color_map['SES'], linestyle='--', linewidth=2, marker='s')
                        except Exception as e:
                            st.warning(f"SES forecast failed: {str(e)[:100]}")

                    if use_des:
                        try:
                            if forecast_trend is None:
                                model = SimpleExpSmoothing(forecast_data.values).fit(optimized=True)
                            elif forecast_trend == 'add':
                                model = Holt(forecast_data.values).fit(optimized=True)
                            else:
                                model = ExponentialSmoothing(forecast_data.values, trend='mul', seasonal=None).fit(optimized=True)

                            forecast = model.forecast(steps=forecast_periods)
                            forecast = np.maximum(forecast, 0)
                            future_forecasts['DES'] = pd.Series(forecast, index=future_dates)
                            trend_label = "add" if forecast_trend == "add" else "mul" if forecast_trend == "mul" else "none"
                            ax.plot(future_dates, forecast, label=f'DES (trend={trend_label})', color=color_map['DES'], linestyle='--', linewidth=2, marker='s')
                        except Exception as e:
                            st.warning(f"DES forecast failed: {str(e)[:100]}")

                    if use_tes:
                        try:
                            seasonal_periods_actual = min(forecast_seasonal_period, len(forecast_data) // 2)
                            if seasonal_periods_actual >= 2:
                                model = ExponentialSmoothing(forecast_data.values, trend=forecast_trend if forecast_trend else None, seasonal=forecast_season if forecast_season else None, seasonal_periods=seasonal_periods_actual).fit(optimized=True)
                                forecast = model.forecast(steps=forecast_periods)
                                forecast = np.maximum(forecast, 0)
                                future_forecasts['TES'] = pd.Series(forecast, index=future_dates)
                                trend_label = "add" if forecast_trend == "add" else "mul" if forecast_trend == "mul" else "none"
                                season_label = "add" if forecast_season == "add" else "mul" if forecast_season == "mul" else "none"
                                ax.plot(future_dates, forecast, label=f'TES (trend={trend_label}, season={season_label})', color=color_map['TES'], linestyle='--', linewidth=2, marker='s')
                            else:
                                st.info(f"Not enough data for seasonal model. Need at least {forecast_seasonal_period * 2} months.")
                        except Exception as e:
                            st.warning(f"TES forecast failed: {str(e)[:100]}")

                ax.set_xlabel("Date", fontsize=11)
                ax.set_ylabel("Quantity", fontsize=11)
                ax.set_title(f"{selected_material[:60]} - Future Forecast", fontsize=12)
                ax.legend(loc='best', fontsize=9)
                ax.grid(True, alpha=0.3)
                ax.tick_params(labelsize=9)
                plt.xticks(rotation=45)
                st.pyplot(fig)

                if future_forecasts:
                    st.markdown("#### 📊 Total Forecast Summary")
                    total_summary = []
                    for model_name, forecast_series in future_forecasts.items():
                        total_summary.append({
                            "Model": model_name,
                            f"Total for Period": f"{forecast_series.sum():,.0f}",
                            "Average Monthly": f"{forecast_series.mean():,.0f}",
                            "Min Month": f"{forecast_series.min():,.0f}",
                            "Max Month": f"{forecast_series.max():,.0f}"
                        })

                    total_df = pd.DataFrame(total_summary)
                    st.dataframe(total_df, use_container_width=True, hide_index=True)

                st.session_state['future_forecasts'] = future_forecasts
        else:
            st.warning(f"Not enough data for forecasting. Need at least 3 months. Currently have {len(material_data)}.")

    with tab6:
        st.markdown(f"### Forecast Results - {selected_material[:50]}...")

        if 'future_forecasts' in st.session_state and st.session_state['future_forecasts']:
            forecasts = st.session_state['future_forecasts']
            forecast_df = pd.DataFrame(forecasts)

            if not isinstance(forecast_df.index, pd.DatetimeIndex):
                forecast_df.index = pd.to_datetime(forecast_df.index)

            forecast_df_display = forecast_df.copy()
            forecast_df_display.index = forecast_df_display.index.strftime('%b-%Y')

            st.markdown("#### 🎯 Select Time Range for Detailed View")
            col1, col2 = st.columns(2)

            with col1:
                available_dates = forecast_df_display.index.tolist()
                if len(available_dates) > 0:
                    start_date = st.selectbox("Start Date", options=available_dates, index=0, key="range_start")

            with col2:
                if len(available_dates) > 0:
                    end_date = st.selectbox("End Date", options=available_dates, index=len(available_dates)-1, key="range_end")

            if len(available_dates) > 0:
                start_pos = available_dates.index(start_date)
                end_pos = available_dates.index(end_date)

                if start_pos <= end_pos:
                    filtered_df = forecast_df.iloc[start_pos:end_pos+1]
                    filtered_df_display = forecast_df_display.iloc[start_pos:end_pos+1]

                    st.markdown(f"#### 📋 Detailed Monthly Forecast ({start_date} to {end_date})")

                    transposed_df = filtered_df_display.T
                    transposed_df.index.name = 'Model'
                    transposed_df.columns.name = 'Date'
                    st.dataframe(transposed_df, use_container_width=True)

                    st.markdown(f"#### 📊 Yearly Split Summary (Fiscal Year - April to March)")

                    def get_fiscal_year_from_date(date):
                        if date.month >= 4:
                            return f"FY {date.year}/{str(date.year+1)[-2:]}"
                        else:
                            return f"FY {date.year-1}/{str(date.year)[-2:]}"

                    all_yearly_summaries = []
                    for model_name in filtered_df.columns:
                        model_data = filtered_df[model_name]
                        fiscal_year_dict = {}
                        for idx, value in model_data.items():
                            fiscal_year = get_fiscal_year_from_date(idx)
                            if fiscal_year not in fiscal_year_dict:
                                fiscal_year_dict[fiscal_year] = []
                            fiscal_year_dict[fiscal_year].append(value)

                        for fiscal_year, values in fiscal_year_dict.items():
                            yearly_total = sum(values)
                            monthly_avg = yearly_total / len(values)
                            all_yearly_summaries.append({
                                "Model": model_name,
                                "Fiscal Year": fiscal_year,
                                "Total Demand": f"{yearly_total:,.0f}",
                                "Average Monthly": f"{monthly_avg:,.0f}",
                                "Number of Months": len(values)
                            })

                    if all_yearly_summaries:
                        yearly_summary_df = pd.DataFrame(all_yearly_summaries)
                        yearly_summary_df = yearly_summary_df.sort_values(['Model', 'Fiscal Year'])
                        st.dataframe(yearly_summary_df, use_container_width=True, hide_index=True)

                        st.markdown("#### 📊 Pivot View - Yearly Totals by Model")
                        pivot_df = yearly_summary_df.pivot(index='Model', columns='Fiscal Year', values='Total Demand')
                        st.dataframe(pivot_df, use_container_width=True)

                    st.markdown(f"#### 📊 Selected Range Summary ({start_date} to {end_date})")
                    summary_range_data = []
                    for model_name in filtered_df.columns:
                        summary_range_data.append({
                            "Model": model_name,
                            "Total for Period": f"{filtered_df[model_name].sum():,.0f}",
                            "Average Monthly": f"{filtered_df[model_name].mean():,.0f}",
                            "Min in Period": f"{filtered_df[model_name].min():,.0f}",
                            "Max in Period": f"{filtered_df[model_name].max():,.0f}",
                            "Number of Months": len(filtered_df)
                        })

                    st.dataframe(pd.DataFrame(summary_range_data), use_container_width=True, hide_index=True)

                    csv_transposed = transposed_df.to_csv()
                    safe_name = re.sub(r'[^\w\s-]', '', selected_material[:30]).replace(' ', '_')
                    st.download_button(
                        label=f"📥 Download Forecast Data (Transposed - {start_date} to {end_date})", 
                        data=csv_transposed, 
                        file_name=f"forecast_{safe_name}_{start_date}_{end_date}_transposed.csv", 
                        mime="text/csv", 
                        use_container_width=True
                    )
                else:
                    st.error("End date must be after start date")
        else:
            st.info("👈 Please generate forecasts in the 'Forecasting' tab first.")

else:
    st.markdown("""
    <div class="info-box">
    <h3>👈 Please upload your Excel file to begin</h3>
    <p><strong>Your file should have:</strong><br>
    - <strong>First column</strong>: Material Description (product names)<br>
    - <strong>Other columns</strong>: Monthly data columns (can be dates or month names)<br>
    - <strong>Values</strong>: Demand quantities (can have commas like "2,353")</p>

    <p><strong>Models Available:</strong><br>
    - <strong>SMA</strong> (Simple Moving Average) - Rolling window, drops oldest each time<br>
    - <strong>EMA</strong> (Exponential Moving Average) - More weight to recent<br>
    - <strong>ARIMA</strong> (AutoRegressive Integrated Moving Average)<br>
    - <strong>SES</strong> (Simple Exponential Smoothing)<br>
    - <strong>DES</strong> (Double Exponential Smoothing/Holt)<br>
    - <strong>TES</strong> (Triple Exponential Smoothing/Holt-Winters)<br>
    - <strong>Linear Regression (Yearly)</strong> - Uses fiscal year totals for forecasting<br>
    - <strong>Simple Average (Yearly)</strong> - Average of historical yearly totals<br>
    - <strong>Weighted Average (Yearly)</strong> - Optimal weights that minimize forecast error</p>

    <p><strong>How to use:</strong><br>
    1. Upload your Excel file<br>
    2. Select a material from the dropdown<br>
    3. Go to <strong>Model Training</strong>, ensure all models are checked (default), then click "Train Models"<br>
    4. Go to <strong>Forecasting</strong>, choose data points to use, forecast approach, then click "Generate Future Forecast"<br>
    5. Download results in <strong>Results</strong> tab</p>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #6c757d; padding: 15px; font-family: "Times New Roman", Times, serif; font-size: 0.8rem;'>
    <b>Health Program Medicines Demand Forecasting Dashboard</b><br>
    Upload → Select → Train → Forecast → Download
    </div>
    """, 
    unsafe_allow_html=True
)
