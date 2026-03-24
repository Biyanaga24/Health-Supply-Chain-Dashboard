import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import sys
import os
import time
import requests
from io import BytesIO
from supabase import create_client

# Add the current directory to path
sys.path.append(os.path.dirname(__file__))

# Import authentication functions
from auth import show_login_page, show_profile_page, show_admin_panel

# ---------------------------------------------------
# Supabase Configuration - Using Streamlit Secrets
# ---------------------------------------------------
@st.cache_resource
def init_supabase():
    """Initialize Supabase client using Streamlit secrets"""
    try:
        # Check if secrets are available
        if not hasattr(st, 'secrets') or not st.secrets:
            st.error("Streamlit secrets not found. Please configure your secrets.")
            return None

        # Get credentials from Streamlit secrets
        SUPABASE_URL = st.secrets.get("SUPABASE_URL")
        SUPABASE_KEY = st.secrets.get("SUPABASE_KEY")

        if not SUPABASE_URL or not SUPABASE_KEY:
            st.error("SUPABASE_URL or SUPABASE_KEY not found in secrets. Please check your configuration.")
            return None

        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        return supabase
    except Exception as e:
        st.error(f"Error connecting to Supabase: {e}")
        return None

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
# Initialize session state
# ---------------------------------------------------
if 'data_timestamp' not in st.session_state:
    st.session_state.data_timestamp = datetime.now()
if 'auto_refresh' not in st.session_state:
    st.session_state.auto_refresh = False
if 'recommendations' not in st.session_state:
    st.session_state.recommendations = {}
if 'heatmap_page' not in st.session_state:
    st.session_state.heatmap_page = 1
if 'google_sheets_data' not in st.session_state:
    st.session_state.google_sheets_data = None
if 'supabase_client' not in st.session_state:
    st.session_state.supabase_client = init_supabase()

# ---------------------------------------------------
# Database Connection Functions
# ---------------------------------------------------
def load_national_data():
    """Load national_data from Supabase and map columns to original format (NO CACHING - REAL TIME)"""
    try:
        if st.session_state.supabase_client is None:
            st.error("Supabase client not initialized")
            return pd.DataFrame()

        # Fetch data from Supabase - always fresh
        response = st.session_state.supabase_client.table("health_data").select("*").execute()

        if not response.data:
            st.warning("No data found in Supabase")
            return pd.DataFrame()

        # Convert to DataFrame
        df = pd.DataFrame(response.data)

        # Create comprehensive column mapping from Supabase (lowercase_underscore) to original format
        column_mapping = {
            'material_description': 'Material Description',
            'adama_branch': 'Adama Branch',
            'addis_ababa_branch_1': 'Addis Ababa Branch 1',
            'addis_ababa_branch_2': 'Addis Ababa Branch 2',
            'arba_minch_branch': 'Arba Minch Branch',
            'assosa_branch': 'Assosa Branch',
            'bahir_dar_branch': 'Bahir Dar Branch',
            'dessie_branch': 'Dessie Branch',
            'dire_dawa_branch': 'Dire Dawa Branch',
            'gambela_branch': 'Gambela Branch',
            'gondar_branch': 'Gondar Branch',
            'hawassa_branch': 'Hawassa Branch',
            'jigjiga_branch': 'Jigjiga Branch',
            'jimma_branch': 'Jimma Branch',
            'kebridahar_branch': 'Kebridahar Branch',
            'mekele_branch': 'Mekele Branch',
            'negele_borena_branch': 'Negele Borena Branch',
            'nekemte_branch': 'Nekemte Branch',
            'semera_branch': 'Semera Branch',
            'shire_branch': 'Shire Branch',
            'head_office': 'Head Office',
            'hubs': 'Hubs',
            'nsoh': 'NSOH',
            'expiry': 'Expiry'
        }

        # Only map columns that exist in the Supabase data
        existing_mapping = {k: v for k, v in column_mapping.items() if k in df.columns}

        # Rename columns to original format
        df = df.rename(columns=existing_mapping)

        # Clean dataframe
        df = df.loc[:, ~df.columns.str.contains("^Unnamed")]
        df.columns = df.columns.str.strip()

        # Fill NaN with empty string for object columns
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].fillna("")

        return df
    except Exception as e:
        st.error(f"Error loading data from Supabase: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def load_branch_data():
    """Load branch AMC data from GitHub"""
    try:
        url = "https://raw.githubusercontent.com/Biyanaga24/Health-Supply-Chain-Dashboard/main/Branch_Health%20Program_AMC%20.xlsx"

        response = requests.get(url, timeout=30)
        response.raise_for_status()

        df = pd.read_excel(BytesIO(response.content), header=0)

        # Clean dataframe
        df = df.loc[:, ~df.columns.str.contains("^Unnamed")]
        df.columns = df.columns.str.strip()

        # Fill NaN with empty string for object columns
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].fillna("")

        return df
    except Exception as e:
        st.warning(f"Could not load branch data: {e}")
        return None

