import streamlit as st
import pandas as pd
import numpy as np
import math
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# ---------------------------------------------------
# Page Setup
# ---------------------------------------------------
st.set_page_config(page_title="Health Program Supply Chain Dashboard", layout="wide")

st.title("Health Program Supply Chain Dashboard")

# ---------------------------------------------------
# Utility Functions
# ---------------------------------------------------
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
        # Convert to float first if it's a string
        if isinstance(x, str):
            x = x.replace(',', '')  # Remove existing commas if any
            x = float(x) if x else np.nan
        if pd.isna(x):
            return ""
        # Round to nearest integer for whole numbers
        x = round(x)
        return f"{x:,.0f}"
    except:
        return ""

def format_mos_with_decimals(x):
    """Format MOS with 2 decimals and return empty string if NaN/None"""
    try:
        if pd.isna(x) or x == "" or x is None:
            return ""
        # Convert to float first if it's a string
        if isinstance(x, str):
            x = float(x) if x else np.nan
        if pd.isna(x):
            return ""
        return f"{x:.2f}"
    except:
        return ""

def format_po(col):
    col = pd.to_numeric(col, errors="coerce").round(0)
    return col.apply(lambda x: f"{int(x)}" if pd.notna(x) else "")

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
        # Check if series contains datetime objects
        if pd.api.types.is_datetime64_any_dtype(series):
            return series  # Return as-is for datetime
        return pd.to_numeric(series, errors='coerce')
    except:
        return series

def safe_sort_unique(values):
    """Safely sort unique values, handling mixed types including datetime"""
    try:
        # Convert to list and filter out empty strings
        values_list = [str(v) for v in values if v != "" and pd.notna(v)]
        return sorted(values_list)
    except:
        # If sorting fails, return unsorted list
        return [str(v) for v in values if v != "" and pd.notna(v)]

# ---------------------------------------------------
# Load Google Sheets
# ---------------------------------------------------
@st.cache_data
def load_google(sheet_id):
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
    sheets = pd.read_excel(url, sheet_name=None, header=2)
    return {name: clean_df(df) for name, df in sheets.items()}

# ---------------------------------------------------
# Load External Excel
# ---------------------------------------------------
@st.cache_data(ttl=60)
def load_external(path):
    try:
        df = pd.read_excel(path, header=0)
        return clean_df(df)
    except Exception as e:
        st.error(f"External Excel not found or invalid: {e}")
        return pd.DataFrame()

# ---------------------------------------------------
# Load Data
# ---------------------------------------------------
sheet_id = "14VvZ7IyOmpM4SZrY5_ArHDgLkeFN4inW"
google_sheets = load_google(sheet_id)

external_path = "./Hp_medicines_Stock_Final.xlsx"
df_external = load_external(external_path)

if df_external.empty:
    st.error("External Excel contains no valid data.")
    st.stop()

# ---------------------------------------------------
# Sidebar Program Selection - ADDED "All" option and set as default
# ---------------------------------------------------
program_list = ["All"] + list(google_sheets.keys())
sheet_name = st.sidebar.selectbox("Program", program_list, index=0)  # index=0 makes "All" default

if sheet_name == "All":
    # Combine all programs
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
'Material Description','AMC',
'GIT_PO','GIT_Qty','GIT_MOS',
'LC_PO','LC_Qty','LC_MOS',
'WB_PO','WB_Qty','WB_MOS',
'TMD_PO','TMD_Qty','TMD_MOS',"Status"
]
df_google = df_google[[c for c in required_cols if c in df_google.columns]]

# ---------------------------------------------------
# Merge
# ---------------------------------------------------
df = df_external.merge(df_google, on="Material Description", how="right")
if 'S/N' in df.columns:
    df = df.drop(columns=['S/N'])
df = df.set_index("Material Description")

# ---------------------------------------------------
# Preserve Status and Expiry columns as text
# ---------------------------------------------------
# Store Status values if they exist
if 'Status' in df.columns:
    status_values = df['Status'].copy()
else:
    status_values = None

# Store Expiry values if they exist (keep as original text)
if 'Expiry' in df.columns:
    expiry_values = df['Expiry'].copy()
else:
    expiry_values = None

# ---------------------------------------------------
# Convert only numeric columns (excluding Status, Expiry, and date columns)
# ---------------------------------------------------
# List of columns that should remain as text
text_columns = ['Status', 'Expiry']  # Expiry kept as text

