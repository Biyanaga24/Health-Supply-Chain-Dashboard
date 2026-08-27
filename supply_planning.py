import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
from io import BytesIO
import re
from supabase import create_client
import base64
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
import random

CACHE_TTL = 3600

# Custom CSS for better UI
def inject_custom_css():
    st.markdown("""
    <style>
        /* Global Styles */
        .main {
            padding: 0rem 1rem;
        }
        .stApp {
            background-color: #f8f9fa;
        }

        /* Font Styles - Times New Roman for main content */
        .main * {
            font-family: 'Times New Roman', Times, serif !important;
        }

        /* Sidebar - keep default font */
        .css-1d391kg, .sidebar-content, .stSidebar * {
            font-family: inherit !important;
        }

        /* Expander - keep default font */
        .streamlit-expanderHeader, .streamlit-expanderContent * {
            font-family: inherit !important;
        }

        /* Card Styles */
        .custom-card {
            background: white;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.08);
            margin: 10px 0;
            border-left: 4px solid #667eea;
            transition: transform 0.2s;
        }
        .custom-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 20px rgba(0,0,0,0.12);
        }

        /* Metric Cards */
        .metric-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 12px;
            padding: 15px 20px;
            color: white;
            text-align: center;
            margin: 5px 0;
        }
        .metric-card .metric-value {
            font-size: 28px;
            font-weight: 700;
            margin: 5px 0;
        }
        .metric-card .metric-label {
            font-size: 14px;
            opacity: 0.9;
        }

        /* Status Badges */
        .status-badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
        }
        .status-badge:hover {
            transform: scale(1.05);
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        }
        .status-badge.completed { background: #28a745; color: white; }
        .status-badge.ongoing { background: #007bff; color: white; }
        .status-badge.pending { background: #ffc107; color: #333; }
        .status-badge.initiated { background: #6f42c1; color: white; }

        /* Clickable Rows */
        .clickable-row {
            cursor: pointer;
            transition: background-color 0.2s;
        }
        .clickable-row:hover {
            background-color: #f0f0f0;
        }

        /* Tab Styles - Bold, Larger, No Card */
        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
            background-color: transparent;
            padding: 4px 0px;
            border-radius: 0px;
            box-shadow: none;
            border: none;
            border-bottom: 3px solid #e0e0e0;
        }
        .stTabs [data-baseweb="tab"] {
            border-radius: 8px 8px 0 0;
            padding: 14px 28px;
            font-weight: 700 !important;
            font-size: 20px !important;
            transition: all 0.3s;
            color: #777 !important;
            border: none;
            border-bottom: 4px solid transparent;
            letter-spacing: 0.5px;
            background-color: transparent !important;
        }
        .stTabs [data-baseweb="tab"]:hover {
            background-color: #f5f5f5 !important;
            color: #333 !important;
        }
        .stTabs [aria-selected="true"] {
            background-color: transparent !important;
            color: #9b111e !important;
            font-weight: 700 !important;
            font-size: 20px !important;
            border-bottom: 4px solid #9b111e;
            box-shadow: none;
        }
        .stTabs [data-baseweb="tab-list"] button {
            font-weight: 700 !important;
            font-size: 20px !important;
            letter-spacing: 0.5px;
        }

        /* Header Styles with Animation - Ruby color */
        .app-header {
            background: linear-gradient(135deg, #9b111e 0%, #e0115f 50%, #9b111e 100%);
            padding: 20px 30px;
            border-radius: 12px;
            margin-bottom: 20px;
            color: white;
            animation: slideIn 1s ease-out;
            box-shadow: 0 4px 20px rgba(155, 17, 30, 0.3);
        }
        @keyframes slideIn {
            0% {
                transform: translateX(-100%);
                opacity: 0;
            }
            100% {
                transform: translateX(0);
                opacity: 1;
            }
        }
        @keyframes slowMove {
            0% { transform: translateX(0); }
            50% { transform: translateX(10px); }
            100% { transform: translateX(0); }
        }
        .app-header h1 {
            margin: 0;
            font-weight: 700;
            animation: slowMove 3s ease-in-out infinite;
        }

        /* Table Styles */
        .dataframe-container {
            background: white;
            border-radius: 12px;
            padding: 15px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
            overflow-x: auto;
        }
        .dataframe-container th {
            background-color: #667eea;
            color: white;
            padding: 12px;
            font-family: 'Times New Roman', Times, serif !important;
            font-size: 14px;
        }
        .dataframe-container td {
            padding: 10px 12px;
            font-family: 'Times New Roman', Times, serif !important;
            font-size: 14px;
        }

        /* Button Styles */
        .stButton > button {
            border-radius: 8px;
            font-weight: 500;
            transition: all 0.3s;
        }
        .stButton > button:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
        }

        /* Expander Styles */
        .streamlit-expanderHeader {
            background-color: white;
            border-radius: 8px;
            font-weight: 500;
        }

        /* Sidebar Styles */
        .css-1d391kg {
            background-color: white;
        }

        /* Selectbox Styles - Gray background, black text */
        .stSelectbox > div > div {
            background-color: #e8e8e8 !important;
            color: #000000 !important;
            border-radius: 6px;
            border: 1px solid #ccc;
        }
        .stSelectbox > div > div > div {
            color: #000000 !important;
        }
        .stSelectbox label {
            color: #333 !important;
        }

        /* Dropdown options - Gray background, black text */
        .stSelectbox > div > div > div > div {
            background-color: #e8e8e8 !important;
            color: #000000 !important;
        }
        .stSelectbox > div > div > div > div:hover {
            background-color: #d0d0d0 !important;
        }

        /* Text inputs */
        .stTextInput > div > div > input {
            background-color: white !important;
            color: #333 !important;
            border-radius: 6px;
        }
        .stTextArea > div > div > textarea {
            background-color: white !important;
            color: #333 !important;
            border-radius: 6px;
        }

        /* Title Styles - Times New Roman */
        h1, h2, h3, h4, h5, h6 {
            font-family: 'Times New Roman', Times, serif !important;
        }

        /* Download Button */
        .download-btn {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 8px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.3s;
            text-decoration: none;
            display: inline-block;
        }
        .download-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
        }

        /* Scrollbar */
        ::-webkit-scrollbar {
            width: 8px;
            height: 8px;
        }
        ::-webkit-scrollbar-track {
            background: #f1f1f1;
            border-radius: 10px;
        }
        ::-webkit-scrollbar-thumb {
            background: #667eea;
            border-radius: 10px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: #764ba2;
        }

        /* Progress Status Cards - Colorful, Reduced Height */
        .progress-status-card {
            border-radius: 12px;
            padding: 8px 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.08);
            cursor: pointer;
            transition: all 0.3s;
            text-align: center;
            border: 3px solid transparent;
            min-height: 60px;
        }
        .progress-status-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 20px rgba(0,0,0,0.15);
        }
        .progress-status-card.active {
            border-color: #333;
            box-shadow: 0 4px 20px rgba(0,0,0,0.2);
        }
        .progress-status-card .status-number {
            font-size: 24px;
            font-weight: 700;
            font-family: 'Times New Roman', Times, serif !important;
            color: white;
            line-height: 1.2;
        }
        .progress-status-card .status-label {
            font-size: 12px;
            color: rgba(255,255,255,0.9);
            font-family: 'Times New Roman', Times, serif !important;
        }
        .progress-status-card .status-icon {
            font-size: 18px;
        }

        .progress-status-card.card-total { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
        .progress-status-card.card-completed { background: linear-gradient(135deg, #28a745 0%, #20c997 100%); }
        .progress-status-card.card-ongoing { background: linear-gradient(135deg, #007bff 0%, #4dabf7 100%); }
        .progress-status-card.card-pending { background: linear-gradient(135deg, #fcc419 0%, #ff922b 100%); }
        .progress-status-card.card-initiated { background: linear-gradient(135deg, #6f42c1 0%, #cc5de8 100%); }

        /* Progress Summary Row */
        .progress-summary-row {
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 10px;
            margin: 10px 0 15px 0;
        }
        @media (max-width: 768px) {
            .progress-summary-row {
                grid-template-columns: repeat(3, 1fr);
            }
        }
        @media (max-width: 480px) {
            .progress-summary-row {
                grid-template-columns: 1fr;
            }
        }

        /* Filter Row */
        .filter-row {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 15px;
            margin: 15px 0;
            background: white;
            padding: 15px;
            border-radius: 12px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        }
        @media (max-width: 768px) {
            .filter-row {
                grid-template-columns: 1fr;
            }
        }

        /* Material Info Card - Ruby color */
        .material-info-card {
            background: linear-gradient(135deg, #9b111e 0%, #e0115f 50%, #9b111e 100%);
            padding: 25px;
            border-radius: 12px;
            border: none;
            margin: 10px 0;
            box-shadow: 0 4px 20px rgba(155, 17, 30, 0.3);
        }
        .material-info-card h4 {
            color: white;
            font-size: 20px;
            font-weight: 700;
        }
        .material-info-card .info-row {
            padding: 8px 12px;
            border-radius: 6px;
            background: rgba(255,255,255,0.15);
            color: white;
        }

        /* Action Buttons */
        .action-btn-group {
            display: flex;
            gap: 10px;
            margin: 10px 0;
            flex-wrap: wrap;
        }
        .action-btn-group .stButton {
            flex: 1;
        }

        /* Filter Row Title */
        .filter-title {
            font-size: 16px;
            font-weight: 600;
            color: #333;
            margin-bottom: 5px;
            font-family: 'Times New Roman', Times, serif !important;
        }

        /* Progress Summary Title */
        .progress-summary-title {
            font-size: 18px;
            font-weight: 700;
            color: #333;
            margin: 5px 0 5px 0;
            font-family: 'Times New Roman', Times, serif !important;
        }

        /* Time Range Selector */
        .time-range-selector {
            background: white;
            padding: 15px 20px;
            border-radius: 12px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
            margin: 10px 0;
            border-left: 4px solid #667eea;
        }
        .time-range-selector label {
            font-weight: 600;
            color: #333;
            font-family: 'Times New Roman', Times, serif !important;
        }

        /* Progress Status Summary - Reduced height */
        .progress-summary-container {
            margin-bottom: 10px;
        }
        .progress-summary-container .stColumns {
            gap: 5px;
        }

        /* Expert Action Card */
        .expert-action-card {
            background: white;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.08);
            margin: 10px 0;
            border-left: 4px solid #9b111e;
        }
        .expert-action-card h4 {
            color: #9b111e;
            font-weight: 700;
        }

        /* Status Distribution Summary */
        .status-distribution-card {
            background: white;
            border-radius: 12px;
            padding: 15px 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
            margin: 10px 0;
            border-left: 4px solid #667eea;
        }
        .status-distribution-card h3 {
            font-size: 18px;
            font-weight: 700;
            color: #333;
            margin-bottom: 10px;
            font-family: 'Times New Roman', Times, serif !important;
        }
        .status-distribution-item {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 6px 0;
            font-family: 'Times New Roman', Times, serif !important;
        }
        .status-distribution-item .status-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            display: inline-block;
        }
        .status-distribution-item .status-label {
            font-weight: 600;
            min-width: 100px;
            font-family: 'Times New Roman', Times, serif !important;
        }
        .status-distribution-item .status-count {
            font-weight: 700;
            font-family: 'Times New Roman', Times, serif !important;
        }

        /* Two-column layout for charts */
        .chart-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin: 10px 0;
        }
        @media (max-width: 768px) {
            .chart-row {
                grid-template-columns: 1fr;
            }
        }

        /* Clear axis lines for charts */
        .js-plotly-plot .plotly .main-svg {
            overflow: visible !important;
        }
        .js-plotly-plot .plotly .xaxislayer-above, 
        .js-plotly-plot .plotly .yaxislayer-above {
            stroke: #333 !important;
            stroke-width: 1.5px !important;
        }
    </style>
    """, unsafe_allow_html=True)

# Helper function to sort months chronologically
def sort_months_chronologically(month_list):
    """Sort month strings (MMM-YYYY) chronologically"""
    def parse_month(month_str):
        try:
            return pd.to_datetime(month_str, format='%b-%Y')
        except:
            # Manual fallback
            try:
                mon, year = month_str.split('-')
                month_map = {'Jan':1, 'Feb':2, 'Mar':3, 'Apr':4, 'May':5, 'Jun':6,
                            'Jul':7, 'Aug':8, 'Sep':9, 'Oct':10, 'Nov':11, 'Dec':12}
                return datetime(int(year), month_map.get(mon[:3], 1), 1)
            except:
                return datetime(1900, 1, 1)
    return sorted(month_list, key=parse_month)

# JavaScript for click handlers
def inject_javascript():
    st.markdown("""
    <script>
        // Click handler for status badges
        document.addEventListener('click', function(e) {
            const badge = e.target.closest('.status-badge');
            if (badge) {
                const status = badge.dataset.status;
                const material = badge.dataset.material;
                window.parent.postMessage({
                    type: 'status_click',
                    status: status,
                    material: material
                }, '*');
            }
        });

        // Click handler for table rows
        document.addEventListener('click', function(e) {
            const row = e.target.closest('.clickable-row');
            if (row) {
                const material = row.dataset.material;
                window.parent.postMessage({
                    type: 'row_click',
                    material: material
                }, '*');
            }
        });

        // Click handler for progress status cards
        document.addEventListener('click', function(e) {
            const card = e.target.closest('.progress-status-card');
            if (card) {
                const status = card.dataset.status;
                window.parent.postMessage({
                    type: 'status_filter',
                    status: status
                }, '*');
            }
        });
    </script>
    """, unsafe_allow_html=True)

@st.cache_resource
def init_supabase():
    try:
        supabase_url = st.secrets["SUPABASE_URL"]
        supabase_key = st.secrets["SUPABASE_KEY"]
        return create_client(supabase_url, supabase_key)
    except Exception as e:
        st.error(f"Supabase connection error: {e}")
        return None

_supabase = None

def get_supabase():
    global _supabase
    if _supabase is None:
        _supabase = init_supabase()
    return _supabase

# ============================================================================
# RESPONSIBLE BODY DROPDOWN OPTIONS
# ============================================================================

RESPONSIBLE_BODIES = [
    "EPSS_CMD",
    "EPSS_DMD", 
    "EPSS_PMD",
    "EPSS_Finance",
    "MOH_PMED",
    "MOH_Program",
    "MSH_SCS",
    "Other"
]

