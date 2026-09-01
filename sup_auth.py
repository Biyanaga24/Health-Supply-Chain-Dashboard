"""
Supabase Authentication Module for Supply Planning Dashboard
Provides authentication, user management, and access control functions
Uses the 'supply_users' table in Supabase
"""

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
import re

# Suppress warnings
warnings.filterwarnings("ignore")
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("requests").setLevel(logging.ERROR)

# ============================================================
# SUPABASE INITIALIZATION
# ============================================================

@st.cache_resource
def init_supabase():
    """Initialize Supabase client with credentials from secrets"""
    try:
        supabase_url = st.secrets["SUPABASE_URL"]
        supabase_key = st.secrets["SUPABASE_KEY"]
        return create_client(supabase_url, supabase_key)
    except Exception as e:
        st.error(f"Supabase connection error: {e}")
        return None

_supabase = None

def get_supabase():
    """Get cached Supabase client instance"""
    global _supabase
    if _supabase is None:
        _supabase = init_supabase()
    return _supabase

# ============================================================
# TIMEZONE CONFIGURATION
# ============================================================

ADDIS_ABABA_TZ = pytz.timezone('Africa/Addis_Ababa')

def get_current_time():
    """Get current time in Addis Ababa timezone"""
    return datetime.now(ADDIS_ABABA_TZ)

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
    if hasattr(dt, 'tzinfo'):
        if dt.tzinfo is None:
            dt = pytz.UTC.localize(dt).astimezone(ADDIS_ABABA_TZ)
        else:
            dt = dt.astimezone(ADDIS_ABABA_TZ)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return str(dt)

# ============================================================
# USER AUTHENTICATION FUNCTIONS - USING supply_users TABLE
# ============================================================

def authenticate_user(email, password):
    """Authenticate user from Supabase supply_users table - Checks if approved"""
    supabase = get_supabase()
    if supabase is None:
        return None

    # Hash the password using SHA256
    hashed = hashlib.sha256(password.encode()).hexdigest()

    try:
        # Query user by email and hashed password from supply_users table
        # NOTE: Using 'password_hash' column as per schema
        response = supabase.table("supply_users") \
            .select("*") \
            .eq("email", email) \
            .eq("password_hash", hashed) \
            .execute()

        if response.data:
            user = response.data[0]

            # Check if user is approved (is_approved = true)
            if not user.get('is_approved', False):
                return {'error': 'not_approved'}

            # Check if user is active (is_active = true)
            if not user.get('is_active', True):
                return {'error': 'inactive'}

            return {
                'id': user.get('id'),
                'email': user['email'],
                'full_name': user.get('full_name', user['email'].split('@')[0]),
                'role': user.get('role', 'viewer'),
                'is_approved': user.get('is_approved', False),
                'is_active': user.get('is_active', True),
                'program_access': user.get('program_access', ''),
                'created_at': user.get('created_at'),
                'last_login': user.get('last_login')
            }
        else:
            return None
    except Exception as e:
        st.error(f"Authentication error: {e}")
        return None

def create_user(email, password, full_name):
    """Create new user in Supabase supply_users table - Pending approval by default"""
    supabase = get_supabase()
    if supabase is None:
        return False, "Database connection error"

    try:
        # Hash the password using SHA256
        hashed = hashlib.sha256(password.encode()).hexdigest()

        # Check if user already exists
        existing = supabase.table("supply_users").select("*").eq("email", email).execute()
        if existing.data:
            return False, "Email already exists. Please use a different email."

        current_time = get_current_time().isoformat()

        # Insert new user with password_hash column
        supabase.table("supply_users").insert({
            "email": email,
            "password_hash": hashed,  # Using password_hash column
            "full_name": full_name,
            "role": "viewer",
            "is_approved": False,  # Pending approval
            "is_active": True,
            "program_access": "",
            "created_at": current_time,
            "last_login": current_time,
            "updated_at": current_time
        }).execute()
        return True, "Registration successful! Your account is pending admin approval."
    except Exception as e:
        return False, f"Registration failed: {str(e)}"

