
import streamlit as st
from supabase import create_client
import logging
from typing import Optional, Dict, Any

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
# HELPER FUNCTIONS
# ===================================================
def get_user_from_db(email: str) -> Optional[Dict]:
    """Fetch user metadata from users_vehicle table."""
    if not email:
        return None
    try:
        supabase = get_supabase()
        if not supabase:
            return None
        resp = supabase.table(USERS_TABLE).select("*").eq("email", email).execute()
        if resp.data:
            return resp.data[0]
        return None
    except Exception as e:
        logger.error(f"Error fetching user: {e}")
        return None

def create_user_in_db(email: str, full_name: str) -> bool:
    """Create a new user record in users_vehicle (pending approval)."""
    try:
        supabase = get_supabase()
        if not supabase:
            return False
        new_user = {
            "email": email,
            "full_name": full_name,
            "role": "user",
            "is_approved": 0,
        }
        resp = supabase.table(USERS_TABLE).insert(new_user).execute()
        return bool(resp.data)
    except Exception as e:
        logger.error(f"Error creating user in DB: {e}")
        return False

# ===================================================
# AUTHENTICATION FUNCTIONS (UI + Logic)
# ===================================================
def setup_auth() -> bool:
    """Show login/register UI and handle authentication."""
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
        st.session_state.user_email = None
        st.session_state.user_data = None

    if st.session_state.authenticated:
        return True

    st.title("🚚 Fleet Management System")
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
                        try:
                            # Sign in with Supabase Auth
                            auth_resp = supabase.auth.sign_in_with_password({
                                "email": email,
                                "password": password
                            })
                            if auth_resp.user:
                                # Fetch role & approval from users_vehicle
                                user_meta = get_user_from_db(email)
                                if not user_meta:
                                    st.error("User account not found in system. Please register.")
                                elif user_meta.get("is_approved") != 1:
                                    st.error("Account pending approval. Please wait for admin.")
                                else:
                                    st.session_state.authenticated = True
                                    st.session_state.user_email = email
                                    st.session_state.user_data = {
                                        "email": email,
                                        "full_name": user_meta.get("full_name", ""),
                                        "role": user_meta.get("role", "user"),
                                        "is_approved": user_meta.get("is_approved", 0),
                                    }
                                    st.rerun()
                            else:
                                st.error("Invalid email or password")
                        except Exception as e:
                            st.error(f"Login error: {str(e)}")

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
                else:
                    supabase = get_supabase()
                    if not supabase:
                        st.error("Database connection error")
                    else:
                        try:
                            # Check if already registered in our table
                            existing = get_user_from_db(email)
                            if existing:
                                st.error("Email already registered. Please login.")
                            else:
                                # Create user in Supabase Auth
                                auth_resp = supabase.auth.sign_up({
                                    "email": email,
                                    "password": password,
                                })
                                if auth_resp.user:
                                    # Create record in users_vehicle (pending)
                                    if create_user_in_db(email, full_name):
                                        st.success("Registration successful! Please wait for admin approval.")
                                    else:
                                        st.error("Registration failed: could not save user data")
                                else:
                                    st.error("Registration failed. Email may already be in use.")
                        except Exception as e:
                            st.error(f"Registration error: {str(e)}")

    return False

# ===================================================
# EXPOSED FUNCTIONS (for vehicle_assignment.py)
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
        supabase = get_supabase()
        if supabase:
            supabase.auth.sign_out()
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
        return resp.data if resp.data else []
    except Exception as e:
        logger.error(f"Error fetching all users: {e}")
        return []

def get_pending_users() -> list:
    try:
        supabase = get_supabase()
        if not supabase:
            return []
        resp = supabase.table(USERS_TABLE).select("*").eq("is_approved", 0).execute()
        return resp.data if resp.data else []
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

# ===================================================
# OPTIONAL ADMIN PANEL WIDGET (if needed)
# ===================================================
def admin_panel():
    """Standalone admin panel widget for use in main app."""
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