# ============================================================================
# OPTIMIZED DATA LOADING FUNCTIONS
# ============================================================================

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def load_national_data_raw():
    """Load raw national data from Supabase - cached"""
    supabase = get_supabase()
    if supabase is None:
        return pd.DataFrame()
    try:
        all_data = []
        page = 0
        page_size = 1000
        while True:
            response = supabase.table("health_data") \
                .select("*") \
                .range(page * page_size, (page + 1) * page_size - 1) \
                .execute()
            if not response.data:
                break
            all_data.extend(response.data)
            if len(response.data) < page_size:
                break
            page += 1
        if not all_data:
            return pd.DataFrame()
        df = pd.DataFrame(all_data)
        if 'id' in df.columns:
            df = df.drop(columns=['id'])
        return df
    except Exception as e:
        st.error(f"Error loading national data: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def process_national_data(df):
    """Process raw national data - cached"""
    if df.empty:
        return df

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

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def load_national_data():
    """Main function to load and process national data with caching"""
    df_raw = load_national_data_raw()
    if df_raw.empty:
        return pd.DataFrame()
    return process_national_data(df_raw)

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def load_issue_data_raw():
    """Load raw issue data from Supabase - cached"""
    supabase = get_supabase()
    if supabase is None:
        return pd.DataFrame()
    try:
        all_data = []
        page = 0
        page_size = 1000
        while True:
            response = supabase.table("issue_data") \
                .select("material_descr, plant, delivery_date, region_descr, quantity") \
                .range(page * page_size, (page + 1) * page_size - 1) \
                .execute()
            if not response.data:
                break
            all_data.extend(response.data)
            if len(response.data) < page_size:
                break
            page += 1
        if not all_data:
            return pd.DataFrame()
        return pd.DataFrame(all_data)
    except Exception as e:
        st.warning(f"Could not load issue data: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def process_issue_data(df):
    """Process raw issue data - cached"""
    if df.empty:
        return df

    df = df.rename(columns={
        'material_descr': 'Material Description',
        'plant': 'Plant',
        'delivery_date': 'Delivery Date',
        'region_descr': 'Region',
        'quantity': 'Quantity'
    })
    df['Quantity'] = pd.to_numeric(df['Quantity'], errors='coerce').fillna(0)
    if 'Delivery Date' in df.columns:
        df['Delivery Date'] = pd.to_datetime(df['Delivery Date'], errors='coerce')
    return df

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def load_issue_data():
    """Main function to load and process issue data with caching"""
    df_raw = load_issue_data_raw()
    if df_raw.empty:
        return pd.DataFrame()
    return process_issue_data(df_raw)

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def load_new_deliveries_raw():
    """Load raw new deliveries data from Supabase - cached"""
    supabase = get_supabase()
    if supabase is None:
        return pd.DataFrame()
    try:
        response = supabase.table("new_deliveries") \
            .select("*") \
            .execute()
        if not response.data:
            return pd.DataFrame()
        return pd.DataFrame(response.data)
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def process_new_deliveries(df):
    """Process raw new deliveries data - cached"""
    if df.empty:
        return df

    possible_material = ['material_description', 'material_descr', 'material', 'item_description', 'item']
    possible_date = ['posting_date', 'postingdate', 'date', 'delivery_date', 'deliverydate']
    possible_qty = ['quantity', 'qty', 'delivered_quantity', 'delivered_qty', 'order_qty']

    material_col = None
    date_col = None
    qty_col = None

    for col in df.columns:
        col_lower = col.lower().strip()
        if material_col is None and any(p in col_lower for p in possible_material):
            material_col = col
        if date_col is None and any(p in col_lower for p in possible_date):
            date_col = col
        if qty_col is None and any(p in col_lower for p in possible_qty):
            qty_col = col

    if material_col is None or date_col is None or qty_col is None:
        return pd.DataFrame()

    df = df.rename(columns={
        material_col: 'Material Description',
        date_col: 'Posting Date',
        qty_col: 'Quantity'
    })
    df['Quantity'] = pd.to_numeric(df['Quantity'], errors='coerce').fillna(0)
    df['Posting Date'] = pd.to_datetime(df['Posting Date'], errors='coerce')
    df = df.dropna(subset=['Posting Date'])
    df = df[['Material Description', 'Posting Date', 'Quantity']]
    return df

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def load_new_deliveries():
    """Main function to load and process new deliveries data with caching"""
    df_raw = load_new_deliveries_raw()
    if df_raw.empty:
        return pd.DataFrame()
    return process_new_deliveries(df_raw)

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def load_google_sheets_raw(sheet_id):
    """Load raw Google Sheets data - cached with better error handling"""
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
    try:
        # Use a session with proper headers to mimic a browser
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        session.trust_env = False
        response = session.get(url, timeout=60)
        response.raise_for_status()
        return response.content
    except requests.exceptions.RequestException as e:
        st.warning(f"Could not load Google Sheets: {e}")
        return None
    except Exception as e:
        st.warning(f"Unexpected error loading Google Sheets: {e}")
        return None

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def process_google_sheets(content, sheet_id):
    """Process raw Google Sheets data - cached"""
    if content is None:
        return {}
    try:
        # Try with openpyxl engine first
        sheets = pd.read_excel(BytesIO(content), sheet_name=None, header=2, engine='openpyxl')
        cleaned = {}
        for name, df in sheets.items():
            if df.empty:
                cleaned[name] = df
                continue
            df = df.loc[:, ~df.columns.str.contains("^Unnamed")]
            df.columns = df.columns.str.strip()
            for col in df.columns:
                if df[col].dtype == 'object':
                    df[col] = df[col].fillna("")
            cleaned[name] = df
        return cleaned
    except Exception as e:
        st.warning(f"Error processing Google Sheets with openpyxl: {e}")
        try:
            # Try with xlrd engine as fallback
            sheets = pd.read_excel(BytesIO(content), sheet_name=None, header=2, engine='xlrd')
            cleaned = {}
            for name, df in sheets.items():
                if df.empty:
                    cleaned[name] = df
                    continue
                df = df.loc[:, ~df.columns.str.contains("^Unnamed")]
                df.columns = df.columns.str.strip()
                for col in df.columns:
                    if df[col].dtype == 'object':
                        df[col] = df[col].fillna("")
                cleaned[name] = df
            return cleaned
        except Exception as e2:
            st.warning(f"Error processing Google Sheets with xlrd: {e2}")
            return {}

def load_google_sheets_fallback():
    """Provide fallback program data if Google Sheets fails to load"""
    fallback_programs = {
        "Malaria": pd.DataFrame(),
        "HIV": pd.DataFrame(),
        "TB": pd.DataFrame(),
        "OI and Hepatitis": pd.DataFrame(),
        "Nutrition": pd.DataFrame(),
        "Lab TB": pd.DataFrame(),
        "HIV Lab": pd.DataFrame()
    }
    return fallback_programs

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def load_google_sheets(sheet_id):
    """Main function to load and process Google Sheets data with caching and fallback"""
    content = load_google_sheets_raw(sheet_id)
    if content is None:
        st.warning("Using fallback program data. Google Sheets could not be loaded.")
        return load_google_sheets_fallback()
    result = process_google_sheets(content, sheet_id)
    if not result:
        st.warning("Using fallback program data. Google Sheets data could not be processed.")
        return load_google_sheets_fallback()
    return result

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def load_branch_amc_raw(sheet_id):
    """Load raw branch AMC data - cached"""
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
    try:
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        session.trust_env = False
        response = session.get(url, timeout=45)
        response.raise_for_status()
        return response.content
    except Exception:
        return None

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def process_branch_amc(content):
    """Process raw branch AMC data - cached"""
    if content is None:
        return pd.DataFrame()
    try:
        df = pd.read_excel(BytesIO(content), header=0)
        df = df.loc[:, ~df.columns.str.contains("^Unnamed")]
        df.columns = df.columns.str.strip()
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].fillna("")
        return df
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def load_branch_amc(sheet_id):
    """Main function to load and process branch AMC data with caching"""
    content = load_branch_amc_raw(sheet_id)
    if content is None:
        return pd.DataFrame()
    return process_branch_amc(content)

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def load_ho_nsoh_snapshots_raw():
    """Load raw HO NSOH snapshots from Supabase - cached"""
    supabase = get_supabase()
    if supabase is None:
        return pd.DataFrame()
    try:
        all_data = []
        page = 0
        page_size = 1000
        while True:
            response = supabase.table("ho_nsoh_snapshots") \
                .select("*") \
                .order("snapshot_date") \
                .range(page * page_size, (page + 1) * page_size - 1) \
                .execute()
            if not response.data:
                break
            all_data.extend(response.data)
            if len(response.data) < page_size:
                break
            page += 1
        if not all_data:
            return pd.DataFrame()
        return pd.DataFrame(all_data)
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def process_ho_nsoh_snapshots(df):
    """Process raw HO NSOH snapshots - cached"""
    if df.empty:
        return df
    if 'snapshot_date' in df.columns:
        df['snapshot_date'] = pd.to_datetime(df['snapshot_date']).dt.date
    return df

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def load_ho_nsoh_snapshots():
    """Main function to load and process HO NSOH snapshots with caching"""
    df_raw = load_ho_nsoh_snapshots_raw()
    if df_raw.empty:
        return pd.DataFrame()
    return process_ho_nsoh_snapshots(df_raw)

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def load_dos_tracking_raw():
    """Load raw DOS tracking data - cached"""
    supabase = get_supabase()
    if supabase is None:
        return {}
    try:
        response = supabase.table("dos_tracking").select("*").execute()
        if response.data:
            dos_tracking = {}
            for rec in response.data:
                material = rec['material_description']
                dos_tracking[material] = {
                    'days': rec.get('current_dos', 0),
                    'is_out_of_stock': rec.get('is_out_of_stock', False)
                }
            return dos_tracking
        return {}
    except Exception:
        return {}

def load_dos_tracking():
    """Load DOS tracking data (not cached for writes)"""
    return load_dos_tracking_raw()

def save_dos_tracking(dos_tracking):
    """Save DOS tracking data"""
    supabase = get_supabase()
    if supabase is None:
        return False
    try:
        records = []
        for material, data in dos_tracking.items():
            records.append({
                'material_description': material,
                'current_dos': data['days'],
                'is_out_of_stock': data['is_out_of_stock']
            })
        if records:
            supabase.table("dos_tracking").upsert(records).execute()
            return True
        return False
    except Exception:
        return False

# ============================================================================
# EXPERT PLAN RECORDS DATABASE FUNCTIONS
# ============================================================================

@st.cache_data(ttl=300, show_spinner=False)
def load_expert_plan_records(program=None, quarter=None, year=None):
    """Load expert plan records from Supabase, optionally filtered by program, quarter, year"""
    supabase = get_supabase()
    if supabase is None:
        return []
    try:
        query = supabase.table("expert_plan_records").select("*")
        if program:
            query = query.eq("program", program)
        if quarter:
            query = query.eq("quarter", quarter)
        if year:
            query = query.eq("year", year)
        response = query.order("created_at", desc=True).execute()

        if response.data:
            records = []
            for rec in response.data:
                records.append({
                    'record_id': rec.get('record_id'),
                    'Material': rec.get('material'),
                    'NSOH': rec.get('nsoh'),
                    'AMC': rec.get('amc'),
                    'PMOS': rec.get('pmos'),
                    'NMOS': rec.get('nmos'),
                    'TMOS': rec.get('tmos'),
                    'Purchase Order': rec.get('purchase_order'),
                    'Order Quantity': rec.get('order_quantity'),
                    'Identified Problem': rec.get('identified_problem'),
                    'Action Point': rec.get('action_point'),
                    'Responsible Body': rec.get('responsible_body'),
                    'Due Date': rec.get('due_date'),
                    'Status': rec.get('status', 'Pending'),
                    'Quarter': rec.get('quarter'),
                    'Year': rec.get('year'),
                    'Program': rec.get('program')
                })
            return records
        return []
    except Exception as e:
        st.warning(f"Could not load expert plan records: {e}")
        return []

def save_expert_plan_record(record):
    """Save a single expert plan record to Supabase"""
    supabase = get_supabase()
    if supabase is None:
        return False
    try:
        data = {
            'record_id': record.get('record_id'),
            'material': record.get('Material'),
            'nsoh': record.get('NSOH'),
            'amc': record.get('AMC'),
            'pmos': record.get('PMOS'),
            'nmos': record.get('NMOS'),
            'tmos': record.get('TMOS'),
            'purchase_order': record.get('Purchase Order'),
            'order_quantity': record.get('Order Quantity'),
            'identified_problem': record.get('Identified Problem'),
            'action_point': record.get('Action Point'),
            'responsible_body': record.get('Responsible Body'),
            'due_date': record.get('Due Date'),
            'status': record.get('Status', 'Pending'),
            'quarter': record.get('Quarter'),
            'year': int(record.get('Year')) if record.get('Year') else None,
            'program': record.get('Program')
        }

        response = supabase.table("expert_plan_records") \
            .upsert(data, on_conflict="record_id") \
            .execute()

        load_expert_plan_records.clear()
        return True
    except Exception as e:
        st.error(f"Error saving expert plan record: {e}")
        return False

def delete_expert_plan_record(record_id):
    """Delete an expert plan record from Supabase"""
    supabase = get_supabase()
    if supabase is None:
        return False
    try:
        response = supabase.table("expert_plan_records") \
            .delete() \
            .eq("record_id", record_id) \
            .execute()

        load_expert_plan_records.clear()
        return True
    except Exception as e:
        st.error(f"Error deleting expert plan record: {e}")
        return False

# ============================================================================
# END OF DATABASE FUNCTIONS
# ============================================================================

def calculate_dos(df):
    current_date = datetime.now().date()
    dos_tracking = load_dos_tracking()
    updated = {}
    for idx, row in df.iterrows():
        material = row.get('Material Description')
        if pd.isna(material):
            continue
        nmos = row.get('NMOS', 1)
        if pd.isna(nmos):
            nmos = 1
        is_out = nmos < 1
        if material not in dos_tracking:
            updated[material] = {
                'days': 1 if is_out else 0,
                'is_out_of_stock': is_out
            }
        else:
            prev = dos_tracking[material]
            if is_out:
                days = prev.get('days', 0) + 1
                updated[material] = {
                    'days': days,
                    'is_out_of_stock': True
                }
            else:
                updated[material] = {
                    'days': 0,
                    'is_out_of_stock': False
                }
    save_dos_tracking(updated)
    return {material: data['days'] for material, data in updated.items()}

def format_number_with_commas(x):
    try:
        if pd.isna(x) or x is None:
            return ""
        x = float(x)
        return f"{int(round(x)):,}"
    except:
        return str(x)

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
        if pd.isna(nmos):
            return ""
        x = float(nmos)
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
    values = pd.to_numeric(values, errors='coerce')
    values = values[values.notna() & (values > 0)]
    if len(values) > 1:
        mean = values.mean()
        std = values.std()
        if mean > 0:
            return (std / mean) * 100
    return np.nan

def calculate_risk(row):
    try:
        nmos = row.get('NMOS', np.nan)
        if pd.isna(nmos) or nmos < 1:
            return ""
        git_mos = row.get('GIT_MOS', 0) or 0
        lc_mos = row.get('LC_MOS', 0) or 0
        wb_mos = row.get('WB_MOS', 0) or 0
        tmd_mos = row.get('TMD_MOS', 0) or 0
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

def parse_multiple_expiry_batches(expiry_str, amc):
    try:
        if pd.isna(expiry_str) or expiry_str == "" or expiry_str is None:
            return [], amc if pd.notna(amc) else 0

        expiry_str = str(expiry_str)
        pattern = r'(\d[\d,]*)\s*\(([A-Za-z]+)-(\d{4})\)'
        matches = re.findall(pattern, expiry_str)

        if not matches:
            return [], amc if pd.notna(amc) else 0

        batches = []
        month_map = {'Jan':1, 'Feb':2, 'Mar':3, 'Apr':4, 'May':5, 'Jun':6,
                    'Jul':7, 'Aug':8, 'Sep':9, 'Oct':10, 'Nov':11, 'Dec':12}

        for quantity_str, month, year in matches:
            quantity = float(quantity_str.replace(',', ''))
            month_num = month_map.get(month[:3], 1)
            expiry_date = datetime(int(year), month_num, 1)

            if pd.notna(amc) and amc > 0:
                remaining_mos = quantity / amc
            else:
                remaining_mos = 0

            batches.append({
                'quantity': quantity,
                'expiry_date': expiry_date,
                'remaining_mos': round(remaining_mos, 2)
            })

        batches.sort(key=lambda x: x['expiry_date'])

        if pd.isna(amc) or amc <= 0:
            return batches, 0

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

        return batches, has_risk
    except Exception:
        return [], amc if pd.notna(amc) else 0

def get_pipeline_recommendation(row):
    git_mos = row.get('GIT_MOS', 0)
    lc_mos = row.get('LC_MOS', 0)
    wb_mos = row.get('WB_MOS', 0)
    tmd_mos = row.get('TMD_MOS', 0)
    git_po = row.get('GIT_PO', '')
    lc_po = row.get('LC_PO', '')
    wb_po = row.get('WB_PO', '')
    tmd_po = row.get('TMD_PO', '')
    try:
        git_mos = float(git_mos) if pd.notna(git_mos) else 0
        lc_mos = float(lc_mos) if pd.notna(lc_mos) else 0
        wb_mos = float(wb_mos) if pd.notna(wb_mos) else 0
        tmd_mos = float(tmd_mos) if pd.notna(tmd_mos) else 0
    except:
        return "Review supply chain - invalid MOS values", "EPSS_DMD"
    if git_mos > 0 and git_po and str(git_po) != 'nan' and str(git_po) != '':
        return f"Expedite the shipment of PO: {str(git_po).strip()}", "EPSS_CMD"
    elif lc_mos > 0 and lc_po and str(lc_po) != 'nan' and str(lc_po) != '':
        return f"Expedite the LC opening process of PO: {str(lc_po).strip()}", "EPSS_CMD"
    elif wb_mos > 0 and wb_po and str(wb_po) != 'nan' and str(wb_po) != '':
        return f"Expedite budget transfer for PO: {str(wb_po).strip()}", "MOH"
    elif tmd_mos > 0 and tmd_po and str(tmd_po) != 'nan' and str(tmd_po) != '':
        return f"Expedite the tender process and request for PO: {str(tmd_po).strip()}", "EPSS_TMD"
    else:
        return "No pipeline stock - initiate procurement", "MOH"

def get_expiry_risk_action(row):
    cv_category = row.get('CV Category', 'Unknown')
    hubs_pct = row.get('Hubs%', 0)
    ho_pct = row.get('Head Office%', 0)
    try:
        hubs_pct = float(hubs_pct) if pd.notna(hubs_pct) else 0
        ho_pct = float(ho_pct) if pd.notna(ho_pct) else 0
    except:
        hubs_pct = 0
        ho_pct = 0
    if cv_category == 'High variation':
        return "Redistribution required - high variation across hubs", "EPSS_DMD, Branch Managers"
    elif hubs_pct < ho_pct:
        return "Push stock to hubs - hubs have lower stock than head office", "EPSS_DMD, Logistics"
    else:
        return "Explore donation options - excess stock that may expire", "EPSS_DMD, MOH"

def get_total_pipeline_mos(row):
    git_mos = row.get('GIT_MOS', 0)
    lc_mos = row.get('LC_MOS', 0)
    wb_mos = row.get('WB_MOS', 0)
    tmd_mos = row.get('TMD_MOS', 0)
    try:
        return float(git_mos) + float(lc_mos) + float(wb_mos) + float(tmd_mos)
    except:
        return 0

def get_end_of_month_date(year, month):
    year = int(year)
    month = int(month)
    if month == 12:
        next_month = 1
        next_year = year + 1
    else:
        next_month = month + 1
        next_year = year
    last_day = (datetime(next_year, next_month, 1) - timedelta(days=1)).day
    return datetime(year, month, last_day)

def calculate_due_date_for_pipeline(tmos_value):
    current_date = datetime.now()
    if tmos_value < 8:
        return "IMMEDIATELY"
    else:
        months_until_need = tmos_value - 8
        if months_until_need <= 0.3:
            first_day = current_date.replace(day=1)
            return f"Beginning of this month ({first_day.strftime('%d %b %Y')})"
        elif months_until_need <= 0.7:
            last_day = get_end_of_month_date(current_date.year, current_date.month)
            return f"End of this month ({last_day.strftime('%d %b %Y')})"
        else:
            target_date = current_date + timedelta(days=int(months_until_need * 30))
            return f"By {target_date.strftime('%d %b %Y')}"

def has_pipeline(row):
    return get_total_pipeline_mos(row) > 0

PROGRAM_ORDER_LIST = [
    "Malaria",
    "HIV", 
    "OI and Hepatitis",
    "Hepatitis",
    "STI",
    "TB",
    "Drug Susceptible -TB Medicine (DS-TB)",
    "Drug Resisitance -TB Medicine (DR-TB)",
    "Leprosy Medicines",
    "Nutrition",
    "Lab TB",
    "TB diagnostics& Laboratory reagent",
    "TB Lab Supplies",
    "HIV Lab",
    "HIV VL Reagents",
    "CD4 ,AHD &HIV RTKs"
]

@st.cache_data(ttl=CACHE_TTL)
def get_program_materials(sheet_name):
    sheet_id = "14VvZ7IyOmpM4SZrY5_ArHDgLkeFN4inW"
    google_sheets = load_google_sheets(sheet_id)
    ordered = []
    if google_sheets:
        if sheet_name == "All":
            for prog in PROGRAM_ORDER_LIST:
                if prog in google_sheets and 'Material Description' in google_sheets[prog].columns:
                    for mat in google_sheets[prog]['Material Description'].dropna().tolist():
                        if mat not in ordered:
                            ordered.append(mat)
            for prog in google_sheets.keys():
                if prog not in PROGRAM_ORDER_LIST and 'Material Description' in google_sheets[prog].columns:
                    for mat in google_sheets[prog]['Material Description'].dropna().tolist():
                        if mat not in ordered:
                            ordered.append(mat)
        else:
            if sheet_name in google_sheets and 'Material Description' in google_sheets[sheet_name].columns:
                ordered = google_sheets[sheet_name]['Material Description'].dropna().tolist()
    return tuple(ordered)

def get_material_program(material_name, sheet_name):
    """Get the program name for a material"""
    if sheet_name != "All":
        return sheet_name

    sheet_id = "14VvZ7IyOmpM4SZrY5_ArHDgLkeFN4inW"
    google_sheets = load_google_sheets(sheet_id)

    if google_sheets:
        for prog in PROGRAM_ORDER_LIST:
            if prog in google_sheets and 'Material Description' in google_sheets[prog].columns:
                materials = google_sheets[prog]['Material Description'].dropna().tolist()
                if material_name in materials:
                    return prog
        # Check other sheets not in PROGRAM_ORDER_LIST
        for prog in google_sheets.keys():
            if prog not in PROGRAM_ORDER_LIST and 'Material Description' in google_sheets[prog].columns:
                materials = google_sheets[prog]['Material Description'].dropna().tolist()
                if material_name in materials:
                    return prog
    return "Multiple Programs"

def order_df_by_program(df, ordered_materials_tuple, material_col='Material Description'):
    if df.empty or material_col not in df.columns:
        return df
    order_map = {mat: idx for idx, mat in enumerate(ordered_materials_tuple)}
    df['_order'] = df[material_col].map(order_map)
    df['_order'] = df['_order'].fillna(len(ordered_materials_tuple) + 1)
    df = df.sort_values('_order')
    df = df.drop(columns=['_order'])
    return df

@st.cache_data(ttl=CACHE_TTL)
def compute_nsoh_pivot():
    df = load_ho_nsoh_snapshots()
    if df.empty:
        return pd.DataFrame()
    df['month_year'] = pd.to_datetime(df['snapshot_date']).dt.strftime('%b-%Y')
    pivot = df.pivot_table(index='material_description', columns='month_year', values='nsoh', aggfunc='first')
    month_cols = [c for c in pivot.columns]
    month_cols_sorted = sort_months_chronologically(month_cols)
    pivot = pivot[month_cols_sorted]
    pivot = pivot.reset_index().rename(columns={'material_description': 'Material Description'})
    return pivot

@st.cache_data(ttl=CACHE_TTL)
def compute_issue_pivot(program_materials_tuple):
    issue_data = load_issue_data()
    if issue_data.empty:
        return pd.DataFrame()
    if program_materials_tuple:
        filtered = issue_data[issue_data['Material Description'].isin(program_materials_tuple)]
        filtered = filtered[~filtered['Plant'].str.contains('Head Office|HO01', case=False, na=False)]
        if 'Delivery Date' in filtered.columns and not filtered.empty:
            monthly = filtered.copy()
            monthly['Month'] = monthly['Delivery Date'].dt.strftime('%b-%Y')
            pivot = monthly.groupby(['Material Description', 'Month'])['Quantity'].sum().reset_index()
            pivot = pivot.pivot_table(index='Material Description', columns='Month', values='Quantity', fill_value=0)
            if not pivot.empty:
                month_order = sort_months_chronologically(list(pivot.columns))
                pivot = pivot[month_order]
                pivot = pivot.reset_index()
                return pivot
    return pd.DataFrame()

@st.cache_data(ttl=CACHE_TTL)
def compute_new_deliveries_pivot(program_materials_tuple):
    deliveries = load_new_deliveries()
    if deliveries.empty:
        return pd.DataFrame()
    if program_materials_tuple:
        filtered = deliveries[deliveries['Material Description'].isin(program_materials_tuple)]
        if 'Posting Date' in filtered.columns and not filtered.empty:
            monthly = filtered.copy()
            monthly['Month'] = monthly['Posting Date'].dt.strftime('%b-%Y')
            pivot = monthly.groupby(['Material Description', 'Month'])['Quantity'].sum().reset_index()
            pivot = pivot.pivot_table(index='Material Description', columns='Month', values='Quantity', fill_value=0)
            if not pivot.empty:
                month_order = sort_months_chronologically(list(pivot.columns))
                pivot = pivot[month_order]
                pivot = pivot.reset_index()
                return pivot
    return pd.DataFrame()

@st.cache_data(ttl=CACHE_TTL)
def compute_consumption_pivot(program_materials_tuple):
    nsoh_raw = load_ho_nsoh_snapshots()
    deliveries_raw = load_new_deliveries()
    if nsoh_raw.empty or deliveries_raw.empty:
        return pd.DataFrame()
    if program_materials_tuple:
        nsoh_raw = nsoh_raw[nsoh_raw['material_description'].isin(program_materials_tuple)]
        deliveries_raw = deliveries_raw[deliveries_raw['Material Description'].isin(program_materials_tuple)]
    else:
        return pd.DataFrame()
    nsoh_raw['Month'] = pd.to_datetime(nsoh_raw['snapshot_date']).dt.strftime('%b-%Y')
    deliveries_raw['Month'] = deliveries_raw['Posting Date'].dt.strftime('%b-%Y')
    deliveries_agg = deliveries_raw.groupby(['Material Description', 'Month'])['Quantity'].sum().reset_index()
    nsoh_agg = nsoh_raw.groupby(['material_description', 'Month'])['nsoh'].first().reset_index()
    nsoh_agg.rename(columns={'material_description': 'Material Description', 'nsoh': 'NSOH'}, inplace=True)
    combined = pd.merge(nsoh_agg, deliveries_agg, on=['Material Description', 'Month'], how='outer')
    combined.fillna({'NSOH': 0, 'Quantity': 0}, inplace=True)
    combined['Month_dt'] = pd.to_datetime(combined['Month'], format='%b-%Y')
    combined.sort_values(['Material Description', 'Month_dt'], inplace=True)
    combined['Prev_NSOH'] = combined.groupby('Material Description')['NSOH'].shift(1)
    combined['Consumption'] = combined['Prev_NSOH'] - combined['NSOH'] + combined['Quantity']
    combined.loc[combined['Prev_NSOH'].isna(), 'Consumption'] = np.nan
    combined.loc[combined['Consumption'] < 0, 'Consumption'] = 0
    pivot = combined.pivot_table(index='Material Description', columns='Month', values='Consumption', aggfunc='first')
    month_order = sort_months_chronologically(list(pivot.columns))
    pivot = pivot[month_order]
    pivot = pivot.reset_index().rename(columns={'index': 'Material Description'})
    return pivot

@st.cache_data(ttl=CACHE_TTL)
def get_filtered_data(sheet_name, subcategory_filter):
    df_national = load_national_data()
    sheet_id_amc = "14VvZ7IyOmpM4SZrY5_ArHDgLkeFN4inW"
    google_sheets = load_google_sheets(sheet_id_amc)
    branch_amc_data = load_branch_amc("12Z5xqX32QIzjoN6tNvGbjutMheXx5US1")

    if sheet_name == "All" and google_sheets:
        all_dfs = []
        for name, df_prog in google_sheets.items():
            if df_prog.empty:
                continue
            df_copy = df_prog.copy()
            df_copy.columns = df_copy.columns.astype(str)
            if df_copy.columns.duplicated().any():
                df_copy = df_copy.loc[:, ~df_copy.columns.duplicated()]
            all_dfs.append(df_copy)
        if all_dfs:
            df_google = pd.concat(all_dfs, ignore_index=True, sort=False)
        else:
            df_google = pd.DataFrame()
    elif google_sheets and sheet_name in google_sheets:
        df_google = google_sheets[sheet_name].copy()
        df_google.columns = df_google.columns.astype(str)
        if df_google.columns.duplicated().any():
            df_google = df_google.loc[:, ~df_google.columns.duplicated()]
    else:
        df_google = pd.DataFrame()

    if not df_google.empty and not df_national.empty:
        required_cols = ['Material Description', 'AMC', 'GIT_PO', 'GIT_Qty', 'GIT_MOS',
                         'LC_PO', 'LC_Qty', 'LC_MOS', 'WB_PO', 'WB_Qty', 'WB_MOS',
                         'TMD_PO', 'TMD_Qty', 'TMD_MOS', "Status"]
        available_cols = [c for c in required_cols if c in df_google.columns]
        df_google = df_google[available_cols]
        df_national = df_national.drop_duplicates(subset=['Material Description'], keep='first')
        df_google = df_google.drop_duplicates(subset=['Material Description'], keep='first')
        df = df_national.merge(df_google, on="Material Description", how="right")
        df = df.drop_duplicates(subset=['Material Description'], keep='first')
    else:
        df = df_national.copy()

    if df.empty:
        return pd.DataFrame()

    if 'S/N' in df.columns:
        df = df.drop(columns=['S/N'])

    text_columns = ['Status', 'Expiry', 'GIT_PO', 'LC_PO', 'WB_PO', 'TMD_PO']
    numeric_columns = [col for col in df.columns if col not in text_columns + ['Material Description']]
    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    if 'NSOH' in df.columns and 'AMC' in df.columns:
        df['NSOH'] = pd.to_numeric(df['NSOH'], errors='coerce')
        df['AMC'] = pd.to_numeric(df['AMC'], errors='coerce')
        mask = (df['AMC'] > 0) & (df['NSOH'].isna())
        df.loc[mask, 'NSOH'] = 0
        df['NSOH'] = df['NSOH'].fillna(0)

    if 'NSOH' in df.columns and 'AMC' in df.columns:
        nsoh = pd.to_numeric(df['NSOH'], errors='coerce')
        amc = pd.to_numeric(df['AMC'], errors='coerce')
        amc = amc.replace(0, np.nan)
        nmos = nsoh / amc
        nmos = nmos.replace([np.inf, -np.inf], np.nan)
        df['NMOS'] = nmos.round(2)

    dos_dict = calculate_dos(df)
    df['DOS'] = df['Material Description'].map(dos_dict).fillna(0).astype(int)

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

    if 'NMOS' in df.columns:
        df['Risk of Stock'] = df.apply(calculate_risk, axis=1)

        expiry_data = df.apply(lambda row: parse_multiple_expiry_batches(row.get('Expiry', ''), row.get('AMC', np.nan)), axis=1)
        df['Expiry Batches'] = expiry_data.apply(lambda x: x[0])
        df['Has Expiry Risk'] = expiry_data.apply(lambda x: x[1] if isinstance(x, tuple) and len(x) > 1 else False)

        def format_expiry_only(batches):
            if not batches:
                return ""
            parts = []
            for batch in batches:
                parts.append(f"{int(batch['quantity']):,} ({batch['expiry_date'].strftime('%b-%Y')})")
            return "; ".join(parts)

        def format_mos_with_expiry(batches):
            if not batches:
                return ""
            parts = []
            for batch in batches:
                mos_str = f"{batch['remaining_mos']:.2f}" if batch['remaining_mos'] > 0 else "0.00"
                expiry_str = batch['expiry_date'].strftime('%b-%Y') if batch.get('expiry_date') else ""
                parts.append(f"{mos_str} ({expiry_str})")
            return "; ".join(parts)

        df['Expiry'] = df['Expiry Batches'].apply(format_expiry_only)
        df['Expiry MOS'] = df['Expiry Batches'].apply(format_mos_with_expiry)

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

    PROGRAM_HIERARCHY = {
        "OI and Hepatitis": {"subcategories": ["AHD", "Hepatitis", "OI", "STI"], "is_parent": True},
        "TB": {"subcategories": ["Drug Susceptible -TB Medicine (DS-TB)", "Drug Resisitance -TB Medicine (DR-TB)", "Leprosy Medicines", "Nutrition"], "is_parent": True},
        "Lab TB": {"subcategories": ["TB diagnostics& Laboratory reagent", "TB Lab Supplies"], "is_parent": True},
        "HIV Lab": {"subcategories": ["HIV VL Reagents", "CD4 ,AHD &HIV RTKs"], "is_parent": True}
    }
    if sheet_name in PROGRAM_HIERARCHY:
        subcategory_list = PROGRAM_HIERARCHY[sheet_name]["subcategories"]
        mask = ~df['Material Description'].astype(str).str.strip().isin(subcategory_list)
        df = df[mask].copy()

    if subcategory_filter != "All":
        subcat_map = {}
        current = None
        for idx, row in df.iterrows():
            mat = row['Material Description']
            if mat in subcategory_list:
                current = mat
            elif current is not None:
                subcat_map[mat] = current
        df['Assigned Subcategory'] = df['Material Description'].map(subcat_map)
        df = df[df['Assigned Subcategory'] == subcategory_filter]

    return df

@st.cache_data(ttl=CACHE_TTL)
def compute_supply_plan(df_filtered):
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
                urgency = "🟡 PLAN"
                order_by_readable = get_readable_order_by(months_until_order)
                action = f"Place this {order_quantity:,} units by {order_by_readable}"
                order_by = order_by_readable
                total_months_to_delivery = months_until_order + 6
                expected_delivery = get_future_date(total_months_to_delivery)

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
    else:
        supply_df = pd.DataFrame()
    return supply_df, supply_plan

@st.cache_data(ttl=CACHE_TTL)
def compute_action_plan(df_filtered):
    def get_total_pipeline_mos(row):
        git_mos = row.get('GIT_MOS', 0)
        lc_mos = row.get('LC_MOS', 0)
        wb_mos = row.get('WB_MOS', 0)
        tmd_mos = row.get('TMD_MOS', 0)
        try:
            git_mos = float(git_mos) if pd.notna(git_mos) else 0
            lc_mos = float(lc_mos) if pd.notna(lc_mos) else 0
            wb_mos = float(wb_mos) if pd.notna(wb_mos) else 0
            tmd_mos = float(tmd_mos) if pd.notna(tmd_mos) else 0
        except:
            return 0
        return git_mos + lc_mos + wb_mos + tmd_mos

    def has_pipeline(row):
        return get_total_pipeline_mos(row) > 0

    material_problems = {}
    for idx, row in df_filtered.iterrows():
        material = row['Material Description']
        if pd.isna(material):
            continue

        nmos = row.get('NMOS', 0)
        tmos = row.get('TMOS', 0)
        nsoh = row.get('NSOH', 0)
        amc = row.get('AMC', 0)
        risk_type = row.get('Risk Type', '')
        has_expiry_risk = row.get('Has Expiry Risk', False)
        risk_of_stock = row.get('Risk of Stock', '')
        cv_category = row.get('CV Category', 'Unknown')

        try:
            nmos = float(nmos) if pd.notna(nmos) else 0
            tmos = float(tmos) if pd.notna(tmos) else 0
            nsoh = float(nsoh) if pd.notna(nsoh) else 0
            amc = float(amc) if pd.notna(amc) else 0
        except:
            continue

        if amc == 0 and not has_expiry_risk:
            continue

        mos_needed_calc = 18 - tmos
        if mos_needed_calc < 0:
            mos_needed_calc = 0

        nsoh_formatted = f"{int(nsoh):,}" if nsoh > 0 else "0"
        amc_formatted = f"{int(amc):,}" if amc > 0 else "N/A"
        pmos = round(get_total_pipeline_mos(row), 2)
        current_date = datetime.now()
        end_of_month = get_end_of_month_date(current_date.year, current_date.month)

        if material not in material_problems:
            material_problems[material] = {
                'NSOH': nsoh_formatted,
                'AMC': amc_formatted,
                'PMOS': pmos,
                'NMOS': round(nmos, 2),
                'TMOS': round(tmos, 2),
                'MOS Needed': round(mos_needed_calc, 2),
                'problems': []
            }

        if nmos < 1:
            if has_pipeline(row):
                action_point, responsible_body = get_pipeline_recommendation(row)
            else:
                months_needed_stock = 18 - tmos
                if months_needed_stock < 0:
                    months_needed_stock = 0
                order_qty = int(months_needed_stock * amc) if amc > 0 and months_needed_stock > 0 else 0
                action_point = f"Mobilize resource and initiate purchase request for {months_needed_stock:.1f} months ({order_qty:,} units)"
                responsible_body = "MOH"
            material_problems[material]['problems'].append({
                'Identified Problem': '🔴 Stock Out',
                'Action Point': action_point,
                'Responsible Body': responsible_body,
                'Due Date': 'IMMEDIATELY'
            })

        elif nmos >= 1 and (risk_of_stock == 'Risk of Stock out' or risk_type == 'Risk of Stock out'):
            if has_pipeline(row):
                action_point, responsible_body = get_pipeline_recommendation(row)
            else:
                months_needed_stock = 18 - tmos
                if months_needed_stock < 0:
                    months_needed_stock = 0
                order_qty = int(months_needed_stock * amc) if amc > 0 and months_needed_stock > 0 else 0
                action_point = f"Mobilize resource and initiate purchase request for {months_needed_stock:.1f} months ({order_qty:,} units)"
                responsible_body = "MOH"
            material_problems[material]['problems'].append({
                'Identified Problem': '🟡 Risk of Stock Out',
                'Action Point': action_point,
                'Responsible Body': responsible_body,
                'Due Date': end_of_month.strftime('Before %d %b %Y')
            })

        if has_expiry_risk or risk_type == 'Expiry Risk':
            action_point, responsible_body = get_expiry_risk_action(row)
            material_problems[material]['problems'].append({
                'Identified Problem': '⚠️ Expiry Risk',
                'Action Point': action_point,
                'Responsible Body': responsible_body,
                'Due Date': 'ASAP'
            })

        if 1 <= nmos < 6:
            if has_pipeline(row):
                action_point, responsible_body = get_pipeline_recommendation(row)
            else:
                months_needed_stock = 18 - tmos
                if months_needed_stock < 0:
                    months_needed_stock = 0
                order_qty = int(months_needed_stock * amc) if amc > 0 and months_needed_stock > 0 else 0
                action_point = f"Mobilize resource and initiate purchase request for {months_needed_stock:.1f} months ({order_qty:,} units)"
                responsible_body = "MOH"
            material_problems[material]['problems'].append({
                'Identified Problem': '📉 Below Minimum Stock Level',
                'Action Point': action_point,
                'Responsible Body': responsible_body,
                'Due Date': end_of_month.strftime('Before %d %b %Y')
            })

        if tmos < 18:
            months_needed_stock = 18 - tmos
            order_qty = int(months_needed_stock * amc) if amc > 0 and months_needed_stock > 0 else 0
            action_point = f"Mobilize resource and initiate purchase request for {months_needed_stock:.1f} months ({order_qty:,} units)"
            responsible_body = "MOH"
            due_date = calculate_due_date_for_pipeline(tmos)
            material_problems[material]['problems'].append({
                'Identified Problem': '📦 Pipeline Insufficient - Cannot Reach Max Stock',
                'Action Point': action_point,
                'Responsible Body': responsible_body,
                'Due Date': due_date
            })

    for material, data in material_problems.items():
        if data['problems']:
            has_risk_of_stock = any(p['Identified Problem'] == '🟡 Risk of Stock Out' for p in data['problems'])
            if has_risk_of_stock:
                data['problems'] = [p for p in data['problems'] if p['Identified Problem'] != '📉 Below Minimum Stock Level']
    for material, data in material_problems.items():
        if data['problems']:
            has_stock_out = any(p['Identified Problem'] == '🔴 Stock Out' for p in data['problems'])
            if has_stock_out:
                data['problems'] = [p for p in data['problems'] if p['Identified Problem'] != '📉 Below Minimum Stock Level']
    for material, data in material_problems.items():
        if data['problems'] and data['PMOS'] == 0:
            has_stock_out = any(p['Identified Problem'] == '🔴 Stock Out' for p in data['problems'])
            has_risk_of_stock = any(p['Identified Problem'] == '🟡 Risk of Stock Out' for p in data['problems'])
            has_below_min = any(p['Identified Problem'] == '📉 Below Minimum Stock Level' for p in data['problems'])
            if has_stock_out or has_risk_of_stock or has_below_min:
                data['problems'] = [p for p in data['problems'] if p['Identified Problem'] != '📦 Pipeline Insufficient - Cannot Reach Max Stock']

    action_plan_rows = []
    for material, data in material_problems.items():
        if data['problems']:
            for problem in data['problems']:
                row_data = {
                    'Material': material,
                    'NSOH': data['NSOH'],
                    'AMC': data['AMC'],
                    'PMOS': data['PMOS'],
                    'NMOS': data['NMOS'],
                    'TMOS': data['TMOS'],
                    'MOS Needed': data['MOS Needed'],
                    'Identified Problem': problem['Identified Problem'],
                    'Action Point': problem['Action Point'],
                    'Responsible Body': problem['Responsible Body'],
                    'Due Date': problem['Due Date']
                }
                action_plan_rows.append(row_data)

    if action_plan_rows:
        action_df = pd.DataFrame(action_plan_rows)
        action_df = action_df.drop_duplicates(
            subset=['Material', 'Identified Problem'], 
            keep='first'
        )
        return material_problems, action_df

    return material_problems, pd.DataFrame()

def get_month_columns(df):
    pattern = re.compile(r'^[A-Za-z]{3}-\d{4}$')
    months = [col for col in df.columns if pattern.match(col)]
    return sort_months_chronologically(months)

def render_unified_historical_table(df_filtered, issue_pivot, nsoh_pivot, consumption_pivot, deliveries_pivot, ordered_materials_tuple, sheet_name):
    """Render a unified historical table with months as columns and data types as rows"""
    # Removed the duplicate header - only keep the one inside the custom-card

    if df_filtered.empty:
        st.info("No data available.")
        return

    # Get all available months from NSOH pivot
    all_available_months = []
    if not nsoh_pivot.empty:
        all_available_months = get_month_columns(nsoh_pivot)

    if not all_available_months:
        st.info("No month data available.")
        return

    # Time range filter with calendar-like dropdowns
    st.markdown("""
    <div class="time-range-selector">
        <label>📅 Select Time Range</label>
    </div>
    """, unsafe_allow_html=True)

    col_start, col_end = st.columns(2)
    with col_start:
        start_month = st.selectbox(
            "Start Month",
            all_available_months,
            index=0,
            key="hist_start_month"
        )
    with col_end:
        end_month = st.selectbox(
            "End Month",
            all_available_months,
            index=len(all_available_months) - 1,
            key="hist_end_month"
        )

    # Filter months based on selection - maintain chronological order
    if start_month and end_month:
        start_idx = all_available_months.index(start_month)
        end_idx = all_available_months.index(end_month)
        if start_idx <= end_idx:
            selected_months = all_available_months[start_idx:end_idx + 1]
        else:
            selected_months = all_available_months[start_idx:] + all_available_months[:end_idx + 1]
            selected_months = sort_months_chronologically(selected_months)
    else:
        selected_months = all_available_months

    material_list = sorted(df_filtered['Material Description'].dropna().unique())

    if not material_list:
        st.info("No materials found.")
        return

    selected_material = st.selectbox("🔍 Select Material to view historical data", material_list, key="historical_material_select")

    if not selected_material:
        return

    def get_row_data(df, material_col='Material Description'):
        if df.empty:
            return None
        row = df[df[material_col] == selected_material]
        if row.empty:
            return None
        return row.iloc[0]

    nsoh_row = get_row_data(nsoh_pivot)
    issue_row = get_row_data(issue_pivot) if not issue_pivot.empty else None
    cons_row = get_row_data(consumption_pivot) if not consumption_pivot.empty else None
    deliv_row = get_row_data(deliveries_pivot) if not deliveries_pivot.empty else None

    amc_value = 0
    material_row = df_filtered[df_filtered['Material Description'] == selected_material]
    if not material_row.empty:
        amc_value = material_row.iloc[0].get('AMC', 0)
        if pd.isna(amc_value):
            amc_value = 0

    # Use selected months
    all_months = selected_months

    if not all_months:
        st.info("No data available for the selected time range.")
        return

    # Build the unified table with all data types
    data_rows = []

    # NSOH row
    nsoh_vals = []
    for month in all_months:
        if nsoh_row is not None and month in nsoh_row.index:
            val = nsoh_row[month]
            nsoh_vals.append(f"{int(val):,}" if pd.notna(val) and val > 0 else "0")
        else:
            nsoh_vals.append("0")
    data_rows.append({
        'Data Type': '📦 NSOH',
        **{month: nsoh_vals[i] for i, month in enumerate(all_months)}
    })

    # AMC row (same value for all months)
    amc_display = f"{int(amc_value):,}" if amc_value > 0 else "0"
    data_rows.append({
        'Data Type': '📊 AMC',
        **{month: amc_display for month in all_months}
    })

    # NMOS row (NSOH / AMC)
    nmos_vals = []
    for i, month in enumerate(all_months):
        nsoh_val = float(nsoh_vals[i].replace(',', '')) if nsoh_vals[i] else 0
        if amc_value > 0 and nsoh_val > 0:
            nmos_val = nsoh_val / amc_value
            nmos_vals.append(f"{nmos_val:.2f}")
        else:
            nmos_vals.append("0.00")
    data_rows.append({
        'Data Type': '📈 NMOS',
        **{month: nmos_vals[i] for i, month in enumerate(all_months)}
    })

    # Consumption row - starts from the 2nd month (first month is NaN)
    cons_vals = []
    for month in all_months:
        if cons_row is not None and month in cons_row.index:
            val = cons_row[month]
            if pd.notna(val):
                cons_vals.append(f"{int(val):,}" if val > 0 else "0")
            else:
                cons_vals.append("")  # First month is empty (NaN)
        else:
            cons_vals.append("")
    data_rows.append({
        'Data Type': '📊 Consumption',
        **{month: cons_vals[i] for i, month in enumerate(all_months)}
    })

    # Issue row
    issue_vals = []
    for month in all_months:
        if issue_row is not None and month in issue_row.index:
            val = issue_row[month]
            issue_vals.append(f"{int(val):,}" if pd.notna(val) and val > 0 else "0")
        else:
            issue_vals.append("")
    data_rows.append({
        'Data Type': '📤 Issue',
        **{month: issue_vals[i] for i, month in enumerate(all_months)}
    })

    # Calculate A_AMC as moving average of last 3 months for each month
    a_amc_vals = []
    for i, month in enumerate(all_months):
        month_dt = pd.to_datetime(month, format='%b-%Y')
        prev_1_dt = month_dt - pd.DateOffset(months=1)
        prev_2_dt = month_dt - pd.DateOffset(months=2)

        prev_1_month = prev_1_dt.strftime('%b-%Y')
        prev_2_month = prev_2_dt.strftime('%b-%Y')

        month_values = []

        if issue_row is not None and month in issue_row.index:
            val = issue_row[month]
            if pd.notna(val) and val > 0:
                month_values.append(float(val))

        if issue_row is not None and prev_1_month in issue_row.index:
            val = issue_row[prev_1_month]
            if pd.notna(val) and val > 0:
                month_values.append(float(val))

        if issue_row is not None and prev_2_month in issue_row.index:
            val = issue_row[prev_2_month]
            if pd.notna(val) and val > 0:
                month_values.append(float(val))

        if month_values:
            a_amc_val = sum(month_values) / len(month_values)
            a_amc_vals.append(f"{a_amc_val:.1f}")
        else:
            a_amc_vals.append("0.0")

    data_rows.append({
        'Data Type': '📊 A_AMC (3m avg)',
        **{month: a_amc_vals[i] for i, month in enumerate(all_months)}
    })

    # AMOS row (NSOH / A_AMC)
    amos_vals = []
    for i, month in enumerate(all_months):
        nsoh_val = float(nsoh_vals[i].replace(',', '')) if nsoh_vals[i] else 0
        a_amc_val = float(a_amc_vals[i]) if a_amc_vals[i] else 0
        if a_amc_val > 0 and nsoh_val > 0:
            amos_val = nsoh_val / a_amc_val
            amos_vals.append(f"{amos_val:.2f}")
        else:
            amos_vals.append("0.00")
    data_rows.append({
        'Data Type': '📈 AMOS',
        **{month: amos_vals[i] for i, month in enumerate(all_months)}
    })

    # Received Quantity row
    deliv_vals = []
    for month in all_months:
        if deliv_row is not None and month in deliv_row.index:
            val = deliv_row[month]
            deliv_vals.append(f"{int(val):,}" if pd.notna(val) and val > 0 else "0")
        else:
            deliv_vals.append("")
    data_rows.append({
        'Data Type': '📥 Received',
        **{month: deliv_vals[i] for i, month in enumerate(all_months)}
    })

    # Create DataFrame
    unified_df = pd.DataFrame(data_rows)

    st.markdown(f"""
    <div class="custom-card">
        <h4 style='font-size: 16px; font-weight: 600; margin-bottom: 10px;'>📋 Historical Data for: {selected_material}</h4>
        <p style='font-size: 12px; color: #666;'>Showing {len(all_months)} months (Consumption starts from the 2nd month)</p>
    </div>
    """, unsafe_allow_html=True)
    st.dataframe(unified_df, use_container_width=True, hide_index=True)

    # Download as XLSX
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        unified_df.to_excel(writer, index=False, sheet_name='Historical Data')
    excel_data = output.getvalue()

    st.download_button(
        label="📥 Download Historical Data (XLSX)",
        data=excel_data,
        file_name=f"historical_data_{selected_material}_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

    # Graph 0: NMOS vs AMOS Trends with shadow gap
    st.markdown("---")
    st.markdown("""
    <div class="custom-card">
        <h4 style='font-size: 16px; font-weight: 600; margin-bottom: 5px;'>📊 NMOS vs AMOS Trends</h4>
        <p style='font-size: 13px; color: #666;'>Gap between NMOS and AMOS is filled with gray</p>
    </div>
    """, unsafe_allow_html=True)

    plot_data_nmos_amos = []
    for row in data_rows:
        data_type = row['Data Type']
        if data_type not in ['📈 NMOS', '📈 AMOS']:
            continue
        values = []
        has_data = False
        text_values = []
        for month in all_months:
            val_str = row.get(month, "0")
            if val_str == "" or val_str is None:
                values.append(None)
                text_values.append("")
            else:
                val_str = str(val_str).replace(',', '')
                try:
                    val = float(val_str) if val_str else 0
                    values.append(val)
                    if val > 0:
                        has_data = True
                        text_values.append(f"{val:.2f}")
                    else:
                        text_values.append("")
                except:
                    values.append(0)
                    text_values.append("")

        if has_data:
            plot_data_nmos_amos.append({
                'Data Type': data_type, 
                'values': values, 
                'months': all_months,
                'text_values': text_values
            })

    if plot_data_nmos_amos:
        fig_nmos_amos = go.Figure()

        # Find NMOS and AMOS data for gap filling
        nmos_data = None
        amos_data = None
        for data in plot_data_nmos_amos:
            if data['Data Type'] == '📈 NMOS':
                nmos_data = data
            elif data['Data Type'] == '📈 AMOS':
                amos_data = data

        # Add gap fill between NMOS and AMOS
        if nmos_data is not None and amos_data is not None:
            nmos_vals = [v if v is not None else 0 for v in nmos_data['values']]
            amos_vals = [v if v is not None else 0 for v in amos_data['values']]

            x_vals_nmos_amos = []
            y_upper_nmos_amos = []
            y_lower_nmos_amos = []
            for i, month in enumerate(all_months):
                n_val = nmos_vals[i] if i < len(nmos_vals) else 0
                a_val = amos_vals[i] if i < len(amos_vals) else 0
                if n_val > 0 and a_val > 0:
                    x_vals_nmos_amos.append(month)
                    y_upper_nmos_amos.append(max(n_val, a_val))
                    y_lower_nmos_amos.append(min(n_val, a_val))

            if x_vals_nmos_amos:
                fig_nmos_amos.add_trace(go.Scatter(
                    x=x_vals_nmos_amos + x_vals_nmos_amos[::-1],
                    y=y_upper_nmos_amos + y_lower_nmos_amos[::-1],
                    fill='toself',
                    fillcolor='rgba(200, 200, 200, 0.4)',
                    line=dict(color='rgba(200, 200, 200, 0)'),
                    showlegend=False,
                    hoverinfo='skip',
                    name='Gap'
                ))

        colors_nmos_amos = {
            '📈 NMOS': '#4DABF7',
            '📈 AMOS': '#FF922B'
        }

        # Get max value for text positioning
        max_val_nmos_amos = 0
        for data in plot_data_nmos_amos:
            for v in data['values']:
                if v and v > max_val_nmos_amos:
                    max_val_nmos_amos = v

        for data in plot_data_nmos_amos:
            fig_nmos_amos.add_trace(go.Scatter(
                x=data['months'],
                y=data['values'],
                name=data['Data Type'],
                mode='lines+markers+text',
                line=dict(color=colors_nmos_amos.get(data['Data Type'], '#666'), width=3),
                marker=dict(size=10, color=colors_nmos_amos.get(data['Data Type'], '#666'), line=dict(width=2, color='white')),
                text=data['text_values'],
                textposition='top center',
                textfont=dict(size=10, color='black', family='Times New Roman, Times, serif'),
                hovertemplate='<b>%{x}</b><br>%{fullData.name}: %{y:.2f}<extra></extra>'
            ))

        fig_nmos_amos.update_layout(
            title=dict(
                text=f"NMOS vs AMOS for {selected_material}",
                font=dict(size=16, color='#333', family='Times New Roman, Times, serif')
            ),
            xaxis_title="Month",
            yaxis_title="Months of Stock",
            height=400,
            legend=dict(
                orientation='h', 
                yanchor='bottom', 
                y=1.02, 
                xanchor='center', 
                x=0.5,
                font=dict(size=12, family='Times New Roman, Times, serif')
            ),
            hovermode='x unified',
            xaxis=dict(
                showgrid=False,
                showline=True,
                linecolor='#333',
                linewidth=2,
                tickangle=45,
                tickfont=dict(size=11, family='Times New Roman, Times, serif'),
                categoryorder='array',
                categoryarray=all_months
            ),
            yaxis=dict(
                showgrid=True,
                gridcolor='#e0e0e0',
                showline=True,
                linecolor='#333',
                linewidth=2,
                tickfont=dict(size=11, family='Times New Roman, Times, serif')
            ),
            plot_bgcolor='white',
            margin=dict(l=60, r=40, t=60, b=60),
            font=dict(family='Times New Roman, Times, serif')
        )
        st.plotly_chart(fig_nmos_amos, use_container_width=True, config={'displayModeBar': True})

    # Graph 1: NSOH vs Consumption vs Issue with gap fill
    st.markdown("---")
    st.markdown("""
    <div class="custom-card">
        <h4 style='font-size: 16px; font-weight: 600; margin-bottom: 5px;'>📊 NSOH vs Consumption vs Issue Trends</h4>
        <p style='font-size: 13px; color: #666;'>Gap between NSOH and Issue is filled with gray</p>
    </div>
    """, unsafe_allow_html=True)

    plot_data = []
    for row in data_rows:
        data_type = row['Data Type']
        if data_type not in ['📦 NSOH', '📊 Consumption', '📤 Issue']:
            continue
        values = []
        has_data = False
        text_values = []
        for month in all_months:
            val_str = row.get(month, "0")
            if val_str == "" or val_str is None:
                values.append(None)
                text_values.append("")
            else:
                val_str = str(val_str).replace(',', '')
                try:
                    val = float(val_str) if val_str else 0
                    values.append(val)
                    if val > 0:
                        has_data = True
                        text_values.append(f"{val:,.0f}")
                    else:
                        text_values.append("")
                except:
                    values.append(0)
                    text_values.append("")

        if has_data:
            plot_data.append({
                'Data Type': data_type, 
                'values': values, 
                'months': all_months,
                'text_values': text_values
            })

    if plot_data:
        fig = go.Figure()

        # Find NSOH and Issue data for gap filling
        nsoh_data = None
        issue_data = None
        cons_data = None
        for data in plot_data:
            if data['Data Type'] == '📦 NSOH':
                nsoh_data = data
            elif data['Data Type'] == '📤 Issue':
                issue_data = data
            elif data['Data Type'] == '📊 Consumption':
                cons_data = data

        # Add gap fill between NSOH and Issue - use the chronological order from all_months
        if nsoh_data is not None and issue_data is not None:
            nsoh_vals = [v if v is not None else 0 for v in nsoh_data['values']]
            issue_vals = [v if v is not None else 0 for v in issue_data['values']]

            # Fill gap only where both have values
            x_vals = []
            y_upper = []
            y_lower = []
            for i, month in enumerate(all_months):
                n_val = nsoh_vals[i] if i < len(nsoh_vals) else 0
                i_val = issue_vals[i] if i < len(issue_vals) else 0
                if n_val > 0 and i_val > 0:
                    x_vals.append(month)
                    y_upper.append(max(n_val, i_val))
                    y_lower.append(min(n_val, i_val))

            if x_vals:
                fig.add_trace(go.Scatter(
                    x=x_vals + x_vals[::-1],
                    y=y_upper + y_lower[::-1],
                    fill='toself',
                    fillcolor='rgba(200, 200, 200, 0.4)',
                    line=dict(color='rgba(200, 200, 200, 0)'),
                    showlegend=False,
                    hoverinfo='skip',
                    name='Gap'
                ))

        colors = {
            '📦 NSOH': '#FF6B6B',
            '📊 Consumption': '#51CF66',
            '📤 Issue': '#4DABF7'
        }
        line_styles = {
            '📦 NSOH': 'solid',
            '📊 Consumption': 'solid',
            '📤 Issue': 'solid'
        }

        # Get max value for text positioning
        max_val = 0
        for data in plot_data:
            for v in data['values']:
                if v and v > max_val:
                    max_val = v

        for data in plot_data:
            # Determine text position: above for Consumption, below for Issue, above for NSOH
            text_pos = 'top center'
            if data['Data Type'] == '📤 Issue':
                text_pos = 'bottom center'
            elif data['Data Type'] == '📊 Consumption':
                text_pos = 'top center'

            # Add offset to avoid overlap
            text_offset = 0
            if data['Data Type'] == '📤 Issue':
                text_offset = -max_val * 0.05
            elif data['Data Type'] == '📊 Consumption':
                text_offset = max_val * 0.05

            fig.add_trace(go.Scatter(
                x=data['months'],
                y=data['values'],
                name=data['Data Type'],
                mode='lines+markers+text',
                line=dict(color=colors.get(data['Data Type'], '#666'), width=3, dash=line_styles.get(data['Data Type'], 'solid')),
                marker=dict(size=10, color=colors.get(data['Data Type'], '#666')),
                text=data['text_values'],
                textposition=text_pos,
                textfont=dict(size=10, color='black', family='Times New Roman, Times, serif'),
                hovertemplate='<b>%{x}</b><br>%{fullData.name}: %{y:,.0f}<extra></extra>'
            ))

        fig.update_layout(
            title=dict(
                text=f"NSOH vs Consumption vs Issue for {selected_material}",
                font=dict(size=16, color='#333', family='Times New Roman, Times, serif')
            ),
            xaxis_title="Month",
            yaxis_title="Value",
            height=450,
            legend=dict(
                orientation='h', 
                yanchor='bottom', 
                y=1.02, 
                xanchor='center', 
                x=0.5,
                font=dict(size=12, family='Times New Roman, Times, serif')
            ),
            hovermode='x unified',
            xaxis=dict(
                showgrid=False,
                showline=True,
                linecolor='#333',
                linewidth=2,
                tickangle=45,
                tickfont=dict(size=11, family='Times New Roman, Times, serif'),
                categoryorder='array',
                categoryarray=all_months
            ),
            yaxis=dict(
                showgrid=True,
                gridcolor='#e0e0e0',
                showline=True,
                linecolor='#333',
                linewidth=2,
                tickfont=dict(size=11, family='Times New Roman, Times, serif')
            ),
            plot_bgcolor='white',
            margin=dict(l=60, r=40, t=60, b=60),
            font=dict(family='Times New Roman, Times, serif')
        )
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': True})

    # Graph 2: AMC vs Consumption vs Issue with gap fill
    st.markdown("---")
    st.markdown("""
    <div class="custom-card">
        <h4 style='font-size: 16px; font-weight: 600; margin-bottom: 5px;'>📊 AMC vs Consumption vs Issue Trends</h4>
        <p style='font-size: 13px; color: #666;'>Gap between AMC and Issue is filled with gray</p>
    </div>
    """, unsafe_allow_html=True)

    plot_data_amc = []
    for row in data_rows:
        data_type = row['Data Type']
        if data_type not in ['📊 AMC', '📊 Consumption', '📤 Issue']:
            continue
        values = []
        has_data = False
        text_values = []
        for month in all_months:
            val_str = row.get(month, "0")
            if val_str == "" or val_str is None:
                values.append(None)
                text_values.append("")
            else:
                val_str = str(val_str).replace(',', '')
                try:
                    val = float(val_str) if val_str else 0
                    values.append(val)
                    if val > 0:
                        has_data = True
                        text_values.append(f"{val:,.0f}")
                    else:
                        text_values.append("")
                except:
                    values.append(0)
                    text_values.append("")

        if has_data:
            plot_data_amc.append({
                'Data Type': data_type, 
                'values': values, 
                'months': all_months,
                'text_values': text_values
            })

    if plot_data_amc:
        fig2 = go.Figure()

        # Find AMC and Issue data for gap filling
        amc_data = None
        issue_data2 = None
        cons_data2 = None
        for data in plot_data_amc:
            if data['Data Type'] == '📊 AMC':
                amc_data = data
            elif data['Data Type'] == '📤 Issue':
                issue_data2 = data
            elif data['Data Type'] == '📊 Consumption':
                cons_data2 = data

        # Add gap fill between AMC and Issue
        if amc_data is not None and issue_data2 is not None:
            amc_vals = [v if v is not None else 0 for v in amc_data['values']]
            issue_vals2 = [v if v is not None else 0 for v in issue_data2['values']]

            x_vals2 = []
            y_upper2 = []
            y_lower2 = []
            for i, month in enumerate(all_months):
                a_val = amc_vals[i] if i < len(amc_vals) else 0
                i_val2 = issue_vals2[i] if i < len(issue_vals2) else 0
                if a_val > 0 and i_val2 > 0:
                    x_vals2.append(month)
                    y_upper2.append(max(a_val, i_val2))
                    y_lower2.append(min(a_val, i_val2))

            if x_vals2:
                fig2.add_trace(go.Scatter(
                    x=x_vals2 + x_vals2[::-1],
                    y=y_upper2 + y_lower2[::-1],
                    fill='toself',
                    fillcolor='rgba(200, 200, 200, 0.4)',
                    line=dict(color='rgba(200, 200, 200, 0)'),
                    showlegend=False,
                    hoverinfo='skip',
                    name='Gap'
                ))

        colors_amc = {
            '📊 AMC': '#CC5DE8',
            '📊 Consumption': '#51CF66',
            '📤 Issue': '#4DABF7'
        }

        # Get max value for text positioning
        max_val2 = 0
        for data in plot_data_amc:
            for v in data['values']:
                if v and v > max_val2:
                    max_val2 = v

        for data in plot_data_amc:
            text_pos = 'top center'
            if data['Data Type'] == '📤 Issue':
                text_pos = 'bottom center'
            elif data['Data Type'] == '📊 Consumption':
                text_pos = 'top center'

            fig2.add_trace(go.Scatter(
                x=data['months'],
                y=data['values'],
                name=data['Data Type'],
                mode='lines+markers+text',
                line=dict(color=colors_amc.get(data['Data Type'], '#666'), width=3),
                marker=dict(size=10, color=colors_amc.get(data['Data Type'], '#666')),
                text=data['text_values'],
                textposition=text_pos,
                textfont=dict(size=10, color='black', family='Times New Roman, Times, serif'),
                hovertemplate='<b>%{x}</b><br>%{fullData.name}: %{y:,.0f}<extra></extra>'
            ))

        fig2.update_layout(
            title=dict(
                text=f"AMC vs Consumption vs Issue for {selected_material}",
                font=dict(size=16, color='#333', family='Times New Roman, Times, serif')
            ),
            xaxis_title="Month",
            yaxis_title="Value",
            height=450,
            legend=dict(
                orientation='h', 
                yanchor='bottom', 
                y=1.02, 
                xanchor='center', 
                x=0.5,
                font=dict(size=12, family='Times New Roman, Times, serif')
            ),
            hovermode='x unified',
            xaxis=dict(
                showgrid=False,
                showline=True,
                linecolor='#333',
                linewidth=2,
                tickangle=45,
                tickfont=dict(size=11, family='Times New Roman, Times, serif'),
                categoryorder='array',
                categoryarray=all_months
            ),
            yaxis=dict(
                showgrid=True,
                gridcolor='#e0e0e0',
                showline=True,
                linecolor='#333',
                linewidth=2,
                tickfont=dict(size=11, family='Times New Roman, Times, serif')
            ),
            plot_bgcolor='white',
            margin=dict(l=60, r=40, t=60, b=60),
            font=dict(family='Times New Roman, Times, serif')
        )
        st.plotly_chart(fig2, use_container_width=True, config={'displayModeBar': True})
    else:
        st.info("No AMC data available for comparison.")

def render_supply_planning_exercise(df_filtered, supply_df, supply_plan, ordered_materials_tuple, sheet_name, action_df):
    st.markdown(f"""
    <div class="custom-card">
        <h3 style='font-size: 24px; font-weight: bold; margin-bottom: 10px;'>📦 {sheet_name if sheet_name != 'All' else 'All Programs'} - System Generated Action Plan</h3>
        <p style='color: #666; margin-bottom: 0;'>Automated supply planning based on stock levels and consumption</p>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("📖 Parameters & Instructions", expanded=False):
        st.markdown("""
        **Supply Planning Parameters:**
        - Lead Time = 6 months (time from order placement to delivery)
        - Safety Stock = 2 months (buffer stock)
        - Minimum Stock Level = 6 months
        - Maximum Stock Level = 18 months
        - Reorder Point = Lead Time + Safety Stock = 8 months

        **Order Quantity Formula:**
        - Order Quantity = (18 - TMOS) × AMC (ONLY if 18 - TMOS is POSITIVE)
        - MOS Needed = 18 - TMOS (months of stock required to reach maximum)

        **TMOS = NMOS + Pipeline MOS** (GIT_MOS + LC_MOS + WB_MOS + TMD_MOS)
        """)

    if 'TMOS' not in df_filtered.columns or 'AMC' not in df_filtered.columns:
        st.warning("Required columns for supply planning not found.")
        return

    if supply_df.empty:
        st.info("✅ No materials need ordering at this time.")
        return

    if not ordered_materials_tuple:
        ordered_materials_tuple = tuple(supply_df['Material'].unique())
    order_map = {mat: idx for idx, mat in enumerate(ordered_materials_tuple)}
    supply_df['_order'] = supply_df['Material'].map(order_map)
    supply_df['_order'] = supply_df['_order'].fillna(len(ordered_materials_tuple) + 1)
    supply_df = supply_df.sort_values('_order')
    supply_df = supply_df.drop(columns=['_order'])

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">📋 Materials to Order</div>
            <div class="metric-value">{len(supply_df)}</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        critical = len([s for s in supply_plan if s['Urgency'] == '🔴 CRITICAL'])
        st.markdown(f"""
        <div class="metric-card" style="background: linear-gradient(135deg, #ff6b6b 0%, #c92a2a 100%);">
            <div class="metric-label">🔴 Critical</div>
            <div class="metric-value">{critical}</div>
            <div style="font-size: 12px; opacity: 0.8;">Order Now</div>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        plan = len([s for s in supply_plan if s['Urgency'] == '🟡 PLAN'])
        st.markdown(f"""
        <div class="metric-card" style="background: linear-gradient(135deg, #fcc419 0%, #e67700 100%);">
            <div class="metric-label">🟡 Plan</div>
            <div class="metric-value">{plan}</div>
            <div style="font-size: 12px; opacity: 0.8;">Future Order</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("### Order Quantity Plan")
    st.dataframe(
        supply_df[['Material', 'Current TMOS', 'NMOS', 'Pipeline', 'AMC', 'MOS Needed', 'Order Quantity', 'Urgency', 'Action', 'Order By', 'Expected Delivery']],
        use_container_width=True,
        hide_index=True
    )

    # Download as XLSX
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        supply_df.to_excel(writer, index=False, sheet_name='Order Quantity Plan')
    excel_data = output.getvalue()

    st.download_button(
        label="📥 Download Order Quantity Plan (XLSX)",
        data=excel_data,
        file_name=f"order_quantity_plan_{sheet_name}_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

    # Add pie charts for Identified Problem and Responsible Body
    if action_df is not None and not action_df.empty:
        st.markdown("---")
        st.markdown("### 📊 Problem & Responsible Body Distribution")

        col_pie1, col_pie2 = st.columns(2)

        with col_pie1:
            # Identified Problem pie chart
            problem_counts = action_df['Identified Problem'].value_counts().reset_index()
            problem_counts.columns = ['Problem', 'Count']

            fig_problem = go.Figure(data=[go.Pie(
                labels=problem_counts['Problem'],
                values=problem_counts['Count'],
                hole=0.3,
                marker=dict(colors=['#FF6B6B', '#FCC419', '#FF922B', '#4DABF7', '#CC5DE8']),
                textinfo='label+percent',
                textfont=dict(size=12, family='Times New Roman, Times, serif'),
                hoverinfo='label+value+percent'
            )])
            fig_problem.update_layout(
                title=dict(
                    text="Identified Problems",
                    font=dict(size=14, color='#333', family='Times New Roman, Times, serif')
                ),
                height=350,
                font=dict(family='Times New Roman, Times, serif'),
                plot_bgcolor='white',
                paper_bgcolor='white',
                legend=dict(
                    orientation='h',
                    yanchor='bottom',
                    y=-0.1,
                    xanchor='center',
                    x=0.5,
                    font=dict(size=11, family='Times New Roman, Times, serif')
                )
            )
            st.plotly_chart(fig_problem, use_container_width=True, config={'displayModeBar': True})

        with col_pie2:
            # Responsible Body pie chart - split by comma
            # Split responsible bodies by comma and explode
            all_bodies = []
            for body_str in action_df['Responsible Body'].dropna():
                # Split by comma and strip whitespace
                bodies = [b.strip() for b in body_str.split(',') if b.strip()]
                all_bodies.extend(bodies)

            body_counts = pd.Series(all_bodies).value_counts().reset_index()
            body_counts.columns = ['Responsible Body', 'Count']

            fig_body = go.Figure(data=[go.Pie(
                labels=body_counts['Responsible Body'],
                values=body_counts['Count'],
                hole=0.3,
                marker=dict(colors=['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2']),
                textinfo='label+percent',
                textfont=dict(size=12, family='Times New Roman, Times, serif'),
                hoverinfo='label+value+percent'
            )])
            fig_body.update_layout(
                title=dict(
                    text="Responsible Bodies",
                    font=dict(size=14, color='#333', family='Times New Roman, Times, serif')
                ),
                height=350,
                font=dict(family='Times New Roman, Times, serif'),
                plot_bgcolor='white',
                paper_bgcolor='white',
                legend=dict(
                    orientation='h',
                    yanchor='bottom',
                    y=-0.1,
                    xanchor='center',
                    x=0.5,
                    font=dict(size=11, family='Times New Roman, Times, serif')
                )
            )
            st.plotly_chart(fig_body, use_container_width=True, config={'displayModeBar': True})

def render_action_plan_graph(df_filtered, material_problems, action_df, nsoh_pivot, sheet_name):
    """Render action plan graph as time-series with NMOS, AMOS, and horizontal threshold lines"""
    st.markdown(f"""
    <div class="custom-card">
        <h3 style='font-size: 24px; font-weight: bold; margin-bottom: 10px;'>📊 {sheet_name if sheet_name != 'All' else 'All Programs'} - Action Plan Graph</h3>
        <p style='color: #666; margin-bottom: 0;'>Visualize stock levels and identify action items</p>
    </div>
    """, unsafe_allow_html=True)

    material_list = df_filtered['Material Description'].dropna().unique()
    selected_material = st.selectbox("🔍 Select a Material to view its NMOS trend:", material_list, key="material_selector_graph")

    if selected_material:
        if not nsoh_pivot.empty:
            mat_row = df_filtered[df_filtered['Material Description'] == selected_material]
            amc_value = 0
            if not mat_row.empty:
                amc_value = float(mat_row.iloc[0].get('AMC', 0)) if pd.notna(mat_row.iloc[0].get('AMC', 0)) else 0

            nsoh_row = None
            if 'Material Description' in nsoh_pivot.columns:
                row = nsoh_pivot[nsoh_pivot['Material Description'] == selected_material]
                if not row.empty:
                    nsoh_row = row.iloc[0]

            if nsoh_row is not None:
                months = get_month_columns(nsoh_pivot)
                if months:
                    months = [m for m in months if pd.to_datetime(m, format='%b-%Y') >= pd.to_datetime('Jan-2026', format='%b-%Y')]

                    if months:
                        nmos_values = []
                        amos_values = []
                        for month in months:
                            nsoh_val = nsoh_row[month] if month in nsoh_row.index else 0
                            if pd.notna(nsoh_val) and amc_value > 0 and nsoh_val > 0:
                                nmos_val = nsoh_val / amc_value
                                nmos_values.append(nmos_val)
                            else:
                                nmos_values.append(0)

                            # Calculate AMOS (using A_AMC from the historical data if available)
                            amos_values.append(0)

                        fig = go.Figure()

                        # Add area fill (shadow) between x-axis and NMOS line
                        fig.add_trace(go.Scatter(
                            x=months + months[::-1],
                            y=nmos_values + [0]*len(nmos_values),
                            fill='toself',
                            fillcolor='rgba(102, 126, 234, 0.15)',
                            line=dict(color='rgba(102, 126, 234, 0)'),
                            showlegend=False,
                            hoverinfo='skip'
                        ))

                        # NMOS line with data labels
                        fig.add_trace(go.Scatter(
                            x=months,
                            y=nmos_values,
                            name='NMOS',
                            mode='lines+markers+text',
                            line=dict(color='#4DABF7', width=3),
                            marker=dict(size=12, color='#4DABF7', line=dict(width=2, color='white')),
                            text=[f"{v:.2f}" for v in nmos_values],
                            textposition='top center',
                            textfont=dict(size=10, color='#333', family='Times New Roman, Times, serif'),
                            hovertemplate='<b>%{x}</b><br>NMOS: %{y:.2f} months<extra></extra>'
                        ))

                        # AMOS line (if available)
                        if any(v > 0 for v in amos_values):
                            fig.add_trace(go.Scatter(
                                x=months,
                                y=amos_values,
                                name='AMOS',
                                mode='lines+markers+text',
                                line=dict(color='#FF922B', width=2, dash='dot'),
                                marker=dict(size=10, color='#FF922B', line=dict(width=2, color='white')),
                                text=[f"{v:.2f}" for v in amos_values],
                                textposition='bottom center',
                                textfont=dict(size=9, color='#FF922B', family='Times New Roman, Times, serif'),
                                hovertemplate='<b>%{x}</b><br>AMOS: %{y:.2f} months<extra></extra>'
                            ))

                        # Horizontal threshold lines - only Safety Stock, Min, Max, Reorder Point
                        thresholds = [
                            (2, 'Safety Stock (2m)', '#FF6B6B', 'dash'),
                            (6, 'Min Stock (6m)', '#FF922B', 'dash'),
                            (8, 'Reorder Point (8m)', '#CC5DE8', 'dash'),
                            (18, 'Max Stock (18m)', '#51CF66', 'dash')
                        ]

                        for threshold, label, color, dash in thresholds:
                            fig.add_hline(
                                y=threshold,
                                line_dash=dash,
                                line_color=color,
                                line_width=2,
                                annotation_text=label,
                                annotation_position='right',
                                annotation_font=dict(size=11, color=color, family='Times New Roman, Times, serif')
                            )

                        # Add current NMOS as a marker
                        current_nmos = nmos_values[-1] if nmos_values else 0
                        fig.add_trace(go.Scatter(
                            x=[months[-1]],
                            y=[current_nmos],
                            mode='markers',
                            marker=dict(symbol='star', size=20, color='#FCC419', line=dict(width=2, color='white')),
                            name=f'Current NMOS: {current_nmos:.2f}m',
                            hovertemplate='<b>Current NMOS</b><br>%{y:.2f} months<extra></extra>'
                        ))

                        if selected_material in material_problems:
                            data = material_problems[selected_material]
                            tmos_val = data['TMOS']
                            mos_needed = data['MOS Needed']
                            order_qty = int(mos_needed * amc_value) if amc_value > 0 and mos_needed > 0 else 0

                            if not action_df.empty:
                                mat_actions = action_df[action_df['Material'] == selected_material]
                                if not mat_actions.empty:
                                    first_problem = mat_actions.iloc[0]['Identified Problem']
                                    first_action = mat_actions.iloc[0]['Action Point']
                                    problem_text = f"{first_problem}: {first_action}"
                                else:
                                    problem_text = "✅ No action required"
                            else:
                                problem_text = "✅ No action required"

                            fig.add_annotation(
                                x=0.98, y=0.05,
                                xref='paper', yref='paper',
                                text=problem_text,
                                showarrow=False,
                                font=dict(size=11, family='Times New Roman, Times, serif'),
                                bgcolor='rgba(255, 255, 200, 0.9)',
                                bordercolor='#333',
                                borderwidth=1,
                                borderpad=6,
                                align='right'
                            )

                            order_text = f"Order Qty: {order_qty:,} units" if order_qty > 0 else "No order needed"
                            fig.add_annotation(
                                x=0.02, y=0.95,
                                xref='paper', yref='paper',
                                text=f"AMC: {int(amc_value):,} units/month  |  {order_text}",
                                showarrow=False,
                                font=dict(size=11, family='Times New Roman, Times, serif'),
                                bgcolor='rgba(255, 255, 255, 0.9)',
                                bordercolor='#333',
                                borderwidth=1,
                                borderpad=6,
                                align='left'
                            )

                        fig.update_layout(
                            title=dict(
                                text=f"NMOS Trend for {selected_material[:50]}" if len(selected_material) <= 50 else f"NMOS Trend for {selected_material[:47]}...",
                                font=dict(size=16, color='#333', family='Times New Roman, Times, serif')
                            ),
                            xaxis_title=dict(text='Month-Year', font=dict(size=13, family='Times New Roman, Times, serif')),
                            yaxis_title=dict(text='Months of Stock (NMOS)', font=dict(size=13, family='Times New Roman, Times, serif')),
                            height=500,
                            margin=dict(l=60, r=140, t=60, b=60),
                            legend=dict(
                                orientation='h',
                                yanchor='bottom',
                                y=1.02,
                                xanchor='center',
                                x=0.5,
                                font=dict(size=12, family='Times New Roman, Times, serif')
                            ),
                            hovermode='x unified',
                            xaxis=dict(
                                showgrid=False,
                                showline=True,
                                linecolor='#333',
                                linewidth=2,
                                tickangle=45,
                                tickfont=dict(size=11, family='Times New Roman, Times, serif')
                            ),
                            yaxis=dict(
                                showgrid=True,
                                gridcolor='#e0e0e0',
                                showline=True,
                                linecolor='#333',
                                linewidth=2,
                                tickfont=dict(size=11, family='Times New Roman, Times, serif')
                            ),
                            plot_bgcolor='white',
                            font=dict(family='Times New Roman, Times, serif')
                        )
                        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': True})
                    else:
                        st.info("No historical data available from Jan-2026 onward.")
                else:
                    st.info("No month columns found in the data.")
            else:
                st.info(f"No NSOH historical data found for {selected_material}.")
        else:
            st.info("No NSOH pivot data available.")

        return selected_material
    return None

def render_system_generated_action_plan(action_df, material_problems, sheet_name):
    st.markdown(f"""
    <div class="custom-card">
        <h3 style='font-size: 20px; font-weight: bold; margin-bottom: 10px;'>📝 {sheet_name if sheet_name != 'All' else 'All Programs'} - System Generated Action Plan</h3>
        <p style='color: #666; margin-bottom: 0;'>Automated action items based on stock analysis</p>
    </div>
    """, unsafe_allow_html=True)

    if action_df.empty:
        st.success("✅ No action items identified")
        st.balloons()
        return

    selected_tab_action = st.session_state.action_plan_tab
    col_filter1, col_filter2, col_filter3, col_filter4, col_filter5, col_filter6 = st.columns(6)
    with col_filter1:
        if st.button("📋 All Issues", use_container_width=True, type="primary" if selected_tab_action == "📋 All Issues" else "secondary"):
            st.session_state.action_plan_tab = "📋 All Issues"
            st.rerun()
    with col_filter2:
        if st.button("🔴 Stock Out", use_container_width=True, type="primary" if selected_tab_action == "🔴 Stock Out" else "secondary"):
            st.session_state.action_plan_tab = "🔴 Stock Out"
            st.rerun()
    with col_filter3:
        if st.button("🟡 Risk of SO", use_container_width=True, type="primary" if selected_tab_action == "🟡 Risk of Stock Out" else "secondary"):
            st.session_state.action_plan_tab = "🟡 Risk of Stock Out"
            st.rerun()
    with col_filter4:
        if st.button("⚠️ Expiry Risk", use_container_width=True, type="primary" if selected_tab_action == "⚠️ Expiry Risk" else "secondary"):
            st.session_state.action_plan_tab = "⚠️ Expiry Risk"
            st.rerun()
    with col_filter5:
        if st.button("📉 Below Min", use_container_width=True, type="primary" if selected_tab_action == "📉 Below Min Stock" else "secondary"):
            st.session_state.action_plan_tab = "📉 Below Min Stock"
            st.rerun()
    with col_filter6:
        if st.button("📦 Pipeline Insuff", use_container_width=True, type="primary" if selected_tab_action == "📦 Pipeline Insufficient" else "secondary"):
            st.session_state.action_plan_tab = "📦 Pipeline Insufficient"
            st.rerun()

    st.markdown("---")

    total_problems = len(action_df)
    problem_counts = {
        '🔴 Stock Out': 0,
        '🟡 Risk of Stock Out': 0,
        '⚠️ Expiry Risk': 0,
        '📉 Below Minimum Stock Level': 0,
        '📦 Pipeline Insufficient - Cannot Reach Max Stock': 0
    }
    for data in material_problems.values():
        for p in data['problems']:
            if p['Identified Problem'] in problem_counts:
                problem_counts[p['Identified Problem']] += 1

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        st.markdown(f"""
        <div class="metric-card" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
            <div class="metric-label">📋 Materials with Issues</div>
            <div class="metric-value">{len(material_problems.keys())}</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class="metric-card" style="background: linear-gradient(135deg, #ff6b6b 0%, #c92a2a 100%);">
            <div class="metric-label">🔴 Stock Out</div>
            <div class="metric-value">{problem_counts['🔴 Stock Out']}</div>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown(f"""
        <div class="metric-card" style="background: linear-gradient(135deg, #fcc419 0%, #e67700 100%);">
            <div class="metric-label">🟡 Risk of SO</div>
            <div class="metric-value">{problem_counts['🟡 Risk of Stock Out']}</div>
        </div>
        """, unsafe_allow_html=True)
    with col4:
        st.markdown(f"""
        <div class="metric-card" style="background: linear-gradient(135deg, #ff922b 0%, #e8590c 100%);">
            <div class="metric-label">⚠️ Expiry Risk</div>
            <div class="metric-value">{problem_counts['⚠️ Expiry Risk']}</div>
        </div>
        """, unsafe_allow_html=True)
    with col5:
        st.markdown(f"""
        <div class="metric-card" style="background: linear-gradient(135deg, #4dabf7 0%, #1864ab 100%);">
            <div class="metric-label">📉 Below Min</div>
            <div class="metric-value">{problem_counts['📉 Below Minimum Stock Level']}</div>
        </div>
        """, unsafe_allow_html=True)
    with col6:
        st.markdown(f"""
        <div class="metric-card" style="background: linear-gradient(135deg, #cc5de8 0%, #862e9c 100%);">
            <div class="metric-label">📦 Pipeline Insuff</div>
            <div class="metric-value">{problem_counts['📦 Pipeline Insufficient - Cannot Reach Max Stock']}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    if selected_tab_action == "🔴 Stock Out":
        filtered_df = action_df[action_df['Identified Problem'].str.contains('🔴 Stock Out', na=False)]
    elif selected_tab_action == "🟡 Risk of Stock Out":
        filtered_df = action_df[action_df['Identified Problem'].str.contains('🟡 Risk of Stock Out', na=False)]
    elif selected_tab_action == "⚠️ Expiry Risk":
        filtered_df = action_df[action_df['Identified Problem'].str.contains('⚠️ Expiry Risk', na=False)]
    elif selected_tab_action == "📉 Below Min Stock":
        filtered_df = action_df[action_df['Identified Problem'].str.contains('📉 Below Minimum Stock Level', na=False)]
    elif selected_tab_action == "📦 Pipeline Insufficient":
        filtered_df = action_df[action_df['Identified Problem'].str.contains('📦 Pipeline Insufficient - Cannot Reach Max Stock', na=False)]
    else:
        filtered_df = action_df

    if selected_tab_action == "📋 All Issues":
        st.info(f"📌 Showing {len(filtered_df)} problem records for {len(filtered_df['Material'].unique())} materials (total {total_problems} problems identified)")
    else:
        st.info(f"📌 Showing {len(filtered_df)} problem records with {selected_tab_action}")

    display_df = filtered_df[['Material', 'NSOH', 'AMC', 'PMOS', 'NMOS', 'TMOS', 'MOS Needed', 'Identified Problem', 'Action Point', 'Responsible Body', 'Due Date']].copy()
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    # Download as XLSX
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        filtered_df.to_excel(writer, index=False, sheet_name='Action Plan')
    excel_data = output.getvalue()

    st.download_button(
        label="📥 Download Filtered View (XLSX)",
        data=excel_data,
        file_name=f"action_plan_filtered_{sheet_name}_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

def render_expert_action_plan_with_status(df_filtered, material_problems, action_df, sheet_name, nsoh_pivot, selected_quarter, selected_year):
    # Get current quarter and year for defaults
    current_year = datetime.now().year

    # Load records filtered by program, quarter, year
    if 'expert_plan_records' not in st.session_state:
        st.session_state.expert_plan_records = load_expert_plan_records(
            sheet_name if sheet_name != "All" else None,
            selected_quarter if selected_quarter != "All" else None,
            selected_year if selected_year != "All" else None
        )
    if 'edit_record_id' not in st.session_state:
        st.session_state.edit_record_id = None
    if 'clear_form' not in st.session_state:
        st.session_state.clear_form = False
    if 'selected_material_for_expert' not in st.session_state:
        st.session_state.selected_material_for_expert = None
    if 'show_material_info' not in st.session_state:
        st.session_state.show_material_info = False
    if 'show_change_list' not in st.session_state:
        st.session_state.show_change_list = False
    if 'adding_action_point' not in st.session_state:
        st.session_state.adding_action_point = False

    def generate_record_id():
        return int(datetime.now().timestamp() * 1000) + random.randint(1, 1000)

    def get_material_base_info(material):
        """Get base info for a material (NSOH, AMC, etc.)"""
        row = df_filtered[df_filtered['Material Description'] == material]
        if row.empty:
            return None

        row = row.iloc[0]
        nsoh = row.get('NSOH', 0)
        amc = row.get('AMC', 0)
        nmos = row.get('NMOS', 0)
        tmos = row.get('TMOS', 0)
        status = row.get('Status', '')

        if material in material_problems:
            pmos = material_problems[material]['PMOS']
            mos_needed = material_problems[material]['MOS Needed']
        else:
            pmos = row.get('PMOS', 0)
            if pd.isna(pmos):
                pmos = tmos - nmos
            mos_needed = max(0, 18 - tmos)

        return {
            'nsoh': f"{int(nsoh):,}" if nsoh > 0 else "0",
            'amc': f"{int(amc):,}" if amc > 0 else "N/A",
            'pmos': round(pmos, 2),
            'nmos': round(nmos, 2),
            'tmos': round(tmos, 2),
            'mos_needed': round(mos_needed, 2),
            'status': status if status else 'N/A'
        }

    def get_system_generated_problems(material):
        """Get all system-generated problems for a material from action_df"""
        if action_df.empty:
            return []

        mat_actions = action_df[action_df['Material'] == material]
        if mat_actions.empty:
            return []

        problems = []
        for _, row in mat_actions.iterrows():
            problems.append({
                'problem': row.get('Identified Problem', ''),
                'action': row.get('Action Point', ''),
                'due_date': row.get('Due Date', ''),
                'responsible': row.get('Responsible Body', '')
            })
        return problems

    # Get selected material from dropdown
    material_list = sorted(df_filtered['Material Description'].dropna().unique())
    selected_material = st.selectbox("🔍 Select Material", material_list, key="expert_material_select")

    if selected_material:
        st.session_state.selected_material_for_expert = selected_material

    # =========================================================================
    # NMOS TREND GRAPH WITH FUTURE PROJECTIONS (6 months)
    # =========================================================================
    if selected_material and not nsoh_pivot.empty:
        st.markdown("---")
        st.markdown("### 📊 NMOS Trend with Threshold Lines")

        # Get AMC value for the selected material
        mat_row = df_filtered[df_filtered['Material Description'] == selected_material]
        amc_value = 0
        if not mat_row.empty:
            amc_value = float(mat_row.iloc[0].get('AMC', 0)) if pd.notna(mat_row.iloc[0].get('AMC', 0)) else 0

        # Get NSOH data for the selected material
        nsoh_row = None
        if 'Material Description' in nsoh_pivot.columns:
            row = nsoh_pivot[nsoh_pivot['Material Description'] == selected_material]
            if not row.empty:
                nsoh_row = row.iloc[0]

        if nsoh_row is not None:
            all_months = get_month_columns(nsoh_pivot)
            if all_months:
                # Filter months from Jan-2026 onward
                all_months = [m for m in all_months if pd.to_datetime(m, format='%b-%Y') >= pd.to_datetime('Jan-2026', format='%b-%Y')]

                if all_months:
                    # Calculate NMOS values for all months
                    nmos_values = []
                    for month in all_months:
                        nsoh_val = nsoh_row[month] if month in nsoh_row.index else 0
                        if pd.notna(nsoh_val) and amc_value > 0 and nsoh_val > 0:
                            nmos_val = nsoh_val / amc_value
                            nmos_values.append(nmos_val)
                        else:
                            nmos_values.append(0)

                    # Get current NMOS (last month's value)
                    current_nmos = nmos_values[-1] if nmos_values else 0

                    # Generate future months (6 months ahead)
                    last_month = pd.to_datetime(all_months[-1], format='%b-%Y')
                    future_months = []
                    future_nmos = []

                    # Use current NMOS and AMC to project future
                    current_nsoh = 0
                    if nsoh_row is not None and all_months[-1] in nsoh_row.index:
                        current_nsoh = nsoh_row[all_months[-1]] if pd.notna(nsoh_row[all_months[-1]]) else 0

                    # Project NMOS for next 6 months based on consumption
                    projected_nsoh = current_nsoh
                    for i in range(1, 7):
                        next_month = last_month + pd.DateOffset(months=i)
                        future_month = next_month.strftime('%b-%Y')
                        future_months.append(future_month)

                        projected_nsoh = max(0, projected_nsoh - amc_value)
                        if amc_value > 0:
                            future_nmos_val = projected_nsoh / amc_value if projected_nsoh > 0 else 0
                        else:
                            future_nmos_val = 0
                        future_nmos.append(future_nmos_val)

                    # Combine historical and future months
                    all_months_extended = all_months + future_months
                    nmos_values_extended = nmos_values + future_nmos

                    # Determine stock out month based on projection
                    stock_out_month = None
                    overstock_month = None
                    understock_month = None

                    # Check future projections
                    for i, (month, nmos_val) in enumerate(zip(future_months, future_nmos)):
                        if nmos_val < 1 and stock_out_month is None:
                            stock_out_month = month
                        elif nmos_val > 18 and overstock_month is None:
                            overstock_month = month
                        elif 1 <= nmos_val < 6 and understock_month is None:
                            understock_month = month

                    # For current stock level predictions
                    if current_nmos < 1:
                        stock_out_month = "NOW (Current Stock Out)"
                    elif current_nmos < 6:
                        if amc_value > 0 and current_nsoh > 0:
                            months_until_out = current_nsoh / amc_value
                            if months_until_out <= 6:
                                future_date = last_month + pd.DateOffset(months=int(months_until_out) + 1)
                                stock_out_month = future_date.strftime('%b-%Y')
                    elif current_nmos > 18:
                        overstock_month = "NOW (Current Overstock)"
                    elif current_nmos >= 6 and current_nmos <= 18:
                        understock_month = None

                    # Determine color for the NMOS line based on current NMOS
                    if current_nmos < 1:
                        nmos_color = '#FF0000'
                        status_text = "🔴 Stock Out"
                    elif 1 <= current_nmos < 6:
                        nmos_color = '#FF8C00'
                        status_text = "🟡 Below Min"
                    elif 6 <= current_nmos <= 18:
                        nmos_color = '#32CD32'
                        status_text = "🟢 Normal"
                    else:
                        nmos_color = '#87CEEB'
                        status_text = "🔵 Overstock"

                    # Create the graph - only Safety Stock, Min, Max, Reorder Point, and Current
                    fig = go.Figure()

                    # Add area fill (shadow) between x-axis and NMOS line
                    fig.add_trace(go.Scatter(
                        x=all_months_extended + all_months_extended[::-1],
                        y=nmos_values_extended + [0]*len(nmos_values_extended),
                        fill='toself',
                        fillcolor=f'rgba({int(nmos_color[1:3], 16)}, {int(nmos_color[3:5], 16)}, {int(nmos_color[5:7], 16)}, 0.15)',
                        line=dict(color='rgba(200, 200, 200, 0)'),
                        showlegend=False,
                        hoverinfo='skip'
                    ))

                    # Historical NMOS line (solid)
                    fig.add_trace(go.Scatter(
                        x=all_months,
                        y=nmos_values,
                        name=f'NMOS (Historical)',
                        mode='lines+markers+text',
                        line=dict(color=nmos_color, width=3),
                        marker=dict(size=10, color=nmos_color, line=dict(width=2, color='white')),
                        text=[f"{v:.2f}" for v in nmos_values],
                        textposition='top center',
                        textfont=dict(size=9, color='#333', family='Times New Roman, Times, serif'),
                        hovertemplate='<b>%{x}</b><br>NMOS: %{y:.2f} months<extra></extra>'
                    ))

                    # Future NMOS line (dashed)
                    fig.add_trace(go.Scatter(
                        x=future_months,
                        y=future_nmos,
                        name='NMOS (Projected)',
                        mode='lines+markers+text',
                        line=dict(color='#FF6B6B', width=2, dash='dash'),
                        marker=dict(size=8, color='#FF6B6B', line=dict(width=1, color='white'), symbol='diamond'),
                        text=[f"{v:.2f}" for v in future_nmos],
                        textposition='top center',
                        textfont=dict(size=9, color='#666', family='Times New Roman, Times, serif'),
                        hovertemplate='<b>%{x}</b><br>NMOS (Projected): %{y:.2f} months<extra></extra>'
                    ))

                    # Add vertical line separating historical and future
                    fig.add_vline(
                        x=all_months[-1],
                        line_dash='dot',
                        line_color='#666',
                        line_width=1.5
                    )

                    # Add annotation for the vertical line
                    max_y = max(nmos_values_extended) if nmos_values_extended else 10
                    fig.add_annotation(
                        x=all_months[-1],
                        y=max_y + 1,
                        text='Current',
                        showarrow=False,
                        font=dict(size=10, color='#666', family='Times New Roman, Times, serif'),
                        yshift=10
                    )

                    # Horizontal threshold lines - only Safety Stock, Min, Max, Reorder Point
                    thresholds = [
                        (2, 'Safety Stock (2m)', '#FF6B6B', 'dash'),
                        (6, 'Min Stock (6m)', '#FF922B', 'dash'),
                        (8, 'Reorder Point (8m)', '#CC5DE8', 'dash'),
                        (18, 'Max Stock (18m)', '#51CF66', 'dash')
                    ]

                    for threshold, label, color, dash in thresholds:
                        fig.add_hline(
                            y=threshold,
                            line_dash=dash,
                            line_color=color,
                            line_width=2,
                            annotation_text=label,
                            annotation_position='right',
                            annotation_font=dict(size=11, color=color, family='Times New Roman, Times, serif')
                        )

                    # Add current NMOS as a reference star
                    fig.add_trace(go.Scatter(
                        x=[all_months[-1]],
                        y=[current_nmos],
                        mode='markers',
                        marker=dict(symbol='star', size=18, color='#FCC419', line=dict(width=2, color='white')),
                        name=f'Current: {current_nmos:.2f}m',
                        hovertemplate='<b>Current NMOS</b><br>%{y:.2f} months<extra></extra>'
                    ))

                    # Add prediction annotations for risks
                    if stock_out_month:
                        fig.add_annotation(
                            x=stock_out_month if stock_out_month != "NOW (Current Stock Out)" else all_months[-1],
                            y=0.5,
                            text=f"⚠️ Stock Out Risk: {stock_out_month}",
                            showarrow=True,
                            arrowhead=2,
                            arrowsize=1.5,
                            arrowwidth=2,
                            arrowcolor='#FF0000',
                            font=dict(size=12, color='#FF0000', family='Times New Roman, Times, serif'),
                            bgcolor='rgba(255, 255, 200, 0.9)',
                            bordercolor='#FF0000',
                            borderwidth=1,
                            borderpad=4
                        )
                    elif overstock_month:
                        fig.add_annotation(
                            x=overstock_month if overstock_month != "NOW (Current Overstock)" else all_months[-1],
                            y=19,
                            text=f"📈 Overstock Risk: {overstock_month}",
                            showarrow=True,
                            arrowhead=2,
                            arrowsize=1.5,
                            arrowwidth=2,
                            arrowcolor='#87CEEB',
                            font=dict(size=12, color='#0066CC', family='Times New Roman, Times, serif'),
                            bgcolor='rgba(200, 230, 255, 0.9)',
                            bordercolor='#87CEEB',
                            borderwidth=1,
                            borderpad=4
                        )
                    elif understock_month:
                        fig.add_annotation(
                            x=understock_month,
                            y=3,
                            text=f"⚠️ Understock Risk: {understock_month}",
                            showarrow=True,
                            arrowhead=2,
                            arrowsize=1.5,
                            arrowwidth=2,
                            arrowcolor='#FF8C00',
                            font=dict(size=12, color='#FF8C00', family='Times New Roman, Times, serif'),
                            bgcolor='rgba(255, 200, 150, 0.9)',
                            bordercolor='#FF8C00',
                            borderwidth=1,
                            borderpad=4
                        )

                    fig.update_layout(
                        title=dict(
                            text=f"NMOS Trend (with 6-month projection) for {selected_material[:50]}" if len(selected_material) <= 50 else f"NMOS Trend (with 6-month projection) for {selected_material[:47]}...",
                            font=dict(size=16, color='#333', family='Times New Roman, Times, serif')
                        ),
                        xaxis_title=dict(text='Month-Year', font=dict(size=13, family='Times New Roman, Times, serif')),
                        yaxis_title=dict(text='Months of Stock (NMOS)', font=dict(size=13, family='Times New Roman, Times, serif')),
                        height=550,
                        margin=dict(l=60, r=180, t=60, b=60),
                        legend=dict(
                            orientation='h',
                            yanchor='bottom',
                            y=1.02,
                            xanchor='center',
                            x=0.5,
                            font=dict(size=11, family='Times New Roman, Times, serif')
                        ),
                        hovermode='x unified',
                        xaxis=dict(
                            showgrid=False,
                            showline=True,
                            linecolor='#333',
                            linewidth=2,
                            tickangle=45,
                            tickfont=dict(size=11, family='Times New Roman, Times, serif'),
                            categoryorder='array',
                            categoryarray=all_months_extended
                        ),
                        yaxis=dict(
                            showgrid=True,
                            gridcolor='#e0e0e0',
                            showline=True,
                            linecolor='#333',
                            linewidth=2,
                            tickfont=dict(size=11, family='Times New Roman, Times, serif'),
                            range=[0, max(22, max(nmos_values_extended) + 3)] if nmos_values_extended else [0, 22]
                        ),
                        plot_bgcolor='white',
                        font=dict(family='Times New Roman, Times, serif')
                    )
                    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': True})

                    st.markdown("---")
                else:
                    st.info("No historical data available from Jan-2026 onward.")
            else:
                st.info("No month columns found in the data.")
        else:
            st.info(f"No NSOH historical data found for {selected_material}.")

    # =========================================================================
    # END OF NMOS TREND GRAPH WITH FUTURE PROJECTIONS
    # =========================================================================

    # Display material info card when toggled
    if st.session_state.show_material_info and selected_material:
        base_info = get_material_base_info(selected_material)
        system_problems = get_system_generated_problems(selected_material)

        if base_info:
            nsoh_str = base_info['nsoh']
            amc_str = base_info['amc']
            pmos_str = f"{base_info['pmos']:.2f}" if base_info['pmos'] else "0.00"
            nmos_str = f"{base_info['nmos']:.2f}" if base_info['nmos'] else "0.00"
            tmos_str = f"{base_info['tmos']:.2f}" if base_info['tmos'] else "0.00"
            status_str = base_info['status']

            # Build card HTML
            html = '<div style="background: #87CEEB; padding: 3px; border-radius: 12px; margin: 10px 0;">'
            html += '<div style="background: #f0f0f0; padding: 20px; border-radius: 10px;">'
            html += f'<h4 style="color: #333; font-size: 18px; font-weight: 700; margin-bottom: 15px;">📦 {selected_material}</h4>'

            html += f'<div style="background: white; padding: 8px 12px; border-radius: 6px; margin-bottom: 5px;"><strong>NSOH:</strong> {nsoh_str}</div>'
            html += f'<div style="background: white; padding: 8px 12px; border-radius: 6px; margin-bottom: 5px;"><strong>AMC:</strong> {amc_str}</div>'
            html += f'<div style="background: white; padding: 8px 12px; border-radius: 6px; margin-bottom: 5px;"><strong>PMOS:</strong> {pmos_str}</div>'
            html += f'<div style="background: white; padding: 8px 12px; border-radius: 6px; margin-bottom: 5px;"><strong>NMOS:</strong> {nmos_str}</div>'
            html += f'<div style="background: white; padding: 8px 12px; border-radius: 6px; margin-bottom: 5px;"><strong>TMOS:</strong> {tmos_str}</div>'
            html += f'<div style="background: white; padding: 8px 12px; border-radius: 6px; margin-bottom: 5px;"><strong>Status:</strong> {status_str}</div>'

            if system_problems:
                html += '<div style="margin-top: 10px;"><strong>System Generated Action Items:</strong><br>'
                for idx, prob in enumerate(system_problems, 1):
                    html += f'<div style="background: rgba(200, 200, 200, 0.3); padding: 8px 12px; border-radius: 6px; margin: 5px 0;">'
                    html += f'<div><span style="display: inline-block; width: 12px; height: 12px; border-radius: 50%; background: #87CEEB; margin-right: 8px;"></span>'
                    html += f'<strong>{idx}. Identified Problem:</strong> {prob["problem"]}</div>'
                    html += f'<div style="padding-left: 24px;"><strong>Action Point:</strong> {prob["action"]}</div>'
                    html += f'<div style="padding-left: 24px; font-size: 12px; opacity: 0.8;"><strong>Due:</strong> {prob["due_date"]} | <strong>Responsible:</strong> {prob["responsible"]}</div>'
                    html += '</div>'
                html += '</div>'
            else:
                html += '<div style="margin-top: 10px;"><strong>System Generated Action Items:</strong> None</div>'

            html += '</div></div>'

            st.markdown(html, unsafe_allow_html=True)

        if st.button("Hide Stock Info", use_container_width=True):
            st.session_state.show_material_info = False
            st.rerun()

        st.markdown("---")

    # =========================================================================
    # ACTION BUTTONS: Stock Info, Add New Action, Change
    # =========================================================================
    if selected_material:
        material_records = [r for r in st.session_state.expert_plan_records if r['Material'] == selected_material]
        has_records = len(material_records) > 0

        col_actions = st.columns(3)

        with col_actions[0]:
            if st.button("📊 Stock Info", use_container_width=True):
                st.session_state.show_material_info = not st.session_state.show_material_info
                st.rerun()

        with col_actions[1]:
            if st.button("➕ Add New Action", use_container_width=True):
                st.session_state.adding_action_point = True
                st.session_state.edit_record_id = None
                st.session_state.show_change_list = False
                st.rerun()

        with col_actions[2]:
            if has_records:
                button_label = "🔄 Hide Actions" if st.session_state.show_change_list else "🔄 Change"
                if st.button(button_label, use_container_width=True):
                    st.session_state.show_change_list = not st.session_state.show_change_list
                    st.session_state.adding_action_point = False
                    st.session_state.edit_record_id = None
                    st.rerun()
            else:
                st.button("🔄 Change", use_container_width=True, disabled=True)

    st.markdown("---")

    # =========================================================================
    # DISPLAY CHANGE LIST (when show_change_list is True)
    # =========================================================================
    if selected_material and st.session_state.show_change_list:
        material_records = [r for r in st.session_state.expert_plan_records if r['Material'] == selected_material]

        if material_records:
            st.markdown(f"### 📋 Action Points for {selected_material}")

            for idx, record in enumerate(material_records):
                with st.container():
                    col1, col2, col3 = st.columns([3, 1, 1])

                    with col1:
                        st.markdown(f"""
                        <div style="background: #f8f9fa; padding: 12px 15px; border-radius: 8px; margin-bottom: 5px; border-left: 4px solid #667eea;">
                            <div><strong>Action #{idx + 1}</strong></div>
                            <div><strong>Problem:</strong> {record.get('Identified Problem', '')}</div>
                            <div><strong>Action:</strong> {record.get('Action Point', '')}</div>
                            <div style="font-size: 12px; color: #666; margin-top: 3px;">
                                <strong>Responsible:</strong> {record.get('Responsible Body', '')} | 
                                <strong>Due:</strong> {record.get('Due Date', '')} | 
                                <strong>Status:</strong> {record.get('Status', 'Pending')}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

                    with col2:
                        if st.button(f"Edit", key=f"change_edit_{record['record_id']}"):
                            st.session_state.edit_record_id = record['record_id']
                            st.session_state.adding_action_point = False
                            st.session_state.show_change_list = False
                            st.rerun()

                    with col3:
                        if st.button(f"Delete", key=f"change_delete_{record['record_id']}"):
                            if st.session_state.get(f'confirm_delete_{record["record_id"]}', False):
                                delete_expert_plan_record(record['record_id'])
                                st.session_state.expert_plan_records = load_expert_plan_records(
                                    sheet_name if sheet_name != "All" else None,
                                    selected_quarter if selected_quarter != "All" else None,
                                    selected_year if selected_year != "All" else None
                                )
                                st.session_state[f'confirm_delete_{record["record_id"]}'] = False
                                st.session_state.show_change_list = False
                                st.rerun()
                            else:
                                st.session_state[f'confirm_delete_{record["record_id"]}'] = True
                                st.warning(f"⚠️ Click Delete again to confirm")
                    st.markdown("---")
        else:
            st.info(f"No action points for {selected_material}.")
            st.session_state.show_change_list = False

    # =========================================================================
    # ADD/EDIT ACTION POINT FORM - Removed "Responsible Body (optional)"
    # =========================================================================
    is_editing = st.session_state.edit_record_id is not None
    is_adding = st.session_state.adding_action_point

    if is_editing or is_adding:
        edit_record = None
        if is_editing:
            for r in st.session_state.expert_plan_records:
                if r['record_id'] == st.session_state.edit_record_id:
                    edit_record = r
                    break

        base_info = get_material_base_info(selected_material)
        material_program = get_material_program(selected_material, sheet_name) if selected_material else ""

        with st.form(key=f"action_point_form_{selected_material}"):
            st.markdown(f"### {'✏️ Edit Action Point' if is_editing else '➕ Add New Action Point'}")

            if is_editing and edit_record:
                problem_val = edit_record.get('Identified Problem', '')
                action_val = edit_record.get('Action Point', '')
                resp_val = edit_record.get('Responsible Body', '')
                due_val = edit_record.get('Due Date', '')
                status_val = edit_record.get('Status', 'Pending')
                purchase_order_val = edit_record.get('Purchase Order', '')
                order_quantity_val = edit_record.get('Order Quantity', '')
                quarter_val = edit_record.get('Quarter', selected_quarter if selected_quarter != "All" else "Q1")
                year_val = edit_record.get('Year', selected_year if selected_year != "All" else current_year)
            else:
                problem_val = ""
                action_val = ""
                resp_val = ""
                due_val = ""
                status_val = "Pending"
                quarter_val = selected_quarter if selected_quarter != "All" else "Q1"
                year_val = selected_year if selected_year != "All" else current_year
                purchase_order_val = ""
                order_quantity_val = ""

            col_q, col_y = st.columns(2)
            with col_q:
                quarter = st.selectbox("Quarter", ["Q1", "Q2", "Q3", "Q4"], index=["Q1", "Q2", "Q3", "Q4"].index(quarter_val) if quarter_val in ["Q1", "Q2", "Q3", "Q4"] else 0, key="ap_quarter")
            with col_y:
                year = st.selectbox("Year", list(range(2020, 2031)), index=list(range(2020, 2031)).index(int(year_val)) if year_val in list(range(2020, 2031)) else 0, key="ap_year")

            col1, col2 = st.columns(2)
            with col1:
                purchase_order = st.text_input("Purchase Order", value=purchase_order_val, key="ap_purchase_order")
                identified_problem = st.text_area("Identified Problem", value=problem_val, key="ap_problem", height=60)
            with col2:
                order_quantity = st.text_input("Order Quantity", value=order_quantity_val, key="ap_order_quantity")
                action_point = st.text_area("Action Point", value=action_val, key="ap_action", height=60)
                due_date = st.text_input("Due Date", value=due_val, key="ap_due_date")
                status = st.selectbox("Status", ["Initiated", "Ongoing", "Pending", "Completed"], index=["Initiated", "Ongoing", "Pending", "Completed"].index(status_val) if status_val in ["Initiated", "Ongoing", "Pending", "Completed"] else 0, key="ap_status")

            # Responsible Body as a multiselect
            st.markdown("**Responsible Body**")
            default_responsible = []
            if is_editing and edit_record and resp_val:
                # Split by comma and strip whitespace
                default_responsible = [b.strip() for b in resp_val.split(',') if b.strip()]
            additional_responsible = st.multiselect(
                "Select responsible bodies",
                RESPONSIBLE_BODIES,
                default=default_responsible,
                key="ap_additional_responsible"
            )

            final_responsible = ", ".join(additional_responsible) if additional_responsible else ""

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                submit_label = "💾 Update" if is_editing else "💾 Save"
                submit_clicked = st.form_submit_button(submit_label, use_container_width=True)
            with col_btn2:
                cancel_clicked = st.form_submit_button("❌ Cancel", use_container_width=True)

            if submit_clicked:
                if selected_material and identified_problem and action_point and due_date:
                    if is_editing and edit_record:
                        updated_record = {
                            'record_id': st.session_state.edit_record_id,
                            'Material': selected_material,
                            'NSOH': base_info['nsoh'] if base_info else "",
                            'AMC': base_info['amc'] if base_info else "",
                            'PMOS': base_info['pmos'] if base_info else 0,
                            'NMOS': base_info['nmos'] if base_info else 0,
                            'TMOS': base_info['tmos'] if base_info else 0,
                            'Purchase Order': purchase_order,
                            'Order Quantity': order_quantity,
                            'Identified Problem': identified_problem,
                            'Action Point': action_point,
                            'Responsible Body': final_responsible,
                            'Due Date': due_date,
                            'Status': status,
                            'Quarter': quarter,
                            'Year': int(year),
                            'Program': material_program if material_program != "Multiple Programs" else sheet_name if sheet_name != "All" else "Multiple Programs"
                        }
                        if save_expert_plan_record(updated_record):
                            st.session_state.expert_plan_records = load_expert_plan_records(sheet_name if sheet_name != "All" else None, quarter if quarter != "All" else None, year if year != "All" else None)
                            st.session_state.edit_record_id = None
                            st.session_state.adding_action_point = False
                            st.rerun()
                    else:
                        new_record = {
                            'record_id': generate_record_id(),
                            'Material': selected_material,
                            'NSOH': base_info['nsoh'] if base_info else "",
                            'AMC': base_info['amc'] if base_info else "",
                            'PMOS': base_info['pmos'] if base_info else 0,
                            'NMOS': base_info['nmos'] if base_info else 0,
                            'TMOS': base_info['tmos'] if base_info else 0,
                            'Purchase Order': purchase_order,
                            'Order Quantity': order_quantity,
                            'Identified Problem': identified_problem,
                            'Action Point': action_point,
                            'Responsible Body': final_responsible,
                            'Due Date': due_date,
                            'Status': status,
                            'Quarter': quarter,
                            'Year': int(year),
                            'Program': material_program if material_program != "Multiple Programs" else sheet_name if sheet_name != "All" else "Multiple Programs"
                        }
                        if save_expert_plan_record(new_record):
                            st.session_state.expert_plan_records = load_expert_plan_records(sheet_name if sheet_name != "All" else None, quarter if quarter != "All" else None, year if year != "All" else None)
                            st.session_state.adding_action_point = False
                            st.rerun()
                else:
                    st.warning("Please fill all required fields (Identified Problem, Action Point, Due Date).")

            if cancel_clicked:
                st.session_state.edit_record_id = None
                st.session_state.adding_action_point = False
                st.session_state.show_change_list = False
                st.rerun()

    st.markdown("---")

    # =========================================================================
    # DISPLAY ALL RECORDS TABLE - WITH FILTERS AND GROUPED BY QUARTER
    # =========================================================================
    if st.session_state.expert_plan_records:
        records_df = pd.DataFrame(st.session_state.expert_plan_records)

        # Apply filters
        if sheet_name != "All":
            records_df = records_df[records_df['Program'] == sheet_name]

        if selected_quarter != "All":
            records_df = records_df[records_df['Quarter'] == selected_quarter]

        if selected_year != "All":
            records_df = records_df[records_df['Year'] == int(selected_year)]

        if not records_df.empty:
            # Sort materials alphabetically
            records_df = records_df.sort_values('Material')

            # Get unique programs for filter
            all_programs = sorted(records_df['Program'].unique().tolist()) if 'Program' in records_df.columns else []
            default_programs = ['Malaria'] if 'Malaria' in all_programs else all_programs[:1] if all_programs else []

            # Get unique problems for filter
            all_problems = sorted(records_df['Identified Problem'].unique().tolist()) if 'Identified Problem' in records_df.columns else []

            # Get unique responsible bodies for filter
            all_responsible = sorted(records_df['Responsible Body'].unique().tolist()) if 'Responsible Body' in records_df.columns else []

            # Get unique statuses for filter
            all_statuses = sorted(records_df['Status'].unique().tolist()) if 'Status' in records_df.columns else []

            # Multi-select filters - Updated to include NMOS dropdown and Status dropdown
            col_filter1, col_filter2, col_filter3, col_filter4 = st.columns(4)

            with col_filter1:
                selected_programs = st.multiselect(
                    "Program",
                    options=all_programs,
                    default=default_programs,
                    key="filter_program"
                )

            with col_filter2:
                # NMOS filter - dropdown with various options
                nmos_filter_type = st.selectbox(
                    "NMOS Filter",
                    ["All", "< 1", "1-4", "1-6", "< 6", "6-18", "> 18", "< 12"],
                    key="nmos_filter_type"
                )

            with col_filter3:
                selected_problems = st.multiselect(
                    "Identified Problem",
                    options=all_problems,
                    default=[],
                    key="filter_problem"
                )

            with col_filter4:
                selected_statuses = st.multiselect(
                    "Status",
                    options=all_statuses,
                    default=[],
                    key="filter_status"
                )

            # Apply filters
            filtered_df = records_df.copy()

            if selected_programs:
                filtered_df = filtered_df[filtered_df['Program'].isin(selected_programs)]

            # Apply NMOS filter
            if nmos_filter_type != "All" and 'NMOS' in filtered_df.columns:
                filtered_df['NMOS'] = pd.to_numeric(filtered_df['NMOS'], errors='coerce')
                if nmos_filter_type == "< 1":
                    filtered_df = filtered_df[filtered_df['NMOS'] < 1]
                elif nmos_filter_type == "1-4":
                    filtered_df = filtered_df[(filtered_df['NMOS'] >= 1) & (filtered_df['NMOS'] <= 4)]
                elif nmos_filter_type == "1-6":
                    filtered_df = filtered_df[(filtered_df['NMOS'] >= 1) & (filtered_df['NMOS'] <= 6)]
                elif nmos_filter_type == "< 6":
                    filtered_df = filtered_df[filtered_df['NMOS'] < 6]
                elif nmos_filter_type == "6-18":
                    filtered_df = filtered_df[(filtered_df['NMOS'] >= 6) & (filtered_df['NMOS'] <= 18)]
                elif nmos_filter_type == "> 18":
                    filtered_df = filtered_df[filtered_df['NMOS'] > 18]
                elif nmos_filter_type == "< 12":
                    filtered_df = filtered_df[filtered_df['NMOS'] < 12]

            if selected_problems:
                filtered_df = filtered_df[filtered_df['Identified Problem'].isin(selected_problems)]

            if selected_statuses:
                filtered_df = filtered_df[filtered_df['Status'].isin(selected_statuses)]

            # Group by Quarter and display separately
            if 'Quarter' in filtered_df.columns:
                quarters = sorted(filtered_df['Quarter'].unique())

                for quarter in quarters:
                    quarter_df = filtered_df[filtered_df['Quarter'] == quarter]

                    if not quarter_df.empty:
                        # Get year for this quarter
                        years = quarter_df['Year'].unique()
                        year_str = ", ".join([str(y) for y in sorted(years)])

                        # Get programs for this quarter
                        programs = quarter_df['Program'].unique()
                        program_str = ", ".join(sorted(programs))

                        st.markdown(f"### 📋 {quarter}, {year_str} - {program_str}")

                        # Select columns to display
                        cols = ['Material', 'NSOH', 'AMC', 'PMOS', 'NMOS', 'TMOS', 
                                'Purchase Order', 'Order Quantity', 'Identified Problem', 
                                'Action Point', 'Responsible Body', 'Due Date', 'Status']
                        cols = [c for c in cols if c in quarter_df.columns]
                        display_df = quarter_df[cols]

                        st.dataframe(display_df, use_container_width=True, hide_index=True)
                        st.markdown("---")
            else:
                # If no Quarter column, display all together
                st.markdown(f"### 📋 All Action Points")
                cols = ['Material', 'NSOH', 'AMC', 'PMOS', 'NMOS', 'TMOS', 
                        'Purchase Order', 'Order Quantity', 'Identified Problem', 
                        'Action Point', 'Responsible Body', 'Due Date', 'Status']
                cols = [c for c in cols if c in filtered_df.columns]
                display_df = filtered_df[cols]
                st.dataframe(display_df, use_container_width=True, hide_index=True)

            # Download button for all filtered data as XLSX
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                filtered_df.to_excel(writer, index=False, sheet_name='Action Points')
            excel_data = output.getvalue()

            st.download_button(
                label="📥 Download All Action Points (XLSX)",
                data=excel_data,
                file_name=f"all_action_points_{sheet_name}_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        else:
            st.info(f"No action points found for {sheet_name} with the selected filters.")
    else:
        if selected_material:
            st.info("No action points saved for this material.")
        else:
            st.info("No expert action plans saved yet.")

    # Reload records
    st.session_state.expert_plan_records = load_expert_plan_records(
        sheet_name if sheet_name != "All" else None,
        selected_quarter if selected_quarter != "All" else None,
        selected_year if selected_year != "All" else None
    )

def render_ap_progress_follow_up(sheet_name, selected_quarter, selected_year, selected_status):
    # Load records with filters
    records = load_expert_plan_records(
        sheet_name if sheet_name != "All" else None,
        selected_quarter if selected_quarter != "All" else None,
        selected_year if selected_year != "All" else None
    )

    if not records:
        st.info("No Expert Action Plan records available for this program with the selected filters. Please add some records in the Expert Action Plan section.")
        return

    df = pd.DataFrame(records)

    if 'Status' not in df.columns:
        df['Status'] = "Pending"

    # =========================================================================
    # FILTERS - Updated to remove header and use only the summary table
    # =========================================================================
    # Determine the latest quarter
    latest_quarter = None
    latest_year = None
    if 'Quarter' in df.columns and 'Year' in df.columns:
        quarter_order = {'Q1': 1, 'Q2': 2, 'Q3': 3, 'Q4': 4}
        df['Quarter_Sort'] = df['Year'].astype(str) + df['Quarter'].map(quarter_order).astype(str)
        if not df.empty:
            latest_row = df.loc[df['Quarter_Sort'].idxmax()]
            latest_quarter = latest_row['Quarter']
            latest_year = latest_row['Year']

    # Display title with latest quarter, year, and program
    program_name = sheet_name if sheet_name != "All" else "All Programs"
    if latest_quarter and latest_year:
        st.markdown(f"### 📋 {latest_quarter}, {latest_year} - {program_name} Action Plan Summary Table")
    else:
        st.markdown(f"### 📋 {program_name} Action Plan Summary Table")

    st.markdown('<div class="filter-row">', unsafe_allow_html=True)

    col_filter0, col_filter1, col_filter2, col_filter3 = st.columns(4)

    with col_filter0:
        all_programs = sorted(df['Program'].unique().tolist()) if 'Program' in df.columns else []
        default_programs = ['Malaria'] if 'Malaria' in all_programs else all_programs[:1] if all_programs else []

        program_filter = st.multiselect(
            "Program",
            options=all_programs,
            default=default_programs,
            key="ap_program_filter"
        )

    with col_filter1:
        problem_options = ["All"] + sorted(df['Identified Problem'].unique().tolist()) if 'Identified Problem' in df.columns else ["All"]
        problem_filter = st.selectbox("Problem Type", problem_options, key="problem_filter_dropdown")

    with col_filter2:
        body_options = ["All"] + sorted(df['Responsible Body'].unique().tolist()) if 'Responsible Body' in df.columns else ["All"]
        body_filter = st.selectbox("Responsible Body", body_options, key="body_filter_dropdown")

    with col_filter3:
        status_options = ["All"] + sorted(df['Status'].unique().tolist()) if 'Status' in df.columns else ["All"]
        status_filter = st.selectbox("Status", status_options, key="status_filter_dropdown_ap")

    st.markdown('</div>', unsafe_allow_html=True)

    # Apply filters
    filtered_df = df.copy()

    if program_filter:
        filtered_df = filtered_df[filtered_df['Program'].isin(program_filter)]

    if problem_filter != "All" and 'Identified Problem' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['Identified Problem'] == problem_filter]

    if body_filter != "All" and 'Responsible Body' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['Responsible Body'] == body_filter]

    if status_filter != "All" and 'Status' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['Status'] == status_filter]

    if selected_status != "All" and 'Status' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['Status'] == selected_status]

    if filtered_df.empty:
        st.info("No records match the selected filters.")
        return

    # =========================================================================
    # FILTER TO LATEST QUARTER ONLY
    # =========================================================================
    if 'Quarter' in filtered_df.columns and 'Year' in filtered_df.columns:
        quarter_order = {'Q1': 1, 'Q2': 2, 'Q3': 3, 'Q4': 4}
        filtered_df['Quarter_Sort'] = filtered_df['Year'].astype(str) + filtered_df['Quarter'].map(quarter_order).astype(str)
        if not filtered_df.empty:
            latest_quarter_val = filtered_df.loc[filtered_df['Quarter_Sort'].idxmax()]['Quarter']
            latest_year_val = filtered_df.loc[filtered_df['Quarter_Sort'].idxmax()]['Year']

            filtered_df = filtered_df[(filtered_df['Quarter'] == latest_quarter_val) & (filtered_df['Year'] == latest_year_val)]

            if filtered_df.empty:
                st.info(f"No records found for the latest quarter ({latest_quarter_val}, {latest_year_val}).")
                return

            # Update title with latest quarter info
            program_name = sheet_name if sheet_name != "All" else "All Programs"
            st.markdown(f"### 📋 {latest_quarter_val}, {latest_year_val} - {program_name} Action Plan Summary Table")

    # Sort materials alphabetically
    filtered_df = filtered_df.sort_values('Material')

    # =========================================================================
    # CALCULATE STATUS COUNTS
    # =========================================================================
    total = len(filtered_df)
    completed = len(filtered_df[filtered_df['Status'] == 'Completed'])
    ongoing = len(filtered_df[filtered_df['Status'] == 'Ongoing'])
    pending = len(filtered_df[filtered_df['Status'] == 'Pending'])
    initiated = len(filtered_df[filtered_df['Status'] == 'Initiated'])

    not_completed = initiated + ongoing

    # =========================================================================
    # CREATE STATUS BADGES
    # =========================================================================
    def status_badge_html(status, material):
        colors = {
            'Completed': '#28a745',
            'Ongoing': '#007bff',
            'Pending': '#ffc107',
            'Initiated': '#6f42c1'
        }
        color = colors.get(status, '#6c757d')
        return f'<span class="status-badge" style="background: {color}; color: white; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; cursor: pointer;" data-status="{status}" data-material="{material}">{status}</span>'

    display_df = filtered_df.copy()
    display_df['Status Display'] = display_df.apply(lambda row: status_badge_html(row.get('Status', 'Pending'), row.get('Material', '')), axis=1)

    # Show table - increased width for Identified Problem and Action Point
    cols_to_display = ['Material', 'NMOS', 'Identified Problem', 'Action Point', 'Responsible Body', 'Due Date', 'Status Display']
    cols_to_display = [c for c in cols_to_display if c in display_df.columns or c == 'Status Display']

    html_table = '<div class="dataframe-container"><table class="styled-table" style="font-family: Times New Roman, Times, serif !important; font-size: 14px; width: 100%;"><thead><tr>'
    for col in cols_to_display:
        if col == 'Status Display':
            html_table += '<th style="font-family: Times New Roman, Times, serif !important; font-size: 15px; width: 10%;">Status</th>'
        elif col == 'Identified Problem':
            html_table += '<th style="font-family: Times New Roman, Times, serif !important; font-size: 15px; width: 25%;">Identified Problem</th>'
        elif col == 'Action Point':
            html_table += '<th style="font-family: Times New Roman, Times, serif !important; font-size: 15px; width: 25%;">Action Point</th>'
        else:
            html_table += f'<th style="font-family: Times New Roman, Times, serif !important; font-size: 15px;">{col}</th>'
    html_table += '</tr></thead><tbody>'

    for _, row in display_df.iterrows():
        html_table += '<tr class="clickable-row" data-material="' + str(row.get('Material', '')) + '">'
        for col in cols_to_display:
            if col == 'Status Display':
                html_table += f'<td style="font-family: Times New Roman, Times, serif !important; font-size: 14px;">{row[col]}</td>'
            elif col == 'Identified Problem':
                html_table += f'<td style="font-family: Times New Roman, Times, serif !important; font-size: 14px; min-width: 200px;">{row.get(col, "")}</td>'
            elif col == 'Action Point':
                html_table += f'<td style="font-family: Times New Roman, Times, serif !important; font-size: 14px; min-width: 200px;">{row.get(col, "")}</td>'
            else:
                html_table += f'<td style="font-family: Times New Roman, Times, serif !important; font-size: 14px;">{row.get(col, "")}</td>'
        html_table += '</tr>'

    html_table += '</tbody></table></div>'

    st.markdown(html_table, unsafe_allow_html=True)

    # Download as XLSX
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        display_df[['Material', 'NMOS', 'Identified Problem', 'Action Point', 'Responsible Body', 'Due Date', 'Status']].to_excel(writer, index=False, sheet_name='Action Plan')
    excel_data = output.getvalue()

    st.download_button(
        label="📥 Download Detailed Action Plan (XLSX)",
        data=excel_data,
        file_name=f"detailed_action_plan_{sheet_name}_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

    st.markdown("---")

    # =========================================================================
    # PIE CHART - Dynamic Title based on selected program
    # =========================================================================
    selected_program_names = program_filter if program_filter else ["All Programs"]
    program_title = ", ".join(selected_program_names)

    st.markdown(f"### 📊 {program_title} Action Plan Status Distribution")

    status_labels = ['Completed', 'Not Completed', 'Pending']
    status_values = [completed, not_completed, pending]
    status_colors_pie = ['#28a745', '#007bff', '#ffc107']

    fig_pie = go.Figure(data=[go.Pie(
        labels=status_labels,
        values=status_values,
        hole=0.3,
        marker=dict(colors=status_colors_pie),
        textinfo='label+percent',
        textfont=dict(size=13, family='Times New Roman, Times, serif'),
        hoverinfo='label+value+percent',
        hovertemplate='<b>%{label}</b><br>Count: %{value}<br>Percentage: %{percent}<extra></extra>'
    )])
    fig_pie.update_layout(
        title=dict(
            text=f"Total Action Points: {total}",
            font=dict(size=14, color='#333', family='Times New Roman, Times, serif')
        ),
        height=400,
        font=dict(family='Times New Roman, Times, serif'),
        plot_bgcolor='white',
        paper_bgcolor='white',
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=-0.1,
            xanchor='center',
            x=0.5,
            font=dict(size=12, family='Times New Roman, Times, serif')
        )
    )
    st.plotly_chart(fig_pie, use_container_width=True, config={'displayModeBar': True})

    st.markdown("---")

    # =========================================================================
    # BAR CHARTS - Side by side: Program Action Points Breakdown and Responsible Body
    # =========================================================================
    col_bar1, col_bar2 = st.columns(2)

    with col_bar1:
        st.markdown(f"### 📊 Program Action Points Breakdown")

        # Get program breakdown
        if 'Program' in filtered_df.columns:
            program_breakdown = filtered_df['Program'].value_counts().reset_index()
            program_breakdown.columns = ['Program', 'Count']
            program_breakdown['Percentage'] = (program_breakdown['Count'] / total * 100).round(1)

            if not program_breakdown.empty:
                # Sort by count descending
                program_breakdown = program_breakdown.sort_values('Count', ascending=False)

                fig_prog_bar = go.Figure()

                colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']

                fig_prog_bar.add_trace(go.Bar(
                    x=program_breakdown['Program'],
                    y=program_breakdown['Percentage'],
                    marker_color=colors[:len(program_breakdown)],
                    text=program_breakdown['Percentage'].apply(lambda x: f'{x:.1f}%'),
                    textposition='inside',
                    textfont=dict(size=11, color='white', family='Times New Roman, Times, serif', weight='bold'),
                    hovertemplate='<b>%{x}</b><br>Percentage: %{y:.1f}%<br>Count: %{customdata}<extra></extra>',
                    customdata=program_breakdown['Count'],
                    width=0.6
                ))

                fig_prog_bar.update_layout(
                    title=dict(
                        text="Action Points by Program",
                        font=dict(size=14, color='#333', family='Times New Roman, Times, serif')
                    ),
                    xaxis_title=dict(text="Program", font=dict(size=12, family='Times New Roman, Times, serif')),
                    yaxis_title=dict(text="Percentage of Total (%)", font=dict(size=12, family='Times New Roman, Times, serif')),
                    height=400,
                    xaxis=dict(
                        tickfont=dict(size=11, family='Times New Roman, Times, serif'),
                        showgrid=False,
                        showline=True,
                        linecolor='#333',
                        linewidth=1.5
                    ),
                    yaxis=dict(
                        tickfont=dict(size=11, family='Times New Roman, Times, serif'),
                        showgrid=True,
                        gridcolor='#e0e0e0',
                        showline=True,
                        linecolor='#333',
                        linewidth=1.5,
                        range=[0, max(60, program_breakdown['Percentage'].max() + 10)] if not program_breakdown.empty else [0, 100],
                        tickformat='.0f',
                        ticksuffix='%'
                    ),
                    plot_bgcolor='white',
                    margin=dict(l=50, r=30, t=60, b=50),
                    font=dict(family='Times New Roman, Times, serif')
                )

                for i, row in program_breakdown.iterrows():
                    if row['Count'] > 0:
                        fig_prog_bar.add_annotation(
                            x=row['Program'],
                            y=row['Percentage'] / 2,
                            text=f"n={row['Count']}",
                            showarrow=False,
                            font=dict(size=11, color='white', family='Times New Roman, Times, serif', weight='bold'),
                            bgcolor='rgba(0,0,0,0)',
                            borderpad=0
                        )

                st.plotly_chart(fig_prog_bar, use_container_width=True, config={'displayModeBar': True})
            else:
                st.info("No program data available.")
        else:
            st.info("No program data available.")

    with col_bar2:
        st.markdown(f"### 📊 Responsible Body Breakdown")

        # Split responsible bodies by comma and explode
        all_bodies = []
        for body_str in filtered_df['Responsible Body'].dropna():
            bodies = [b.strip() for b in body_str.split(',') if b.strip()]
            all_bodies.extend(bodies)

        if all_bodies:
            body_counts = pd.Series(all_bodies).value_counts().reset_index()
            body_counts.columns = ['Responsible Body', 'Count']
            body_counts['Percentage'] = (body_counts['Count'] / total * 100).round(1)

            # Sort by count descending
            body_counts = body_counts.sort_values('Count', ascending=False)

            fig_body_bar = go.Figure()

            colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']

            fig_body_bar.add_trace(go.Bar(
                x=body_counts['Responsible Body'],
                y=body_counts['Percentage'],
                marker_color=colors[:len(body_counts)],
                text=body_counts['Percentage'].apply(lambda x: f'{x:.1f}%'),
                textposition='inside',
                textfont=dict(size=11, color='white', family='Times New Roman, Times, serif', weight='bold'),
                hovertemplate='<b>%{x}</b><br>Percentage: %{y:.1f}%<br>Count: %{customdata}<extra></extra>',
                customdata=body_counts['Count'],
                width=0.6
            ))

            fig_body_bar.update_layout(
                title=dict(
                    text="Action Points by Responsible Body",
                    font=dict(size=14, color='#333', family='Times New Roman, Times, serif')
                ),
                xaxis_title=dict(text="Responsible Body", font=dict(size=12, family='Times New Roman, Times, serif')),
                yaxis_title=dict(text="Percentage of Total (%)", font=dict(size=12, family='Times New Roman, Times, serif')),
                height=400,
                xaxis=dict(
                    tickfont=dict(size=10, family='Times New Roman, Times, serif'),
                    showgrid=False,
                    showline=True,
                    linecolor='#333',
                    linewidth=1.5,
                    tickangle=45
                ),
                yaxis=dict(
                    tickfont=dict(size=11, family='Times New Roman, Times, serif'),
                    showgrid=True,
                    gridcolor='#e0e0e0',
                    showline=True,
                    linecolor='#333',
                    linewidth=1.5,
                    range=[0, max(60, body_counts['Percentage'].max() + 10)] if not body_counts.empty else [0, 100],
                    tickformat='.0f',
                    ticksuffix='%'
                ),
                plot_bgcolor='white',
                margin=dict(l=50, r=30, t=60, b=80),
                font=dict(family='Times New Roman, Times, serif')
            )

            for i, row in body_counts.iterrows():
                if row['Count'] > 0:
                    fig_body_bar.add_annotation(
                        x=row['Responsible Body'],
                        y=row['Percentage'] / 2,
                        text=f"n={row['Count']}",
                        showarrow=False,
                        font=dict(size=11, color='white', family='Times New Roman, Times, serif', weight='bold'),
                        bgcolor='rgba(0,0,0,0)',
                        borderpad=0
                    )

            st.plotly_chart(fig_body_bar, use_container_width=True, config={'displayModeBar': True})
        else:
            st.info("No responsible body data available.")

    st.markdown("---")

    # =========================================================================
    # DETAILED BAR CHART - EPSS Breakdown (EPSS_CMD, EPSS_PMD, EPSS_DMD, EPSS_Finance)
    # =========================================================================
    # Check if EPSS has data - use the exploded body list
    epss_bodies = ['EPSS_CMD', 'EPSS_DMD', 'EPSS_PMD', 'EPSS_Finance']
    epss_total = 0
    for body in epss_bodies:
        epss_total += len([b for b in all_bodies if b == body]) if all_bodies else 0

    if epss_total > 0 and all_bodies:
        st.markdown("### 📊 EPSS Detailed Breakdown")

        epss_detail_data = []
        for body in epss_bodies:
            body_count = len([b for b in all_bodies if b == body])
            if body_count > 0:
                # Get status breakdown for this body
                body_status_counts = {}
                for _, row in filtered_df.iterrows():
                    responsible = row.get('Responsible Body', '')
                    if body in [b.strip() for b in responsible.split(',') if b.strip()]:
                        status = row.get('Status', 'Pending')
                        body_status_counts[status] = body_status_counts.get(status, 0) + 1

                completed_body = body_status_counts.get('Completed', 0)
                not_completed_body = body_status_counts.get('Initiated', 0) + body_status_counts.get('Ongoing', 0)
                pending_body = body_status_counts.get('Pending', 0)

                epss_detail_data.append({
                    'Body': body,
                    'Total': body_count,
                    'Completed': completed_body,
                    'Completed %': (completed_body / body_count * 100) if body_count > 0 else 0,
                    'Not Completed': not_completed_body,
                    'Not Completed %': (not_completed_body / body_count * 100) if body_count > 0 else 0,
                    'Pending': pending_body,
                    'Pending %': (pending_body / body_count * 100) if body_count > 0 else 0
                })

        if epss_detail_data:
            epss_detail_df = pd.DataFrame(epss_detail_data)

            fig_epss = go.Figure()

            statuses = ['Completed', 'Not Completed', 'Pending']
            status_colors_bar = {
                'Completed': '#28a745',
                'Not Completed': '#007bff',
                'Pending': '#ffc107'
            }

            for status in statuses:
                fig_epss.add_trace(go.Bar(
                    name=status,
                    x=epss_detail_df['Body'],
                    y=epss_detail_df[f'{status} %'],
                    marker_color=status_colors_bar.get(status, '#666'),
                    text=epss_detail_df[f'{status} %'].apply(lambda x: f'{x:.1f}%'),
                    textposition='inside',
                    textfont=dict(size=11, color='white', family='Times New Roman, Times, serif'),
                    hovertemplate='<b>%{x}</b><br>%{fullData.name}: %{y:.1f}%<br>Count: %{customdata}<extra></extra>',
                    customdata=epss_detail_df[status]
                ))

            fig_epss.update_layout(
                title=dict(
                    text="EPSS Detailed Breakdown by Body",
                    font=dict(size=16, color='#333', family='Times New Roman, Times, serif')
                ),
                xaxis_title=dict(text="EPSS Body", font=dict(size=13, family='Times New Roman, Times, serif')),
                yaxis_title=dict(text="Percentage (%)", font=dict(size=13, family='Times New Roman, Times, serif')),
                barmode='stack',
                height=400,
                legend=dict(
                    orientation='h',
                    yanchor='bottom',
                    y=1.02,
                    xanchor='center',
                    x=0.5,
                    font=dict(size=12, family='Times New Roman, Times, serif')
                ),
                xaxis=dict(
                    tickfont=dict(size=11, family='Times New Roman, Times, serif'),
                    showgrid=False,
                    showline=True,
                    linecolor='#333',
                    linewidth=1.5
                ),
                yaxis=dict(
                    tickfont=dict(size=11, family='Times New Roman, Times, serif'),
                    showgrid=True,
                    gridcolor='#e0e0e0',
                    showline=True,
                    linecolor='#333',
                    linewidth=1.5,
                    range=[0, 105],
                    tickformat='.0f',
                    ticksuffix='%'
                ),
                plot_bgcolor='white',
                margin=dict(l=50, r=30, t=80, b=50),
                font=dict(family='Times New Roman, Times, serif')
            )

            for i, row in epss_detail_df.iterrows():
                fig_epss.add_annotation(
                    x=row['Body'],
                    y=102,
                    text=f"n={row['Total']}",
                    showarrow=False,
                    font=dict(size=11, color='#333', family='Times New Roman, Times, serif', weight='bold'),
                    bgcolor='rgba(255,255,255,0.9)',
                    bordercolor='#ccc',
                    borderwidth=1,
                    borderpad=4
                )

            st.plotly_chart(fig_epss, use_container_width=True, config={'displayModeBar': True})

            # Show EPSS summary table
            st.markdown("#### EPSS Summary Table")
            epss_display = epss_detail_df.copy()
            epss_display['Completed %'] = epss_display['Completed %'].round(1)
            epss_display['Not Completed %'] = epss_display['Not Completed %'].round(1)
            epss_display['Pending %'] = epss_display['Pending %'].round(1)
            epss_display = epss_display[['Body', 'Total', 'Completed', 'Completed %', 'Not Completed', 'Not Completed %', 'Pending', 'Pending %']]
            epss_display.columns = ['Body', 'Total', 'Completed', 'Completed %', 'Not Completed', 'Not Completed %', 'Pending', 'Pending %']
            st.dataframe(epss_display, use_container_width=True, hide_index=True)

def main():
    st.set_page_config(
        page_title="Supply Planning – EPSS",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # Initialize ALL session state variables at the start
    if 'action_plan_tab' not in st.session_state:
        st.session_state.action_plan_tab = "📋 All Issues"
    if 'expert_plan_records' not in st.session_state:
        st.session_state.expert_plan_records = []
    if 'edit_record_id' not in st.session_state:
        st.session_state.edit_record_id = None
    if 'clear_form' not in st.session_state:
        st.session_state.clear_form = False
    if 'selected_program' not in st.session_state:
        st.session_state.selected_program = "All"
    if 'selected_subcategory' not in st.session_state:
        st.session_state.selected_subcategory = "All"
    if 'selected_material_for_expert' not in st.session_state:
        st.session_state.selected_material_for_expert = None
    if 'status_filter' not in st.session_state:
        st.session_state.status_filter = None
    if 'show_status_table' not in st.session_state:
        st.session_state.show_status_table = False
    if 'confirm_delete' not in st.session_state:
        st.session_state.confirm_delete = False
    if 'show_material_info' not in st.session_state:
        st.session_state.show_material_info = False
    if 'selected_quarter' not in st.session_state:
        st.session_state.selected_quarter = "All"
    if 'selected_year' not in st.session_state:
        st.session_state.selected_year = "All"
    if 'selected_status' not in st.session_state:
        st.session_state.selected_status = "All"

    # Inject custom CSS and JavaScript
    inject_custom_css()
    inject_javascript()

    # App Header - Ruby color (removed subtitle)
    st.markdown("""
    <div class="app-header fade-in">
        <h1>📦 Supply Planning Dashboard</h1>
    </div>
    """, unsafe_allow_html=True)

    # Sidebar: Program selection and Quarter/Year filters
    with st.sidebar:
        st.markdown("## 🎯 Program Selection")
        sheet_id_amc = "14VvZ7IyOmpM4SZrY5_ArHDgLkeFN4inW"
        google_sheets = load_google_sheets(sheet_id_amc)

        # Check if google_sheets has data
        has_data = False
        if google_sheets:
            for key, df in google_sheets.items():
                if not df.empty:
                    has_data = True
                    break

        if not has_data:
            st.warning("⚠️ Could not load program data from Google Sheets. Using fallback programs.")
            program_list = ["All", "Malaria", "HIV", "TB", "OI and Hepatitis", "Nutrition", "Lab TB", "HIV Lab"]
        else:
            program_list = ["All"] + list(google_sheets.keys()) if google_sheets else ["All"]

        sheet_name = st.selectbox("Select Program", program_list, index=program_list.index(st.session_state.selected_program) if st.session_state.selected_program in program_list else 0)
        st.session_state.selected_program = sheet_name

        PROGRAM_HIERARCHY = {
            "OI and Hepatitis": {"subcategories": ["AHD", "Hepatitis", "OI", "STI"], "is_parent": True},
            "TB": {"subcategories": ["Drug Susceptible -TB Medicine (DS-TB)", "Drug Resisitance -TB Medicine (DR-TB)", "Leprosy Medicines", "Nutrition"], "is_parent": True},
            "Lab TB": {"subcategories": ["TB diagnostics& Laboratory reagent", "TB Lab Supplies"], "is_parent": True},
            "HIV Lab": {"subcategories": ["HIV VL Reagents", "CD4 ,AHD &HIV RTKs"], "is_parent": True}
        }
        subcategory_options = ["All"]
        if sheet_name in PROGRAM_HIERARCHY and PROGRAM_HIERARCHY[sheet_name]["is_parent"]:
            subcategory_options = ["All"] + PROGRAM_HIERARCHY[sheet_name]["subcategories"]
            subcategory_filter = st.selectbox("Subcategory", subcategory_options, index=subcategory_options.index(st.session_state.selected_subcategory) if st.session_state.selected_subcategory in subcategory_options else 0)
            st.session_state.selected_subcategory = subcategory_filter
        else:
            subcategory_filter = "All"
            st.session_state.selected_subcategory = "All"

        st.markdown("---")
        st.markdown("## 📅 Quarter & Year Filters")

        # Quarter dropdown
        quarter_options = ["All", "Q1", "Q2", "Q3", "Q4"]
        selected_quarter = st.selectbox(
            "Select Quarter",
            quarter_options,
            index=quarter_options.index(st.session_state.selected_quarter) if st.session_state.selected_quarter in quarter_options else 0
        )
        st.session_state.selected_quarter = selected_quarter

        # Year dropdown
        current_year = datetime.now().year
        year_options = ["All"] + list(range(current_year - 5, current_year + 2))
        selected_year = st.selectbox(
            "Select Year",
            year_options,
            index=year_options.index(st.session_state.selected_year) if st.session_state.selected_year in year_options else 0
        )
        st.session_state.selected_year = selected_year

        st.markdown("---")

    # Load data based on filters
    df_filtered = get_filtered_data(sheet_name, subcategory_filter)
    if df_filtered.empty:
        st.error("No data available for the selected filters. Please check your data sources or select a different program.")
        st.stop()

    # Load records for progress summary
    records = load_expert_plan_records(
        sheet_name if sheet_name != "All" else None,
        selected_quarter if selected_quarter != "All" else None,
        selected_year if selected_year != "All" else None
    )

    # Display Progress Status Summary - Latest quarter only with program-specific name
    if records:
        df_records = pd.DataFrame(records)
        if 'Status' in df_records.columns and 'Quarter' in df_records.columns and 'Year' in df_records.columns:
            # Filter to latest quarter only
            quarter_order = {'Q1': 1, 'Q2': 2, 'Q3': 3, 'Q4': 4}
            df_records['Quarter_Sort'] = df_records['Year'].astype(str) + df_records['Quarter'].map(quarter_order).astype(str)
            latest_quarter_val = df_records.loc[df_records['Quarter_Sort'].idxmax()]['Quarter']
            latest_year_val = df_records.loc[df_records['Quarter_Sort'].idxmax()]['Year']

            df_records = df_records[(df_records['Quarter'] == latest_quarter_val) & (df_records['Year'] == latest_year_val)]

            total = len(df_records)
            completed = len(df_records[df_records['Status'] == 'Completed'])
            ongoing = len(df_records[df_records['Status'] == 'Ongoing'])
            pending = len(df_records[df_records['Status'] == 'Pending'])
            initiated = len(df_records[df_records['Status'] == 'Initiated'])

            # Program-specific title
            program_display = sheet_name if sheet_name != "All" else "All Programs"
            st.markdown(f"""
            <div class="progress-summary-container">
                <h3 class="progress-summary-title">📊 {program_display} - {latest_quarter_val} {latest_year_val} Progress Status Summary</h3>
            </div>
            """, unsafe_allow_html=True)

            col1, col2, col3, col4, col5 = st.columns(5)

            def status_card_html(label, count, status, card_class, icon, is_active=False):
                active_class = "active" if is_active else ""
                return f"""
                <div class="progress-status-card {card_class} {active_class}" data-status="{status}">
                    <div class="status-icon">{icon}</div>
                    <div class="status-number">{count}</div>
                    <div class="status-label">{label}</div>
                </div>
                """

            with col1:
                st.markdown(status_card_html("Total", total, "All", "card-total", "📋", st.session_state.selected_status == "All"), unsafe_allow_html=True)
            with col2:
                st.markdown(status_card_html("Completed", completed, "Completed", "card-completed", "✅", st.session_state.selected_status == "Completed"), unsafe_allow_html=True)
            with col3:
                st.markdown(status_card_html("Ongoing", ongoing, "Ongoing", "card-ongoing", "🔄", st.session_state.selected_status == "Ongoing"), unsafe_allow_html=True)
            with col4:
                st.markdown(status_card_html("Pending", pending, "Pending", "card-pending", "⏳", st.session_state.selected_status == "Pending"), unsafe_allow_html=True)
            with col5:
                st.markdown(status_card_html("Initiated", initiated, "Initiated", "card-initiated", "🚀", st.session_state.selected_status == "Initiated"), unsafe_allow_html=True)

            st.markdown("---")

    ordered_materials_tuple = get_program_materials(sheet_name)

    # Compute all required pivots and plans
    issue_pivot = compute_issue_pivot(ordered_materials_tuple)
    nsoh_pivot = compute_nsoh_pivot()
    consumption_pivot = compute_consumption_pivot(ordered_materials_tuple)
    deliveries_pivot = compute_new_deliveries_pivot(ordered_materials_tuple)

    def move_avg_to_end(df, avg_col):
        if not df.empty and avg_col in df.columns:
            cols = [c for c in df.columns if c != avg_col] + [avg_col]
            return df[cols]
        return df

    issue_pivot = move_avg_to_end(issue_pivot, 'A_AMC')
    nsoh_pivot = move_avg_to_end(nsoh_pivot, 'A_NSOH')
    consumption_pivot = move_avg_to_end(consumption_pivot, 'A_Consumption')
    deliveries_pivot = move_avg_to_end(deliveries_pivot, 'A_Deliveries')

    issue_pivot = order_df_by_program(issue_pivot, ordered_materials_tuple, 'Material Description')
    nsoh_pivot = order_df_by_program(nsoh_pivot, ordered_materials_tuple, 'Material Description')
    consumption_pivot = order_df_by_program(consumption_pivot, ordered_materials_tuple, 'Material Description')
    deliveries_pivot = order_df_by_program(deliveries_pivot, ordered_materials_tuple, 'Material Description')

    supply_df, supply_plan = compute_supply_plan(df_filtered)
    material_problems, action_df = compute_action_plan(df_filtered)

    # Load expert records for the selected program with quarter/year filters
    st.session_state.expert_plan_records = load_expert_plan_records(
        sheet_name if sheet_name != "All" else None,
        selected_quarter if selected_quarter != "All" else None,
        selected_year if selected_year != "All" else None
    )

    # Render tabs with order: Historical Data, Expert Action Plan, Action Plan Follow Up, System Generated Action Plan
    tab_hist, tab_expert, tab_ap, tab_supply = st.tabs([
        "📊 Historical Data",
        "📋 Expert Action Plan",
        "📈 Action Plan Follow Up",
        "📦 System Generated Action Plan"
    ])

    with tab_hist:
        st.markdown(f"## 📊 {sheet_name if sheet_name != 'All' else 'All Programs'} Historical Data")
        render_unified_historical_table(df_filtered, issue_pivot, nsoh_pivot, consumption_pivot, deliveries_pivot, ordered_materials_tuple, sheet_name)

    with tab_expert:
        st.markdown(f"## 📋 {sheet_name if sheet_name != 'All' else 'All Programs'} Expert Action Plan")
        render_expert_action_plan_with_status(df_filtered, material_problems, action_df, sheet_name, nsoh_pivot, selected_quarter, selected_year)

    with tab_ap:
        # Removed the header title from here since it's now inside render_ap_progress_follow_up
        render_ap_progress_follow_up(sheet_name, selected_quarter, selected_year, st.session_state.selected_status)

    with tab_supply:
        # Removed the header title from here since it's now inside render_supply_planning_exercise
        render_supply_planning_exercise(df_filtered, supply_df, supply_plan, ordered_materials_tuple, sheet_name, action_df)
        st.markdown("---")
        render_system_generated_action_plan(action_df, material_problems, sheet_name)

if __name__ == "__main__":
    main()
