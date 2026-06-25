
import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
from supabase import create_client
from typing import Optional, Dict, Any
import logging
import plotly.express as px
import plotly.graph_objects as go
import time

# ===================================================
# AUTHENTICATION SETUP
# ===================================================
from auth import (
    setup_auth,
    get_user_email,
    get_user_metadata,
    sign_out,
    get_user_role,
    is_admin,
    admin_panel,
    get_current_user,
    is_authenticated,
    get_all_users,
    get_pending_users,
    approve_user,
    reject_user,
    update_password
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Setup authentication - This will show login if not authenticated
authenticated = setup_auth()
if not authenticated:
    st.stop()

# ===================================================
# GET USER INFO - MULTIPLE METHODS
# ===================================================
user_email = None

# Method 1: Try get_user_email
try:
    user_email = get_user_email()
except:
    pass

# Method 2: Try session state
if not user_email:
    user_email = st.session_state.get("user_email", None)

# Method 3: Try get_current_user
if not user_email:
    try:
        current_user = get_current_user()
        if current_user and current_user.user:
            user_email = current_user.user.email
            st.session_state["user_email"] = user_email
    except:
        pass

# Method 4: Try Supabase directly
if not user_email:
    try:
        supabase_temp = create_client(
            "https://etjfrptbjecafupbbase.supabase.co",
            "sb_publishable_j0JwaJAJBuJO79-xh7RkYg_PFKqLK1H"
        )
        user = supabase_temp.auth.get_user()
        if user and user.user:
            user_email = user.user.email
            st.session_state["user_email"] = user_email
    except:
        pass

# Get user metadata
user_metadata = get_user_metadata()

# ===================================================
# DIRECT ADMIN CHECK FROM DATABASE
# ===================================================
user_role = 'user'
is_admin_user = False

if user_email:
    try:
        supabase_admin = create_client(
            "https://etjfrptbjecafupbbase.supabase.co",
            "sb_publishable_j0JwaJAJBuJO79-xh7RkYg_PFKqLK1H"
        )

        # Check if user exists in users_vehicle
        user_check = supabase_admin.table("users_vehicle").select("*").eq("email", user_email).execute()

        if user_check.data:
            user_data = user_check.data[0]
            user_role = user_data.get('role', 'user')
            is_approved = user_data.get('is_approved', 0)

            # If user is admin and approved, set as admin
            if user_role == 'admin' and is_approved == 1:
                is_admin_user = True

    except Exception as e:
        st.error(f"Error checking admin status: {str(e)}")

# ===================================================
# SIDEBAR - Navigation
# ===================================================
st.sidebar.markdown("---")
st.sidebar.markdown("### 👤 User Info")
st.sidebar.markdown(f"**Email:** {user_email}")
if user_metadata:
    st.sidebar.markdown(f"**Name:** {user_metadata.get('full_name', 'N/A')}")
st.sidebar.markdown(f"**Role:** {'👑 Admin' if is_admin_user else '👤 User'}")

st.sidebar.markdown("---")
st.sidebar.markdown("### 📋 Navigation")

# Navigation options - Admin Panel is a separate page
nav_options = ["📋 Trip Management", "📊 KPIs & Analysis"]
if is_admin_user:
    nav_options.append("👑 Admin Panel")

selected_page = st.sidebar.radio("Go to", nav_options, index=0)

st.sidebar.markdown("---")

# ===================================================
# PASSWORD CHANGE OPTION IN SIDEBAR
# ===================================================
st.sidebar.markdown("### 🔐 Account Settings")
with st.sidebar.expander("Change Password", expanded=False):
    with st.form("change_password_form"):
        current_password = st.text_input("Current Password", type="password", placeholder="Enter current password")
        new_password = st.text_input("New Password", type="password", placeholder="Enter new password (min 6 chars)")
        confirm_password = st.text_input("Confirm New Password", type="password", placeholder="Confirm new password")

        submit_password = st.form_submit_button("Update Password", type="primary", use_container_width=True)

        if submit_password:
            if not current_password or not new_password or not confirm_password:
                st.error("⚠️ Please fill in all fields")
            elif new_password != confirm_password:
                st.error("⚠️ New passwords do not match")
            elif len(new_password) < 6:
                st.error("⚠️ Password must be at least 6 characters")
            else:
                result = update_password(current_password, new_password)
                if result["success"]:
                    st.success("✅ Password updated successfully!")
                    st.info("Please login again with your new password.")
                    time.sleep(2)
                    sign_out()
                    st.session_state["authenticated"] = False
                    st.session_state["user_email"] = None
                    st.rerun()
                else:
                    st.error(f"❌ {result.get('error', 'Password update failed')}")

st.sidebar.markdown("---")

if st.sidebar.button("🚪 Sign Out", use_container_width=True):
    if sign_out():
        st.session_state["authenticated"] = False
        st.session_state["user_email"] = None
        st.rerun()

st.sidebar.markdown("---")

# ===================================================
# 1. Connect to Supabase
# ===================================================
url = "https://etjfrptbjecafupbbase.supabase.co"
key = "sb_publishable_j0JwaJAJBuJO79-xh7RkYg_PFKqLK1H"
supabase = create_client(url, key)

st.set_page_config(page_title="Fleet Dashboard", layout="wide")

# ===================================================
# CUSTOM CSS
# ===================================================
st.markdown("""
<style>
    .main { padding: 0rem 1rem; }
    .section-header {
        background: linear-gradient(90deg, #4CAF50, #45a049);
        color: white;
        padding: 0.5rem 1rem;
        border-radius: 8px;
        margin: 1rem 0;
    }
    .status-planned {
        background-color: #2196F3;
        color: white;
        padding: 2px 10px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: bold;
        display: inline-block;
    }
    .status-transit {
        background-color: #FF9800;
        color: white;
        padding: 2px 10px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: bold;
        display: inline-block;
    }
    .status-completed {
        background-color: #4CAF50;
        color: white;
        padding: 2px 10px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: bold;
        display: inline-block;
    }
    .stButton button {
        border-radius: 8px;
        font-weight: 500;
        transition: all 0.3s;
    }
    .stButton button:hover {
        transform: scale(1.02);
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
    }
    .dataframe {
        border-radius: 10px;
        overflow: hidden;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    .dataframe th {
        background-color: #4CAF50 !important;
        color: white !important;
        font-weight: bold !important;
    }
    .dataframe tr:hover {
        background-color: #f5f5f5 !important;
    }
    .edit-container {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 10px;
        border-left: 5px solid #4CAF50;
        margin: 1rem 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)

st.title("🚚 Supply Chain Fleet Control Dashboard")

# ===================================================
# PAGE ROUTING
# ===================================================
if selected_page == "👑 Admin Panel":
    # ===========================================
    # ADMIN PANEL PAGE (Separate page in sidebar)
    # ===========================================
    if not is_admin_user:
        st.error("⚠️ You don't have permission to access this page.")
        st.stop()

    st.markdown('<div class="section-header">👑 Admin Panel - User Management</div>', unsafe_allow_html=True)

    all_users = get_all_users()
    pending_users = get_pending_users()

    # Display statistics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Users", len(all_users))
    with col2:
        st.metric("Pending Approval", len(pending_users))
    with col3:
        admins = len([u for u in all_users if u.get('role') == 'admin'])
        st.metric("Admins", admins)

    # Show pending approvals
    if pending_users:
        st.subheader("📋 Pending Approvals")
        for user in pending_users:
            with st.container(border=True):
                col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
                with col1:
                    st.markdown(f"**Name:** {user.get('full_name', 'N/A')}")
                with col2:
                    st.markdown(f"**Email:** {user.get('email', 'N/A')}")
                with col3:
                    if st.button("✅ Approve", key=f"approve_{user['id']}"):
                        result = approve_user(user['id'])
                        if result["success"]:
                            st.success(f"User {user.get('email')} approved!")
                            st.cache_data.clear()
                            st.rerun()
                with col4:
                    if st.button("❌ Reject", key=f"reject_{user['id']}"):
                        result = reject_user(user['id'])
                        if result["success"]:
                            st.warning(f"User {user.get('email')} rejected.")
                            st.cache_data.clear()
                            st.rerun()
    else:
        st.info("✅ No pending approvals")

    # Show all users
    if all_users:
        st.subheader("📊 All Users")
        users_df = pd.DataFrame(all_users)
        display_cols = ['id', 'email', 'full_name', 'role', 'is_approved', 'created_at']
        available_cols = [col for col in display_cols if col in users_df.columns]
        st.dataframe(users_df[available_cols], use_container_width=True, hide_index=True)

    st.stop()

else:
    # ===========================================
    # MAIN CONTENT - Trip Management & KPIs as Tabs
    # ===========================================
    MASTER_TABLE = "vehicle_master_data"
    TXN_TABLE = "vehicle_assignments"

    # ===================================================
    # CACHE MANAGEMENT
    # ===================================================
    @st.cache_data(ttl=300, show_spinner=False)
    def load_master():
        try:
            res = supabase.table(MASTER_TABLE).select("*").execute()
            df = pd.DataFrame(res.data)
            return df
        except Exception as e:
            logger.error(f"Failed to load master data: {e}")
            return pd.DataFrame()

    @st.cache_data(ttl=120, show_spinner=False)
    def load_assignments():
        try:
            res = supabase.table(TXN_TABLE).select("*").execute()
            df = pd.DataFrame(res.data)
            return df
        except Exception as e:
            logger.error(f"Failed to load assignments: {e}")
            return pd.DataFrame()

    def validate_date_sequence(dates: Dict[str, Any]) -> tuple:
        try:
            date_objects = {}
            for key, value in dates.items():
                if isinstance(value, date):
                    date_objects[key] = value
                elif isinstance(value, str):
                    date_objects[key] = datetime.strptime(value, '%Y-%m-%d').date()
                else:
                    date_objects[key] = value

            if date_objects.get('loading_start') and date_objects.get('loading_end'):
                if date_objects['loading_start'] > date_objects['loading_end']:
                    return False, "Loading start date cannot be after end date"
            if date_objects.get('trip_start') and date_objects.get('trip_end'):
                if date_objects['trip_start'] > date_objects['trip_end']:
                    return False, "Trip start date cannot be after end date"
            if date_objects.get('arrival') and date_objects.get('return_date'):
                if date_objects['arrival'] > date_objects['return_date']:
                    return False, "Arrival date cannot be after return date"
            return True, "Valid dates"
        except Exception as e:
            return False, f"Date validation error: {str(e)}"

    def add_master_vehicle(plate_number: str, driver_name: str, from_location: str, assigned_branch_name: str) -> bool:
        try:
            new_vehicle = {
                "plate_number": plate_number,
                "driver_name": driver_name,
                "from_location": from_location,
                "assigned_branch_name": assigned_branch_name
            }
            res = supabase.table(MASTER_TABLE).insert(new_vehicle).execute()
            if res.data:
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to add vehicle: {e}")
            return False

    def get_trip_by_id(trip_id: str):
        try:
            res = supabase.table(TXN_TABLE).select("*").eq("id", trip_id).execute()
            if res.data:
                return res.data[0]
            return None
        except Exception as e:
            logger.error(f"Error fetching trip: {e}")
            return None

    def parse_date(date_str):
        if not date_str:
            return date.today()
        try:
            return datetime.strptime(date_str, '%Y-%m-%d').date()
        except:
            return date.today()

    # ===================================================
    # LOAD MASTER DATA
    # ===================================================
    df = load_master()

    if df.empty:
        st.warning("⚠️ No vehicles found in master data. Please add vehicles first.")
        with st.expander("🚗 Add New Vehicle to Master Data", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                new_plate = st.text_input("Plate Number", placeholder="e.g., ABC-1234")
                new_driver = st.text_input("Driver Name", placeholder="e.g., John Doe")
            with col2:
                new_from = st.text_input("From Location", placeholder="e.g., Warehouse A")
                new_branch = st.text_input("Assigned Branch", placeholder="e.g., Branch 1")
            if st.button("➕ Add Vehicle", type="primary"):
                if new_plate and new_driver and new_from and new_branch:
                    if add_master_vehicle(new_plate, new_driver, new_from, new_branch):
                        st.success(f"✅ Vehicle {new_plate} added successfully!")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error("❌ Failed to add vehicle. Please check the data.")
                else:
                    st.warning("⚠️ Please fill all fields.")
        st.stop()

    # ===================================================
    # CLEAN MASTER DATA
    # ===================================================
    df.columns = df.columns.str.strip()

    plate_numbers = sorted(df["plate_number"].dropna().unique().tolist())
    from_locations = sorted(df["from_location"].dropna().unique().tolist())
    branches = sorted(df["assigned_branch_name"].dropna().unique().tolist())

    plate_to_driver = dict(zip(df["plate_number"], df["driver_name"]))
    plate_to_location = dict(zip(df["plate_number"], df["from_location"]))
    plate_to_branch = dict(zip(df["plate_number"], df["assigned_branch_name"]))

    # ===================================================
    # TABS: Trip Management & KPIs
    # ===================================================
    tab1, tab2 = st.tabs(["📋 Trip Management", "📊 KPIs & Analysis"])

    # ===================================================
    # TAB 1: TRIP MANAGEMENT
    # ===================================================
    with tab1:
        # Initialize session state
        if 'editing_id' not in st.session_state:
            st.session_state.editing_id = None
        if 'edit_data' not in st.session_state:
            st.session_state.edit_data = None
        if 'show_add_form' not in st.session_state:
            st.session_state.show_add_form = False
        if 'selected_trip_for_action' not in st.session_state:
            st.session_state.selected_trip_for_action = None

        # ===========================================
        # ADD NEW TRIP FORM - Using form to prevent reruns
        # ===========================================
        if st.session_state.show_add_form:
            st.markdown('<div class="edit-container">', unsafe_allow_html=True)
            st.markdown("### ➕ Add New Trip")

            with st.form(key="add_trip_form"):
                col1, col2, col3 = st.columns(3)

                with col1:
                    plate_number = st.selectbox("Plate Number *", plate_numbers, key="add_plate")
                    derived_driver = plate_to_driver.get(plate_number, "Not Found")
                    st.markdown(f"**Driver Name:** {derived_driver}")
                    from_location = st.selectbox("From Location *", from_locations, key="add_from")
                    assigned_branch_name = st.selectbox("Assigned Branch *", branches, key="add_branch")

                with col2:
                    assigned_by = st.text_input("Assigned By *", placeholder="Enter name", key="add_assigned_by")
                    requested_by = st.text_input("Requested By *", placeholder="Enter name", key="add_requested_by")
                    assigned_date = st.date_input("Assigned Date *", date.today(), key="add_assigned_date")
                    status = st.selectbox("Status *", ["Planned", "In Transit", "Completed"], key="add_status")

                with col3:
                    st.markdown("**Activity Timeline**")
                    loading_start = st.date_input("Loading Started", date.today(), key="add_loading_start")
                    loading_end = st.date_input("Loading Completed", date.today(), key="add_loading_end")
                    trip_start = st.date_input("Departure Date", date.today(), key="add_trip_start")
                    arrival = st.date_input("Arrival Date", date.today(), key="add_arrival")
                    return_dt = st.date_input("Return Date", date.today(), key="add_return")
                    trip_end = st.date_input("Trip Completed", date.today(), key="add_trip_end")

                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    save_clicked = st.form_submit_button("💾 Save Trip", type="primary", use_container_width=True)
                    if save_clicked:
                        current_driver = derived_driver
                        current_plate = plate_number

                        if not current_plate or not current_driver or not from_location or not assigned_branch_name:
                            st.error("⚠️ Please fill all required fields")
                        else:
                            new_record = {
                                "plate_number": current_plate,
                                "driver_name": current_driver,
                                "from_location": from_location,
                                "assigned_branch_name": assigned_branch_name,
                                "assigned_by": assigned_by,
                                "requested_by": requested_by,
                                "assigned_date": str(assigned_date),
                                "status": status,
                                "loading_starting_date": str(loading_start),
                                "loading_date_end": str(loading_end),
                                "trip_starting_date": str(trip_start),
                                "arrival_date": str(arrival),
                                "return_date": str(return_dt),
                                "trip_end_date": str(trip_end),
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
                    cancel_clicked = st.form_submit_button("❌ Cancel", use_container_width=True)
                    if cancel_clicked:
                        st.session_state.show_add_form = False
                        st.rerun()

            st.markdown('</div>', unsafe_allow_html=True)

        # ===========================================
        # TRIP RECORDS TABLE
        # ===========================================
        st.markdown('<div class="section-header">📋 Trip Records</div>', unsafe_allow_html=True)

        if not st.session_state.show_add_form and not st.session_state.editing_id:
            if st.button("➕ Add New Trip", type="primary"):
                st.session_state.show_add_form = True
                st.rerun()

        try:
            data = load_assignments()

            if not data.empty:
                data.columns = data.columns.str.strip()

                if 'created_at' in data.columns:
                    data = data.sort_values(by="created_at", ascending=False)
                else:
                    data = data.sort_values(by="id", ascending=False)

                display_columns = [
                    "id",
                    "plate_number",
                    "driver_name",
                    "from_location",
                    "assigned_branch_name",
                    "assigned_by",
                    "assigned_date",
                    "loading_starting_date",
                    "requested_by",
                    "loading_date_end",
                    "trip_starting_date",
                    "arrival_date",
                    "return_date",
                    "trip_end_date",
                    "status",
                    "created_at"
                ]

                for col in display_columns:
                    if col not in data.columns:
                        data[col] = None

                plate_groups = data.groupby('plate_number')
                st.info(f"📊 Total Records: {len(data)} | Unique Vehicles: {len(plate_groups)}")

                # ===========================================
                # DROPDOWN FOR EDIT/DELETE - Using form to prevent reruns
                # ===========================================
                with st.form(key="action_form"):
                    col_action1, col_action2, col_action3 = st.columns([2, 1, 1])
                    with col_action1:
                        trip_options = []
                        for idx, row in data.iterrows():
                            if row.get('id'):
                                trip_label = f"{row.get('plate_number', 'N/A')} - {row.get('driver_name', 'N/A')} ({row.get('status', 'N/A')})"
                                trip_options.append((row['id'], trip_label))

                        if trip_options:
                            selected_trip = st.selectbox(
                                "Select Trip to Edit/Delete",
                                options=[opt[0] for opt in trip_options],
                                format_func=lambda x: next((opt[1] for opt in trip_options if opt[0] == x), "Select Trip"),
                                key="trip_action_select"
                            )
                            st.session_state.selected_trip_for_action = selected_trip

                    with col_action2:
                        edit_clicked = st.form_submit_button("✏️ Edit Selected", use_container_width=True)
                        if edit_clicked:
                            if st.session_state.selected_trip_for_action:
                                st.session_state.editing_id = st.session_state.selected_trip_for_action
                                st.session_state.edit_data = None
                                st.rerun()
                            else:
                                st.warning("Please select a trip first")

                    with col_action3:
                        delete_clicked = st.form_submit_button("🗑️ Delete Selected", use_container_width=True)
                        if delete_clicked:
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
                # INLINE EDIT FORM - Using form to prevent reruns
                # ===========================================
                if st.session_state.editing_id:
                    if st.session_state.edit_data is None:
                        trip_data = get_trip_by_id(st.session_state.editing_id)
                        if trip_data:
                            st.session_state.edit_data = trip_data
                        else:
                            st.session_state.editing_id = None
                            st.error("Trip not found")
                            st.rerun()

                    if st.session_state.edit_data:
                        st.markdown('<div class="edit-container">', unsafe_allow_html=True)
                        st.markdown(f"### ✏️ Edit Trip - {st.session_state.edit_data.get('plate_number', 'N/A')}")

                        edit = st.session_state.edit_data

                        with st.form(key="edit_trip_form"):
                            col1, col2, col3 = st.columns(3)

                            with col1:
                                edit_plate = st.selectbox(
                                    "Plate Number",
                                    plate_numbers,
                                    index=plate_numbers.index(edit.get('plate_number', plate_numbers[0])) if edit.get('plate_number') in plate_numbers else 0,
                                    key="edit_plate"
                                )
                                edit_derived_driver = plate_to_driver.get(edit_plate, "Not Found")
                                st.markdown(f"**Driver Name:** {edit_derived_driver}")
                                edit_from = st.selectbox(
                                    "From Location",
                                    from_locations,
                                    index=from_locations.index(edit.get('from_location', from_locations[0])) if edit.get('from_location') in from_locations else 0,
                                    key="edit_from"
                                )
                                edit_branch = st.selectbox(
                                    "Assigned Branch",
                                    branches,
                                    index=branches.index(edit.get('assigned_branch_name', branches[0])) if edit.get('assigned_branch_name') in branches else 0,
                                    key="edit_branch"
                                )

                            with col2:
                                edit_assigned_by = st.text_input("Assigned By", value=edit.get('assigned_by', ''), key="edit_assigned_by")
                                edit_requested_by = st.text_input("Requested By", value=edit.get('requested_by', ''), key="edit_requested_by")
                                edit_assigned_date = st.date_input("Assigned Date", value=parse_date(edit.get('assigned_date', '')), key="edit_assigned_date")
                                edit_status = st.selectbox(
                                    "Status",
                                    ["Planned", "In Transit", "Completed"],
                                    index=["Planned", "In Transit", "Completed"].index(edit.get('status', 'Planned')) if edit.get('status') in ["Planned", "In Transit", "Completed"] else 0,
                                    key="edit_status"
                                )

                            with col3:
                                st.markdown("**Activity Timeline**")
                                edit_loading_start = st.date_input("Loading Started", value=parse_date(edit.get('loading_starting_date', '')), key="edit_loading_start")
                                edit_loading_end = st.date_input("Loading Completed", value=parse_date(edit.get('loading_date_end', '')), key="edit_loading_end")
                                edit_trip_start = st.date_input("Departure Date", value=parse_date(edit.get('trip_starting_date', '')), key="edit_trip_start")
                                edit_arrival = st.date_input("Arrival Date", value=parse_date(edit.get('arrival_date', '')), key="edit_arrival")
                                edit_return = st.date_input("Return Date", value=parse_date(edit.get('return_date', '')), key="edit_return")
                                edit_trip_end = st.date_input("Trip Completed", value=parse_date(edit.get('trip_end_date', '')), key="edit_trip_end")

                            col_btn1, col_btn2 = st.columns(2)
                            with col_btn1:
                                update_clicked = st.form_submit_button("🔄 Update Trip", type="primary", use_container_width=True)
                                if update_clicked:
                                    current_driver = edit_derived_driver

                                    updated_record = {
                                        "plate_number": edit_plate,
                                        "driver_name": current_driver,
                                        "from_location": edit_from,
                                        "assigned_branch_name": edit_branch,
                                        "assigned_by": edit_assigned_by,
                                        "requested_by": edit_requested_by,
                                        "assigned_date": str(edit_assigned_date),
                                        "status": edit_status,
                                        "loading_starting_date": str(edit_loading_start),
                                        "loading_date_end": str(edit_loading_end),
                                        "trip_starting_date": str(edit_trip_start),
                                        "arrival_date": str(edit_arrival),
                                        "return_date": str(edit_return),
                                        "trip_end_date": str(edit_trip_end)
                                    }
                                    try:
                                        res = supabase.table(TXN_TABLE).update(updated_record).eq("id", st.session_state.editing_id).execute()
                                        if res.data:
                                            st.success("✅ Trip updated successfully!")
                                            st.session_state.editing_id = None
                                            st.session_state.edit_data = None
                                            st.cache_data.clear()
                                            st.rerun()
                                    except Exception as e:
                                        st.error(f"❌ Error: {str(e)}")

                            with col_btn2:
                                cancel_edit_clicked = st.form_submit_button("❌ Cancel Edit", use_container_width=True)
                                if cancel_edit_clicked:
                                    st.session_state.editing_id = None
                                    st.session_state.edit_data = None
                                    st.rerun()

                        st.markdown('</div>', unsafe_allow_html=True)

                # ===========================================
                # FILTERS
                # ===========================================
                col_filter1, col_filter2, col_filter3 = st.columns(3)
                with col_filter1:
                    filter_status = st.multiselect(
                        "Status",
                        options=["All"] + sorted(data["status"].unique().tolist()) if "status" in data.columns else ["All"],
                        default=["All"],
                        key="filter_status_table"
                    )
                with col_filter2:
                    filter_branch = st.multiselect(
                        "Branch",
                        options=["All"] + sorted(data["assigned_branch_name"].unique().tolist()) if "assigned_branch_name" in data.columns else ["All"],
                        default=["All"],
                        key="filter_branch_table"
                    )
                with col_filter3:
                    filter_plate = st.multiselect(
                        "Vehicle",
                        options=["All"] + sorted(data["plate_number"].unique().tolist()) if "plate_number" in data.columns else ["All"],
                        default=["All"],
                        key="filter_plate_table"
                    )

                filtered_data = data.copy()
                if "All" not in filter_status and filter_status:
                    filtered_data = filtered_data[filtered_data["status"].isin(filter_status)]
                if "All" not in filter_branch and filter_branch:
                    filtered_data = filtered_data[filtered_data["assigned_branch_name"].isin(filter_branch)]
                if "All" not in filter_plate and filter_plate:
                    filtered_data = filtered_data[filtered_data["plate_number"].isin(filter_plate)]

                if len(filtered_data) < len(data):
                    st.info(f"📊 Showing {len(filtered_data)} of {len(data)} records")

                # ===========================================
                # DISPLAY TABLE
                # ===========================================
                if not filtered_data.empty:
                    display_data = filtered_data[[col for col in display_columns if col != 'id']].copy()

                    st.dataframe(
                        display_data,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "status": st.column_config.Column("Status", width="small"),
                            "plate_number": st.column_config.Column("Plate", width="small"),
                            "driver_name": st.column_config.Column("Driver", width="medium"),
                            "assigned_branch_name": st.column_config.Column("Branch", width="medium"),
                            "from_location": st.column_config.Column("From", width="medium"),
                            "trip_starting_date": st.column_config.Column("Departure", width="medium"),
                            "arrival_date": st.column_config.Column("Arrival", width="medium"),
                            "return_date": st.column_config.Column("Return", width="medium"),
                            "trip_end_date": st.column_config.Column("Trip End", width="medium"),
                            "created_at": st.column_config.Column("Created", width="medium"),
                        }
                    )

                    col_export1, col_export2 = st.columns([1, 5])
                    with col_export1:
                        if st.button("📥 Export to CSV"):
                            csv = display_data.to_csv(index=False)
                            st.download_button(
                                label="Download CSV",
                                data=csv,
                                file_name=f"fleet_trips_{date.today()}.csv",
                                mime="text/csv",
                                key="download_csv_table"
                            )
                else:
                    st.info("📭 No records match the selected filters")
            else:
                st.info("📭 No trip records found. Click 'Add New Trip' to create one!")

        except Exception as e:
            st.error(f"❌ Load error: {str(e)}")
            logger.error(f"Dashboard load error: {e}")

    # ===================================================
    # TAB 2: KPIs & ANALYSIS
    # ===================================================
    with tab2:
        st.markdown('<div class="section-header">📊 Key Performance Indicators & Analysis</div>', unsafe_allow_html=True)

        try:
            data = load_assignments()

            if data.empty:
                st.info("📭 No data available for analysis")
                st.stop()

            data.columns = data.columns.str.strip()

            date_columns = ['assigned_date', 'loading_starting_date', 'loading_date_end',
                           'trip_starting_date', 'arrival_date', 'return_date', 'trip_end_date']
            for col in date_columns:
                if col in data.columns:
                    data[col] = pd.to_datetime(data[col], errors='coerce')

            col_metric1, col_metric2, col_metric3, col_metric4, col_metric5 = st.columns(5)

            with col_metric1:
                total_trips = len(data)
                st.metric("Total Trips", total_trips)

            with col_metric2:
                if 'status' in data.columns:
                    planned = len(data[data['status'] == 'Planned'])
                    st.metric("Planned", planned)

            with col_metric3:
                if 'status' in data.columns:
                    in_transit = len(data[data['status'] == 'In Transit'])
                    st.metric("In Transit", in_transit)

            with col_metric4:
                if 'status' in data.columns:
                    completed = len(data[data['status'] == 'Completed'])
                    st.metric("Completed", completed)

            with col_metric5:
                if 'status' in data.columns:
                    completion_rate = (completed / total_trips * 100) if total_trips > 0 else 0
                    st.metric("Completion Rate", f"{completion_rate:.1f}%")

            col_chart1, col_chart2 = st.columns(2)

            with col_chart1:
                st.subheader("📈 Trip Status Distribution")
                if 'status' in data.columns:
                    status_counts = data['status'].value_counts()
                    fig_status = px.pie(
                        values=status_counts.values,
                        names=status_counts.index,
                        title="Trips by Status",
                        color_discrete_sequence=px.colors.qualitative.Set3
                    )
                    fig_status.update_traces(textposition='inside', textinfo='percent+label')
                    st.plotly_chart(fig_status, use_container_width=True)

            with col_chart2:
                st.subheader("🏢 Trips by Branch")
                if 'assigned_branch_name' in data.columns:
                    branch_counts = data['assigned_branch_name'].value_counts().head(10)
                    fig_branch = px.bar(
                        x=branch_counts.values,
                        y=branch_counts.index,
                        orientation='h',
                        title="Top 10 Branches by Trip Volume",
                        color=branch_counts.values,
                        color_continuous_scale=px.colors.sequential.Blues
                    )
                    fig_branch.update_layout(xaxis_title="Number of Trips", yaxis_title="Branch")
                    st.plotly_chart(fig_branch, use_container_width=True)

            col_chart3, col_chart4 = st.columns(2)

            with col_chart3:
                st.subheader("🚛 Vehicle Utilization")
                if 'plate_number' in data.columns:
                    vehicle_counts = data['plate_number'].value_counts().head(10)
                    fig_vehicle = px.bar(
                        x=vehicle_counts.index,
                        y=vehicle_counts.values,
                        title="Top 10 Most Used Vehicles",
                        color=vehicle_counts.values,
                        color_continuous_scale=px.colors.sequential.Greens
                    )
                    fig_vehicle.update_layout(xaxis_title="Plate Number", yaxis_title="Number of Trips")
                    st.plotly_chart(fig_vehicle, use_container_width=True)

            with col_chart4:
                st.subheader("👤 Driver Performance")
                if 'driver_name' in data.columns:
                    driver_counts = data['driver_name'].value_counts().head(10)
                    fig_driver = px.bar(
                        x=driver_counts.index,
                        y=driver_counts.values,
                        title="Top 10 Drivers by Trip Volume",
                        color=driver_counts.values,
                        color_continuous_scale=px.colors.sequential.Oranges
                    )
                    fig_driver.update_layout(xaxis_title="Driver Name", yaxis_title="Number of Trips")
                    st.plotly_chart(fig_driver, use_container_width=True)

            st.subheader("📅 Timeline Analysis")
            col_chart5, col_chart6 = st.columns(2)

            with col_chart5:
                if 'created_at' in data.columns:
                    if not pd.api.types.is_datetime64_any_dtype(data['created_at']):
                        data['created_at'] = pd.to_datetime(data['created_at'], errors='coerce')

                    daily_trips = data.groupby(data['created_at'].dt.date).size().reset_index(name='count')
                    daily_trips.columns = ['Date', 'Trips']

                    fig_timeline = px.line(
                        daily_trips,
                        x='Date',
                        y='Trips',
                        title="Daily Trip Volume",
                        markers=True
                    )
                    fig_timeline.update_layout(xaxis_title="Date", yaxis_title="Number of Trips")
                    st.plotly_chart(fig_timeline, use_container_width=True)

            with col_chart6:
                if 'created_at' in data.columns and 'status' in data.columns:
                    status_over_time = data.groupby([data['created_at'].dt.date, 'status']).size().reset_index(name='count')
                    status_over_time.columns = ['Date', 'Status', 'Count']

                    fig_status_time = px.line(
                        status_over_time,
                        x='Date',
                        y='Count',
                        color='Status',
                        title="Status Trends Over Time",
                        markers=True
                    )
                    fig_status_time.update_layout(xaxis_title="Date", yaxis_title="Number of Trips")
                    st.plotly_chart(fig_status_time, use_container_width=True)

            st.subheader("📊 Summary Statistics")

            summary_data = []

            if 'status' in data.columns:
                status_summary = data['status'].value_counts()
                for status_name, count in status_summary.items():
                    percentage = (count / len(data)) * 100
                    summary_data.append({
                        'Metric': f'Status: {status_name}',
                        'Count': count,
                        'Percentage': f'{percentage:.1f}%'
                    })

            if 'assigned_branch_name' in data.columns:
                branch_summary = data['assigned_branch_name'].value_counts().head(5)
                for branch_name, count in branch_summary.items():
                    percentage = (count / len(data)) * 100
                    summary_data.append({
                        'Metric': f'Branch: {branch_name}',
                        'Count': count,
                        'Percentage': f'{percentage:.1f}%'
                    })

            if summary_data:
                summary_df = pd.DataFrame(summary_data)
                st.dataframe(summary_df, use_container_width=True, hide_index=True)

            with st.expander("📋 Detailed Statistics"):
                st.write("### Data Overview")
                if 'created_at' in data.columns and not data['created_at'].isna().all():
                    st.write(f"**Total Records:** {len(data)}")
                    st.write(f"**Date Range:** {data['created_at'].min()} to {data['created_at'].max()}")
                else:
                    st.write(f"**Total Records:** {len(data)}")

                if 'status' in data.columns:
                    st.write("### Status Breakdown")
                    status_breakdown = data['status'].value_counts()
                    for status_name, count in status_breakdown.items():
                        st.write(f"- {status_name}: {count} ({count/len(data)*100:.1f}%)")

                if 'plate_number' in data.columns:
                    st.write("### Unique Vehicles")
                    st.write(f"Total unique vehicles: {data['plate_number'].nunique()}")

                if 'driver_name' in data.columns:
                    st.write("### Unique Drivers")
                    st.write(f"Total unique drivers: {data['driver_name'].nunique()}")

        except Exception as e:
            st.error(f"❌ Analysis error: {str(e)}")
            logger.error(f"Analysis error: {e}")