@st.cache_data(ttl=300)
def load_google_sheets(sheet_id):
    """Load Google Sheets data (AMC and pipeline data)"""
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=45)
            response.raise_for_status()

            content = response.content
            sheets = pd.read_excel(BytesIO(content), sheet_name=None, header=2)

            cleaned_sheets = {}
            for name, df in sheets.items():
                df = df.loc[:, ~df.columns.str.contains("^Unnamed")]
                df.columns = df.columns.str.strip()

                # Fill NaN with empty string for object columns
                for col in df.columns:
                    if df[col].dtype == 'object':
                        df[col] = df[col].fillna("")

                cleaned_sheets[name] = df

            st.session_state.google_sheets_data = cleaned_sheets
            return cleaned_sheets
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2)
            else:
                if st.session_state.google_sheets_data:
                    return st.session_state.google_sheets_data
                st.error(f"Error loading Google Sheets: {e}")
                return {}
    return {}

# ---------------------------------------------------
# Admin Functions for Supabase
# ---------------------------------------------------
def upload_to_supabase(df, table_name="health_data"):
    """Upload DataFrame to Supabase (convert to lowercase with underscores)"""
    try:
        if st.session_state.supabase_client is None:
            st.error("Supabase client not initialized")
            return False

        # Create reverse mapping to convert original format to Supabase format
        reverse_mapping = {
            'Material Description': 'material_description',
            'Adama Branch': 'adama_branch',
            'Addis Ababa Branch 1': 'addis_ababa_branch_1',
            'Addis Ababa Branch 2': 'addis_ababa_branch_2',
            'Arba Minch Branch': 'arba_minch_branch',
            'Assosa Branch': 'assosa_branch',
            'Bahir Dar Branch': 'bahir_dar_branch',
            'Dessie Branch': 'dessie_branch',
            'Dire Dawa Branch': 'dire_dawa_branch',
            'Gambela Branch': 'gambela_branch',
            'Gondar Branch': 'gondar_branch',
            'Hawassa Branch': 'hawassa_branch',
            'Jigjiga Branch': 'jigjiga_branch',
            'Jimma Branch': 'jimma_branch',
            'Kebridahar Branch': 'kebridahar_branch',
            'Mekele Branch': 'mekele_branch',
            'Negele Borena Branch': 'negele_borena_branch',
            'Nekemte Branch': 'nekemte_branch',
            'Semera Branch': 'semera_branch',
            'Shire Branch': 'shire_branch',
            'Head Office': 'head_office',
            'Hubs': 'hubs',
            'NSOH': 'nsoh',
            'Expiry': 'expiry'
        }

        # Select only columns that should be uploaded to Supabase
        upload_columns = [col for col in reverse_mapping.keys() if col in df.columns]
        df_upload = df[upload_columns].copy()

        # Rename columns to Supabase format
        df_upload = df_upload.rename(columns=reverse_mapping)

        # Replace NaN with None
        df_upload = df_upload.replace({np.nan: None})

        # Convert to records
        data = df_upload.to_dict(orient="records")

        # Upload to Supabase
        response = st.session_state.supabase_client.table(table_name).insert(data).execute()

        st.success(f"Successfully uploaded {len(data)} records to Supabase!")
        return True
    except Exception as e:
        st.error(f"Error uploading to Supabase: {e}")
        return False

def clear_supabase_table(table_name="health_data"):
    """Clear all data from Supabase table"""
    try:
        if st.session_state.supabase_client is None:
            st.error("Supabase client not initialized")
            return False

        # Delete all records
        response = st.session_state.supabase_client.table(table_name).delete().neq("id", 0).execute()

        st.success(f"Successfully cleared table {table_name}!")
        return True
    except Exception as e:
        st.error(f"Error clearing table: {e}")
        return False

