
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
USERS_TABLE = "users_vehicle"   # <-- using your existing table

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
# AUTHENTICATION HELPERS (from auth.py)
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

def create_user(email, password, full_name):
    """Insert new user with hashed password – pending approval (unless first admin)"""
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
            "role": "user",
            "is_approved": 0,
            "created_at": current_time,
            "last_active": current_time
        }).execute()
        return True, "Registration successful! Pending admin approval."
    except Exception as e:
        return False, f"Registration failed: {e}"

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
# EXPORTED INTERFACE (for vehicle_assignment.py)
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
                            # Check if first user (no admins) -> auto-approve and make admin
                            admin_count = get_admin_count()
                            is_first = (admin_count == 0)

                            success, message = create_user(email, password, full_name)
                            if success:
                                if is_first:
                                    # Get the newly created user and update role & approval
                                    user_resp = supabase.table(USERS_TABLE).select("id").eq("email", email).execute()
                                    if user_resp.data:
                                        supabase.table(USERS_TABLE).update({
                                            "role": "admin",
                                            "is_approved": 1
                                        }).eq("id", user_resp.data[0]['id']).execute()
                                    st.success("🎉 You are the first user! You have been granted Admin privileges and auto-approved.")
                                else:
                                    st.success("✅ Registration successful! Please wait for admin approval.")
                                st.balloons()
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error(f"❌ {message}")

        st.markdown('</div>', unsafe_allow_html=True)

    return False

# ===================================================
# EXPORTED FUNCTIONS (for vehicle_assignment.py)
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
# ADMIN PANEL (inline, no extra imports)
# ===================================================

def admin_panel():
    """Admin panel widget (called from vehicle_assignment.py)."""
    if not is_authenticated() or st.session_state.get('user', {}).get('role') != 'admin':
        st.error("⚠️ Admin access required.")
        return

    st.markdown("## 👑 Admin Panel")
    all_users = get_all_users()
    pending = get_pending_users()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Users", len(all_users))
    with col2:
        st.metric("Pending", len(pending))
    with col3:
        admins = len(all_users[all_users['role'] == 'admin']) if not all_users.empty else 0
        st.metric("Admins", admins)

    if not pending.empty:
        st.subheader("📋 Pending Approvals")
        for _, row in pending.iterrows():
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([2,2,1,1])
                with c1:
                    st.write(f"**{row.get('full_name','N/A')}**")
                with c2:
                    st.write(row.get('email'))
                with c3:
                    if st.button("✅ Approve", key=f"app_{row['id']}"):
                        if approve_user(row['id']):
                            st.success("Approved!")
                            st.cache_data.clear()
                            st.rerun()
                with c4:
                    if st.button("❌ Reject", key=f"rej_{row['id']}"):
                        if reject_user(row['id']):
                            st.warning("Rejected.")
                            st.cache_data.clear()
                            st.rerun()
    else:
        st.info("✅ No pending approvals")

    if not all_users.empty:
        st.subheader("📊 All Users")
        df_display = all_users.copy()
        if 'password' in df_display.columns:
            df_display = df_display.drop(columns=['password'])
        cols = [c for c in ['id','email','full_name','role','is_approved','created_at'] if c in df_display.columns]
        st.dataframe(df_display[cols], use_container_width=True, hide_index=True)

# ===================================================
# Standalone test
# ===================================================
if __name__ == "__main__":
    setup_auth()