def change_password(user_id, old_password, new_password):
    """Change user password"""
    supabase = get_supabase()
    if supabase is None:
        return False, "Database connection error"

    try:
        hashed_old = hashlib.sha256(old_password.encode()).hexdigest()

        # Verify old password using password_hash column
        response = supabase.table("supply_users") \
            .select("id") \
            .eq("id", user_id) \
            .eq("password_hash", hashed_old) \
            .execute()

        if not response.data:
            return False, "Current password is incorrect"

        # Update to new password
        hashed_new = hashlib.sha256(new_password.encode()).hexdigest()
        current_time = get_current_time().isoformat()

        supabase.table("supply_users") \
            .update({
                "password_hash": hashed_new,
                "updated_at": current_time
            }) \
            .eq("id", user_id) \
            .execute()

        return True, "Password changed successfully! Please login again."
    except Exception as e:
        return False, f"Failed to change password: {e}"

# ============================================================
# USER MANAGEMENT FUNCTIONS - USING supply_users TABLE
# ============================================================

def get_all_users():
    """Get all users from supply_users table"""
    supabase = get_supabase()
    if supabase is None:
        return []

    try:
        response = supabase.table("supply_users") \
            .select("*") \
            .order("created_at", desc=True) \
            .execute()

        if response.data:
            users = []
            for user in response.data:
                # Remove password_hash from response
                user_copy = {k: v for k, v in user.items() if k != 'password_hash'}
                users.append(user_copy)
            return users
        return []
    except Exception as e:
        st.error(f"Error getting users: {e}")
        return []

def get_pending_users():
    """Get all pending users (is_approved = false) from supply_users table"""
    supabase = get_supabase()
    if supabase is None:
        return []

    try:
        response = supabase.table("supply_users") \
            .select("id, email, full_name, created_at") \
            .eq("is_approved", False) \
            .order("created_at", desc=False) \
            .execute()

        if response.data:
            return response.data
        return []
    except Exception as e:
        st.error(f"Error getting pending users: {e}")
        return []

def approve_user(user_id):
    """Approve a user (set is_approved = true) in supply_users table"""
    supabase = get_supabase()
    if supabase is None:
        return False

    try:
        current_time = get_current_time().isoformat()
        supabase.table("supply_users") \
            .update({
                "is_approved": True,
                "updated_at": current_time
            }) \
            .eq("id", user_id) \
            .execute()
        return True
    except Exception as e:
        return False

def reject_user(user_id):
    """Reject/delete a user from supply_users table"""
    supabase = get_supabase()
    if supabase is None:
        return False

    try:
        supabase.table("supply_users").delete().eq("id", user_id).execute()
        return True
    except Exception as e:
        return False

def update_user_role(user_id, new_role):
    """Update a user's role in supply_users table"""
    supabase = get_supabase()
    if supabase is None:
        return False

    try:
        current_time = get_current_time().isoformat()
        supabase.table("supply_users") \
            .update({
                "role": new_role,
                "updated_at": current_time
            }) \
            .eq("id", user_id) \
            .execute()
        return True
    except Exception as e:
        return False

def toggle_user_active(user_id, is_active):
    """Activate or deactivate a user in supply_users table"""
    supabase = get_supabase()
    if supabase is None:
        return False

    try:
        current_time = get_current_time().isoformat()
        supabase.table("supply_users") \
            .update({
                "is_active": is_active,
                "updated_at": current_time
            }) \
            .eq("id", user_id) \
            .execute()
        return True
    except Exception as e:
        return False

def update_user_program_access(user_id, programs):
    """Update a user's program access in supply_users table"""
    supabase = get_supabase()
    if supabase is None:
        return False

    try:
        program_str = ", ".join(programs) if programs else ""
        current_time = get_current_time().isoformat()
        supabase.table("supply_users") \
            .update({
                "program_access": program_str,
                "updated_at": current_time
            }) \
            .eq("id", user_id) \
            .execute()
        return True
    except Exception as e:
        return False

def delete_user(user_id):
    """Delete a user from supply_users table"""
    supabase = get_supabase()
    if supabase is None:
        return False, "Database connection error"

    try:
        response = supabase.table("supply_users") \
            .select("id, email, full_name") \
            .eq("id", user_id) \
            .execute()

        if not response.data:
            return False, f"User with ID {user_id} not found"

        user = response.data[0]
        supabase.table("supply_users").delete().eq("id", user_id).execute()
        return True, f"User {user.get('full_name', user.get('email'))} deleted successfully"
    except Exception as e:
        return False, str(e)

