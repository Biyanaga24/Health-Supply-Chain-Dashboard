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
import warnings
import re
import datetime
from scipy import stats
warnings.filterwarnings("ignore")

# Page configuration
st.set_page_config(
    page_title="Malaria Medicines Forecasting Dashboard",
    page_icon="💊",
    layout="wide"
)

# Title
st.title("💊 Malaria Medicines Forecasting Dashboard")
st.markdown("### Time Series Analysis and Demand Forecasting")

# Initialize session state
if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = False
if 'df' not in st.session_state:
    st.session_state.df = None
if 'materials' not in st.session_state:
    st.session_state.materials = []

# Sidebar for file upload
st.sidebar.header("📁 Data Upload")

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

def create_fiscal_year_chart(data_series, material_name):
    """Create fiscal year comparison chart (April-March)"""

    # Create a DataFrame with fiscal year groupings
    df_fiscal = pd.DataFrame({
        'Date': data_series.index,
        'Demand': data_series.values
    })

    # Assign fiscal year (April to March)
    df_fiscal['Fiscal_Year'] = df_fiscal['Date'].apply(
        lambda x: f"Apr {x.year - 1 if x.month <= 3 else x.year}-Mar {x.year if x.month <= 3 else x.year + 1}"
    )

    # Assign month number for ordering (April=1 to March=12)
    month_order = {4:1, 5:2, 6:3, 7:4, 8:5, 9:6, 10:7, 11:8, 12:9, 1:10, 2:11, 3:12}
    df_fiscal['Month_Num'] = df_fiscal['Date'].dt.month.map(month_order)
    df_fiscal['Month_Name'] = df_fiscal['Date'].dt.strftime('%b')

    # Sort by month order
    df_fiscal = df_fiscal.sort_values('Month_Num')

    # Pivot for fiscal year comparison
    fiscal_pivot = df_fiscal.pivot(index='Month_Name', columns='Fiscal_Year', values='Demand')

    # Create the plot
    fig, ax = plt.subplots(figsize=(14, 7))

    # Plot each fiscal year
    colors = ['#2E86AB', '#E63946', '#2A9D8F', '#E9C46A']
    markers = ['o', 's', '^', 'D']

    for i, (year, col) in enumerate(fiscal_pivot.items()):
        if not col.isna().all():
            ax.plot(fiscal_pivot.index, col.values, 
                   marker=markers[i % len(markers)], 
                   linewidth=2.5, 
                   markersize=8,
                   color=colors[i % len(colors)], 
                   label=year)

            # Add value labels
            for j, (month, value) in enumerate(zip(fiscal_pivot.index, col.values)):
                if not pd.isna(value) and value > 0:
                    ax.annotate(f'{value:,.0f}', 
                               xy=(month, value), 
                               xytext=(0, 8 if j % 2 == 0 else -12),
                               textcoords='offset points',
                               fontsize=8,
                               ha='center',
                               bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.7))

    ax.set_xlabel("Month", fontsize=12)
    ax.set_ylabel("Demand Quantity", fontsize=12)
    ax.set_title(f"Fiscal Year Comparison (April-March) - {material_name[:60]}", fontsize=14)
    ax.legend(loc='best')
    ax.grid(True, alpha=0.3)
    ax.set_xticklabels(fiscal_pivot.index, rotation=45)

    plt.tight_layout()

    return fig, fiscal_pivot

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

    st.subheader("📦 Select Material for Analysis")
    selected_material = st.selectbox(
        "Choose a material description",
        materials,
        key="material_selector"
    )

    material_data_full = df[selected_material]
    material_data = material_data_full[material_data_full > 0]

    st.header("📊 Data Overview")

    if len(material_data) > 0:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Records (with demand)", len(material_data))
        with col2:
            st.metric("Total Months in Timeline", len(material_data_full))
        with col3:
            start_date = material_data.index[0].strftime('%b-%Y') if hasattr(material_data.index[0], 'strftime') else str(material_data.index[0])
            st.metric("Start Date", start_date)
        with col4:
            end_date = material_data.index[-1].strftime('%b-%Y') if hasattr(material_data.index[-1], 'strftime') else str(material_data.index[-1])
            st.metric("End Date", end_date)
    else:
        st.warning("No valid data for this material")
        st.stop()

    # Create 7 tabs (added Fiscal Year Comparison)
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "📈 Data Explorer", 
        "📅 Fiscal Year Comparison",
        "🔍 Stationarity Test",
        "📊 Seasonal Decomposition",
        "📉 Model Training & Comparison",
        "🔮 Forecasting",
        "📊 Results"
    ])

    with tab1:
        st.subheader(f"Data Preview - {selected_material[:50]}...")

        display_df = material_data_full.to_frame(name="Demand")
        if hasattr(display_df.index, 'strftime'):
            display_df.index = display_df.index.strftime('%b-%Y')
        st.dataframe(display_df, use_container_width=True)

        # 1. Time Series Plot with trend line
        st.subheader("📈 Time Series Plot with Trend Line")
        fig, ax = plt.subplots(figsize=(12, 5))

        # Plot actual data
        ax.plot(material_data_full.index, material_data_full.values, 
                marker='o', linewidth=2, markersize=6, 
                color='#2E86AB', label='Actual Demand')

        # Add trend line (linear regression)
        x = np.arange(len(material_data_full.index))
        y = material_data_full.values
        z = np.polyfit(x, y, 1)
        p = np.poly1d(z)
        ax.plot(material_data_full.index, p(x), 
                linestyle='--', linewidth=2.5, color='#E63946', 
                label=f'Trend Line (slope: {z[0]:.1f})')

        # Add value labels with improved placement to avoid overlap
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

        ax.set_xlabel("Date", fontsize=12)
        ax.set_ylabel("Demand Quantity", fontsize=12)
        ax.set_title(f"{selected_material[:60]}...", fontsize=14)
        ax.legend(loc='best')
        ax.grid(True, alpha=0.3)
        plt.xticks(rotation=45)
        plt.tight_layout()
        st.pyplot(fig)

        # 2. Demand Distribution
        st.subheader("📊 Demand Distribution")
        fig2, ax2 = plt.subplots(figsize=(10, 5))

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

        ax2.set_xlabel("Demand Quantity", fontsize=12)
        ax2.set_ylabel("Density", fontsize=12)
        ax2.set_title("Demand Distribution with Density Curve", fontsize=14)
        ax2.legend(loc='best')
        ax2.grid(True, alpha=0.3)
        plt.tight_layout()
        st.pyplot(fig2)

        # 3. Summary Statistics
        st.subheader("📋 Summary Statistics (Non-Zero Values)")

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

        with st.expander("📖 Understanding the Statistics"):
            st.markdown("""
            **Key Statistics Explained:**
            - **Mean**: Average demand - sensitive to outliers
            - **Median**: Middle value when sorted - better for skewed data
            - **CV < 30%**: Low variability | **CV 30-60%**: Moderate | **CV > 60%**: High variability
            - **Skewness**: Positive = right-skewed (more low values, few high spikes)
            """)

        # Box plot
        st.subheader("🔍 Outlier Detection (Box Plot)")
        fig3, ax3 = plt.subplots(figsize=(10, 4))
        ax3.boxplot(material_data.values, vert=True, patch_artist=True,
                   boxprops=dict(facecolor='#2E86AB', alpha=0.7),
                   medianprops=dict(color='#E63946', linewidth=2))
        ax3.set_ylabel("Demand Quantity", fontsize=12)
        ax3.set_title(f"Box Plot - {selected_material[:50]}...", fontsize=14)
        ax3.grid(True, alpha=0.3, axis='y')

        q1_val = material_data.quantile(0.25)
        q3_val = material_data.quantile(0.75)
        iqr_val = q3_val - q1_val
        upper_bound = q3_val + 1.5 * iqr_val
        outliers = material_data[material_data > upper_bound]
        if len(outliers) > 0:
            ax3.text(1.1, upper_bound, f'Upper bound: {upper_bound:,.0f}\nOutliers: {len(outliers)}', 
                    fontsize=9, verticalalignment='bottom')

        plt.tight_layout()
        st.pyplot(fig3)

    with tab2:
        st.subheader(f"📅 Fiscal Year Comparison (April-March) - {selected_material[:50]}...")
        st.info("This chart compares demand across different fiscal years, helping identify year-over-year trends and seasonal patterns.")

        if len(material_data_full) >= 12:
            fig, fiscal_pivot = create_fiscal_year_chart(material_data_full, selected_material)
            st.pyplot(fig)

            # Display summary table
            st.subheader("📊 Fiscal Year Summary")

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

            # Growth rate calculation
            if len(fiscal_pivot.columns) >= 2:
                st.subheader("📈 Year-over-Year Growth")
                cols = list(fiscal_pivot.columns)
                growth_rates = []

                for i in range(1, len(cols)):
                    prev_year = fiscal_pivot[cols[i-1]].sum()
                    curr_year = fiscal_pivot[cols[i]].sum()
                    if prev_year > 0:
                        growth = ((curr_year - prev_year) / prev_year) * 100
                        growth_rates.append({
                            "Period": f"{cols[i-1]} → {cols[i]}",
                            "Growth Rate": f"{growth:+.1f}%",
                            "Change in Units": f"{curr_year - prev_year:+,.0f}"
                        })

                if growth_rates:
                    growth_df = pd.DataFrame(growth_rates)
                    st.dataframe(growth_df, use_container_width=True, hide_index=True)

                    if growth_rates and float(growth_rates[-1]['Growth Rate'].replace('%', '').replace('+', '')) > 10:
                        st.warning("⚠️ **High growth detected!** Ensure supply chain capacity can handle increasing demand.")
        else:
            st.warning(f"Not enough data for fiscal year comparison. Need at least 12 months of data. Currently have {len(material_data_full)} months.")

    with tab3:
        st.subheader(f"Stationarity Test - {selected_material[:50]}...")

        if len(material_data) >= 3:
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

                if len(material_data) > 1:
                    diff_data = material_data.diff().dropna()
                    fig, ax = plt.subplots(figsize=(10, 4))
                    ax.plot(diff_data.index, diff_data.values, color='green', marker='o', linewidth=1.5)
                    ax.set_xlabel("Date")
                    ax.set_ylabel("Differenced Quantity")
                    ax.set_title("First Difference", fontsize=12)
                    ax.axhline(y=0, color='red', linestyle='--', alpha=0.5)
                    ax.grid(True, alpha=0.3)
                    plt.xticks(rotation=45)
                    st.pyplot(fig)
        else:
            st.warning(f"Not enough data for stationarity test (need at least 3 data points). Currently have {len(material_data)}.")

    with tab4:
        st.subheader(f"Seasonal Decomposition - {selected_material[:50]}...")

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

                    fig, axes = plt.subplots(4, 1, figsize=(12, 10))

                    axes[0].plot(material_data_full.index, material_data_full.values, color='#2E86AB')
                    axes[0].set_title('Original Series', fontsize=12)
                    axes[0].set_ylabel('Demand')
                    axes[0].grid(True, alpha=0.3)

                    axes[1].plot(material_data_full.index, decomposition.trend, color='#E9C46A')
                    axes[1].set_title('Trend Component', fontsize=12)
                    axes[1].set_ylabel('Trend')
                    axes[1].grid(True, alpha=0.3)

                    axes[2].plot(material_data_full.index, decomposition.seasonal, color='#2A9D8F')
                    axes[2].set_title('Seasonal Component', fontsize=12)
                    axes[2].set_ylabel('Seasonal')
                    axes[2].grid(True, alpha=0.3)

                    axes[3].plot(material_data_full.index, decomposition.resid, color='#E63946')
                    axes[3].set_title('Residual Component', fontsize=12)
                    axes[3].set_ylabel('Residual')
                    axes[3].set_xlabel('Date')
                    axes[3].grid(True, alpha=0.3)

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

    with tab5:
        st.subheader(f"Model Training & Comparison - {selected_material[:50]}...")

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

            st.subheader("Select Models to Train")
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
            st.subheader("⚙️ Exponential Smoothing Configuration (For DES & TES)")
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

                # Simple Moving Average
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

                # Exponential Moving Average
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

                # ARIMA
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

                # SES
                if run_ses:
                    progress_text.text("Training Simple Exponential Smoothing (SES)...")
                    try:
                        model_ses = SimpleExpSmoothing(train.values).fit(optimized=True)
                        forecast_ses = model_ses.forecast(steps=len(test))
                        results['SES'] = {'forecast': forecast_ses, 'alpha': model_ses.params['smoothing_level'] if hasattr(model_ses, 'params') else None}
                    except Exception as e:
                        st.warning(f"SES failed: {str(e)[:100]}")

                # DES
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

                # TES
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

                    st.subheader("📊 Model Performance Metrics")
                    st.dataframe(pd.DataFrame(metrics), use_container_width=True, hide_index=True)

                    valid_metrics = [m for m in metrics if m['MAPE'] not in ['inf', 'nan', 'inf%'] and 'inf' not in m['MAPE']]
                    if valid_metrics:
                        best_model = min(valid_metrics, key=lambda x: float(x['MAPE'].replace('%', '')))
                        st.success(f"🏆 **Best Model: {best_model['Model']}** with MAPE = {best_model['MAPE']}")

                        fig, ax = plt.subplots(figsize=(12, 6))
                        ax.plot(material_data.index, material_data.values, label='Actual', color='#2E86AB', linewidth=2, marker='o')
                        forecast_dates = test.index

                        for name, result in results.items():
                            if name in color_map:
                                forecast_values = result['forecast'][:len(forecast_dates)]
                                forecast_values = np.maximum(forecast_values, 0)
                                ax.plot(forecast_dates, forecast_values, label=name, color=color_map[name], linestyle='--', linewidth=2, marker='s')

                        ax.set_xlabel("Date", fontsize=12)
                        ax.set_ylabel("Quantity", fontsize=12)
                        ax.set_title(f"{selected_material[:60]} - Model Comparison", fontsize=14)
                        ax.legend()
                        ax.grid(True, alpha=0.3)
                        plt.xticks(rotation=45)
                        st.pyplot(fig)

                        st.session_state['trained_models'] = results
                        st.session_state['test_data'] = test
                        st.session_state['best_model_name'] = best_model['Model']
                    else:
                        st.error("Could not determine best model from metrics")
                else:
                    st.error("No models were successfully trained.")

    with tab6:
        st.subheader(f"Future Forecasting - {selected_material[:50]}...")

        if len(material_data) >= 3:
            forecast_periods = st.number_input("Number of months to forecast", min_value=1, max_value=36, value=12, key="forecast_periods")

            st.subheader("Select Models for Forecasting")
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

            st.markdown("---")
            st.subheader("⚙️ Forecasting Configuration Options")
            st.info("Change these options to see how different configurations affect future forecasts!")

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

            if st.button("🔮 Generate Future Forecast", type="primary", use_container_width=True, key="generate_forecast"):
                fig, ax = plt.subplots(figsize=(12, 6))
                ax.plot(material_data_full.index, material_data_full.values, label='Historical', color='#2E86AB', linewidth=2, marker='o')

                future_forecasts = {}
                color_map = {'SMA': '#F4A261', 'EMA': '#E76F51', 'ARIMA': '#E63946', 'SES': '#2A9D8F', 'DES': '#E9C46A', 'TES': '#9B5DE5'}

                last_date = material_data_full.index[-1]
                if hasattr(last_date, 'strftime'):
                    future_dates = pd.date_range(start=last_date, periods=forecast_periods + 1, freq='MS')[1:]
                else:
                    future_dates = pd.date_range(start=pd.Timestamp.now(), periods=forecast_periods, freq='MS')

                # SMA Forecast
                if use_sma:
                    try:
                        data_values = material_data_full.values
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

                # EMA Forecast
                if use_ema:
                    try:
                        data_values = material_data_full.values
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

                # ARIMA Forecast
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

                        data_for_forecast = material_data_full.values
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

                # SES Forecast
                if use_ses:
                    try:
                        model = SimpleExpSmoothing(material_data_full.values).fit(optimized=True)
                        forecast = model.forecast(steps=forecast_periods)
                        forecast = np.maximum(forecast, 0)
                        future_forecasts['SES'] = pd.Series(forecast, index=future_dates)
                        ax.plot(future_dates, forecast, label='SES Forecast', color=color_map['SES'], linestyle='--', linewidth=2, marker='s')
                    except Exception as e:
                        st.warning(f"SES forecast failed: {str(e)[:100]}")

                # DES Forecast
                if use_des:
                    try:
                        if forecast_trend is None:
                            model = SimpleExpSmoothing(material_data_full.values).fit(optimized=True)
                        elif forecast_trend == 'add':
                            model = Holt(material_data_full.values).fit(optimized=True)
                        else:
                            model = ExponentialSmoothing(material_data_full.values, trend='mul', seasonal=None).fit(optimized=True)

                        forecast = model.forecast(steps=forecast_periods)
                        forecast = np.maximum(forecast, 0)
                        future_forecasts['DES'] = pd.Series(forecast, index=future_dates)
                        trend_label = "add" if forecast_trend == "add" else "mul" if forecast_trend == "mul" else "none"
                        ax.plot(future_dates, forecast, label=f'DES (trend={trend_label})', color=color_map['DES'], linestyle='--', linewidth=2, marker='s')
                    except Exception as e:
                        st.warning(f"DES forecast failed: {str(e)[:100]}")

                # TES Forecast
                if use_tes:
                    try:
                        seasonal_periods_actual = min(forecast_seasonal_period, len(material_data_full) // 2)
                        if seasonal_periods_actual >= 2:
                            model = ExponentialSmoothing(material_data_full.values, trend=forecast_trend if forecast_trend else None, seasonal=forecast_season if forecast_season else None, seasonal_periods=seasonal_periods_actual).fit(optimized=True)
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

                ax.set_xlabel("Date", fontsize=12)
                ax.set_ylabel("Quantity", fontsize=12)
                ax.set_title(f"{selected_material[:60]} - Future Forecast", fontsize=14)
                ax.legend(loc='best')
                ax.grid(True, alpha=0.3)
                plt.xticks(rotation=45)
                st.pyplot(fig)

                st.session_state['future_forecasts'] = future_forecasts
        else:
            st.warning(f"Not enough data for forecasting. Need at least 3 months. Currently have {len(material_data)}.")

    with tab7:
        st.subheader(f"Forecast Results - {selected_material[:50]}...")

        if 'future_forecasts' in st.session_state and st.session_state['future_forecasts']:
            forecasts = st.session_state['future_forecasts']
            forecast_df = pd.DataFrame(forecasts)
            if hasattr(forecast_df.index, 'strftime'):
                forecast_df.index = forecast_df.index.strftime('%b-%Y')

            st.subheader("🎯 Select Time Range for Detailed View")
            col1, col2 = st.columns(2)

            with col1:
                available_dates = forecast_df.index.tolist()
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

                    st.subheader(f"📋 Detailed Monthly Forecast ({start_date} to {end_date})")
                    st.dataframe(filtered_df, use_container_width=True)

                    st.subheader("📊 Selected Range Summary")
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

                    with st.expander("📊 View Full Forecast Totals (All Months)"):
                        total_all = forecast_df.sum()
                        totals_all_df = pd.DataFrame([total_all], index=["TOTAL ALL MONTHS"], columns=forecast_df.columns)
                        st.dataframe(totals_all_df, use_container_width=True)

                    csv_filtered = filtered_df.to_csv()
                    safe_name = re.sub(r'[^\w\s-]', '', selected_material[:30]).replace(' ', '_')
                    st.download_button(label=f"📥 Download Forecast Data ({start_date} to {end_date})", data=csv_filtered, file_name=f"forecast_{safe_name}_{start_date}_{end_date}.csv", mime="text/csv", use_container_width=True)
                else:
                    st.error("End date must be after start date")
        else:
            st.info("👈 Please generate forecasts in the 'Forecasting' tab first.")

else:
    st.info("""
    ## 👈 Please upload your Excel file to begin

    ### Your file should have:
    - **First column**: Material Description (product names)
    - **Other columns**: Monthly data columns (can be dates or month names)
    - **Values**: Demand quantities (can have commas like "2,353")

    ### Models Available:
    - **SMA** (Simple Moving Average) - Rolling window, drops oldest each time
    - **EMA** (Exponential Moving Average) - More weight to recent
    - **ARIMA** (AutoRegressive Integrated Moving Average)
    - **SES** (Simple Exponential Smoothing)
    - **DES** (Double Exponential Smoothing/Holt)
    - **TES** (Triple Exponential Smoothing/Holt-Winters)

    ### How to use:
    1. Upload your Excel file
    2. Select a material from the dropdown
    3. Go to **Fiscal Year Comparison** to see Apr-Mar trends
    4. Go to **Seasonal Decomposition** to understand patterns
    5. Go to **Model Training**, select options, click "Train Models"
    6. Go to **Forecasting**, change options, click "Generate Future Forecast"
    7. Download results in **Results** tab
    """)

st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: gray; padding: 20px;'>
    <b>Malaria Medicines Demand Forecasting Dashboard</b><br>
    Upload -> Select -> Compare Fiscal Years -> Train -> Forecast -> Download
    </div>
    """, 
    unsafe_allow_html=True
)
