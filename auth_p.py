
import streamlit as st
from supabase import create_client
import logging
import hashlib
import time
from typing import Optional, Dict, Any
import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===================================================
# CONSTANTS
# ===================================================
SUPABASE_URL = "https://etjfrptbjecafupbbase.supabase.co"
SUPABASE_KEY = "sb_publishable_j0JwaJAJBuJO79-xh7RkYg_PFKqLK1H"
USERS_TABLE = "users_vehicle"

# ===================================================
# CACHED SUPABASE CLIENT
# ===================================================
@st.cache_resource
def get_supabase():
    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        logger.error(f"Failed to create Supabase client: {e}")
        return None

# ===================================================
# HELPER FUNCTIONS (with password hashing)
# ===================================================
def hash_password(password: str) -> str:
    """Return SHA256 hash of password."""
    return hashlib.sha256(password.encode()).hexdigest()

def get_user_from_db(email: str) -> Optional[Dict]:
    """Fetch user metadata from users_vehicle table (excluding password)."""
    if not email:
        return None
    try:
        supabase = get_supabase()
        if not supabase:
            return None
        resp = supabase.table(USERS_TABLE).select("*").eq("email", email).execute()
        if resp.data:
            user = resp.data[0]
            if 'password' in user:
                del user['password']
            return user
        return None
    except Exception as e:
        logger.error(f"Error fetching user: {e}")
        return None

def authenticate_user(email: str, password: str) -> Optional[Dict]:
    """Authenticate using hashed password stored in users_vehicle."""
    hashed = hash_password(password)
    try:
        supabase = get_supabase()
        if not supabase:
            return None
        resp = supabase.table(USERS_TABLE) \
            .select("*") \
            .eq("email", email) \
            .eq("password", hashed) \
            .execute()
        if resp.data:
            user = resp.data[0]
            if user.get('is_approved', 0) == 0:
                return {'error': 'not_approved'}
            if 'password' in user:
                del user['password']
            return user
        return None
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        return None

def create_user_in_db(email: str, full_name: str, hashed_password: str, is_admin: bool = False) -> bool:
    """Create a new user record in users_vehicle (pending approval unless admin)."""
    try:
        supabase = get_supabase()
        if not supabase:
            return False
        new_user = {
            "email": email,
            "full_name": full_name,
            "role": "admin" if is_admin else "user",
            "is_approved": 1 if is_admin else 0,
            "password": hashed_password,
        }
        resp = supabase.table(USERS_TABLE).insert(new_user).execute()
        return bool(resp.data)
    except Exception as e:
        logger.error(f"Error creating user in DB: {e}")
        return False

def get_admins_count() -> int:
    """Return number of admin users in the system."""
    try:
        supabase = get_supabase()
        if not supabase:
            return 0
        resp = supabase.table(USERS_TABLE).select("id").eq("role", "admin").execute()
        return len(resp.data) if resp.data else 0
    except Exception as e:
        logger.error(f"Error counting admins: {e}")
        return 0

# ===================================================
# AUTHENTICATION UI (with first-user-admin logic)
# ===================================================
def setup_auth() -> bool:
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
        st.session_state.user_email = None
        st.session_state.user_data = None

    if st.session_state.authenticated:
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
                        supabase = get_supabase()
                        if not supabase:
                            st.error("Database connection error")
                        else:
                            with st.spinner("Authenticating..."):
                                user = authenticate_user(email, password)
                                if user and 'error' in user:
                                    st.error("Account pending approval. Please wait for admin.")
                                elif user:
                                    st.session_state.authenticated = True
                                    st.session_state.user_email = email
                                    st.session_state.user_data = {
                                        "email": email,
                                        "full_name": user.get("full_name", ""),
                                        "role": user.get("role", "user"),
                                        "is_approved": user.get("is_approved", 0),
                                    }
                                    st.success("Login successful!")
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error("Invalid email or password")

        with tab2:
            with st.form("register_form"):
                full_name = st.text_input("Full Name", key="register_name")
                email = st.text_input("Email", key="register_email")
                password = st.text_input("Password", type="password", key="register_password")
                confirm = st.text_input("Confirm Password", type="password", key="register_confirm")
                submitted = st.form_submit_button("Register")

                if submitted:
                    if not full_name or not email or not password or not confirm:
                        st.warning("Please fill all fields")
                    elif password != confirm:
                        st.error("Passwords do not match")
                    elif len(password) < 6:
                        st.error("Password must be at least 6 characters")
                    else:
                        supabase = get_supabase()
                        if not supabase:
                            st.error("Database connection error")
                        else:
                            existing = get_user_from_db(email)
                            if existing:
                                if existing.get('is_approved') == 0:
                                    st.error("This email is already registered and pending admin approval. Please wait.")
                                else:
                                    st.error("Email already registered. Please login.")
                            else:
                                # Check if any admin exists
                                admin_count = get_admins_count()
                                is_first_admin = (admin_count == 0)

                                with st.spinner("Creating account..."):
                                    hashed = hash_password(password)
                                    success = create_user_in_db(email, full_name, hashed, is_admin=is_first_admin)
                                    if success:
                                        if is_first_admin:
                                            st.success("🎉 You are the first user! You have been granted Admin privileges and auto-approved.")
                                        else:
                                            st.success("Registration successful! Please wait for admin approval.")
                                        st.balloons()
                                    else:
                                        st.error("Registration failed. Please try again.")

        st.markdown('</div>', unsafe_allow_html=True)

    return False

