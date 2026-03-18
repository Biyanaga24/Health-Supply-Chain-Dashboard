import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import sys
import os

# Add the current directory to path
sys.path.append(os.path.dirname(__file__))

# Import authentication functions
from auth import show_login_page, show_profile_page, show_admin_panel

# Check authentication
if 'auth' not in st.session_state:
    st.session_state['auth'] = False

if not st.session_state['auth']:
    show_login_page()
    st.stop()

# ---------------------------------------------------
# Page Setup
# ---------------------------------------------------
st.set_page_config(page_title="Health Program Medicines Dashboard", layout="wide")

# ---------------------------------------------------
# User Info in Sidebar
# ---------------------------------------------------
with st.sidebar:
    st.title(f"Welcome, {st.session_state['user']['full_name']}!")

# ---------------------------------------------------
# Load Data
# ---------------------------------------------------
@st.cache_data
def load_google(sheet_id):
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
    sheets = pd.read_excel(url, sheet_name=None, header=2)
    return {name: clean_df(df) for name, df in sheets.items()}

@st.cache_data(ttl=60)
def load_external(path):
    try:
        df = pd.read_excel(path, header=0)
        return clean_df(df)
    except Exception as e:
        st.error(f"External Excel not found or invalid: {e}")
        return pd.DataFrame()

@st.cache_data
def load_branch_data(filename):
    """Load branch data from current directory"""
    try:
        if os.path.exists(filename):
            df = pd.read_excel(filename)
            return clean_df(df)
        else:
            st.warning(f"Branch data file '{filename}' not found in the application directory.")
            return None
    except Exception as e:
        st.error(f"Error loading branch data: {e}")
        return None

# Utility Functions
def clean_df(df):
    df = df.loc[:, ~df.columns.str.contains("^Unnamed")]
    df.columns = df.columns.str.strip()
    df = df.replace({None:"", "None":""}).fillna("")
    return df

def format_number_with_commas(x):
    """Format number with commas and return empty string if NaN/None"""
    try:
        if pd.isna(x) or x == "" or x is None:
            return ""
        if isinstance(x, str):
            x = x.replace(',', '')
            x = float(x) if x else np.nan
        if pd.isna(x):
            return ""
        x = round(x)
        return f"{x:,.0f}"
    except:
        return ""

def format_mos_with_decimals(x):
    """Format MOS with 2 decimals and return empty string if NaN/None"""
    try:
        if pd.isna(x) or x == "" or x is None:
            return ""
        if isinstance(x, str):
            x = float(x) if x else np.nan
        if pd.isna(x):
            return ""
        return f"{x:.2f}"
    except:
        return ""

def format_percentage(x):
    """Format percentage with 1 decimal"""
    try:
        if pd.isna(x) or x == "" or x is None:
            return "0.0%"
        return f"{float(x):.1f}%"
    except:
        return "0.0%"

def categorize_stock(nmos):
    try:
        x = float(nmos) if pd.notna(nmos) else np.nan
        if pd.isna(x):
            return ""
        if x < 1:
            return "Stock Out"
        elif x < 6:
            return "Understock"
        elif x <= 18:
            return "Normal Stock"
        else:
            return "Overstock"
    except:
        return ""

def safe_convert_to_numeric(series):
    """Safely convert series to numeric, handling datetime objects"""
    try:
        if pd.api.types.is_datetime64_any_dtype(series):
            return series
        return pd.to_numeric(series, errors='coerce')
    except:
        return series

def wrap_text(text, width=30):
    """Wrap text to specified width"""
    if pd.isna(text) or text == "":
        return ""
    text = str(text)
    words = text.split()
    lines = []
    current_line = []
    current_length = 0

    for word in words:
        if current_length + len(word) + 1 <= width:
            current_line.append(word)
            current_length += len(word) + 1
        else:
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [word]
            current_length = len(word)

    if current_line:
        lines.append(' '.join(current_line))

    return '<br>'.join(lines)

def calculate_coefficient_of_variation(values):
    """Calculate coefficient of variation (CV = std/mean * 100)"""
    try:
        values = pd.to_numeric(values, errors='coerce')
        values = values[values.notna() & (values > 0)]
        if len(values) > 1:
            mean = values.mean()
            std = values.std()
            if mean > 0:
                return (std / mean) * 100
        return np.nan
    except:
        return np.nan

# Load data
sheet_id = "14VvZ7IyOmpM4SZrY5_ArHDgLkeFN4inW"
google_sheets = load_google(sheet_id)

external_path = "./Hp_medicines_Stock_Final.xlsx"
df_external = load_external(external_path)

if df_external.empty:
    st.error("External Excel contains no valid data.")
    st.stop()

# Load branch data from current directory
branch_filename = "Branch_Health Program_AMC .xlsx"  # Name of the file in current directory
cf = load_branch_data(branch_filename)

# ---------------------------------------------------
# Program Selection (First filter in sidebar)
# ---------------------------------------------------
program_list = ["All"] + list(google_sheets.keys())
sheet_name = st.sidebar.selectbox("Program", program_list, index=0)

if sheet_name == "All":
    all_dfs = []
    for name, df_program in google_sheets.items():
        df_program = df_program.copy()
        all_dfs.append(df_program)
    df_google = pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()
else:
    df_google = google_sheets[sheet_name]

