import streamlit as st
import hashlib
import pandas as pd
from datetime import datetime, timedelta
import warnings
import logging
from supabase import create_client
import time
import uuid
import pytz
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Suppress warnings
warnings.filterwarnings("ignore")
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("requests").setLevel(logging.ERROR)

# ONE shared account system lives in core_auth.py (table: app_users).
# This file keeps the dashboard-style login / profile / admin screens.
from core_auth import init_supabase
supabase = init_supabase()

# Set timezone for Addis Ababa (East Africa Time)
ADDIS_ABABA_TZ = pytz.timezone('Africa/Addis_Ababa')

def get_current_time():
    """Get current time in Addis Ababa timezone"""
    return datetime.now(ADDIS_ABABA_TZ)
def clear_procurement_cache_only():
    """Clear ONLY the procurement lead time cache — leaves other caches intact"""
    try:
        load_procurement_lead_time.clear()
    except Exception:
        pass
def format_time_for_display(dt):
    """Format datetime for display in Addis Ababa time"""
    if dt is None or pd.isna(dt):
        return "Never"
    if isinstance(dt, str):
        if dt == 'None' or dt == '':
            return "Never"
        try:
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except Exception:
            return dt
    # Check if dt is a datetime object
    if hasattr(dt, 'tzinfo'):
        if dt.tzinfo is None:
            dt = pytz.UTC.localize(dt).astimezone(ADDIS_ABABA_TZ)
        else:
            dt = dt.astimezone(ADDIS_ABABA_TZ)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return str(dt)

# ============================================================
# FOOTER FUNCTION
# ============================================================

def show_footer():
    """Display copyright footer on all pages"""
    st.markdown("""
    <style>
    .footer {
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
        color: white;
        text-align: center;
        padding: 10px;
        font-size: 13px;
        font-family: 'Times New Roman', Times, serif;
        z-index: 999;
        box-shadow: 0 -2px 15px rgba(0,0,0,0.2);
    }
    .footer a {
        color: #ffd700;
        text-decoration: none;
        font-weight: bold;
    }
    .footer a:hover {
        text-decoration: underline;
    }
    .main-content {
        margin-bottom: 50px;
    }
    </style>
    <div class="footer">
        © 2026 HPC SUPPLY CHAIN MANAGEMENT TOOL | Developed by Biyensa Negera
    </div>
    """, unsafe_allow_html=True)

    # Add margin to main content to prevent overlap with footer
    st.markdown('<div class="main-content"></div>', unsafe_allow_html=True)

# ============================================================
# DATABASE FUNCTIONS - Using 'users' table with approval
# ============================================================

from core_auth import (
    MODULES, MODULE_ICONS, ROLES,
    authenticate_user, create_user, change_password, update_user_profile,
    get_pending_users, approve_user, reject_user, delete_user, add_user_by_admin,
    update_user_role, toggle_user_active, update_user_modules,
    get_module_access, update_module_access,
    update_user_session, get_online_users, get_user_row,
    refresh_user_access, check_session_validity,
    request_password_reset, get_password_reset_requests, approve_password_reset,
    reject_password_reset, has_approved_password_reset, complete_password_reset,
    get_all_users_df as get_all_users,
)

MAIN_TAB_OPTIONS = ["Dashboard", "Advanced Analytics", "Executive Summary", "Issue Data", "Upload"]
PROGRAM_OPTIONS = ["All", "Malaria", "HIV", "TB", "OI and Hepatitis", "FP", "CH", "MH",
                   "Nutrition", "Lab Malaria", "Lab TB", "HIV Lab", "Vaccine"]

def get_user_activity_stats():
    """Get detailed user activity statistics - FIXED datetime comparison"""
    try:
        all_users = get_all_users()
        if all_users.empty:
            return {}

        # Calculate basic statistics
        stats = {
            'total_users': len(all_users),
            'approved_users': len(all_users[all_users['is_approved'] == 1]) if 'is_approved' in all_users else 0,
            'pending_users': len(all_users[all_users['is_approved'] == 0]) if 'is_approved' in all_users else 0,
            'admin_users': len(all_users[all_users['role'] == 'admin']) if 'role' in all_users else 0,
            'regular_users': len(all_users[all_users['role'] != 'admin']) if 'role' in all_users else 0,
        }

        # Activity trends (last 7 days) - FIXED datetime comparison
        if 'last_active' in all_users.columns:
            # Convert to datetime with error handling
            all_users['last_active_date'] = pd.to_datetime(all_users['last_active'], errors='coerce', utc=True)

            # Drop NaN values
            all_users_clean = all_users.dropna(subset=['last_active_date'])

            if not all_users_clean.empty:
                # Get current time in UTC for comparison
                current_time_utc = datetime.now(pytz.UTC)
                last_7_days_utc = current_time_utc - timedelta(days=7)

                # Filter users active in last 7 days - both are now timezone-aware
                active_mask = all_users_clean['last_active_date'] > last_7_days_utc
                stats['active_last_7_days'] = active_mask.sum()
                stats['inactive_last_7_days'] = stats['total_users'] - stats['active_last_7_days']
            else:
                stats['active_last_7_days'] = 0
                stats['inactive_last_7_days'] = stats['total_users']
        else:
            stats['active_last_7_days'] = 0
            stats['inactive_last_7_days'] = stats['total_users']

        # Registration trends by date
        if 'created_at' in all_users.columns:
            all_users['created_date'] = pd.to_datetime(all_users['created_at'], errors='coerce', utc=True)
            # Drop NaT values
            all_users_clean = all_users.dropna(subset=['created_date'])
            if not all_users_clean.empty:
                # Convert to date for grouping
                all_users_clean['created_date_only'] = all_users_clean['created_date'].dt.date
                daily_registrations = all_users_clean.groupby('created_date_only').size().reset_index(name='count')
                daily_registrations.columns = ['created_date', 'count']
                stats['daily_registrations'] = daily_registrations
            else:
                stats['daily_registrations'] = pd.DataFrame(columns=['created_date', 'count'])

        # Activity by hour of day
        if 'last_active' in all_users.columns:
            # Convert to datetime and extract hour
            all_users['active_datetime'] = pd.to_datetime(all_users['last_active'], errors='coerce', utc=True)
            # Drop NaT values
            all_users_clean = all_users.dropna(subset=['active_datetime'])
            if not all_users_clean.empty:
                all_users_clean['active_hour'] = all_users_clean['active_datetime'].dt.hour
                hourly_activity = all_users_clean.groupby('active_hour').size().reset_index(name='count')
                stats['hourly_activity'] = hourly_activity
            else:
                stats['hourly_activity'] = pd.DataFrame(columns=['active_hour', 'count'])

        return stats
    except Exception as e:
        st.error(f"Error getting user stats: {e}")
        import traceback
        st.error(f"Details: {traceback.format_exc()}")
        return {}