def get_table_info():
    """Get information about the Supabase table"""
    try:
        if st.session_state.supabase_client is None:
            return None

        response = st.session_state.supabase_client.table("health_data").select("*").execute()

        if response.data:
            df = pd.DataFrame(response.data)
            return {
                "rows": len(df),
                "columns": len(df.columns),
                "column_names": list(df.columns)
            }
        return None
    except Exception as e:
        st.error(f"Error getting table info: {e}")
        return None

# ---------------------------------------------------
# Utility Functions
# ---------------------------------------------------
def format_number_with_commas(x):
    """Format number with commas"""
    try:
        if pd.isna(x) or x == "" or x is None:
            return ""
        if isinstance(x, str):
            x = x.replace(',', '')
            try:
                x = float(x) if x else np.nan
            except:
                return x
        if pd.isna(x):
            return ""
        x = round(x)
        return f"{x:,.0f}"
    except:
        return str(x) if x else ""

def format_mos_with_decimals(x):
    """Format MOS with 2 decimals"""
    try:
        if pd.isna(x) or x == "" or x is None:
            return ""
        if isinstance(x, str):
            try:
                x = float(x) if x else np.nan
            except:
                return x
        if pd.isna(x):
            return ""
        return f"{x:.2f}"
    except:
        return str(x) if x else ""

def categorize_stock(nmos):
    """Categorize stock status"""
    try:
        if pd.isna(nmos) or nmos == "" or nmos is None:
            return ""
        x = float(nmos) if not isinstance(nmos, (int, float)) else nmos
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

def calculate_coefficient_of_variation(values):
    """Calculate coefficient of variation"""
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

def calculate_risk(row):
    """Calculate risk of stock out"""
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

# ---------------------------------------------------
# Load ALL data
# ---------------------------------------------------
sheet_id = "14VvZ7IyOmpM4SZrY5_ArHDgLkeFN4inW"

# Load data from different sources
df_external = load_national_data()  # Real-time from Supabase (no cache)
cf = load_branch_data()  # Cached for 5 minutes
google_sheets = load_google_sheets(sheet_id)  # Cached for 5 minutes

if df_external.empty:
    st.error("No data in Supabase. Please upload data through admin panel.")
    st.stop()

# ---------------------------------------------------
# User Info in Sidebar
# ---------------------------------------------------
with st.sidebar:
    st.title(f"Welcome, {st.session_state['user']['full_name']}!")
    st.caption(f"Role: {st.session_state['user']['role'].title()}")

    # Show Supabase connection status for admin only
    if st.session_state['user']['role'] == 'admin' and st.session_state.supabase_client:
        st.success("✅ Connected to Supabase")

# ---------------------------------------------------
# Program Selection
# ---------------------------------------------------
if google_sheets:
    program_list = ["All"] + list(google_sheets.keys())
else:
    program_list = ["All"]

sheet_name = st.sidebar.selectbox("Program", program_list, index=0, key="program_selector")

if sheet_name == "All" and google_sheets:
    all_dfs = []
    for name, df_program in google_sheets.items():
        all_dfs.append(df_program.copy())
    df_google = pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()
elif google_sheets and sheet_name in google_sheets:
    df_google = google_sheets[sheet_name]
else:
    df_google = pd.DataFrame()

# ---------------------------------------------------
# Google Sheets data (AMC and pipeline data)
# ---------------------------------------------------
if not df_google.empty:
    required_cols = [
        'Material Description', 'AMC',
        'GIT_PO', 'GIT_Qty', 'GIT_MOS',
        'LC_PO', 'LC_Qty', 'LC_MOS',
        'WB_PO', 'WB_Qty', 'WB_MOS',
        'TMD_PO', 'TMD_Qty', 'TMD_MOS', "Status"
    ]
    available_cols = [c for c in required_cols if c in df_google.columns]
    df_google = df_google[available_cols]
else:
    df_google = pd.DataFrame()

