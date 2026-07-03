import streamlit as st
import hashlib
import pandas as pd
from datetime import datetime, timedelta
import logging
from supabase import create_client
import time
import pytz

# Suppress warnings
import warnings
warnings.filterwarnings("ignore")
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("requests").setLevel(logging.ERROR)

# ===================================================
# CONSTANTS & SUPABASE CLIENT
# ===================================================
SUPABASE_URL = "https://etjfrptbjecafupbbase.supabase.co"
SUPABASE_KEY = "sb_publishable_j0JwaJAJBuJO79-xh7RkYg_PFKqLK1H"
USERS_TABLE = "users_vehicle"   # <-- your table name

@st.cache_resource
def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = get_supabase()

# Timezone for Addis Ababa
ADDIS_ABABA_TZ = pytz.timezone('Africa/Addis_Ababa')

def get_current_time():
    return datetime.now(ADDIS_ABABA_TZ)

def format_time_for_display(dt):
    if dt is None or pd.isna(dt):
        return "Never"
    if isinstance(dt, str):
        if dt == 'None' or dt == '':
            return "Never"
        try:
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except:
            return dt
    if hasattr(dt, 'tzinfo'):
        if dt.tzinfo is None:
            dt = pytz.UTC.localize(dt).astimezone(ADDIS_ABABA_TZ)
        else:
            dt = dt.astimezone(ADDIS_ABABA_TZ)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return str(dt)

# ===================================================
# AUTHENTICATION HELPERS
# ===================================================

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def authenticate_user(email, password):
    """Check credentials – returns user dict or {'error': 'not_approved'}"""
    hashed = hash_password(password)
    try:
        response = supabase.table(USERS_TABLE) \
            .select("*") \
            .eq("email", email) \
            .eq("password", hashed) \
            .execute()
        if response.data:
            user = response.data[0]
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
    except Exception:
        return None

def create_user(email, password, full_name, role="Trip Management"):
    """Insert new user with hashed password – auto‑approved if created by admin."""
    try:
        hashed = hash_password(password)
        existing = supabase.table(USERS_TABLE).select("*").eq("email", email).execute()
        if existing.data:
            return False, "Email already exists."
        current_time = get_current_time().isoformat()
        supabase.table(USERS_TABLE).insert({
            "email": email,
            "password": hashed,
            "full_name": full_name,
            "role": role,
            "is_approved": 1,          # auto-approved when admin creates
            "created_at": current_time,
            "last_active": current_time
        }).execute()
        return True, f"User {full_name} created successfully with role '{role}'."
    except Exception as e:
        return False, f"Creation failed: {e}"

def update_user_session(user_id, session_id):
    try:
        current_time = get_current_time().isoformat()
        supabase.table(USERS_TABLE).update({"last_active": current_time}).eq("id", user_id).execute()
        return True
    except:
        return False

def get_all_users():
    try:
        response = supabase.table(USERS_TABLE).select("*").order("created_at", desc=True).execute()
        if response.data:
            df = pd.DataFrame(response.data)
            if 'password' in df.columns:
                df = df.drop(columns=['password'])
            return df
        return pd.DataFrame()
    except:
        return pd.DataFrame()

def get_pending_users():
    try:
        response = supabase.table(USERS_TABLE) \
            .select("id, email, full_name, created_at") \
            .eq("is_approved", 0) \
            .order("created_at", desc=False) \
            .execute()
        if response.data:
            return pd.DataFrame(response.data)
        return pd.DataFrame()
    except:
        return pd.DataFrame()

def approve_user(user_id):
    try:
        supabase.table(USERS_TABLE).update({"is_approved": 1}).eq("id", user_id).execute()
        return True
    except:
        return False

def reject_user(user_id):
    try:
        supabase.table(USERS_TABLE).delete().eq("id", user_id).execute()
        return True
    except:
        return False

def delete_user(user_id):
    try:
        response = supabase.table(USERS_TABLE).select("email, full_name").eq("id", user_id).execute()
        if not response.data:
            return False, "User not found"
        supabase.table(USERS_TABLE).delete().eq("id", user_id).execute()
        return True, f"Deleted {response.data[0]['full_name']}"
    except:
        return False, "Deletion failed"