# ============================================================
# SESSION MANAGEMENT FUNCTIONS
# ============================================================

def update_user_session(user_id, session_id=None):
    """Update user's last login timestamp with Addis Ababa time in supply_users table"""
    supabase = get_supabase()
    if supabase is None:
        return False

    try:
        current_time = get_current_time().isoformat()
        supabase.table("supply_users") \
            .update({
                "last_login": current_time,
                "updated_at": current_time
            }) \
            .eq("id", user_id) \
            .execute()
        return True
    except Exception as e:
        return False

def get_online_users():
    """Get list of users currently online (active in last 5 minutes) from supply_users table"""
    supabase = get_supabase()
    if supabase is None:
        return []

    try:
        current_time = get_current_time()
        five_minutes_ago = current_time - timedelta(minutes=5)

        response = supabase.table("supply_users") \
            .select("id, email, full_name, role, last_login, created_at") \
            .eq("is_approved", True) \
            .eq("is_active", True) \
            .gt("last_login", five_minutes_ago.isoformat()) \
            .execute()

        if response.data:
            online_users = sorted(response.data, key=lambda x: x.get('last_login', ''), reverse=True)
            for user in online_users:
                if user.get('last_login'):
                    user['last_active_display'] = format_time_for_display(user['last_login'])
                else:
                    user['last_active_display'] = "Unknown"
            return online_users
        return []
    except Exception as e:
        print(f"Error getting online users: {e}")
        return []

# ============================================================
# ACCESS CONTROL FUNCTIONS
# ============================================================

def get_current_user():
    """Get current user from session state"""
    return st.session_state.get('user', None)

def get_user_role():
    """Get current user's role"""
    user = get_current_user()
    if user:
        return user.get('role', 'viewer')
    return None

def is_admin():
    """Check if current user is an admin"""
    return get_user_role() == 'admin'

def is_editor():
    """Check if current user is an editor or admin"""
    role = get_user_role()
    return role in ['editor', 'admin']

def require_auth():
    """Require authentication - returns True if authenticated"""
    if 'auth' not in st.session_state:
        st.session_state['auth'] = False

    if not st.session_state.get('auth'):
        show_login_page()
        return False

    # Update session activity
    if st.session_state.get('user'):
        now = get_current_time()
        if (now - st.session_state.get('last_activity', now)).seconds >= 30:
            update_user_session(st.session_state['user']['id'], st.session_state.get('session_id', ''))
            st.session_state['last_activity'] = now

    return True

def get_user_program_access():
    """Get program access list for current user"""
    user = get_current_user()
    if user:
        program_str = user.get('program_access', '')
        if program_str:
            return [p.strip() for p in program_str.split(',') if p.strip()]
        return []
    return []

def check_program_access(program_name):
    """Check if user has access to a specific program"""
    if is_admin():
        return True

    user_programs = get_user_program_access()
    if not user_programs:
        return False

    if "All" in user_programs:
        return True

    return program_name in user_programs

def logout():
    """Handle user logout"""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# ============================================================
# SESSION STATE INITIALIZATION
# ============================================================

def init_session_state():
    """Initialize all session state variables"""
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
    if 'show_admin_page' not in st.session_state:
        st.session_state['show_admin_page'] = False
    if 'data_loaded' not in st.session_state:
        st.session_state['data_loaded'] = False
    if 'selected_program' not in st.session_state:
        st.session_state['selected_program'] = "All"
    if 'selected_subcategory' not in st.session_state:
        st.session_state['selected_subcategory'] = "All"
    if 'selected_quarter' not in st.session_state:
        st.session_state['selected_quarter'] = "All"
    if 'selected_year' not in st.session_state:
        st.session_state['selected_year'] = "All"
    if 'selected_status' not in st.session_state:
        st.session_state['selected_status'] = "All"
    if 'action_plan_tab' not in st.session_state:
        st.session_state['action_plan_tab'] = "📋 All Issues"
    if 'expert_plan_records' not in st.session_state:
        st.session_state['expert_plan_records'] = []
    if 'edit_record_id' not in st.session_state:
        st.session_state['edit_record_id'] = None
    if 'show_material_info' not in st.session_state:
        st.session_state['show_material_info'] = False
    if 'show_change_list' not in st.session_state:
        st.session_state['show_change_list'] = False
    if 'adding_action_point' not in st.session_state:
        st.session_state['adding_action_point'] = False
    if 'selected_material_for_expert' not in st.session_state:
        st.session_state['selected_material_for_expert'] = None