# Convert all other columns to numeric where possible
for col in df.columns:
    if col not in text_columns:
        try:
            df[col] = safe_convert_to_numeric(df[col])
        except:
            # Keep as is if can't convert
            pass

# Restore Status column if it was overwritten
if status_values is not None:
    df['Status'] = status_values

# Restore Expiry column if it was overwritten (keep as original text)
if expiry_values is not None:
    df['Expiry'] = expiry_values

# ---------------------------------------------------
# Calculate NMOS if not present
# ---------------------------------------------------
if 'NSOH' in df.columns and 'AMC' in df.columns:
    nsoh = df['NSOH']
    amc = df['AMC']
    # Avoid division by zero
    nmos = np.where(amc != 0, nsoh / amc, np.nan)
    df['NMOS'] = pd.Series(nmos, index=df.index)

# ---------------------------------------------------
# Calculate TMOS
# ---------------------------------------------------
mos_cols = ['NMOS', 'GIT_MOS', 'LC_MOS', 'WB_MOS', 'TMD_MOS']
available_mos = [c for c in mos_cols if c in df.columns]
if available_mos:
    df['TMOS'] = df[available_mos].sum(axis=1)

# ---------------------------------------------------
# Stock Status
# ---------------------------------------------------
df = df.reset_index()
df['Stock Status'] = df['NMOS'].apply(categorize_stock)

# ---------------------------------------------------
# Risk of Stock (Corrected Logic)
# ---------------------------------------------------
def calculate_risk(row):
    try:
        nmos = row['NMOS'] if pd.notna(row['NMOS']) else np.nan
        git_mos = row['GIT_MOS'] if pd.notna(row['GIT_MOS']) else 0
        lc_mos = row['LC_MOS'] if pd.notna(row['LC_MOS']) else 0
        wb_mos = row['WB_MOS'] if pd.notna(row['WB_MOS']) else 0
        tmd_mos = row['TMD_MOS'] if pd.notna(row['TMD_MOS']) else 0

        # Only consider if NMOS > 1
        if pd.notna(nmos) and nmos > 1:
            # Condition 1: NMOS < 4 and GIT_MOS is zero
            if nmos < 4 and git_mos == 0:
                return "Risk of Stock out"

            # Condition 2: NMOS < 6 and GIT_MOS, LC_MOS, WB_MOS are all zero
            elif nmos < 6 and git_mos == 0 and lc_mos == 0 and wb_mos == 0:
                return "Risk of Stock out"

            # Condition 3: NMOS < 7 and GIT_MOS, LC_MOS, WB_MOS, TMD_MOS are all zero
            elif nmos < 7 and git_mos == 0 and lc_mos == 0 and wb_mos == 0 and tmd_mos == 0:
                return "Risk of Stock out"

        return ""
    except Exception as e:
        return ""

df['Risk of Stock'] = df.apply(calculate_risk, axis=1)

# ---------------------------------------------------
# Create formatted display version of dataframe
# ---------------------------------------------------
display_df = df.copy()

# Define which columns should keep their original text values
text_columns_to_preserve = ['Material Description', 'Stock Status', 'Risk of Stock', 'Status', 'Expiry']

# Format all numeric columns (excluding text columns)
for col in display_df.columns:
    if col not in text_columns_to_preserve:
        if col in ['NMOS', 'GIT_MOS', 'LC_MOS', 'WB_MOS', 'TMD_MOS', 'TMOS']:
            # Format MOS columns with 2 decimals
            display_df[col] = display_df[col].apply(format_mos_with_decimals)
        else:
            # Format other numeric columns with commas
            display_df[col] = display_df[col].apply(format_number_with_commas)

# ---------------------------------------------------
# Sidebar Filters - with safe sorting
# ---------------------------------------------------
materials = ["All"] + sorted(df['Material Description'].astype(str).unique())

# Safely get unique stock statuses
status_values = [s for s in df['Stock Status'].unique() if s != "" and pd.notna(s)]
statuses = ["All"] + sorted(status_values)

risk_filter_options = ["All", "Risk of Stock out"]

# Safely get unique Status text values
if 'Status' in df.columns:
    status_text_values = [str(s) for s in df['Status'].unique() if s != "" and pd.notna(s)]
    status_text_options = ["All"] + sorted(status_text_values)
else:
    status_text_options = ["All"]