def change_password(user_id, old_password, new_password):
    try:
        hashed_old = hash_password(old_password)
        response = supabase.table(USERS_TABLE).select("id").eq("id", user_id).eq("password", hashed_old).execute()
        if not response.data:
            return False, "Current password is incorrect"
        hashed_new = hash_password(new_password)
        supabase.table(USERS_TABLE).update({"password": hashed_new}).eq("id", user_id).execute()
        return True, "Password changed successfully! Please login again."
    except Exception as e:
        return False, str(e)

def update_user_role(user_id, new_role):
    """Update a user's role (admin only)."""
    try:
        supabase.table(USERS_TABLE).update({"role": new_role}).eq("id", user_id).execute()
        return True
    except:
        return False

def get_online_users():
    try:
        current_time = get_current_time()
        five_minutes_ago = current_time - timedelta(minutes=5)
        response = supabase.table(USERS_TABLE) \
            .select("id, email, full_name, role, last_active") \
            .eq("is_approved", 1) \
            .gt("last_active", five_minutes_ago.isoformat()) \
            .execute()
        if response.data:
            return sorted(response.data, key=lambda x: x.get('last_active', ''), reverse=True)
        return []
    except:
        return []

def get_admin_count():
    """Return number of admin users (for first-user logic)."""
    try:
        resp = supabase.table(USERS_TABLE).select("id").eq("role", "admin").execute()
        return len(resp.data) if resp.data else 0
    except:
        return 0

# ===================================================
# EXPORTED INTERFACE
# ===================================================

