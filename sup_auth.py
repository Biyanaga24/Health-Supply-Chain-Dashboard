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
# PASSWORD HASHING
# ============================================================

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# ============================================================
# USER AUTHENTICATION FUNCTIONS
# ============================================================

def authenticate_user(email, password):
    """
    Authenticate user from Supabase supply_users table.
    - Checks approval, active status.
    - Blocks login if a password reset is pending approval.
    - Blocks login if a password reset has been approved (must reset).
    """
    supabase = get_supabase()
    if supabase is None:
        return None

    hashed = hash_password(password)

    try:
        response = supabase.table("supply_users") \
            .select("*") \
            .eq("email", email) \
            .eq("password_hash", hashed) \
            .execute()

        if not response.data:
            return None

        user = response.data[0]

        if not user.get('is_approved', False):
            return {'error': 'not_approved'}

        if not user.get('is_active', True):
            return {'error': 'inactive'}

        # Password reset requested but not approved yet → block
        if user.get('password_reset_requested', False) and \
           not user.get('password_reset_approved', False):
            return {'error': 'reset_pending'}

        return {
            'id': user.get('id'),
            'email': user['email'],
            'full_name': user.get('full_name', user['email'].split('@')[0]),
            'role': user.get('role', 'viewer'),
            'is_approved': user.get('is_approved', False),
            'is_active': user.get('is_active', True),
            'program_access': user.get('program_access', ''),
            'tab_access': user.get('tab_access', 'All'),
            'created_at': user.get('created_at'),
            'last_login': user.get('last_login'),
            'updated_at': user.get('updated_at'),
            'password_reset_requested': user.get('password_reset_requested', False),
            'password_reset_approved': user.get('password_reset_approved', False),
        }
    except Exception as e:
        st.error(f"Authentication error: {e}")
        return None


def create_user(email, password, full_name):
    """Create new user in Supabase supply_users table - Pending approval by default"""
    supabase = get_supabase()
    if supabase is None:
        return False, "Database connection error"

    try:
        hashed = hash_password(password)

        existing = supabase.table("supply_users").select("*").eq("email", email).execute()
        if existing.data:
            return False, "Email already exists. Please use a different email."

        current_time = get_current_time().isoformat()

        supabase.table("supply_users").insert({
            "email": email,
            "password_hash": hashed,
            "full_name": full_name,
            "role": "viewer",
            "is_approved": False,
            "is_active": True,
            "program_access": "",
            "tab_access": "All",
            "password_reset_requested": False,
            "password_reset_approved": False,
            "created_at": current_time,
            "last_login": current_time,
            "updated_at": current_time
        }).execute()
        return True, "Registration successful! Your account is pending admin approval."
    except Exception as e:
        return False, f"Registration failed: {str(e)}"


def change_password(user_id, old_password, new_password):
    """Change user password (requires old password)"""
    supabase = get_supabase()
    if supabase is None:
        return False, "Database connection error"

    try:
        hashed_old = hash_password(old_password)

        response = supabase.table("supply_users") \
            .select("id") \
            .eq("id", user_id) \
            .eq("password_hash", hashed_old) \
            .execute()

        if not response.data:
            return False, "Current password is incorrect"

        hashed_new = hash_password(new_password)
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
# PROFILE FUNCTIONS (NEW)
# ============================================================

def update_user_profile(user_id, full_name=None):
    """Update user's own profile (full_name only). Email/role/program/tab are admin-only."""
    supabase = get_supabase()
    if supabase is None:
        return False, "Database connection error"

    try:
        current_time = get_current_time().isoformat()
        update_payload = {"updated_at": current_time}
        if full_name is not None and full_name.strip():
            update_payload["full_name"] = full_name.strip()

        supabase.table("supply_users") \
            .update(update_payload) \
            .eq("id", user_id) \
            .execute()
        return True, "Profile updated successfully."
    except Exception as e:
        return False, f"Failed to update profile: {e}"