material_filter = st.sidebar.selectbox("Material Description", materials)
status_filter = st.sidebar.selectbox("Stock Status", statuses)
risk_filter = st.sidebar.selectbox("Risk of Stock", risk_filter_options)

# Add Status text filter if Status column exists
if 'Status' in df.columns:
    status_text_filter = st.sidebar.selectbox("Status Text", status_text_options)
else:
    status_text_filter = "All"

# Apply filters to both dataframes
df_filtered = df.copy()
display_df_filtered = display_df.copy()

if material_filter != "All":
    df_filtered = df_filtered[df_filtered['Material Description']==material_filter]
    display_df_filtered = display_df_filtered[display_df_filtered['Material Description']==material_filter]
if status_filter != "All":
    df_filtered = df_filtered[df_filtered['Stock Status']==status_filter]
    display_df_filtered = display_df_filtered[display_df_filtered['Stock Status']==status_filter]
if risk_filter != "All":
    df_filtered = df_filtered[df_filtered['Risk of Stock']==risk_filter]
    display_df_filtered = display_df_filtered[display_df_filtered['Risk of Stock']==risk_filter]
if 'Status' in df.columns and status_text_filter != "All":
    df_filtered = df_filtered[df_filtered['Status']==status_text_filter]
    display_df_filtered = display_df_filtered[display_df_filtered['Status']==status_text_filter]

# ---------------------------------------------------
# Initialize session state for recommendations
# ---------------------------------------------------
if 'recommendations' not in st.session_state:
    st.session_state.recommendations = {}

# ---------------------------------------------------
# Tabs
# ---------------------------------------------------
tab1, tab2, tab3 = st.tabs(["Stock Table", "KPIs", "Decision Briefs"])

# ---------------------------------------------------
# TAB 1 TABLE - All columns
# ---------------------------------------------------
with tab1:
    st.subheader("Complete Stock Status Table")

    # Reorder columns
    cols = list(display_df_filtered.columns)
    if 'NMOS' in cols and 'AMC' in cols:
        cols.insert(cols.index('AMC') + 1, cols.pop(cols.index('NMOS')))
    if 'Risk of Stock' in cols and 'Stock Status' in cols:
        cols.insert(cols.index('Stock Status') + 1, cols.pop(cols.index('Risk of Stock')))
    display_df_filtered = display_df_filtered[cols]

    def color_row(row):
        colors = {
            "Stock Out":"background-color:red;color:white",
            "Understock":"background-color:yellow",
            "Normal Stock":"background-color:green;color:white",
            "Overstock":"background-color:skyblue"
        }
        styles=['']*len(row)
        # Find the index of 'Material Description' column
        for i, col in enumerate(row.index):
            if col == 'Material Description':
                styles[i] = colors.get(row['Stock Status'], '')
                break
        return styles

    styled = display_df_filtered.style.apply(color_row, axis=1)

    st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        height=(len(display_df_filtered)+1)*35
    )