# ---------------------------------------------------
# Merge: Supabase data + Google Sheets data
# ---------------------------------------------------
if not df_google.empty and not df_external.empty:
    # Merge on Material Description
    if 'Material Description' in df_external.columns and 'Material Description' in df_google.columns:
        # Remove duplicates before merge
        df_external = df_external.drop_duplicates(subset=['Material Description'], keep='first')
        df_google = df_google.drop_duplicates(subset=['Material Description'], keep='first')

        # Merge
        df = df_external.merge(df_google, on="Material Description", how="right")

        # Remove any duplicates after merge
        df = df.drop_duplicates(subset=['Material Description'], keep='first')
    else:
        st.error("Material Description column missing for merge")
        df = df_external.copy()
else:
    df = df_external.copy()

if not df.empty:
    # Remove S/N column if it exists
    if 'S/N' in df.columns:
        df = df.drop(columns=['S/N'])

    # Define text columns that should remain as strings
    text_columns = ['Status', 'Expiry', 'GIT_PO', 'LC_PO', 'WB_PO', 'TMD_PO']

    # Store text values before any conversion
    text_values = {}
    for col in text_columns:
        if col in df.columns:
            text_values[col] = df[col].copy()

    # Convert numeric columns (excluding text columns and Material Description)
    for col in df.columns:
        if col not in text_columns and col != 'Material Description':
            try:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            except:
                pass

    # Restore text columns
    for col, values in text_values.items():
        if col in df.columns:
            df[col] = values

    # Calculate NMOS using NSOH (from Supabase) and AMC (from Google Sheets)
    if 'NSOH' in df.columns and 'AMC' in df.columns:
        nsoh = pd.to_numeric(df['NSOH'], errors='coerce')
        amc = pd.to_numeric(df['AMC'], errors='coerce')
        # Avoid division by zero
        nmos = np.where(amc != 0, nsoh / amc, np.nan)
        df['NMOS'] = nmos

    # Calculate TMOS
    mos_cols = ['NMOS', 'GIT_MOS', 'LC_MOS', 'WB_MOS', 'TMD_MOS']
    available_mos = []
    for col in mos_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            available_mos.append(col)

    if available_mos:
        df['TMOS'] = df[available_mos].sum(axis=1)
    else:
        df['TMOS'] = np.nan

    # Stock Status
    if 'NMOS' in df.columns:
        df['Stock Status'] = df['NMOS'].apply(categorize_stock)
    else:
        df['Stock Status'] = ""

    # Calculate Hubs% and Head Office%
    if 'Hubs' in df.columns and 'Head Office' in df.columns and 'NSOH' in df.columns:
        hubs_vals = pd.to_numeric(df['Hubs'], errors='coerce').fillna(0)
        ho_vals = pd.to_numeric(df['Head Office'], errors='coerce').fillna(0)
        nsoh_vals = pd.to_numeric(df['NSOH'], errors='coerce')

        valid_mask = nsoh_vals.notna() & (nsoh_vals > 0)

        df['Hubs%'] = np.where(valid_mask, (hubs_vals / nsoh_vals * 100).round(1), np.nan)
        df['Head Office%'] = np.where(valid_mask, (ho_vals / nsoh_vals * 100).round(1), np.nan)
    else:
        df['Hubs%'] = np.nan
        df['Head Office%'] = np.nan

    # Risk of Stock calculation
    if 'NMOS' in df.columns:
        df['Risk of Stock'] = df.apply(calculate_risk, axis=1)
    else:
        df['Risk of Stock'] = ""

    # Create formatted display version
    display_df = df.copy()

    # Columns to preserve as text
    text_columns_to_preserve = ['Material Description', 'Stock Status', 'Risk of Stock', 'Status', 'Expiry', 'GIT_PO', 'LC_PO', 'WB_PO', 'TMD_PO']

    # Format percentages specially
    if 'Hubs%' in display_df.columns:
        text_columns_to_preserve.append('Hubs%')
    if 'Head Office%' in display_df.columns:
        text_columns_to_preserve.append('Head Office%')

    # Format numeric columns
    for col in display_df.columns:
        if col not in text_columns_to_preserve:
            if col in ['NMOS', 'GIT_MOS', 'LC_MOS', 'WB_MOS', 'TMD_MOS', 'TMOS']:
                display_df[col] = display_df[col].apply(format_mos_with_decimals)
            elif col in ['Hubs%', 'Head Office%']:
                display_df[col] = display_df[col].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "")
            else:
                display_df[col] = display_df[col].apply(format_number_with_commas)

    # Filters
    if 'Material Description' in df.columns:
        materials = ["All"] + sorted(df['Material Description'].astype(str).unique())

        if 'Stock Status' in df.columns:
            status_values = [s for s in df['Stock Status'].unique() if s != "" and pd.notna(s)]
            statuses = ["All"] + sorted(status_values) if status_values else ["All"]
        else:
            statuses = ["All"]

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
        if status_filter != "All" and 'Stock Status' in df_filtered.columns:
            df_filtered = df_filtered[df_filtered['Stock Status'] == status_filter]
            display_df_filtered = display_df_filtered[display_df_filtered['Stock Status'] == status_filter]
        if risk_filter != "All" and 'Risk of Stock' in df_filtered.columns:
            df_filtered = df_filtered[df_filtered['Risk of Stock'] == risk_filter]
            display_df_filtered = display_df_filtered[display_df_filtered['Risk of Stock'] == risk_filter]
    else:
        st.error("Material Description column not found in the data")
        df_filtered = pd.DataFrame()
        display_df_filtered = pd.DataFrame()