# ===================================================
# EXPOSED FUNCTIONS
# ===================================================
def get_user_email() -> Optional[str]:
    return st.session_state.get("user_email")

def get_user_metadata() -> Dict[str, Any]:
    data = st.session_state.get("user_data", {})
    return {
        "full_name": data.get("full_name", "N/A"),
        "role": data.get("role", "user"),
        "is_approved": data.get("is_approved", 0),
    }

def sign_out() -> bool:
    try:
        st.session_state.clear()
        st.cache_data.clear()
        return True
    except Exception:
        return False

def get_current_user() -> Dict[str, Any]:
    return st.session_state.get("user_data", {})

def is_authenticated() -> bool:
    return st.session_state.get("authenticated", False)

# ===================================================
# USER MANAGEMENT (Admin)
# ===================================================
def get_all_users() -> list:
    try:
        supabase = get_supabase()
        if not supabase:
            return []
        resp = supabase.table(USERS_TABLE).select("*").execute()
        if resp.data:
            return [{k: v for k, v in user.items() if k != 'password'} for user in resp.data]
        return []
    except Exception as e:
        logger.error(f"Error fetching all users: {e}")
        return []

def get_pending_users() -> list:
    try:
        supabase = get_supabase()
        if not supabase:
            return []
        resp = supabase.table(USERS_TABLE).select("*").eq("is_approved", 0).execute()
        if resp.data:
            return [{k: v for k, v in user.items() if k != 'password'} for user in resp.data]
        return []
    except Exception as e:
        logger.error(f"Error fetching pending users: {e}")
        return []

def approve_user(user_id: int) -> Dict[str, Any]:
    try:
        supabase = get_supabase()
        if not supabase:
            return {"success": False, "message": "Database error"}
        resp = supabase.table(USERS_TABLE).update({"is_approved": 1}).eq("id", user_id).execute()
        if resp.data:
            st.cache_data.clear()
            return {"success": True}
        return {"success": False, "message": "No user updated"}
    except Exception as e:
        return {"success": False, "message": str(e)}

def reject_user(user_id: int) -> Dict[str, Any]:
    try:
        supabase = get_supabase()
        if not supabase:
            return {"success": False, "message": "Database error"}
        resp = supabase.table(USERS_TABLE).delete().eq("id", user_id).execute()
        if resp.data:
            st.cache_data.clear()
            return {"success": True}
        return {"success": False, "message": "No user deleted"}
    except Exception as e:
        return {"success": False, "message": str(e)}

def admin_panel():
    if not is_authenticated() or st.session_state.get("user_data", {}).get("role") != "admin":
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
        admins = len([u for u in all_users if u.get('role') == 'admin'])
        st.metric("Admins", admins)
    if pending:
        st.subheader("📋 Pending Approvals")
        for user in pending:
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([2,2,1,1])
                with c1:
                    st.write(f"**{user.get('full_name','N/A')}**")
                with c2:
                    st.write(user.get('email'))
                with c3:
                    if st.button("✅ Approve", key=f"app_{user['id']}"):
                        res = approve_user(user['id'])
                        if res["success"]:
                            st.success("Approved!")
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error(res.get("message","Error"))
                with c4:
                    if st.button("❌ Reject", key=f"rej_{user['id']}"):
                        res = reject_user(user['id'])
                        if res["success"]:
                            st.warning("Rejected.")
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error(res.get("message","Error"))
    else:
        st.info("✅ No pending approvals")
    if all_users:
        st.subheader("📊 All Users")
        df = pd.DataFrame(all_users)
        cols = [c for c in ['id','email','full_name','role','is_approved','created_at'] if c in df.columns]
        st.dataframe(df[cols], use_container_width=True, hide_index=True)
