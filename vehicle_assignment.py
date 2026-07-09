import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
from supabase import create_client
from typing import Optional, Dict, Any, List
import logging
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import time

# ===================================================
# AUTHENTICATION SETUP
# ===================================================
from auth_p import (
    setup_auth,
    get_user_email,
    get_user_metadata,
    sign_out,
    get_current_user,
    is_authenticated,
    get_all_users,
    get_pending_users,
    approve_user,
    reject_user
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===================================================
# CONSTANTS
# ===================================================
SUPABASE_URL = "https://etjfrptbjecafupbbase.supabase.co"
SUPABASE_KEY = "sb_publishable_j0JwaJAJBuJO79-xh7RkYg_PFKqLK1H"
MASTER_TABLE = "vehicle_master_data"
TXN_TABLE = "vehicle_assignments"
MAINT_TABLE = "vehicle_maintance"

# ===================================================
# EXPECTED TRIP END DATE MAPPING (Branch → Days)
# ===================================================
BRANCH_EXPECTED_DAYS = {
    "AA1": 0,
    "AA2": 0,
    "Adama": 0,
    "Arbamnch": 1,
    "Assosa": 2,
    "Bahir dar": 1,
    "Dessie": 1,
    "Dire dawa": 1,
    "Gambela": 2,
    "Gondar": 2,
    "Hawassa": 0,
    "Kebridehar": 2,
    "Jigjiga": 1,
    "Jimma": 0,
    "Mekele": 2,
    "Negeleborena": 1,
    "Nekemte": 0,
    "Semera": 1,
    "Shire": 3,
    "Bole": 0
}

# ===================================================
# CACHED RESOURCES
# ===================================================
@st.cache_resource
def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = get_supabase()

@st.cache_data(ttl=60, show_spinner=False)
def load_master():
    try:
        res = supabase.table(MASTER_TABLE).select("*").execute()
        return pd.DataFrame(res.data)
    except Exception as e:
        logger.error(f"Failed to load master data: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=60, show_spinner=False)
def load_assignments():
    try:
        res = supabase.table(TXN_TABLE).select("*").execute()
        return pd.DataFrame(res.data)
    except Exception as e:
        logger.error(f"Failed to load assignments: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=60, show_spinner=False)
def load_maintenance():
    try:
        res = supabase.table(MAINT_TABLE).select("*").execute()
        return pd.DataFrame(res.data)
    except Exception as e:
        logger.error(f"Failed to load maintenance data: {e}")
        return pd.DataFrame()

# ===================================================
# MULTI-ROLE SUPPORT (cached)
# ===================================================
@st.cache_data(ttl=60, show_spinner=False)
def get_user_roles_cached(email):
    if not email:
        return [], False, False
    try:
        res = supabase.table("users_vehicle").select("roles", "is_approved").eq("email", email).execute()
        if res.data:
            user_data = res.data[0]
            roles_raw = user_data.get('roles', [])
            if isinstance(roles_raw, str):
                roles = [r.strip() for r in roles_raw.split(',') if r.strip()]
            elif isinstance(roles_raw, list):
                roles = roles_raw
            else:
                roles = []
            is_approved = user_data.get('is_approved', 0) == 1
            is_admin = 'admin' in roles and is_approved
            return roles, is_approved, is_admin
        return [], False, False
    except Exception as e:
        logger.error(f"Error fetching user roles: {str(e)}")
        return [], False, False

# ===================================================
# AUTHENTICATION & SESSION STATE
# ===================================================
authenticated = setup_auth()
if not authenticated:
    st.stop()

if 'user_email' not in st.session_state:
    user_email = None
    try:
        user_email = get_user_email()
    except:
        pass
    if not user_email:
        user_email = st.session_state.get("user_email", None)
    if not user_email:
        try:
            current_user = get_current_user()
            if current_user and current_user.user:
                user_email = current_user.user.email
        except:
            pass
    if not user_email:
        try:
            user = supabase.auth.get_user()
            if user and user.user:
                user_email = user.user.email
        except:
            pass
    st.session_state.user_email = user_email
else:
    user_email = st.session_state.user_email

if 'user_roles_data' not in st.session_state:
    roles, approved, is_admin = get_user_roles_cached(user_email)
    st.session_state.user_roles_data = (roles, approved, is_admin)
else:
    roles, approved, is_admin = st.session_state.user_roles_data

user_roles = roles
is_approved_user = approved
is_admin_user = is_admin

user_metadata = get_user_metadata()

st.set_page_config(page_title="EPSS Fleet Dashboard", layout="wide")

# ===================================================
# CUSTOM CSS (font: Times New Roman except tables)
# ===================================================
st.markdown("""
<style>
    /* Set Times New Roman for all text except tables */
    .stApp, .stMarkdown, .stButton, .stSelectbox, .stTextInput, .stNumberInput, .stDateInput,
    .stCheckbox, .stRadio, .stMultiselect, .stSlider, .stTextArea, .stFileUploader,
    .stSidebar, .stExpander, .stTabs, .stMetric, .stAlert, .stInfo, .stSuccess, .stWarning, .stError,
    .stCaption, .stCode, .stHtml, .stDataFrame, .stTable, .stPlotlyChart,
    h1, h2, h3, h4, h5, h6, .kpi-card, .status-card, .section-header {
        font-family: 'Times New Roman', Times, serif !important;
    }
    /* Override for data tables only – keep default font */
    .dataframe, .stDataFrame, .stTable, .stDataFrame table, .stTable table,
    .stDataFrame th, .stDataFrame td, .stTable th, .stTable td {
        font-family: inherit !important;
    }
    .stApp { background-color: #ffffff !important; }
    .main { padding: 0rem 1rem; }
    h1 { color: #1E88E5 !important; }
    h2, h3, h4 { color: #1565C0 !important; }
    .kpi-header {
        font-size: 1.8rem !important;
        font-weight: 700 !important;
        padding: 0.5rem 0 0.3rem 0 !important;
        margin-bottom: 0.3rem !important;
        color: #0d47a1 !important;
        border-bottom: 4px solid #1E88E5;
        display: inline-block;
    }
    .section-header {
        background: linear-gradient(90deg, #1E88E5, #1565C0) !important;
        color: white !important;
        padding: 0.5rem 1rem;
        border-radius: 8px;
        margin: 1rem 0;
    }
    .edit-container {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 10px;
        border-left: 5px solid #1E88E5;
        margin: 1rem 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .stButton button { border-radius: 8px; font-weight: 500; transition: all 0.3s; }
    .stButton button:hover { transform: scale(1.02); box-shadow: 0 4px 8px rgba(0,0,0,0.2); }
    .dataframe { border-radius: 10px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
    .dataframe tr:hover { background-color: #f5f5f5 !important; }
    .st-emotion-cache-1y4p8pa { max-width: 100%; }
    .role-tag {
        display: inline-block;
        background: #e3f2fd;
        color: #0d47a1;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.8rem;
        font-weight: 500;
        margin: 2px 4px 2px 0;
    }
    .role-tag.admin {
        background: #ffcdd2;
        color: #b71c1c;
    }
    .role-tag.trip_manager {
        background: #c8e6c9;
        color: #1b5e20;
    }
    .role-tag.maintenance {
        background: #fff9c4;
        color: #f57f17;
    }
    .role-tag.analyst {
        background: #d1c4e9;
        color: #4a148c;
    }
    .status-card {
        background: white;
        border-radius: 10px;
        padding: 12px 16px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        text-align: center;
        flex: 1;
        min-width: 100px;
        margin: 4px;
        border-top: 4px solid #607D8B;
    }
    .status-card .count {
        font-size: 24px;
        font-weight: 700;
        line-height: 1.2;
    }
    .status-card .label {
        font-size: 12px;
        color: #666;
        font-weight: 500;
    }
    .status-card .percentage {
        font-size: 14px;
        color: #888;
    }
    .kpi-card {
        transition: all 0.2s ease;
    }
    .kpi-card:hover {
        transform: scale(1.02);
        box-shadow: 0 8px 24px rgba(0,0,0,0.2) !important;
    }
    .card-container {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 2px;
    }
</style>
""", unsafe_allow_html=True)

st.title("EPSS Fleet Management Dashboard")

# ===================================================
# SIDEBAR – SHOW ONLY PAGES USER CAN ACCESS
# ===================================================
st.sidebar.markdown("---")
st.sidebar.markdown("### 📋 Navigation")

nav_options = []
if any(role in user_roles for role in ['trip_manager', 'admin']):
    nav_options.append("📋 Trip Management")
if any(role in user_roles for role in ['analyst', 'admin']):
    nav_options.append("📊 KPIs & Analysis")
nav_options.append("👤 User Info")
if any(role in user_roles for role in ['maintenance', 'admin']):
    nav_options.append("🔧 Vehicle Maintenance")
if 'admin' in user_roles:
    nav_options.append("👑 Admin Panel")

selected_page = st.sidebar.radio("Go to", nav_options, index=0)

st.sidebar.markdown("---")
if st.sidebar.button("🔄 Refresh Data", use_container_width=True):
    load_master.clear()
    load_assignments.clear()
    load_maintenance.clear()
    st.rerun()

st.sidebar.markdown("---")
if st.sidebar.button("🚪 Sign Out", use_container_width=True):
    if sign_out():
        st.session_state.clear()
        st.rerun()
st.sidebar.markdown("---")

# ===================================================
# HELPER FUNCTIONS
# ===================================================
def combine_date_with_current_time(date_obj):
    if date_obj is None:
        return None
    now = datetime.now()
    return datetime(date_obj.year, date_obj.month, date_obj.day, now.hour, now.minute, now.second)

def format_datetime_for_db(dt):
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    return str(dt)

def parse_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except:
        return None

def get_date_from_value(value):
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            dt = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
            return dt.date()
        except:
            try:
                dt = datetime.strptime(value, '%Y-%m-%d')
                return dt.date()
            except:
                return None
    return None

def get_trip_by_id(trip_id: int):
    try:
        res = supabase.table(TXN_TABLE).select("*").eq("new_id", trip_id).execute()
        if res.data:
            return res.data[0]
        return None
    except Exception as e:
        logger.error(f"Error fetching trip: {e}")
        return None

def get_maintenance_by_id(record_id: int):
    try:
        # Use 'id' column (primary key)
        res = supabase.table(MAINT_TABLE).select("*").eq("id", record_id).execute()
        if res.data:
            return res.data[0]
        # Fallback to 'new_id' if exists
        res = supabase.table(MAINT_TABLE).select("*").eq("new_id", record_id).execute()
        if res.data:
            return res.data[0]
        return None
    except Exception as e:
        logger.error(f"Error fetching maintenance record: {e}")
        return None

def calculate_status_and_errors(record):
    def has_value(val):
        if val is None:
            return False
        if pd.isna(val):
            return False
        if isinstance(val, str) and val.strip() == '':
            return False
        return True
    assigned = record.get("assigned_date")
    loading_start = record.get("loading_starting_date")
    trip_start = record.get("trip_starting_date")
    trip_end = record.get("trip_end_date")
    has_assigned = has_value(assigned)
    has_loading_start = has_value(loading_start)
    has_trip_start = has_value(trip_start)
    has_trip_end = has_value(trip_end)
    if has_trip_end:
        return "Completed", None
    elif has_trip_start:
        return "In Transit", None
    elif has_loading_start:
        return "Loading", None
    elif has_assigned:
        return "Planned", None
    else:
        return "Planned", None

def format_days_hours(days):
    if pd.isna(days):
        return ''
    sign = '-' if days < 0 else ''
    days_abs = abs(days)
    d = int(days_abs)
    h = int(round((days_abs - d) * 24))
    if h == 24:
        d += 1
        h = 0
    return f"{sign}{d}:{h}"

def format_days_hours_display(days):
    """Format as 'X hrs (Y days)' for display."""
    if pd.isna(days):
        return ''
    sign = '-' if days < 0 else ''
    days_abs = abs(days)
    d = int(days_abs)
    h = int(round((days_abs - d) * 24))
    if h == 24:
        d += 1
        h = 0
    total_hours = d * 24 + h
    return f"{sign}{total_hours} hrs ({d} day{'s' if d != 1 else ''})"

# ===================================================
# DATA LOADING & PREPROCESSING (ONCE PER RERUN)
# ===================================================
@st.cache_data(ttl=60, show_spinner=False)
def process_vehicle_data(df):
    if df.empty:
        return {
            'plate_numbers': [],
            'from_locations': [],
            'branches': [],
            'plate_to_driver': {},
            'plate_to_location': {},
            'plate_to_branch': {},
            'plate_to_phone': {},
            'plate_to_vehicle_type': {}
        }
    df.columns = df.columns.str.strip()
    plate_numbers = sorted(df["plate_number"].dropna().unique().tolist())
    from_locations = sorted(df["from_location"].dropna().unique().tolist())
    branches = sorted(df["assigned_branch_name"].dropna().unique().tolist())

    plate_to_driver = {}
    plate_to_location = {}
    plate_to_branch = {}
    plate_to_phone = {}
    plate_to_vehicle_type = {}

    for _, row in df.iterrows():
        plate = row.get('plate_number')
        if plate:
            plate_to_driver[plate] = row.get('driver_name', '')
            plate_to_location[plate] = row.get('from_location', '')
            plate_to_branch[plate] = row.get('assigned_branch_name', '')
            plate_to_phone[plate] = row.get('phone_number', '')
            plate_to_vehicle_type[plate] = row.get('vehicle_type', '')

    return {
        'plate_numbers': plate_numbers,
        'from_locations': from_locations,
        'branches': branches,
        'plate_to_driver': plate_to_driver,
        'plate_to_location': plate_to_location,
        'plate_to_branch': plate_to_branch,
        'plate_to_phone': plate_to_phone,
        'plate_to_vehicle_type': plate_to_vehicle_type
    }

def get_available_vehicles(master_df, assignments_df, maintenance_df):
    if master_df.empty:
        return []
    all_plates = set(master_df['plate_number'].dropna().unique())
    active_plates = set()
    if not assignments_df.empty and 'status' in assignments_df.columns:
        active_statuses = ['Planned', 'Loading', 'In Transit']
        active = assignments_df[assignments_df['status'].isin(active_statuses)]
        active_plates = set(active['plate_number'].dropna().unique())
    maint_plates = set()
    if not maintenance_df.empty and 'plate_number' in maintenance_df.columns:
        under_maint = maintenance_df[
            maintenance_df['back_to_duty'].astype(str).str.strip().str.lower() == 'no'
        ]
        maint_plates = set(under_maint['plate_number'].dropna().unique())
    available_plates = all_plates - active_plates - maint_plates
    last_end_date = {}
    if not assignments_df.empty:
        trips = assignments_df[assignments_df['plate_number'].isin(available_plates)]
        if not trips.empty and 'trip_end_date' in trips.columns:
            last_end = trips.groupby('plate_number')['trip_end_date'].max()
            last_end_date = last_end.to_dict()
    sorted_plates = sorted(
        available_plates,
        key=lambda p: (last_end_date.get(p) is None, last_end_date.get(p) or datetime.min)
    )
    return sorted_plates

# Load data once per rerun
master_df = load_master()
assignments_df = load_assignments()
maintenance_df = load_maintenance()

if not assignments_df.empty:
    assignments_df.columns = assignments_df.columns.str.strip()
    date_cols = [
        'assigned_date', 'requested_date', 'loading_starting_date', 'loading_date_end',
        'trip_starting_date', 'arrival_date', 'return_date', 'trip_end_date',
        'expected_arrival_date', 'expected_trip_end_date',
        'created_at', 'deleted_at'
    ]
    for col in date_cols:
        if col in assignments_df.columns:
            assignments_df[col] = pd.to_datetime(assignments_df[col], errors='coerce')
    if 'is_deleted' not in assignments_df.columns:
        assignments_df['is_deleted'] = False

    # Compute expected arrival date and expected trip end date based on new logic
    # Get transit days from branch mapping
    assignments_df['_transit_days'] = assignments_df['assigned_branch_name'].str.strip().map(BRANCH_EXPECTED_DAYS)

    # Expected Arrival Date = trip_start + transit_days
    if 'trip_starting_date' in assignments_df.columns:
        assignments_df['expected_arrival_date'] = pd.NaT
        mask = assignments_df['trip_starting_date'].notna() & assignments_df['_transit_days'].notna()
        assignments_df.loc[mask, 'expected_arrival_date'] = (
            assignments_df.loc[mask, 'trip_starting_date'] +
            pd.to_timedelta(assignments_df.loc[mask, '_transit_days'], unit='D')
        )
    else:
        assignments_df['expected_arrival_date'] = pd.NaT

    # Expected Trip End Date = trip_start + 2 * transit_days
    if 'trip_starting_date' in assignments_df.columns:
        assignments_df['expected_trip_end_date'] = pd.NaT
        mask = assignments_df['trip_starting_date'].notna() & assignments_df['_transit_days'].notna()
        assignments_df.loc[mask, 'expected_trip_end_date'] = (
            assignments_df.loc[mask, 'trip_starting_date'] +
            pd.to_timedelta(assignments_df.loc[mask, '_transit_days'] * 2, unit='D')
        )
    else:
        assignments_df['expected_trip_end_date'] = pd.NaT

    # On-Time Delivery Time (Days) = arrival_date - expected_arrival_date
    if 'arrival_date' in assignments_df.columns and 'expected_arrival_date' in assignments_df.columns:
        assignments_df['on_time_delivery_days'] = (
            (assignments_df['arrival_date'] - assignments_df['expected_arrival_date']).dt.days
        )
    else:
        assignments_df['on_time_delivery_days'] = None

    # Trip Variance (Days) = trip_end_date - expected_trip_end_date
    if 'trip_end_date' in assignments_df.columns and 'expected_trip_end_date' in assignments_df.columns:
        assignments_df['trip_variance_days'] = (
            (assignments_df['trip_end_date'] - assignments_df['expected_trip_end_date']).dt.days
        )
    else:
        assignments_df['trip_variance_days'] = None

    # ---- NEW: Delivery Status and Trip Status ----
    def get_delivery_status(row):
        days = row.get('on_time_delivery_days')
        if pd.isna(days):
            return None
        if days < 0:
            return 'Earlier'
        elif days == 0:
            return 'Ontime'
        else:
            return 'Later'

    def get_trip_status(row):
        days = row.get('trip_variance_days')
        if pd.isna(days):
            return None
        if days < 0:
            return 'Early Return'
        elif days == 0:
            return 'On Schedule'
        else:
            return 'Delayed'

    assignments_df['delivery_status'] = assignments_df.apply(get_delivery_status, axis=1)
    assignments_df['trip_status'] = assignments_df.apply(get_trip_status, axis=1)

    # Drop temporary column
    assignments_df.drop(columns=['_transit_days'], inplace=True, errors='ignore')

    # Status function
    def status_func(row):
        if row.get('is_deleted', False):
            return 'Deleted'
        assigned = row.get('assigned_date')
        loading_start = row.get('loading_starting_date')
        trip_start = row.get('trip_starting_date')
        trip_end = row.get('trip_end_date')
        has_assigned = pd.notna(assigned)
        has_loading_start = pd.notna(loading_start)
        has_trip_start = pd.notna(trip_start)
        has_trip_end = pd.notna(trip_end)
        if has_trip_end:
            return "Completed"
        elif has_trip_start:
            return "In Transit"
        elif has_loading_start:
            return "Loading"
        elif has_assigned:
            return "Planned"
        else:
            return "Planned"
    assignments_df['status'] = assignments_df.apply(status_func, axis=1)
    mask = assignments_df['is_deleted'] == False
    def safe_days(col1, col2):
        m = mask & assignments_df[col1].notna() & assignments_df[col2].notna()
        if m.any():
            return (assignments_df.loc[m, col2] - assignments_df.loc[m, col1]).dt.total_seconds() / 86400
        else:
            return pd.Series(index=assignments_df.index, dtype=float)
    assignments_df['loading_time'] = safe_days('loading_starting_date', 'loading_date_end')
    assignments_df['ongoing_time'] = safe_days('trip_starting_date', 'arrival_date')
    assignments_df['incoming_time'] = safe_days('return_date', 'trip_end_date')
    assignments_df['total_trip_time'] = safe_days('trip_starting_date', 'trip_end_date')
    assignments_df['idle_assigned_to_loading'] = safe_days('assigned_date', 'loading_starting_date')
    assignments_df['idle_loading_to_trip'] = safe_days('loading_date_end', 'trip_starting_date')
    assignments_df['idle_assigned_to_end'] = safe_days('assigned_date', 'trip_end_date')
    assignments_df['total_idle'] = assignments_df[['idle_assigned_to_loading', 'idle_loading_to_trip', 'idle_assigned_to_end']].sum(axis=1, skipna=True)

if not maintenance_df.empty:
    if 'is_deleted' not in maintenance_df.columns:
        maintenance_df['is_deleted'] = False
    if 'deleted_at' not in maintenance_df.columns:
        maintenance_df['deleted_at'] = None

def compute_vehicle_kpis(master_df, assignments_df, maintenance_df):
    all_vehicles = set(master_df['plate_number'].dropna().unique()) if not master_df.empty else set()
    total_vehicles = len(all_vehicles)
    active_assignments = assignments_df[assignments_df['is_deleted'] == False] if not assignments_df.empty else pd.DataFrame()
    active_maintenance = maintenance_df[maintenance_df['is_deleted'] == False] if not maintenance_df.empty else pd.DataFrame()
    assigned_plates = set()
    if not active_assignments.empty and 'status' in active_assignments.columns:
        active_statuses = ['Planned', 'Loading', 'In Transit']
        latest_trips = active_assignments.sort_values('assigned_date', ascending=False).drop_duplicates('plate_number')
        assigned_plates = set(latest_trips[latest_trips['status'].isin(active_statuses)]['plate_number'].dropna().unique())
    assigned_count = len(assigned_plates)
    under_maint_plates = set()
    if not active_maintenance.empty and 'plate_number' in active_maintenance.columns:
        under_maint_df = active_maintenance[active_maintenance['back_to_duty'].astype(str).str.strip().str.lower() == 'no']
        under_maint_plates = set(under_maint_df['plate_number'].dropna().unique())
    under_maint_count = len(under_maint_plates)
    available_plates = all_vehicles - assigned_plates - under_maint_plates
    available_count = len(available_plates)

    active_plates = assigned_plates | available_plates
    active_count = len(active_plates)

    utilization_rate = (assigned_count / active_count * 100) if active_count > 0 else 0
    fleet_performance = (assigned_count / total_vehicles * 100) if total_vehicles > 0 else 0
    availability_rate = (available_count / total_vehicles * 100) if total_vehicles > 0 else 0
    downtime_rate = (under_maint_count / total_vehicles * 100) if total_vehicles > 0 else 0

    return {
        'total_vehicles': total_vehicles,
        'assigned_count': assigned_count,
        'under_maint_count': under_maint_count,
        'available_count': available_count,
        'active_count': active_count,
        'assigned_plates': assigned_plates,
        'under_maint_plates': under_maint_plates,
        'available_plates': available_plates,
        'active_plates': active_plates,
        'all_vehicles': all_vehicles,
        'utilization_rate': utilization_rate,
        'fleet_performance': fleet_performance,
        'availability_rate': availability_rate,
        'downtime_rate': downtime_rate
    }

kpis = compute_vehicle_kpis(master_df, assignments_df, maintenance_df)
vehicle_data = process_vehicle_data(master_df)
plate_numbers = vehicle_data['plate_numbers']
from_locations = vehicle_data['from_locations']
branches = vehicle_data['branches']
plate_to_driver = vehicle_data['plate_to_driver']
plate_to_location = vehicle_data['plate_to_location']
plate_to_branch = vehicle_data['plate_to_branch']
plate_to_phone = vehicle_data['plate_to_phone']
plate_to_vehicle_type = vehicle_data['plate_to_vehicle_type']

# ===================================================
# ADMIN USER MANAGEMENT (unchanged)
# ===================================================
def admin_user_management():
    st.subheader("👥 Manage Users")
    try:
        res = supabase.table("users_vehicle").select("email", "full_name", "roles", "is_approved").execute()
        users = pd.DataFrame(res.data) if res.data else pd.DataFrame()
    except Exception as e:
        st.error(f"Error loading users: {e}")
        return
    if users.empty:
        st.info("No users found.")
        return
    pending = users[users['is_approved'] == 0]
    approved = users[users['is_approved'] == 1]
    st.markdown("### ⏳ Pending Approvals")
    if pending.empty:
        st.info("No pending users.")
    else:
        for idx, row in pending.iterrows():
            email = row['email']
            full_name = row.get('full_name', 'N/A')
            with st.expander(f"{full_name} ({email})"):
                col1, col2 = st.columns([3, 1])
                with col1:
                    role_options = ['trip_manager', 'maintenance', 'analyst', 'admin']
                    selected_roles = []
                    cols = st.columns(len(role_options))
                    for i, role in enumerate(role_options):
                        with cols[i]:
                            if st.checkbox(role.replace('_', ' ').title(), key=f"role_{email}_{role}"):
                                selected_roles.append(role)
                    st.caption("Select one or more roles for this user.")
                with col2:
                    if st.button("✅ Approve", key=f"approve_{email}"):
                        if not selected_roles:
                            st.error("Please select at least one role.")
                        else:
                            try:
                                supabase.table("users_vehicle").update({
                                    "roles": selected_roles,
                                    "is_approved": 1
                                }).eq("email", email).execute()
                                st.success(f"User {email} approved with roles: {', '.join(selected_roles)}")
                                get_user_roles_cached.clear()
                                st.rerun()
                            except Exception as e:
                                st.error(f"Approval failed: {e}")
                    if st.button("❌ Reject", key=f"reject_{email}"):
                        try:
                            supabase.table("users_vehicle").delete().eq("email", email).execute()
                            st.success(f"User {email} rejected and removed.")
                            get_user_roles_cached.clear()
                            st.rerun()
                        except Exception as e:
                            st.error(f"Rejection failed: {e}")
    st.markdown("---")
    st.markdown("### ✅ Approved Users")
    if approved.empty:
        st.info("No approved users yet.")
    else:
        display_data = approved[['email', 'full_name', 'roles']].copy()
        display_data['roles_display'] = display_data['roles'].apply(
            lambda r: ', '.join([role.replace('_', ' ').title() for role in r]) if isinstance(r, list) else r
        )
        st.dataframe(
            display_data[['email', 'full_name', 'roles_display']],
            column_config={
                "email": "Email",
                "full_name": "Full Name",
                "roles_display": "Roles",
            },
            use_container_width=True,
            hide_index=True
        )
        if 'edit_user_email' not in st.session_state:
            st.session_state.edit_user_email = None
        col_edit_select, col_edit_btn = st.columns([3, 1])
        with col_edit_select:
            user_to_edit = st.selectbox(
                "Select a user to edit roles",
                options=approved['email'].tolist(),
                format_func=lambda x: f"{approved[approved['email']==x]['full_name'].iloc[0]} ({x})",
                key="edit_user_select"
            )
        with col_edit_btn:
            if st.button("✏️ Edit Roles", use_container_width=True):
                st.session_state.edit_user_email = user_to_edit
                st.rerun()
        if st.session_state.edit_user_email:
            email = st.session_state.edit_user_email
            user_row = approved[approved['email'] == email].iloc[0]
            current_roles = user_row['roles']
            if isinstance(current_roles, str):
                current_roles = [r.strip() for r in current_roles.split(',') if r.strip()]
            elif not isinstance(current_roles, list):
                current_roles = []
            st.markdown(f"#### Edit Roles for **{user_row['full_name']}** ({email})")
            col_roles = st.columns(4)
            new_roles = []
            role_options = ['trip_manager', 'maintenance', 'analyst', 'admin']
            for i, role in enumerate(role_options):
                with col_roles[i]:
                    checked = st.checkbox(
                        role.replace('_', ' ').title(),
                        value=(role in current_roles),
                        key=f"edit_role_{email}_{role}"
                    )
                    if checked:
                        new_roles.append(role)
            col_save, col_cancel = st.columns(2)
            with col_save:
                if st.button("💾 Save Roles", key=f"save_roles_{email}", use_container_width=True):
                    if not new_roles:
                        st.warning("User must have at least one role.")
                    else:
                        try:
                            supabase.table("users_vehicle").update({
                                "roles": new_roles
                            }).eq("email", email).execute()
                            st.success(f"Roles updated for {email}")
                            get_user_roles_cached.clear()
                            st.session_state.edit_user_email = None
                            st.rerun()
                        except Exception as e:
                            st.error(f"Update failed: {e}")
            with col_cancel:
                if st.button("❌ Cancel", key=f"cancel_edit_{email}", use_container_width=True):
                    st.session_state.edit_user_email = None
                    st.rerun()

# ===================================================
# VEHICLE MASTER DATA MANAGEMENT (unchanged)
# ===================================================
def manage_vehicle_master(master_df):
    st.markdown("### 🚗 Manage Vehicle Master Data")
    if 'edit_vehicle_id' not in st.session_state:
        st.session_state.edit_vehicle_id = None
    if 'edit_vehicle_data' not in st.session_state:
        st.session_state.edit_vehicle_data = None
    with st.expander("➕ Add New Vehicle", expanded=False):
        with st.form("add_vehicle_form"):
            col1, col2 = st.columns(2)
            with col1:
                new_plate = st.text_input("Plate Number *", placeholder="e.g., AA-1234")
                new_driver = st.text_input("Driver Name", placeholder="Full name")
            with col2:
                new_phone = st.text_input("Phone Number", placeholder="09xxxxxxxx")
                new_vehicle_type = st.text_input("Vehicle Type", placeholder="e.g., Truck, Bus")
            submitted = st.form_submit_button("💾 Add Vehicle", type="primary")
            if submitted:
                if not new_plate:
                    st.error("Plate Number is required.")
                else:
                    existing = supabase.table(MASTER_TABLE).select("plate_number").eq("plate_number", new_plate).execute()
                    if existing.data:
                        st.error(f"❌ Plate number '{new_plate}' already exists.")
                    else:
                        try:
                            supabase.table(MASTER_TABLE).insert({
                                "plate_number": new_plate,
                                "driver_name": new_driver or None,
                                "phone_number": new_phone or None,
                                "vehicle_type": new_vehicle_type or None
                            }).execute()
                            st.success("✅ Vehicle added successfully!")
                            load_master.clear()
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Error: {str(e)}")
    if master_df.empty:
        st.info("No vehicle master data available.")
        return
    required_cols = ['plate_number', 'driver_name', 'phone_number', 'vehicle_type']
    for col in required_cols:
        if col not in master_df.columns:
            master_df[col] = None
    display_df = master_df[required_cols].copy()
    display_df.columns = ['Plate Number', 'Driver Name', 'Phone', 'Vehicle Type']
    st.subheader("📋 Current Vehicle Records")
    st.dataframe(display_df, use_container_width=True, hide_index=True)
    st.markdown("---")
    col_sel1, col_sel2, col_sel3 = st.columns([2, 1, 1])
    with col_sel1:
        vehicle_options = master_df['plate_number'].dropna().unique().tolist()
        if vehicle_options:
            selected_plate = st.selectbox(
                "Select a vehicle to edit or delete",
                options=vehicle_options,
                key="vehicle_action_select"
            )
        else:
            selected_plate = None
            st.info("No vehicles to select.")
    with col_sel2:
        if st.button("✏️ Edit Selected", use_container_width=True):
            if selected_plate:
                st.session_state.edit_vehicle_id = selected_plate
                row = master_df[master_df['plate_number'] == selected_plate].iloc[0]
                st.session_state.edit_vehicle_data = row.to_dict()
                st.rerun()
            else:
                st.warning("Please select a vehicle first.")
    with col_sel3:
        if st.button("🗑️ Delete Selected", use_container_width=True):
            if selected_plate:
                st.warning(f"Are you sure you want to delete vehicle '{selected_plate}'? This cannot be undone.")
                col_confirm1, col_confirm2 = st.columns(2)
                with col_confirm1:
                    if st.button("✅ Yes, Delete", key="confirm_delete_vehicle"):
                        try:
                            supabase.table(MASTER_TABLE).delete().eq("plate_number", selected_plate).execute()
                            st.success(f"✅ Vehicle '{selected_plate}' deleted successfully!")
                            st.session_state.edit_vehicle_id = None
                            st.session_state.edit_vehicle_data = None
                            load_master.clear()
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Delete failed: {str(e)}")
                with col_confirm2:
                    if st.button("❌ Cancel", key="cancel_delete_vehicle"):
                        st.rerun()
            else:
                st.warning("Please select a vehicle first.")
    if st.session_state.edit_vehicle_id and st.session_state.edit_vehicle_data:
        st.markdown("---")
        st.markdown(f"### ✏️ Edit Vehicle - {st.session_state.edit_vehicle_id}")
        edit_data = st.session_state.edit_vehicle_data
        with st.form("edit_vehicle_form"):
            col1, col2 = st.columns(2)
            with col1:
                new_plate = st.text_input("Plate Number *", value=edit_data.get('plate_number', ''))
                new_driver = st.text_input("Driver Name", value=edit_data.get('driver_name', ''))
            with col2:
                new_phone = st.text_input("Phone Number", value=edit_data.get('phone_number', ''))
                new_vehicle_type = st.text_input("Vehicle Type", value=edit_data.get('vehicle_type', ''))
            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                update_clicked = st.form_submit_button("🔄 Update Vehicle", type="primary")
            with col_btn2:
                cancel_clicked = st.form_submit_button("❌ Cancel Edit")
        if cancel_clicked:
            st.session_state.edit_vehicle_id = None
            st.session_state.edit_vehicle_data = None
            st.rerun()
        if update_clicked:
            if not new_plate:
                st.error("Plate Number is required.")
            else:
                original_plate = edit_data.get('plate_number')
                if new_plate != original_plate:
                    existing = supabase.table(MASTER_TABLE).select("plate_number").eq("plate_number", new_plate).execute()
                    if existing.data:
                        st.error(f"❌ Plate number '{new_plate}' already exists.")
                        st.stop()
                try:
                    supabase.table(MASTER_TABLE).update({
                        "plate_number": new_plate,
                        "driver_name": new_driver or None,
                        "phone_number": new_phone or None,
                        "vehicle_type": new_vehicle_type or None
                    }).eq("plate_number", original_plate).execute()
                    st.success("✅ Vehicle updated successfully!")
                    st.session_state.edit_vehicle_id = None
                    st.session_state.edit_vehicle_data = None
                    load_master.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Update failed: {str(e)}")

# ===================================================
# VEHICLE MAINTENANCE (UPDATED with two-dropdown design)
# ===================================================
def view_vehicle_maintenance(master_df, assignments_df, maintenance_df):
    # ---- Session state ----
    if 'show_add_maint' not in st.session_state:
        st.session_state.show_add_maint = False
    if 'show_edit_maint' not in st.session_state:
        st.session_state.show_edit_maint = False
    if 'edit_maint_id' not in st.session_state:
        st.session_state.edit_maint_id = None
    if 'edit_maint_data' not in st.session_state:
        st.session_state.edit_maint_data = None
    if 'show_delete_confirmation' not in st.session_state:
        st.session_state.show_delete_confirmation = False

    # ----- Section header -----
    st.markdown(
        '<div class="section-header">🚗 Vehicle Maintenance</div>',
        unsafe_allow_html=True
    )

    # ----- TOP ROW: Add New and Edit/Delete buttons -----
    col_top1, col_top2, col_top3 = st.columns([1, 1, 2])
    with col_top1:
        if not st.session_state.show_add_maint:
            if st.button("➕ Add New Maintenance Record", type="primary", use_container_width=True):
                st.session_state.show_add_maint = True
                st.session_state.add_form_key += 1
                if st.session_state.show_edit_maint:
                    st.session_state.show_edit_maint = False
                    st.session_state.edit_maint_id = None
                    st.session_state.edit_maint_data = None
                st.rerun()
    with col_top2:
        if not st.session_state.show_edit_maint:
            if st.button("📝 Edit or Delete Maintenance Record", type="secondary", use_container_width=True):
                st.session_state.show_edit_maint = True
                if st.session_state.show_add_maint:
                    st.session_state.show_add_maint = False
                st.session_state.edit_maint_id = None
                st.session_state.edit_maint_data = None
                st.rerun()
    with col_top3:
        st.empty()

    st.markdown("---")
    st.write("")

    # ----- ADD NEW MAINTENANCE RECORD FORM -----
    if st.session_state.show_add_maint:
        st.markdown("### ➕ Add New Maintenance Record")

        # Plate selection (outside form)
        plate_options_master = sorted(master_df['plate_number'].dropna().astype(str).str.strip().unique().tolist()) if not master_df.empty else []
        plate_options = ["Select Plate Number"] + plate_options_master
        selected_plate = st.selectbox(
            "Plate Number *",
            options=plate_options,
            key="maint_add_plate_select",
            help="Select the vehicle that requires maintenance."
        )

        # Derive vehicle type from master
        vehicle_type = ""
        if selected_plate != "Select Plate Number" and not master_df.empty:
            row = master_df[master_df['plate_number'].astype(str).str.strip() == selected_plate.strip()]
            if not row.empty:
                vehicle_type = row.iloc[0].get('vehicle_type', '')

        col_info1, col_info2, col_info3 = st.columns(3)
        with col_info1:
            st.text_input("Vehicle Type", value=vehicle_type, disabled=True)
        with col_info2:
            # We can display driver name if needed, but not in maintenance table
            st.text_input("Driver", value="", disabled=True)
        with col_info3:
            st.text_input("Phone", value="", disabled=True)

        # Branch selection (outside form)
        branch_options = ["Select Branch"] + sorted(assignments_df['assigned_branch_name'].dropna().astype(str).str.strip().unique().tolist()) if not assignments_df.empty else ["Select Branch"]
        selected_branch = st.selectbox(
            "Branch *",
            options=branch_options,
            key="maint_add_branch_select"
        )

        # Workstation selection (from master)
        workstation_values = []
        if not master_df.empty and 'workstation' in master_df.columns:
            workstation_values = sorted(master_df['workstation'].dropna().astype(str).str.strip().unique().tolist())
        workstation_options = ["Select Workstation"] + workstation_values
        selected_workstation = st.selectbox(
            "Workstation",
            options=workstation_options,
            key="maint_add_workstation"
        )

        # Main form
        with st.form(key="maint_add_form"):
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                request_date = st.date_input("Request Date *", value=None, key="maint_add_request_date")
                maint_type = st.selectbox(
                    "Maintenance Type *",
                    options=["Select Maintenance Type", "scheduled", "corrective", "preventive"],
                    index=0,
                    key="maint_add_type"
                )
                responsible = st.text_input("Responsible Body *", placeholder="Enter name", key="maint_add_responsible")

            with col2:
                start_date = st.date_input("Start Date *", value=None, key="maint_add_start")
                end_date = st.date_input("End Date", value=None, key="maint_add_end")
                cost = st.text_input("Cost", placeholder="e.g., 1500", key="maint_add_cost")

            with col3:
                back_to_duty = st.selectbox(
                    "Back to Duty",
                    options=["Select Duty Status", "Yes", "No"],
                    index=0,
                    key="maint_add_back"
                )
                remark = st.text_area("Remark", key="maint_add_remark", height=68)

            with col4:
                # Auto-calculate total days
                if start_date:
                    if back_to_duty == "No":
                        total_days = (date.today() - start_date).days
                    elif back_to_duty == "Yes" and end_date:
                        total_days = (end_date - start_date).days
                    else:
                        total_days = 0
                else:
                    total_days = 0
                st.number_input("Total Days (auto-calculated)", value=total_days, disabled=True, key="maint_add_total_days")
                st.empty()  # placeholder for alignment

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                save_clicked = st.form_submit_button("💾 Save Record", type="primary", use_container_width=True)
            with col_btn2:
                cancel_clicked = st.form_submit_button("❌ Cancel", use_container_width=True)

            if save_clicked:
                errors = []
                if not selected_plate or selected_plate == "Select Plate Number":
                    errors.append("Please select a valid Plate Number.")
                if not selected_branch or selected_branch == "Select Branch":
                    errors.append("Please select a Branch.")
                if not request_date:
                    errors.append("Request Date is required.")
                if not start_date:
                    errors.append("Start Date is required.")
                if not maint_type or maint_type == "Select Maintenance Type":
                    errors.append("Please select a Maintenance Type.")
                if back_to_duty == "Select Duty Status":
                    errors.append("Please select Back to Duty status.")
                if start_date and end_date and start_date > end_date:
                    errors.append("Start Date must be before End Date.")
                if errors:
                    for err in errors:
                        st.error(f"❌ {err}")
                else:
                    if back_to_duty == "No":
                        final_total_days = (date.today() - start_date).days
                    else:
                        if end_date:
                            final_total_days = (end_date - start_date).days
                        else:
                            final_total_days = 0

                    data = {
                        "plate_number": selected_plate,
                        "vehicle_type": vehicle_type,
                        "maintenace_type": maint_type,
                        "branch": selected_branch,
                        "maintenance_workstation": selected_workstation if selected_workstation != "Select Workstation" else None,
                        "responsible_person": responsible,
                        "maintenance_request_date": request_date.strftime('%Y-%m-%d') if request_date else None,
                        "maintenance_starting_date": start_date.strftime('%Y-%m-%d') if start_date else None,
                        "maintenance_ending_date": end_date.strftime('%Y-%m-%d') if end_date else None,
                        "maintenance_total_day": final_total_days,
                        "maintenace_cost": cost if cost else None,
                        "reason": remark if remark else None,
                        "back_to_duty": back_to_duty,
                        "created_at": datetime.now().isoformat(),
                        "is_deleted": False,
                        "deleted_at": None
                    }
                    try:
                        res = supabase.table(MAINT_TABLE).insert(data).execute()
                        if res.data:
                            st.success("✅ Maintenance record saved successfully!")
                            st.session_state.show_add_maint = False
                            load_maintenance.clear()
                            st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error saving record: {str(e)}")

            if cancel_clicked:
                st.session_state.show_add_maint = False
                st.rerun()

        st.markdown("---")
        st.write("")

    # ----- EDIT / DELETE MAINTENANCE RECORD FORM -----
    if st.session_state.show_edit_maint:
        st.markdown("### 📝 Edit or Delete Maintenance Record")

        # Build list of active maintenance records (all, not just active statuses)
        active_maint = maintenance_df[maintenance_df['is_deleted'] == False] if not maintenance_df.empty else pd.DataFrame()
        record_options = [("", "Select Maintenance Record")]
        if not active_maint.empty:
            for idx, row in active_maint.iterrows():
                rec_id = row['id']
                label = f"{row['plate_number']} - {row['maintenace_type']} ({row['maintenance_request_date']})"
                record_options.append((str(rec_id), label))
            record_options.sort(key=lambda x: x[1], reverse=True)  # newest first

        selected_record_id = st.selectbox(
            "Select Maintenance Record",
            options=[opt[0] for opt in record_options],
            format_func=lambda x: next((opt[1] for opt in record_options if opt[0] == x), "Select Maintenance Record"),
            key="maint_edit_record_select",
            label_visibility="collapsed"
        )
        st.caption("Choose a maintenance record from the list below to edit or delete it.")

        if selected_record_id:
            # Load record data if not loaded or changed
            if st.session_state.edit_maint_id != selected_record_id:
                record_data = get_maintenance_by_id(selected_record_id)
                if record_data:
                    st.session_state.edit_maint_data = record_data
                    st.session_state.edit_maint_id = selected_record_id
                else:
                    st.error("Could not load maintenance record.")
                    st.session_state.edit_maint_data = None
                    st.session_state.edit_maint_id = None

            if st.session_state.edit_maint_data:
                edit_data = st.session_state.edit_maint_data
                plate_display = edit_data.get('plate_number', 'Unknown')

                st.markdown('<div class="edit-container">', unsafe_allow_html=True)
                st.markdown(f"### ✏️ Edit Maintenance Record – {plate_display}")

                # Pre-fill values
                current_plate = edit_data.get('plate_number', '')
                current_branch = edit_data.get('branch', '')
                current_workstation = edit_data.get('maintenance_workstation', '')
                current_request_date = get_date_from_value(edit_data.get('maintenance_request_date'))
                current_start = get_date_from_value(edit_data.get('maintenance_starting_date'))
                current_end = get_date_from_value(edit_data.get('maintenance_ending_date'))
                current_type = edit_data.get('maintenace_type', '')
                current_responsible = edit_data.get('responsible_person', '')
                current_cost = edit_data.get('maintenace_cost', '')
                current_remark = edit_data.get('reason', '')
                current_back = edit_data.get('back_to_duty', '')
                current_total_days = edit_data.get('maintenance_total_day', 0)

                # Plate selection (outside form)
                plate_options_master = sorted(master_df['plate_number'].dropna().astype(str).str.strip().unique().tolist()) if not master_df.empty else []
                plate_options = ["Select Plate Number"] + plate_options_master
                plate_edit = st.selectbox(
                    "Plate Number *",
                    options=plate_options,
                    index=plate_options.index(current_plate) if current_plate in plate_options else 0,
                    key="maint_edit_plate_select"
                )
                # Derive vehicle type
                vehicle_type_edit = ""
                if plate_edit != "Select Plate Number" and not master_df.empty:
                    row = master_df[master_df['plate_number'].astype(str).str.strip() == plate_edit.strip()]
                    if not row.empty:
                        vehicle_type_edit = row.iloc[0].get('vehicle_type', '')

                col_info1, col_info2, col_info3 = st.columns(3)
                with col_info1:
                    st.text_input("Vehicle Type", value=vehicle_type_edit, disabled=True)
                with col_info2:
                    st.text_input("Driver", value="", disabled=True)
                with col_info3:
                    st.text_input("Phone", value="", disabled=True)

                # Branch selection (outside form)
                branch_options = ["Select Branch"] + sorted(assignments_df['assigned_branch_name'].dropna().astype(str).str.strip().unique().tolist()) if not assignments_df.empty else ["Select Branch"]
                branch_edit = st.selectbox(
                    "Branch *",
                    options=branch_options,
                    index=branch_options.index(current_branch) if current_branch in branch_options else 0,
                    key="maint_edit_branch_select"
                )

                # Workstation selection
                workstation_values = []
                if not master_df.empty and 'workstation' in master_df.columns:
                    workstation_values = sorted(master_df['workstation'].dropna().astype(str).str.strip().unique().tolist())
                workstation_options = ["Select Workstation"] + workstation_values
                workstation_edit = st.selectbox(
                    "Workstation",
                    options=workstation_options,
                    index=workstation_options.index(current_workstation) if current_workstation in workstation_options else 0,
                    key="maint_edit_workstation"
                )

                # Main edit form
                with st.form(key="maint_edit_form"):
                    col1, col2, col3, col4 = st.columns(4)

                    with col1:
                        request_date_edit = st.date_input(
                            "Request Date *",
                            value=current_request_date,
                            key="maint_edit_request_date"
                        )
                        maint_type_edit = st.selectbox(
                            "Maintenance Type *",
                            options=["Select Maintenance Type", "scheduled", "corrective", "preventive"],
                            index=["Select Maintenance Type", "scheduled", "corrective", "preventive"].index(current_type) if current_type in ["scheduled", "corrective", "preventive"] else 0,
                            key="maint_edit_type"
                        )
                        responsible_edit = st.text_input(
                            "Responsible Body *",
                            value=current_responsible,
                            key="maint_edit_responsible"
                        )

                    with col2:
                        start_date_edit = st.date_input(
                            "Start Date *",
                            value=current_start,
                            key="maint_edit_start"
                        )
                        end_date_edit = st.date_input(
                            "End Date",
                            value=current_end,
                            key="maint_edit_end"
                        )
                        cost_edit = st.text_input(
                            "Cost",
                            value=current_cost,
                            key="maint_edit_cost"
                        )

                    with col3:
                        back_to_duty_edit = st.selectbox(
                            "Back to Duty",
                            options=["Select Duty Status", "Yes", "No"],
                            index=["Select Duty Status", "Yes", "No"].index(current_back) if current_back in ["Yes", "No"] else 0,
                            key="maint_edit_back"
                        )
                        remark_edit = st.text_area(
                            "Remark",
                            value=current_remark,
                            key="maint_edit_remark",
                            height=68
                        )

                    with col4:
                        # Auto-calculate total days
                        if start_date_edit:
                            if back_to_duty_edit == "No":
                                total_days_edit = (date.today() - start_date_edit).days
                            elif back_to_duty_edit == "Yes" and end_date_edit:
                                total_days_edit = (end_date_edit - start_date_edit).days
                            else:
                                total_days_edit = 0
                        else:
                            total_days_edit = 0
                        st.number_input("Total Days (auto-calculated)", value=total_days_edit, disabled=True, key="maint_edit_total_days")
                        st.empty()  # placeholder

                    col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 1])
                    with col_btn1:
                        update_clicked = st.form_submit_button("🔄 Update Record", type="primary", use_container_width=True)
                    with col_btn2:
                        delete_clicked = st.form_submit_button("🗑️ Delete Record", use_container_width=True)
                    with col_btn3:
                        cancel_clicked = st.form_submit_button("❌ Cancel", use_container_width=True)

                    if update_clicked:
                        errors = []
                        if not plate_edit or plate_edit == "Select Plate Number":
                            errors.append("Please select a valid Plate Number.")
                        if not branch_edit or branch_edit == "Select Branch":
                            errors.append("Please select a Branch.")
                        if not request_date_edit:
                            errors.append("Request Date is required.")
                        if not start_date_edit:
                            errors.append("Start Date is required.")
                        if not maint_type_edit or maint_type_edit == "Select Maintenance Type":
                            errors.append("Please select a Maintenance Type.")
                        if back_to_duty_edit == "Select Duty Status":
                            errors.append("Please select Back to Duty status.")
                        if start_date_edit and end_date_edit and start_date_edit > end_date_edit:
                            errors.append("Start Date must be before End Date.")
                        if errors:
                            for err in errors:
                                st.error(f"❌ {err}")
                        else:
                            if back_to_duty_edit == "No":
                                final_total_days = (date.today() - start_date_edit).days
                            else:
                                if end_date_edit:
                                    final_total_days = (end_date_edit - start_date_edit).days
                                else:
                                    final_total_days = 0

                            update_data = {
                                "plate_number": plate_edit,
                                "vehicle_type": vehicle_type_edit,
                                "maintenace_type": maint_type_edit,
                                "branch": branch_edit,
                                "maintenance_workstation": workstation_edit if workstation_edit != "Select Workstation" else None,
                                "responsible_person": responsible_edit,
                                "maintenance_request_date": request_date_edit.strftime('%Y-%m-%d') if request_date_edit else None,
                                "maintenance_starting_date": start_date_edit.strftime('%Y-%m-%d') if start_date_edit else None,
                                "maintenance_ending_date": end_date_edit.strftime('%Y-%m-%d') if end_date_edit else None,
                                "maintenance_total_day": final_total_days,
                                "maintenace_cost": cost_edit if cost_edit else None,
                                "reason": remark_edit if remark_edit else None,
                                "back_to_duty": back_to_duty_edit,
                            }
                            try:
                                res = supabase.table(MAINT_TABLE).update(update_data).eq("id", selected_record_id).execute()
                                if res.data:
                                    st.success("✅ Maintenance record updated successfully!")
                                    st.session_state.show_edit_maint = False
                                    st.session_state.edit_maint_id = None
                                    st.session_state.edit_maint_data = None
                                    load_maintenance.clear()
                                    st.rerun()
                            except Exception as e:
                                st.error(f"❌ Update failed: {str(e)}")

                    if delete_clicked:
                        st.session_state.show_delete_confirmation = True
                        st.rerun()

                    if cancel_clicked:
                        st.session_state.show_edit_maint = False
                        st.session_state.edit_maint_id = None
                        st.session_state.edit_maint_data = None
                        st.rerun()

                st.markdown('</div>', unsafe_allow_html=True)

                # Delete confirmation (outside form)
                if st.session_state.show_delete_confirmation:
                    st.warning("Are you sure you want to delete this maintenance record?")
                    col_conf1, col_conf2 = st.columns(2)
                    with col_conf1:
                        if st.button("✅ Yes, Delete", key="confirm_delete_maint_edit_final"):
                            try:
                                supabase.table(MAINT_TABLE).update({
                                    "is_deleted": True,
                                    "deleted_at": datetime.now().isoformat()
                                }).eq("id", selected_record_id).execute()
                                st.success("✅ Maintenance record deleted successfully!")
                                st.session_state.show_delete_confirmation = False
                                st.session_state.show_edit_maint = False
                                st.session_state.edit_maint_id = None
                                st.session_state.edit_maint_data = None
                                load_maintenance.clear()
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Delete failed: {str(e)}")
                    with col_conf2:
                        if st.button("❌ Cancel", key="cancel_delete_maint_edit_final"):
                            st.session_state.show_delete_confirmation = False
                            st.rerun()
        else:
            st.info("👆 Please select a maintenance record from the dropdown above to edit or delete it.")

        st.markdown("---")
        st.write("")

    # ----- MAINTENANCE RECORDS TABLE -----
    st.markdown('<div class="section-header">📋 Vehicle Maintenance Information Table</div>', unsafe_allow_html=True)

    # Filters
    active_maint = maintenance_df[maintenance_df['is_deleted'] == False] if not maintenance_df.empty else pd.DataFrame()
    col_filter1, col_filter2 = st.columns(2)
    with col_filter1:
        plate_filter_options = ["All"] + sorted(active_maint['plate_number'].dropna().astype(str).str.strip().unique().tolist()) if not active_maint.empty else ["All"]
        selected_plate_filter = st.selectbox(
            "Filter by Plate Number",
            options=plate_filter_options,
            key="maint_plate_filter_table"
        )
    with col_filter2:
        # Optionally add more filters (e.g., maintenance type)
        type_options = ["All"] + sorted(active_maint['maintenace_type'].dropna().unique().tolist()) if not active_maint.empty else ["All"]
        selected_type_filter = st.selectbox(
            "Filter by Maintenance Type",
            options=type_options,
            key="maint_type_filter_table"
        )

    if selected_plate_filter != "All":
        filtered_maint = active_maint[active_maint['plate_number'].astype(str).str.strip() == selected_plate_filter.strip()]
    else:
        filtered_maint = active_maint.copy()
    if selected_type_filter != "All":
        filtered_maint = filtered_maint[filtered_maint['maintenace_type'] == selected_type_filter]

    if filtered_maint.empty:
        st.info("📭 No active maintenance records found.")
    else:
        # Prepare display dataframe
        if 'maintenance_total_day' not in filtered_maint.columns:
            filtered_maint['maintenance_total_day'] = None
        # Compute total days if missing
        if filtered_maint['maintenance_total_day'].isna().all():
            def compute_days(row):
                start = row.get('maintenance_starting_date')
                end = row.get('maintenance_ending_date')
                back = str(row.get('back_to_duty', '')).strip().lower()
                if start:
                    start_dt = pd.to_datetime(start, errors='coerce')
                    if pd.notna(start_dt):
                        if back == 'yes' and end:
                            end_dt = pd.to_datetime(end, errors='coerce')
                            if pd.notna(end_dt):
                                return (end_dt - start_dt).days
                        elif back == 'no':
                            return (pd.Timestamp.today() - start_dt).days
                return None
            filtered_maint['maintenance_total_day'] = filtered_maint.apply(compute_days, axis=1)

        # Sort by request date descending
        if 'maintenance_request_date' in filtered_maint.columns:
            filtered_maint['maintenance_request_date'] = pd.to_datetime(filtered_maint['maintenance_request_date'], errors='coerce')
            filtered_maint = filtered_maint.sort_values(by='maintenance_request_date', ascending=False)

        # Select columns to display
        display_columns = [
            ('ID', 'id'),
            ('Plate', 'plate_number'),
            ('Request Date', 'maintenance_request_date'),
            ('Vehicle Type', 'vehicle_type'),
            ('Maintenance Type', 'maintenace_type'),
            ('Branch', 'branch'),
            ('Start Date', 'maintenance_starting_date'),
            ('End Date', 'maintenance_ending_date'),
            ('Workstation', 'maintenance_workstation'),
            ('Responsible Person', 'responsible_person'),
            ('Total Days', 'maintenance_total_day'),
            ('Cost', 'maintenace_cost'),
            ('Remark', 'reason'),
            ('Back to Duty', 'back_to_duty'),
            ('Created At', 'created_at')
        ]
        display_data = {}
        for display_name, source_col in display_columns:
            if source_col in filtered_maint.columns:
                if source_col in ['maintenance_request_date', 'maintenance_starting_date', 'maintenance_ending_date', 'created_at']:
                    series = pd.to_datetime(filtered_maint[source_col], errors='coerce')
                    if source_col == 'created_at':
                        display_data[display_name] = series.dt.strftime('%Y-%m-%d %H:%M')
                    else:
                        display_data[display_name] = series.dt.strftime('%Y-%m-%d')
                else:
                    display_data[display_name] = filtered_maint[source_col]
            else:
                display_data[display_name] = None
        display_df = pd.DataFrame(display_data)

        st.dataframe(display_df, use_container_width=True, hide_index=True)
        st.caption(f"Showing {len(display_df)} record(s)")

        # Export to CSV
        col_export1, col_export2 = st.columns([1, 5])
        with col_export1:
            if st.button("📥 Export to CSV"):
                csv = display_df.to_csv(index=False)
                st.download_button(
                    label="Download CSV",
                    data=csv,
                    file_name=f"maintenance_records_{date.today()}.csv",
                    mime="text/csv",
                    key="download_maint_csv"
                )

    # Deleted records expander
    with st.expander("🗑️ Deleted Maintenance Records", expanded=False):
        deleted_maint = maintenance_df[maintenance_df['is_deleted'] == True] if not maintenance_df.empty else pd.DataFrame()
        if deleted_maint.empty:
            st.info("No deleted maintenance records.")
        else:
            st.dataframe(deleted_maint, use_container_width=True, hide_index=True)

# ===================================================
# TRIP MANAGEMENT (unchanged)
# ===================================================
def show_trip_management(assignments_df, master_df):
    if 'show_add_form' not in st.session_state:
        st.session_state.show_add_form = False
    if 'add_form_key' not in st.session_state:
        st.session_state.add_form_key = 0
    if 'show_edit_form' not in st.session_state:
        st.session_state.show_edit_form = False
    if 'edit_trip_id' not in st.session_state:
        st.session_state.edit_trip_id = None
    if 'edit_trip_data' not in st.session_state:
        st.session_state.edit_trip_data = None
    if 'show_delete_confirmation' not in st.session_state:
        st.session_state.show_delete_confirmation = False

    # ----- Section title (same style as the table header) -----
    st.markdown(
        '<div class="section-header">🚛 Vehicle Trip Management</div>',
        unsafe_allow_html=True
    )

    # ----- TOP ROW: Add New Trip and Edit/Delete buttons -----
    col_top1, col_top2, col_top3 = st.columns([1, 1, 2])
    with col_top1:
        if not st.session_state.show_add_form:
            if st.button("➕ Add New Trip", type="primary", use_container_width=True):
                st.session_state.show_add_form = True
                st.session_state.add_form_key += 1
                if st.session_state.show_edit_form:
                    st.session_state.show_edit_form = False
                    st.session_state.edit_trip_id = None
                    st.session_state.edit_trip_data = None
                st.rerun()
    with col_top2:
        if not st.session_state.show_edit_form:
            if st.button("📝 Edit or Delete", type="secondary", use_container_width=True):
                st.session_state.show_edit_form = True
                if st.session_state.show_add_form:
                    st.session_state.show_add_form = False
                st.session_state.edit_trip_id = None
                st.session_state.edit_trip_data = None
                st.rerun()
    with col_top3:
        st.empty()

    # Add a separator and spacing between the buttons and the forms
    st.markdown("---")
    st.write("")  # vertical spacing

    # ----- ADD NEW TRIP FORM (if shown) -----
    if st.session_state.show_add_form:
        st.markdown("### ➕ Add New Trip")

        # Get available vehicles
        available_vehicles = get_available_vehicles(master_df, assignments_df, maintenance_df)

        # ---- Plate selection (outside form) ----
        plate_options = ["Select Plate Number"] + available_vehicles
        selected_plate = st.selectbox(
            "Plate Number *",
            options=plate_options,
            key="add_plate_select",
            help="Only vehicles without active trips and not under maintenance are shown."
        )

        # Derive info from master data (if a valid plate is selected)
        if selected_plate and selected_plate != "Select Plate Number":
            driver = plate_to_driver.get(selected_plate, "")
            phone = plate_to_phone.get(selected_plate, "")
            vehicle_type = plate_to_vehicle_type.get(selected_plate, "")
        else:
            driver = ""
            phone = ""
            vehicle_type = ""

        # Show derived info in 3 disabled fields
        col_info1, col_info2, col_info3 = st.columns(3)
        with col_info1:
            st.text_input("Driver", value=driver, disabled=True)
        with col_info2:
            st.text_input("Phone", value=phone, disabled=True)
        with col_info3:
            st.text_input("Truck Type", value=vehicle_type, disabled=True)

        # ---- Branch selection (outside form) ----
        branch_options = ["Select Assigned Branch"] + branches
        assigned_branch_name = st.selectbox(
            "Assigned Branch *",
            options=branch_options,
            key="add_branch_outside"
        )

        # Compute Expected Transit Days based on branch selection
        expected_transit_days = None
        if assigned_branch_name and assigned_branch_name != "Select Assigned Branch":
            expected_transit_days = BRANCH_EXPECTED_DAYS.get(assigned_branch_name.strip())
        st.markdown(f"**Expected Transit Days:** {expected_transit_days if expected_transit_days is not None else '—'}")

        # Now the form with all other fields
        with st.form(key=f"add_trip_form_{st.session_state.add_form_key}"):
            # ---- Row 2: From, Requested By, Assigned By (Branch removed) ----
            col5, col6, col7, col8 = st.columns(4)
            with col5:
                from_options = ["Select Location"] + from_locations
                from_location = st.selectbox("From Location *", options=from_options, key="add_from")
            with col6:
                requested_by = st.text_input("Requested By *", placeholder="Enter name", key="add_requested_by")
            with col7:
                assigned_by = st.text_input("Assigned By *", placeholder="Enter name", key="add_assigned_by")
            with col8:
                st.empty()

            # ---- Row 3: Dates (Requested, Assigned, Loading Start, Loading End) ----
            col9, col10, col11, col12 = st.columns(4)
            with col9:
                requested_date = st.date_input("Requested Date *", value=None, key="add_requested_date")
            with col10:
                assigned_date = st.date_input("Assigned Date *", value=None, key="add_assigned_date")
            with col11:
                loading_start = st.date_input("Loading Starting Date", value=None, key="add_loading_start")
            with col12:
                loading_end = st.date_input("Loading Date End", value=None, key="add_loading_end")

            # ---- Row 4: Trip Start, Return, Actual Trip End, Arrival Date ----
            col13, col14, col15, col16 = st.columns(4)
            with col13:
                trip_start = st.date_input("Trip Starting Date", value=None, key="add_trip_start")
            with col14:
                return_dt = st.date_input("Return Date", value=None, key="add_return")
            with col15:
                trip_end = st.date_input("Actual Trip End Date", value=None, key="add_trip_end")
            with col16:
                arrival = st.date_input("Arrival Date", value=None, key="add_arrival")

            # ---- Row 5: Buttons ----
            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                save_clicked = st.form_submit_button("💾 Save Trip", type="primary", use_container_width=True)
            with col_btn2:
                cancel_clicked = st.form_submit_button("❌ Cancel", use_container_width=True)

            # ---- Form submission handling ----
            if save_clicked:
                errors = []
                if not selected_plate or selected_plate == "Select Plate Number":
                    errors.append("Please select a valid Plate Number.")
                if not requested_date:
                    errors.append("Requested Date is required.")
                if not assigned_date:
                    errors.append("Assigned Date is required.")
                if from_location == "Select Location":
                    errors.append("Please select a valid From Location.")
                if assigned_branch_name == "Select Assigned Branch":
                    errors.append("Please select a valid Assigned Branch.")
                if errors:
                    for err in errors:
                        st.error(f"❌ {err}")
                else:
                    current_driver = driver
                    current_phone = phone
                    current_vehicle_type = vehicle_type
                    current_plate = selected_plate

                    # Check for active trip
                    existing = supabase.table(TXN_TABLE)\
                        .select("new_id,status")\
                        .eq("plate_number", current_plate)\
                        .in_("status", ["Planned", "Loading", "In Transit"])\
                        .execute()
                    if existing.data:
                        st.error(
                            f"❌ Vehicle {current_plate} already has an active trip "
                            f"({existing.data[0]['status']}). Complete that trip before creating another."
                        )
                        st.stop()

                    loading_start_dt = combine_date_with_current_time(loading_start) if loading_start else None
                    loading_end_dt = combine_date_with_current_time(loading_end) if loading_end else None
                    trip_start_dt = combine_date_with_current_time(trip_start) if trip_start else None
                    arrival_dt = combine_date_with_current_time(arrival) if arrival else None
                    return_dt_combined = combine_date_with_current_time(return_dt) if return_dt else None
                    trip_end_dt = combine_date_with_current_time(trip_end) if trip_end else None

                    temp_record = {
                        'assigned_date': assigned_date,
                        'loading_starting_date': loading_start,
                        'trip_starting_date': trip_start,
                        'trip_end_date': trip_end
                    }
                    status, _ = calculate_status_and_errors(temp_record)

                    new_record = {
                        "plate_number": current_plate,
                        "driver_name": current_driver,
                        "phone_number": current_phone if current_phone else None,
                        "vehicle_type": current_vehicle_type if current_vehicle_type else None,
                        "from_location": from_location,
                        "assigned_branch_name": assigned_branch_name,
                        "requested_date": str(requested_date) if requested_date else None,
                        "requested_by": requested_by,
                        "assigned_by": assigned_by,
                        "assigned_date": str(assigned_date) if assigned_date else None,
                        "status": status,
                        "loading_starting_date": format_datetime_for_db(loading_start_dt),
                        "loading_date_end": format_datetime_for_db(loading_end_dt),
                        "trip_starting_date": format_datetime_for_db(trip_start_dt),
                        "arrival_date": format_datetime_for_db(arrival_dt),
                        "return_date": format_datetime_for_db(return_dt_combined),
                        "trip_end_date": format_datetime_for_db(trip_end_dt),
                        "created_at": datetime.now().isoformat(),
                        "is_deleted": False,
                        "deleted_at": None
                    }
                    try:
                        res = supabase.table(TXN_TABLE).insert(new_record).execute()
                        if res.data:
                            st.success("✅ Trip saved successfully!")
                            st.session_state.show_add_form = False
                            load_assignments.clear()
                            st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")

            if cancel_clicked:
                st.session_state.show_add_form = False
                st.rerun()

        st.markdown("---")
        st.write("")  # extra spacing after the add form

    # ----- EDIT / DELETE FORM (if shown) -----
    if st.session_state.show_edit_form:
        st.markdown("### 📝 Edit or Delete Trip")

        # Build list of editable trips (Planned, Loading, In Transit)
        active_trips = assignments_df[assignments_df['is_deleted'] == False] if not assignments_df.empty else pd.DataFrame()
        editable_trips = active_trips[active_trips['status'].str.title().isin(['Planned', 'Loading', 'In Transit'])] if not active_trips.empty else pd.DataFrame()
        trip_options = [("", "Select Trip")]
        for idx, row in editable_trips.iterrows():
            if row.get('new_id'):
                status_display = row.get('status', 'N/A')
                trip_label = f"{row.get('plate_number', 'N/A')} - {row.get('driver_name', 'N/A')} ({status_display})"
                trip_options.append((row['new_id'], trip_label))

        # ---- Select Trip dropdown (outside form) ----
        # Hide the label by using label_visibility="collapsed"
        selected_trip_id = st.selectbox(
            "Select Trip",
            options=[opt[0] for opt in trip_options],
            format_func=lambda x: next((opt[1] for opt in trip_options if opt[0] == x), "Select Trip"),
            key="edit_trip_select",
            label_visibility="collapsed"
        )
        # Add a small placeholder text above the dropdown for clarity
        st.caption("Choose a trip from the list below to edit or delete it.")

        # If a trip is selected, load its data and display the edit form
        if selected_trip_id:
            # Fetch trip data if not already loaded or if changed
            if st.session_state.edit_trip_id != selected_trip_id:
                trip_data = get_trip_by_id(selected_trip_id)
                if trip_data:
                    st.session_state.edit_trip_data = trip_data
                    st.session_state.edit_trip_id = selected_trip_id
                else:
                    st.error("Could not load trip data.")
                    st.session_state.edit_trip_data = None
                    st.session_state.edit_trip_id = None

            if st.session_state.edit_trip_data:
                edit_data = st.session_state.edit_trip_data
                plate_display = edit_data.get('plate_number', 'Unknown')

                st.markdown('<div class="edit-container">', unsafe_allow_html=True)
                st.markdown(f"### ✏️ Edit Trip – {plate_display}")

                # Pre-fill values from edit_data
                current_plate = edit_data.get('plate_number', '')
                current_from = edit_data.get('from_location', '')
                current_branch = edit_data.get('assigned_branch_name', '')
                current_requested_by = edit_data.get('requested_by', '')
                current_assigned_by = edit_data.get('assigned_by', '')
                current_requested_date = get_date_from_value(edit_data.get('requested_date'))
                current_assigned_date = get_date_from_value(edit_data.get('assigned_date'))
                current_loading_start = get_date_from_value(edit_data.get('loading_starting_date'))
                current_loading_end = get_date_from_value(edit_data.get('loading_date_end'))
                current_trip_start = get_date_from_value(edit_data.get('trip_starting_date'))
                current_arrival = get_date_from_value(edit_data.get('arrival_date'))
                current_return = get_date_from_value(edit_data.get('return_date'))
                current_trip_end = get_date_from_value(edit_data.get('trip_end_date'))

                # Derive driver info from master data (or fallback to trip's stored values)
                if current_plate in plate_to_driver:
                    derived_driver = plate_to_driver[current_plate]
                    derived_phone = plate_to_phone.get(current_plate, '')
                    derived_vehicle_type = plate_to_vehicle_type.get(current_plate, '')
                else:
                    derived_driver = edit_data.get('driver_name', '')
                    derived_phone = edit_data.get('phone_number', '')
                    derived_vehicle_type = edit_data.get('vehicle_type', '')

                # Expected dates (computed, display only)
                computed_expected_arrival = None
                computed_expected_trip_end = None
                if current_branch and current_trip_start:
                    transit_days = BRANCH_EXPECTED_DAYS.get(current_branch.strip())
                    if transit_days is not None:
                        computed_expected_arrival = current_trip_start + timedelta(days=transit_days)
                        computed_expected_trip_end = current_trip_start + timedelta(days=2 * transit_days)

                # ---- Form: same fields as Add New Trip, but pre-filled ----
                # Plate selection (outside form)
                plate_edit = st.selectbox(
                    "Plate Number *",
                    options=plate_numbers,
                    index=plate_numbers.index(current_plate) if current_plate in plate_numbers else 0,
                    key="edit_plate_select"
                )
                # Re‑derive driver info if plate changes (this will rerun when selection changes)
                if plate_edit in plate_to_driver:
                    derived_driver = plate_to_driver[plate_edit]
                    derived_phone = plate_to_phone.get(plate_edit, '')
                    derived_vehicle_type = plate_to_vehicle_type.get(plate_edit, '')
                else:
                    derived_driver = ''
                    derived_phone = ''
                    derived_vehicle_type = ''

                col_info1, col_info2, col_info3 = st.columns(3)
                with col_info1:
                    st.text_input("Driver", value=derived_driver, disabled=True)
                with col_info2:
                    st.text_input("Phone", value=derived_phone, disabled=True)
                with col_info3:
                    st.text_input("Truck Type", value=derived_vehicle_type, disabled=True)

                # Branch selection (outside form)
                branch_edit = st.selectbox(
                    "Assigned Branch *",
                    options=branches,
                    index=branches.index(current_branch) if current_branch in branches else 0,
                    key="edit_branch_select"
                )
                transit_days = BRANCH_EXPECTED_DAYS.get(branch_edit.strip(), None)
                st.caption(f"Expected Transit Days: {transit_days if transit_days is not None else '—'}")

                # Now the form with all other fields
                with st.form(key="edit_trip_form"):
                    # Row 1: From Location, Requested By, Assigned By
                    col5, col6, col7, col8 = st.columns(4)
                    with col5:
                        from_location_edit = st.selectbox(
                            "From Location *",
                            options=from_locations,
                            index=from_locations.index(current_from) if current_from in from_locations else 0,
                            key="edit_from"
                        )
                    with col6:
                        requested_by_edit = st.text_input(
                            "Requested By *",
                            value=current_requested_by,
                            key="edit_requested_by"
                        )
                    with col7:
                        assigned_by_edit = st.text_input(
                            "Assigned By *",
                            value=current_assigned_by,
                            key="edit_assigned_by"
                        )
                    with col8:
                        st.empty()

                    # Row 2: Requested Date, Assigned Date, Loading Start, Loading End
                    col9, col10, col11, col12 = st.columns(4)
                    with col9:
                        requested_date_edit = st.date_input(
                            "Requested Date",
                            value=current_requested_date,
                            key="edit_requested_date"
                        )
                    with col10:
                        assigned_date_edit = st.date_input(
                            "Assigned Date",
                            value=current_assigned_date,
                            key="edit_assigned_date"
                        )
                    with col11:
                        loading_start_edit = st.date_input(
                            "Loading Starting Date",
                            value=current_loading_start,
                            key="edit_loading_start"
                        )
                    with col12:
                        loading_end_edit = st.date_input(
                            "Loading Date End",
                            value=current_loading_end,
                            key="edit_loading_end"
                        )

                    # Row 3: Trip Start, Return, Actual Trip End, Arrival
                    col13, col14, col15, col16 = st.columns(4)
                    with col13:
                        trip_start_edit = st.date_input(
                            "Trip Starting Date",
                            value=current_trip_start,
                            key="edit_trip_start"
                        )
                    with col14:
                        return_edit = st.date_input(
                            "Return Date",
                            value=current_return,
                            key="edit_return"
                        )
                    with col15:
                        trip_end_edit = st.date_input(
                            "Actual Trip End Date",
                            value=current_trip_end,
                            key="edit_trip_end"
                        )
                    with col16:
                        arrival_edit = st.date_input(
                            "Arrival Date",
                            value=current_arrival,
                            key="edit_arrival"
                        )

                    # Expected dates (display only)
                    st.caption(f"**Expected Arrival:** {computed_expected_arrival.strftime('%Y-%m-%d') if computed_expected_arrival else '—'}")
                    st.caption(f"**Expected Trip End:** {computed_expected_trip_end.strftime('%Y-%m-%d') if computed_expected_trip_end else '—'}")

                    # ---- Buttons: Update (primary) and Delete (red) ----
                    col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 1])
                    with col_btn1:
                        update_clicked = st.form_submit_button("🔄 Update Trip", type="primary", use_container_width=True)
                    with col_btn2:
                        delete_clicked = st.form_submit_button("🗑️ Delete Trip", use_container_width=True)
                    with col_btn3:
                        cancel_clicked = st.form_submit_button("❌ Cancel", use_container_width=True)

                    if update_clicked:
                        errors = []
                        if not plate_edit:
                            errors.append("Plate Number is required.")
                        if not requested_date_edit:
                            errors.append("Requested Date is required.")
                        if not assigned_date_edit:
                            errors.append("Assigned Date is required.")
                        if not from_location_edit:
                            errors.append("From Location is required.")
                        if not branch_edit:
                            errors.append("Assigned Branch is required.")
                        if errors:
                            for err in errors:
                                st.error(f"❌ {err}")
                        else:
                            existing = supabase.table(TXN_TABLE)\
                                .select("new_id,status")\
                                .eq("plate_number", plate_edit)\
                                .in_("status", ["Planned", "Loading", "In Transit"])\
                                .execute()
                            conflict = any(row['new_id'] != selected_trip_id for row in existing.data)
                            if conflict:
                                st.error(f"❌ Vehicle {plate_edit} already has another active trip. Complete that trip first.")
                            else:
                                loading_start_dt = combine_date_with_current_time(loading_start_edit) if loading_start_edit else None
                                loading_end_dt = combine_date_with_current_time(loading_end_edit) if loading_end_edit else None
                                trip_start_dt = combine_date_with_current_time(trip_start_edit) if trip_start_edit else None
                                arrival_dt = combine_date_with_current_time(arrival_edit) if arrival_edit else None
                                return_dt_combined = combine_date_with_current_time(return_edit) if return_edit else None
                                trip_end_dt = combine_date_with_current_time(trip_end_edit) if trip_end_edit else None

                                temp_record = {
                                    'assigned_date': assigned_date_edit,
                                    'loading_starting_date': loading_start_edit,
                                    'trip_starting_date': trip_start_edit,
                                    'trip_end_date': trip_end_edit
                                }
                                status, _ = calculate_status_and_errors(temp_record)

                                update_data = {
                                    "plate_number": plate_edit,
                                    "driver_name": derived_driver,
                                    "phone_number": derived_phone if derived_phone else None,
                                    "vehicle_type": derived_vehicle_type if derived_vehicle_type else None,
                                    "from_location": from_location_edit,
                                    "assigned_branch_name": branch_edit,
                                    "requested_date": str(requested_date_edit) if requested_date_edit else None,
                                    "requested_by": requested_by_edit,
                                    "assigned_by": assigned_by_edit,
                                    "assigned_date": str(assigned_date_edit) if assigned_date_edit else None,
                                    "status": status,
                                    "loading_starting_date": format_datetime_for_db(loading_start_dt),
                                    "loading_date_end": format_datetime_for_db(loading_end_dt),
                                    "trip_starting_date": format_datetime_for_db(trip_start_dt),
                                    "arrival_date": format_datetime_for_db(arrival_dt),
                                    "return_date": format_datetime_for_db(return_dt_combined),
                                    "trip_end_date": format_datetime_for_db(trip_end_dt),
                                }
                                try:
                                    res = supabase.table(TXN_TABLE).update(update_data).eq("new_id", selected_trip_id).execute()
                                    if res.data:
                                        st.success("✅ Trip updated successfully!")
                                        st.session_state.show_edit_form = False
                                        st.session_state.edit_trip_id = None
                                        st.session_state.edit_trip_data = None
                                        load_assignments.clear()
                                        st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Update failed: {str(e)}")

                    if delete_clicked:
                        st.session_state.show_delete_confirmation = True
                        st.rerun()

                    if cancel_clicked:
                        st.session_state.show_edit_form = False
                        st.session_state.edit_trip_id = None
                        st.session_state.edit_trip_data = None
                        st.rerun()

                st.markdown('</div>', unsafe_allow_html=True)

                # ---- Delete confirmation (outside form) ----
                if st.session_state.show_delete_confirmation:
                    st.warning("Are you sure you want to delete this trip?")
                    col_conf1, col_conf2 = st.columns(2)
                    with col_conf1:
                        if st.button("✅ Yes, Delete", key="confirm_delete_trip_edit_final"):
                            try:
                                supabase.table(TXN_TABLE).update({
                                    "is_deleted": True,
                                    "deleted_at": datetime.now().isoformat()
                                }).eq("new_id", selected_trip_id).execute()
                                st.success("✅ Trip deleted successfully!")
                                st.session_state.show_delete_confirmation = False
                                st.session_state.show_edit_form = False
                                st.session_state.edit_trip_id = None
                                st.session_state.edit_trip_data = None
                                load_assignments.clear()
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Delete failed: {str(e)}")
                    with col_conf2:
                        if st.button("❌ Cancel", key="cancel_delete_trip_edit_final"):
                            st.session_state.show_delete_confirmation = False
                            st.rerun()
        else:
            # Informative message when no trip is selected
            st.info("👆 Please select a trip from the dropdown above to edit or delete it.")

        st.markdown("---")
        st.write("")  # extra spacing after the edit form

    # ----- TRIP RECORDS TABLE (always shown below the forms) -----
    st.markdown('<div class="section-header">📋 Vehicle Trip Information Table</div>', unsafe_allow_html=True)

    try:
        active_trips = assignments_df[assignments_df['is_deleted'] == False] if not assignments_df.empty else pd.DataFrame()

        if not active_trips.empty:
            data = active_trips.copy()
            if 'created_at' in data.columns:
                data = data.sort_values(by="created_at", ascending=False)
            else:
                data = data.sort_values(by="new_id", ascending=False)

            # Ensure new columns exist (they are computed in preprocessing)
            for col in ['expected_arrival_date', 'expected_trip_end_date', 'on_time_delivery_days', 'trip_variance_days',
                        'delivery_status', 'trip_status']:
                if col not in data.columns:
                    data[col] = None

            # Base display columns – we will reorder later
            base_columns = [
                "new_id", "plate_number", "driver_name", "phone_number", "vehicle_type",
                "from_location", "assigned_branch_name", "requested_date",
                "requested_by", "assigned_by", "assigned_date",
                "loading_starting_date", "loading_date_end", "trip_starting_date",
                "arrival_date", "return_date", "trip_end_date",
                "expected_arrival_date", "expected_trip_end_date",
                "status", "created_at",
                "loading_time", "ongoing_time", "incoming_time", "total_trip_time",
                "on_time_delivery_days", "trip_variance_days",
                "delivery_status", "trip_status",
                "idle_assigned_to_loading", "idle_loading_to_trip", "idle_assigned_to_end", "total_idle"
            ]
            for col in base_columns:
                if col not in data.columns:
                    data[col] = None

            # Define desired column order for display
            display_cols_order = [
                "plate_number", "driver_name", "phone_number", "vehicle_type",
                "from_location", "assigned_branch_name", "requested_date",
                "requested_by", "assigned_by", "assigned_date",
                "loading_starting_date", "loading_date_end", "trip_starting_date",
                "arrival_date", "return_date", "trip_end_date",
                "expected_arrival_date", "expected_trip_end_date",
                "status", "created_at",
                "loading_time", "ongoing_time", "incoming_time", "total_trip_time",
                "on_time_delivery_days",
                "delivery_status",
                "trip_variance_days",
                "trip_status",
                "idle_assigned_to_loading", "idle_loading_to_trip", "idle_assigned_to_end", "total_idle"
            ]
            for col in display_cols_order:
                if col not in data.columns:
                    data[col] = None

            # ---- Filters and display ----
            col_filter1, col_filter2, col_filter3 = st.columns(3)
            with col_filter1:
                status_options = ["All"]
                if "status" in data.columns:
                    status_values = data["status"].dropna().unique().tolist()
                    status_options.extend(sorted([str(s) for s in status_values if s is not None]))
                filter_status = st.multiselect("Status", options=status_options, default=["All"], key="filter_status_table")
            with col_filter2:
                branch_options = ["All"]
                if "assigned_branch_name" in data.columns:
                    branch_values = data["assigned_branch_name"].dropna().unique().tolist()
                    branch_options.extend(sorted([str(b) for b in branch_values if b is not None]))
                filter_branch = st.multiselect("Branch", options=branch_options, default=["All"], key="filter_branch_table")
            with col_filter3:
                plate_options = ["All"]
                if "plate_number" in data.columns:
                    plate_values = data["plate_number"].dropna().unique().tolist()
                    plate_options.extend(sorted([str(p) for p in plate_values if p is not None]))
                filter_plate = st.multiselect("Vehicle", options=plate_options, default=["All"], key="filter_plate_table")

            filtered_data = data.copy()
            if "All" not in filter_status and filter_status:
                filtered_data = filtered_data[filtered_data["status"].notna() & filtered_data["status"].astype(str).isin(filter_status)]
            if "All" not in filter_branch and filter_branch:
                filtered_data = filtered_data[filtered_data["assigned_branch_name"].notna() & filtered_data["assigned_branch_name"].astype(str).isin(filter_branch)]
            if "All" not in filter_plate and filter_plate:
                filtered_data = filtered_data[filtered_data["plate_number"].notna() & filtered_data["plate_number"].astype(str).isin(filter_plate)]

            if len(filtered_data) < len(data):
                st.info(f"📊 Showing {len(filtered_data)} of {len(data)} records")

            if not filtered_data.empty:
                display_data = filtered_data[display_cols_order].copy()

                rename_map = {
                    'plate_number': 'Plate Number',
                    'driver_name': 'Driver',
                    'phone_number': 'Phone Number',
                    'vehicle_type': 'Vehicle Type',
                    'from_location': 'From Location',
                    'assigned_branch_name': 'Assigned Branch',
                    'requested_date': 'Requested Date',
                    'requested_by': 'Requested By',
                    'assigned_by': 'Assigned By',
                    'assigned_date': 'Assigned Date',
                    'loading_starting_date': 'Loading Starting Date',
                    'loading_date_end': 'Loading Date End',
                    'trip_starting_date': 'Trip Starting Date',
                    'arrival_date': 'Arrival Date',
                    'return_date': 'Return Date',
                    'trip_end_date': 'Actual Trip End Date',
                    'expected_arrival_date': 'Expected Arrival Date',
                    'expected_trip_end_date': 'Expected Trip End Date',
                    'status': 'Status',
                    'created_at': 'Created At',
                    'loading_time': 'Loading Time',
                    'ongoing_time': 'Ongoing Time',
                    'incoming_time': 'Incoming Time',
                    'total_trip_time': 'Total Trip Time',
                    'on_time_delivery_days': 'On-Time Delivery (Days)',
                    'delivery_status': 'Delivery Status',
                    'trip_variance_days': 'Trip Variance (Days)',
                    'trip_status': 'Trip Status',
                    'idle_assigned_to_loading': 'Idle (Assigned→Loading)',
                    'idle_loading_to_trip': 'Idle (Loading→Trip)',
                    'idle_assigned_to_end': 'Idle (Assigned→End)',
                    'total_idle': 'Total Idle'
                }
                display_data.rename(columns=rename_map, inplace=True)

                def format_delivery_status(val):
                    if pd.isna(val):
                        return ''
                    if val == 'Earlier':
                        return '🔵 Earlier'
                    elif val == 'Ontime':
                        return '🟢 Ontime'
                    elif val == 'Later':
                        return '🔴 Later'
                    return val

                def format_trip_status(val):
                    if pd.isna(val):
                        return ''
                    if val == 'Early Return':
                        return '🔵 Early Return'
                    elif val == 'On Schedule':
                        return '🟢 On Schedule'
                    elif val == 'Delayed':
                        return '🔴 Delayed'
                    return val

                if 'Delivery Status' in display_data.columns:
                    display_data['Delivery Status'] = display_data['Delivery Status'].apply(format_delivery_status)
                if 'Trip Status' in display_data.columns:
                    display_data['Trip Status'] = display_data['Trip Status'].apply(format_trip_status)

                time_cols = [
                    'Loading Time', 'Ongoing Time', 'Incoming Time', 'Total Trip Time',
                    'Idle (Assigned→Loading)', 'Idle (Loading→Trip)', 'Idle (Assigned→End)', 'Total Idle'
                ]
                for col in time_cols:
                    if col in display_data.columns:
                        display_data[col] = display_data[col].apply(format_days_hours)

                date_cols = ['Requested Date', 'Loading Starting Date', 'Loading Date End', 'Trip Starting Date',
                             'Arrival Date', 'Return Date', 'Actual Trip End Date', 'Expected Arrival Date', 'Expected Trip End Date']
                for col in date_cols:
                    if col in display_data.columns:
                        display_data[col] = pd.to_datetime(display_data[col], errors='coerce')
                        display_data[col] = display_data[col].dt.strftime('%Y-%m-%d %H:%M')

                st.dataframe(
                    display_data,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Status": st.column_config.Column("Status", width="small"),
                        "Plate Number": st.column_config.Column("Plate Number", width="small"),
                        "Driver": st.column_config.Column("Driver", width="medium"),
                        "Phone Number": st.column_config.Column("Phone Number", width="medium"),
                        "Vehicle Type": st.column_config.Column("Vehicle Type", width="medium"),
                        "From Location": st.column_config.Column("From Location", width="medium"),
                        "Assigned Branch": st.column_config.Column("Assigned Branch", width="medium"),
                        "Requested Date": st.column_config.Column("Requested Date", width="medium"),
                        "Requested By": st.column_config.Column("Requested By", width="medium"),
                        "Assigned By": st.column_config.Column("Assigned By", width="medium"),
                        "Assigned Date": st.column_config.Column("Assigned Date", width="medium"),
                        "Loading Starting Date": st.column_config.Column("Loading Starting Date", width="medium"),
                        "Loading Date End": st.column_config.Column("Loading Date End", width="medium"),
                        "Trip Starting Date": st.column_config.Column("Trip Starting Date", width="medium"),
                        "Arrival Date": st.column_config.Column("Arrival Date", width="medium"),
                        "Return Date": st.column_config.Column("Return Date", width="medium"),
                        "Actual Trip End Date": st.column_config.Column("Actual Trip End Date", width="medium"),
                        "Expected Arrival Date": st.column_config.Column("Expected Arrival Date", width="medium"),
                        "Expected Trip End Date": st.column_config.Column("Expected Trip End Date", width="medium"),
                        "Created At": st.column_config.Column("Created At", width="medium"),
                        "Loading Time": st.column_config.Column("Loading Time", width="small"),
                        "Ongoing Time": st.column_config.Column("Ongoing Time", width="small"),
                        "Incoming Time": st.column_config.Column("Incoming Time", width="small"),
                        "Total Trip Time": st.column_config.Column("Total Trip Time", width="small"),
                        "On-Time Delivery (Days)": st.column_config.Column("On-Time Delivery (Days)", width="small"),
                        "Delivery Status": st.column_config.Column("Delivery Status", width="medium"),
                        "Trip Variance (Days)": st.column_config.Column("Trip Variance (Days)", width="small"),
                        "Trip Status": st.column_config.Column("Trip Status", width="medium"),
                        "Idle (Assigned→Loading)": st.column_config.Column("Idle (Assigned→Loading)", width="small"),
                        "Idle (Loading→Trip)": st.column_config.Column("Idle (Loading→Trip)", width="small"),
                        "Idle (Assigned→End)": st.column_config.Column("Idle (Assigned→End)", width="small"),
                        "Total Idle": st.column_config.Column("Total Idle", width="small"),
                    }
                )

                col_export1, col_export2 = st.columns([1, 5])
                with col_export1:
                    if st.button("📥 Export to CSV"):
                        export_data = display_data.copy()
                        csv = export_data.to_csv(index=False)
                        st.download_button(label="Download CSV", data=csv, file_name=f"fleet_trips_{date.today()}.csv", mime="text/csv", key="download_csv_table")
            else:
                st.info("📭 No records match the selected filters")
        else:
            st.info("📭 No active trip records found. Click 'Add New Trip' to create one!")

        with st.expander("🗑️ Deleted Trip Records", expanded=False):
            deleted_trips = assignments_df[assignments_df['is_deleted'] == True] if not assignments_df.empty else pd.DataFrame()
            if deleted_trips.empty:
                st.info("No deleted trips.")
            else:
                st.dataframe(deleted_trips, use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"❌ Load error: {str(e)}")
        logger.error(f"Dashboard load error: {e}")