else:
    st.error("No data available.")
    df_filtered = pd.DataFrame()
    display_df_filtered = pd.DataFrame()

# ---------------------------------------------------
# Navigation
# ---------------------------------------------------
st.sidebar.divider()

if st.session_state['user']['role'] == 'admin':
    page = st.sidebar.radio("Navigation", ["Dashboard", "Admin Panel", "Profile"])
else:
    page = st.sidebar.radio("Navigation", ["Dashboard", "Profile"])

# ---------------------------------------------------
# Data Refresh Controls
# ---------------------------------------------------
st.sidebar.divider()
st.sidebar.markdown("### 🔄 Data Updates")

# Display last refresh time for all users
st.sidebar.caption(f"📅 Data as of: {st.session_state.data_timestamp.strftime('%Y-%m-%d %H:%M:%S')}")

# Show data source info for admin only
if st.session_state['user']['role'] == 'admin':
    st.sidebar.info("📊 Data Sources:\n- Supabase: Real-time\n- Google Sheets: Cached 5 min\n- Branch AMC: Cached 5 min")

# Auto-refresh option
auto_refresh = st.sidebar.checkbox("Auto-refresh every 5 minutes", value=st.session_state.auto_refresh)
if auto_refresh != st.session_state.auto_refresh:
    st.session_state.auto_refresh = auto_refresh

if st.session_state.auto_refresh:
    time_since_refresh = (datetime.now() - st.session_state.data_timestamp).total_seconds()
    if time_since_refresh > 300:  # 5 minutes
        st.cache_data.clear()  # Clear cache for Google Sheets and Branch data
        st.session_state.data_timestamp = datetime.now()
        st.rerun()

# Manual refresh button for all users
if st.sidebar.button("🔄 Refresh Now", use_container_width=True, type="primary"):
    st.cache_data.clear()  # Clear all cached data
    st.session_state.data_timestamp = datetime.now()
    st.rerun()

# Option to force clear all caches - admin only
if st.session_state['user']['role'] == 'admin':
    if st.sidebar.button("🗑️ Clear All Caches", use_container_width=True):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.session_state.data_timestamp = datetime.now()
        st.success("All caches cleared! Refreshing...")
        time.sleep(1)
        st.rerun()

# ---------------------------------------------------
# Admin Panel - Supabase Management
# ---------------------------------------------------
if st.session_state['user']['role'] == 'admin':
    with st.sidebar.expander("📁 Supabase Management"):
        st.caption("Manage data in Supabase")

        # Show current table info
        table_info = get_table_info()
        if table_info:
            st.info(f"Current data: {table_info['rows']} rows, {table_info['columns']} columns")

        # Upload new data
        st.markdown("#### Upload New Data")
        st.caption("Upload Excel or CSV file with your data")

        uploaded_file = st.file_uploader("Choose Excel or CSV file", type=['xlsx', 'csv', 'xls'], key='data_upload')

        if uploaded_file:
            try:
                # Read the uploaded file
                if uploaded_file.name.endswith('.csv'):
                    df_upload = pd.read_csv(uploaded_file)
                else:
                    df_upload = pd.read_excel(uploaded_file)

                st.write(f"Preview of data to upload ({len(df_upload)} rows):")
                st.dataframe(df_upload.head())

                col1, col2 = st.columns(2)
                with col1:
                    if st.button("📤 Upload to Supabase", use_container_width=True, type="primary"):
                        with st.spinner("Uploading to Supabase..."):
                            if upload_to_supabase(df_upload):
                                st.cache_data.clear()
                                st.session_state.data_timestamp = datetime.now()
                                st.success("Upload successful! Refreshing...")
                                time.sleep(1)
                                st.rerun()
                with col2:
                    if st.button("⚠️ Clear All Data", use_container_width=True):
                        with st.spinner("Clearing Supabase data..."):
                            if clear_supabase_table():
                                st.cache_data.clear()
                                st.session_state.data_timestamp = datetime.now()
                                st.success("Data cleared! Refreshing...")
                                time.sleep(1)
                                st.rerun()
            except Exception as e:
                st.error(f"Error reading file: {e}")

        st.markdown("---")
        st.caption("Data stored in Supabase table: `health_data`")