def setup_auth() -> bool:
    """Main authentication UI – returns True if authenticated."""
    if 'authenticated' in st.session_state and st.session_state.authenticated:
        return True

    # ---- Orange Theme CSS ----
    st.markdown("""
    <style>
        .stApp { background-color: #fff8f0; }
        .stButton button { background-color: #FF8C00 !important; color: white !important; border-radius: 8px !important; font-weight: bold !important; border: none !important; }
        .stButton button:hover { background-color: #e67e00 !important; box-shadow: 0 4px 12px rgba(255,140,0,0.4) !important; }
        .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p { font-weight: 600 !important; color: #333 !important; }
        .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] { border-bottom: 3px solid #FF8C00 !important; }
        h1, h2, h3 { color: #e67e00 !important; }
        .feature-card { background: white; padding: 1rem 1.2rem; border-radius: 12px; border-left: 6px solid #FF8C00; box-shadow: 0 2px 8px rgba(0,0,0,0.06); margin-bottom: 0.8rem; transition: transform 0.2s; }
        .feature-card:hover { transform: translateX(4px); box-shadow: 0 4px 12px rgba(255,140,0,0.15); }
        .feature-card h4 { margin: 0 0 0.3rem 0; color: #e67e00; font-size: 1.1rem; }
        .feature-card p { margin: 0; font-size: 0.95rem; color: #333; }
        .auth-container { background: white; padding: 1.5rem 1.8rem; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); border: 1px solid #f0e0d0; }
        .auth-container .stTabs { margin-top: 0.5rem; }
        .auth-container .stTextInput > div > div > input { border-radius: 8px; }
    </style>
    """, unsafe_allow_html=True)

    st.title("🚚 EPSS Fleet Management System")
    col_left, col_right = st.columns([1.2, 1], gap="large")

    with col_left:
        st.markdown("### 📋 Key Features")
        st.markdown("""
        <div class="feature-card"><h4>📝 Trip Management</h4><p>Create, edit, and delete trips with real‑time status tracking.</p></div>
        <div class="feature-card"><h4>📊 Vehicle KPIs</h4><p>At‑a‑glance metrics: Total, Active, Grounded, Assigned, and Available vehicles.</p></div>
        <div class="feature-card"><h4>📈 Performance Analytics</h4><p>Interactive charts for trip volume, branch distribution, driver performance, and timeline trends.</p></div>
        <div class="feature-card"><h4>👑 Admin Panel</h4><p>Approve or reject new user registrations (admin only).</p></div>
        <div class="feature-card"><h4>🔒 Secure Authentication</h4><p>Email/password login with role‑based access control.</p></div>
        """, unsafe_allow_html=True)

    with col_right:
        st.markdown('<div class="auth-container">', unsafe_allow_html=True)
        # Check if any admin exists
        admin_exists = get_admin_count() > 0

        if admin_exists:
            # Only show login tab (registration disabled)
            with st.form("login_form"):
                st.markdown("#### 🔐 Login")
                email = st.text_input("Email", key="login_email")
                password = st.text_input("Password", type="password", key="login_password")
                submitted = st.form_submit_button("Login")

                if submitted:
                    if not email or not password:
                        st.warning("Please fill all fields")
                    else:
                        with st.spinner("Authenticating..."):
                            user = authenticate_user(email, password)
                            if user and 'error' in user:
                                st.error("⏳ Your account is pending admin approval. Please wait.")
                            elif user:
                                st.session_state.authenticated = True
                                st.session_state.user = {
                                    "id": user.get('id'),
                                    "email": user['email'],
                                    "full_name": user.get('full_name', ''),
                                    "role": user.get('role', 'user'),
                                    "is_approved": user.get('is_approved', 1)
                                }
                                st.session_state.user_email = user['email']
                                st.success("✅ Login successful!")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error("❌ Invalid email or password")
            st.caption("Registration is closed. Contact your administrator.")
        else:
            # No admin exists → show both Login and Register (first user becomes admin)
            tab1, tab2 = st.tabs(["🔐 Login", "📝 Register"])
            with tab1:
                with st.form("login_form"):
                    email = st.text_input("Email", key="login_email")
                    password = st.text_input("Password", type="password", key="login_password")
                    submitted = st.form_submit_button("Login")
                    if submitted:
                        if not email or not password:
                            st.warning("Please fill all fields")
                        else:
                            with st.spinner("Authenticating..."):
                                user = authenticate_user(email, password)
                                if user and 'error' in user:
                                    st.error("⏳ Your account is pending admin approval. Please wait.")
                                elif user:
                                    st.session_state.authenticated = True
                                    st.session_state.user = {
                                        "id": user.get('id'),
                                        "email": user['email'],
                                        "full_name": user.get('full_name', ''),
                                        "role": user.get('role', 'user'),
                                        "is_approved": user.get('is_approved', 1)
                                    }
                                    st.session_state.user_email = user['email']
                                    st.success("✅ Login successful!")
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error("❌ Invalid email or password")
            with tab2:
                with st.form("register_form"):
                    full_name = st.text_input("Full Name", key="reg_name")
                    email = st.text_input("Email", key="reg_email")
                    password = st.text_input("Password", type="password", key="reg_password")
                    confirm = st.text_input("Confirm Password", type="password", key="reg_confirm")
                    submitted = st.form_submit_button("Register")
                    if submitted:
                        if not full_name or not email or not password or not confirm:
                            st.warning("Please fill all fields")
                        elif password != confirm:
                            st.error("Passwords do not match")
                        elif len(password) < 6:
                            st.error("Password must be at least 6 characters")
                        else:
                            with st.spinner("Creating account..."):
                                # First user: auto-approve and make admin
                                success, message = create_user(email, password, full_name, role="admin")
                                if success:
                                    # Ensure admin role and approved (already set)
                                    st.success("🎉 You are the first user! You have been granted Admin privileges and auto-approved.")
                                    st.balloons()
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error(f"❌ {message}")

        st.markdown('</div>', unsafe_allow_html=True)

    return False

# ===================================================
# ROLE‑BASED ACCESS HELPERS
# ===================================================

def get_user_role():
    """Return the role of the currently logged‑in user."""
    user = st.session_state.get('user', {})
    return user.get('role', None)

def has_access(required_role):
    """Check if current user has the required role (exact match)."""
    return get_user_role() == required_role

# ===================================================
# EXPORTED FUNCTIONS
# ===================================================

def get_user_email():
    return st.session_state.get('user_email')

def get_user_metadata():
    data = st.session_state.get('user', {})
    return {
        "full_name": data.get("full_name", "N/A"),
        "role": data.get("role", "user"),
        "is_approved": data.get("is_approved", 0),
    }