# ===================================================
def show_kpis_analysis(assignments_df, master_df, maintenance_df, kpis):
    if 'selected_kpi' not in st.session_state:
        st.session_state.selected_kpi = None
    if 'maintenance_view' not in st.session_state:
        st.session_state.maintenance_view = None

    st.markdown("""
    <style>
        @keyframes vibrate {
            0% { transform: translate(0); }
            20% { transform: translate(-2px, 2px); }
            40% { transform: translate(2px, -2px); }
            60% { transform: translate(-2px, -2px); }
            80% { transform: translate(2px, 2px); }
            100% { transform: translate(0); }
        }
        .kpi-card { transition: all 0.2s ease; }
        .kpi-card:hover {
            animation: vibrate 0.3s ease-in-out;
            box-shadow: 0 8px 24px rgba(0,0,0,0.2) !important;
        }
        .card-container {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 2px;
        }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style="font-size: 32px; font-weight: 700; color: #0d47a1; margin: 0 0 16px 0; text-align: center;">
        📊 Fleet Management Performance
    </div>
    """, unsafe_allow_html=True)

    total_vehicles = kpis['total_vehicles']
    assigned_count = kpis['assigned_count']
    under_maint_count = kpis['under_maint_count']
    available_count = kpis['available_count']
    active_count = kpis['active_count']
    assigned_plates = kpis['assigned_plates']
    under_maint_plates = kpis['under_maint_plates']
    available_plates = kpis['available_plates']
    active_plates = kpis['active_plates']
    all_vehicles = kpis['all_vehicles']
    utilization_rate = kpis['utilization_rate']
    fleet_performance = kpis['fleet_performance']
    availability_rate = kpis['availability_rate']
    downtime_rate = kpis['downtime_rate']

    active_assign = assignments_df[assignments_df['is_deleted'] == False] if not assignments_df.empty else pd.DataFrame()
    completed = active_assign[active_assign['status'] == 'Completed'] if not active_assign.empty else pd.DataFrame()
    completed_count = len(completed)

    otd_rate = 0
    trip_variance_rate = 0
    if completed_count > 0:
        otd_count = len(completed[completed['delivery_status'].isin(['Ontime', 'Earlier'])]) if 'delivery_status' in completed.columns else 0
        otd_rate = (otd_count / completed_count) * 100
        on_schedule_count = len(completed[completed['trip_status'].isin(['On Schedule', 'Early Return'])]) if 'trip_status' in completed.columns else 0
        trip_variance_rate = (on_schedule_count / completed_count) * 100

    if not active_assign.empty and 'total_idle' in active_assign.columns:
        total_idle_sum = active_assign['total_idle'].sum()
        active_vehicles = active_assign['plate_number'].nunique() if 'plate_number' in active_assign.columns else 0
        avg_idle = total_idle_sum / active_vehicles if active_vehicles > 0 else 0
        avg_idle_display = format_days_hours_display(avg_idle)
    else:
        avg_idle_display = "0 hrs (0 days)"

    st.subheader("🚗 Vehicle Status")

    if not active_assign.empty and 'status' in active_assign.columns:
        status_counts_all = active_assign['status'].value_counts()
        total_trips = len(active_assign)
    else:
        status_counts_all = pd.Series()
        total_trips = 0

    kpi_colors = {
        "Total Vehicles": "#0d47a1",
        "Assigned Vehicles": "#e65100",
        "Under Maintenance": "#b71c1c",
        "Available Vehicles": "#1b5e20",
        "Active Vehicles": "#1565C0"
    }

    kpi_data = {
        "Total Vehicles": {"value": total_vehicles, "plates": all_vehicles},
        "Assigned Vehicles": {"value": assigned_count, "plates": assigned_plates},
        "Under Maintenance": {"value": under_maint_count, "plates": under_maint_plates},
        "Available Vehicles": {"value": available_count, "plates": available_plates},
        "Active Vehicles": {"value": active_count, "plates": active_plates}
    }

    cols = st.columns(5)
    for idx, (label, data) in enumerate(kpi_data.items()):
        with cols[idx]:
            key = label.lower().replace(" ", "_")
            color = kpi_colors.get(label, "#0d47a1")
            st.markdown(f"""
            <div class="card-container">
                <div class="kpi-card" style="background: {color}; color: white; border-radius: 14px; padding: 10px 6px; text-align: center; box-shadow: 0 4px 12px rgba(0,0,0,0.12); width: 100%;">
                    <div style="font-size: 32px; font-weight: 900; line-height: 1.2;">{data['value']}</div>
                    <div style="font-size: 14px; font-weight: 500; opacity: 0.9;">{label}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("👁️", key=f"eye_{key}", help=f"View details for {label}", use_container_width=True):
                if st.session_state.selected_kpi == key:
                    st.session_state.selected_kpi = None
                else:
                    st.session_state.selected_kpi = key
                st.rerun()

    if not status_counts_all.empty:
        st.markdown("#### Status Breakdown")
        st.caption("Based on all trips")
        status_cols = st.columns(min(len(status_counts_all), 4))
        for idx, (status, count) in enumerate(status_counts_all.items()):
            with status_cols[idx]:
                percentage = (count / total_trips * 100) if total_trips > 0 else 0
                color = {'Planned': '#2196F3', 'Loading': '#FF9800', 'In Transit': '#9C27B0', 'Completed': '#4CAF50'}.get(status, '#607D8B')
                st.markdown(f"""
                <div style="background: white; border-radius: 10px; padding: 12px 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); text-align: center; border-top: 4px solid {color};">
                    <div style="font-size: 24px; font-weight: 700; line-height: 1.2;">{count}</div>
                    <div style="font-size: 12px; color: #666; font-weight: 500;">{status}</div>
                    <div style="font-size: 14px; color: #888;">{percentage:.1f}%</div>
                </div>
                """, unsafe_allow_html=True)

    if st.session_state.selected_kpi:
        selected_key = st.session_state.selected_kpi
        selected_label = None
        for lbl in kpi_data.keys():
            if lbl.lower().replace(" ", "_") == selected_key:
                selected_label = lbl
                break
        if selected_label is None:
            selected_label = selected_key.replace("_", " ").title()
        selected_plates = kpi_data.get(selected_label, {}).get("plates", set())
        st.markdown("---")
        st.subheader(f"📋 {selected_label} - Details")

        if not selected_plates:
            st.info("No vehicles in this category.")
            st.stop()

        if selected_label == "Active Vehicles":
            if not master_df.empty:
                display_cols = ['plate_number', 'driver_name', 'phone_number', 'vehicle_type']
                missing = [c for c in display_cols if c not in master_df.columns]
                for col in missing:
                    master_df[col] = None
                filtered_df = master_df[master_df['plate_number'].isin(selected_plates)][display_cols].copy()
                filtered_df.rename(columns={
                    'plate_number': 'Plate',
                    'driver_name': 'Driver',
                    'phone_number': 'Phone',
                    'vehicle_type': 'Type'
                }, inplace=True)
                st.dataframe(filtered_df, use_container_width=True, hide_index=True)
                st.caption(f"Showing {len(filtered_df)} vehicle(s)")
            else:
                st.info("No master data available.")
        elif selected_label == "Assigned Vehicles":
            if not active_assign.empty:
                filtered = active_assign[active_assign['plate_number'].isin(selected_plates)].copy()
                if 'assigned_date' in filtered.columns:
                    filtered = filtered.sort_values('assigned_date', ascending=False).drop_duplicates('plate_number')
                display_columns = [
                    "plate_number", "driver_name", "phone_number", "vehicle_type", 
                    "from_location", "assigned_branch_name", "requested_date", 
                    "requested_by", "assigned_by", "assigned_date",
                    "loading_starting_date", "loading_date_end", "trip_starting_date", 
                    "arrival_date", "return_date", "trip_end_date", 
                    "expected_arrival_date", "expected_trip_end_date",
                    "status", "created_at",
                    "loading_time", "ongoing_time", "incoming_time", "total_trip_time",
                    "on_time_delivery_days", "trip_variance_days",
                    "delivery_status", "trip_status",
                    "idle_assigned_to_loading", "idle_loading_to_trip", "idle_assigned_to_end", "total_idle"
                ]
                display_columns = [col for col in display_columns if col in filtered.columns]
                display_data = filtered[display_columns].copy()
                rename_map = {
                    'phone_number': 'Phone Number',
                    'vehicle_type': 'Vehicle Type',
                    'requested_date': 'Requested Date',
                    'loading_starting_date': 'Loading Starting Date',
                    'loading_date_end': 'Loading Date End',
                    'trip_starting_date': 'Trip Starting Date',
                    'arrival_date': 'Arrival Date',
                    'return_date': 'Return Date',
                    'trip_end_date': 'Actual Trip End Date',
                    'expected_arrival_date': 'Expected Arrival Date',
                    'expected_trip_end_date': 'Expected Trip End Date',
                    'loading_time': 'Loading Time',
                    'ongoing_time': 'Ongoing Time',
                    'incoming_time': 'Incoming Time',
                    'total_trip_time': 'Total Trip Time',
                    'on_time_delivery_days': 'On-Time Delivery (Days)',
                    'trip_variance_days': 'Trip Variance (Days)',
                    'delivery_status': 'Delivery Status',
                    'trip_status': 'Trip Status',
                    'idle_assigned_to_loading': 'Idle (Assigned→Loading)',
                    'idle_loading_to_trip': 'Idle (Loading→Trip)',
                    'idle_assigned_to_end': 'Idle (Assigned→End)',
                    'total_idle': 'Total Idle'
                }
                display_data.rename(columns=rename_map, inplace=True)
                def format_delivery_status(val):
                    if pd.isna(val):
                        return ''
                    if val == 'Earlier':
                        return '🔵 Earlier'
                    elif val == 'Ontime':
                        return '🟢 Ontime'
                    elif val == 'Later':
                        return '🔴 Later'
                    return val
                def format_trip_status(val):
                    if pd.isna(val):
                        return ''
                    if val == 'Early Return':
                        return '🔵 Early Return'
                    elif val == 'On Schedule':
                        return '🟢 On Schedule'
                    elif val == 'Delayed':
                        return '🔴 Delayed'
                    return val
                if 'Delivery Status' in display_data.columns:
                    display_data['Delivery Status'] = display_data['Delivery Status'].apply(format_delivery_status)
                if 'Trip Status' in display_data.columns:
                    display_data['Trip Status'] = display_data['Trip Status'].apply(format_trip_status)
                time_cols = [
                    'Loading Time', 'Ongoing Time', 'Incoming Time', 'Total Trip Time',
                    'Idle (Assigned→Loading)', 'Idle (Loading→Trip)', 'Idle (Assigned→End)', 'Total Idle'
                ]
                for col in time_cols:
                    if col in display_data.columns:
                        display_data[col] = display_data[col].apply(format_days_hours)
                date_cols = ['Requested Date', 'Loading Starting Date', 'Loading Date End', 'Trip Starting Date',
                             'Arrival Date', 'Return Date', 'Actual Trip End Date', 'Expected Arrival Date', 'Expected Trip End Date']
                for col in date_cols:
                    if col in display_data.columns:
                        display_data[col] = pd.to_datetime(display_data[col], errors='coerce')
                        display_data[col] = display_data[col].dt.strftime('%Y-%m-%d %H:%M')
                st.dataframe(display_data, use_container_width=True, hide_index=True)
                st.caption(f"Showing {len(display_data)} active trip(s)")
            else:
                st.info("No assignment data available.")
        elif selected_label == "Under Maintenance":
            active_maint = maintenance_df[maintenance_df['is_deleted'] == False] if not maintenance_df.empty else pd.DataFrame()
            if not active_maint.empty:
                filtered = active_maint[active_maint['plate_number'].isin(selected_plates)].copy()
                if 'maintenance_request_date' in filtered.columns:
                    filtered = filtered.sort_values('maintenance_request_date', ascending=False)
                filtered.columns = [col.replace('_', ' ').title() for col in filtered.columns]
                for col in filtered.columns:
                    if 'date' in col.lower() or 'time' in col.lower():
                        filtered[col] = pd.to_datetime(filtered[col], errors='coerce')
                        filtered[col] = filtered[col].dt.strftime('%Y-%m-%d %H:%M')
                st.dataframe(filtered, use_container_width=True, hide_index=True)
                st.caption(f"Showing {len(filtered)} maintenance record(s)")
            else:
                st.info("No maintenance data available.")
        else:
            if not master_df.empty:
                display_cols = ['plate_number', 'driver_name', 'phone_number', 'vehicle_type']
                missing = [c for c in display_cols if c not in master_df.columns]
                for col in missing:
                    master_df[col] = None
                filtered_df = master_df[master_df['plate_number'].isin(selected_plates)][display_cols].copy()
                filtered_df.rename(columns={
                    'plate_number': 'Plate',
                    'driver_name': 'Driver',
                    'phone_number': 'Phone',
                    'vehicle_type': 'Type'
                }, inplace=True)
                st.dataframe(filtered_df, use_container_width=True, hide_index=True)
                st.caption(f"Showing {len(filtered_df)} vehicle(s)")
            else:
                st.info("No master data available.")

    st.markdown("---")
    st.markdown("""
    <div style="background: linear-gradient(135deg, #E3F2FD, #BBDEFB); border-radius: 16px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">
        <h4 style="text-align: center; color: #0d47a1; margin: 0 0 12px 0;">📊 Fleet Performance Rates</h4>
        <div style="display: flex; justify-content: space-around; flex-wrap: wrap; gap: 12px;">
            <div style="text-align: center; flex: 1; min-width: 120px;">
                <div style="font-size: 28px; font-weight: 900; color: #0d47a1;">📈 {fleet_performance:.1f}%</div>
                <div style="font-size: 14px; color: #333;">Fleet Performance</div>
            </div>
            <div style="text-align: center; flex: 1; min-width: 120px;">
                <div style="font-size: 28px; font-weight: 900; color: #0d47a1;">⚡ {utilization_rate:.1f}%</div>
                <div style="font-size: 14px; color: #333;">Utilization Rate</div>
            </div>
            <div style="text-align: center; flex: 1; min-width: 120px;">
                <div style="font-size: 28px; font-weight: 900; color: #0d47a1;">✅ {availability_rate:.1f}%</div>
                <div style="font-size: 14px; color: #333;">Fleet Availability Rate</div>
            </div>
            <div style="text-align: center; flex: 1; min-width: 120px;">
                <div style="font-size: 28px; font-weight: 900; color: #0d47a1;">🔧 {downtime_rate:.1f}%</div>
                <div style="font-size: 14px; color: #333;">Fleet Downtime Rate</div>
            </div>
        </div>
        <div style="display: flex; justify-content: center; flex-wrap: wrap; gap: 12px; margin-top: 16px; padding-top: 16px; border-top: 1px solid #90CAF9;">
            <div style="text-align: center; flex: 1; min-width: 120px;">
                <div style="font-size: 28px; font-weight: 900; color: #0d47a1;">✅ {otd_rate:.1f}%</div>
                <div style="font-size: 14px; color: #333;">OTD Rate (On-Time Delivery)</div>
            </div>
            <div style="text-align: center; flex: 1; min-width: 120px;">
                <div style="font-size: 28px; font-weight: 900; color: #0d47a1;">📊 {trip_variance_rate:.1f}%</div>
                <div style="font-size: 14px; color: #333;">Trip Variance Rate</div>
            </div>
            <div style="text-align: center; flex: 1; min-width: 120px;">
                <div style="font-size: 20px; font-weight: 700; color: #0d47a1;">⏱️ {avg_idle_display}</div>
                <div style="font-size: 14px; color: #333;">Average Idle Time</div>
            </div>
        </div>
    </div>
    """.format(fleet_performance=fleet_performance, utilization_rate=utilization_rate,
               availability_rate=availability_rate, downtime_rate=downtime_rate,
               avg_idle_display=avg_idle_display, otd_rate=otd_rate, trip_variance_rate=trip_variance_rate),
    unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("📊 Delivery & Trip Status Distribution (Completed Trips)")

    if completed_count > 0:
        delivery_counts = completed['delivery_status'].value_counts().reset_index()
        delivery_counts.columns = ['Delivery Status', 'Count']
        trip_counts = completed['trip_status'].value_counts().reset_index()
        trip_counts.columns = ['Trip Status', 'Count']

        col_chart1, col_chart2 = st.columns(2)
        with col_chart1:
            if not delivery_counts.empty:
                fig_delivery = px.pie(
                    delivery_counts,
                    values='Count',
                    names='Delivery Status',
                    title='Delivery Status Distribution',
                    color='Delivery Status',
                    color_discrete_map={'Earlier': '#1E88E5', 'Ontime': '#4CAF50', 'Later': '#F44336'},
                    hole=0.3
                )
                fig_delivery.update_traces(textposition='inside', textinfo='percent+label')
                fig_delivery.update_layout(height=400)
                st.plotly_chart(fig_delivery, use_container_width=True)
            else:
                st.info("No delivery status data available.")
        with col_chart2:
            if not trip_counts.empty:
                fig_trip = px.pie(
                    trip_counts,
                    values='Count',
                    names='Trip Status',
                    title='Trip Status Distribution',
                    color='Trip Status',
                    color_discrete_map={'Early Return': '#1E88E5', 'On Schedule': '#4CAF50', 'Delayed': '#F44336'},
                    hole=0.3
                )
                fig_trip.update_traces(textposition='inside', textinfo='percent+label')
                fig_trip.update_layout(height=400)
                st.plotly_chart(fig_trip, use_container_width=True)
            else:
                st.info("No trip status data available.")
    else:
        st.info("No completed trips to display status distributions.")

    st.markdown("---")
    st.subheader("🔧 Maintenance Performance")
    active_maint = maintenance_df[maintenance_df['is_deleted'] == False] if not maintenance_df.empty else pd.DataFrame()
    total_requests = len(active_maint) if not active_maint.empty else 0
    back_to_duty_count = len(active_maint[active_maint['back_to_duty'].astype(str).str.strip().str.lower() == 'yes']) if not active_maint.empty else 0
    vehicles_with_maint = set(active_maint['plate_number'].dropna().unique()) if not active_maint.empty else set()
    total_cost = active_maint['maintenace_cost'].astype(float).sum() if not active_maint.empty and 'maintenace_cost' in active_maint.columns else 0
    avg_cost = active_maint['maintenace_cost'].astype(float).mean() if not active_maint.empty and 'maintenace_cost' in active_maint.columns else 0
    avg_cost_per_vehicle = total_cost / len(vehicles_with_maint) if len(vehicles_with_maint) > 0 else 0

    maint_data = {
        "Total Requests": {"value": total_requests, "plates": vehicles_with_maint},
        "Under Maintenance": {"value": under_maint_count, "plates": under_maint_plates},
        "Back to Duty": {"value": back_to_duty_count, "plates": set(active_maint[active_maint['back_to_duty'].astype(str).str.strip().str.lower() == 'yes']['plate_number'].dropna().unique())}
    }

    col_m1, col_m2, col_m3 = st.columns(3)
    for col, (label, data) in zip([col_m1, col_m2, col_m3], maint_data.items()):
        with col:
            view_key = label.lower().replace(" ", "_")
            color = {"Total Requests": "#0d47a1", "Under Maintenance": "#b71c1c", "Back to Duty": "#1b5e20"}[label]
            st.markdown(f"""
            <div class="card-container">
                <div class="kpi-card" style="background: {color}; color: white; border-radius: 14px; padding: 10px 6px; text-align: center; box-shadow: 0 4px 12px rgba(0,0,0,0.12); width: 100%;">
                    <div style="font-size: 32px; font-weight: 900; line-height: 1.2;">{data['value']}</div>
                    <div style="font-size: 14px; font-weight: 500; opacity: 0.9;">{label}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("👁️", key=f"maint_eye_{view_key}", help=f"View vehicles for {label}", use_container_width=True):
                if st.session_state.maintenance_view == view_key:
                    st.session_state.maintenance_view = None
                else:
                    st.session_state.maintenance_view = view_key
                st.rerun()

    if st.session_state.maintenance_view:
        view_key = st.session_state.maintenance_view
        plates_to_show = set()
        for lbl, d in maint_data.items():
            if lbl.lower().replace(" ", "_") == view_key:
                plates_to_show = d["plates"]
                break
        st.markdown("---")
        st.subheader(f"📋 Vehicle List - {view_key.replace('_', ' ').title()}")
        if plates_to_show and not master_df.empty:
            display_cols = ['plate_number', 'driver_name', 'phone_number', 'vehicle_type']
            missing = [c for c in display_cols if c not in master_df.columns]
            for col in missing:
                master_df[col] = None
            filtered_df = master_df[master_df['plate_number'].isin(plates_to_show)][display_cols].copy()
            filtered_df.rename(columns={
                'plate_number': 'Plate',
                'driver_name': 'Driver',
                'phone_number': 'Phone',
                'vehicle_type': 'Type'
            }, inplace=True)
            st.dataframe(filtered_df, use_container_width=True, hide_index=True)
            st.caption(f"Showing {len(filtered_df)} vehicle(s)")
        else:
            st.info("No vehicles in this category.")

    st.markdown("---")
    st.subheader("💰 Maintenance Cost Overview")
    st.markdown("""
    <div style="background: linear-gradient(135deg, #E3F2FD, #BBDEFB); border-radius: 16px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">
        <div style="display: flex; justify-content: space-around; flex-wrap: wrap; gap: 12px;">
            <div style="text-align: center; flex: 1; min-width: 120px;">
                <div style="font-size: 28px; font-weight: 900; color: #0d47a1;">{total_cost:,.0f}</div>
                <div style="font-size: 14px; color: #333;">Total Cost (ETB)</div>
            </div>
            <div style="text-align: center; flex: 1; min-width: 120px;">
                <div style="font-size: 28px; font-weight: 900; color: #0d47a1;">{avg_cost:,.0f}</div>
                <div style="font-size: 14px; color: #333;">Avg Cost / Event (ETB)</div>
            </div>
            <div style="text-align: center; flex: 1; min-width: 120px;">
                <div style="font-size: 28px; font-weight: 900; color: #0d47a1;">{avg_cost_per_vehicle:,.0f}</div>
                <div style="font-size: 14px; color: #333;">Avg Cost / Vehicle (ETB)</div>
            </div>
        </div>
    </div>
    """.format(total_cost=total_cost, avg_cost=avg_cost, avg_cost_per_vehicle=avg_cost_per_vehicle), unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("📊 Maintenance Type Breakdown")
    if not active_maint.empty and 'maintenace_type' in active_maint.columns:
        type_counts = active_maint['maintenace_type'].value_counts().reset_index()
        type_counts.columns = ['Maintenance Type', 'Count']
        if not type_counts.empty:
            fig = px.pie(
                type_counts,
                values='Count',
                names='Maintenance Type',
                title='Distribution of Maintenance Types',
                color_discrete_sequence=px.colors.qualitative.Set3,
                hole=0.3
            )
            fig.update_traces(textposition='inside', textinfo='percent+label')
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No maintenance type data available for chart.")
    else:
        st.info("Maintenance type column not found in data.")

    st.markdown("---")
    st.subheader("⏱️ Trip Performance Summary (Averages)")

    if not active_assign.empty:
        metrics = {}
        if 'loading_time' in active_assign.columns and active_assign['loading_time'].notna().any():
            metrics['Loading Time'] = active_assign['loading_time']
        if 'ongoing_time' in active_assign.columns and active_assign['ongoing_time'].notna().any():
            metrics['Ongoing Time'] = active_assign['ongoing_time']
        if 'incoming_time' in active_assign.columns and active_assign['incoming_time'].notna().any():
            metrics['Incoming Time'] = active_assign['incoming_time']
        if 'total_trip_time' in active_assign.columns and active_assign['total_trip_time'].notna().any():
            metrics['Total Trip Time'] = active_assign['total_trip_time']
        if 'on_time_delivery_days' in active_assign.columns and active_assign['on_time_delivery_days'].notna().any():
            metrics['On-Time Delivery'] = active_assign['on_time_delivery_days']
        if 'trip_variance_days' in active_assign.columns and active_assign['trip_variance_days'].notna().any():
            metrics['Trip Variance'] = active_assign['trip_variance_days']

        avg_metrics = {}
        for name, series in metrics.items():
            if series.notna().any():
                avg = series.mean()
                avg_metrics[name] = avg

        if avg_metrics:
            summary_data = []
            for name, avg_val in avg_metrics.items():
                summary_data.append({
                    'Metric': name,
                    'Avg Days': f"{avg_val:.2f}",
                    'Avg Hours': f"{avg_val * 24:.1f}"
                })
            summary_df = pd.DataFrame(summary_data)
            st.dataframe(summary_df, use_container_width=True, hide_index=True)
        else:
            st.info("No trip performance data available.")
    else:
        st.info("No trip data available.")

    st.markdown("---")
    st.subheader("📈 Charts & Detailed Analysis")

    @st.cache_data(ttl=900, show_spinner=False)
    def create_charts(data):
        charts = {}
        if data.empty:
            return charts
        data_copy = data.copy()
        data_copy.columns = data_copy.columns.str.strip()
        date_columns = ['assigned_date', 'requested_date', 'loading_starting_date', 'loading_date_end',
                       'trip_starting_date', 'arrival_date', 'return_date', 'trip_end_date',
                       'expected_arrival_date', 'expected_trip_end_date']
        for col in date_columns:
            if col in data_copy.columns:
                data_copy[col] = pd.to_datetime(data_copy[col], errors='coerce')
        if 'status' in data_copy.columns:
            data_copy['status'] = data_copy['status'].str.title()
            status_counts = data_copy['status'].value_counts()
            if not status_counts.empty:
                fig_status = px.pie(values=status_counts.values, names=status_counts.index, title="Trips by Status", color_discrete_sequence=px.colors.qualitative.Set3)
                fig_status.update_traces(textposition='inside', textinfo='percent+label')
                charts['status_pie'] = fig_status
        if 'assigned_branch_name' in data_copy.columns:
            branch_counts = data_copy['assigned_branch_name'].value_counts().head(10)
            fig_branch = px.bar(x=branch_counts.values, y=branch_counts.index, orientation='h', title="Top 10 Branches by Trip Volume", color=branch_counts.values, color_continuous_scale=px.colors.sequential.Blues)
            fig_branch.update_layout(xaxis_title="Number of Trips", yaxis_title="Branch")
            charts['branch_bar'] = fig_branch
        if 'plate_number' in data_copy.columns:
            vehicle_counts = data_copy['plate_number'].value_counts().head(10)
            fig_vehicle = px.bar(x=vehicle_counts.index, y=vehicle_counts.values, title="Top 10 Most Used Vehicles", color=vehicle_counts.values, color_continuous_scale=px.colors.sequential.Greens)
            fig_vehicle.update_layout(xaxis_title="Plate Number", yaxis_title="Number of Trips")
            charts['vehicle_bar'] = fig_vehicle
        if 'driver_name' in data_copy.columns:
            driver_counts = data_copy['driver_name'].value_counts().head(10)
            fig_driver = px.bar(x=driver_counts.index, y=driver_counts.values, title="Top 10 Drivers by Trip Volume", color=driver_counts.values, color_continuous_scale=px.colors.sequential.Oranges)
            fig_driver.update_layout(xaxis_title="Driver Name", yaxis_title="Number of Trips")
            charts['driver_bar'] = fig_driver
        if 'vehicle_type' in data_copy.columns:
            vehicle_type_counts = data_copy['vehicle_type'].value_counts()
            fig_vehicle_type = px.pie(values=vehicle_type_counts.values, names=vehicle_type_counts.index, title="Vehicle Type Distribution", color_discrete_sequence=px.colors.qualitative.Pastel)
            fig_vehicle_type.update_traces(textposition='inside', textinfo='percent+label')
            charts['vehicle_type_pie'] = fig_vehicle_type
        return charts

    if not active_assign.empty:
        data = active_assign.copy()
        if 'assigned_date' in data.columns:
            data['trip_date'] = pd.to_datetime(data['assigned_date'], errors='coerce')
        else:
            data['trip_date'] = pd.NaT
        if data['trip_date'].isna().all() and 'created_at' in data.columns:
            data['trip_date'] = pd.to_datetime(data['created_at'], errors='coerce')
        if data['trip_date'].isna().all():
            data['trip_date'] = data.index

        latest_trips = data.sort_values('trip_date', ascending=False).drop_duplicates('plate_number')

        status_counts = latest_trips['status'].value_counts()
        planned_vehicles = status_counts.get('Planned', 0)
        loading_vehicles = status_counts.get('Loading', 0)
        in_transit_vehicles = status_counts.get('In Transit', 0)
        completed_vehicles = status_counts.get('Completed', 0)
        total_unique_vehicles = latest_trips['plate_number'].nunique()
        completion_rate = (completed_vehicles / total_unique_vehicles * 100) if total_unique_vehicles > 0 else 0

        col_metric1, col_metric2, col_metric3, col_metric4, col_metric5, col_metric6 = st.columns(6)
        with col_metric1:
            st.metric("Total Vehicles", total_unique_vehicles)
        with col_metric2:
            st.metric("Planned", planned_vehicles)
        with col_metric3:
            st.metric("Loading", loading_vehicles)
        with col_metric4:
            st.metric("In Transit", in_transit_vehicles)
        with col_metric5:
            st.metric("Completed", completed_vehicles)
        with col_metric6:
            st.metric("Completion Rate", f"{completion_rate:.1f}%")

        charts = create_charts(data)
        col_chart1, col_chart2 = st.columns(2)
        with col_chart1:
            if 'status_pie' in charts:
                st.plotly_chart(charts['status_pie'], use_container_width=True)
        with col_chart2:
            if 'branch_bar' in charts:
                st.plotly_chart(charts['branch_bar'], use_container_width=True)
        col_chart3, col_chart4 = st.columns(2)
        with col_chart3:
            if 'vehicle_bar' in charts:
                st.plotly_chart(charts['vehicle_bar'], use_container_width=True)
        with col_chart4:
            if 'driver_bar' in charts:
                st.plotly_chart(charts['driver_bar'], use_container_width=True)
        if 'vehicle_type_pie' in charts:
            st.plotly_chart(charts['vehicle_type_pie'], use_container_width=True)

        st.subheader("📋 Detailed Statistics")
        if 'created_at' in data.columns and not data['created_at'].isna().all():
            st.write(f"**Total Records:** {len(data)}")
            st.write(f"**Date Range:** {data['created_at'].min()} to {data['created_at'].max()}")
        else:
            st.write(f"**Total Records:** {len(data)}")
        if 'status' in data.columns:
            st.write("**Status Breakdown:**")
            status_breakdown = data['status'].value_counts()
            for status_name, count in status_breakdown.items():
                st.write(f"- {status_name}: {count} ({count/len(data)*100:.1f}%)")
        if 'plate_number' in data.columns:
            st.write(f"**Total unique vehicles:** {data['plate_number'].nunique()}")
        if 'driver_name' in data.columns:
            st.write(f"**Total unique drivers:** {data['driver_name'].nunique()}")
        if 'vehicle_type' in data.columns:
            st.write("**Vehicle Types:**")
            vehicle_types = data['vehicle_type'].value_counts()
            for vtype, count in vehicle_types.items():
                st.write(f"- {vtype}: {count}")
    else:
        st.info("No trip data available for charts.")

# ===================================================
# PAGE ROUTING
# ===================================================
if selected_page == "👤 User Info":
    st.markdown('<div class="section-header">👤 User Profile</div>', unsafe_allow_html=True)
    col1, col2 = st.columns([1, 2])
    with col1:
        st.image("https://ui-avatars.com/api/?name=" + user_email.replace("@", "%40") + "&size=150&background=1E88E5&color=fff&bold=true", width=150)
    with col2:
        st.markdown(f"### {user_metadata.get('full_name', 'N/A')}")
        st.markdown(f"**Email:** {user_email}")
        roles_display = ', '.join([r.replace('_', ' ').title() for r in user_roles])
        st.markdown(f"**Roles:** {roles_display}")
        st.markdown(f"**Status:** {'✅ Approved' if is_approved_user else '⏳ Pending Approval'}")
    st.markdown("---")
    st.subheader("🔑 Change Password")
    with st.form("change_password_form_profile"):
        new_password = st.text_input("New Password", type="password")
        confirm_password = st.text_input("Confirm Password", type="password")
        submit_pw = st.form_submit_button("Update Password")
        if submit_pw:
            if not new_password or not confirm_password:
                st.error("Please fill in both fields.")
            elif new_password != confirm_password:
                st.error("Passwords do not match.")
            elif len(new_password) < 6:
                st.error("Password must be at least 6 characters.")
            else:
                try:
                    user = supabase.auth.get_user()
                    if user and user.user:
                        response = supabase.auth.update_user({"password": new_password})
                        if response.user:
                            st.success("✅ Password updated successfully!")
                        else:
                            st.error("❌ Failed to update password.")
                    else:
                        st.error("❌ Not logged in.")
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
    st.stop()

elif selected_page == "👑 Admin Panel" and ('admin' in user_roles):
    st.markdown('<div class="section-header">👑 Admin Panel</div>', unsafe_allow_html=True)
    tab_admin_users, tab_admin_vehicles = st.tabs(["👥 User Management", "🚗 Vehicle Master Data"])
    with tab_admin_users:
        admin_user_management()
    with tab_admin_vehicles:
        manage_vehicle_master(master_df)
    st.stop()

elif selected_page == "🔧 Vehicle Maintenance":
    if not any(role in user_roles for role in ['maintenance', 'admin']):
        st.error("You do not have permission to view this page.")
        st.stop()
    else:
        view_vehicle_maintenance(master_df, assignments_df, maintenance_df)
    st.stop()

elif selected_page == "📋 Trip Management":
    if not any(role in user_roles for role in ['trip_manager', 'admin']):
        st.error("You do not have permission to view this page.")
        st.stop()
    else:
        show_trip_management(assignments_df, master_df)
    st.stop()

elif selected_page == "📊 KPIs & Analysis":
    if not any(role in user_roles for role in ['analyst', 'admin']):
        st.error("You do not have permission to view this page.")
        st.stop()
    else:
        show_kpis_analysis(assignments_df, master_df, maintenance_df, kpis)
    st.stop()

else:
    st.info("Select a page from the sidebar.")
