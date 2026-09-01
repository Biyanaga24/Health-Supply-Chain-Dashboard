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

# Initialize Supabase client
@st.cache_resource
def init_supabase():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_supabase()

# Set timezone for Addis Ababa (East Africa Time)
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
        © 2026 Health Program Medicines Dashboard | Developed by Biyensa Negera
    </div>
    """, unsafe_allow_html=True)

    # Add margin to main content to prevent overlap with footer
    st.markdown('<div class="main-content"></div>', unsafe_allow_html=True)

# ============================================================
# DATABASE FUNCTIONS - Using 'users' table with approval
# ============================================================

def authenticate_user(email, password):
    """Authenticate user from Supabase - Checks if approved"""
    hashed = hashlib.sha256(password.encode()).hexdigest()

    try:
        response = supabase.table("users") \
            .select("*") \
            .eq("email", email) \
            .eq("password", hashed) \
            .execute()

        if response.data:
            user = response.data[0]
            # Check if user is approved
            if user.get('is_approved', 0) == 0:
                return {'error': 'not_approved'}
            return {
                'id': user.get('id'),
                'email': user['email'],
                'full_name': user.get('full_name', user['email'].split('@')[0]),
                'role': user.get('role', 'user'),
                'is_approved': user.get('is_approved', 1)
            }
        return None
    except Exception as e:
        st.error(f"Authentication error: {e}")
        return None

def create_user(email, password, full_name):
    """Create new user in Supabase - Pending approval by default"""
    try:
        hashed = hashlib.sha256(password.encode()).hexdigest()

        # Check if user already exists
        existing = supabase.table("users").select("*").eq("email", email).execute()
        if existing.data:
            return False, "Email already exists. Please use a different email."

        current_time = get_current_time().isoformat()

        supabase.table("users").insert({
            "email": email,
            "password": hashed,
            "full_name": full_name,
            "role": "user",
            "is_approved": 0,  # Pending approval
            "created_at": current_time,
            "last_active": current_time
        }).execute()
        return True, "Registration successful! Your account is pending admin approval."
    except Exception as e:
        return False, f"Registration failed: {str(e)}"

def change_password(user_id, old_password, new_password):
    """Change user password"""
    try:
        # First verify old password
        hashed_old = hashlib.sha256(old_password.encode()).hexdigest()

        response = supabase.table("users") \
            .select("id") \
            .eq("id", user_id) \
            .eq("password", hashed_old) \
            .execute()

        if not response.data:
            return False, "Current password is incorrect"

        # Update to new password
        hashed_new = hashlib.sha256(new_password.encode()).hexdigest()
        supabase.table("users") \
            .update({"password": hashed_new}) \
            .eq("id", user_id) \
            .execute()

        return True, "Password changed successfully! Please login again."
    except Exception as e:
        return False, f"Failed to change password: {e}"

def get_pending_users():
    """Get all pending users (is_approved = 0)"""
    try:
        response = supabase.table("users") \
            .select("id, email, full_name, created_at") \
            .eq("is_approved", 0) \
            .order("created_at", desc=False) \
            .execute()

        if response.data:
            return pd.DataFrame(response.data)
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error getting pending users: {e}")
        return pd.DataFrame()

def get_all_users():
    """Get all users from users table"""
    try:
        response = supabase.table("users") \
            .select("*") \
            .order("created_at", desc=True) \
            .execute()

        if response.data:
            df = pd.DataFrame(response.data)
            # Remove password from display
            if 'password' in df.columns:
                df = df.drop(columns=['password'])
            return df
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error getting users: {e}")
        return pd.DataFrame()

def approve_user(user_id):
    """Approve a user (set is_approved = 1)"""
    try:
        supabase.table("users") \
            .update({"is_approved": 1}) \
            .eq("id", user_id) \
            .execute()
        return True
    except Exception as e:
        return False

def reject_user(user_id):
    """Reject/delete a user"""
    try:
        supabase.table("users").delete().eq("id", user_id).execute()
        return True
    except Exception as e:
        return False

def delete_user(user_id):
    """Delete a user"""
    try:
        response = supabase.table("users") \
            .select("id, email, full_name") \
            .eq("id", user_id) \
            .execute()

        if not response.data:
            return False, f"User with ID {user_id} not found"

        user = response.data[0]
        supabase.table("users").delete().eq("id", user_id).execute()
        return True, f"User {user.get('full_name', user.get('email'))} deleted successfully"
    except Exception as e:
        return False, str(e)

def update_user_session(user_id, session_id):
    """Update user's last activity timestamp with Addis Ababa time"""
    try:
        current_time = get_current_time().isoformat()
        supabase.table("users").update({
            "last_active": current_time
        }).eq("id", user_id).execute()
        return True
    except Exception as e:
        return False

