import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from datetime import timedelta
import sys
import os
import time
import requests
import re
from io import BytesIO
from supabase import create_client
import socket
from openpyxl.utils import get_column_letter

# Add the current directory to path
sys.path.append(os.path.dirname(__file__))

# Import authentication functions
from auth import show_login_page, show_profile_page, show_admin_panel

# ---------------------------------------------------
# Supabase Configuration - Using Streamlit Secrets
# ---------------------------------------------------
@st.cache_resource
def init_supabase():
    """Initialize Supabase client"""
    try:
        supabase_url = st.secrets["SUPABASE_URL"]
        supabase_key = st.secrets["SUPABASE_KEY"]
        supabase = create_client(supabase_url, supabase_key)
        return supabase
    except Exception as e:
        st.error(f"Error connecting to Supabase: {e}")
        return None

def check_supabase_connection():
    """Check Supabase connection health"""
    try:
        if st.session_state.supabase_client:
            response = st.session_state.supabase_client.table("health_data").select("*").limit(1).execute()
            return True
    except Exception:
        return False
    return False

# Check authentication
if 'auth' not in st.session_state:
    st.session_state['auth'] = False

if not st.session_state['auth']:
    show_login_page()
    st.stop()

# ---------------------------------------------------
# Page Setup
# ---------------------------------------------------
st.set_page_config(
    page_title="Health Program Medicines Dashboard", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

# ---------------------------------------------------
# CSS Styling with Mobile Responsiveness
# ---------------------------------------------------
st.markdown("""
<style>
    /* Main container */
    .stApp {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    }

    /* Metric cards */
    div[data-testid="stMetric"] {
        background: white;
        border-radius: 15px;
        padding: 15px;
        transition: all 0.3s ease;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }

    div[data-testid="stMetric"]:hover {
        transform: translateY(-5px);
        box-shadow: 0 8px 15px rgba(0,0,0,0.2);
        background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
    }

    /* Animations */
    @keyframes shake {
        0%, 100% { transform: translateX(0); }
        10%, 30%, 50%, 70%, 90% { transform: translateX(-2px); }
        20%, 40%, 60%, 80% { transform: translateX(2px); }
    }

    @keyframes vertical-shake {
        0%, 100% { transform: translateY(0); }
        10%, 30%, 50%, 70%, 90% { transform: translateY(-2px); }
        20%, 40%, 60%, 80% { transform: translateY(2px); }
    }

    @keyframes gentle-shake {
        0%, 100% { transform: translateX(0); }
        25%, 75% { transform: translateX(-1px); }
        50% { transform: translateX(1px); }
    }

    .stButton button:hover {
        animation: shake 0.5s ease-in-out;
        transform: scale(1.02);
        transition: all 0.3s ease;
    }

    div[data-testid="stMetricValue"]:hover {
        animation: gentle-shake 0.3s ease-in-out;
    }

    .stDownloadButton button:hover {
        animation: shake 0.4s ease-in-out;
    }

    button[data-baseweb="tab"]:hover {
        animation: gentle-shake 0.2s ease-in-out;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white !important;
    }

    /* Stock cards */
    .stock-card {
        border: 1px solid #ddd;
        border-radius: 10px;
        padding: 15px;
        margin: 5px;
        background-color: white;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        transition: all 0.3s ease;
    }

    .stock-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.15);
    }

    .gradient-text {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        font-weight: bold;
    }

    /* Tabs */
    button[data-baseweb="tab"] {
        font-size: 18px !important;
        font-weight: 700 !important;
        font-family: 'Times New Roman', sans-serif !important;
        padding: 10px 20px !important;
    }

    /* Legend box */
    .legend-box {
        margin: 10px 0 20px 0;
        padding: 15px;
        background-color: #f8f9fa;
        border-radius: 10px;
        border: 1px solid #dee2e6;
    }

    .legend-title {
        margin: 0 0 10px 0;
        font-size: 16px;
        font-weight: bold;
    }

    .legend-item {
        display: flex;
        align-items: center;
        gap: 8px;
    }

    .legend-color {
        width: 20px;
        height: 20px;
        border-radius: 3px;
    }

    /* Mobile Responsive */
    @media only screen and (max-width: 768px) {
        .stApp {
            padding: 0.5rem !important;
        }

        div[data-testid="stMetric"] {
            margin-bottom: 10px !important;
            padding: 10px !important;
        }

        h1 {
            font-size: 22px !important;
            text-align: center !important;
        }

        h3 {
            font-size: 18px !important;
        }

        button[data-baseweb="tab"] {
            font-size: 12px !important;
            padding: 6px 10px !important;
            white-space: nowrap !important;
        }

        [data-testid="stTabs"] {
            overflow-x: auto !important;
            white-space: nowrap !important;
            flex-wrap: nowrap !important;
        }

        [data-testid="stTabs"] button {
            flex: 0 0 auto !important;
        }

        .stock-card {
            padding: 8px !important;
            margin: 5px 0 !important;
        }

        div[data-testid="stMetricValue"] {
            font-size: 20px !important;
        }

        div[data-testid="stMetricLabel"] {
            font-size: 12px !important;
        }

        .stButton button {
            font-size: 12px !important;
            padding: 6px 12px !important;
        }

        [data-testid="stSidebar"] {
            width: 280px !important;
        }

        .stPlotlyChart {
            width: 100% !important;
            overflow-x: auto !important;
        }
    }

    @media only screen and (max-width: 480px) {
        h1 {
            font-size: 18px !important;
        }

        button[data-baseweb="tab"] {
            font-size: 10px !important;
            padding: 4px 8px !important;
        }

        div[data-testid="stMetricValue"] {
            font-size: 16px !important;
        }
    }
</style>
""", unsafe_allow_html=True)

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
if 'branch_amc_data' not in st.session_state:
    st.session_state.branch_amc_data = None
if 'supabase_client' not in st.session_state:
    st.session_state.supabase_client = init_supabase()
if 'branch_data' not in st.session_state:
    st.session_state.branch_data = None
if 'search_query' not in st.session_state:
    st.session_state.search_query = ""
if 'last_sheet_name' not in st.session_state:
    st.session_state.last_sheet_name = ""
if 'saved_recommendations' not in st.session_state:
    st.session_state.saved_recommendations = {}
if 'view_mode' not in st.session_state:
    st.session_state.view_mode = "table"
if 'risk_type_filter' not in st.session_state:
    st.session_state.risk_type_filter = "All"
if 'subcategory_filter' not in st.session_state:
    st.session_state.subcategory_filter = "All"
if 'previous_nsoh_data' not in st.session_state:
    st.session_state.previous_nsoh_data = None
if 'nsoh_changes' not in st.session_state:
    st.session_state.nsoh_changes = None
if 'raw_previous_data' not in st.session_state:
    st.session_state.raw_previous_data = None
if 'material_views' not in st.session_state:
    st.session_state.material_views = {}
if 'user_activity' not in st.session_state:
    st.session_state.user_activity = []
if 'notifications' not in st.session_state:
    st.session_state.notifications = []

# Check connection periodically
if st.session_state.supabase_client and not check_supabase_connection():
    st.warning("⚠️ Supabase connection lost. Attempting to reconnect...")
    st.session_state.supabase_client = init_supabase()

# ---------------------------------------------------
# Program Hierarchy Configuration
# ---------------------------------------------------
PROGRAM_HIERARCHY = {
    "OI and Hepatitis": {
        "subcategories": ["AHD", "Hepatitis", "OI", "STI"],
        "is_parent": True
    },
    "TB": {
        "subcategories": ["Drug Susceptible -TB Medicine (DS-TB)", "Drug Resisitance -TB Medicine (DR-TB)", "Leprosy Medicines", "Nutrition"],
        "is_parent": True
    }
}

# ---------------------------------------------------
# Function to assign subcategories based on sequential order
# ---------------------------------------------------
def assign_subcategories_to_materials(df, subcategory_list):
    """Assign subcategory to each material based on sequential order in Material Description column"""
    subcategory_mapping = {}
    current_subcategory = None

    for idx in range(len(df)):
        material_desc = str(df.iloc[idx]['Material Description']).strip()

        # Check if this row is a subcategory header
        is_subcategory = False
        for subcat in subcategory_list:
            if material_desc == subcat:
                current_subcategory = subcat
                is_subcategory = True
                break

        # If not a subcategory header and we have a current subcategory, assign it
        if not is_subcategory and current_subcategory is not None:
            subcategory_mapping[material_desc] = current_subcategory

    return subcategory_mapping

def is_subcategory_header(material_desc, subcategory_list):
    """Check if a material description is actually a subcategory header"""
    return material_desc.strip() in subcategory_list

def filter_out_subcategory_headers(df, subcategory_list):
    """Remove subcategory header rows from the dataframe"""
    if subcategory_list is None or not subcategory_list:
        return df

    # Create a mask to filter out rows where Material Description is a subcategory header
    mask = ~df['Material Description'].astype(str).str.strip().isin(subcategory_list)
    return df[mask].copy()

# ---------------------------------------------------
# Expiry Risk Calculation Function
# ---------------------------------------------------
def parse_multiple_expiry_batches(expiry_str, amc):
    """Parse multiple batches and determine expiry risk"""
    try:
        if pd.isna(expiry_str) or expiry_str == "" or expiry_str is None:
            return False, ""

        expiry_str = str(expiry_str)
        pattern = r'(\d[\d,]*)\s*\(([A-Za-z]+)-(\d{4})\)'
        matches = re.findall(pattern, expiry_str)

        if not matches:
            return False, ""

        batches = []
        month_map = {'Jan':1, 'Feb':2, 'Mar':3, 'Apr':4, 'May':5, 'Jun':6,
                    'Jul':7, 'Aug':8, 'Sep':9, 'Oct':10, 'Nov':11, 'Dec':12}

        for quantity_str, month, year in matches:
            quantity = float(quantity_str.replace(',', ''))
            month_num = month_map.get(month[:3], 1)
            expiry_date = datetime(int(year), month_num, 1)
            batches.append({'quantity': quantity, 'expiry_date': expiry_date})

        batches.sort(key=lambda x: x['expiry_date'])

        if pd.isna(amc) or amc <= 0:
            return False, ""

        cumulative_stock = 0
        has_risk = False
        risk_details = []

        for batch in batches:
            months_until_expiry = max(0, (batch['expiry_date'].year - datetime.now().year) * 12 + 
                                      (batch['expiry_date'].month - datetime.now().month))
            cumulative_stock += batch['quantity']
            stock_needed = amc * months_until_expiry

            if cumulative_stock > stock_needed:
                excess = cumulative_stock - stock_needed
                batch_risk = min(batch['quantity'], excess)
                if batch_risk > 0:
                    has_risk = True
                    risk_details.append(f"{batch_risk:,.0f} units expiring {batch['expiry_date'].strftime('%b-%Y')}")

        return has_risk, "; ".join(risk_details) if risk_details else ""
    except Exception as e:
        return False, f"Error: {e}"

# ---------------------------------------------------
# Database Connection Functions
# ---------------------------------------------------
def load_national_data():
    """Load national_data from Supabase"""
    try:
        if st.session_state.supabase_client is None:
            st.error("Supabase client not initialized")
            return pd.DataFrame()

        response = st.session_state.supabase_client.table("health_data").select("*").execute()

        if not response.data:
            st.warning("No data found in Supabase")
            return pd.DataFrame()

        df = pd.DataFrame(response.data)

        if 'id' in df.columns:
            df = df.drop(columns=['id'])

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

        existing_mapping = {k: v for k, v in column_mapping.items() if k in df.columns}
        df = df.rename(columns=existing_mapping)

        df = df.loc[:, ~df.columns.str.contains("^Unnamed")]
        df.columns = df.columns.str.strip()

        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].fillna("")

        return df
    except Exception as e:
        st.error(f"Error loading data from Supabase: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def load_branch_amc_from_google_sheets(sheet_id):
    """Load branch AMC data from Google Sheets"""
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"

    for attempt in range(1):
        try:
            session = requests.Session()
            session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
            session.trust_env = False

            response = session.get(url, timeout=45)
            response.raise_for_status()

            content = response.content
            df = pd.read_excel(BytesIO(content), header=0)

            df = df.loc[:, ~df.columns.str.contains("^Unnamed")]
            df.columns = df.columns.str.strip()

            for col in df.columns:
                if df[col].dtype == 'object':
                    df[col] = df[col].fillna("")

            st.session_state.branch_amc_data = df
            return df
        except Exception as e:
            if st.session_state.branch_amc_data is not None:
                st.warning(f"Using cached branch AMC data. New data unavailable: {str(e)}")
                return st.session_state.branch_amc_data
            st.warning(f"Could not load branch AMC data: {str(e)}")
            return pd.DataFrame(columns=['Material Description'])
    return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def load_google_sheets(sheet_id):
    """Load Google Sheets data (AMC and pipeline data)"""
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"

    for attempt in range(3):
        try:
            session = requests.Session()
            session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
            session.trust_env = False

            response = session.get(url, timeout=45)
            response.raise_for_status()

            content = response.content
            sheets = pd.read_excel(BytesIO(content), sheet_name=None, header=2)

            cleaned_sheets = {}
            for name, df in sheets.items():
                if df.empty:
                    cleaned_sheets[name] = df
                    continue

                df = df.loc[:, ~df.columns.str.contains("^Unnamed")]
                df.columns = df.columns.str.strip()

                for col in df.columns:
                    try:
                        if col in df.columns and len(df) > 0:
                            if pd.api.types.is_object_dtype(df[col]):
                                df[col] = df[col].fillna("")
                            elif df[col].dtype == 'object':
                                df[col] = df[col].fillna("")
                    except Exception:
                        continue

                cleaned_sheets[name] = df

            st.session_state.google_sheets_data = cleaned_sheets
            return cleaned_sheets
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
            else:
                if st.session_state.google_sheets_data:
                    st.warning(f"Using cached Google Sheets data. New data unavailable: {str(e)}")
                    return st.session_state.google_sheets_data
                st.error(f"Error loading Google Sheets: {str(e)}")
                return {}
    return {}

def validate_upload_data(df):
    """Validate data before uploading to Supabase"""
    required_columns = ['Material Description', 'NSOH']
    missing_columns = [col for col in required_columns if col not in df.columns]

    if missing_columns:
        st.error(f"Missing required columns: {', '.join(missing_columns)}")
        return False

    if df['Material Description'].duplicated().any():
        st.warning("Duplicate Material Descriptions found. Only first occurrence will be kept.")
        df = df.drop_duplicates(subset=['Material Description'], keep='first')

    return True

# ---------------------------------------------------
# Admin Functions for Supabase
# ---------------------------------------------------
def upload_to_supabase(df, table_name="health_data"):
    """Upload DataFrame to Supabase"""
    try:
        if st.session_state.supabase_client is None:
            st.error("Supabase client not initialized")
            return False

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

        upload_columns = [col for col in reverse_mapping.keys() if col in df.columns]
        df_upload = df[upload_columns].copy()
        df_upload = df_upload.rename(columns=reverse_mapping)
        df_upload = df_upload.replace({np.nan: None})
        data = df_upload.to_dict(orient="records")

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
            return {"rows": len(df), "columns": len(df.columns), "column_names": list(df.columns)}
        return None
    except Exception as e:
        st.error(f"Error getting table info: {e}")
        return None

# ---------------------------------------------------
# Stock Change Tracking Function
# ---------------------------------------------------
def calculate_stock_changes(current_df, previous_df):
    """Calculate stock quantity changes based on NMOS differences"""
    if previous_df is None or previous_df.empty:
        return None

    if 'NMOS' not in current_df.columns or 'AMC' not in current_df.columns:
        return None
    if 'NMOS' not in previous_df.columns or 'AMC' not in previous_df.columns:
        return None

    current_data = current_df[['Material Description', 'NMOS', 'AMC']].copy()
    previous_data = previous_df[['Material Description', 'NMOS', 'AMC']].copy()

    for df_data in [current_data, previous_data]:
        df_data['NMOS'] = pd.to_numeric(df_data['NMOS'], errors='coerce')
        df_data['AMC'] = pd.to_numeric(df_data['AMC'], errors='coerce')
        df_data['NMOS'] = df_data['NMOS'].fillna(0)
        df_data['AMC'] = df_data['AMC'].fillna(0)

    merged = current_data.merge(
        previous_data, 
        on='Material Description', 
        suffixes=('_now', '_previous'), 
        how='inner'
    )

    merged['NMOS_Difference'] = merged['NMOS_now'] - merged['NMOS_previous']

    merged['Added_Quantity'] = np.where(
        merged['NMOS_Difference'] > 0,
        merged['NMOS_Difference'] * merged['AMC_now'],
        0
    )

    positive_changes = merged[merged['NMOS_Difference'] > 0].copy()

    if not positive_changes.empty:
        positive_changes = positive_changes.sort_values('NMOS_Difference', ascending=False)

        positive_changes['NMOS_previous'] = positive_changes['NMOS_previous'].apply(
            lambda x: f"{x:.2f}" if pd.notna(x) else "0.00"
        )
        positive_changes['NMOS_now'] = positive_changes['NMOS_now'].apply(
            lambda x: f"{x:.2f}" if pd.notna(x) else "0.00"
        )
        positive_changes['NMOS_Difference'] = positive_changes['NMOS_Difference'].apply(
            lambda x: f"+{x:.2f}" if pd.notna(x) else "0.00"
        )
        positive_changes['Added_Quantity'] = positive_changes['Added_Quantity'].apply(
            lambda x: f"{int(x):,}" if pd.notna(x) and x > 0 else "0"
        )

        return positive_changes[[
            'Material Description', 
            'NMOS_previous', 
            'NMOS_now', 
            'NMOS_Difference', 
            'AMC_now',
            'Added_Quantity'
        ]].rename(columns={'AMC_now': 'AMC'})

    return None

# ---------------------------------------------------
# Utility Functions
# ---------------------------------------------------
def format_number_with_commas(x):
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
    """Calculate risk of stock out - ONLY for NMOS >= 1"""
    try:
        nmos = row['NMOS'] if pd.notna(row['NMOS']) else np.nan
        git_mos = row['GIT_MOS'] if pd.notna(row['GIT_MOS']) else 0
        lc_mos = row['LC_MOS'] if pd.notna(row['LC_MOS']) else 0
        wb_mos = row['WB_MOS'] if pd.notna(row['WB_MOS']) else 0
        tmd_mos = row['TMD_MOS'] if pd.notna(row['TMD_MOS']) else 0

        if pd.isna(nmos) or nmos < 1:
            return ""

        if 1 <= nmos < 2:
            return "Risk of Stock out"

        if 2 <= nmos < 4 and git_mos == 0:
            return "Risk of Stock out"

        if 4 <= nmos < 6 and git_mos == 0 and lc_mos == 0 and wb_mos == 0:
            return "Risk of Stock out"

        if 6 <= nmos < 7 and git_mos == 0 and lc_mos == 0 and wb_mos == 0 and tmd_mos == 0:
            return "Risk of Stock out"

        return ""
    except:
        return ""

def get_stock_out_recommendation(row):
    """Generate recommendation for Risk of Stock out"""
    try:
        git_mos = row.get('GIT_MOS', 0)
        lc_mos = row.get('LC_MOS', 0)
        wb_mos = row.get('WB_MOS', 0)
        tmd_mos = row.get('TMD_MOS', 0)
        git_po = row.get('GIT_PO', '')
        lc_po = row.get('LC_PO', '')
        wb_po = row.get('WB_PO', '')
        tmd_po = row.get('TMD_PO', '')

        git_mos = pd.to_numeric(git_mos, errors='coerce') if not isinstance(git_mos, (int, float)) else git_mos
        lc_mos = pd.to_numeric(lc_mos, errors='coerce') if not isinstance(lc_mos, (int, float)) else lc_mos
        wb_mos = pd.to_numeric(wb_mos, errors='coerce') if not isinstance(wb_mos, (int, float)) else wb_mos
        tmd_mos = pd.to_numeric(tmd_mos, errors='coerce') if not isinstance(tmd_mos, (int, float)) else tmd_mos

        git_mos = git_mos if pd.notna(git_mos) else 0
        lc_mos = lc_mos if pd.notna(lc_mos) else 0
        wb_mos = wb_mos if pd.notna(wb_mos) else 0
        tmd_mos = tmd_mos if pd.notna(tmd_mos) else 0

        if git_mos > 0:
            po_text = f" PO {git_po}" if git_po and str(git_po) != 'nan' and str(git_po) != '' else ""
            return f"🚚 Expedite shipment{po_text} - goods in transit"
        elif git_mos == 0 and lc_mos > 0:
            po_text = f" PO {lc_po}" if lc_po and str(lc_po) != 'nan' and str(lc_po) != '' else ""
            return f"📄 Expedite L/C opening process{po_text}"
        elif git_mos == 0 and lc_mos == 0 and wb_mos > 0:
            po_text = f" PO {wb_po}" if wb_po and str(wb_po) != 'nan' and str(wb_po) != '' else ""
            return f"💰 Expedite budget transfer{po_text}"
        elif git_mos == 0 and lc_mos == 0 and wb_mos == 0 and tmd_mos > 0:
            po_text = f" PO {tmd_po}" if tmd_po and str(tmd_po) != 'nan' and str(tmd_po) != '' else ""
            return f"📋 Expedite tender process{po_text}"
        else:
            return "🔄 Initiate additional quantity - no pipeline stock"
    except Exception as e:
        return f"⚠️ Review supply chain status"

def get_expiry_risk_recommendation(row, cv_category=None):
    """Generate recommendation for Expiry Risk"""
    try:
        if cv_category is None:
            cv_category = row.get('CV Category', 'Unknown')

        hubs_pct = row.get('Hubs%', 0)
        ho_pct = row.get('Head Office%', 0)
        expiry_details = row.get('Expiry Risk Details', '')

        hubs_pct = pd.to_numeric(hubs_pct, errors='coerce') if not isinstance(hubs_pct, (int, float)) else hubs_pct
        ho_pct = pd.to_numeric(ho_pct, errors='coerce') if not isinstance(ho_pct, (int, float)) else ho_pct
        hubs_pct = hubs_pct if pd.notna(hubs_pct) else 0
        ho_pct = ho_pct if pd.notna(ho_pct) else 0

        expiry_info = f" [Expiry: {expiry_details}]" if expiry_details and expiry_details != "" else ""

        if cv_category == 'High variation':
            return f"🔄 Redistribution required - high variation across hubs{expiry_info}"
        elif hubs_pct < ho_pct:
            return f"📦 Push stock to hubs - hubs have lower stock than head office{expiry_info}"
        else:
            return f"🌍 Donate to other countries - excess stock for donation{expiry_info}"

    except Exception as e:
        return f"⚠️ Review expiry risk - check batch details"

# ---------------------------------------------------
# Load ALL data
# ---------------------------------------------------
amc_pipeline_sheet_id = "14VvZ7IyOmpM4SZrY5_ArHDgLkeFN4inW"
branch_amc_sheet_id = "12Z5xqX32QIzjoN6tNvGbjutMheXx5US1"

df_external = load_national_data()
branch_amc_data = load_branch_amc_from_google_sheets(branch_amc_sheet_id)
google_sheets = load_google_sheets(amc_pipeline_sheet_id)

if df_external.empty:
    st.error("No data in Supabase. Please upload data through admin panel.")
    st.stop()

# ---------------------------------------------------
# User Info in Sidebar
# ---------------------------------------------------
with st.sidebar:
    st.title(f"Welcome, {st.session_state['user']['full_name']}!")
    st.caption(f"Role: {st.session_state['user']['role'].title()}")

    if st.session_state['user']['role'] == 'admin' and st.session_state.supabase_client:
        st.success("✅ Connected to Supabase")

    if st.session_state.notifications:
        st.markdown(f"### 🔔 Notifications ({len(st.session_state.notifications)})")
        for notif in st.session_state.notifications[:3]:
            st.warning(notif)

# ---------------------------------------------------
# Program Selection
# ---------------------------------------------------
if google_sheets:
    program_list = ["All"] + list(google_sheets.keys())
else:
    program_list = ["All"]

sheet_name = st.sidebar.selectbox("Program", program_list, index=0, key="program_selector")

subcategory_options = ["All"]
if sheet_name in PROGRAM_HIERARCHY and PROGRAM_HIERARCHY[sheet_name]["is_parent"]:
    subcategory_options = ["All"] + PROGRAM_HIERARCHY[sheet_name]["subcategories"]
    subcategory_filter = st.sidebar.selectbox("Subcategory", subcategory_options, key="subcategory_filter")
else:
    subcategory_filter = "All"
    st.session_state.subcategory_filter = "All"

if sheet_name != st.session_state.last_sheet_name:
    st.session_state.heatmap_page = 1
    st.session_state.last_sheet_name = sheet_name

if sheet_name == "All" and google_sheets:
    all_dfs = []
    for name, df_program in google_sheets.items():
        if df_program.empty:
            continue
        df_copy = df_program.copy()
        df_copy.columns = df_copy.columns.astype(str)
        if df_copy.columns.duplicated().any():
            df_copy = df_copy.loc[:, ~df_copy.columns.duplicated()]
        all_dfs.append(df_copy)

    if all_dfs:
        try:
            df_google = pd.concat(all_dfs, ignore_index=True, sort=False)
        except Exception as concat_error:
            st.error(f"Error combining sheets: {concat_error}")
            df_google = pd.DataFrame()
    else:
        df_google = pd.DataFrame()
elif google_sheets and sheet_name in google_sheets:
    df_google = google_sheets[sheet_name].copy()
    df_google.columns = df_google.columns.astype(str)
    if df_google.columns.duplicated().any():
        df_google = df_google.loc[:, ~df_google.columns.duplicated()]
else:
    df_google = pd.DataFrame()

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

if not df_google.empty and not df_external.empty:
    if 'Material Description' in df_external.columns and 'Material Description' in df_google.columns:
        df_external = df_external.drop_duplicates(subset=['Material Description'], keep='first')
        df_google = df_google.drop_duplicates(subset=['Material Description'], keep='first')
        df = df_external.merge(df_google, on="Material Description", how="right")
        df = df.drop_duplicates(subset=['Material Description'], keep='first')
    else:
        st.error("Material Description column missing for merge")
        df = df_external.copy()
else:
    df = df_external.copy()

if not df.empty:
    if 'S/N' in df.columns:
        df = df.drop(columns=['S/N'])

    text_columns = ['Status', 'Expiry', 'GIT_PO', 'LC_PO', 'WB_PO', 'TMD_PO']
    numeric_columns = [col for col in df.columns if col not in text_columns + ['Material Description']]

    for col in numeric_columns:
        if col in df.columns:
            try:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            except Exception:
                continue

    for col in text_columns:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str)

    if 'NSOH' in df.columns and 'AMC' in df.columns:
        nsoh = pd.to_numeric(df['NSOH'], errors='coerce')
        amc = pd.to_numeric(df['AMC'], errors='coerce')
        amc = amc.replace(0, np.nan)
        nmos = nsoh / amc
        nmos = nmos.replace([np.inf, -np.inf], np.nan)
        df['NMOS'] = nmos.round(2)

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

    if 'NMOS' in df.columns:
        df['Stock Status'] = df['NMOS'].apply(categorize_stock)
    else:
        df['Stock Status'] = ""

    if 'Hubs' in df.columns and 'Head Office' in df.columns and 'NSOH' in df.columns:
        hubs_vals = pd.to_numeric(df['Hubs'], errors='coerce').fillna(0)
        ho_vals = pd.to_numeric(df['Head Office'], errors='coerce').fillna(0)
        nsoh_vals = pd.to_numeric(df['NSOH'], errors='coerce')
        valid_mask = nsoh_vals.notna() & (nsoh_vals > 0)
        df['Hubs%'] = np.where(valid_mask, (hubs_vals / nsoh_vals * 100).round(1), np.nan)
        df['Head Office%'] = np.where(valid_mask, (ho_vals / nsoh_vals * 100).round(1), np.nan)
        df['Avail Gap'] = np.where(valid_mask, (df['Hubs%'] - df['Head Office%']).round(1), np.nan)
    else:
        df['Hubs%'] = np.nan
        df['Head Office%'] = np.nan
        df['Avail Gap'] = np.nan

    if not branch_amc_data.empty and 'Material Description' in branch_amc_data.columns:
        branch_cols = [col for col in df.columns if 'Branch' in col or col == 'Material Description']
        if len(branch_cols) > 1:
            stock_data = df[branch_cols].copy()
            merged_cv = pd.merge(stock_data, branch_amc_data, on='Material Description', how='inner', suffixes=('_stock', '_amc'))

            if not merged_cv.empty:
                branch_cols_list = [col for col in stock_data.columns if col != 'Material Description']
                amc_cols = [col for col in branch_amc_data.columns if col != 'Material Description']
                cv_calc_data = {'Material Description': merged_cv['Material Description']}

                for i in range(min(len(branch_cols_list), len(amc_cols))):
                    stock_col = branch_cols_list[i]
                    amc_col = amc_cols[i]
                    stock_vals = pd.to_numeric(merged_cv[f"{stock_col}_stock"], errors='coerce')
                    amc_vals = pd.to_numeric(merged_cv[f"{amc_col}_amc"], errors='coerce')
                    with np.errstate(divide='ignore', invalid='ignore'):
                        mos_vals = np.where(amc_vals > 0, stock_vals / amc_vals, np.nan)
                    cv_calc_data[stock_col] = mos_vals

                cv_df = pd.DataFrame(cv_calc_data)
                mos_cols_for_cv = [col for col in cv_df.columns if col != 'Material Description']
                cv_df['CV (%)'] = cv_df[mos_cols_for_cv].apply(lambda row: calculate_coefficient_of_variation(row), axis=1)
                cv_df['CV (%)'] = cv_df['CV (%)'].round(1)

                def categorize_cv(cv_value):
                    if pd.isna(cv_value):
                        return "Unknown"
                    elif cv_value < 50:
                        return "Low variation"
                    elif cv_value <= 100:
                        return "Moderate variation"
                    else:
                        return "High variation"

                cv_df['CV Category'] = cv_df['CV (%)'].apply(categorize_cv)
                df = df.merge(cv_df[['Material Description', 'CV Category']], on='Material Description', how='left')
            else:
                df['CV Category'] = "Unknown"
        else:
            df['CV Category'] = "Unknown"
    else:
        df['CV Category'] = "Unknown"

    # Handle subcategory filtering
    if sheet_name in PROGRAM_HIERARCHY:
        subcategory_list = PROGRAM_HIERARCHY[sheet_name]["subcategories"]

        df = filter_out_subcategory_headers(df, subcategory_list)

        subcategory_mapping = assign_subcategories_to_materials(df, subcategory_list)
        df['Assigned Subcategory'] = df['Material Description'].map(subcategory_mapping)

        if subcategory_filter != "All":
            df = df[df['Assigned Subcategory'] == subcategory_filter]
    else:
        df['Assigned Subcategory'] = None

    if 'NMOS' in df.columns:
        df['Risk of Stock'] = df.apply(calculate_risk, axis=1)
    else:
        df['Risk of Stock'] = ""

    expiry_data = df.apply(lambda row: parse_multiple_expiry_batches(row.get('Expiry', ''), row.get('AMC', np.nan)), axis=1)
    df['Has Expiry Risk'] = expiry_data.apply(lambda x: x[0])
    df['Expiry Risk Details'] = expiry_data.apply(lambda x: x[1])

    risk_types = []
    for idx, row in df.iterrows():
        risk_of_stock = row.get('Risk of Stock', '') == 'Risk of Stock out'
        expiry_risk = row.get('Has Expiry Risk', False)

        if risk_of_stock and expiry_risk:
            risk_types.append("Critical Risk")
        elif risk_of_stock:
            risk_types.append("Risk of Stock out")
        elif expiry_risk:
            risk_types.append("Expiry Risk")
        else:
            risk_types.append("")
    df['Risk Type'] = risk_types

    # Track stock changes
    if st.session_state.raw_previous_data is not None:
        stock_changes = calculate_stock_changes(df, st.session_state.raw_previous_data)
        if stock_changes is not None:
            st.session_state.nsoh_changes = stock_changes
        else:
            st.session_state.nsoh_changes = None
    else:
        st.session_state.nsoh_changes = None

    st.session_state.raw_previous_data = df.copy()

    display_df = df.copy()
    text_columns_to_preserve = ['Material Description', 'Stock Status', 'Risk Type', 'Status', 'Expiry', 'GIT_PO', 'LC_PO', 'WB_PO', 'TMD_PO', 'CV Category']

    if 'Hubs%' in display_df.columns:
        text_columns_to_preserve.append('Hubs%')
    if 'Head Office%' in display_df.columns:
        text_columns_to_preserve.append('Head Office%')
    if 'Avail Gap' in display_df.columns:
        text_columns_to_preserve.append('Avail Gap')

    for col in display_df.columns:
        if col not in text_columns_to_preserve:
            if col in ['NMOS', 'GIT_MOS', 'LC_MOS', 'WB_MOS', 'TMD_MOS', 'TMOS']:
                display_df[col] = display_df[col].apply(format_mos_with_decimals)
            elif col in ['Hubs%', 'Head Office%', 'Avail Gap']:
                display_df[col] = display_df[col].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "")
            else:
                display_df[col] = display_df[col].apply(format_number_with_commas)

    if 'Material Description' in df.columns:
        unique_materials = df['Material Description'].dropna().astype(str).unique()
        materials = ["All"] + sorted(unique_materials)

        statuses = ["All"] + sorted([s for s in df['Stock Status'].unique() if s != "" and pd.notna(s)]) if 'Stock Status' in df.columns else ["All"]

        risk_type_options = ["All", "Risk of Stock out", "Expiry Risk", "Critical Risk"]
        risk_type_filter = st.sidebar.selectbox("Risk Type", risk_type_options, index=risk_type_options.index(st.session_state.risk_type_filter) if st.session_state.risk_type_filter in risk_type_options else 0)
        st.session_state.risk_type_filter = risk_type_filter

        material_filter = st.sidebar.selectbox("Material Description", materials)
        status_filter = st.sidebar.selectbox("Stock Status", statuses)

        df_filtered = df.copy()
        display_df_filtered = display_df.copy()

        if material_filter != "All":
            df_filtered = df_filtered[df_filtered['Material Description'] == material_filter]
            display_df_filtered = display_df_filtered[display_df_filtered['Material Description'] == material_filter]
            if material_filter not in st.session_state.material_views:
                st.session_state.material_views[material_filter] = 0
            st.session_state.material_views[material_filter] += 1

            if 'user' in st.session_state:
                st.session_state.user_activity.append({
                    'user': st.session_state['user']['email'],
                    'role': st.session_state['user']['role'],
                    'action': 'view_material',
                    'material': material_filter,
                    'timestamp': datetime.now().isoformat()
                })

        if status_filter != "All" and 'Stock Status' in df_filtered.columns:
            df_filtered = df_filtered[df_filtered['Stock Status'] == status_filter]
            display_df_filtered = display_df_filtered[display_df_filtered['Stock Status'] == status_filter]

        if risk_type_filter == "Risk of Stock out":
            df_filtered = df_filtered[df_filtered['Risk Type'] == "Risk of Stock out"]
            display_df_filtered = display_df_filtered[display_df_filtered['Risk Type'] == "Risk of Stock out"]
        elif risk_type_filter == "Expiry Risk":
            df_filtered = df_filtered[df_filtered['Risk Type'] == "Expiry Risk"]
            display_df_filtered = display_df_filtered[display_df_filtered['Risk Type'] == "Expiry Risk"]
        elif risk_type_filter == "Critical Risk":
            df_filtered = df_filtered[df_filtered['Risk Type'] == "Critical Risk"]
            display_df_filtered = display_df_filtered[display_df_filtered['Risk Type'] == "Critical Risk"]
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
    page = st.sidebar.radio("Navigation", ["Dashboard", "Supply Planning", "Executive Summary", "Admin Panel", "Profile"])