def refresh_current_user():
    """Re-fetch the current user from DB and update session state."""
    user = st.session_state.get('user')
    if not user:
        return None
    supabase = get_supabase()
    if supabase is None:
        return user
    try:
        response = supabase.table("supply_users") \
            .select("*") \
            .eq("id", user['id']) \
            .execute()
        if response.data:
            u = response.data[0]
            st.session_state['user'] = {
                'id': u.get('id'),
                'email': u['email'],
                'full_name': u.get('full_name', u['email'].split('@')[0]),
                'role': u.get('role', 'viewer'),
                'is_approved': u.get('is_approved', False),
                'is_active': u.get('is_active', True),
                'program_access': u.get('program_access', ''),
                'tab_access': u.get('tab_access', 'All'),
                'created_at': u.get('created_at'),
                'last_login': u.get('last_login'),
                'updated_at': u.get('updated_at'),
                'password_reset_requested': u.get('password_reset_requested', False),
                'password_reset_approved': u.get('password_reset_approved', False),
            }
            return st.session_state['user']
    except Exception:
        pass
    return user


# ============================================================
# PASSWORD RESET FUNCTIONS (NEW)
# ============================================================

def request_password_reset(email):
    """User submits a password reset request."""
    supabase = get_supabase()
    if supabase is None:
        return False, "Database connection error"

    try:
        response = supabase.table("supply_users").select("*").eq("email", email).execute()
        if not response.data:
            # Don't leak whether email exists
            return True, "If your email exists, a reset request has been submitted to the admin."

        user = response.data[0]

        if user.get('password_reset_requested', False) and \
           not user.get('password_reset_approved', False):
            return True, "You already have a pending reset request. Please wait for admin approval."

        current_time = get_current_time().isoformat()
        supabase.table("supply_users").update({
            "password_reset_requested": True,
            "password_reset_approved": False,
            "password_reset_requested_at": current_time,
            "password_reset_approved_at": None,
            "updated_at": current_time
        }).eq("id", user['id']).execute()

        return True, "Your password reset request has been submitted. Please wait for admin approval."
    except Exception as e:
        return False, f"Failed to submit request: {e}"


def get_password_reset_requests():
    """Admin: get list of users with pending reset requests."""
    supabase = get_supabase()
    if supabase is None:
        return []
    try:
        response = supabase.table("supply_users") \
            .select("id, email, full_name, password_reset_requested, password_reset_approved, password_reset_requested_at, password_reset_approved_at") \
            .eq("password_reset_requested", True) \
            .order("password_reset_requested_at", desc=False) \
            .execute()
        return response.data or []
    except Exception as e:
        st.error(f"Error getting password reset requests: {e}")
        return []


def approve_password_reset(user_id):
    """Admin: approve a password reset request."""
    supabase = get_supabase()
    if supabase is None:
        return False
    try:
        current_time = get_current_time().isoformat()
        supabase.table("supply_users").update({
            "password_reset_approved": True,
            "password_reset_approved_at": current_time,
            "updated_at": current_time
        }).eq("id", user_id).execute()
        return True
    except Exception as e:
        st.error(f"Approve failed: {e}")
        return False


def reject_password_reset(user_id):
    """Admin: reject a password reset request (clears all flags)."""
    supabase = get_supabase()
    if supabase is None:
        return False
    try:
        current_time = get_current_time().isoformat()
        supabase.table("supply_users").update({
            "password_reset_requested": False,
            "password_reset_approved": False,
            "password_reset_requested_at": None,
            "password_reset_approved_at": None,
            "updated_at": current_time
        }).eq("id", user_id).execute()
        return True
    except Exception as e:
        st.error(f"Reject failed: {e}")
        return False


def has_approved_password_reset(user_id):
    """Check if the user has an approved (but not yet completed) password reset."""
    supabase = get_supabase()
    if supabase is None:
        return False
    try:
        response = supabase.table("supply_users") \
            .select("password_reset_requested, password_reset_approved") \
            .eq("id", user_id) \
            .execute()
        if response.data:
            u = response.data[0]
            return bool(u.get('password_reset_requested')) and bool(u.get('password_reset_approved'))
    except Exception:
        pass
    return False


def complete_password_reset(user_id, new_password):
    """User: complete the reset by setting a new password. Clears all reset flags."""
    supabase = get_supabase()
    if supabase is None:
        return False, "Database connection error"

    try:
        hashed = hash_password(new_password)
        current_time = get_current_time().isoformat()
        supabase.table("supply_users").update({
            "password_hash": hashed,
            "password_reset_requested": False,
            "password_reset_approved": False,
            "password_reset_requested_at": None,
            "password_reset_approved_at": None,
            "updated_at": current_time
        }).eq("id", user_id).execute()
        return True, "Password reset successfully! Please login with your new password."
    except Exception as e:
        return False, f"Failed to reset password: {e}"