# ---------------------------------------------------
# Logout
# ---------------------------------------------------
st.sidebar.divider()
if st.sidebar.button("🚪 Logout", use_container_width=True):
    st.session_state['auth'] = False
    st.session_state['user'] = None
    st.rerun()

# ---------------------------------------------------
# Route to pages
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
# Tabs
# ---------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 **STOCK STATUS TABLE**", 
    "📈 **STOCK STATUS KPI**", 
    "⚠️ **DECISION BRIEFS**", 
    "🗺️ **EPSS HUBS DISTRIBUTION PATTERN**"
])

# ---------------------------------------------------
# TAB 1 - Stock Status Table
# ---------------------------------------------------
with tab1:
    st.markdown("<h3 style='font-size: 28px; font-weight: bold; font-family: Times New Roman;'>Complete Stock Status Table</h3>", unsafe_allow_html=True)

    if not display_df_filtered.empty and 'Material Description' in display_df_filtered.columns:
        # Reorder columns
        cols = list(display_df_filtered.columns)
        if 'Material Description' in cols:
            cols.remove('Material Description')
            cols.insert(0, 'Material Description')
        if 'NMOS' in cols and 'AMC' in cols:
            cols.remove('NMOS')
            amc_index = cols.index('AMC') if 'AMC' in cols else 0
            cols.insert(amc_index + 1, 'NMOS')
        if 'Risk of Stock' in cols and 'Stock Status' in cols:
            cols.remove('Risk of Stock')
            status_index = cols.index('Stock Status') if 'Stock Status' in cols else 0
            cols.insert(status_index + 1, 'Risk of Stock')

        cols = [c for c in cols if c in display_df_filtered.columns]
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
                pinned=True
            )
        }

        st.dataframe(
            styled,
            column_config=column_config,
            use_container_width=True,
            hide_index=True,
            height=min(800, (len(display_df_filtered) + 1) * 35)
        )
    else:
        st.info("No data available or Material Description column missing.")