# ---------------------------------------------------
# Required Columns
# ---------------------------------------------------
required_cols = [
    'Material Description', 'AMC',
    'GIT_PO', 'GIT_Qty', 'GIT_MOS',
    'LC_PO', 'LC_Qty', 'LC_MOS',
    'WB_PO', 'WB_Qty', 'WB_MOS',
    'TMD_PO', 'TMD_Qty', 'TMD_MOS', "Status"
]
df_google = df_google[[c for c in required_cols if c in df_google.columns]]

# ---------------------------------------------------
# Merge and process data
# ---------------------------------------------------
df = df_external.merge(df_google, on="Material Description", how="right")
if 'S/N' in df.columns:
    df = df.drop(columns=['S/N'])
df = df.set_index("Material Description")

# Preserve Status and Expiry columns as text
if 'Status' in df.columns:
    status_values = df['Status'].copy()
else:
    status_values = None

if 'Expiry' in df.columns:
    expiry_values = df['Expiry'].copy()
else:
    expiry_values = None

# Convert numeric columns
text_columns = ['Status', 'Expiry']
for col in df.columns:
    if col not in text_columns:
        try:
            df[col] = safe_convert_to_numeric(df[col])
        except:
            pass

# Restore text columns
if status_values is not None:
    df['Status'] = status_values
if expiry_values is not None:
    df['Expiry'] = expiry_values

# Calculate NMOS if not present
if 'NSOH' in df.columns and 'AMC' in df.columns:
    nsoh = df['NSOH']
    amc = df['AMC']
    nmos = np.where(amc != 0, nsoh / amc, np.nan)
    df['NMOS'] = pd.Series(nmos, index=df.index)

# Calculate TMOS
mos_cols = ['NMOS', 'GIT_MOS', 'LC_MOS', 'WB_MOS', 'TMD_MOS']
available_mos = [c for c in mos_cols if c in df.columns]
if available_mos:
    df['TMOS'] = df[available_mos].sum(axis=1)

# Stock Status
df = df.reset_index()
df['Stock Status'] = df['NMOS'].apply(categorize_stock)

# Calculate Hubs% and Head Office%
if 'Hubs' in df.columns and 'Head Office' in df.columns and 'NSOH' in df.columns:
    hubs_vals = pd.to_numeric(df['Hubs'], errors='coerce').fillna(0)
    ho_vals = pd.to_numeric(df['Head Office'], errors='coerce').fillna(0)
    nsoh_vals = pd.to_numeric(df['NSOH'], errors='coerce')

    valid_mask = nsoh_vals.notna() & (nsoh_vals > 0)

    df['Hubs%'] = np.where(valid_mask, (hubs_vals / nsoh_vals * 100).round(1), np.nan)
    df['Head Office%'] = np.where(valid_mask, (ho_vals / nsoh_vals * 100).round(1), np.nan)

# Risk of Stock calculation
def calculate_risk(row):
    try:
        nmos = row['NMOS'] if pd.notna(row['NMOS']) else np.nan
        git_mos = row['GIT_MOS'] if pd.notna(row['GIT_MOS']) else 0
        lc_mos = row['LC_MOS'] if pd.notna(row['LC_MOS']) else 0
        wb_mos = row['WB_MOS'] if pd.notna(row['WB_MOS']) else 0
        tmd_mos = row['TMD_MOS'] if pd.notna(row['TMD_MOS']) else 0

        if pd.notna(nmos) and nmos > 1:
            if nmos < 4 and git_mos == 0:
                return "Risk of Stock out"
            elif nmos < 6 and git_mos == 0 and lc_mos == 0 and wb_mos == 0:
                return "Risk of Stock out"
            elif nmos < 7 and git_mos == 0 and lc_mos == 0 and wb_mos == 0 and tmd_mos == 0:
                return "Risk of Stock out"
        return ""
    except:
        return ""

df['Risk of Stock'] = df.apply(calculate_risk, axis=1)

# Create formatted display version
display_df = df.copy()
text_columns_to_preserve = ['Material Description', 'Stock Status', 'Risk of Stock', 'Status', 'Expiry', 'Hubs%', 'Head Office%']

for col in display_df.columns:
    if col not in text_columns_to_preserve:
        if col in ['NMOS', 'GIT_MOS', 'LC_MOS', 'WB_MOS', 'TMD_MOS', 'TMOS']:
            display_df[col] = display_df[col].apply(format_mos_with_decimals)
        else:
            display_df[col] = display_df[col].apply(format_number_with_commas)

# ---------------------------------------------------
# Additional Filters (After Program selection)
# ---------------------------------------------------
materials = ["All"] + sorted(df['Material Description'].astype(str).unique())
status_values = [s for s in df['Stock Status'].unique() if s != "" and pd.notna(s)]
statuses = ["All"] + sorted(status_values)
risk_filter_options = ["All", "Risk of Stock out"]

material_filter = st.sidebar.selectbox("Material Description", materials)
status_filter = st.sidebar.selectbox("Stock Status", statuses)
risk_filter = st.sidebar.selectbox("Risk of Stock", risk_filter_options)

# Apply filters
df_filtered = df.copy()
display_df_filtered = display_df.copy()

if material_filter != "All":
    df_filtered = df_filtered[df_filtered['Material Description'] == material_filter]
    display_df_filtered = display_df_filtered[display_df_filtered['Material Description'] == material_filter]
if status_filter != "All":
    df_filtered = df_filtered[df_filtered['Stock Status'] == status_filter]
    display_df_filtered = display_df_filtered[display_df_filtered['Stock Status'] == status_filter]