# ============================================================
# USER MANAGEMENT (ADMIN)
# ============================================================

def get_all_users():
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
                user_copy = {k: v for k, v in user.items() if k != 'password_hash'}
                users.append(user_copy)
            return users
        return []
    except Exception as e:
        st.error(f"Error getting users: {e}")
        return []


def get_pending_users():
    supabase = get_supabase()
    if supabase is None:
        return []
    try:
        response = supabase.table("supply_users") \
            .select("id, email, full_name, created_at") \
            .eq("is_approved", False) \
            .order("created_at", desc=False) \
            .execute()
        return response.data or []
    except Exception as e:
        st.error(f"Error getting pending users: {e}")
        return []


def approve_user(user_id):
    supabase = get_supabase()
    if supabase is None:
        return False
    try:
        current_time = get_current_time().isoformat()
        supabase.table("supply_users") \
            .update({"is_approved": True, "updated_at": current_time}) \
            .eq("id", user_id).execute()
        return True
    except Exception:
        return False


def reject_user(user_id):
    supabase = get_supabase()
    if supabase is None:
        return False
    try:
        supabase.table("supply_users").delete().eq("id", user_id).execute()
        return True
    except Exception:
        return False


def update_user_role(user_id, new_role):
    supabase = get_supabase()
    if supabase is None:
        return False
    try:
        current_time = get_current_time().isoformat()
        supabase.table("supply_users") \
            .update({"role": new_role, "updated_at": current_time}) \
            .eq("id", user_id).execute()
        return True
    except Exception:
        return False


def toggle_user_active(user_id, is_active):
    supabase = get_supabase()
    if supabase is None:
        return False
    try:
        current_time = get_current_time().isoformat()
        supabase.table("supply_users") \
            .update({"is_active": is_active, "updated_at": current_time}) \
            .eq("id", user_id).execute()
        return True
    except Exception:
        return False


def update_user_program_access(user_id, programs):
    supabase = get_supabase()
    if supabase is None:
        return False
    try:
        program_str = ", ".join(programs) if programs else ""
        current_time = get_current_time().isoformat()
        supabase.table("supply_users") \
            .update({"program_access": program_str, "updated_at": current_time}) \
            .eq("id", user_id).execute()
        return True
    except Exception:
        return False


def update_user_tab_access(user_id, tabs):
    """Update a user's tab access. FIXED: removed duplicate except block."""
    supabase = get_supabase()
    if supabase is None:
        return False

    try:
        if isinstance(tabs, str):
            if "All" in tabs or not tabs.strip():
                tab_str = "All"
            else:
                tab_str = tabs.strip()
        elif isinstance(tabs, list):
            if not tabs or 'All' in tabs:
                tab_str = "All"
            else:
                cleaned_tabs = [str(t).strip() for t in tabs if t and str(t).strip()]
                tab_str = ", ".join(cleaned_tabs) if cleaned_tabs else "All"
        else:
            tab_str = "All"

        current_time = get_current_time().isoformat()

        try:
            query_user_id = int(user_id)
        except (ValueError, TypeError):
            query_user_id = user_id

        response = supabase.table("supply_users") \
            .update({"tab_access": tab_str, "updated_at": current_time}) \
            .eq("id", query_user_id) \
            .execute()

        if response.data:
            return True
        return False
    except Exception as e:
        print(f"Error updating tab access: {e}")
        return False


def get_user_tab_access():
    """Get the tab access for the current user."""
    user = get_current_user()
    if user:
        access = user.get('tab_access', 'All')
        if access == 'All' or not access:
            return ['All']
        return [t.strip() for t in access.split(',') if t.strip()]
    return ['All']


def delete_user(user_id):
    supabase = get_supabase()
    if supabase is None:
        return False, "Database connection error"
    try:
        response = supabase.table("supply_users") \
            .select("id, email, full_name").eq("id", user_id).execute()
        if not response.data:
            return False, f"User with ID {user_id} not found"
        user = response.data[0]
        supabase.table("supply_users").delete().eq("id", user_id).execute()
        return True, f"User {user.get('full_name', user.get('email'))} deleted successfully"
    except Exception as e:
        return False, str(e)