# ---------------------------------------------------
# TAB 2 KPIs & Charts
# ---------------------------------------------------
with tab2:
    st.subheader("Key Performance Indicators")

    # --- KPI Gauges ---
    nmos_values = pd.to_numeric(df_filtered['NMOS'], errors='coerce').dropna()
    availability = (nmos_values > 1).mean() * 100 if len(nmos_values) > 0 else 0
    sap = ((nmos_values >= 6) & (nmos_values <= 18)).mean() * 100 if len(nmos_values) > 0 else 0

    availability_target = 100
    sap_target = 65
    col1, col2 = st.columns(2)

    def create_kpi_fig(value, target, title):
        display_color = 'red' if value < target else 'black'
        return go.Figure(go.Indicator(
            mode="gauge+number",
            value=value,
            number={'suffix': "%",'font': {'size': 36, 'color': display_color, 'family': 'Times New Roman', 'weight':'bold'}},
            title={'text': f"<b>{title} KPI</b>",'font': {'size': 24, 'family': 'Times New Roman', 'weight':'bold'}},
            gauge={'axis': {'range':[0,100]}, 'bar': {'color':'skyblue'}, 'bgcolor': "lightgray", 'borderwidth': 2, 'bordercolor': "gray"}
        ))

    with col1:
        st.plotly_chart(create_kpi_fig(availability, availability_target, "Availability"), use_container_width=True)
    with col2:
        st.plotly_chart(create_kpi_fig(sap, sap_target, "SAP"), use_container_width=True)

    # --- Pie Chart ---
    try:
        status_counts = df_filtered['Stock Status'].replace("", np.nan).dropna().value_counts()
        status_counts = status_counts.astype(int)
        if not status_counts.empty:
            total_count = status_counts.sum()
            fig = px.pie(
                values=status_counts.values,
                names=status_counts.index.astype(str),
                hole=0.5,
                color=status_counts.index.astype(str),
                color_discrete_map={"Stock Out":"red","Understock":"yellow","Normal Stock":"green","Overstock":"skyblue"},
            )
            fig.update_traces(textposition='inside', textinfo='percent+value', insidetextfont={'size':16, 'color':'black', 'family':'Times New Roman'})
            fig.add_annotation(dict(text=f"Total:<br>{total_count}", x=0.5, y=0.5, showarrow=False, font_size=20, font_color='black', font_family='Times New Roman'))
            fig.update_layout(title={'text':"<b>Stock Status</b>", 'x':0.5, 'xanchor':'center', 'font':{'size':24, 'family':'Times New Roman'}},
                              legend_title_text='Status', legend={'font':{'size':14, 'family':'Times New Roman'}})
            st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Pie chart could not be displayed: {e}")

    # --- MOS Horizontal Bar Chart (Ascending NMOS) ---
    try:
        mos_cols_chart = ['Material Description','NMOS','GIT_MOS','LC_MOS','WB_MOS','TMD_MOS','TMOS']
        available_cols = [c for c in mos_cols_chart if c in df_filtered.columns]
        mos_df = df_filtered[available_cols].copy()
        mos_df = mos_df[mos_df['NMOS'].notna()]
        if not mos_df.empty:
            for c in ['NMOS','GIT_MOS','LC_MOS','WB_MOS','TMD_MOS','TMOS']:
                if c in mos_df.columns:
                    mos_df[c] = pd.to_numeric(mos_df[c], errors='coerce').fillna(0)

            mos_df = mos_df.sort_values('NMOS', ascending=True).reset_index(drop=True)

            split_len = 40
            mos_df['Material_split'] = mos_df['Material Description'].apply(
                lambda x: '<br>'.join([str(x)[i:i+split_len] for i in range(0, len(str(x)), split_len)])
            )

            mos_df['NMOS_color'] = mos_df['NMOS'].apply(lambda x: "red" if x<1 else "yellow" if x<6 else "green" if x<=18 else "skyblue")

            split_size = 10
            for i in range(0, len(mos_df), split_size):
                df_chunk = mos_df.iloc[i:i+split_size]
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

                for col, color, label in [('GIT_MOS','cyan','GIT MOS'),('LC_MOS','plum','LC MOS'),
                                          ('WB_MOS','gray','WB MOS'),('TMD_MOS','orange','TMD MOS')]:
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

                fig.update_layout(
                    barmode='stack', 
                    title={'text': f'National and Pipeline Stock Status ({i+1}-{i+len(df_chunk)})',
                           'x':0.5, 'xanchor':'center', 'font':{'size':24, 'family':'Times New Roman'}},
                    xaxis_title='Months of Stock', 
                    yaxis_title='Material Description',
                    xaxis={'title_font':{'family':'Times New Roman'}, 'tickfont':{'family':'Times New Roman'}},
                    yaxis={'title_font':{'family':'Times New Roman'}, 'tickfont':{'family':'Times New Roman'}, 'autorange':"reversed"},
                    height=max(500, 35*len(df_chunk)), 
                    legend_title='MOS Type',
                    legend={'font':{'family':'Times New Roman'}}
                )
                st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"MOS bar chart could not be displayed: {e}")

    # --- Stacked Bar Chart: Hubs vs Head Office with NSOH values ---
    try:
        if 'Hubs' in df_filtered.columns and 'Head Office' in df_filtered.columns and 'NSOH' in df_filtered.columns:
            # Convert to numeric
            hubs_vals = pd.to_numeric(df_filtered['Hubs'], errors='coerce').fillna(0)
            ho_vals = pd.to_numeric(df_filtered['Head Office'], errors='coerce').fillna(0)
            nsoh_vals = pd.to_numeric(df_filtered['NSOH'], errors='coerce')

            # Filter only rows where NSOH is not empty and > 0
            valid_nsoh_mask = nsoh_vals.notna() & (nsoh_vals > 0)

            if valid_nsoh_mask.any():  # Only proceed if there are valid NSOH values
                # Apply mask to all relevant data
                valid_indices = valid_nsoh_mask[valid_nsoh_mask].index

                hubs_vals_valid = hubs_vals[valid_indices]
                ho_vals_valid = ho_vals[valid_indices]
                nsoh_vals_valid = nsoh_vals[valid_indices]
                materials_valid = df_filtered.loc[valid_indices, 'Material Description']

                # Calculate percentages
                hubs_pct = (hubs_vals_valid / nsoh_vals_valid * 100).fillna(0)
                ho_pct = (ho_vals_valid / nsoh_vals_valid * 100).fillna(0)

                # Format NSOH with commas
                nsoh_formatted = nsoh_vals_valid.apply(lambda x: f"{x:,.0f}")

                bar_df = pd.DataFrame({
                    'Material Description': materials_valid,
                    'Hubs%': hubs_pct,
                    'Head Office%': ho_pct,
                    'NSOH_actual': nsoh_vals_valid,
                    'NSOH_display': nsoh_formatted
                }).reset_index(drop=True)

                # Sort by Hubs% ascending
                bar_df = bar_df.sort_values('Hubs%')

                # Create wrapped material names for display
                bar_df['Material_split'] = bar_df['Material Description'].apply(
                    lambda x: '<br>'.join([str(x)[i:i+25] for i in range(0, len(str(x)), 25)])
                )

                n = 11
                for i in range(0, len(bar_df), n):
                    df_chunk = bar_df.iloc[i:i+n]

                    # Create the stacked bar chart
                    fig_bar = go.Figure()

                    # Add Hubs% trace
                    fig_bar.add_trace(go.Bar(
                        y=df_chunk['Material_split'], 
                        x=df_chunk['Hubs%'], 
                        name='Hubs%', 
                        orientation='h',
                        marker_color='skyblue', 
                        text=df_chunk['Hubs%'].apply(lambda x: f"{x:.1f}%" if x > 0 else ""), 
                        textposition='inside',
                        textfont=dict(size=10, family='Times New Roman')
                    ))

                    # Add Head Office% trace
                    fig_bar.add_trace(go.Bar(
                        y=df_chunk['Material_split'], 
                        x=df_chunk['Head Office%'], 
                        name='Head Office%', 
                        orientation='h',
                        marker_color='orange', 
                        text=df_chunk['Head Office%'].apply(lambda x: f"{x:.1f}%" if x > 0 else ""), 
                        textposition='inside',
                        textfont=dict(size=10, family='Times New Roman')
                    ))

                    # Add NSOH annotations at the tip of each bar
                    for idx, row in df_chunk.iterrows():
                        # Calculate total percentage (should be near 100)
                        total_pct = row['Hubs%'] + row['Head Office%']

                        # Add NSOH annotation at the end of the bar
                        fig_bar.add_annotation(
                            x=total_pct + 2,  # Position slightly to the right of the bar
                            y=row['Material_split'],
                            text=f"NSOH: {row['NSOH_display']}",
                            showarrow=False,
                            font=dict(size=10, color="black", family='Times New Roman'),
                            xanchor='left',
                            yanchor='middle'
                        )

                    fig_bar.update_layout(
                        barmode='stack',
                        title={'text': f'NSOH Distribution (%) by Hubs vs Head Office (Materials with NSOH > 0 - {i+1} to {i+len(df_chunk)})',
                               'x': 0.5, 'xanchor': 'center', 'font': {'size': 24, 'family': 'Times New Roman'}},
                        xaxis_title='Percentage of NSOH (%)',
                        yaxis_title='Material Description',
                        xaxis={'title_font':{'family':'Times New Roman'}, 'tickfont':{'family':'Times New Roman'}, 'range':[0, 120]},
                        yaxis={'title_font':{'family':'Times New Roman'}, 'tickfont':{'family':'Times New Roman'}, 'categoryorder':'total ascending'},
                        legend_title='Location',
                        legend={'font':{'family':'Times New Roman'}},
                        height=max(600, 40*len(df_chunk)),
                        margin=dict(r=150)  # Add right margin for NSOH text
                    )

                    st.plotly_chart(fig_bar, use_container_width=True)
            else:
                st.info("No materials with valid NSOH (>0) to display in the stacked bar chart.")
    except Exception as e:
        st.error(f"Stacked bar chart could not be displayed: {e}")