if risk_filter != "All":
    df_filtered = df_filtered[df_filtered['Risk of Stock'] == risk_filter]
    display_df_filtered = display_df_filtered[display_df_filtered['Risk of Stock'] == risk_filter]

# ---------------------------------------------------
# Navigation and Logout (Below filters in sidebar)
# ---------------------------------------------------
st.sidebar.divider()

# Show navigation options
if st.session_state['user']['role'] == 'admin':
    page = st.sidebar.radio("Navigation", ["Dashboard", "Admin Panel", "Profile"])
else:
    page = st.sidebar.radio("Navigation", ["Dashboard", "Profile"])

st.sidebar.divider()
if st.sidebar.button("🚪 Logout", use_container_width=True):
    st.session_state['auth'] = False
    st.session_state['user'] = None
    st.rerun()

# ---------------------------------------------------
# Route to different pages
# ---------------------------------------------------
if page == "Profile":
    show_profile_page()
    st.stop()
elif page == "Admin Panel" and st.session_state['user']['role'] == 'admin':
    show_admin_panel()
    st.stop()

# ---------------------------------------------------
# MAIN DASHBOARD
# ---------------------------------------------------
st.markdown("<h1 style='font-size: 32px; font-weight: bold; font-family: Times New Roman;'>Health Program Medicines Dashboard</h1>", unsafe_allow_html=True)

# ---------------------------------------------------
# Initialize session state for recommendations and heatmap page
# ---------------------------------------------------
if 'recommendations' not in st.session_state:
    st.session_state.recommendations = {}

if 'heatmap_page' not in st.session_state:
    st.session_state.heatmap_page = 1

# ---------------------------------------------------
# Tabs
# ---------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 **STOCK STATUS TABLE**", 
    "📈 **STOCK STATUS KPI**", 
    "⚠️ **DECISION BRIEFS**", 
    "🗺️ **EPSS HUBS DISTRIBUTION PATTERN**"
])

# ---------------------------------------------------
# TAB 1 TABLE
# ---------------------------------------------------
with tab1:
    st.markdown("<h3 style='font-size: 28px; font-weight: bold; font-family: Times New Roman;'>Complete Stock Status Table</h3>", unsafe_allow_html=True)

    # Reorder columns
    cols = list(display_df_filtered.columns)
    if 'NMOS' in cols and 'AMC' in cols:
        cols.insert(cols.index('AMC') + 1, cols.pop(cols.index('NMOS')))
    if 'Risk of Stock' in cols and 'Stock Status' in cols:
        cols.insert(cols.index('Stock Status') + 1, cols.pop(cols.index('Risk of Stock')))
    display_df_filtered = display_df_filtered[cols]

    def color_row(row):
        colors = {
            "Stock Out": "background-color:red;color:white",
            "Understock": "background-color:yellow",
            "Normal Stock": "background-color:green;color:white",
            "Overstock": "background-color:skyblue"
        }
        styles = [''] * len(row)
        for i, col in enumerate(row.index):
            if col == 'Material Description':
                styles[i] = colors.get(row['Stock Status'], '')
                break
        return styles

    styled = display_df_filtered.style.apply(color_row, axis=1)

    column_config = {
        "Material Description": st.column_config.TextColumn(
            "Material Description",
            width=300,
            pinned=True,
            help="Material name (frozen column)"
        )
    }

    st.dataframe(
        styled,
        column_config=column_config,
        use_container_width=True,
        hide_index=True,
        height=(len(display_df_filtered) + 1) * 35
    )