# ============================================================
# SESSION MANAGEMENT
# ============================================================

def update_user_session(user_id, session_id=None):
    supabase = get_supabase()
    if supabase is None:
        return False
    try:
        current_time = get_current_time().isoformat()
        supabase.table("supply_users") \
            .update({"last_login": current_time, "updated_at": current_time}) \
            .eq("id", user_id).execute()
        return True
    except Exception:
        return False


def get_online_users():
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
                user['last_active_display'] = format_time_for_display(user.get('last_login'))
            return online_users
        return []
    except Exception:
        return []


# ============================================================
# ACCESS CONTROL
# ============================================================

def get_current_user():
    return st.session_state.get('user', None)


def get_user_role():
    user = get_current_user()
    if user:
        return user.get('role', 'viewer')
    return None


def is_admin():
    return get_user_role() == 'admin'


def is_editor():
    role = get_user_role()
    return role in ['editor', 'admin']


def require_auth():
    if 'auth' not in st.session_state:
        st.session_state['auth'] = False
    if not st.session_state.get('auth'):
        show_login_page()
        return False
    if st.session_state.get('user'):
        now = get_current_time()
        if (now - st.session_state.get('last_activity', now)).seconds >= 30:
            update_user_session(st.session_state['user']['id'], st.session_state.get('session_id', ''))
            st.session_state['last_activity'] = now
    return True


def get_user_program_access():
    user = get_current_user()
    if user:
        program_str = user.get('program_access', '')
        if program_str:
            return [p.strip() for p in program_str.split(',') if p.strip()]
        return []
    return []


def check_program_access(program_name):
    if is_admin():
        return True
    user_programs = get_user_program_access()
    if not user_programs:
        return False
    if "All" in user_programs:
        return True
    return program_name in user_programs


def logout():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()


# ============================================================
# SESSION STATE INIT
# ============================================================