def init_session_state():
    """Initialize all session state variables needed by dashboard"""
    if 'auth' not in st.session_state:
        st.session_state['auth'] = False
    if 'user' not in st.session_state:
        st.session_state['user'] = None
    if 'session_id' not in st.session_state:
        st.session_state['session_id'] = str(uuid.uuid4())
    if 'login_time' not in st.session_state:
        st.session_state['login_time'] = get_current_time()
    if 'last_activity' not in st.session_state:
        st.session_state['last_activity'] = get_current_time()
    if 'data_timestamp' not in st.session_state:
        st.session_state['data_timestamp'] = get_current_time()
    if 'auto_refresh' not in st.session_state:
        st.session_state['auto_refresh'] = False
    if 'recommendations' not in st.session_state:
        st.session_state['recommendations'] = {}
    if 'heatmap_page' not in st.session_state:
        st.session_state['heatmap_page'] = 1
    if 'google_sheets_data' not in st.session_state:
        st.session_state['google_sheets_data'] = None
    if 'branch_amc_data' not in st.session_state:
        st.session_state['branch_amc_data'] = None
    if 'supabase_client' not in st.session_state:
        st.session_state['supabase_client'] = supabase
    if 'search_query' not in st.session_state:
        st.session_state['search_query'] = ""
    if 'last_sheet_name' not in st.session_state:
        st.session_state['last_sheet_name'] = ""
    if 'saved_recommendations' not in st.session_state:
        st.session_state['saved_recommendations'] = {}
    if 'view_mode' not in st.session_state:
        st.session_state['view_mode'] = "table"
    if 'risk_type_filter' not in st.session_state:
        st.session_state['risk_type_filter'] = "All"
    if 'subcategory_filter' not in st.session_state:
        st.session_state['subcategory_filter'] = "All"
    if 'previous_nsoh_data' not in st.session_state:
        st.session_state['previous_nsoh_data'] = None
    if 'nsoh_changes' not in st.session_state:
        st.session_state['nsoh_changes'] = None
    if 'raw_previous_data' not in st.session_state:
        st.session_state['raw_previous_data'] = None
    if 'material_views' not in st.session_state:
        st.session_state['material_views'] = {}
    if 'user_activity' not in st.session_state:
        st.session_state['user_activity'] = []
    if 'notifications' not in st.session_state:
        st.session_state['notifications'] = []
    if 'dos_tracking' not in st.session_state:
        st.session_state['dos_tracking'] = {}
    if 'previous_data_hash' not in st.session_state:
        st.session_state['previous_data_hash'] = None
    if 'go_to_dashboard_tab' not in st.session_state:
        st.session_state['go_to_dashboard_tab'] = None
    if 'go_to_analytics_tab' not in st.session_state:
        st.session_state['go_to_analytics_tab'] = None
    if 'go_to_summary_section' not in st.session_state:
        st.session_state['go_to_summary_section'] = None
    if 'last_dashboard_tab' not in st.session_state:
        st.session_state['last_dashboard_tab'] = None
    if 'last_analytics_tab' not in st.session_state:
        st.session_state['last_analytics_tab'] = None
    if 'last_summary_section' not in st.session_state:
        st.session_state['last_summary_section'] = None
    if 'action_plan_tab' not in st.session_state:
        st.session_state['action_plan_tab'] = "📋 All Issues"
    if 'font_size' not in st.session_state:
        st.session_state.font_size = "medium"

def logout_user():
    """Handle user logout"""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# ============================================================
# UI FUNCTIONS
# ============================================================