# ---------------------------------------------------
# TAB 2 KPIs & Charts
# ---------------------------------------------------
with tab2:
    st.markdown("<h3 style='font-size: 28px; font-weight: bold; font-family: Times New Roman;'>Key Performance Indicators</h3>", unsafe_allow_html=True)

    # KPI Gauges
    nmos_values = pd.to_numeric(df_filtered['NMOS'], errors='coerce').dropna()
    availability = (nmos_values > 1).mean() * 100 if len(nmos_values) > 0 else 0
    sap = ((nmos_values >= 6) & (nmos_values <= 18)).mean() * 100 if len(nmos_values) > 0 else 0

    # Calculate average Hubs% and Head Office%
    if 'Hubs%' in df_filtered.columns:
        hubs_pct_values = pd.to_numeric(df_filtered['Hubs%'], errors='coerce').dropna()
        avg_hubs_pct = hubs_pct_values.mean() if len(hubs_pct_values) > 0 else 0
    else:
        avg_hubs_pct = 0

    if 'Head Office%' in df_filtered.columns:
        ho_pct_values = pd.to_numeric(df_filtered['Head Office%'], errors='coerce').dropna()
        avg_ho_pct = ho_pct_values.mean() if len(ho_pct_values) > 0 else 0
    else:
        avg_ho_pct = 0

    availability_target = 100
    sap_target = 65

    # Display 4 KPI gauges
    col1, col2 = st.columns(2)
    col3, col4 = st.columns(2)

    def create_kpi_fig(value, target, title, suffix="%"):
        display_color = 'red' if value < target else 'black'
        return go.Figure(go.Indicator(
            mode="gauge+number",
            value=value,
            number={'suffix': suffix, 'font': {'size': 36, 'color': display_color, 'family': 'Times New Roman', 'weight': 'bold'}},
            title={'text': f"<b>{title}</b>", 'font': {'size': 24, 'family': 'Times New Roman', 'weight': 'bold'}},
            gauge={'axis': {'range': [0, 100]}, 'bar': {'color': 'skyblue'}, 'bgcolor': "lightgray", 'borderwidth': 2, 'bordercolor': "gray"}
        ))

    with col1:
        st.plotly_chart(create_kpi_fig(availability, availability_target, "Availability"), use_container_width=True)
    with col2:
        st.plotly_chart(create_kpi_fig(sap, sap_target, "SAP"), use_container_width=True)
    with col3:
        st.plotly_chart(create_kpi_fig(avg_hubs_pct, 50, "Avg Hubs %"), use_container_width=True)
    with col4:
        st.plotly_chart(create_kpi_fig(avg_ho_pct, 50, "Avg Head Office %"), use_container_width=True)

    # Pie Chart
    try:
        status_counts = df_filtered['Stock Status'].replace("", np.nan).dropna().value_counts()
        status_counts = status_counts.astype(int)
        if not status_counts.empty:
            total_count = status_counts.sum()

            if sheet_name == "All":
                pie_title = "<b>Stock Status - All Programs (Medicines)</b>"
            else:
                pie_title = f"<b>Stock Status - {sheet_name} (Medicines)</b>"

            fig = px.pie(
                values=status_counts.values,
                names=status_counts.index.astype(str),
                hole=0.5,
                color=status_counts.index.astype(str),
                color_discrete_map={"Stock Out": "red", "Understock": "yellow", "Normal Stock": "green", "Overstock": "skyblue"},
            )
            fig.update_traces(textposition='inside', textinfo='percent+value', insidetextfont={'size': 16, 'color': 'black', 'family': 'Times New Roman'})
            fig.add_annotation(dict(text=f"Total:<br>{total_count}", x=0.5, y=0.5, showarrow=False, font_size=20, font_color='black', font_family='Times New Roman'))
            fig.update_layout(
                title={'text': pie_title, 'x': 0.5, 'xanchor': 'center', 'font': {'size': 28, 'family': 'Times New Roman', 'weight': 'bold'}},
                legend_title_text='Status',
                legend={'font': {'size': 14, 'family': 'Times New Roman'}}
            )
            st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Pie chart could not be displayed: {e}")

    # MOS Horizontal Bar Chart
    try:
        mos_cols_chart = ['Material Description', 'NMOS', 'GIT_MOS', 'LC_MOS', 'WB_MOS', 'TMD_MOS', 'TMOS']
        available_cols = [c for c in mos_cols_chart if c in df_filtered.columns]
        mos_df = df_filtered[available_cols].copy()
        mos_df = mos_df[mos_df['NMOS'].notna()]
        if not mos_df.empty:
            for c in ['NMOS', 'GIT_MOS', 'LC_MOS', 'WB_MOS', 'TMD_MOS', 'TMOS']:
                if c in mos_df.columns:
                    mos_df[c] = pd.to_numeric(mos_df[c], errors='coerce').fillna(0)

            mos_df = mos_df.sort_values('NMOS', ascending=True).reset_index(drop=True)

            split_len = 40
            mos_df['Material_split'] = mos_df['Material Description'].apply(
                lambda x: '<br>'.join([str(x)[i:i + split_len] for i in range(0, len(str(x)), split_len)])
            )

            mos_df['NMOS_color'] = mos_df['NMOS'].apply(lambda x: "red" if x < 1 else "yellow" if x < 6 else "green" if x <= 18 else "skyblue")

            split_size = 10
            for i in range(0, len(mos_df), split_size):
                df_chunk = mos_df.iloc[i:i + split_size]
                fig = go.Figure()

                fig.add_trace(go.Bar(
                    y=df_chunk['Material_split'],
                    x=df_chunk['NMOS'],
                    name='NMOS',
                    orientation='h',
                    marker=dict(color=df_chunk['NMOS_color']),
                    text=df_chunk['NMOS'].apply(lambda x: f"{x:.1f}"),
                    textposition='inside'
                ))

                for col, color, label in [('GIT_MOS', 'cyan', 'GIT MOS'), ('LC_MOS', 'plum', 'LC MOS'),
                                          ('WB_MOS', 'gray', 'WB MOS'), ('TMD_MOS', 'orange', 'TMD MOS')]:
                    if col in df_chunk.columns:
                        fig.add_trace(go.Bar(
                            y=df_chunk['Material_split'],
                            x=df_chunk[col],
                            name=label,
                            orientation='h',
                            marker_color=color,
                            text=df_chunk[col].apply(lambda x: f"{x:.1f}"),
                            textposition='inside'
                        ))

                fig.add_trace(go.Scatter(
                    y=df_chunk['Material_split'],
                    x=df_chunk['TMOS'],
                    mode='text',
                    text=df_chunk['TMOS'].apply(lambda x: f"TMOS: {x:.2f}"),
                    textposition='middle right',
                    showlegend=False
                ))

                if sheet_name == "All":
                    chart_title = f'<b>National and Pipeline Stock Status - All Programs (Medicines {i + 1}-{i + len(df_chunk)})</b>'
                else:
                    chart_title = f'<b>National and Pipeline Stock Status - {sheet_name} (Medicines {i + 1}-{i + len(df_chunk)})</b>'

                fig.update_layout(
                    barmode='stack',
                    title={'text': chart_title,
                           'x': 0.5, 'xanchor': 'center', 'font': {'size': 28, 'family': 'Times New Roman', 'weight': 'bold'}},
                    xaxis_title='Months of Stock',
                    yaxis_title='Material Description',
                    xaxis={'title_font': {'family': 'Times New Roman', 'size': 16}, 'tickfont': {'family': 'Times New Roman', 'size': 14}},
                    yaxis={'title_font': {'family': 'Times New Roman', 'size': 16}, 'tickfont': {'family': 'Times New Roman', 'size': 12}, 'autorange': "reversed"},
                    height=max(500, 35 * len(df_chunk)),
                    legend_title='MOS Type',
                    legend={'font': {'family': 'Times New Roman', 'size': 14}}
                )
                st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"MOS bar chart could not be displayed: {e}")

    # Stacked Bar Chart: Hubs vs Head Office
    try:
        if 'Hubs' in df_filtered.columns and 'Head Office' in df_filtered.columns and 'NSOH' in df_filtered.columns:
            hubs_vals = pd.to_numeric(df_filtered['Hubs'], errors='coerce').fillna(0)
            ho_vals = pd.to_numeric(df_filtered['Head Office'], errors='coerce').fillna(0)
            nsoh_vals = pd.to_numeric(df_filtered['NSOH'], errors='coerce')

            valid_nsoh_mask = nsoh_vals.notna() & (nsoh_vals > 0)

            if valid_nsoh_mask.any():
                valid_indices = valid_nsoh_mask[valid_nsoh_mask].index

                hubs_vals_valid = hubs_vals[valid_indices]
                ho_vals_valid = ho_vals[valid_indices]
                nsoh_vals_valid = nsoh_vals[valid_indices]
                materials_valid = df_filtered.loc[valid_indices, 'Material Description']

                hubs_pct = (hubs_vals_valid / nsoh_vals_valid * 100).fillna(0)
                ho_pct = (ho_vals_valid / nsoh_vals_valid * 100).fillna(0)

                nsoh_formatted = nsoh_vals_valid.apply(lambda x: f"{x:,.0f}")

                bar_df = pd.DataFrame({
                    'Material Description': materials_valid,
                    'Hubs%': hubs_pct,
                    'Head Office%': ho_pct,
                    'NSOH_actual': nsoh_vals_valid,
                    'NSOH_display': nsoh_formatted
                }).reset_index(drop=True)

                bar_df = bar_df.sort_values('Hubs%')
                bar_df['Material_split'] = bar_df['Material Description'].apply(
                    lambda x: '<br>'.join([str(x)[i:i + 25] for i in range(0, len(str(x)), 25)])
                )

                n = 11
                for i in range(0, len(bar_df), n):
                    df_chunk = bar_df.iloc[i:i + n]

                    fig_bar = go.Figure()

                    fig_bar.add_trace(go.Bar(
                        y=df_chunk['Material_split'],
                        x=df_chunk['Hubs%'],
                        name='Hubs%',
                        orientation='h',
                        marker_color='skyblue',
                        text=df_chunk['Hubs%'].apply(lambda x: f"{x:.1f}%" if x > 0 else ""),
                        textposition='inside',
                        textfont=dict(size=12, family='Times New Roman')
                    ))

                    fig_bar.add_trace(go.Bar(
                        y=df_chunk['Material_split'],
                        x=df_chunk['Head Office%'],
                        name='Head Office%',
                        orientation='h',
                        marker_color='orange',
                        text=df_chunk['Head Office%'].apply(lambda x: f"{x:.1f}%" if x > 0 else ""),
                        textposition='inside',
                        textfont=dict(size=12, family='Times New Roman')
                    ))

                    for idx, row in df_chunk.iterrows():
                        total_pct = row['Hubs%'] + row['Head Office%']

                        fig_bar.add_annotation(
                            x=total_pct + 2,
                            y=row['Material_split'],
                            text=f"NSOH: {row['NSOH_display']}",
                            showarrow=False,
                            font=dict(size=12, color="black", family='Times New Roman'),
                            xanchor='left',
                            yanchor='middle'
                        )

                    fig_bar.update_layout(
                        barmode='stack',
                        title={'text': f'Stock Distribution Hubs vs Head Office (Materials - {i + 1} to {i + len(df_chunk)})',
                               'x': 0.5, 'xanchor': 'center', 'font': {'size': 28, 'family': 'Times New Roman', 'weight': 'bold'}},
                        xaxis_title='Percentage of NSOH (%)',
                        yaxis_title='Material Description',
                        xaxis={'title_font': {'family': 'Times New Roman', 'size': 16}, 'tickfont': {'family': 'Times New Roman', 'size': 14}, 'range': [0, 120]},
                        yaxis={'title_font': {'family': 'Times New Roman', 'size': 16}, 'tickfont': {'family': 'Times New Roman', 'size': 12}, 'categoryorder': 'total ascending'},
                        legend_title='Location',
                        legend={'font': {'family': 'Times New Roman', 'size': 14}},
                        height=max(600, 40 * len(df_chunk)),
                        margin=dict(r=150)
                    )

                    st.plotly_chart(fig_bar, use_container_width=True)
            else:
                st.info("No materials with valid NSOH (>0) to display in the stacked bar chart.")
    except Exception as e:
        st.error(f"Stacked bar chart could not be displayed: {e}")