def sign_out():
    try:
        st.session_state.clear()
        st.cache_data.clear()
        return True
    except:
        return False

def get_current_user():
    return st.session_state.get('user', {})

def is_authenticated():
    return st.session_state.get('authenticated', False)

# ===================================================
# ADMIN PANEL (with user creation & role management)
# ===================================================

def admin_panel():
    """Admin panel widget – allows creation, role editing, and password change for users."""
    if not is_authenticated() or st.session_state.get('user', {}).get('role') != 'admin':
        st.error("⚠️ Admin access required.")
        return

    st.markdown("## 👑 Admin Panel")

    # ---- Create User ----
    st.subheader("➕ Create New User")
    with st.form("create_user_form"):
        c1, c2 = st.columns(2)
        with c1:
            new_email = st.text_input("Email")
            new_fullname = st.text_input("Full Name")
        with c2:
            new_password = st.text_input("Temporary Password", type="password")
            new_role = st.selectbox(
                "Role",
                options=["Trip Management", "KPIs and Analysis", "Vehicles Maintenance"]
            )
        submitted = st.form_submit_button("Create User")
        if submitted:
            if not new_email or not new_fullname or not new_password:
                st.warning("All fields are required.")
            else:
                success, msg = create_user(new_email, new_password, new_fullname, new_role)
                if success:
                    st.success(msg)
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error(msg)

    # ---- Manage Users ----
    st.subheader("📋 Manage Users")
    all_users = get_all_users()
    if all_users.empty:
        st.info("No users found.")
        return

    # Exclude current admin from editable list? We'll show all.
    for idx, row in all_users.iterrows():
        with st.container(border=True):
            cols = st.columns([2, 2, 2, 1, 1])
            with cols[0]:
                st.write(f"**{row.get('full_name', 'N/A')}**")
            with cols[1]:
                st.write(row.get('email'))
            with cols[2]:
                # Role dropdown (editable)
                current_role = row.get('role', 'Trip Management')
                new_role = st.selectbox(
                    "Role",
                    options=["Trip Management", "KPIs and Analysis", "Vehicles Maintenance"],
                    index=["Trip Management", "KPIs and Analysis", "Vehicles Maintenance"].index(current_role)
                    if current_role in ["Trip Management", "KPIs and Analysis", "Vehicles Maintenance"]
                    else 0,
                    key=f"role_{row['id']}",
                    label_visibility="collapsed"
                )
                if new_role != current_role:
                    if st.button("Update Role", key=f"upd_{row['id']}"):
                        if update_user_role(row['id'], new_role):
                            st.success(f"Role updated to {new_role}")
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error("Update failed")
            with cols[3]:
                # Delete button (avoid deleting yourself)
                if row['id'] != st.session_state.user.get('id'):
                    if st.button("🗑️", key=f"del_{row['id']}"):
                        success, msg = delete_user(row['id'])
                        if success:
                            st.warning(msg)
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error(msg)
                else:
                    st.write("(you)")
            with cols[4]:
                # Show last active
                last = row.get('last_active')
                st.caption(f"Last active: {format_time_for_display(last)}")

# ===================================================
# PASSWORD CHANGE UI (for any logged‑in user)
# ===================================================

def password_change_ui():
    """Render a password change form (call from sidebar or main)."""
    if not is_authenticated():
        return
    user_id = st.session_state.user.get('id')
    if not user_id:
        return

    st.markdown("### 🔑 Change Password")
    with st.form("change_pw_form"):
        old = st.text_input("Current Password", type="password")
        new1 = st.text_input("New Password", type="password")
        new2 = st.text_input("Confirm New Password", type="password")
        submitted = st.form_submit_button("Update Password")
        if submitted:
            if not old or not new1 or not new2:
                st.warning("All fields are required.")
            elif new1 != new2:
                st.error("New passwords do not match.")
            elif len(new1) < 6:
                st.error("New password must be at least 6 characters.")
            else:
                success, msg = change_password(user_id, old, new1)
                if success:
                    st.success(msg)
                    # Force re-login: clear session
                    st.session_state.clear()
                    st.cache_data.clear()
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(msg)

# ===================================================
# Standalone test
# ===================================================
if __name__ == "__main__":
    setup_auth()