def get_online_users():
    """Get list of users currently online (active in last 5 minutes) - sorted by newest first"""
    try:
        current_time = get_current_time()
        five_minutes_ago = current_time - timedelta(minutes=5)

        response = supabase.table("users") \
            .select("id, email, full_name, role, last_active, created_at") \
            .eq("is_approved", 1) \
            .gt("last_active", five_minutes_ago.isoformat()) \
            .execute()

        if response.data:
            # Sort by last_active descending (newest first)
            online_users = sorted(response.data, key=lambda x: x.get('last_active', ''), reverse=True)

            # Convert timestamps to Addis Ababa time for display
            for user in online_users:
                if user.get('last_active'):
                    user['last_active_display'] = format_time_for_display(user['last_active'])
                else:
                    user['last_active_display'] = "Unknown"

            return online_users
        return []
    except Exception as e:
        print(f"Error getting online users: {e}")
        return []

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
            'regular_users': len(all_users[all_users['role'] == 'user']) if 'role' in all_users else 0,
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

def check_session_validity():
    """Update user's last active timestamp with Addis Ababa time"""
    if st.session_state.get('auth') and st.session_state.get('user'):
        now = get_current_time()
        if (now - st.session_state.get('last_activity', now)).seconds >= 30:
            update_user_session(
                st.session_state['user']['id'], 
                st.session_state.get('session_id', '')
            )
            st.session_state['last_activity'] = now

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

    /* Hero Section */
    .hero-section {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 20px;
        padding: 50px;
        text-align: center;
        color: white;
        margin-bottom: 40px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.2);
    }
    .hero-title {
        font-size: 3.5rem;
        margin-bottom: 1rem;
        font-weight: bold;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
    }
    .hero-subtitle {
        font-size: 1.3rem;
        opacity: 0.95;
        margin-bottom: 1.5rem;
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
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
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
    }
    .step-box {
        background: rgba(255,255,255,0.15);
        border-radius: 12px;
        padding: 20px;
        text-align: left;
        backdrop-filter: blur(10px);
        transition: all 0.3s ease;
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
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
    }

    /* Form Styling */
    .stForm {
        background: transparent;
    }
    .stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 10px;
        font-weight: 600;
        padding: 10px;
        transition: all 0.3s ease;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
    }

    /* Welcome Section */
    .welcome-section {
        text-align: center;
        margin: 30px 0;
    }
    .welcome-title {
        font-size: 2rem;
        color: #667eea;
        font-weight: bold;
        margin-bottom: 15px;
    }
    .welcome-text {
        font-size: 1.1rem;
        color: #555;
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

    # Hero Section
    st.markdown("""
    <div class="hero-section">
        <div class="hero-title">💊 HPC STOCK MANAGEMENT DASHBOARD</div>
        <div class="hero-subtitle">Comprehensive Stock Management & Analytics Platform</div>
        <p style="opacity: 0.95; font-size: 1.1rem;">Secure • Real-time • Data-driven Decision Making</p>
    </div>
    """, unsafe_allow_html=True)

    # Create two columns for layout
    left_col, right_col = st.columns([1, 1], gap="large")

    with left_col:
        st.markdown("""
        <div class="welcome-section">
            <div class="welcome-title">✨ Welcome!</div>
            <div class="welcome-text">Access your dashboard to monitor stock levels, track pipelines, and get actionable insights.</div>
        </div>
        """, unsafe_allow_html=True)

        # Features Section
        st.markdown("### 🚀 Key Features")

        features = [
            ("📊", "Real-time Analytics", "Monitor stock levels and KPIs instantly"),
            ("🚚", "Pipeline Tracking", "Track GIT, LC, WB, and TMD orders"),
            ("📍", "Hub Distribution", "Visualize stock across all branches"),
            ("📋", "Decision Support", "Get actionable insights and recommendations"),
            ("🔐", "Secure Access", "Role-based access with admin approval"),
            ("📈", "Risk Analysis", "Identify high-risk products"),
        ]

        for icon, title, desc in features:
            st.markdown(f"""
            <div style="background: white; border-radius: 12px; padding: 15px; margin-bottom: 12px; border-left: 4px solid #667eea; box-shadow: 0 2px 8px rgba(0,0,0,0.05);">
                <div style="display: flex; align-items: center; gap: 15px;">
                    <div style="font-size: 2rem;">{icon}</div>
                    <div>
                        <strong style="font-size: 1rem; color: #667eea;">{title}</strong>
                        <div style="color: #666; font-size: 0.9rem;">{desc}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    with right_col:
        st.markdown("""
        <div class="auth-container">
            <div style="text-align: center; margin-bottom: 20px;">
                <h2 style="color: #667eea; margin: 0;">🔐 Account Access</h2>
                <p style="color: #666;">Login or create a new account</p>
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
                                st.error("⏳ Your account is pending admin approval. Please wait for approval.")
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
                Access analytics, pipeline tracking, and recommendations
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
            <div style="background: linear-gradient(135deg, #667eea15 0%, #764ba215 100%); border-left: 4px solid #4caf50; padding: 10px; margin: 8px 0; border-radius: 8px;">
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
    st.markdown("<h1 style='font-size: 32px; font-weight: bold; color: #667eea;'>👤 User Profile</h1>", unsafe_allow_html=True)

    # Display current Addis Ababa time
    current_time = get_current_time()
    st.markdown(f"""
    <div style="text-align: right; margin-bottom: 20px; padding: 10px; background: rgba(102,126,234,0.1); border-radius: 10px;">
        <small>🕐 Local Time (Addis Ababa): {current_time.strftime('%Y-%m-%d %H:%M:%S')}</small>
    </div>
    """, unsafe_allow_html=True)

    if st.session_state.get('user'):
        user = st.session_state['user']

        col1, col2 = st.columns([1, 2])

        with col1:
            st.markdown(f"""
            <div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                        border-radius: 15px; 
                        padding: 30px; 
                        text-align: center;
                        color: white;
                        box-shadow: 0 10px 25px rgba(0,0,0,0.1);'>
                <div style='font-size: 48px; margin-bottom: 10px;'>👤</div>
                <h3 style='margin: 0;'>{user.get('full_name', 'N/A')}</h3>
                <p style='margin: 5px 0; opacity: 0.9;'>{user.get('role', 'user').title()}</p>
                <p style='margin: 5px 0; font-size: 12px; opacity: 0.8;'>{user.get('email', 'N/A')}</p>
                <p style='margin: 5px 0; font-size: 11px; opacity: 0.7;'>✅ Account Approved</p>
            </div>
            """, unsafe_allow_html=True)

        with col2:
            st.markdown("### 📋 Profile Information")

            # Get user's last active time
            try:
                response = supabase.table("users") \
                    .select("last_active, created_at") \
                    .eq("id", user['id']) \
                    .execute()
                if response.data:
                    last_active = response.data[0].get('last_active')
                    created_at = response.data[0].get('created_at')
                    last_active_display = format_time_for_display(last_active) if last_active else "Never"
                    created_at_display = format_time_for_display(created_at) if created_at else "Unknown"
                else:
                    last_active_display = "Unknown"
                    created_at_display = "Unknown"
            except:
                last_active_display = "Unknown"
                created_at_display = "Unknown"

            st.markdown(f"""
            <div style="background: #f8f9fa; border-radius: 10px; padding: 20px;">
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
        <div style="font-size: 12px; opacity: 0.9;">{label}</div>
    </div>
    """

    with col1:
        st.markdown(metric_style.format(
            icon="👥", value=stats.get('total_users', 0),
            label="Total Users", color1="#667eea", color2="#764ba2"
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

        colors = ['#764ba2', '#667eea']

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
            plot_bgcolor='rgba(0,0,0,0)'
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
            plot_bgcolor='rgba(0,0,0,0)'
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
                yaxis_title="Number of Users"
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

                fig4.update_traces(line=dict(color='#667eea', width=3),
                                  marker=dict(size=8, color='#764ba2'))

                fig4.update_layout(
                    height=400,
                    margin=dict(t=50, l=0, r=0, b=0),
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    xaxis_title="Hour of Day (0-23)",
                    yaxis_title="Number of Active Users",
                    xaxis=dict(tickmode='linear', tick0=0, dtick=2)
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
                marker_color='#667eea',
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
                plot_bgcolor='rgba(0,0,0,0)'
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

def show_admin_panel():
    """Display admin panel - User Management with Approval/Rejection and Deletion"""
    st.markdown("<h1 style='font-size: 32px; font-weight: bold; color: #667eea;'>👑 Admin Panel - User Management</h1>", unsafe_allow_html=True)

    # Display current Addis Ababa time
    current_time = get_current_time()
    st.markdown(f"""
    <div style="text-align: right; margin-bottom: 20px; padding: 10px; background: rgba(102,126,234,0.1); border-radius: 10px;">
        <small>🕐 Local Time (Addis Ababa): {current_time.strftime('%Y-%m-%d %H:%M:%S')}</small>
    </div>
    """, unsafe_allow_html=True)

    pending_df = get_pending_users()
    all_users = get_all_users()

    # Metrics row with better styling
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("👥 Total Users", len(all_users))
    with col2:
        approved_count = len(all_users[all_users['is_approved'] == 1]) if not all_users.empty else 0
        st.metric("✅ Approved Users", approved_count)
    with col3:
        st.metric("⏳ Pending Approvals", len(pending_df))
    with col4:
        online_count = len(get_online_users())
        st.metric("🟢 Online Now", online_count)

    st.markdown("---")

    # Create tabs with statistics dashboard
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 User Statistics", "⏳ Pending Approvals", "🟢 Online Users", "📋 All Users", "➕ Add New User"])

    with tab1:
        show_user_statistics()

    with tab2:
        st.markdown("### ⏳ Users Awaiting Approval")
        if not pending_df.empty:
            for idx, row in pending_df.iterrows():
                col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 1, 1])
                with col1:
                    st.write(f"**{row['full_name']}**")
                with col2:
                    st.write(row['email'])
                with col3:
                    created_at_display = format_time_for_display(row['created_at']) if row.get('created_at') else "Unknown"
                    st.write(f"📅 {created_at_display}")
                with col4:
                    if st.button("✅ Approve", key=f"approve_{row['id']}"):
                        if approve_user(row['id']):
                            st.success(f"✅ Approved {row['full_name']}")
                            st.rerun()
                with col5:
                    if st.button("❌ Reject", key=f"reject_{row['id']}"):
                        if reject_user(row['id']):
                            st.warning(f"❌ Rejected {row['full_name']}")
                            st.rerun()
                st.divider()
        else:
            st.success("✅ No pending approvals. All users have been approved.")

    with tab3:
        show_online_users()

    with tab4:
        if not all_users.empty:
            # Convert timestamps to Addis Ababa time for display
            display_df = all_users.copy()

            # Safely convert last_active column
            if 'last_active' in display_df.columns:
                def safe_format_last_active(x):
                    if x is None or x == 'None' or pd.isna(x):
                        return 'Never'
                    return format_time_for_display(x)
                display_df['last_active'] = display_df['last_active'].apply(safe_format_last_active)

            # Safely convert created_at column
            if 'created_at' in display_df.columns:
                def safe_format_created_at(x):
                    if x is None or x == 'None' or pd.isna(x):
                        return 'Unknown'
                    return format_time_for_display(x)
                display_df['created_at'] = display_df['created_at'].apply(safe_format_created_at)

            # Show approval status
            if 'is_approved' in display_df.columns:
                display_df['status'] = display_df['is_approved'].apply(lambda x: "✅ Approved" if x == 1 else "⏳ Pending")
                display_df = display_df.drop(columns=['is_approved'])

            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "id": st.column_config.NumberColumn("ID", width="small"),
                    "email": st.column_config.TextColumn("Email", width="medium"),
                    "full_name": st.column_config.TextColumn("Full Name", width="medium"),
                    "role": st.column_config.TextColumn("Role", width="small"),
                    "status": st.column_config.TextColumn("Status", width="small"),
                    "last_active": st.column_config.TextColumn("Last Active", width="medium"),
                    "created_at": st.column_config.TextColumn("Registered", width="medium")
                }
            )

            st.markdown("---")
            st.markdown("### 🗑️ Delete User")
            st.warning("⚠️ Warning: Deleting a user will permanently remove their account. This action cannot be undone.")

            # Create two columns for delete user section
            col1, col2 = st.columns([3, 1])
            with col1:
                user_to_delete = st.selectbox("Select user to delete", all_users['email'].tolist(), key="delete_user_select")
            with col2:
                st.markdown("<br>", unsafe_allow_html=True)
                confirm_delete = st.checkbox("I confirm deletion", key="confirm_delete")

            if st.button("🗑️ Delete Selected User", type="secondary", use_container_width=True, disabled=not confirm_delete):
                if user_to_delete == st.session_state['user']['email']:
                    st.error("❌ You cannot delete your own account!")
                else:
                    user_row = all_users[all_users['email'] == user_to_delete].iloc[0]
                    success, message = delete_user(user_row['id'])
                    if success:
                        st.success(f"✅ {message}")
                        st.rerun()
                    else:
                        st.error(f"❌ {message}")
        else:
            st.info("No users found")

    with tab5:
        with st.form("add_user_form"):
            col1, col2 = st.columns(2)
            with col1:
                new_email = st.text_input("Email")
                new_full_name = st.text_input("Full Name")
            with col2:
                new_role = st.selectbox("Role", ["user", "admin"])
                new_password = st.text_input("Password", type="password")

            auto_approve = st.checkbox("Auto-approve this user", value=True)

            if st.form_submit_button("➕ Add User", type="primary", use_container_width=True):
                if new_email and new_full_name and new_password:
                    if len(new_password) < 6:
                        st.error("❌ Password must be at least 6 characters")
                    else:
                        with st.spinner("Creating user..."):
                            hashed = hashlib.sha256(new_password.encode()).hexdigest()
                            current_time = get_current_time().isoformat()
                            try:
                                supabase.table("users").insert({
                                    "email": new_email,
                                    "full_name": new_full_name,
                                    "password": hashed,
                                    "role": new_role,
                                    "is_approved": 1 if auto_approve else 0,
                                    "created_at": current_time,
                                    "last_active": current_time
                                }).execute()
                                st.success(f"✅ User {new_email} added successfully!")
                                if not auto_approve:
                                    st.info("User is pending approval. They will need to be approved before logging in.")
                                st.rerun()
                            except Exception as e:
                                if "duplicate" in str(e).lower():
                                    st.error("❌ Email already exists")
                                else:
                                    st.error(f"❌ Error adding user: {e}")
                else:
                    st.error("❌ Please fill all fields")

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