# ---------------------------------------------------
# TAB 3 - Decision Briefs
# ---------------------------------------------------
with tab3:
    if sheet_name == "All":
        st.markdown("<h3 style='font-size: 28px; font-weight: bold; font-family: Times New Roman;'>All Programs - Medicines Needing Immediate Action</h3>", unsafe_allow_html=True)
    else:
        st.markdown(f"<h3 style='font-size: 28px; font-weight: bold; font-family: Times New Roman;'>{sheet_name} Medicines Needing Immediate Action</h3>", unsafe_allow_html=True)

    st.markdown("<h4 style='font-size: 24px; font-weight: bold; font-family: Times New Roman;'>Quick Summary</h4>", unsafe_allow_html=True)

    decision_cols = ['Material Description', 'NSOH', 'Expiry', 'AMC', 'NMOS', 'Status']
    available_decision_cols = [col for col in decision_cols if col in display_df_filtered.columns]

    if available_decision_cols:
        decision_df = display_df_filtered[available_decision_cols].copy()
        decision_df['Identified Problems'] = ''

        for idx, row in df_filtered.iterrows():
            problems = []
            if row['Stock Status'] == 'Stock Out':
                problems.append('Stock Out')
            if row['Risk of Stock'] == 'Risk of Stock out':
                problems.append('Risk of Stock out')

            if problems:
                decision_df.at[idx, 'Identified Problems'] = ', '.join(problems)

        decision_df = decision_df[decision_df['Identified Problems'] != ''].copy()

        if len(decision_df) > 0:
            decision_df['Priority'] = decision_df['Identified Problems'].apply(
                lambda x: 1 if 'Stock Out' in x else 2
            )
            decision_df = decision_df.sort_values('Priority').drop(columns=['Priority'])
            decision_df = decision_df.reset_index(drop=True)

            col1, col2, col3 = st.columns(3)
            with col1:
                items_with_problems = len(decision_df)
                st.metric("Items with Problems", items_with_problems)
            with col2:
                stock_out_count = len(decision_df[decision_df['Identified Problems'].str.contains(r'\bStock Out\b', na=False, regex=True)])
                st.metric("Stock Out Items", stock_out_count)
            with col3:
                risk_count = len(decision_df[decision_df['Identified Problems'].str.contains(r'\bRisk of Stock out\b', na=False, regex=True)])
                st.metric("Items at Risk of Stock Out", risk_count)

            st.markdown("---")

            decision_df['Recommendation'] = ''

            column_config = {
                "Material Description": st.column_config.TextColumn(
                    "Material Description",
                    width=300,
                    disabled=True,
                    pinned=True,
                    help="Material name (frozen column)"
                ),
                "NSOH": st.column_config.TextColumn(
                    "NSOH",
                    width=100,
                    disabled=True
                ),
                "Expiry": st.column_config.TextColumn(
                    "Expiry",
                    width=100,
                    disabled=True,
                    help="Expiry date (as text)"
                ),
                "AMC": st.column_config.TextColumn(
                    "AMC",
                    width=100,
                    disabled=True
                ),
                "NMOS": st.column_config.TextColumn(
                    "NMOS",
                    width=100,
                    disabled=True
                ),
                "Status": st.column_config.TextColumn(
                    "Status",
                    width=120,
                    disabled=True
                ),
                "Identified Problems": st.column_config.TextColumn(
                    "Identified Problems",
                    width=250,
                    disabled=True,
                    help="Issues identified with this material"
                ),
                "Recommendation": st.column_config.TextColumn(
                    "Recommendation",
                    width=350,
                    required=False,
                    help="Double-click to add/edit recommendation"
                )
            }

            edited_result = st.data_editor(
                decision_df,
                column_config=column_config,
                use_container_width=False,
                hide_index=True,
                height=(len(decision_df) + 1) * 35,
                num_rows="fixed"
            )

            if 'saved_recommendations' not in st.session_state:
                st.session_state.saved_recommendations = {}

            for idx, row in edited_result.iterrows():
                material = row['Material Description']
                st.session_state.saved_recommendations[material] = row['Recommendation']

            st.download_button(
                label="Download Decision Briefs with Recommendations",
                data=edited_result.to_csv(index=False),
                file_name=f"{sheet_name}_decision_briefs.csv".replace(" ", "_"),
                mime="text/csv"
            )

            if st.button("Clear All Recommendations"):
                st.session_state.saved_recommendations = {}
                st.rerun()
        else:
            if sheet_name == "All":
                st.info("No medicines with identified problems across all programs.")
            else:
                st.info(f"No {sheet_name} medicines with identified problems to display.")
    else:
        st.warning("Required columns for Decision Briefs not found in the data.")