# ---------------------------------------------------
# TAB 2 - KPIs & Charts
# ---------------------------------------------------
with tab2:
    st.markdown("<h3 style='font-size: 28px; font-weight: bold; font-family: Times New Roman;'>Key Performance Indicators</h3>", unsafe_allow_html=True)

    if not df_filtered.empty and 'NMOS' in df_filtered.columns:
        # KPI Gauges
        nmos_values = pd.to_numeric(df_filtered['NMOS'], errors='coerce').dropna()
        availability = (nmos_values > 1).mean() * 100 if len(nmos_values) > 0 else 0
        sap = ((nmos_values >= 6) & (nmos_values <= 18)).mean() * 100 if len(nmos_values) > 0 else 0

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

        def create_kpi_fig(value, target, title, suffix="%"):
            display_color = 'red' if value < target else 'black'
            return go.Figure(go.Indicator(
                mode="gauge+number",
                value=value,
                number={'suffix': suffix, 'font': {'size': 36, 'color': display_color}},
                title={'text': f"<b>{title}</b>", 'font': {'size': 24}},
                gauge={'axis': {'range': [0, 100]}, 'bar': {'color': 'skyblue'}}
            ))

        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(create_kpi_fig(availability, availability_target, "Availability"), use_container_width=True)
        with col2:
            st.plotly_chart(create_kpi_fig(sap, sap_target, "SAP"), use_container_width=True)

        col3, col4 = st.columns(2)
        with col3:
            st.plotly_chart(create_kpi_fig(avg_hubs_pct, 50, "Avg Hubs %"), use_container_width=True)
        with col4:
            st.plotly_chart(create_kpi_fig(avg_ho_pct, 50, "Avg Head Office %"), use_container_width=True)

        # Pie Chart
        try:
            if 'Stock Status' in df_filtered.columns:
                status_counts = df_filtered['Stock Status'].replace("", np.nan).dropna().value_counts()
                if not status_counts.empty:
                    fig = px.pie(
                        values=status_counts.values,
                        names=status_counts.index,
                        hole=0.5,
                        color=status_counts.index,
                        color_discrete_map={
                            "Stock Out": "red", 
                            "Understock": "yellow", 
                            "Normal Stock": "green", 
                            "Overstock": "skyblue"
                        },
                    )
                    fig.update_traces(textposition='inside', textinfo='percent+value')
                    fig.update_layout(
                        title={'text': f"Stock Status - {sheet_name}", 'x': 0.5}
                    )
                    st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            pass

        # MOS Horizontal Bar Chart
        try:
            if 'Material Description' in df_filtered.columns and 'NMOS' in df_filtered.columns:
                mos_cols_chart = ['Material Description', 'NMOS', 'GIT_MOS', 'LC_MOS', 'WB_MOS', 'TMD_MOS', 'TMOS']
                available_cols = [c for c in mos_cols_chart if c in df_filtered.columns]
                mos_df = df_filtered[available_cols].copy()
                mos_df['NMOS'] = pd.to_numeric(mos_df['NMOS'], errors='coerce')
                mos_df = mos_df[mos_df['NMOS'].notna()]
                if not mos_df.empty:
                    for c in ['GIT_MOS', 'LC_MOS', 'WB_MOS', 'TMD_MOS', 'TMOS']:
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

                        if 'TMOS' in df_chunk.columns:
                            fig.add_trace(go.Scatter(
                                y=df_chunk['Material_split'],
                                x=df_chunk['TMOS'],
                                mode='text',
                                text=df_chunk['TMOS'].apply(lambda x: f"TMOS: {x:.2f}"),
                                textposition='middle right',
                                showlegend=False
                            ))

                        if sheet_name == "All":
                            chart_title = f'National and Pipeline Stock Status - All Programs (Medicines {i + 1}-{i + len(df_chunk)})'
                        else:
                            chart_title = f'National and Pipeline Stock Status - {sheet_name} (Medicines {i + 1}-{i + len(df_chunk)})'

                        fig.update_layout(
                            barmode='stack',
                            title=chart_title,
                            xaxis_title='Months of Stock',
                            yaxis_title='Material Description',
                            height=max(500, 35 * len(df_chunk))
                        )
                        st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            pass

        # Stacked Bar Chart: Hubs vs Head Office
        try:
            if all(col in df_filtered.columns for col in ['Hubs', 'Head Office', 'NSOH', 'Material Description']):
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
                            textposition='inside'
                        ))

                        fig_bar.add_trace(go.Bar(
                            y=df_chunk['Material_split'],
                            x=df_chunk['Head Office%'],
                            name='Head Office%',
                            orientation='h',
                            marker_color='orange',
                            text=df_chunk['Head Office%'].apply(lambda x: f"{x:.1f}%" if x > 0 else ""),
                            textposition='inside'
                        ))

                        for idx, row in df_chunk.iterrows():
                            total_pct = row['Hubs%'] + row['Head Office%']

                            fig_bar.add_annotation(
                                x=total_pct + 2,
                                y=row['Material_split'],
                                text=f"NSOH: {row['NSOH_display']}",
                                showarrow=False,
                                font=dict(size=10),
                                xanchor='left',
                                yanchor='middle'
                            )

                        fig_bar.update_layout(
                            barmode='stack',
                            title=f'Stock Distribution Hubs vs Head Office (Materials {i + 1}-{i + len(df_chunk)})',
                            xaxis_title='Percentage of NSOH (%)',
                            yaxis_title='Material Description',
                            xaxis={'range': [0, 120]},
                            height=max(600, 40 * len(df_chunk)),
                            margin=dict(r=150)
                        )

                        st.plotly_chart(fig_bar, use_container_width=True)
                else:
                    st.info("No materials with valid NSOH (>0) to display.")
        except Exception as e:
            pass
    else:
        st.info("No data available for KPI calculations.")

