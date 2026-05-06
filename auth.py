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
    if dt is None:
        return "Unknown"
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except:
            return dt
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt).astimezone(ADDIS_ABABA_TZ)
    else:
        dt = dt.astimezone(ADDIS_ABABA_TZ)
    return dt.strftime("%Y-%m-%d %H:%M:%S")

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
        # Fix: Use desc=False instead of asc=True
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
        # Fix: Use desc=True for descending order
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
    """Display login page"""
    st.markdown("""
    <style>
    * { font-family: 'Times New Roman', Times, serif !important; }
    .stApp { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
    .main-title {
        text-align: center;
        padding: 1.5rem;
        background: linear-gradient(135deg, rgba(255,255,255,0.2) 0%, rgba(255,255,255,0.1) 100%);
        backdrop-filter: blur(10px);
        border-radius: 20px;
        margin-bottom: 2rem;
        color: white;
    }
    .login-container {
        background: rgba(255, 255, 255, 0.95);
        border-radius: 20px;
        padding: 2rem;
        box-shadow: 0 20px 60px rgba(0,0,0,0.3);
    }
    .welcome-text {
        text-align: center;
        font-size: 1.3rem;
        color: #667eea;
        margin-bottom: 1.5rem;
        font-weight: 600;
    }
    .feature-card {
        background: white;
        border-radius: 15px;
        padding: 1.5rem;
        text-align: center;
        transition: transform 0.3s ease;
    }
    .feature-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 10px 30px rgba(0,0,0,0.2);
    }
    .feature-icon { font-size: 2.5rem; margin-bottom: 1rem; }
    .feature-title { font-weight: 600; color: #333; margin-bottom: 0.5rem; }
    .feature-desc { font-size: 0.85rem; color: #666; }
    .stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 10px;
        font-weight: 600;
        width: 100%;
    }
    .online-user-card {
        background: linear-gradient(135deg, #667eea15 0%, #764ba215 100%);
        border-left: 4px solid #4caf50;
        padding: 10px;
        margin: 5px 0;
        border-radius: 8px;
        transition: transform 0.2s;
    }
    .online-user-card:hover {
        transform: translateX(5px);
    }
    .online-indicator {
        display: inline-block;
        width: 10px;
        height: 10px;
        border-radius: 50%;
        background-color: #4caf50;
        animation: pulse 2s infinite;
        margin-right: 8px;
    }
    @keyframes pulse {
        0% { transform: scale(1); opacity: 1; }
        50% { transform: scale(1.2); opacity: 0.7; }
        100% { transform: scale(1); opacity: 1; }
    }
    </style>
    """, unsafe_allow_html=True)

    # Display current Addis Ababa time
    current_time = get_current_time()
    st.markdown(f"""
    <div style="text-align: right; padding: 5px 20px; color: white; font-size: 12px;">
        🕐 Addis Ababa Time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="main-title">
        <h1 style="font-size: 2.5rem; margin: 0;">💊 Health Program Medicines Dashboard</h1>
        <p style="margin-top: 0.5rem; opacity: 0.9;">Comprehensive Stock Management & Analytics Platform</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([1, 1.2])

    with col1:
        st.markdown('<div class="login-container">', unsafe_allow_html=True)
        st.markdown('<div class="welcome-text">✨ Key Features</div>', unsafe_allow_html=True)

        features = [
            ("📊", "Real-time Analytics", "Monitor stock levels and KPIs instantly"),
            ("🚚", "Pipeline Tracking", "Track GIT, LC, WB, and TMD orders"),
            ("📍", "Hub Distribution", "Visualize stock across all branches"),
            ("📋", "Decision Support", "Get actionable insights and recommendations"),
            ("🔐", "Admin Approval", "Secure account approval process"),
        ]

        for icon, title, desc in features:
            st.markdown(f"""
            <div class="feature-card">
                <div class="feature-icon">{icon}</div>
                <div class="feature-title">{title}</div>
                <div class="feature-desc">{desc}</div>
            </div>
            """, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="login-container">', unsafe_allow_html=True)
        st.markdown('<div class="welcome-text">👋 Welcome! Please Login</div>', unsafe_allow_html=True)

        tab1, tab2 = st.tabs(["🔐 Login", "📝 Register"])

        with tab1:
            with st.form("login_form"):
                email = st.text_input("Email", placeholder="Enter your email")
                password = st.text_input("Password", type="password", placeholder="Enter your password")
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
                new_email = st.text_input("Email", placeholder="you@example.com")
                new_full_name = st.text_input("Full Name", placeholder="Enter your full name")
                new_password = st.text_input("Password", type="password", placeholder="Create a password (min 6 characters)")
                confirm_password = st.text_input("Confirm Password", type="password", placeholder="Confirm your password")
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
            <div class="online-user-card">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <span class="online-indicator"></span>
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
    st.markdown("<h1 style='font-size: 32px; font-weight: bold;' class='gradient-text'>👤 User Profile</h1>", unsafe_allow_html=True)

    # Display current Addis Ababa time
    current_time = get_current_time()
    st.markdown(f"""
    <div style="text-align: right; margin-bottom: 20px;">
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
                        color: white;'>
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
            | Field | Value |
            |-------|-------|
            | **Full Name** | {user.get('full_name', 'N/A')} |
            | **Email** | {user.get('email', 'N/A')} |
            | **Role** | {user.get('role', 'user').title()} |
            | **Last Active** | {last_active_display} |
            | **Account Created** | {created_at_display} |
            """)

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

def show_admin_panel():
    """Display admin panel - User Management with Approval/Rejection"""
    st.markdown("<h1 style='font-size: 32px; font-weight: bold;' class='gradient-text'>👑 Admin Panel - User Management</h1>", unsafe_allow_html=True)

    # Display current Addis Ababa time
    current_time = get_current_time()
    st.markdown(f"""
    <div style="text-align: right; margin-bottom: 20px;">
        <small>🕐 Local Time (Addis Ababa): {current_time.strftime('%Y-%m-%d %H:%M:%S')}</small>
    </div>
    """, unsafe_allow_html=True)

    pending_df = get_pending_users()
    all_users = get_all_users()

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

    tab1, tab2, tab3, tab4 = st.tabs(["⏳ Pending Approvals", "🟢 Online Users", "📋 All Users", "➕ Add New User"])

    with tab1:
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

    with tab2:
        show_online_users()

    with tab3:
        if not all_users.empty:
            # Convert timestamps to Addis Ababa time for display
            display_df = all_users.copy()
            if 'last_active' in display_df.columns:
                display_df['last_active'] = display_df['last_active'].apply(
                    lambda x: format_time_for_display(x) if x and x != 'None' else 'Never'
                )
            if 'created_at' in display_df.columns:
                display_df['created_at'] = display_df['created_at'].apply(
                    lambda x: format_time_for_display(x) if x and x != 'None' else 'Unknown'
                )
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

            user_to_delete = st.selectbox("Select user to delete", all_users['email'].tolist())
            if st.button("🗑️ Delete User", type="secondary", use_container_width=True):
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

    with tab4:
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
        return True
    else:
        show_login_page()
        return False

# For standalone testing
if __name__ == "__main__":
    main()