# ============================================================
# LOGIN PAGE UI - UPDATED WITH REQUESTED CHANGES
# ============================================================

def show_login_page():
    """Display login page with login/register forms"""

    # Custom CSS for login page
    st.markdown("""
    <style>
    .stApp {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    }

    .hero-section {
        background: linear-gradient(135deg, #1a5276 0%, #2e86c1 50%, #1a5276 100%);
        border-radius: 20px;
        padding: 30px 40px;
        text-align: center;
        color: white;
        margin-bottom: 30px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        border: 2px solid rgba(255,255,255,0.1);
    }

    @keyframes pulse {
        0% { transform: scale(1); }
        50% { transform: scale(1.02); }
        100% { transform: scale(1); }
    }

    @keyframes slideIn {
        0% { transform: translateX(-100%); opacity: 0; }
        100% { transform: translateX(0); opacity: 1; }
    }

    @keyframes glow {
        0% { text-shadow: 0 0 10px rgba(255,215,0,0.3); }
        50% { text-shadow: 0 0 20px rgba(255,215,0,0.6), 0 0 30px rgba(255,215,0,0.3); }
        100% { text-shadow: 0 0 10px rgba(255,215,0,0.3); }
    }

    .hero-title {
        font-family: 'Times New Roman', Times, serif !important;
        font-size: 2.0rem !important;
        margin-bottom: 0.3rem !important;
        font-weight: bold;
        color: #ffd700;
        animation: pulse 3s ease-in-out infinite, glow 2s ease-in-out infinite;
        letter-spacing: 2px;
    }

    .hero-subtitle {
        font-family: 'Times New Roman', Times, serif !important;
        font-size: 1.0rem !important;
        opacity: 0.95;
        animation: slideIn 0.8s ease-out;
        color: #e8f4fd;
    }

    .auth-container {
        background: white;
        border-radius: 20px;
        padding: 30px;
        box-shadow: 0 15px 40px rgba(0,0,0,0.15);
        margin-bottom: 30px;
        border: 1px solid rgba(26, 82, 118, 0.2);
    }

    .time-display {
        text-align: center;
        padding: 12px;
        background: rgba(26, 82, 118, 0.08);
        border-radius: 10px;
        margin-bottom: 20px;
        font-size: 1rem;
        font-weight: 500;
        color: #1a5276;
        border: 1px solid rgba(26, 82, 118, 0.15);
        font-family: 'Times New Roman', Times, serif !important;
    }

    .feature-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
        gap: 20px;
        margin-top: 25px;
        margin-bottom: 25px;
    }
    .feature-card {
        background: white;
        border-radius: 15px;
        padding: 20px;
        text-align: center;
        transition: all 0.3s ease;
        box-shadow: 0 8px 25px rgba(0,0,0,0.1);
        border: 1px solid #e8e8e8;
    }
    .feature-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 15px 35px rgba(0,0,0,0.15);
        border-color: #2e86c1;
    }
    .feature-icon {
        font-size: 2.8rem;
        margin-bottom: 10px;
    }
    .feature-title {
        font-family: 'Times New Roman', Times, serif !important;
        font-size: 1.0rem;
        font-weight: 700;
        color: #1a5276;
        margin-bottom: 8px;
    }
    .feature-desc {
        color: #555;
        line-height: 1.4;
        font-size: 0.85rem;
        font-family: 'Times New Roman', Times, serif !important;
    }

    .info-section {
        background: linear-gradient(135deg, #1a5276 0%, #2e86c1 50%, #1a5276 100%);
        border-radius: 15px;
        padding: 30px;
        margin-top: 25px;
        color: white;
        box-shadow: 0 8px 25px rgba(0,0,0,0.1);
    }
    .info-section h3 {
        color: #ffd700;
        margin-bottom: 15px;
        font-size: 1.3rem;
        text-align: center;
        font-family: 'Times New Roman', Times, serif !important;
    }
    .step-box {
        background: rgba(255,255,255,0.12);
        border-radius: 12px;
        padding: 18px;
        text-align: left;
        backdrop-filter: blur(10px);
        transition: all 0.3s ease;
        border: 1px solid rgba(255,255,255,0.1);
        font-family: 'Times New Roman', Times, serif !important;
    }
    .step-box:hover {
        background: rgba(255,255,255,0.22);
        transform: translateX(5px);
        border-color: #ffd700;
    }
    .step-number {
        font-size: 1.6rem;
        font-weight: bold;
        margin-bottom: 5px;
        color: #ffd700;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 10px;
        padding: 10px 20px;
        font-weight: 600;
        background-color: #f0f2f6;
        font-family: 'Times New Roman', Times, serif !important;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #1a5276 0%, #2e86c1 100%);
        color: white;
    }

    .stButton > button {
        background: linear-gradient(135deg, #1a5276 0%, #2e86c1 100%);
        color: white;
        border: none;
        border-radius: 10px;
        font-weight: 600;
        padding: 10px;
        transition: all 0.3s ease;
        font-family: 'Times New Roman', Times, serif !important;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(26, 82, 118, 0.4);
    }

    .welcome-section {
        text-align: center;
        margin: 20px 0;
    }
    .welcome-title {
        font-family: 'Times New Roman', Times, serif !important;
        font-size: 1.6rem;
        color: #1a5276;
        font-weight: bold;
        margin-bottom: 10px;
    }
    .welcome-text {
        font-family: 'Times New Roman', Times, serif !important;
        font-size: 1rem;
        color: #555;
    }

    .login-header {
        font-family: 'Times New Roman', Times, serif !important;
        color: #1a5276;
    }

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
    """, unsafe_allow_html=True)

    # Display current Addis Ababa time
    current_time = get_current_time()
    st.markdown(f"""
    <div class="time-display">
        🕐 Addis Ababa Time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}
    </div>
    """, unsafe_allow_html=True)

    # Hero Section - UPDATED: Removed subtitle line, reduced font size, Times Roman, animated
    st.markdown("""
    <div class="hero-section">
        <div class="hero-title">📦 HPC Supply Planning Dashboard</div>
        <div class="hero-subtitle">Efficient Supply Chain Management for Health Programs</div>
    </div>
    """, unsafe_allow_html=True)

    # Create two columns
    left_col, right_col = st.columns([1, 1], gap="large")

    with left_col:
        st.markdown("""
        <div class="welcome-section">
            <div class="welcome-title">✨ Welcome!</div>
            <div class="welcome-text">Access the supply planning dashboard to monitor stock levels, generate action plans, and track progress.</div>
        </div>
        """, unsafe_allow_html=True)

        # Features - REMOVED Pipeline Tracking, updated with supply planning focus
        st.markdown("### 🚀 Key Features")

        features = [
            ("📊", "Historical Stock Data", "View NSOH, NMOS, Consumption, and Issue trends with interactive charts"),
            ("📋", "System Generated Action Plan", "AI-driven identification of stock issues with actionable recommendations"),
            ("👨‍💼", "Expert Action Plan", "Create, edit, and manage custom action plans with quarterly tracking"),
            ("📈", "Action Plan Follow Up", "Monitor action plan completion status with detailed progress tracking"),
            ("🔐", "Secure Access", "Role-based access with admin approval and program-level permissions"),
        ]

        for icon, title, desc in features:
            st.markdown(f"""
            <div style="background: white; border-radius: 12px; padding: 14px; margin-bottom: 10px; border-left: 4px solid #2e86c1; box-shadow: 0 2px 8px rgba(0,0,0,0.05);">
                <div style="display: flex; align-items: center; gap: 15px;">
                    <div style="font-size: 1.8rem;">{icon}</div>
                    <div>
                        <strong style="font-size: 1rem; color: #1a5276; font-family: 'Times New Roman', Times, serif;">{title}</strong>
                        <div style="color: #666; font-size: 0.85rem; font-family: 'Times New Roman', Times, serif;">{desc}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        # Add a distinguishing note about HPC
        st.markdown("""
        <div style="background: #eaf2f8; border-radius: 10px; padding: 15px; margin-top: 15px; border-left: 4px solid #1a5276;">
            <p style="font-family: 'Times New Roman', Times, serif; color: #1a5276; margin: 0; font-size: 0.9rem;">
                <strong>🏥 HPC Supply Planning</strong> — A comprehensive tool for health program supply chain management
            </p>
        </div>
        """, unsafe_allow_html=True)

    with right_col:
        st.markdown("""
        <div class="auth-container">
            <div style="text-align: center; margin-bottom: 20px;">
                <h2 style="color: #1a5276; margin: 0; font-family: 'Times New Roman', Times, serif;">🔐 Account Access</h2>
                <p style="color: #666; font-family: 'Times New Roman', Times, serif;">Login or create a new account</p>
            </div>
        """, unsafe_allow_html=True)

        # Tabs for Login and Register
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
                                if user['error'] == 'not_approved':
                                    st.error("⏳ Your account is pending admin approval. Please wait for approval.")
                                elif user['error'] == 'inactive':
                                    st.error("❌ Your account has been deactivated. Please contact admin.")
                            elif user:
                                st.session_state['auth'] = True
                                st.session_state['user'] = user
                                st.session_state['login_time'] = get_current_time()
                                st.session_state['last_activity'] = get_current_time()
                                update_user_session(user['id'], st.session_state.get('session_id', ''))
                                st.success("✅ Login successful! Redirecting...")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error("❌ Invalid email or password")
                    else:
                        st.warning("⚠️ Please enter both email and password")

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

    # Information Section
    st.markdown("""
    <div class="info-section">
        <h3>ℹ️ How to Get Started</h3>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-top: 15px;">
            <div class="step-box">
                <div class="step-number">1</div>
                <strong>Register Account</strong><br>
                <span style="font-size: 0.9rem; opacity: 0.9;">Create your account on the Register tab</span>
            </div>
            <div class="step-box">
                <div class="step-number">2</div>
                <strong>Wait for Approval</strong><br>
                <span style="font-size: 0.9rem; opacity: 0.9;">Admin will review and approve your account</span>
            </div>
            <div class="step-box">
                <div class="step-number">3</div>
                <strong>Login</strong><br>
                <span style="font-size: 0.9rem; opacity: 0.9;">Once approved, login to access the dashboard</span>
            </div>
            <div class="step-box">
                <div class="step-number">4</div>
                <strong>Start Planning</strong><br>
                <span style="font-size: 0.9rem; opacity: 0.9;">Analyze data, generate plans, and track progress</span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Footer
    st.markdown("""
    <div class="footer">
        © 2026 HPC Supply Planning Dashboard | Developed by Biyensa Negera
    </div>
    <div class="main-content"></div>
    """, unsafe_allow_html=True)

# ============================================================
# ADMIN USER CREATION HELPER - For debugging/testing
# ============================================================

def create_admin_user(email, password, full_name):
    """Create an admin user directly in supply_users table (for debugging/testing)"""
    supabase = get_supabase()
    if supabase is None:
        return False, "Database connection error"

    try:
        hashed = hashlib.sha256(password.encode()).hexdigest()

        # Check if user already exists
        existing = supabase.table("supply_users").select("*").eq("email", email).execute()
        if existing.data:
            return False, "Email already exists."

        current_time = get_current_time().isoformat()

        supabase.table("supply_users").insert({
            "email": email,
            "password_hash": hashed,  # Using password_hash column
            "full_name": full_name,
            "role": "admin",
            "is_approved": True,  # Auto-approved
            "is_active": True,
            "program_access": "All",
            "created_at": current_time,
            "last_login": current_time,
            "updated_at": current_time
        }).execute()
        return True, "Admin user created successfully!"
    except Exception as e:
        return False, f"Failed to create admin: {str(e)}"

# ============================================================
# MAIN FUNCTION FOR STANDALONE TESTING
# ============================================================

def main():
    """Main authentication function - called by dashboard"""
    init_session_state()

    if st.session_state.get('auth'):
        # Update session activity
        if st.session_state.get('user'):
            now = get_current_time()
            if (now - st.session_state.get('last_activity', now)).seconds >= 30:
                update_user_session(st.session_state['user']['id'], st.session_state.get('session_id', ''))
                st.session_state['last_activity'] = now
        return True
    else:
        show_login_page()
        return False

if __name__ == "__main__":
    main()