# ---------------------------------------------------
# TAB 3 - Decision Briefs (Program-specific title) - FIXED COUNTING
# ---------------------------------------------------
with tab3:
    # Dynamic title with program name
    if sheet_name == "All":
        st.subheader("All Programs - Medicines Needing Immediate Action")
    else:
        st.subheader(f"{sheet_name} Medicines Needing Immediate Action")

    # Quick Summary at the TOP of Decision Briefs
    st.markdown("### Quick Summary")

    # Calculate summary metrics first (need decision_df)
    # Define columns for Decision Briefs
    decision_cols = ['Material Description', 'NSOH', 'Expiry', 'AMC', 'NMOS', 'Status']

    # Check which columns exist
    available_decision_cols = [col for col in decision_cols if col in display_df_filtered.columns]

    if available_decision_cols:
        # Create decision briefs dataframe
        decision_df = display_df_filtered[available_decision_cols].copy()

        # Add Identified Problems column based ONLY on Stock Status and Risk of Stock
        decision_df['Identified Problems'] = ''

        # Populate Identified Problems based ONLY on existing conditions
        for idx, row in df_filtered.iterrows():
            problems = []
            if row['Stock Status'] == 'Stock Out':
                problems.append('Stock Out')
            if row['Risk of Stock'] == 'Risk of Stock out':
                problems.append('Risk of Stock out')

            if problems:
                decision_df.at[idx, 'Identified Problems'] = ', '.join(problems)

        # Filter to show only materials with identified problems
        decision_df = decision_df[decision_df['Identified Problems'] != ''].copy()

        if len(decision_df) > 0:
            # Sort by priority (Stock Out first, then Risk of Stock Out)
            decision_df['Priority'] = decision_df['Identified Problems'].apply(
                lambda x: 1 if 'Stock Out' in x else 2
            )
            decision_df = decision_df.sort_values('Priority').drop(columns=['Priority'])

            # Reset index
            decision_df = decision_df.reset_index(drop=True)

            # Display Quick Summary metrics at the top
            col1, col2, col3 = st.columns(3)

            with col1:
                items_with_problems = len(decision_df)
                st.metric("Items with Problems", items_with_problems)

            with col2:
                # Count items with EXACT 'Stock Out' (not part of 'Risk of Stock Out')
                # Using regex to match whole phrase only
                stock_out_count = len(decision_df[decision_df['Identified Problems'].str.contains(r'\bStock Out\b', na=False, regex=True)])
                st.metric("Stock Out Items", stock_out_count)

            with col3:
                # Count items with EXACT 'Risk of Stock Out' (complete phrase)
                risk_count = len(decision_df[decision_df['Identified Problems'].str.contains(r'\bRisk of Stock out\b', na=False, regex=True)])
                st.metric("Items at Risk of Stock Out", risk_count)

            st.markdown("---")

            # Add empty Recommendation column
            decision_df['Recommendation'] = ''

            # Create an editable dataframe using st.data_editor with fixed column widths
            column_config = {
                "Material Description": st.column_config.TextColumn(
                    "Material Description", 
                    width=300,
                    disabled=True,
                    help="Material name"
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

            # Use data_editor for editable table with fixed column widths
            edited_result = st.data_editor(
                decision_df,
                column_config=column_config,
                use_container_width=False,
                hide_index=True,
                height=(len(decision_df)+1)*35,
                num_rows="fixed"
            )

            # Save recommendations to session state
            if 'saved_recommendations' not in st.session_state:
                st.session_state.saved_recommendations = {}

            # Update session state with edited recommendations
            for idx, row in edited_result.iterrows():
                material = row['Material Description']
                st.session_state.saved_recommendations[material] = row['Recommendation']

            # Export option for Decision Briefs with recommendations
            st.download_button(
                label="Download Decision Briefs with Recommendations",
                data=edited_result.to_csv(index=False),
                file_name=f"{sheet_name}_decision_briefs.csv".replace(" ", "_"),
                mime="text/csv"
            )

            # Button to clear all recommendations
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
# Download Filtered Data (Full Table)
# ---------------------------------------------------
st.divider()
st.download_button(
    label="Download Full Filtered Data", 
    data=display_df_filtered.to_csv(index=False), 
    file_name="full_stock_dashboard.csv", 
    mime="text/csv"
)
