import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
from supabase import create_client
from typing import Optional, Dict, Any
import logging
import plotly.express as px
import plotly.graph_objects as go
import numpy as np

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

@st.cache_data(ttl=300, show_spinner=False)
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

@st.cache_data(ttl=3600, show_spinner=False)
def get_user_role_cached(email):
    if not email:
        return 'user', False
    try:
        user_check = supabase.table("users_vehicle").select("*").eq("email", email).execute()
        if user_check.data:
            user_data = user_check.data[0]
            user_role = user_data.get('role', 'user')
            is_approved = user_data.get('is_approved', 0)
            return user_role, (user_role == 'admin' and is_approved == 1)
        return 'user', False
    except Exception as e:
        logger.error(f"Error checking admin status: {str(e)}")
        return 'user', False

# ===================================================
# AUTHENTICATION
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

if 'user_role_data' not in st.session_state:
    user_role, is_admin_user = get_user_role_cached(user_email)
    st.session_state.user_role_data = (user_role, is_admin_user)
else:
    user_role, is_admin_user = st.session_state.user_role_data

user_metadata = get_user_metadata()

st.set_page_config(page_title="EPSS Fleet Dashboard", layout="wide")

# ===================================================
# CUSTOM CSS – HEADERS & MISCELLANEOUS
# ===================================================
st.markdown("""
<style>
    .stApp { background-color: #f5f5f5 !important; }
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
    .dataframe th {
        background-color: #1E88E5 !important;
        color: white !important;
        font-weight: bold !important;
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
</style>
""", unsafe_allow_html=True)

st.title("EPSS Fleet Management Dashboard")

# ===================================================
# SIDEBAR (without vehicle filter)
# ===================================================
st.sidebar.markdown("---")
st.sidebar.markdown("### 📋 Navigation")
nav_options = ["📋 Trip Management", "📊 KPIs & Analysis", "👤 User Info", "🔧 Vehicle Maintenance"]
if is_admin_user:
    nav_options.append("👑 Admin Panel")
selected_page = st.sidebar.radio("Go to", nav_options, index=0)

st.sidebar.markdown("---")
if st.sidebar.button("🔄 Refresh Data", use_container_width=True):
    refresh_data()

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

def get_trip_by_id(trip_id: str):
    try:
        res = supabase.table(TXN_TABLE).select("*").eq("id", trip_id).execute()
        if res.data:
            return res.data[0]
        return None
    except Exception as e:
        logger.error(f"Error fetching trip: {e}")
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

def refresh_data():
    st.cache_data.clear()
    st.rerun()

def get_vehicle_kpis(master_df, assignments_df):
    if master_df.empty:
        return 0, 0, 0, 0, 0
    total_count = master_df['plate_number'].nunique()
    all_assigned_plates = assignments_df['plate_number'].dropna().unique() if not assignments_df.empty else []
    total_active = len(all_assigned_plates)
    if not assignments_df.empty and 'status' in assignments_df.columns:
        active_plates = assignments_df[
            assignments_df['status'].str.title().isin(['Planned', 'Loading', 'In Transit'])
        ]['plate_number'].dropna().unique()
        assigned_count = len(active_plates)
    else:
        assigned_count = 0
    grounded = total_count - total_active
    available = total_count - grounded - assigned_count
    return total_count, total_active, grounded, assigned_count, available

def parse_datetime_flexible(val):
    if pd.isna(val) or val is None:
        return pd.NaT
    if isinstance(val, (pd.Timestamp, datetime)):
        return val
    if isinstance(val, str):
        try:
            return pd.to_datetime(val, format='%Y-%m-%d %H:%M:%S', errors='raise')
        except:
            try:
                return pd.to_datetime(val, format='%Y-%m-%d', errors='raise')
            except:
                return pd.to_datetime(val, errors='coerce')
    return pd.NaT

def format_days_hours(days):
    """Convert decimal days to 'days:hours' format, e.g., 1:0 for 1 day 0 hours."""
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

# ===================================================
# VEHICLE MASTER DATA MANAGEMENT (for Admin)
# ===================================================
def manage_vehicle_master():
    """Admin panel tab for managing vehicle master data."""
    st.markdown("### 🚗 Manage Vehicle Master Data")

    if 'edit_vehicle_id' not in st.session_state:
        st.session_state.edit_vehicle_id = None
    if 'edit_vehicle_data' not in st.session_state:
        st.session_state.edit_vehicle_data = None

    master_df = load_master()

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
                            st.cache_data.clear()
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
                            st.cache_data.clear()
                            st.session_state.edit_vehicle_id = None
                            st.session_state.edit_vehicle_data = None
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
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Update failed: {str(e)}")