def init_session_state():
    defaults = {
        'auth': False,
        'user': None,
        'session_id': str(uuid.uuid4()),
        'login_time': get_current_time(),
        'last_activity': get_current_time(),
        'show_admin_page': False,
        'data_loaded': False,
        'selected_program': "All",
        'selected_subcategory': "All",
        'selected_quarter': "All",
        'selected_year': "All",
        'selected_status': "All",
        'action_plan_tab': "📋 All Issues",
        'expert_plan_records': [],
        'edit_record_id': None,
        'show_material_info': False,
        'show_change_list': False,
        'adding_action_point': False,
        'selected_material_for_expert': None,
        'show_profile': False,
        'force_password_reset': False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ============================================================
# LOGIN PAGE UI (with Forgot Password)
# ============================================================

def show_login_page():
    st.markdown("""
    <style>
    .stApp { background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%); }
    .hero-section {
        background: linear-gradient(135deg, #1a5276 0%, #2e86c1 50%, #1a5276 100%);
        border-radius: 20px; padding: 30px 40px; text-align: center; color: white;
        margin-bottom: 30px; box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        border: 2px solid rgba(255,255,255,0.1);
    }
    @keyframes pulse { 0%{transform:scale(1);} 50%{transform:scale(1.02);} 100%{transform:scale(1);} }
    @keyframes slideIn { 0%{transform:translateX(-100%);opacity:0;} 100%{transform:translateX(0);opacity:1;} }
    @keyframes glow {
        0% { text-shadow: 0 0 10px rgba(255,215,0,0.3); }
        50% { text-shadow: 0 0 20px rgba(255,215,0,0.6), 0 0 30px rgba(255,215,0,0.3); }
        100% { text-shadow: 0 0 10px rgba(255,215,0,0.3); }
    }
    .hero-title {
        font-family: 'Times New Roman', Times, serif !important;
        font-size: 2.0rem !important; margin-bottom: 0.3rem !important;
        font-weight: bold; color: #ffd700;
        animation: pulse 3s ease-in-out infinite, glow 2s ease-in-out infinite;
        letter-spacing: 2px;
    }
    .hero-subtitle {
        font-family: 'Times New Roman', Times, serif !important;
        font-size: 1.0rem !important; opacity: 0.95;
        animation: slideIn 0.8s ease-out; color: #e8f4fd;
    }
    .auth-container {
        background: white; border-radius: 20px; padding: 30px;
        box-shadow: 0 15px 40px rgba(0,0,0,0.15); margin-bottom: 30px;
        border: 1px solid rgba(26, 82, 118, 0.2);
    }
    .time-display {
        text-align: center; padding: 12px; background: rgba(26, 82, 118, 0.08);
        border-radius: 10px; margin-bottom: 20px; font-size: 1rem;
        font-weight: 500; color: #1a5276; border: 1px solid rgba(26, 82, 118, 0.15);
        font-family: 'Times New Roman', Times, serif !important;
    }
    .info-section {
        background: linear-gradient(135deg, #1a5276 0%, #2e86c1 50%, #1a5276 100%);
        border-radius: 15px; padding: 30px; margin-top: 25px;
        color: white; box-shadow: 0 8px 25px rgba(0,0,0,0.1);
    }
    .info-section h3 { color: #ffd700; margin-bottom: 15px; font-size: 1.3rem; text-align: center; }
    .step-box {
        background: rgba(255,255,255,0.12); border-radius: 12px; padding: 18px;
        text-align: left; backdrop-filter: blur(10px);
        border: 1px solid rgba(255,255,255,0.1);
    }
    .step-number { font-size: 1.6rem; font-weight: bold; margin-bottom: 5px; color: #ffd700; }
    .stTabs [data-baseweb="tab"] {
        border-radius: 10px; padding: 10px 20px; font-weight: 600;
        background-color: #f0f2f6;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #1a5276 0%, #2e86c1 100%); color: white;
    }
    .stButton > button {
        background: linear-gradient(135deg, #1a5276 0%, #2e86c1 100%);
        color: white; border: none; border-radius: 10px; font-weight: 600;
        padding: 10px; transition: all 0.3s ease;
    }
    .stButton > button:hover { transform: translateY(-2px); box-shadow: 0 5px 15px rgba(26, 82, 118, 0.4); }
    .footer {
        position: fixed; bottom: 0; left: 0; right: 0;
        background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
        color: white; text-align: center; padding: 10px; font-size: 13px;
        z-index: 999; box-shadow: 0 -2px 15px rgba(0,0,0,0.2);
    }
    .main-content { margin-bottom: 50px; }
    </style>
    """, unsafe_allow_html=True)

    current_time = get_current_time()
    st.markdown(f"""
    <div class="time-display">
        🕐 Addis Ababa Time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="hero-section">
        <div class="hero-title">📦 HPC Supply Planning Dashboard</div>
        <div class="hero-subtitle">Efficient Supply Chain Management for Health Programs</div>
    </div>
    """, unsafe_allow_html=True)

    left_col, right_col = st.columns([1, 1], gap="large")

    with left_col:
        st.markdown("### 🚀 Key Features")
        features = [
            ("📊", "Historical Stock Data", "View NSOH, NMOS, Consumption trends"),
            ("📋", "System Generated Action Plan", "AI-driven stock issue detection"),
            ("👨‍💼", "Expert Action Plan", "Create and manage custom action plans"),
            ("📈", "Action Plan Follow Up", "Monitor completion status"),
            ("🔐", "Secure Access", "Role-based access with admin approval"),
        ]
        for icon, title, desc in features:
            st.markdown(f"""
            <div style="background: white; border-radius: 12px; padding: 14px; margin-bottom: 10px; border-left: 4px solid #2e86c1;">
                <div style="display: flex; align-items: center; gap: 15px;">
                    <div style="font-size: 1.8rem;">{icon}</div>
                    <div>
                        <strong style="font-size: 1rem; color: #1a5276;">{title}</strong>
                        <div style="color: #666; font-size: 0.85rem;">{desc}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    with right_col:
        st.markdown("""
        <div class="auth-container">
            <div style="text-align: center; margin-bottom: 20px;">
                <h2 style="color: #1a5276; margin: 0;">🔐 Account Access</h2>
                <p style="color: #666;">Login or create a new account</p>
            </div>
        """, unsafe_allow_html=True)

        tab1, tab2, tab3 = st.tabs(["🔐 Login", "📝 Register", "🔑 Forgot Password"])

        # ---------- LOGIN TAB ----------
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
                                    st.error("⏳ Your account is pending admin approval.")
                                elif user['error'] == 'inactive':
                                    st.error("❌ Your account has been deactivated. Contact admin.")
                                elif user['error'] == 'reset_pending':
                                    st.warning("🔑 Your password reset request is pending admin approval.")
                            elif user:
                                st.session_state['auth'] = True
                                st.session_state['user'] = user
                                st.session_state['login_time'] = get_current_time()
                                st.session_state['last_activity'] = get_current_time()
                                # Check if approved reset is pending
                                if user.get('password_reset_approved', False):
                                    st.session_state['force_password_reset'] = True
                                update_user_session(user['id'], st.session_state.get('session_id', ''))
                                st.success("✅ Login successful! Redirecting...")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error("❌ Invalid email or password")
                    else:
                        st.warning("⚠️ Please enter both email and password")

        # ---------- REGISTER TAB ----------
        with tab2:
            with st.form("register_form"):
                new_email = st.text_input("Email", placeholder="you@example.com", key="reg_email")
                new_full_name = st.text_input("Full Name", placeholder="Enter your full name", key="reg_name")
                new_password = st.text_input("Password", type="password", placeholder="Min 6 characters", key="reg_password")
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

        # ---------- FORGOT PASSWORD TAB ----------
        with tab3:
            st.markdown("""
            <div style="background: #eaf2f8; border-radius: 10px; padding: 12px; margin-bottom: 15px; border-left: 4px solid #2e86c1;">
                <p style="color: #1a5276; margin: 0; font-size: 0.9rem;">
                    <strong>ℹ️ How it works:</strong> Submit your email. The admin will review and approve your request. 
                    Then you can log in with your old password and set a new one.
                </p>
            </div>
            """, unsafe_allow_html=True)

            with st.form("forgot_password_form"):
                fp_email = st.text_input("Email", placeholder="Enter your registered email", key="fp_email")
                submitted = st.form_submit_button("Request Password Reset", type="primary", use_container_width=True)

                if submitted:
                    if not fp_email:
                        st.warning("⚠️ Please enter your email")
                    else:
                        with st.spinner("Submitting request..."):
                            success, message = request_password_reset(fp_email)
                            if success:
                                st.success(f"✅ {message}")
                            else:
                                st.error(f"❌ {message}")

        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("""
    <div class="info-section">
        <h3>ℹ️ How to Get Started</h3>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
            <div class="step-box"><div class="step-number">1</div><strong>Register</strong><br><span style="font-size:0.9rem;opacity:0.9;">Create your account</span></div>
            <div class="step-box"><div class="step-number">2</div><strong>Wait for Approval</strong><br><span style="font-size:0.9rem;opacity:0.9;">Admin reviews your account</span></div>
            <div class="step-box"><div class="step-number">3</div><strong>Login</strong><br><span style="font-size:0.9rem;opacity:0.9;">Access the dashboard</span></div>
            <div class="step-box"><div class="step-number">4</div><strong>Start Planning</strong><br><span style="font-size:0.9rem;opacity:0.9;">Analyze and act</span></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="footer">© 2026 HPC Supply Planning Dashboard | Developed by Biyensa Negera</div>
    <div class="main-content"></div>
    """, unsafe_allow_html=True)


# ============================================================
# FORGOT PASSWORD HELPER (used by dashboard)
# ============================================================

def create_admin_user(email, password, full_name):
    """Create an admin user directly in supply_users table (for debugging/testing)"""
    supabase = get_supabase()
    if supabase is None:
        return False, "Database connection error"
    try:
        hashed = hash_password(password)
        existing = supabase.table("supply_users").select("*").eq("email", email).execute()
        if existing.data:
            return False, "Email already exists."
        current_time = get_current_time().isoformat()
        supabase.table("supply_users").insert({
            "email": email,
            "password_hash": hashed,
            "full_name": full_name,
            "role": "admin",
            "is_approved": True,
            "is_active": True,
            "program_access": "All",
            "tab_access": "All",
            "password_reset_requested": False,
            "password_reset_approved": False,
            "created_at": current_time,
            "last_login": current_time,
            "updated_at": current_time
        }).execute()
        return True, "Admin user created successfully!"
    except Exception as e:
        return False, f"Failed to create admin: {str(e)}"


# ============================================================
# MAIN (standalone test)
# ============================================================

def main():
    init_session_state()
    if st.session_state.get('auth'):
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