else:
    page = st.sidebar.radio("Navigation", ["Dashboard", "Supply Planning", "Executive Summary", "Profile"])

# ---------------------------------------------------
# Data Refresh Controls
# ---------------------------------------------------
st.sidebar.divider()
st.sidebar.markdown("### 🔄 Data Updates")
st.sidebar.caption(f"📅 Data as of: {st.session_state.data_timestamp.strftime('%Y-%m-%d %H:%M:%S')}")

if st.session_state['user']['role'] == 'admin':
    st.sidebar.info("📊 Data Sources:\n- Supabase: Real-time\n- Google Sheets (AMC/Pipeline): Cached 5 min\n- Google Sheets (Branch AMC): Cached 5 min")

auto_refresh = st.sidebar.checkbox("Auto-refresh every 5 minutes", value=st.session_state.auto_refresh)
if auto_refresh != st.session_state.auto_refresh:
    st.session_state.auto_refresh = auto_refresh

if st.session_state.auto_refresh:
    time_since_refresh = (datetime.now() - st.session_state.data_timestamp).total_seconds()
    if time_since_refresh > 300:
        st.cache_data.clear()
        st.session_state.data_timestamp = datetime.now()
        st.rerun()

if st.sidebar.button("🔄 Refresh Now", use_container_width=True, type="primary"):
    st.cache_data.clear()
    st.session_state.data_timestamp = datetime.now()
    st.rerun()

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

        table_info = get_table_info()
        if table_info:
            st.info(f"Current data: {table_info['rows']} rows, {table_info['columns']} columns")

        st.markdown("#### Upload New Data")
        st.caption("Upload Excel or CSV file with your data")

        uploaded_file = st.file_uploader("Choose Excel or CSV file", type=['xlsx', 'csv', 'xls'], key='data_upload')

        if uploaded_file:
            try:
                if uploaded_file.name.endswith('.csv'):
                    df_upload = pd.read_csv(uploaded_file)
                else:
                    df_upload = pd.read_excel(uploaded_file)

                st.write(f"Preview of data to upload ({len(df_upload)} rows):")
                st.dataframe(df_upload.head())

                col1, col2 = st.columns(2)
                with col1:
                    if st.button("📤 Upload to Supabase", use_container_width=True, type="primary"):
                        with st.spinner("Validating and uploading..."):
                            if validate_upload_data(df_upload):
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
elif page == "Supply Planning":
    # ===================================================
    # SUPPLY PLANNING PAGE (FIXED)
    # ===================================================
    st.markdown("<h1 style='font-size: 32px; font-weight: bold; font-family: Times New Roman;' class='gradient-text'>📦 Supply Planning - Procurement Requirements</h1>", unsafe_allow_html=True)

    with st.expander("📖 Parameters & Instructions", expanded=False):
        st.markdown("""
        **Supply Planning Parameters:**
        - Lead Time = 6 months (time from order placement to delivery)
        - Safety Stock = 2 months (buffer stock)
        - Maximum Stock Level = 18 months
        - Reorder Point = Lead Time + Safety Stock = 8 months

        **Order Quantity Formula:**
        - Order Quantity = (18 - TMOS) × AMC (ONLY if 18 - TMOS is POSITIVE)
        - MOS Needed = 18 - TMOS (months of stock required to reach maximum)

        **TMOS = NMOS + Pipeline MOS** (GIT_MOS + LC_MOS + WB_MOS + TMD_MOS)
        """)

    if 'TMOS' in df_filtered.columns and 'AMC' in df_filtered.columns and 'NMOS' in df_filtered.columns:
        supply_plan = []
        current_date = datetime.now()

        def get_future_date(months_from_now):
            target_date = current_date
            months_int = int(months_from_now)
            new_year = target_date.year + ((target_date.month + months_int - 1) // 12)
            new_month = ((target_date.month + months_int - 1) % 12) + 1
            target_date = target_date.replace(year=new_year, month=new_month, day=1)
            return target_date

        def get_readable_order_by(months_until_order):
            if months_until_order <= 0:
                return "Now"
            target_date = get_future_date(months_until_order)
            month_name = target_date.strftime('%B')
            year = target_date.year
            if target_date.day <= 15:
                period = "beginning"
            else:
                period = "end"
            if target_date.year == current_date.year:
                return f"{period} of {month_name}"
            else:
                return f"{period} of {month_name} {year}"

        for idx, row in df_filtered.iterrows():
            tmos = row.get('TMOS', 0)
            amc = row.get('AMC', 0)
            nmos = row.get('NMOS', 0)
            material = row['Material Description']

            git_mos = row.get('GIT_MOS', 0)
            lc_mos = row.get('LC_MOS', 0)
            wb_mos = row.get('WB_MOS', 0)
            tmd_mos = row.get('TMD_MOS', 0)

            try:
                tmos = float(tmos) if pd.notna(tmos) else 0
                amc = float(amc) if pd.notna(amc) else 0
                nmos = float(nmos) if pd.notna(nmos) else 0
                git_mos = float(git_mos) if pd.notna(git_mos) else 0
                lc_mos = float(lc_mos) if pd.notna(lc_mos) else 0
                wb_mos = float(wb_mos) if pd.notna(wb_mos) else 0
                tmd_mos = float(tmd_mos) if pd.notna(tmd_mos) else 0
            except:
                continue

            pipeline_mos = git_mos + lc_mos + wb_mos + tmd_mos
            mos_needed = 18 - tmos

            if mos_needed > 0 and amc > 0:
                order_quantity = int(mos_needed * amc)

                if tmos <= 8:
                    urgency = "🔴 CRITICAL"
                    action = f"Place this {order_quantity:,} units IMMEDIATELY"
                    order_by = "Now"
                    expected_delivery = get_future_date(6)
                else:
                    months_until_order = round(tmos - 8, 1)
                    order_by_readable = get_readable_order_by(months_until_order)
                    action = f"Place this {order_quantity:,} units by {order_by_readable}"
                    order_by = order_by_readable
                    total_months_to_delivery = months_until_order + 6
                    expected_delivery = get_future_date(total_months_to_delivery)
                    urgency = "🟡 PLAN"  # <-- FIXED: Added this line

                pipeline_parts = []
                if git_mos > 0:
                    pipeline_parts.append(f"GIT: {round(git_mos,1)}m")
                if lc_mos > 0:
                    pipeline_parts.append(f"LC: {round(lc_mos,1)}m")
                if wb_mos > 0:
                    pipeline_parts.append(f"WB: {round(wb_mos,1)}m")
                if tmd_mos > 0:
                    pipeline_parts.append(f"TMD: {round(tmd_mos,1)}m")
                pipeline_status = ", ".join(pipeline_parts) if pipeline_parts else "No pipeline stock"

                supply_plan.append({
                    'Material': material,
                    'Current TMOS': round(tmos, 2),
                    'NMOS': round(nmos, 2),
                    'Pipeline': round(pipeline_mos, 2),
                    'Pipeline Status': pipeline_status,
                    'AMC': int(amc),
                    'MOS Needed': round(mos_needed, 2),
                    'Order Quantity': f"{order_quantity:,}",
                    'Urgency': urgency,
                    'Action': action,
                    'Order By': order_by,
                    'Expected Delivery': expected_delivery.strftime('%b %Y')
                })

        if supply_plan:
            supply_df = pd.DataFrame(supply_plan).sort_values('Current TMOS', ascending=True)

            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                st.metric("📋 Materials to Order", len(supply_df))
            with col2:
                critical = len([s for s in supply_plan if s['Urgency'] == '🔴 CRITICAL'])
                st.metric("🔴 Critical", critical, delta="Order Now")
            with col3:
                plan = len([s for s in supply_plan if s['Urgency'] == '🟡 PLAN'])
                st.metric("🟡 Plan", plan, delta="Future Order")
            with col4:
                total_quantity = sum([int(s['Order Quantity'].replace(',', '')) for s in supply_plan])
                st.metric("📦 Total Order Qty", f"{total_quantity:,} units")
            with col5:
                avg_mos_needed = supply_df['MOS Needed'].mean()
                st.metric("📊 Avg MOS Needed", f"{round(avg_mos_needed, 1)} months")

            st.dataframe(
                supply_df[['Material', 'Current TMOS', 'NMOS', 'Pipeline', 'AMC', 'MOS Needed', 'Order Quantity', 'Urgency', 'Action', 'Order By', 'Expected Delivery']],
                use_container_width=True,
                hide_index=True
            )

            st.download_button(
                label="📥 Download Order Quantity Plan (CSV)",
                data=supply_df.to_csv(index=False),
                file_name=f"order_quantity_plan_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )

            # Action Plan Table
            st.markdown("---")
            st.markdown("<h3 style='font-size: 24px; font-weight: bold;'>📝 Action Plan - Materials Requiring Attention</h3>", unsafe_allow_html=True)

            action_plan = []
            for idx, row in df_filtered.iterrows():
                material = row['Material Description']
                nmos = row.get('NMOS', 0)
                tmos = row.get('TMOS', 0)
                nsoh = row.get('NSOH', 0)
                amc = row.get('AMC', 0)
                stock_status = row.get('Stock Status', '')
                risk_type = row.get('Risk Type', '')
                has_expiry_risk = row.get('Has Expiry Risk', False)
                risk_of_stock = row.get('Risk of Stock', '')

                git_mos = row.get('GIT_MOS', 0)
                lc_mos = row.get('LC_MOS', 0)
                wb_mos = row.get('WB_MOS', 0)
                tmd_mos = row.get('TMD_MOS', 0)

                try:
                    nmos = float(nmos) if pd.notna(nmos) else 0
                    tmos = float(tmos) if pd.notna(tmos) else 0
                    nsoh = float(nsoh) if pd.notna(nsoh) else 0
                    amc = float(amc) if pd.notna(amc) else 0
                except:
                    continue

                if amc == 0 and not has_expiry_risk:
                    continue

                identified_problem = []

                if stock_status == 'Stock Out':
                    identified_problem.append("Stock Out")
                elif risk_of_stock == 'Risk of Stock out' or risk_type == 'Risk of Stock out':
                    identified_problem.append("Risk of Stock Out")
                elif has_expiry_risk or risk_type == 'Expiry Risk':
                    identified_problem.append("Expiry Risk")
                elif nmos < 6 and amc > 0:
                    identified_problem.append("Below minimum stock level")
                elif tmos < 18 and amc > 0:
                    identified_problem.append("Stock on pipeline is not enough to reach maximum stock level")

                if identified_problem:
                    problem_text = ", ".join(identified_problem)

                    if stock_status == 'Stock Out' or risk_of_stock == 'Risk of Stock out' or risk_type == 'Risk of Stock out':
                        action_point = get_stock_out_recommendation(row)
                    elif has_expiry_risk or risk_type == 'Expiry Risk':
                        action_point = get_expiry_risk_recommendation(row)
                    elif (nmos < 6 or tmos < 18) and amc > 0:
                        order_qty = int((18 - tmos) * amc)
                        action_point = f"Place order for {order_qty:,} units to reach maximum stock level"
                    else:
                        action_point = "Monitor stock levels"

                    if "Initiate additional quantity" in action_point:
                        order_qty = int((18 - tmos) * amc)
                        action_point = f"Place order for {order_qty:,} units to reach maximum stock level"

                    # Responsible Body Mapping
                    responsible_body = ""
                    if "Expedite shipment" in action_point:
                        responsible_body = "EPSS_CMD, EPSS_DMD"
                    elif "Expedite L/C" in action_point:
                        responsible_body = "EPSS_CMD, EPSS_DMD"
                    elif "Expedite tender" in action_point:
                        responsible_body = "EPSS_PMD, EPSS_DMD"
                    elif "Expedite budget" in action_point:
                        responsible_body = "EPSS_Finance, MOH"
                    elif "Place order" in action_point:
                        responsible_body = "MOH"
                    elif has_expiry_risk or risk_type == 'Expiry Risk':
                        responsible_body = "EPSS_DMD"
                    else:
                        responsible_body = "EPSS_DMD"

                    # Due Date
                    current_date = datetime.now()
                    current_month = current_date.month
                    current_year = current_date.year

                    def get_end_of_month_date(year, month):
                        year_int = int(year)
                        month_int = int(month)
                        if month_int == 12:
                            next_month = 1
                            next_year = year_int + 1
                        else:
                            next_month = month_int + 1
                            next_year = year_int
                        last_day = (datetime(next_year, next_month, 1) - timedelta(days=1)).day
                        return datetime(year_int, month_int, last_day)

                    if "Place order" in action_point:
                        if tmos <= 8:
                            end_of_month = get_end_of_month_date(current_year, current_month)
                            due_date = end_of_month.strftime('Before %d %b %Y')
                        else:
                            due_date = "Plan for next quarter"
                    elif has_expiry_risk or risk_type == 'Expiry Risk':
                        due_date = "ASAP"
                    elif "Expedite" in action_point:
                        end_of_month = get_end_of_month_date(current_year, current_month)
                        due_date = end_of_month.strftime('Before %d %b %Y')
                    else:
                        due_date = "Review and act"

                    nsoh_formatted = f"{int(nsoh):,}" if nsoh > 0 else "0"
                    amc_formatted = f"{int(amc):,}" if amc > 0 else "N/A"

                    action_plan.append({
                        'Material': material,
                        'NSOH': nsoh_formatted,
                        'AMC': amc_formatted,
                        'NMOS': round(nmos, 2) if amc > 0 else 0,
                        'TMOS': round(tmos, 2),
                        'Identified Problem': problem_text,
                        'Action Point': action_point,
                        'Responsible Body': responsible_body,
                        'Due Date': due_date
                    })

            if action_plan:
                action_df = pd.DataFrame(action_plan)

                total_items = len(action_df)
                stock_out_count = len([a for a in action_plan if 'Stock Out' in a['Identified Problem']])
                risk_count = len([a for a in action_plan if 'Risk of Stock Out' in a['Identified Problem']])
                expiry_count = len([a for a in action_plan if 'Expiry Risk' in a['Identified Problem']])

                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("📋 Total Action Items", total_items)
                with col2:
                    st.metric("🔴 Stock Out", stock_out_count)
                with col3:
                    st.metric("🟡 Risk of Stock Out", risk_count)
                with col4:
                    st.metric("⚠️ Expiry Risk", expiry_count)

                st.dataframe(
                    action_df,
                    column_config={
                        'Material': st.column_config.TextColumn('Material', width=200),
                        'NSOH': st.column_config.TextColumn('NSOH', width=100),
                        'AMC': st.column_config.TextColumn('AMC', width=80),
                        'NMOS': st.column_config.NumberColumn('NMOS', width=80, format="%.2f"),
                        'TMOS': st.column_config.NumberColumn('TMOS', width=80, format="%.2f"),
                        'Identified Problem': st.column_config.TextColumn('Problem', width=180),
                        'Action Point': st.column_config.TextColumn('Action Point', width=300),
                        'Responsible Body': st.column_config.TextColumn('Responsible Body', width=180),
                        'Due Date': st.column_config.TextColumn('Due Date', width=120)
                    },
                    use_container_width=True,
                    hide_index=True,
                    height=min(600, (len(action_df) + 1) * 45)
                )

                st.download_button(
                    label="📥 Download Action Plan (CSV)",
                    data=action_df.to_csv(index=False),
                    file_name=f"action_plan_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            else:
                st.success("✅ No action items identified")
        else:
            st.success("✅ No procurement needed. All materials have TMOS ≥ 18 months.")
    else:
        st.info("TMOS, NMOS, or AMC data not available for supply planning")

    st.stop()

elif page == "Executive Summary":
    # ===================================================
    # EXECUTIVE SUMMARY PAGE (FULLY FIXED)
    # ===================================================
    st.markdown("<h1 style='font-size: 36px; font-weight: bold; font-family: Times New Roman;' class='gradient-text'>📊 Executive Summary Dashboard</h1>", unsafe_allow_html=True)
    st.caption(f"Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Program: {sheet_name if sheet_name != 'All' else 'All Programs'}")

    # SECTION 1: PERFORMANCE METRICS
    st.markdown("---")
    st.markdown("<h2 style='font-size: 28px; font-weight: bold;'>🎯 1. Performance Metrics</h2>", unsafe_allow_html=True)

    if not df_filtered.empty and 'NMOS' in df_filtered.columns:
        nmos_values = pd.to_numeric(df_filtered['NMOS'], errors='coerce').dropna()

        total_materials = len(df_filtered)
        stock_out_count = len(df_filtered[df_filtered['Stock Status'] == 'Stock Out'])
        understock_count = len(df_filtered[df_filtered['Stock Status'] == 'Understock'])
        normal_count = len(df_filtered[df_filtered['Stock Status'] == 'Normal Stock'])
        overstock_count = len(df_filtered[df_filtered['Stock Status'] == 'Overstock'])

        availability = (nmos_values > 1).mean() * 100 if len(nmos_values) > 0 else 0
        sap_achievement = ((nmos_values >= 6) & (nmos_values <= 18)).mean() * 100 if len(nmos_values) > 0 else 0

        # Calculate Avail. Gap (Hubs% - Head Office%)
        if 'Avail Gap' in df_filtered.columns:
            avail_gap_values = pd.to_numeric(df_filtered['Avail Gap'], errors='coerce').dropna()
            avg_avail_gap = avail_gap_values.mean() if len(avail_gap_values) > 0 else 0
        else:
            avg_avail_gap = 0

        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 15px; padding: 20px; color: white;'>
                <h3 style='margin:0; font-size: 14px; opacity:0.9'>AVAILABILITY</h3>
                <p style='font-size: 36px; font-weight: bold; margin:5px 0'>{availability:.1f}%</p>
                <p style='margin:0; font-size: 12px; opacity:0.8'>Target: 100%</p>
            </div>
            """, unsafe_allow_html=True)
        with col2:
            st.markdown(f"""
            <div style='background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); border-radius: 15px; padding: 20px; color: white;'>
                <h3 style='margin:0; font-size: 14px; opacity:0.9'>SAP ACHIEVEMENT</h3>
                <p style='font-size: 36px; font-weight: bold; margin:5px 0'>{sap_achievement:.1f}%</p>
                <p style='margin:0; font-size: 12px; opacity:0.8'>Target: 65%</p>
            </div>
            """, unsafe_allow_html=True)
        with col3:
            st.markdown(f"""
            <div style='background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); border-radius: 15px; padding: 20px; color: white;'>
                <h3 style='margin:0; font-size: 14px; opacity:0.9'>AVAIL. GAP</h3>
                <p style='font-size: 36px; font-weight: bold; margin:5px 0'>{avg_avail_gap:.1f}%</p>
                <p style='margin:0; font-size: 12px; opacity:0.8'>Hubs% - Head Office%</p>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # Quick Stats - 5 columns
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("📦 Total Materials", total_materials)
        with col2:
            st.metric("🔴 Stock Out", stock_out_count)
        with col3:
            st.metric("🟡 Understock", understock_count)
        with col4:
            st.metric("🟢 Normal Stock", normal_count)
        with col5:
            st.metric("🔵 Overstock", overstock_count)

        # SECTION 2: RISK SUMMARY (Markdown Table - 3 columns)
        st.markdown("---")
        st.markdown("<h2 style='font-size: 28px; font-weight: bold;'>⚠️ 2. Risk Summary</h2>", unsafe_allow_html=True)

        critical_risk = len(df_filtered[df_filtered['Risk Type'] == 'Critical Risk'])
        risk_stock_out = len(df_filtered[df_filtered['Risk Type'] == 'Risk of Stock out'])
        expiry_risk = len(df_filtered[df_filtered['Risk Type'] == 'Expiry Risk'])

        st.markdown(f"""
        <table style='width: 100%; border-collapse: collapse; margin: 20px 0;'>
            <tr style='background-color: #ff4444; color: white; text-align: center;'>
                <th style='padding: 15px; font-size: 18px; border-radius: 10px 0 0 0;'>🔴 CRITICAL RISK</th>
                <th style='padding: 15px; font-size: 18px; background-color: #ffa500;'>🟡 RISK OF STOCK OUT</th>
                <th style='padding: 15px; font-size: 18px; background-color: #ff9800; border-radius: 0 10px 0 0;'>⚠️ EXPIRY RISK</th>
            </tr>
            <tr style='text-align: center; background-color: #f8f9fa;'>
                <td style='padding: 20px; font-size: 42px; font-weight: bold; color: #ff4444;'>{critical_risk}</td>
                <td style='padding: 20px; font-size: 42px; font-weight: bold; color: #ffa500;'>{risk_stock_out}</td>
                <td style='padding: 20px; font-size: 42px; font-weight: bold; color: #ff9800;'>{expiry_risk}</td>
            </tr>
            <tr style='text-align: center; background-color: #ffffff;'>
                <td style='padding: 10px; font-size: 14px;'>require URGENT attention</td>
                <td style='padding: 10px; font-size: 14px;'>need expediting</td>
                <td style='padding: 10px; font-size: 14px;'>approaching expiration</td>
            </tr>
        </table>
        """, unsafe_allow_html=True)

        # SECTION 3: STOCK DISTRIBUTION ACROSS HUBS BY MOS
        st.markdown("---")
        st.markdown("<h2 style='font-size: 28px; font-weight: bold;'>📍 3. Stock Distribution Across Hubs by MOS</h2>", unsafe_allow_html=True)

        if 'CV Category' in df_filtered.columns:
            cv_counts = df_filtered['CV Category'].value_counts()
            total_cv_materials = len(df_filtered[df_filtered['CV Category'] != 'Unknown'])

            low_variation = cv_counts.get('Low variation', 0)
            moderate_variation = cv_counts.get('Moderate variation', 0)
            high_variation = cv_counts.get('High variation', 0)

            low_pct = (low_variation / total_cv_materials * 100) if total_cv_materials > 0 else 0
            mod_pct = (moderate_variation / total_cv_materials * 100) if total_cv_materials > 0 else 0
            high_pct = (high_variation / total_cv_materials * 100) if total_cv_materials > 0 else 0

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("📊 Total Materials", total_cv_materials)
            with col2:
                st.metric("🟢 Low Variation (<50%)", f"{low_variation} ({low_pct:.1f}%)")
            with col3:
                st.metric("🟡 Moderate Variation (50-100%)", f"{moderate_variation} ({mod_pct:.1f}%)")
            with col4:
                st.metric("🔴 High Variation (>100%)", f"{high_variation} ({high_pct:.1f}%)")
        else:
            st.info("CV Category data not available")

        # SECTION 4: BRANCH RANKING
        st.markdown("---")
        st.markdown("<h2 style='font-size: 28px; font-weight: bold;'>🏆 4. Branch Ranking by Stock Availability</h2>", unsafe_allow_html=True)
        st.caption("Availability = materials with NMOS ≥ 0.5 (at least 2 weeks of stock)")

        if branch_amc_data is not None and not branch_amc_data.empty:
            branch_stock_cols = [col for col in df.columns if 'Branch' in col and col != 'Material Description']
            amc_branch_cols = [col for col in branch_amc_data.columns if col != 'Material Description']
            rankings = []

            for amc_branch in amc_branch_cols:
                stock_col = None
                for bc in branch_stock_cols:
                    if amc_branch == bc:
                        stock_col = bc
                        break

                if stock_col:
                    try:
                        merged = pd.merge(
                            df[['Material Description', stock_col]], 
                            branch_amc_data[['Material Description', amc_branch]], 
                            on='Material Description', how='inner'
                        )
                        if not merged.empty:
                            stock_values = pd.to_numeric(merged[stock_col + '_x'], errors='coerce').fillna(0)
                            amc_values = pd.to_numeric(merged[amc_branch + '_y'], errors='coerce').fillna(1)
                            amc_values = amc_values.replace(0, 1)
                            branch_nmos = stock_values / amc_values
                            availability_count = np.sum(branch_nmos >= 0.5)
                            total_materials_branch = len(branch_nmos)
                            availability_score = (availability_count / total_materials_branch * 100) if total_materials_branch > 0 else 0
                            rankings.append({
                                'Branch': amc_branch,
                                'Score': availability_score
                            })
                    except Exception:
                        continue

            if rankings:
                rankings_df = pd.DataFrame(rankings).sort_values('Score', ascending=False)
                top_branch = rankings_df.iloc[0]['Branch']
                bottom_branch = rankings_df.iloc[-1]['Branch']
                top_score = rankings_df.iloc[0]['Score']
                bottom_score = rankings_df.iloc[-1]['Score']

                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"""
                    <div style='background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); border-radius: 15px; padding: 20px; color: white; text-align: center;'>
                        <h3 style='margin:0; font-size: 16px;'>🏆 TOP BRANCH</h3>
                        <p style='font-size: 24px; font-weight: bold; margin: 10px 0;'>{top_branch}</p>
                        <p style='margin:0; font-size: 14px;'>Availability: {top_score:.1f}%</p>
                    </div>
                    """, unsafe_allow_html=True)
                with col2:
                    st.markdown(f"""
                    <div style='background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); border-radius: 15px; padding: 20px; color: white; text-align: center;'>
                        <h3 style='margin:0; font-size: 16px;'>📉 BOTTOM BRANCH</h3>
                        <p style='font-size: 24px; font-weight: bold; margin: 10px 0;'>{bottom_branch}</p>
                        <p style='margin:0; font-size: 14px;'>Availability: {bottom_score:.1f}%</p>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("No branch ranking data available")
        else:
            st.info("Branch AMC data not available")

        # SECTION 5: TOP AND BOTTOM PROGRAM
        st.markdown("---")
        st.markdown("<h2 style='font-size: 28px; font-weight: bold;'>📊 5. Program Performance</h2>", unsafe_allow_html=True)

        if google_sheets and len(google_sheets) > 0:
            program_metrics = []
            for program_name, program_df in google_sheets.items():
                if program_df.empty or 'Material Description' not in program_df.columns:
                    continue

                merged = program_df[['Material Description']].merge(
                    df[['Material Description', 'NMOS']], on='Material Description', how='left'
                )
                nmos_values = pd.to_numeric(merged['NMOS'], errors='coerce').dropna()

                if len(nmos_values) > 0:
                    availability_prog = (nmos_values > 1).mean() * 100
                    program_metrics.append({
                        'Program': program_name,
                        'Availability': availability_prog
                    })

            if program_metrics:
                prog_df = pd.DataFrame(program_metrics).sort_values('Availability', ascending=False)
                top_program = prog_df.iloc[0]['Program']
                top_availability = prog_df.iloc[0]['Availability']
                bottom_program = prog_df.iloc[-1]['Program']
                bottom_availability = prog_df.iloc[-1]['Availability']

                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"""
                    <div style='background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); border-radius: 15px; padding: 20px; color: white; text-align: center;'>
                        <h3 style='margin:0; font-size: 16px;'>🥇 TOP PROGRAM</h3>
                        <p style='font-size: 22px; font-weight: bold; margin: 10px 0;'>{top_program}</p>
                        <p style='margin:0; font-size: 14px;'>Availability: {top_availability:.1f}%</p>
                    </div>
                    """, unsafe_allow_html=True)
                with col2:
                    st.markdown(f"""
                    <div style='background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); border-radius: 15px; padding: 20px; color: white; text-align: center;'>
                        <h3 style='margin:0; font-size: 16px;'>📉 BOTTOM PROGRAM</h3>
                        <p style='font-size: 22px; font-weight: bold; margin: 10px 0;'>{bottom_program}</p>
                        <p style='margin:0; font-size: 14px;'>Availability: {bottom_availability:.1f}%</p>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("No program data available for comparison")
        else:
            st.info("Google Sheets data not available")

    # Download button
    st.markdown("---")

    # Create summary text for download - SIMPLE APPROACH without nested conditionals
    summary_lines = []
    summary_lines.append("EXECUTIVE SUMMARY REPORT")
    summary_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    summary_lines.append(f"Program: {sheet_name if sheet_name != 'All' else 'All Programs'}")
    summary_lines.append("")
    summary_lines.append("PERFORMANCE METRICS")

    if 'availability' in locals():
        summary_lines.append(f"- Availability: {availability:.1f}% (Target: 100%)")
        summary_lines.append(f"- SAP Achievement: {sap_achievement:.1f}% (Target: 65%)")
        summary_lines.append(f"- Avail. Gap: {avg_avail_gap:.1f}% (Hubs% - Head Office%)")
        summary_lines.append(f"- Total Materials: {total_materials}")
        summary_lines.append(f"- Stock Out: {stock_out_count}")
        summary_lines.append(f"- Understock: {understock_count}")
        summary_lines.append(f"- Normal Stock: {normal_count}")
        summary_lines.append(f"- Overstock: {overstock_count}")
        summary_lines.append("")
        summary_lines.append("RISK SUMMARY")
        summary_lines.append(f"- Critical Risk: {critical_risk} materials require URGENT attention")
        summary_lines.append(f"- Risk of Stock Out: {risk_stock_out} materials need expediting")
        summary_lines.append(f"- Expiry Risk: {expiry_risk} materials approaching expiration")
        summary_lines.append("")
        summary_lines.append("STOCK DISTRIBUTION ACROSS HUBS")
        summary_lines.append(f"- Total Materials: {total_cv_materials if 'total_cv_materials' in locals() else 0}")

        if 'low_variation' in locals():
            low_pct_val = low_pct if 'low_pct' in locals() else 0
            mod_pct_val = mod_pct if 'mod_pct' in locals() else 0
            high_pct_val = high_pct if 'high_pct' in locals() else 0
            summary_lines.append(f"- Low Variation (<50%): {low_variation} ({low_pct_val:.1f}%)")
            summary_lines.append(f"- Moderate Variation (50-100%): {moderate_variation} ({mod_pct_val:.1f}%)")
            summary_lines.append(f"- High Variation (>100%): {high_variation} ({high_pct_val:.1f}%)")

        summary_lines.append("")
        summary_lines.append("BRANCH RANKING")
        if 'top_branch' in locals():
            summary_lines.append(f"- Top Branch: {top_branch} ({top_score:.1f}%)")
            summary_lines.append(f"- Bottom Branch: {bottom_branch} ({bottom_score:.1f}%)")
        else:
            summary_lines.append("- No branch ranking data available")

        summary_lines.append("")
        summary_lines.append("PROGRAM PERFORMANCE")
        if 'top_program' in locals():
            summary_lines.append(f"- Top Program: {top_program} ({top_availability:.1f}%)")
            summary_lines.append(f"- Bottom Program: {bottom_program} ({bottom_availability:.1f}%)")
        else:
            summary_lines.append("- No program data available")

    summary_text = "\n".join(summary_lines)

    st.download_button(
        label="📥 Download Executive Summary Report",
        data=summary_text,
        file_name=f"executive_summary_{datetime.now().strftime('%Y%m%d')}.txt",
        mime="text/plain",
        use_container_width=True
    )

    st.stop()

# ===================================================
# MAIN DASHBOARD (with 5 tabs including Advanced Analytics)
# ===================================================
else:
    # MAIN DASHBOARD
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown("<h1 style='font-size: 32px; font-weight: bold; font-family: Times New Roman;' class='gradient-text'>Health Program Medicines Dashboard</h1>", unsafe_allow_html=True)
    with col2:
        st.markdown("<p style='font-size: 10px; color: #666; margin-bottom: 0;'>🎨 Display Settings</p>", unsafe_allow_html=True)
        view_mode = st.selectbox("View Mode", ["Table View", "Card View"], index=0 if st.session_state.view_mode == "table" else 1, label_visibility="collapsed")
        st.session_state.view_mode = "table" if view_mode == "Table View" else "card"

    # 5-COLUMN QUICK STATS
    if not df_filtered.empty:
        col1, col2, col3, col4, col5 = st.columns(5)

        total_items = len(df_filtered)
        stock_out = len(df_filtered[df_filtered['Stock Status'] == 'Stock Out']) if 'Stock Status' in df_filtered.columns else 0
        understock = len(df_filtered[df_filtered['Stock Status'] == 'Understock']) if 'Stock Status' in df_filtered.columns else 0
        normal = len(df_filtered[df_filtered['Stock Status'] == 'Normal Stock']) if 'Stock Status' in df_filtered.columns else 0
        overstock = len(df_filtered[df_filtered['Stock Status'] == 'Overstock']) if 'Stock Status' in df_filtered.columns else 0

        if sheet_name == "All":
            program_display = "All Programs"
        elif subcategory_filter != "All":
            program_display = f"{sheet_name} - {subcategory_filter}"
        else:
            program_display = sheet_name

        with col1:
            st.metric(f"📊 {program_display} Total Items", total_items)
        with col2:
            st.metric("🔴 Stock Out", stock_out, delta=f"-{stock_out}" if stock_out > 0 else "0", delta_color="inverse")
        with col3:
            st.metric("🟡 Understock", understock, delta=f"-{understock}" if understock > 0 else "0", delta_color="inverse")
        with col4:
            st.metric("🟢 Normal Stock", normal, delta=f"+{normal}" if normal > 0 else "0", delta_color="normal")
        with col5:
            st.metric("🔵 Overstock", overstock, delta=f"-{overstock}" if overstock > 0 else "0", delta_color="inverse")

    # TABS (Now 5 tabs including Advanced Analytics)
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📋 Stock Status Table", 
        "📈 KPIs & Analytics", 
        "💡 Decision Briefs", 
        "📍 Hubs Distribution",
        "🔬 Advanced Analytics"
    ])

    # TAB 1 - Stock Status Table
    with tab1:
        st.markdown("<h3 style='font-size: 28px; font-weight: bold; font-family: Times New Roman;'>Complete Stock Status Table</h3>", unsafe_allow_html=True)

        if not display_df_filtered.empty and 'Material Description' in display_df_filtered.columns:
            search_query = st.text_input(
                "Search by Material Description or any column value:",
                value=st.session_state.search_query,
                placeholder="Type to search...",
                key="search_input"
            )

            if search_query != st.session_state.search_query:
                st.session_state.search_query = search_query
                st.rerun()

            search_df = display_df_filtered.copy()

            if st.session_state.search_query:
                search_term = st.session_state.search_query.lower()
                string_df = search_df.astype(str)
                mask = string_df.apply(
                    lambda col: col.str.lower().str.contains(search_term, na=False, regex=False)
                ).any(axis=1)
                search_df = search_df[mask]
                st.info(f"🔍 Found {len(search_df)} matching records for '{st.session_state.search_query}'")
                if st.button("🗑️ Clear Search"):
                    st.session_state.search_query = ""
                    st.rerun()
            else:
                st.info(f"📊 Showing all {len(search_df)} records")

            cols = list(search_df.columns)
            if 'Material Description' in cols:
                cols.remove('Material Description')
                cols.insert(0, 'Material Description')
            if 'NMOS' in cols and 'AMC' in cols:
                cols.remove('NMOS')
                amc_index = cols.index('AMC') if 'AMC' in cols else 0
                cols.insert(amc_index + 1, 'NMOS')
            if 'Risk Type' in cols and 'Stock Status' in cols:
                cols.remove('Risk Type')
                status_index = cols.index('Stock Status') if 'Stock Status' in cols else 0
                cols.insert(status_index + 1, 'Risk Type')

            cols = [c for c in cols if c in search_df.columns]
            search_df = search_df[cols]

            if st.session_state.view_mode == "card":
                st.markdown("### 📇 Card View")
                cols_per_row = 3
                for i in range(0, len(search_df), cols_per_row):
                    cols = st.columns(cols_per_row)
                    for j, col in enumerate(cols):
                        idx = i + j
                        if idx < len(search_df):
                            row = search_df.iloc[idx]
                            status = row.get('Stock Status', '')
                            color_map = {
                                "Stock Out": "#ff4444",
                                "Understock": "#ffa500",
                                "Normal Stock": "#4CAF50",
                                "Overstock": "#2196F3"
                            }
                            border_color = color_map.get(status, "#ddd")
                            risk_type_value = row.get('Risk Type', 'N/A')
                            risk_color = {
                                "Critical Risk": "#9b59b6",
                                "Risk of Stock out": "#ffa500",
                                "Expiry Risk": "#ffa500"
                            }.get(risk_type_value, border_color)

                            with col:
                                st.markdown(f"""
                                <div class="stock-card" style='border-left: 4px solid {border_color};'>
                                    <h4 style='color: {border_color}; margin-bottom: 10px;'>{row['Material Description'][:60]}</h4>
                                    <p><strong>📦 NSOH:</strong> {row.get('NSOH', 'N/A')}</p>
                                    <p><strong>📈 AMC:</strong> {row.get('AMC', 'N/A')}</p>
                                    <p><strong>⏰ NMOS:</strong> <span style='color: {border_color}; font-weight: bold;'>{row.get('NMOS', 'N/A')}</span></p>
                                    <p><strong>📊 Status:</strong> {row.get('Stock Status', 'N/A')}</p>
                                    <p><strong>🔄 TMOS:</strong> {row.get('TMOS', 'N/A')}</p>
                                    <p><strong>⚠️ Risk Type:</strong> <span style='color: {risk_color}; font-weight: bold;'>{risk_type_value}</span></p>
                                </div>
                                """, unsafe_allow_html=True)
            else:
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

                styled = search_df.style.apply(color_row, axis=1)

                def color_risk_type(val):
                    if val == "Critical Risk":
                        return 'background-color: #9b59b6; color: white'
                    elif val == "Risk of Stock out":
                        return 'background-color: #ffa500; color: white'
                    elif val == "Expiry Risk":
                        return 'background-color: #ffa500; color: white'
                    return ''

                styled = styled.map(color_risk_type, subset=['Risk Type'])

                column_config = {
                    "Material Description": st.column_config.TextColumn("Material Description", width=300, pinned=True),
                    "Risk Type": st.column_config.TextColumn("Risk Type", width=150)
                }

                st.dataframe(styled, column_config=column_config, use_container_width=True, hide_index=True, height=min(800, (len(search_df) + 1) * 35))

                st.markdown("""
                <div class="legend-box">
                    <h5 class="legend-title">📊 Color Legend - Stock Status:</h5>
                    <div style="display: flex; gap: 20px; flex-wrap: wrap;">
                        <div class="legend-item"><div class="legend-color" style="background-color: red;"></div><span><strong>Red</strong> = Stock Out (NMOS &lt; 1)</span></div>
                        <div class="legend-item"><div class="legend-color" style="background-color: yellow;"></div><span><strong>Yellow</strong> = Understock (1 ≤ NMOS &lt; 6)</span></div>
                        <div class="legend-item"><div class="legend-color" style="background-color: green;"></div><span><strong>Green</strong> = Normal Stock (6 ≤ NMOS ≤ 18)</span></div>
                        <div class="legend-item"><div class="legend-color" style="background-color: skyblue;"></div><span><strong>Blue</strong> = Overstock (NMOS > 18)</span></div>
                        <div class="legend-item"><div class="legend-color" style="background-color: #9b59b6;"></div><span><strong>Purple</strong> = Critical Risk</span></div>
                        <div class="legend-item"><div class="legend-color" style="background-color: #ffa500;"></div><span><strong>Orange</strong> = Risk of Stock out or Expiry Risk</span></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

            # DOWNLOAD REPORT
            st.markdown("---")
            st.markdown("<h4 style='font-size: 20px; font-weight: bold; font-family: Times New Roman;'>📥 Download Report</h4>", unsafe_allow_html=True)

            report_columns = []

            if 'Material Description' in df_filtered.columns:
                report_columns.append('Material Description')

            all_columns = list(df_filtered.columns)

            if 'Material Description' in all_columns and 'TMOS' in all_columns:
                mat_index = all_columns.index('Material Description')
                tmos_index = all_columns.index('TMOS')
                all_cols_between = all_columns[mat_index:tmos_index + 1]

                if 'AMC' in all_cols_between and 'NMOS' in all_cols_between:
                    for col in all_cols_between:
                        if col == 'NMOS':
                            continue
                        report_columns.append(col)
                    if 'AMC' in report_columns:
                        amc_pos = report_columns.index('AMC')
                        report_columns.insert(amc_pos + 1, 'NMOS')
                else:
                    report_columns = all_cols_between
            else:
                for col in all_columns:
                    if col not in ['Stock Status', 'Risk of Stock', 'Hubs%', 'Head Office%', 'Avail Gap', 'CV (%)', 'CV Category', 'Has Expiry Risk', 'Expiry Risk Details', 'Assigned Subcategory', 'Risk Type']:
                        report_columns.append(col)

            if not report_columns:
                report_columns = ['Material Description']

            report_columns = list(dict.fromkeys(report_columns))

            report_df = df_filtered[report_columns].copy()

            for col in report_df.columns:
                if col in ['NMOS', 'GIT_MOS', 'LC_MOS', 'WB_MOS', 'TMD_MOS', 'TMOS']:
                    report_df[col] = report_df[col].apply(lambda x: round(x, 2) if pd.notna(x) else "")
                elif col in ['NSOH', 'AMC', 'Hubs', 'Head Office']:
                    report_df[col] = report_df[col].apply(lambda x: f"{int(x):,}" if pd.notna(x) and x != "" else "" if x == "" else x)

            output = BytesIO()

            try:
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    if sheet_name == "All":
                        report_title = "All Programs Medicines Monthly National and Pipeline Report"
                    else:
                        report_title = f"{sheet_name} Medicines Monthly National and Pipeline Report"

                    report_df.to_excel(writer, sheet_name=report_title[:31], index=False)
                    worksheet = writer.sheets[report_title[:31]]

                    for column in report_df.columns:
                        try:
                            str_values = report_df[column].astype(str).replace('nan', '').replace('None', '')
                            if len(str_values) > 0:
                                column_length = max(str_values.map(len).max(), len(column))
                            else:
                                column_length = len(column)
                            column_length = min(column_length, 50)
                            col_idx = report_df.columns.get_loc(column)
                            col_letter = get_column_letter(col_idx + 1)
                            worksheet.column_dimensions[col_letter].width = column_length + 2
                        except Exception:
                            col_idx = report_df.columns.get_loc(column)
                            col_letter = get_column_letter(col_idx + 1)
                            worksheet.column_dimensions[col_letter].width = 15

                output.seek(0)
                st.download_button(
                    label=f"📊 Download {sheet_name} Monthly National and Pipeline Report (Excel)",
                    data=output,
                    file_name=f"{sheet_name}_Monthly_National_Pipeline_Report_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    type="primary"
                )
                st.caption(f"Report includes columns from Material Description to TMOS ({len(report_columns)} columns)")

            except Exception as excel_error:
                st.error(f"Error creating Excel file: {excel_error}")
                csv_data = report_df.to_csv(index=False)
                st.download_button(
                    label=f"📊 Download {sheet_name} Monthly National and Pipeline Report (CSV)",
                    data=csv_data,
                    file_name=f"{sheet_name}_Monthly_National_Pipeline_Report_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )

            # STOCK CHANGES TABLE
            st.markdown("---")
            st.markdown("<h4 style='font-size: 20px; font-weight: bold; font-family: Times New Roman;'>📈 Stock Changes Since Last Update (Based on NMOS)</h4>", unsafe_allow_html=True)

            if st.session_state.nsoh_changes is not None and not st.session_state.nsoh_changes.empty:
                st.info("📊 Materials that received new stock (positive NMOS increase):")

                total_added = st.session_state.nsoh_changes['Added_Quantity'].astype(str).str.replace(',', '').astype(float).sum() if 'Added_Quantity' in st.session_state.nsoh_changes.columns else 0

                col1, col2 = st.columns(2)
                with col1:
                    st.metric("📦 Materials with Stock Increase", len(st.session_state.nsoh_changes))
                with col2:
                    st.metric("➕ Total Added Quantity", f"{int(total_added):,}")

                st.dataframe(
                    st.session_state.nsoh_changes,
                    column_config={
                        "Material Description": st.column_config.TextColumn("Material", width=300),
                        "NMOS_previous": st.column_config.TextColumn("Previous NMOS", width=100),
                        "NMOS_now": st.column_config.TextColumn("Current NMOS", width=100),
                        "NMOS_Difference": st.column_config.TextColumn("NMOS Increase (+)", width=100),
                        "AMC": st.column_config.TextColumn("AMC", width=100),
                        "Added_Quantity": st.column_config.TextColumn("Added Quantity", width=120)
                    },
                    use_container_width=True,
                    hide_index=True
                )

                changes_csv = st.session_state.nsoh_changes.to_csv(index=False)
                st.download_button(
                    label="📥 Download Stock Changes (CSV)",
                    data=changes_csv,
                    file_name=f"stock_changes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            elif st.session_state.raw_previous_data is not None:
                st.success("✅ No NMOS increases detected since last update.")
            else:
                st.info("ℹ️ Stock change tracking will appear after the next Supabase data update.")
        else:
            st.info("No data available.")

    # TAB 2 - KPIs & Analytics
    with tab2:
        if sheet_name == "All":
            program_display = "All Programs"
        elif subcategory_filter != "All":
            program_display = f"{sheet_name} - {subcategory_filter}"
        else:
            program_display = sheet_name

        st.markdown(f"<h3 style='font-size: 28px; font-weight: bold; font-family: Times New Roman;'>{program_display} Medicines Performance Metrics</h3>", unsafe_allow_html=True)

        if not df_filtered.empty and 'NMOS' in df_filtered.columns:
            nmos_values = pd.to_numeric(df_filtered['NMOS'], errors='coerce').dropna()
            availability = (nmos_values > 1).mean() * 100 if len(nmos_values) > 0 else 0
            sap = ((nmos_values >= 6) & (nmos_values <= 18)).mean() * 100 if len(nmos_values) > 0 else 0

            if 'Avail Gap' in df_filtered.columns:
                avail_gap_values = pd.to_numeric(df_filtered['Avail Gap'], errors='coerce').dropna()
                avg_avail_gap = avail_gap_values.mean() if len(avail_gap_values) > 0 else 0
            else:
                avg_avail_gap = 0

            avail_delta = availability - 100

            if -5 <= avg_avail_gap <= 5:
                avail_gap_status = "✅ Within Target (-5% to 5%)"
                avail_gap_delta = None
            elif avg_avail_gap > 5:
                avail_gap_status = f"⚠️ Above Target (+{avg_avail_gap - 5:.1f}% over)"
                avail_gap_delta = f"+{avg_avail_gap - 5:.1f}%"
            else:
                avail_gap_status = f"⚠️ Below Target ({avg_avail_gap + 5:.1f}% under)"
                avail_gap_delta = f"{avg_avail_gap + 5:.1f}%"

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("📈 Availability", f"{availability:.1f}%", delta=f"{avail_delta:+.1f}%", delta_color="inverse")
                st.caption("Target: 100%")
            with col2:
                st.metric("🎯 SAP Achievement", f"{sap:.1f}%", delta=f"{sap - 65:.1f}%")
                st.caption("Target: 65%")
            with col3:
                st.metric("📊 Avail. Gap (Hubs% - Head Office%)", f"{avg_avail_gap:.1f}%", delta=avail_gap_delta, delta_color="inverse" if avg_avail_gap > 5 or avg_avail_gap < -5 else "off")
                st.caption(avail_gap_status)

            st.markdown("---")

            def create_kpi_fig(value, target, title):
                color = 'red' if value < target else 'black'
                return go.Figure(go.Indicator(mode="gauge+number", value=value, number={'suffix': '%', 'font': {'size': 36, 'color': color}}, title={'text': f"<b>{title}</b>", 'font': {'size': 24}}, gauge={'axis': {'range': [0, 100]}, 'bar': {'color': 'skyblue'}}))

            col1, col2 = st.columns(2)
            with col1:
                st.plotly_chart(create_kpi_fig(availability, 100, "Availability"), use_container_width=True)
            with col2:
                st.plotly_chart(create_kpi_fig(sap, 65, "SAP"), use_container_width=True)

            try:
                if 'Stock Status' in df_filtered.columns:
                    status_counts = df_filtered['Stock Status'].replace("", np.nan).dropna().value_counts()
                    if not status_counts.empty:
                        fig = px.pie(values=status_counts.values, names=status_counts.index, hole=0.5, color=status_counts.index, color_discrete_map={"Stock Out": "red", "Understock": "yellow", "Normal Stock": "green", "Overstock": "skyblue"})
                        fig.update_traces(textposition='inside', textinfo='percent+value', textfont_size=16)
                        total_count = len(df_filtered[df_filtered['Stock Status'] != ""])
                        fig.update_layout(title={'text': f"{program_display} Stock Status (Total: {total_count} items)", 'x': 0, 'xanchor': 'left', 'font': {'size': 20, 'weight': 'bold'}}, annotations=[dict(text=f"Total<br>{total_count}", x=0.5, y=0.5, font_size=20, showarrow=False)])
                        st.plotly_chart(fig, use_container_width=True)
            except Exception:
                pass

            st.markdown("### 🚚 Pipeline Status Analysis")
            pipeline_cols = [col for col in ['GIT_MOS', 'LC_MOS', 'WB_MOS', 'TMD_MOS'] if col in df_filtered.columns]
            if pipeline_cols:
                pipeline_summary = df_filtered[pipeline_cols].sum()
                if pipeline_summary.sum() > 0:
                    fig_pipeline = px.pie(values=pipeline_summary.values, names=pipeline_summary.index, title="Pipeline MOS Distribution", color_discrete_sequence=px.colors.sequential.Blues_r)
                    fig_pipeline.update_traces(textposition='inside', textinfo='percent+label')
                    st.plotly_chart(fig_pipeline, use_container_width=True)
                else:
                    st.info("No pipeline data available")
            else:
                st.info("Pipeline MOS columns not available")

            st.markdown("### ⚠️ Critical Items - Stock Out")
            stock_out_items = df_filtered[df_filtered['Stock Status'] == 'Stock Out'][['Material Description', 'NSOH', 'AMC', 'NMOS']].copy()
            if not stock_out_items.empty:
                stock_out_items = stock_out_items.sort_values('NMOS').head(10)
                fig_stock_out = go.Figure(data=[go.Bar(x=stock_out_items['Material Description'], y=stock_out_items['NMOS'], marker_color='red', text=stock_out_items['NMOS'].round(2), textposition='outside', name='NMOS')])
                fig_stock_out.update_layout(title="Top 10 Stock Out Items (Lowest NMOS)", xaxis_title="Material Description", yaxis_title="Months of Stock (NMOS)", height=400, xaxis_tickangle=-45)
                st.plotly_chart(fig_stock_out, use_container_width=True)
            else:
                st.success("✅ No stock out items found!")

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
                        mos_df['Material_split'] = mos_df['Material Description'].apply(lambda x: '<br>'.join([str(x)[i:i + split_len] for i in range(0, len(str(x)), split_len)]))
                        mos_df['NMOS_color'] = mos_df['NMOS'].apply(lambda x: "red" if x < 1 else "yellow" if x < 6 else "green" if x <= 18 else "skyblue")

                        split_size = 10
                        for i in range(0, len(mos_df), split_size):
                            df_chunk = mos_df.iloc[i:i + split_size].copy()
                            df_chunk = df_chunk.iloc[::-1].reset_index(drop=True)
                            fig = go.Figure()
                            fig.add_trace(go.Bar(y=df_chunk['Material_split'], x=df_chunk['NMOS'], name='NMOS', orientation='h', marker=dict(color=df_chunk['NMOS_color']), text=df_chunk['NMOS'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else ""), textposition='inside', textfont_size=12, hovertemplate='NMOS: %{x:.1f} months<extra></extra>'))
                            pipeline_traces = [('GIT_MOS', 'cyan', 'GIT MOS'), ('LC_MOS', 'plum', 'LC MOS'), ('WB_MOS', 'gray', 'WB MOS'), ('TMD_MOS', 'orange', 'TMD MOS')]
                            for col, color, label in pipeline_traces:
                                if col in df_chunk.columns and (df_chunk[col] > 0).any():
                                    fig.add_trace(go.Bar(y=df_chunk['Material_split'], x=df_chunk[col], name=label, orientation='h', marker_color=color, text=df_chunk[col].apply(lambda x: f"{x:.1f}" if x > 0 else ""), textposition='inside', textfont_size=12, hovertemplate=f'{label}: %{{x:.1f}} months<extra></extra>'))
                            if 'TMOS' in df_chunk.columns:
                                fig.add_trace(go.Scatter(y=df_chunk['Material_split'], x=df_chunk['TMOS'], mode='text', text=df_chunk['TMOS'].apply(lambda x: f"TMOS: {x:.2f}" if x > 0 else ""), textposition='middle right', showlegend=False, textfont_size=12))
                            original_start = i + 1
                            original_end = i + len(df_chunk)
                            chart_title = f'{program_display} Stock Status - National and Pipeline (Medicines {original_start}-{original_end})'
                            fig.update_layout(barmode='stack', title=chart_title, xaxis_title='Months of Stock', yaxis_title='Material Description', height=max(500, 35 * len(df_chunk)), showlegend=True, legend=dict(orientation="v", yanchor="bottom", y=1.02, xanchor="right", x=1), margin=dict(l=20, r=120, t=60, b=20))
                            st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.error(f"Error creating MOS chart: {e}")

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
                        bar_df = pd.DataFrame({'Material Description': materials_valid, 'Hubs%': hubs_pct, 'Head Office%': ho_pct, 'NSOH_display': nsoh_formatted}).reset_index(drop=True)
                        bar_df = bar_df.sort_values('Hubs%')
                        bar_df['Material_split'] = bar_df['Material Description'].apply(lambda x: '<br>'.join([str(x)[i:i + 25] for i in range(0, len(str(x)), 25)]))
                        n = 11
                        for i in range(0, len(bar_df), n):
                            df_chunk = bar_df.iloc[i:i + n]
                            fig_bar = go.Figure()
                            fig_bar.add_trace(go.Bar(y=df_chunk['Material_split'], x=df_chunk['Hubs%'], name='Hubs%', orientation='h', marker_color='skyblue', text=df_chunk['Hubs%'].apply(lambda x: f"{x:.1f}%" if x > 0 else ""), textposition='inside', textfont_size=12))
                            fig_bar.add_trace(go.Bar(y=df_chunk['Material_split'], x=df_chunk['Head Office%'], name='Head Office%', orientation='h', marker_color='orange', text=df_chunk['Head Office%'].apply(lambda x: f"{x:.1f}%" if x > 0 else ""), textposition='inside', textfont_size=12))
                            for idx, row in df_chunk.iterrows():
                                fig_bar.add_annotation(x=row['Hubs%'] + row['Head Office%'] + 2, y=row['Material_split'], text=f"NSOH: {row['NSOH_display']}", showarrow=False, font=dict(size=12), xanchor='left', yanchor='middle')
                            fig_bar.update_layout(barmode='stack', title=f'{program_display} Stock Distribution - Hubs vs Head Office (Materials {i + 1}-{i + len(df_chunk)})', xaxis_title='Percentage of NSOH (%)', yaxis_title='Material Description', xaxis={'range': [0, 120]}, height=max(600, 40 * len(df_chunk)), margin=dict(r=150))
                            st.plotly_chart(fig_bar, use_container_width=True)
                    else:
                        st.info("No materials with valid NSOH (>0) to display.")
            except Exception:
                pass
        else:
            st.info("No data available for KPI calculations.")

    # TAB 3 - Decision Briefs
    with tab3:
        if sheet_name == "All":
            st.markdown("<h3 style='font-size: 28px; font-weight: bold; font-family: Times New Roman;'>All Programs - Medicines Needing Immediate Action</h3>", unsafe_allow_html=True)
        else:
            st.markdown(f"<h3 style='font-size: 28px; font-weight: bold; font-family: Times New Roman;'>{program_display} Medicines Needing Immediate Action</h3>", unsafe_allow_html=True)

        if not df_filtered.empty and 'Material Description' in df_filtered.columns:
            decision_df = df_filtered[['Material Description', 'NSOH', 'Expiry', 'AMC', 'NMOS', 'Status', 'Risk Type', 'Stock Status', 'Expiry Risk Details', 
                                       'GIT_MOS', 'LC_MOS', 'WB_MOS', 'TMD_MOS', 'GIT_PO', 'LC_PO', 'WB_PO', 'TMD_PO', 'Hubs%', 'Head Office%', 'CV Category']].copy()

            def get_identified_problems(row):
                if row.get('Stock Status') == 'Stock Out':
                    return "Stock Out"
                risk = row.get('Risk Type', '')
                if risk and risk != '':
                    return risk
                return ''

            decision_df['Identified Problems'] = decision_df.apply(get_identified_problems, axis=1)

            def get_automated_recommendation(row):
                problem = row.get('Identified Problems', '')
                if problem == 'Expiry Risk':
                    cv_cat = row.get('CV Category', 'Unknown')
                    return get_expiry_risk_recommendation(row, cv_cat)
                elif problem == 'Critical Risk':
                    stock_rec = get_stock_out_recommendation(row)
                    cv_cat = row.get('CV Category', 'Unknown')
                    expiry_rec = get_expiry_risk_recommendation(row, cv_cat)
                    return f"{stock_rec}\n{expiry_rec}"
                elif problem in ['Risk of Stock out', 'Stock Out']:
                    return get_stock_out_recommendation(row)
                return ''

            decision_df['Recommendation'] = decision_df.apply(get_automated_recommendation, axis=1)
            decision_df = decision_df[decision_df['Identified Problems'] != ''].copy()

            if len(decision_df) > 0:
                for col in ['NSOH', 'AMC']:
                    if col in decision_df.columns:
                        decision_df[col] = decision_df[col].apply(format_number_with_commas)
                if 'NMOS' in decision_df.columns:
                    decision_df['NMOS'] = decision_df['NMOS'].apply(format_mos_with_decimals)
                if 'Hubs%' in decision_df.columns:
                    decision_df['Hubs%'] = decision_df['Hubs%'].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "")
                if 'Head Office%' in decision_df.columns:
                    decision_df['Head Office%'] = decision_df['Head Office%'].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "")

                st.markdown("<h4 style='font-size: 24px; font-weight: bold; font-family: Times New Roman;'>Quick Summary</h4>", unsafe_allow_html=True)
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Items with Problems", len(decision_df))
                with col2:
                    st.metric("Stock Out Items", len(decision_df[decision_df['Identified Problems'] == 'Stock Out']))
                with col3:
                    st.metric("At Risk of Stock Out", len(decision_df[decision_df['Identified Problems'] == 'Risk of Stock out']))
                with col4:
                    st.metric("At Risk of Expiry", len(decision_df[decision_df['Identified Problems'] == 'Expiry Risk']) + len(decision_df[decision_df['Identified Problems'] == 'Critical Risk']))

                st.markdown("---")

                st.markdown("### ✏️ Sales and Operational Planning")
                st.info("💡 Recommendations are auto-generated based on pipeline status (with PO numbers) and distribution patterns. You can edit them as needed.")

                display_columns = ['Material Description', 'NSOH', 'Expiry', 'AMC', 'NMOS', 'Status', 'CV Category', 'Identified Problems', 'Recommendation']
                available_display_columns = [col for col in display_columns if col in decision_df.columns]

                column_config = {
                    "Material Description": st.column_config.TextColumn("Material", width=250, disabled=True, pinned=True),
                    "NSOH": st.column_config.TextColumn("NSOH", width=100, disabled=True),
                    "Expiry": st.column_config.TextColumn("Expiry", width=120, disabled=True),
                    "AMC": st.column_config.TextColumn("AMC", width=100, disabled=True),
                    "NMOS": st.column_config.TextColumn("NMOS", width=80, disabled=True),
                    "Status": st.column_config.TextColumn("Status", width=100, disabled=True),
                    "CV Category": st.column_config.TextColumn("CV Category", width=120, disabled=True),
                    "Identified Problems": st.column_config.TextColumn("Problem", width=120, disabled=True),
                    "Recommendation": st.column_config.TextColumn("Recommendation", width=450, disabled=False)
                }

                edited_result = st.data_editor(
                    decision_df[available_display_columns],
                    column_config=column_config,
                    use_container_width=True, 
                    hide_index=True, 
                    height=min(600, (len(decision_df) + 1) * 45), 
                    num_rows="fixed"
                )

                for idx, row in edited_result.iterrows():
                    st.session_state.saved_recommendations[row['Material Description']] = {
                        'recommendation': row['Recommendation']
                    }

                st.download_button(
                    label="📥 Download Decision Briefs (CSV)", 
                    data=edited_result.to_csv(index=False), 
                    file_name=f"{sheet_name}_decision_briefs_{datetime.now().strftime('%Y%m%d')}.csv".replace(" ", "_"), 
                    mime="text/csv",
                    use_container_width=True
                )

                if st.button("🗑️ Clear All Recommendations", use_container_width=True):
                    st.session_state.saved_recommendations = {}
                    st.rerun()

                st.markdown("---")
                st.markdown("### 📇 Card View with Recommendations")

                for idx, row in decision_df.iterrows():
                    risk_type = row['Identified Problems']
                    if risk_type == "Critical Risk":
                        status_color = "#9b59b6"
                    elif risk_type == "Stock Out":
                        status_color = "#ff4444"
                    elif risk_type in ["Risk of Stock out", "Expiry Risk"]:
                        status_color = "#ffa500"
                    else:
                        status_color = "#ffa500"

                    recommendation_text = row.get('Recommendation', '')
                    cv_category = row.get('CV Category', 'N/A')

                    st.markdown(f"""
                    <div class="stock-card" style='border-left: 4px solid {status_color}; margin-bottom: 15px;'>
                        <h4 style='color: {status_color}; margin-bottom: 10px;'>{row['Material Description']}</h4>
                        <p><strong>📦 NSOH:</strong> {row.get('NSOH', 'N/A')}</p>
                        <p><strong>📅 Expiry:</strong> {row.get('Expiry', 'N/A')}</p>
                        <p><strong>📈 AMC:</strong> {row.get('AMC', 'N/A')}</p>
                        <p><strong>⏰ NMOS:</strong> <span style='color: {status_color}; font-weight: bold;'>{row.get('NMOS', 'N/A')}</span></p>
                        <p><strong>📊 Status:</strong> {row.get('Status', 'N/A')}</p>
                        <p><strong>⚠️ Risk Type:</strong> <span style='color: {status_color}; font-weight: bold;'>{risk_type}</span></p>
                        <p><strong>📊 CV Category:</strong> {cv_category}</p>
                        <p><strong>💡 Recommendation:</strong> <span style='background-color: #f0f2f6; padding: 5px; border-radius: 5px; display: inline-block;'>{recommendation_text}</span></p>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.success("✅ No medicines with identified problems! All items are within normal stock levels.")
                st.balloons()
        else:
            st.info("No data available.")

    # TAB 4 - Hubs Distribution
    with tab4:
        try:
            if not df.empty:
                if branch_amc_data is not None and 'Material Description' in df.columns and 'Material Description' in branch_amc_data.columns and not branch_amc_data.empty:
                    branch_cols = [col for col in df.columns if 'Branch' in col or col == 'Material Description']
                    gh = df[branch_cols].copy() if branch_cols else pd.DataFrame()

                    st.markdown("<h4 style='font-size: 24px; font-weight: bold; font-family: Times New Roman;'>Stock Distribution Across Hubs by MOS</h4>", unsafe_allow_html=True)

                    merged_df = pd.merge(gh, branch_amc_data, on='Material Description', how='inner', suffixes=('_gh', '_cf'))

                    if not merged_df.empty:
                        gh_cols = [col for col in gh.columns if col != 'Material Description']
                        cf_cols = [col for col in branch_amc_data.columns if col != 'Material Description']
                        division_data = {'Material Description': merged_df['Material Description']}

                        min_cols = min(len(gh_cols), len(cf_cols))

                        for i in range(min_cols):
                            gh_col = gh_cols[i]
                            cf_col = cf_cols[i]
                            display_col_name = gh_col
                            gh_values = pd.to_numeric(merged_df[f"{gh_col}_gh"], errors='coerce')
                            cf_values = pd.to_numeric(merged_df[f"{cf_col}_cf"], errors='coerce')
                            with np.errstate(divide='ignore', invalid='ignore'):
                                division_result = np.where(cf_values != 0, gh_values / cf_values, np.nan)
                            division_data[display_col_name] = division_result

                        division_df = pd.DataFrame(division_data)
                        division_df = division_df.replace([np.inf, -np.inf], np.nan).round(2)

                        if division_df.shape[1] > 1:
                            branch_cols_list = [col for col in division_df.columns if col != 'Material Description']
                            division_df['CV (%)'] = division_df[branch_cols_list].apply(lambda row: calculate_coefficient_of_variation(row), axis=1)
                            division_df['CV (%)'] = division_df['CV (%)'].round(1)
                            cols = ['Material Description', 'CV (%)'] + branch_cols_list
                            division_df = division_df[cols]

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
                            cv_counts = division_df['CV Category'].value_counts()

                            col1, col2, col3, col4 = st.columns(4)
                            with col1:
                                st.metric("Total Materials", len(division_df))
                            if 'Low variation' in cv_counts:
                                with col2:
                                    low_count = cv_counts['Low variation']
                                    low_pct = (low_count / len(division_df) * 100) if len(division_df) > 0 else 0
                                    st.metric("Low Variation (<50%)", f"{low_count} ({low_pct:.1f}%)")
                            if 'Moderate variation' in cv_counts:
                                with col3:
                                    mod_count = cv_counts['Moderate variation']
                                    mod_pct = (mod_count / len(division_df) * 100) if len(division_df) > 0 else 0
                                    st.metric("Moderate Variation (50-100%)", f"{mod_count} ({mod_pct:.1f}%)")
                            if 'High variation' in cv_counts:
                                with col4:
                                    high_count = cv_counts['High variation']
                                    high_pct = (high_count / len(division_df) * 100) if len(division_df) > 0 else 0
                                    st.metric("High Variation (>100%)", f"{high_count} ({high_pct:.1f}%)")

                            # HEATMAP
                            if division_df.shape[1] > 2:
                                branch_cols_list = [col for col in division_df.columns if col not in ['Material Description', 'CV (%)', 'CV Category']]
                                heatmap_df = division_df.copy()
                                heatmap_df = heatmap_df.sort_values('Material Description')
                                heatmap_df_indexed = heatmap_df.set_index('Material Description')
                                heatmap_df_indexed = heatmap_df_indexed[branch_cols_list]
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
                                        st.markdown(f"<h5 style='text-align: center;'>Page {st.session_state.heatmap_page} of {total_pages}</h5>", unsafe_allow_html=True)
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
                                    z=heatmap_page_df.values, y=heatmap_page_df.index, x=heatmap_page_df.columns,
                                    colorscale=[[0.0, 'red'], [0.125, 'yellow'], [0.5, 'green'], [1.0, 'skyblue']],
                                    zmin=0, zmax=8, text=heatmap_page_df.values.round(1), texttemplate='%{text}', textfont={"size": 14},
                                    colorbar=dict(title="MOS", tickvals=[0.5, 1, 2, 4, 6, 8], ticktext=['0.5', '1', '2', '4', '6', '8+']),
                                    hovertemplate='<b>Material:</b> %{x}<br><b>Branch:</b> %{y}<br><b>MOS:</b> %{z:.2f} months<br><extra></extra>'
                                ))
                                fig.update_layout(xaxis={'title': 'Material Description', 'tickangle': -45, 'tickfont': {'size': 12}}, 
                                                yaxis={'title': 'Branches', 'tickfont': {'size': 12}}, height=650, margin=dict(l=120, r=120, t=50, b=200))
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
                        st.markdown("<h5 style='font-size: 20px; font-weight: bold;'>Full Branch MOS Data with CV</h5>", unsafe_allow_html=True)
                        display_division_df = division_df.copy()
                        display_division_df['CV (%)'] = display_division_df['CV (%)'].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "")
                        st.dataframe(display_division_df, use_container_width=True, height=400, hide_index=True)
                        st.download_button(label="Download Hubs MOS with CV", data=division_df.to_csv(index=False), file_name="hubs_mos_distribution_with_cv.csv", mime="text/csv")

                        st.markdown("---")
                        st.markdown("<h5 style='font-size: 20px; font-weight: bold;'>EPSS Hubs SOH</h5>", unsafe_allow_html=True)
                        st.dataframe(gh, use_container_width=True, height=400, hide_index=True)

                        st.markdown("---")
                        st.markdown("<h5 style='font-size: 20px; font-weight: bold;'>EPSS Hubs AMC Data (from Google Sheets)</h5>", unsafe_allow_html=True)
                        st.dataframe(branch_amc_data, use_container_width=True, height=400, hide_index=True)
                    else:
                        st.warning("No matching Material Description found")
                elif branch_amc_data is None or branch_amc_data.empty:
                    st.info("Branch AMC data is currently unavailable.")
                    if not df.empty and 'Material Description' in df.columns:
                        branch_cols = [col for col in df.columns if 'Branch' in col or col == 'Material Description']
                        gh = df[branch_cols].copy() if branch_cols else df[['Material Description']].copy()
                        st.dataframe(gh, use_container_width=True, height=400, hide_index=True)
                else:
                    st.error("'Material Description' column not found")
            else:
                st.warning("Main dataframe is empty.")
        except Exception as e:
            st.error(f"Error processing files: {e}")

    # TAB 5 - Advanced Analytics (Now inside Dashboard tabs)
    with tab5:
        st.markdown("<h3 style='font-size: 28px; font-weight: bold; font-family: Times New Roman;'>🔬 Advanced Analytics</h3>", unsafe_allow_html=True)

        # Create sub-tabs within Advanced Analytics
        aa_tab1, aa_tab2, aa_tab3, aa_tab4, aa_tab5, aa_tab6, aa_tab7, aa_tab8 = st.tabs([
            "🏆 Branch Ranking", "🔄 Redistribution", "📧 Critical Alerts", "⏰ Expiry Notifications",
            "📊 Program Comparison", "🗺️ Regional Map", "👁️ Popular Materials", "👥 User Analytics"
        ])

        # TAB 1: Branch Ranking
        with aa_tab1:
            st.markdown("<h4 style='font-size: 22px; font-weight: bold;'>Branch Ranking by Stock Availability</h4>", unsafe_allow_html=True)
            st.caption("Availability = materials with NMOS ≥ 0.5 (at least 2 weeks of stock)")

            if branch_amc_data is not None and not branch_amc_data.empty:
                branch_stock_cols = [col for col in df.columns if 'Branch' in col and col != 'Material Description']
                amc_branch_cols = [col for col in branch_amc_data.columns if col != 'Material Description']
                rankings = []

                for amc_branch in amc_branch_cols:
                    stock_col = None
                    for bc in branch_stock_cols:
                        if amc_branch == bc:
                            stock_col = bc
                            break

                    if stock_col:
                        try:
                            merged = pd.merge(
                                df[['Material Description', stock_col]], 
                                branch_amc_data[['Material Description', amc_branch]], 
                                on='Material Description', how='inner'
                            )
                            if not merged.empty:
                                stock_values = pd.to_numeric(merged[stock_col + '_x'], errors='coerce').fillna(0)
                                amc_values = pd.to_numeric(merged[amc_branch + '_y'], errors='coerce').fillna(1)
                                amc_values = amc_values.replace(0, 1)
                                branch_nmos = stock_values / amc_values
                                availability_count = np.sum(branch_nmos >= 0.5)
                                total_materials = len(branch_nmos)
                                availability_score = (availability_count / total_materials * 100) if total_materials > 0 else 0
                                rankings.append({
                                    'Branch': amc_branch,
                                    'Availability Score (%)': round(availability_score, 1),
                                    'Total Materials': total_materials
                                })
                        except Exception:
                            continue

                if rankings:
                    rankings_df = pd.DataFrame(rankings).sort_values('Availability Score (%)', ascending=False)
                    rankings_df['Rank'] = range(1, len(rankings_df) + 1)

                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("🏆 Top Branch", rankings_df.iloc[0]['Branch'])
                    with col2:
                        st.metric("📉 Bottom Branch", rankings_df.iloc[-1]['Branch'])

                    st.dataframe(rankings_df, use_container_width=True, hide_index=True)

                    fig = px.bar(rankings_df, x='Branch', y='Availability Score (%)', color='Availability Score (%)',
                                color_continuous_scale='RdYlGn', title='Branch Availability Scores')
                    fig.update_layout(height=500, xaxis_tickangle=-45)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("No branch data available for ranking")

        # TAB 2: Redistribution Recommendations
        with aa_tab2:
            st.markdown("<h4 style='font-size: 22px; font-weight: bold;'>Stock Redistribution Recommendations</h4>", unsafe_allow_html=True)
            st.info("Trigger: Expiry Risk OR Understock (National NMOS < 6). Source: NMOS > 8, Target: NMOS < 0.5")

            if branch_amc_data is not None and not branch_amc_data.empty:
                branch_stock_cols = [col for col in df.columns if 'Branch' in col and col != 'Material Description']
                amc_branch_cols = [col for col in branch_amc_data.columns if col != 'Material Description']
                recommendations = []

                df_aligned = df.set_index('Material Description')
                amc_aligned = branch_amc_data.set_index('Material Description')
                common_materials = df_aligned.index.intersection(amc_aligned.index)

                for material in list(common_materials)[:30]:
                    material_row = df[df['Material Description'] == material]
                    if material_row.empty:
                        continue

                    has_expiry_risk = material_row.iloc[0].get('Has Expiry Risk', False)
                    national_nmos = material_row.iloc[0].get('NMOS', 10)
                    if pd.isna(national_nmos):
                        national_nmos = 10

                    is_understock = national_nmos < 6

                    if not (has_expiry_risk or is_understock):
                        continue

                    branch_nmos = {}
                    branch_amc_val = {}

                    for amc_branch in amc_branch_cols:
                        stock_col = None
                        for bc in branch_stock_cols:
                            if amc_branch == bc:
                                stock_col = bc
                                break

                        if stock_col and stock_col in df_aligned.columns:
                            try:
                                stock = pd.to_numeric(df_aligned.loc[material, stock_col], errors='coerce')
                                amc = pd.to_numeric(amc_aligned.loc[material, amc_branch], errors='coerce')
                                if pd.isna(stock):
                                    stock = 0
                                if pd.isna(amc) or amc <= 0:
                                    amc = 1
                                nmos = stock / amc
                                branch_nmos[amc_branch] = nmos
                                branch_amc_val[amc_branch] = amc
                            except Exception:
                                continue

                    overstocked = [b for b, nmos in branch_nmos.items() if nmos > 8]
                    understocked = [b for b, nmos in branch_nmos.items() if 0 < nmos < 0.5]

                    for source in overstocked[:2]:
                        for target in understocked[:2]:
                            if source != target:
                                recommendations.append({
                                    'Material': material[:50],
                                    'Trigger': 'Expiry Risk' if has_expiry_risk else 'Understock',
                                    'Source': source,
                                    'Target': target,
                                    'Source NMOS': round(branch_nmos[source], 2),
                                    'Target NMOS': round(branch_nmos[target], 2)
                                })

                if recommendations:
                    st.dataframe(pd.DataFrame(recommendations), use_container_width=True, hide_index=True)
                    st.metric("🔄 Total Transfer Opportunities", len(recommendations))
                else:
                    st.success("✅ No redistribution opportunities identified")

        # TAB 3: Critical Alerts
        with aa_tab3:
            st.markdown("<h4 style='font-size: 22px; font-weight: bold;'>Critical Stock-Out Alerts</h4>", unsafe_allow_html=True)

            critical_items = []
            for idx, row in df_filtered.iterrows():
                nmos = row.get('NMOS', 0)
                if pd.notna(nmos) and nmos < 0.5:
                    critical_items.append({
                        'Material': row['Material Description'][:60],
                        'NMOS': round(nmos, 2),
                        'NSOH': row.get('NSOH', 0),
                        'AMC': row.get('AMC', 0)
                    })

            if critical_items:
                st.error(f"⚠️ {len(critical_items)} critical items requiring immediate attention!")
                st.dataframe(pd.DataFrame(critical_items), use_container_width=True, hide_index=True)
            else:
                st.success("✅ No critical stock-outs detected")

        # TAB 4: Expiry Notifications
        with aa_tab4:
            st.markdown("<h4 style='font-size: 22px; font-weight: bold;'>Expiring Stock Notifications</h4>", unsafe_allow_html=True)

            notifications = []
            current_date = datetime.now()

            for idx, row in df_filtered.iterrows():
                expiry_str = row.get('Expiry', '')
                if pd.isna(expiry_str) or expiry_str == '':
                    continue

                pattern = r'(\d[\d,]*)\s*\(([A-Za-z]+)-(\d{4})\)'
                matches = re.findall(pattern, str(expiry_str))
                month_map = {'Jan':1, 'Feb':2, 'Mar':3, 'Apr':4, 'May':5, 'Jun':6,
                            'Jul':7, 'Aug':8, 'Sep':9, 'Oct':10, 'Nov':11, 'Dec':12}

                for qty_str, month, year in matches[:2]:
                    try:
                        qty = float(qty_str.replace(',', ''))
                        month_num = month_map.get(month[:3], 1)
                        expiry_date = datetime(int(year), month_num, 1)
                        months_to_expiry = (expiry_date.year - current_date.year) * 12 + (expiry_date.month - current_date.month)

                        if months_to_expiry <= 3:
                            notifications.append({
                                'Material': row['Material Description'][:50],
                                'Priority': '🔴 CRITICAL',
                                'Quantity': int(qty),
                                'Expiry Date': expiry_date.strftime('%b-%Y'),
                                'Months Left': months_to_expiry
                            })
                    except:
                        continue

            if notifications:
                st.warning(f"⚠️ {len(notifications)} items with critical expiry (≤3 months)")
                st.dataframe(pd.DataFrame(notifications), use_container_width=True, hide_index=True)
            else:
                st.success("✅ No critical expiry items detected")

        # TAB 5: Program Comparison
        with aa_tab5:
            st.markdown("<h4 style='font-size: 22px; font-weight: bold;'>Program Performance Comparison</h4>", unsafe_allow_html=True)

            if google_sheets and len(google_sheets) > 0:
                program_metrics = []
                for program_name, program_df in google_sheets.items():
                    if program_df.empty or 'Material Description' not in program_df.columns:
                        continue

                    merged = program_df[['Material Description']].merge(
                        df[['Material Description', 'NMOS']], on='Material Description', how='left'
                    )
                    nmos_values = pd.to_numeric(merged['NMOS'], errors='coerce').dropna()

                    if len(nmos_values) > 0:
                        availability = (nmos_values > 1).mean() * 100
                        program_metrics.append({
                            'Program': program_name,
                            'Availability (%)': round(availability, 1),
                            'Materials': len(nmos_values)
                        })

                if program_metrics:
                    comparison_df = pd.DataFrame(program_metrics).sort_values('Availability (%)', ascending=False)
                    st.dataframe(comparison_df, use_container_width=True, hide_index=True)
                    st.metric("🏆 Top Program", comparison_df.iloc[0]['Program'])
                else:
                    st.info("No program comparison data available")

        # TAB 6: Regional Map
        with aa_tab6:
            st.markdown("<h4 style='font-size: 22px; font-weight: bold;'>Regional Stock Distribution Map</h4>", unsafe_allow_html=True)

            branch_coords = {
                'Adama Branch': [8.5483, 39.2696],
                'Addis Ababa Branch 1': [9.0320, 38.7469],
                'Bahir Dar Branch': [11.5742, 37.3613],
                'Dire Dawa Branch': [9.6000, 41.8500],
                'Hawassa Branch': [7.0500, 38.4667],
                'Mekele Branch': [13.4967, 39.4769]
            }

            map_data = []
            for branch, coords in branch_coords.items():
                if branch in df.columns:
                    avg_stock = pd.to_numeric(df[branch], errors='coerce').mean()
                    map_data.append({
                        'Branch': branch,
                        'Latitude': coords[0],
                        'Longitude': coords[1],
                        'Avg Stock': round(avg_stock, 0) if pd.notna(avg_stock) else 0
                    })

            if map_data:
                map_df = pd.DataFrame(map_data)
                fig = px.scatter_mapbox(map_df, lat='Latitude', lon='Longitude', size='Avg Stock', size_max=30,
                                        hover_name='Branch', hover_data=['Avg Stock'], zoom=5, height=500)
                fig.update_layout(mapbox_style='open-street-map')
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Map data not available")

        # TAB 7: Popular Materials
        with aa_tab7:
            st.markdown("<h4 style='font-size: 22px; font-weight: bold;'>Most Viewed Materials</h4>", unsafe_allow_html=True)

            if st.session_state.material_views:
                popular_df = pd.DataFrame([
                    {'Material': k[:50], 'Views': v} for k, v in st.session_state.material_views.items()
                ]).sort_values('Views', ascending=False).head(10)

                st.metric("👁️ Total Material Views", popular_df['Views'].sum())
                st.dataframe(popular_df, use_container_width=True, hide_index=True)
            else:
                st.info("No material view data yet")

        # TAB 8: User Analytics
        with aa_tab8:
            st.markdown("<h4 style='font-size: 22px; font-weight: bold;'>User Role Analytics</h4>", unsafe_allow_html=True)

            if st.session_state['user']['role'] == 'admin':
                if st.session_state.user_activity:
                    activity_df = pd.DataFrame(st.session_state.user_activity)
                    if not activity_df.empty:
                        role_summary = activity_df.groupby('role').agg({
                            'user': 'nunique',
                            'action': 'count'
                        }).rename(columns={'user': 'Unique Users', 'action': 'Total Actions'})
                        st.dataframe(role_summary, use_container_width=True)
                    else:
                        st.info("No user activity data yet")
                else:
                    st.info("No user activity data yet")
            else:
                st.info("User analytics are only available to administrators")

# ---------------------------------------------------
# Download Filtered Data
# ---------------------------------------------------
if not display_df_filtered.empty and 'Material Description' in display_df_filtered.columns and page != "Supply Planning" and page != "Executive Summary":
    st.divider()
    st.download_button(label="📥 Download Full Data (CSV)", data=display_df_filtered.to_csv(index=False), 
                      file_name=f"full_stock_dashboard_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", 
                      mime="text/csv", use_container_width=True)