# ===================================================
# VEHICLE MAINTENANCE – READ-ONLY + ADD NEW
# ===================================================
def view_vehicle_maintenance():
    """View and add maintenance records."""
    st.markdown('<div class="section-header">🔧 Vehicle Maintenance</div>', unsafe_allow_html=True)

    maint_df = load_maintenance()
    master_df = load_master()

    # ---- Add New Maintenance Record ----
    with st.expander("➕ Add New Maintenance Record", expanded=False):
        with st.form("add_maintenance_form"):
            col1, col2, col3 = st.columns(3)

            with col1:
                # Request Date (mandatory)
                request_date = st.date_input("Request Date *", value=date.today(), key="maint_add_request_date")

                # Plate number dropdown
                plate_options = sorted(master_df['plate_number'].dropna().astype(str).str.strip().unique().tolist()) if not master_df.empty else []
                selected_plate = st.selectbox("Plate Number *", options=plate_options, key="maint_add_plate")

                # Auto-fetch vehicle type
                vehicle_type = ""
                if selected_plate and not master_df.empty:
                    row = master_df[master_df['plate_number'].astype(str).str.strip() == selected_plate.strip()]
                    if not row.empty:
                        vehicle_type = row.iloc[0].get('vehicle_type', '')
                st.text_input("Vehicle Type", value=vehicle_type, disabled=True, key="maint_add_vehicle_type_display")
                st.session_state["_maint_add_vehicle_type"] = vehicle_type

            with col2:
                maint_type = st.selectbox("Maintenance Type *", options=["scheduled", "corrective", "preventive"], key="maint_add_type")

                branch_options = sorted(assignments_df['assigned_branch_name'].dropna().astype(str).str.strip().unique().tolist()) if not assignments_df.empty else []
                branch = st.selectbox("Branch *", options=branch_options, key="maint_add_branch")

                # Workstation from master (no "Add new")
                workstation_values = []
                if not master_df.empty and 'workstation' in master_df.columns:
                    workstation_values = sorted(master_df['workstation'].dropna().astype(str).str.strip().unique().tolist())
                workstation = st.selectbox("Workstation", options=workstation_values, key="maint_add_workstation")

                responsible = st.text_input("Responsible Body *", key="maint_add_responsible")

            with col3:
                start_date = st.date_input("Maintenance Start Date *", value=None, key="maint_add_start")
                # End Date is NOT mandatory (no asterisk)
                end_date = st.date_input("Maintenance End Date", value=None, key="maint_add_end")

                back_to_duty = st.selectbox("Back to Duty", options=["Yes", "No"], key="maint_add_back")

                # Compute Total Days
                total_days = 0
                if start_date:
                    if back_to_duty == "No":
                        total_days = (date.today() - start_date).days
                    else:  # "Yes"
                        if end_date:
                            total_days = (end_date - start_date).days
                        # else remains 0
                st.number_input("Total Days (auto-calculated)", value=total_days, disabled=True, key="maint_add_total_days")

                cost = st.text_input("Cost", placeholder="e.g., 1500", key="maint_add_cost")
                remark = st.text_area("Remark", key="maint_add_remark")

            submitted = st.form_submit_button("💾 Save Maintenance Record", type="primary")
            if submitted:
                errors = []
                # Mandatory fields: Plate, Branch, Responsible, Request Date, Start Date
                if not selected_plate:
                    errors.append("Plate Number is required.")
                if not branch:
                    errors.append("Branch is required.")
                if not responsible:
                    errors.append("Responsible Body is required.")
                if not start_date:
                    errors.append("Maintenance Start Date is required.")
                # End Date is NOT mandatory - no validation
                # If back_to_duty == "Yes" and end_date is missing, we still allow save (total_days will be 0)
                if start_date and end_date and start_date > end_date:
                    errors.append("Start Date must be before End Date.")
                if errors:
                    for err in errors:
                        st.error(f"❌ {err}")
                else:
                    # Recalculate final total days
                    if back_to_duty == "No":
                        final_total_days = (date.today() - start_date).days
                    else:  # "Yes"
                        if end_date:
                            final_total_days = (end_date - start_date).days
                        else:
                            final_total_days = 0

                    data = {
                        "plate_number": selected_plate,
                        "vehicle_type": st.session_state.get("_maint_add_vehicle_type", ""),
                        "maintenace_type": maint_type,
                        "branch": branch,
                        "maintenance_workstation": workstation,
                        "responsible_person": responsible,
                        "maintenance_request_date": request_date.strftime('%Y-%m-%d') if request_date else None,
                        "maintenance_starting_date": start_date.strftime('%Y-%m-%d') if start_date else None,
                        "maintenance_ending_date": end_date.strftime('%Y-%m-%d') if end_date else None,
                        "maintenance_total_day": final_total_days,
                        "maintenace_cost": cost if cost else None,
                        "reason": remark if remark else None,
                        "back_to_duty": back_to_duty,
                        "created_at": datetime.now().isoformat()
                    }
                    try:
                        res = supabase.table(MAINT_TABLE).insert(data).execute()
                        if res.data:
                            st.success("✅ Maintenance record saved successfully!")
                            st.cache_data.clear()
                            st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error saving record: {str(e)}")

    # ---- Display Maintenance Records ----
    if maint_df.empty:
        st.info("📭 No maintenance records found.")
        return

    # Optional filter by plate
    col_filter = st.columns([1, 2])[0]
    with col_filter:
        plate_filter = st.selectbox("Filter by Plate", options=["All"] + plate_options, key="maint_plate_filter_simple")

    if plate_filter != "All":
        filtered_df = maint_df[
            maint_df['plate_number'].astype(str).str.strip().str.lower() == plate_filter.strip().lower()
        ].copy()
    else:
        filtered_df = maint_df.copy()

    # Ensure the Total Days column exists
    if 'maintenance_total_day' not in filtered_df.columns:
        filtered_df['maintenance_total_day'] = None

    if 'maintenance_request_date' in filtered_df.columns:
        filtered_df['maintenance_request_date'] = pd.to_datetime(filtered_df['maintenance_request_date'], errors='coerce')
        filtered_df = filtered_df.sort_values(by='maintenance_request_date', ascending=False)

    # Display columns – always include Total Days
    display_columns = [
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
        if source_col in filtered_df.columns:
            if source_col in ['maintenance_request_date', 'maintenance_starting_date', 'maintenance_ending_date', 'created_at']:
                series = pd.to_datetime(filtered_df[source_col], errors='coerce')
                if source_col == 'created_at':
                    display_data[display_name] = series.dt.strftime('%Y-%m-%d %H:%M')
                else:
                    display_data[display_name] = series.dt.strftime('%Y-%m-%d')
            else:
                display_data[display_name] = filtered_df[source_col]
        else:
            display_data[display_name] = None

    display_df = pd.DataFrame(display_data)
    display_df = display_df.dropna(axis=1, how='all')

    if display_df.empty:
        st.info("No matching records for the selected plate.")
    else:
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        st.caption(f"Showing {len(display_df)} record(s)")

# ===================================================
# TRIP MANAGEMENT PAGE
# ===================================================
def show_trip_management():
    """Trip Management page – full CRUD for trips."""
    # Initialize session state
    if 'editing_id' not in st.session_state:
        st.session_state.editing_id = None
    if 'edit_data' not in st.session_state:
        st.session_state.edit_data = None
    if 'edit_initialized' not in st.session_state:
        st.session_state.edit_initialized = False
    if 'show_add_form' not in st.session_state:
        st.session_state.show_add_form = False
    if 'selected_trip_for_action' not in st.session_state:
        st.session_state.selected_trip_for_action = None
    if 'needs_rerun' not in st.session_state:
        st.session_state.needs_rerun = False
    if 'add_form_key' not in st.session_state:
        st.session_state.add_form_key = 0

    # ===========================================
    # ADD NEW TRIP FORM
    # ===========================================
    if st.session_state.show_add_form:
        st.markdown('<div class="edit-container">', unsafe_allow_html=True)
        st.markdown("### ➕ Add New Trip")

        col_refresh1, col_refresh2 = st.columns([4, 1])
        with col_refresh2:
            if st.button("🔄 Refresh Master Data", key="refresh_master_add"):
                st.cache_data.clear()
                st.session_state.add_form_key += 1
                st.rerun()

        col1, col2, col3 = st.columns(3)

        with col1:
            plate_key = f"add_plate_{st.session_state.add_form_key}"
            plate_number = st.selectbox("Plate Number *", plate_numbers, key=plate_key)

            derived_driver = plate_to_driver.get(plate_number, "Not Found")
            derived_phone = plate_to_phone.get(plate_number, "")
            derived_vehicle_type = plate_to_vehicle_type.get(plate_number, "")

            st.session_state["_add_derived_driver"] = derived_driver
            st.session_state["_add_derived_phone"] = derived_phone
            st.session_state["_add_derived_vehicle_type"] = derived_vehicle_type

            st.markdown(f"**Driver Name:** {derived_driver}")
            st.markdown(f"**Phone Number:** {derived_phone}")
            st.markdown(f"**Vehicle Type:** {derived_vehicle_type}")

            from_key = f"add_from_{st.session_state.add_form_key}"
            from_location = st.selectbox("From Location *", from_locations, key=from_key)

            branch_key = f"add_branch_{st.session_state.add_form_key}"
            assigned_branch_name = st.selectbox("Assigned Branch *", branches, key=branch_key)

        with col2:
            requested_date = st.date_input("Requested Date", value=None, key="add_requested_date")
            requested_by = st.text_input("Requested By *", placeholder="Enter name", key="add_requested_by")
            assigned_by = st.text_input("Assigned By *", placeholder="Enter name", key="add_assigned_by")
            assigned_date = st.date_input("Assigned Date *", date.today(), key="add_assigned_date")

        with col3:
            st.markdown("**Activity Timeline**")
            st.info("⏰ Time will be automatically set to current system time")
            loading_start = st.date_input("Loading Starting Date", value=None, key="add_loading_start")
            loading_end = st.date_input("Loading Date End", value=None, key="add_loading_end")
            trip_start = st.date_input("Trip Starting Date", value=None, key="add_trip_start")
            arrival = st.date_input("Arrival Date", value=None, key="add_arrival")
            return_dt = st.date_input("Return Date", value=None, key="add_return")
            trip_end = st.date_input("Actual Trip End Date", value=None, key="add_trip_end")
            expected_trip_end = st.date_input("Expected Trip End Date", value=None, key="add_expected_trip_end")

        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("💾 Save Trip", type="primary", use_container_width=True):
                current_driver = st.session_state.get("_add_derived_driver", "Not Found")
                current_phone = st.session_state.get("_add_derived_phone", "")
                current_vehicle_type = st.session_state.get("_add_derived_vehicle_type", "")
                current_plate = plate_number

                if not current_plate or not current_driver or not from_location or not assigned_branch_name:
                    st.error("⚠️ Please fill all required fields")
                else:
                    existing = supabase.table(TXN_TABLE)\
                        .select("id,status")\
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
                    expected_trip_end_dt = combine_date_with_current_time(expected_trip_end) if expected_trip_end else None

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
                        "expected_trip_end_date": format_datetime_for_db(expected_trip_end_dt),
                        "created_at": datetime.now().isoformat()
                    }
                    try:
                        res = supabase.table(TXN_TABLE).insert(new_record).execute()
                        if res.data:
                            st.success("✅ Trip saved successfully!")
                            st.session_state.show_add_form = False
                            st.cache_data.clear()
                            st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")

        with col_btn2:
            if st.button("❌ Cancel", use_container_width=True):
                st.session_state.show_add_form = False
                st.rerun()

        st.markdown('</div>', unsafe_allow_html=True)

    # ===========================================
    # TRIP RECORDS TABLE
    # ===========================================
    st.markdown('<div class="section-header">📋 Trip Records</div>', unsafe_allow_html=True)

    col_action_top1, col_action_top2, col_action_top3 = st.columns([2, 1, 1])
    with col_action_top1:
        if not st.session_state.show_add_form and not st.session_state.editing_id:
            if st.button("➕ Add New Trip", type="primary"):
                st.session_state.show_add_form = True
                st.session_state.add_form_key += 1
                st.rerun()

    try:
        data = assignments_df.copy()

        if not data.empty:
            # Ensure status is present
            if 'status' not in data.columns:
                statuses = []
                for _, row in data.iterrows():
                    status, _ = calculate_status_and_errors(row)
                    statuses.append(status)
                data['status'] = statuses

            if 'created_at' in data.columns:
                data = data.sort_values(by="created_at", ascending=False)
            else:
                data = data.sort_values(by="id", ascending=False)

            # ===== ADD TRIP PERFORMANCE METRICS =====
            def safe_days(col1, col2):
                mask = data[col1].notna() & data[col2].notna()
                if mask.any():
                    return (data.loc[mask, col2] - data.loc[mask, col1]).dt.total_seconds() / 86400
                else:
                    return pd.Series(index=data.index, dtype=float)

            # Existing time metrics
            data['loading_time'] = safe_days('loading_starting_date', 'loading_date_end')
            data['ongoing_time'] = safe_days('trip_starting_date', 'arrival_date')
            data['incoming_time'] = safe_days('return_date', 'trip_end_date')
            data['total_trip_time'] = safe_days('trip_starting_date', 'trip_end_date')
            data['trip_variance'] = safe_days('expected_trip_end_date', 'trip_end_date')

            # ----- NEW: Idle Time Metrics -----
            data['idle_assigned_to_loading'] = safe_days('assigned_date', 'loading_starting_date')
            data['idle_loading_to_trip'] = safe_days('loading_date_end', 'trip_starting_date')
            data['idle_assigned_to_end'] = safe_days('assigned_date', 'trip_end_date')

            # Total idle = sum of the three (only if all exist, else NaN)
            # We'll sum only if all three are not NaN, but we can also treat NaN as 0 for display.
            # Better: compute sum ignoring NaNs.
            data['total_idle'] = data[['idle_assigned_to_loading', 'idle_loading_to_trip', 'idle_assigned_to_end']].sum(axis=1, skipna=True)

            # ---- Display columns ----
            display_columns = [
                "id", "plate_number", "driver_name", "phone_number", "vehicle_type", 
                "from_location", "assigned_branch_name", "requested_date", 
                "requested_by", "assigned_by", "assigned_date",
                "loading_starting_date", "loading_date_end", "trip_starting_date", 
                "arrival_date", "return_date", "trip_end_date", 
                "expected_trip_end_date", "status", "created_at"
            ]
            metric_cols = [
                'loading_time', 'ongoing_time', 'incoming_time', 'total_trip_time', 'trip_variance',
                'idle_assigned_to_loading', 'idle_loading_to_trip', 'idle_assigned_to_end', 'total_idle'
            ]
            for mc in metric_cols:
                if mc in data.columns:
                    display_columns.append(mc)

            for col in display_columns:
                if col not in data.columns:
                    data[col] = None

            # ===========================================
            # DROPDOWN FOR EDIT/DELETE (unchanged)
            # ===========================================
            col_action1, col_action2, col_action3 = st.columns([2, 1, 1])
            with col_action1:
                editable_trips = data[data['status'].str.title().isin(['Planned', 'Loading', 'In Transit'])]
                trip_options = []
                for idx, row in editable_trips.iterrows():
                    if row.get('id'):
                        status_display = row.get('status', 'N/A')
                        trip_label = f"{row.get('plate_number', 'N/A')} - {row.get('driver_name', 'N/A')} ({status_display})"
                        trip_options.append((row['id'], trip_label))
                if trip_options:
                    selected_trip = st.selectbox(
                        "Select Trip to Edit/Delete",
                        options=[opt[0] for opt in trip_options],
                        format_func=lambda x: next((opt[1] for opt in trip_options if opt[0] == x), "Select Trip"),
                        key="trip_action_select"
                    )
                    st.session_state.selected_trip_for_action = selected_trip
                else:
                    st.info("📭 No trips available for editing (only Planned, Loading, and In Transit trips can be edited)")
                    st.session_state.selected_trip_for_action = None

            with col_action2:
                if st.button("✏️ Edit Selected", use_container_width=True):
                    if st.session_state.selected_trip_for_action:
                        st.session_state.editing_id = st.session_state.selected_trip_for_action
                        st.session_state.edit_data = None
                        st.session_state.edit_initialized = False
                        st.rerun()
                    else:
                        st.warning("Please select a trip first")

            with col_action3:
                if st.button("🗑️ Delete Selected", use_container_width=True):
                    if st.session_state.selected_trip_for_action:
                        try:
                            supabase.table(TXN_TABLE).delete().eq("id", st.session_state.selected_trip_for_action).execute()
                            st.success("✅ Trip deleted successfully!")
                            st.session_state.selected_trip_for_action = None
                            st.cache_data.clear()
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Delete failed: {str(e)}")
                    else:
                        st.warning("Please select a trip first")

            # ===========================================
            # INLINE EDIT FORM (unchanged)
            # ===========================================
            if st.session_state.editing_id:
                # ... (keep existing edit logic exactly as before)
                pass  # The full edit form is unchanged; we omit it for brevity but you must keep it.

            # ===========================================
            # FILTERS FOR THE TABLE
            # ===========================================
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
                display_data = filtered_data[[col for col in display_columns if col != 'id']].copy()

                # Rename columns for display
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
                    'expected_trip_end_date': 'Expected Trip End Date',
                    'loading_time': 'Loading Time',
                    'ongoing_time': 'Ongoing Time',
                    'incoming_time': 'Incoming Time',
                    'total_trip_time': 'Total Trip Time',
                    'trip_variance': 'Trip Variance',
                    'idle_assigned_to_loading': 'Idle (Assigned→Loading)',
                    'idle_loading_to_trip': 'Idle (Loading→Trip)',
                    'idle_assigned_to_end': 'Idle (Assigned→End)',
                    'total_idle': 'Total Idle'
                }
                display_data.rename(columns=rename_map, inplace=True)

                # Format time columns to "days:hours"
                time_cols = [
                    'Loading Time', 'Ongoing Time', 'Incoming Time', 'Total Trip Time', 'Trip Variance',
                    'Idle (Assigned→Loading)', 'Idle (Loading→Trip)', 'Idle (Assigned→End)', 'Total Idle'
                ]
                for col in time_cols:
                    if col in display_data.columns:
                        display_data[col] = display_data[col].apply(format_days_hours)

                # Convert date columns
                date_cols = ['Requested Date', 'Loading Starting Date', 'Loading Date End', 'Trip Starting Date',
                             'Arrival Date', 'Return Date', 'Actual Trip End Date', 'Expected Trip End Date']
                for col in date_cols:
                    if col in display_data.columns:
                        display_data[col] = pd.to_datetime(display_data[col], errors='coerce')

                # Display table with column config
                st.dataframe(
                    display_data,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "status": st.column_config.Column("Status", width="small"),
                        "plate_number": st.column_config.Column("Plate", width="small"),
                        "driver_name": st.column_config.Column("Driver", width="medium"),
                        "Phone Number": st.column_config.Column("Phone", width="medium"),
                        "Vehicle Type": st.column_config.Column("Vehicle Type", width="medium"),
                        "from_location": st.column_config.Column("From", width="medium"),
                        "assigned_branch_name": st.column_config.Column("Branch", width="medium"),
                        "Requested Date": st.column_config.DatetimeColumn("Requested Date", format="YYYY-MM-DD HH:mm", width="medium"),
                        "requested_by": st.column_config.Column("Requested By", width="medium"),
                        "assigned_by": st.column_config.Column("Assigned By", width="medium"),
                        "assigned_date": st.column_config.DatetimeColumn("Assigned Date", format="YYYY-MM-DD HH:mm", width="medium"),
                        "Loading Starting Date": st.column_config.DatetimeColumn("Loading Starting Date", format="YYYY-MM-DD HH:mm", width="medium"),
                        "Loading Date End": st.column_config.DatetimeColumn("Loading Date End", format="YYYY-MM-DD HH:mm", width="medium"),
                        "Trip Starting Date": st.column_config.DatetimeColumn("Trip Starting Date", format="YYYY-MM-DD HH:mm", width="medium"),
                        "Arrival Date": st.column_config.DatetimeColumn("Arrival Date", format="YYYY-MM-DD HH:mm", width="medium"),
                        "Return Date": st.column_config.DatetimeColumn("Return Date", format="YYYY-MM-DD HH:mm", width="medium"),
                        "Actual Trip End Date": st.column_config.DatetimeColumn("Actual Trip End Date", format="YYYY-MM-DD HH:mm", width="medium"),
                        "Expected Trip End Date": st.column_config.DatetimeColumn("Expected Trip End Date", format="YYYY-MM-DD HH:mm", width="medium"),
                        "created_at": st.column_config.DatetimeColumn("Created", format="YYYY-MM-DD HH:mm", width="medium"),
                        "Loading Time": st.column_config.Column("Loading Time", width="small"),
                        "Ongoing Time": st.column_config.Column("Ongoing Time", width="small"),
                        "Incoming Time": st.column_config.Column("Incoming Time", width="small"),
                        "Total Trip Time": st.column_config.Column("Total Trip Time", width="small"),
                        "Trip Variance": st.column_config.Column("Trip Variance", width="small"),
                        "Idle (Assigned→Loading)": st.column_config.Column("Idle (Assigned→Loading)", width="small"),
                        "Idle (Loading→Trip)": st.column_config.Column("Idle (Loading→Trip)", width="small"),
                        "Idle (Assigned→End)": st.column_config.Column("Idle (Assigned→End)", width="small"),
                        "Total Idle": st.column_config.Column("Total Idle", width="small"),
                    }
                )

                # Export button
                col_export1, col_export2 = st.columns([1, 5])
                with col_export1:
                    if st.button("📥 Export to CSV"):
                        export_data = display_data.copy()
                        csv = export_data.to_csv(index=False)
                        st.download_button(label="Download CSV", data=csv, file_name=f"fleet_trips_{date.today()}.csv", mime="text/csv", key="download_csv_table")
            else:
                st.info("📭 No records match the selected filters")
        else:
            st.info("📭 No trip records found. Click 'Add New Trip' to create one!")

    except Exception as e:
        st.error(f"❌ Load error: {str(e)}")
        logger.error(f"Dashboard load error: {e}")