# ---------------------------------------------------
# TAB 4 - Hubs Distribution Pattern
# ---------------------------------------------------
with tab4:
    try:
        # Use the cf data loaded from current directory
        main_df = df.copy()

        if cf is not None and 'Material Description' in main_df.columns and 'Material Description' in cf.columns:
            gh = main_df.iloc[:, 0:20].copy()

            st.markdown("<h4 style='font-size: 24px; font-weight: bold; font-family: Times New Roman;'>Stock Distribution Across Hubs by MOS</h4>", unsafe_allow_html=True)

            merged_df = pd.merge(
                gh,
                cf,
                on='Material Description',
                how='inner',
                suffixes=('_gh', '_cf')
            )

            if not merged_df.empty:
                gh_cols = [col for col in gh.columns if col != 'Material Description']
                cf_cols = [col for col in cf.columns if col != 'Material Description']

                division_data = {'Material Description': merged_df['Material Description']}

                branch_name_map = {
                    'Addis Ababa Branch 1': 'Addis Ababa 1',
                    'Addis Ababa Branch 2': 'Addis Ababa 2',
                    'Adama Branch': 'Adama',
                    'Bahir Dar Branch': 'Bahir Dar',
                    'Mekelle Branch': 'Mekelle',
                    'Hawassa Branch': 'Hawassa',
                    'Dire Dawa Branch': 'Dire Dawa',
                    'Jimma Branch': 'Jimma',
                    'Gondar Branch': 'Gondar',
                    'Dessie Branch': 'Dessie'
                }

                min_cols = min(len(gh_cols), len(cf_cols))

                for i in range(min_cols):
                    gh_col = gh_cols[i]
                    cf_col = cf_cols[i]

                    display_col_name = gh_col
                    for full_name, short_name in branch_name_map.items():
                        if full_name in gh_col:
                            display_col_name = short_name
                            break

                    gh_values = pd.to_numeric(merged_df[f"{gh_col}_gh"], errors='coerce')
                    cf_values = pd.to_numeric(merged_df[f"{cf_col}_cf"], errors='coerce')

                    with np.errstate(divide='ignore', invalid='ignore'):
                        division_result = np.where(
                            cf_values != 0,
                            gh_values / cf_values,
                            np.nan
                        )

                    division_data[display_col_name] = division_result

                division_df = pd.DataFrame(division_data)
                division_df = division_df.replace([np.inf, -np.inf], np.nan).round(2)

                # Calculate Coefficient of Variation for each material
                if division_df.shape[1] > 1:
                    branch_cols = [col for col in division_df.columns if col != 'Material Description']
                    division_df['CV (%)'] = division_df[branch_cols].apply(
                        lambda row: calculate_coefficient_of_variation(row), axis=1
                    )
                    division_df['CV (%)'] = division_df['CV (%)'].round(1)

                    # Reorder columns to put CV after Material Description
                    cols = ['Material Description', 'CV (%)'] + branch_cols
                    division_df = division_df[cols]

                    # Categorize CV values
                    def categorize_cv(cv_value):
                        if pd.isna(cv_value):
                            return "Unknown"
                        elif cv_value < 50:
                            return "Low variation"
                        elif cv_value <= 100:
                            return "Moderate variation"
                        else:
                            return "High variation"

                    division_df['CV Category'] = division_df['CV (%)'].apply(categorize_cv)

                    # Count materials in each category
                    cv_counts = division_df['CV Category'].value_counts()

                    # Display metrics in columns
                    col1, col2, col3, col4 = st.columns(4)

                    with col1:
                        total_materials = len(division_df)
                        st.metric("Total Materials", total_materials)

                    if 'Low variation' in cv_counts:
                        with col2:
                            low_count = cv_counts['Low variation']
                            low_pct = (low_count / total_materials * 100) if total_materials > 0 else 0
                            st.metric("Low Variation (<50%)", f"{low_count} ({low_pct:.1f}%)")

                    if 'Moderate variation' in cv_counts:
                        with col3:
                            mod_count = cv_counts['Moderate variation']
                            mod_pct = (mod_count / total_materials * 100) if total_materials > 0 else 0
                            st.metric("Moderate Variation (50-100%)", f"{mod_count} ({mod_pct:.1f}%)")

                    if 'High variation' in cv_counts:
                        with col4:
                            high_count = cv_counts['High variation']
                            high_pct = (high_count / total_materials * 100) if total_materials > 0 else 0
                            st.metric("High Variation (>100%)", f"{high_count} ({high_pct:.1f}%)")

                    # HEATMAP
                    if division_df.shape[1] > 2:
                        branch_cols = [col for col in division_df.columns if col not in ['Material Description', 'CV (%)', 'CV Category']]

                        heatmap_df = division_df.copy()
                        heatmap_df = heatmap_df.sort_values('Material Description')

                        heatmap_df_indexed = heatmap_df.set_index('Material Description')
                        heatmap_df_indexed = heatmap_df_indexed[branch_cols]
                        heatmap_df_transposed = heatmap_df_indexed.T

                        total_materials = len(heatmap_df_transposed.columns)
                        materials_per_page = 11

                        if total_materials > materials_per_page:
                            total_pages = (total_materials + materials_per_page - 1) // materials_per_page

                            col1, col2, col3 = st.columns([1, 3, 1])
                            with col1:
                                if st.button("◀ Previous", key="heatmap_prev"):
                                    if st.session_state.heatmap_page > 1:
                                        st.session_state.heatmap_page -= 1
                                        st.rerun()
                            with col2:
                                st.markdown(f"<h5 style='text-align: center; font-family: Times New Roman;'>Page {st.session_state.heatmap_page} of {total_pages}</h5>", unsafe_allow_html=True)
                            with col3:
                                if st.button("Next ▶", key="heatmap_next"):
                                    if st.session_state.heatmap_page < total_pages:
                                        st.session_state.heatmap_page += 1
                                        st.rerun()

                            start_idx = (st.session_state.heatmap_page - 1) * materials_per_page
                            end_idx = min(start_idx + materials_per_page, total_materials)

                            page_materials = heatmap_df_transposed.columns[start_idx:end_idx]
                            heatmap_page_df = heatmap_df_transposed[page_materials]

                            st.info(f"Showing materials {start_idx + 1} to {end_idx} of {total_materials}")
                        else:
                            heatmap_page_df = heatmap_df_transposed

                        fig = go.Figure(data=go.Heatmap(
                            z=heatmap_page_df.values,
                            y=heatmap_page_df.index,
                            x=heatmap_page_df.columns,
                            colorscale=[
                                [0.0, 'red'],
                                [0.0625, 'red'],
                                [0.125, 'yellow'],
                                [0.25, 'yellow'],
                                [0.5, 'green'],
                                [0.75, 'green'],
                                [1.0, 'skyblue']
                            ],
                            zmin=0,
                            zmax=8,
                            text=heatmap_page_df.values.round(1),
                            texttemplate='%{text}',
                            textfont={"size": 12, "color": "black", "family": "Times New Roman"},
                            colorbar=dict(
                                title=dict(
                                    text="MOS",
                                    side="right",
                                    font=dict(size=12, family="Times New Roman")
                                ),
                                tickvals=[0.5, 1, 2, 4, 6, 8],
                                ticktext=['0.5', '1', '2', '4', '6', '8+'],
                                tickfont=dict(size=12, family="Times New Roman")
                            ),
                            hovertemplate='<b>Material:</b> %{x}<br>' +
                                        '<b>Branch:</b> %{y}<br>' +
                                        '<b>MOS:</b> %{z:.2f} months<br>' +
                                        '<extra></extra>'
                        ))

                        fig.update_layout(
                            xaxis={
                                'title': 'Material Description',
                                'tickangle': -45,
                                'tickfont': {'size': 12, 'family': 'Times New Roman'},
                                'title_font': {'size': 14, 'family': 'Times New Roman', 'weight': 'bold'}
                            },
                            yaxis={
                                'title': 'Branches',
                                'tickfont': {'size': 12, 'family': 'Times New Roman', 'weight': 'bold'},
                                'title_font': {'size': 14, 'family': 'Times New Roman', 'weight': 'bold'},
                                'automargin': True
                            },
                            height=650,
                            width=min(1200, 200 * len(heatmap_page_df.columns)),
                            margin=dict(l=120, r=120, t=50, b=200)
                        )

                        st.plotly_chart(fig, use_container_width=True)

                        st.markdown("#### MOS Thresholds:")
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.markdown("🔴 **< 0.5** : Stock Out")
                        with col2:
                            st.markdown("🟡 **0.5 - 1** : Understock")
                        with col3:
                            st.markdown("🟢 **1 - 4** : Normal Stock")
                        with col4:
                            st.markdown("🔵 **> 4** : Overstock")

                st.markdown("---")
                st.markdown("<h5 style='font-size: 20px; font-weight: bold; font-family: Times New Roman;'>Full Branch MOS Data with CV</h5>", unsafe_allow_html=True)

                # Create a display version with formatted CV
                display_division_df = division_df.copy()
                display_division_df['CV (%)'] = display_division_df['CV (%)'].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "N/A")

                st.dataframe(
                    display_division_df,
                    use_container_width=True,
                    height=400,
                    hide_index=True
                )
                st.caption(f"**Rows:** {division_df.shape[0]} | **Columns:** {division_df.shape[1]}")

                st.download_button(
                    label="Download Hubs MOS with CV",
                    data=division_df.to_csv(index=False),
                    file_name="hubs_mos_distribution_with_cv.csv",
                    mime="text/csv"
                )

                st.markdown("---")
                st.markdown("<h5 style='font-size: 20px; font-weight: bold; font-family: Times New Roman;'>EPSS Hubs SOH</h5>", unsafe_allow_html=True)
                st.dataframe(
                    gh,
                    use_container_width=True,
                    height=400,
                    hide_index=True
                )
                st.caption(f"**Rows:** {gh.shape[0]} | **Columns:** {gh.shape[1]}")

                st.markdown("---")
                st.markdown("<h5 style='font-size: 20px; font-weight: bold; font-family: Times New Roman;'>EPSS Hubs AMC Data</h5>", unsafe_allow_html=True)
                st.dataframe(
                    cf,
                    use_container_width=True,
                    height=400,
                    hide_index=True
                )
                st.caption(f"**Rows:** {cf.shape[0]} | **Columns:** {cf.shape[1]}")
            else:
                st.warning("No matching Material Description found between the two files")
        elif cf is None:
            st.warning(f"Branch data file '{branch_filename}' not found in the application directory.")
            st.info("Please upload the file to the same folder as this application.")

            # Show available data as fallback
            if 'Material Description' in df.columns:
                gh = df[['Material Description'] + df.columns[1:20].tolist()].copy()
                st.markdown("<h5 style='font-size: 20px; font-weight: bold; font-family: Times New Roman;'>Available Hubs SOH Data</h5>", unsafe_allow_html=True)
                st.dataframe(
                    gh,
                    use_container_width=True,
                    height=400,
                    hide_index=True
                )
        else:
            st.error("'Material Description' column not found in one or both dataframes")

    except Exception as e:
        st.error(f"Error processing files: {e}")
        import traceback
        st.code(traceback.format_exc())

# ---------------------------------------------------
# Download Filtered Data
# ---------------------------------------------------
st.divider()
st.download_button(
    label="Download Full Filtered Data",
    data=display_df_filtered.to_csv(index=False),
    file_name=f"full_stock_dashboard_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
    mime="text/csv"
)