def show_login_page():
    """Display login page with login/register forms and features"""

    # Custom CSS for better visibility and attractive colors
    st.markdown("""
    <style>
    /* Global styles */
    .stApp {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    }

    /* Hero Section Animation */
    @keyframes gentlePulse {
        0% { transform: scale(1); }
        50% { transform: scale(1.02); }
        100% { transform: scale(1); }
    }

    @keyframes fadeInUp {
        from { opacity: 0; transform: translateY(20px); }
        to { opacity: 1; transform: translateY(0); }
    }

    /* Hero Section - Skyblue Background */
    .hero-section {
        background: linear-gradient(135deg, #87CEEB 0%, #4A90D9 100%);
        border-radius: 20px;
        padding: 35px 50px;
        text-align: center;
        color: white;
        margin-bottom: 40px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.15);
        animation: gentlePulse 3s ease-in-out infinite;
    }
    .hero-title {
        font-size: 2.2rem;
        margin-bottom: 0.8rem;
        font-weight: bold;
        font-family: 'Times New Roman', Times, serif;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
        animation: fadeInUp 0.8s ease-out;
    }
    .hero-subtitle {
        font-size: 1.1rem;
        font-family: 'Times New Roman', Times, serif;
        opacity: 0.95;
        margin-bottom: 1rem;
        animation: fadeInUp 1s ease-out;
    }
    .hero-section p {
        font-family: 'Times New Roman', Times, serif;
        animation: fadeInUp 1.2s ease-out;
    }

    /* Time Display */
    .time-display {
        text-align: center;
        padding: 15px;
        background: rgba(102, 126, 234, 0.15);
        border-radius: 10px;
        margin-bottom: 25px;
        font-size: 1.1rem;
        font-weight: 500;
        color: #2c3e50;
        border: 1px solid rgba(102, 126, 234, 0.3);
    }

    /* Login/Register Container */
    .auth-container {
        background: white;
        border-radius: 20px;
        padding: 30px;
        box-shadow: 0 15px 40px rgba(0,0,0,0.15);
        margin-bottom: 30px;
        border: 1px solid rgba(102, 126, 234, 0.2);
    }

    /* Feature Grid */
    .feature-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        gap: 25px;
        margin-top: 30px;
        margin-bottom: 30px;
    }
    .feature-card {
        background: white;
        border-radius: 15px;
        padding: 25px;
        text-align: center;
        transition: all 0.3s ease;
        box-shadow: 0 8px 25px rgba(0,0,0,0.1);
        border: 1px solid #e8e8e8;
    }
    .feature-card:hover {
        transform: translateY(-8px);
        box-shadow: 0 15px 35px rgba(0,0,0,0.15);
        border-color: #667eea;
    }
    .feature-icon {
        font-size: 3.5rem;
        margin-bottom: 15px;
    }
    .feature-title {
        font-size: 1.3rem;
        font-weight: 700;
        color: #667eea;
        margin-bottom: 12px;
    }
    .feature-desc {
        color: #555;
        line-height: 1.5;
        font-size: 0.95rem;
    }

    /* Info Section */
    .info-section {
        background: linear-gradient(135deg, #87CEEB 0%, #4A90D9 100%);
        border-radius: 15px;
        padding: 35px;
        margin-top: 30px;
        color: white;
        box-shadow: 0 8px 25px rgba(0,0,0,0.1);
    }
    .info-section h3 {
        color: white;
        margin-bottom: 20px;
        font-size: 1.8rem;
        font-family: 'Times New Roman', Times, serif;
    }
    .step-box {
        background: rgba(255,255,255,0.15);
        border-radius: 12px;
        padding: 20px;
        text-align: left;
        backdrop-filter: blur(10px);
        transition: all 0.3s ease;
        font-family: 'Times New Roman', Times, serif;
    }
    .step-box:hover {
        background: rgba(255,255,255,0.25);
        transform: translateX(5px);
    }
    .step-number {
        font-size: 2rem;
        font-weight: bold;
        margin-bottom: 10px;
    }

    /* Tabs Styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 10px;
        padding: 10px 20px;
        font-weight: 600;
        background-color: #f0f2f6;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #87CEEB 0%, #4A90D9 100%);
        color: white;
    }

    /* Form Styling */
    .stForm {
        background: transparent;
    }
    .stButton > button {
        background: linear-gradient(135deg, #87CEEB 0%, #4A90D9 100%);
        color: white;
        border: none;
        border-radius: 10px;
        font-weight: 600;
        padding: 10px;
        transition: all 0.3s ease;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(74, 144, 217, 0.4);
    }

    /* Welcome Section */
    .welcome-section {
        text-align: center;
        margin: 30px 0;
    }
    .welcome-title {
        font-size: 2rem;
        color: #4A90D9;
        font-weight: bold;
        margin-bottom: 15px;
        font-family: 'Times New Roman', Times, serif;
    }
    .welcome-text {
        font-size: 1.1rem;
        color: #555;
        font-family: 'Times New Roman', Times, serif;
    }

    /* Alert Styling */
    .stAlert {
        border-radius: 10px;
        border-left: 4px solid;
    }
    </style>
    """, unsafe_allow_html=True)

    # Display current Addis Ababa time
    current_time = get_current_time()
    st.markdown(f"""
    <div class="time-display">
        🕐 Addis Ababa Time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}
    </div>
    """, unsafe_allow_html=True)

    # Hero Section - Skyblue with animation
    st.markdown("""
    <div class="hero-section">
        <div class="hero-title">💊 HPC SUPPLY CHAIN MANAGEMENT TOOL</div>
        <div class="hero-subtitle">Integrated Stock Management, Supply Planning &amp; Demand Forecasting Platform</div>
        <p style="opacity: 0.95; font-size: 1rem;">Secure • Real-time • Data-driven Decision Making</p>
    </div>
    """, unsafe_allow_html=True)

    # Create two columns for layout
    left_col, right_col = st.columns([1, 1], gap="large")

    with left_col:
        st.markdown("""
        <div class="welcome-section">
            <div class="welcome-title">✨ Welcome!</div>
            <div class="welcome-text">Access your modules to monitor stock levels, plan supply, forecast demand, and get actionable insights.</div>
        </div>
        """, unsafe_allow_html=True)

        # Features Section
        st.markdown("### 🚀 Key Features")

        features = [
            ("📦", "Stock Management", "Monitor stock status, KPIs and risk of stock-out or expiry"),
            ("🚚", "Pipeline Tracking", "Track GIT, LC, WB, and TMD orders"),
            ("📍", "Hub Distribution", "Visualize stock across all branches"),
            ("🗂️", "Supply Planning", "Expert action plans, follow-up and system-generated action plans"),
            ("📈", "Demand Forecasting", "Forecast demand per material from monthly issue history"),
            ("🔐", "Secure Access", "Role-based access with admin approval"),
        ]

        for icon, title, desc in features:
            st.markdown(f"""
            <div style="background: white; border-radius: 12px; padding: 15px; margin-bottom: 12px; border-left: 4px solid #4A90D9; box-shadow: 0 2px 8px rgba(0,0,0,0.05);">
                <div style="display: flex; align-items: center; gap: 15px;">
                    <div style="font-size: 2rem;">{icon}</div>
                    <div>
                        <strong style="font-size: 1rem; color: #4A90D9; font-family: 'Times New Roman', Times, serif;">{title}</strong>
                        <div style="color: #666; font-size: 0.9rem; font-family: 'Times New Roman', Times, serif;">{desc}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    with right_col:
        st.markdown("""
        <div class="auth-container">
            <div style="text-align: center; margin-bottom: 20px;">
                <h2 style="color: #4A90D9; margin: 0; font-family: 'Times New Roman', Times, serif;">🔐 Account Access</h2>
                <p style="color: #666; font-family: 'Times New Roman', Times, serif;">Login or create a new account</p>
            </div>
        """, unsafe_allow_html=True)

        # Create tabs for Login and Register
        tab1, tab2 = st.tabs(["🔐 Login", "📝 Register"])

        with tab1:
            with st.form("login_form"):
                email = st.text_input("Email", placeholder="Enter your email", key="login_email")
                password = st.text_input("Password", type="password", placeholder="Enter your password", key="login_password")
                submitted = st.form_submit_button("Login", type="primary", use_container_width=True)

                if submitted:
                    if email and password:
                        with st.spinner("Authenticating..."):
                            user = authenticate_user(email, password)
                            if user and 'error' in user:
                                st.error({
                                    'not_approved': "⏳ Your account is pending admin approval. Please wait for approval.",
                                    'inactive': "⛔ Your account has been deactivated. Contact an administrator.",
                                    'reset_pending': "🔑 Your password reset request is awaiting admin approval.",
                                    'no_modules': "🧩 Your account is approved but has no modules assigned yet. Contact an administrator.",
                                }.get(user['error'], "❌ Unable to sign in."))
                            elif user:
                                st.session_state['auth'] = True
                                st.session_state['user'] = user
                                st.session_state['login_time'] = get_current_time()
                                st.session_state['last_activity'] = get_current_time()
                                update_user_session(user['id'], st.session_state.get('session_id', ''))
                                st.session_state['force_password_reset'] = has_approved_password_reset(user['id'])
                                st.success("✅ Login successful! Redirecting...")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error("❌ Invalid email or password")
                    else:
                        st.warning("⚠️ Please enter both email and password")

            with st.expander("Forgot password?"):
                fp_email = st.text_input("Your account email", key="forgot_email")
                if st.button("Request password reset", key="forgot_btn"):
                    if fp_email:
                        ok, msg = request_password_reset(fp_email)
                        (st.success if ok else st.error)(msg)
                    else:
                        st.warning("⚠️ Enter your email first")

        with tab2:
            with st.form("register_form"):
                new_email = st.text_input("Email", placeholder="you@example.com", key="reg_email")
                new_full_name = st.text_input("Full Name", placeholder="Enter your full name", key="reg_name")
                new_password = st.text_input("Password", type="password", placeholder="Create a password (min 6 characters)", key="reg_password")
                confirm_password = st.text_input("Confirm Password", type="password", placeholder="Confirm your password", key="reg_confirm")
                submitted = st.form_submit_button("Register", type="primary", use_container_width=True)

                if submitted:
                    if not new_email or not new_full_name or not new_password:
                        st.warning("⚠️ Please fill all fields")
                    elif new_password != confirm_password:
                        st.error("❌ Passwords do not match")
                    elif len(new_password) < 6:
                        st.error("❌ Password must be at least 6 characters")
                    else:
                        with st.spinner("Creating your account..."):
                            success, message = create_user(new_email, new_password, new_full_name)
                            if success:
                                st.success(f"✅ {message}")
                                st.balloons()
                                st.info("📋 Admin will review and approve your account.")
                            else:
                                st.error(f"❌ {message}")

        st.markdown('</div>', unsafe_allow_html=True)

    # Information Section below both columns
    st.markdown("""
    <div class="info-section">
        <h3 style="text-align: center;">ℹ️ How to Get Started</h3>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 25px; margin-top: 20px;">
            <div class="step-box">
                <div class="step-number">1</div>
                <strong>Register Account</strong><br>
                Click on the Register tab and fill in your details
            </div>
            <div class="step-box">
                <div class="step-number">2</div>
                <strong>Wait for Approval</strong><br>
                Admin will review and approve your account
            </div>
            <div class="step-box">
                <div class="step-number">3</div>
                <strong>Login</strong><br>
                Once approved, login to access the dashboard
            </div>
            <div class="step-box">
                <div class="step-number">4</div>
                <strong>Explore Features</strong><br>
                Access stock management, supply planning, and demand forecasting
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Show footer on login page
    show_footer()

def show_online_users():
    """Display online users widget - sorted by newest first"""
    st.markdown("### 🟢 Currently Online Users")
    st.caption(f"Last updated: {get_current_time().strftime('%H:%M:%S')}")

    online_users = get_online_users()

    if online_users:
        st.markdown(f"**{len(online_users)} user(s) currently online**")
        st.markdown("---")

        for user in online_users:
            is_current = st.session_state['user']['id'] == user['id']
            user_icon = "⭐" if is_current else "🟢"
            user_name = f"{user_icon} **{user['full_name']}**" + (" (You)" if is_current else "")

            last_active_str = user.get('last_active_display', 'Unknown')

            st.markdown(f"""
            <div style="background: linear-gradient(135deg, #87CEEB15 0%, #4A90D915 100%); border-left: 4px solid #4caf50; padding: 10px; margin: 8px 0; border-radius: 8px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <span style="display: inline-block; width: 10px; height: 10px; border-radius: 50%; background-color: #4caf50; animation: pulse 2s infinite; margin-right: 8px;"></span>
                        {user_name}
                    </div>
                    <small style="color: #666;">Active at: {last_active_str}</small>
                </div>
                <div style="margin-top: 5px; margin-left: 18px;">
                    <small>📧 {user['email']} | 🔑 {user['role'].title()}</small>
                </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("👻 No users currently online")

def show_profile_page():
    """Display user profile page"""
    st.markdown("<h1 style='font-size: 32px; font-weight: bold; color: #4A90D9; font-family: Times New Roman, Times, serif;'>👤 User Profile</h1>", unsafe_allow_html=True)

    # Display current Addis Ababa time
    current_time = get_current_time()
    st.markdown(f"""
    <div style="text-align: right; margin-bottom: 20px; padding: 10px; background: rgba(74,144,217,0.1); border-radius: 10px;">
        <small style="font-family: 'Times New Roman', Times, serif;">🕐 Local Time (Addis Ababa): {current_time.strftime('%Y-%m-%d %H:%M:%S')}</small>
    </div>
    """, unsafe_allow_html=True)

    if st.session_state.get('user'):
        user = st.session_state['user']

        col1, col2 = st.columns([1, 2])

        with col1:
            st.markdown(f"""
            <div style='background: linear-gradient(135deg, #87CEEB 0%, #4A90D9 100%); 
                        border-radius: 15px; 
                        padding: 30px; 
                        text-align: center;
                        color: white;
                        box-shadow: 0 10px 25px rgba(0,0,0,0.1);'>
                <div style='font-size: 48px; margin-bottom: 10px;'>👤</div>
                <h3 style='margin: 0; font-family: Times New Roman, Times, serif;'>{user.get('full_name', 'N/A')}</h3>
                <p style='margin: 5px 0; opacity: 0.9; font-family: Times New Roman, Times, serif;'>{user.get('role', 'user').title()}</p>
                <p style='margin: 5px 0; font-size: 12px; opacity: 0.8; font-family: Times New Roman, Times, serif;'>{user.get('email', 'N/A')}</p>
                <p style='margin: 5px 0; font-size: 11px; opacity: 0.7; font-family: Times New Roman, Times, serif;'>✅ Account Approved</p>
            </div>
            """, unsafe_allow_html=True)

        with col2:
            st.markdown("### 📋 Profile Information")

            # Get user's last active time
            try:
                _row = get_user_row(user['id']) or {}
                last_active = _row.get('last_active')
                created_at = _row.get('created_at')
                last_active_display = format_time_for_display(last_active) if last_active else "Never"
                created_at_display = format_time_for_display(created_at) if created_at else "Unknown"
            except Exception:
                last_active_display = "Unknown"
                created_at_display = "Unknown"

            st.markdown(f"""
            <div style="background: #f8f9fa; border-radius: 10px; padding: 20px; font-family: 'Times New Roman', Times, serif;">
            <table style="width: 100%;">
                <tr>
                    <td><strong>Full Name</strong></td>
                    <td>{user.get('full_name', 'N/A')}</td>
                </tr>
                <tr>
                    <td><strong>Email</strong></td>
                    <td>{user.get('email', 'N/A')}</td>
                </tr>
                <tr>
                    <td><strong>Role</strong></td>
                    <td>{user.get('role', 'user').title()}</td>
                </tr>
                <tr>
                    <td><strong>Last Active</strong></td>
                    <td>{last_active_display}</td>
                </tr>
                <tr>
                    <td><strong>Account Created</strong></td>
                    <td>{created_at_display}</td>
                </tr>
            </table>
            </div>
            """, unsafe_allow_html=True)

            with st.expander("✏️ Edit display name"):
                _new_name = st.text_input("Full name", value=user.get('full_name', ''), key="profile_new_name")
                if st.button("Save name", key="profile_save_name"):
                    _ok, _msg = update_user_profile(user['id'], _new_name)
                    if _ok:
                        st.session_state['user']['full_name'] = _new_name.strip()
                        st.success(_msg)
                    else:
                        st.error(_msg)
            _mods = [MODULES[m] for m in user.get('modules', []) if m in MODULES]
            st.caption("Modules: " + (", ".join(_mods) if _mods else "none"))

            st.markdown("---")
            st.markdown("### 🔒 Change Password")

            with st.form("change_password_form"):
                old_password = st.text_input("Current Password", type="password")
                new_password = st.text_input("New Password", type="password")
                confirm_password = st.text_input("Confirm New Password", type="password")

                col1, col2 = st.columns(2)
                with col1:
                    submitted = st.form_submit_button("Update Password", type="primary", use_container_width=True)
                with col2:
                    if st.form_submit_button("Cancel", use_container_width=True):
                        st.rerun()

                if submitted:
                    if not old_password or not new_password:
                        st.error("⚠️ Please fill all fields")
                    elif new_password != confirm_password:
                        st.error("❌ New passwords do not match")
                    elif len(new_password) < 6:
                        st.error("❌ Password must be at least 6 characters")
                    else:
                        with st.spinner("Changing password..."):
                            success, message = change_password(user['id'], old_password, new_password)
                            if success:
                                st.success(f"✅ {message}")
                                st.info("Please login again with your new password.")
                                time.sleep(2)
                                logout_user()
                            else:
                                st.error(f"❌ {message}")
    else:
        st.warning("User data not found")

def show_user_statistics():
    """Display interactive user statistics dashboard"""
    st.markdown("### 📊 User Analytics Dashboard")

    stats = get_user_activity_stats()

    if not stats or stats.get('total_users', 0) == 0:
        st.warning("No user data available for statistics")
        return

    # Filter options
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        show_chart_type = st.selectbox(
            "Chart Style",
            ["Modern", "Classic", "Minimalist"],
            key="chart_style"
        )
    with col2:
        time_range = st.selectbox(
            "Time Range",
            ["Last 7 Days", "Last 30 Days", "All Time"],
            key="time_range"
        )
    with col3:
        st.markdown("### ")
        if st.button("🔄 Refresh Statistics", use_container_width=True):
            st.rerun()

    # Key Metrics Row with enhanced styling
    col1, col2, col3, col4, col5 = st.columns(5)

    metric_style = """
    <div style="background: linear-gradient(135deg, {color1}, {color2}); 
                border-radius: 15px; 
                padding: 15px; 
                text-align: center;
                color: white;
                box-shadow: 0 4px 15px rgba(0,0,0,0.1);
                transition: transform 0.3s;">
        <div style="font-size: 32px; margin-bottom: 5px;">{icon}</div>
        <div style="font-size: 24px; font-weight: bold;">{value}</div>
        <div style="font-size: 12px; opacity: 0.9; font-family: Times New Roman, Times, serif;">{label}</div>
    </div>
    """

    with col1:
        st.markdown(metric_style.format(
            icon="👥", value=stats.get('total_users', 0),
            label="Total Users", color1="#87CEEB", color2="#4A90D9"
        ), unsafe_allow_html=True)

    with col2:
        st.markdown(metric_style.format(
            icon="✅", value=stats.get('approved_users', 0),
            label="Approved", color1="#11998e", color2="#38ef7d"
        ), unsafe_allow_html=True)

    with col3:
        st.markdown(metric_style.format(
            icon="⏳", value=stats.get('pending_users', 0),
            label="Pending", color1="#f093fb", color2="#f5576c"
        ), unsafe_allow_html=True)

    with col4:
        st.markdown(metric_style.format(
            icon="👑", value=stats.get('admin_users', 0),
            label="Admins", color1="#fa709a", color2="#fee140"
        ), unsafe_allow_html=True)

    with col5:
        st.markdown(metric_style.format(
            icon="🟢", value=stats.get('active_last_7_days', 0),
            label="Active (7d)", color1="#4facfe", color2="#00f2fe"
        ), unsafe_allow_html=True)

    st.markdown("---")

    # Create two columns for charts
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### 📈 User Role Distribution")

        # Role distribution pie chart
        role_data = pd.DataFrame({
            'Role': ['Admin Users', 'Regular Users'],
            'Count': [stats.get('admin_users', 0), stats.get('regular_users', 0)]
        })

        colors = ['#4A90D9', '#87CEEB']

        fig = px.pie(role_data, values='Count', names='Role',
                     title='User Roles',
                     color_discrete_sequence=colors,
                     hole=0.4)

        fig.update_layout(
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
            height=400,
            margin=dict(t=50, l=0, r=0, b=0),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font_family="Times New Roman, Times, serif"
        )

        fig.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("#### ✅ Approval Status")

        # Approval status donut chart
        approval_data = pd.DataFrame({
            'Status': ['Approved', 'Pending'],
            'Count': [stats.get('approved_users', 0), stats.get('pending_users', 0)]
        })

        fig2 = px.pie(approval_data, values='Count', names='Status',
                      title='Account Approval Status',
                      color_discrete_sequence=['#11998e', '#f5576c'],
                      hole=0.4)

        fig2.update_layout(
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
            height=400,
            margin=dict(t=50, l=0, r=0, b=0),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font_family="Times New Roman, Times, serif"
        )

        fig2.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig2, use_container_width=True)

    with col2:
        st.markdown("#### 📅 User Activity (Last 7 Days)")

        if 'active_last_7_days' in stats:
            activity_data = pd.DataFrame({
                'Category': ['Active Users', 'Inactive Users'],
                'Count': [stats['active_last_7_days'], stats['inactive_last_7_days']]
            })

            fig3 = px.bar(activity_data, x='Category', y='Count',
                         title='User Activity Status',
                         color='Category',
                         color_discrete_sequence=['#38ef7d', '#f5576c'],
                         text='Count')

            fig3.update_traces(textposition='outside')
            fig3.update_layout(
                showlegend=False,
                height=400,
                margin=dict(t=50, l=0, r=0, b=0),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                xaxis_title="",
                yaxis_title="Number of Users",
                font_family="Times New Roman, Times, serif"
            )
            st.plotly_chart(fig3, use_container_width=True)

        st.markdown("#### ⏰ Hourly Activity Pattern")

        if 'hourly_activity' in stats and not stats['hourly_activity'].empty:
            hourly_df = stats['hourly_activity'].copy()
            hourly_df = hourly_df.dropna()

            if not hourly_df.empty:
                fig4 = px.line(hourly_df, x='active_hour', y='count',
                              title='User Activity by Hour of Day',
                              markers=True,
                              line_shape='spline')

                fig4.update_traces(line=dict(color='#4A90D9', width=3),
                                  marker=dict(size=8, color='#87CEEB'))

                fig4.update_layout(
                    height=400,
                    margin=dict(t=50, l=0, r=0, b=0),
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    xaxis_title="Hour of Day (0-23)",
                    yaxis_title="Number of Active Users",
                    xaxis=dict(tickmode='linear', tick0=0, dtick=2),
                    font_family="Times New Roman, Times, serif"
                )
                st.plotly_chart(fig4, use_container_width=True)
            else:
                st.info("No hourly activity data available")
        else:
            st.info("No hourly activity data available")

    # Registration trends over time
    st.markdown("---")
    st.markdown("#### 📊 User Registration Trends")

    if 'daily_registrations' in stats and not stats['daily_registrations'].empty:
        reg_df = stats['daily_registrations'].copy()
        reg_df['created_date'] = pd.to_datetime(reg_df['created_date'])
        reg_df = reg_df.sort_values('created_date')

        # Apply time range filter
        if time_range == "Last 7 Days":
            cutoff = get_current_time().date() - timedelta(days=7)
            reg_df = reg_df[reg_df['created_date'].dt.date >= cutoff]
        elif time_range == "Last 30 Days":
            cutoff = get_current_time().date() - timedelta(days=30)
            reg_df = reg_df[reg_df['created_date'].dt.date >= cutoff]

        if not reg_df.empty:
            fig5 = go.Figure()

            # Add bar chart
            fig5.add_trace(go.Bar(
                x=reg_df['created_date'],
                y=reg_df['count'],
                name='New Users',
                marker_color='#4A90D9',
                text=reg_df['count'],
                textposition='outside'
            ))

            # Add trend line if enough data points
            if len(reg_df) >= 3:
                fig5.add_trace(go.Scatter(
                    x=reg_df['created_date'],
                    y=reg_df['count'].rolling(window=3, min_periods=1).mean(),
                    name='Trend (3-day MA)',
                    line=dict(color='#f5576c', width=2, dash='dash'),
                    mode='lines+markers'
                ))

            fig5.update_layout(
                title='New User Registrations Over Time',
                xaxis_title='Date',
                yaxis_title='Number of Registrations',
                height=450,
                hovermode='x unified',
                showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font_family="Times New Roman, Times, serif"
            )

            st.plotly_chart(fig5, use_container_width=True)

            # Show statistics summary
            with st.expander("📈 Detailed Statistics"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    avg_registrations = reg_df['count'].mean()
                    st.metric("Average Daily Registrations", f"{avg_registrations:.1f}")
                with col2:
                    max_registrations = reg_df['count'].max()
                    max_date = reg_df[reg_df['count'] == max_registrations]['created_date'].iloc[0].strftime('%Y-%m-%d')
                    st.metric("Peak Registrations", f"{max_registrations} (on {max_date})")
                with col3:
                    total_period = reg_df['count'].sum()
                    st.metric(f"Total Registrations ({time_range})", total_period)
        else:
            st.info("No registration data available for the selected time range")
    else:
        st.info("No registration data available")

    # Export functionality
    st.markdown("---")
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        if st.button("📥 Export Statistics Report", use_container_width=True):
            # Create report data
            report_data = {
                'Metric': ['Total Users', 'Approved Users', 'Pending Users', 'Admin Users', 'Regular Users', 'Active Last 7 Days'],
                'Value': [stats.get('total_users', 0), stats.get('approved_users', 0), 
                         stats.get('pending_users', 0), stats.get('admin_users', 0),
                         stats.get('regular_users', 0), stats.get('active_last_7_days', 0)]
            }
            report_df = pd.DataFrame(report_data)

            # Convert to CSV
            csv = report_df.to_csv(index=False)
            st.download_button(
                label="📥 Download CSV",
                data=csv,
                file_name=f"user_statistics_{get_current_time().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )
    with col2:
        if st.button("📸 Export Charts", use_container_width=True):
            st.info("Charts exported - Use browser screenshot or Plotly save functionality")

# Keep in sync with TAB_OPTIONS in planning.py (internal keys are what is stored in each user's tab access).
SUPPLY_TAB_OPTIONS = [
    "Action Plan Dashboard",
    "Historical Data",
    "Expert Action Plan",
    "AP Progress Review",
    "System Generated Action Plan",
]
SUPPLY_TAB_LABELS = {                      # display names only
    "Action Plan Dashboard": "AP Dashboard",
    "System Generated Action Plan": "System Action Plan",
}
# Old saved value -> the tabs it now stands for (users saved before the split keep their access)
_LEGACY_TAB_ALIASES = {"Action Plan Follow Up": ["Action Plan Dashboard", "AP Progress Review"]}


def _expand_legacy_tabs(tabs):
    out = []
    for t in (tabs or []):
        out.append(t)
        out.extend(_LEGACY_TAB_ALIASES.get(t, []))
    return list(dict.fromkeys(out))
_MODULE_LABEL = {k: f"{MODULE_ICONS[k]} {v}" for k, v in MODULES.items()}


def show_forced_password_reset():
    """Shown right after login when an admin has approved this user's password-reset request."""
    user = st.session_state.get('user')
    if not user or not has_approved_password_reset(user['id']):
        st.session_state['force_password_reset'] = False
        return False
    st.markdown("""
    <div style="max-width: 600px; margin: 40px auto; background: white; border-radius: 16px; padding: 30px; box-shadow: 0 8px 30px rgba(0,0,0,0.15); border-top: 5px solid #2e86c1;">
        <h2 style="color: #1a5276; text-align: center;">🔑 Set Your New Password</h2>
        <p style="color: #555; text-align: center;">Your password reset request has been approved. Please set a new password to continue.</p>
    </div>
    """, unsafe_allow_html=True)
    _, col2, _ = st.columns([1, 2, 1])
    with col2:
        with st.form("forced_reset_form", clear_on_submit=True):
            new_pw = st.text_input("New Password", type="password", key="fr_new")
            confirm_pw = st.text_input("Confirm New Password", type="password", key="fr_confirm")
            if st.form_submit_button("✅ Set New Password", type="primary", use_container_width=True):
                if not new_pw or not confirm_pw:
                    st.warning("Please fill both fields.")
                elif new_pw != confirm_pw:
                    st.error("Passwords do not match.")
                elif len(new_pw) < 6:
                    st.error("Password must be at least 6 characters.")
                else:
                    ok, msg = complete_password_reset(user['id'], new_pw)
                    if ok:
                        st.success(msg)
                        time.sleep(1.2)
                        logout_user()
                    else:
                        st.error(msg)
        if st.button("🚪 Cancel & Logout", use_container_width=True):
            logout_user()
    return True


def _ok_box(text):
    st.markdown(
        f"<div style='background:#d4edda;color:#155724;padding:8px 12px;border-radius:8px;"
        f"border:1px solid #c3e6cb;font-weight:600;margin-top:6px;'>✅ {text}</div>",
        unsafe_allow_html=True)


def _access_editor(uid, module, label, program_options, tab_options, supply_style):
    """Program + tab restrictions for one module (Stock, or Supply/Forecasting)."""
    st.markdown(f"##### {label}")
    c1, c2 = st.columns(2)
    with c1:
        cur = get_module_access(uid, module, "program")
        if not supply_style and not cur:
            cur = ["All"]
        sel = st.multiselect("Programs", program_options,
                             default=[p for p in cur if p in program_options],
                             key=f"prog_{module}_{uid}",
                             help=("No selection = NO programs." if supply_style else "No selection = All programs."))
        if st.button("📋 Update Programs", key=f"upd_prog_{module}_{uid}", use_container_width=True):
            if update_module_access(uid, module, "program", sel):
                _ok_box("Program access updated!")
            else:
                st.error("❌ Failed to update program access.")
    with c2:
        cur = _expand_legacy_tabs(get_module_access(uid, module, "tab"))
        if not cur or "All" in cur:
            cur = list(tab_options)
        sel_t = st.multiselect("Tabs", tab_options, default=[t for t in cur if t in tab_options],
                               format_func=lambda t: SUPPLY_TAB_LABELS.get(t, t) if module == "supply" else t,
                               key=f"tab_{module}_{uid}")
        if st.button("🗂️ Update Tabs", key=f"upd_tab_{module}_{uid}", use_container_width=True):
            vals = ["All"] if (not sel_t or set(sel_t) == set(tab_options)) else sel_t
            if update_module_access(uid, module, "tab", vals):
                _ok_box("Tab access updated!")
            else:
                st.error("❌ Failed to update tab access.")


def _single_user_editor(row):
    """Edit one user (role, status, modules, per-module restrictions)."""
    uid = row["id"]
    uid = int(uid) if str(uid).isdigit() else uid

    col_role, col_active, col_mods = st.columns([1, 1, 2])
    with col_role:
        st.markdown("##### 🔑 Role")
        cur_role = row.get("role") if row.get("role") in ROLES else "viewer"
        new_role = st.selectbox("Role", ROLES, index=ROLES.index(cur_role), key=f"role_{uid}",
                                format_func=lambda x: {"viewer": "👁️ View", "editor": "✏️ Editor", "admin": "👑 Admin"}[x])
        if st.button("🔑 Update Role", key=f"upd_role_{uid}", use_container_width=True):
            if update_user_role(uid, new_role):
                _ok_box(f"Role updated to <b>{new_role}</b>")
    with col_active:
        st.markdown("##### 🚦 Account")
        is_act = st.checkbox("Account active", value=row.get("is_active") is not False, key=f"act_{uid}")
        if st.button("💾 Save Status", key=f"upd_act_{uid}", use_container_width=True):
            if uid == st.session_state['user']['id'] and not is_act:
                st.error("❌ You cannot deactivate your own account!")
            elif toggle_user_active(uid, is_act):
                _ok_box("Status updated")
    with col_mods:
        st.markdown("##### 🧩 Module Access")
        cur_mods = [m for m in (row.get("module_access") or "").split(",") if m.strip() in MODULES]
        cur_mods = [m.strip() for m in cur_mods]
        new_mods = st.multiselect("Modules this user can open", list(MODULES), default=cur_mods,
                                  format_func=lambda k: _MODULE_LABEL[k], key=f"mods_{uid}",
                                  help="Admins can always open every module.")
        if st.button("🧩 Update Modules", key=f"upd_mods_{uid}", use_container_width=True):
            if update_user_modules(uid, new_mods):
                _ok_box("Module access updated")

    st.markdown("#### 🔒 Restrictions per module")
    e1, e2 = st.columns(2)
    with e1:
        _access_editor(uid, "stock", "📦 Stock Management", PROGRAM_OPTIONS, MAIN_TAB_OPTIONS, supply_style=False)
    with e2:
        _access_editor(uid, "supply", "🗂️ Supply Planning & 📈 Forecasting", PROGRAM_OPTIONS, SUPPLY_TAB_OPTIONS, supply_style=True)


def _bulk_user_editor(rows):
    """Apply one change to several selected users at once. Nothing is pre-filled, because the users may differ."""
    me = st.session_state['user']['id']
    uids = [(int(r["id"]) if str(r["id"]).isdigit() else r["id"]) for _, r in rows.iterrows()]
    n = len(uids)
    sig = "_".join(str(u) for u in uids)           # new selection -> fresh widgets
    st.info(f"✏️ Bulk edit: each button below applies **only its own setting** to all **{n}** selected users.")

    def _apply(fn, what, skip_self=False):
        done, failed = 0, []
        for u in uids:
            if skip_self and u == me:
                continue
            try:
                ok = fn(u)
            except Exception:
                ok = False
            if ok:
                done += 1
            else:
                failed.append(str(u))
        if failed:
            st.error(f"❌ {what}: failed for {len(failed)} user(s) (ids: {', '.join(failed)}). Updated {done}.")
        else:
            _ok_box(f"{what}: updated {done} user(s)")
        if skip_self and me in uids:
            st.caption("Your own account was skipped.")

    col_role, col_active, col_mods = st.columns([1, 1, 2])
    with col_role:
        st.markdown("##### 🔑 Role")
        new_role = st.selectbox("Role for all selected", ROLES, key=f"bulk_role_{sig}",
                                format_func=lambda x: {"viewer": "👁️ View", "editor": "✏️ Editor", "admin": "👑 Admin"}[x])
        if st.button(f"🔑 Update Role ({n})", key=f"bulk_upd_role_{sig}", use_container_width=True):
            _apply(lambda u: update_user_role(u, new_role), f"Role set to {new_role}", skip_self=(new_role != "admin"))
    with col_active:
        st.markdown("##### 🚦 Account")
        is_act = st.checkbox("Account active", value=True, key=f"bulk_act_{sig}")
        if st.button(f"💾 Save Status ({n})", key=f"bulk_upd_act_{sig}", use_container_width=True):
            _apply(lambda u: toggle_user_active(u, is_act), "Status", skip_self=not is_act)
    with col_mods:
        st.markdown("##### 🧩 Module Access")
        new_mods = st.multiselect("Modules for all selected", list(MODULES), format_func=lambda k: _MODULE_LABEL[k],
                                  key=f"bulk_mods_{sig}", help="Replaces each selected user's modules with this list.")
        if st.button(f"🧩 Update Modules ({n})", key=f"bulk_upd_mods_{sig}", use_container_width=True):
            _apply(lambda u: update_user_modules(u, new_mods), "Module access")

    st.markdown("#### 🔒 Restrictions per module")

    def _bulk_access(module, label, program_options, tab_options, supply_style):
        st.markdown(f"##### {label}")
        c1, c2 = st.columns(2)
        with c1:
            sel = st.multiselect("Programs", program_options, key=f"bulk_prog_{module}_{sig}",
                                 help=("No selection = NO programs." if supply_style else "No selection = All programs."))
            if st.button(f"📋 Update Programs ({n})", key=f"bulk_upd_prog_{module}_{sig}", use_container_width=True):
                vals = sel if (sel or supply_style) else ["All"]
                _apply(lambda u: update_module_access(u, module, "program", vals), "Program access")
        with c2:
            sel_t = st.multiselect("Tabs", tab_options, key=f"bulk_tab_{module}_{sig}",
                                   format_func=lambda t: SUPPLY_TAB_LABELS.get(t, t) if module == "supply" else t,
                                   help="No selection = All tabs.")
            if st.button(f"🗂️ Update Tabs ({n})", key=f"bulk_upd_tab_{module}_{sig}", use_container_width=True):
                vals = ["All"] if (not sel_t or set(sel_t) == set(tab_options)) else sel_t
                _apply(lambda u: update_module_access(u, module, "tab", vals), "Tab access")

    e1, e2 = st.columns(2)
    with e1:
        _bulk_access("stock", "📦 Stock Management", PROGRAM_OPTIONS, MAIN_TAB_OPTIONS, False)
    with e2:
        _bulk_access("supply", "🗂️ Supply Planning & 📈 Forecasting", PROGRAM_OPTIONS, SUPPLY_TAB_OPTIONS, True)



def show_admin_panel():
    """Unified admin panel: approvals, module access, roles, restrictions, resets."""
    st.markdown("<h1 style='font-size: 32px; font-weight: bold; color: #4A90D9; font-family: Times New Roman, Times, serif;'>👑 Admin Panel - User Management</h1>", unsafe_allow_html=True)
    current_time = get_current_time()
    st.markdown(f"""
    <div style="text-align: right; margin-bottom: 20px; padding: 10px; background: rgba(74,144,217,0.1); border-radius: 10px;">
        <small style="font-family: 'Times New Roman', Times, serif;">🕐 Local Time (Addis Ababa): {current_time.strftime('%Y-%m-%d %H:%M:%S')}</small>
    </div>
    """, unsafe_allow_html=True)

    pending_df = get_pending_users()
    all_users = get_all_users()
    reset_reqs = [r for r in get_password_reset_requests() if not r.get('password_reset_approved')]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("👥 Total Users", len(all_users))
    c2.metric("✅ Approved Users", int(all_users['is_approved'].astype(bool).sum()) if not all_users.empty else 0)
    c3.metric("⏳ Pending Approvals", len(pending_df))
    c4.metric("🟢 Online Now", len(get_online_users()))
    st.markdown("---")

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 User Statistics", f"⏳ Pending Approvals ({len(pending_df)})", "🟢 Online Users",
        "📋 All Users", "➕ Add New User", f"🔑 Password Resets ({len(reset_reqs)})"])

    with tab1:
        show_user_statistics()

    # ---------------- pending: choose modules when approving
    with tab2:
        st.markdown("### ⏳ Users Awaiting Approval")
        if not pending_df.empty:
            for _, row in pending_df.iterrows():
                rid = row['id']
                a, b, c = st.columns([2, 2, 2])
                a.write(f"**{row['full_name']}**")
                b.write(row['email'])
                c.write(f"📅 {format_time_for_display(row['created_at']) if row.get('created_at') else 'Unknown'}")
                m1, m2, m3, m4 = st.columns([3, 1.5, 1, 1])
                mods = m1.multiselect("Modules to grant", list(MODULES), format_func=lambda k: _MODULE_LABEL[k],
                                      key=f"pend_mods_{rid}")
                role = m2.selectbox("Role", ROLES, key=f"pend_role_{rid}")
                m3.markdown("<br>", unsafe_allow_html=True)
                if m3.button("✅ Approve", key=f"approve_{rid}", disabled=not mods and role != 'admin'):
                    if approve_user(rid, modules=mods, role=role):
                        st.success(f"✅ Approved {row['full_name']}")
                        st.rerun()
                m4.markdown("<br>", unsafe_allow_html=True)
                if m4.button("❌ Reject", key=f"reject_{rid}"):
                    if reject_user(rid):
                        st.warning(f"❌ Rejected {row['full_name']}")
                        st.rerun()
                st.divider()
        else:
            st.success("✅ No pending approvals. All users have been approved.")

    with tab3:
        show_online_users()

    # ---------------- all users + edit
    with tab4:
        if all_users.empty:
            st.info("No users found")
        else:
            disp = all_users.copy()
            for col in ('last_active', 'created_at'):
                if col in disp.columns:
                    disp[col] = disp[col].apply(lambda x: 'Never' if (x is None or x == 'None' or pd.isna(x)) else format_time_for_display(x))
            disp['status'] = disp.apply(
                lambda r: "⛔ Inactive" if r.get('is_active') is False else ("✅ Approved" if r.get('is_approved') else "⏳ Pending"), axis=1)
            cols = [c for c in ('id', 'email', 'full_name', 'role', 'status', 'module_access', 'last_active', 'created_at') if c in disp.columns]
            st.dataframe(disp[cols], use_container_width=True, hide_index=True)

            st.markdown("---")
            st.markdown("### ✏️ Edit User")
            names = [f"{r['full_name']} ({r['email']})" for _, r in all_users.iterrows()]
            all_sel = st.checkbox("Select all users", key="edit_user_all")
            picked = st.multiselect("Select user(s) to edit", range(len(names)), format_func=lambda x: names[x],
                                    default=list(range(len(names))) if all_sel else None,
                                    key=f"edit_user_select_{'all' if all_sel else 'some'}",
                                    help="Pick one user to edit them, or several to change the same setting for all of them.")
            if not picked:
                st.info("Select at least one user.")
            elif len(picked) == 1:
                _single_user_editor(all_users.iloc[picked[0]])
            else:
                _bulk_user_editor(all_users.iloc[picked])

            st.markdown("---")
            st.markdown("### 🗑️ Delete User")
            st.warning("⚠️ Deleting a user permanently removes their account (for ALL modules). This cannot be undone.")
            d1, d2 = st.columns([3, 1])
            user_to_delete = d1.selectbox("Select user to delete", all_users['email'].tolist(), key="delete_user_select")
            d2.markdown("<br>", unsafe_allow_html=True)
            confirm_delete = d2.checkbox("I confirm deletion", key="confirm_delete")
            if st.button("🗑️ Delete Selected User", type="secondary", use_container_width=True, disabled=not confirm_delete):
                if user_to_delete == st.session_state['user']['email']:
                    st.error("❌ You cannot delete your own account!")
                else:
                    ok, msg = delete_user(all_users[all_users['email'] == user_to_delete].iloc[0]['id'])
                    (st.success if ok else st.error)(f"{'✅' if ok else '❌'} {msg}")
                    if ok:
                        st.rerun()

    # ---------------- add user
    with tab5:
        with st.form("add_user_form"):
            a, b = st.columns(2)
            new_email = a.text_input("Email")
            new_full_name = a.text_input("Full Name")
            new_role = b.selectbox("Role", ROLES)
            new_password = b.text_input("Password", type="password")
            new_mods = st.multiselect("Modules", list(MODULES), default=list(MODULES), format_func=lambda k: _MODULE_LABEL[k])
            auto_approve = st.checkbox("Auto-approve this user", value=True)
            if st.form_submit_button("➕ Add User", type="primary", use_container_width=True):
                if not (new_email and new_full_name and new_password):
                    st.error("❌ Please fill all fields")
                elif len(new_password) < 6:
                    st.error("❌ Password must be at least 6 characters")
                elif not new_mods and new_role != 'admin':
                    st.error("❌ Choose at least one module")
                else:
                    ok, msg = add_user_by_admin(new_email, new_full_name, new_password, new_role, new_mods, auto_approve)
                    if ok:
                        st.success(f"✅ User {new_email} added successfully!")
                        st.rerun()
                    else:
                        st.error(f"❌ {msg}")

    # ---------------- password resets
    with tab6:
        st.markdown("### 🔑 Password Reset Requests")
        reqs = get_password_reset_requests()
        if not reqs:
            st.info("✅ No pending password reset requests.")
        for req in reqs:
            approved = bool(req.get('password_reset_approved'))
            stamp = (req.get('password_reset_approved_at') if approved else req.get('password_reset_requested_at')) or ''
            st.markdown(f"**{req.get('full_name', 'Unknown')}** · 📧 {req.get('email', '')} · "
                        f"{'✅ approved' if approved else '⏳ requested'} {str(stamp)[:19]}")
            x, y, _ = st.columns([1, 1, 3])
            if not approved:
                if x.button("✅ Approve", key=f"appr_reset_{req['id']}", use_container_width=True):
                    if approve_password_reset(req['id']):
                        st.rerun()
                if y.button("❌ Reject", key=f"rej_reset_{req['id']}", use_container_width=True):
                    if reject_password_reset(req['id']):
                        st.rerun()
            elif x.button("↩️ Revoke", key=f"revoke_reset_{req['id']}", use_container_width=True):
                if reject_password_reset(req['id']):
                    st.rerun()
            st.divider()


def main():
    """Main authentication function - called by dashboard"""
    init_session_state()

    if st.session_state.get('auth'):
        check_session_validity()
        # Show footer on all authenticated pages
        show_footer()
        return True
    else:
        show_login_page()
        return False

# For standalone testing
if __name__ == "__main__":
    main()