# ---------------------------------------------------
# TAB 3 - Decision Briefs
# ---------------------------------------------------
with tab3:
    if sheet_name == "All":
        st.markdown("<h3 style='font-size: 28px; font-weight: bold; font-family: Times New Roman;'>All Programs - Medicines Needing Immediate Action</h3>", unsafe_allow_html=True)
    else:
        st.markdown(f"<h3 style='font-size: 28px; font-weight: bold; font-family: Times New Roman;'>{sheet_name} Medicines Needing Immediate Action</h3>", unsafe_allow_html=True)

    if not df_filtered.empty and 'Material Description' in df_filtered.columns:
        st.markdown("<h4 style='font-size: 24px; font-weight: bold; font-family: Times New Roman;'>Quick Summary</h4>", unsafe_allow_html=True)

        decision_cols = ['Material Description', 'NSOH', 'Expiry', 'AMC', 'NMOS', 'Status']
        available_decision_cols = [col for col in decision_cols if col in df_filtered.columns]

        if available_decision_cols:
            decision_df = df_filtered[available_decision_cols].copy()
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
                # Format numeric columns for display
                for col in ['NSOH', 'AMC']:
                    if col in decision_df.columns:
                        decision_df[col] = decision_df[col].apply(format_number_with_commas)
                if 'NMOS' in decision_df.columns:
                    decision_df['NMOS'] = decision_df['NMOS'].apply(format_mos_with_decimals)

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
                        pinned=True
                    ),
                    "NSOH": st.column_config.TextColumn(
                        "NSOH",
                        width=100,
                        disabled=True
                    ),
                    "Expiry": st.column_config.TextColumn(
                        "Expiry",
                        width=100,
                        disabled=True
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
                        disabled=True
                    ),
                    "Recommendation": st.column_config.TextColumn(
                        "Recommendation",
                        width=350,
                        required=False
                    )
                }

                edited_result = st.data_editor(
                    decision_df,
                    column_config=column_config,
                    use_container_width=False,
                    hide_index=True,
                    height=min(600, (len(decision_df) + 1) * 35),
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
    else:
        st.info("No data available for decision briefs.")

# ---------------------------------------------------
# TAB 4 - Hubs Distribution Pattern
# ---------------------------------------------------
with tab4:
    try:
        if not df.empty:
            main_df = df.copy()

            if cf is not None and 'Material Description' in main_df.columns and 'Material Description' in cf.columns:
                # Take Material Description plus branch columns
                branch_cols = [col for col in main_df.columns if 'Branch' in col or col == 'Material Description']
                gh = main_df[branch_cols].copy() if branch_cols else pd.DataFrame()

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
                                textfont={"size": 10},
                                colorbar=dict(
                                    title="MOS",
                                    tickvals=[0.5, 1, 2, 4, 6, 8],
                                    ticktext=['0.5', '1', '2', '4', '6', '8+']
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
                                    'tickfont': {'size': 10}
                                },
                                yaxis={
                                    'title': 'Branches',
                                    'tickfont': {'size': 10}
                                },
                                height=650,
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
                st.warning("Branch data file not available from GitHub.")

                # Show available data as fallback
                if not df.empty and 'Material Description' in df.columns:
                    branch_cols = [col for col in df.columns if 'Branch' in col or col == 'Material Description']
                    gh = df[branch_cols].copy() if branch_cols else df[['Material Description']].copy()
                    st.markdown("<h5 style='font-size: 20px; font-weight: bold; font-family: Times New Roman;'>Available Hubs SOH Data</h5>", unsafe_allow_html=True)
                    st.dataframe(
                        gh,
                        use_container_width=True,
                        height=400,
                        hide_index=True
                    )
            else:
                st.error("'Material Description' column not found in one or both dataframes")
        else:
            st.warning("Main dataframe is empty.")

    except Exception as e:
        st.error(f"Error processing files: {e}")

# ---------------------------------------------------
# Download Filtered Data
# ---------------------------------------------------
if not display_df_filtered.empty and 'Material Description' in display_df_filtered.columns:
    st.divider()
    st.download_button(
        label="Download Full Filtered Data",
        data=display_df_filtered.to_csv(index=False),
        file_name=f"full_stock_dashboard_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv"
    )
