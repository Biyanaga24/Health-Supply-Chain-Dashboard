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
USERS_TABLE = "users_vehicle"

@st.cache_resource
def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = get_supabase()

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
    try:
        resp = supabase.table(USERS_TABLE).select("id").eq("role", "admin").execute()
        return len(resp.data) if resp.data else 0
    except:
        return 0

# ===================================================
# EXPORTED INTERFACE
# ===================================================

def setup_auth() -> bool:
    if 'authenticated' in st.session_state and st.session_state.authenticated:
        return True

    st.markdown("""
    <style>
        /* Force Times New Roman everywhere */
        * {
            font-family: 'Times New Roman', Times, serif !important;
        }
        .stApp { background-color: #f5f7fa; }
        .stButton button { 
            background-color: #FF8C00 !important; 
            color: white !important; 
            border-radius: 8px !important; 
            font-weight: bold !important; 
            border: none !important; 
            font-family: 'Times New Roman', Times, serif !important;
        }
        .stButton button:hover { 
            background-color: #e67e00 !important; 
            box-shadow: 0 4px 12px rgba(255,140,0,0.4) !important; 
        }
        .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p { 
            font-weight: 600 !important; 
            color: #333 !important; 
        }
        .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] { 
            border-bottom: 3px solid #FF8C00 !important; 
        }
        h1, h2, h3 { 
            color: #1E88E5 !important; 
            font-family: 'Times New Roman', Times, serif !important;
        }

        /* Big card – centered with strong visible edges */
        .big-card-wrapper {
            display: flex;
            justify-content: center;
            margin: 1rem 0;
        }
        .big-card {
            background: white;
            padding: 2rem 2.5rem;
            border-radius: 20px;
            border: 4px solid #1E88E5;
            box-shadow: 0 8px 30px rgba(30, 136, 229, 0.3);
            max-width: 1100px;
            width: 100%;
            border-left: 8px solid #1E88E5;
            border-right: 8px solid #1E88E5;
        }
        .big-card h2 {
            color: #1E88E5;
            margin-top: 0;
            font-size: 1.6rem;
        }

        /* Feature cards grid – white background */
        .feature-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1rem;
            margin: 1.2rem 0;
        }
        .feature-card {
            background: white;
            border: 1px solid #d0d7e3;
            border-radius: 12px;
            padding: 1rem 1.2rem;
            box-shadow: 0 2px 6px rgba(0,0,0,0.04);
            transition: all 0.2s ease;
        }
        .feature-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 16px rgba(30, 136, 229, 0.15);
            border-color: #1E88E5;
        }
        .feature-card strong {
            color: #1E88E5;
            font-size: 1.05rem;
            display: block;
            margin-bottom: 0.2rem;
        }
        .feature-card p {
            margin: 0;
            font-size: 0.95rem;
            color: #333;
            line-height: 1.4;
        }

        /* Auth container – pure white background */
        .auth-container {
            background: white !important;
            padding: 1.2rem 1.8rem;
            border-radius: 16px;
            border: 1px solid #d0d7e3;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        }
        /* Force white background for auth container and all its children */
        .auth-container,
        .auth-container .stTabs,
        .auth-container .stTabs [data-baseweb="tab-list"],
        .auth-container .stTabs [data-baseweb="tab-panel"],
        .auth-container .stForm,
        .auth-container .stTextInput > div > div > input,
        .auth-container .stTextInput > div > div {
            background-color: white !important;
        }
        /* Ensure the tab panels and forms inside are white */
        .auth-container .stTabs [data-baseweb="tab-panel"] {
            background-color: white !important;
        }
        .auth-container .stForm {
            background-color: white !important;
        }
        .auth-container .stTextInput > div > div > input {
            background-color: white !important;
        }

        .stTextInput > div > div > input { border-radius: 8px; }

        /* Slow moving title */
        @keyframes slideTitle {
            0% { transform: translateX(-20px); opacity: 0; }
            20% { opacity: 1; }
            80% { opacity: 1; }
            100% { transform: translateX(20px); opacity: 0; }
        }
        .moving-title {
            display: inline-block;
            animation: slideTitle 6s ease-in-out infinite;
            animation-direction: alternate;
        }

        /* Responsive */
        @media (max-width: 768px) {
            .big-card { padding: 1.5rem; border-width: 3px; border-left-width: 4px; border-right-width: 4px; }
            .auth-container { margin-top: 1.5rem; }
            .feature-grid { grid-template-columns: 1fr; }
        }
    </style>
    """, unsafe_allow_html=True)

    # Animated title
    st.markdown(
        "<h1 style='text-align: center; color: #1E88E5;'>"
        "<span class='moving-title'>🚚 EPSS Fleet Management System</span>"
        "</h1>",
        unsafe_allow_html=True
    )

    st.markdown('<div class="big-card-wrapper"><div class="big-card">', unsafe_allow_html=True)

    col_left, col_right = st.columns([2.2, 1], gap="large")

    with col_left:
        st.markdown("""
        <h2>📊 Dashboard Overview</h2>
        <p style="font-size:1rem;">
            Welcome to the <strong>Ethiopian Pharmaceutical Supply Service (EPSS)</strong> fleet management system.
            This dashboard provides all the tools to manage your vehicle fleet efficiently.
        </p>
        <div class="feature-grid">
            <div class="feature-card">
                <strong>📋 Trip Management</strong>
                <p>Plan, assign, and track trips with real‑time status updates.</p>
            </div>
            <div class="feature-card">
                <strong>📊 KPIs & Analysis</strong>
                <p>Monitor utilisation, OTD, trip variance, and idle times.</p>
            </div>
            <div class="feature-card">
                <strong>🔧 Vehicle Maintenance</strong>
                <p>Record maintenance events, costs, and service history.</p>
            </div>
            <div class="feature-card">
                <strong>👑 Admin Panel</strong>
                <p>Manage users, roles, and vehicle master data.</p>
            </div>
            <div class="feature-card" style="grid-column: span 2;">
                <strong>🔐 Role‑Based Access</strong>
                <p>Secure access tailored to each user's responsibilities.</p>
            </div>
        </div>
        <p style="margin-top:0.8rem; font-style:italic; font-size:0.95rem;">
            Log in or register to access your personalised dashboard.
        </p>
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
                            admin_count = get_admin_count()
                            is_first = (admin_count == 0)

                            success, message = create_user(email, password, full_name)
                            if success:
                                if is_first:
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

    st.markdown('</div></div>', unsafe_allow_html=True)

    return False

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
# ADMIN PANEL
# ===================================================

def admin_panel():
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