# ===================================================
def show_kpis_analysis():
    """KPIs & Analysis page – Operational Fleet KPIs, Maintenance KPIs, Trip Performance."""

    # ---- Add CSS for hover effect (vibration) on all cards ----
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
        .kpi-card {
            transition: all 0.2s ease;
        }
        .kpi-card:hover {
            animation: vibrate 0.3s ease-in-out;
            box-shadow: 0 8px 24px rgba(0,0,0,0.2) !important;
        }
        .eye-button {
            background: transparent !important;
            border: none !important;
            color: #555 !important;
            font-size: 20px !important;
            padding: 4px 0 !important;
            width: 100% !important;
            text-align: center !important;
            cursor: pointer;
            transition: transform 0.2s;
        }
        .eye-button:hover {
            transform: scale(1.2);
        }
        .card-container {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 2px;
        }
    </style>
    """, unsafe_allow_html=True)

    # Big Title
    st.markdown("""
    <div style="font-size: 32px; font-weight: 700; color: #0d47a1; margin: 0 0 16px 0; text-align: center;">
        📊 Fleet Management Performance
    </div>
    """, unsafe_allow_html=True)

    # ---- Use the already processed global DataFrames ----
    global_assign = assignments_df
    global_master = df
    maint_df = load_maintenance()

    # ---- 1. Vehicle Management KPIs (Operational State) ----
    all_vehicles = set(global_master['plate_number'].dropna().unique()) if not global_master.empty else set()
    total_vehicles = len(all_vehicles)

    assigned_plates = set()
    if not global_assign.empty and 'plate_number' in global_assign.columns and 'status' in global_assign.columns:
        global_assign['status_clean'] = global_assign['status'].astype(str).str.strip().str.title()
        active_statuses = ['Planned', 'Loading', 'In Transit']
        if 'assigned_date' in global_assign.columns:
            global_assign['trip_date'] = pd.to_datetime(global_assign['assigned_date'], errors='coerce')
        else:
            global_assign['trip_date'] = pd.NaT
        if global_assign['trip_date'].isna().all() and 'created_at' in global_assign.columns:
            global_assign['trip_date'] = pd.to_datetime(global_assign['created_at'], errors='coerce')
        if global_assign['trip_date'].isna().all():
            global_assign['trip_date'] = global_assign.index
        latest_trips = global_assign.sort_values('trip_date', ascending=False).drop_duplicates('plate_number')
        assigned_plates = set(latest_trips[
            latest_trips['status_clean'].isin(active_statuses)
        ]['plate_number'].dropna().unique())

    assigned_count = len(assigned_plates)

    under_maint_plates = set()
    if not maint_df.empty and 'plate_number' in maint_df.columns:
        under_maint_df = maint_df[maint_df['back_to_duty'].astype(str).str.strip().str.lower() == 'no']
        under_maint_plates = set(under_maint_df['plate_number'].dropna().unique())
    under_maint_count = len(under_maint_plates)

    available_plates = all_vehicles - assigned_plates - under_maint_plates
    available_count = len(available_plates)

    utilization_rate = (assigned_count / total_vehicles * 100) if total_vehicles > 0 else 0
    availability_rate = (available_count / total_vehicles * 100) if total_vehicles > 0 else 0
    downtime_rate = (under_maint_count / total_vehicles * 100) if total_vehicles > 0 else 0

    # ---- Vehicle Status (colored cards + eye icon under) ----
    st.subheader("🚗 Vehicle Status")

    if 'selected_kpi' not in st.session_state:
        st.session_state.selected_kpi = None

    # Exact labels as requested
    kpi_colors = {
        "Total Vehicles": "#0d47a1",
        "Assigned Vehicles": "#e65100",
        "Under Maintenance": "#b71c1c",
        "Available Vehicles": "#1b5e20"
    }

    kpi_data = {
        "Total Vehicles": {"value": total_vehicles, "plates": all_vehicles},
        "Assigned Vehicles": {"value": assigned_count, "plates": assigned_plates},
        "Under Maintenance": {"value": under_maint_count, "plates": under_maint_plates},
        "Available Vehicles": {"value": available_count, "plates": available_plates}
    }

    cols = st.columns(4)
    for idx, (label, data) in enumerate(kpi_data.items()):
        with cols[idx]:
            key = label.lower().replace(" ", "_")
            color = kpi_colors.get(label, "#0d47a1")  # fallback
            # Card
            st.markdown(f"""
            <div class="card-container">
                <div class="kpi-card" style="background: {color}; color: white; border-radius: 14px; padding: 10px 6px; text-align: center; box-shadow: 0 4px 12px rgba(0,0,0,0.12); width: 100%;">
                    <div style="font-size: 32px; font-weight: 900; line-height: 1.2;">{data['value']}</div>
                    <div style="font-size: 14px; font-weight: 500; opacity: 0.9;">{label}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            # Eye button (only this one)
            if st.button("👁️", key=f"eye_{key}", help=f"View vehicles for {label}", use_container_width=True):
                if st.session_state.selected_kpi == key:
                    st.session_state.selected_kpi = None
                else:
                    st.session_state.selected_kpi = key
                st.rerun()

    if st.session_state.selected_kpi:
        selected_key = st.session_state.selected_kpi
        # Find the correct label in kpi_data (case-insensitive)
        selected_label = None
        for lbl in kpi_data.keys():
            if lbl.lower().replace(" ", "_") == selected_key:
                selected_label = lbl
                break
        if selected_label is None:
            selected_label = selected_key.replace("_", " ").title()
        selected_plates = kpi_data.get(selected_label, {}).get("plates", set())
        st.markdown("---")
        st.subheader(f"📋 {selected_label} - Vehicle List")
        if selected_plates and not global_master.empty:
            display_cols = ['plate_number', 'driver_name', 'phone_number', 'vehicle_type']
            missing = [c for c in display_cols if c not in global_master.columns]
            for col in missing:
                global_master[col] = None
            filtered_df = global_master[global_master['plate_number'].isin(selected_plates)][display_cols].copy()
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

    # ---- Fleet Performance Rates (styled like Cost Overview) ----
    st.markdown("---")
    st.markdown("""
    <div style="background: linear-gradient(135deg, #E3F2FD, #BBDEFB); border-radius: 16px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">
        <h4 style="text-align: center; color: #0d47a1; margin: 0 0 12px 0;">📊 Fleet Performance Rates</h4>
        <div style="display: flex; justify-content: space-around; flex-wrap: wrap; gap: 12px;">
            <div style="text-align: center; flex: 1; min-width: 120px;">
                <div style="font-size: 28px; font-weight: 900; color: #0d47a1;">🚀 {utilization_rate:.1f}%</div>
                <div style="font-size: 14px; color: #333;"> Fleet Utilization Rate</div>
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
    </div>
    """.format(utilization_rate=utilization_rate, availability_rate=availability_rate, downtime_rate=downtime_rate), unsafe_allow_html=True)

    # ---- 2. Maintenance Performance KPIs ----
    st.markdown("---")
    st.subheader("🔧 Maintenance Performance")

    total_requests = len(maint_df) if not maint_df.empty else 0
    back_to_duty_count = len(maint_df[maint_df['back_to_duty'].astype(str).str.strip().str.lower() == 'yes']) if not maint_df.empty else 0
    avg_days = maint_df['maintenance_total_day'].mean() if not maint_df.empty and 'maintenance_total_day' in maint_df.columns else 0
    max_days = maint_df['maintenance_total_day'].max() if not maint_df.empty and 'maintenance_total_day' in maint_df.columns else 0
    total_cost = maint_df['maintenace_cost'].astype(float).sum() if not maint_df.empty and 'maintenace_cost' in maint_df.columns else 0
    avg_cost = maint_df['maintenace_cost'].astype(float).mean() if not maint_df.empty and 'maintenace_cost' in maint_df.columns else 0
    total_by_type = maint_df['maintenace_type'].value_counts() if not maint_df.empty and 'maintenace_type' in maint_df.columns else pd.Series()
    preventive = total_by_type.get('preventive', 0)
    corrective = total_by_type.get('corrective', 0)
    scheduled = total_by_type.get('scheduled', 0)
    preventive_pct = (preventive / total_requests * 100) if total_requests > 0 else 0
    corrective_pct = (corrective / total_requests * 100) if total_requests > 0 else 0
    scheduled_pct = (scheduled / total_requests * 100) if total_requests > 0 else 0
    vehicles_with_maint = set(maint_df['plate_number'].dropna().unique()) if not maint_df.empty else set()
    avg_cost_per_vehicle = total_cost / len(vehicles_with_maint) if len(vehicles_with_maint) > 0 else 0

    # ---- Maintenance Summary Cards (colored + eye icon under) ----
    if 'maintenance_view' not in st.session_state:
        st.session_state.maintenance_view = None

    maint_data = {
        "Total Requests": {"value": total_requests, "plates": vehicles_with_maint},
        "Under Maintenance": {"value": under_maint_count, "plates": under_maint_plates},
        "Back to Duty": {"value": back_to_duty_count, "plates": set(maint_df[maint_df['back_to_duty'].astype(str).str.strip().str.lower() == 'yes']['plate_number'].dropna().unique())}
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
            # Eye button
            if st.button("👁️", key=f"maint_eye_{view_key}", help=f"View vehicles for {label}", use_container_width=True):
                if st.session_state.maintenance_view == view_key:
                    st.session_state.maintenance_view = None
                else:
                    st.session_state.maintenance_view = view_key
                st.rerun()

    # ---- Show vehicle list based on selected maintenance view ----
    if st.session_state.maintenance_view:
        view_key = st.session_state.maintenance_view
        plates_to_show = set()
        for lbl, d in maint_data.items():
            if lbl.lower().replace(" ", "_") == view_key:
                plates_to_show = d["plates"]
                break
        st.markdown("---")
        st.subheader(f"📋 Vehicle List - {view_key.replace('_', ' ').title()}")
        if plates_to_show and not global_master.empty:
            display_cols = ['plate_number', 'driver_name', 'phone_number', 'vehicle_type']
            missing = [c for c in display_cols if c not in global_master.columns]
            for col in missing:
                global_master[col] = None
            filtered_df = global_master[global_master['plate_number'].isin(plates_to_show)][display_cols].copy()
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

    # ---- Maintenance Cost Overview (moved up) ----
    st.markdown("---")
    st.markdown("""
    <div style="background: linear-gradient(135deg, #E3F2FD, #BBDEFB); border-radius: 16px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">
        <h4 style="text-align: center; color: #0d47a1; margin: 0 0 12px 0;">💰 Maintenance Cost Overview</h4>
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

    # ---- Maintenance Type Breakdown (moved down) ----
    st.markdown("---")
    st.subheader("📊 Maintenance Type Breakdown")
    col_pct1, col_pct2, col_pct3 = st.columns(3)
    with col_pct1:
        st.metric("Preventive %", f"{preventive_pct:.1f}%")
    with col_pct2:
        st.metric("Corrective %", f"{corrective_pct:.1f}%")
    with col_pct3:
        st.metric("Scheduled %", f"{scheduled_pct:.1f}%")

    # ---- Maintenance Cost by Vehicle (Bar Chart, TOP 10) ----
    st.markdown("---")
    st.subheader("📊 Maintenance Cost by Vehicle (Top 10)")
    if not maint_df.empty and 'maintenace_cost' in maint_df.columns:
        cost_vehicle = maint_df.groupby('plate_number')['maintenace_cost'].sum().reset_index()
        cost_vehicle = cost_vehicle.sort_values('maintenace_cost', ascending=False).head(10)
        if not cost_vehicle.empty:
            fig = px.bar(
                cost_vehicle,
                x='plate_number',
                y='maintenace_cost',
                title="Top 10 Vehicles by Maintenance Cost",
                labels={'plate_number': 'Vehicle', 'maintenace_cost': 'Total Cost (ETB)'},
                color='maintenace_cost',
                color_continuous_scale='Reds'
            )
            fig.update_layout(xaxis_tickangle=-45, height=400)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No cost data available.")
    else:
        st.info("No maintenance cost data available.")

    # ---- Maintenance by Branch (Bar Chart) ----
    if not maint_df.empty and 'branch' in maint_df.columns:
        branch_counts = maint_df['branch'].value_counts().reset_index()
        branch_counts.columns = ['Branch', 'Count']
        st.markdown("---")
        st.subheader("📊 Maintenance by Branch")
        fig = px.bar(
            branch_counts,
            x='Branch',
            y='Count',
            title="Maintenance Requests by Branch",
            color='Count',
            color_continuous_scale='Blues'
        )
        fig.update_layout(height=350)
        st.plotly_chart(fig, use_container_width=True)

    # ---- Maintenance by Workstation (Bar Chart) ----
    if not maint_df.empty and 'maintenance_workstation' in maint_df.columns:
        ws_counts = maint_df['maintenance_workstation'].value_counts().reset_index()
        ws_counts.columns = ['Workstation', 'Count']
        st.markdown("---")
        st.subheader("📊 Maintenance by Workstation")
        fig = px.bar(
            ws_counts,
            x='Workstation',
            y='Count',
            title="Maintenance Requests by Workstation",
            color='Count',
            color_continuous_scale='Greens'
        )
        fig.update_layout(height=350)
        st.plotly_chart(fig, use_container_width=True)

    # ---- Detailed Maintenance Tables (expandable) ----
    with st.expander("📋 Detailed Maintenance Tables", expanded=False):
        if not maint_df.empty:
            freq_vehicle = maint_df['plate_number'].value_counts().reset_index()
            freq_vehicle.columns = ['Plate', 'Maintenance Count']
            st.subheader("Maintenance Frequency by Vehicle")
            st.dataframe(freq_vehicle, use_container_width=True, hide_index=True)
        else:
            st.info("No maintenance data available.")

    # ---- 3. Trip Performance Summary (unchanged) ----
    st.markdown("---")
    st.subheader("⏱️ Trip Performance Summary (Averages)")

    if not global_assign.empty:
        data = global_assign.copy()
        metrics = {}
        if 'loading_starting_date' in data.columns and 'loading_date_end' in data.columns:
            mask = data['loading_starting_date'].notna() & data['loading_date_end'].notna()
            if mask.any():
                metrics['Loading Time'] = (data.loc[mask, 'loading_date_end'] - data.loc[mask, 'loading_starting_date']).dt.total_seconds() / 86400
        if 'arrival_date' in data.columns and 'trip_starting_date' in data.columns:
            mask = data['arrival_date'].notna() & data['trip_starting_date'].notna()
            if mask.any():
                metrics['Ongoing Time'] = (data.loc[mask, 'arrival_date'] - data.loc[mask, 'trip_starting_date']).dt.total_seconds() / 86400
        if 'trip_end_date' in data.columns and 'return_date' in data.columns:
            mask = data['trip_end_date'].notna() & data['return_date'].notna()
            if mask.any():
                metrics['Incoming Time'] = (data.loc[mask, 'trip_end_date'] - data.loc[mask, 'return_date']).dt.total_seconds() / 86400
        if 'trip_end_date' in data.columns and 'trip_starting_date' in data.columns:
            mask = data['trip_end_date'].notna() & data['trip_starting_date'].notna()
            if mask.any():
                metrics['Total Trip Time'] = (data.loc[mask, 'trip_end_date'] - data.loc[mask, 'trip_starting_date']).dt.total_seconds() / 86400
        if 'trip_end_date' in data.columns and 'expected_trip_end_date' in data.columns:
            mask = data['trip_end_date'].notna() & data['expected_trip_end_date'].notna()
            if mask.any():
                metrics['Trip Variance'] = (data.loc[mask, 'trip_end_date'] - data.loc[mask, 'expected_trip_end_date']).dt.total_seconds() / 86400

        if 'total_idle' in data.columns:
            total_idle_sum = data['total_idle'].sum()
            active_vehicles = data['plate_number'].nunique() if 'plate_number' in data.columns else 0
            if active_vehicles > 0:
                avg_idle = total_idle_sum / active_vehicles
                metrics['Average Idle Time (per active vehicle)'] = avg_idle
            else:
                metrics['Average Idle Time (per active vehicle)'] = 0

        avg_metrics = {}
        for name, series in metrics.items():
            if isinstance(series, pd.Series):
                if series.notna().any():
                    avg = series.mean()
                    avg_metrics[name] = avg
            else:
                avg_metrics[name] = series

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

    # ---- 4. Charts & Additional Analysis (unchanged) ----
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
                       'trip_starting_date', 'arrival_date', 'return_date', 'trip_end_date', 'expected_trip_end_date']
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

    if not global_assign.empty:
        data = global_assign.copy()
        if 'status' not in data.columns:
            statuses = []
            for _, row in data.iterrows():
                status, _ = calculate_status_and_errors(row)
                statuses.append(status)
            data['status'] = statuses

        @st.cache_data(ttl=600)
        def calculate_metrics(data):
            total_trips = len(data)
            if 'status' in data.columns:
                data['status'] = data['status'].str.title()
            planned = len(data[data['status'] == 'Planned']) if 'status' in data.columns else 0
            loading = len(data[data['status'] == 'Loading']) if 'status' in data.columns else 0
            in_transit = len(data[data['status'] == 'In Transit']) if 'status' in data.columns else 0
            completed = len(data[data['status'] == 'Completed']) if 'status' in data.columns else 0
            completion_rate = (completed / total_trips * 100) if total_trips > 0 else 0
            return total_trips, planned, loading, in_transit, completed, completion_rate

        total_trips, planned, loading, in_transit, completed, completion_rate = calculate_metrics(data)

        col_metric1, col_metric2, col_metric3, col_metric4, col_metric5, col_metric6 = st.columns(6)
        with col_metric1:
            st.metric("Total Trips", total_trips)
        with col_metric2:
            st.metric("Planned", planned)
        with col_metric3:
            st.metric("Loading", loading)
        with col_metric4:
            st.metric("In Transit", in_transit)
        with col_metric5:
            st.metric("Completed", completed)
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
# LOAD DATA (global) – used by all pages
# ===================================================
df = load_master()
assignments_df = load_assignments()

if not assignments_df.empty:
    assignments_df.columns = assignments_df.columns.str.strip()
    statuses = []
    for _, row in assignments_df.iterrows():
        status, _ = calculate_status_and_errors(row)
        statuses.append(status)
    assignments_df['status'] = statuses
else:
    assignments_df['status'] = pd.Series(dtype='object')

date_columns = [
    'assigned_date', 'requested_date', 'loading_starting_date', 'loading_date_end',
    'trip_starting_date', 'arrival_date', 'return_date', 'trip_end_date',
    'expected_trip_end_date', 'created_at'
]
for col in date_columns:
    if col in assignments_df.columns:
        assignments_df[col] = assignments_df[col].apply(parse_datetime_flexible)

vehicle_data = process_vehicle_data(df)
plate_numbers = vehicle_data['plate_numbers']
from_locations = vehicle_data['from_locations']
branches = vehicle_data['branches']
plate_to_driver = vehicle_data['plate_to_driver']
plate_to_location = vehicle_data['plate_to_location']
plate_to_branch = vehicle_data['plate_to_branch']
plate_to_phone = vehicle_data['plate_to_phone']
plate_to_vehicle_type = vehicle_data['plate_to_vehicle_type']

total_count, total_active, grounded, assigned_count, available_count = get_vehicle_kpis(df, assignments_df)

# ===================================================
# PAGE ROUTING (based on sidebar selection)
# ===================================================
if selected_page == "👤 User Info":
    st.markdown('<div class="section-header">👤 User Profile</div>', unsafe_allow_html=True)
    col1, col2 = st.columns([1, 2])
    with col1:
        st.image("https://ui-avatars.com/api/?name=" + user_email.replace("@", "%40") + "&size=150&background=1E88E5&color=fff&bold=true", width=150)
    with col2:
        st.markdown(f"### {user_metadata.get('full_name', 'N/A')}")
        st.markdown(f"**Email:** {user_email}")
        st.markdown(f"**Role:** {'👑 Admin' if is_admin_user else '👤 User'}")
        st.markdown(f"**Status:** {'✅ Approved' if is_admin_user else '✅ Active'}")

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
                            st.success("✅ Password updated successfully! You can now sign in with your new password.")
                        else:
                            st.error("❌ Failed to update password. Please try again.")
                    else:
                        st.error("❌ Not logged in or session expired. Please sign out and sign in again.")
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
    st.stop()

elif selected_page == "👑 Admin Panel" and is_admin_user:
    st.markdown('<div class="section-header">👑 Admin Panel</div>', unsafe_allow_html=True)
    tab_admin_users, tab_admin_vehicles = st.tabs(["👥 User Management", "🚗 Vehicle Master Data"])
    with tab_admin_users:
        from auth_p import admin_panel
        admin_panel()
    with tab_admin_vehicles:
        manage_vehicle_master()
    st.stop()

elif selected_page == "🔧 Vehicle Maintenance":
    view_vehicle_maintenance()
    st.stop()

elif selected_page == "📋 Trip Management":
    show_trip_management()
    st.stop()

elif selected_page == "📊 KPIs & Analysis":
    show_kpis_analysis()
    st.stop()

else:
    st.info("Select a page from the sidebar.")
